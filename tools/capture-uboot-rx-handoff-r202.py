#!/usr/bin/env python3
"""PARENT-ONLY hardware reader: snapshot H199A U-Boot RX handoff after final TFTP.

Only bdinfo and small md.l reads inside verified DRAM are issued. No network
traffic, boot, writes, environment changes, or Linux memory reads. The resulting
cursor is specific to this handoff; never reuse it after another receive/TFTP.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
RIG = ROOT.parent
BACKUP_SHA = '559864fe931dcd66ec891823bd945f4469bdcf72e8490e6257b064d7197440c4'
LINK_BASE = 0x47edf800
LINK_RX_CODE = 0x47f2ff24
LINK_RX_TABLE = 0x47f5a648


def words(text):
    result = {}
    for match in re.finditer(r'^([0-9a-fA-F]{8}):((?: [0-9a-fA-F]{8}){1,4})(?:\s|$)', text, re.M):
        for i, value in enumerate(match[2].split()):
            addr = int(match[1], 16) + i * 4
            if addr in result:
                raise ValueError('duplicate memory address in one response')
            result[addr] = int(value, 16)
    return result


def decode_descriptor(values):
    if len(values) != 4:
        raise ValueError('descriptor requires exactly four words')
    d = struct.pack('<4I', *values)
    return {'words': [f'{v:08x}' for v in values],
            'buffer': (d[7] >> 1) | (d[8] << 7), 'pool': d[9] & 1,
            'length': (int.from_bytes(d[12:14], 'little') >> 2) & 0x3fff}


def capture(run, backup=None):
    info = run('bdinfo')
    def field(name):
        match = re.search(r'^' + re.escape(name) + r'\s*=\s*0x([0-9a-fA-F]+)', info, re.M)
        if not match:
            raise ValueError('missing bdinfo field: ' + name)
        return int(match[1], 16)
    start, size, reloc, offset = (field(n) for n in ('-> start', '-> size', 'relocaddr', 'reloc off'))
    if start != 0x40000000 or size != 0x08000000 or reloc != 0x47f00000 + offset:
        raise ValueError('unexpected RAM/relocation; do not guess linked addresses')
    def read(addr, count):
        if not 1 <= count <= 16 or addr % 4 or addr < start or addr + count * 4 > start + size:
            raise ValueError('read is not a bounded aligned DRAM read')
        result = words(run(f'md.l 0x{addr:08x} 0x{count:x}'))
        expected = [addr+i*4 for i in range(count)]
        if set(result) != set(expected):
            raise ValueError('incomplete/unexpected memory response')
        return [result[a] for a in expected]
    if backup is None:
        backup = (RIG / 'h199a-firmware/mtd0-bootloader.bin').read_bytes()
    if hashlib.sha256(backup).hexdigest() != BACKUP_SHA:
        raise ValueError('unexpected H199A backup identity')
    code = read(LINK_RX_CODE + offset, 16)
    pos = LINK_RX_CODE - LINK_BASE
    if struct.pack('<16I', *code) != backup[pos:pos+64]:
        raise ValueError('running relocated RX code does not match verified backup')
    table_address = LINK_RX_TABLE + offset
    table = read(table_address, 16)
    queues = []
    for q in range(8):
        base, cursor = table[q*2:q*2+2]
        if base != 0x41a00000 + q * 0x10000 or not 0 <= cursor < 1024:
            raise ValueError('unexpected RX table geometry/cursor')
        queues.append({'queue': q, 'base': f'0x{base:08x}', 'next_cursor': cursor})
    cursor = queues[0]['next_cursor']
    descriptors = {}
    for role, slot in [('zero', 0), ('previous', (cursor-1) % 1024), ('next', cursor)]:
        address = 0x41a00000 + slot * 16
        descriptors[role] = {'slot': slot, 'address': f'0x{address:08x}', **decode_descriptor(read(address, 4))}
    if read(table_address, 16) != table:
        raise ValueError('RX cursor table changed during capture; handoff is not stable')
    return {'relocaddr': hex(reloc), 'reloc_off': hex(offset),
            'runtime_code_address': hex(LINK_RX_CODE+offset), 'runtime_table_address': hex(table_address),
            'code_matches_64_backup_bytes': True, 'table_stable_across_reads': True,
            'queue0_next_cursor': cursor, 'queues': queues, 'descriptors': descriptors,
            'scope': 'Software next-consumer table in working U-Boot, not a hardware producer-index read.',
            'freshness': 'Invalidated by another U-Boot receive/network operation; re-read after FINAL TFTP.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-prefix', type=Path, required=True)
    args = parser.parse_args()
    output = Path(str(args.output_prefix) + '.json')
    log = Path(str(args.output_prefix) + '.log')
    if output.exists() or log.exists():
        parser.error('output exists; select a new handoff prefix')
    with log.open('x') as transcript:
        def run(command):
            if not (command == 'bdinfo' or re.fullmatch(r'md\.l 0x[0-9a-f]{8} 0x[0-9a-f]+', command)):
                raise ValueError('non-read command rejected')
            result = subprocess.run([str(RIG / 'ub.sh'), command, '2'], capture_output=True, text=True, check=True)
            transcript.write(result.stdout)
            transcript.flush()
            return result.stdout
        result = capture(run)
    with output.open('x') as target:
        json.dump(result, target, indent=2)
        target.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
