#!/usr/bin/env python3
"""RAM-only TFTP boot while an existing sole UART reader keeps logging.

This adapter reads a regular raw log for TEXT console control only. Never use
it for XMODEM. It sends no flash/persistent-environment commands. The stock
PCI-only mode sets explicit volatile boot arguments. The caller must already
serve the selected immutable image at the bootloader's configured server IP.
"""
import argparse
from contextlib import nullcontext
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import secrets
import subprocess
import time

from h199a_uart_fd import Console, PROMPT, UARTError
from h199a_cold_r206 import parse_image, verify_enabled, validate_crc_output
import h199a_normal_ram as normal_ram

STOCK_PCI_ARGS = ('mem=128M console=ttyAMA0,115200n8 ro root=/dev/mtdblock8 '
                  'rootfstype=jffs2 panic=0 h199a_pci_only=1')
# This U-Boot appends a literal trailer after the last argument. Keep an
# ignored marker last so the semicolon cannot become part of panic=0's value.
STOCK_PCI_TRAILER = b'; U-Boot V1.0.0 20210706145901 0x700000 0x0 0xaf 0xa3'
STOCK_PANIC = re.compile(rb'Kernel panic - not syncing: VFS: Unable to mount root fs[^\r\n]*\r?\n')


def validate_stock_pci_log(boot):
    found = re.findall(rb'Kernel command line: ([^\r\n]*)', boot)
    if len(found) != 1 or found[0] not in (STOCK_PCI_ARGS.encode(),
                                        STOCK_PCI_ARGS.encode() + STOCK_PCI_TRAILER):
        raise UARTError('stock reference effective command line differs from the contained scope')
    if not STOCK_PANIC.search(boot):
        raise UARTError('expected root-mount stop was not observed')
    if re.search(rb'zte_spifc_dt_probe|NAND device:|Creating \d+ MTD partitions', boot):
        raise UARTError('unexpected NAND initialization in PCI-only reference')
    return {'command_line': found[0].decode(), 'intentional_root_mount_failure': True}


def validate_boot_markers(boot, backend):
    if b'Run /bin/sh as init process' not in boot:
        raise UARTError('diagnostic shell boot marker missing')
    if backend == 'legacy':
        if (b'zx_spifc_nand.ondie_probe=1' not in boot or
                b'all array writes disabled' not in boot):
            raise UARTError('legacy read-only boot markers missing')
    elif backend == 'native-ro':
        if not re.search(rb'zx279128-spifc .*inherited working clock \d+ Hz; array writes disabled', boot):
            raise UARTError('native SPI write-denial boot marker missing')
    elif backend == 'native-write-test':
        marker = (b'STAGING WRITE TEST: bytes [063e0000,06400000), rows [c7c0,c800), '
                  b'one program attempt/page')
        if marker not in boot or b'spi_zx279128.write_test=1' not in boot:
            raise UARTError('bounded native write-test boot markers missing')
    elif backend == 'native-ubi-test':
        markers = (b'UBI WRITE TEST: bytes [05400000,06400000), rows [a800,c800), aligned erase only',
                   b'diagnostic mutation guard: no bad-block marking; stop on write/erase failure',
                   b'spi_zx279128.ubi_test=1', b'spinand.diagnostic_write_guard=1')
        if not all(marker in boot for marker in markers):
            raise UARTError('bounded UBI test or core failure-guard marker missing')
    else:
        raise UARTError('unknown storage backend')


def native_readonly_query(nonce, *, mount=True):
    begin = 'H199A_NATIVE_BEGIN_' + nonce
    end = 'H199A_NATIVE_END_' + nonce
    prefix = ('mount -t proc proc /proc; mount -t sysfs sysfs /sys; '
              'echo 4 >/proc/sys/kernel/printk; ') if mount else ''
    command = (prefix +
        "printf '\\n" + begin + "\\n'; "
        'for p in /sys/class/mtd/mtd[0-9]*; do '
        'test -f "$p/flags" || continue; '
        'printf "%s " "${p##*/}"; cat "$p/flags"; done; '
        "printf 'GEOMETRY\\n'; "
        'cat /sys/class/mtd/mtd0/size /sys/class/mtd/mtd0/writesize '
        '/sys/class/mtd/mtd0/oobsize; '
        "printf '" + end + "\\n'")
    if len(command) > 500:
        raise UARTError('native verification command exceeds console bound')
    return command.encode('ascii'), begin.encode(), end.encode()


