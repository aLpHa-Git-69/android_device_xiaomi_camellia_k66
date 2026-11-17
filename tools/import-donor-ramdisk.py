#!/usr/bin/env python3
"""Save the original OrangeFox ramdisk for fast manual repacking."""
import argparse
import gzip
import hashlib
import json
import pathlib
import struct
import zipfile

DONOR_SHA256 = '599d4e395b61bd524811f3afc988a47579ed115ed8cd2db2eca7f9a9d2c5a6b9'

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('donor_zip', type=pathlib.Path)
args = parser.parse_args()
tree = pathlib.Path(__file__).resolve().parents[1]
if hashlib.sha256(args.donor_zip.read_bytes()).hexdigest() != DONOR_SHA256:
    raise ValueError('not the supplied OrangeFox R12.0_1 donor archive')
with zipfile.ZipFile(args.donor_zip) as archive:
    image = archive.read('recovery.img')
if image[:8] != b'ANDROID!' or struct.unpack_from('<I', image, 40)[0] != 2:
    raise ValueError('unexpected donor boot format')
kernel_size = struct.unpack_from('<I', image, 8)[0]
ramdisk_size = struct.unpack_from('<I', image, 16)[0]
page = struct.unpack_from('<I', image, 36)[0]
offset = page + (kernel_size + page - 1) // page * page
ramdisk = image[offset:offset + ramdisk_size]
raw = gzip.decompress(ramdisk)
if b'system/bin/recovery\0' not in raw or b'lib/modules/modules.load\0' in raw:
    raise ValueError('unexpected donor ramdisk contents')
path = tree / 'prebuilt/donor-recovery.cpio.gz'
path.write_bytes(ramdisk)
info = {
    'donor_zip_sha256': DONOR_SHA256,
    'ramdisk_sha256': hashlib.sha256(ramdisk).hexdigest(),
    'ramdisk_size': len(ramdisk),
    'recovery_codebase': 'OrangeFox fox_12.1, supplied R12.0_1 build',
}
(tree / 'prebuilt/donor-recovery.json').write_text(json.dumps(info, indent=2) + '\n')
print(json.dumps(info, indent=2))
