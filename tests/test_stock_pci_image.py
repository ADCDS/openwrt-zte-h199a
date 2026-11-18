"""Fixed-layout RAM patches must suppress registration without touching the rest."""
import gzip
import hashlib
import importlib.util
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
import zlib

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stock = load('stock_pci_image_test', 'stock-pci-image.py')
ramboot = load('stock_pci_ramboot_test', 'ramboot-h199a-tftp.py')


class StockPciImageTests(unittest.TestCase):
    def setUp(self):
        raw = bytearray(stock.RAW_SIZE)
        for offset, old, _, _ in stock.PATCHES:
            raw[offset:offset+len(old)] = old
        for offset, value in stock.INITCALLS:
            struct.pack_into('<I', raw, offset, value)
        self.raw = bytes(raw)
        packed = gzip.compress(self.raw, mtime=0)
        packed = packed[:3]+b'\x08'+packed[4:10]+b'R'*4095+b'\0'+packed[10:]
        payload = b'P'*(stock.GZIP_OFFSET-96)+packed+b'unchanged-appended-dtb'
        header = bytearray(struct.pack('>7I4B32s', 0x27051956, 0, 0, len(payload),
                           0x40008000, 0x40008000, zlib.crc32(payload), 5, 2, 2, 0, b'stock'))
        struct.pack_into('>I', header, 4, zlib.crc32(header))
        self.source = (b'Z'*32+header+payload).ljust(3*1024*1024, b'\xff')
        self.patch1 = patch.object(stock, 'SOURCE_SHA', hashlib.sha256(self.source).hexdigest())
        self.patch2 = patch.object(stock, 'RAW_SHA', hashlib.sha256(self.raw).hexdigest())
        self.patch1.start()
        self.patch2.start()
        self.addCleanup(self.patch1.stop)
        self.addCleanup(self.patch2.stop)

    def test_only_three_bound_patches_and_all_linked_offsets_preserved(self):
        image, record = stock.prepare(self.source)
        decoder = zlib.decompressobj(31)
        raw = decoder.decompress(image[stock.GZIP_OFFSET:])
        expected = bytearray(self.raw)
        for offset, old, new, _ in stock.PATCHES:
            self.assertEqual(len(old), len(new))
            expected[offset:offset+len(old)] = new
        self.assertEqual(raw, expected)
        self.assertEqual(image[:32], self.source[:32])
        self.assertEqual(image[96:stock.GZIP_OFFSET], self.source[96:stock.GZIP_OFFSET])
        end = stock.GZIP_OFFSET + record['gzip_slot_bytes']
        self.assertEqual(image[end:], self.source[end:])
        header = bytearray(image[32:96])
        hcrc = struct.unpack_from('>I', header, 4)[0]
        struct.pack_into('>I', header, 4, 0)
        self.assertEqual(zlib.crc32(header), hcrc)
        size, dcrc = struct.unpack_from('>I', header, 12)[0], struct.unpack_from('>I', header, 24)[0]
        self.assertEqual(zlib.crc32(image[96:96+size]), dcrc)
        self.assertEqual(stock.verify_candidate(image, self.source), record)
        with self.assertRaises(ValueError):
            stock.verify_candidate(image[:-1]+b'X', self.source)

    def test_unidentified_source_and_wrong_patch_anchor_are_rejected(self):
        with self.assertRaises(ValueError):
            stock.prepare(self.source[:-1]+b'X')
        with patch.object(stock, 'PATCHES', ((0x57d660, b'wrong123', bytes(8), 'bad anchor'),)):
            with self.assertRaises(ValueError):
                stock.prepare(self.source)

    def test_expected_panic_requires_exact_128m_readonly_command_line(self):
        panic = b'Kernel panic - not syncing: VFS: Unable to mount root fs on unknown-block(31,8)\r\n'
        boot = b'[0.0] Kernel command line: '+ramboot.STOCK_PCI_ARGS.encode()+b'\r\n'+panic
        self.assertTrue(ramboot.validate_stock_pci_log(boot)['intentional_root_mount_failure'])
        trailer_boot = boot.replace(b'\r\n', ramboot.STOCK_PCI_TRAILER+b'\r\n', 1)
        self.assertTrue(ramboot.validate_stock_pci_log(trailer_boot)['intentional_root_mount_failure'])
        for bad in (boot.replace(b'mem=128M', b'mem=256M'), boot.replace(b'panic=0', b'panic=2'),
                    boot.replace(b' ro ', b' rw '), boot.replace(panic, b''),
                    boot+b'NAND device: found\n', boot+b'Creating 12 MTD partitions\n',
                    trailer_boot.replace(b'0xaf 0xa3', b'0xaf panic=2')):
            with self.assertRaises(ramboot.UARTError):
                ramboot.validate_stock_pci_log(bad)