def validate_native_mtd(response, begin, end, write_test=False, writable=None):
    """`writable`, when given, is the exact set of MTD indices that must carry
    MTD_WRITEABLE (production-policy qualification: master, bank A, overlay)."""
    data = response.replace(b'\r', b'')
    start = b'\n' + begin + b'\n'
    finish = end + b'\n'
    if data.count(start) != 1 or data.count(b'\n' + finish) != 1:
        raise UARTError('native MTD verification markers are ambiguous')
    body = data.split(start, 1)[1].split(finish, 1)[0]
    parts = body.split(b'GEOMETRY\n')
    if len(parts) != 2:
        raise UARTError('native MTD geometry missing')
    entries = parts[0].splitlines()
    flags = {}
    for entry in entries:
        match = re.fullmatch(rb'mtd(\d+) (0x[0-9a-fA-F]+)', entry)
        if not match:
            raise UARTError('malformed native MTD flag evidence')
        index, value = int(match[1]), int(match[2], 16)
        expected_writable = (index in writable) if writable is not None else (write_test and index in (0, 13))
        if index in flags or bool(value & 0x400) != expected_writable:
            raise UARTError('duplicate or unexpected native MTD write permissions')
        flags[index] = value
    if set(flags) != set(range(14 if (write_test or writable is not None) else 13)):
        raise UARTError('native master/partition set differs from the selected layout')
    if parts[1].splitlines() != [b'134217728', b'2048', b'128']:
        raise UARTError('native SPI-NAND geometry differs from the expected Micron chip')
    return {'flags': flags, 'bytes': 134217728, 'page': 2048, 'oob': 128}


def write_test_partition_query(nonce, ubi=False):
    begin, end = 'H199A_WINDOW_BEGIN_' + nonce, 'H199A_WINDOW_END_' + nonce
    command = ("printf '\\n" + begin + "\\n'; "
               'for f in name offset size erasesize writesize oobsize; do '
               'cat /sys/class/mtd/mtd13/$f; done; '
               'cat /sys/module/spi_zx279128/parameters/' + ('ubi_test' if ubi else 'write_test') + '; '
               "printf '" + end + "\\n'")
    return command.encode('ascii'), begin.encode(), end.encode()


def validate_write_test_partition(response, begin, end, ubi=False):
    data = response.replace(b'\r', b'')
    start, finish = b'\n' + begin + b'\n', b'\n' + end + b'\n'
    if data.count(start) != 1 or data.count(finish) != 1:
        raise UARTError('write-test window evidence is ambiguous')
    body = data.split(start, 1)[1].split(finish, 1)[0].splitlines()
    expected = ([b'ubi-test', b'88080384', b'16777216'] if ubi else
                [b'write-test', b'104726528', b'131072']) + [b'131072', b'2048', b'128', b'Y']
    if body != expected:
        raise UARTError('write-test partition/window/driver guard differs from selected scope')
    if ubi:
        return {'partition': 'mtd13', 'offset': 0x5400000, 'bytes': 0x1000000}
    return {'partition': 'mtd13', 'offset': 0x63e0000, 'bytes': 0x20000,
            'one_program_attempt_per_page': True}


def ubi_guard_query(nonce):
    begin, end = 'H199A_UBIG_BEGIN_' + nonce, 'H199A_UBIG_END_' + nonce
    command = ("printf '\\n"+begin+"\\n'; s=/sys/module; "
               'cat $s/spinand/parameters/diagnostic_write_guard '
               '$s/spi_zx279128/parameters/write_test; '
               'd=/sys/bus/spi/drivers/spi-nand; '
               'test -d $d -a ! -e $d/bind -a ! -e $d/unbind && echo NO_REBIND; '
               'set -- /sys/class/ubi/ubi[0-9]*; '
               'test -e /sys/class/misc/ubi_ctrl/dev -a ! -e "$1" && '
               'grep -qw ubifs /proc/filesystems && echo UBI_READY; '
               "printf '"+end+"\\n'")
    if len(command) > 500:
        raise UARTError('UBI guard query exceeds the console bound')
    return command.encode(), begin.encode(), end.encode()


