#!/usr/bin/env bash
# What a browser does in the rehearsal's Studio, with curl: sign in, upload a Document through a presigned link (with
# the CORS preflight a browser sends), and wait for it to become Ready. Usage: usable.sh <studio url> <email> <password> <file>
set -euo pipefail
base=$1 email=$2 password=$3 file=$4
w=$(mktemp -d); trap 'rm -rf "$w"' EXIT
echo "## sign in at $base"
code=$(curl -s -D "$w/h" -o "$w/b" -w '%{http_code}' -H 'Content-Type: application/json' -d "{\"email\":\"$email\",\"password\":\"$password\"}" "$base/api/auth/sign-in")
echo "POST /api/auth/sign-in -> $code"
cookie=$(grep -i '^set-cookie: studio_session=' "$w/h" | head -1 | sed -E 's/^[Ss]et-[Cc]ookie: (studio_session=[^;]*).*/\1/')
grep -i '^set-cookie: studio_session=' "$w/h" | sed -E 's/studio_session=[^;]*/studio_session=<token>/' | tr -d '\r'
org=$(jq -r '.active_organisation_id' "$w/b")
api() { curl -s -H "Cookie: $cookie" -H 'Content-Type: application/json' "$@"; }
project=$(api "$base/api/organisations/$org/projects" | jq -r '.[0].id // .items[0].id')
echo "organisation $org, project $project"
size=$(wc -c <"$file"); name=$(basename "$file")
api -d "{\"filename\":\"$name\",\"size_bytes\":$size}" "$base/api/organisations/$org/projects/$project/uploads" >"$w/up"
url=$(jq -r .url "$w/up"); ctype=$(jq -r .content_type "$w/up"); upload=$(jq -r .upload_id "$w/up")
echo "presigned URL host: $(sed -E 's#^(https?://[^/]+)/.*#\1#' <<<"$url")"
echo "## CORS preflight from the Studio's origin"
curl -s -o /dev/null -D - -X OPTIONS -H "Origin: $base" -H 'Access-Control-Request-Method: PUT' -H 'Access-Control-Request-Headers: content-type' "$url" | grep -iE '^HTTP|^access-control-allow-(origin|methods)' | tr -d '\r'
echo "## PUT the file from the Studio's origin"
curl -s -o /dev/null -D - -X PUT -H "Origin: $base" -H "Content-Type: $ctype" --data-binary "@$file" "$url" | grep -iE '^HTTP|^access-control-allow-origin|^etag' | tr -d '\r'
hash=$(sha256sum "$file" | cut -d' ' -f1)
doc=$(api -d "{\"upload_id\":\"$upload\",\"content_hash\":\"$hash\"}" "$base/api/organisations/$org/projects/$project/documents" | jq -r .id)
echo "confirmed: Document $doc"
for i in $(seq 90); do
  status=$(api "$base/api/organisations/$org/projects/$project/documents/statuses" | jq -r --arg id "$doc" '.[] | select(.id == $id) | "\(.status) chunks=\(.chunk_count) error=\(.error_message)"')
  case "$status" in ready*|Ready*|failed*|Failed*) break ;; esac
  sleep 4
done
echo "after $((i * 4)) s: $status"
echo "## every Document in the Project"
api "$base/api/organisations/$org/projects/$project/documents/statuses" | jq -r '.[] | "\(.status) chunks=\(.chunk_count)"'
