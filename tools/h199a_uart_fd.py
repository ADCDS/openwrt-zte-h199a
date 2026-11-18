"""Parent-only UART building blocks; no device access on import.

Lease acquisition/release REQUIRE the router externally confirmed powered off.
No service, relay, network, boot, baud-switch or automatic recovery actions here.
Keep the SAME existing logger-lock inode. Proc auditing is metadata-only and must
be complete; TIOCEXCL does not exclude old descriptors or privileged openers.
Caller must quiesce all writers and stop the supervising logger UNIT first.

Timeout reads return b''; EOF/disconnection raises. Writes return only the known
accepted prefix. No tcflush/tcdrain, device reopening, log-tail reads or DTR/RTS
ioctls. Raw115200/8N1 preserves HUPCL; caller powers off before releasing because
modem-line wiring/driver last-close effects are not certified.
"""
from __future__ import annotations
import argparse
import errno
import fcntl
import json
import math
import os
from pathlib import Path
import re
import select
import stat
import struct
import termios
import time
from xmodem_h199a import TransferPlan, SenderOptions, SendResult, send as send_xmodem


class UARTError(RuntimeError):
    pass


def identity(s):
    return dict(dev=s.st_dev, inode=s.st_ino, rdev=s.st_rdev, uid=s.st_uid,
                mode=stat.S_IFMT(s.st_mode))


def audit_device(path):
    """Enumerate proc descriptor METADATA only; any access denial invalidates it."""
    target = os.stat(path)
    if not stat.S_ISCHR(target.st_mode):
        raise UARTError('UART path is not a character device')
    holders, errors = [], []
    for pid in os.listdir('/proc'):
        if not pid.isdecimal():
            continue
        folder = f'/proc/{pid}/fd'
        try:
            names = os.listdir(folder)
        except OSError as e:
            if e.errno not in (errno.ENOENT, errno.ESRCH):
                errors.append([folder, e.errno])
            continue
        for fd in names:
            try:
                s = os.stat(f'{folder}/{fd}')
                if stat.S_ISCHR(s.st_mode) and s.st_rdev == target.st_rdev:
                    holders.append([int(pid), int(fd)])
            except OSError as e:
                if e.errno not in (errno.ENOENT, errno.ESRCH, errno.EBADF):
                    errors.append([f'{folder}/{fd}', e.errno])
    return dict(device=identity(target), holders=sorted(holders), errors=errors,
                complete=not errors)


def check_audit(result, expected, allowed):
    if (result.get('complete') is not True or result.get('errors') != [] or
            result.get('device') != expected or
            sorted(result.get('holders', [])) != sorted([list(x) for x in allowed])):
        raise UARTError(f'UART ownership audit failed: {result}')


def raw_attrs(original):
    attrs = list(original)
    attrs[6] = list(original[6])
    attrs[0] = attrs[1] = attrs[3] = 0
    clear = termios.CSIZE | termios.PARENB | termios.PARODD | termios.CSTOPB
    clear |= getattr(termios, 'CRTSCTS', 0) | getattr(termios, 'CMSPAR', 0)
    clear |= termios.CBAUD | getattr(termios, 'CIBAUD', 0)
    attrs[2] = (attrs[2] & ~clear) | termios.CS8 | termios.CREAD | termios.CLOCAL | termios.B115200
    attrs[4] = attrs[5] = termios.B115200
    attrs[6][termios.VMIN] = 1
    attrs[6][termios.VTIME] = 0
    return attrs


