#!/usr/bin/env bash
#
# fetch-tools.sh — download the tooling patch-night.sh needs
#
#   ./tools/fetch-tools.sh
#
# The tooling is deliberately not stored in this repo: apktool.jar alone is 24 MB, and
# its size changes with every release. Downloading on demand is better.
#
set -Eeuo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

APKTOOL_VER="2.11.1"
SIGNER_VER="1.3.0"

info() { printf '  %s\n' "$*"; }
die()  { printf '\n  [X] %s\n\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

have java || die "java not found. Install JDK 17+ and retry."
have curl || die "curl not found."

[[ -f apktool.jar ]] || {
  info "downloading apktool ${APKTOOL_VER}…"
  curl -sSL -o apktool.jar \
    "https://github.com/iBotPeaches/Apktool/releases/download/v${APKTOOL_VER}/apktool_${APKTOOL_VER}.jar"
  [[ -s apktool.jar ]] || die "failed to download apktool"
}
info "apktool.jar            $(du -h apktool.jar | cut -f1)"

[[ -f uber-apk-signer.jar ]] || {
  info "downloading uber-apk-signer ${SIGNER_VER}…"
  curl -sSL -o uber-apk-signer.jar \
    "https://github.com/patrickfav/uber-apk-signer/releases/download/v${SIGNER_VER}/uber-apk-signer-${SIGNER_VER}.jar"
  [[ -s uber-apk-signer.jar ]] || die "failed to download uber-apk-signer"
}
info "uber-apk-signer.jar   $(du -h uber-apk-signer.jar | cut -f1)"

printf '\n  [OK] tooling ready.\n  Next:  ./tools/patch-night.sh <MiuiCamera.apk>\n\n'