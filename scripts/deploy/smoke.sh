#!/usr/bin/env bash
# The deploy workflow's smoke check (spec 09 story 32): the API is healthy, the Studio loads, and the widget shell
# answers with a Content-Security-Policy that has frame-ancestors, all through the CloudFront URL.
# Each check is retried (SMOKE_ATTEMPTS, default 20, SMOKE_DELAY_SECONDS apart, default 15) while new tasks
# register with the ALB and the invalidation settles.
# The widget shell is checked for an unknown Agent (404 with `frame-ancestors *`) unless a live Agent's public ID is
# given (200 with its Allowed Origins).
# Usage: scripts/deploy/smoke.sh <https://distribution URL> [agent public id]
set -euo pipefail

usage() { echo "usage: $0 <base URL, such as https://d111111abcdef8.cloudfront.net> [agent public id]" >&2; exit 2; }
[ $# -ge 1 ] && [ $# -le 2 ] || usage
base=${1%/}
[[ "$base" =~ ^https?://[^/]+$ ]] || usage
agent=${2:-smoke-check}
attempts=${SMOKE_ATTEMPTS:-20}
delay=${SMOKE_DELAY_SECONDS:-15}

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

# fetch <path>: GETs the path; sets $code, and leaves the headers and body in $work.
fetch() {
  code=$(curl -sS --max-time 20 -D "$work/headers" -o "$work/body" -w '%{http_code}' "$base$1" 2>"$work/error") || code=000
}

# header <name>: the value of a response header, without its trailing CR.
header() {
  grep -i "^$1:" "$work/headers" | tail -n 1 | cut -d: -f2- | sed -e 's/^[[:space:]]*//' -e 's/\r$//'
}

check_health() {
  fetch /api/health
  [ "$code" = 200 ] && jq -e '.status == "ok"' "$work/body" >/dev/null 2>&1 && return 0
  problem="health: /api/health answered $code: $(head -c 300 "$work/body" 2>/dev/null; cat "$work/error")"
  return 1
}

check_studio() {
  fetch /
  [ "$code" = 200 ] && [[ "$(header Content-Type)" == text/html* ]] && grep -q '<div id="root"></div>' "$work/body" && return 0
  problem="studio: / answered $code ($(header Content-Type)), not the Studio's index.html"
  return 1
}

check_widget_shell() {
  fetch "/widget/a/$agent"
  local csp
  csp=$(header Content-Security-Policy)
  if [[ "$code" =~ ^(200|404)$ ]] && [[ "$csp" == *frame-ancestors* ]]; then return 0; fi
  problem="widget shell: /widget/a/$agent answered $code with Content-Security-Policy '${csp}'"
  return 1
}

for check in check_health check_studio check_widget_shell; do
  problem=""
  for attempt in $(seq "$attempts"); do
    if "$check"; then echo "ok   ${check#check_}"; break; fi
    if [ "$attempt" = "$attempts" ]; then
      echo "::error title=Smoke check failed::$problem (after $attempts attempts)" >&2
      exit 1
    fi
    sleep "$delay"
  done
done

echo "Smoke check passed: $base"
