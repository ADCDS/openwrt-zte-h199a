#!/usr/bin/env python3
"""h199a-netinstall — install this OpenWrt port on a stock ZXHN H199A over the LAN.

The installer logs into the stock web UI and uploads a vendor-format container.
The stock flasher validates it and writes the inactive firmware bank. Current
bank-aware kernels boot from either bank. Older A-only kernels require a
verified stock bank-B boot and an explicit --source-bank b assertion.

Safety, stated as the code enforces it:

  * it writes nothing to flash itself — it hands one file to the vendor's own
    web endpoint. The vendor chooses the bank at runtime and also erases the
    backup header. The client checks the appended kernel device tree for
    bank-aware support; it does not detect the running stock bank. For a
    legacy kernel, --source-bank b is an operator assertion. The container carries
    `hdr[+0x8c] = 0`, which is the single field that makes `fw_flashing` skip
    `WriteBoot`;
  * every CRC is checked before a single byte is uploaded;
  * the original bank-window geometry is checked and preserved;
  * the image is refused unless it is byte-for-byte the one the CRCs describe.

Container layout, checked against BOTH `cspd` and `fw_flashing`:

    0x000   four vendor magic words
    0x010   u32 X = 0 (optional prefix length, NOT hdr[+0x08])
    0x014   512-byte unit header
    0x214   kernel container, 0x300000 B
    0x300214 rootfs, 0xd20000 B
    0x1020214 end

The flasher seeks to X+20 and X+0x214; cspd verifies CRCs at the absolute file
offsets in hdr[+0x38] and hdr[+0x44]. The NAND header's +0x08 stays 0x266.

Usage:
    h199a-netinstall.py --dry-run --parts DIR
    h199a-netinstall.py --parts DIR --out webflash.bin
    h199a-netinstall.py --parts DIR [--host 192.168.1.1]

The password is read from the H199A_PASSWORD environment variable or prompted
for; it is never taken from argv (argv is world-readable in /proc) and never
logged, echoed, or written into the image or the session state.

Exit codes: 0 success, 1 refused/failed before upload, 2 usage, 3 upload or
flash failed after the upload started.
"""
import argparse
import getpass
import hashlib
import http.client
import json
import html
import os
import re
import struct
import sys
import time
import xml.etree.ElementTree as ET
import zlib

# --- the contract, from the release header and docs/INSTALL.md -----------------
HEADER_512 = 512
PREAMBLE = 20
FW_MAGIC = struct.pack("<4I", 0x99999999, 0x44444444, 0x55555555, 0xaaaaaaaa)
NAND_MAGIC = struct.pack("<4I", 0x33333333, 0x66666666, 0x99999999, 0xcccccccc)
KERNEL_CONTAINER_LEN = 0x300000
FS_LEN = 0xd20000
KERNEL_CRC_SKIP = 0x20
KERNEL_CRC_LEN = 0x2ffdcc

# header field offsets
H_VERSION = 0x10          # "V9.1.0P3N2_MUL"
H_MODEL = 0x6a            # "ZXHN H199AV91"
H_HDR_OFF = 0x08          # 0x266
H_KSTART = 0x38           # 0x234
H_KLEN = 0x34             # 0x2ffdcc
H_FSSTART = 0x44          # 0x300214
H_FSLEN = 0x40            # 0xd20000
H_KCRC = 0x3c
H_FSCRC = 0x48
H_KTARGET = 0x4c          # 0x700000 = kernel1
H_BOOTFLAG = 0x8c         # must be 0
H_SELFCRC = 0xa4
H_SELFCRC_LEN = 0xa4
H_NAND_MAGIC = 0xf4
H_EXTCRC = 0x1fc
H_WINA_START = 0x1e0      # bank A write window
H_WINA_END = 0x1e4
H_WINB_START = 0x1e8      # bank B write window; selected by stock A
H_WINB_END = 0x1ec

# the only values this board has ever had; anything else is a different device
EXPECT_HDR_OFF = 0x266
EXPECT_KTARGET = 0x700000
EXPECT_KERNEL_CONTAINER_LEN = 0x300000
EXPECT_FS_LEN = 0xd20000
EXPECT_WINA = (0x700000, 0x2000000)
EXPECT_WINB = (0x2000000, 0x3900000)

MODEL_PREFIX = b"ZXHN H199A"

