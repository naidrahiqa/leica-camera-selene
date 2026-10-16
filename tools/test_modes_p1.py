#!/usr/bin/env python3
"""
test_modes_p1.py - uji mode kamera yang belum pernah diuji (P1).

Sudah hijau (tidak diulang): Photo 0.6/1.0/2.0, Night 0.6/1.0/2.0,
Portrait, Pro, Documents.

Sisa 11 mode:
  panel "More" (node `more_mode_edit`, isinya `mode_name`):
    50MP, Panorama, VLOG, Short film, Slow motion, Time-lapse,
    Sticker avatars, Movie effects, Long exposure, Clone, Director mode
  row utama: Video

Verdict:
  [OK]    file baru muncul, -110 = 0, onCameraAbnormal = 0
  [X]     file tidak muncul, atau ada error
"""
import re
import subprocess
import sys
import time

S = "65cb03c00702"

# Mode foto -> diuji dengan menghitung file .jpg
PHOTO_MODES = ["50MP", "Panorama", "Sticker avatars",
               "Movie effects", "Long exposure", "Clone"]
# Mode video -> diuji dengan menghitung file .mp4
#
# CATATAN: "Director mode" sempat diletakkan di PHOTO_MODES dan selalu gagal
# (foto+0). Ternyata itu mode VIDEO: shutter-nya merekam mp4. Salah klasifikasi,
# bukan mode rusak. Cine UI-nya juga lebih tinggi, jadi bounds shutter-nya
# [412,1924][667,2179], bukan [412,1864][667,2119] seperti mode biasa —
# karena itu _shutter() SELALU membaca bounds dari UI, tidak pernah hardcode.
VIDEO_MODES = ["Director mode", "VLOG", "Short film",
               "Slow motion", "Time-lapse"]

# Mode yang TIDAK bisa diuji otomatis: shutter-nya mati sampai template diunduh
# dari internet (ikon unduh di tiap kartu template). Bukan cacat kamera.
NEEDS_DOWNLOAD = {
    "VLOG": "setiap template harus diunduh dulu sebelum bisa merekam",
    "Short film": "setiap template harus diunduh dulu sebelum bisa merekam",
}

# Prasyarat per mode: dipanggil setelah mode terkonfirmasi aktif, sebelum jepret.
PREREQ = {}


# ── dasar ───────────────────────────────────────────────────────────────────
def sh(c, t=90):
    try:
        r = subprocess.run(["adb", "-s", S, "shell", c], capture_output=True, timeout=t)
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
    byid, flat = {}, []
    for n in re.finditer(r"<node[^>]*>", x):
        t = n.group(0)

        def g(a):
            r = re.search(a + r'="([^"]*)"', t)
            return r.group(1) if r else ""
        d = {"text": g("text"), "desc": g("content-desc"),
             "bounds": g("bounds"), "click": g("clickable")}
        byid.setdefault(g("resource-id").split("/")[-1], []).append(d)
        flat.append(d)
    return byid, flat


def center(b):
    v = [int(x) for x in re.findall(r"-?\d+", b)]
    return (v[0] + v[2]) // 2, (v[1] + v[3]) // 2


def count(ext="jpg"):
    """Hitung file <ext> di DCIM/Camera.

    PENTING: jangan pakai `ls .../*.{ext} | wc -l`. Kalau glob tidak expand
    (mis. momentarily tidak ada file, atau quoting shell berubah), hasilnya 0
    dan delta jadi angka negatif palsu seperti "foto+-632" - itu bohongan,
    bukan data. Pakai `ls -1 <dir>` lalu filter, dan kalau hasilnya 0 padahal
    sebelumnya tidak 0, baca ulang sekali sebelum diteruskan.
    """
    d = "/data/media/0/DCIM/Camera"
    cmd = "su -c \"ls -1 %s 2>/dev/null | grep -c '\\.%s$' || true\"" % (d, ext)

    def read():
        m = re.search(r"(\d+)", sh(cmd))
        return int(m.group(1)) if m else -1

    n = read()
    if n < 0:          # perintah gagal / output tidak bisa dibaca
        return None
    if n == 0:         # mungkin sesaat tidak terbaca - coba sekali lagi
        time.sleep(1.5)
        n2 = read()
        if n2 >= 0:
            n = n2
    return n


