#!/usr/bin/env bash
# envs/demo composes every module (ticket 09-06). The one exception is ci-oidc: the GitHub OIDC deploy role must
# exist before any environment can be planned from CI, so infra/bootstrap composes it instead (ticket 09-01).
# Every other environment (envs/local, the rehearsal on Floci: ticket 23-03) composes exactly the demo's modules, so
# what is rehearsed is what is deployed.
# terraform test sees one root module at a time, so this reads the module blocks' sources directly.
# Usage: infra/tests/compose.test.sh [infra-dir]
set -euo pipefail
infra=${1:-$(cd "$(dirname "$0")/.." && pwd)}
failures=0

fail() { echo "FAIL $1"; failures=$((failures + 1)); }

# sources <root dir>: the local module directories a root module's module blocks use, one name per line.
sources() {
  sed -e 's/#.*//' "$1"/*.tf | grep -Eo 'source[[:space:]]*=[[:space:]]*"\.\./(\.\./)?modules/[a-z0-9-]+"' | sed -E 's#.*modules/([a-z0-9-]+)"#\1#' | sort -u
}

modules=$(find "$infra/modules" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort)
[ -n "$modules" ] || { echo "FAIL no modules under $infra/modules"; exit 1; }
demo=$(sources "$infra/envs/demo")
bootstrap=$(sources "$infra/bootstrap")

for module in $modules; do
  if [ "$module" = ci-oidc ]; then
    grep -qx ci-oidc <<<"$bootstrap" || fail "ci-oidc: infra/bootstrap must compose it"
    if grep -qx ci-oidc <<<"$demo"; then fail "ci-oidc: envs/demo must not compose it (the bootstrap owns the deploy role)"; else echo "ok   infra/bootstrap composes ci-oidc"; fi
    continue
  fi
  if grep -qx "$module" <<<"$demo"; then echo "ok   envs/demo composes $module"; else fail "$module: envs/demo does not compose it"; fi
done

for env in "$infra"/envs/*/; do
  name=$(basename "$env")
  [ "$name" = demo ] && continue
  if [ "$(sources "$env")" = "$demo" ]; then echo "ok   envs/$name composes the same modules as envs/demo"; else fail "envs/$name: composes $(sources "$env" | tr '\n' ' ')but envs/demo composes $(tr '\n' ' ' <<<"$demo")"; fi
done

exit $((failures > 0))
