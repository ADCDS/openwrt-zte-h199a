"""Owner calibration stays private and is checked in the compiled DTB."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import struct
import tarfile
import tempfile
import unittest
import zlib
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('owner_calibration', ROOT / 'tools/h199a-calibration.py')
cal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cal)
FIXTURE = b'\x03\x76' + bytes(range(255)) * 2
DTS = '''/dts-v1/;
/ { soc { pcie@f100000 { pcie@0,0 { wifi2g: wifi@0,0 {
    mediatek,eeprom-merge-otp;
}; }; }; }; };
'''


class OwnerCalibrationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.dts = self.root / 'board.dts'
        self.dts.write_text(DTS)
        self.eeprom = self.root / 'owner-input.bin'
        self.eeprom.write_bytes(FIXTURE)
        self.hash = hashlib.sha256(FIXTURE).hexdigest()
        self.patch = patch.object(cal, 'SUPPORTED_SHA256', self.hash)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def compile(self):
        dtb = self.root / 'board.dtb'
        subprocess.run(['dtc', '-I', 'dts', '-O', 'dtb', '-i', str(self.root),
                        '-o', str(dtb), str(self.dts)], check=True, capture_output=True)
        return dtb

    def archive(self, dtb, duplicate=False, corrupt=False):
        payload = b'fixture kernel' * 20 + dtb
        header = bytearray(struct.pack('>7I4B32s', 0x27051956, 0, 0, len(payload),
                           0x40008000, 0x40008000, zlib.crc32(payload), 5, 2, 2, 0, b'h199a-test'))
        struct.pack_into('>I', header, 4, zlib.crc32(header))
        kernel = (bytes(32) + header + payload).ljust(3 * 1024 * 1024, b'\0')
        if corrupt:
            kernel = kernel[:100] + bytes([kernel[100] ^ 1]) + kernel[101:]
        image = self.root / 'image.tar'
        with tarfile.open(image, 'w') as stream:
            for _ in range(2 if duplicate else 1):
                member = tarfile.TarInfo('h199a/kernel')
                member.size = len(kernel)
                stream.addfile(member, io.BytesIO(kernel))
        return image

    def test_generated_include_and_compiled_blob_match_without_padding(self):
        first = cal.install(self.dts, self.eeprom)
        source = self.dts.read_text()
        self.assertEqual(first['eeprom_bytes'], 512)
        self.assertEqual((self.root / cal.BLOB).read_bytes(), FIXTURE)
        for name in (cal.BLOB, cal.INCLUDE, cal.MANIFEST):
            self.assertEqual((self.root / name).stat().st_mode & 0o777, 0o600)
        cal.install(self.dts, self.eeprom)
        self.assertEqual(self.dts.read_text(), source)
        dtb = self.compile()
        image = self.archive(dtb.read_bytes())
        result = cal.verify(dtb, self.root / cal.MANIFEST, image)
        self.assertEqual(result['eeprom_sha256'], self.hash)
        self.assertTrue(result['merge_otp'] and result['compiled_eeprom_verified'])
        self.assertEqual(result['image_sha256'], hashlib.sha256(image.read_bytes()).hexdigest())
        dtb_only = cal.verify(dtb, self.root / cal.MANIFEST)
        self.assertNotIn('image_sha256', dtb_only)
        self.assertNotIn('packaged_kernel_sha256', dtb_only)

    def test_packaged_kernel_must_contain_the_verified_dtb(self):
        cal.install(self.dts, self.eeprom)
        dtb = self.compile()
        for data, duplicate, corrupt in ((dtb.read_bytes()[:-1]+b'X', False, False),
                                          (dtb.read_bytes(), True, False),
                                          (dtb.read_bytes(), False, True)):
            image = self.archive(data, duplicate, corrupt)
            with self.assertRaises(ValueError):
                cal.verify(dtb, self.root / cal.MANIFEST, image)
        image.write_bytes(b'not a firmware archive')
        with self.assertRaises(tarfile.TarError):
            cal.verify(dtb, self.root / cal.MANIFEST, image)

    def test_clear_removes_private_outputs_and_reference(self):
        cal.install(self.dts, self.eeprom)
        cal.clear(self.dts)
        cal.clear(self.dts)
        self.assertNotIn(cal.INCLUDE, self.dts.read_text())
        for name in (cal.BLOB, cal.INCLUDE, cal.MANIFEST):
            self.assertFalse((self.root / name).exists())
        self.assertEqual(self.eeprom.read_bytes(), FIXTURE)
        self.compile()

    def test_invalid_input_cannot_replace_existing_generated_calibration(self):
        cal.install(self.dts, self.eeprom)
        before = {name: (self.root / name).read_bytes() for name in (cal.BLOB, cal.INCLUDE, cal.MANIFEST)}
        for bad in (FIXTURE[:-1], FIXTURE + b'\0', b'\0\0' + FIXTURE[2:], FIXTURE[:5] + b'X' + FIXTURE[6:]):
            self.eeprom.write_bytes(bad)
            with self.assertRaises(ValueError):
                cal.install(self.dts, self.eeprom)
            self.assertEqual(before, {name: (self.root / name).read_bytes() for name in before})

    def test_final_dtb_must_have_merge_flag_and_exact_input(self):
        cal.install(self.dts, self.eeprom)
        dtb = self.compile()
        subprocess.run(['fdtput', '-d', str(dtb), cal.NODE, 'mediatek,eeprom-merge-otp'], check=True)
        with self.assertRaises(subprocess.CalledProcessError):
            cal.verify(dtb, self.root / cal.MANIFEST)
        dtb = self.compile()
        subprocess.run(['fdtput', '-t', 'bx', str(dtb), cal.NODE, 'mediatek,eeprom-data', '03', '76'], check=True)
        with self.assertRaises(ValueError):
            cal.verify(dtb, self.root / cal.MANIFEST)

    def test_normal_build_refuses_missing_input_before_any_build(self):
        env = os.environ.copy()
        env.update(BOOT_PROFILE='normal', H199A_MT7603_EEPROM='', NAND_ONDIE_PROBE='0',
                   NAND_ONDIE_PROBE_ALL='0', ETH_FORCE_INIT='0', DIAGNOSTIC_RADIOS='0', JOBS='1')
        run = subprocess.run(['bash', 'build.sh'], cwd=ROOT, env=env, capture_output=True, text=True, timeout=10)
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('normal builds require H199A_MT7603_EEPROM', run.stderr)
