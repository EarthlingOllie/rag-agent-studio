#!/bin/bash
# Applies one single-line regression at a time to the cdn module, its SPA fallback function or the demo wiring,
# runs that root's tests, and restores the file. Every regression must fail the tests (exit 1). Then removes
# needed Checkov skips one at a time and shows Checkov failing. Set TF_CLI_CONFIG_FILE first if the provider comes
# from a local mirror.
cd "$(git rev-parse --show-toplevel)/infra"
BAK=$(mktemp)
NODE_TEST="node --test --experimental-test-coverage --test-coverage-lines=100 --test-coverage-branches=100 --test-coverage-functions=100 modules/cdn/functions/spa-fallback.test.mjs"
mutate() { # file, test root (or "node"), label, sed expression
  local f=$1 root=$2 label=$3 expr=$4
  cp "$f" "$BAK"
  sed -i "$expr" "$f"
  echo "### $f: $label"
  diff "$BAK" "$f" | grep -E "^[<>]" || echo "!! sed did not change the file"
  if [ "$root" = node ]; then
    $NODE_TEST 2>&1 | grep -E '^not ok|^# (pass|fail) ' | head -4
  else
    terraform -chdir=$root test -no-color 2>&1 | grep -E '\.\.\. fail$|^Success|^Failure' | head -4
  fi
  echo "exit=${PIPESTATUS[0]}"
  cp "$BAK" "$f"
  echo
}
M=modules/cdn/main.tf
mutate $M modules/cdn "dynamic paths cached for a day" '0,/default_ttl = 0/s//default_ttl = 86400/'
mutate $M modules/cdn "Host forwarded to the ALB" 's/header_behavior = "allExcept"/header_behavior = "allViewer"/'
mutate $M modules/cdn "cookies not forwarded to the API" 's/cookie_behavior = "all"/cookie_behavior = "none"/'
mutate $M modules/cdn "query strings not forwarded to the API" 's/query_string_behavior = "all"/query_string_behavior = "none"/'
mutate $M modules/cdn "SSE responses compressed" 's/compress                   = false/compress                   = true/'
mutate $M modules/cdn "API reachable only for GET" 's/allowed_methods            = \["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"\]/allowed_methods            = ["GET", "HEAD"]/'
mutate $M modules/cdn "read timeout ignores the variable" 's/origin_read_timeout      = var.origin_read_timeout/origin_read_timeout      = 30/'
mutate $M modules/cdn "origin header secret not sent" 's/value = var.origin_header_value/value = "not-the-secret"/'
mutate $M modules/cdn "ALB origin over HTTPS" 's/origin_protocol_policy   = "http-only"/origin_protocol_policy   = "https-only"/'
mutate $M modules/cdn "static bucket without origin access control" '/origin_access_control_id = var.static_origin_access_control_id/d'
mutate $M modules/cdn "/embed.js has no behaviour" 's|static_paths  = \["/embed.js", "/widget/assets/\*"\]|static_paths  = ["/widget/assets/*"]|'
mutate $M modules/cdn "/widget/a/* served from S3" 's|dynamic_paths = \["/api/\*", "/widget/a/\*"\]|dynamic_paths = ["/api/*"]|'
mutate $M modules/cdn "static assets vary on cookies (session in the cache)" '0,/cookie_behavior = "none"/s//cookie_behavior = "all"/'
mutate $M modules/cdn "SPA fallback on responses instead of requests" 's/event_type   = "viewer-request"/event_type   = "viewer-response"/'
mutate $M modules/cdn "Studio served over plain HTTP" '0,/viewer_protocol_policy     = "redirect-to-https"/s//viewer_protocol_policy     = "allow-all"/'
mutate $M modules/cdn "every edge location (cost)" 's/price_class         = "PriceClass_100"/price_class         = "PriceClass_All"/'
mutate $M modules/cdn "custom domain still on the default certificate" 's/cloudfront_default_certificate = !local.custom_domain/cloudfront_default_certificate = true/'
mutate $M modules/cdn "custom domain allows TLS 1.0" 's/local.custom_domain ? "TLSv1.2_2021" : "TLSv1"/"TLSv1"/'
mutate $M modules/cdn "certificate outside us-east-1" '0,/region            = "us-east-1"/s//region            = "eu-west-2"/'
mutate $M modules/cdn "no IPv6 record" 's/toset(local.custom_domain ? \["A", "AAAA"\] : \[\])/toset(local.custom_domain ? ["A"] : [])/'
mutate $M modules/cdn "distribution does not answer on the domain" 's/aliases             = local.custom_domain ? \[var.domain_name\] : \[\]/aliases             = []/'
mutate $M modules/cdn "certificate created without a domain" '0,/count = local.custom_domain ? 1 : 0/s//count = 1/'
mutate $M modules/cdn "Studio may be framed" 's/frame_option = "DENY"/frame_option = "SAMEORIGIN"/'
mutate $M modules/cdn "API nosniff overrides the API" 's/      override = false/      override = true/'
mutate modules/cdn/outputs.tf modules/cdn "URL always the cloudfront.net name" 's|value       = "https://${local.custom_domain ? var.domain_name : aws_cloudfront_distribution.this.domain_name}"|value       = "https://${aws_cloudfront_distribution.this.domain_name}"|'
F=modules/cdn/functions/spa-fallback.js
mutate $F node "files rewritten to index.html too" 's/lastSegment.indexOf(".") === -1/true/'
mutate $F node "routes not rewritten" 's|request.uri = "/index.html";|request.uri = request.uri;|'
mutate $F node "only the first segment checked" 's/request.uri.lastIndexOf("\/")/request.uri.indexOf("\/")/'
D=envs/demo/main.tf
mutate $D envs/demo "Documents CORS not wired to the CloudFront origin" 's/documents_cors_allowed_origin  = module.cdn.url/documents_cors_allowed_origin  = null/'
mutate $D envs/demo "static bucket trusts no distribution" 's/static_assets_distribution_arn = module.cdn.distribution_arn/static_assets_distribution_arn = null/'
mutate $D envs/demo "custom domain not passed to the cdn" 's/domain_name                        = var.domain_name/domain_name                        = null/'
mutate envs/demo/outputs.tf envs/demo "no CloudFront URL output" 's/value       = module.cdn.url/value       = module.storage.documents_cors_allowed_origin == null ? "" : "https:\/\/wrong"/'

skip() { # file, check id
  local f=$1 id=$2
  cp "$f" "$BAK"
  sed -i "/#checkov:skip=$id:/d" "$f"
  echo "### $f: without the $id skip"
  checkov --config-file .checkov.yaml --check "$id" 2>&1 | grep -E "^(Passed|Check:)|FAILED" | head -4
  cp "$BAK" "$f"
  echo
}
skip $M CKV_AWS_174
skip $M CKV_AWS_259
skip $M CKV_AWS_68
rm -f "$BAK"
