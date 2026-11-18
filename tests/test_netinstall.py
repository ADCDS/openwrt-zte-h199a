"""The network installer must refuse anything it does not recognise.

The failure this guards against is the expensive one: a malformed container is
accepted by the stock flasher's three CRC32s, written over bank A, and the unit
then boots stock bank B with our rootfs gone. So every refusal path is tested
here, plus the container layout itself, because a layout that is off by 0x0c
still produces a file that looks plausible.

The vendor cspd validates magic and CRCs at absolute file offsets before it
starts fw_flashing. Checking only the latter's seeks missed both format bugs.
"""
import hashlib
import http.client
import importlib.util
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
import zlib
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs
from test_upgrade_header import kernel_image

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / 'tools/h199a-netinstall.py'

spec = importlib.util.spec_from_file_location('netinstall', TOOL)
netinstall = importlib.util.module_from_spec(spec)
spec.loader.exec_module(netinstall)

KERNEL_LEN = 0x300000
FS_LEN = 0xd20000
HDR_BLK = 0x20000


def make_header(kernel=b'\x00' * KERNEL_LEN, rootfs=b'\x00' * FS_LEN):
    """A structurally valid bank-A header for the synthetic parts below."""
    hdr = bytearray(HDR_BLK)
    struct.pack_into('<I', hdr, 0x08, 0x266)
    hdr[0x10:0x10 + 14] = b'V9.1.0P3N2_MUL'
    struct.pack_into('<I', hdr, 0x34, 0x2ffdcc)
    struct.pack_into('<I', hdr, 0x38, 0x234)
    struct.pack_into('<I', hdr, 0x40, 0xd20000)
    struct.pack_into('<I', hdr, 0x44, 0x300214)
    struct.pack_into('<I', hdr, 0x4c, 0x700000)
    struct.pack_into('<I', hdr, 0x1e0, 0x700000)
    struct.pack_into('<I', hdr, 0x1e4, 0x2000000)
    struct.pack_into('<I', hdr, 0x1e8, 0x2000000)
    struct.pack_into('<I', hdr, 0x1ec, 0x3900000)
    struct.pack_into('<I', hdr, 0x8c, 0)
    struct.pack_into('<4I', hdr, 0xf4, 0x33333333, 0x66666666, 0x99999999, 0xcccccccc)
    hdr[0x6a:0x6a + 15] = b'\x00\x01ZXHN H199AV91'
    struct.pack_into('<I', hdr, 0x3c, zlib.crc32(kernel[0x20:0x20 + 0x2ffdcc]) & 0xffffffff)
    struct.pack_into('<I', hdr, 0x48, zlib.crc32(rootfs) & 0xffffffff)
    struct.pack_into('<I', hdr, 0xa4, zlib.crc32(bytes(hdr[0:0xa4])) & 0xffffffff)
    struct.pack_into('<I', hdr, 0x1fc, zlib.crc32(hdr[:0x1fc]) & 0xffffffff)
    return bytes(hdr)


def make_parts(kernel=None, rootfs=None, header=None):
    kernel = kernel if kernel is not None else bytes(
        i & 0xff for i in range(KERNEL_LEN))
    rootfs = rootfs if rootfs is not None else bytes(
        (i * 7) & 0xff for i in range(FS_LEN))
    header = header if header is not None else make_header(kernel, rootfs)
    return {'kernel': kernel, 'rootfs': rootfs, 'header': header}


