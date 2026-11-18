#!/usr/bin/env python3
"""Validate an H199A production sysupgrade tar against the bank-A contract.

Checks every property the vendor bootloader relies on, so a bad factory image
is caught in the build instead of on the bench:

  * exactly the three members h199a/{kernel,rootfs,header}, each a regular file;
  * kernel container = 3 MiB, ZTE magic + uImage with load/entry 0x40008000;
  * rootfs = fs_size (0xd20000), padded, i.e. it fills the rootfs partition;
  * header +0x3c == csp_crc(kernel[0x20:0x20+0x2ffdcc])   (kernel CRC);
  * header +0x48 == csp_crc(rootfs)                        (fs CRC);
  * header +0xa4 == crc32(header[0:0xa4])                  (self-CRC);
  * every header byte OUTSIDE {0x3c.., 0x48.., 0xa4..} equals the unit's
    template, so the per-unit identity (version string, serial +0x1f4,
    upgrade keys, magic) is preserved and only the CRC fields changed.

Optionally extracts the three loose parts for a first U-Boot TFTP install.
It reads files only; it never touches hardware.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tarfile

TOOLS = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('flash_prep', TOOLS / 'flash-prep.py')
fp = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fp)

UIMAGE_MAGIC = bytes.fromhex('27051956')
LOAD_ENTRY = 0x40008000


def _member(tar, name):
    try:
        info = tar.getmember(name)
    except KeyError:
        raise ValueError(f'missing member {name}')
    if not info.isfile():
        raise ValueError(f'member {name} is not a regular file')
    return info, tar.extractfile(info).read()


def verify(tar_path, template, extract_dir=None):
    template = bytes(template)
    if len(template) == fp.HEADER_OFF + fp.HEADER_BLK or len(template) == fp.HEADER_BLK:
        tpl = bytes(fp.header_template(template))
    else:
        raise ValueError('header template must be the 128 KiB block or a full dump')

    with tarfile.open(tar_path, 'r:') as tar:
        names = [m.name for m in tar.getmembers() if m.isfile()]
        expected = {'h199a/kernel', 'h199a/rootfs', 'h199a/header'}
        extra = set(names) - expected
        if extra:
            raise ValueError(f'unexpected members: {sorted(extra)}')
        _, kernel = _member(tar, 'h199a/kernel')
        _, rootfs = _member(tar, 'h199a/rootfs')
        _, header = _member(tar, 'h199a/header')

    report = {'tar': str(tar_path)}

    if len(kernel) != fp.KERNEL_LEN:
        raise ValueError(f'kernel container {len(kernel)} != {fp.KERNEL_LEN:#x}')
    if kernel[:16] != fp.ZTE_MAGIC[:16] or kernel[16:32] != fp.ZTE_MAGIC[16:]:
        raise ValueError('kernel container missing the 32-byte ZTE magic')
    if kernel[32:36] != UIMAGE_MAGIC:
        raise ValueError('kernel container has no uImage at +0x20')
    load, entry = struct.unpack_from('>II', kernel, 32 + 16)
    if load != LOAD_ENTRY or entry != LOAD_ENTRY:
        raise ValueError(f'uImage load/entry {load:#x}/{entry:#x} != {LOAD_ENTRY:#x}')

    if len(rootfs) != fp.FS_LEN:
        raise ValueError(f'rootfs {len(rootfs)} != fs_size {fp.FS_LEN:#x} (must be padded, never shrunk)')
    if rootfs[:4] != b'hsqs':
        raise ValueError('rootfs is not a SquashFS image')

    if len(header) != fp.HEADER_BLK:
        raise ValueError(f'header {len(header)} != {fp.HEADER_BLK:#x}')

    kcrc = fp.kernel_crc(kernel)
    fscrc = fp.fs_crc(rootfs)
    hdr_kcrc = struct.unpack_from('<I', header, 0x3c)[0]
    hdr_fscrc = struct.unpack_from('<I', header, 0x48)[0]
    hdr_self = struct.unpack_from('<I', header, 0xa4)[0]
    if hdr_kcrc != kcrc:
        raise ValueError(f'header kernel CRC {hdr_kcrc:#010x} != computed {kcrc:#010x}')
    if hdr_fscrc != fscrc:
        raise ValueError(f'header fs CRC {hdr_fscrc:#010x} != computed {fscrc:#010x}')
    expect_self = fp.zlib.crc32(header[:0xa4]) & 0xffffffff
    if hdr_self != expect_self:
        raise ValueError(f'header self-CRC {hdr_self:#010x} != computed {expect_self:#010x}')

    # fs_size field (+0x40) is load-bearing: it must stay 0xd20000 or the
    # derived HeaderOffset moves and the bank vanishes.
    fs_size = struct.unpack_from('<I', header, 0x40)[0]
    if fs_size != fp.FS_LEN:
        raise ValueError(f'header fs_size {fs_size:#x} != {fp.FS_LEN:#x}')

    # The header must equal the template everywhere except the three CRC fields:
    # proves the only change from this unit's own header is the CRC math.
    rebuilt = fp.patch_header(tpl, kcrc, fscrc)
    if rebuilt != header:
        diffs = [hex(i) for i in range(len(header)) if header[i] != rebuilt[i]]
        raise ValueError(f'header diverges from template+CRCs at offsets {diffs[:16]}')
    identity = [i for i in range(len(tpl)) if tpl[i] != header[i]]
    expected_fields = set(range(0x3c, 0x40)) | set(range(0x48, 0x4c)) | set(range(0xa4, 0xa8))
    if set(identity) - expected_fields:
        raise ValueError('header changes bytes outside the CRC fields; identity not preserved')

    report.update(
        kernel_bytes=len(kernel), rootfs_bytes=len(rootfs), header_bytes=len(header),
        kernel_crc=f'{kcrc:08x}', fs_crc=f'{fscrc:08x}', header_self_crc=f'{hdr_self:08x}',
        fs_size=f'{fs_size:08x}', identity_bytes_changed=len(identity),
        kernel_sha256=hashlib.sha256(kernel).hexdigest(),
        rootfs_sha256=hashlib.sha256(rootfs).hexdigest(),
        header_sha256=hashlib.sha256(header).hexdigest())

    if extract_dir is not None:
        out = Path(extract_dir)
        out.mkdir(parents=True, exist_ok=True)
        (out / 'kernel').write_bytes(kernel)
        (out / 'rootfs').write_bytes(rootfs)
        (out / 'header').write_bytes(header)
        report['extract_dir'] = str(out)
    return report


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('tar', type=Path)
    ap.add_argument('--header-template', type=Path, required=True)
    ap.add_argument('--extract-dir', type=Path)
    args = ap.parse_args()
    try:
        report = verify(args.tar, args.header_template.read_bytes(), args.extract_dir)
    except (OSError, ValueError, tarfile.TarError) as error:
        sys.stderr.write('production image invalid: ' + str(error) + '\n')
        raise SystemExit(1)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
