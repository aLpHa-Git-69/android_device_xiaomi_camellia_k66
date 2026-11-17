#!/usr/bin/env python3
"""Install the device-tested kernel payload into this OrangeFox tree."""
import argparse
import json
import pathlib
import shutil

from kernel66 import sha256, verify_payload, verify_tree


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('payload', type=pathlib.Path)
    args = parser.parse_args()
    tree = pathlib.Path(__file__).resolve().parents[1]
    payload = args.payload.resolve()
    info = json.loads((payload / 'build-info.json').read_text())
    verify_payload(payload, info)
    destination = tree / 'recovery/root/lib/modules'
    if destination.exists() and any(destination.iterdir()) and not (tree / 'prebuilt/kernel66.json').exists():
        raise ValueError('refusing to replace an existing, untracked module directory')
    destination.mkdir(parents=True, exist_ok=True)
    files = {}

    def install(source, relative):
        target = tree / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o644)
        files[relative] = sha256(target)

    install(payload / 'Image.gz', 'prebuilt/kernel')
    install(payload / 'dtb', 'prebuilt/dtb.img')
    for path in sorted((payload / 'lib/modules').iterdir()):
        if path.is_file():
            install(path, 'recovery/root/lib/modules/' + path.name)
    install(payload / 'lib/modules/modules.load', 'recovery/root/lib/modules/modules.load.recovery')
    for path in sorted((payload / 'lib/firmware').iterdir()):
        if path.is_file():
            install(path, 'recovery/root/lib/firmware/' + path.name)
    manifest = {
        'build_info': info,
        'source_repository': 'https://github.com/aLpHa-Git-69/kernel_xiaomi_mt6833_66',
        'source_run_id': '43736910427',
        'module_count': len(list(destination.glob('*.ko'))),
        'files': files,
    }
    (tree / 'prebuilt/kernel66.json').write_text(json.dumps(manifest, indent=2) + '\n')
    verify_tree(tree)


if __name__ == '__main__':
    main()
