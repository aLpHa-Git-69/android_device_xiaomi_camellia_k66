#!/usr/bin/env python3
"""Export this complete device tree, including verified 6.6 prebuilts."""
import argparse
import hashlib
import os
import pathlib
import stat
import zipfile

from kernel66 import verify_tree

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('output', type=pathlib.Path)
args = parser.parse_args()
tree = pathlib.Path(__file__).resolve().parents[1]
verify_tree(tree)
prefix = pathlib.PurePosixPath('device/xiaomi/camellia')
with zipfile.ZipFile(args.output, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for path in sorted(tree.rglob('*')):
        relative = path.relative_to(tree)
        if path.resolve() in (args.output.resolve(), args.output.with_suffix(args.output.suffix + '.sha256').resolve()):
            continue
        if any(part in ('.git', 'out', '__pycache__') for part in relative.parts):
            continue
        name = (prefix / pathlib.PurePosixPath(relative.as_posix())).as_posix()
        if path.is_symlink():
            entry = zipfile.ZipInfo(name)
            entry.create_system = 3
            entry.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(entry, os.readlink(path))
        elif path.is_file():
            archive.write(path, name)
with zipfile.ZipFile(args.output) as archive:
    if archive.testzip() is not None:
        raise ValueError('exported tree archive is corrupt')
digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
args.output.with_suffix(args.output.suffix + '.sha256').write_text(
    digest + '  ' + args.output.name + '\n'
)
print(digest + '  ' + args.output.name)
