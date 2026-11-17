#!/usr/bin/env python3
"""Validate the device-tested Camellia 6.6 kernel and its recovery modules."""
import gzip
import hashlib
import json
import pathlib
import struct

SOURCE_COMMIT = '907092a3926ada9fe54b90e66e82632519251c84'
MODULE_COUNT = 272
CRITICAL_MODULES = {
    'clk-mt6833.ko', 'clk-mt6833-audiosys.ko', 'pinctrl-mt6833.ko',
    'pinctrl-mtk-v2.ko', 'mtk-scpsys-mt6833.ko', 'mtk-pmic-wrap.ko',
    'mt6397.ko', 'mt6359p-regulator.ko', 'i2c-mt65xx.ko',
    'ufs-mediatek-mod.ko', 'mtk-mmc.ko', 'mtk_iommu.ko',
    'mediatek-drm.ko', 'mali_kbase_mt6833_r49.ko',
    'camellia-ft8722-ts.ko', 'camellia-nt36672c-ts.ko',
    'panel-ft8722-tianma-fhdp-dsi-vdo-90hz.ko',
    'panel-nt36672c-tianma-fhdp-dsi-vdo-90hz.ko',
    'mt635x-auxadc.ko', 'pwm-mtk-disp.ko', 'mtk-dvfsrc-helper.ko',
    'musb_hdrc.ko', 'musb_main.ko', 'mtu3.ko', 'xhci-mtk-hcd-v2.ko',
    'camellia_aw87559.ko', 'camellia_fs1815.ko', 'mt6833-mt6359p.ko',
}


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def vermagic(data, label):
    if len(data) < 64 or data[:7] != b'\x7fELF\x02\x01\x01':
        raise ValueError(f'{label}: expected little-endian ELF64')
    if struct.unpack_from('<HH', data, 16) != (1, 183):
        raise ValueError(f'{label}: expected an arm64 kernel module')
    offset = struct.unpack_from('<Q', data, 40)[0]
    stride, count, names_index = struct.unpack_from('<HHH', data, 58)
    if stride != 64 or not count or names_index >= count or offset + stride * count > len(data):
        raise ValueError(f'{label}: invalid section table')
    headers = [struct.unpack_from('<IIQQQQIIQQ', data, offset + index * stride)
               for index in range(count)]

    def section(header):
        start, size = header[4:6]
        if start + size > len(data):
            raise ValueError(f'{label}: section exceeds the file')
        return data[start:start + size]

    names = section(headers[names_index])
    info = None
    descriptor = False
    for header in headers:
        end = names.find(b'\0', header[0])
        if header[0] >= len(names) or end < 0:
            raise ValueError(f'{label}: invalid section name')
        name = names[header[0]:end]
        if name == b'.modinfo':
            if info is not None:
                raise ValueError(f'{label}: duplicate module metadata')
            info = section(header)
        if name == b'.gnu.linkonce.this_module':
            descriptor = header[5] >= 64
    values = [entry[9:] for entry in (info or b'').split(b'\0')
              if entry.startswith(b'vermagic=')]
    if not descriptor or len(values) != 1 or not values[0]:
        raise ValueError(f'{label}: missing kernel module metadata')
    return values[0].decode('ascii')


def verify_payload(payload, info):
    if info['source_commit'] != SOURCE_COMMIT:
        raise ValueError('kernel source is not the device-tested 6.6 build')
    kernel = gzip.decompress((payload / 'Image.gz').read_bytes())
    if len(kernel) < 64 or kernel[56:60] != b'ARM\x64':
        raise ValueError('invalid arm64 kernel Image')
    if ('Linux version ' + info['kernel_release']).encode() not in kernel:
        raise ValueError('kernel banner does not match the module release')
    dtb = (payload / 'dtb').read_bytes()
    if len(dtb) < 40 or struct.unpack_from('>II', dtb) != (0xd00dfeed, len(dtb)):
        raise ValueError('invalid merged device tree')
    modules = payload / 'lib/modules'
    order = (modules / 'modules.load').read_text().splitlines()
    files = {path.name for path in modules.glob('*.ko')}
    if len(order) != MODULE_COUNT or len(set(order)) != MODULE_COUNT or set(order) != files:
        raise ValueError('expected the complete 272-module inventory')
    if not CRITICAL_MODULES <= files:
        raise ValueError('missing recovery-critical modules: ' + repr(sorted(CRITICAL_MODULES - files)))
    expected = None
    for name in order:
        if pathlib.PurePosixPath(name).name != name:
            raise ValueError('invalid module path')
        magic = vermagic((modules / name).read_bytes(), name)
        if not magic.startswith(info['kernel_release'] + ' ') or (expected and magic != expected):
            raise ValueError('module release or build flags mismatch: ' + name)
        expected = magic
    for provider in ('camellia_aw87559.ko', 'camellia_fs1815.ko'):
        if order.index(provider) >= order.index('mt6833-mt6359p.ko'):
            raise ValueError('speaker providers must load before the sound card')
    for filename in ('modules.dep', 'modules.alias', 'modules.softdep', 'modules.options'):
        if not (modules / filename).is_file():
            raise ValueError('missing module index: ' + filename)
    for line in (modules / 'modules.dep').read_text().splitlines():
        name, dependencies = line.split(':', 1)
        if name not in files or not set(dependencies.split()) <= files:
            raise ValueError('module dependency is not packaged: ' + name)
    return order


def verify_tree(tree):
    manifest = json.loads((tree / 'prebuilt/kernel66.json').read_text())
    for name, expected in manifest['files'].items():
        path = tree / name
        if not path.is_file() or sha256(path) != expected:
            raise ValueError('prebuilt hash mismatch: ' + name)
    root = tree / 'recovery/root'
    info = manifest['build_info']
    kernel = gzip.decompress((tree / 'prebuilt/kernel').read_bytes())
    if ('Linux version ' + info['kernel_release']).encode() not in kernel:
        raise ValueError('tree kernel release mismatch')
    order = (root / 'lib/modules/modules.load').read_text().splitlines()
    recovery_order = (root / 'lib/modules/modules.load.recovery').read_text().splitlines()
    if order != recovery_order or len(order) != MODULE_COUNT:
        raise ValueError('recovery load list is incomplete')
    files = {p.name for p in (root / 'lib/modules').glob('*.ko')}
    if set(order) != files or not CRITICAL_MODULES <= files:
        raise ValueError('tree is missing required module files')
    for name in order:
        if not vermagic((root / 'lib/modules' / name).read_bytes(), name).startswith(info['kernel_release'] + ' '):
            raise ValueError('tree module version mismatch: ' + name)
    print(f"Verified recovery tree: {info['kernel_release']}, {len(order)} matching modules")
    return manifest
