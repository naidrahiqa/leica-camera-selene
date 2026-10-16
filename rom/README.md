# Integrasi ke Custom ROM

Membakar Leica Camera langsung ke dalam image ROM, tanpa modul Magix/KernelSU.

Target yang sudah dipakai saat pembuatan:
[`selene-aosp/android_device_xiaomi_selene`](https://github.com/selene-aosp/android_device_xiaomi_selene)
branch `lineage-23.2` (= Android 16).

---

## Yang perlu disalin

Folder `prebuilt/leica-camera/` di repo ini **harus** diperbesar dengan file
binary dari modul Leica:

```
MiuiCamera.apk            ← dari modul, SUDAH dipatch (hasil patch-night.sh)
MiuiExtraPhoto.apk        ← dari modul
MiuiScanner.apk           ← dari modul, opsional
lib-MiuiCamera/*.so       ← 8 file dari modul
lib-MiuiExtraPhoto/*.so   ← 39 file dari modul
sceneDetection.xml        ← dari modul (vendor/etc/camera/)
```

Repo ini sengaja tidak memuat file-file itu (169 MB + lisensi pihak ketiga).
`.gitignore` juga menahan=kSQLUP file binary.

Filenya bisa diambil dari modul KernelSU:

```bash
unzip -p Leica-5.0-Beta-8.3-Port-Selene.zip \
     system/priv-app/MiuiCamera/MiuiCamera.apk > MiuiCamera.apk
```

---

## Yang perlu diedit di device tree

### 1. `device.mk`

```make
# Leica Camera 5.0 (patched untuk selene/MT6768 - software MFNR, tanpa MFB)
$(call inherit-product, prebuilt/leica-camera/camera.mk)
```

Letakkan sebelum baris vendor blobs (`selene-vendor.mk`).

### 2. Tidak perlu sentuh `BoardConfig.mk`

`camera.mk` sudah menambahkan sendiri:

```make
BOARD_VENDOR_SEPOLICY_DIRS += \
    prebuilt/leica-camera/sepolicy \
    $(DEVICE_PATH)/sepolicy
```

`prebuilt/leica-camera/Android.bp` berada di dalam `$DEVICE_PATH`, yang sudah
terdaftar di `PRODUCT_SOONG_NAMESPACES`.

---

## Signing

Default `Android.bp` memakai `certificate: "platform"`.

Kamera meminta 9 privileged permission (`SYSTEM_CAMERA`, `WRITE_SECURE_SETTINGS`,
`WRITE_MEDIA_STORAGE`, …). Kalau signed dengan platform key, Android otomatis
memberi hak priv-app tanpa perlu allowlist.

Kalau kamera MIUI menolak signature (crash saat dibuka, atau sebagian fitur mati),
komentari baris `certificate:` di ketiga modul supaya signature asli dipertahankan.
Jalur "signature asli + allowlist" sudah terbukti bekerja — itulah yang dipakai
modul KernelSU dengan signature debug.

---

## SELinux

`sepolicy/leica-camera.te` **belum pernah diuji di device** dan sengaja dibuat
minimal.

Kalau build gagal dengan `neverallow` atau `duplicate declaration`, hapus dulu
file itu — vendor policy MTK kemungkinan besar sudah cukup untuk kamera.

Kalau boot berhasil tapi kamera tidak bisa mengakses vendor blob, cari rule yang
benar-benar dipakai:

```bash
adb logcat -b all | grep -i avc
```

Rule asli dari modul (format KernelSU) ada di
[`sepolicy.rule`](sepolicy/leica.rule.orig) untuk dibandingkan.

---

## Yang sengaja tidak ikut

| Dari modul | Alasan |
|---|---|
| `ro.control_privapp_permissions=log` | Pancingan anti-bootloop untuk modul yang mount bisa gagal. ROM harus tetap `enforce` |
| `service.sh` | Sudah terbukti tidak dibutuhkan begitu patch aktif |
| `selene.json` | Sama — diverifikasi: `service.sh` dimatikan, folder config dihapus, reboot, semua mode tetap jalan |

---

## Ukuran

Sekitar **326 MB** di dalam image:

| Komponen | Ukuran |
|---|---|
| `MiuiCamera.apk` | 169 MB |
| `MiuiScanner.apk` | 20 MB (boleh dihapus) |
| `MiuiExtraPhoto.apk` | 13 MB |
| 47 `.so` | ~124 MB |

`MiuiScanner` bisa dihapus kalau hemat ruang lebih penting — tidak ada mode
kamera yang bergantung padanya. Tapi `MiuiExtraPhoto` jangan dihapus: mode
Documents membutuhkannya.