# Leica Camera 5.0 for Redmi 10 / Redmi 10 2022 (selene / MT6768)

> **Status: 5.0 is the supported release.** The 6.4 experiment was withdrawn
> and its release/tag removed. Use v1.4.0; do not install 6.x.

Leica Camera 5.0 (MIUI Leica port), patched so it actually works on the Redmi
10 / Redmi 10 2022 — including **Night mode**, which previously hung forever.

Drop-in vendor blob repo for custom ROMs, in the standard LineageOS layout.

```
Photo  1.0X  2.0X           OK
Night  1.0X  2.0X           OK   <- previously produced no file at all
Portrait · Pro · Documents  OK
50MP · Panorama · Long exposure · Sticker avatars   OK
Video · Slow motion · Time-lapse · Director mode   OK
Movie effects (Magic zoom)  OK   (manual save step)
─────────────────────────────────────────────────────────
Photo/Night 0.6X            OK with a fixed kernel - see 0.6X below
```

### 0.6X ultra-wide

Earlier releases shipped with the label "0.6X hangs the camera" and the
assumption that the Redmi 10 has no ultra-wide sensor. That assumption was
**wrong**: the device has an **IMX355 ultra-wide** (Sunny variant,
`persist.vendor.camera.ultra=sunny_imx355_ultra_i`). The preview freeze
happened because the kernel side was missing, not the phone:

- the EsTehAnget 4.19 kernel trees carried no IMX355 imgsensor drivers
  (`camera_project/selene/imx355_{sunny,aac}_ultra_mipi_raw` absent), and
- `selene_defconfig` did not list the sensor names,

so the HAL only ever registered 5 cameras and the app's 0.6X button
selected a nonexistent camera path.

On a kernel built from the fixed tree, the driver probes
(`IMX355_SUNNY ... vendor_id=104`, sensor id `0x356`) and the HAL reports
**6 cameras** with camera 2 as ultra-wide (role 21). Kernel-level fix is
verified on hardware (2026-10-24); an in-app capture re-test on 0.6X is
the remaining step before v1.4.1 is tagged.

On kernels **without** the IMX355 fix, 0.6X still freezes: use **1.0X or
2.0X**, force-stop the camera to recover. Every other core mode was
re-tested on 2026-10-23 with `-110 = 0` and `onCameraAbnormal = 0`.

### Documents mode and MiuiExtraPhoto

Documents is a capture + handoff pipeline, not a standalone editor. The camera
saves `DOCUMENT_PICTURE_*` and sends it to `com.miui.extraphoto` for auto-crop
and perspective correction. That is why this module bundles **MiuiExtraPhoto**
and its 39 arm64 libraries. Removing them still lets Documents take the photo,
but the correction step will not open.

### Video frame rate

The selene camera HAL exposes `aeAvailableTargetFpsRanges` only up to **30fps**
(10/15/20/30). There is no 1080p60 or 720p60 stream to select. The 60fps strings
inside the APK are generic Xiaomi camera code for other devices; they do not
make the sensor/HAL support it. Forcing MediaTek `smvrMode` is not a real 60fps
fix and can break audio or stability.

---

## The problem

The Redmi 10 2022 (`selene`, SoC **MT6768 / MT6769H**) has **no MFB block at all**:

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
  "url": "https://github.com/naidrahiqa/leica_cam_selene",
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

## Using it as a Magisk/KernelSU module

### Install the flashable module

Download the release ZIP and install it from KernelSU Manager / Magisk, or from
a root shell:

```bash
adb push Leica-5.0-Beta-8.3-Port-Selene-v1.4.0.zip /data/local/tmp/
adb shell su -c 'ksud module install /data/local/tmp/Leica-5.0-Beta-8.3-Port-Selene-v1.4.0.zip'
adb reboot
```

Do **not** use `adb install`: `com.android.camera` is a privileged system app,
so the APK has to be mounted as a module. Replacing it directly with
`adb install` will fail with a signature/permission error.

### Rebuild the APK from source

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

## Modes that need manual steps

These are not part of the automated pass/fail set:

| Mode | Status |
|---|---|
| **Clone** | Requires landscape orientation. The camera locks portrait, so adb cannot trigger the capture; not verified. |
| **Movie effects** | Multi-step cinemagraph wizard. Magic zoom was captured and saved manually (`VID_*.mp4`). |
| **VLOG** | Requires landscape orientation; template must be selected before recording. Not verified over adb. |
| **Short film** | Records template segments and saves a **draft** (`VPWorkspaceActivity`); it is not a gallery mp4 until exported. |
| **Panorama** | Needs the 17.25 MB plugin on first use. After download, a `PANO_*.jpg` was captured and saved. |

These are workflow limitations, not proof that the camera pipeline is broken.
Test them manually if you need those exact modes.

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