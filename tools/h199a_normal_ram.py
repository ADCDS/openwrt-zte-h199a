#!/usr/bin/env python3
"""Bounded normal-userspace RAM boot: checksum envelope and acceptance gates.

The root envelope is a kernel-type uImage solely because the verified vendor
bootloader exposes `bootm start`, but neither crc32 nor iminfo. Never execute
this envelope. Its 64-byte header precedes the unchanged SquashFS RAM disk.
"""
import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import struct
import zlib

from h199a_uart_fd import UARTError

ROOT_HEADER = 0x43ffffc0
ROOT_START = 0x44000000
ROOT_LIMIT = 0x45000000
ROOT_NAME = 'h199a-root-check-only'
# procd's askfirst console can start before /etc/init.d/system sets the hostname,
# so the first prompt after activation carries the kernel default nodename
# "(none)" (observed on the first normal-X boot, 2026-11-15). Accept exactly that
# value in addition to ordinary hostnames; nothing broader.
NORMAL_PROMPT = re.compile(rb'(?:^|\r?\n)root@(?:[A-Za-z0-9_.-]+|\(none\)):[^\r\n]*# ')
ACTIVATE = b'Please press Enter to activate this console.'
READY = b'H199A_OVERLAY_READY:'
MOUNTED = b'H199A_OVERLAY_MOUNTED:'


@dataclass(frozen=True)
class RootEnvelope:
    data: bytes
    payload_bytes: int
    header_crc: int
    data_crc: int
    name: str = ROOT_NAME


def make_envelope(raw):
    if not isinstance(raw, bytes) or raw[:4] != b'hsqs' or not 96 < len(raw) <= 16*1024*1024:
        raise ValueError('expected raw SquashFS within the 16 MiB RAM-root window')
    fields = [0x27051956, 0, 0, len(raw), ROOT_START, ROOT_START,
              zlib.crc32(raw), 5, 2, 2, 0, ROOT_NAME.encode().ljust(32, b'\0')]
    header = struct.pack('>7I4B32s', *fields)
    fields[1] = zlib.crc32(header)
    return struct.pack('>7I4B32s', *fields) + raw


def parse_envelope(data):
    if not isinstance(data, bytes) or not 160 < len(data) <= 64+16*1024*1024:
        raise ValueError('root checksum envelope size outside its bounded window')
    h = data[:64]
    magic, hcrc, stamp, length, load, entry, dcrc, os_, arch, kind, comp, name = struct.unpack('>7I4B32s', h)
    if (magic, load, entry, os_, arch, kind, comp) != (0x27051956, ROOT_START, ROOT_START, 5, 2, 2, 0):
        raise ValueError('root checksum envelope metadata differs')
    if length != len(data)-64 or data[64:68] != b'hsqs':
        raise ValueError('root payload length/signature differs')
    if name != ROOT_NAME.encode().ljust(32, b'\0'):
        raise ValueError('wrong checksum-only root label')
    if zlib.crc32(h[:4]+bytes(4)+h[8:]) != hcrc or zlib.crc32(data[64:]) != dcrc:
        raise ValueError('root checksum envelope CRC mismatch')
    return RootEnvelope(data, length, hcrc, dcrc)


