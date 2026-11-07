#!/usr/bin/env bash
# Tests for scripts/deploy/smoke.sh, the deploy workflow's final step (spec 09 story 32). Each case serves fixed
# responses from a local HTTP server (fake_site.py) standing in for the CloudFront URL, so the real curl calls run.
# Usage: scripts/deploy/tests/smoke.test.sh
set -uo pipefail
here=$(cd "$(dirname "$0")" && pwd)
smoke="$here/../smoke.sh"
work=$(mktemp -d)
pids=()
# shellcheck disable=SC2329 # Called by the EXIT trap.
cleanup() { for pid in "${pids[@]}"; do kill "$pid" 2>/dev/null; done; rm -rf "$work"; }
trap cleanup EXIT
failures=0

HEALTHY='{"status":"ok","checks":{"database":"ok","redis":"ok"}}'
STUDIO='<!doctype html><html lang="en"><head><title>RAG Agent Studio</title></head><body><div id="root"></div><script type="module" src="/assets/index-abc123.js"></script></body></html>'

# site <name> <routes json>: starts a fake site serving those routes and sets $url to its base URL.
site() {
  local routes="$work/$1.json" port=""
  printf '%s' "$2" >"$routes"
  python3 -I "$here/fake_site.py" "$routes" >"$routes.port" 2>/dev/null &
  pids+=("$!")
  for _ in $(seq 100); do
    port=$(cat "$routes.port")
    [ -n "$port" ] && break
    sleep 0.05
  done
  url="http://127.0.0.1:$port"
}

# routes <health status> <health body> <studio status> <studio type> <studio body> <shell path> <shell status> <shell csp>
routes() {
  jq -n --arg hs "$1" --arg hb "$2" --arg ss "$3" --arg st "$4" --arg sb "$5" --arg wp "$6" --arg ws "$7" --arg csp "$8" '{
    "/api/health": {status: ($hs | tonumber), headers: {"Content-Type": "application/json"}, body: $hb},
    "/": {status: ($ss | tonumber), headers: {"Content-Type": $st}, body: $sb},
    ($wp): {status: ($ws | tonumber), headers: ({"Content-Type": "text/html; charset=utf-8"} + (if $csp == "" then {} else {"Content-Security-Policy": $csp} end)), body: "<!doctype html><title>shell</title>"}
  }'
}

url=""

# check <name> <expected exit> <expected message> <routes json> [smoke.sh args after the URL...]
check() {
  local name=$1 expected=$2 message=$3 out status
  site "$name" "$4"
  shift 4
  out=$(SMOKE_ATTEMPTS=${SMOKE_ATTEMPTS:-1} SMOKE_DELAY_SECONDS=0 "$smoke" "$url" "$@" 2>&1)
  status=$?
  if [ "$status" != "$expected" ]; then
    echo "FAIL $name: exit $status, expected $expected. Output: $out"; failures=$((failures + 1)); return
  fi
  if ! grep -qF "$message" <<<"$out"; then
    echo "FAIL $name: expected '$message' in: $out"; failures=$((failures + 1)); return
  fi
  echo "ok   $name"
}

shell=/widget/a/smoke-check
ok_routes=$(routes 200 "$HEALTHY" 200 "text/html" "$STUDIO" "$shell" 404 "frame-ancestors *")

check passes_when_health_studio_and_the_widget_shell_respond 0 "Smoke check passed" "$ok_routes"
check passes_against_a_live_agent_whose_shell_names_its_allowed_origins 0 "Smoke check passed" \
  "$(routes 200 "$HEALTHY" 200 "text/html; charset=utf-8" "$STUDIO" /widget/a/agt_live123 200 "frame-ancestors https://example.com")" agt_live123
check fails_when_the_health_endpoint_reports_an_error 1 "health: /api/health" \
  "$(routes 503 '{"status":"error","checks":{"database":"error","redis":"ok"}}' 200 "text/html" "$STUDIO" "$shell" 404 "frame-ancestors *")"
