#!/usr/bin/env python3
"""Pure tests of the TX extension; R202 tests separately cover its RX prerequisite."""
import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('tx_handoff', ROOT / 'tools/capture-uboot-tx-handoff-r204.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

class TxHandoffTests(unittest.TestCase):
    def setUp(self):
        self.offset = 0x95000
        self.state = module.LINK_STATE + self.offset
        self.code = module.LINK_TX_CODE + self.offset
        self.literal = module.LINK_STATE_LITERAL + self.offset
        self.rx = {'reloc_off': hex(self.offset), 'queue0_next_cursor': 97}
        self.backup = bytes(0x100000)
        self.memory = {self.code + 4 * i: 0 for i in range(8)}
        self.memory.update({self.literal: self.state, self.state + 0x54: 98,
                            self.state + 0x58: 0x41c00000})
        self.calls = []
        self.state_reads = 0
        self.mutate = False
        self.extra = False

    def run_read(self, command):
        self.calls.append(command)
        kind, address, count = command.split()
        self.assertEqual(kind, 'md.l')
        address, count = int(address, 16), int(count, 16)
        if address == self.state + 0x54:
            self.state_reads += 1
            if self.mutate and self.state_reads == 2:
                self.memory[address] += 1
        words = [self.memory[address + 4 * i] for i in range(count)]
        output = ''.join(f'{address + i * 4:08x}: ' + ' '.join(f'{w:08x}' for w in words[i:i+4]) + '\n'
                         for i in range(0, count, 4))
        if self.extra:
            output += '40000000: 00000000\n'
        return output

    def capture(self):
        with patch.object(module.reader, 'capture', return_value=dict(self.rx)) as prerequisite:
            result = module.capture(self.run_read, self.backup)
            prerequisite.assert_called_once_with(self.run_read, self.backup)
            return result

    def test_verified_software_state(self):
        result = self.capture()
        self.assertEqual(result['tx_software_cursor'], 98)
        self.assertEqual(result['tx_base'], '0x41c00000')
        self.assertEqual(len(self.calls), 4)
        self.assertTrue(result['tx_state_stable'])
        self.assertIn('not hardware origins', result['scope'])

    def test_code_mismatch_rejected(self):
        self.memory[self.code] ^= 1
        with self.assertRaisesRegex(ValueError, 'instruction window'):
            self.capture()

    def test_unrelocated_literal_rejected(self):
        self.memory[self.literal] = module.LINK_STATE
        with self.assertRaisesRegex(ValueError, 'state literal'):
            self.capture()

    def test_cursor_bounds(self):
        self.memory[self.state + 0x54] = 1024
        with self.assertRaisesRegex(ValueError, 'origin/base'):
            self.capture()

    def test_base_mismatch(self):
        self.memory[self.state + 0x58] = 0x41a00000
        with self.assertRaisesRegex(ValueError, 'origin/base'):
            self.capture()

    def test_stability_required(self):
        self.mutate = True
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.capture()

    def test_extra_memory_response_rejected(self):
        self.extra = True
        with self.assertRaisesRegex(ValueError, 'unexpected TX memory'):
            self.capture()

    def test_outside_dram_never_issued(self):
        self.rx['reloc_off'] = '0x90000000'
        with self.assertRaisesRegex(ValueError, 'bounded aligned DRAM'):
            self.capture()
        self.assertFalse(self.calls)

if __name__ == '__main__':
    unittest.main()
