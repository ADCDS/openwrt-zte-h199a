#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Build a RAM-only stock PCI reference with NAND/watchdog registration disabled.

Only the identified owner's corrected stock image is accepted. The unchanged
linked layout and stock DTB are retained. No filesystem can mount through this
NAND driver; the intended endpoint is a root-mount panic, then external power-off.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import struct
import zlib

SOURCE_SHA = 'da53645b7f312941d30bc5d852a864e510b8dff35dfc0ff560a37d54b8d319a1'
RAW_SHA = 'b3b1434a6996c9de266c6db68014889f9f0836a3a53be9145ce7af9a62ae1b64'
RAW_SIZE = 6087328
GZIP_OFFSET = 0x6608
NAME = 'h199a-stock-pci-no-flash'
PATCHES = (
    (0x57d660, bytes.fromhex('f40f06e30010a0e3'), bytes.fromhex('0000a0e31eff2fe1'), 'disable SPI-NAND registration'),
    (0x57e8d8, bytes.fromhex('04009fe50010a0e3'), bytes.fromhex('0000a0e31eff2fe1'), 'disable watchdog registration'),
    (0x5b4588, bytes.fromhex('05000000'), bytes(4), 'disable default panic reboot'),
)
INITCALLS = ((0x598634, 0xc0585660), (0x5983c0, 0xc05868d8))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def prepare(source):
    require(len(source) == 3 * 1024 * 1024 and sha(source) == SOURCE_SHA,
            'unsupported original stock image; use the verified corrected own-unit bank')
    header = bytearray(source[32:96])
    magic, hcrc, _, size, load, entry, dcrc = struct.unpack_from('>7I', header)
    require(magic == 0x27051956 and load == entry == 0x40008000 and
            header[28:32] == bytes((5, 2, 2, 0)), 'unexpected uImage wrapper')
    struct.pack_into('>I', header, 4, 0)
    payload = source[96:96 + size]
    require(len(payload) == size and zlib.crc32(header) == hcrc and
            zlib.crc32(payload) == dcrc, 'original wrapper checksum mismatch')
    decoder = zlib.decompressobj(31)
    raw = decoder.decompress(source[GZIP_OFFSET:96 + size], RAW_SIZE + 1)
    require(decoder.eof and len(raw) == RAW_SIZE and sha(raw) == RAW_SHA,
            'original decompressed kernel differs; offsets were not guessed')
    length = 96 + size - GZIP_OFFSET - len(decoder.unused_data)
    for offset, target in INITCALLS:
        require(struct.unpack_from('<I', raw, offset)[0] == target,
                'initcall does not point to the expected ARM function')
    patched = bytearray(raw)
    for offset, expected, replacement, label in PATCHES:
        require(raw[offset:offset + len(expected)] == expected, label + ': unexpected original bytes')
        patched[offset:offset + len(expected)] = replacement
    compressor = zlib.compressobj(9, zlib.DEFLATED, 31)
    packed = compressor.compress(patched) + compressor.flush()
    padding = length - len(packed)
    require(padding >= 0 and packed[3] == 0, 'replacement gzip does not fit the original slot')
    if padding:
        packed = packed[:3] + b'\x08' + packed[4:10] + b'R' * (padding - 1) + b'\0' + packed[10:]
    require(len(packed) == length and zlib.decompress(packed, 31) == patched,
            'fixed-length gzip roundtrip failed')
    output = bytearray(source)
    output[GZIP_OFFSET:GZIP_OFFSET + length] = packed
    header[32:64] = NAME.encode().ljust(32, b'\0')
    struct.pack_into('>I', header, 24, zlib.crc32(output[96:96 + size]))
    struct.pack_into('>I', header, 4, zlib.crc32(header))
    output[32:96] = header
    record = {'name': NAME, 'source_sha256': sha(source), 'source_kernel_sha256': sha(raw),
              'patched_kernel_sha256': sha(patched), 'image_sha256': sha(output),
              'image_bytes': len(output), 'gzip_offset': GZIP_OFFSET, 'gzip_slot_bytes': length,
              'patches': [{'offset': hex(offset), 'original': old.hex(), 'replacement': new.hex(),
                           'purpose': label} for offset, old, new, label in PATCHES],
              'scope': 'RAM-only PCI reference; NAND/watchdog registration suppressed; no root mount expected'}
    return bytes(output), record


def verify_candidate(candidate, original):
    expected, record = prepare(original)
    require(candidate == expected, 'candidate differs from the exact contained stock RAM transformation')
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    manifest = args.output.with_suffix(args.output.suffix + '.json')
    require(not args.output.exists() and not manifest.exists(), 'refusing to overwrite existing evidence')
    os.umask(0o077)
    image, record = prepare(args.source.read_bytes())
    with args.output.open('xb') as stream:
        stream.write(image)
    with manifest.open('x') as stream:
        json.dump(record, stream, indent=2)
        stream.write('\n')
    print(json.dumps(record))


if __name__ == '__main__':
    main()