def validate_manifest(manifest, kernel, root, backend='normal-ram-root'):
    if backend not in ('normal-ram-root', 'production-qualify') or manifest.get('storage_backend') != backend:
        raise ValueError(f'{backend} RAM-root manifest required')
    if (manifest.get('sha256') != hashlib.sha256(kernel.data).hexdigest() or
            manifest.get('bytes') != len(kernel.data) or manifest.get('name') != kernel.name):
        raise ValueError('kernel does not match the normal RAM-root manifest')
    info = manifest.get('ram_root', {})
    expected = {'bytes': root.payload_bytes, 'load_address': ROOT_START,
                'end_address': ROOT_START+root.payload_bytes}
    for key, value in expected.items():
        if type(info.get(key)) is not int or info[key] != value:
            raise ValueError('root manifest extent differs: '+key)
    if (info.get('sha256') != hashlib.sha256(root.data[64:]).hexdigest() or
            info.get('crc32') != f'{root.data_crc:08x}'):
        raise ValueError('root payload does not match the normal RAM-root manifest')
    end, workspace = info.get('kernel_end'), info.get('conservative_decompress_end')
    if (type(end) is not int or type(workspace) is not int or
            not 0x40008000 < end <= workspace <= 0x41000000 or
            info['end_address'] > ROOT_LIMIT or 0x42000000+len(kernel.data) >= ROOT_HEADER):
        raise ValueError('kernel/root memory extents overlap or exceed the qualified layout')
    return {'root_sha256': info['sha256'], 'root_bytes': root.payload_bytes,
            'envelope_bytes': len(root.data), 'header_address': ROOT_HEADER,
            'payload_address': ROOT_START, 'payload_end': info['end_address'],
            'conservative_decompress_end': workspace}


def validate_bdinfo(response, kernel_bytes, root_bytes):
    fields = {}
    patterns = {'bank': rb'DRAM bank', 'start': rb'-> start', 'size': rb'-> size',
                'boot_params': rb'boot_params', 'tlb': rb'TLB addr',
                'reloc': rb'relocaddr', 'reloc_offset': rb'reloc off',
                'irq_sp': rb'irq_sp', 'sp': rb'sp start'}
    for key, pattern in patterns.items():
        values = re.findall(rb'^'+pattern+rb'\s*=\s*0x([0-9a-fA-F]+)\s*\r?$', response, re.M)
        if len(values) != 1:
            raise UARTError('missing or duplicate bootloader memory field: '+key)
        fields[key] = int(values[0], 16)
    # This is a consistency gate for the known vendor layout, not an assertion
    # that bdinfo enumerates every allocation made by the bootloader.
    if (fields['bank'], fields['start'], fields['size'], fields['boot_params']) != (
            0, 0x40000000, 0x08000000, 0x40000100):
        raise UARTError('unexpected DRAM bank or boot-parameter layout')
    if not (0x47000000 <= fields['sp'] <= fields['irq_sp'] < fields['reloc'] < fields['tlb'] < 0x48000000):
        raise UARTError('bootloader stack/relocation is outside the reserved upper RAM')
    if fields['irq_sp']-fields['sp'] != 16 or fields['reloc']-fields['reloc_offset'] != 0x47f00000:
        raise UARTError('bootloader relocation/stack geometry differs')
    if not (0 < kernel_bytes <= 5*1024*1024 and 64 < root_bytes <= 64+16*1024*1024 and
            0x42000000+kernel_bytes < ROOT_HEADER and ROOT_HEADER+root_bytes <= ROOT_LIMIT):
        raise UARTError('payload lies outside its separate RAM window')
    return fields


def validate_boot(boot):
    command_lines = re.findall(rb'Kernel command line: ([^\r\n]*)', boot)
    if len(command_lines) != 1:
        raise UARTError('ambiguous normal kernel command line')
    tokens = command_lines[0].split()
    required = (b'console=ttyAMA0,115200n8', b'earlycon=zteuart,0x94404000',
                b'clk_ignore_unused', b'root=/dev/ram0', b'rootfstype=squashfs',
                b'ro', b'panic=0', b'spi_zx279128.ubi_test=1', b'spinand.diagnostic_write_guard=1')
    if len(tokens) != len(required) or set(tokens) != set(required):
        raise UARTError('normal qualification kernel command line differs')
    needed = (b'RAMDISK: squashfs filesystem found', b'VFS: Mounted root (squashfs filesystem)',
              b'Run /sbin/init as init process', READY, MOUNTED,
              b'L2C-310 enabling early BRESP for Cortex-A9',
              b'UBI WRITE TEST: bytes [05400000,06400000), rows [a800,c800), aligned erase only',
              b'diagnostic mutation guard: no bad-block marking; stop on write/erase failure')
    if not all(marker in boot for marker in needed):
        raise UARTError('normal RAM root, init or guarded overlay boot marker missing')
    if boot.count(READY) != 1 or boot.count(MOUNTED) != 1 or boot.index(READY) >= boot.index(MOUNTED):
        raise UARTError('ambiguous or reordered overlay startup markers')
    if re.search(rb'H199A_OVERLAY_FAILED|Kernel panic|Run /bin/sh as init|switching to ramoverlay|fallback to ramoverlay', boot):
        raise UARTError('normal boot entered a failure or fallback path')
    return {'normal_init': True, 'ram_lower': True, 'guarded_overlay_mounted': True,
            'pl310_started_disabled': True}


