"""install-bank-a-uboot.py: the closed command set and every response gate.

No hardware: the static plan, the allowed-command set and the response
validators are exercised with outputs in both bootloader print formats (the
generic cmd_nand path and the vendor cspboot path, read from the unit's own
bootloader strings), and every failure shape that must abort.
"""
import importlib.util
from pathlib import Path
import re
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('install_bank_a', ROOT / 'tools' / 'install-bank-a-uboot.py')
ib = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ib)
from h199a_uart_fd import UARTError  # noqa: E402

PROTECTED = [  # (name, start, end) regions that must never appear in a command
    ('bootloader..defcfg', 0x0, 0x700000),
    ('gap', 0x1740000, 0x2000000),
    ('bank B', 0x2000000, 0x3040000),
    ('legacy/staging/UBI/suffix', 0x3040000, 0x8000000),
]


class Plan(unittest.TestCase):
    def test_plan_is_bank_a_only_header_last(self):
        self.assertTrue(ib.check_plan())
        self.assertEqual([p[0] for p in ib.PARTS], ['rootfs', 'kernel', 'header'])
        self.assertEqual([(p[2], p[3]) for p in ib.PARTS],
                         [(0xa00000, 0xd20000), (0x700000, 0x300000), (0x1720000, 0x20000)])

    def test_plan_rejects_escapes(self):
        bad = [
            (('rootfs', 'r', 0x1720000, 0x40000), ('header', 'h', 0x1720000, 0x20000)),  # past bank A
            (('kernel', 'k', 0x2000000, 0x300000), ('header', 'h', 0x1720000, 0x20000)),  # bank B
            (('kernel', 'k', 0x700000, 0x300000), ('rootfs', 'r', 0xa00000, 0xd20000)),  # header not last
            (('kernel', 'k', 0x700800, 0x300000), ('header', 'h', 0x1720000, 0x20000)),  # unaligned
            (('kernel', 'k', 0x700000, 0x400000), ('rootfs', 'r', 0xa00000, 0x20000),
             ('header', 'h', 0x1720000, 0x20000)),  # overlap
            (('evil', 'e', 0x700000, 0x20000), ('header', 'h', 0x1720000, 0x20000)),  # unservable name
        ]
        for plan in bad:
            with self.assertRaises(ValueError, msg=plan):
                ib.check_plan(plan)

    def test_allowed_set_is_closed(self):
        allowed = ib.allowed_commands()
        self.assertEqual(len(allowed), 1 + 3 * 6)
        for text in allowed:
            self.assertNotRegex(text, r'saveenv|setenv|reset|boot|go |mw|nand scrub|nand markbad|erase\.chip|;')
            nums = [int(x, 16) for x in re.findall(r'0x([0-9a-f]+)', text)]
            if text.startswith('nand '):
                off = nums[1] if text.startswith(('nand write', 'nand read')) else nums[0]
                size = nums[-1]
                self.assertTrue(ib.BANK_A[0] <= off and off + size <= ib.BANK_A[1], text)
                for name, s, e in PROTECTED:
                    self.assertFalse(off < e and s < off + size, (text, name))
        erases = sorted(t for t in allowed if t.startswith('nand erase'))
        self.assertEqual(erases, ['nand erase 0x1720000 0x20000', 'nand erase 0x700000 0x300000',
                                  'nand erase 0xa00000 0xd20000'])


class Drill(unittest.TestCase):
    def test_drill_erases_only_the_bank_a_header(self):
        d = ib.drill_commands()
        self.assertEqual(d, {'printenv ipaddr serverip verify', 'nand erase 0x1720000 0x20000'})
        self.assertTrue(d < ib.allowed_commands())
        self.assertFalse(any(t.startswith(('nand write', 'tftp')) for t in d))


GEN_ERASE = (b'\r\nNAND erase: device 0 offset 0xa00000, size 0xd20000\r\n'
             b'\rErasing at 0x1700000 -- 100% complete.\r\nOK\r\n=> ')
VND_ERASE = b'\r\nNAND erase: device 0 offset 0xa00000, size 0xd20000 \r\nOK\r\n=> '
GEN_WRITE = (b'\r\nNAND write: device 0 offset 0xa00000, size 0xd20000\r\n'
             b' 13762560 bytes written: OK\r\n=> ')