check fails_when_health_answers_200_without_status_ok 1 "health: /api/health" \
  "$(routes 200 '{"status":"error"}' 200 "text/html" "$STUDIO" "$shell" 404 "frame-ancestors *")"
check fails_when_the_studio_is_not_served 1 "studio: /" \
  "$(routes 200 "$HEALTHY" 403 "application/xml" "<Error>AccessDenied</Error>" "$shell" 404 "frame-ancestors *")"
check fails_when_the_studio_page_is_not_the_studio 1 "studio: /" \
  "$(routes 200 "$HEALTHY" 200 "text/html" "<html><body>Welcome to nginx</body></html>" "$shell" 404 "frame-ancestors *")"
check fails_when_the_studio_is_not_html 1 "studio: /" \
  "$(routes 200 "$HEALTHY" 200 "text/plain" "$STUDIO" "$shell" 404 "frame-ancestors *")"
check fails_when_the_widget_shell_has_no_csp 1 "widget shell: $shell" \
  "$(routes 200 "$HEALTHY" 200 "text/html" "$STUDIO" "$shell" 404 "")"
check fails_when_the_widget_shell_csp_has_no_frame_ancestors 1 "widget shell: $shell" \
  "$(routes 200 "$HEALTHY" 200 "text/html" "$STUDIO" "$shell" 404 "default-src 'self'")"
check fails_when_the_widget_shell_errors 1 "widget shell: $shell" \
  "$(routes 200 "$HEALTHY" 200 "text/html" "$STUDIO" "$shell" 502 "frame-ancestors *")"

# Every check is retried while CloudFront and the services settle; the last failure is reported.
SMOKE_ATTEMPTS=3 check retries_each_check_before_failing 1 "after 3 attempts" \
  "$(routes 503 '{"status":"error"}' 200 "text/html" "$STUDIO" "$shell" 404 "frame-ancestors *")"
health_calls=$(grep -cx /api/health "$work/retries_each_check_before_failing.json.log")
if [ "$health_calls" = 3 ]; then echo "ok   retries_the_health_check_3_times"; else echo "FAIL retries_the_health_check_3_times: $health_calls calls"; failures=$((failures + 1)); fi

# A check that passes on a later attempt passes the smoke check: the site turns healthy while smoke.sh waits.
site turns_healthy "$(routes 503 '{"status":"error"}' 200 "text/html" "$STUDIO" "$shell" 404 "frame-ancestors *")"
( sleep 1; printf '%s' "$ok_routes" >"$work/turns_healthy.json" ) &
writer=$!
if out=$(SMOKE_ATTEMPTS=10 SMOKE_DELAY_SECONDS=0.5 "$smoke" "$url" 2>&1) && grep -qF "Smoke check passed" <<<"$out"; then
  echo "ok   passes_once_a_failing_check_recovers"
else
  echo "FAIL passes_once_a_failing_check_recovers: $out"; failures=$((failures + 1))
fi
wait "$writer"

# Nothing listening: curl fails, and so does the smoke check.
if out=$(SMOKE_ATTEMPTS=1 SMOKE_DELAY_SECONDS=0 "$smoke" http://127.0.0.1:9 2>&1); then
  echo "FAIL fails_when_the_site_is_unreachable: exit 0"; failures=$((failures + 1))
elif grep -qF "health: /api/health" <<<"$out"; then echo "ok   fails_when_the_site_is_unreachable"
else echo "FAIL fails_when_the_site_is_unreachable: $out"; failures=$((failures + 1)); fi

# The URL must be given, without a trailing path.
for args in "" "ftp://example.com" "https://d111111abcdef8.cloudfront.net/studio"; do
  if out=$("$smoke" $args 2>&1); then
    echo "FAIL rejects_bad_arguments '$args': exit 0"; failures=$((failures + 1))
  elif grep -qF "usage:" <<<"$out"; then echo "ok   rejects_bad_arguments '$args'"
  else echo "FAIL rejects_bad_arguments '$args': $out"; failures=$((failures + 1)); fi
done

exit $((failures > 0))
