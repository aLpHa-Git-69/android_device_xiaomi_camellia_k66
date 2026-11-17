#!/usr/bin/env python3
"""Assemble format-checked test images from the supplied OrangeFox userspace.

This is a donor-ramdisk assembly check, not a full OrangeFox source build.
"""
import argparse
import gzip
import hashlib
import json
import pathlib
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import zipfile

from kernel66 import verify_tree

DONOR_SHA256 = '599d4e395b61bd524811f3afc988a47579ed115ed8cd2db2eca7f9a9d2c5a6b9'
COMMAND_LINE = ('bootopt=64S3,32N2,64N2 androidboot.init_fatal_reboot_target=recovery '
                'androidboot.selinux=permissive firmware_class.path=/vendor/firmware '
                'log_buf_len=16M buildvariant=eng')


def run(args, cwd):
    result = subprocess.run([str(item) for item in args], cwd=cwd,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode:
        print(result.stdout, end='')
        print(result.stderr, end='', file=sys.stderr)
        raise subprocess.CalledProcessError(result.returncode, args)


def cpio_file(name, data, mode, inode):
    encoded = name.encode() + b'\0'
    fields = (inode, mode, 0, 0, 1, 0, len(data), 0, 0, 0, 0, len(encoded), 0)
    value = b'070701' + b''.join(f'{field:08x}'.encode() for field in fields) + encoded
    value += b'\0' * (-len(value) % 4)
    value += data + b'\0' * (-len(data) % 4)
    return value


def generic_ramdisk(init):
    raw = cpio_file('init', init, stat.S_IFREG | 0o750, 1)
    raw += cpio_file('TRAILER!!!', b'', 0, 2)
    raw += b'\0' * (-len(raw) % 512)
    return gzip.compress(raw, compresslevel=9, mtime=0)


def verify_vendor_pair(boot, vendor, tree):
    data = boot.read_bytes()
    if data[:8] != b'ANDROID!' or struct.unpack_from('<I', data, 40)[0] != 3:
        raise ValueError('invalid converted boot-v3 header')
    size = struct.unpack_from('<I', data, 8)[0]
    if data[4096:4096 + size] != (tree / 'prebuilt/kernel').read_bytes():
        raise ValueError('converted boot kernel mismatch')
    data = vendor.read_bytes()
    if data[:8] != b'VNDRBOOT' or struct.unpack_from('<I', data, 8)[0] != 3:
        raise ValueError('invalid vendor-boot-v3 header')
    page, kernel_address, ramdisk_address, size = struct.unpack_from('<4I', data, 12)
    header_size, dtb_size, dtb_address = struct.unpack_from('<IIQ', data, 2096)
    if (page, kernel_address, ramdisk_address, header_size, dtb_address) != (
            4096, 0x40000000, 0x51100000, 2112, 0x47c80000):
        raise ValueError('vendor_boot geometry mismatch')
    position = 4096 + (size + page - 1) // page * page
    if data[position:position + dtb_size] != (tree / 'prebuilt/dtb.img').read_bytes():
        raise ValueError('vendor_boot DTB mismatch')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('donor_zip', type=pathlib.Path)
    parser.add_argument('output', type=pathlib.Path)
    parser.add_argument('--mkbootimg', required=True, type=pathlib.Path,
                        help='host-compatible AOSP mkbootimg.py or mkbootimg binary')
    parser.add_argument('--magiskboot', type=pathlib.Path,
                        help='host-compatible binary; default uses the donor ARM64 binary')
    parser.add_argument('--temporary-directory', type=pathlib.Path)
    parser.add_argument('--layout', choices=('vendor-boot-v3', 'boot-v2'), default='vendor-boot-v3')
    args = parser.parse_args()
    tree = pathlib.Path(__file__).resolve().parents[1]
    manifest = verify_tree(tree)
    if hashlib.sha256(args.donor_zip.read_bytes()).hexdigest() != DONOR_SHA256:
        raise ValueError('donor is not the supplied OrangeFox R12.0_1 archive')
    args.output.mkdir(parents=True, exist_ok=True)
    temporary = args.temporary_directory or args.output
    with tempfile.TemporaryDirectory(dir=temporary) as directory:
        work = pathlib.Path(directory)
        with zipfile.ZipFile(args.donor_zip) as archive:
            archive.extract('recovery.img', work)
            archive.extract('magiskboot', work)
        magisk = args.magiskboot.resolve() if args.magiskboot else work / 'magiskboot'
        magisk.chmod(0o755)
        run([magisk, 'unpack', '-h', work / 'recovery.img'], work)
        ramdisk = work / 'ramdisk.cpio'
        run([magisk, 'cpio', ramdisk, 'extract system/bin/init ' + str(work / 'first-stage-init')], work)
        commands = ['rm -r lib/modules']
        root = tree / 'recovery/root'
        directories = sorted((p for p in root.rglob('*') if p.is_dir()),
                             key=lambda p: (len(p.relative_to(root).parts), str(p)))
        for path in directories:
            commands.append('mkdir 0755 ' + path.relative_to(root).as_posix())
        for path in sorted(root.rglob('*')):
            if path.is_file():
                name = path.relative_to(root).as_posix()
                mode = 0o755 if name.startswith(('vendor/bin/', 'system/bin/')) else path.stat().st_mode & 0o777
                commands.append(f'add {mode:04o} {name} {path}')
        run([magisk, 'cpio', ramdisk, *commands], work)
        recovery_ramdisk = work / 'recovery-ramdisk.gz'
        recovery_ramdisk.write_bytes(gzip.compress(ramdisk.read_bytes(), compresslevel=9, mtime=0))
        generic = work / 'generic-ramdisk.gz'
        generic.write_bytes(generic_ramdisk((work / 'first-stage-init').read_bytes()))
        tool = ([sys.executable, str(args.mkbootimg.resolve())]
                if args.mkbootimg.suffix == '.py' else [str(args.mkbootimg.resolve())])
        common = ['--kernel', tree / 'prebuilt/kernel', '--dtb', tree / 'prebuilt/dtb.img',
                  '--base', '0', '--kernel_offset', '0x40000000',
                  '--ramdisk_offset', '0x51100000', '--tags_offset', '0x47c80000',
                  '--dtb_offset', '0x47c80000', '--os_version', '99.87.36',
                  '--os_patch_level', '2127-12']
        if args.layout == 'vendor-boot-v3':
            boot = args.output.resolve() / 'boot-v3-kernel66.img'
            vendor = args.output.resolve() / 'vendor_boot-v3-kernel66.img'
            run([*tool, *common, '--header_version', '3', '--pagesize', '4096',
                 '--ramdisk', generic, '--vendor_ramdisk', recovery_ramdisk,
                 '--vendor_cmdline', COMMAND_LINE, '--output', boot, '--vendor_boot', vendor], work)
            verify_vendor_pair(boot, vendor, tree)
            images = [boot, vendor]
        else:
            boot = args.output.resolve() / 'OrangeFox-kernel66-boot-v2.img'
            run([*tool, *common, '--header_version', '2', '--pagesize', '2048',
                 '--ramdisk', recovery_ramdisk, '--cmdline', COMMAND_LINE, '--output', boot], work)
            images = [boot]
        for image in images:
            if image.stat().st_size > 64 * 1024 * 1024:
                raise ValueError('image exceeds its 64 MiB partition: ' + image.name)
            digest = hashlib.sha256(image.read_bytes()).hexdigest()
            image.with_suffix('.img.sha256').write_text(digest + '  ' + image.name + '\n')
        report = {
            'layout': args.layout, 'kernel_release': manifest['build_info']['kernel_release'],
            'module_count': manifest['module_count'], 'donor_sha256': DONOR_SHA256,
            'assembly': 'donor userspace plus device-tree files, not a full source build',
            'device_validated': False,
            'images': {image.name: image.stat().st_size for image in images},
        }
        (args.output / 'test-image-manifest.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
