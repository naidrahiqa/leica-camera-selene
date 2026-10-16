# ISSUE: MFB (Multi-Frame Blending) timeout — foto zoom 0.6x & 1x gagal ke-save

> Status: **TERBUKA** — akar masalah sudah dipetakan sampai ke pass ke-5; tinggal instrumentasi kernel.
> Terakhir diperbarui: 14 Okt 2026, ~20:45 WIB
> Device: Redmi Note 10 (selene / 21061119AG), MediaTek MT6769H
> Kernel: 4.19.325-PawwwNunungggg-cip136-st20 (build sendiri via GitHub Actions)
> Build saat test: `g1951bbc122b3`
> ROM: Project Infinity GSI (release 16 / sdk 36)
> Module: Leica cam (`xiaomicamera`) + KernelSU root

---

## Ringkasan (TL;DR)

Semua masalah sudah **BERES** (status per 15 Okt 2026, 20:11):

1. ~~Reboot panic saat foto~~ — **FIX** (patch CMDQ NULL-deref, commit lokal, gak di-push).
2. ~~"Foto hilang setelah reboot"~~ — **Bukan bug**. Itu FBE lock (Direct Boot). Semua file balik setelah unlock.
3. ~~Foto zoom 0.6x & 1x gagal ke-save~~ — **FIX** lewat `selene.json` (`isLegacyMfnrDevice` + `supportSwMfnr`) → software MFNR, bukan MFB hardware. Lihat bagian SOLUSI.
4. ~~Night mode nggak bisa dipakai~~ — **FIX** lewat patch APK (matikan `applyMfnr`/`applySuperNightMfnr`, nyalakan `applySwMfnr`). Lihat "MASALAH 5".

Matriks mode final: **Foto 0.6/1.0/2.0, Night, Portrait, Pro, Documents, Video — semua ✅**.

---

## SOLUSI (15 Okt 2026) — SELENAI SUDAH KAMPAI

### TL;DR
Foto **0.6X, 1.0X, dan 2.0X semua berhasil ke-save**. Tanpa patch kernel, tanpa rebuild.
Cukup satu file konfigurasi:

```
/data/media/0/Download/XiaomiCamera/selene.json
  "isLegacyMfnrDevice" : false  ->  true
  "supportSwMfnr"      : false  ->  true
```
(kdang `/sdcard/Download/...` — file yang sama, di belakang `/storage/emulated/0`)

### Kenapa itu memperbaiki

App Leica/MIUI punya cabut "legacy device" yang memang dirancang untuk chip tanpa MFB
(`com/android/camera/module/Camera2Module.java`):
```java
public boolean Tm() {          // key "supportSwMfnr"
    ...
    if (DataItemFeature.l2().s3() && m != 167 && m != 173 && !CameraSettings.M5()) {
        Log.d(TAG, "For the devices does not have hardware MFNR, use software MFNR");
        return true;
    }
```
- `s3()` -> file key **`isLegacyMfnrDevice`**
- `pb()` -> file key **`supportSwMfnr`**

Dan di `Camera2Module.Kp(boolean)` (key `isSupportMfnr`, sumber log `setMfnr to X`):
```java
boolean z = true;
if (Tm() || !enable || (... )) z = false;
Log.d(TAG, "setMfnr to " + z);
```
Selama `isLegacyMfnrDevice=false` dan `supportSwMfnr=false`, `Tm()` false, dan syarat
`me().ng() != 1.0f` (zoom multiple) **hanya benar di selain 1.0X** — makanya hardware MFNR
menyala **tepat di 1.0X** saja. Setelah dua key di-set true, `Tm()` true -> `setMfnr to false`
-> hardware MFNR tidak dipakai, ganti **software** MFNR (`AppMfbll`) yang tidak butuh MFB.

### ROOT CAUSE FINAL (terbukti dengan instrumen sampler kernel)

Kernel instrumen (`DIPSMP`, sampling 10 ms) menunjukkan **langsung** perbedaan antara pass
sukses dan pass yang nangkut. `cqint` = `ISP_DIP_A_BASE+0x044` (`CTL_CQ_INT_STATUSX`),
bit0 = CQ thread0 EOF:

```
1117.809  cq0=4b19c000  cqint=20000001   pass selesai (16 ms kemudian)   OK
1117.841  cq0=4b1a8000  cqint=20000001   OK
1117.873  cq0=4b1ae000  cqint=20000003   CQ0 + CQ1 done                  OK
1117.905  cq0=4b1ba000  cqint=20000003   OK
1117.921  cq0=4b1c0000  cqint=20000002
1117.937  cq0=4b1c0000  cqint=00000000   BIT0 TIDAK PERNAH NAIK  <-- pass nangkut
1119.665  cq0=4b1c6000  cqint=00000000   masih 0 setelah 1,7 detik
```

Pada setiap pass sukses, base CQ0 baru diprogram -> dalam 16-32 ms `cqint` jadi `0x20000001`.
Pada pass MFNR yang gagal, base **tetep** diprogram dengan `ctl=0x11` (armed) tapi bit0
tidak pernah naik -> `CMDQ_EVENT_DIP_CQ_THREAD0_EOF` tidak pernah raise -> GCE wait
1,15 detik -> `-110` -> `onCameraAbnormal error=2`.

**Kesimpulan:** hardware MFNR (MFB) di MT6768 tidak bisa dieksekusi. Job-nya success
dijalankan GCE, CQ-nya di-arm, tapi unit MFB-nya tidak ada sehingga job tidak pernah
selesai. Bukti pendukung: **0 port MFB di M4U** (chip lain 5-16), **0 event MFB** di
`mt6768-gce.h`, tidak ada driver/clock `img_mfb`.

### Cara installing (biar permanent)
Script sudah di-append ke `service.sh` module (`/data/adb/modules/xiaomicamera/service.sh`,
backup: `service.sh.bak.mfnr`):
```sh
for BASE in /data/media/0/Download/XiaomiCamera /sdcard/Download/XiaomiCamera; do
    [ -d "$BASE" ] || continue
    GC="$BASE/general_config.json"; DEV="$BASE/selene.json"
    [ -f "$GC" ] || echo '[{"deviceCodename":"selene"}]' > "$GC"
    if [ ! -f "$DEV" ]; then
        echo '[{"isLegacyMfnrDevice":true},{"supportSwMfnr":true}]' > "$DEV"
    else
        sed -i 's/"isLegacyMfnrDevice":false/"isLegacyMfnrDevice":true/g;
                s/"supportSwMfnr":false/"supportSwMfnr":true/g' "$DEV"
    fi
    chown media_rw:media_rw "$DEV"; chmod 664 "$DEV"
    chown media_rw:media_rw "$GC";  chmod 664 "$GC"
    break
done
```
Catatan: app **cache** config ini di memori, jadi setelah mengubah file harus
`am force-stop com.android.camera` dulu.

### HASIL TEST FINAL (15 Okt 2026, kernel clean `g4ec4208ddead`, module v2 `830002`)

Test ulang SETELAH rebuild module + flash kernel bersih (instrumen debug sudah dibuang):

| Mode | Hasil | Bukti |
|---|---|---|
| Photo 0.6X | **OK** | foto tersimpan, `-110`=0, `err2`=0 |
| Photo 1.0X | **OK** | foto tersimpan, `-110`=0, `err2`=0 |
| Photo 2.0X | **OK** | foto tersimpan, `-110`=0, `err2`=0 |
| Portrait | **OK** | `IMG_20261015_184618_1.jpg` |
| Pro | **OK** | foto+1, `-110`=0, `err2`=0 |
| Documents | **OK** | `DOCUMENT_PICTURE_1792064878056.jpg` (3.6 MB) |
| Video | **OK** | `VID_20261015_184950.mp4` (25.5 MB) |
| **Night** | **GAGAL** | `onCameraAbnormal`=2, `wait flush result`=1 |