def validate_ubi_guard(response, begin, end):
    data = response.replace(b'\r', b'')
    start, finish = b'\n'+begin+b'\n', b'\n'+end+b'\n'
    if data.count(start) != 1 or data.count(finish) != 1:
        raise UARTError('ambiguous UBI guard evidence')
    body = data.split(start, 1)[1].split(finish, 1)[0].splitlines()
    if body != [b'Y', b'N', b'NO_REBIND', b'UBI_READY']:
        raise UARTError('UBI failure guard, rebind suppression or unattached filesystem readiness missing')
    return {'failure_stop': True, 'badblock_marking': False, 'child_rebind': False,
            'ubi_attached': False, 'ubifs_available': True}


def restart_guard_query(nonce):
    begin, end = 'H199A_RST_BEGIN_' + nonce, 'H199A_RST_END_' + nonce
    command = ("printf '\\n" + begin + "\\n'; "
               'test -d /sys/bus/platform/drivers/zx279128-reboot/94000044.reset-controller '
               '&& echo RESTART_BOUND; '
               "grep -Eq '(^| )init=/bin/sh( |$)' /proc/cmdline && echo SHELL_PROFILE; "
               "printf '" + end + "\\n'")
    if len(command) > 500:
        raise UARTError('restart guard query exceeds console bound')
    return command.encode(), begin.encode(), end.encode()


def validate_restart_guard(response, begin, end):
    data = response.replace(b'\r', b'')
    start, finish = b'\n' + begin + b'\n', b'\n' + end + b'\n'
    if data.count(start) != 1 or data.count(finish) != 1:
        raise UARTError('ambiguous restart guard evidence')
    body = data.split(start, 1)[1].split(finish, 1)[0].splitlines()
    if body != [b'RESTART_BOUND', b'SHELL_PROFILE']:
        raise UARTError('software restart requires bound driver and diagnostic shell')
    return {'driver_bound': True, 'diagnostic_shell': True}


