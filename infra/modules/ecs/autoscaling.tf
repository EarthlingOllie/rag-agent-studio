# Autoscaling (ticket 22-05, ADR-0021). The API tracks average CPU. Each worker pool follows its queue's jobs, waiting
# plus in flight: a worker takes a message only when it has a free slot and deletes it when the job ends
# (task_acks_late), so a job being worked on stays in flight and keeps its task counted. Beat is not scaled.
#
# A worker pool has two step policies, each driven by a CloudWatch alarm on that sum:
#   - jobs: while the queue holds at least one job, the pool runs one task per jobs_per_task jobs (the slots a task
#     has), up to its maximum, so the runs pool goes from zero to one as soon as anything is queued. As jobs drain, the
#     count follows them down but never below the tasks the in-flight jobs need; task protection (ticket 22-06) makes
#     ECS stop an idle task, not a busy one.
#   - idle: once the queue has held no job for idle_minutes, the pool goes back to its minimum (zero for the runs pool).
# ECS reports no CPU for a service at zero tasks, which is why the workers scale on their queue (spec 22 risks).
locals {
  scaled = toset(["api", "worker-general", "worker-runs"])

  worker_queues = { "worker-general" = var.queues.general.name, "worker-runs" = var.queues.runs.name }

  # Step bounds are relative to the jobs alarm's threshold of one job, lower bound inclusive and upper exclusive:
  # with two slots, 1-2 jobs is one task, 3-4 two, and so on; the last step has no upper bound.
  worker_steps = { for k in local.workers : k => [for n in range(1, var.scaling[k].max + 1) : {
    lower    = tostring((n - 1) * var.scaling[k].jobs_per_task)
    upper    = n == var.scaling[k].max ? null : tostring(n * var.scaling[k].jobs_per_task)
    capacity = n
  }] }
}

resource "aws_appautoscaling_target" "this" {
  for_each = local.scaled

  service_namespace  = "ecs"
  scalable_dimension = "ecs:service:DesiredCount"
  resource_id        = "service/${aws_ecs_cluster.this.name}/${aws_ecs_service.this[each.key].name}"
  min_capacity       = var.scaling[each.key].min
  max_capacity       = var.scaling[each.key].max

  tags = merge(local.tags, { Name = "${local.name}-${each.key}" })
}

resource "aws_appautoscaling_policy" "api_cpu" {
  name               = "${local.name}-api-cpu"
  policy_type        = "TargetTrackingScaling"
  service_namespace  = aws_appautoscaling_target.this["api"].service_namespace
  scalable_dimension = aws_appautoscaling_target.this["api"].scalable_dimension
  resource_id        = aws_appautoscaling_target.this["api"].resource_id

  target_tracking_scaling_policy_configuration {
    target_value       = var.scaling.api.cpu_target
    scale_out_cooldown = var.scaling.api.scale_out_cooldown
    scale_in_cooldown  = var.scaling.api.scale_in_cooldown

    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
  }
}

resource "aws_appautoscaling_policy" "worker_jobs" {
  for_each = local.workers

  name               = "${local.name}-${each.key}-jobs"
  policy_type        = "StepScaling"
  service_namespace  = aws_appautoscaling_target.this[each.key].service_namespace
  scalable_dimension = aws_appautoscaling_target.this[each.key].scalable_dimension
  resource_id        = aws_appautoscaling_target.this[each.key].resource_id

  step_scaling_policy_configuration {
    adjustment_type         = "ExactCapacity"
    cooldown                = var.scaling[each.key].scale_out_cooldown
    metric_aggregation_type = "Maximum"

    dynamic "step_adjustment" {
      for_each = local.worker_steps[each.key]

      content {
        metric_interval_lower_bound = step_adjustment.value.lower
        metric_interval_upper_bound = step_adjustment.value.upper
        scaling_adjustment          = step_adjustment.value.capacity
      }
    }
  }
}

resource "aws_appautoscaling_policy" "worker_idle" {
  for_each = local.workers

  name               = "${local.name}-${each.key}-idle"
  policy_type        = "StepScaling"
  service_namespace  = aws_appautoscaling_target.this[each.key].service_namespace
  scalable_dimension = aws_appautoscaling_target.this[each.key].scalable_dimension
  resource_id        = aws_appautoscaling_target.this[each.key].resource_id

  step_scaling_policy_configuration {
    adjustment_type         = "ExactCapacity"
    cooldown                = var.scaling[each.key].scale_in_cooldown
    metric_aggregation_type = "Maximum"

    step_adjustment {
      metric_interval_upper_bound = "0"
      scaling_adjustment          = var.scaling[each.key].min
    }
  }
}

resource "aws_cloudwatch_metric_alarm" "worker_jobs" {
  for_each = local.workers

  alarm_name          = "${local.name}-${each.key}-jobs"
  alarm_description   = "${each.key}: its queue holds jobs, waiting or in flight. Drives the pool's jobs scaling policy."
  comparison_operator = "GreaterThanOrEqualToThreshold"
  threshold           = 1
  evaluation_periods  = 1
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_appautoscaling_policy.worker_jobs[each.key].arn]

  metric_query {
    id = "waiting"
    metric {
      namespace   = "AWS/SQS"
      metric_name = "ApproximateNumberOfMessagesVisible"
      dimensions  = { QueueName = local.worker_queues[each.key] }
      period      = 60
      stat        = "Maximum"
    }
  }

  metric_query {
    id = "in_flight"
    metric {
      namespace   = "AWS/SQS"
      metric_name = "ApproximateNumberOfMessagesNotVisible"
      dimensions  = { QueueName = local.worker_queues[each.key] }
      period      = 60
      stat        = "Maximum"
    }
  }

  metric_query {
    id          = "jobs"
    expression  = "waiting + in_flight"
    label       = "Jobs waiting or in flight"
    return_data = true
  }

  tags = merge(local.tags, { Name = "${local.name}-${each.key}-jobs" })
}

# SQS stops sending metrics for a queue that has been idle for a while, so missing data counts as empty here.
resource "aws_cloudwatch_metric_alarm" "worker_idle" {
  for_each = local.workers

  alarm_name          = "${local.name}-${each.key}-idle"
  alarm_description   = "${each.key}: its queue has held no job for ${var.scaling[each.key].idle_minutes} minutes. Returns the pool to its minimum."
  comparison_operator = "LessThanThreshold"
  threshold           = 1
  evaluation_periods  = var.scaling[each.key].idle_minutes
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_appautoscaling_policy.worker_idle[each.key].arn]

  metric_query {
    id = "waiting"
    metric {
      namespace   = "AWS/SQS"
      metric_name = "ApproximateNumberOfMessagesVisible"
      dimensions  = { QueueName = local.worker_queues[each.key] }
      period      = 60
      stat        = "Maximum"
    }
  }

  metric_query {
    id = "in_flight"
    metric {
      namespace   = "AWS/SQS"
      metric_name = "ApproximateNumberOfMessagesNotVisible"
      dimensions  = { QueueName = local.worker_queues[each.key] }
      period      = 60
      stat        = "Maximum"
    }
  }

  metric_query {
    id          = "jobs"
    expression  = "waiting + in_flight"
    label       = "Jobs waiting or in flight"
    return_data = true
  }

  tags = merge(local.tags, { Name = "${local.name}-${each.key}-idle" })
}
