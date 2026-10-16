#!/usr/bin/env python3
"""
patch_night.py - patch XiaomiCamera (Leica Camera) for selene / MT6768.

MASALAH
-------
MT6768 (Redmi Note 10 / selene) has NO MFB block at all: 0 MFB M4U ports,
0 MFB events in the IRQ, no MFB driver/clock/node. XiaomiCamera still requests
hardware MFNR in Night mode / 1.0X zoom -> the HAL waits for an MFB that never finishes
-> "wait task result failed:-110" (ETIMEDOUT) -> onCameraAbnormal -> foto hilang.

SOLUSI
------
Force the request: disable hardware MFB, enable software MFNR. Done at the
TAG WRITING POINT (MiCameraCompatBaseImpl) rather than at the invoking call
so it applies globally to every mode without having to find 30+ call sites.

PAKAI
-----
    patch_night.py <direktori-smali-apktool> [--check]

    --check   verify only; NEVER write anything.
              Used to inspect the resulting APK. A verifier must not
              "repair" the file it is verifying.

exit 0 = success (3 methods patched / already correct)
exit 1 = failure, with a clear reason. Never silently "succeeds".
"""

import re
import sys
from pathlib import Path

# method -> value forced into p2
# p2 = register parameter ke-3 (p0=this, p1=builder, p2=boolean)
PATCHES = {
    "applyMfnr":           "0x0",   # hardware MFNR (MFB)   -> MATI
    "applySwMfnr":         "0x1",   # software MFNR         -> NYALA
    "applySuperNightMfnr": "0x0",   # super-night MFB       -> MATI
}

TARGET_REL = Path("smali_classes2/com/android/camera2/compat/MiCameraCompatBaseImpl.smali")

CONST4_RE = re.compile(r"^\s*const/4\s+[vp]\d+\s*,\s*(0x[0-9a-fA-F]+)\s*$")


class PatchError(Exception):
    """A failure that must halt the process - never let it pass silently."""


def find_method(lines, name):
    """Return the (start, end) line indices of method `name`'s body."""
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
            f"method '{name}' at line {start+1} has no '.end method' - is the smali file corrupt?"
        )
    return None


def first_insn(lines, start, end):
    """Index baris instruksi PERTAMA di body method, atau None.

    PENTING: isi blok .annotation (mis. "ignore = false", "0x0,") BUKAN instruksi.
    Mis-detecting it puts the const/4 inside an annotation block and smali then fails to
    compile with:
        missing END_ANNOTATION_DIRECTIVE at 'const/4'
    So annotation depth has to be tracked (.annotation / .end annotation).
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
        if depth > 0:                # still inside an annotation -> not an instruction
            continue
        # Sanity: a smali instruction never contains '=' or starts with a quote.
        if "=" in s or s.startswith('"'):
            raise PatchError(
                f"baris {i+1} '{s}' is normally not an instruction. The parser cannot be sure "
                f"yakin di mana body method mulai - STOP, jangan patch tebakan."
            )
        return i
    return None


def patch_method(lines, name, value):
    """Sisipkan const/4 p2, <value> sebagai instruksi pertama. Idempoten."""
    span = find_method(lines, name)
    if span is None:
        raise PatchError(
            f"method '{name}' NOT FOUND.\n"
            f"    -> This APK may be a different version, or the methods were renamed.\n"
            f"    -> Do NOT assume the patch succeeded; stop here."
        )
    start, end = span
    first = first_insn(lines, start, end)
    if first is None:
        raise PatchError(f"method '{name}' (line {start+1}) has no instructions at all")

    # Idempotency: check the FIRST instruction itself, not the line before it.
    # (the line before it is usually blank or ".end annotation")
    m = CONST4_RE.match(lines[first])
    if m:
        if m.group(1).lower() == value.lower():
            return "already"
        raise PatchError(
            f"method '{name}': first instruction is already const/4 with value "
            f"{m.group(1)}, but the expected value is {value}.\n"
            f"    -> an existing patch uses a different value - STOP, do not overwrite."
        )

    lines.insert(first, f"    const/4 p2, {value}")
    return "patched"


def verify(lines):
    """The FIRST instruction of each method must be exactly const/4 p2, <expected>."""
    problems = []
    for name, value in PATCHES.items():
        span = find_method(lines, name)
        if span is None:
            problems.append(f"{name}: method not found")
            continue
        start, end = span
        first = first_insn(lines, start, end)
        if first is None:
            problems.append(f"{name}: empty body")
            continue
        m = CONST4_RE.match(lines[first])
        if not m:
            problems.append(
                f"{name}: instruksi pertama '{lines[first].strip()}' "
                f"is not const/4 p2 (no patch here)"
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
            print(f"  [i] not at the standard path, but found: {cands[0].relative_to(root)}")
            target = cands[0]
        elif len(cands) > 1:
            print("  [!] more than one MiCameraCompatBaseImpl.smali exists:")
            for c in cands:
                print(f"        {c.relative_to(root)}")
            print("  [!] stop - pick the right one yourself.")
            return 1
        else:
            print(f"  [X] MiCameraCompatBaseImpl.smali not found in {root}")
            print("  [X] STOP. This APK is probably not the XiaomiCamera we know.")
            return 1

    lines = target.read_text(encoding="utf-8").split("\n")
    before = len(lines)

    print(f"  target : {target.relative_to(root)}  ({before} lines)")
    mode = "CHECK (read-only)" if check_only else "PATCH"
    print(f"  mode   : {mode}")
    print()

    # ── check mode: inspect the file as-is, never touch it ──
    if check_only:
        try:
            problems = verify(lines)
        except PatchError as e:
            print(f"    [X] {e}")
            print()
            print("  [X] FAILED - the file cannot be verified.")
            return 1
        if problems:
            for p in problems:
                print(f"    [X] {p}")
            print()
            print("  [X] FAILED - the patch is NOT complete in this file.")
            return 1
        for name, value in PATCHES.items():
            print(f"    [OK] {name:22s} const/4 p2, {value}")
        print()
        print("  [OK] all patches are present with the correct values.")
        return 0

    results = {}
    for name, value in PATCHES.items():
        try:
            results[name] = patch_method(lines, name, value)
        except PatchError as e:
            print(f"  [X] {name}: {e}")
            print()
            print("  [X] PATCH FAILED - file NOT written, the APK will not be built.")
            return 1

    print("  result:")
    for name in PATCHES:
        state = results[name]
        mark = "=" if state == "already" else "+"
        print(f"    {mark} {name:22s} {state}")

    print()
    print("  verification:")
    try:
        problems = verify(lines)
    except PatchError as e:
        print(f"    [X] {e}")
        print()
        print("  [X] VERIFICATION FAILED - file NOT written.")
        return 1
    if problems:
        for p in problems:
            print(f"    [X] {p}")
        print()
        print("  [X] VERIFICATION FAILED - file NOT written.")
        return 1
    for name, value in PATCHES.items():
        print(f"    [OK] {name:22s} const/4 p2, {value}")

    if all(v == "already" for v in results.values()):
        print()
        print("  [i] already correct, nothing changed (idempotent).")
        return 0

    if check_only:
        print()
        print("  [X] mode --check: the patch is NOT present in this file. Nothing was written.")
        return 1

    target.write_text("\n".join(lines), encoding="utf-8")
    print()
    print(f"  [OK] written: {len(lines) - before:+d} baris")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except PatchError as e:
        print(f"\n  [X] {e}")
        sys.exit(1)