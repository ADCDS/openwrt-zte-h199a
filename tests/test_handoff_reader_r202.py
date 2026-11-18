"""Pure fixtures: no serial, sockets or subprocesses are used by these tests."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('handoff_r202', Path(__file__).resolve().parents[1] / 'tools/capture-uboot-rx-handoff-r202.py')
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)


class Fixture:
    def __init__(self, cursor=97):
        self.calls = []
        self.table_reads = 0
        self.change_table = False
        self.info = ('-> start = 0x40000000\n-> size = 0x08000000\n'
                     'relocaddr = 0x47F95000\nreloc off = 0x00095000\n')
        self.code = [0xe59b3000 + i for i in range(16)]
        pos = M.LINK_RX_CODE - M.LINK_BASE
        self.backup = bytes(pos) + struct.pack('<16I', *self.code)
        self.mem = {M.LINK_RX_CODE + 0x95000 + i*4: word for i,word in enumerate(self.code)}
        for q in range(8):
            self.mem[0x47fef648+q*8] = 0x41a00000+q*0x10000
            self.mem[0x47fef64c+q*8] = cursor if q == 0 else 0
        for slot in (0, (cursor-1) % 1024, cursor):
            for i,w in enumerate((0x1bb,0x01180000,0x200bd400,0x002417a8)):
                self.mem[0x41a00000+slot*16+i*4] = w

    def run(self, command):
        self.calls.append(command)
        if command == 'bdinfo':
            return self.info
        _, address, count = command.split()
        address, count = int(address, 0), int(count, 0)
        assert 0x40000000 <= address < address+count*4 <= 0x48000000
        assert count <= 16
        if address == 0x47fef648:
            self.table_reads += 1
            if self.change_table and self.table_reads > 1:
                self.mem[0x47fef64c] += 1
        lines = []
        for i in range(0,count,4):
            vals = [self.mem[address+j*4] for j in range(i,min(i+4,count))]
            lines.append(f'{address+i*4:08x}: ' + ' '.join(f'{v:08x}' for v in vals) + '    ....')
        return '\n'.join(lines) + '\n=> '

    def capture(self):
        with patch.object(M, 'BACKUP_SHA', hashlib.sha256(self.backup).hexdigest()):
            return M.capture(self.run, self.backup)


class HandoffTests(unittest.TestCase):
    def test_verified_relocated_snapshot(self):
        f = Fixture()
        r = f.capture()
        self.assertEqual(r['queue0_next_cursor'], 97)
        self.assertEqual(r['runtime_table_address'], '0x47fef648')
        self.assertEqual(r['descriptors']['next']['length'], 1514)
        self.assertTrue(r['table_stable_across_reads'])
        self.assertTrue(all(c == 'bdinfo' or c.startswith('md.l ') for c in f.calls))

    def test_zero_cursor_previous_wrap(self):
        r = Fixture(0).capture()
        self.assertEqual(r['descriptors']['previous']['slot'], 1023)
        self.assertEqual(r['descriptors']['previous']['address'], '0x41a03ff0')

    def test_wrong_relocation_rejected_before_reads(self):
        f = Fixture()
        f.info = f.info.replace('0x47F95000', '0x47F94000')
        with self.assertRaises(ValueError): f.capture()
        self.assertEqual(f.calls, ['bdinfo'])

    def test_wrong_running_code_rejected_before_table(self):
        f = Fixture()
        f.mem[0x47fc4f24] ^= 1
        with self.assertRaises(ValueError): f.capture()
        self.assertEqual(f.table_reads, 0)

    def test_bad_table_geometry_and_cursor_rejected(self):
        for addr,value in ((0x47fef648,0x41b00000),(0x47fef64c,1024)):
            f = Fixture()
            f.mem[addr] = value
            with self.assertRaises(ValueError): f.capture()

    def test_unstable_table_rejected(self):
        f = Fixture()
        f.change_table = True
        with self.assertRaises(ValueError): f.capture()

    def test_wrong_backup_hash_rejected(self):
        with self.assertRaises(ValueError): M.capture(Fixture().run, b'wrong firmware')

    def test_word_parser_and_descriptor_length(self):
        self.assertEqual(M.words('47fef648: 41a00000 00000061    ...A\n'),
                         {0x47fef648:0x41a00000,0x47fef64c:97})
        with self.assertRaises(ValueError):
            M.words('40000000: 00000000    ....\n40000000: 00000001    ....\n')
        self.assertEqual(M.decode_descriptor([0x19e,0x00180000,0x20007800,0x000400f0])['length'],60)


if __name__ == '__main__':
    unittest.main()
