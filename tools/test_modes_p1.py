#!/usr/bin/env python3
"""
test_modes_p1.py - test the camera modes that had never been exercised.

Core modes tested separately (not repeated here):
    Photo 1.0X/2.0X, Night 1.0X/2.0X, Portrait, Pro, Documents

Photo/Night 0.6X is known-broken on this device: it hangs the camera and
saves no file. Use 1.0X or 2.0X.

The remaining 11 modes:
    panel "More" (node `more_mode_edit`, entries under `mode_name`):
        50MP, Panorama, VLOG, Short film, Slow motion, Time-lapse,
        Sticker avatars, Movie effects, Long exposure, Clone, Director mode
    main row:
        Video

Verdict per mode:
    [OK]    a new file appears, -110 = 0, onCameraAbnormal = 0
    [X]     no file appears, or an error is logged

Usage:
    python3 tools/test_modes_p1.py                    # all modes
    python3 tools/test_modes_p1.py "Night,Clone,VLOG" # resume, selected modes only
"""
import re
import subprocess
import sys
import time

S = "65cb03c00702"
DCIM = "/data/media/0/DCIM/Camera"

PHOTO_MODES = ["50MP", "Panorama", "Sticker avatars",
               "Movie effects", "Long exposure", "Clone"]
# Video modes -> verified by counting .mp4 files.
#
# NOTE: "Director mode" was initially placed in PHOTO_MODES and always failed
# (photos+0). It is actually a VIDEO mode: the shutter records mp4. That was a
# misclassification on the harness side, not a broken mode. Its Cine UI is also
# taller, so the shutter bounds are [412,1924][667,2179] rather than
# [412,1864][667,2119] as in normal modes - which is why _shutter() always reads
# bounds from the UI and never hardcodes them.
VIDEO_MODES = ["Director mode", "VLOG", "Short film",
               "Slow motion", "Time-lapse"]

# Modes that CANNOT be tested automatically: the shutter stays disabled until the
# template is downloaded from the internet (download icon on each template card).
# Not a camera defect.
NEEDS_DOWNLOAD = {
    "VLOG": "every template must be downloaded before recording is possible",
    "Short film": "every template must be downloaded before recording is possible",
}

KNOWN_MODES = ["Documents", "Video", "Photo", "Portrait", "Night", "More",
               "Pro", "50MP", "Panorama", "VLOG", "Short film", "Slow motion",
               "Time-lapse", "Sticker avatars", "Movie effects",
               "Long exposure", "Clone", "Director mode"]

# node desc: "<mode>,Double tap to exit"  - used by modes picked from the More panel
RE_DOUBLE_TAP = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9 +\-]{0,24}),\s*Double tap to exit$")


# ── basics ──────────────────────────────────────────────────────────────────
def sh(cmd, timeout=90):
    try:
        r = subprocess.run(["adb", "-s", S, "shell", cmd],
                           capture_output=True, timeout=timeout)
        return r.stdout.decode("utf-8", "replace").replace("\r", "")
    except Exception as e:
        return f"ERR:{e}"


def focus():
    m = re.search(r"mCurrentFocus=Window\{[^}]*?\s(\S+)\}",
                  sh("dumpsys window | grep mCurrentFocus"))
    return m.group(1) if m else "?"


def parse():
    sh("uiautomator dump /sdcard/ui.xml")
    x = sh("cat /sdcard/ui.xml")
    by_id, flat = {}, []
    for node in re.finditer(r"<node[^>]*>", x):
        t = node.group(0)

        def g(attr):
            m = re.search(attr + r'="([^"]*)"', t)
            return m.group(1) if m else ""
        d = {"text": g("text"), "desc": g("content-desc"),
             "bounds": g("bounds"), "click": g("clickable")}
        by_id.setdefault(g("resource-id").split("/")[-1], []).append(d)
        flat.append(d)
    return by_id, flat


