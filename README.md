# Leica Camera 5.0 untuk Redmi Note 10 (selene / MT6768)

Patch Leica Camera 5.0 (port MIUI) supaya **benar-benar bisa dipakai** di
Redmi Note 10 — termasuk **Night mode** yang biasanya menggantung.

Repo ini berisi skrip untuk membuat ulang patch tersebut, plus-file integrasi
untuk membakar kamera langsung ke dalam custom ROM.

```
Foto   0.6X  1.0X  2.0X     ✅
Night  0.6X  1.0X  2.0X     ✅   ← sebelum patch: tidak pernah menghasilkan file
Portrait · Pro · Documents   ✅
50MP · Panorama · Long exposure · Sticker avatars   ✅
Video · Slow motion · Time-lapse · Director mode   ✅
─────────────────────────────────────────────
17 mode terverifikasi,  -110 = 0  dan  onCameraAbnormal = 0  di SEMUA mode
```

---

## Masalahnya apa

Redmi Note 10 (`selene`, SoC **MT6769H**) **tidak punya blok MFB sama sekali**:

```
port MFB M4U           : 0
                         (mt6779 = 5, mt6873/6853/6781/6833/6885 = 16)
event MFB di IRQ       : 0
driver / clock / node MFB : tidak ada
```

Aplikasi Leica tetap mengirim tag MFNR hardware saat Night mode dan saat zoom 1.0X.
HAL lalu menunggu MFB yang tidak pernah selesai:

```
wait task result failed:-110        ← ETIMEDOUT
onCameraAbnormal: 2
(tidak ada file di DCIM)
```

Zoom 2.0X kebetulan aman karena di titik itu aplikasi tidak meminta MFNR sama sekali.

Ini **bukan** bug kernel, bug modul, atau bug ROM — blok MFB memang tidak ada di
silikon. Yang bisa kita ubah hanya permintaannya.

---

## Solusinya

Paksa di **titik penulisan tag** — `com/android/camera2/compat/MiCameraCompatBaseImpl` —
dengan satu baris per method:

| Method | Dipaksa | Arti |
|---|---|---|
| `applyMfnr` | `const/4 p2, 0x0` | hardware MFNR (MFB) **mati** |
| `applySwMfnr` | `const/4 p2, 0x1` | software MFNR **nyala** |
| `applySuperNightMfnr` | `const/4 p2, 0x0` | super-night MFB **mati** |

Night mode lalu memakai pipeline software-MFNR yang sama dengan mode foto —
persis jalur yang sudah terbukti jalan.

### Kenapa di situ, bukan di call site

Versi pertama tried di `d/c/b/a5.smali` (call site hasil decompile).
**Tidak berefek sama sekali** — apk-nya ke-sign, ke-install, kelihatan beres,
tapi log tetap `applyMfnrEnable: true`. Jalur runtime-nya lewat
`d/c/b/k4.smali` (`CAM_CaptureRequestBuilder`).

Mengganti 30+ call site satu per satu juga rapuh. Satu titik penulisan tag
dipakai semua mode, jadi 3 baris ini menutup semuanya sekaligus.

---

## Pemakaian

### 1. Ambil APK dasar

Modul aslinya (KernelSU/Magisk) berisi `MiuiCamera.apk` **belum dipatch** di
`system/priv-app/MiuiCamera/`. Ambil dari sana, atau dari ROM donor.

### 2. Ambil tooling

```bash
./tools/fetch-tools.sh
```

Mengunduh `apktool.jar` (24 MB) dan `uber-apk-signer.jar` (3 MB). Keduanya
sengaja tidak disimpan di repo.

### 3. Patch

```bash
./tools/patch-night.sh <MiuiCamera.apk> -o MiuiCamera-patched.apk
```

Sekitar 2 menit: decode → patch → build → zipalign → sign → verifikasi.

### 4. Pasang

**Sebagai modul (KernelSU / Magisk):**

```
adb push MiuiCamera-patched.apk /data/local/tmp/
adb shell su -c 'cp /data/local/tmp/MiuiCamera-patched.apk \
  /data/adb/modules/xiaomicamera/system/priv-app/MiuiCamera/MiuiCamera.apk'
adb shell su -c reboot
```

**Sebagai bagian ROM:** lihat [`rom/`](rom/).

---

## Dua mode yang tidak bisa diuji otomatis

Bukan mode rusak — memang butuh langkah atau konten tambahan:

| Mode | Alasan |
|---|---|
| **Clone** | Aplikasi menampilkan *"Cloning only works in landscape mode"*; kamera mengunci orientasi portrait, jadi tidak bisa dipicu lewat adb |
| **Movie effects** | Wizard cinemagraph multi-langkah (*"Place your subject into the frame"*) |
| **VLOG · Short film** | Setiap template harus diunduh lebih dulu sebelum shutter aktif |

