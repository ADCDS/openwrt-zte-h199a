#!/usr/bin/env python3
"""Ladder step 4: power the router on and PASSIVELY observe an uninterrupted
boot from NAND bank A. Writes no byte to the UART (holds the TX lock so no
other tool can either) and reads RX only from the sole capture's raw log.

Required, in order:  correct header @1720000 -> bootloader selects firmware
[0] at kernel 0x700000 -> verify kernel success -> verify fs success ->
Linux with `spi_zx279128.production=1` on the command line -> squashfs root
mounted -> console ready ("Please press Enter").

Immediate power-OFF on anything that means bank A was not accepted or the
system is not running OpenWrt from bank A: firmware [1] selected (stock bank
B), a stock login prompt, a CRC/verify failure, a kernel panic, or a timeout.
Stock must never run unattended (it may write its own partitions).

On success the router is LEFT ON for acceptance queries over
uart-normal-command.py.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import time

ORDERED = [
    ('header_bank_a', rb'correct header has been found @1720000'),
    ('select_bank_a', rb'pdt_start_kernel \[0\]firmware kernle@700000'),
    ('verify_kernel', rb'verify kernel success!!'),
    ('verify_fs', rb'verify fs success!!'),
    ('uimage_name', rb'Image Name:\s+[^\r\n]+'),
    ('linux', rb'Linux version [^\r\n]+'),
    ('production_cmdline', rb'Kernel command line:[^\r\n]*spi_zx279128\.production=1'),
    ('squashfs_root', rb'VFS: Mounted root \(squashfs filesystem\) readonly'),
    ('console_ready', rb'Please press Enter to activate this console\.'),
]
INFO = [
    ('overlay_hook', rb'[^\r\n]*(?:h199a|production)[^\r\n]*(?:overlay|ubi|rootfs_data)[^\r\n]*'),
    ('ubi_attach', rb'ubi0: attached mtd\d+[^\r\n]*'),
    ('ubifs_mount', rb'UBIFS \(ubi0:\d+\): [^\r\n]*mount[^\r\n]*'),
    ('policy', rb'[^\r\n]*write policy[^\r\n]*'),
    ('fail_stop', rb'[^\r\n]*fail-stop[^\r\n]*'),
]
FATAL = [
    ('selected_bank_b', rb'pdt_start_kernel \[1\]firmware'),
    ('stock_login', rb'H199A V9\.1 login:'),
    ('verify_failed', rb'verify (?:kernel|fs) (?:fail|error)'),
    ('crc_mismatch', rb'(?i)crc (?:error|mismatch|check fail)'),
    ('panic', rb'Kernel panic'),
    ('bad_magic', rb'Bad Magic Number|Bad Data CRC|Bad Header Checksum'),
    ('ubi_error', rb'ubi0 error:'),
    ('squashfs_error', rb'SQUASHFS error'),
]


def relay(name, action, out):
    r = subprocess.run([name, action], capture_output=True, timeout=45, check=True)
    (out / f'power-{action}.txt').write_bytes(r.stdout + r.stderr)


def relay_is_on(name):
    r = subprocess.run([name, 'json'], capture_output=True, timeout=45, check=True, text=True)
    return json.loads(r.stdout).get('1')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--execute', action='store_true', required=True)
    ap.add_argument('--raw-log', type=Path, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--relay', default='tomada')
    ap.add_argument('--timeout', type=float, default=180)
    a = ap.parse_args()
    a.output.mkdir()
    res = {'success': False, 'uart_bytes_written': 0, 'markers': {}, 'info': {}, 'fatal': None}
    save = lambda: (a.output / 'result.json').write_text(json.dumps(res, indent=2) + '\n')
    with open('/tmp/h199a-uart-tx.lock', 'a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        if relay_is_on(a.relay) is not False:
            raise SystemExit('router must be powered off before a fresh NAND boot observation')
        log = a.raw_log.open('rb'); log.seek(0, os.SEEK_END)
        buf = bytearray(); idx = 0; leave_on = False
        try:
            relay(a.relay, 'on', a.output)
            t0 = time.monotonic(); res['power_on_monotonic'] = t0
            while time.monotonic() - t0 < a.timeout:
                chunk = log.read(65536)
                if not chunk:
                    time.sleep(0.05); continue
                buf += chunk
                for name, rx in FATAL:
                    m = re.search(rx, buf)
                    if m:
                        res['fatal'] = {'marker': name, 'text': m.group(0).decode('ascii', 'replace'),
                                        't': round(time.monotonic() - t0, 2)}
                        raise RuntimeError('fatal boot marker: ' + name)
                while idx < len(ORDERED):
                    name, rx = ORDERED[idx]
                    start = res['markers'][ORDERED[idx - 1][0]]['end'] if idx else 0
                    m = re.compile(rx).search(buf, start)
                    if not m:
                        break
                    res['markers'][name] = {'text': m.group(0).decode('ascii', 'replace')[:200],
                                            't': round(time.monotonic() - t0, 2), 'end': m.end()}
                    idx += 1
                if idx == len(ORDERED):
                    time.sleep(2); buf += log.read(1 << 20)
                    break
            for name, rx in INFO:
                res['info'][name] = [x.decode('ascii', 'replace')[:200] for x in re.findall(rx, buf)][:8]
            if idx < len(ORDERED):
                res['missing'] = [n for n, _ in ORDERED[idx:]]
                raise RuntimeError('timeout before ' + ORDERED[idx][0])
            res['success'] = True; leave_on = True
        except BaseException as e:
            res['error'] = repr(e)
            raise
        finally:
            (a.output / 'boot.raw').write_bytes(bytes(buf))
            if not leave_on:
                try:
                    relay(a.relay, 'off', a.output); res['left_powered_off'] = True
                except Exception as e:
                    res['left_powered_off'] = False; res['power_off_error'] = repr(e)
            else:
                res['left_powered_on'] = True
            save(); log.close()
            print(json.dumps({k: res[k] for k in ('success', 'fatal') if k in res}
                             | {'markers': {k: v['text'][:90] for k, v in res['markers'].items()}}, indent=2))


if __name__ == '__main__':
    main()
