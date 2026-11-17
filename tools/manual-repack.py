#!/usr/bin/env python3
"""Reuse a compiled boot-v3 image and manually populate vendor_boot's ramdisk."""
import argparse
import gzip
import hashlib
import json
import os
import pathlib
import shutil
import stat
import struct
import subprocess
import sys

from kernel66 import sha256, verify_tree


def cpio_entry(name, content, mode, inode):
    encoded = name.encode() + b'\0'
    fields = (inode, mode, 0, 0, 2 if stat.S_ISDIR(mode) else 1,
              0, len(content), 0, 0, 0, 0, len(encoded), 0)
    value = b'070701' + b''.join(f'{field:08x}'.encode() for field in fields) + encoded
    value += b'\0' * (-len(value) % 4)
    value += content + b'\0' * (-len(content) % 4)
    return value


def overlay_ramdisk(root):
    result = bytearray()
    inode = 1
    paths = sorted(root.rglob('*'), key=lambda p: (len(p.relative_to(root).parts), str(p)))
    for path in paths:
        name = path.relative_to(root).as_posix()
        if path.is_symlink():
            mode, content = stat.S_IFLNK | 0o777, os.readlink(path).encode()
        elif path.is_dir():
            mode, content = stat.S_IFDIR | 0o755, b''
        elif path.is_file():
            permissions = 0o755 if name.startswith(('vendor/bin/', 'system/bin/')) else path.stat().st_mode & 0o777
            mode, content = stat.S_IFREG | permissions, path.read_bytes()
        else:
            continue
        result.extend(cpio_entry(name, content, mode, inode))
        inode += 1
    result.extend(cpio_entry('TRAILER!!!', b'', 0, inode))
    result.extend(b'\0' * (-len(result) % 512))
    return gzip.compress(result, compresslevel=9, mtime=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('compiled_images', type=pathlib.Path)
    parser.add_argument('output', type=pathlib.Path)
    parser.add_argument('--avbtool', required=True, type=pathlib.Path)
    args = parser.parse_args()
    tree = pathlib.Path(__file__).resolve().parents[1]
    manifest = verify_tree(tree)
    donor = (tree / 'prebuilt/donor-recovery.cpio.gz').read_bytes()
    info = json.loads((tree / 'prebuilt/donor-recovery.json').read_text())
    if hashlib.sha256(donor).hexdigest() != info['ramdisk_sha256']:
        raise ValueError('donor ramdisk checksum mismatch')
    boot = args.compiled_images / 'boot.img'
    data = boot.read_bytes()
    if data[:8] != b'ANDROID!' or struct.unpack_from('<I', data, 40)[0] != 3:
        raise ValueError('a compiled boot-header-v3 image is required')
    size = struct.unpack_from('<I', data, 8)[0]
    if data[4096:4096 + size] != (tree / 'prebuilt/kernel').read_bytes():
        raise ValueError('compiled boot image uses a different kernel')
    subprocess.run([sys.executable, str(args.avbtool.resolve()), 'verify_image',
                    '--image', str(boot.resolve())], check=True)
    reference = (args.compiled_images / 'vendor_boot.img').read_bytes()
    if reference[:8] != b'VNDRBOOT' or struct.unpack_from('<II', reference, 8) != (3, 4096):
        raise ValueError('expected the matching vendor-boot-v3 reference')
    ramdisk = donor + overlay_ramdisk(tree / 'recovery/root')
    dtb = (tree / 'prebuilt/dtb.img').read_bytes()
    header = bytearray(reference[:4096])
    struct.pack_into('<I', header, 24, len(ramdisk))
    struct.pack_into('<I', header, 2100, len(dtb))
    image = header + ramdisk + b'\0' * (-len(ramdisk) % 4096)
    image += dtb + b'\0' * (-len(dtb) % 4096)
    if len(image) > 64 * 1024 * 1024 - 65536:
        raise ValueError('vendor_boot payload is too large for the partition/footer')
    args.output.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(boot, args.output / 'boot.img')
    vendor = args.output / 'vendor_boot.img'
    vendor.write_bytes(image)
    salt = hashlib.sha256(manifest['build_info']['source_commit'].encode()).hexdigest()
    subprocess.run([sys.executable, str(args.avbtool.resolve()), 'add_hash_footer',
                    '--image', str(vendor.resolve()), '--partition_name', 'vendor_boot',
                    '--partition_size', str(64 * 1024 * 1024), '--algorithm', 'NONE',
                    '--salt', salt], check=True)
    subprocess.run([sys.executable, str(args.avbtool.resolve()), 'verify_image',
                    '--image', str(vendor.resolve())], check=True)
    report = {
        'assembly': 'manual-repack',
        'boot_reused_byte_identical': sha256(args.output / 'boot.img') == sha256(boot),
        'kernel_release': manifest['build_info']['kernel_release'],
        'module_count': manifest['module_count'],
        'donor_ramdisk_sha256': info['ramdisk_sha256'],
        'vendor_boot_payload_size': len(image),
        'device_validated': False,
    }
    (args.output / 'manual-repack-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