def center(bounds):
    v = [int(x) for x in re.findall(r"-?\d+", bounds)]
    return (v[0] + v[2]) // 2, (v[1] + v[3]) // 2


def count(ext="jpg"):
    """Count <ext> files in DCIM.

    IMPORTANT: do not use `ls .../*.jpg | wc -l`. If the glob does not expand
    (no files momentarily, changed shell quoting) the result is 0 and the delta
    becomes a fake negative number like "photos+-632", which is bogus rather
    than data. Use `ls -1 <dir>` then filter, and if the result is 0 while it
    was not 0 before, read once more before continuing.
    """
    cmd = "su -c \"ls -1 %s 2>/dev/null | grep -c '\\.%s$' || true\"" % (DCIM, ext)

    def read():
        m = re.search(r"(\d+)", sh(cmd))
        return int(m.group(1)) if m else -1

    n = read()
    if n < 0:                      # command failed / output unreadable
        return None
    if n == 0:                      # may be a transient read failure, retry once
        time.sleep(1.5)
        n2 = read()
        if n2 >= 0:
            n = n2
    return n


def cam_focused():
    """True when the screen belongs to the com.android camera package.

    Note: Movie effects / VLOG / Short film open their OWN activity within the
    same package, so do not only compare against ".Camera" - that would treat a
    legitimate activity as "another app stole the screen".
    """
    return "com.android.camera" in focus()


def mode_label():
    """Name of the active mode.

    Three sources, most trustworthy first:
      1. mode_select_view (content-desc) -> a mode on the main row
      2. node desc "<mode>,Double tap to exit" -> a mode from the More panel
      3. node text matching one of KNOWN_MODES, in the mode row area (y > 1600)

    Note: a mode from the "More" panel has NO mode_select_view at all, so
    relying on (1) alone always reports None.
    """
    by_id, flat = parse()

    v = by_id.get("mode_select_view")
    if v and (v[0].get("desc") or "").strip():
        return v[0]["desc"].strip()

    for d in flat:
        m = RE_DOUBLE_TAP.match((d["desc"] or "").strip())
        if m:
            return m.group(1).strip()

    cands = []
    for d in flat:
        t = (d["text"] or "").strip()
        if t in KNOWN_MODES:
            ys = [int(x) for x in re.findall(r"-?\d+", d["bounds"] or "")]
            if len(ys) == 4 and ys[1] > 1600:
                cands.append(t)
    if len(cands) == 1:
        return cands[0]
    if cands:
        return f"?{sorted(set(cands))}"

    # Some modes (Director mode / Cine) put the mode name in content-desc
    # without the "Double tap to exit" suffix and without mode_select_view.
    names = set()
    for d in flat:
        t = (d["desc"] or "").strip()
        if t in KNOWN_MODES:
            ys = [int(x) for x in re.findall(r"-?\d+", d["bounds"] or "")]
            if len(ys) == 4 and ys[1] > 1600:
                names.add(t)
    if len(names) == 1:
        return names.pop()
    if names:
        return f"?{sorted(names)}"
    return None


def camera_ready():
    """Camera focused AND its UI rendered (mode_select_view present and set)."""
    if not cam_focused():
        return False
    return bool(mode_label())


def steal_check(where):
    """Abort when another app has taken the screen (e.g. the phone is in use)."""
    if cam_focused():
        return
    print(f"\n   [!!] TEST ABORTED at {where}: the screen is owned by another app")
    print(f"        focus = {focus()}")
    print(f"        close it / return to the camera, then run again.")
    raise SystemExit(3)


def gate(where="", tries=10):
    """Make sure the camera is focused and rendered. Fails hard if it is not.

    This matters because `am start` can succeed while the screen is actually
    being used by something else, so the check is stricter than "focus is not
    null".
    """
    for _ in range(tries):
        if camera_ready():
            return True
        f = focus()
        if "Shade" in f or "systemui" in f:
            sh("input keyevent 4")
            time.sleep(1.5)
            continue
        sh("am start -n com.android.camera/.Camera")
        time.sleep(6)
    print(f"\n   [!!] GATE FAILED{(' at ' + where) if where else ''}: "
          f"focus={focus()} mode_label={mode_label()!r}")
    return False


