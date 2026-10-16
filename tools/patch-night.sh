#!/usr/bin/env bash
#
# patch-night.sh — patch XiaomiCamera (Leica Camera) untuk selene / MT6768.
#
#   MT6768 tidak punya blok MFB. App tetap request MFNR hardware => timeout -110.
#   Patch ini memaksa: hardware MFB OFF, software MFNR ON.
#
# PEMAKAIAN
#   ./patch-night.sh <MiuiCamera.apk> [-o OUTPUT] [--work DIR] [--fast] [--keep]
#
#     -o OUTPUT   nama APK hasil (default: <input>-selene.apk)
#     --work DIR  direktori kerja (default: ./build)
#     --fast      lewati verifikasi decode ulang APK hasil
#     --keep      jangan hapus direktori kerja
#
# exit 0 = APK patched & signed, siap install
# exit 1 = gagal. APK TIDAK ditulis kalau patching gagal.
#
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

APKTOOL="$SCRIPT_DIR/apktool.jar"
SIGNER="$SCRIPT_DIR/uber-apk-signer.jar"
PATCHER="$SCRIPT_DIR/patch_night.py"

usage() { cat <<'EOF'
patch-night.sh - patch XiaomiCamera (Leica Camera) untuk selene / MT6768.

  MT6768 tidak punya blok MFB sama sekali (0 port MFB M4U, 0 event MFB di IRQ,
  tidak ada driver/clock/node). App tetap request MFNR hardware saat Night dan
  zoom 1.0X => HAL menunggu MFB yang tidak pernah selesai =>
  "wait task result failed:-110" => foto hilang.

  Patch ini memaksa di TITIK PENULISAN TAG (MiCameraCompatBaseImpl), bukan di
  call site pemanggilnya, sehingga berlaku untuk semua mode sekaligus:
      applyMfnr           -> false   hardware MFB  MATI
      applySwMfnr         -> true    software MFNR NYALA
      applySuperNightMfnr -> false   super-night MFB MATI

PEMAKAIAN
  ./patch-night.sh <MiuiCamera.apk> [-o OUTPUT] [--work DIR] [--fast] [--keep]

  -o OUTPUT   nama APK hasil       (default: <input>-selene.apk)
  --work DIR  direktori kerja      (default: ./build)
  --fast      lewati verifikasi decode ulang APK hasil
  --keep      jangan hapus artefak kerja

KELUAR
  0  APK ter-patch, ter-sign, siap install
  1  gagal. APK TIDAK ditulis kalau patching atau verifikasi gagal.
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
    -*)          echo "[X] opsi tidak dikenal: $1" >&2; exit 2 ;;
    *)           [[ -z "$INPUT" ]] && INPUT="$1" || { echo "[X] terlalu banyak argumen: $1" >&2; exit 2; }
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

[[ -n "$INPUT" ]]   || { usage; die "APK input belum diisi"; }
[[ -f "$INPUT" ]]  || die "APK input tidak ditemukan: $INPUT"
[[ -f "$APKTOOL" ]] || die "apktool.jar tidak ada di $SCRIPT_DIR"
[[ -f "$SIGNER" ]]  || die "uber-apk-signer.jar tidak ada di $SCRIPT_DIR"
[[ -f "$PATCHER" ]] || die "patch_night.py tidak ada di $SCRIPT_DIR"

command -v java >/dev/null 2>&1 || die "java tidak ditemukan di PATH"
INPUT="$(readlink -f "$INPUT")"
[[ -n "$OUTPUT" ]] || OUTPUT="${INPUT%.apk}-selene.apk"
[[ -n "$WORK" ]]   || WORK="$ROOT_DIR/build"
mkdir -p "$WORK"
WORK="$(readlink -f "$WORK")"
DEC="$WORK/decoded"; OUTDIR="$WORK/out"

echo
echo "=========================================================="
echo " patch-night : Leica Camera port untuk selene / MT6768"
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
[[ -d "$DEC" ]] || die "decode gagal, $DEC tidak terbentuk"
info "smali files : $(find "$DEC" -name '*.smali' | wc -l)"

# ── 2. patch ─────────────────────────────────────────────────────────────────
step 2 "Patch MiCameraCompatBaseImpl"
if ! python3 "$PATCHER" "$DEC"; then
  die "patching gagal — APK hasil TIDAK dibangun (lihat pesan di atas)"
