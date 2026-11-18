#!/usr/bin/env python3
"""Prepare slot-A test AVB metadata for the matched boot/vendor_boot pair.

Preserves the stock system/vendor/mi_ext descriptors, replaces the boot-chain
key with the compiled image's embedded public key, and adds vendor_boot's hash.
This prepares a file only; it never writes a device partition.
"""
import argparse
import hashlib
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stock_vbmeta', type=pathlib.Path)
    parser.add_argument('images', type=pathlib.Path)
    parser.add_argument('output', type=pathlib.Path)
    parser.add_argument('--avbtool', required=True, type=pathlib.Path)
    parser.add_argument('--test-key', required=True, type=pathlib.Path)
    parser.add_argument('--copy-pair', action='store_true', help='copy the unchanged boot/vendor_boot pair alongside the test metadata')
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location('avbtool_module', args.avbtool)
    avb = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(avb)

    def parse(path):
        data = path.read_bytes()
        if data[:4] != b'AVB0':
            footer = avb.AvbFooter(data[-avb.AvbFooter.SIZE:])
            data = data[footer.vbmeta_offset:footer.vbmeta_offset + footer.vbmeta_size]
        header = avb.AvbVBMetaHeader(data[:256])
        auxiliary = 256 + header.authentication_data_block_size
        start = auxiliary + header.descriptors_offset
        descriptors = avb.parse_descriptors(data[start:start + header.descriptors_size])
        public_key = data[auxiliary + header.public_key_offset:
                          auxiliary + header.public_key_offset + header.public_key_size]
        return header, descriptors, public_key, data

    stock_header, stock_descriptors, _, _ = parse(args.stock_vbmeta)
    boot_header, _, boot_key, _ = parse(args.images / 'boot.img')
    _, vendor_descriptors, _, _ = parse(args.images / 'vendor_boot.img')
    if not boot_key:
        raise ValueError('compiled boot image has no signing public key')
    old_boot = [d for d in stock_descriptors
                if isinstance(d, avb.AvbChainPartitionDescriptor) and d.partition_name == 'boot']
    vendor_hash = [d for d in vendor_descriptors
                   if isinstance(d, avb.AvbHashDescriptor) and d.partition_name == 'vendor_boot']
    if len(old_boot) != 1 or len(vendor_hash) != 1:
        raise ValueError('unexpected stock boot chain or vendor_boot descriptor')
    preserved = [d for d in stock_descriptors if d not in old_boot]
    encoded = b''.join(d.encode() for d in preserved)
    carrier_header = avb.AvbVBMetaHeader()
    carrier_header.descriptors_size = len(encoded)
    carrier_header.auxiliary_data_block_size = (len(encoded) + 63) // 64 * 64
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=args.output.parent) as directory:
        work = pathlib.Path(directory)
        carrier = work / 'preserved-descriptors.img'
        carrier.write_bytes(carrier_header.encode() + encoded +
                            b'\0' * (carrier_header.auxiliary_data_block_size - len(encoded)))
        public = work / 'boot-public-key.avbpubkey'
        public.write_bytes(boot_key)
        location = boot_header.rollback_index_location or old_boot[0].rollback_index_location
        command = [sys.executable, str(args.avbtool.resolve()), 'make_vbmeta_image',
                   '--output', str(args.output.resolve()), '--algorithm', 'SHA256_RSA2048',
                   '--key', str(args.test_key.resolve()),
                   '--flags', str(stock_header.flags), '--rollback_index', str(stock_header.rollback_index),
                   '--include_descriptors_from_image', str(carrier),
                   '--include_descriptors_from_image', str((args.images / 'vendor_boot.img').resolve()),
                   '--chain_partition', f'boot:{location}:{public}']
        subprocess.run(command, check=True)
    header, descriptors, _, blob = parse(args.output)
    if not avb.verify_vbmeta_signature(header, blob):
        raise ValueError('test vbmeta signature did not verify')
    chains = [d for d in descriptors if isinstance(d, avb.AvbChainPartitionDescriptor)
              and d.partition_name == 'boot']
    hashes = [d for d in descriptors if isinstance(d, avb.AvbHashDescriptor)
              and d.partition_name == 'vendor_boot']
    if len(chains) != 1 or chains[0].public_key != boot_key or chains[0].rollback_index_location != location:
        raise ValueError('test vbmeta boot chain is incorrect')
    if len(hashes) != 1 or hashes[0].encode() != vendor_hash[0].encode():
        raise ValueError('test vbmeta vendor_boot hash is incorrect')
    preserved_bytes = {d.encode() for d in preserved}
    if not preserved_bytes <= {d.encode() for d in descriptors}:
        raise ValueError('stock system/vendor descriptors were changed')
    if header.flags != stock_header.flags or header.rollback_index != stock_header.rollback_index:
        raise ValueError('stock verification flags or rollback index were changed')
    digest = hashlib.sha256(args.output.read_bytes()).hexdigest()
    args.output.with_suffix('.img.sha256').write_text(digest + '  ' + args.output.name + '\n')
    report = {
        'test_only': True, 'device_validated': False, 'target_slot': 'a',
        'stock_vbmeta_sha256': hashlib.sha256(args.stock_vbmeta.read_bytes()).hexdigest(),
        'stock_descriptors_preserved': len(preserved),
        'boot_chain_key_sha1': hashlib.sha1(boot_key).hexdigest(),
        'boot_chain_rollback_location': location,
        'vendor_boot_hash_descriptor_added': True,
        'flags_preserved': header.flags, 'rollback_index_preserved': header.rollback_index,
        'sha256': digest,
    }
    args.output.with_suffix('.img.json').write_text(json.dumps(report, indent=2) + '\n')
    if args.copy_pair:
        for name in ('boot.img', 'vendor_boot.img'):
            target = args.output.parent / name
            shutil.copyfile(args.images / name, target)
            target.with_suffix('.img.sha256').write_text(
                hashlib.sha256(target.read_bytes()).hexdigest() + '  ' + name + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
