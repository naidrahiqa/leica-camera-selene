#!/usr/bin/env bash
#
# fetch-tools.sh — unduh tooling yang dibutuhkan patch-night.sh
#
#   ./tools/fetch-tools.sh
#
# Tooling sengaja TIDAK disimpan di repo ini: apktool.jar saja 24 MB, dan
# ukurannya berubah tiap rilis. Lebih baik diunduh saat perlu.
#
set -Eeuo pipefail

cd "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

APKTOOL_VER="2.11.1"
SIGNER_VER="1.3.0"

info() { printf '  %s\n' "$*"; }
die()  { printf '\n  [X] %s\n\n' "$*" >&2; exit 1; }

have() { command -v "$1" >/dev/null 2>&1; }

have java || die "java tidak ditemukan. Install JDK 17+ lalu ulangi."
have curl || die "curl tidak ditemukan."

[[ -f apktool.jar ]] || {
  info "mengunduh apktool ${APKTOOL_VER}…"
  curl -sSL -o apktool.jar \
    "https://github.com/iBotPeaches/Apktool/releases/download/v${APKTOOL_VER}/apktool_${APKTOOL_VER}.jar"
  [[ -s apktool.jar ]] || die "gagal mengunduh apktool"
}
info "apktool.jar            $(du -h apktool.jar | cut -f1)"

[[ -f uber-apk-signer.jar ]] || {
  info "mengunduh uber-apk-signer ${SIGNER_VER}…"
  curl -sSL -o uber-apk-signer.jar \
    "https://github.com/patrickfav/uber-apk-signer/releases/download/v${SIGNER_VER}/uber-apk-signer-${SIGNER_VER}.jar"
  [[ -s uber-apk-signer.jar ]] || die "gagal mengunduh uber-apk-signer"
}
info "uber-apk-signer.jar   $(du -h uber-apk-signer.jar | cut -f1)"

printf '\n  [OK] tooling siap.\n  Lanjut:  ./tools/patch-night.sh <MiuiCamera.apk>\n\n'