fi

# ── 3. rebuild ───────────────────────────────────────────────────────────────
step 3 "Rebuild APK"
UNSIGNED="$WORK/unsigned.apk"
rm -f "$UNSIGNED"
java -Xmx6g -jar "$APKTOOL" b "$DEC" -o "$UNSIGNED" 2>&1 | sed 's/^/    /'
[[ -f "$UNSIGNED" ]] || die "build gagal, $UNSIGNED tidak terbentuk"
info "unsigned : $(stat -c%s "$UNSIGNED") byte"

# ── 4. zipalign + sign ───────────────────────────────────────────────────────
step 4 "Zipalign + sign"
rm -rf "$OUTDIR"; mkdir -p "$OUTDIR"
java -Xmx4g -jar "$SIGNER" -a "$UNSIGNED" -o "$OUTDIR" --allowResign 2>&1 \
  | grep -aE 'zipalign|sign |signature|Successfully|error|ERROR' | sed 's/^/    /'
SIGNED="$(find "$OUTDIR" -maxdepth 1 -name '*-debugSigned.apk' ! -name '*.idsig' | head -1)"
[[ -n "$SIGNED" && -f "$SIGNED" ]] || die "signing gagal, tidak ada APK signed di $OUTDIR"
info "signed   : $(stat -c%s "$SIGNED") byte"

# ── 5. verifikasi ────────────────────────────────────────────────────────────
step 5 "Verifikasi"
cp -f "$SIGNED" "$OUTPUT"
info "sha256   : $(sha256sum "$OUTPUT" | cut -d' ' -f1)"

if [[ "$FAST" -eq 0 ]]; then
  VDIR="$WORK/verify"
  rm -rf "$VDIR"

  # Verifikasi dengan patcher-nya sendiri, bukan grep sendiri di shell.
  # Alasannya: "instruksi pertama" harus dihitung dengan melacak blok .annotation.
  # Grep/head sepele seperti `awk ... | head -8` akan salah dan melaporkan patch
  # hilang padahal ada. patch_night.py sudah benar, dan idempoten — kalau APK hasil
  # sudah ter-patch, dia melaporkan "already" untuk ketiganya.
  info "decode ulang untuk memastikan patch benar-benar ada di APK akhir…"
  if ! java -Xmx6g -jar "$APKTOOL" d -r -f -o "$VDIR" "$OUTPUT" >"$WORK/verify-decode.log" 2>&1; then
    tail -20 "$WORK/verify-decode.log" | sed 's/^/    /'
    die "verifikasi gagal: APK hasil tidak bisa di-decode"
  fi

  if ! python3 "$PATCHER" "$VDIR" --check >"$WORK/verify.log" 2>&1; then
    sed 's/^/    /' "$WORK/verify.log"
    echo
    die "verifikasi GAGAL - patch tidak utuh di APK hasil. File OUTPUT sudah ada tapi JANGAN dipakai."
  fi
  sed -n '/hasil:/,$p' "$WORK/verify.log" | sed 's/^/  /'
  rm -rf "$VDIR"
  info "semua patch terverifikasi di APK akhir"
fi

# signature sanity
if command -v unzip >/dev/null 2>&1; then
  unzip -t "$OUTPUT" >/dev/null 2>&1 || die "APK hasil rusak (CRC zip gagal)"
  info "zip CRC  : OK"
fi

if [[ "$KEEP" -eq 0 ]]; then
  rm -rf "$DEC" "$OUTDIR" "$UNSIGNED"
else
  info "(--keep: artefak kerja disimpan di $WORK)"
fi

cat <<EOF

==========================================================
 SELESAI
==========================================================
  output : $OUTPUT
  ukuran : $(stat -c%s "$OUTPUT") byte
  sha256 : $(sha256sum "$OUTPUT" | cut -d' ' -f1)

  install:
    adb shell su -c 'cp $OUTPUT \\
      /data/adb/modules/xiaomicamera/system/priv-app/MiuiCamera/MiuiCamera.apk'
    adb shell su -c reboot

  rollback (APK asli ada di /data/local/tmp/MiuiCamera.apk.ORIG):
    adb shell su -c 'cp /data/local/tmp/MiuiCamera.apk.ORIG \\
      /data/adb/modules/xiaomicamera/system/priv-app/MiuiCamera/MiuiCamera.apk'

EOF