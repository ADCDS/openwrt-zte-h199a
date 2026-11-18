#!/usr/bin/env python3
"""Ladder step 5: passively observe a production sysupgrade, optionally inject
a power cut at a chosen write phase, then observe the following boot.

The upgrade itself is launched beforehand (detached, output to /dev/console)
with uart-normal-command.py; pass the raw-log size taken BEFORE that launch as
--from-offset. This tool then holds the UART TX lock and never writes a byte.

Phase A (upgrade, from the console): platform.sh's ordered messages
  h199a: writing rootfs / verifying rootfs / writing kernel1 /
  verifying kernel1 / writing header / verifying header, then the restart.
With --cut-at <phase>, the outlet is switched OFF the moment that message
appears (the write it announces is then in flight), and back ON 8 s later.

Phase B (boot): the bootloader either accepts bank A (firmware [0], verify
kernel+fs success) and OpenWrt comes up  -> outcome "openwrt" (router left ON),
or falls back to bank B (firmware [1])   -> outcome "stock-fallback", power is
cut immediately so stock never runs. Anything else (timeout, panic, no
bootloader decision) is a FAILURE and the router is powered off.

Without --cut-at the only passing outcome is "openwrt"; with it, both
outcomes pass (never a brick), and the observed one is recorded.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import time

UPGRADE = [
    ('writing-rootfs', rb'h199a: writing rootfs'),
    ('verifying-rootfs', rb'h199a: verifying rootfs'),
    ('writing-kernel1', rb'h199a: writing kernel1'),
    ('verifying-kernel1', rb'h199a: verifying kernel1'),
    ('writing-header', rb'h199a: writing header'),
    ('verifying-header', rb'h199a: verifying header'),
    # the kernel's restart line, or (if it was not printed) the bootloader's first prompt
    ('restart', rb'reboot: Restarting system|Restarting system|Press 1 means entering boot mode'),
]
UPGRADE_FATAL = rb'MISMATCH|h199a: write \S+ failed|extract failed|Image check failed|Kernel panic'
BOOT_A = [
    ('select_bank_a', rb'pdt_start_kernel \[0\]firmware kernle@700000'),
    ('verify_kernel', rb'verify kernel success!!'),
    ('verify_fs', rb'verify fs success!!'),
    ('production_cmdline', rb'Kernel command line:[^\r\n]*spi_zx279128\.production=1'),
    ('squashfs_root', rb'VFS: Mounted root \(squashfs filesystem\) readonly'),
    ('ubifs_overlay', rb'mount_root: switching to ubifs overlay'),
    ('console_ready', rb'Please press Enter to activate this console\.'),
]
BANK_B = rb'pdt_start_kernel \[1\]firmware'
BOOT_FATAL = rb'Kernel panic|H199A V9\.1 login:|SQUASHFS error|ubi0 error:|Bad Data CRC|Bad Magic Number'
BOOT_NOTES = rb'[^\r\n]*(?:correct header has been found @[0-9a-f]+|verify (?:kernel|fs)[^\r\n]*|Total found[^\r\n]*)'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--execute', action='store_true', required=True)
    ap.add_argument('--raw-log', type=Path, required=True)
    ap.add_argument('--from-offset', type=int, required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--relay', default='tomada')
    ap.add_argument('--cut-at', choices=[n for n, _ in UPGRADE[:-1]])
    ap.add_argument('--upgrade-timeout', type=float, default=600)
    ap.add_argument('--boot-timeout', type=float, default=200)
    ap.add_argument('--launch-token', required=True,
                    help='a per-run NONCE echoed by the launch command (e.g. "launched-<hex>"); '
                         'upgrade messages count only after its first appearance')
    a = ap.parse_args()
    if not re.fullmatch(r'launched-[0-9a-f]{12,}', a.launch_token):
        ap.error('--launch-token must be a fresh nonce of the form launched-<hex>')
    a.output.mkdir()
    res = {'success': False, 'cut_at': a.cut_at, 'uart_bytes_written': 0, 'upgrade': {}, 'boot': {},
           'outcome': None}
    relay = lambda act: (a.output / f'power-{act}-{time.time():.0f}.txt').write_bytes(
        (lambda r: r.stdout + r.stderr)(subprocess.run([a.relay, act], capture_output=True, timeout=45, check=True)))
    log = a.raw_log.open('rb')  # follows the symlink to the live capture
    size = os.fstat(log.fileno()).st_size
    # A stale offset (e.g. `stat` of the symlink itself) would replay old upgrade
    # messages and cut power at the wrong moment: refuse it.
    if not (0 <= size - a.from_offset <= 256 << 10):
        raise SystemExit(f'--from-offset {a.from_offset} is not within 256 KiB of the live log end {size}')
    res['from_offset'] = a.from_offset; res['log_size_at_start'] = size
    log.seek(a.from_offset)
    token = a.launch_token.encode()
    buf = bytearray(); powered = True; leave_on = False

    def pump():
        chunk = log.read(65536)
        if chunk:
            buf.extend(chunk)
        else:
            time.sleep(0.02)

    with open('/tmp/h199a-uart-tx.lock', 'a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            # ---- phase A
            t0 = time.monotonic(); idx = 0; pos = None
            while pos is None:  # anchor on the launch echo; nothing before it counts
                if time.monotonic() - t0 > 60:
                    raise RuntimeError('launch token not seen within 60 s')
                pump()
                at = buf.find(token)
                if at >= 0:
                    pos = at + len(token)
            res['launch_seen'] = round(time.monotonic() - t0, 3)
            while idx < len(UPGRADE):
                if time.monotonic() - t0 > a.upgrade_timeout:
                    raise RuntimeError('upgrade timeout before ' + UPGRADE[idx][0])
                pump()
                m = re.compile(UPGRADE_FATAL).search(buf, pos)
                if m:
                    res['upgrade_fatal'] = m.group(0).decode('ascii', 'replace')
                    raise RuntimeError('upgrade failure text: ' + res['upgrade_fatal'])
                while idx < len(UPGRADE):
                    name, rx = UPGRADE[idx]
                    m = re.compile(rx).search(buf, pos)
                    if not m:
                        break
                    pos = m.end(); idx += 1
                    res['upgrade'][name] = round(time.monotonic() - t0, 3)
                    if name == a.cut_at:
                        relay('off'); powered = False
                        res['cut'] = {'at': name, 't': round(time.monotonic() - t0, 3)}
                        break
                if a.cut_at and not powered:
                    break
            (a.output / 'upgrade.raw').write_bytes(bytes(buf))
            boot_from = pos  # end of the last upgrade marker: nothing after it is skipped
            if not powered:
                time.sleep(8)
                relay('on'); powered = True
            # ---- phase B
            t1 = time.monotonic(); idx = 0; pos = boot_from
            while True:
                if time.monotonic() - t1 > a.boot_timeout:
                    raise RuntimeError('boot timeout; bootloader/OS decision incomplete')
                pump()
                if re.compile(BANK_B).search(buf, boot_from):
                    relay('off'); powered = False
                    res['outcome'] = 'stock-fallback'
                    break
                m = re.compile(BOOT_FATAL).search(buf, boot_from)
                if m:
                    res['boot_fatal'] = m.group(0).decode('ascii', 'replace')
                    raise RuntimeError('boot failure text: ' + res['boot_fatal'])
                while idx < len(BOOT_A):
                    name, rx = BOOT_A[idx]
                    m = re.compile(rx).search(buf, pos)
                    if not m:
                        break
                    pos = m.end(); idx += 1
                    res['boot'][name] = round(time.monotonic() - t1, 3)
                if idx == len(BOOT_A):
                    res['outcome'] = 'openwrt'; leave_on = True
                    break
            res['boot_notes'] = [x.decode('ascii', 'replace').strip()[:160]
                                 for x in re.findall(BOOT_NOTES, bytes(buf[boot_from:]))][:24]
            ok = {'openwrt'} if not a.cut_at else {'openwrt', 'stock-fallback'}
            res['success'] = res['outcome'] in ok
            if not res['success']:
                raise RuntimeError('outcome not acceptable: ' + str(res['outcome']))
        except BaseException as e:
            res['error'] = repr(e)
            raise
        finally:
            (a.output / 'all.raw').write_bytes(bytes(buf))
            if powered and not leave_on:
                try:
                    relay('off'); powered = False
                except Exception as e:
                    res['power_off_error'] = repr(e)
            res['left_powered'] = 'on' if powered else 'off'
            (a.output / 'result.json').write_text(json.dumps(res, indent=2) + '\n')
            log.close()
            print(json.dumps({k: res.get(k) for k in ('success', 'outcome', 'cut', 'upgrade', 'boot',
                                                     'left_powered', 'error')}, indent=1))


if __name__ == '__main__':
    main()
