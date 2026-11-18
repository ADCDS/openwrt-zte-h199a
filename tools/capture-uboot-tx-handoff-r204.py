#!/usr/bin/env python3
"""Parent-only bounded DRAM observer of vendor RX and TX software origins.

Extends the verified R202 reader; no MMIO, network, writes, boot, or live Linux
access. A vendor software cursor is NOT a hardware cursor or a post-reset seed.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import struct
import subprocess

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('rx_handoff_r202', ROOT / 'tools/capture-uboot-rx-handoff-r202.py')
reader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reader)
LINK_TX_CODE = 0x47f30268
# SHA-bound H backup relocation record at file0x7092c targets this literal
# with R_ARM_RELATIVE(0x17); live literal must identify state+reloc_off.
LINK_STATE_LITERAL = 0x47f302c4
LINK_STATE = 0x47f5a640


def capture(run, backup=None):
    if backup is None:
        backup = (reader.RIG / 'h199a-firmware/mtd0-bootloader.bin').read_bytes()
    result = reader.capture(run, backup)  # RAM/relocation, backup SHA and RX checks
    offset = int(result['reloc_off'], 16)

    def read(address, count):
        if not 1 <= count <= 16 or address % 4 or not 0x40000000 <= address < address + count * 4 <= 0x48000000:
            raise ValueError('TX observation outside bounded aligned DRAM')
        values = reader.words(run(f'md.l 0x{address:08x} 0x{count:x}'))
        expected = [address + 4 * i for i in range(count)]
        if set(values) != set(expected):
            raise ValueError('incomplete/unexpected TX memory response')
        return [values[a] for a in expected]

    code_address = LINK_TX_CODE + offset
    pos = LINK_TX_CODE - reader.LINK_BASE
    if struct.pack('<8I', *read(code_address, 8)) != backup[pos:pos + 32]:
        raise ValueError('relocated TX instruction window differs from H backup')
    state = LINK_STATE + offset
    if read(LINK_STATE_LITERAL + offset, 1) != [state]:
        raise ValueError('TX state literal does not identify the expected relocated state')
    address = state + 0x54
    first = read(address, 2)
    if not 0 <= first[0] < 1024 or first[1] != 0x41c00000:
        raise ValueError('unexpected vendor software TX origin/base')
    if read(address, 2) != first:
        raise ValueError('vendor software TX state changed during observation')
    result.update(tx_software_cursor=first[0], tx_base=hex(first[1]),
                  tx_state_address=hex(address), tx_code_address=hex(code_address),
                  tx_code_32_bytes_match=True, tx_state_literal_verified=True,
                  tx_state_stable=True,
                  scope='Vendor software RX consumer and TX writer state, not hardware origins; do not apply after reset.')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-prefix', type=Path, required=True)
    args = parser.parse_args()
    output = Path(str(args.output_prefix) + '.json')
    log = Path(str(args.output_prefix) + '.log')
    if output.exists() or log.exists():
        parser.error('output already exists; select a new observation prefix')
    with log.open('x') as transcript:
        def run(command):
            if command != 'bdinfo' and not re.fullmatch(r'md\.l 0x[0-9a-f]{8} 0x[0-9a-f]+', command):
                raise ValueError('non-read command rejected')
            value = subprocess.run([str(reader.RIG / 'ub.sh'), command, '2'],
                                   capture_output=True, text=True, check=True).stdout
            transcript.write(value)
            transcript.flush()
            return value
        result = capture(run)
    with output.open('x') as target:
        json.dump(result, target, indent=2)
        target.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