# --- web endpoint --------------------------------------------------------------
# Verified against the stock login page's own g_loginToken():
# login_token is served as XML, the login itself posts to `login_entry` and
# answers JSON. `_tag=login` is NOT the endpoint the UI uses.
LOGIN_PAGE = "/"
LOGIN_TOKEN = "/?_type=loginData&_tag=login_token"
LOGIN_POST = "/?_type=loginData&_tag=login_entry"
UPGRADE_VIEW = "/?_type=menuView&_tag=firmwareUpgr&Menu3Location=0"
UPGRADE_PAGE = "/?_type=menuData&_tag=do_firmware_upgrade.lua"
UPLOAD_ALLOW = "/?_type=menuData&_tag=updownload_prevent_ctl.lua"
UPGRADE_QUERY = "/?_type=menuData&_tag=upgrade_firmware_query_lua.lua"
UPLOAD_FIELD = "VersionUpload"


class Refused(Exception):
    """A precondition failed. Nothing has been uploaded."""


class UploadFailed(Exception):
    """The upload was started and did not complete cleanly."""


def le32(buf, off):
    return struct.unpack_from("<I", buf, off)[0]


def be32(buf, off):
    return struct.unpack_from(">I", buf, off)[0]


def kernel_bank_aware(kernel):
    """Recognize the bank-aware boot contract in a checksum-valid appended DTB."""
    try:
        if len(kernel) != KERNEL_CONTAINER_LEN or kernel[:16] != struct.pack(
                '<4I', 0x33333333, 0xcccccccc, 0x88888888, 0xdddddddd):
            return False
        hdr = bytearray(kernel[32:96])
        stored = be32(hdr, 4)
        struct.pack_into('>I', hdr, 4, 0)
        size = be32(hdr, 12)
        if (be32(hdr, 0) != 0x27051956 or zlib.crc32(hdr) != stored or
                size < 48 or size > len(kernel) - 96 or
                be32(hdr, 16) != 0x40008000 or be32(hdr, 20) != 0x40008000 or
                hdr[28:32] != bytes((5, 2, 2, 0))):
            return False
        payload = kernel[96:96 + size]
        if zlib.crc32(payload) != be32(hdr, 24) or le32(payload, 36) != 0x016f2818:
            return False
        start, stop = le32(payload, 40), le32(payload, 44)
        if stop < start or not 48 <= stop - start <= len(payload):
            return False
        dt = payload[stop - start:]
        if len(dt) < 40 or be32(dt, 0) != 0xd00dfeed or be32(dt, 20) != 17:
            return False
        total, pos, string_offset = be32(dt, 4), be32(dt, 8), be32(dt, 12)
        string_size, structure_size = be32(dt, 32), be32(dt, 36)
        if (total > len(dt) or total < 40 or pos < 40 or pos % 4 or
                pos + structure_size > total or string_offset + string_size > total):
            return False
        end = pos + structure_size
        strings = dt[string_offset:string_offset + string_size]
        stack, board, marker, aware, roots = [], False, False, False, 0
        nodes_seen, props_seen = set(), set()
        while pos + 4 <= end:
            token = be32(dt, pos)
            pos += 4
            if token == 1:
                zero = dt.find(b'\0', pos, end)
                if zero < 0 or len(stack) >= 32:
                    return False
                name = dt[pos:zero].decode('ascii')
                if '/' in name:
                    return False
                if not stack:
                    roots += 1
                    if name or roots != 1:
                        return False
                stack.append(name)
                path = '/' + '/'.join(stack[1:])
                if path in ('/chosen', '/soc/spi@94406000/flash@0'):
                    if path in nodes_seen:
                        return False
                    nodes_seen.add(path)
                pos = (zero + 4) & ~3
            elif token == 2:
                if not stack:
                    return False
                stack.pop()
            elif token == 3:
                if not stack or pos + 8 > end:
                    return False
                length, name_offset = be32(dt, pos), be32(dt, pos + 4)
                pos += 8
                zero = strings.find(b'\0', name_offset)
                if pos + length > end or name_offset >= len(strings) or zero < 0:
                    return False
                name, value = strings[name_offset:zero], dt[pos:pos + length]
                path = '/' + '/'.join(stack[1:])
                if ((path == '/' and name == b'compatible') or
                        (path == '/chosen' and name == b'zte,boot-bank') or
                        (path == '/soc/spi@94406000/flash@0' and name == b'zte,bank-aware')):
                    if (path, name) in props_seen:
                        return False
                    props_seen.add((path, name))
                if path == '/' and name == b'compatible':
                    if not value.endswith(b'\0'):
                        return False
                    board = b'zte,zxhn-h199a' in value.split(b'\0')
                if path == '/chosen' and name == b'zte,boot-bank':
                    marker = value == b'\xff' * 4
                if path == '/soc/spi@94406000/flash@0' and name == b'zte,bank-aware':
                    aware = length == 0
                pos = (pos + length + 3) & ~3
            elif token == 9:
                return not stack and roots == 1 and board and marker and aware
            elif token != 4:
                return False
    except (struct.error, UnicodeDecodeError, ValueError):
        pass
    return False