**7 dari 8 mode normal.** Night masih merusak (detail di bawah).

Kernel clean — verifikasi instrumen sudah hilang:
```
DIPSMP / DIPCQSNAP / dip1 irq # / DIP INT(_030 : 0  (semua)
enable_irq dip                   : 6  (fix asli tetap ada)
oops di boot ini                 : 0
dmesg                            : 8.957 baris (sebelumnya 23.000+)
```

### Verifikasi
| Zoom | Sebelum fix | Sesudah fix |
|---|---|---|
| 0.6X | gagal, `-110`, `error=2` | ✅ `IMG_20261015_180803_1.jpg` |
| 1.0X | gagal, `-110`, `error=2` | ✅ 3 foto berturut (`180618`, `180641`, `180648`) |
| 2.0X | ✅ selalu berhasil | ✅ |

---

## Masalah 1: Reboot panic (SUDAH FIX)

**Gejala:** Jepret 1 foto → phone reboot (kernel panic).

**Root cause:** Bug NULL-deref di jalur dump-error CMDQ kamera.
- File: `drivers/misc/mediatek/cmdq/v3/cmdq_helper_ext.c`
- Fungsi `cmdq_core_save_hex_first_dump()` (~baris 1688) nulis ke `cmdq_first_err.cmdqString` yang **TIDAK PERNAH dialokasi** (allocator satu-satunya di `cmdq_core_save_first_dump()` dimatikan `#if 0`).
- Saat CMDQ timeout pertama: `flag=true`, `cmdqString=NULL` → `snprintf(NULL, 32768, "%s%p:%s\n", ...)` → oops di vsprintf `number()`/`pointer_string` (WRITE ke alamat 0) → `panic_on_oops=1` → reboot.
- Bug sekunder: `cmdqMaxSize` (s32) bisa underflow → size_t raksasa → heap overflow.

**Fix (commit lokal, JANGAN di-push):** alokasi buffer on-demand (GFP_ATOMIC) + NULL-check + stop loop saat buffer penuh + `kfree` di `cmdq_core_reset_first_dump()`.

**Bukti fix berhasil:** Tes kamera 14 Okt → **0 oops** di `test4-kmsg.txt` (sebelumnya crash).

---

## Masalah 2: "Foto hilang setelah reboot" (BUKAN BUG)

**Gejala:** Foto muncul di preview, setelah reboot hilang dari galeri.

**Root cause:** **FBE (File-Based Encryption) lock / Direct Boot**, bukan data loss.
- `/data` (f2fs) mount dengan `inlinecrypt` + `fileencryption=aes-256-...keydirectory=/metadata/vold/metadata_encryption` (dari `/vendor/etc/fstab.mt6768`).
- `/data/media/0` (= backing `/sdcard`) adalah storage **CE (Credential Encrypted)** — kunci baru tersedia setelah user **unlock** (masukin PIN/pola).
- Setelah `adb reboot`, HP nyala ke lock screen (`vold.decrypt=locked`). Storage CE belum bisa diakses → file kelihatan "hilang" / tulis gagal `Required key not available` (ENOKEY).
- **Begitu unlock, semua file KEMBALI** — dibuktikan: foto 20:08 (`IMG_20261013_200834.jpg` + video) dan file tes `_durtest.bin` balik semua.

**Konsep penting:** `fsync_mode=nobarrier` (di fstab ROM) itu trade-off durability, tapi TIDAK menyebabkan kehilangan file di sini. Jangan salahkan nobarrier.

**Catatan metodologi:** Jangan pernah verify persistence file CE via `adb shell su` saat device locked — hasilnya misleading (file "hilang" padahal cuma kekunci).

---

## Masalah 3: MFB timeout — foto 0.6x & 1x gagal (SELESAI — lihat bagian SOLUSI)

### Gejala
- Zoom **0.6x** & **1x**: freeze ±1.15s → `onError: error = 4` → **foto gak ke-save**.
- Zoom **2x** & **Mode PRO**: aman, cepat (343ms), ke-save.

### Reproduksi 100% andal (dipakai semua tes)
1. Buka kamera → mode **Foto** → zoom **1.0X**.
2. `logcat -b all -c`
3. `input tap 540 1992`  (shutter `[430,1882][650,2102]`)
4. ~1.7s kemudian: `[cmdq][err] timeout` → `wait task result failed:-110` → `error=4`.

Pembanding: `input tap 665 1595` (2.0X) → sukses 343ms, `setMfnr to false`, **0** `AppMfbll`, **0** `DpIsp: ISP Pass2 only`.

### Pemicu sudah diisolasi 1:1
| Aplikasi | Hasil |
|---|---|
| `setMfnr=true` (Photo @1.0x / 0.6x) | **GAGAL** (CMDQ `-110`) |
| `setMfnr=false` | **SUKSES** 5+ foto berturut-turut |

`setMfnr` murni **logika app** (`CAM_Camera2Module` / `CAM_ProModule`) — tidak ada prop/module config yang mengendalikannya.

---

### RANTAI AKAR MASALAH (terbukti dari log, konsisten di 5 run)

**MFNR = tepat 5 pass `DpIsp: ISP Pass2 only` (libdp `DpIspStream`, scenario 8, via MDP). Pass 1–4 selesai, pass 5 SELALU hang.**

Run yang diverifikasi (selalu: 5 submit → hang):
| Waktu | Submit pass 1..5 | Gagal |
|---|---|---|
| 18:12:25 (testB) | .207 .784 26.060 .307 .362 | 18:12:27.993 |
| 18:18:55 (testB) | .921 .996 56.037 .070 .105 | 18:18:57.694 |
| 19:51:37 (live) | .600 .769 .819 .862 .905 | 19:51:39.040 |
| 19:54:32 (live) | .558 .661 .708 .751 .796 | 19:54:33.832 |
| 19:59:46 (live) | .584 .729 .776 .817 .863 | 19:59:48.022 |

Run 19:59:46 detail (pass 1–4 selesai, pass 5 hang):
```
46.584 DpIsp: ISP Pass2 only   → 46.628 src 46 ms   OK
46.729 DpIsp: ISP Pass2 only   → 46.770 src 41 ms   OK
46.776 DpIsp: ISP Pass2 only   → 46.813 waitFramedone 35ms, scenario 8, waitComplete 35 ms  OK
46.817 DpIsp: ISP Pass2 only   → 46.858 waitFramedone 35ms, scenario 8, waitComplete 35 ms  OK
46.863 DpIsp: ISP Pass2 only   → 48.022 waitFramedone failed(-1) 110 Connection timed out
                                 scenario 8, waitComplete 1157 ms   <<< HANG
```
Capture **2.0X yang sukses punya 0 pass `ISP Pass2 only`** → jalur MFNR memang khusus.

**Rantai hang-nya:**
1. `MultiFrameNode::onRequestProcess +` (46.462) tidak pernah menutup.
2. GCE thread **11/12**, scenario `CMDQ_SCENARIO_USER_MDP`(12), caller `MDP-0`/`MDP-1`,
   eksekusi instruksi `0x80008001:0x20000101` = **`Wait And Clear Event:CMDQ_EVENT_DIP_CQ_THREAD0_EOF`** (eventID `0x3FF & insts[1]` = `0x101` = **257**).
