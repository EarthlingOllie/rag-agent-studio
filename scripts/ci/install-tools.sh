#!/usr/bin/env bash
# Installs pinned, checksum-verified CLI tools for the CI gates into $TOOLS_BIN (default ~/.local/bin).
# Usage: scripts/ci/install-tools.sh terraform tflint gitleaks trivy checkov
# Release binaries are downloaded directly rather than through third-party actions, so every version and
# checksum is reviewed here. Trivy stays on 0.69.3, the last release before the compromised 0.69.4.
set -euo pipefail

TOOLS_BIN=${TOOLS_BIN:-$HOME/.local/bin}
mkdir -p "$TOOLS_BIN"
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

fetch() { # url sha256 file
  curl -fsSL --retry 3 -o "$work/$3" "$1"
  echo "$2  $work/$3" | sha256sum --check --quiet
}

unzip_to_bin() { # zip member
  python3 -c 'import sys, zipfile; zipfile.ZipFile(sys.argv[1]).extract(sys.argv[2], sys.argv[3])' "$1" "$2" "$TOOLS_BIN"
}

for tool in "$@"; do
  case "$tool" in
    terraform)
      fetch https://releases.hashicorp.com/terraform/1.13.4/terraform_1.13.4_linux_amd64.zip \
        98aa516201e948306698efd9954ab4cc0d1227c2578ba56245898b5f679e590b terraform.zip
      unzip_to_bin "$work/terraform.zip" terraform; chmod +x "$TOOLS_BIN/terraform" ;;
    tflint)
      fetch https://github.com/terraform-linters/tflint/releases/download/v0.59.1/tflint_linux_amd64.zip \
        6108d84282292f11d793dc8038ce08fbc629dcd25324d6f13c63d8100b52e01f tflint.zip
      unzip_to_bin "$work/tflint.zip" tflint; chmod +x "$TOOLS_BIN/tflint" ;;
    gitleaks)
      fetch https://github.com/gitleaks/gitleaks/releases/download/v8.28.0/gitleaks_8.28.0_linux_x64.tar.gz \
        a65b5253807a68ac0cafa4414031fd740aeb55f54fb7e55f386acb52e6a840eb gitleaks.tar.gz
      tar -xzf "$work/gitleaks.tar.gz" -C "$TOOLS_BIN" gitleaks ;;
    trivy)
      fetch https://github.com/aquasecurity/trivy/releases/download/v0.69.3/trivy_0.69.3_Linux-64bit.tar.gz \
        1816b632dfe529869c740c0913e36bd1629cb7688bd5634f4a858c1d57c88b75 trivy.tar.gz
      tar -xzf "$work/trivy.tar.gz" -C "$TOOLS_BIN" trivy ;;
    checkov)
      uv tool install --quiet checkov==3.4.3 ;;
    *)
      echo "Unknown tool: $tool" >&2; exit 2 ;;
  esac
  echo "Installed $tool"
done

if [ -n "${GITHUB_PATH:-}" ]; then echo "$TOOLS_BIN" >> "$GITHUB_PATH"; fi