# --- 1. parts and their invariants ---------------------------------------------
def load_parts(parts_dir):
    """Read kernel/rootfs/header and check the sizes the layout depends on."""
    want = {"kernel": KERNEL_CONTAINER_LEN, "rootfs": FS_LEN, "header": 0x20000}
    parts = {}
    for name, size in want.items():
        path = os.path.join(parts_dir, name)
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError as exc:
            raise Refused("cannot read %s: %s" % (path, exc))
        if len(data) != size:
            raise Refused(
                "%s is %d bytes, expected %d (0x%x). The container layout is "
                "fixed by these sizes; a different part is a different product."
                % (path, len(data), size, size))
        parts[name] = data
    return parts


def check_header(hdr):
    """Validate this board's identity, geometry and checksums."""
    if len(hdr) != 0x20000:
        raise Refused("header must be exactly one 0x20000-byte NAND block")
    ver = hdr[H_VERSION:H_VERSION + 14]
    # The model field carries a two-byte prefix ("\x00\x01") before the string,
    # so strip leading NUL/0x01 padding rather than splitting at the first NUL.
    model = hdr[H_MODEL:H_MODEL + 16].lstrip(b"\x00\x01").split(b"\x00", 1)[0]
    if MODEL_PREFIX not in model:
        raise Refused(
            "header model field is %r, expected it to contain %r — this is "
            "not a ZXHN H199A image" % (model, MODEL_PREFIX))
    if hdr[H_BOOTFLAG] != 0 or hdr[H_BOOTFLAG + 1] != 0:
        raise Refused(
            "header +0x8c is %#x, not 0. That field makes the stock flasher "
            "write the BOOTLOADER. Refusing: this is the one thing that can "
            "brick the unit." % le32(hdr, H_BOOTFLAG))
    hoff = le32(hdr, H_HDR_OFF)
    if hoff != EXPECT_HDR_OFF:
        raise Refused(
            "header +0x08 is %#x, expected %#x. This NAND metadata must be "
            "preserved; the file prefix length is a separate field."
            % (hoff, EXPECT_HDR_OFF))
    if le32(hdr, H_KTARGET) != EXPECT_KTARGET:
        raise Refused(
            "header +0x4c (kernel target) is %#x, expected %#x (kernel1). "
            "Refusing a noncanonical vendor kernel-target field."
            % (le32(hdr, H_KTARGET), EXPECT_KTARGET))
    if le32(hdr, H_FSLEN) != EXPECT_FS_LEN:
        raise Refused(
            "header +0x40 (fs length) is %#x, expected %#x"
            % (le32(hdr, H_FSLEN), EXPECT_FS_LEN))
    if le32(hdr, H_KLEN) != KERNEL_CRC_LEN:
        raise Refused(
            "header +0x34 (kernel CRC length) is %#x, expected %#x"
            % (le32(hdr, H_KLEN), KERNEL_CRC_LEN))
    for off, expected in ((H_KSTART, 0x234), (H_FSSTART, 0x300214),
                          (0x90, 0), (0x104, 0)):
        if le32(hdr, off) != expected:
            raise Refused("header +%#x is %#x, expected %#x for this layout"
                          % (off, le32(hdr, off), expected))
    if hdr[H_NAND_MAGIC:H_NAND_MAGIC + 16] != NAND_MAGIC:
        raise Refused("header has no recognised NAND extension magic")
    # NAND geometry / bank windows: the flasher picks a window from these, and
    # the choice is made on the board at runtime. A header whose bank-A window
    # is not kernel1..bankB-start is not this device's header.
    wina = (le32(hdr, H_WINA_START), le32(hdr, H_WINA_END))
    winb = (le32(hdr, H_WINB_START), le32(hdr, H_WINB_END))
    if wina != EXPECT_WINA:
        raise Refused(
            "header bank-A write window is %#x..%#x, expected %#x..%#x — the "
            "stock flasher would erase the wrong region"
            % (wina + EXPECT_WINA))
    if winb != EXPECT_WINB:
        raise Refused(
            "header bank-B window is %#x..%#x, expected %#x..%#x"
            % (winb + EXPECT_WINB))
    selfcrc = le32(hdr, H_SELFCRC)
    calc = zlib.crc32(hdr[:H_SELFCRC_LEN]) & 0xffffffff
    if calc != selfcrc:
        raise Refused(
            "header self-CRC is %#010x but recomputes to %#010x — the header "
            "does not describe itself" % (selfcrc, calc))
    if zlib.crc32(hdr[:H_EXTCRC]) & 0xffffffff != le32(hdr, H_EXTCRC):
        raise Refused("header extended CRC at +0x1fc does not match its bytes")
    return {"version": ver, "model": model, "hdr_off": hoff}