3. Setelah ~1.15s: `wait flush result cost:1153754us` → `wait task result failed:-110` → `DpIspStream: wait stream failed(-26)` → `error=4`.
4. Konsekuensi turunan: `WaitHub waitCondition timeout(100)`, `SharedBufferPool requestIIBuffer pool[fpipe.tpi.shared] timeout`, `ULogGuard TimeBomb`, `HalPipeDequeNode ERROR: Dequeue Buffer Fail`.

### Bukti bahwa event 257 tidak pernah terjadi
- `cmdq_core_dump_pc()` baca balik `CMDQ_SYNC_TOKEN_ID=257` → **`value:0`** (tidak pernah di-set).
- Kontras: `CMDQ_EVENT_DISP_RDMA0_EOF`(=1) dibaca **`is 1`** → jalur GCE + display **sehat**, bukan GCE-nya rusak.
- → **DIP CQ thread0 memang tidak pernah menghasilkan EOF.**

### Bukti kondisi register DIP saat hang (dari `ISP_DumpDIPReg`, identik di testA/testB/live)
```
direct link:15020030(0x10000)
isp: 15022000(0x1)      <- CTL_START: bit0 (CQ thread0) masih aktif
isp: 15022004(0x123dfc) 15022008(0xf0) 1502200C(0x7c00)
CTL_INT_STATUSX      0x15022040(0x40100000)
CTL_CQ_INT_STATUSX   0x15022044(0x0)    <- CQ TIDAK PERNAH raise interrupt/EOF
CTL_CQ_INT2_STATUSX  0x15022048(0x0)
CTL_CQ_INT3_STATUSX  0x1502204C(0x0)
isp: 15022104(0x11)-15022108(0x4f790000) <- CQ0 base terprogram (semua thread 0x11, hanya CQ0 base!=0)
isp: 15022204(0x57110000)                 <- tdriaddr terprogram
isp: 15022408(0x0)
mfb:  0x15022F60(0xc41)...   mfbo: 0x15022350(0x78c00000)...   <- register MFB (di dalam DIP) terisi
```
`CAMA PHY cqcnt:N VIR cqcnt:N` selalu **in-sync** (VIR_CQCNT bukan penyebab).

### Yang SUDAH DITUTUP (dengan bukti)
| Kandidat | Status | Bukti |
|---|---|---|
| Prop / module config | **Tutup** | Tes A & Tes B keduanya gagal; tak ada prop yang mengendalikan `setMfnr` |
| `sendCommand(0x1500)` NOT support | **Tutup** | 27.069 kemunculan (tiap 33ms, preview) — **muncul juga di jalur sukses** → noise |
| Clock DIP | **Tutup** | `img_dip` enable count naik 0→7 selama capture |
| SMI hang | **Tutup** | `SMI MM bus NOT hang` |
| IOMMU / fault | **Tutup** | tak ada fault |
| Nomor event GCE | **Tutup** | `0x101`=257 cocok `include/dt-bindings/gce/mt6768-gce.h:118` |
| VIR_CQCNT desync | **Tutup** | in-sync |
| Engine mask `0x4245` | **Tutup** | WARN hanya `task_count > 3` (congestion), bukan error |
| Log-silencing `c041feaa256f` | **Tutup** | hanya `pr_info`→`pr_debug`, tak ada perilaku berubah |
| Callback CPU `dip1` | **Tutup** (bukan jalur selesai) | count=0 **bahkan saat capture 2.0X SUKSES** → selesai DIP tidak lewat GIC. Build instrumen: IRQ sudah di-`enable`, tapi `dip1 irq #` tetap 0 → DIP tidak assert interrupt sama sekali |
| Regresi `enable_irq` DIP | **Tutup** (regresi nyata, tapi bukan pemicu) | sudah di-fix (`enable_irq dip, irq=115` muncul), hasil kegagalan **tidak berubah** |

### REGRESI BARU: IRQ `dip1` tidak PERNAH di-enable (commit `b291949aa61c`)
- `b291949aa61c` (28 Sep 2026) menambahkan `disable_irq(isp_dev->irq)` untuk **SEMUA** device setelah `request_irq` (`camera_isp.c:13063`).
- Tapi `enable_irq` hanya loop: `for (module = ISP_CAM_A_IDX; module < ISP_CAMSV4_IDX; module++)` (`camera_isp.c:4182`).
- Enum `ISP_DEV_NODE_ENUM` di `src/mt6768/inc/camera_isp.h:52`:
  `0=IMGSYS_CONFIG, 1=DIP_A, 2=CAMSYS_CONFIG, 3=UNI_A, 4=CAM_A … 10=CAMSV4, 11=CAMSV5`
- **`ISP_DIP_A_IDX = 1` ada di LUAR `[4,10)` → IRQ `dip1` (GIC 115) tak pernah di-enable.** (`ISP_UNI_A_IDX=3` juga kena.)
- **Bukti live:** `/proc/interrupts` `dip1` = **0 di semua capture**; dmesg hanya mencetak `enable_irq cam 4, irq=124` … `cam 9, irq=129`.
- Akibat: `ISP_Irq_DIP_A()` tak pernah jalan → `IspInfo.IrqInfo.Status[ISP_IRQ_TYPE_INT_DIP_A_ST]` tak pernah terisi.
- **Catatan jujur:** kemungkinan **bukan** pemicu langsung (jalur 2x sukses juga tanpa dip1, dan tak ada `ISP_WaitIrq Type(2)` di log). Tapi ini regresi nyata dan wajib difix — lihat prompt di bawah.

`ISP_IRQ_TYPE_ENUM` mt6768 (`src/mt6768/inc/camera_isp.h:98`): `0=CAM_A, 1=CAM_B, 2=DIP_A, 3=CAMSV_0, 4=CAMSV_1, 5..8=CAMSV_2..5, 9=UNI_A`.
Semua `ISP_WaitIrq` di log hanya Type **0** (CAM_A) dan **4** (CAMSV_1) — tak pernah Type **2** (DIP_A).

### HASIL BUILD INSTRUMEN (15 Okt 2026, kernel `g5b9f76bfa86b-dirty`) — 4 kegagalan, signature identik

Instrumen **aktif dan terbaca**. Fix `enable_irq` juga terbukti bekerja (`enable_irq dip, irq=115` muncul, seimbang dengan `disable_irq dip`). Hasil:

| Sinyal | Nilai saat hang | Arti |
|---|---|---|
| `dip1 irq #` | **0** (padahal IRQ sudah aktif) | ISR `ISP_Irq_DIP_A` **tidak pernah dipanggil** sama sekali |
| `DIP INT(_030/034/038)` | **`0x0 / 0x0 / 0x0`** | `_INT_STATUS`, `_CQ_INT_STATUS`, `_CQ_LD_INT_STATUS` **semua nol** → DIP tidak punya interrupt apa pun yang tertunda |
| `CTL_CQ_INT_STATUSX (0x044)` | **`0x0`** | CQ0 **tidak pernah** raise EOF |
| `CTL_INT_STATUSX (0x040)` | `0x40100000` | konstan di semua dump (bit 30+28) — bukan penanda CQ |
| `CTL_START (0x000)` | `0x1` | thread0 "started" |
| `CQ0 ctl/base/size (0x104/108/10C)` | `0x11` / `0x4c6a8000` / `0x2d8` | base+size terprogram |
| `CQ0 ctl` vs CQ lain | **semua 32 slot = `0x11`** | `0x11` = nilai default/reserved → **CQ0 kemungkinan besar tidak pernah benar-benar di-kick**, hanya base+size yang ditulis |
| isi descriptor di `CQ0 base` | run MFNR: `DIPCQ0[00]=0x000a0065`, sisanya **nol semua**; run lain: nol + heap garbage di offset `0x280` | **buffer descriptor praktis kosong** |
| isi `DRIPTP` (tdri) | data acak / pixel-like | `memremap` addr itu tidak menghasilkan descriptor yang bisa dibaca |