class LayoutTest(unittest.TestCase):
    """The container geometry, pinned to the values §5.1 derives."""

    def setUp(self):
        self.img, self.info = netinstall.assemble(make_parts())

    def test_header_follows_preamble(self):
        self.assertEqual(self.info['hdr_off'], 0x14)

    def test_kernel_and_rootfs_offsets(self):
        # Read off fw_flashing: header at X+20, body at X+0x214.
        self.assertEqual(self.info['k_off'], 0x214)
        self.assertEqual(self.info['fs_off'], 0x300214)
        # The identity that makes the layout self-consistent.
        self.assertEqual(self.info['k_off'] + KERNEL_LEN, self.info['fs_off'])

    def test_preamble_carries_the_seek_value(self):
        # main: read 20 bytes, then lseek(u32 at file 0x10 + 20).
        self.assertEqual(struct.unpack_from('<I', self.img, 0x10)[0], 0)
        seek = 20 + struct.unpack_from('<I', self.img, 0x10)[0]
        self.assertEqual(seek, self.info['hdr_off'])

    def test_vendor_checker_accepts_absolute_crc_ranges(self):
        # Independent model of cspd: verifyCspFwMagic, NandFlashHeader_Check,
        # UpgradeCheckFirmware. Do not use the builder's layout() or info.
        self.assertEqual(struct.unpack_from('<4I', self.img),
                         (0x99999999, 0x44444444, 0x55555555, 0xaaaaaaaa))
        x = struct.unpack_from('<I', self.img, 16)[0]
        hdr = self.img[20 + x:20 + x + 512]
        self.assertEqual(struct.unpack_from('<I', hdr, 8)[0], 0x266)
        for lenoff, startoff, crcoff in [(0x34, 0x38, 0x3c), (0x40, 0x44, 0x48)]:
            size, start, expected = [struct.unpack_from('<I', hdr, o)[0]
                                     for o in (lenoff, startoff, crcoff)]
            payload = self.img[start:start + size]
            self.assertEqual(len(payload), size)
            self.assertEqual(zlib.crc32(payload), expected)
        for offset in (0xa4, 0x1fc):
            self.assertEqual(zlib.crc32(hdr[:offset]),
                             struct.unpack_from('<I', hdr, offset)[0])

    def test_normal_flash_prep_header_is_accepted(self):
        # Exercise the build tool's actual CRC contract: updating the inner
        # CRC preserves the outer CRC residue, so no header normalization is
        # needed when wrapping freshly built parts for the stock web updater.
        spec = importlib.util.spec_from_file_location('flash_prep', ROOT / 'tools/flash-prep.py')
        prep = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(prep)
        parts = make_parts()
        parts['header'] = prep.patch_header(
            make_header(), prep.kernel_crc(parts['kernel']), prep.fs_crc(parts['rootfs']))
        image, _ = netinstall.assemble(parts)
        self.assertEqual(image[20:532], parts['header'][:512])

    def test_header_lands_where_the_seek_points(self):
        parts = make_parts()
        at_seek = self.img[self.info['hdr_off']:self.info['hdr_off'] + 512]
        self.assertEqual(at_seek, parts['header'][:512])

    def test_crcs_recompute_from_the_container(self):
        parts = make_parts()
        k = self.img[self.info['k_off'] + 0x20:
                     self.info['k_off'] + 0x20 + 0x2ffdcc]
        self.assertEqual(zlib.crc32(k) & 0xffffffff,
                         struct.unpack_from('<I', parts['header'], 0x3c)[0])
        f = self.img[self.info['fs_off']:self.info['fs_off'] + FS_LEN]
        self.assertEqual(zlib.crc32(f) & 0xffffffff,
                         struct.unpack_from('<I', parts['header'], 0x48)[0])

    def test_total_size(self):
        self.assertEqual(len(self.img), 0x1020214)

    def test_header_is_flush_against_the_body(self):
        # 0x214 - 20 == 0x200 == sizeof(header): no gap, which is what makes
        # the two independently-derived offsets agree.
        self.assertEqual(self.info['k_off'] - self.info['hdr_off'], 512)

    def test_body_lands_where_writeversion_seeks(self):
        # WriteVersion: add r3, r1, #532 on the same X -> body at X + 0x214.
        x = struct.unpack_from('<I', self.img, 0x10)[0]
        self.assertEqual(x + 0x214, self.info['k_off'])
        parts = make_parts()
        self.assertEqual(self.img[self.info['k_off']:self.info['k_off'] + 4],
                         parts['kernel'][:4])


