output "name" {
  description = "Name the module gives its resources."
  value       = local.name
}

output "tags" {
  description = "Tags the module applies to its resources."
  value       = local.tags
}

output "queues" {
  description = "The general and runs queues: each one's name (the services' settings), URL and ARN (for IAM policies)."
  value       = { for k, q in aws_sqs_queue.this : k => { name = q.name, url = q.url, arn = q.arn } }
}

output "dead_letter_queues" {
  description = "Each queue's dead-letter queue: name, URL and ARN."
  value       = { for k, q in aws_sqs_queue.dead_letter : k => { name = q.name, url = q.url, arn = q.arn } }
}

output "dead_letter_alarm_names" {
  description = "Name of the CloudWatch alarm on each dead-letter queue's depth."
  value       = { for k, a in aws_cloudwatch_metric_alarm.dead_letter : k => a.alarm_name }
}
