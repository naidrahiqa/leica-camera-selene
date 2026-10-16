#
# Copyright (C) 2026 selene-aosp
#
# SPDX-License-Identifier: Apache-2.0
#
# Leica Camera 5.0 untuk selene / MT6768.
#
# Dipakai dari device.mk:
#     $(call inherit-product, prebuilt/leica-camera/camera.mk)
#

LEICA_CAMERA_PATH := prebuilt/leica-camera

# ── APK ────────────────────────────────────────────────────────────────────
# Modul didefinisikan di prebuilt/leica-camera/Android.bp sebagai
# android_app_import, jadi cukup sebutin lewat PRODUCT_PACKAGES.
PRODUCT_PACKAGES += \
    MiuiCamera.apk \
    MiuiExtraPhoto.apk \
    MiuiScanner.apk

# ── native library ─────────────────────────────────────────────────────────
# .so ditaruh di system/priv-app/<pkg>/lib/arm64/ — konvensi yang dipakai
# modul KernelSU, dan tetap didukung untuk app di /system.
# Karena 47 file, pakai find-copy-subdir-files daripada menulis satu per satu.
PRODUCT_COPY_FILES += \
    $(call find-copy-subdir-files,*,$(LEICA_CAMERA_PATH)/lib-MiuiCamera,$(TARGET_COPY_OUT_SYSTEM)/priv-app/MiuiCamera/lib/arm64) \
    $(call find-copy-subdir-files,*,$(LEICA_CAMERA_PATH)/lib-MiuiExtraPhoto,$(TARGET_COPY_OUT_SYSTEM)/priv-app/MiuiExtraPhoto/lib/arm64)

# ── permission & feature XML ───────────────────────────────────────────────
# privapp allowlist. Tetap dipasang walau APK signed platform key, sebagai
# jaring pengaman kalau nanti ada yang ganti ke signature asli.
PRODUCT_COPY_FILES += \
    $(LEICA_CAMERA_PATH)/permissions/privapp-permissions-miuicamera.xml:$(TARGET_COPY_OUT_SYSTEM)/etc/permissions/privapp-permissions-miuicamera.xml

# Android 14+ hidden API whitelist — tanpa ini kamera akan crash saat memanggil
# API internal yang sudah di-hide.
PRODUCT_COPY_FILES += \
    $(LEICA_CAMERA_PATH)/sysconfig/miuicamera-hiddenapi-package-whitelist.xml:$(TARGET_COPY_OUT_SYSTEM)/etc/sysconfig/miuicamera-hiddenapi-package-whitelist.xml

# Scene detection config (dipakai Vendor Tag Manager MTK).
PRODUCT_COPY_FILES += \
    $(LEICA_CAMERA_PATH)/sceneDetection.xml:$(TARGET_COPY_OUT_VENDOR)/etc/camera/sceneDetection.xml

# ── properties ─────────────────────────────────────────────────────────────
# Diterjemahkan dari system.prop modul KernelSU.
PRODUCT_VENDOR_PROPERTIES += \
    persist.vendor.camera.enableAdvanceFeatures=0x3E7 \
    persist.vendor.camera.multicam=TRUE \
    persist.vendor.camera.multicam.fpsmatch=TRUE \
    persist.vendor.camera.multicam.framesync=1 \
    persist.vendor.camera.multicam.hwsync=TRUE \
    persist.vendor.camera.privapp.list=com.android.camera \
    persist.vendor.camera.picturesize.limit.enable=false

PRODUCT_SYSTEM_PROPERTIES += \
    ro.boot.camera.config=_pro \
    ro.com.google.lens.oem_camera_package=com.android.camera

# CATATAN: modul KernelSU menyertakan
#     ro.control_privapp_permissions=log
# sebagai pancingan anti-bootloop. JANGAN ikut di sini — pada ROM normal
# nilainya harus tetap `enforce`. Allowlist di atas sudah benar, jadi tidak
# perlu lowering keamanan hanya untuk booted.

# ── SELinux ────────────────────────────────────────────────────────────────
# Diterjemahkan dari sepolicy.rule modul (format KernelSU) ke .te yang valid
# untuk device/mediatek/sepolicy_vndr.
BOARD_VENDOR_SEPOLICY_DIRS += \
    prebuilt/leica-camera/sepolicy \
    $(DEVICE_PATH)/sepolicy

# Peringatan: kalau build gagal dengan "neverallow" atau bootloop dengan
# avc: denied, sepolicy ini kandidat pertamanya. Lihat sepolicy/README.md.