VND_WRITE = (b'\r\nNAND write: device 0 offset 0xa00000, size 13762560 ... \r\n'
             b' 13762560 bytes written: OK\r\n=> ')
VND_READ = (b'\r\nNAND read: device 0 offset 0xa00000, size 13762560 ... \r\n'
            b' 13762560 bytes read: OK\r\n=> ')
N, OFF = 0xd20000, 0xa00000


class Responses(unittest.TestCase):
    def test_both_print_paths_accepted(self):
        self.assertTrue(ib.check_nand('erase', GEN_ERASE, OFF, N)['complete_100'])
        self.assertTrue(ib.check_nand('erase', VND_ERASE, OFF, N)['printed_header'])
        self.assertTrue(ib.check_nand('write', GEN_WRITE, OFF, N)['printed_header'])
        self.assertTrue(ib.check_nand('write', VND_WRITE, OFF, N)['printed_header'])
        self.assertTrue(ib.check_nand('read', VND_READ, OFF, N)['printed_header'])
        # A path that prints no header still needs the exact OK line.
        self.assertFalse(ib.check_nand('write', b'\r\n 13762560 bytes written: OK\r\n', OFF, N)['printed_header'])

    def test_failures_abort(self):
        cases = [
            ('erase', GEN_ERASE.replace(b'\rErasing', b'\r\nSkipping bad block at  0x00b00000\r\n\rErasing')),
            ('erase', VND_ERASE.replace(b'OK', b'nand_erase 1 erase block[58] error! mark bad\r\nOK')),
            ('erase', VND_ERASE.replace(b'0xa00000', b'0x000000')),            # wrong printed offset
            ('erase', VND_ERASE.replace(b'size 0xd20000', b'size 0xd00000')),  # wrong printed size
            ('erase', VND_ERASE.replace(b'OK', b'ERROR')),
            ('write', VND_WRITE.replace(b'written: OK', b'written: ERROR')),
            ('write', VND_WRITE.replace(b' 13762560 bytes', b' 13631488 bytes')),  # short
            ('write', VND_WRITE.replace(b' \r\n 1376', b' \r\nwrite skip_and_mark bad block[5a]\r\n 1376')),
            ('write', VND_WRITE.replace(b' \r\n 1376', b' \r\nalready write mtdpart_end = 0x1700000! offs = 0x1700000\r\n 1376')),
            ('read', VND_READ.replace(b' \r\n 1376', b' \r\nskip bad block[5a]\r\n 1376')),
            ('read', VND_READ.replace(b' \r\n 1376', b' \r\nread fail block[5a]\r\n 1376')),
            ('read', VND_READ.replace(b' \r\n 1376', b' \r\nSkip bad: fs start:a00000 skip:1\r\n 1376')),
            ('read', VND_READ.replace(b'size 13762560', b'size 13762561')),
            ('write', b'Usage:\r\nnand - NAND sub-system\r\n=> '),
        ]
        for kind, text in cases:
            with self.assertRaises(UARTError, msg=(kind, text)):
                ib.check_nand(kind, text, OFF, N)

    def test_tftp_exact(self):
        good = b'TFTP from server 192.168.1.100; our IP address is 192.168.1.1\r\nLoading: ####\r\ndone\r\nBytes transferred = 13762560 (d20000 hex)\r\n=> '
        self.assertTrue(ib.check_tftp(good, N))
        for bad in (good.replace(b'13762560 (d20000', b'13762559 (d1ffff'),
                    good + good, b'TFTP error: \'File not found\' (1)\r\n=> '):
            with self.assertRaises(UARTError):
                ib.check_tftp(bad, N)

    def test_cmp_exact(self):
        self.assertTrue(ib.check_cmp(b'Total of 13762560 byte(s) were the same\r\n=> ', N))
        for bad in (b'byte at 0x42001000 (0xd7) != byte at 0x44001000 (0xf7)\r\nTotal of 4096 byte(s) were the same\r\n',
                    b'Total of 13762559 byte(s) were the same\r\n', b'\r\n=> '):
            with self.assertRaises(UARTError):
                ib.check_cmp(bad, N)


