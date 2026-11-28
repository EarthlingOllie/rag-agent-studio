#!/usr/bin/env bash
# The scaling demonstration (ticket 22-07; spec 22 stories 43-47, ADR-0021): puts real work on the deployed, seeded
# demo and prints a timeline of each service scaling out and back in. In order:
#   1. terraform init against the bootstrap's state bucket and read the deploy output (nothing is applied): the
#      cluster, the api and worker pool services and the job queues; then each service's minimum from its scalable
#      target
#   2. sign in as the Owner and create a throwaway Project ("Scaling demonstration <UTC time>")
#   3. upload the seed Documents (seed/documents) --copies times each, as scale-<n>-<file>, each copy made different
#      (a comment at the end of text files and PDFs, the archive comment of Office files) because a Project refuses a
#      file whose content it already holds: the general pool gets the ingestion jobs
#   4. send API requests from --api-workers parallel loops for --api-seconds, so the API's CPU climbs, and meanwhile
#      start Evaluation Runs on the seeded Agents (one at a time per Agent, as the Studio allows, up to --runs in all;
#      an Agent without an Evaluation Set is skipped), so the runs pool gets work
#   5. every --poll-seconds, read each service's running and desired tasks from ECS and each queue's latest waiting
#      and in-flight jobs from CloudWatch, and print a line of the timeline, until the load is over and every service
#      is back at its minimum with both queues empty, or --timeout-minutes have passed
#   6. delete the Project (archive it, then delete it with its name as the confirmation), also when it fails or is
#      interrupted, so it can be run again; a failure or interruption also cancels its Runs still in progress
# It exits 1 naming each service that never ran more tasks than its minimum, or that was not back at it in time.
# The defaults finish in about fifteen minutes with the module's default cooldowns: five minutes of load, then the
# pools' five idle minutes and the API's scale-in (CloudWatch's target tracking waits for fifteen low minutes, so the
# API can be the last back).
# Usage: OWNER_EMAIL=... OWNER_PASSWORD=... TF_STATE_BUCKET=... AWS_REGION=... scripts/deploy/scale.sh [options] <Studio URL>
# Optional: DEPLOY_ROOT (default infra/envs/demo), SCALE_DOCUMENTS_DIR (default seed/documents).
set -euo pipefail

usage() {
  cat >&2 <<EOF
usage: $0 [options] <Studio URL, such as https://d111111abcdef8.cloudfront.net>
  --copies N        each seed Document is uploaded N times (default 5)
  --runs N          at most N Evaluation Runs are started on the seeded Agents (default 3)
  --api-seconds N   the load (API requests and Runs) lasts N seconds (default 300)
  --api-workers N   N parallel loops send the API requests (default 8)
  --poll-seconds N  ECS and CloudWatch are read every N seconds (default 30)
  --timeout-minutes N
                    every service must be back at its minimum within N minutes (default 25)
Needs OWNER_EMAIL and OWNER_PASSWORD (the seeded demo's Owner), TF_STATE_BUCKET and AWS_REGION.
EOF
  exit 2
}

copies=5 runs=3 api_seconds=300 api_workers=8 poll_seconds=30 timeout_minutes=25 base=""
while [ $# -gt 0 ]; do
  case "$1" in
    --copies | --runs | --api-seconds | --api-workers | --poll-seconds | --timeout-minutes)
      [ $# -ge 2 ] && [[ "$2" =~ ^[1-9][0-9]*$ ]] || usage
      case "$1" in
        --copies) copies=$2 ;;
        --runs) runs=$2 ;;
        --api-seconds) api_seconds=$2 ;;
        --api-workers) api_workers=$2 ;;
        --poll-seconds) poll_seconds=$2 ;;
        --timeout-minutes) timeout_minutes=$2 ;;
      esac
      shift 2 ;;
    -*) usage ;;
    *) [ -z "$base" ] || usage; base=${1%/}; shift ;;
  esac