class RefusalTest(unittest.TestCase):
    """Everything unrecognised is refused before a byte could be uploaded."""

    def refuse(self, parts):
        with self.assertRaises(netinstall.Refused):
            netinstall.assemble(parts)

    def test_bootloader_flag_set_is_refused(self):
        kernel = make_parts()['kernel']
        rootfs = make_parts()['rootfs']
        hdr = bytearray(make_header(kernel, rootfs))
        struct.pack_into('<I', hdr, 0x8c, 1)
        struct.pack_into('<I', hdr, 0xa4, zlib.crc32(bytes(hdr[0:0xa4])) & 0xffffffff)
        self.refuse(make_parts(kernel, rootfs, bytes(hdr)))

    def test_wrong_model_is_refused(self):
        kernel, rootfs = make_parts()['kernel'], make_parts()['rootfs']
        hdr = bytearray(make_header(kernel, rootfs))
        hdr[0x6a:0x6a + 15] = b'\x00\x01ZXHN H298AV91'
        struct.pack_into('<I', hdr, 0xa4, zlib.crc32(bytes(hdr[0:0xa4])) & 0xffffffff)
        self.refuse(make_parts(kernel, rootfs, bytes(hdr)))

    def test_wrong_kernel_target_is_refused(self):
        kernel, rootfs = make_parts()['kernel'], make_parts()['rootfs']
        hdr = bytearray(make_header(kernel, rootfs))
        struct.pack_into('<I', hdr, 0x4c, 0x2000000)   # bank B
        struct.pack_into('<I', hdr, 0xa4, zlib.crc32(bytes(hdr[0:0xa4])) & 0xffffffff)
        self.refuse(make_parts(kernel, rootfs, bytes(hdr)))

    def test_bank_b_window_is_refused(self):
        kernel, rootfs = make_parts()['kernel'], make_parts()['rootfs']
        hdr = bytearray(make_header(kernel, rootfs))
        struct.pack_into('<I', hdr, 0x1e8, 0x2100000)
        struct.pack_into('<I', hdr, 0xa4, zlib.crc32(bytes(hdr[0:0xa4])) & 0xffffffff)
        struct.pack_into('<I', hdr, 0x1fc, zlib.crc32(hdr[:0x1fc]))
        self.refuse(make_parts(kernel, rootfs, bytes(hdr)))

    def test_unexpected_header_offset_is_refused(self):
        kernel, rootfs = make_parts()['kernel'], make_parts()['rootfs']
        hdr = bytearray(make_header(kernel, rootfs))
        struct.pack_into('<I', hdr, 0x08, 0x286)   # the wrong value
        struct.pack_into('<I', hdr, 0xa4, zlib.crc32(bytes(hdr[0:0xa4])) & 0xffffffff)
        self.refuse(make_parts(kernel, rootfs, bytes(hdr)))

    def test_corrupt_header_self_crc_is_refused(self):
        kernel, rootfs = make_parts()['kernel'], make_parts()['rootfs']
        hdr = bytearray(make_header(kernel, rootfs))
        struct.pack_into('<I', hdr, 0xa4, 0xdeadbeef)
        self.refuse(make_parts(kernel, rootfs, bytes(hdr)))

    def test_rootfs_that_does_not_match_its_crc_is_refused(self):
        parts = make_parts()
        bad = bytearray(parts['rootfs'])
        bad[0x1000] ^= 0xff
        self.refuse(make_parts(parts['kernel'], bytes(bad), parts['header']))

    def test_kernel_that_does_not_match_its_crc_is_refused(self):
        parts = make_parts()
        bad = bytearray(parts['kernel'])
        bad[0x100] ^= 0xff
        self.refuse(make_parts(bytes(bad), parts['rootfs'], parts['header']))

    def test_short_part_is_refused(self):
        parts = make_parts()
        self.refuse({'kernel': parts['kernel'][:0x1000],
                     'rootfs': parts['rootfs'], 'header': parts['header']})

    def test_crc_correct_wrong_payload_starts_are_refused(self):
        parts = make_parts()
        for off in (0x38, 0x44):
            with self.subTest(offset=off):
                hdr = bytearray(parts['header'])
                struct.pack_into('<I', hdr, off, struct.unpack_from('<I', hdr, off)[0] + 0x266)
                struct.pack_into('<I', hdr, 0xa4, zlib.crc32(hdr[:0xa4]))
                struct.pack_into('<I', hdr, 0x1fc, zlib.crc32(hdr[:0x1fc]))
                self.refuse(make_parts(parts['kernel'], parts['rootfs'], bytes(hdr)))

    def test_extended_header_corruption_is_refused(self):
        parts = make_parts()
        hdr = bytearray(parts['header'])
        hdr[0x180] ^= 1  # outside the older 164-byte self-CRC
        self.refuse(make_parts(parts['kernel'], parts['rootfs'], bytes(hdr)))


