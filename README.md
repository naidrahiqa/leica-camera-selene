# Leica Camera 5.0 for Redmi Note 10 (selene / MT6768)

Leica Camera 5.0 (MIUI Leica port), patched so it actually works on the Redmi
Note 10 — including **Night mode**, which previously hung forever.

Drop-in vendor blob repo for custom ROMs, in the standard LineageOS layout.

```
Photo  0.6X  1.0X  2.0X     OK
Night  0.6X  1.0X  2.0X     OK   <- previously produced no file at all
Portrait · Pro · Documents   OK
50MP · Panorama · Long exposure · Sticker avatars   OK
Video · Slow motion · Time-lapse · Director mode   OK
─────────────────────────────────────────────────────────
17 modes verified.  -110 = 0  and  onCameraAbnormal = 0  in every one.
```

---

## The problem

The Redmi Note 10 (`selene`, SoC **MT6769H**) has **no MFB block at all**:

```
MFB M4U ports          : 0
                         (mt6779 = 5, mt6873/6853/6781/6833/6885 = 16)
MFB events in IRQ      : 0
MFB driver / clock / node : absent
```

The camera app still asks for hardware MFNR in Night mode and at 1.0X zoom.
The HAL then waits for an MFB that will never finish:

```
wait task result failed:-110        <- ETIMEDOUT
onCameraAbnormal: 2
(no file in DCIM)
```

2.0X happened to work only because the app does not request MFNR at that zoom.

This is **not** a kernel bug, a module bug, or a ROM bug. The block genuinely
does not exist in the silicon. The only thing that can be changed is whether
the request is made.

---

## The fix

Force it at the **tag-writing layer** —
`com/android/camera2/compat/MiCameraCompatBaseImpl` — one line per method:

| Method | Forced | Meaning |
|---|---|---|
| `applyMfnr` | `const/4 p2, 0x0` | hardware MFNR (MFB) **off** |
| `applySwMfnr` | `const/4 p2, 0x1` | software MFNR **on** |
| `applySuperNightMfnr` | `const/4 p2, 0x0` | super-night MFB **off** |

Night mode then uses the software-MFNR pipeline — the exact path that already
worked for regular photos.

### Why that location

The first attempt patched `d/c/b/a5.smali` (a call site found by decompiling).
It **did nothing**: the APK signed, installed, and looked fine, but the log kept
reporting `applyMfnrEnable: true`, because the runtime path goes through
`d/c/b/k4.smali` (`CAM_CaptureRequestBuilder`) instead.

Fixing 30+ call sites one by one is also brittle. A single tag-writing point is
shared by every mode, so these three lines cover all of them at once.

---

## Using it in a ROM

### 1. Add the repo

```json
{
  "name": "Leica Camera for selene",
  "url": "https://github.com/naidrahiqa/leica-camera-selene",
  "branch": "main"
}
```

### 2. Inherit from `device.mk`

```make
$(call inherit-product, vendor/xiaomi/leica_camera/config.mk)
```

### 3. SELinux

`sepolicy/leica-camera.te` has to be picked up from `BoardConfig.mk`:

```make
BOARD_VENDOR_SEPOLICY_DIRS += \
    vendor/xiaomi/leica_camera/sepolicy
```

That file is **not verified on device** and is deliberately minimal. If the
build fails with `neverallow` or duplicate-declaration errors, delete it first —
the MediaTek vendor policy is very likely already sufficient. See
`sepolicy/leica-camera.te` for the full caveats.

### That's it

`config.mk` handles the packages, the native libraries, the priv-app allowlist,
the hidden-API whitelist and the camera properties.