Ketiganya tetap jalan normal di aplikasi.

---

## Kalau dipakai untuk chipset lain

**Baca dulu. Ini penting.**

Patch ini **mematikan hardware MFNR**. Itu benar untuk MT6768/MT6769, tapi
**merusak** untuk chipset yang punya MFB:

| Chipset | Port M4U | Efek patch |
|---|---|---|
| MT6768 / MT6769 (selene) | **0** | ✅ tepat sasaran |
| MT6779 | 5 | ❌ kualitas turun |
| MT6873 / MT6853 / MT6781 / MT6833 / MT6885 | 16 | ❌ kualitas turun |

Cek dulu sebelum menjalankan:

```bash
su -c 'cat /proc/mfb/port 2>/dev/null || echo TIDAK ADA BLOK MFB'
```

Kalau keluar `TIDAK ADA BLOK MFB`, patch ini yang benar.
Kalau keluar daftar port, **jangan** jalankan — pakai kamera bawaan ROM.

---

## Isi repo

```
tools/
  fetch-tools.sh        unduh apktool + uber-apk-signer
  patch-night.sh        decode -> patch -> build -> sign -> verifikasi
  patch_night.py        patch smali + verifier (--check tidak menulis apa pun)
  test_modes_p1.py      harness uji mode kamera (support resume per mode)
rom/
  prebuilt/leica-camera/  Android.bp, camera.mk, sepolicy, permission XML
  README.md               cara integrate ke device tree
docs/
  ISSUE-mfb-timeout.md    catatan investigasi lengkap
  VERSIONING.md           skema versi modul
```

Tidak ada binary di repo ini: APK Leica punya lisensi pihak ketiga dan ukurannya
169 MB. Repo ini menyediakan **cara membuat ulang** patch-nya.

---

## Keandalan skrip

`patch-night.sh` sengaja gagal keras daripada diam-diam salah. Ini penting:
patch versi pertama keluar `exit 0`, APK-nya valid, tapi tidak bekerja — kalau
tidak diverifikasi, itu terbuang berjam-jam.

| Uji | Hasil |
|---|---|
| Patch dari nol → bandingkan `classes*.dex`, `resources.arsc`, `AndroidManifest.xml` dengan APK yang sudah dipakai | **byte-identik** |
| Patch 3× di tree yang sama | idempoten, tidak menumpuk |
| `--check` pada APK yang belum dipatch | keluar 1, menyebut instruksi pertama yang sebenarnya |
| Tree tanpa `MiCameraCompatBaseImpl.smali` | keluar 1, file tidak ditulis |
| Method berubah nama (APK versi lain) | keluar 1, file tidak ditulis |

`patch_night.py --check` **tidak menulis file apa pun**. Verifier yang bisa
"memperbaiki" targetnya tidak berguna sebagai verifikasi.

### Jebakan yang sudah ditangani

1. Isi blok `.annotation` (`ignore = false`) bukan instruksi. Salah mendeteksi →
   `const/4` mendarat di dalam annotation → `missing END_ANNOTATION_DIRECTIVE`.
2. Idempotensi harus dicek ke **instruksi pertama**, bukan baris sebelumnya
   (baris sebelumnya baris kosong). Kalau salah, patch kedua menumpuk.
3. `ls dir/*.jpg | wc -l` menghasilkan 0 saat glob tidak expand, sehingga delta
   hitung 파일 jadi angka negatif palsu (`foto+-632`).
4. Tombol shutter di panel turunan **tidak punya `resource-id`**, hanya
   `content-desc='Shutter button'`.

---

## Versi

```
version     = 1.4.0        <- dilihat manusia
versionCode = 10400        <- dilihat mesin
formula: MAJOR*10000 + MINOR*100 + PATCH
```

`versionCode` sengaja memakai integer, bukan `1.4.0`. String memang bisa
ke-parse di KernelSU Manager, tapi logika deteksi-update membandingkan
angka, jadi string bisa gagal diam-diam saat modul diperbarui.

Riwayat versi dan aturan naiknya: [`docs/VERSIONING.md`](docs/VERSIONING.md).

---

## Credit

Modul Leica Camera 5.0 Universal oleh
**HolyBear0610, Sevtinge, Sipollo, lostark13, itzdfplayer, Troj80**.

Lisensi: Apache-2.0 (lihat `LICENSE`). Script di repo ini milik
`selene-aosp` / contributor. Leica Camera sendiri adalah karya pihak ketiga
dan tunduk pada lisensinya masing-masing.