#!/usr/bin/env python3
"""
patch_night.py - patch XiaomiCamera (Leica Camera) untuk selene / MT6768.

MASALAH
-------
MT6768 (Redmi Note 10 / selene) TIDAK punya blok MFB sama sekali: 0 port MFB M4U,
0 event MFB di IRQ, tidak ada driver/clock/node MFB. App XiaomiCamera tetap me-request
MFNR hardware saat Night / zoom 1.0X -> HAL menunggu MFB yang tidak pernah selesai
-> "wait task result failed:-110" (ETIMEDOUT) -> onCameraAbnormal -> foto hilang.

SOLUSI
------
Paksa request-nya: matikan hardware MFB, nyalakan software MFNR. Dilakukan di
TITIK PENULISAN TAG (MiCameraCompatBaseImpl), bukan di call site pemanggilnya,
supaya berlaku global untuk semua mode tanpa harus menemukan 30+ call site.

PAKAI
-----
    patch_night.py <direktori-smali-apktool> [--check]

    --check   hanya verifikasi, JANGAN menulis file sama sekali.
              Dipakai untuk memeriksa APK hasil: verifier tidak boleh
              "memperbaiki" file yang sedang diverifikasi.

exit 0 = sukses (3 method ter-patch / sudah sesuai)
exit 1 = gagal, dengan alasan jelas. Tidak pernah diam-diam "berhasil".
"""

import re
import sys
from pathlib import Path

# method -> nilai yang dipaksakan ke p2
# p2 = register parameter ke-3 (p0=this, p1=builder, p2=boolean)
PATCHES = {
    "applyMfnr":           "0x0",   # hardware MFNR (MFB)   -> MATI
    "applySwMfnr":         "0x1",   # software MFNR         -> NYALA
    "applySuperNightMfnr": "0x0",   # super-night MFB       -> MATI
}

TARGET_REL = Path("smali_classes2/com/android/camera2/compat/MiCameraCompatBaseImpl.smali")

CONST4_RE = re.compile(r"^\s*const/4\s+[vp]\d+\s*,\s*(0x[0-9a-fA-F]+)\s*$")


class PatchError(Exception):
    """Kegagalan yang harus menghentikan proses - JANGAN diloloskan diam-diam."""


def find_method(lines, name):
    """Kembalikan (start, end) index baris untuk body method `name`."""
    start = None
    for i, ln in enumerate(lines):
        if start is None:
            if re.match(rf"^\.method\b.*\b{re.escape(name)}\(", ln):
                start = i
            continue
        if ln.strip() == ".end method":
            return start, i
    if start is not None:
        raise PatchError(
            f"method '{name}' di baris {start+1} tidak punya '.end method' - file smali rusak?"
        )
    return None


def first_insn(lines, start, end):
    """Index baris instruksi PERTAMA di body method, atau None.

    PENTING: isi blok .annotation (mis. "ignore = false", "0x0,") BUKAN instruksi.
    Salah mendeteksi membuat const/4 tersisip di dalam annotation dan smali gagal
    compile dengan:
        missing END_ANNOTATION_DIRECTIVE at 'const/4'
    Jadi harus lacak kedalaman annotation (.annotation / .end annotation).
    """
    depth = 0
    for i in range(start, end):
        s = lines[i].strip()
        if s.startswith(".annotation"):
            depth += 1
            continue
        if s == ".end annotation":
            depth = max(0, depth - 1)
            continue
        if s.startswith("."):        # directive lain: .locals .param .line .local ...
            continue
        if not s:                    # baris kosong
            continue
        if depth > 0:                # masih di dalam annotation -> bukan instruksi
            continue
        # Sanity: instruksi smali tidak pernah mengandung '=' atau diawali kutip.
        if "=" in s or s.startswith('"'):
            raise PatchError(
                f"baris {i+1} '{s}' normalnya bukan instruksi. Parser tidak bisa "
                f"yakin di mana body method mulai - STOP, jangan patch tebakan."
            )
        return i
    return None


def patch_method(lines, name, value):
    """Sisipkan const/4 p2, <value> sebagai instruksi pertama. Idempoten."""
    span = find_method(lines, name)
    if span is None:
        raise PatchError(
            f"method '{name}' TIDAK DITEMUKAN.\n"
            f"    -> APK ini mungkin versi lain, atau nama method sudah berubah.\n"
            f"    -> JANGAN diasumsikan patch berhasil; stop di sini."
        )
    start, end = span
    first = first_insn(lines, start, end)
    if first is None:
        raise PatchError(f"method '{name}' (baris {start+1}) tidak punya instruksi sama sekali")

    # Idempotensi: cek instruksi PERTAMA itu sendiri, bukan baris sebelumnya.
    # (baris sebelumnya biasanya baris kosong / ".end annotation")
    m = CONST4_RE.match(lines[first])
    if m:
        if m.group(1).lower() == value.lower():
            return "already"
        raise PatchError(
            f"method '{name}': instruksi pertama sudah const/4 dengan nilai "
            f"{m.group(1)}, sedangkan yang diharapkan {value}.\n"
            f"    -> sudah ada patch dengan nilai lain - STOP, jangan menimpa."
        )

    lines.insert(first, f"    const/4 p2, {value}")
    return "patched"