def framed_query(nonce, label, body):
    if not re.fullmatch(r'[a-f0-9]{12}', nonce) or not re.fullmatch(r'[A-Z]+', label):
        raise ValueError('bounded query identifiers required')
    begin, end = f'H199A_{label}_BEGIN_{nonce}', f'H199A_{label}_END_{nonce}'
    command = f"printf '\\n{begin}\\n'; "+body+f"; printf '{end}\\n'"
    if len(command) > 500:
        raise ValueError('normal runtime query exceeds console limit')
    return command.encode(), begin.encode(), end.encode()


def frame_lines(response, begin, end):
    data = response.replace(b'\r', b'')
    start, finish = b'\n'+begin+b'\n', b'\n'+end+b'\n'
    if data.count(start) != 1 or data.count(finish) != 1:
        raise UARTError('ambiguous normal runtime query evidence')
    if data.index(finish) <= data.index(start):
        raise UARTError('normal runtime query markers are out of order')
    return data.split(start, 1)[1].split(finish, 1)[0].splitlines()


def runtime_queries(nonce):
    bodies = {
        'NAMES': 'for i in 1 2 3 4 5 6 7 8 9 10 11 12 13; do cat /sys/class/mtd/mtd$i/name; done',
        'WINDOW': 'for f in offset size erasesize writesize oobsize type; do cat /sys/class/mtd/mtd13/$f; done',
        'GUARDS': 's=/sys/module; cat $s/spi_zx279128/parameters/ubi_test $s/spi_zx279128/parameters/write_test '
                  '$s/spinand/parameters/diagnostic_write_guard; for d in /sys/bus/spi/drivers/spi-nand '
                  '/sys/bus/platform/drivers/zx279128-spifc; do test -d $d -a ! -e $d/bind -a ! -e $d/unbind && echo NO_REBIND; done',
        'VOLUME': 'for p in /sys/class/ubi/ubi[0-9]*; do echo ${p##*/}; done; '
                  'cat /sys/class/ubi/ubi0/mtd_num /sys/class/ubi/ubi0_0/name '
                  '/sys/class/ubi/ubi0_0/type /sys/class/ubi/ubi0_0/reserved_ebs',
        'MOUNTS': 'boot_hook_add(){ :; }; . /rom/lib/preinit/79_h199a_overlay; '
                  'h199a_overlay_mount_check && echo MOUNTS_OK; cat /proc/1/comm; '
                  'test ! -e /tmp/failsafe -a ! -e /tmp/.failsafe && echo NO_FAILSAFE',
        'STATE': 'readlink /overlay/.fs_state || echo ABSENT',
    }
    return {label: framed_query(nonce, label, body) for label, body in bodies.items()}


