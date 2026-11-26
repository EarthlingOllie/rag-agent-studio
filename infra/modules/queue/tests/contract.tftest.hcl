# Module contract for the queue module (ticket 22-02), at the module seam, with a mocked AWS provider.
# Runs that compare ARNs or URLs use `command = apply`: the mock provider only invents them at apply time,
# and it never calls AWS, so apply here creates nothing real.
mock_provider "aws" {}

# Real-looking ARNs and URLs, so the redrive policies and outputs are shown to name the right queues.
override_resource {
  target = aws_sqs_queue.this["general"]
  values = {
    arn = "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-general"
    url = "https://sqs.eu-west-2.amazonaws.com/123456789012/studio-demo-queue-general"
  }
}

override_resource {
  target = aws_sqs_queue.this["runs"]
  values = {
    arn = "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-runs"
    url = "https://sqs.eu-west-2.amazonaws.com/123456789012/studio-demo-queue-runs"
  }
}

override_resource {
  target = aws_sqs_queue.dead_letter["general"]
  values = { arn = "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-general-dlq" }
}

override_resource {
  target = aws_sqs_queue.dead_letter["runs"]
  values = { arn = "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-runs-dlq" }
}

variables {
  name_prefix = "studio-demo"
  tags        = { Environment = "demo", Project = "rag-agent-studio" }
}

run "creates_the_general_and_runs_queues_each_with_a_dead_letter_queue" {
  command = plan

  assert {
    condition     = { for k, q in aws_sqs_queue.this : k => q.name } == { general = "studio-demo-queue-general", runs = "studio-demo-queue-runs" }
    error_message = "The module must create the general and runs queues, named from the prefix."
  }

  assert {
    condition     = { for k, q in aws_sqs_queue.dead_letter : k => q.name } == { general = "studio-demo-queue-general-dlq", runs = "studio-demo-queue-runs-dlq" }
    error_message = "Each queue must have its own dead-letter queue."
  }

  assert {
    condition     = alltrue([for q in aws_sqs_queue.dead_letter : q.message_retention_seconds == 1209600])
    error_message = "A set-aside message must be kept for the SQS maximum of 14 days, so it can be looked at."
  }
}

run "redrives_a_message_to_its_dead_letter_queue_after_the_redrive_limit" {
  command = apply

  assert {
    condition = { for k, q in aws_sqs_queue.this : k => jsondecode(q.redrive_policy) } == {
      general = { deadLetterTargetArn = "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-general-dlq", maxReceiveCount = 5 }
      runs    = { deadLetterTargetArn = "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-runs-dlq", maxReceiveCount = 5 }
    }
    error_message = "Each queue must move a message to its own dead-letter queue after five failed deliveries."
  }

  assert {
    condition = { for k, p in aws_sqs_queue_redrive_allow_policy.dead_letter : k => jsondecode(p.redrive_allow_policy) } == {
      general = { redrivePermission = "byQueue", sourceQueueArns = ["arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-general"] }
      runs    = { redrivePermission = "byQueue", sourceQueueArns = ["arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-runs"] }
    }
    error_message = "Each dead-letter queue must accept messages from its own queue only."
  }

  assert {
    condition     = alltrue([for k, p in aws_sqs_queue_redrive_allow_policy.dead_letter : p.queue_url == aws_sqs_queue.dead_letter[k].id])
    error_message = "Each redrive allow policy must be set on its own dead-letter queue."
  }
}

run "the_redrive_limit_is_a_variable" {
  command = apply

  variables {
    max_receive_count = 3
  }

  assert {
    condition     = alltrue([for q in aws_sqs_queue.this : jsondecode(q.redrive_policy).maxReceiveCount == 3])
    error_message = "max_receive_count must set the redrive limit of both queues."
  }
}

run "rejects_a_redrive_limit_sqs_does_not_accept" {
  command = plan

  variables {
    max_receive_count = 0
  }

  expect_failures = [var.max_receive_count]
}

run "visibility_timeouts_are_an_hour_on_general_and_twelve_hours_on_runs" {
  command = plan

  assert {
    condition     = aws_sqs_queue.this["general"].visibility_timeout_seconds == 3600 && aws_sqs_queue.this["runs"].visibility_timeout_seconds == 43200
    error_message = "A normal job must not be redelivered while it runs: one hour on general, twelve hours (the SQS maximum) on runs."
  }
}

run "visibility_timeouts_are_variables" {
  command = plan

  variables {
    general_visibility_timeout_seconds = 1800
    runs_visibility_timeout_seconds    = 7200
  }

  assert {
    condition     = aws_sqs_queue.this["general"].visibility_timeout_seconds == 1800 && aws_sqs_queue.this["runs"].visibility_timeout_seconds == 7200
    error_message = "Both visibility timeouts must be variables."
  }
}

