#!/usr/bin/env bash
# Tests for scripts/deploy/rehearsal/drive-scaling.sh (ticket 23-05), which publishes what Floci does not compute for
# itself during `make rehearse-scale`: each worker pool's jobs (waiting plus in flight) as the single metric its alarms
# watch in `local`, and the API service's CPU. aws and docker are stubs that log each call and answer from STUB_*
# variables; nothing calls the emulator or starts a container.
# Usage: scripts/deploy/tests/drive-scaling.test.sh
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
drive="$here/../rehearsal/drive-scaling.sh"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
failures=0
fail() { echo "FAIL $1: $2"; failures=$((failures + 1)); }

mkdir -p "$work/bin"
# aws: queue URLs from the name, queue attributes from STUB_<QUEUE>_DEPTH ("<waiting> <in flight>").
cat >"$work/bin/aws" <<'EOF'
#!/usr/bin/env bash
echo "aws $*" >>"$STUB_CALLS"
case "$1 $2" in
  "sqs get-queue-url") echo "https://floci:4566/000000000000/$4" ;;
  "sqs get-queue-attributes")
    case "$4" in
      *general) printf '%s\t%s\n' ${STUB_GENERAL_DEPTH:-0 0} ;;
      *runs) printf '%s\t%s\n' ${STUB_RUNS_DEPTH:-0 0} ;;
    esac ;;
  "cloudwatch put-metric-data") exit "${STUB_PUT_EXIT:-0}" ;;
esac
EOF
# docker: the running containers and their CPU from STUB_CONTAINERS ("<name> <CPU %> <nano CPUs>" per line).
cat >"$work/bin/docker" <<'EOF'
#!/usr/bin/env bash
echo "docker $*" >>"$STUB_CALLS"
case "$1" in
  ps) awk 'NF { print $1 }' <<<"${STUB_CONTAINERS:-}" ;;
  stats) while read -r n cpu _; do [[ " $* " == *" $n "* ]] && echo "$n $cpu"; done <<<"${STUB_CONTAINERS:-}" ;;
  inspect) awk -v n="${*: -1}" '$1 == n { print $3 }' <<<"${STUB_CONTAINERS:-}" ;;
esac
EOF
chmod +x "$work/bin/aws" "$work/bin/docker"

# run <case> [VAR=value...]: one pass of the driver; sets $status, $out, $calls.
run() {
  local name=$1
  shift
  : >"$work/$name.calls"
  out=$(env PATH="$work/bin:$PATH" STUB_CALLS="$work/$name.calls" "$@" \
    "$drive" --once studio-local-ecs studio-local-ecs-api studio-local-queue-general studio-local-queue-runs Rehearsal/SQS 2>&1)
  status=$?
  calls=$(cat "$work/$name.calls")
}
has() { grep -qF -- "$2" <<<"$calls" || { fail "$1" "no call with '$2' in: $calls"; return 1; }; }
never() { if grep -qE -- "$2" <<<"$calls"; then fail "$1" "unexpected call matching '$2'"; return 1; fi; }

name=publishes_each_pools_waiting_plus_in_flight_jobs_as_the_metric_its_alarms_watch
run $name STUB_GENERAL_DEPTH="3 2" STUB_RUNS_DEPTH="0 1"
ok=1
[ "$status" = 0 ] || { fail $name "exit $status: $out"; ok=0; }
has $name 'aws cloudwatch put-metric-data --namespace Rehearsal/SQS --metric-data [{"MetricName":"Jobs","Dimensions":[{"Name":"QueueName","Value":"studio-local-queue-general"}],"Value":5,"Unit":"Count"},{"MetricName":"Jobs","Dimensions":[{"Name":"QueueName","Value":"studio-local-queue-runs"}],"Value":1,"Unit":"Count"}]' || ok=0
has $name 'aws sqs get-queue-attributes --queue-url https://floci:4566/000000000000/studio-local-queue-general --attribute-names ApproximateNumberOfMessages ApproximateNumberOfMessagesNotVisible' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=empty_queues_publish_zero_jobs
run $name
ok=1
has $name '"Value":"studio-local-queue-general"}],"Value":0,' || ok=0
has $name '"Value":"studio-local-queue-runs"}],"Value":0,' || ok=0
[ $ok = 1 ] && echo "ok   $name"

# The API's tasks are containers named floci-aws-ecs-<task id>-api. Each one's CPU is docker's percentage of one core
# over the CPUs the task has (its task size): 30% of a core on half a vCPU is 60% of the task.
name=publishes_the_api_services_average_cpu_from_its_task_containers
run $name STUB_CONTAINERS="floci-aws-ecs-aaa-api 30.00% 500000000
floci-aws-ecs-bbb-api 10.00% 500000000
floci-aws-ecs-ccc-worker-general 95.00% 1000000000"
ok=1
has $name 'aws cloudwatch put-metric-data --namespace AWS/ECS --metric-data [{"MetricName":"CPUUtilization","Dimensions":[{"Name":"ClusterName","Value":"studio-local-ecs"},{"Name":"ServiceName","Value":"studio-local-ecs-api"}],"Value":40,"Unit":"Percent"}]' || ok=0
[ $ok = 1 ] && echo "ok   $name"

name=publishes_no_cpu_when_no_api_task_runs
run $name STUB_CONTAINERS="floci-aws-ecs-ccc-worker-general 95.00% 1000000000"
ok=1
never $name 'namespace AWS/ECS' || ok=0
[ "$status" = 0 ] || { fail $name "exit $status"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=a_failed_publish_is_reported_and_the_driver_carries_on
run $name STUB_PUT_EXIT=1
ok=1
[ "$status" = 0 ] || { fail $name "exit $status"; ok=0; }
grep -qF "Could not publish" <<<"$out" || { fail $name "expected a warning in: $out"; ok=0; }
[ $ok = 1 ] && echo "ok   $name"

name=rejects_missing_arguments
if out=$(env PATH="$work/bin:$PATH" STUB_CALLS=/dev/null "$drive" --once studio-local-ecs 2>&1); then
  fail $name "exit 0"
elif grep -qF "usage:" <<<"$out"; then echo "ok   $name"
else fail $name "$out"; fi

# Without --once it repeats every REHEARSAL_DRIVE_SECONDS until stopped.
name=repeats_until_stopped
: >"$work/loop.calls"
env PATH="$work/bin:$PATH" STUB_CALLS="$work/loop.calls" REHEARSAL_DRIVE_SECONDS=0.2 \
  "$drive" studio-local-ecs studio-local-ecs-api studio-local-queue-general studio-local-queue-runs Rehearsal/SQS >/dev/null 2>&1 &
pid=$!
sleep 1.5
kill "$pid" 2>/dev/null
wait "$pid" 2>/dev/null
passes=$(grep -c 'namespace Rehearsal/SQS' "$work/loop.calls")
if [ "$passes" -ge 2 ]; then echo "ok   $name"; else fail $name "$passes passes"; fi
urls=$(grep -c 'get-queue-url' "$work/loop.calls")
if [ "$urls" = 2 ]; then echo "ok   looks_up_each_queue_url_once"; else fail looks_up_each_queue_url_once "$urls lookups"; fi

exit $((failures > 0))
