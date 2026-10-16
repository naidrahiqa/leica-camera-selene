#
# Copyright (C) 2026 naidrahiqa
#
# SPDX-License-Identifier: Apache-2.0
#
# Leica Camera 5.0 for Redmi Note 10 (selene / MT6768).
#
# Inherit from device.mk:
#     $(call inherit-product, vendor/xiaomi/leica_camera/config.mk)
#
# Prerequisites in the device tree:
#   1. Add the repo to the manifest (repo link or local path).
#   2. Make sure sepolicy_vndr.mk of the device includes a directory that
#      picks up sepolicy/ from this repo — see "SELinux" below.
#

VENDOR_LEICA_CAMERA := vendor/xiaomi/leica_camera

PRODUCT_SOONG_NAMESPACES += \
    $(VENDOR_LEICA_CAMERA)

# ── native libraries ─────────────────────────────────────────────────────────
# They sit in priv-app/<pkg>/lib/arm64/, the same layout the Magix/KernelSU
# module uses. That path is still supported for apps installed under /system.
PRODUCT_COPY_FILES += \
    $(call find-copy-subdir-files,*,$(VENDOR_LEICA_CAMERA)/proprietary/system/priv-app/MiuiCameraLeica/lib,$(TARGET_COPY_OUT_SYSTEM)/priv-app/MiuiCameraLeica/lib) \
    $(call find-copy-subdir-files,*,$(VENDOR_LEICA_CAMERA)/proprietary/system/priv-app/MiuiExtraPhoto/lib,$(TARGET_COPY_OUT_SYSTEM)/priv-app/MiuiExtraPhoto/lib)

# ── permissions ─────────────────────────────────────────────────────────────
PRODUCT_COPY_FILES += \
    $(VENDOR_LEICA_CAMERA)/proprietary/system/etc/permissions/privapp-permissions-miuicamera.xml:$(TARGET_COPY_OUT_SYSTEM)/etc/permissions/privapp-permissions-miuicamera.xml

# Android 14+ hidden API whitelist. Without it the camera crashes when it
# calls internal APIs that the platform has hidden.
PRODUCT_COPY_FILES += \
    $(VENDOR_LEICA_CAMERA)/proprietary/system/etc/sysconfig/miuicamera-hiddenapi-package-whitelist.xml:$(TARGET_COPY_OUT_SYSTEM)/etc/sysconfig/miuicamera-hiddenapi-package-whitelist.xml

# Scene detection config, read by the MediaTek vendor tag manager.
PRODUCT_COPY_FILES += \
    $(VENDOR_LEICA_CAMERA)/proprietary/sceneDetection.xml:$(TARGET_COPY_OUT_VENDOR)/etc/camera/sceneDetection.xml

# ── packages ────────────────────────────────────────────────────────────────
PRODUCT_PACKAGES += \
    MiuiCameraLeica \
    MiuiExtraPhoto \
    MiuiScanner

# ── properties ──────────────────────────────────────────────────────────────
# Translated from the KernelSU module's system.prop.
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

# NOTE: the module shipped `ro.control_privapp_permissions=log` as a bootloop
# workaround, because a module can fail to mount. That must NOT be copied
# here — in a ROM it has to stay `enforce`. The allowlist above is complete,
# so there is no reason to weaken enforcement.

# ── SELinux ─────────────────────────────────────────────────────────────────
# The device tree has to pick up sepolicy/ from this repo, e.g. in
# BoardConfig.mk next to its existing sepolicy include:
#
#     BOARD_VENDOR_SEPOLICY_DIRS += \
#         vendor/xiaomi/leica_camera/sepolicy
#
# sepolicy/leica-camera.te is intentionally minimal and is NOT verified on
# device. Most of the rules already exist in device/mediatek/sepolicy_vndr.
# If the build fails with neverallow or duplicate-declaration errors, delete
# the .te first — the MediaTek vendor policy is very likely sufficient.
# If the ROM boots but the camera cannot reach its vendor blobs, inspect:
#     adb logcat -b all | grep -i avc
# The original KernelSU-format rules are kept for reference in
# sepolicy/leica-camera.rule.orig.