run "rejects_a_visibility_timeout_above_the_sqs_maximum" {
  command = plan

  variables {
    runs_visibility_timeout_seconds = 43201
  }

  expect_failures = [var.runs_visibility_timeout_seconds]
}

run "rejects_a_negative_visibility_timeout" {
  command = plan

  variables {
    general_visibility_timeout_seconds = -1
  }

  expect_failures = [var.general_visibility_timeout_seconds]
}

run "encrypts_every_queue_at_rest" {
  command = plan

  assert {
    condition     = alltrue([for q in concat(values(aws_sqs_queue.this), values(aws_sqs_queue.dead_letter)) : q.sqs_managed_sse_enabled == true])
    error_message = "Every queue and dead-letter queue must be encrypted at rest (SSE-SQS)."
  }
}

run "alarms_on_each_dead_letter_queues_depth" {
  command = plan

  assert {
    condition     = { for k, a in aws_cloudwatch_metric_alarm.dead_letter : k => a.alarm_name } == { general = "studio-demo-queue-general-dlq-depth", runs = "studio-demo-queue-runs-dlq-depth" }
    error_message = "Each dead-letter queue must have its own alarm."
  }

  assert {
    condition = alltrue([for k, a in aws_cloudwatch_metric_alarm.dead_letter :
      a.namespace == "AWS/SQS" && a.metric_name == "ApproximateNumberOfMessagesVisible" &&
      a.dimensions.QueueName == "studio-demo-queue-${k}-dlq" && length(a.dimensions) == 1 &&
      a.statistic == "Maximum" && a.comparison_operator == "GreaterThanThreshold" && a.threshold == 0 &&
      a.treat_missing_data == "notBreaching"
    ])
    error_message = "An alarm must fire as soon as its dead-letter queue holds a message, and stay quiet while it is empty."
  }

  assert {
    condition     = alltrue([for a in aws_cloudwatch_metric_alarm.dead_letter : length(coalesce(a.alarm_actions, [])) == 0])
    error_message = "The alarms have no notification target: they are for the console (spec 22)."
  }
}

run "outputs_each_queues_name_url_and_arn" {
  command = apply

  assert {
    condition = output.queues == {
      general = {
        name = "studio-demo-queue-general"
        url  = "https://sqs.eu-west-2.amazonaws.com/123456789012/studio-demo-queue-general"
        arn  = "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-general"
      }
      runs = {
        name = "studio-demo-queue-runs"
        url  = "https://sqs.eu-west-2.amazonaws.com/123456789012/studio-demo-queue-runs"
        arn  = "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-runs"
      }
    }
    error_message = "The module must output each queue's name, URL and ARN."
  }

  assert {
    condition = { for k, q in output.dead_letter_queues : k => [q.name, q.arn] } == {
      general = ["studio-demo-queue-general-dlq", "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-general-dlq"]
      runs    = ["studio-demo-queue-runs-dlq", "arn:aws:sqs:eu-west-2:123456789012:studio-demo-queue-runs-dlq"]
    }
    error_message = "The module must output each dead-letter queue's name, URL and ARN."
  }

  assert {
    condition     = output.dead_letter_alarm_names == { general = "studio-demo-queue-general-dlq-depth", runs = "studio-demo-queue-runs-dlq-depth" }
    error_message = "The module must output the alarm names."
  }

  assert {
    condition     = output.name == "studio-demo-queue"
    error_message = "The module must output its name."
  }
}

run "every_resource_carries_the_standard_tags" {
  command = plan

  assert {
    condition = alltrue([for t in concat(
      [for q in aws_sqs_queue.this : q.tags],
      [for q in aws_sqs_queue.dead_letter : q.tags],
      [for a in aws_cloudwatch_metric_alarm.dead_letter : a.tags],
    ) : t.Project == "rag-agent-studio" && t.Environment == "demo" && t.Module == "queue" && t.ManagedBy == "terraform"])
    error_message = "Every resource must carry the standard tags."
  }

  assert {
    condition     = output.tags == { Environment = "demo", Project = "rag-agent-studio", Module = "queue", ManagedBy = "terraform" }
    error_message = "The module must output its tags."
  }
}

run "rejects_tags_without_project_and_environment" {
  command = plan

  variables {
    tags = { Project = "rag-agent-studio" }
  }

  expect_failures = [var.tags]
}

run "rejects_an_invalid_prefix" {
  command = plan

  variables {
    name_prefix = "Studio_Demo"
  }

  expect_failures = [var.name_prefix]
}