class TftpRoot(unittest.TestCase):
    def test_served_files_must_equal_validated_parts(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            parts = {'kernel': b'k' * 8, 'rootfs': b'r' * 8, 'header': b'h' * 8}
            for name, data in parts.items():
                (d / f'{name}.bin').write_bytes(data)
                (d / name).symlink_to(d / f'{name}.bin')
            self.assertEqual(set(ib.verify_tftp_root(d, parts)), set(parts))
            (d / 'rootfs.bin').write_bytes(b'R' * 8)
            with self.assertRaises(ValueError):
                ib.verify_tftp_root(d, parts)



class FakeRouter:
    """Bootloader line editor: echoes what it RECEIVES (optionally corrupted),
    executes on CR, discards on Ctrl-C."""
    def __init__(self, corrupt_first=0, trailing_first=0):
        self.corrupt_first, self.trailing_first = corrupt_first, trailing_first
        self.out = bytearray(); self.received = bytearray(); self.line = bytearray()
        self.executed = []; self.discarded = []; self.lines_typed = 0

    # transport side used by type_and_confirm(io=...)
    def read(self, size, timeout):
        data = bytes(self.out[:size]); del self.out[:size]; self.received.extend(data); return data

    def type(self, data):
        for b in data:
            if b == 0x03:
                self.discarded.append(bytes(self.line)); self.line.clear(); self.out += b'<INTERRUPT>\r\n=> '
            elif b == 0x0d:
                self.executed.append(bytes(self.line)); self.line.clear(); self.out += b'\r\n=> '
            else:
                self.line.append(b); self.out.append(b)
        if data and data[-1] not in (3, 13):
            self.lines_typed += 1
            if self.lines_typed <= self.corrupt_first:   # a digit flips on the router's RX
                i = self.line.find(b'0xa')
                self.line[i + 2:i + 3] = b'0'
                self.out[-len(self.line):] = self.line
            elif self.lines_typed <= self.corrupt_first + self.trailing_first:
                self.line += b'0'; self.out += b'0'       # an inserted trailing char


class FakeConsole:
    def __init__(self, router):
        self.r = router

    def write_all(self, data, timeout=3):
        self.r.type(data)

    def until(self, marker, timeout=10, limit=65536):
        buf = bytes(self.r.out)
        m = marker.search(buf) if hasattr(marker, 'search') else None
        i = buf.find(marker) if isinstance(marker, bytes) else -1
        stop = m.end() if m else (i + len(marker) if i >= 0 else None)
        if stop is None:
            self.r.out.clear(); raise UARTError('marker absent')
        del self.r.out[:stop]; return buf[:stop]


class EchoGuard(unittest.TestCase):
    LINE = b'nand erase 0xa00000 0xd20000'

    def run_guard(self, router):
        c, log = FakeConsole(router), []
        attempt = ib.type_and_confirm(c, router, self.LINE, log, quiet=0)
        c.write_all(b'\r')
        return attempt, log

    def test_clean_echo_executes_once(self):
        r = FakeRouter()
        self.assertEqual(self.run_guard(r)[0], 0)
        self.assertEqual(r.executed, [self.LINE]); self.assertEqual(r.discarded, [])

    def test_corrupted_line_is_discarded_never_executed(self):
        r = FakeRouter(corrupt_first=2)
        attempt, log = self.run_guard(r)
        self.assertEqual(attempt, 2)
        self.assertEqual(r.executed, [self.LINE])           # only the verified line ran
        self.assertEqual(len(r.discarded), 2)
        self.assertTrue(all(d != self.LINE for d in r.discarded))
        self.assertTrue(all(e['echo_mismatch_discarded'] for e in log))

    def test_trailing_garbage_is_discarded(self):
        r = FakeRouter(trailing_first=1)
        attempt, _ = self.run_guard(r)
        self.assertEqual(attempt, 1); self.assertEqual(r.executed, [self.LINE])

    def test_persistent_corruption_executes_nothing(self):
        r = FakeRouter(corrupt_first=3)
        with self.assertRaises(UARTError):
            ib.type_and_confirm(FakeConsole(r), r, self.LINE, [], quiet=0)
        self.assertEqual(r.executed, []); self.assertEqual(len(r.discarded), 3)


if __name__ == '__main__':
    unittest.main()