class LoggedTextTransport:
    def __init__(self, device, log):
        self.device = device
        self.log = log.open('rb')
        self.log.seek(0, os.SEEK_END)
        self.fd = os.open(device, os.O_WRONLY | os.O_NOCTTY | os.O_NONBLOCK | os.O_CLOEXEC)
        self.identity = os.fstat(self.fd)
        self.pending = bytearray()
        self.received = bytearray()
        self.writes_allowed = True

    def pushback(self, data):
        self.pending[:0] = data

    def read(self, size, timeout):
        if self.pending:
            out = bytes(self.pending[:size]);del self.pending[:size];return out
        deadline = time.monotonic() + timeout
        while True:
            out = self.log.read(size)
            if out:
                self.received.extend(out)
                if len(self.received) > 1024 * 1024:
                    raise UARTError('text capture exceeded its bound')
                return out
            if time.monotonic() >= deadline:
                return b''
            time.sleep(min(.02, max(0, deadline-time.monotonic())))

    def write(self, data, timeout):
        current = os.stat(self.device)
        if (current.st_ino,current.st_rdev) != (self.identity.st_ino,self.identity.st_rdev):
            raise UARTError('UART device identity changed')
        if not self.writes_allowed or not select.select([], [self.fd], [], timeout)[1]:
            raise UARTError('UART write unavailable')
        count = os.write(self.fd, data[:8])
        if not count:
            raise UARTError('UART write made no progress')
        time.sleep(.01)
        return count

    def close(self):
        os.close(self.fd)
        self.log.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--execute', action='store_true', required=True)
    ap.add_argument('--device', required=True)
    ap.add_argument('--raw-log', type=Path, required=True)
    ap.add_argument('--image', type=Path, required=True)
    ap.add_argument('--image-name', required=True)
    ap.add_argument('--tftp-name', required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--serverip', default='192.168.1.100')
    ap.add_argument('--ipaddr', default='192.168.1.1')
    ap.add_argument('--relay', default='tomada')
    ap.add_argument('--software-reboot', action='store_true',
                    help='test kernel reboot from a verified read-only diagnostic shell; native-ro only')
    ap.add_argument('--storage-backend', choices=('legacy', 'native-ro', 'native-write-test', 'native-ubi-test', 'stock-pci-only', 'normal-ram-root', 'production-qualify'), default='legacy')
    ap.add_argument('--stock-reference', type=Path, help='verified corrected original; mandatory for stock-pci-only')
    ap.add_argument('--rootfs-envelope', type=Path,
                    help='checksum-only rootfs envelope from h199a_normal_ram.py; normal-ram-root only')
    ap.add_argument('--rootfs-tftp-name')
    ap.add_argument('--normal-manifest', type=Path)
    args = ap.parse_args()
    if args.software_reboot and args.storage_backend != 'native-ro':
        ap.error('--software-reboot requires the native-ro destination profile')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', args.tftp_name):
        ap.error('simple TFTP filename required')
    image = parse_image(args.image.read_bytes(), expected_name=args.image_name)
    root = root_manifest = None
    root_arguments = (args.rootfs_envelope, args.rootfs_tftp_name, args.normal_manifest)
    qualify = args.storage_backend == 'production-qualify'
    if args.storage_backend in ('normal-ram-root', 'production-qualify'):
        if not all(root_arguments):
            ap.error('RAM-root boot requires rootfs envelope, TFTP name and manifest')
        if (not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', args.rootfs_tftp_name) or
                args.rootfs_tftp_name == args.tftp_name):
            ap.error('rootfs requires a distinct simple TFTP filename')
        root = normal_ram.parse_envelope(args.rootfs_envelope.read_bytes())
        root_manifest = normal_ram.validate_manifest(
            json.loads(args.normal_manifest.read_text()), image, root, backend=args.storage_backend)
    elif any(root_arguments):
        ap.error('rootfs arguments apply only to normal-ram-root and production-qualify')
    stock_guards = None
    if args.storage_backend == 'stock-pci-only':
        if args.stock_reference is None:
            ap.error('stock-pci-only requires the verified original --stock-reference')
        spec = importlib.util.spec_from_file_location('stock_pci_image', Path(__file__).with_name('stock-pci-image.py'))
        stock = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(stock)
        stock_guards = stock.verify_candidate(image.data, args.stock_reference.read_bytes())
    elif args.stock_reference is not None:
        ap.error('--stock-reference applies only to stock-pci-only')
    args.output.mkdir()  # dedicated run, never overwrite earlier evidence
    (args.output/'controller.py').write_bytes(Path(__file__).read_bytes())
    result = {'success': False, 'phase': 'preflight', 'flash_commands': False,
              'environment_commands': False, 'uboot_network_used': False,
              'image_sha256': hashlib.sha256(image.data).hexdigest()}
    result['storage_backend'] = args.storage_backend
    if root:
        result['ram_root'] = root_manifest
        result['root_envelope_sha256'] = hashlib.sha256(root.data).hexdigest()
        (args.output/'h199a_normal_ram.py').write_bytes(Path(normal_ram.__file__).read_bytes())
    if stock_guards:
        result['stock_guards'] = stock_guards
        result['persistent_environment_commands'] = False
    io = None
    power_on = None

    def checkpoint(phase):
        result['phase'] = phase
        print(phase, flush=True)
        (args.output/'result.json').write_text(json.dumps(result, indent=2)+'\n')
        if io:
            (args.output/'uart.raw').write_bytes(io.received)

    def relay(action):
        r = subprocess.run([args.relay, action], capture_output=True, timeout=45, check=True)
        (args.output/f'power-{action}.txt').write_bytes(r.stdout+r.stderr)

    with open('/tmp/h199a-uart-tx.lock', 'a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            if not args.software_reboot:
                checkpoint('power-off')
                relay('off')
                time.sleep(8)
            io = LoggedTextTransport(args.device, args.raw_log)
            c = Console(io)
            if args.software_reboot:
                c.state = 'linux'
                checkpoint('verify-restart-source')
                c.write_all(b'\r')
                c.until(re.compile(rb'(?:^|\r?\n)~ # '), timeout=10)
                query, begin, end = native_readonly_query(secrets.token_hex(6))
                c.write_all(query + b'\r')
                evidence = c.until(re.compile(rb'(?:^|\r?\n)' + end + rb'\r?\n'), timeout=40)
                c.until(re.compile(rb'(?:^|\r?\n)~ # '), timeout=5)
                (args.output/'restart-source-mtd.raw').write_bytes(evidence)
                result['restart_source_mtd'] = validate_native_mtd(evidence, begin, end)
                query, begin, end = restart_guard_query(secrets.token_hex(6))
                c.write_all(query + b'\r')
                evidence = c.until(re.compile(rb'(?:^|\r?\n)' + end + rb'\r?\n'), timeout=15)
                c.until(re.compile(rb'(?:^|\r?\n)~ # '), timeout=5)
                (args.output/'restart-source-driver.raw').write_bytes(evidence)
                result['restart_guard'] = validate_restart_guard(evidence, begin, end)
                checkpoint('software-reboot')
                c.write_all(b'reboot -f\r')
                evidence = c.until(b'Restarting system', timeout=20)
                (args.output/'restart-kernel.raw').write_bytes(evidence)
                result['software_reboot'] = {'kernel_restart_marker': True, 'outlet_cycle': False}
                c.state = 'boot-entry'
            checkpoint('fresh-boot-entry')
            with (nullcontext() if args.software_reboot else
                  (args.output/'power-on.txt').open('wb')) as power_log:
                if not args.software_reboot:
                    power_on = subprocess.Popen([args.relay, 'on'], stdout=power_log, stderr=subprocess.STDOUT)
                c.until(b'Press 1 means entering boot mode', timeout=45)
                c.boot_token(b'1')
                c.until(b'input bootmode password', timeout=12)
                c.boot_token(b'Boot4128s!\r')
                c.until(b'Hit any key to stop autoboot', timeout=12)
                c.boot_token(b'\r')
                result['version'] = c.confirm_uboot().decode('ascii', 'backslashreplace')
                if power_on is not None and power_on.wait(timeout=20):
                    raise UARTError('relay on did not confirm success')
                power_on = None

            tftp = f'tftp 0x42000000 {args.tftp_name}'
            transfers = {tftp: len(image.data)}
            allowed = {'printenv ipaddr serverip verify', tftp, 'bootm start 0x42000020'}
            if root:
                root_tftp = f'tftp 0x{normal_ram.ROOT_HEADER:08x} {args.rootfs_tftp_name}'
                transfers[root_tftp] = len(root.data)
                allowed.update({'bdinfo', root_tftp, 'bootm start 0x43ffffc0'})
            if stock_guards:
                allowed.update({'setenv bootargs ' + STOCK_PCI_ARGS, 'printenv bootargs'})
            def command(text, timeout=15):
                if c.state != 'console' or text not in allowed:
                    raise UARTError('command outside RAM-only text protocol')
                index = len(result.setdefault('commands', []))
                result['commands'].append(text)
                start = len(io.received)
                c.write_all(text.encode()+b'\r')
                try:
                    response = c.until(PROMPT, timeout=timeout)
                except UARTError:
                    captured = bytes(io.received[start:])
                    # This is a text-only TFTP wait, never a binary receiver.
                    # Old bootloader net loops can retry forever after their
                    # first PHY check. Abort explicitly and require a fresh
                    # prompt before another attempt; never boot partial data.
                    if text not in transfers or b'TFTP from server' not in captured:
                        raise
                    c.write_all(b'\x03')
                    c.until(PROMPT, timeout=8)
                    response = bytes(io.received[start:])
                (args.output/f'command-{index:02d}.raw').write_bytes(response)
                return response

            checkpoint('verify-environment')
            env = command('printenv ipaddr serverip verify')
            for name, expected in (('ipaddr', args.ipaddr), ('serverip', args.serverip)):
                found = re.findall(rb'^'+name.encode()+rb'=(.*?)\r?$', env, re.M)
                if found != [expected.encode()]:
                    raise UARTError(f'unexpected {name}; no environment mutation attempted: {found}')
            result['verify'] = verify_enabled(env)
            if root:
                checkpoint('verify-normal-ram-layout')
                result['bdinfo'] = normal_ram.validate_bdinfo(
                    command('bdinfo'), len(image.data), len(root.data))
            if stock_guards:
                checkpoint('set-volatile-stock-pci-arguments')
                result['environment_commands'] = True
                result['volatile_bootargs_only'] = True
                command('setenv bootargs ' + STOCK_PCI_ARGS)
                response = command('printenv bootargs')
                if re.findall(rb'^bootargs=(.*?)\r?$', response, re.M) != [STOCK_PCI_ARGS.encode()]:
                    raise UARTError('volatile stock boot arguments did not read back exactly')

            result['uboot_network_used'] = True
            checkpoint('tftp-into-ram')
            time.sleep(3)
            for transfer, size in transfers.items():
                for attempt in range(3):
                    response = command(transfer, timeout=30 if root else 20)
                    sizes = re.findall(rb'Bytes transferred = (\d+)', response)
                    if sizes == [str(size).encode()]:
                        break
                else:
                    raise UARTError('TFTP size not established after three attempts: '+transfer)
            if root:
                checkpoint('ram-root-header-and-crc')
                if c.memory(normal_ram.ROOT_HEADER, 16) != root.data[:64]:
                    raise UARTError('RAM root checksum header differs')
                validate_crc_output(command('bootm start 0x43ffffc0', timeout=30), root,
                                    address=normal_ram.ROOT_HEADER, load=normal_ram.ROOT_START)
                result['root_crc'] = {'validated': True, 'header': f'{root.header_crc:08x}',
                                      'payload': f'{root.data_crc:08x}', 'executed': False}
            checkpoint('ram-header-and-crc')
            header = c.memory(0x42000000, 16) + c.memory(0x42000040, 8)
            if header != image.data[:96]:
                raise UARTError('RAM prefix/header differ from selected file')
            result['ram_header_equal'] = True
            validate_crc_output(command('bootm start 0x42000020'), image)
            result['crc'] = {'validated': True, 'header': f'{image.header_crc:08x}',
                             'payload': f'{image.data_crc:08x}'}
            checkpoint('boot-ram-candidate')
            c.write_all(b'bootm 0x42000020\r')
            c.state = 'linux'
            if root:
                boot = c.until(re.compile(rb'Please press Enter to activate this console\.|'
                                          rb'H199A_(?:PROD_)?OVERLAY_FAILED[^\r\n]*|Kernel panic[^\r\n]*'), timeout=180)
                (args.output/'boot.raw').write_bytes(boot)
                if qualify:
                    result['production_qualify_boot'] = normal_ram.validate_production_qualify_boot(boot)
                else:
                    result['normal_boot'] = normal_ram.validate_boot(boot)
                c.write_all(b'\r')
                c.until(normal_ram.NORMAL_PROMPT, timeout=30)
                # procd keeps emitting module-load and netifd messages to the
                # console for several seconds after activation; that printk can
                # interleave into a framed acceptance query and corrupt it
                # (observed on the first normal-X boot, 2026-11-15). Lower the
                # console loglevel once and let it settle before querying. This
                # changes only console verbosity: no storage, flash or
                # environment state, and boot markers were already validated
                # from the full-verbosity boot log above.
                c.write_all(b'echo 1 >/proc/sys/kernel/printk\r')
                c.until(normal_ram.NORMAL_PROMPT, timeout=15)

                def query_normal(query, begin, end, label):
                    c.write_all(query+b'\r')
                    response = c.until(re.compile(rb'(?:^|\r?\n)'+end+rb'\r?\n'), timeout=20)
                    c.until(normal_ram.NORMAL_PROMPT, timeout=10)
                    (args.output/f'normal-{label}.raw').write_bytes(response)
                    return response

                if qualify:
                    # Production write-policy qualification: exact writability
                    # matrix, idle (unlatched) policy, the compiled allow/deny map
                    # against the independent spec model, and no overlay attached.
                    checkpoint('verify-production-qualify')
                    query, begin, end = native_readonly_query(secrets.token_hex(6), mount=False)
                    evidence = query_normal(query, begin, end, 'mtd')
                    result['native_mtd'] = validate_native_mtd(evidence, begin, end,
                                                               writable=normal_ram.QUALIFY_WRITABLE)
                    result['production_qualify_runtime'] = {}
                    for label, (query, begin, end) in normal_ram.production_qualify_queries(
                            secrets.token_hex(6)).items():
                        evidence = query_normal(query, begin, end, label.lower())
                        result['production_qualify_runtime'][label] = \
                            normal_ram.validate_production_qualify_runtime(
                                label, normal_ram.frame_lines(evidence, begin, end))
                    result['success'] = True
                    checkpoint('production-qualify-ready')
                    return

                checkpoint('verify-normal-userspace')
                query, begin, end = native_readonly_query(secrets.token_hex(6), mount=False)
                evidence = query_normal(query, begin, end, 'mtd')
                result['native_mtd'] = validate_native_mtd(evidence, begin, end, write_test=True)
                result['normal_runtime'] = {}
                for label, (query, begin, end) in normal_ram.runtime_queries(secrets.token_hex(6)).items():
                    if label == 'STATE':
                        continue
                    evidence = query_normal(query, begin, end, label.lower())
                    result['normal_runtime'][label] = normal_ram.validate_runtime(
                        label, normal_ram.frame_lines(evidence, begin, end))
                # Console availability precedes S95done. Observe fstools READY;
                # do not invoke mount_root done to manufacture that transition.
                deadline = time.monotonic()+90
                for attempt in range(46):
                    query, begin, end = normal_ram.runtime_queries(secrets.token_hex(6))['STATE']
                    evidence = query_normal(query, begin, end, f'state-{attempt:02d}')
                    if normal_ram.validate_runtime('STATE', normal_ram.frame_lines(evidence, begin, end)):
                        result['normal_runtime']['fstools_ready'] = True
                        break
                    if time.monotonic() >= deadline:
                        raise UARTError('fstools did not reach READY within the acceptance window')
                    time.sleep(2)
                else:
                    raise UARTError('fstools readiness attempts exhausted')
                # An old READY symlink cannot vouch for the current mount.
                # Recheck after init finishes, including a possible read-only
                # transition during the readiness wait.
                query, begin, end = normal_ram.runtime_queries(secrets.token_hex(6))['MOUNTS']
                evidence = query_normal(query, begin, end, 'mounts-final')
                result['normal_runtime']['final_mounts'] = normal_ram.validate_runtime(
                    'MOUNTS', normal_ram.frame_lines(evidence, begin, end))
                result['success'] = True
                checkpoint('normal-openwrt-ready')
                return
            if stock_guards:
                boot = c.until(STOCK_PANIC, timeout=120)
                (args.output/'boot.raw').write_bytes(boot)
                result['stock_pci_stop'] = validate_stock_pci_log(boot)
                # The disabled drivers provide containment; power-off follows
                # the observation and is not a race against storage startup.
                relay('off')
                result['left_powered_off'] = True
                result['success'] = True
                checkpoint('stock-pci-reference-captured')
                return
            boot = c.until(re.compile(rb'(?:^|\r?\n)~ # '), timeout=120)
            (args.output/'boot.raw').write_bytes(boot)
            validate_boot_markers(boot, args.storage_backend)
            if args.storage_backend.startswith('native-'):
                ubi_test = args.storage_backend == 'native-ubi-test'
                write_test = args.storage_backend in ('native-write-test', 'native-ubi-test')
                checkpoint('verify-native-protection')
                query, begin, end = native_readonly_query(secrets.token_hex(6))
                time.sleep(.3)
                c.write_all(query + b'\r')
                evidence = c.until(re.compile(rb'(?:^|\r?\n)' + end + rb'\r?\n'), timeout=40)
                c.until(re.compile(rb'(?:^|\r?\n)~ # '), timeout=5)
                (args.output/'native-readonly.raw').write_bytes(evidence)
                result['native_mtd'] = validate_native_mtd(evidence, begin, end, write_test=write_test)
                if write_test:
                    query, begin, end = write_test_partition_query(secrets.token_hex(6), ubi=ubi_test)
                    c.write_all(query + b'\r')
                    evidence = c.until(re.compile(rb'(?:^|\r?\n)' + end + rb'\r?\n'), timeout=20)
                    c.until(re.compile(rb'(?:^|\r?\n)~ # '), timeout=5)
                    (args.output/'native-write-window.raw').write_bytes(evidence)
                    result['write_test_window'] = validate_write_test_partition(evidence, begin, end, ubi=ubi_test)
                if ubi_test:
                    query, begin, end = ubi_guard_query(secrets.token_hex(6))
                    c.write_all(query + b'\r')
                    evidence = c.until(re.compile(rb'(?:^|\r?\n)' + end + rb'\r?\n'), timeout=20)
                    c.until(re.compile(rb'(?:^|\r?\n)~ # '), timeout=5)
                    (args.output/'native-ubi-guard.raw').write_bytes(evidence)
                    result['ubi_guard'] = validate_ubi_guard(evidence, begin, end)
            result['success'] = True
            checkpoint('linux-shell-ready')
        except BaseException as error:
            result['error'] = repr(error)
            if power_on is not None:
                # Let an already issued ON settle before issuing the cleanup OFF.
                try: power_on.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    power_on.kill();power_on.wait()
            relay('off')
            result['left_powered_off'] = True
            checkpoint('failed')
            raise
        finally:
            if io:
                (args.output/'uart.raw').write_bytes(io.received)
                # The persistent monitor still holds RX, so this is not last-close.
                io.close()


if __name__ == '__main__':
    main()