# --- 2. container assembly -----------------------------------------------------
def layout(hdr):
    """File offsets of the header, kernel container and rootfs.

    cspd uses absolute offsets for payload CRCs. The prefix length X is zero;
    the unrelated NAND header field +0x08 is not a file offset.
    """
    hdr_off = PREAMBLE
    k_off = le32(hdr, H_KSTART) - KERNEL_CRC_SKIP
    fs_off = le32(hdr, H_FSSTART)
    end = fs_off + le32(hdr, H_FSLEN)
    return hdr_off, k_off, fs_off, end


def assemble(parts):
    """Build the vendor container and verify every CRC from the container.

    The CRCs are recomputed over the *container* bytes at the offsets the header
    declares — the same ranges the bootloader and fw_flashing read — rather than
    trusting the header or the parts.
    """
    kernel, rootfs, hdr = parts["kernel"], parts["rootfs"], parts["header"]
    if len(kernel) != KERNEL_CONTAINER_LEN or len(rootfs) != FS_LEN:
        raise Refused("kernel/rootfs sizes do not match the fixed firmware-bank layout")
    info = check_header(hdr)

    hdr_off, k_off, fs_off, end = layout(hdr)
    if hdr_off + HEADER_512 > k_off:
        raise Refused(
            "layout is inconsistent: header [%#x,%#x) would overlap the body at "
            "%#x" % (hdr_off, hdr_off + HEADER_512, k_off))
    if k_off + KERNEL_CONTAINER_LEN != fs_off:
        raise Refused(
            "layout is inconsistent: kernel container at %#x + %#x = %#x but the "
            "header puts the rootfs at %#x"
            % (k_off, KERNEL_CONTAINER_LEN, k_off + KERNEL_CONTAINER_LEN, fs_off))

    img = bytearray(end)
    img[hdr_off:hdr_off + HEADER_512] = hdr[:HEADER_512]
    img[k_off:k_off + len(kernel)] = kernel
    img[fs_off:fs_off + len(rootfs)] = rootfs

    # cspd verifies these words before it reads the header. X is zero, so
    # fw_flashing's seeks agree with cspd's absolute CRC offsets.
    img[:16] = FW_MAGIC
    struct.pack_into("<I", img, 0x10, 0)

    # Recompute the three CRCs from the assembled container.
    kcrc = zlib.crc32(bytes(img[k_off + KERNEL_CRC_SKIP:
                                  k_off + KERNEL_CRC_SKIP + KERNEL_CRC_LEN])) & 0xffffffff
    fcrc = zlib.crc32(bytes(img[fs_off:fs_off + FS_LEN])) & 0xffffffff
    selfcrc = zlib.crc32(bytes(img[hdr_off:hdr_off + H_SELFCRC_LEN])) & 0xffffffff

    bad = []
    if kcrc != le32(hdr, H_KCRC):
        bad.append("kernel CRC: container %#010x, header +0x3c %#010x"
                   % (kcrc, le32(hdr, H_KCRC)))
    if fcrc != le32(hdr, H_FSCRC):
        bad.append("rootfs CRC: container %#010x, header +0x48 %#010x"
                   % (fcrc, le32(hdr, H_FSCRC)))
    if selfcrc != le32(hdr, H_SELFCRC):
        bad.append("header self-CRC: recomputed %#010x, stored %#010x"
                   % (selfcrc, le32(hdr, H_SELFCRC)))
    if bad:
        raise Refused("the assembled container does not match its header:\n  "
                      + "\n  ".join(bad))

    info.update({
        "hdr_off": hdr_off, "k_off": k_off, "fs_off": fs_off, "end": end,
        "kcrc": kcrc, "fcrc": fcrc, "selfcrc": selfcrc,
        "sha256": hashlib.sha256(bytes(img)).hexdigest(),
        "bank_aware": kernel_bank_aware(kernel),
    })
    return bytes(img), info