**Dua varian kegagalan, signature register sama persis:**
- **Varian A (MFNR klasik):** `setMfnr` → 2 pass `scenario 8` sukses (39 ms, 35 ms) → pass berikutnya hang `waitComplete 1135 ms` → `-110` → `error=2`.
- **Varian B (gagal lebih awal):** job `DpIspStream scenario 8` **pertama** langsung hang (`waitComplete 1768 ms`) → `-110` → `error=2`, **sebelum** `setMfnr` ter-log.

⇒ Hangnya **bukan khusus pass ke-5 / bukan khusus MFB**. Yang menentukan cuma: begitu ada job MDP `scenario 8` yang menunggu `CMDQ_EVENT_DIP_CQ_THREAD0_EOF`, DIP tidak pernah menuntaskan CQ-nya.

**Kontrol 2.0X (05:04):** SUKSES penuh — `setMfnr` 0, `ISP Pass2 only` 0, `AppMfbll` 0, `DpIspStream` wait 0, `-110` 0, `error=2` 0, foto tersimpan `IMG_20261015_050401_1.jpg` (3.68 MB).

### HASIL PENENTUAN H1 vs H2 (15 Okt 17:43) — H2 TERBUKTI, H1 gugur

**H2 benar. Semua temuan "descriptor kosong" adalah artefak pengukuran.**

Bukti:
1. Port M4U `CAM_IMGI(1)` (dan semua `CAM_*`) **aktif** di device.
2. `/sys/kernel/debug/m4u/buffer` → `cmdqaddr` jatuh di dalam alokasi **MVA** (bukan physical).
3. `/sys/kernel/debug/m4u/pgtable` (**167.324 baris, dump-nya cuma 0.36 detik**) diambil ~1 detik setelah tap, pas di detik hang. Untuk capture itu `cmdqaddr=0x48912000`:

| Alamat di register DIP | Ter-map di M4U? | Physical sebenarnya |
|---|---|---|
| `0x48912000` — **CQ0 base** | **YA** | **`0x51700000`** |
| `0x48a08000` — CQ1 base | YA | `0x50A00000` |
| `0x4a440000` — tdri | YA | `0xD8250000` |

Jadi `memremap(0x48912000)` di dump sebelumnya **baca halaman yang salah**. Descriptor CQ kemungkinan besar **ada dan valid** → **H1 ("CQ tidak pernah di-kick karena descriptor kosong") tidak didukung bukti**, dan `cq0ctl=0x11` yang "sama dengan CQ lain" ternyata cuma nilai register, bukan bukti apa pun.

**Konsekuensi ke prompt:** `DIPCQSNAP` harus pakai `m4u_mva_map_kernel()`, bukan `memremap()`. Kabar baiknya `camera_isp.c` **sudah** `#include <m4u.h>` (baris 63) dan **sudah** memakai pola itu di baris 3272, jadi tinggal meniru.

Yang tersisa cuma satu pertanyaan: **apakah DIP benar-benar menjalankan CQ lalu tidak pernah EOF, atau memang tidak dijalankan sama sekali.** Itu jawabannya hanya dari timeline register (`DIPSMP`) — karena saat ini kita belum pernah melihat CQ0 pada pass yang BERHASIL.

### Belum MFB "nggak ada" di MT6768?
- `mt6768-gce.h`: **0** event MFB (mt6779 punya `CMDQ_EVENT_MFB_DONE=278`).
- `cameraisp/mfb/Makefile`: MT6768 **tidak ada** di `ifeq` mana pun → cuma `camera_mfb_dummy.o`.
- Tak ada `img_mfb` clock, tak ada node `mfb@` di DTS.
- **Tapi** register `mfb`/`mfbo` berada **di dalam DIP** (`0x15022F60`, `0x15022350`, `0x1502265C`) dan ikut ke-dump/terisi → MFB memang sub-blok DIP, bukan IP terpisah.

---

### PROMPT UNTUK AGENT KERNEL (build ke-2 - TRACE PROGRAM GCE)  <-- KERJAKAN INI DULU

Repo: `/home/naidra/Projects/Kernel/android_kernel_xiaomi_mt6768-k419` (branch `PawwwNunungggg24.0`).
**Build lokal, commit LOKAL saja, JANGAN di-push.** Semua instrumen sebelumnya (fix `enable_irq`, `ISP_DumpDIPReg`, `dip1 irq #`) **SUDAH ada di working tree - jangan diubah, jangan di-revert.**

File: `drivers/misc/mediatek/cmdq/v3/cmdq_helper_ext.c`. **Tidak ada perubahan fungsional.**

Alasan: register DIP itu ditulis oleh **HAL lewat GCE**, bukan oleh driver kernel. Driver cuma baca. Jadi selama ini kita belum pernah melihat apakah HAL benar-benar men-"kick" CQ-nya. GCE thread yang nge-wait event 257 itu punya satu instruksi `WFE` di akhir, dan **seluruh program thread itu masih utuh di SRAM** - kita tinggal decode.

Yang sudah ada di file ini (jangan tulis ulang, pakai saja):
- `cmdq_core_parse_instruction(const u32 *pcVA, char *buf, unsigned int bufLen)` - decoder 1 instruksi
- `cmdq_core_get_pc_va(dma_addr_t, handle)` - PA -> VA
- `cmdq_core_get_pc(thread)` / `cmdq_core_get_end(thread)`
- `CMDQ_IS_END_ADDR(pc)`

#### 1. Fungsi trace baru

Taruh **tepat sebelum** `cmdq_core_dump_error_handle()` (sekitar baris 3301):

```c
/* ==== INSTRUMEN: trace seluruh program GCE thread yang hang ==== */
static void cmdq_core_trace_thread_program(const struct cmdqRecStruct *handle,
	s32 thread)
{
	dma_addr_t pc_pa, end_pa, cur_pa;
	char buf[160];
	int i;

	if (!handle || thread == CMDQ_INVALID_THREAD)
		return;
	if (handle->secData.is_secure) {
		CMDQ_ERR("[TRACE] thread %d secure, skip\n", thread);
		return;
	}

	pc_pa = (dma_addr_t)cmdq_core_get_pc(thread);
	end_pa = (dma_addr_t)cmdq_core_get_end(thread);
	if (CMDQ_IS_END_ADDR(pc_pa) || CMDQ_IS_END_ADDR(end_pa))
		return;

	CMDQ_ERR("[TRACE] ===== thread %d End=0x%08x PC=0x%08x =====\n",
		thread, end_pa, pc_pa);

	/* GCE mulai eksekusi tepat SESUDAH instruksi End */
	cur_pa = end_pa + 8;

	for (i = 0; i < 400; i++) {
		u32 *pVA;
		u32 insts[2];

		if (cur_pa == end_pa)
			break;	/* guard: program circular */
		pVA = cmdq_core_get_pc_va(cur_pa, handle);
		if (!pVA)
			break;

		insts[0] = pVA[0];
		insts[1] = pVA[1];

		buf[0] = '\0';
		cmdq_core_parse_instruction(pVA, buf, sizeof(buf));
		CMDQ_ERR("[TRACE] %3d 0x%08x:0x%08x => %s%s\n",
			i, insts[0], insts[1], buf,
			(cur_pa == pc_pa) ? "   <== PC (MACET DI SINI)" : "");

		if (cur_pa == pc_pa)
			break;
		cur_pa += 8;
	}
}
```

#### 2. Panggil dari jalur dump error

Di `cmdq_core_dump_error_handle()`, di dalam blok `if (handle) { ... }`, **tepat setelah** baris `hwPC = cmdq_core_dump_pc(handle, thread, "ERR");`:

