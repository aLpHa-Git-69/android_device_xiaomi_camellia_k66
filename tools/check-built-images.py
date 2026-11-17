#!/usr/bin/env python3
"""Check compiled image headers and require the full recovery/module contents."""
import argparse
import gzip
import hashlib
import json
import pathlib
import struct

from kernel66 import MODULE_COUNT, sha256, verify_tree


def cpio_entries(data):
    position = 0
    result = {}
    while position + 110 <= len(data):
        # Linux initramfs supports multiple padded cpio/gzip members.
        while position < len(data) and data[position] == 0:
            position += 1
        if position + 110 > len(data):
            break
        header = data[position:position + 110]
        if header[:6] not in (b'070701', b'070702'):
            raise ValueError('invalid recovery cpio header')
        size = int(header[54:62], 16)
        namesize = int(header[94:102], 16)
        name = data[position + 110:position + 110 + namesize - 1].decode()
        start = (position + 110 + namesize + 3) // 4 * 4
        if start + size > len(data):
            raise ValueError('truncated recovery cpio entry')
        position = (start + size + 3) // 4 * 4
        if name == 'TRAILER!!!':
            continue
        result[name.removeprefix('./')] = data[start:start + size]
    return result


def recovery_contents(ramdisk, tree):
    if len(ramdisk) < 1024 * 1024:
        raise ValueError('recovery ramdisk is empty or too small')
    entries = cpio_entries(gzip.decompress(ramdisk))
    if not entries.get('system/bin/recovery'):
        raise ValueError('compiled image does not contain the recovery binary')
    expected_load = (tree / 'recovery/root/lib/modules/modules.load.recovery').read_bytes()
    if entries.get('lib/modules/modules.load.recovery') != expected_load:
        raise ValueError('compiled image does not contain the recovery module load list')
    modules = {name: data for name, data in entries.items()
               if name.startswith('lib/modules/') and name.endswith('.ko')}
    if len(modules) != MODULE_COUNT:
        raise ValueError(f'compiled image has {len(modules)} modules, expected {MODULE_COUNT}')
    for name, data in modules.items():
        if hashlib.sha256(data).hexdigest() != sha256(tree / 'recovery/root' / name):
            raise ValueError('compiled module differs from the verified prebuilt: ' + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image_directory', type=pathlib.Path)
    parser.add_argument('--assembly', choices=('source-build', 'manual-repack'), default='source-build')
    args = parser.parse_args()
    tree = pathlib.Path(__file__).resolve().parents[1]
    manifest = verify_tree(tree)
    directory = args.image_directory.resolve()
    boot = directory / 'boot.img'
    data = boot.read_bytes()
    if len(data) > 64 * 1024 * 1024 or data[:8] != b'ANDROID!':
        raise ValueError('invalid boot image or partition size')
    version = struct.unpack_from('<I', data, 40)[0]
    expected_kernel = (tree / 'prebuilt/kernel').read_bytes()
    kernel_size = struct.unpack_from('<I', data, 8)[0]
    if version == 3:
        if data[4096:4096 + kernel_size] != expected_kernel:
            raise ValueError('boot-v3 kernel is not the verified 6.6 prebuilt')
        vendor = directory / 'vendor_boot.img'
        contents = vendor.read_bytes()
        if len(contents) > 64 * 1024 * 1024 or contents[:8] != b'VNDRBOOT':
            raise ValueError('invalid vendor_boot image or partition size')
        if struct.unpack_from('<I', contents, 8)[0] != 3:
            raise ValueError('expected vendor-boot header v3')
        page, kernel_address, ramdisk_address, size = struct.unpack_from('<4I', contents, 12)
        header_size, dtb_size, dtb_address = struct.unpack_from('<IIQ', contents, 2096)
        if (page, kernel_address, ramdisk_address, header_size, dtb_address) != (
                4096, 0x40000000, 0x51100000, 2112, 0x47c80000):
            raise ValueError('vendor_boot load addresses or header geometry mismatch')
        recovery_contents(contents[4096:4096 + size], tree)
        position = 4096 + (size + page - 1) // page * page
        if contents[position:position + dtb_size] != (tree / 'prebuilt/dtb.img').read_bytes():
            raise ValueError('vendor_boot DTB mismatch')
        images = [boot, vendor]
    elif version == 2:
        page = struct.unpack_from('<I', data, 36)[0]
        size = struct.unpack_from('<I', data, 16)[0]
        if page != 2048 or data[page:page + kernel_size] != expected_kernel:
            raise ValueError('boot-v2 kernel or page size mismatch')
        position = page + (kernel_size + page - 1) // page * page
        recovery_contents(data[position:position + size], tree)
        images = [boot]
    else:
        raise ValueError('unsupported compiled boot header version')
    report = {
        'source_build': args.assembly == 'source-build',
        'assembly': args.assembly,
        'device_validated': False,
        'kernel_release': manifest['build_info']['kernel_release'],
        'module_count': MODULE_COUNT,
        'boot_header_version': version,
        'images': {image.name: {'size': image.stat().st_size, 'sha256': sha256(image)}
                   for image in images},
    }
    for image in images:
        image.with_suffix('.img.sha256').write_text(sha256(image) + '  ' + image.name + '\n')
    (directory / 'recovery-build-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
