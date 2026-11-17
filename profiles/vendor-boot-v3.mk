# SPDX-License-Identifier: Apache-2.0
# Experimental: requires a matching boot-v3 image, not the existing boot-v2 image.
CAMELLIA_RECOVERY_LAYOUT := vendor-boot-v3
BOARD_USES_RECOVERY_AS_BOOT := false
BOARD_BOOTIMG_HEADER_VERSION := 3
BOARD_KERNEL_PAGESIZE := 4096
BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE := 67108864
BOARD_USES_GENERIC_KERNEL_IMAGE := true
BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT := true
# Header v3 uses a complete vendor ramdisk, not header-v4 recovery fragments.
BOARD_INCLUDE_RECOVERY_RAMDISK_IN_VENDOR_BOOT := false
include $(DEVICE_PATH)/profiles/common.mk