def validate_runtime(label, lines):
    expected = {
        'NAMES': b'bootloader tag wifi usercfg defcfg kernel1 rootfs header kernel2 rootfs2 legacy_overlay staging overlay_ubi'.split(),
        'WINDOW': b'88080384 16777216 131072 2048 128 nand'.split(),
        'GUARDS': b'Y N Y NO_REBIND NO_REBIND'.split(),
        'VOLUME': b'ubi0 ubi0_0 13 rootfs_data dynamic 104'.split(),
        'MOUNTS': b'MOUNTS_OK procd NO_FAILSAFE'.split(),
    }
    if label == 'STATE':
        if len(lines) != 1 or lines[0] not in (b'ABSENT', b'0', b'1', b'2'):
            raise UARTError('unexpected fstools readiness state')
        return lines == [b'2']
    if label not in expected or lines != expected[label]:
        raise UARTError('normal runtime check failed: '+label)
    return True


# ---- production-policy qualification (BOOT_PROFILE=production PRODUCTION_QUALIFY=1)
# A RAM-root image carrying the production write policy in qualification mode.
# Bank A is writable at the MTD layer and so is the partitioned master, so every
# refusal observed on hardware is proof of the transport allowlist (layer 2)
# alone. No overlay hook acts in this image: it runs on a tmpfs overlay and never
# attaches the owner's rootfs_data.
QUALIFY_TOKENS = (b'console=ttyAMA0,115200n8', b'earlycon=zteuart,0x94404000',
                  b'clk_ignore_unused', b'spi_zx279128.production_qualify=1',
                  b'root=/dev/ram0', b'rootfstype=squashfs', b'ro', b'panic=0')
QUALIFY_POLICY_MARKER = (b'PRODUCTION POLICY QUALIFICATION: program/erase only UBI '
                         b'[05400000,06400000); bank A [00700000,01740000) refused; '
                         b'first refusal latches')
QUALIFY_WRITABLE = frozenset({0, 6, 7, 8, 13})  # master, kernel1, rootfs, header, overlay_ubi
QUALIFY_STATE_IDLE = b'mode=production-qualify latched=0 refusals=0 bank_a_refusals=0 first_opcode=00 first_addr=0'


def validate_production_qualify_boot(boot):
    command_lines = re.findall(rb'Kernel command line: ([^\r\n]*)', boot)
    if len(command_lines) != 1:
        raise UARTError('ambiguous qualification kernel command line')
    tokens = command_lines[0].split()
    if len(tokens) != len(QUALIFY_TOKENS) or set(tokens) != set(QUALIFY_TOKENS):
        raise UARTError('production-qualify kernel command line differs')
    needed = (b'RAMDISK: squashfs filesystem found', b'VFS: Mounted root (squashfs filesystem)',
              b'Run /sbin/init as init process', b'L2C-310 enabling early BRESP for Cortex-A9',
              QUALIFY_POLICY_MARKER)
    if not all(marker in boot for marker in needed) or boot.count(QUALIFY_POLICY_MARKER) != 1:
        raise UARTError('production-qualify RAM root, init or write-policy marker missing')
    if re.search(rb'H199A_OVERLAY_(READY|MOUNTED|FAILED)|H199A_PROD_OVERLAY|Kernel panic|'
                 rb'Run /bin/sh as init|ubi0: attaching|UBI WRITE TEST|diagnostic mutation guard|'
                 rb'write policy (denied|refused)', boot):
        raise UARTError('qualification boot attached storage, took a diagnostic path or refused early')
    return {'production_qualify_init': True, 'ram_lower': True, 'policy_marker': True,
            'no_overlay_attach': True, 'pl310_started_disabled': True}