Verified against
[`selene-aosp/android_device_xiaomi_selene`](https://github.com/selene-aosp/android_device_xiaomi_selene),
branch `lineage-23.2` (Android 16).

---

## Using it as a Magix/KernelSU module

The patched APK can also replace the one in the Leica module:

```bash
tools/fetch-tools.sh
tools/patch-night.sh <unpatched-MiuiCamera.apk>
```

```
adb push MiuiCamera-patched.apk /data/local/tmp/
adb shell su -c 'cp /data/local/tmp/MiuiCamera-patched.apk \
  /data/adb/modules/xiaomicamera/system/priv-app/MiuiCamera/MiuiCamera.apk'
adb shell su -c reboot
```

A signature change on a system package is accepted by PackageManager — no
uninstall needed.

### Versioning

```
version     = 1.4.0        <- human readable
versionCode = 10400        <- machine read
formula: MAJOR*10000 + MINOR*100 + PATCH
```

Details and the version history: [`docs/VERSIONING.md`](docs/VERSIONING.md).

`versionCode` is an integer rather than the string `1.4.0` on purpose. The
string does parse in KernelSU Manager, but update detection compares numbers, so
a string can fail silently when the module is updated later.

---

## Modes that cannot be tested automatically

Not broken — they just need extra steps or content:

| Mode | Why |
|---|---|
| **Clone** | The app shows *"Cloning only works in landscape mode"*; the camera locks orientation to portrait, so it cannot be triggered over adb |
| **Movie effects** | Multi-step cinemagraph wizard (*"Place your subject into the frame"*) |
| **VLOG · Short film** | Every template must be downloaded before the shutter becomes active |

All three work normally in the app.

---

## ⚠️ Before using this on a different chipset

**Read this. It matters.**

The patch **disables hardware MFNR**. That is correct for MT6768/MT6769, but it
**degrades quality** on chipsets that do have MFB hardware:

| Chipset | M4U ports | Effect of the patch |
|---|---|---|
| MT6768 / MT6769 (selene) | **0** | correct target |
| MT6779 | 5 | quality loss |
| MT6873 / MT6853 / MT6781 / MT6833 / MT6885 | 16 | quality loss |

Check first:

```bash
su -c 'cat /proc/mfb/port 2>/dev/null || echo NO_MFB_BLOCK'
```

`NO_MFB_BLOCK` -> this patch is right. A list of ports -> do not use it, keep
the ROM's stock camera.

---

## Layout

```
Android.bp                      android_app_import definitions
Android.mk
config.mk                       PRODUCT_PACKAGES / COPY_FILES / properties
.gitattributes                  Git LFS tracking

proprietary/system/
  priv-app/MiuiCameraLeica/     patched APK + lib/arm64 (8 .so)
  priv-app/MiuiExtraPhoto/      APK + lib/arm64 (39 .so)
  priv-app/MiuiScanner/         APK (optional, ~20 MB)
  etc/permissions/              priv-app allowlist
  etc/sysconfig/                hidden API whitelist
  sceneDetection.xml            (repo root: proprietary/sceneDetection.xml)

sepolicy/
  leica-camera.te               minimal, NOT verified on device
  leica-camera.rule.orig        original KernelSU-format rules

tools/
  fetch-tools.sh                download apktool + uber-apk-signer
  patch-night.sh                decode -> patch -> build -> sign -> verify
  patch_night.py                smali patcher + verifier (--check is read-only)
  test_modes_p1.py              camera mode test harness, supports resume

docs/
  VERSIONING.md                 module version scheme
  module.prop.example           module.prop template
```

Total about **326 MB**, of which the camera APK is 169 MB.

---

## Reproducibility

`patch-night.sh` fails loudly rather than silently producing a broken APK. That
matters, because the first patch attempt exited `0`, produced a perfectly valid
APK, and did not work at all — without a verification step that would have been
hours lost.

| Test | Result |
|---|---|
| Patch from scratch, compared against the APK in use | `classes*.dex`, `resources.arsc`, `AndroidManifest.xml` **byte-identical** |
| Patch 3× on the same tree | idempotent, no duplicated instructions |
| `--check` on an unpatched APK | exits 1, names the actual first instruction |
| Tree without `MiCameraCompatBaseImpl.smali` | exits 1, nothing written |
| Method renamed (different APK version) | exits 1, nothing written |

`patch_night.py --check` **writes nothing at all**. A verifier that can repair
its own target is not a verification.

### Pitfalls already handled

1. Contents of a `.annotation` block (`ignore = false`) are not instructions.
   Mis-detecting them drops the `const/4` inside the annotation and smali fails
   with `missing END_ANNOTATION_DIRECTIVE`.
2. Idempotency must be checked against the **first instruction**, not the line
   before it (which is blank). Getting this wrong makes the second patch stack
   duplicates.
3. `ls dir/*.jpg | wc -l` returns 0 when the glob does not expand, which turns a
   file-count delta into a fake negative number (`photos+-632`).
4. The shutter button in sub-panels has **no `resource-id`**, only
   `content-desc='Shutter button'`.

---

## Credits

Leica Camera 5.0 Universal module by
**HolyBear0610, Sevtinge, Sipollo, lostark13, itzdfplayer, Troj80**.

Licensed under Apache-2.0 (see `LICENSE`). The scripts in this repository are
the work of the contributors. Leica Camera itself is third-party work and
remains under its own licence.