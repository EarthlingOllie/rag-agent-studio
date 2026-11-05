#!/usr/bin/env bash
# Drives the running rag0106 stack: account delays and lockout, per-IP counting via X-Forwarded-For,
# uniform answers for an unknown email, and the Audit Event row.
set -uo pipefail
API=http://localhost:38006
EMAIL="demo-$(date +%s)@example.test"
PW="correct horse battery staple"
post() { curl -s -o /tmp/b06 -w '%{http_code}' -H 'content-type: application/json' -H "X-Forwarded-For: $1" -D /tmp/h06 "$API/api/auth/sign-in" -d "{\"email\":\"$2\",\"password\":\"$3\"}"; }
echo "\$ sign up $EMAIL"
curl -s -c /tmp/jar06 -o /tmp/su06 -w 'sign-up %{http_code}\n' -H 'content-type: application/json' "$API/api/auth/sign-up" \
  -d "{\"name\":\"Demo\",\"email\":\"$EMAIL\",\"password\":\"$PW\",\"organisation_name\":\"Demo Org\"}"
ORG=$(python3 -c 'import json;print(json.load(open("/tmp/su06"))["organisations"][0]["id"])')
echo "== wrong passwords for one account from 203.0.113.7, waiting out each delay"
for i in $(seq 1 30); do
  code=$(post 203.0.113.7 "$EMAIL" "wrong password")
  body=$(cat /tmp/b06); ra=$(grep -i '^retry-after' /tmp/h06 | tr -d '\r')
  echo "attempt $i: $code $body ${ra}"
  if [ "$code" = 429 ]; then
    if grep -q '"locked":true' /tmp/b06; then break; fi
    sleep "$(echo "$body" | sed 's/.*"retry_after_seconds":\([0-9]*\).*/\1/')"
  fi
done
echo "== the right password while locked"
echo "$(post 203.0.113.7 "$EMAIL" "$PW") $(cat /tmp/b06)"
echo "== the right password from another IP (the account counter still applies)"
echo "$(post 198.51.100.9 "$EMAIL" "$PW") $(cat /tmp/b06)"
echo "== an unknown email from a fresh IP gets the same first answers"
for i in 1 2 3 4; do echo "attempt $i: $(post 192.0.2.44 "nobody-$EMAIL" "wrong password") $(cat /tmp/b06)"; done
echo "== the Audit Event, as the Owner (still signed in from sign-up) lists it through the API"
curl -s -b /tmp/jar06 "$API/api/organisations/$ORG/audit-events?action=member.locked_out"; echo
echo "== Redis keys (hashed email, IPs as seen through X-Forwarded-For)"
docker exec rag0106-redis-1 redis-cli --scan --pattern 'sign-in-failures:*' | sort
echo "DEMO_EMAIL=$EMAIL"
echo "DEMO_ORG=$ORG"
grep studio_session /tmp/jar06 | cut -f7 > /tmp/session06  # the Owner session, for the screenshot script; kept out of the log
