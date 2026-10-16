#!/usr/bin/env bash
#
# patch-night.sh — patch XiaomiCamera (Leica Camera) for selene / MT6768.
#
#   MT6768 has no MFB block. The app still requests hardware MFNR => timeout -110.
#   This patch forces: hardware MFB OFF, software MFNR ON.
#
# PEMAKAIAN
#   ./patch-night.sh <MiuiCamera.apk> [-o OUTPUT] [--work DIR] [--fast] [--keep]
#
#     -o OUTPUT   result APK filename (default: <input>-selene.apk)
#     --work DIR  direktori kerja (default: ./build)
#     --fast      skip the decode-and-verify pass over the resulting APK
#     --keep      jangan hapus direktori kerja
#
# exit 0 = APK patched & signed, siap install
# exit 1 = failure. The APK is NOT written when patching fails.
#
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

APKTOOL="$SCRIPT_DIR/apktool.jar"
SIGNER="$SCRIPT_DIR/uber-apk-signer.jar"
PATCHER="$SCRIPT_DIR/patch_night.py"

usage() { cat <<'EOF'
patch-night.sh - patch XiaomiCamera (Leica Camera) for selene / MT6768.

  MT6768 has no MFB block at all (0 MFB M4U ports, 0 MFB events in the IRQ,
  no driver/clock/node). The app still requests hardware MFNR in Night mode and at
  1.0X zoom => the HAL waits for an MFB that never finishes =>
  "wait task result failed:-110" => foto hilang.

  This patch forces values at the TAG WRITING POINT (MiCameraCompatBaseImpl), not at
  the call sites that invoke it, so it applies to every mode at once:
      applyMfnr           -> false   hardware MFB  MATI
      applySwMfnr         -> true    software MFNR NYALA
      applySuperNightMfnr -> false   super-night MFB MATI

PEMAKAIAN
  ./patch-night.sh <MiuiCamera.apk> [-o OUTPUT] [--work DIR] [--fast] [--keep]

  -o OUTPUT   result APK filename  (default: <input>-selene.apk)
  --work DIR  direktori kerja      (default: ./build)
  --fast      skip the decode-and-verify pass over the resulting APK
  --keep      jangan hapus artefak kerja

KELUAR
  0  APK ter-patch, ter-sign, siap install
  1  failure. The APK is NOT written when patching or verification fails.
EOF
}
die()  { printf '\n  [X] FATAL: %s\n\n' "$*" >&2; exit 1; }
step() { printf '\n\033[1m[%s/5] %s\033[0m\n' "$1" "$2"; }
info() { printf '  %s\n' "$*"; }

INPUT=""; OUTPUT=""; WORK=""; FAST=0; KEEP=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o|--output) OUTPUT="$2"; shift 2 ;;
    --work)      WORK="$2"; shift 2 ;;
    --fast)      FAST=1; shift ;;
    --keep)      KEEP=1; shift ;;
    -h|--help)   usage; exit 0 ;;
    -*)          echo "[X] unknown option: $1" >&2; exit 2 ;;
    *)           [[ -z "$INPUT" ]] && INPUT="$1" || { echo "[X] too many arguments: $1" >&2; exit 2; }
                 shift ;;
  esac
done

usage() { sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }
die()  { printf '\n  [X] FATAL: %s\n\n' "$*" >&2; exit 1; }
step() { printf '\n\033[1m[%s/5] %s\033[0m\n' "$1" "$2"; }
info() { printf '  %s\n' "$*"; }

