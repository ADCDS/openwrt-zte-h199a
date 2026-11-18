#!/usr/bin/env python3
"""Install owner-extracted MT7603 calibration into the ignored build tree."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import struct
import tarfile
import tempfile
import zlib

SUPPORTED_SHA256 = 'c2c0f5acfc78f63edb6b9b2b1dea95f03274b4b489769344be9380d0cde88cc5'
BLOB = 'h199a-mt7603-eeprom.bin'
INCLUDE = 'zx279128s-h199a-owner-calibration.dtsi'
MANIFEST = 'h199a-owner-calibration.json'
DIRECTIVE = '/* H199A owner calibration (generated) */\n/include/ "' + INCLUDE + '"\n'
NODE = '/soc/pcie@f100000/pcie@0,0/wifi@0,0'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate(data):
    if len(data) != 512 or int.from_bytes(data[:2], 'little') != 0x7603:
        raise ValueError('expected the 512-byte MT7603 EEPROM base from the supported stock extractor')
    if digest(data) != SUPPORTED_SHA256:
        raise ValueError('unsupported EEPROM base hash; qualify the stock extraction before use')
    return {'chip': 'MT7603', 'eeprom_bytes': len(data), 'eeprom_sha256': digest(data)}


def write_private(path, data):
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(data)
    temporary.replace(path)


def clear(dts):
    text = dts.read_text()
    if text.count(DIRECTIVE) > 1:
        raise ValueError('ambiguous generated calibration include')
    # Refresh the source timestamp even after build.sh has copied a pristine
    # public DTS over it, so a previously calibrated DTB cannot remain stale.
    dts.write_text(text.replace(DIRECTIVE, ''))
    for name in (BLOB, INCLUDE, MANIFEST):
        (dts.parent / name).unlink(missing_ok=True)


def install(dts, eeprom):
    data = eeprom.read_bytes()
    record = validate(data)  # Refuse invalid input before changing any output.
    if dts.read_text().count('wifi2g: wifi@0,0') != 1:
        raise ValueError('expected one labelled H199A 2.4 GHz endpoint')
    clear(dts)
    write_private(dts.parent / BLOB, data)
    include = '&wifi2g {\n\tmediatek,eeprom-data = /incbin/("' + BLOB + '");\n};\n'
    write_private(dts.parent / INCLUDE, include.encode())
    dts.write_text(dts.read_text().rstrip() + '\n\n' + DIRECTIVE)
    record['dts_sha256'] = digest(dts.read_bytes())
    write_private(dts.parent / MANIFEST, (json.dumps(record, indent=2) + '\n').encode())
    return record


def verify_packaged_kernel(image, dtb):
    if image.stat().st_size > 32 * 1024 * 1024:
        raise ValueError('unexpectedly large H199A sysupgrade archive')
    with tarfile.open(image, 'r:') as archive:
        entries = [entry for entry in archive if entry.name == 'h199a/kernel']
        if len(entries) != 1 or not entries[0].isfile() or entries[0].size != 3 * 1024 * 1024:
            raise ValueError('expected exactly one regular 3MiB h199a/kernel archive member')
        kernel = archive.extractfile(entries[0]).read()
    header = bytearray(kernel[32:96])
    magic, hcrc, _, size, load, entry, dcrc = struct.unpack_from('>7I', header)
    if (magic != 0x27051956 or load != 0x40008000 or entry != load or
            header[28:32] != bytes((5, 2, 2, 0)) or not 0 < size <= len(kernel) - 96):
        raise ValueError('unexpected packaged kernel wrapper')
    struct.pack_into('>I', header, 4, 0)
    payload = kernel[96:96 + size]
    if zlib.crc32(header) != hcrc or zlib.crc32(payload) != dcrc:
        raise ValueError('packaged kernel checksum mismatch')
    if (dtb[:4] != b'\xd0\x0d\xfe\xed' or len(dtb) < 40 or
            struct.unpack_from('>I', dtb, 4)[0] != len(dtb) or not payload.endswith(dtb)):
        raise ValueError('packaged kernel does not end with the verified image DTB')
    return digest(kernel)


def verify(dtb, manifest, image=None):
    record = json.loads(manifest.read_text())
    run = subprocess.run(['fdtget', '-t', 'bx', str(dtb), NODE, 'mediatek,eeprom-data'],
                         check=True, capture_output=True, text=True)
    data = bytes(int(value, 16) for value in run.stdout.split())
    checked = validate(data)
    if any(record.get(key) != value for key, value in checked.items()):
        raise ValueError('compiled calibration differs from the build input manifest')
    subprocess.run(['fdtget', str(dtb), NODE, 'mediatek,eeprom-merge-otp'],
                   check=True, capture_output=True)
    record['dtb_sha256'] = digest(dtb.read_bytes())
    record['compiled_eeprom_verified'] = True
    record['merge_otp'] = True
    record.pop('image_sha256', None)
    record.pop('packaged_kernel_sha256', None)
    if image is not None:
        record['packaged_kernel_sha256'] = verify_packaged_kernel(image, dtb.read_bytes())
        record['image_sha256'] = digest(image.read_bytes())
    write_private(manifest, (json.dumps(record, indent=2) + '\n').encode())
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('check').add_argument('eeprom', type=Path)
    installer = commands.add_parser('install')
    installer.add_argument('dts', type=Path)
    installer.add_argument('eeprom', type=Path)
    commands.add_parser('clear').add_argument('dts', type=Path)
    verifier = commands.add_parser('verify')
    verifier.add_argument('dtb', type=Path)
    verifier.add_argument('manifest', type=Path)
    verifier.add_argument('--image', type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        if args.command == 'check':
            record = validate(args.eeprom.read_bytes())
        elif args.command == 'install':
            record = install(args.dts, args.eeprom)
        elif args.command == 'clear':
            clear(args.dts)
            record = {'cleared': True}
        else:
            record = verify(args.dtb, args.manifest, args.image)
    except (OSError, ValueError, tarfile.TarError, subprocess.CalledProcessError) as error:
        parser.exit(1, 'Calibration preparation failed: ' + str(error) + '\n')
    print(json.dumps(record, sort_keys=True))


if __name__ == '__main__':
    main()
