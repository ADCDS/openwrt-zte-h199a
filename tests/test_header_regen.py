"""The on-device header regeneration must agree with the host tool byte for byte.

tools/flash-prep.py builds the bank-A header on the build host from a template
extracted from one unit. That is what stops a single public image installing on
every unit: the template carries device-specific fields. tools/h199a-header-
regen.c is the same computation running on the board against the board's own
header, so one image works anywhere.

The risk is subtle and expensive: if the two disagree by one bit, the
bootloader rejects the header and the unit does not boot. So this test runs
both over the same synthetic inputs and compares all 128 KiB.

It also pins the three facts the whole thing rests on:
  - the kernel CRC covers kernel[0x20 : 0x20+0x2ffdcc], not the whole partition
  - the filesystem CRC covers a fixed 0xd20000 bytes, not the actual length
  - the self-CRC covers hdr[0:0xa4] and must be computed after the other two
"""
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'tools/h199a-header-regen.c'
FLASH_PREP = ROOT / 'tools/flash-prep.py'

import importlib.util
spec = importlib.util.spec_from_file_location('flash_prep', FLASH_PREP)
flash_prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(flash_prep)

HEADER_BLK = 0x20000
CRC_LEN = 0x2ffdcc
FS_LEN = 0xd20000
KERNEL_SKIP = 0x20


def build_helper(out: Path) -> Path:
    binary = out / 'h199a-header-regen'
    run = subprocess.run(['cc', '-std=gnu11', '-O1', '-Wall', '-Wextra', '-Werror',
                          str(SOURCE), '-o', str(binary)],
                         capture_output=True, text=True)
    if run.returncode:
        raise AssertionError(run.stderr)
    return binary


def synthetic(directory: Path, seed: int):
    """A header block with recognisable device-specific bytes, plus a kernel
    partition and a filesystem image of the sizes the contract names."""
    hdr = bytearray(((i * 7 + seed) & 0xff) for i in range(HEADER_BLK))
    # Mark the fields the tool must NOT touch.
    hdr[0x00:0x10] = b'ZTEH199A-VENDOR!'[:16]
    hdr[0x1f4:0x1f8] = struct.pack('<I', 0xdeadbeef)      # version serial
    hdr[0x1fc:0x200] = struct.pack('<I', 0x0badc0de)      # stale CRC
    kernel = bytearray(((i * 13 + seed) & 0xff) for i in range(0x300000))
    rootfs = bytearray(((i * 3 + seed) & 0xff) for i in range(FS_LEN))
    return hdr, kernel, rootfs


class HeaderRegenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.binary = build_helper(Path(cls.dir.name))

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def run_both(self, hdr, kernel, rootfs):
        d = Path(self.dir.name)
        hdr_p = d / 'header.bin'
        ker_p = d / 'kernel.bin'
        fs_p = d / 'rootfs.bin'
        out_p = d / 'header.out'
        hdr_p.write_bytes(bytes(hdr))
        ker_p.write_bytes(bytes(kernel))
        fs_p.write_bytes(bytes(rootfs))

        # the host tool, as the build uses it
        kcrc = zlib.crc32(bytes(kernel[KERNEL_SKIP:KERNEL_SKIP + CRC_LEN])) & 0xffffffff
        fcrc = zlib.crc32(bytes(rootfs[:FS_LEN])) & 0xffffffff
        expected = flash_prep.patch_header(bytes(hdr), kcrc, fcrc)

        # the device tool
        run = subprocess.run([str(self.binary), str(hdr_p), str(ker_p),
                              str(fs_p), str(out_p)],
                             capture_output=True, text=True)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return expected, out_p.read_bytes(), (kcrc, fcrc)

    def test_agrees_with_the_host_tool_for_a_clean_header(self):
        hdr, kernel, rootfs = synthetic(Path(self.dir.name), 1)
        expected, actual, _ = self.run_both(hdr, kernel, rootfs)
        self.assertEqual(len(actual), HEADER_BLK)
        self.assertEqual(actual, expected)

    def test_agrees_when_the_header_already_has_stale_crcs(self):
        """The unit's header carries CRCs from whatever is installed now; the
        tool must overwrite them, not depend on them being zero."""
        hdr, kernel, rootfs = synthetic(Path(self.dir.name), 2)
        struct.pack_into('<I', hdr, 0x3c, 0x11111111)
        struct.pack_into('<I', hdr, 0x48, 0x22222222)
        struct.pack_into('<I', hdr, 0xa4, 0x33333333)
        expected, actual, _ = self.run_both(hdr, kernel, rootfs)
        self.assertEqual(actual, expected)

    def test_every_other_byte_is_preserved(self):
        hdr, kernel, rootfs = synthetic(Path(self.dir.name), 3)
        before = bytes(hdr)
        _, actual, _ = self.run_both(hdr, kernel, rootfs)
        touched = {0x3c, 0x3d, 0x3e, 0x3f, 0x48, 0x49, 0x4a, 0x4b,
                   0xa4, 0xa5, 0xa6, 0xa7}
        diff = [i for i in range(HEADER_BLK) if actual[i] != before[i]]
        self.assertTrue(set(diff) <= touched,
                        f'the tool changed bytes outside the three CRC words: '
                        f'{[hex(i) for i in diff if i not in touched][:8]}')
        # and the device-specific markers really survived
        self.assertEqual(actual[0x00:0x10], before[0x00:0x10])
        self.assertEqual(actual[0x1f4:0x1f8], before[0x1f4:0x1f8])
        self.assertEqual(actual[0x1fc:0x200], before[0x1fc:0x200])

    def test_the_three_facts_the_contract_rests_on(self):
        """Kernel CRC starts at 0x20 and covers CRC_LEN; the filesystem CRC
        covers a fixed FS_LEN; the self-CRC covers hdr[0:0xa4]."""
        hdr, kernel, rootfs = synthetic(Path(self.dir.name), 4)
        expected, actual, (kcrc, fcrc) = self.run_both(hdr, kernel, rootfs)
        self.assertEqual(struct.unpack_from('<I', actual, 0x3c)[0], kcrc)
        self.assertEqual(struct.unpack_from('<I', actual, 0x48)[0], fcrc)
        self.assertEqual(struct.unpack_from('<I', actual, 0xa4)[0],
                         zlib.crc32(actual[:0xa4]) & 0xffffffff)
        # the kernel CRC is not the whole partition
        whole = zlib.crc32(bytes(kernel)) & 0xffffffff
        self.assertNotEqual(kcrc, whole)

    def test_it_refuses_a_truncated_header(self):
        d = Path(self.dir.name)
        short = d / 'short.bin'
        short.write_bytes(b'\x00' * (HEADER_BLK - 1))
        run = subprocess.run([str(self.binary), str(short), str(short), str(short)],
                             capture_output=True, text=True)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('full', run.stderr + run.stdout)


if __name__ == '__main__':
    unittest.main()