def verify(lines):
    """Instruksi PERTAMA tiap method harus persis const/4 p2, <nilai yang diharapkan>."""
    problems = []
    for name, value in PATCHES.items():
        span = find_method(lines, name)
        if span is None:
            problems.append(f"{name}: method tidak ada")
            continue
        start, end = span
        first = first_insn(lines, start, end)
        if first is None:
            problems.append(f"{name}: body kosong")
            continue
        m = CONST4_RE.match(lines[first])
        if not m:
            problems.append(
                f"{name}: instruksi pertama '{lines[first].strip()}' "
                f"bukan const/4 p2 (patch tidak ada di sini)"
            )
        elif m.group(1).lower() != value.lower():
            problems.append(f"{name}: nilai {m.group(1)}, harusnya {value}")
    return problems


def main():
    args = [a for a in sys.argv[1:] if a != "--check"]
    check_only = "--check" in sys.argv[1:]

    if len(args) != 1:
        print(__doc__)
        return 2

    root = Path(args[0])
    target = root / TARGET_REL

    if not target.is_file():
        cands = list(root.rglob("MiCameraCompatBaseImpl.smali"))
        if len(cands) == 1:
            print(f"  [i] tidak di path standar, tapi ketemu: {cands[0].relative_to(root)}")
            target = cands[0]
        elif len(cands) > 1:
            print("  [!] ada LEBIH dari satu MiCameraCompatBaseImpl.smali:")
            for c in cands:
                print(f"        {c.relative_to(root)}")
            print("  [!] stop - pilih sendiri yang benar.")
            return 1
        else:
            print(f"  [X] MiCameraCompatBaseImpl.smali tidak ditemukan di {root}")
            print("  [X] STOP. APK ini kemungkinan bukan XiaomiCamera yang kita kenal.")
            return 1

    lines = target.read_text(encoding="utf-8").split("\n")
    before = len(lines)

    print(f"  target : {target.relative_to(root)}  ({before} baris)")
    mode = "CHECK (tidak menulis)" if check_only else "PATCH"
    print(f"  mode   : {mode}")
    print()

    # ── mode check: hanya periksa file apa adanya, jangan sentuh sama sekali ──
    if check_only:
        try:
            problems = verify(lines)
        except PatchError as e:
            print(f"    [X] {e}")
            print()
            print("  [X] GAGAL - file tidak bisa diverifikasi.")
            return 1
        if problems:
            for p in problems:
                print(f"    [X] {p}")
            print()
            print("  [X] GAGAL - patch BELUM lengkap di file ini.")
            return 1
        for name, value in PATCHES.items():
            print(f"    [OK] {name:22s} const/4 p2, {value}")
        print()
        print("  [OK] semua patch ada dan nilainya benar.")
        return 0

    results = {}
    for name, value in PATCHES.items():
        try:
            results[name] = patch_method(lines, name, value)
        except PatchError as e:
            print(f"  [X] {name}: {e}")
            print()
            print("  [X] PATCH GAGAL - file TIDAK ditulis, APK tidak akan dibangun.")
            return 1

    print("  hasil:")
    for name in PATCHES:
        state = results[name]
        mark = "=" if state == "already" else "+"
        print(f"    {mark} {name:22s} {state}")

    print()
    print("  verifikasi:")
    try:
        problems = verify(lines)
    except PatchError as e:
        print(f"    [X] {e}")
        print()
        print("  [X] VERIFIKASI GAGAL - file TIDAK ditulis.")
        return 1
    if problems:
        for p in problems:
            print(f"    [X] {p}")
        print()
        print("  [X] VERIFIKASI GAGAL - file TIDAK ditulis.")
        return 1
    for name, value in PATCHES.items():
        print(f"    [OK] {name:22s} const/4 p2, {value}")

    if all(v == "already" for v in results.values()):
        print()
        print("  [i] sudah sesuai, tidak ada perubahan (idempoten).")
        return 0

    if check_only:
        print()
        print("  [X] mode --check: patch BELUM ada di file ini. Tidak ada yang ditulis.")
        return 1

    target.write_text("\n".join(lines), encoding="utf-8")
    print()
    print(f"  [OK] ditulis: {len(lines) - before:+d} baris")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PatchError as e:
        print(f"\n  [X] {e}")
        sys.exit(1)