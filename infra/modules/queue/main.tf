# Queue module (ticket 22-02): the general and runs SQS queues that carry jobs to the two worker pools (ADR-0021).
# Each queue sets a message aside on its own dead-letter queue after repeated failed deliveries, and an alarm shows
# it in the console. Messages carry only identifiers (ADR-0020), and every queue is encrypted at rest.
locals {
  module_name = "queue"
  name        = "${var.name_prefix}-${local.module_name}"
  tags        = merge(var.tags, { Module = local.module_name, ManagedBy = "terraform" })

  # How long a received message stays hidden. A redelivered copy of a job that is still running fails its claim
  # and exits (ADR-0020), so these keep things tidy rather than correct.
  visibility_timeouts = {
    general = var.general_visibility_timeout_seconds
    runs    = var.runs_visibility_timeout_seconds
  }

  dead_letter_retention_seconds = 1209600 # 14 days, the SQS maximum.
}

# SSE-SQS rather than a customer key: no key policy grants for every sender and receiver, and no KMS request costs.
resource "aws_sqs_queue" "dead_letter" {
  for_each = local.visibility_timeouts

  name                      = "${local.name}-${each.key}-dlq"
  message_retention_seconds = local.dead_letter_retention_seconds
  sqs_managed_sse_enabled   = true

  tags = merge(local.tags, { Name = "${local.name}-${each.key}-dlq" })
}

resource "aws_sqs_queue" "this" {
  for_each = local.visibility_timeouts

  name                       = "${local.name}-${each.key}"
  visibility_timeout_seconds = each.value
  message_retention_seconds  = var.message_retention_seconds
  receive_wait_time_seconds  = 20 # Long polling: fewer empty receives while a pool waits for work.
  sqs_managed_sse_enabled    = true

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dead_letter[each.key].arn
    maxReceiveCount     = var.max_receive_count
  })

  tags = merge(local.tags, { Name = "${local.name}-${each.key}" })
}

# Set separately from the dead-letter queue, which the source queue's redrive policy already refers to.
resource "aws_sqs_queue_redrive_allow_policy" "dead_letter" {
  for_each = local.visibility_timeouts

  queue_url = aws_sqs_queue.dead_letter[each.key].id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.this[each.key].arn]
  })
}

# No notification target: the alarm is for the console (spec 22).
resource "aws_cloudwatch_metric_alarm" "dead_letter" {
  for_each = local.visibility_timeouts

  alarm_name          = "${aws_sqs_queue.dead_letter[each.key].name}-depth"
  alarm_description   = "A ${each.key} job was set aside after ${var.max_receive_count} failed deliveries: look at ${aws_sqs_queue.dead_letter[each.key].name}."
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = aws_sqs_queue.dead_letter[each.key].name }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  comparison_operator = "GreaterThanThreshold"
  threshold           = 0
  treat_missing_data  = "notBreaching"

  tags = merge(local.tags, { Name = "${aws_sqs_queue.dead_letter[each.key].name}-depth" })
}
