#!/usr/bin/env python3
"""R208 read-only UART RX error probe (TIOCGICOUNT) + timestamped capture.

Question this answers: when the router's early boot output fails to arrive, is
the host (a) OVERRUNNING (data arrived but the reader/driver dropped it), or
(b) seeing FRAME/PARITY/BREAK errors (signal or baud problem), or (c) simply
receiving nothing at all (path dead / not driven)?

Read-only: never writes a byte to the router, never enters boot mode, powers the
router OFF before releasing the port and restores the normal logger on exit.
Outside the frozen R206 protocol (host-side only).
"""
import argparse
import fcntl
import json
import os
import struct
import subprocess
import time
from pathlib import Path

PORT = '/dev/h199a-uart'
UNIT = 'h199a-uart-log.service'
TIOCGICOUNT = 0x545D
# struct serial_icounter_struct: 4 handshake + rx/tx + frame/overrun/parity/brk
# + buf_overrun + reserved[9]  -> 20 ints
ICOUNT_FIELDS = ('cts', 'dsr', 'rng', 'dcd', 'rx', 'tx', 'frame', 'overrun',
                 'parity', 'brk', 'buf_overrun')
ICOUNT_STRUCT = struct.Struct('20i')


def run(argv, timeout=40):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout)


def plug(cmd, tries=6):
    for _ in range(tries):
        try:
            r = run(['tomada', cmd], timeout=30)
            if r.stdout.strip():
                return r.stdout.strip().replace('\n', ' ')
        except subprocess.TimeoutExpired:
            pass
        time.sleep(2)
    raise RuntimeError(f'tomada {cmd} gave no answer')


def icount(fd):
    try:
        raw = fcntl.ioctl(fd, TIOCGICOUNT, b'\0' * ICOUNT_STRUCT.size)
    except OSError as error:
        return {'unsupported': error.strerror or str(error)}
    values = ICOUNT_STRUCT.unpack(raw)
    return dict(zip(ICOUNT_FIELDS, values))


def delta(before, after):
    if 'unsupported' in before or 'unsupported' in after:
        return before
    return {k: after[k] - before[k] for k in ICOUNT_FIELDS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out-prefix', type=Path, required=True)
    parser.add_argument('--seconds', type=float, default=120)
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error('run as the bench user')
    out = args.out_prefix.resolve()
    unit_active = run(['systemctl', '--user', 'is-active', UNIT]).stdout.strip() == 'active'
    if unit_active:
        run(['systemctl', '--user', 'stop', UNIT], 30)
    if run(['systemctl', '--user', 'is-active', UNIT]).stdout.strip() == 'active':
        raise SystemExit('logger did not stop')
    result = {}
    try:
        run(['stty', '-F', PORT, '115200', 'cs8', '-cstopb', '-parenb', '-echo',
             'raw', '-ixon', '-crtscts'], 15)
        fd = os.open(PORT, os.O_RDONLY | os.O_NONBLOCK | os.O_NOCTTY | os.O_CLOEXEC)
        try:
            result['icount_before'] = icount(fd)
            result['stty'] = run(['stty', '-F', PORT, '-a'], 15).stdout.strip().splitlines()[0]
            result['off'] = plug('off')
            time.sleep(12)
            t0 = time.monotonic()
            result['on'] = plug('on')
            chunks, raw = [], bytearray()
            while time.monotonic() - t0 < args.seconds:
                try:
                    data = os.read(fd, 4096)
                except BlockingIOError:
                    time.sleep(0.005)
                    continue
                if data:
                    chunks.append([round(time.monotonic() - t0, 3), len(data)])
                    raw.extend(data)
            result['off_after'] = plug('off')
            result['icount_after'] = icount(fd)
        finally:
            os.close(fd)
        result['icount_delta'] = delta(result['icount_before'], result['icount_after'])
        result['chunks'] = chunks
        result['bytes'] = len(raw)
        data = bytes(raw)
        out.with_suffix('.rx.bin').write_bytes(data)
        printable = sum(1 for b in data if 32 <= b < 127 or b in (9, 10, 13))
        result['printable_ratio'] = round(printable / max(1, len(data)), 3)
        result['tokens'] = {t.decode(): data.find(t) for t in
                            (b'Boot SPI NAND', b'non secure uboot', b'Press 1 means entering boot mode',
                             b'cspboot', b'U-Boot 2013.04', b'Linux version', b'zx279128-eth')}
    finally:
        try:
            plug('off')
            result['left_powered_off'] = True
        except Exception as error:
            result['power_off_error'] = repr(error)
        if unit_active:
            run(['systemctl', '--user', 'start', UNIT], 30)
            time.sleep(1)
            result['logger_restored'] = run(['systemctl', '--user', 'is-active', UNIT]).stdout.strip()
        out.with_suffix('.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'chunks'}, indent=2))
    print('first 16 chunks:', result.get('chunks', [])[:16])


if __name__ == '__main__':
    main()
