"""Production write-policy qualification (BOOT_PROFILE=production PRODUCTION_QUALIFY=1).

Covers the host side of hardware ladder step 1:
  * the transport's real C zx_policy_map(), compiled on the host, must produce
    exactly the text of the independent spec model in h199a_normal_ram;
  * the qualify boot validator accepts only the exact production-qualify
    command line and markers, and rejects any overlay attach or early refusal;
  * the runtime validators reject a latched policy, an attached UBI, a wrong
    writability matrix and a tampered map;
  * the controller's production-qualify backend runs the same checksum-verified
    RAM boot as normal-X, executes only the kernel, and powers off on failure.
"""
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

TESTS = Path(__file__).resolve().parent
sys.path.insert(0, str(TESTS))
import test_normal_ram_boot as base  # noqa: E402  (also puts tools/ on sys.path)
from test_tx_origin_r204 import function  # noqa: E402

normal, controller = base.normal, base.controller
SOURCE = TESTS.parent / 'files/target/linux/armsr/files-6.6/drivers/spi/spi-zx279128.c'

QUALIFY_BOOT = (
    b'Kernel command line: console=ttyAMA0,115200n8 earlycon=zteuart,0x94404000 clk_ignore_unused '
    b'spi_zx279128.production_qualify=1 root=/dev/ram0 rootfstype=squashfs ro panic=0\n'
    b'L2C-310 enabling early BRESP for Cortex-A9\n'
    + normal.QUALIFY_POLICY_MARKER + b'\n'
    b'RAMDISK: squashfs filesystem found at block 0\n'
    b'VFS: Mounted root (squashfs filesystem) readonly on device 1:0.\n'
    b'Run /sbin/init as init process\n'
    b'mount_root: no usable overlay filesystem found, using tmpfs overlay\n'
    b'Please press Enter to activate this console.')

C_MAP_HARNESS = r'''
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
#define BIT(n) (1U<<(n))
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
static char page[65536];
static int sysfs_emit_at(char *buf, int at, const char *fmt, ...)
{
	va_list ap; int n;
	va_start(ap, fmt); n = vsnprintf(buf + at, sizeof(page) - at, fmt, ap); va_end(ap);
	return n;
}
'''