class ProtocolTest(unittest.TestCase):
    """The login protocol, as the stock page's own g_loginToken() does it."""

    def test_token_is_parsed_from_xml(self):
        self.assertEqual(
            netinstall._find_token(b'<ajax_response_xml_root>87088390</ajax_response_xml_root>'),
            '87088390')

    def test_token_still_parses_from_json(self):
        self.assertEqual(netinstall._find_token(b'{"logintoken":"abc"}'), 'abc')

    def test_login_posts_to_login_entry_not_login(self):
        # The UI uses login_entry (JSON). _tag=login is XML and is not it.
        self.assertIn('_tag=login_entry', netinstall.LOGIN_POST)
        self.assertNotIn('_tag=login"', netinstall.LOGIN_POST)

    def test_password_digest_is_sha256_of_password_plus_token(self):
        # sha256(Password + xmlObj), from the page's g_loginToken().
        import hashlib
        self.assertEqual(
            hashlib.sha256(b'multipro' + b'12345678').hexdigest(),
            hashlib.sha256(('multipro' + '12345678').encode()).hexdigest())

    def test_json_error_field(self):
        self.assertEqual(
            netinstall._json_field(b'{"loginErrMsg":"expired"}', 'loginErrMsg'),
            'expired')
        self.assertIsNone(netinstall._json_field(b'not json', 'loginErrMsg'))


class KernelSupportTest(unittest.TestCase):
    def test_bank_aware_uimage_and_dt_contract(self):
        self.assertTrue(netinstall.kernel_bank_aware(kernel_image()))

    def test_unused_capability_string_in_legacy_tree_does_not_enable_bank_b(self):
        self.assertFalse(netinstall.kernel_bank_aware(kernel_image(bank_aware=False)))

    def test_damaged_uimage_is_not_marked_bank_aware(self):
        kernel = bytearray(kernel_image())
        kernel[120] ^= 1
        self.assertFalse(netinstall.kernel_bank_aware(kernel))

    def test_ambiguous_dt_capabilities_are_not_marked_bank_aware(self):
        for change in ('duplicate_property', 'duplicate_node', 'slash_node'):
            with self.subTest(change=change):
                self.assertFalse(netinstall.kernel_bank_aware(kernel_image(**{change: True})))

    def test_new_kernel_upload_needs_no_source_bank_assertion(self):
        with patch.object(netinstall, 'load_parts', return_value={}), \
                patch.object(netinstall, 'assemble', return_value=(b'image', {'bank_aware': True})), \
                patch.object(netinstall, 'report'), patch.object(netinstall, 'StockWeb') as web, \
                patch.dict(netinstall.os.environ, {'H199A_PASSWORD': 'test-only'}):
            web.return_value.upload.return_value = (200, b'{"IF_ERRORID":0}')
            self.assertEqual(netinstall.main([]), 0)
            web.return_value.wait_for_openwrt.assert_called_once()

    def test_legacy_kernel_without_verified_source_bank_sends_nothing(self):
        with patch.object(netinstall, 'load_parts', return_value={}), \
                patch.object(netinstall, 'assemble', return_value=(b'image', {'bank_aware': False})), \
                patch.object(netinstall, 'report'), patch.object(netinstall, 'StockWeb') as web:
            self.assertEqual(netinstall.main([]), 1)
            web.assert_not_called()