class Lease:
    """One UART FD, one retained lock FD; caller owns power/service transaction."""
    def __init__(self):
        self.fd = self.lock_fd = None
        self.old_attrs = None
        self.path = None
        self.expected = None

    @classmethod
    def acquire(cls, path, lock_path, *, powered_off, audit=audit_device):
        if powered_off is not True:
            raise UARTError('power-off confirmation required before lease acquisition')
        self = cls()
        self.path = str(path)
        self.audit = audit
        before = os.stat(path)
        if not stat.S_ISCHR(before.st_mode):
            raise UARTError('not a character device')
        self.expected = identity(before)
        lock = os.lstat(lock_path)
        if not stat.S_ISREG(lock.st_mode) or lock.st_uid != os.getuid():
            raise UARTError('logger lock must be an existing owned regular file')
        self.lock_identity = identity(lock)
        self.lock_path = str(lock_path)
        try:
            self.lock_fd = os.open(lock_path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.check_lock()
            check_audit(audit(path), self.expected, [])
            self.fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_NOCTTY | os.O_CLOEXEC)
            if identity(os.fstat(self.fd)) != self.expected:
                raise UARTError('device identity changed at open')
            fcntl.ioctl(self.fd, termios.TIOCEXCL)
            self.old_attrs = termios.tcgetattr(self.fd)
            wanted = raw_attrs(self.old_attrs)
            termios.tcsetattr(self.fd, termios.TCSANOW, wanted)
            if termios.tcgetattr(self.fd) != wanted:
                raise UARTError('raw UART configuration did not read back exactly')
            self.recheck()
            self.transport = FDTransport(self.fd, self.check_identity)
            return self
        except BaseException:
            self.release(powered_off=True)
            raise

    def check_lock(self):
        if (identity(os.fstat(self.lock_fd)) != self.lock_identity or
                identity(os.lstat(self.lock_path)) != self.lock_identity):
            raise UARTError('logger lock inode/identity changed')

    def check_identity(self):
        if self.fd is None or identity(os.fstat(self.fd)) != self.expected or identity(os.stat(self.path)) != self.expected:
            raise UARTError('UART was closed, replaced or re-enumerated')
        self.check_lock()

    def recheck(self):
        self.check_identity()
        check_audit(self.audit(self.path), self.expected, [(os.getpid(), self.fd)])

    def release(self, *, powered_off):
        if powered_off is not True:
            raise UARTError('power-off confirmation required; no implicit restoration')
        error = None
        if self.fd is not None:
            try:
                if self.old_attrs is not None:
                    termios.tcsetattr(self.fd, termios.TCSANOW, self.old_attrs)
                fcntl.ioctl(self.fd, termios.TIOCNXCL)
            except OSError as e:
                error = e
            finally:
                os.close(self.fd)
                self.fd = None
        if self.lock_fd is not None:
            os.close(self.lock_fd)
            self.lock_fd = None
        if error is not None:
            raise UARTError(f'powered-off release failed: {error}') from error