```c
			cmdq_core_trace_thread_program(handle, thread);  /* TAMBAHAN */
```

Kalau `cmdq_core_trace_thread_program()` dianggap terlalu statis untuk dipakai hanya di file ini, hapus modifier `static`-nya.

#### 3. Batasan

- Hanya baca. Tidak ubah state GCE sama sekali.
- `cmdq_core_get_pc_va()` dipanggil dengan PA; kalau dia mengembalikan NULL karena di luar buffer, loop berhenti - itu normal.
- Batasi 400 instruksi supaya tidak flooding.
- Jangan lupa: file ini dipakai beberapa platform, jadi jangan sampai ada warning `unused variable`.

#### Cara tes setelah flash

Resep reproduksi tetap: **Foto + 1.0X + `input tap 540 1992`**, lalu `dmesg`.

Yang dicari:
1. Blok `[TRACE]` untuk thread yang hang (biasanya thread 11, scenario 12 `CMDQ_SCENARIO_USER_MDP`).
2. Cari instruksi yang menulis register DIP CQ, yaitu yang `parseModule`/`addr:`-nya sekitar `0x15022xxx` - khususnya `0x15022104` (ctl), `0x15022108` (base), `0x1502210C` (size), `0x15022000` (CTL_START).
3. **Pertanyaan penentu:**
   - Apakah ada instruksi **write** ke `0x15022104` dengan nilai yang berbeda dari `0x11`? Kalau tidak ada sama sekali -> HAL tidak pernah meng-kick CQ (H1 benar, tapi karena HAL, bukan karena descriptor).
   - Kalau ada write dengan nilai `0x11` -> nilai `0x11` memang nilai "armed", dan masalahnya CQ jalan tapi tidak pernah EOF.
   - Ada/tidaknya write ke `0x15022000` (CTL_START) dan urutan relatifnya terhadap `WFE 257`?
4. Catat juga: berapa instruksi total, dan apakah ada instruksi setelah `WFE` yang berarti (kalau ada, artinya program-nya belum selesai disusun).

Kirim balik: (a) `git diff` untuk `cmdq_helper_ext.c`, (b) blok `[TRACE]` lengkap dari satu capture yang gagal, (c) `dmesg | grep -c TRACE`.

---

### PROMPT UNTUK AGENT KERNEL (build ke-3 - SAMPLER periodik CQ DIP (JALANKAN SETELAH build ke-2))

Repo: `/home/naidra/Projects/Kernel/android_kernel_xiaomi_mt6768-k419` (branch `PawwwNunungggg24.0`).
**Build lokal, commit LOKAL saja, JANGAN di-push.** Fix `enable_irq` yang lalu **SUDAH terpasang di working tree - jangan diubah, jangan di-revert.**

Tujuan eksperimen ini satu: **dalam SATU capture yang gagal, lihat kondisi register CQ DIP pada pass yang BERHASIL (1-2) lalu pada pass yang NYANGKIT (terakhir).** Dump sekarang hanya jalan saat timeout, jadi kita tidak pernah melihat sisi yang sehat.

Semua perubahan hanya di `drivers/misc/mediatek/cameraisp/src/mt6768/camera_isp.c`. **Tidak ada perubahan fungsional** - jangan sentuh alur kamera.

#### 1. Sampler periodik

Taruh blok ini **setelah baris ~742** (`static unsigned int G_u4EnableClockCount;`), supaya masih di atas `ISP_EnableClock()`:

```c
/* ==== INSTRUMEN: sampler CQ DIP (hapus setelah selesai) ==== */
#define DIP_SMP_INTERVAL_MS 10
#define DIP_SMP_MAX_SAMPLES 1200
#define DIP_SMP_SNAP_MAX    64

static atomic_t dip_smp_atomic = ATOMIC_INIT(0);	/* 0=idle 1=run 2=stop */
static unsigned int dip_smp_n;
static unsigned int dip_smp_snap_n;
static unsigned int dip_smp_p_start, dip_smp_p_cq0ctl, dip_smp_p_cq0base;
static unsigned int dip_smp_p_cq0size, dip_smp_p_cq1base;
static unsigned int dip_smp_p_cqint, dip_smp_p_intst;
static unsigned int dip_smp_p_tdri, dip_smp_p_imgi;

static void dip_smp_work(struct work_struct *w);
static DECLARE_DELAYED_WORK(dip_smp_dwork, dip_smp_work);

static void dip_smp_snapshot(unsigned int mva, unsigned int size)
{
	/* PENTING: base ini MVA (M4U), BUKA physical address.
	 * memremap() akan membaca halaman yang salah.
	 * Pakai m4u_mva_map_kernel() - polanya sudah dipakai file ini
	 * di ~baris 3272 untuk dump tpipe.
	 */
	unsigned int map_va = 0, map_size = 0;
	int *p;
	int i, lim;

	if (mva == 0 || mva == 0xffffffff)
		return;
	if (m4u_mva_map_kernel(mva, 0x1000, 0, &map_va, &map_size) != 0 ||
	    map_va == 0) {
		pr_info("DIPCQSNAP #%u mva_map_kernel FAIL mva=%08x\n",
			dip_smp_n, mva);
		return;
	}
	p = map_va;
	lim = (size && size < 0x1000) ? (int)(size / 4) : 64;
	if (lim > 64)
		lim = 64;
	for (i = 0; i + 4 <= lim; i += 4)
		pr_info("DIPCQSNAP #%u [%02x] %08x %08x %08x %08x\n",
			dip_smp_n, i / 4, p[i], p[i + 1], p[i + 2], p[i + 3]);
	m4u_mva_unmap_kernel(mva, map_size, map_va);
}

static void dip_smp_sample(int force)
{
	unsigned int s_start, cq0ctl, cq0base, cq0size, cq1base;
	unsigned int cqint, intst, tdri, imgi;
	int base_changed, int_changed;

	if (G_u4EnableClockCount == 0)	/* clock mati: jangan sentuh HW */
		return;

	s_start = ISP_RD32(ISP_DIP_A_BASE + 0x000);
	cq0ctl  = ISP_RD32(ISP_DIP_A_BASE + 0x104);
	cq0base = ISP_RD32(ISP_DIP_A_BASE + 0x108);
	cq0size = ISP_RD32(ISP_DIP_A_BASE + 0x10C);
	cq1base = ISP_RD32(ISP_DIP_A_BASE + 0x114);
	cqint   = ISP_RD32(ISP_DIP_A_BASE + 0x044);
	intst   = ISP_RD32(ISP_DIP_A_BASE + 0x030);
	tdri    = ISP_RD32(ISP_DIP_A_BASE + 0x204);
	imgi    = ISP_RD32(ISP_DIP_A_BASE + 0x400);

	base_changed = (cq0base != dip_smp_p_cq0base);
	int_changed  = (cqint != dip_smp_p_cqint);

	if (force || base_changed || int_changed ||
	    s_start != dip_smp_p_start || cq0ctl != dip_smp_p_cq0ctl ||
	    cq0size != dip_smp_p_cq0size || cq1base != dip_smp_p_cq1base ||
	    intst != dip_smp_p_intst || tdri != dip_smp_p_tdri ||
	    imgi != dip_smp_p_imgi) {
		pr_info("DIPSMP #%u start=%08x cq0=%08x/%08x/%08x cq1base=%08x cqint=%08x int=%08x tdri=%08x imgi=%08x\n",
			dip_smp_n, s_start, cq0ctl, cq0base, cq0size,
			cq1base, cqint, intst, tdri, imgi);

		dip_smp_p_start = s_start; dip_smp_p_cq0ctl = cq0ctl;
		dip_smp_p_cq0base = cq0base; dip_smp_p_cq0size = cq0size;
		dip_smp_p_cq1base = cq1base; dip_smp_p_cqint = cqint;
		dip_smp_p_intst = intst; dip_smp_p_tdri = tdri;
		dip_smp_p_imgi = imgi;

		/*
		 * base CQ0 baru diprogram ATAU status CQ berubah ->
		 * snapshot descriptor SEKARANG, sebelum buffer di-reuse.
		 */
		if ((base_changed || int_changed) &&
		    dip_smp_snap_n < DIP_SMP_SNAP_MAX) {
			dip_smp_snap_n++;
			dip_smp_snapshot(cq0base, cq0size);
		}
	}
}

static void dip_smp_work(struct work_struct *w)
{
	if (atomic_read(&dip_smp_atomic) != 1)
		return;

	dip_smp_sample(0);

	if (++dip_smp_n >= DIP_SMP_MAX_SAMPLES ||
	    atomic_read(&dip_smp_atomic) != 1) {
		atomic_set(&dip_smp_atomic, 0);
		return;
	}
	queue_delayed_work(system_wq, &dip_smp_dwork,
			   msecs_to_jiffies(DIP_SMP_INTERVAL_MS));
}

static void dip_smp_start(void)
{
	dip_smp_n = 0;
	dip_smp_snap_n = 0;
	dip_smp_p_start = ~0U; dip_smp_p_cq0ctl = ~0U;
	dip_smp_p_cq0base = ~0U; dip_smp_p_cq0size = ~0U;
	dip_smp_p_cq1base = ~0U; dip_smp_p_cqint = ~0U;
	dip_smp_p_intst = ~0U; dip_smp_p_tdri = ~0U;
	dip_smp_p_imgi = ~0U;
	atomic_set(&dip_smp_atomic, 1);
	queue_delayed_work(system_wq, &dip_smp_dwork,
			   msecs_to_jiffies(DIP_SMP_INTERVAL_MS));
}

static void dip_smp_stop(void)
{
	if (atomic_read(&dip_smp_atomic) == 1) {
		atomic_set(&dip_smp_atomic, 2);
		cancel_delayed_work_sync(&dip_smp_dwork);
		dip_smp_sample(1);	/* sampel terakhir, clock masih hidup */
		atomic_set(&dip_smp_atomic, 0);
	}
}
```

