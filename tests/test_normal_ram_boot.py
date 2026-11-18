"""Normal RAM-root payload, memory, checksum and userspace acceptance gates."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

TOOLS = Path(__file__).resolve().parents[1]/'tools'
sys.path.insert(0, str(TOOLS))
import h199a_normal_ram as normal
from h199a_cold_r206 import parse_image, validate_crc_output
spec = importlib.util.spec_from_file_location('normal_ram_controller', TOOLS/'ramboot-h199a-tftp.py')
controller = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controller)

BDINFO = b'''bdinfo
boot_params = 0x40000100
DRAM bank   = 0x00000000
-> start    = 0x40000000
-> size     = 0x08000000
TLB addr    = 0x47FF0000
relocaddr   = 0x47F95000
reloc off   = 0x00095000
irq_sp      = 0x47554F40
sp start    = 0x47554F30
=> '''
BOOT = b'''Kernel command line: console=ttyAMA0,115200n8 earlycon=zteuart,0x94404000 clk_ignore_unused spi_zx279128.ubi_test=1 spinand.diagnostic_write_guard=1 root=/dev/ram0 rootfstype=squashfs ro panic=0
UBI WRITE TEST: bytes [05400000,06400000), rows [a800,c800), aligned erase only
diagnostic mutation guard: no bad-block marking; stop on write/erase failure
L2C-310 enabling early BRESP for Cortex-A9
RAMDISK: squashfs filesystem found at block 0
VFS: Mounted root (squashfs filesystem) readonly on device 1:0.
Run /sbin/init as init process
H199A_OVERLAY_READY: guarded UBI volume available for mount_root
H199A_OVERLAY_MOUNTED: verified UBIFS upper and SquashFS RAM lower
Please press Enter to activate this console.'''


def payloads():
    data = b'kernel-test-payload'*32
    fields = [0x27051956, 0, 0, len(data), 0x40008000, 0x40008000,
              zlib.crc32(data), 5, 2, 2, 0, b'h199a-test'.ljust(32, b'\0')]
    fields[1] = zlib.crc32(struct.pack('>7I4B32s', *fields))
    kernel = parse_image(bytes(32)+struct.pack('>7I4B32s', *fields)+data, expected_name='h199a-test')
    raw = b'hsqs'+bytes(2044)
    root = normal.parse_envelope(normal.make_envelope(raw))
    manifest = {'storage_backend': 'normal-ram-root', 'name': kernel.name,
                'bytes': len(kernel.data), 'sha256': hashlib.sha256(kernel.data).hexdigest(),
                'ram_root': {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                             'crc32': f'{zlib.crc32(raw):08x}', 'load_address': normal.ROOT_START,
                             'end_address': normal.ROOT_START+len(raw), 'kernel_end': 0x40b00000,
                             'conservative_decompress_end': 0x40e00000}}
    return kernel, root, manifest


def checksum_response(image, address, load):
    return (f'## Booting kernel from Legacy Image at {address:08x}\n'
            f'Image Name:   {image.name}\nImage Type:   ARM Linux Kernel Image (uncompressed)\n'
            f'Data Size:    {image.payload_bytes} Bytes\nLoad Address: {load:08x}\n'
            f'Entry Point:  {load:08x}\nVerifying Checksum ... OK\n=> ').encode()


class NormalRamGateTests(unittest.TestCase):
    def setUp(self):
        self.kernel, self.root, self.manifest = payloads()

    def test_console_prompt_accepts_first_boot_default_hostname_only(self):
        # The console can activate before the hostname is set: "root@(none):~# ".
        for prompt in (b'\nroot@OpenWrt:~# ', b'\nroot@OpenWrt:/# ', b'\r\nroot@(none):~# ',
                       b'root@h199a-1.lan:/tmp# '):
            self.assertIsNotNone(normal.NORMAL_PROMPT.search(prompt), prompt)
        for prompt in (b'\n~ # ', b'\nroot@(nonex):~# ', b'\nroot@two words:~# ', b'\nroot@:~# ',
                       b'\nuser@OpenWrt:~# ', b'\nroot@OpenWrt:~$ ', b'\nroot@(none)x:~# '):
            self.assertIsNone(normal.NORMAL_PROMPT.search(prompt), prompt)

    def test_checksum_envelope_leaves_raw_payload_at_chosen_initrd_address(self):
        self.assertEqual(normal.ROOT_HEADER+64, normal.ROOT_START)
        self.assertEqual(self.root.data[64:68], b'hsqs')
        self.assertEqual(normal.make_envelope(self.root.data[64:]), self.root.data)
        for offset in (0, 4, 12, 16, 20, 24, 28, 29, 30, 31, 32, 100):
            broken = bytearray(self.root.data)
            broken[offset] ^= 1
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                normal.parse_envelope(bytes(broken))
        for invalid in (self.root.data[:-1], self.root.data+b'\0', b'hsqs'+bytes(100)):
            with self.assertRaises(ValueError):
                normal.parse_envelope(invalid)

    def test_manifest_binds_both_payloads_and_each_extent(self):
        normal.validate_manifest(self.manifest, self.kernel, self.root)
        for field, value in (('bytes', 1), ('sha256', '0'*64), ('name', 'wrong')):
            invalid = dict(self.manifest, **{field: value})
            with self.assertRaises(ValueError):
                normal.validate_manifest(invalid, self.kernel, self.root)
        for field, value in (('bytes', 1), ('load_address', normal.ROOT_HEADER),
                             ('end_address', normal.ROOT_START+1), ('sha256', '0'*64),
                             ('crc32', '00000000'), ('kernel_end', True),
                             ('conservative_decompress_end', 0x41000001)):
            invalid = dict(self.manifest, ram_root=dict(self.manifest['ram_root'], **{field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                normal.validate_manifest(invalid, self.kernel, self.root)

    def test_bdinfo_rejects_missing_duplicate_or_overlapping_layout(self):
        normal.validate_bdinfo(BDINFO, len(self.kernel.data), len(self.root.data))
        for invalid in (BDINFO.replace(b'0x47554F30', b'0x44400000'),
                        BDINFO.replace(b'0x08000000', b'0x04000000'),
                        BDINFO.replace(b'0x40000100', b'0x44000100'),
                        BDINFO.replace(b'sp start', b'unknown'),
                        BDINFO+b'\n-> start = 0x40000000\n',
                        BDINFO+b'\nDRAM bank = 0x00000001\n'):
            with self.assertRaises(normal.UARTError):
                normal.validate_bdinfo(invalid, len(self.kernel.data), len(self.root.data))
        with self.assertRaises(normal.UARTError):
            normal.validate_bdinfo(BDINFO, len(self.kernel.data), 64+16*1024*1024+1)

    def test_checksum_stage_refuses_wrong_addresses_execution_and_ambiguous_success(self):
        good = checksum_response(self.root, normal.ROOT_HEADER, normal.ROOT_START)
        validate = lambda data: validate_crc_output(data, self.root, address=normal.ROOT_HEADER, load=normal.ROOT_START)
        validate(good)
        for invalid in (good.replace(b'43ffffc0', b'42000020'), good.replace(b'44000000', b'40008000'),
                        good.replace(b'... OK', b'... Bad'), good+b'\nVerifying Checksum ... OK\n',
                        good+b'\nLoading Kernel Image\n', good+b'\nStarting kernel\n'):
            with self.assertRaises(normal.UARTError):
                validate(invalid)
        with self.assertRaises(normal.UARTError):
            validate(good+b'\nLoad Address: 44000000\n')

    def test_normal_boot_rejects_fallback_old_root_and_missing_or_reordered_gates(self):
        normal.validate_boot(BOOT)
        for invalid in (BOOT.replace(b'/dev/ram0', b'/dev/mtdblock7'),
                        BOOT.replace(b'panic=0', b'panic=1'),
                        BOOT.replace(b'L2C-310 enabling early BRESP for Cortex-A9', b'L2C-310 enabled'),
                        BOOT.replace(normal.READY, b'MISSING'), BOOT.replace(normal.MOUNTED, b'MISSING'),
                        BOOT.replace(normal.READY, b'TMP').replace(normal.MOUNTED, normal.READY).replace(b'TMP', normal.MOUNTED),
                        BOOT+b'\nH199A_OVERLAY_FAILED\n', BOOT+b'\nswitching to ramoverlay\n',
                        BOOT+b'\nswitching to ubifs failed - fallback to ramoverlay\n'):
            with self.assertRaises(normal.UARTError):
                normal.validate_boot(invalid)

    def test_runtime_queries_are_bounded_and_cannot_credit_partial_evidence(self):
        for label, (query, begin, end) in normal.runtime_queries('0123456789ab').items():
            self.assertLessEqual(len(query), 500)
            response = query+b'\n\n'+begin+b'\nvalue\n'+end+b'\n'
            self.assertEqual(normal.frame_lines(response, begin, end), [b'value'])
            with self.assertRaises(normal.UARTError):
                normal.frame_lines(response+response, begin, end)
            if label != 'STATE':
                with self.assertRaises(normal.UARTError):
                    normal.validate_runtime(label, [b'value'])
        for state in (b'ABSENT', b'0', b'1'):
            self.assertFalse(normal.validate_runtime('STATE', [state]))
        self.assertTrue(normal.validate_runtime('STATE', [b'2']))
        with self.assertRaises(normal.UARTError):
            normal.validate_runtime('STATE', [b'2', b'2'])
        query, _, _ = controller.native_readonly_query('0123456789ab', mount=False)
        self.assertNotIn(b'mount ', query)
        self.assertNotIn(b'>', query)


class FakeConsole:
    def __init__(self, io):
        self.io, self.state, self.last = io, 'boot-entry', b''

    def write_all(self, data):
        self.last = data.rstrip(b'\r')
        self.io.commands.append(self.last)

    boot_token = write_all

    def confirm_uboot(self):
        self.state = 'console'
        return b'U-Boot 2013.04 test'

    def memory(self, address, count):
        if address == normal.ROOT_HEADER:
            return self.io.root.data[:64]
        offset = address-0x42000000
        return self.io.kernel.data[offset:offset+count*4]

    def until(self, marker, **kwargs):
        if marker == normal.NORMAL_PROMPT:
            return b'\nroot@OpenWrt:/# '
        if marker == controller.PROMPT:
            command = self.last.decode()
            if command == 'printenv ipaddr serverip verify':
                return b'ipaddr=192.168.1.1\nserverip=192.168.1.100\nverify=yes\n=> '
            if command == 'bdinfo':
                return BDINFO
            if command.startswith('tftp '):
                root = '43ffffc0' in command
                count = len(self.io.root.data if root else self.io.kernel.data)
                if root and self.io.failure == 'partial-root':
                    count -= 1
                return f'TFTP from server\nBytes transferred = {count}\n=> '.encode()
            if command.startswith('bootm start '):
                root = '43ffffc0' in command
                output = checksum_response(self.io.root if root else self.io.kernel,
                                           normal.ROOT_HEADER if root else 0x42000020,
                                           normal.ROOT_START if root else 0x40008000)
                return output.replace(b'... OK', b'... Bad') if root and self.io.failure == 'root-crc' else output
        if hasattr(marker, 'pattern') and b'Please press Enter' in marker.pattern:
            return BOOT
        if hasattr(marker, 'pattern') and b'H199A_' in marker.pattern:
            begin = re.search(rb'H199A_([A-Z]+)_BEGIN_[a-f0-9]+', self.last)
            end = re.search(rb'H199A_[A-Z]+_END_[a-f0-9]+', self.last)
            label = begin[1].decode()
            if label == 'NATIVE':
                lines = [f'mtd{i} 0x{1024 if i in (0,13) else 0:x}'.encode() for i in range(14)]
                lines += b'GEOMETRY 134217728 2048 128'.split()
            else:
                lines = {
                    'NAMES': b'bootloader tag wifi usercfg defcfg kernel1 rootfs header kernel2 rootfs2 legacy_overlay staging overlay_ubi'.split(),
                    'WINDOW': b'88080384 16777216 131072 2048 128 nand'.split(),
                    'GUARDS': b'Y N Y NO_REBIND NO_REBIND'.split(),
                    'VOLUME': b'ubi0 ubi0_0 13 rootfs_data dynamic 104'.split(),
                    'MOUNTS': b'MOUNTS_OK procd NO_FAILSAFE'.split(),
                    'STATE': [b'1' if self.io.failure == 'pending-state' else b'2'],
                }[label]
            if label == 'MOUNTS':
                self.io.mount_queries += 1
                if self.io.failure == 'late-readonly' and self.io.mount_queries == 2:
                    lines = b'procd NO_FAILSAFE'.split()
            return b'\n'+begin[0]+b'\n'+b'\n'.join(lines)+b'\n'+end[0]+b'\n'
        return marker if isinstance(marker, bytes) else b'=> '


class NormalRamControllerTests(unittest.TestCase):
    def run_controller(self, failure=None):
        kernel, root, manifest = payloads()
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            for name, data in (('kernel', kernel.data), ('root', root.data), ('manifest', json.dumps(manifest).encode())):
                (folder/name).write_bytes(data)
            io = SimpleNamespace(received=bytearray(), commands=[], kernel=kernel, root=root,
                                 failure=failure, mount_queries=0, close=lambda: None)
            relay_calls = []
            def relay(args, **kwargs):
                relay_calls.append(args[-1])
                return SimpleNamespace(stdout=b'mocked relay', stderr=b'', returncode=0)
            args = ['ramboot', '--execute', '--device', '/mock/uart', '--raw-log', str(folder/'raw'),
                    '--image', str(folder/'kernel'), '--image-name', kernel.name, '--tftp-name', 'kernel',
                    '--output', str(folder/'run'), '--storage-backend', 'normal-ram-root',
                    '--rootfs-envelope', str(folder/'root'), '--rootfs-tftp-name', 'root',
                    '--normal-manifest', str(folder/'manifest')]
            with patch.object(sys, 'argv', args), patch.object(controller, 'Console', FakeConsole), \
                 patch.object(controller, 'LoggedTextTransport', return_value=io), \
                 patch.object(controller.subprocess, 'run', side_effect=relay), \
                 patch.object(controller.subprocess, 'Popen', return_value=SimpleNamespace(wait=lambda **k: 0)), \
                 patch.object(controller.time, 'sleep'), patch.object(controller.fcntl, 'flock'):
                if failure:
                    with self.assertRaises(controller.UARTError):
                        controller.main()
                else:
                    controller.main()
            return json.loads((folder/'run/result.json').read_text()), io.commands, relay_calls

    def test_only_kernel_executes_after_both_checksum_stages_and_ready_state(self):
        result, commands, _ = self.run_controller()
        self.assertTrue(result['success'])
        self.assertTrue(result['normal_runtime']['fstools_ready'])
        root_check = commands.index(b'bootm start 0x43ffffc0')
        kernel_check = commands.index(b'bootm start 0x42000020')
        execute = commands.index(b'bootm 0x42000020')
        self.assertLess(root_check, kernel_check)
        self.assertLess(kernel_check, execute)
        self.assertNotIn(b'bootm 0x43ffffc0', commands)

    def test_console_loglevel_lowered_before_acceptance_queries(self):
        # Module-load/netifd printk must be silenced before any framed query so
        # it cannot interleave into and corrupt the acceptance evidence.
        result, commands, _ = self.run_controller()
        self.assertTrue(result['success'])
        quiesce = commands.index(b'echo 1 >/proc/sys/kernel/printk')
        activate = commands.index(b'bootm 0x42000020')
        first_query = next(i for i, c in enumerate(commands) if b'H199A_NATIVE_BEGIN_' in c)
        self.assertLess(activate, quiesce)
        self.assertLess(quiesce, first_query)

    def test_second_transfer_or_crc_failure_never_executes_either_payload(self):
        for failure in ('partial-root', 'root-crc'):
            result, commands, relay = self.run_controller(failure)
            self.assertFalse(result['success'])
            self.assertTrue(result['left_powered_off'])
            self.assertEqual(relay[-1], 'off')
            self.assertNotIn(b'bootm 0x42000020', commands)
            self.assertNotIn(b'bootm 0x43ffffc0', commands)

    def test_pending_overlay_never_receives_success_credit(self):
        result, commands, _ = self.run_controller('pending-state')
        self.assertFalse(result['success'])
        self.assertTrue(result['left_powered_off'])
        self.assertFalse(any(b'mount_root done' in command for command in commands))

    def test_old_ready_state_cannot_hide_late_readonly_mount(self):
        result, commands, _ = self.run_controller('late-readonly')
        self.assertFalse(result['success'])
        self.assertTrue(result['normal_runtime']['fstools_ready'])
        self.assertTrue(result['left_powered_off'])
        self.assertEqual(sum(b'h199a_overlay_mount_check' in command for command in commands), 2)
