#!/usr/bin/env python3
"""Check the 6.6 prebuilts and essential recovery build configuration."""
import pathlib

from kernel66 import verify_tree

tree = pathlib.Path(__file__).resolve().parents[1]
verify_tree(tree)
board = (tree / 'BoardConfig.mk').read_text() + (tree / 'profiles/common.mk').read_text()
selection = (tree / 'recovery-layout.mk').read_text()
layout = 'vendor-boot-v3' if 'vendor-boot-v3.mk' in selection else 'boot-v2'
board += (tree / 'profiles' / (layout + '.mk')).read_text()
for setting in (
    'BOARD_KERNEL_BASE := 0x00000000',
    'BOARD_KERNEL_OFFSET := 0x40000000',
    'BOARD_MKBOOTIMG_ARGS := --kernel_offset $(BOARD_KERNEL_OFFSET)',
    'BOARD_RAMDISK_OFFSET := 0x51100000',
    'BOARD_DTB_OFFSET := 0x47c80000',
    'BOARD_BOOTIMAGE_PARTITION_SIZE := 67108864',
):
    if setting not in board:
        raise ValueError('missing boot configuration: ' + setting)
if layout == 'vendor-boot-v3':
    for setting in ('BOARD_BOOTIMG_HEADER_VERSION := 3',
                    'BOARD_VENDOR_BOOTIMAGE_PARTITION_SIZE := 67108864',
                    'BOARD_MOVE_RECOVERY_RESOURCES_TO_VENDOR_BOOT := true'):
        if setting not in board:
            raise ValueError('missing vendor_boot configuration: ' + setting)
else:
    if 'BOARD_USES_RECOVERY_AS_BOOT := true' not in board or 'BOARD_BOOTIMG_HEADER_VERSION := 2' not in board:
        raise ValueError('invalid boot-v2 fallback configuration')
if 'recovery/root,recovery/root' not in (tree / 'device.mk').read_text():
    raise ValueError('device ramdisk is not included in the product')
print('Boot layout and ramdisk copy configuration verified:', layout)