usage() { sed -n '2,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }
die()  { printf '\n  [X] FATAL: %s\n\n' "$*" >&2; exit 1; }
step() { printf '\n\033[1m[%s/5] %s\033[0m\n' "$1" "$2"; }
info() { printf '  %s\n' "$*"; }

[[ -n "$INPUT" ]]   || { usage; die "no input APK given"; }
[[ -f "$INPUT" ]]  || die "input APK not found: $INPUT"
[[ -f "$APKTOOL" ]] || die "apktool.jar not found in $SCRIPT_DIR"
[[ -f "$SIGNER" ]]  || die "uber-apk-signer.jar not found in $SCRIPT_DIR"
[[ -f "$PATCHER" ]] || die "patch_night.py not found in $SCRIPT_DIR"

command -v java >/dev/null 2>&1 || die "java not found in PATH"
INPUT="$(readlink -f "$INPUT")"
[[ -n "$OUTPUT" ]] || OUTPUT="${INPUT%.apk}-selene.apk"
[[ -n "$WORK" ]]   || WORK="$ROOT_DIR/build"
mkdir -p "$WORK"
WORK="$(readlink -f "$WORK")"
DEC="$WORK/decoded"; OUTDIR="$WORK/out"

echo
echo "=========================================================="
echo " patch-night : Leica Camera port for selene / MT6768"
echo "=========================================================="
echo "  input  : $INPUT"
echo "        : $(stat -c%s "$INPUT") byte  sha256=$(sha256sum "$INPUT" | cut -c1-16)…"
echo "  output : $OUTPUT"
echo "  work   : $WORK"

# ── 1. decode ────────────────────────────────────────────────────────────────
step 1 "Decode APK -> smali"
if [[ ! -d "$DEC" ]]; then
  java -Xmx6g -jar "$APKTOOL" d -r -f -o "$DEC" "$INPUT" 2>&1 | sed 's/^/    /'
else
  info "(pakai decode cache di $DEC)"
fi
[[ -d "$DEC" ]] || die "decode failed, $DEC was not created"
info "smali files : $(find "$DEC" -name '*.smali' | wc -l)"

# ── 2. patch ─────────────────────────────────────────────────────────────────
step 2 "Patch MiCameraCompatBaseImpl"
if ! python3 "$PATCHER" "$DEC"; then
  die "patching failed - the APK was NOT built (see the message above)"
fi

# ── 3. rebuild ───────────────────────────────────────────────────────────────
step 3 "Rebuild APK"
UNSIGNED="$WORK/unsigned.apk"
rm -f "$UNSIGNED"
java -Xmx6g -jar "$APKTOOL" b "$DEC" -o "$UNSIGNED" 2>&1 | sed 's/^/    /'
[[ -f "$UNSIGNED" ]] || die "build failed, $UNSIGNED was not created"
info "unsigned : $(stat -c%s "$UNSIGNED") byte"

# ── 4. zipalign + sign ───────────────────────────────────────────────────────
step 4 "Zipalign + sign"
rm -rf "$OUTDIR"; mkdir -p "$OUTDIR"
java -Xmx4g -jar "$SIGNER" -a "$UNSIGNED" -o "$OUTDIR" --allowResign 2>&1 \
  | grep -aE 'zipalign|sign |signature|Successfully|error|ERROR' | sed 's/^/    /'
SIGNED="$(find "$OUTDIR" -maxdepth 1 -name '*-debugSigned.apk' ! -name '*.idsig' | head -1)"
[[ -n "$SIGNED" && -f "$SIGNED" ]] || die "signing failed, no signed APK in $OUTDIR"
info "signed   : $(stat -c%s "$SIGNED") byte"

# ── 5. verify ────────────────────────────────────────────────────────────
step 5 "Verify"
cp -f "$SIGNED" "$OUTPUT"
info "sha256   : $(sha256sum "$OUTPUT" | cut -d' ' -f1)"

if [[ "$FAST" -eq 0 ]]; then
  VDIR="$WORK/verify"
  rm -rf "$VDIR"

  # Verify with the patcher itself, not with an ad-hoc grep in the shell.
  # Reason: the "first instruction" has to be computed by tracking .annotation blocks.
  # A naive grep/head such as `awk ... | head -8` gets it wrong and reports the patch
  # as missing even though it is present. patch_night.py handles this correctly and is
  # idempotent - for an already-patched APK it reports "already" for all three.
  info "decoding again to confirm the patch really is in the final APK…"
  if ! java -Xmx6g -jar "$APKTOOL" d -r -f -o "$VDIR" "$OUTPUT" >"$WORK/verify-decode.log" 2>&1; then
    tail -20 "$WORK/verify-decode.log" | sed 's/^/    /'
    die "verification failed: the resulting APK cannot be decoded"
  fi

  if ! python3 "$PATCHER" "$VDIR" --check >"$WORK/verify.log" 2>&1; then
    sed 's/^/    /' "$WORK/verify.log"
    echo
    die "VERIFICATION FAILED - the patch is not complete in the resulting APK. The OUTPUT file exists but must NOT be used."
  fi
  sed -n '/result:/,$p' "$WORK/verify.log" | sed 's/^/  /'
  rm -rf "$VDIR"
  info "all patches verified in the final APK"
fi

# signature sanity
if command -v unzip >/dev/null 2>&1; then
  unzip -t "$OUTPUT" >/dev/null 2>&1 || die "resulting APK is corrupt (zip CRC failed)"
  info "zip CRC  : OK"
fi

if [[ "$KEEP" -eq 0 ]]; then
  rm -rf "$DEC" "$OUTDIR" "$UNSIGNED"
else
  info "(--keep: working artifacts kept in $WORK)"
fi

cat <<EOF

==========================================================
 DONE
==========================================================
  output : $OUTPUT
  ukuran : $(stat -c%s "$OUTPUT") byte
  sha256 : $(sha256sum "$OUTPUT" | cut -d' ' -f1)

  install:
    adb shell su -c 'cp $OUTPUT \\
      /data/adb/modules/xiaomicamera/system/priv-app/MiuiCamera/MiuiCamera.apk'
    adb shell su -c reboot

  rollback (the original APK is at /data/local/tmp/MiuiCamera.apk.ORIG):
    adb shell su -c 'cp /data/local/tmp/MiuiCamera.apk.ORIG \\
      /data/adb/modules/xiaomicamera/system/priv-app/MiuiCamera/MiuiCamera.apk'

EOF