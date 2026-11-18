#!/usr/bin/env python3
"""R208 read-only early-boot BAUD SWEEP diagnostic (outside the frozen R206 protocol).

Motivation: after the rig changed, the ROM/cspboot/U-Boot window stopped arriving
readably while Linux output stayed byte-perfect at 115200. The early garble is
dominated by 0xFF/0xFE idle-padding, the signature of a source baud LOWER than
the host rate. Chinese threads on this exact symptom ("u-boot garbled, kernel
fine") attribute it to a BootROM/U-Boot UART clock-divisor mismatch and suggest
trying 57600, or 117200 for a CH340.

This is a DIAGNOSTIC, not the R206 experiment: it changes only the HOST baud and
captures the router's TX. It never writes a byte to the router, never enters
boot mode, never touches flash/environment, powers the router OFF after every
cycle and restores the normal logger on exit. Authorized by the operator;
R206's "no baud changes" predeclaration otherwise still stands.
"""
import argparse
import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

PORT = '/dev/h199a-uart'
UNIT = 'h199a-uart-log.service'
TOKENS = (b'non secure uboot', b'Press 1 means entering boot mode', b'cspboot',
          b'U-Boot 2013.04', b'input bootmode password', b'Linux version', b'zx279128-eth')


def run(argv, timeout=45, text=True):
    return subprocess.run(argv, capture_output=True, text=text, timeout=timeout)


def plug(cmd, tries=6):
    """Issue a plug command and require an explicit LIGADA/desligada answer."""
    last = ''
    for _ in range(tries):
        try:
            r = run(['tomada', cmd], timeout=30)
            last = (r.stdout or '').strip().replace('\n', ' ')
            if last:
                return last
        except subprocess.TimeoutExpired:
            last = 'TIMEOUT'
        time.sleep(2)
    raise RuntimeError(f'tomada {cmd} gave no answer: {last!r}')


def logger(action):
    run(['systemctl', '--user', action, UNIT], timeout=30)


def service_active():
    r = run(['systemctl', '--user', 'is-active', UNIT], timeout=15)
    return (r.stdout or '').strip()


def holders():
    r = run(['sudo', '-n', 'python3', str(Path(__file__).resolve().parent / 'h199a_uart_fd.py'),
             '--audit-device', PORT], timeout=20)
    return json.loads(r.stdout)


def set_host_baud(baud):
    """Set an ARBITRARY host baud via termios2/BOTHER.

    glibc's stty only accepts standard rates on this box (it rejects 92160 and
    117200 with 'invalid argument'), and 117200 has no termios constant, so the
    kernel's BOTHER path via TCSETS2 is required.
    """
    import ctypes
    import termios as T

    class Termios2(ctypes.Structure):
        _fields_ = [('c_iflag', ctypes.c_uint), ('c_oflag', ctypes.c_uint),
                    ('c_cflag', ctypes.c_uint), ('c_lflag', ctypes.c_uint),
                    ('c_line', ctypes.c_ubyte), ('c_cc', ctypes.c_ubyte * 19),
                    ('c_ispeed', ctypes.c_uint), ('c_ospeed', ctypes.c_uint)]

    TCSETS2 = 0x402C542B
    BOTHER = 0x1000
    HUPCL = 0x400
    libc = ctypes.CDLL('libc.so.6', use_errno=True)
    fd = os.open(PORT, os.O_RDWR | os.O_NONBLOCK | os.O_NOCTTY | os.O_CLOEXEC)
    try:
        attrs = Termios2()
        attrs.c_cflag = T.CS8 | T.CREAD | T.CLOCAL | HUPCL | BOTHER
        attrs.c_cc[T.VMIN] = 1
        attrs.c_cc[T.VTIME] = 0
        attrs.c_ispeed = attrs.c_ospeed = baud
        if libc.ioctl(fd, TCSETS2, ctypes.byref(attrs)) != 0:
            errno = ctypes.get_errno()
            raise RuntimeError(f'TCSETS2 {baud} failed: {os.strerror(errno)}')
        readback = Termios2()
        if libc.ioctl(fd, 0x802C542A, ctypes.byref(readback)) != 0:  # TCGETS2
            raise RuntimeError('TCGETS2 failed')
        return f'c_ispeed={readback.c_ispeed} c_ospeed={readback.c_ospeed} c_cflag=0x{readback.c_cflag:04x}'
    finally:
        os.close(fd)


def analyse(raw):
    printable = sum(1 for b in raw if 32 <= b < 127 or b in (9, 10, 13))
    hits = {}
    for token in TOKENS:
        index = raw.find(token)
        if index >= 0:
            hits[token.decode()] = index
    return dict(bytes=len(raw), printable=printable,
                printable_ratio=round(printable / max(1, len(raw)), 3),
                nul=raw.count(0), ff=raw.count(0xff), fe=raw.count(0xfe),
                feff_ratio=round((raw.count(0xfe) + raw.count(0xff)) / max(1, len(raw)), 3),
                tokens=hits)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-dir', type=Path, required=True)
    parser.add_argument('--bauds', type=int, nargs='+', default=[57600, 115200, 117200, 38400])
    parser.add_argument('--off-seconds', type=float, default=12)
    parser.add_argument('--capture-seconds', type=float, default=40)
    args = parser.parse_args()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if os.geteuid() == 0:
        parser.error('run as the bench user')
    summary = dict(port=PORT, cycles=[], restored=False, left_powered_off=False)
    were_active = service_active() == 'active'
    try:
        if were_active:
            logger('stop')
        if service_active() == 'active':
            raise RuntimeError('logger did not stop')
        audit = holders()
        if audit.get('complete') is not True or audit.get('errors') or audit.get('holders'):
            raise RuntimeError(f'loggers/others still hold the UART: {audit}')
        for baud in args.bauds:
            print(f'=== host baud {baud} ===', flush=True)
            cycle = dict(baud=baud)
            cycle['stty'] = set_host_baud(baud)
            cycle['off'] = plug('off')
            time.sleep(args.off_seconds)
            raw = bytearray()
            fd = os.open(PORT, os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY | os.O_CLOEXEC)
            try:
                cycle['on'] = plug('on')
                end = time.monotonic() + args.capture_seconds
                while time.monotonic() < end:
                    ready, _, _ = select.select([fd], [], [], min(0.1, max(0, end - time.monotonic())))
                    if not ready:
                        continue
                    while True:
                        try:
                            chunk = os.read(fd, 4096)
                        except BlockingIOError:
                            break
                        if not chunk:
                            break
                        raw.extend(chunk)
                # Power OFF before the descriptor is closed, per the documented
                # last-close/modem-line rule.
                cycle['off_after'] = plug('off')
            finally:
                os.close(fd)
            data = bytes(raw)
            cycle.update(analyse(data))
            path = out / f'baud-{baud}.rx.bin'
            path.write_bytes(data)
            cycle['artifact'] = str(path)
            print(json.dumps(cycle, indent=2), flush=True)
            summary['cycles'].append(cycle)
    finally:
        try:
            plug('off')
            summary['left_powered_off'] = True
        except Exception as error:
            summary['power_off_error'] = repr(error)
        if were_active:
            logger('start')
            time.sleep(1)
            summary['restored'] = service_active() == 'active'
        (out / 'sweep.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps({k: v for k, v in summary.items() if k != 'cycles'}, indent=2), flush=True)
    if not summary['restored'] or not summary['left_powered_off']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