class PolicyMapModelTests(unittest.TestCase):
    def test_compiled_c_map_matches_independent_spec_model(self):
        text = SOURCE.read_text()
        constants = '\n'.join(l for l in text.splitlines() if l.startswith('#define ZX_'))
        enum = re.search(r'enum zx_verdict \{.*?\};', text, re.S).group()
        names = re.search(r'static const char \*const zx_verdict_names\[\] = \{.*?\};', text, re.S).group()
        funcs = '\n'.join(function(text, n) for n in
                          ('zx_policy_row', 'zx_policy_feature', 'zx_policy_range', 'zx_policy_map'))
        main = r'''
int main(int argc, char **argv)
{
	bool q = argc > 1 && argv[1][0] == 'q';
	int bank = argc > 2 && argv[2][0] == 'b';
	int at = sysfs_emit_at(page, 0, "zx279128 write policy v1 active=%s\n",
			       q ? "production-qualify" : "production");
	at = zx_policy_map(page, at, false, bank);
	at = zx_policy_map(page, at, true, bank);
	fputs(page, stdout);
	return 0;
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            src, exe = Path(tmp) / 'map.c', Path(tmp) / 'map'
            src.write_text(constants + '\n' + C_MAP_HARNESS + enum + '\n' + names + '\n' + funcs + main)
            r = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Werror', '-Wno-unused-function',
                                str(src), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stderr)
            for arg, mode in (('p', 'production'), ('q', 'production-qualify')):
                for bank in (0, 1):
                    out = subprocess.run([str(exe), arg, 'b' if bank else 'a'],
                                         capture_output=True, text=True, timeout=30).stdout
                    self.assertEqual(out, normal.expected_policy_map(mode, bank), (mode, bank))

    def test_spec_model_protects_every_non_allowlisted_region(self):
        lines = normal.expected_policy_map('production').splitlines()
        prod = lines[lines.index('flavour production'):lines.index('flavour production-qualify')]
        allows = [l for l in prod if l.endswith(' allow')]
        self.assertEqual(sorted(allows), sorted([
            'program 00700000-0173ffff allow', 'program 05400000-063fffff allow',
            'erase 00700000-0173ffff allow', 'erase 05400000-063fffff allow']))
        qual = lines[lines.index('flavour production-qualify'):]
        self.assertEqual([l for l in qual if l.endswith(' allow')],
                         ['program 05400000-063fffff allow', 'erase 05400000-063fffff allow'])


class QualifyValidatorTests(unittest.TestCase):
    def test_boot_accepts_exact_profile(self):
        self.assertTrue(normal.validate_production_qualify_boot(QUALIFY_BOOT)['policy_marker'])

    def test_boot_rejects_wrong_cmdline_overlay_attach_or_early_refusal(self):
        bad = [
            QUALIFY_BOOT.replace(b'production_qualify=1', b'production=1'),
            QUALIFY_BOOT.replace(b' panic=0', b''),
            QUALIFY_BOOT.replace(b'ro panic=0', b'ro panic=0 spi_zx279128.ubi_test=1'),
            QUALIFY_BOOT.replace(normal.QUALIFY_POLICY_MARKER, b'production write policy: something'),
            QUALIFY_BOOT + b'\nubi0: attaching mtd13',
            QUALIFY_BOOT + b'\nH199A_PROD_OVERLAY_READY: ubi0:rootfs_data available',
            QUALIFY_BOOT + b'\nwrite policy denied op=d8 addr=a800',
            QUALIFY_BOOT + b'\nKernel panic - not syncing',
        ]
        for boot in bad:
            with self.assertRaises(normal.UARTError, msg=boot[-60:]):
                normal.validate_production_qualify_boot(boot)

    def test_runtime_rejects_latched_attached_or_tampered(self):
        ok = {'POLICY': [b'production-qualify', normal.QUALIFY_STATE_IDLE],
              'MOUNTS': [b'NO_UBI', b'procd', b'NO_FAILSAFE'],
              'MAP': normal.expected_policy_map('production-qualify').encode().splitlines()}
        for label, lines in ok.items():
            self.assertTrue(normal.validate_production_qualify_runtime(label, lines))
        tampered_map = [l.replace(b'01740000-053fffff deny', b'01740000-053fffff allow') for l in ok['MAP']]
        bad = [('POLICY', [b'production-qualify', normal.QUALIFY_STATE_IDLE.replace(b'latched=0', b'latched=1')]),
               ('POLICY', [b'POLICY_ATTR_MISSING']),
               ('MOUNTS', [b'UBI_ATTACHED', b'ubifs', b'procd', b'NO_FAILSAFE']),
               ('MOUNTS', [b'NO_UBI', b'tmpfs', b'procd', b'NO_FAILSAFE']),
               ('MAP', tampered_map)]
        for label, lines in bad:
            with self.assertRaises(normal.UARTError):
                normal.validate_production_qualify_runtime(label, lines)

    def test_queries_fit_the_console_and_never_exit_the_login_shell(self):
        for label, (query, _, _) in normal.production_qualify_queries('0123456789ab').items():
            self.assertLessEqual(len(query), 500, label)
            self.assertNotRegex(query, rb'(^|[;&|]\s*)exit\b', label)

    def test_writability_matrix(self):
        def evidence(flags):
            lines = [f'mtd{i} 0x{flags.get(i, 0):x}' for i in range(14)]
            return ('\nB\n' + '\n'.join(lines) + '\nGEOMETRY\n134217728\n2048\n128\nE\n').encode()
        good = {i: 0x400 for i in normal.QUALIFY_WRITABLE}
        controller.validate_native_mtd(evidence(good), b'B', b'E', writable=normal.QUALIFY_WRITABLE)
        for change in ({7: 0}, {9: 0x400}, {1: 0x400}, {0: 0}):
            with self.assertRaises(controller.UARTError):
                controller.validate_native_mtd(evidence({**good, **change}), b'B', b'E',
                                               writable=normal.QUALIFY_WRITABLE)


class QualifyFakeConsole(base.FakeConsole):
    def until(self, marker, **kwargs):
        if hasattr(marker, 'pattern') and b'Please press Enter' in marker.pattern:
            return QUALIFY_BOOT
        if hasattr(marker, 'pattern') and b'H199A_' in marker.pattern:
            begin = re.search(rb'H199A_([A-Z]+)_BEGIN_[a-f0-9]+', self.last)
            end = re.search(rb'H199A_[A-Z]+_END_[a-f0-9]+', self.last)
            label, failure = begin[1].decode(), self.io.failure
            if label == 'NATIVE':
                writable = set(normal.QUALIFY_WRITABLE) - ({7} if failure == 'bank-a-ro' else set())
                lines = [f'mtd{i} 0x{0x400 if i in writable else 0:x}'.encode() for i in range(14)]
                lines += b'GEOMETRY 134217728 2048 128'.split()
            else:
                lines = {
                    'NAMES': b'bootloader tag wifi usercfg defcfg kernel1 rootfs header kernel2 rootfs2 legacy_overlay staging overlay_ubi'.split(),
                    'POLICY': [b'production-qualify', normal.QUALIFY_STATE_IDLE.replace(
                        b'latched=0', b'latched=1' if failure == 'latched' else b'latched=0')],
                    'MAP': normal.expected_policy_map('production-qualify').encode().splitlines(),
                    'MOUNTS': [b'UBI_ATTACHED' if failure == 'ubi' else b'NO_UBI',
                               b'procd', b'NO_FAILSAFE'],
                }[label]
            return b'\n' + begin[0] + b'\n' + b'\n'.join(lines) + b'\n' + end[0] + b'\n'
        return super().until(marker, **kwargs)


class QualifyControllerTests(unittest.TestCase):
    def run_controller(self, failure=None):
        kernel, root, manifest = base.payloads()
        manifest['storage_backend'] = 'production-qualify'
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name, data in (('kernel', kernel.data), ('root', root.data),
                               ('manifest', json.dumps(manifest).encode())):
                (folder / name).write_bytes(data)
            io = SimpleNamespace(received=bytearray(), commands=[], kernel=kernel, root=root,
                                 failure=failure, mount_queries=0, close=lambda: None)
            relay_calls = []

            def relay(args, **kwargs):
                relay_calls.append(args[-1])
                return SimpleNamespace(stdout=b'mocked relay', stderr=b'', returncode=0)
            args = ['ramboot', '--execute', '--device', '/mock/uart', '--raw-log', str(folder / 'raw'),
                    '--image', str(folder / 'kernel'), '--image-name', kernel.name, '--tftp-name', 'kernel',
                    '--output', str(folder / 'run'), '--storage-backend', 'production-qualify',
                    '--rootfs-envelope', str(folder / 'root'), '--rootfs-tftp-name', 'root',
                    '--normal-manifest', str(folder / 'manifest')]
            with patch.object(sys, 'argv', args), patch.object(controller, 'Console', QualifyFakeConsole), \
                 patch.object(controller, 'LoggedTextTransport', return_value=io), \
                 patch.object(controller.subprocess, 'run', side_effect=relay), \
                 patch.object(controller.subprocess, 'Popen', return_value=SimpleNamespace(wait=lambda **k: 0)), \
                 patch.object(controller.time, 'sleep'), patch.object(controller.fcntl, 'flock'):
                if failure:
                    with self.assertRaises(controller.UARTError):
                        controller.main()
                else:
                    controller.main()
            return json.loads((folder / 'run/result.json').read_text()), io.commands, relay_calls

    def test_qualify_backend_verifies_and_executes_only_the_kernel(self):
        result, commands, relay = self.run_controller()
        self.assertTrue(result['success'])
        self.assertEqual(result['phase'], 'production-qualify-ready')
        self.assertEqual(set(result['production_qualify_runtime']), {'NAMES', 'POLICY', 'MAP', 'MOUNTS'})
        self.assertLess(commands.index(b'bootm start 0x43ffffc0'), commands.index(b'bootm start 0x42000020'))
        self.assertIn(b'bootm 0x42000020', commands)
        self.assertNotIn(b'bootm 0x43ffffc0', commands)
        self.assertLess(commands.index(b'echo 1 >/proc/sys/kernel/printk'),
                        next(i for i, c in enumerate(commands) if b'H199A_NATIVE_BEGIN_' in c))
        self.assertNotIn('off', relay[1:], 'success leaves the board up for the live deny tests')

    def test_any_qualify_failure_powers_off(self):
        for failure in ('latched', 'ubi', 'bank-a-ro'):
            result, _, relay = self.run_controller(failure)
            self.assertFalse(result['success'], failure)
            self.assertTrue(result['left_powered_off'], failure)
            self.assertEqual(relay[-1], 'off', failure)

    def test_normal_manifest_cannot_drive_the_qualify_backend(self):
        kernel, root, manifest = base.payloads()  # storage_backend normal-ram-root
        with self.assertRaises(ValueError):
            normal.validate_manifest(manifest, kernel, root, backend='production-qualify')


if __name__ == '__main__':
    unittest.main()