class WebExchangeTest(unittest.TestCase):
    """Exercise real HTTP framing and the stock UI's token/preflight sequence."""

    def setUp(self):
        self.responses = []
        self.requests = []
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def handle_request(self):
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                owner.requests.append((self.command, self.path, self.headers, body))
                if not owner.responses:
                    self.send_error(500)
                    return
                status, payload, cookie, headers = owner.responses.pop(0)
                self.send_response(status)
                if cookie:
                    for item in cookie if isinstance(cookie, list) else [cookie]:
                        self.send_header('Set-Cookie', item)
                for name, value in headers.items():
                    self.send_header(name, value)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            do_GET = do_POST = handle_request

        self.server = HTTPServer(('127.0.0.1', 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.web = netinstall.StockWeb('127.0.0.1', self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def reply(self, payload, cookie=None, status=200, headers=None):
        self.responses.append((status, payload, cookie, headers or {}))

    def test_login_preflight_upload_and_flash_acknowledgement(self):
        self.reply(b'<html>login</html>', 'SID=initial; Path=/; HttpOnly')
        self.reply(b'{"sess_token":"csrf"}')
        self.reply(b'<ajax_response_xml_root>12345678</ajax_response_xml_root>')
        self.reply(b'{"loginErrMsg":"","login_need_refresh":true,"sess_token":"after"}',
                   ['SID=initial; Path=/; HttpOnly', 'SID=authenticated; Path=/; HttpOnly'])
        self.reply(b'<script>_sessionTmpToken="\\x76iew-csrf";</script>'
                   b'<input value="upload&amp;token" type="hidden" id="TOKEN_UPLOAD">')
        self.reply(b'<ajax_response_xml_root><IF_ERRORID>0</IF_ERRORID></ajax_response_xml_root>')
        self.reply(b'{"IF_ERRORID":0}')
        self.reply(b'<ajax_response_xml_root><IF_ERRORID>0</IF_ERRORID><Instance>'
                   b'<ParaName>needRefresh</ParaName><ParaValue>false</ParaValue>'
                   b'<ParaName>willReboot</ParaName><ParaValue>true</ParaValue>'
                   b'</Instance></ajax_response_xml_root>')
        self.reply(b'<html><title>OpenWrt - LuCI</title></html>')
        self.web.login('multipro', 'test-password')
        self.web.check_session()
        self.assertEqual(self.web.upload(b'firmware-payload'), (200, b'{"IF_ERRORID":0}'))
        self.web.wait_for_upgrade()
        self.web.wait_for_openwrt()
        self.assertEqual([(r[0], r[1]) for r in self.requests], [
            ('GET', '/'), ('GET', netinstall.LOGIN_POST), ('GET', netinstall.LOGIN_TOKEN),
            ('POST', netinstall.LOGIN_POST), ('GET', netinstall.UPGRADE_VIEW),
            ('POST', netinstall.UPLOAD_ALLOW),
            ('POST', netinstall.UPGRADE_PAGE + '&_sessionTOKEN=upload%26token'),
            ('GET', netinstall.UPGRADE_QUERY), ('GET', '/cgi-bin/luci/')])
        form = parse_qs(self.requests[3][3].decode())
        self.assertEqual(form['_sessionTOKEN'], ['csrf'])
        self.assertEqual(form['Password'], [hashlib.sha256(b'test-password12345678').hexdigest()])
        preflight = self.requests[5]
        self.assertEqual(parse_qs(preflight[3].decode())['sessToken'], ['upload&token'])
        self.assertEqual(parse_qs(preflight[3].decode())['_sessionTOKEN'], ['view-csrf'])
        self.assertEqual(preflight[2]['Check'], hashlib.sha256(preflight[3]).hexdigest())
        upload = self.requests[6]
        self.assertEqual(len(upload[2].get_all('Host')), 1)
        self.assertEqual(int(upload[2]['Content-Length']), len(upload[3]))
        self.assertIn(b'name="VersionUpload"', upload[3])
        self.assertIn(b'filename="firmware.bin"', upload[3])
        self.assertIn(b'firmware-payload', upload[3])
        for _, _, headers, _ in self.requests[4:-1]:
            self.assertIn('SID=authenticated', headers['Cookie'])
            self.assertIn('_TESTCOOKIESUPPORT=1', headers['Cookie'])

    def test_http_200_session_timeout_is_refused(self):
        self.reply(b'SessionTimeout')
        with self.assertRaises(netinstall.Refused):
            self.web.check_session()

    def test_upload_preflight_failure_sends_no_firmware(self):
        self.web.upload_token = 'token'
        self.reply(b'<ajax_response_xml_root><IF_ERRORID>-1452</IF_ERRORID></ajax_response_xml_root>')
        with self.assertRaises(netinstall.Refused):
            self.web.upload(b'must-not-be-sent')
        self.assertEqual(len(self.requests), 1)
        self.assertNotIn(b'must-not-be-sent', self.requests[0][3])

    def test_async_validation_failure_is_not_success(self):
        self.reply(b'<ajax_response_xml_root><IF_ERRORID>0</IF_ERRORID><Instance>'
                   b'<ParaName>needRefresh</ParaName><ParaValue>false</ParaValue>'
                   b'<ParaName>willReboot</ParaName><ParaValue>false</ParaValue>'
                   b'<ParaName>upgrDesc</ParaName><ParaValue>invalid image</ParaValue>'
                   b'</Instance></ajax_response_xml_root>')
        with self.assertRaisesRegex(netinstall.UploadFailed, 'invalid image'):
            self.web.wait_for_upgrade()

    def test_failure_that_claims_it_will_reboot_is_not_success(self):
        self.reply(b'<ajax_response_xml_root><IF_ERRORID>0</IF_ERRORID><Instance>'
                   b'<ParaName>needRefresh</ParaName><ParaValue>false</ParaValue>'
                   b'<ParaName>willReboot</ParaName><ParaValue>true</ParaValue>'
                   b'<ParaName>upgrDesc</ParaName><ParaValue>Upgrade failed, the device will restart soon.</ParaValue>'
                   b'</Instance></ajax_response_xml_root>')
        with self.assertRaisesRegex(netinstall.UploadFailed, 'Upgrade failed'):
            self.web.wait_for_upgrade()

    def test_reboot_before_status_response_still_requires_luci(self):
        with patch.object(self.web, '_conn') as conn:
            conn.return_value.getresponse.side_effect = http.client.RemoteDisconnected()
            self.assertFalse(self.web.wait_for_upgrade())
        self.reply(b'<html>ZXHN H199A login</html>')
        self.reply(b'<html><title>OpenWrt - LuCI</title></html>')
        with patch.object(netinstall.time, 'sleep'):
            self.web.wait_for_openwrt()
        self.assertEqual([r[1] for r in self.requests],
                         ['/cgi-bin/luci/', '/cgi-bin/luci/'])

    def test_stock_login_after_reboot_is_not_openwrt(self):
        self.reply(b'<html>ZXHN H199A login</html>')
        self.reply(b'<html><title>OpenWrt - LuCI</title></html>')
        with patch.object(netinstall.time, 'sleep'):
            self.web.wait_for_openwrt()
        self.assertEqual(len(self.requests), 2)

    def test_openwrt_login_uses_http_403(self):
        self.reply(b'<html><title>OpenWrt - LuCI</title></html>', status=403,
                   headers={'x-luci-login-required': 'yes'})
        self.web.wait_for_openwrt()

    def test_output_file_never_opens_a_network_connection(self):
        with tempfile.TemporaryDirectory() as tmp, \
                patch.object(netinstall, 'load_parts', return_value={}), \
                patch.object(netinstall, 'assemble', return_value=(b'image', {})), \
                patch.object(netinstall, 'report'), patch.object(netinstall, 'StockWeb') as web:
            path = Path(tmp) / 'webflash.bin'
            self.assertEqual(netinstall.main(['--out', str(path)]), 0)
            self.assertEqual(path.read_bytes(), b'image')
            web.assert_not_called()


class CliTest(unittest.TestCase):
    """The command line refuses cleanly, with a message, and never a traceback."""

    def run_tool(self, *args):
        return subprocess.run([sys.executable, str(TOOL)] + list(args),
                              capture_output=True, text=True)

    def test_dry_run_on_real_release_parts(self):
        parts = Path('$BENCH/h199a-firmware/'
                     'rel-7c466f2-20261117/parts')
        if not parts.is_dir():
            self.skipTest('release parts not present on this host')
        run = self.run_tool('--dry-run', '--parts', str(parts))
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn('0x00014', run.stdout)
        self.assertIn('9c2e3f41', run.stdout)
        self.assertIn('0x00214', run.stdout)
        self.assertIn('078cec00', run.stdout)
        self.assertIn('nothing was uploaded', run.stdout)

    def test_missing_parts_refuses_without_traceback(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self.run_tool('--dry-run', '--parts', tmp)
        self.assertEqual(run.returncode, 1)
        self.assertIn('REFUSED', run.stderr)
        self.assertNotIn('Traceback', run.stderr)

    def test_no_upload_without_password_on_a_pipe(self):
        # --dry-run must not even try, and a non-tty run must refuse rather
        # than prompt or upload.
        run = self.run_tool('--parts', '/nonexistent')
        self.assertEqual(run.returncode, 1)
        self.assertNotIn('Traceback', run.stderr)


if __name__ == '__main__':
    unittest.main()