#### 2. Nyalakan/matikan sampler di area clock ISP

Semua ini di `ISP_EnableClock()` (mulai baris ~4191), cabang **`#else/*CCF*/`** yang aktif (kita sudah lihat `enable_irq dip` tercetak di sana).

**Nyalakan** - di dalam blok `if (G_u4EnableClockCount == 1) { ... }` (sekitar baris 4242-4254), **setelah** blok `enable_irq dip` / `spin_unlock`:

```c
			dip_smp_start();          /* TAMBAHAN */
```

**Matikan** - di dalam blok `if (G_u4EnableClockCount == 0)` pada jalur disable (sekitar baris 4314-4326), **setelah** blok `disable_irq dip` / `spin_unlock`:

```c
			dip_smp_stop();           /* TAMBAHAN */
```

PENTING: di cabang CCF, `Disable_Unprepared_ccf_clock()` baru jalan **setelah** titik itu, jadi saat `dip_smp_stop()` dipanggil clock DIP **masih hidup** -> sampel terakhir aman dibaca. Jangan geser titik ini.

#### 3. Pastikan tidak mengganggu

- Semua baca register dijaga `G_u4EnableClockCount == 0` (DIP clock mati -> jangan sentuh, DEVAPC monitor).
- Hanya `pr_info`, tanpa alokasi memori besar.
- `m4u_mva_map_kernel()` / `m4u_mva_unmap_kernel()` harus selalu dipasangkan, dan keduanya TIDAK boleh dipanggil sambil hold spinlock.
- `cancel_delayed_work_sync()` aman karena kedua titik call berada di luar spinlock.
- `<linux/workqueue.h>` (baris 157) dan `<linux/delay.h>` (baris 41) sudah di-include.

#### Cara tes setelah flash

Resep reproduksi tetap: **Foto + 1.0X + `input tap 540 1992`** (shutter bounds `[412,1864][667,2119]`), lalu ambil `dmesg`.

Yang dicari di dmesg:
1. `DIPSMP` - signature register per-sample. Kalau pada pass yang sukses `cq0base` **berubah** + `cqint` sempat jadi bukan-0, lalu pada pass yang nangkit `cq0base` **tidak berubah sama sekali** -> **H1 terbukti: CQ0 tidak pernah di-kick ulang**.
2. Kalau `cq0base` selalu sama dan `cqint` selalu 0 sejak awal -> descriptor hanya ditulis sekali.
3. `DIPCQSNAP` - isi descriptor **saat base-nya baru diprogram**. Kalau `0x00000000` semua -> descriptor memang tidak pernah ditulis HAL. Kalau isinya valid -> descriptor ada, masalahnya di eksekusi CQ.
4. **Paling penting:** catat apakah `cq0ctl` pernah **berbeda dari `0x11`**. Kalau `0x11` ternyata nilai "CQ aktif", maka H1 gugur dan diganti dengan "CQ jalan tapi tidak pernah EOF".

Kirim balik: (a) `git diff --stat` + `git diff` untuk `camera_isp.c`, (b) output `dmesg` berisi semua baris `DIPSMP` + `DIPCQSNAP` dari satu capture lengkap yang gagal (dari sebelum tap sampai 15 detik setelahnya), (c) konfirmasi `dmesg | grep -c 'DIPSMP'`.

---

### File log terkait
- `/tmp/opencode/run3-logcat.txt` + `run3-kmsg.txt` — **run 15 Okt 05:02, paling berguna**: 3 capture beruntun, 3× `-110`, capture #3 kena pola MFNR klasik (2 pass sukses 39/35 ms lalu pass ke-3 hang 1135 ms)
- `/tmp/opencode/run2-logcat.txt` + `run2-kmsg.txt` — 15 Okt 05:01, varian B (gagal di job MDP pertama, sebelum `setMfnr`)
- `/tmp/opencode/run2x-logcat.txt` — 15 Okt 05:04, **kontrol 2.0X sukses**
- `/tmp/opencode/repro-logcat.txt` + `repro-kmsg.txt` — 15 Okt 04:29 (run pertama setelah flash ulang module)
- `/tmp/opencode/camstart.txt` — 15 Okt 04:56, bukti `ApkAssets.nativeLoad` IOException (Masalah 4)
- `/tmp/opencode/live-logcat.txt` (139MB) + `live-kmsg.txt` — run 19:59 (paling lengkap dari sesi lama)
- `/tmp/opencode/testB-logcat.txt`, `testB-kmsg.txt` — run 18:12 & 18:18
- `/tmp/opencode/testA-*` — tes prop
- `/tmp/opencode/win.txt` — jendela logcat percobaan 20:16 (device terkunci, no-op)
- Anchor waktu: `LARB4 [ ON][ 6405.41147]` muncul di logcat `19:59:47.932` → pass5 (`19:59:46.863`) ≈ uptime **6404.35**

---

## Masalah 4: Module kamera hilang dari `/system` → kamera crash-loop (SELESAI dengan re-flash)

**Gejala:** kamera `am start` balas `Status: ok`, tapi proses langsung mati dan `ps` tidak menemukan `com.android.camera`. Loop tiap ~1 detik.