# ── mode navigation ─────────────────────────────────────────────────────────
def panel_open():
    by_id, _ = parse()
    return bool(by_id.get("more_mode_edit"))


def panel_modes():
    """[(name, tap_bounds)] from the More panel.

    Uses the `mode_item` bounds (a 3-column grid) rather than `mode_name`,
    which is only a text label and a much smaller target. The lists line up by
    index: mode_name[i] corresponds to mode_item[i].
    """
    by_id, _ = parse()
    names = by_id.get("mode_name", [])
    items = by_id.get("mode_item", [])
    out = []
    for i, n in enumerate(names):
        nm = (n["text"] or "").strip()
        if not nm:
            continue
        b = items[i]["bounds"] if i < len(items) else n["bounds"]
        out.append((nm, b))
    return out


def open_more():
    """Idempotent: do not tap again when the panel is already open (it toggles)."""
    if panel_open():
        return True
    by_id, _ = parse()
    more = [i for i in by_id.get("mode_select_item", []) if i["text"] == "More"]
    if not more:
        for _ in range(4):
            sh("input swipe 250 1758 950 1758 350")
            time.sleep(1.5)
            by_id, _ = parse()
            more = [i for i in by_id.get("mode_select_item", []) if i["text"] == "More"]
            if more:
                break
    if not more:
        return False
    x, y = center(more[0]["bounds"])
    sh(f"input tap {x} {y}")
    time.sleep(3)
    if not panel_open():
        time.sleep(3)
    return panel_open()


def close_panel():
    """Close the panel.

    BACK is used rather than a tap on the centre of more_mode_mask: the mask
    covers the whole screen, so its centre lands on the panel content.
    """
    if not panel_open():
        return
    sh("input keyevent 4")
    time.sleep(3)
    for _ in range(3):
        if not panel_open():
            return
        sh("input keyevent 4")
        time.sleep(2)


def fresh_camera(where=""):
    """Restart the camera from scratch.

    Used before each mode so no state from the previous mode survives (the main
    row changes after a mode is picked from More).
    """
    sh("su -c 'am force-stop com.android.camera'")
    time.sleep(3)
    sh("am start -n com.android.camera/.Camera")
    time.sleep(3)
    return gate(where or "fresh_camera")


def select_more(name, tries=3):
    """Open More, pick `name`, then VERIFY the mode really changed.

    Returns (ok, actual_label). ok=False when it never matched, so that the
    caller cannot shoot the wrong mode and call it a pass.
    """
    last = None
    for t in range(tries):
        if not open_more():
            last = "the More panel did not open"
            close_panel()
            continue
        hit = next((b for nm, b in panel_modes()
                    if nm.lower() == name.lower()), None)
        if hit is None:
            last = f"mode {name!r} is not in the panel"
            close_panel()
            continue
        x, y = center(hit)
        sh(f"input tap {x} {y}")
        time.sleep(6)
        close_panel()
        time.sleep(2)
        steal_check(f"after selecting {name}")
        if not gate(f"after selecting {name}"):
            last = "gate failed"
            continue
        cur = mode_label()
        last = cur
        if cur and cur.strip().lower() == name.lower():
            return True, cur
        print(f"   [?] {name}: mode_label={cur!r} "
              f"(attempt {t+1}/{tries}, retrying)")
    return False, last


