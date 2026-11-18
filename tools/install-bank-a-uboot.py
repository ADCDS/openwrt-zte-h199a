#!/usr/bin/env python3
"""Guarded first install of a production image into bank A over U-Boot TFTP.

Ladder step 3 of docs/INSTALL.md §12.7. It writes exactly three bank-A
partitions, in the order rootfs -> kernel1 -> header (header LAST = commit
point), and nothing else:

  rootfs  0x00a00000 + 0x00d20000
  kernel1 0x00700000 + 0x00300000
  header  0x01720000 + 0x00020000

Every U-Boot command is drawn from a closed set derived from that table; the
set contains no other flash offset, no environment write, no saveenv, no
reset/boot command. For each part it:

  1. TFTPs the part TWICE (into 0x42000000 and 0x44000000) and requires the
     exact byte count both times and `cmp.b` equality of the two copies,
     before anything is erased;
  2. `nand erase` / `nand write` / `nand read` into 0x44000000 / `cmp.b`,
     rejecting any "Skipping bad block", any error text, a wrong echoed
     offset/size, or a short compare.

UART-corruption guard: every command line is typed WITHOUT its carriage
return, the bootloader's character echo must equal the intended line exactly,
and only then is CR sent; a mismatching echo is discarded with Ctrl-C (the
line never executes). A flipped digit can therefore not turn a bank-A erase
into a bootloader erase.

Any failure powers the router OFF and never lets it autoboot (a partially
written bank A must not boot stock bank B unattended). Success also ends
powered off; boot-from-NAND acceptance is a separate step.

Host-side preflight: the sysupgrade tar is re-validated with
verify-production-image.py against the unit's header template, the three
parts are extracted, and the TFTP root must serve byte-identical files.
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import time

from h199a_uart_fd import Console, PROMPT, UARTError
from h199a_cold_r206 import verify_enabled

TOOLS = Path(__file__).resolve().parent


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, TOOLS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


BLOCK = 0x20000
BANK_A = (0x00700000, 0x01740000)
LOAD = 0x42000000
VERIFY = 0x44000000
UBOOT_RELOC = 0x47f00000
# (tftp name, partition, offset, length) - order is the write order.
PARTS = (
    ('rootfs', 'rootfs', 0x00a00000, 0x00d20000),
    ('kernel', 'kernel1', 0x00700000, 0x00300000),
    ('header', 'header', 0x01720000, 0x00020000),
)
TFTP_NAMES = ('kernel', 'rootfs', 'header')  # the only names tftp-readonly.py serves


def check_plan(parts=PARTS):
    """Static proof that the plan cannot leave bank A."""
    seen = []
    for name, _, off, n in parts:
        if name not in TFTP_NAMES:
            raise ValueError(f'unservable TFTP name {name}')
        if off % BLOCK or n % BLOCK or n <= 0:
            raise ValueError(f'{name}: not block aligned')
        if not (BANK_A[0] <= off and off + n <= BANK_A[1]):
            raise ValueError(f'{name}: outside bank A')
        for _, s, e in seen:
            if off < e and s < off + n:
                raise ValueError(f'{name}: overlaps another part')
        seen.append((name, off, off + n))
        if not (LOAD + n <= VERIFY and VERIFY + n <= UBOOT_RELOC):
            raise ValueError(f'{name}: RAM buffers overlap')
    if parts[-1][0] != 'header':
        raise ValueError('header must be written last')
    return True


def part_commands(name, off, n):
    return {
        'tftp_load': f'tftp 0x{LOAD:08x} {name}',
        'tftp_verify': f'tftp 0x{VERIFY:08x} {name}',
        'cmp': f'cmp.b 0x{LOAD:08x} 0x{VERIFY:08x} 0x{n:x}',
        'erase': f'nand erase 0x{off:x} 0x{n:x}',
        'write': f'nand write 0x{LOAD:08x} 0x{off:x} 0x{n:x}',
        'read': f'nand read 0x{VERIFY:08x} 0x{off:x} 0x{n:x}',
    }


def allowed_commands(parts=PARTS):
    check_plan(parts)
    allowed = {'printenv ipaddr serverip verify'}
    for name, _, off, n in parts:
        allowed.update(part_commands(name, off, n).values())
    return frozenset(allowed)


def drill_commands():
    """Recovery drill (ladder step 6): erase ONLY bank A's header, nothing else.
    Without a valid bank-A header the bootloader falls back to stock bank B."""
    name, _, off, n = PARTS[-1]
    assert name == 'header' and (off, n) == (0x01720000, 0x00020000)
    return frozenset({'printenv ipaddr serverip verify', part_commands(name, off, n)['erase']})


DESTRUCTIVE = re.compile(r'^nand (erase|write) ')
# Both bootloader print paths (generic cmd_nand and the vendor "cspboot" zmtd
# path) were read from the unit's own bootloader strings. Any of these means a
# block was skipped, marked bad or failed: the part is then NOT trusted.
FAILURE_TEXT = (b'bad block', b'skip', b'mark bad', b'error', b'fail', b'usage:',
                b'unknown command', b'not aligned', b'out of range', b'already write',
                b'already erase', b'already read', b'break,', b'have no regist')


def _clean(response):
    low = response.lower()
    for bad in FAILURE_TEXT:
        if bad in low:
            raise UARTError(f'failure text {bad!r} in response')


def check_tftp(response, n):
    sizes = re.findall(rb'Bytes transferred = (\d+) \(([0-9a-f]+) hex\)', response)
    if sizes != [(str(n).encode(), f'{n:x}'.encode())]:
        raise UARTError(f'TFTP byte count not exactly {n}: {sizes}')
    return True


def check_cmp(response, n):
    found = re.findall(rb'Total of (\d+) byte\(s\) were the same', response)
    if found != [str(n).encode()]:
        raise UARTError(f'cmp.b not equal over {n} bytes: {found}')
    if re.search(rb'(?:byte|word|halfword) at 0x', response):
        raise UARTError('cmp.b reported a difference')
    return True


NAND_HEADER = rb'NAND %s: device (\d+) offset 0x([0-9a-fA-F]+), size (0x[0-9a-fA-F]+|\d+)'


def check_nand(kind, response, off, n):
    """Generic path: 'offset 0x.., size 0x..'; vendor path: 'size <decimal> ...'.
    A header, when printed, must name exactly our offset and size."""
    _clean(response)
    headers = re.findall(NAND_HEADER % kind.encode(), response)
    parsed = [(int(d), int(o, 16), int(z, 0)) for d, o, z in headers]
    if parsed and parsed != [(0, off, n)]:
        raise UARTError(f'nand {kind}: printed offset/size differs: {parsed}')
    out = {'printed_header': bool(parsed)}
    if kind == 'erase':
        if not re.search(rb'OK\s*\r?\n', response):
            raise UARTError('nand erase: no OK')
        out['complete_100'] = b'100% complete' in response
        return out
    word = b'written' if kind == 'write' else b'read'
    if not re.search(rb'(?<![0-9])' + str(n).encode() + rb' bytes ' + word + rb': OK', response):
        raise UARTError(f'nand {kind}: no exact "{n} bytes {word.decode()}: OK"')
    return out


def type_and_confirm(c, io, line, log, attempts=3, quiet=0.3):
    """Type `line` WITHOUT CR; return only when the bootloader's echo is exactly
    `line` and nothing else follows within `quiet` seconds. Otherwise discard
    the line with Ctrl-C (it never executes) and retry. The caller sends CR."""
    for attempt in range(attempts):
        start = len(io.received)
        c.write_all(line, timeout=10)
        try:
            echo = c.until(line, timeout=8)
        except UARTError:
            echo = None
        trailing = io.read(64, quiet) if echo == line else b''
        if echo == line and not trailing:
            return attempt
        c.write_all(b'\x03')
        c.until(PROMPT, timeout=8)
        log.append({'command': line.decode('ascii', 'replace'), 'echo_mismatch_discarded': True,
                    'attempt': attempt, 'trailing': trailing.decode('ascii', 'backslashreplace'),
                    'seen': bytes(io.received[start:]).decode('ascii', 'backslashreplace')[-200:]})
    raise UARTError(f'echo never matched; nothing executed: {line!r}')


def verify_tftp_root(root, parts_bytes):
    out = {}
    for name in TFTP_NAMES:
        path = Path(root) / name
        real = path.resolve(strict=True)
        data = real.read_bytes()
        if data != parts_bytes[name]:
            raise ValueError(f'TFTP root {name} -> {real} is not the validated part')
        out[name] = {'served': str(real), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}
    return out


def tftp_service_root():
    r = subprocess.run(['systemctl', 'show', '-p', 'ExecStart', '--value', 'h199a-tftp'],
                       capture_output=True, text=True, timeout=10, check=True)
    m = re.findall(r'--root ([^ ;]+)', r.stdout)
    if len(set(m)) != 1:
        raise ValueError('cannot determine the h199a-tftp served root')
    active = subprocess.run(['systemctl', 'is-active', 'h199a-tftp'], capture_output=True, text=True, timeout=10)
    if active.stdout.strip() != 'active':
        raise ValueError('h199a-tftp is not active')
    return m[0]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--execute', action='store_true', required=True)
    ap.add_argument('--device', required=True)
    ap.add_argument('--raw-log', type=Path, required=True)
    ap.add_argument('--sysupgrade-tar', type=Path, required=True)
    ap.add_argument('--header-template', type=Path, required=True)
    ap.add_argument('--tftp-root', type=Path, required=True)
    ap.add_argument('--expect-tar-sha256', required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--serverip', default='192.168.1.100')
    ap.add_argument('--ipaddr', default='192.168.1.1')
    ap.add_argument('--relay', default='tomada')
    ap.add_argument('--erase-header-only', action='store_true',
                    help='recovery drill: erase only the bank-A header (stock bank B then boots); no TFTP')
    args = ap.parse_args()

    allowed = drill_commands() if args.erase_header_only else allowed_commands()
    tar_bytes = args.sysupgrade_tar.read_bytes()
    if hashlib.sha256(tar_bytes).hexdigest() != args.expect_tar_sha256:
        raise SystemExit('sysupgrade tar sha256 differs from --expect-tar-sha256')
    args.output.mkdir()  # fresh evidence directory, never reused
    vpi = _load('verify_production_image', 'verify-production-image.py')
    parts_dir = args.output / 'parts'
    report = vpi.verify(args.sysupgrade_tar, args.header_template.read_bytes(), extract_dir=parts_dir)
    parts_bytes = {name: (parts_dir / name).read_bytes() for name, *_ in PARTS}
    for name, _, _, n in PARTS:
        if len(parts_bytes[name]) != n:
            raise SystemExit(f'{name}: extracted size {len(parts_bytes[name])} != {n}')
    served_root = tftp_service_root()
    if Path(served_root).resolve() != args.tftp_root.resolve():
        raise SystemExit(f'h199a-tftp serves {served_root}, not {args.tftp_root}')
    served = verify_tftp_root(args.tftp_root, parts_bytes)

    result = {'success': False, 'phase': 'preflight', 'tar_sha256': args.expect_tar_sha256,
              'validator': report, 'served': served, 'plan': [
                  {'name': n, 'partition': p, 'offset': hex(o), 'bytes': s} for n, p, o, s in PARTS],
              'allowed_commands': sorted(allowed), 'destructive_started': False,
              'saveenv': False, 'environment_writes': False, 'boot_commands': False, 'parts': []}
    (args.output / 'install-bank-a-uboot.py').write_bytes(Path(__file__).read_bytes())
    io = c = None
    power_on = None
    ramboot = _load('ramboot', 'ramboot-h199a-tftp.py')

    def checkpoint(phase):
        result['phase'] = phase
        print(phase, flush=True)
        (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
        if io:
            (args.output / 'uart.raw').write_bytes(io.received)

    def relay(action):
        r = subprocess.run([args.relay, action], capture_output=True, timeout=45, check=True)
        (args.output / f'power-{action}.txt').write_bytes(r.stdout + r.stderr)

    def command(text, timeout):
        if c.state != 'console' or text not in allowed:
            raise UARTError(f'command outside the bank-A install set: {text!r}')
        if io.read(1, 0):
            raise UARTError('unexpected buffered console input before command')
        log = result.setdefault('commands', [])
        type_and_confirm(c, io, text.encode('ascii'), log)
        if DESTRUCTIVE.match(text):
            result['destructive_started'] = True
            checkpoint(result['phase'])
        log.append({'command': text, 'echo_exact': True})
        c.write_all(b'\r')
        response = c.until(PROMPT, timeout=timeout, limit=262144)
        index = len(log)
        (args.output / f'command-{index:02d}.raw').write_bytes(response)
        return response

    def tftp(text, n):
        for attempt in range(3):
            start = len(io.received)
            try:
                response = command(text, timeout=240)
            except UARTError:
                # Only a transfer that actually started may be cancelled and retried.
                if b'TFTP from server' not in bytes(io.received[start:]):
                    raise
                c.write_all(b'\x03')
                c.until(PROMPT, timeout=8)
                continue
            sizes = re.findall(rb'Bytes transferred = (\d+)', response)
            if sizes == [str(n).encode()]:
                return check_tftp(response, n)
        raise UARTError(f'TFTP size not established after three attempts: {text}')

    with open('/tmp/h199a-uart-tx.lock', 'a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            checkpoint('power-off')
            relay('off')
            time.sleep(8)
            io = ramboot.LoggedTextTransport(args.device, args.raw_log)
            c = Console(io)
            checkpoint('fresh-boot-entry')
            with (args.output / 'power-on.txt').open('wb') as power_log:
                power_on = subprocess.Popen([args.relay, 'on'], stdout=power_log, stderr=subprocess.STDOUT)
                c.until(b'Press 1 means entering boot mode', timeout=45)
                c.boot_token(b'1')
                c.until(b'input bootmode password', timeout=12)
                c.boot_token(b'Boot4128s!\r')
                c.until(b'Hit any key to stop autoboot', timeout=12)
                c.boot_token(b'\r')
                result['version'] = c.confirm_uboot().decode('ascii', 'backslashreplace')
                if power_on.wait(timeout=20):
                    raise UARTError('relay on did not confirm success')
                power_on = None

            checkpoint('verify-environment')
            env = command('printenv ipaddr serverip verify', timeout=15)
            for name, expected in (('ipaddr', args.ipaddr), ('serverip', args.serverip)):
                found = re.findall(rb'^' + name.encode() + rb'=(.*?)\r?$', env, re.M)
                if found != [expected.encode()]:
                    raise UARTError(f'unexpected {name}: {found}')
            result['verify_env'] = verify_enabled(env)
            if args.erase_header_only:
                name, part, off, n = PARTS[-1]
                result['mode'] = 'erase-header-only'
                checkpoint('header-erase-drill')
                result['header_erase'] = check_nand('erase', command(part_commands(name, off, n)['erase'],
                                                                     timeout=120), off, n)
                result['success'] = True
                checkpoint('header-erased')
                return
            time.sleep(3)  # PHY settle before the first TFTP, as the RAM-boot controller does

            for name, part, off, n in PARTS:
                cmds = part_commands(name, off, n)
                rec = {'name': name, 'partition': part, 'offset': hex(off), 'bytes': n,
                       'sha256': hashlib.sha256(parts_bytes[name]).hexdigest()}
                result['parts'].append(rec)
                checkpoint(f'{part}-tftp-twice')
                tftp(cmds['tftp_load'], n)
                tftp(cmds['tftp_verify'], n)
                check_cmp(command(cmds['cmp'], timeout=120), n)
                rec['tftp_double_copy_equal'] = True
                checkpoint(f'{part}-erase')
                rec['erase'] = check_nand('erase', command(cmds['erase'], timeout=300), off, n)
                checkpoint(f'{part}-write')
                rec['write'] = check_nand('write', command(cmds['write'], timeout=400), off, n)
                checkpoint(f'{part}-readback')
                rec['read'] = check_nand('read', command(cmds['read'], timeout=400), off, n)
                check_cmp(command(cmds['cmp'], timeout=120), n)
                rec['readback_equal'] = True
                checkpoint(f'{part}-done')
            result['success'] = True
            checkpoint('installed')
        except BaseException as error:
            result['error'] = repr(error)
            if power_on is not None:
                try:
                    power_on.wait(timeout=45)
                except subprocess.TimeoutExpired:
                    power_on.kill(); power_on.wait()
            checkpoint('failed')
            raise
        finally:
            # Never let the router autoboot from here: success or failure, power off.
            try:
                relay('off')
                result['left_powered_off'] = True
            except Exception as e:  # recorded; the operator must switch it off
                result['left_powered_off'] = False
                result['power_off_error'] = repr(e)
            if io:
                (args.output / 'uart.raw').write_bytes(io.received)
                io.close()
            (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    main()