**Bukti (logcat 04:56):**
```
W ResourcesManager: failed to preload asset path '/system/priv-app/MiuiCamera/MiuiCamera.apk'
W ResourcesManager: java.io.IOException: Failed to load asset path ...
        at android.content.res.ApkAssets.nativeLoad(Native Method)
        at android.app.ResourcesManager.loadApkAssets(ResourcesManager.java:596)
E ResourcesManager: failed to add asset path '/system/priv-app/MiuiCamera/MiuiCamera.apk'
W ShellStartingWindow: android.content.pm.PackageManager$NameNotFoundException:
        Application package com.android.camera not found
```
Lalu di dalam app:
```
FATAL EXCEPTION: main  Process: com.android.camera
java.lang.NullPointerException: 'String[] Resources.getStringArray(int)' on a null object
    at android.os.GraphicsEnvironment.queryAngleChoice(GraphicsEnvironment.java:482)
    at android.os.GraphicsEnvironment.setupAngle(...:671)
    at android.os.GraphicsEnvironment.setup(...:148)
    at android.app.ActivityThread.setupGraphicsSupport(...:7807)
    at android.app.ActivityThread.handleBindApplication(...:8075)
```
Baris 482 (AOSP android-16, `core/java/android/os/GraphicsEnvironment.java`) = `context.getResources().getStringArray(R.array.config_angleAllowList)` di dalam `if (android.os.Flags.enableAngleAllowList())`. Ini bener-bener **efek samping**, bukan bug-nya — app mati karena APK-nya tidak bisa dimuat.

**Akar masalah:** `/system/priv-app/MiuiCamera/` **tidak ada sama sekali**, begitu juga `/vendor/etc/camera/sceneDetection.xml`. File masih utuh di `/data/adb/modules/xiaomicamera/` (169.314.153 byte). `/proc/mounts` tidak punya satu pun mount module di `/system`. Jadi **systemless mount-nya hilang**, bukan filenya hilang.

**Konteks:** ada metamodule **`nomount` (NoMount v2.1.1)** — "replaces OverlayFS/MagicMount with **VFS path redirection**", dan `ksud module list` menandai `mount: false` untuk dia tapi `mount: true` untuk `xiaomicamera`. Modul `rezygisk` juga punya `managedFeatures: kernel_umount`.-after install ulang + reboot, file langsung termount lagi dan kamera normal.

**Workaround:** re-flash modulenya (`ksud module install`) + reboot. Kalau muncul lagi tanpa reboot,ceb suspect utama = `nomount`.

**Catatan install:** keluar warning `sh: mark_replace: not found` — itu hanya bagian bersihin `oat`/odex, tidak berpengaruh ke fungsi.

---

## MASALAH 5: Night mode nggak bisa dipakai (SELESAI — 15 Okt 2026, 20:11)

### Gejala
Semua mode jalan (Foto 0.6/1.0/2.0, Portrait, Pro, Documents, Video) — **kecuali Night**.
Di Night, tombol shutter nggak menghasilkan apa-apa: `CAM_CaptureRequestBuilder` tetap
menjalankan jalur hardware-MFNR, lalu `wait task result failed:-110`
(`ETIMEDOUT` dari MFB) → `onCameraAbnormal: 2` → tidak ada file di DCIM.

### Kenapa Night beda
Night mengirim tag `applyMfnrEnable(true)` + `applySuperNightMfnr(true)` supaya MFB
hardware (MFBLL) yang.handle noise. Di selene blok itu **tidak ada** (lihat "MASALAH 3":
0 port MFB M4U), jadi permintaan itu selalu timeout.

### Yang DIPERBAIKAN
Bukan call site-nya, tapi **titik penulisan tag-nya** —
`com/android/camera2/compat/MiCameraCompatBaseImpl.smali`, 3 method, disisip 1 baris
`const/4 p2, …` di awal body (paksa nilai boolean, abaikan argumen pemanggil):

| Method | Nilai | Arti |
|---|---|---|
| `applyMfnr(Builder, Z)` | `p2 = 0x0` | hardware MFNR (MFB) **dimatikan** |
| `applySwMfnr(Builder, Z)` | `p2 = 0x1` | software MFNR **dinyalakan** |
| `applySuperNightMfnr(Builder, Z)` | `p2 = 0x0` | super-night MFB **dimatikan** |

Dengan begitu Night memakai pipeline software-MFNR yang sama dengan mode lain — persis
jalur yang sudah terbukti jalan di mode Photo.

Catatan: versi pertama patch Taken di `d/c/b/a5.smali` (call site hasil decompile jadx)
**tidak berefek** — log tetap `applyMfnrEnable: true`.odg-Jalur runtime-nya lewat
`d/c/b/k4.smali` (`CAM_CaptureRequestBuilder`), bukan `a5`. Patch di `a5` sudah dikembalikan
ke asli; yang dipakai hanya patch di `MiCameraCompatBaseImpl`.

### Build & deploy
```
apktool_2.11.1.jar d -r -f -o apkdec MiuiCamera.apk      # decode 8 dex -> smali (36.262 file)
# edit 3 method di smali_classes2/com/android/camera2/compat/MiCameraCompatBaseImpl.smali
apktool_2.11.1.jar b apkdec -o patched2-unsigned.apk     # rebuild
uber-apk-signer-1.3.0.jar -a patched2-unsigned.apk -o signed2   # zipalign + sign
adb push signed2/patched2-aligned-debugSigned.apk /data/local/tmp/
adb shell su -c 'cp ... /data/adb/modules/xiaomicamera/system/priv-app/MiuiCamera/MiuiCamera.apk'
adb shell su -c reboot
```

### Catatan penting
- **Signature berubah** (`CN=Android Debug`, apkSigningVersion=3). PackageManager di Android
  **menerima** perpindahan signature untuk system package: `signatures=[520f898a],
  past signatures:[]` — tanpa error, app tetap jalan normal. Data app tidak di-clear.
- `resources.arsc` & `AndroidManifest.xml` **byte-identical** setelah round-trip smali.
  Hanya `classes2.dex` yang berubah (dex di-assemble ulang, ukuran kebetulan sama).
- apktool hanya rebuild `classes2.dex` kalau smali lain tidak berubah → build ~25 detik.
- Modul sudah dipack ulang jadi **versionCode=830003**, deskripsi `[selene-fix v3 + NIGHT]`,
  APK di dalam zip = APK yang terpasang (sha256 `c2353c69…731801`).

### HASIL TEST FINAL (15 Okt 2026, 20:11)
Diuji ulang setelah modul di-repack & di-reinstall (v4, 15 Okt 20:31):

| Mode | Hasil | `-110` | `onCameraAbnormal` | applyMfnrEnable |
|---|---|---|---|---|
| Foto 1.0X | ✅ | 0 | 0 | false |
| Foto 0.6X | ✅ | 0 | 0 | false |
| Foto 2.0X | ✅ | 0 | 0 | false |
| **Night 1.0X** | ✅ | 0 | 0 | false |
| **Night 0.6X** | ✅ | 0 | 0 | false |
| **Night 2.0X** | ✅ | 0 | 0 | false |
| Portrait | ✅ | 0 | 0 | false |
| Pro | ✅ | 0 | 0 | false |
| Documents | ✅ | 0 | 0 | false |

**9/9 lulus** (termasuk Night di ketiga level zoom — `getSupportedButtonOuterZooms` =
`supernight:0.6:1.0:2.0` jadi ketiganya memang harus jalan). Foto Night = 3072×4080 (12 MP), 5.7 MB, luminansi rata-rata 35/255 dengan
detail terlihat (kursi/lantai/kabel) — bukan frame hitam.

### Mode BELUM di-test (utang untuk versi berikutnya)

Yang terverifikasi cuma 9 (lihat tabel di atas). Mode berikut **belum pernah dites** sama
sekali — sengaja ditunda, bukan karena gagal:

```
50MP · Panorama · Time-lapse · Long exposure
Slow motion · VLOG · Short film · Movie effects
Clone · Director mode · Sticker avatars
Macro (5x–10x) · Video (sebelum patch ✅, sesudah patch belum)
```

Yang paling rawan: **Long exposure** & **Panorama** — keduanya multi-frame dan kemungkinan
punya jalur MFNR sendiri, jadi bisa aja butuh patch tambahan di luar 3 method yang sekarang.

### Status konfigurasi

- `selene.json` (`isLegacyMfnrDevice:true` + `supportSwMfnr:true`) kini **opsional** — sudah
  dibuktikan bahwa APK patch jalan tanpanya (dengan `service.sh` dimatikan + folder config
  dihapus + reboot, semua mode tetap jalan dengan app-default config). File ini sekarang
  berfungsi sebagai jaring pengaman kalau suatu saat app diperbarui dan patch hilang.
- Modul zip final: `Leica-5.0-Beta-8.3-Port-Selene.zip`, `versionCode=830004`,
  APK `sha256 c2353c693a52a6f5540d08f64f4b1546291a9ea0b21a75e80f37c42c37331801`.

### P1: mode lain (16 Okt 2026) — semua aman

13 mode sisanya sudah dites (`tools/test_modes_p1.py`):

| Lulus | Long exposure · 50MP · Panorama · Sticker avatars · Slow motion ·
Time-lapse · Video · **Director mode** |
|---|---|
| Skip | VLOG · Short film (butuh unduh template dulu) |
| Butuh flow khusus | Clone (*"Cloning only works in landscape mode"*, kamera lock portrait) ·
Movie effects (wizard cinemagraph multi-langkah) |

**Temuan utama:** di **semua** mode tersebut, `-110 = 0` dan `onCameraAbnormal = 0`.
Tidak ada mode tersembunyi yang ikut kena cacat MFB, dan patch
`applyMfnr=false / applySwMfnr=true` tidak menimbulkan efek samping di mode mana pun.

Catatan: `Director mode` sempat dilaporkan gagal karena harness-nya menghitung `.jpg`,
padahal itu mode video (`.mp4`). Salah klasifikasi alat uji, bukan mode rusak.

### Rollback
```
adb shell su -c 'cp /data/local/tmp/MiuiCamera.apk.ORIG \
  /data/adb/modules/xiaomicamera/system/priv-app/MiuiCamera/MiuiCamera.apk'
adb shell su -c reboot
```
(`/data/local/tmp/MiuiCamera.apk.ORIG` = APK asli Modul 8.3, 169.314.153 byte.
`MiuiCamera.apk.V1` = patch v1 yang ternyata nggak berefek.)

### Jebakan saat develop
- `adb shell` + `subprocess(..., text=True)` **gagal decode** kalau output logcat punya byte
  non-UTF-8 (`'utf-8' codec can't decode byte 0xb8`). Semua hasil jadi string `ERR:…` →
  counter `-110`/`onCameraAbnormal` selalu 0 dan bikin kelihatan "patch nggak jalan".
  Pakai `.decode('utf-8','replace')`.
- `uiautomator dump` + `resource-id` dipakai untuk cari shutter & mode, JANGAN tap koordinat
  tetap tanpa cek `mCurrentFocus` — sempat ketemu `mCurrentFocus=NotificationShade` sehingga
  semua tap mendarat di shade dan nol log sama sekali.
- Urutan opcode: `invoke-static` = `0x6E`, tapi ada juga `invoke-static/range` = `0x7F`.
  Scanner yang cuma cari `0x6E` akan melewatkan banyak call site.
- **Tombol zoom nggak punya `resource-id`.** Di UI dump hanya `zoom_ratio_toggle_button`
  (ViewGroup, `clickable=false`, bounds `[340,1510][740,1680]`) yang ketemu; anak-anaknya
  (`0.6X zoom`, `1.0X zoom`, `2.0X zoom`, `clickable=true`) **tanpa resource-id** — slicik
  karena `uiautomator` cuma ngumpulin node yang punya rid. Harus diparse dari daftar semua
  node, dan dicocokkan `desc == "1.0X zoom"` (bukan `"1.0X"`).
  Koordinat中心: 0.6X `(415,1595)`, 1.0X `(540,1595)`, 2.0X `(665,1595)`.
  Cara cek zoom aktif: node yang terpilih dipindah ke **front** daftar, jadi
  `['2.0X zoom','0.6X zoom','1.0X zoom','2.0X zoom']` artinya 2.0X aktif.

---

## Environment / catatan teknis

- Root via KernelSU (`adb shell su -c '...'`).
- `panic_on_oops=1` — setiap oops = reboot. (Masalah 1 sudah bikin oops-nya hilang.)
- Kernel source: `/home/naidra/Projects/Kernel/android_kernel_xiaomi_mt6768-k419` (branch `PawwwNunungggg24.0`).
- Commit CMDQ fix ada di repo lokal itu (belum di-push).
- **Device: Redmi Note 10 (selene), GSI Project Infinity = Android 16** (`ro.build.version.release=16`, sdk 36, `BP4A.251205.006`), MT6769H.
- **Kernel aktif sekarang: `4.19.325-PawwwNunungggg-cip136-st20-g5b9f76bfa86b-dirty`** — sudah berisi fix CMDQ NULL-deref + fix `enable_irq` DIP + instrumen `ISP_DumpDIPReg` + `dip1 irq #`.
- **Module Leica sudah ter-install ulang bersih** (15 Okt 04:20, `ksud module install`): `/data/adb/modules/xiaomicamera`, 81 file, mount aktif, foto 2.0X berhasil disimpan.
- **`system.prop` sudah kembali ORIGINAL** (`enableAdvanceFeatures=0x3E7`) — eksperimen prop Tes A/B hilang bersama uninstall.
- `pstore` masih menyimpan oops **jadul** dari kernel lama `g282da32602fa` (scheduler `adios`, `remove_request` NULL-deref). Kernel sekarang: 0 oops, scheduler `mmcblk0` = **mq-deadline** (io-guard aktif).
- **adb sekarang USB** (`-s 65cb03c00702`). WiFi `192.168.127.57:5555` mati setelah reboot (`adb tcpip` tidak persisten). Kabel USB sempat detach ~4 menit (04:46–04:50) tanpa reboot — cek `uptime` sebelum menyimpulkan device restart.
- **Selalu verifikasi `dumpsys window | grep mCurrentFocus` SEBELUM tap apa pun** — beberapa kali layar sedang dipakai aplikasi lain (Instagram, Google Lens, YouTube Music) dan tap-nya mendarat di sana.
- Register DIP yang dipakai instrumen (`camera_isp.c`): `0x000=CTL_START`, `0x030=_INT_STATUS`, `0x034=_CQ_INT_STATUS`, `0x038=_CQ_LD_INT_STATUS`, `0x040=CTL_INT_STATUSX`, `0x044/048/04C=CTL_CQ_INT/2/3_STATUSX`, `0x104+n*12=CQ n ctl`, `0x108+n*12=CQ n base`, `0x10C+n*12=CQ n size`, `0x204=tdri`, `0x400=imgi`.
- Loop pilih CQ di driver: `for (cmdqidx=0..31) if (ctrl_start & (1<<cmdqidx)) g_cmdqaddr = RD32(0x108 + cmdqidx*12)` (`camera_isp.c:3269`).
- Background capture: mulai dengan `setsid nohup ... &`, matikan berdasarkan PID. **Jangan** `pkill -f "dmesg -w"`. `dmesg -w` selalu mencetak seluruh ring buffer dulu (itulah kenapa event lama muncul di file "live".