def select_row(name, tries=3):
    """Pick a mode from the main row, verified the same way as select_more."""
    for t in range(tries):
        by_id, _ = parse()
        d = {i["text"]: i for i in by_id.get("mode_select_item", []) if i["text"]}
        if name not in d:
            for _ in range(4):
                sh("input swipe 250 1758 950 1758 350")
                time.sleep(1.5)
                by_id, _ = parse()
                d = {i["text"]: i for i in by_id.get("mode_select_item", []) if i["text"]}
                if name in d:
                    break
        if name not in d:
            print(f"   [X] {name}: not in the main row "
                  f"(attempt {t+1}/{tries})")
            continue
        x, y = center(d[name]["bounds"])
        sh(f"input tap {x} {y}")
        time.sleep(6)
        steal_check(f"after selecting {name}")
        if not gate(f"after selecting {name}"):
            continue
        cur = mode_label()
        if cur and cur.strip().lower() == name.lower():
            return True, cur
        print(f"   [?] {name}: mode_label={cur!r} "
              f"(attempt {t+1}/{tries}, retrying)")
    return False, mode_label()


def clone_prereq():
    """Clone needs a source photo first; its button is an arrow, not a capture."""
    by_id, _ = parse()
    for rid in ("clone_photo_mode", "clone_photo_item"):
        items = by_id.get(rid, [])
        if items:
            x, y = center(items[0]["bounds"])
            sh(f"input tap {x} {y}")
            time.sleep(4)
            return f"source tab '{rid}' selected at ({x}, {y})"
    return "clone_photo_mode/item not found - the flow may have changed"


# Prerequisites per mode, invoked once the mode is confirmed active.
PREREQ = {"Clone": clone_prereq}


# ── shooting ────────────────────────────────────────────────────────────────
def _shutter():
    """Coordinates of the shutter button.

    Two sources, both required:
      1. resource-id 'shutter_button'   -> the main UI
      2. content-desc 'Shutter button' -> sub-panels (Movie effects, Clone, ...)
         Nodes in sub-panels have NO resource-id, only content-desc. Relying on
         (1) alone makes those modes always report "no shutter button".
    """
    by_id, flat = parse()
    sb = by_id.get("shutter_button")
    if sb:
        return center(sb[0]["bounds"])
    for d in flat:
        if (d["desc"] or "").strip() == "Shutter button":
            return center(d["bounds"])
    return None


def log_summary(log):
    mf = re.findall(r"applyMfnrEnable: (\w+)", log)
    sw = re.findall(r"applySwMfnrEnable: (\w+)", log)
    return f"Mfnr={mf[0] if mf else '-'} SwMfnr={sw[0] if sw else '-'}"


def shoot_photo(tag, tries=2):
    for t in range(tries):
        sp = _shutter()
        if not sp:
            print(f"   [X]  {tag:24s} no shutter_button")
            return False
        p0 = count("jpg")
        if p0 is None:
            print(f"   [X]  {tag:24s} cannot count files (command problem)")
            return False
        sh("logcat -b all -c")
        sh(f"input tap {sp[0]} {sp[1]}")
        prev = 0
        log = ""
        for w in (8, 15, 22, 30, 40, 52, 65, 80):
            time.sleep(w - prev)
            prev = w
            log = sh("logcat -d -b all", 60)
            if count("jpg") > p0 or "onCameraAbnormal" in log:
                break
        n = count("jpg") - p0
        n110 = log.count("wait task result failed:-110")
        nab = log.count("onCameraAbnormal")
        ok = n > 0 and n110 == 0 and nab == 0
        print(f"   {'[OK] ' if ok else '[X]  '}{tag:24s} "
              f"photos+{n}  -110={n110}  err2={nab} | {log_summary(log)}")
        if ok:
            time.sleep(2)
            return True
        time.sleep(4)
    return False