class FDTransport:
    def __init__(self, fd, identity_check=lambda: None, *, max_rx=262144):
        flags = fcntl.fcntl(fd, fcntl.F_GETFL)
        if not flags & os.O_NONBLOCK or not fcntl.fcntl(fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC:
            raise UARTError('FD must be nonblocking and close-on-exec')
        self.fd, self.identity_check = fd, identity_check
        self.pending = bytearray()
        self.received = bytearray()
        self.tx_accepted = 0
        self.max_rx = max_rx
        self.writes_allowed = True
        self.failed = False

    def check(self):
        if self.failed:
            raise UARTError('transport failed; no further I/O')
        try:
            self.identity_check()
        except BaseException:
            self.failed = True
            raise

    @staticmethod
    def deadline(timeout):
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or timeout < 0:
            raise ValueError('invalid timeout')
        return time.monotonic() + timeout

    def pushback(self, data):
        if not isinstance(data, bytes) or len(self.pending) + len(data) > 8192:
            raise UARTError('invalid or excessive parser remainder')
        self.pending[:0] = data

    def read(self, size, timeout):
        if type(size) is not int or not 1 <= size <= 4096:
            raise ValueError('invalid read size')
        end = self.deadline(timeout)
        self.check()
        if self.pending:
            data = bytes(self.pending[:size]);del self.pending[:size]
            return data
        while True:
            try:
                data = os.read(self.fd, size)
                if not data:
                    raise UARTError('EOF/disconnection, not timeout')
                self.check()
                if len(self.received) + len(data) > self.max_rx:
                    raise UARTError('RX evidence budget exceeded')
                self.received.extend(data)
                return data
            except BlockingIOError:
                left = end - time.monotonic()
                if left <= 0:
                    return b''
                select.select([self.fd], [], [], left)
            except InterruptedError:
                if time.monotonic() >= end:
                    return b''
            except BaseException:
                self.failed = True
                raise

    def write(self, data, timeout):
        if not isinstance(data, bytes) or not data:
            raise ValueError('nonempty bytes required')
        end = self.deadline(timeout)
        self.check()
        if not self.writes_allowed:
            raise UARTError('writes prohibited in unverified state')
        while True:
            if time.monotonic() >= end:
                raise TimeoutError('write deadline; no speculative replay')
            try:
                n = os.write(self.fd, data)
                if not 0 < n <= len(data):
                    raise UARTError('invalid write progress')
                self.tx_accepted += n
                self.check()
                return n
            except BlockingIOError:
                left = end - time.monotonic()
                if left <= 0:
                    raise TimeoutError('write deadline')
                select.select([], [self.fd], [], left)
            except InterruptedError:
                continue
            except BaseException:
                self.failed = True
                raise


PROMPT = re.compile(rb'(?:^|\r?\n)=> ')
BANNER = b'xmodem at 42000000\r\n'
MEMORY_LINE = re.compile(rb'^([0-9a-fA-F]{8}):((?: [0-9a-fA-F]{8}){1,4})(?:\s|$)', re.M)


def parse_memory_response(text, address, count):
    """Parse ``md.l`` output from RAW BYTES, not a strict-ASCII decode.

    Measured on this bench (artifacts/r206/cold-default-c): line/byte noise can
    corrupt part of a U-Boot command echo while the ``md.l`` response itself is
    intact and byte-exact. Decoding the whole response strictly turned that
    recoverable echo noise into a fatal UnicodeDecodeError. Parsing bytes keeps
    the evidence contract unchanged and still fails closed: the response must
    contain exactly the requested addresses, each exactly once, and the caller
    compares every reconstructed byte against the SHA-bound backup.
    """
    if not isinstance(text, (bytes, bytearray)):
        raise TypeError('raw bytes response required')
    if type(address) is not int or type(count) is not int or not 1 <= count <= 16:
        raise ValueError('bounded memory parse required')
    text = bytes(text)
    words = {}
    for match in MEMORY_LINE.finditer(text):
        base = int(match[1], 16)
        for index, value in enumerate(match[2].split()):
            word = base + 4 * index
            if word in words:
                raise UARTError('duplicate memory response')
            words[word] = int(value, 16)
    addresses = [address + 4 * index for index in range(count)]
    if set(words) != set(addresses):
        raise UARTError('incomplete/unexpected memory response')
    return struct.pack('<' + 'I' * count, *(words[word] for word in addresses))


def console_noise(data):
    """Bounded, non-fatal stats about raw console bytes (diagnostics only)."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError('bytes required')
    data = bytes(data)
    return dict(bytes=len(data),
                nonascii=sum(1 for b in data if b > 0x7e or (b < 0x20 and b not in (9, 10, 13))),
                nul=data.count(0), ff=data.count(0xff))


class Console:
    """Explicit state machine. Unknown transfer outcomes never get text writes."""
    def __init__(self, transport):
        self.io = transport
        self.state = 'boot-entry'
        self.uboot_log = []

    def until(self, marker, timeout=10, limit=65536):
        end = time.monotonic() + timeout
        buf = bytearray()
        while True:
            if self.state == 'boot-entry' and any(x in buf for x in (b'Starting kernel', b'Booting Linux', b'Kernel command line:')):
                self.state = 'unknown';self.io.writes_allowed = False
                raise UARTError('unexpected OS boot; caller must power off immediately')
            match = marker.search(buf) if hasattr(marker, 'search') else None
            index = buf.find(marker) if isinstance(marker, bytes) else -1
            stop = match.end() if match else index + len(marker) if index >= 0 else None
            if stop is not None:
                self.io.pushback(bytes(buf[stop:]))
                return bytes(buf[:stop])
            if len(buf) >= limit or time.monotonic() >= end:
                raise UARTError('expected console marker absent within bounds')
            buf.extend(self.io.read(min(512, limit-len(buf)), max(0, end-time.monotonic())))

    def write_all(self, data, timeout=3):
        end = time.monotonic() + timeout
        at = 0
        while at < len(data):
            left = end - time.monotonic()
            if left <= 0:
                raise UARTError('console write deadline; state unknown')
            at += self.io.write(data[at:], left)

    def boot_token(self, data):
        if self.state != 'boot-entry' or data not in (b'1', b'Boot4128s!\r', b'\r'):
            raise UARTError('unapproved boot-entry token/state')
        self.write_all(data)

    def confirm_uboot(self):
        if self.state != 'boot-entry':
            raise UARTError('boot-entry state required')
        self.until(PROMPT)
        self.state = 'console'
        result = self.command('version')
        if b'U-Boot 2013.04 (Jul 06 2021 - 14:44:21)' not in result:
            self.state = 'unknown';self.io.writes_allowed = False
            raise UARTError('unexpected bootloader version')
        return result

    def command(self, text):
        # No generic shell, flash, env, reset, network or boot command capability.
        if text not in ('version', 'bdinfo') and not re.fullmatch(r'md\.l 0x[0-9a-f]{8} 0x[0-9a-f]+', text):
            raise UARTError('command not allowed')
        if text.startswith('md.l '):
            _, a, n = text.split();a, n = int(a, 16), int(n, 16)
            if a % 4 or not 1 <= n <= 16 or not 0x40000000 <= a < a + 4*n <= 0x48000000:
                raise UARTError('read outside bounded DRAM')
        if self.state != 'console':
            raise UARTError('verified console required')
        try:
            if self.io.read(1, 0):
                raise UARTError('unexpected buffered console input')
            sent = text.encode('ascii') + b'\r'
            self.write_all(sent)
            response = self.until(PROMPT)
            # Diagnostics only: a corrupted echo is recorded, never credited and
            # never fatal. Gate decisions still come from the parsed evidence.
            self.uboot_log.append(dict(command=text, echo_intact=response.startswith(sent),
                                       **console_noise(response)))
            return response
        except BaseException:
            self.state = 'unknown';self.io.writes_allowed = False
            raise

    def transfer(self, plan, *, options=None, cancel_requested=None):
        # Validate/copy everything before entering a potentially long-lived receiver.
        if not isinstance(plan, TransferPlan):
            raise TypeError('prevalidated TransferPlan required')
        plan = TransferPlan(plan.payload, plan.block_size)
        options = SenderOptions() if options is None else SenderOptions(**vars(options))
        if cancel_requested is not None and not callable(cancel_requested):
            raise TypeError('invalid cancellation callback')
        if self.state != 'console':
            raise UARTError('verified console required')
        try:
            if self.io.read(1, 0):
                raise UARTError('unexpected buffered pre-transfer input')
            self.state = 'transfer'
            self.write_all(b'xmodem 42000000\r')
            self.until(BANNER, timeout=10, limit=4096)  # retain adjacent binary C
            result = send_xmodem(plan, self.io, options=options, cancel_requested=cancel_requested)
            self.state = 'await-prompt';self.io.writes_allowed = False
            if (not isinstance(result, SendResult) or not result.protocol_complete or
                    result.acknowledged_blocks != plan.blocks or result.payload_bytes != len(plan.payload) or
                    result.padded_bytes != plan.padded_bytes):
                raise UARTError('sender did not establish protocol completion')
            self.until(PROMPT, timeout=5, limit=4096)  # passive only after EOT
            self.state = 'console';self.io.writes_allowed = True
            return result
        except BaseException:
            self.state = 'unknown';self.io.writes_allowed = False
            raise

    def memory(self, address, count):
        response = self.command(f'md.l 0x{address:08x} 0x{count:x}')
        return parse_memory_response(response, address, count)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Metadata-only UART ownership audit; never opens UART')
    parser.add_argument('--audit-device', required=True)
    args = parser.parse_args()
    print(json.dumps(audit_device(args.audit_device)))