def gate(where="", tries=10):
    """Pastikan kamera fokus + UI ter-render. Gagal keras kalau tidak.

    Penting: `am start` bisa sukses sementara layar sedang dipakai app lain
    (mis. device dipakai manusia di tengah test). Karena itu syaratnya lebih
    ketat daripada sekadar "fokus tidak null".
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
    print(f"\n   [!!] GATE GAGAL{(' di ' + where) if where else ''}: "
          f"fokus={focus()} mode_label={mode_label()!r}")
    return False


# ── navigasi mode ───────────────────────────────────────────────────────────
def panel_open():
    byid, _ = parse()
    return bool(byid.get("more_mode_edit"))


def panel_modes():
    """[(nama, bounds_tap)] dari panel More. Pakai bounds `mode_item` (grid 3 kolom),
    bukan `mode_name` — `mode_name` cuma label teks dan targetnya lebih kecil.
    Susun according indeks: mode_name[i] sejajar dengan mode_item[i]."""
    byid, _ = parse()
    names = byid.get("mode_name", [])
    items = byid.get("mode_item", [])
    out = []
    for i, n in enumerate(names):
        nm = (n["text"] or "").strip()
        if not nm:
            continue
        b = items[i]["bounds"] if i < len(items) else n["bounds"]
        out.append((nm, b))
    return out


def open_more():
    """Idempoten: kalau panel sudah terbuka, jangan tap lagi (nanti ketutup)."""
    if panel_open():
        return True
    byid, _ = parse()
    more = [i for i in byid.get("mode_select_item", []) if i["text"] == "More"]
    if not more:
        for _ in range(4):
            sh("input swipe 250 1758 950 1758 350")
            time.sleep(1.5)
            byid, _ = parse()
            more = [i for i in byid.get("mode_select_item", []) if i["text"] == "More"]
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
    """Tutup panel. BACK dipakai, bukan tap ke center more_mode_mask
    (mask menutupi layar penuh, jadi center-nya justru menimpa isi panel)."""
    if not panel_open():
        return
    sh("input keyevent 4")
    time.sleep(3)
    for _ in range(3):
        if not panel_open():
            return
        sh("input keyevent 4")
        time.sleep(2)


def select_more(name, tries=3):
    """Buka panel More, pilih `name`, VERIFIKASI mode benar-benar berganti.

    Kembalikan (ok, label_aktual). ok=False kalau tidak pernah cocok — supaya
    caller tidak shooting mode yang salah lalu menganggapnya lulus.
    """
    last = None
    for t in range(tries):
        if not open_more():
            last = "panel More tidak terbuka"
            close_panel()
            continue
        hit = next((b for nm, b in panel_modes()
                    if nm.lower() == name.lower()), None)
        if hit is None:
            last = f"mode {name!r} tidak ada di panel"
            close_panel()
            continue
        x, y = center(hit)
        sh(f"input tap {x} {y}")
        time.sleep(6)
        close_panel()
        time.sleep(2)
        steal_check(f"setelah pilih {name}")
        if not gate(f"setelah pilih {name}"):
            last = "gate gagal"
            continue
        cur = mode_label()
        last = cur
        if cur and cur.strip().lower() == name.lower():
            return True, cur
        print(f"   [?] {name}: mode_label={cur!r} (percobaan {t+1}/{tries}, ulangi)")
    return False, last


def fresh_camera(where=""):
    """Restart kamera dari nol. Dipakai sebelum tiap mode supaya tidak ada
    state sisa mode sebelumnya (row utama berubah setelah pilih mode More)."""
    sh("su -c 'am force-stop com.android.camera'")
    time.sleep(3)
    sh("am start -n com.android.camera/.Camera")
    time.sleep(3)
    return gate(where or "fresh_camera")


def select_row(name, tries=3):
    """Pilih mode dari row utama, dengan verifikasi sama seperti select_more."""
    for t in range(tries):
        byid, _ = parse()
        d = {i["text"]: i for i in byid.get("mode_select_item", []) if i["text"]}
        if name not in d:
            for _ in range(4):
                sh("input swipe 250 1758 950 1758 350")
                time.sleep(1.5)
                byid, _ = parse()
                d = {i["text"]: i for i in byid.get("mode_select_item", []) if i["text"]}
                if name in d:
                    break
        if name not in d:
            print(f"   [X] {name}: tidak ada di row (percobaan {t+1}/{tries})")
            continue
        x, y = center(d[name]["bounds"])
        sh(f"input tap {x} {y}")
        time.sleep(6)
        steal_check(f"setelah pilih {name}")
        if not gate(f"setelah pilih {name}"):
            continue
        cur = mode_label()
        if cur and cur.strip().lower() == name.lower():
            return True, cur
        print(f"   [?] {name}: mode_label={cur!r} (percobaan {t+1}/{tries}, ulangi)")
    return False, mode_label()


KNOWN_MODES = ["Documents", "Video", "Photo", "Portrait", "Night", "More",
               "Pro", "50MP", "Panorama", "VLOG", "Short film", "Slow motion",
               "Time-lapse", "Sticker avatars", "Movie effects",
               "Long exposure", "Clone", "Director mode"]

# node desc: "<mode>,Double tap to exit"  <- dipakai mode yang dipilih dari panel More
RE_DOUBLE_TAP = re.compile(r"^([A-Za-z0-9][A-Za-z0-9 +\-]{0,24}),\s*Double tap to exit$")


def mode_label():
    """Nama mode aktif.

    Tiga sumber, berurutan dari paling tepercaya:
      1. mode_select_view (content-desc)  -> mode di row utama
      2. node desc "<mode>,Double tap to exit" -> mode dari panel More
      3. node text yang persis salah satu KNOWN_MODES, di area baris mode (y>1600)
    Penting: mode dari panel "More" TIDAK punya mode_select_view sama sekali,
    jadi hanya andalkan (1) akan selalu reporting None.
    """
    byid, flat = parse()

    v = byid.get("mode_select_view")
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

    # beberapa mode (mis. Director mode/Cine) menaruh nama mode di content-desc
    # tanpa sufiks "Double tap to exit" dan tanpa mode_select_view.
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
    """Kamera fokus DAN UI-nya sudah ter-render (mode_select_view ada & terisi)."""
    if not cam_focused():
        return False
    return bool(mode_label())


def cam_focused():
    """True kalau layar ini milik package com.android.camera.

    Penting: Movie effects / VLOG / Short film membuka activity SENDIRI di dalam
    package yang sama, jadi jangan hanyaceb comparação ".Camera" - itu akan
    menganggap activity sah sebagai "app lain merebut layar"."""
    return "com.android.camera" in focus()


def steal_check(where):
    """Batalkan test kalau aplikasi lain merebut layar (mis. lo buka HP saat test)."""
    if cam_focused():
        return
    f = focus()
    print(f"\n   [!!] TEST DIBATALKAN di {where}: layar dikuasai app lain")
    print(f"        fokus = {f}")
    print(f"        tutup app itu / kembali ke kamera, lalu jalankan ulang.")
    raise SystemExit(3)


# ── shooting ────────────────────────────────────────────────────────────────
def logsum(lg):
    mf = re.findall(r"applyMfnrEnable: (\w+)", lg)
    sw = re.findall(r"applySwMfnrEnable: (\w+)", lg)
    return f"Mfnr={mf[0] if mf else '-'} SwMfnr={sw[0] if sw else '-'}"


def _shutter():
    """Koordinat tombol shutter.

    Dua sumber, wajib dua-duanya:
      1. resource-id 'shutter_button'  -> UI utama
      2. content-desc 'Shutter button' -> panel turunan (Movie effects, Clone, ...)
         Node di panel turunan TIDAK punya resource-id, cuma content-desc.
         Kalau cuma andalkan (1), mode-mode iniselalu dilaporkan "tidak ada shutter".
    """
    byid, flat = parse()
    sb = byid.get("shutter_button")
    if sb:
        return center(sb[0]["bounds"])
    for d in flat:
        if (d["desc"] or "").strip() == "Shutter button":
            return center(d["bounds"])
    return None


def shoot_photo(tag, tries=2):
    for t in range(tries):
        sp = _shutter()
        if not sp:
            print(f"   [X]  {tag:24s} tidak ada shutter_button")
            return False
        p0 = count("jpg")
        if p0 is None:
            print(f"   [X]  {tag}: tidak bisa menghitung file (perintah bermasalah)")
            return False
        sh("logcat -b all -c")
        sh(f"input tap {sp[0]} {sp[1]}")
        prev = 0
        lg = ""
        for w in (8, 15, 22, 30, 40, 52, 65, 80):
            time.sleep(w - prev)
            prev = w
            lg = sh("logcat -d -b all", 60)
            if count("jpg") > p0 or "onCameraAbnormal" in lg:
                break
        n = count("jpg") - p0
        n110 = lg.count("wait task result failed:-110")
        nab = lg.count("onCameraAbnormal")
        ok = n > 0 and n110 == 0 and nab == 0
        print(f"   {'[OK] ' if ok else '[X]  '}{tag:24s} foto+{n}  -110={n110}  err2={nab} | {logsum(lg)}")
        if ok:
            time.sleep(2)
            return True
        time.sleep(4)
    return False


def shoot_video(tag, secs=6, tries=2):
    for t in range(tries):
        sp = _shutter()
        if not sp:
            print(f"   [X]  {tag:24s} tidak ada shutter_button")
            return False
        v0 = count("mp4")
        if v0 is None:
            print(f"   [X]  {tag}: tidak bisa menghitung file (perintah bermasalah)")
            return False
        sh("logcat -b all -c")
        sh(f"input tap {sp[0]} {sp[1]}")
        time.sleep(secs)
        sp2 = _shutter()
        sh(f"input tap {sp2[0]} {sp2[1]}" if sp2 else f"input tap {sp[0]} {sp[1]}")
        prev = 0
        lg = ""
        for w in (5, 10, 16, 24, 34):
            time.sleep(w - prev)
            prev = w
            lg = sh("logcat -d -b all", 60)
            if count("mp4") > v0:
                break
        n = count("mp4") - v0
        n110 = lg.count("wait task result failed:-110")
        nab = lg.count("onCameraAbnormal")
        ok = n > 0 and n110 == 0 and nab == 0
        print(f"   {'[OK] ' if ok else '[X]  '}{tag:24s} video+{n} -110={n110}  err2={nab}")
        if ok:
            time.sleep(3)
            return True
        time.sleep(4)
    return False


def clone_prereq():
    """Clone butuh sumber foto dulu; tombolnya panah (next), bukan jepret."""
    byid, _ = parse()
    for rid in ("clone_photo_mode", "clone_photo_item"):
        items = byid.get(rid, [])
        if items:
            x, y = center(items[0]["bounds"])
            sh(f"input tap {x} {y}")
            time.sleep(4)
            return f"tab sumber '{rid}' dipilih di ({x}, {y})"
    return "tidak menemukan clone_photo_mode/item — flow mungkin berubah"


# Prasyarat per mode, dipanggil setelah mode terkonfirmasi aktif.
PREREQ = {"Clone": clone_prereq}


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
    print(" P1 — mode yang belum pernah diuji")
    print("=" * 64)
    print(" JANGAN pegang HP selama test berjalan.")
    print(" Jika layar dipakai app lain, test dibatalkan otomatis.")
    if only:
        print(f" RESUME — hanya mode: {', '.join(only)}\n")
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
    print(f"fokus : {focus()}")
    print(f"mode  : {mode_label()}\n")

    res = {}

    def run(names, shooter, header, use_row=False):
        todo = [m for m in names if wanted(m)]
        if not todo:
            return
        print(header)
        for m in todo:
            steal_check(f"sebelum {m}")
            fresh_camera(f"sebelum {m}")
            time.sleep(6)
            ok, actual = select_row(m) if use_row else select_more(m)
            if ok and m in NEEDS_DOWNLOAD:
                print(f"  [SKIP] {m}: {NEEDS_DOWNLOAD[m]}")
                res[m] = "skip"
                close_panel()
                continue
            if ok:
                print(f"  [{m}] aktif={actual!r}")
                pre = PREREQ.get(m)
                if pre:
                    print(f"          prereq: {pre()}")
                res[m] = shooter(m)
            else:
                print(f"  [X] {m}: mode tidak dikonfirmasi (label={actual!r})")
                res[m] = False
            close_panel()
            time.sleep(1)

    run(PHOTO_MODES, shoot_photo, "--- MODE FOTO (panel More) ---")
    run(VIDEO_MODES, shoot_video, "\n--- MODE VIDEO (panel More) ---")
    run(["Video"], lambda m: shoot_video(m, secs=8),
        "\n--- VIDEO (row utama) ---", use_row=True)

    print("\n" + "=" * 64)
    print(" RINGKASAN")
    print("=" * 64)
    good = [k for k, v in res.items() if v is True]
    bad = [k for k, v in res.items() if v is False]
    skip = [k for k, v in res.items() if v == "skip"]
    for k, v in res.items():
        tag = "[OK]  " if v is True else ("[SKIP]" if v == "skip" else "[X]   ")
        print(f"   {tag} {k}")
    n = len(res)
    print(f"\n   lulus : {len(good)}/{n - len(skip)}   (di luar {len(skip)} mode skip)")
    if skip:
        print(f"   skip  : {', '.join(skip)}")
    if bad:
        print(f"   gagal : {', '.join(bad)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())