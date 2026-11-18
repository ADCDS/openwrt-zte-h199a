"""Native boot acceptance requires explicit protection on every MTD device."""
import importlib.util
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest

TOOLS = Path(__file__).resolve().parents[1] / 'tools'
sys.path.insert(0, str(TOOLS))
spec = importlib.util.spec_from_file_location('native_ramboot_gate', TOOLS/'ramboot-h199a-tftp.py')
ramboot = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ramboot)


class NativeBootGateTests(unittest.TestCase):
    def test_restart_requires_bound_driver_and_shell_profile(self):
        query, begin, end = ramboot.restart_guard_query('0123456789ab')
        self.assertLessEqual(len(query), 500)
        evidence = b'\n'+begin+b'\nRESTART_BOUND\nSHELL_PROFILE\n'+end+b'\n'
        self.assertTrue(ramboot.validate_restart_guard(evidence, begin, end)['driver_bound'])
        for invalid in (evidence.replace(b'RESTART_BOUND\n', b''),
                        evidence.replace(b'SHELL_PROFILE\n', b''), evidence+evidence):
            with self.assertRaises(ramboot.UARTError):
                ramboot.validate_restart_guard(invalid, begin, end)

    def setUp(self):
        self.query, self.begin, self.end = ramboot.native_readonly_query('0123456789ab')

    def response(self, entries=None, geometry=b'134217728\r\n2048\r\n128\r\n'):
        if entries is None:
            entries = [f'mtd{i} 0x0'.encode() for i in range(13)]
        return (self.query+b'\r\n\r\n'+self.begin+b'\r\n'+
                b'\r\n'.join(entries)+b'\r\nGEOMETRY\r\n'+geometry+self.end+b'\r\n')

    def test_readonly_master_and_every_partition_with_native_geometry(self):
        result = ramboot.validate_native_mtd(self.response(), self.begin, self.end)
        self.assertEqual(result['oob'], 128)
        self.assertEqual(set(result['flags']), set(range(13)))
        self.assertLessEqual(len(self.query), 500)

    def test_query_skips_readonly_character_aliases_without_flags(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for i in range(13):
                node = root/f'mtd{i}'
                node.mkdir()
                (node/'flags').write_text('0x0\n')
                (root/f'mtd{i}ro').mkdir()
            for name, value in (('size', 134217728), ('writesize', 2048), ('oobsize', 128)):
                (root/'mtd0'/name).write_text(str(value)+'\n')
            # Exercise the actual query body without its real mount/printk prefix.
            query = self.query.decode()
            query = query[query.index("printf '\\n"):].replace('/sys/class/mtd/', str(root)+'/')
            result = subprocess.run(['sh', '-c', query], capture_output=True, check=True)
            self.assertEqual(result.stderr, b'')
            parsed = ramboot.validate_native_mtd(result.stdout, self.begin, self.end)
            self.assertEqual(len(parsed['flags']), 13)

    def test_any_writable_device_is_rejected(self):
        for writable in range(13):
            entries = [f'mtd{i} 0x{0x400 if i==writable else 0:x}'.encode() for i in range(13)]
            with self.subTest(writable=writable), self.assertRaises(ramboot.UARTError):
                ramboot.validate_native_mtd(self.response(entries), self.begin, self.end)

    def test_missing_duplicate_or_malformed_evidence_is_rejected(self):
        for entries in ([b'mtd0 0x0'],
                        [f'mtd{i} 0x0'.encode() for i in range(13)]+[b'mtd0 0x0'],
                        [b'mtd0 permission denied']):
            with self.assertRaises(ramboot.UARTError):
                ramboot.validate_native_mtd(self.response(entries), self.begin, self.end)
        for geometry in (b'134217728\r\n2048\r\n64\r\n', b'0\r\n2048\r\n128\r\n'):
            with self.assertRaises(ramboot.UARTError):
                ramboot.validate_native_mtd(self.response(geometry=geometry), self.begin, self.end)
        with self.assertRaises(ramboot.UARTError):
            ramboot.validate_native_mtd(self.response().replace(self.end+b'\r\n', b''), self.begin, self.end)

    def test_backend_markers_cannot_substitute_for_each_other(self):
        shell = b'Run /bin/sh as init process\n'
        native = b'zx279128-spifc 94406000.spi: inherited working clock 50000000 Hz; array writes disabled\n'
        legacy = b'zx_spifc_nand.ondie_probe=1\nall array writes disabled\n'
        ramboot.validate_boot_markers(shell+native, 'native-ro')
        ramboot.validate_boot_markers(shell+legacy, 'legacy')
        for boot, backend in ((shell+legacy, 'native-ro'), (shell+native, 'legacy'),
                              (native, 'native-ro'), (legacy, 'legacy')):
            with self.assertRaises(ramboot.UARTError):
                ramboot.validate_boot_markers(boot, backend)

    def test_write_test_requires_only_master_and_test_partition_writable(self):
        entries = [f'mtd{i} 0x{0x400 if i in (0, 13) else 0:x}'.encode() for i in range(14)]
        parsed = ramboot.validate_native_mtd(self.response(entries), self.begin, self.end, write_test=True)
        self.assertEqual(parsed['flags'][13], 0x400)
        for i in range(14):
            changed = entries.copy()
            changed[i] = f'mtd{i} 0x{0 if i in (0, 13) else 0x400:x}'.encode()
            with self.subTest(i=i), self.assertRaises(ramboot.UARTError):
                ramboot.validate_native_mtd(self.response(changed), self.begin, self.end, write_test=True)
        with self.assertRaises(ramboot.UARTError):
            ramboot.validate_native_mtd(self.response(entries), self.begin, self.end)

    def test_write_test_window_and_runtime_guard_are_exact(self):
        query, begin, end = ramboot.write_test_partition_query('0123456789ab')
        self.assertLessEqual(len(query), 500)
        values = [b'write-test', b'104726528', b'131072', b'131072', b'2048', b'128', b'Y']
        def evidence(fields):
            return b'\n'+begin+b'\n'+b'\n'.join(fields)+b'\n'+end+b'\n'
        result = ramboot.validate_write_test_partition(evidence(values), begin, end)
        self.assertEqual(result['offset'], 0x63e0000)
        for i in range(len(values)):
            altered = values.copy()
            altered[i] = b'0'
            with self.subTest(i=i), self.assertRaises(ramboot.UARTError):
                ramboot.validate_write_test_partition(evidence(altered), begin, end)
        with self.assertRaises(ramboot.UARTError):
            ramboot.validate_write_test_partition(evidence(values)*2, begin, end)

    def test_write_test_boot_marker_requires_explicit_kernel_parameter(self):
        shell = b'Run /bin/sh as init process\n'
        parameter = b'spi_zx279128.write_test=1\n'
        marker = (b'zx279128-spifc 94406000.spi: STAGING WRITE TEST: '
                  b'bytes [063e0000,06400000), rows [c7c0,c800), one program attempt/page\n')
        ramboot.validate_boot_markers(shell+parameter+marker, 'native-write-test')
        for boot, backend in ((shell+marker, 'native-write-test'),
                              (shell+parameter, 'native-write-test'),
                              (shell+parameter+marker, 'native-ro'),
                              (shell+parameter+marker, 'unknown')):
            with self.assertRaises(ramboot.UARTError):
                ramboot.validate_boot_markers(boot, backend)

    def test_ubi_window_and_independent_failure_guard(self):
        query, begin, end = ramboot.write_test_partition_query('0123456789ab', ubi=True)
        fields = [b'ubi-test', b'88080384', b'16777216', b'131072', b'2048', b'128', b'Y']
        evidence = b'\n'+begin+b'\n'+b'\n'.join(fields)+b'\n'+end+b'\n'
        parsed = ramboot.validate_write_test_partition(evidence, begin, end, ubi=True)
        self.assertEqual(parsed['offset'], 0x5400000)
        self.assertEqual(parsed['bytes'], 0x1000000)
        with self.assertRaises(ramboot.UARTError):
            ramboot.validate_write_test_partition(evidence, begin, end)
        query, begin, end = ramboot.ubi_guard_query('0123456789ab')
        self.assertLessEqual(len(query), 500)
        good = [b'Y', b'N', b'NO_REBIND', b'UBI_READY']
        def reply(values):
            return b'\n'+begin+b'\n'+b'\n'.join(values)+b'\n'+end+b'\n'
        self.assertTrue(ramboot.validate_ubi_guard(reply(good), begin, end)['failure_stop'])
        for i in range(4):
            bad = good.copy();bad[i] = b'BAD'
            with self.assertRaises(ramboot.UARTError):
                ramboot.validate_ubi_guard(reply(bad), begin, end)

    def test_ubi_boot_requires_both_guards(self):
        parts = [b'Run /bin/sh as init process\n',
                 b'UBI WRITE TEST: bytes [05400000,06400000), rows [a800,c800), aligned erase only\n',
                 b'diagnostic mutation guard: no bad-block marking; stop on write/erase failure\n',
                 b'spi_zx279128.ubi_test=1\n', b'spinand.diagnostic_write_guard=1\n']
        ramboot.validate_boot_markers(b''.join(parts), 'native-ubi-test')
        for i in range(len(parts)):
            with self.assertRaises(ramboot.UARTError):
                ramboot.validate_boot_markers(b''.join(parts[:i]+parts[i+1:]), 'native-ubi-test')
