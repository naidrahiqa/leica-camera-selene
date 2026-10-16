# Versioning

## Yang dipakai

```
version     = 1.4.0
versionCode = 10400
```

`version` yang dilihat manusia. `versionCode` yang dilihat mesin.

## Rumus `versionCode`

```
versionCode = MAJOR * 10000 + MINOR * 100 + PATCH
```

| Versi | versionCode |
|---|---|
| 1.0.0 | 10000 |
| 1.3.0 | 10300 |
| 1.3.9 | 10309 |
| 1.4.0 | **10400** |
| 1.4.1 | 10401 |
| 2.0.0 | 20000 |

Skema ini memberi ruang 99 untuk MINOR dan 99 untuk PATCH sebelum keduanya
menggigitMajor berikutnya — cukup untuk seumur hidup proyek ini.

## Kenapa `versionCode` bukan `1.4.0`

Magisk `versionCode` **wajib integer**. Mengisi `1.4.0` memang berhasil ke-parse
dan tampil normal di KernelSU Manager, tapi logika deteksi-update_internal
membandingkan angka, jadi perbandingan bisa gagal diam-diam di kemudian hari
saat modul diperbarui.

Jadi: **semver penuh ada di `version`, dan integer-nya sebagai encode-nya.**

## Arti tiap angka

```
MAJOR  naik kalau ada perubahan besar, atau target chipset berubah
MINOR  naik setiap ada revisi patch yang berhasil diverifikasi
PATCH  naik untuk perbaikan kecil
```

Riwayat:

| Versi | Apa yang berubah | Status |
|---|---|---|
| 1.0.0 | Baseline: modul Leica 5.0 Beta 8.3 + `selene.json` (`isLegacyMfnrDevice` + `supportSwMfnr`) | Foto 0.6X/1.0X jalan, **Night masih mati** |
| 1.1.0 | Patch v1 — di `d/c/b/a5.smali` (call site hasil decompile) | **GAGAL**: log tetap `applyMfnrEnable: true` |
| 1.2.0 | Susun ulang `sepolicy.rule` + `service.sh` yang diperbaiki | Infra saja |
| 1.3.0 | Patch v2 — di `MiCameraCompatBaseImpl` (titik penulisan tag) | **BERHASIL** |
| 1.4.0 | Validasi menyeluruh + `patch-night.sh` reproducible | 17 mode hijau, `-110=0` di semua |

## Sebelumnya: `830004`

Semula dipakai pola `UUU RRR`: `830` = upstream Beta 8.3, `004` = revisi selene.
Pola ini **dibatalkan** — ambigu (620.004 vs 83.0004?) dan tidak memberi
informasi versi semver.

Nomor lama tidak dipetakan ke yang baru. Kalau installing modul ini di atas
versi lama, KernelSU akan memperlakukannya sebagai versi lebih rendah.
 Itu bukan masalah — instalasi tetap jalan, hanya nomornya turun.

## Kalau naik versi

1. Edit `version` + `versionCode` di `module.prop`
2. Hitung ulang `versionCode` dari rumus di atas
3. **Uji dulu** di `ksud module list` — kalau `versionCode` tidak muncul
   sebagai angka, berarti ada yang salah
4. Repack zip, push ke hp, tes 1-2 mode
5. Commit + tag: `git tag -a v1.4.0 -m "..."`

## Kalau naik versi lagi

| Jenis | Nomor berikutnya |
|---|---|
| Perbaikan kecil | `1.4.1` → 10401 |
| Revisi patch berhasil | `1.5.0` → 10500 |
| Ganti versi Leica upstream | `2.0.0` → 20000 |

Naikkan **MAJOR** kalau upstream-nya Leica yang berubah, supaya jelas
ini bukan sekadar revisi kita.