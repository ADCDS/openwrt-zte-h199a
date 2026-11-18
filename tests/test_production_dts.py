"""Compile the H199A device-tree variants and assert the write-permission map.

Layer 1 of the production write policy is the device tree: only bank A
(kernel1/rootfs/header) and the UBI overlay window are writable; everything else
is read-only, and the partitioned master is read-only in the production image.
The RAM-qualification variant is identical except the master stays writable so
the deny matrix can reach the transport. Requires the unpacked kernel tree (for
the dt-bindings include prefixes); skipped otherwise.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DTS_DIR = ROOT / 'files/target/linux/armsr/files-6.6/arch/arm/boot/dts/zte'
INCLUDE_DIR = ROOT / 'files/target/linux/armsr/files-6.6/include'
KTREES = list((ROOT / 'openwrt/build_dir').glob('target-*/linux-armsr_armv7/linux-6.6.151'))

FLASH = '/soc/spi@94406000/flash@0'
PARTS = FLASH + '/partitions'
WRITABLE = {'kernel1', 'rootfs', 'header', 'overlay_ubi'}


@unittest.skipUnless(KTREES and shutil.which('dtc') and shutil.which('fdtget'),
                     'requires the unpacked kernel tree and dtc/fdtget')
class ProductionDtsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ktree = KTREES[0]
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = Path(cls.tmp.name)
        cls.dtb = {}
        for name in ('zx279128s-zte-h199a', 'zx279128s-zte-h199a-production',
                     'zx279128s-zte-h199a-production-qualify'):
            cls.dtb[name] = cls._compile(name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    @classmethod
    def _compile(cls, name):
        pre = cls.out / (name + '.pre')
        dtb = cls.out / (name + '.dtb')
        cpp = subprocess.run([
            'cpp', '-nostdinc', '-x', 'assembler-with-cpp',
            '-I', str(DTS_DIR), '-I', str(INCLUDE_DIR),
            '-I', str(cls.ktree / 'include'),
            '-I', str(cls.ktree / 'scripts/dtc/include-prefixes'),
            '-undef', '-D__DTS__', '-o', str(pre), str(DTS_DIR / (name + '.dts'))],
            capture_output=True, text=True)
        assert cpp.returncode == 0, cpp.stderr
        dtc = subprocess.run(['dtc', '-I', 'dts', '-O', 'dtb', '-i', str(DTS_DIR),
                              '-o', str(dtb), str(pre)], capture_output=True, text=True)
        assert dtc.returncode == 0, dtc.stderr
        return dtb

    def part_map(self, name):
        dtb = self.dtb[name]
        children = subprocess.run(['fdtget', '-l', str(dtb), PARTS],
                                  capture_output=True, text=True, check=True).stdout.split()
        out = {}
        for child in children:
            label = subprocess.run(['fdtget', str(dtb), f'{PARTS}/{child}', 'label'],
                                   capture_output=True, text=True, check=True).stdout.strip()
            ro = subprocess.run(['fdtget', str(dtb), f'{PARTS}/{child}', 'read-only'],
                                capture_output=True).returncode == 0
            reg = subprocess.run(['fdtget', '-t', 'x', str(dtb), f'{PARTS}/{child}', 'reg'],
                                 capture_output=True, text=True, check=True).stdout.strip()
            out[label] = {'ro': ro, 'reg': reg}
        return out

    def has_prop(self, name, node, prop):
        return subprocess.run(['fdtget', str(self.dtb[name]), node, prop],
                              capture_output=True).returncode == 0

    def test_base_dts_is_fully_read_only(self):
        self.assertTrue(self.has_prop('zx279128s-zte-h199a', FLASH, 'read-only'))
        self.assertFalse(self.has_prop('zx279128s-zte-h199a', FLASH, 'partitioned-master-read-only'))
        # Base keeps the raw overlay at 0x4000000 and defines no overlay_ubi.
        parts = self.part_map('zx279128s-zte-h199a')
        self.assertNotIn('overlay_ubi', parts)

    def test_production_writable_set_is_exactly_bank_a_and_overlay(self):
        parts = self.part_map('zx279128s-zte-h199a-production')
        writable = {label for label, info in parts.items() if not info['ro']}
        self.assertEqual(writable, WRITABLE, parts)
        # Master itself is withdrawn; bank A is reachable only via its partitions.
        self.assertFalse(self.has_prop('zx279128s-zte-h199a-production', FLASH, 'read-only'))
        self.assertTrue(self.has_prop('zx279128s-zte-h199a-production', FLASH,
                                      'partitioned-master-read-only'))
        # Geometry the transport allowlist and bootloader both depend on.
        self.assertEqual(parts['kernel1']['reg'], '700000 300000')
        self.assertEqual(parts['rootfs']['reg'], 'a00000 d20000')
        self.assertEqual(parts['header']['reg'], '1720000 20000')
        self.assertEqual(parts['overlay_ubi']['reg'], '5400000 1000000')
        # Bank B and the old raw overlay are read-only and renamed.
        self.assertTrue(parts['kernel2']['ro'] and parts['rootfs2']['ro'])
        self.assertTrue(parts['header2']['ro'])
        self.assertEqual(parts['header2']['reg'], '3020000 20000')
        self.assertTrue(self.has_prop('zx279128s-zte-h199a-production', FLASH, 'zte,bank-aware'))
        self.assertIn('legacy_overlay', parts)
        self.assertTrue(parts['legacy_overlay']['ro'])
        self.assertTrue(parts['staging']['ro'])
        # The rootfs partition is the root device.
        self.assertTrue(self.has_prop('zx279128s-zte-h199a-production',
                                      f'{PARTS}/partition@a00000', 'linux,rootfs'))

    def test_qualify_matches_production_but_master_stays_writable(self):
        prod = self.part_map('zx279128s-zte-h199a-production')
        qual = self.part_map('zx279128s-zte-h199a-production-qualify')
        self.assertEqual({l: v['ro'] for l, v in prod.items()},
                         {l: v['ro'] for l, v in qual.items()})
        self.assertFalse(self.has_prop('zx279128s-zte-h199a-production-qualify', FLASH,
                                       'partitioned-master-read-only'))
        self.assertFalse(self.has_prop('zx279128s-zte-h199a-production-qualify', FLASH, 'read-only'))
        self.assertFalse(self.has_prop('zx279128s-zte-h199a-production-qualify', FLASH, 'zte,bank-aware'))

    def test_mtd_numbering_is_preserved(self):
        # overlay_ubi remains mtd13; the new inactive header is appended mtd14.
        for name in ('zx279128s-zte-h199a-production', 'zx279128s-zte-h199a-production-qualify'):
            labels = list(self.part_map(name).keys())
            self.assertEqual(labels[12:], ['overlay_ubi', 'header2'])
            self.assertEqual(labels[:6],
                             ['bootloader', 'tag', 'wifi', 'usercfg', 'defcfg', 'kernel1'])


if __name__ == '__main__':
    unittest.main()