def shoot_video(tag, secs=6, tries=2):
    for t in range(tries):
        sp = _shutter()
        if not sp:
            print(f"   [X]  {tag:24s} no shutter_button")
            return False
        v0 = count("mp4")
        if v0 is None:
            print(f"   [X]  {tag:24s} cannot count files (command problem)")
            return False
        sh("logcat -b all -c")
        sh(f"input tap {sp[0]} {sp[1]}")          # start recording
        time.sleep(secs)
        sp2 = _shutter()
        sh(f"input tap {sp2[0]} {sp2[1]}" if sp2 else f"input tap {sp[0]} {sp[1]}")
        prev = 0
        log = ""
        for w in (5, 10, 16, 24, 34):
            time.sleep(w - prev)
            prev = w
            log = sh("logcat -d -b all", 60)
            if count("mp4") > v0:
                break
        n = count("mp4") - v0
        n110 = log.count("wait task result failed:-110")
        nab = log.count("onCameraAbnormal")
        ok = n > 0 and n110 == 0 and nab == 0
        print(f"   {'[OK] ' if ok else '[X]  '}{tag:24s} "
              f"videos+{n} -110={n110}  err2={nab}")
        if ok:
            time.sleep(3)
            return True
        time.sleep(4)
    return False


# ── main ────────────────────────────────────────────────────────────────────
def main():
    argv = [a for a in sys.argv[1:] if not a.startswith("-")]
    only = []
    for a in argv:
        only += [x.strip() for x in a.split(",") if x.strip()]

    def wanted(name):
        if not only:
            return True
        return any(name.lower() == o.lower() or name.lower().startswith(o.lower())
                   for o in only)

    print("=" * 64)
    print(" P1 - camera modes that had never been tested")
    print("=" * 64)
    print(" Do not touch the phone while this runs.")
    print(" If the screen is used by another app, the test aborts automatically.")
    if only:
        print(f" RESUME - modes: {', '.join(only)}\n")
    else:
        print()

    sh("input keyevent 4")
    time.sleep(1)
    sh("su -c 'am force-stop com.android.camera'")
    time.sleep(3)
    sh("am start -n com.android.camera/.Camera")
    time.sleep(3)
    if not gate("startup"):
        return 1
    time.sleep(8)
    print(f"focus : {focus()}")
    print(f"mode  : {mode_label()}\n")

    results = {}

    def run(names, shooter, header, use_row=False):
        todo = [m for m in names if wanted(m)]
        if not todo:
            return
        print(header)
        for m in todo:
            steal_check(f"before {m}")
            fresh_camera(f"before {m}")
            time.sleep(6)
            ok, actual = select_row(m) if use_row else select_more(m)
            if ok and m in NEEDS_DOWNLOAD:
                print(f"  [SKIP] {m}: {NEEDS_DOWNLOAD[m]}")
                results[m] = "skip"
                close_panel()
                continue
            if ok:
                print(f"  [{m}] active={actual!r}")
                pre = PREREQ.get(m)
                if pre:
                    print(f"          prereq: {pre()}")
                results[m] = shooter(m)
            else:
                print(f"  [X] {m}: mode could not be confirmed (label={actual!r})")
                results[m] = False
            close_panel()
            time.sleep(1)

    run(PHOTO_MODES, shoot_photo, "--- PHOTO MODES (More panel) ---")
    run(VIDEO_MODES, shoot_video, "\n--- VIDEO MODES (More panel) ---")
    run(["Video"], lambda m: shoot_video(m, secs=8),
        "\n--- VIDEO (main row) ---", use_row=True)

    print("\n" + "=" * 64)
    print(" SUMMARY")
    print("=" * 64)
    good = [k for k, v in results.items() if v is True]
    bad = [k for k, v in results.items() if v is False]
    skip = [k for k, v in results.items() if v == "skip"]
    for k, v in results.items():
        tag = "[OK]  " if v is True else ("[SKIP]" if v == "skip" else "[X]   ")
        print(f"   {tag} {k}")
    n = len(results)
    print(f"\n   passed : {len(good)}/{n - len(skip)}   "
          f"(excluding {len(skip)} skipped)")
    if skip:
        print(f"   skipped: {', '.join(skip)}")
    if bad:
        print(f"   failed : {', '.join(bad)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())