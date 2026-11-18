"""Exercise the packaged header preparer with both banks and unsafe inputs."""
from pathlib import Path
import struct
import subprocess
import tempfile
import unittest
import zlib

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'files/package/utils/h199a-upgrade/src/h199a-upgrade-header.c'


def kernel_image(bank_aware=True, duplicate_property=False, duplicate_node=False, slash_node=False):
    strings = b'compatible\0zte,boot-bank\0zte,bank-aware\0'
    block = bytearray()

    def word(value):
        block.extend(struct.pack('>I', value))

    def align():
        block.extend(bytes((-len(block)) % 4))

    def node(name):
        word(1)
        block.extend(name.encode() + b'\0')
        align()

    def prop(name, value):
        word(3)
        word(len(value))
        word(strings.index(name.encode() + b'\0'))
        block.extend(value)
        align()

    node('')
    prop('compatible', b'zte,zxhn-h199a\0zte,zx279128s\0')
    node('chosen')
    prop('zte,boot-bank', struct.pack('>I', 0xffffffff))
    word(2)
    if duplicate_node:
        node('chosen')
        prop('zte,boot-bank', struct.pack('>I', 0xffffffff))
        word(2)
    if slash_node:
        node('soc/spi@94406000')
    else:
        node('soc')
        node('spi@94406000')
    node('flash@0')
    if bank_aware:
        prop('zte,bank-aware', b'')
        if duplicate_property:
            prop('zte,bank-aware', b'')
    for _ in range(3 if slash_node else 4):
        word(2)
    word(9)
    total = 56 + len(block) + len(strings)
    dt = struct.pack('>10I', 0xd00dfeed, total, 56, 56 + len(block), 40,
                     17, 16, 0, len(strings), len(block)) + bytes(16) + block + strings
    zimage = bytearray(64)
    struct.pack_into('<III', zimage, 36, 0x016f2818, 0, len(zimage))
    payload = bytes(zimage) + dt
    uimage = bytearray(64)
    struct.pack_into('>7I', uimage, 0, 0x27051956, 0, 0, len(payload),
                     0x40008000, 0x40008000, zlib.crc32(payload))
    uimage[28:32] = bytes((5, 2, 2, 0))
    struct.pack_into('>I', uimage, 4, zlib.crc32(uimage))
    image = struct.pack('<4I', 0x33333333, 0xcccccccc, 0x88888888, 0xdddddddd)
    image += b'\xff' * 16 + uimage + payload
    return image.ljust(0x300000, b'\0')


def seal(header):
    struct.pack_into('<I', header, 0xa4, zlib.crc32(header[:0xa4]))
    struct.pack_into('<I', header, 0x1fc, zlib.crc32(header[:0x1fc]))
    return header


def header(bank, serial):
    h = bytearray(b'\xa5' * 0x20000)
    h[:512] = bytes(512)
    for offset, value in ((8, 0x266), (0x34, 0x2ffdcc), (0x38, 0x234),
                          (0x40, 0xd20000), (0x44, 0x300214),
                          (0xf4, 0x33333333), (0xf8, 0x66666666),
                          (0xfc, 0x99999999), (0x100, 0xcccccccc),
                          (0x1e0, 0x700000), (0x1e4, 0x2000000),
                          (0x1e8, 0x2000000), (0x1ec, 0x3900000),
                          (0x1f0, 0x700000 if bank == 'a' else 0x2000000),
                          (0x1f4, serial), (0x1f8, 1)):
        struct.pack_into('<I', h, offset, value)
    h[0x6c:0x76] = b'ZXHN H199A'
    return seal(h)


class UpgradeHeaderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.build.name) / 'header-prep'
        built = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                str(SOURCE), '-o', str(cls.binary)], capture_output=True, text=True)
        if built.returncode:
            raise RuntimeError(built.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.current = self.work / 'current'
        self.backup = self.work / 'backup'
        self.kernel = self.work / 'kernel'
        self.rootfs = self.work / 'rootfs'
        self.output = self.work / 'next'
        for path, size in ((self.kernel, 0x300000), (self.rootfs, 0xd20000)):
            with path.open('wb') as f:
                f.truncate(size)
        self.kernel.write_bytes(kernel_image())

    def prepare(self, bank='a', serial=3, peer=4):
        self.current.write_bytes(header(bank, serial))
        self.backup.write_bytes(header('b' if bank == 'a' else 'a', peer))

    def run_tool(self, bank='a'):
        return subprocess.run([str(self.binary), bank, str(self.current), str(self.backup),
                               str(self.kernel), str(self.rootfs), str(self.output)],
                              capture_output=True, text=True)

    def test_both_banks_keep_identity_and_outrank_backup(self):
        for bank in ('a', 'b'):
            with self.subTest(bank=bank):
                self.prepare(bank, serial=7, peer=99)
                original = self.current.read_bytes()
                run = self.run_tool(bank)
                self.assertEqual(run.returncode, 0, run.stderr)
                out = self.output.read_bytes()
                self.assertEqual(struct.unpack_from('<I', out, 0x1f4)[0], 100)
                self.assertEqual(struct.unpack_from('<I', out, 0x1f0)[0],
                                 0x700000 if bank == 'a' else 0x2000000)
                kernel = self.kernel.read_bytes()
                self.assertEqual(struct.unpack_from('<I', out, 0x3c)[0],
                                 zlib.crc32(kernel[0x20:0x20 + 0x2ffdcc]))
                self.assertEqual(struct.unpack_from('<I', out, 0x48)[0],
                                 zlib.crc32(self.rootfs.read_bytes()))
                for offset in (0xa4, 0x1fc):
                    self.assertEqual(struct.unpack_from('<I', out, offset)[0],
                                     zlib.crc32(out[:offset]))
                allowed = set()
                for start in (0x3c, 0x48, 0xa4, 0x1f0, 0x1f4, 0x1f8, 0x1fc):
                    allowed.update(range(start, start + 4))
                self.assertFalse({i for i, (a, b) in enumerate(zip(original, out))
                                  if a != b} - allowed)
                self.assertEqual(self.current.read_bytes(), original)
                self.output.unlink()

    def test_wrong_running_bank_refused_before_output(self):
        self.prepare('a')
        run = self.run_tool('b')
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_bad_current_header_refused(self):
        self.prepare()
        h = bytearray(self.current.read_bytes())
        h[0x180] ^= 1
        self.current.write_bytes(h)
        self.assertNotEqual(self.run_tool().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_peer_with_bad_extended_crc_still_sets_bootloader_serial_ceiling(self):
        self.prepare(serial=8, peer=999)
        h = bytearray(self.backup.read_bytes())
        h[0x180] ^= 1
        self.backup.write_bytes(h)
        run = self.run_tool()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(struct.unpack_from('<I', self.output.read_bytes(), 0x1f4)[0], 1000)

    def test_peer_with_bad_inner_crc_is_not_bootloader_acceptable(self):
        self.prepare(serial=8, peer=999)
        h = bytearray(self.backup.read_bytes())
        h[0x20] ^= 1
        self.backup.write_bytes(h)
        run = self.run_tool()
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(struct.unpack_from('<I', self.output.read_bytes(), 0x1f4)[0], 9)

    def test_bank_b_refuses_legacy_kernel_before_creating_output(self):
        self.prepare('b')
        self.kernel.write_bytes(kernel_image(bank_aware=False))
        run = self.run_tool('b')
        self.assertNotEqual(run.returncode, 0)
        self.assertFalse(self.output.exists())

    def test_bank_a_keeps_legacy_kernel_compatibility(self):
        self.prepare('a')
        self.kernel.write_bytes(kernel_image(bank_aware=False))
        run = self.run_tool('a')
        self.assertEqual(run.returncode, 0, run.stderr)

    def test_corrupted_uimage_refused_before_creating_output(self):
        self.prepare()
        image = bytearray(self.kernel.read_bytes())
        image[120] ^= 1
        self.kernel.write_bytes(image)
        self.assertNotEqual(self.run_tool().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_preflight_checks_both_banks_without_reading_or_writing_headers(self):
        for aware in (False, True):
            self.kernel.write_bytes(kernel_image(bank_aware=aware))
            for bank in ('a', 'b'):
                run = subprocess.run([str(self.binary), '--check-kernel', bank, str(self.kernel)],
                                     capture_output=True, text=True)
                self.assertEqual(run.returncode, 0 if aware or bank == 'a' else 1, run.stderr)
                self.assertFalse(self.output.exists())
                self.assertFalse(self.current.exists())

    def test_duplicate_capability_entries_and_slash_nodes_are_refused(self):
        self.prepare('b')
        for change in ('duplicate_property', 'duplicate_node', 'slash_node'):
            with self.subTest(change=change):
                self.kernel.write_bytes(kernel_image(**{change: True}))
                self.assertNotEqual(self.run_tool('b').returncode, 0)
                self.assertFalse(self.output.exists())

    def test_serial_wrap_refused(self):
        self.prepare(peer=0x7fffffff)
        self.assertNotEqual(self.run_tool().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_short_payload_refused(self):
        self.prepare()
        self.kernel.write_bytes(b'short')
        self.assertNotEqual(self.run_tool().returncode, 0)
        self.assertFalse(self.output.exists())

    def test_existing_output_and_symlink_are_never_overwritten(self):
        self.prepare()
        original = self.current.read_bytes()
        self.output.symlink_to(self.current)
        self.assertNotEqual(self.run_tool().returncode, 0)
        self.assertEqual(self.current.read_bytes(), original)
        self.output.unlink()
        self.output.write_bytes(b'keep-existing-output')
        self.assertNotEqual(self.run_tool().returncode, 0)
        self.assertEqual(self.output.read_bytes(), b'keep-existing-output')