done
[[ "$base" =~ ^https?://[^/]+$ ]] || usage
for var in OWNER_EMAIL OWNER_PASSWORD TF_STATE_BUCKET AWS_REGION; do
  [ -n "${!var:-}" ] || { echo "$var must be set: see $0 --help." >&2; exit 2; }
done
repo=$(cd "$(dirname "$0")/../.." && pwd)
root=${DEPLOY_ROOT:-$repo/infra/envs/demo}
documents=${SCALE_DOCUMENTS_DIR:-$repo/seed/documents}

die() { echo "::error title=Scaling demonstration failed::$*" >&2; exit 1; }
umask 077
work=$(mktemp -d)
session="$work/session"
project_id="" project_name="" org="" traffic=() started=()

# --- 1. The deployed environment ------------------------------------------------------------------------------------
echo "==> terraform init (state bucket $TF_STATE_BUCKET)"
terraform -chdir="$root" init -input=false -backend-config="bucket=$TF_STATE_BUCKET" -backend-config="region=$AWS_REGION" >/dev/null
if ! terraform -chdir="$root" output -json deploy >"$work/deploy.json"; then
  rm -rf "$work"
  die "The demo environment is not deployed. Run the deploy workflow, then the seed workflow, first."
fi
out() { jq -r "$1" "$work/deploy.json"; }
if [ "$(out '.queue_names.general // empty')" = "" ]; then
  rm -rf "$work"
  die "The deploy output has no job queues: deploy at a commit that has them (ticket 22-07) first."
fi
cluster=$(out .cluster_name)
scaled=(api worker-general worker-runs)
names=() mins=() peaks=() running=() desired=()
for i in 0 1 2; do names[i]=$(out ".services[\"${scaled[i]}\"]"); done
general_queue=$(out .queue_names.general)
runs_queue=$(out .queue_names.runs)

aws application-autoscaling describe-scalable-targets --service-namespace ecs \
  --resource-ids "service/$cluster/${names[0]}" "service/$cluster/${names[1]}" "service/$cluster/${names[2]}" \
  --query 'ScalableTargets[].[ResourceId,MinCapacity]' --output text >"$work/targets"
for i in 0 1 2; do
  mins[i]=$(awk -v id="service/$cluster/${names[i]}" '$1 == id { print $2 }' "$work/targets")
  [[ "${mins[i]}" =~ ^[0-9]+$ ]] || { rm -rf "$work"; die "${scaled[i]} has no scalable target: deploy at a commit with autoscaling (ticket 22-05)."; }
  peaks[i]=${mins[i]}
done

# --- The Studio API -------------------------------------------------------------------------------------------------
# api <method> <path> [body, or @file]: calls the Studio's API with the Owner's session; sets $code and leaves the
# response in $work/body. The script keeps the session cookie itself, from the latest answer that set it: it is Secure,
# and curl neither stores nor sends a Secure cookie over plain HTTP, which the Floci rehearsal's
# http://<id>.cloudfront.localhost Studio is (browsers keep it for localhost names; ticket 23-05).
api() {
  local args=(-sS --max-time 60 -D "$work/headers" -o "$work/body" -w '%{http_code}' -X "$1") renewed
  [ -s "$session" ] && args+=(-H "Cookie: $(cat "$session")")
  [ $# -ge 3 ] && args+=(-H 'Content-Type: application/json' --data-binary "$3")
  : >"$work/headers"
  code=$(curl "${args[@]}" "$base$2" 2>"$work/error") || code=000
  renewed=$(tr -d '\r' <"$work/headers" | sed -n -E 's/^[Ss][Ee][Tt]-[Cc][Oo][Oo][Kk][Ii][Ee]: *(studio_session=[^;]*).*/\1/p' | tail -n 1)
  [ -z "$renewed" ] || printf '%s' "$renewed" >"$session"
}
detail() { jq -r '.detail // empty' "$work/body" 2>/dev/null || head -c 300 "$work/body"; cat "$work/error"; }
# expect <what> <status...>: dies unless the last call answered one of the statuses.
expect() {
  local what=$1 wanted
  shift
  for wanted in "$@"; do [ "$code" = "$wanted" ] && return 0; done
  die "$what answered $code: $(detail)"
}
plural() { if [ "$1" = 1 ]; then echo "1 task"; else echo "$1 tasks"; fi; }

# The Project is deleted however the script ends; a failure or an interruption also cancels the Runs it started.
# shellcheck disable=SC2329 # Called by the EXIT trap.
cleanup() {
  local status=$? run
  trap - EXIT INT TERM
  for pid in "${traffic[@]}"; do kill "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
  if [ "$status" != 0 ]; then
    for run in "${started[@]}"; do
      api POST "${run%% *}/cancel"
      [ "$code" = 200 ] && echo "Cancelled the Evaluation Run on ${run#* }."
    done
  fi
  if [ -n "$project_id" ]; then
    api POST "/api/organisations/$org/projects/$project_id/archive"
    api DELETE "/api/organisations/$org/projects/$project_id" "$(jq -nc --arg n "$project_name" '{confirm_name: $n}')"
    if [ "$code" = 202 ]; then
      echo "Deleted the Project '$project_name'."
    else
      echo "::error title=Project not deleted::Deleting the Project '$project_name' answered $code: $(detail). Archive and delete it in the Studio." >&2
      status=1
    fi
  fi
  rm -rf "$work"
  exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

# --- 2. Sign in and create the throwaway Project --------------------------------------------------------------------
jq -nc --arg e "$OWNER_EMAIL" --arg p "$OWNER_PASSWORD" '{email: $e, password: $p}' >"$work/sign-in.json"
api POST /api/auth/sign-in "@$work/sign-in.json"
[ "$code" != 202 ] || die "$OWNER_EMAIL uses MFA, which this script cannot answer: use an Owner without MFA."
expect "sign-in" 200
org=$(jq -r '.active_organisation_id // empty' "$work/body")
role=$(jq -r --arg org "$org" '.organisations[] | select(.id == $org) | .role' "$work/body")
[ -n "$org" ] && [ "$role" = owner ] || die "$OWNER_EMAIL is not an Owner of their Organisation: sign in as the seeded demo's Owner."
projects="/api/organisations/$org/projects"

name="Scaling demonstration $(date -u +%Y-%m-%dT%H:%M:%SZ)"
api POST "$projects" "$(jq -nc --arg n "$name" '{name: $n, description: "Throwaway Project of scripts/deploy/scale.sh; deleted when it ends."}')"
expect "creating the Project" 201
project_id=$(jq -r .id "$work/body") project_name=$name
echo "Created the Project '$project_name'."

# --- 3. Upload the seed Documents, each copy different --------------------------------------------------------------
mkdir "$work/copies"
uploaded=0
for c in $(seq "$copies"); do
  for seed in "$documents"/*; do
    file="$work/copies/scale-$c-$(basename "$seed")"
    cp "$seed" "$file"
    case "$file" in
      *.md | *.txt | *.html | *.csv) printf '\n\n<!-- Scaling demonstration copy %s -->\n' "$c" >>"$file" ;;
      *.pdf) printf '\n%% Scaling demonstration copy %s\n' "$c" >>"$file" ;;
      *.docx | *.pptx | *.xlsx)
        python3 -I -c 'import sys, zipfile
with zipfile.ZipFile(sys.argv[1], "a") as z: z.comment = sys.argv[2].encode()' "$file" "Scaling demonstration copy $c" ;;
      *) die "$(basename "$seed") is not a type this script can copy (text, PDF or Office)." ;;
    esac
    filename=$(basename "$file")
    api POST "$projects/$project_id/uploads" "$(jq -nc --arg f "$filename" --argjson s "$(wc -c <"$file" | tr -d ' ')" '{filename: $f, size_bytes: $s}')"
    expect "starting the upload of $filename" 201
    upload_id=$(jq -r .upload_id "$work/body")
    put=$(curl -sS --max-time 300 -X PUT -H "Content-Type: $(jq -r .content_type "$work/body")" --data-binary "@$file" \
      -o "$work/body" -w '%{http_code}' "$(jq -r .url "$work/body")" 2>"$work/error") || put=000
    [[ "$put" =~ ^2 ]] || die "the presigned upload of $filename answered $put: $(head -c 300 "$work/body"; cat "$work/error")"
    api POST "$projects/$project_id/documents" "$(jq -nc --arg u "$upload_id" '{upload_id: $u}')"
    expect "confirming the upload of $filename" 201
    uploaded=$((uploaded + 1))
  done
done
echo "Uploaded $uploaded Documents ($copies copies of each seed Document) to '$project_name'."

# --- 4. The seeded Agents, and the load -----------------------------------------------------------------------------
api GET "$projects"
expect "listing the Projects" 200
agents=()
for seeded in $(jq -r --arg own "$project_id" '.[] | select(.archived_at == null and (.deleting | not) and .id != $own) | .id' "$work/body"); do
  api GET "$projects/$seeded/agents"
  expect "listing the Agents" 200
  while IFS=$'\t' read -r id agent_name; do
    agents+=("$projects/$seeded/agents/$id/evaluation/runs"$'\t'"$agent_name")
  done < <(jq -r '.[] | select(.archived_at == null) | [.id, .name] | @tsv' "$work/body")
done
[ ${#agents[@]} -gt 0 ] || die "The Organisation has no seeded Agents: seed the demo first (scripts/deploy/seed.sh)."

# start_runs: asks each Agent still in the list for a Run until --runs have started. An Agent with a Run in progress
# (409 with the conflict) is asked again at the next poll; any other refusal takes it off the list.
start_runs() {
  local keep=() agent path agent_name
  for agent in "${agents[@]}"; do
    [ ${#started[@]} -lt "$runs" ] || return 0
    path=${agent%%$'\t'*} agent_name=${agent#*$'\t'}
    api POST "$path"
    if [ "$code" = 202 ]; then
      started+=("$path/$(jq -r .id "$work/body") $agent_name")
      echo "Started an Evaluation Run on $agent_name."
      keep+=("$agent")
    elif [ "$code" = 409 ] && [ "$(jq -r '.conflict // empty' "$work/body")" != "" ]; then
      keep+=("$agent")
    else
      echo "No Evaluation Run on $agent_name: $(detail)"
    fi
  done
  agents=("${keep[@]}")
}

# send_requests <n>: one loop of API traffic until the load ends; writes how many requests it sent. The loops read
# their own copy of the session, which the script's own calls may rewrite.
cp "$session" "$work/traffic-session"
send_requests() {
  local end=$(($(date +%s) + api_seconds)) sent=0
  while [ "$(date +%s)" -lt "$end" ]; do
    curl -s -o /dev/null --max-time 10 -H "Cookie: $(cat "$work/traffic-session")" "$base$projects" || true
    sent=$((sent + 1))
  done
  echo "$sent" >"$work/sent.$1"
}
for n in $(seq "$api_workers"); do
  send_requests "$n" &
  traffic+=("$!")
done
echo "Sending API requests from $api_workers loops for $api_seconds seconds."

# --- 5. The timeline ------------------------------------------------------------------------------------------------
queries=$(jq -nc --arg g "$general_queue" --arg r "$runs_queue" '
  def q($id; $queue; $metric): {Id: $id, ReturnData: true, MetricStat: {Stat: "Maximum", Period: 60,
    Metric: {Namespace: "AWS/SQS", MetricName: $metric, Dimensions: [{Name: "QueueName", Value: $queue}]}}};
  [q("general_visible"; $g; "ApproximateNumberOfMessagesVisible"), q("general_in_flight"; $g; "ApproximateNumberOfMessagesNotVisible"),
   q("runs_visible"; $r; "ApproximateNumberOfMessagesVisible"), q("runs_in_flight"; $r; "ApproximateNumberOfMessagesNotVisible")]')

# metric <id>: the latest value of one query, as a whole number, or - when CloudWatch has no data point (an idle
# queue's metrics can lapse; the scaling alarms count that as empty, and so does this script).
metric() {
  local value
  value=$(awk -v id="$1" '$1 == id { print $2 }' "$work/metrics")
  if [[ "$value" =~ ^[0-9.]+$ ]]; then printf '%.0f' "$value"; else echo -; fi
}

row='%-8s  %-7s  %-13s  %-10s  %-5s  %-14s  %-11s\n'
echo
# shellcheck disable=SC2059 # The format is the row's.
printf "$row" time elapsed "general queue" "runs queue" api worker-general worker-runs
echo "(queues: waiting+in flight jobs; services: running/desired tasks)"
max_polls=$(((timeout_minutes * 60 + poll_seconds - 1) / poll_seconds))
settled=false
for poll in $(seq "$max_polls"); do
  elapsed=$(((poll - 1) * poll_seconds))
  [ "$elapsed" -ge "$api_seconds" ] || start_runs
  aws ecs describe-services --cluster "$cluster" --services "${names[@]}" \
    --query 'services[].[serviceName,runningCount,desiredCount]' --output text >"$work/services"
  now=$(date +%s)
  aws cloudwatch get-metric-data --start-time $((now - 600)) --end-time "$now" --metric-data-queries "$queries" \
    --query 'MetricDataResults[].[Id,Values[0]]' --output text >"$work/metrics"
  at_minimum=true
  for i in 0 1 2; do
    read -r running[i] desired[i] < <(awk -v n="${names[i]}" '$1 == n { print $2, $3 }' "$work/services")
    [ "${running[i]}" -le "${peaks[i]}" ] || peaks[i]=${running[i]}
    [ "${running[i]}" = "${mins[i]}" ] && [ "${desired[i]}" = "${mins[i]}" ] || at_minimum=false
  done
  depth=()
  for id in general_visible general_in_flight runs_visible runs_in_flight; do
    depth+=("$(metric "$id")")
    case "${depth[${#depth[@]} - 1]}" in 0 | -) ;; *) at_minimum=false ;; esac
  done
  # shellcheck disable=SC2059 # The format is the row's.
  printf "$row" "$(date +%H:%M:%S)" "$(printf '%02d:%02d' $((elapsed / 60)) $((elapsed % 60)))" \
    "${depth[0]}+${depth[1]}" "${depth[2]}+${depth[3]}" "${running[0]}/${desired[0]}" "${running[1]}/${desired[1]}" \
    "${running[2]}/${desired[2]}"
  if [ "$elapsed" -ge "$api_seconds" ] && [ "$at_minimum" = true ]; then settled=true; break; fi
  [ "$poll" = "$max_polls" ] || sleep "$poll_seconds"
done
echo

for pid in "${traffic[@]}"; do wait "$pid" || true; done
traffic=()
sent=$(cat "$work"/sent.* 2>/dev/null | awk '{ n += $1 } END { print n + 0 }')
echo "$sent API requests sent; ${#started[@]} Evaluation Runs started."

# --- The verdict ----------------------------------------------------------------------------------------------------
failed=false
for i in 0 1 2; do
  if [ "${peaks[i]}" -le "${mins[i]}" ]; then
    echo "::error title=Did not scale out::${scaled[i]} never scaled out: it stayed at $(plural "${mins[i]}")." >&2
    failed=true
  fi
done
if [ "$settled" != true ]; then
  for i in 0 1 2; do
    if [ "${running[i]}" != "${mins[i]}" ] || [ "${desired[i]}" != "${mins[i]}" ]; then
      echo "::error title=Did not scale in::${scaled[i]} is not back at its minimum of $(plural "${mins[i]}") after $timeout_minutes minutes (${running[i]} running, ${desired[i]} desired)." >&2
    fi
  done
  echo "::error title=Did not scale in::The services or queues were not all back at rest after $timeout_minutes minutes." >&2
  failed=true
fi
[ "$failed" = false ] || exit 1
summary=()
for i in 0 1 2; do summary+=("${scaled[i]} ${mins[i]} -> ${peaks[i]} -> ${running[i]}"); done
echo "Every service scaled out and back to its minimum: $(IFS=,; echo "${summary[*]}" | sed 's/,/, /g')."
