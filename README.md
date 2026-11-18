# Camellia OrangeFox recovery tree — Linux 6.6

Repository: https://github.com/aLpHa-Git-69/android_device_xiaomi_camellia_k66

This tree ports the supplied **OrangeFox R12.0_1 / fox_12.1** device configuration
to the device-tested Camellia 6.6 kernel. Place it at `device/xiaomi/camellia`
inside a synced OrangeFox `fox_12.1` checkout.

## Recovery layouts

The selected default is **experimental `vendor-boot-v3`**:

- `boot.img`: kernel and generic first-stage ramdisk, boot header v3.
- `vendor_boot.img`: recovery/vendor ramdisk, the matching modules and DTB,
  vendor-boot header v3.
- The current working boot-v2 image does **not** use this vendor-boot layout;
  migrating requires the **matching image pair**.
- This v3 layout uses a complete vendor ramdisk, not v4 recovery fragments.
  The OrangeFox v4-fragment ZIP installer is disabled for this profile.

Both physical `vendor_boot` slots were found to be 64 MiB with empty headers.
The bootloader contains vendor-boot decoder code. These facts support bring-up,
but **on-device vendor-boot migration is not yet validated**.

The first image-pair device test stopped in LK with `vendor_boot image is NULL`
and `invalid vendorboot image header v3`; the bootloader switched back to B.
The stock slot-A root vbmeta chains the stock boot key and has no vendor-boot
descriptor. `tools/make-test-vbmeta.py` prepares a separate **slot-A-only test**
root vbmeta that preserves system/vendor/mi_ext descriptors, verification flags
and rollback index, updates the boot-chain key to the compiled image's key,
and adds the exact vendor-boot hash descriptor. It uses an AOSP test signing
key; it is not stock-signed and this follow-up device test is unvalidated.

The **boot-v2 fallback** matches the proven kernel boot layout and stores the
recovery ramdisk in the boot partition:

```sh
python3 tools/select-layout.py boot-v2
python3 tools/validate-tree.py
```

To select the requested vendor-boot profile:

```sh
python3 tools/select-layout.py vendor-boot-v3
python3 tools/validate-tree.py
```

## Kernel and early module loading

Included prebuilts are pinned to kernel source commit
`907092a3926ada9fe54b90e66e82632519251c84`:

- Kernel `6.6.30-4k-g907092a3926a-dirty` — boots and speaker output works in Android.
- The merged Camellia DTB.
- All **272** matching modules, including UFS, pinctrl, display, Mali GPU,
  touchscreen, USB and TEE drivers.
- `modules.load` and `modules.load.recovery` in `/lib/modules`, for Android
  first-stage init to load before partition mounting.
- Matching touch firmware and the original MediaTek recovery HAL configuration.

`prebuilt/kernel66.json` records source provenance and SHA-256 hashes.
`tools/validate-tree.py` checks the hashes, ELF module versions and boot layout.

To refresh the same pinned payload from the successful kernel build:

```sh
gh run download 43736910427 --repo aLpHa-Git-69/kernel_xiaomi_mt6833_66 \
  --name complete-kernel-sukisu --dir kernel66-payload
python3 tools/import-kernel66.py kernel66-payload
```

## Source build

### Fast ramdisk repack

`.github/workflows/manual-repack.yaml` reuses the compiled boot-v3 image and
manually adds the supplied OrangeFox ramdisk plus this tree's matching modules
to `vendor_boot.img`. It does not repeat the OrangeFox source sync/compilation.
The image manifest explicitly records this as a donor-ramdisk manual repack.
Both image contents and the regenerated vendor-boot AVB hash footer are checked.

```sh
python3 tools/import-donor-ramdisk.py /path/to/OrangeFox-R12.0_1-Unofficial-camellia.zip
python3 tools/manual-repack.py /path/to/compiled-images dist --avbtool /path/to/avbtool.py
python3 tools/check-built-images.py dist --assembly manual-repack
```

### Full source compilation

The full-source header-v3 job currently passes compilation but produces an
empty vendor ramdisk in its automatic packaging path. Its content check rejects
that output. Use the fast manual-repack job for the next device test; its
manifest records the supplied OrangeFox userspace donor explicitly.

Use a Linux build host with enough space for OrangeFox `fox_12.1` (about 45 GiB
for the synced source, plus build output). Sync with OrangeFox's official script:

```sh
git clone https://gitlab.com/OrangeFox/sync.git
bash sync/orangefox_sync.sh --branch 12.1 --path /absolute/path/to/OrangeFox
# Place this tree at /absolute/path/to/OrangeFox/device/xiaomi/camellia
bash device/xiaomi/camellia/tools/build-recovery.sh /absolute/path/to/OrangeFox
```

The vendor-boot profile builds `adbd`, `bootimage` and `vendorbootimage`.
The boot-v2 profile builds `adbd` and `bootimage`. A GitHub Actions build workflow
is included, with the same two selectable layouts and no automatic release.

## Donor assembly check

`tools/create-test-images.py` can assemble format-checked test images using the
supplied OrangeFox ZIP's userspace and this tree's kernel/modules. It requires
AOSP `mkbootimg.py` and a host-compatible Magiskboot (the supplied ARM64 binary
works in Termux). This is **not a full OrangeFox source compilation**, and it
does not establish recovery boot, touch, MTP or decryption functionality.
These donor-assembled test images have no added AVB signature/footer; use the
source-build workflow for the normal AVB-enabled image production path.

For device bring-up, keep the known-working boot image available. Test the
matching boot/vendor-boot pair together on the intended slot; a standalone
vendor-boot flash cannot migrate the current boot-v2 boot chain. Collect
`/tmp/recovery.log`, logcat and dmesg after a recovery test.

## Provenance

- Device-tree base: `PallzNtDv/fox-twrp-device-camellia`, branch `fox_12.1`,
  commit `d75147f08bad1fcd8b0351e2de4129640cdd7425`.
- Donor ZIP SHA-256:
`599d4e395b61bd524811f3afc988a47579ed115ed8cd2db2eca7f9a9d2c5a6b9`.
- Linux kernel/modules: GPL-2.0; source is linked in `prebuilt/kernel66.json`.
- Original recovery configuration credits: OrangeFox, TeamWin, cristidclxvi,
  cd-Crypton, that1 and azwhikaru. Original file license notices are retained.

## Export the tree

```sh
python3 tools/validate-tree.py
python3 tools/export-tree.py camellia-orangefox-kernel66-tree.zip
```

The archive contains `device/xiaomi/camellia/` with all configuration and
prebuilt files; `.git` and temporary image outputs are excluded.
