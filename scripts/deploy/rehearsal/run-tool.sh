#!/usr/bin/env bash
# Runs terraform or the AWS CLI for the rehearsal (ticket 23-03) in a container on the rehearsal's tools network, which
# reaches Floci and nothing else: no AWS account can be touched, whatever credentials this machine holds. The
# terraform and aws files beside this script call it; scripts/deploy/rehearse.sh puts this folder first on PATH, so
# the unchanged deploy scripts run these tools. Floci answers there as floci, and its alias 000000000000.floci makes
# the S3 Control host the AWS provider asks for resolve (infra/rehearsal/compose.yml).
# Only the rehearsal's own settings reach the container: the endpoint, the dummy credentials and region, TF_DATA_DIR
# and TF_VAR_*.
# The repository and the temporary folder are mounted at the same paths, so paths given on the command line work.
# Usage: scripts/deploy/rehearsal/run-tool.sh <terraform|aws> [arguments...]
# Optional: REHEARSAL_TOOLS_NETWORK (default studio-rehearsal-tools), REHEARSAL_TERRAFORM_IMAGE, REHEARSAL_AWS_IMAGE,
# REHEARSAL_TOOLS_DOCKER_ARGS (more `docker run` arguments, split on spaces: for example a provider mirror's mount).
set -euo pipefail

repo=$(cd "$(dirname "$0")/../../.." && pwd)
tool=${1:?usage: $0 <terraform|aws> [arguments...]}
shift
case "$tool" in
  terraform) image=${REHEARSAL_TERRAFORM_IMAGE:-hashicorp/terraform:1.14.0} ;;
  aws) image=${REHEARSAL_AWS_IMAGE:-amazon/aws-cli:2.31.0} ;;
  *) echo "usage: $0 <terraform|aws> [arguments...]" >&2; exit 2 ;;
esac
tmp=${TMPDIR:-/tmp}
tmp=${tmp%/}

args=(--rm -i --network "${REHEARSAL_TOOLS_NETWORK:-studio-rehearsal-tools}" -u "$(id -u):$(id -g)"
  -v "$repo:$repo" -v "$tmp:$tmp" -w "$PWD" -e HOME=/tmp -e TF_IN_AUTOMATION=1 -e AWS_EC2_METADATA_DISABLED=true)
for name in AWS_ENDPOINT_URL AWS_ACCESS_KEY_ID AWS_SECRET_ACCESS_KEY AWS_REGION AWS_DEFAULT_REGION TF_DATA_DIR $(compgen -e | grep '^TF_VAR_' || true); do
  [ -z "${!name+set}" ] || args+=(-e "$name")
done
# shellcheck disable=SC2206 # Split on spaces on purpose.
extra=(${REHEARSAL_TOOLS_DOCKER_ARGS:-})
exec docker run "${args[@]}" "${extra[@]}" --entrypoint "$tool" "$image" "$@"