def expected_policy_map(active, bank=0):
    """Independent spec model of the transport's write_policy_map text.

    Written from the published ranges, not from the C code, so agreement between
    the two (tests/test_production_qualify.py and the live board) is evidence that
    both are right rather than that one was copied from the other.
    """
    firmware = {0: (0x0e00, 0x2e80), 1: (0x4000, 0x6080)}.get(bank, (0, 0))
    ubi, rows, block, cfg_mode = (0xa800, 0xc800), 0x10000, 64, 0xe2

    def verdict(qualify, erase, row):
        if erase and row % block:
            return 'deny'
        if ubi[0] <= row < ubi[1]:
            return 'allow'
        if firmware[0] <= row < firmware[1]:
            return 'refuse-bank-a' if qualify else 'allow'
        return 'deny'

    out = [f'zx279128 write policy v1 active={active}']
    for qualify in (False, True):
        out.append('flavour ' + ('production-qualify' if qualify else 'production'))
        for name, erase in (('program', False), ('erase', True)):
            first, run = 0, None
            for row in range(0, rows, block if erase else 1):
                v = verdict(qualify, erase, row)
                if run is not None and v != run:
                    out.append(f'{name} {first * 2048:08x}-{row * 2048 - 1:08x} {run}')
                    first = row
                run = v
            out.append(f'{name} {first * 2048:08x}-{rows * 2048 - 1:08x} {run}')
        allowed = [v for v in range(256) if not v & cfg_mode]
        cfg_or = 0
        for v in allowed:
            cfg_or |= v
        out += ['erase-unaligned non-deny=0', 'row-alias non-deny=0', 'feature a0 allowed=1 or=00',
                f'feature b0 allowed={len(allowed)} or={cfg_or:02x}', 'feature other allowed=0']
    return '\n'.join(out) + '\n'


def production_qualify_queries(nonce):
    # Typed into the interactive login shell: never `exit` (it would log the
    # console out). A missing or ambiguous attribute prints a marker instead,
    # which fails validation closed.
    def policy(files):
        return ('set -- /sys/bus/platform/devices/*/write_policy_state; '
                'if [ $# -eq 1 ] && [ -e "$1" ]; then cat ' + files + '; else echo POLICY_ATTR_MISSING; fi')
    bodies = {
        'NAMES': 'for i in 1 2 3 4 5 6 7 8 9 10 11 12 13; do cat /sys/class/mtd/mtd$i/name; done',
        'POLICY': policy('"${1%_state}" "$1"'),
        'MAP': policy('"${1%_state}_map"'),
        'MOUNTS': 'test -e /sys/class/ubi/ubi0 && echo UBI_ATTACHED || echo NO_UBI; '
                  'awk \'$2 == "/overlay" {print $3}\' /proc/mounts; cat /proc/1/comm; '
                  'test ! -e /tmp/failsafe -a ! -e /tmp/.failsafe && echo NO_FAILSAFE',
    }
    return {label: framed_query(nonce, label, body) for label, body in bodies.items()}


def validate_production_qualify_runtime(label, lines):
    expected = {
        'NAMES': b'bootloader tag wifi usercfg defcfg kernel1 rootfs header kernel2 rootfs2 legacy_overlay staging overlay_ubi'.split(),
        'POLICY': [b'production-qualify', QUALIFY_STATE_IDLE],
        'MAP': expected_policy_map('production-qualify').encode().splitlines(),
        # Observed on hardware 2026-11-15: fstools tries an ext4 overlay on a loop
        # device backed by the RAM disk, ext4 is absent, so NO overlay is mounted
        # (read-only SquashFS root, /tmp in RAM). Either way the real overlay is
        # never touched; anything else (incl. a tmpfs overlay) fails closed.
        'MOUNTS': [b'NO_UBI', b'procd', b'NO_FAILSAFE'],
    }
    if label not in expected or lines != expected[label]:
        raise UARTError('production-qualify runtime check failed: ' + label)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rootfs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    data = make_envelope(args.rootfs.read_bytes())
    root = parse_envelope(data)
    with args.output.open('xb') as stream:
        stream.write(data)
    print(json.dumps({'path': str(args.output.resolve()), 'bytes': len(data),
                      'sha256': hashlib.sha256(data).hexdigest(),
                      'header_address': ROOT_HEADER, 'payload_address': ROOT_START,
                      'payload_bytes': root.payload_bytes, 'never_execute': True}))


if __name__ == '__main__':
    main()