def report(img, info):
    print("  header   @ %#07x  %s  %s"
          % (info["hdr_off"], info["version"].decode("latin1"), info["model"].decode("latin1")))
    print("  kernel   @ %#07x  %d bytes   CRC32 %#010x" % (info["k_off"], KERNEL_CONTAINER_LEN, info["kcrc"]))
    print("  rootfs   @ %#07x  %d bytes   CRC32 %#010x" % (info["fs_off"], FS_LEN, info["fcrc"]))
    print("  header self-CRC %#010x   bootloader flag +0x8c = 0" % info["selfcrc"])
    print("  container %d bytes, sha256 %s" % (len(img), info["sha256"]))
    print("  kernel bank support: %s" % ("A and B" if info['bank_aware'] else
                                         "A only (verified stock-B source required)"))


# --- 3. the stock web UI -------------------------------------------------------
class StockWeb:
    """Minimal client for the stock httpd: token login, then multipart upload."""

    def __init__(self, host, port=80, host_header=None, timeout=20, verbose=False):
        self.host = host
        self.port = port
        self.host_header = host_header or host
        self.timeout = timeout
        self.verbose = verbose
        self.sid = None
        self.session_token = None
        self.upload_token = None

    def _conn(self, timeout=None):
        return http.client.HTTPConnection(
            self.host, self.port, timeout=timeout or self.timeout)

    def _headers(self, extra=None):
        h = {"Host": self.host_header, "Accept": "application/json, text/plain, */*",
             "Referer": "http://%s/" % self.host_header,
             "X-Requested-With": "XMLHttpRequest"}
        h["Cookie"] = "_TESTCOOKIESUPPORT=1"
        if self.sid:
            h["Cookie"] += "; SID=%s" % self.sid
        if extra:
            h.update(extra)
        return h

    def _note(self, msg):
        if self.verbose:
            print("    .. %s" % msg)

    def login(self, user, password):
        """Token login. The password is never printed, logged or stored.

        The stock UI's own flow is: GET the login page (which sets SID and
        _TESTCOOKIESUPPORT), GET login_token (XML, a number), then POST
        login_entry with Password = sha256(password + token), Username,
        _sessionTOKEN and action=login, answering JSON.
        """
        # 1. The login page, for the session cookies the rest of the flow uses.
        conn = self._conn()
        try:
            conn.request("GET", LOGIN_PAGE, headers=self._headers())
            resp = conn.getresponse()
            resp.read()
            self.sid = _cookie_value(resp.getheader("Set-Cookie") or "", "SID")
        except OSError as exc:
            raise Refused("cannot reach the stock web UI at %s:%d: %s"
                          % (self.host, self.port, exc))
        finally:
            conn.close()

        # The browser initializes sess_token through login_entry BEFORE it
        # requests login_token. The hidden input in the initial HTML is empty.
        conn = self._conn()
        try:
            conn.request("GET", LOGIN_POST, headers=self._headers())
            resp = conn.getresponse()
            body = resp.read()
            self.sid = _cookie_value(resp.getheader("Set-Cookie") or "", "SID") or self.sid
            self.session_token = _json_field(body, "sess_token")
            if resp.status != 200 or not self.session_token:
                raise Refused("login_entry did not initialize a session token")
        except OSError as exc:
            raise Refused("login session initialization failed: %s" % exc)
        finally:
            conn.close()

        conn = self._conn()
        try:
            conn.request("GET", LOGIN_TOKEN, headers=self._headers())
            resp = conn.getresponse()
            body = resp.read()
        except OSError as exc:
            raise Refused("cannot reach the stock web UI at %s:%d: %s"
                          % (self.host, self.port, exc))
        finally:
            conn.close()
        if resp.status != 200:
            raise Refused("login_token returned HTTP %d" % resp.status)
        token = _find_token(body)
        if not token:
            raise Refused(
                "login_token returned no token (first bytes: %r). The stock UI "
                "did not answer as expected — is this really the stock firmware "
                "on 192.168.1.1?" % body[:120])
        self._note("got a login token (%d chars)" % len(token))

        digest = hashlib.sha256((password + token).encode()).hexdigest()
        form = ("Username=%s&Password=%s&_sessionTOKEN=%s&action=login"
                % (_q(user), digest, _q(self.session_token or ""))).encode()
        conn = self._conn()
        try:
            conn.request("POST", LOGIN_POST, body=form, headers=self._headers(
                {"Content-Type": "application/x-www-form-urlencoded",
                 "Content-Length": str(len(form))}))
            resp = conn.getresponse()
            body = resp.read()
            setcookie = resp.getheader("Set-Cookie") or ""
        except OSError as exc:
            raise Refused("login POST failed: %s" % exc)
        finally:
            conn.close()
        self.sid = _cookie_value(setcookie, "SID") or self.sid
        err = _json_field(body, "loginErrMsg")
        sess = _json_field(body, "sess_token")
        if err:
            # A non-empty loginErrMsg means the unit refused the login. It is
            # reported verbatim: on this unit the message is "page expired"
            # even for a CORRECT password, which means the refusal happens
            # before the credential is evaluated.
            raise Refused(
                "the stock UI refused the login: %r (HTTP %d). This is the "
                "unit's own message; if it mentions an expired page the stock "
                "web session layer is not working and no password will help."
                % (err, resp.status))
        if resp.status != 200 or not self.sid or not _json_field(body, "login_need_refresh"):
            raise Refused(
                "login returned no SID cookie (HTTP %d, body %r)."
                % (resp.status, body[:160]))
        self.session_token = sess
        self._note("logged in, SID cookie received")

    def check_session(self):
        """Prove the session is live before the upload, not after."""
        conn = self._conn()
        try:
            conn.request("GET", UPGRADE_VIEW, headers=self._headers())
            resp = conn.getresponse()
            body = resp.read()
        except OSError as exc:
            raise Refused("session check failed: %s" % exc)
        finally:
            conn.close()
        # An unauthenticated stock httpd answers with the login view.
        if resp.status != 200 or b"SessionTimeout" in body or b"loginView" in body or b"login_token" in body:
            raise Refused("the session is not logged in — the upgrade page came "
                          "back as the login view")
        # TOKEN_UPLOAD is generated by the real upgrade view, separately from
        # the login token. Do not accept an HTTP 200 login/error page.
        fields = re.findall(rb'<input\b[^>]*>', body, re.I)
        for field in fields:
            if re.search(rb'\bid=[\"\']TOKEN_UPLOAD[\"\']', field):
                value = re.search(rb'\bvalue=[\"\']([^\"\']+)[\"\']', field)
                if value:
                    self.upload_token = html.unescape(value.group(1).decode())
        if not self.upload_token:
            raise Refused("the authenticated upgrade view returned no TOKEN_UPLOAD")
        # Each view refreshes the generic AJAX token. Mirror the page's
        # final script assignment rather than keeping the login-page token.
        tokens = re.findall(rb'_sessionTmpToken\s*=\s*[\"\']([^\"\']+)[\"\']', body)
        if tokens:
            raw = tokens[-1].decode('ascii')
            self.session_token = re.sub(r'\\x([0-9a-fA-F]{2})',
                                        lambda m: chr(int(m.group(1), 16)), raw)
        else:
            self.session_token = self.upload_token
        self._note("session is logged in (upgrade token received)")

    def allow_upload(self):
        if not self.upload_token:
            raise Refused("upgrade session has not been checked")
        form = ("&sessToken=" + _q(self.upload_token)
                + "&_sessionTOKEN=" + _q(self.session_token or "")).encode()
        conn = self._conn()
        try:
            conn.request("POST", UPLOAD_ALLOW, body=form, headers=self._headers(
                {"Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                 "Check": hashlib.sha256(form).hexdigest()}))
            resp = conn.getresponse()
            body = resp.read()
            if resp.status != 200 or _xml_error(body) != "0":
                raise Refused("stock refused the upload preflight")
        except OSError as exc:
            raise Refused("upload preflight failed: %s" % exc)
        finally:
            conn.close()

    def upload(self, image, timeout=600):
        """Multipart POST of the container as `VersionUpload`."""
        self.allow_upload()
        boundary = "----h199a" + hashlib.sha256(os.urandom(16)).hexdigest()[:24]
        head = (
            "--%s\r\n"
            "Content-Disposition: form-data; name=\"%s\"; filename=\"firmware.bin\"\r\n"
            "Content-Type: application/octet-stream\r\n\r\n"
            % (boundary, UPLOAD_FIELD)).encode()
        tail = ("\r\n--%s--\r\n" % boundary).encode()
        length = len(head) + len(image) + len(tail)

        conn = self._conn(timeout=timeout)
        try:
            conn.putrequest("POST", UPGRADE_PAGE + "&_sessionTOKEN=" + _q(self.upload_token),
                            skip_host=True)
            for k, v in self._headers({"Content-Type":
                                       "multipart/form-data; boundary=%s" % boundary,
                                       "Content-Length": str(length)}).items():
                conn.putheader(k, v)
            conn.endheaders()
            conn.send(head)
            # Stream in chunks so a 16 MiB body does not need a second copy.
            view = memoryview(image)
            for off in range(0, len(image), 1 << 16):
                conn.send(view[off:off + (1 << 16)])
            conn.send(tail)
            resp = conn.getresponse()
            body = resp.read()
        except OSError as exc:
            raise UploadFailed(
                "the upload was interrupted: %s. The unit may be mid-flash. Do "
                "NOT power it off; wait for it to finish or reboot, then check "
                "which bank it boots." % exc)
        finally:
            conn.close()
        return resp.status, body

    def wait_for_upgrade(self, timeout=120):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            conn = self._conn()
            try:
                conn.request("GET", UPGRADE_QUERY, headers=self._headers())
                resp = conn.getresponse()
                body = resp.read()
            except (OSError, http.client.HTTPException):
                # A completed flash can reboot before this poll receives its
                # response. Continue to the read-only LuCI verification; a
                # disconnect itself never counts as installation success.
                return False
            finally:
                conn.close()
            if resp.status != 200 or _xml_error(body) != "0":
                raise UploadFailed("stock returned an invalid upgrade status")
            try:
                root = ET.fromstring(body)
                params = dict(zip((n.text for n in root.iter("ParaName")),
                                  (n.text for n in root.iter("ParaValue"))))
            except ET.ParseError:
                raise UploadFailed("stock returned malformed upgrade status")
            if params.get("needRefresh") == "false":
                description = params.get("upgrDesc", "") or ""
                if any(word in description.casefold() for word in ("upgrade failed", "atualização falhou")):
                    raise UploadFailed("stock rejected the firmware: %s" % description)
                if params.get("willReboot") == "true":
                    return True
                raise UploadFailed("stock rejected the firmware: %s" % params.get("upgrDesc", "unknown error"))
            if params.get("needRefresh") != "true":
                raise UploadFailed("stock returned no recognizable upgrade state")
            time.sleep(2)
        raise UploadFailed("stock did not confirm flashing before the status timeout")

    def wait_for_openwrt(self, timeout=240):
        """Stock's reboot booleans can also describe failure; require LuCI."""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            conn = self._conn(timeout=3)
            try:
                conn.request("GET", "/cgi-bin/luci/", headers={"Host": self.host_header})
                resp = conn.getresponse()
                body = resp.read().lower()
                is_luci = resp.status == 200 or (
                    resp.status == 403 and resp.getheader("x-luci-login-required") == "yes")
                if is_luci and b"openwrt" in body and b"luci" in body:
                    return
            except (OSError, http.client.HTTPException):
                pass  # A reboot is expected, so retry only this read-only probe.
            finally:
                conn.close()
            time.sleep(2)
        raise UploadFailed("OpenWrt LuCI did not appear after upload; installation is unconfirmed")


def _q(s):
    from urllib.parse import quote
    return quote(s, safe="")


def _xml_error(body):
    try:
        return ET.fromstring(body).findtext("IF_ERRORID")
    except ET.ParseError:
        return None


def _find_token(body):
    """The token is served as XML: <ajax_response_xml_root>NNNNNNNN</...>."""
    import re
    m = re.search(rb"<ajax_response_xml_root>\s*([^<\s]+)\s*</ajax_response_xml_root>",
                  body)
    if m:
        return m.group(1).decode("latin1")
    try:
        obj = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return None
    for key in ("logintoken", "token", "loginToken"):
        if isinstance(obj, dict) and isinstance(obj.get(key), str):
            return obj[key]
    # Some builds nest it one level down.
    if isinstance(obj, dict):
        for v in obj.values():
            if isinstance(v, dict):
                for key in ("logintoken", "token"):
                    if isinstance(v.get(key), str):
                        return v[key]
    return None


def _json_field(body, key):
    try:
        obj = json.loads(body.decode("utf-8", "replace"))
    except ValueError:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return None


def _cookie_value(setcookie, name):
    value = None
    for part in setcookie.split(","):
        for chunk in part.split(";"):
            chunk = chunk.strip()
            if chunk.startswith(name + "="):
                # Stock emits the old and promoted SID in the same login
                # response. Browsers apply Set-Cookie fields in wire order.
                value = chunk[len(name) + 1:]
    return value


# --- 4. main -------------------------------------------------------------------
def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Install this OpenWrt port on a stock ZXHN H199A over the LAN.")
    ap.add_argument("--parts", default="parts",
                    help="directory holding kernel, rootfs and header (default: parts)")
    ap.add_argument("--host", default="192.168.1.1", help="stock LAN address")
    ap.add_argument("--port", type=int, default=80)
    ap.add_argument("--user", default="multipro", help="stock admin username")
    ap.add_argument("--dry-run", action="store_true",
                    help="assemble and verify the container, do not upload")
    ap.add_argument("--out", help="write the verified container here and exit without network access")
    ap.add_argument("--source-bank", choices=("a", "b"),
                    help="operator assertion; legacy A-only kernels require verified stock bank B")
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args(argv)

    print("h199a-netinstall")
    try:
        parts = load_parts(args.parts)
        img, info = assemble(parts)
    except Refused as exc:
        print("REFUSED: %s" % exc, file=sys.stderr)
        return 1

    print("container verified:")
    report(img, info)

    if args.out:
        try:
            with open(args.out, "wb") as fh:
                fh.write(img)
        except OSError as exc:
            print("REFUSED: cannot write %s: %s" % (args.out, exc), file=sys.stderr)
            return 1
        print("  written to %s" % args.out)

    if args.dry_run or args.out:
        print("dry run: nothing was uploaded.")
        return 0

    if args.source_bank != "b" and not info['bank_aware']:
        print("REFUSED: upload requires --source-bank b after verifying the CURRENT "
              "stock boot is bank B. A stock bank-A boot would overwrite bank B "
              "and this image would not boot. See docs/INSTALL-NO-UART.md.", file=sys.stderr)
        return 1

    password = os.environ.get("H199A_PASSWORD")
    if password is None:
        if not sys.stdin.isatty():
            print("REFUSED: no password. Set H199A_PASSWORD or run on a terminal.",
                  file=sys.stderr)
            return 1
        password = getpass.getpass("stock admin password for %s: " % args.user)

    web = StockWeb(args.host, args.port, timeout=20, verbose=args.verbose)
    try:
        web.login(args.user, password)
        web.check_session()
    except Refused as exc:
        print("REFUSED: %s" % exc, file=sys.stderr)
        print("Nothing was uploaded; the unit is unchanged.", file=sys.stderr)
        return 1
    finally:
        password = None

    print("uploading %d bytes to %s ..." % (len(img), args.host))
    try:
        status, body = web.upload(img)
    except Refused as exc:
        print("REFUSED: %s" % exc, file=sys.stderr)
        return 1
    except UploadFailed as exc:
        print("FAILED AFTER UPLOAD STARTED: %s" % exc, file=sys.stderr)
        return 3
    if status != 200 or _json_field(body, "IF_ERRORID") != 0:
        print("UPLOAD REJECTED: HTTP %d, body %r" % (status, body[:300]), file=sys.stderr)
        print("The unit should still boot stock. Check the stock UI for an error "
              "and re-run.", file=sys.stderr)
        return 3
    print("upload received; waiting for the stock firmware's validation result ...")
    try:
        confirmed = web.wait_for_upgrade()
        if not confirmed:
            print("Stock status connection closed; checking whether OpenWrt booted.")
        print("Waiting for OpenWrt LuCI after reboot. Do NOT power off.")
        web.wait_for_openwrt()
    except UploadFailed as exc:
        print("UPGRADE UNCONFIRMED: %s. Do NOT power off during flashing." % exc, file=sys.stderr)
        return 3
    print("OpenWrt LuCI is reachable at http://%s:%d/cgi-bin/luci/." % (args.host, args.port))
    return 0


if __name__ == "__main__":
    sys.exit(main())
