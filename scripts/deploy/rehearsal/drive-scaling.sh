#!/usr/bin/env bash
# Publishes, during `make rehearse-scale` (ticket 23-05), the two figures Floci does not compute for itself, so its
# alarms and Application Auto Scaling scale the rehearsal's services as CloudWatch would on AWS:
#   - each worker pool's jobs, waiting plus in flight, read from its queue: the single metric (<namespace>/Jobs, by
#     QueueName) the pools' alarms watch in `local`, because Floci never evaluates the metric-math alarms the demo uses
#     (ticket 23-01) and does not run a step policy on an alarm state set by hand (ticket 23-05)
#   - the API service's average CPU (AWS/ECS CPUUtilization, by ClusterName and ServiceName), which Floci does not
#     synthesise: measured with `docker stats` on the API's task containers (Floci names them
#     floci-aws-ecs-<task id>-api) as a share of the CPUs each task has
# It runs every REHEARSAL_DRIVE_SECONDS (default 15) until stopped, or once with --once. A failed publish is reported
# and the next pass tries again. aws is the rehearsal's (scripts/deploy/rehearsal), pointed at Floci.
# Usage: drive-scaling.sh [--once] <cluster> <api service> <general queue> <runs queue> <metric namespace>
set -uo pipefail

once=false
[ "${1:-}" = --once ] && { once=true; shift; }
[ $# = 5 ] || { echo "usage: $0 [--once] <cluster> <api service> <general queue> <runs queue> <metric namespace>" >&2; exit 2; }
cluster=$1 api_service=$2 namespace=$5
queues=("$3" "$4")
urls=()
for queue in "${queues[@]}"; do
  urls+=("$(aws sqs get-queue-url --queue-name "$queue" --query QueueUrl --output text)")
done

warn() { echo "drive-scaling: $*" >&2; }

# jobs <queue url>: the queue's waiting plus in-flight messages.
jobs() {
  aws sqs get-queue-attributes --queue-url "$1" --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible \
    --query 'Attributes.[ApproximateNumberOfMessages,ApproximateNumberOfMessagesNotVisible]' --output text |
    awk '{ print $1 + $2 }'
}

# api_cpu: the API tasks' average CPU as a percentage of their task size, or nothing when no API task runs.
api_cpu() {
  local names=() name cpus total=0 count=0 percent
  while read -r name; do [[ "$name" == floci-aws-ecs-*-api ]] && names+=("$name"); done < <(docker ps --filter label=io.floci.service=ecs --format '{{.Names}}')
  [ ${#names[@]} -gt 0 ] || return 0
  while read -r name percent; do
    cpus=$(docker inspect --format '{{.HostConfig.NanoCpus}}' "$name")
    total=$(awk -v t="$total" -v p="${percent%\%}" -v c="$cpus" 'BEGIN { print t + (c > 0 ? p / (c / 1e9) : p) }')
    count=$((count + 1))
  done < <(docker stats --no-stream --format '{{.Name}} {{.CPUPerc}}' "${names[@]}")
  [ "$count" -gt 0 ] && awk -v t="$total" -v n="$count" 'BEGIN { printf "%.0f\n", t / n }'
}

publish() {
  local data="" i cpu
  for i in 0 1; do
    data+="${data:+,}{\"MetricName\":\"Jobs\",\"Dimensions\":[{\"Name\":\"QueueName\",\"Value\":\"${queues[i]}\"}],\"Value\":$(jobs "${urls[i]}"),\"Unit\":\"Count\"}"
  done
  aws cloudwatch put-metric-data --namespace "$namespace" --metric-data "[$data]" || warn "Could not publish the queues' jobs."
  cpu=$(api_cpu)
  [ -z "$cpu" ] || aws cloudwatch put-metric-data --namespace AWS/ECS --metric-data \
    "[{\"MetricName\":\"CPUUtilization\",\"Dimensions\":[{\"Name\":\"ClusterName\",\"Value\":\"$cluster\"},{\"Name\":\"ServiceName\",\"Value\":\"$api_service\"}],\"Value\":$cpu,\"Unit\":\"Percent\"}]" ||
    warn "Could not publish the API's CPU."
}

publish
[ "$once" = true ] && exit 0
while sleep "${REHEARSAL_DRIVE_SECONDS:-15}"; do publish; done
