> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# Stock web-firmware upgrade path — does it exist, and what does it require?

**Historical static analysis, corrected after hardware testing on 2026-11-17.**
Use [INSTALL-NO-UART.md](../INSTALL-NO-UART.md) for the current procedure and bank-aware
requirements. The original format and unconditional bank-A conclusions below
were superseded by full-chain validation and hardware tests.

Question: the stock ZXHN H199A web server (`bin/httpd` + Lua web modules). Is there
a firmware-upgrade path we can drive from the LAN with no UART, and what does it
require?

---

## 0. TL;DR (filled in as findings land)

| question | answer |
|---|---|
| upgrade endpoint | `VersionUpload` multipart POST -> `do_firmware_upgrade.lua` -> `file_upload_logic` -> `cmapi.callUploadDownloadProc` -> httpd `my_upload_file` -> `bin/fw_flashing`. **Not unauthenticated.** §2 |
| auth requirement | Requires a logged-in web session. `needAuth` defaults to `ALL`; URL routing returns `loginView` whenever `getLoginStatus() != 'loginAlready'`; the endpoint is not in the `data` whitelist. §5 |
| image format / validation | CSP magic + zero prefix length, header at `0x14`, body at `0x214`; payload CRCs use absolute offsets, with inner and extended header CRCs. See INSTALL-NO-UART.md. |
| what it writes | The inactive bank and runtime backup header. Bootloader writes require `hdr[+0x8c] != 0` (ours is `0`); never `tag`/`wifi`. |
| usable by a normal user, no UART? | Yes, with the current bank-aware kernel from either stock bank. Legacy A-only kernels still require a verified stock-B boot. See INSTALL-NO-UART.md. |
| best untested lead | **DHCP option 43 -> TR-069 ACS URL**, unauthenticated, reaches the same flasher. §7 |

---

## 1. How the web server is structured

- `bin/httpd` — C server. Strings reference `rsaDecryptWithKeyFile` (uses
  `/etc/enwebdhardcodefile`, the RSA private key) and `cmapi querylist`.
- `home/httpd/webmodules/modules/*.lua` — **Lua 5.1 bytecode** (`\x1bLuaQ`), 304
  files. Not plaintext.
- `home/httpd/webmodules/modules/*_t.lp`, `*_js.lp` — page templates / JS.
- `etc/webserver/serverpkcs12.pfx` — TLS material.
- Config DB: `cmapi` object store; `do_*` modules drive it.

### Tooling note

Stock Lua is bytecode; there is no plaintext source on the device. A small
parser/disassembler lives at `tools/luadump/lua51dump.py` (pure Python, PUC
Lua 5.1 format, prints constants + pseudo-disassembly). Use it to read any
`webmodules/**/*.lua`.

---

## 2. The upgrade endpoint

`home/httpd/webmodules/modules/do_firmware_upgrade.lua` is 388 bytes of
bytecode and does exactly one thing:

```lua
local up = require('modules.file_upload_logic')
return { VersionUpload = up.UploadFile('VersionUpload') }
```

`file_upload_logic.lua` is the shared upload path for *every* upload endpoint
(firmware, defcfg, usercfg, certs). Its `UploadFile(kind)` returns a handler that:

1. sets a `text/html` content header,
2. calls **`cmapi.callUploadDownloadProc(REQUEST.SERVER_FD, REQUEST.EXEC_OUT,
   handler, request, <upload kind>)`**,
3. on `IF_ERRORID != 0`, logs `uploading file(...) failed!` and returns the
   error as JSON.

So the Lua layer is a **thin wrapper**: the entire upload implementation —
where the file lands, whether it is validated, and whether the caller must be
logged in — is in the C side, in `cmapi.callUploadDownloadProc` and whatever
`httpd` does before dispatching. That is where the real question is answered.

(TBD: exact URL, auth, format, target.)

### Confirmed: `my_upload_file` is the generic multipart uploader

`my_upload_file` (httpd, `0x3b988`, 0xc84 bytes) is the single C-side handler for
every upload type. Recovered control flow (literal pool dereferenced; all strings
are real strings from the binary):

1. `get_line_from_post` reads the multipart header lines; strips CRLF.
2. Finds `name="` and extracts the form field name; finds the first `.` in it and
   truncates there (so `VersionUpload.xxx` -> `VersionUpload`).
3. `strcasecmp(field, filetype)` — the type must match the registered endpoint,
   else HTTP **404** (`str [r4,#12] = 0x194`).
4. `GetUploadFileEntryItem(field)` / `GetDownloadFileEntryItem(field)` look up a
   **registered upload-file table entry**. If absent -> error.
5. If the entry's byte `[+4] == 0` the handler treats it as a *push upgrade*:
   logs `Send push upgrade msg.`, builds a small struct and calls
   `CmUpgradeStart(callback = webProcUpgradeResult)` — **before** any file data is
   written.
6. Otherwise `prepare_firmware_upgrade` path: checks free space
   (`GetUpgradeFreeMemSize`), `malloc(2048)` a copy buffer, then
   `fopen(<dest>, "wb")` where **`<dest>` comes from the registry entry**
   (`SafeStrncpy(..., entry[+16], 51)` into the struct at `[r4,#16]`), parses
   `Content-Type: `, and streams the body with `recv`/`fwrite` until the
   multipart terminator.

So: the destination path and the allowed space are **not** attacker-controlled
by the request — they come from the registered table. The uploaded bytes go to a
staging file; `CmUpgradeStart` (in `libcmapi.so`) is what validates and flashes.

Note the `SELF()` syscall (`bl SELF@plt`, 0x3bd40) immediately before
`CmUpgradeStart` — that is a flash-lock / secure-mode probe, not authentication.

**Important:** nothing in this function checks a login session. Auth, if any,
must happen in `httpd`'s request dispatcher *before* `my_upload_file` is called.

## 3. The flash writer: `bin/fw_flashing`

The uploaded file is handed to **`bin/fw_flashing`** (58 KB, not stripped). This is
the component that validates and writes. Recovered CLI (`getopt "d:r:p:f:m:v:"`):

| flag | meaning (from usage/log sites) |
|---|---|
| `-d <path>` | firmware image file |
| `-r <addr>` | upgrade start address in flash |
| `-p <size>` | image size |
| `-f <flag>` | force-erase / bootloader-update flag |
| `-m <mode>` | mode; non-zero selects the *result-report* path |
| `-v <n>` | version |
| `switch` | positional arg: switch active bank (`CspSwitchVersion`) then `reboot()` |

Writes to **`/dev/mtd0`** via `ioctl(MEMGETINFO=0x80204d01)` for block size, then
`CspUserMtdErase`/`CspUserMtdWrite` (bad-block aware). It reports results back to
`cspd.cspd.upgrade_mgr` via `ASEND` (msgs 0x260e/0x260f/0x2612).

### Image layout as fw_flashing expects it

`main` does, in order:

1. `open(image)`, `stat()`; refuses if size is 0 ("download firmware too small").
2. **`read(fd, buf, 20)`** — must return exactly 20 or it prints "read  magic
   failed!". So the file starts with a **20-byte preamble**.
3. **`lseek(fd, [buf+0x20] + 20, SEEK_SET)`** — it seeks to an offset taken from
   the preamble plus 20, then reads **512 bytes** into a header buffer.
4. Calls `WriteVersion(mtd0_fd, image_fd, filesize)`.

So the header is **not** at file offset 0: it sits at `20 + <u32 at preamble+0x20>`.
That matches our own `docs/INSTALL.md` §3 layout, where the vendor header is
reached through an offset field rather than being the first bytes of the file.

### Validation actually performed (this is the good news)

| check | function | what it really does |
|---|---|---|
| header read | `main` | `read()==512` only |
| `Checkheader` | `0x9aa0` | reads 512 B **back from flash** at the target and `memcmp`s it against the in-memory header — a *write verification*, not a signature check |
| `CheckFile` | `0x9928` | streams image vs. flash and `memcmp`s — again a read-back verify of what was just written |
| bootloader CRC | `WriteBoot` | `Read bootloader magic failed` / `Boot bad magic numbers` / `Boot header CRC error (0x%08x)` / `Boot Content CRC error (0x%08x)` |
| version header | `SetVersionHeader` | `version header crc failed`, `version integrality failed` |

**There is no RSA/ECDSA signature check and no vendor-key verification anywhere
in `fw_flashing`.** Validation is: structural (magic/CRC) plus read-back compare.
The only CRCs are the standard ones already documented for our bootloader
contract, and `fw_flashing` computes CRC32 with a table built from polynomial
`0x04c11db7` at startup (visible in `main`).

### The bootloader is only touched conditionally — and we control the flag

In `WriteVersion` (`0xa584`):

```
ldrh r3, [hdr + 0x8c]     ; 16-bit field in the 512-byte header
cmp  r3, #0
beq  <skip>               ; field == 0  -> "NO need upgrade boot!!!"
bl   WriteBoot            ; field != 0  -> writes bootloader
```

So **`hdr[0x8c:0x8e] == 0` means the bootloader is never written.** That is a
hard safety property we can assert on our own image, and it is the single most
important field in the header for "is this safe to hand to users".

(TBD: confirm what bank/partition the write targets, and the auth gate.)

## 4. Image format — fully reconciled with our own contract

Verified against the real bank-A header block
(`logs/stock-harvest-baseline-nand/bankA-header-block.bin`, 131072 bytes, taken
from the unit). Every field `fw_flashing` uses reproduces exactly:

| header offset | value on the unit | meaning |
|---|---|---|
| `+0x08` | `0x266` | **offset used by `fw_flashing`'s seek** |
| `+0x10` | `"V9.1.0P3N2_MUL"` | version string |
| `+0x34` | `0x2ffdcc` | kernel length (the value in our kernel-CRC contract) |
| `+0x38` | `0x234` | kernel start offset inside the image |
| `+0x3c` | `0xf34ffb20` | **kernel CRC32** |
| `+0x40` | `0xd20000` | filesystem length (the value in our fs-CRC contract) |
| `+0x44` | `0x300214` | filesystem start offset inside the image (`0x214` = `0x234-0x20`) |
| `+0x48` | `0x35d58d58` | **filesystem CRC32** |
| `+0x4c` | `0x700000` | kernel target flash offset (= `kernel1`) |
| `+0x50` | `0x1900000` | end / total |
| `+0x58`/`+0x5c` | `0x1000000`, `0x2000000` | bank B region markers |
| `+0x6a` | `"ZXHN H199AV91"` | vendor/model string |
| `+0x8c` | **`0x0000`** | **bootloader-update flag — 0 = do not touch boot** |
| `+0xa0` | `0x1` | (integrity/version-header present) |
| `+0xa4` | `0x513c6d71` | **header self-CRC32 over `hdr[0:0xa4]`** — recomputed `0x513c6d71`, MATCH |
| `+0xb4` | `"20210706145901"` | build timestamp |

So the vendor image is:

```
[ 20-byte preamble ][ ... ][ 512-byte header at 0x20 + hdr[+0x08] ][ image body ]
```

with `20 + 0x266 = 0x286`. `fw_flashing` reads 20 bytes, then `lseek(20 +
preamble[0x20])` and reads 512 bytes. For our image that means the header must be
reachable at `file[0x286 : 0x286+0x200]`, and the CRC'd regions are the
**in-image** streams at `hdr[+0x38]` and `hdr[+0x44]` — i.e. the same
`kernel[0x20:0x20+0x2ffdcc]` / `rootfs[0:0xd20000]` convention already documented
in `docs/INSTALL.md` §3 and implemented by `tools/h199a-header-regen.c`.

**Consequence: we can build the image ourselves.** The CRCs are plain
`zlib.crc32`, the offsets are explicit header fields, and there is no signature.
An OpenWrt payload wrapped in this container with correct CRCs, `hdr[+0x8c] = 0`,
and `hdr[+0xa0]`/version fields set is exactly what the vendor flasher accepts.

## 5. Authentication — there is a real session framework, and it is on by default

The previous investigator's note that login validates against `cmapi` /
`OBJ_USERINFO_ID` is consistent with what follows. The important new finding is
**where the gate sits and what it defaults to**.

### 5.1 `httpd` (the C layer) has no authentication of its own

- `funcs_callUploadDownloadProc` (httpd `0x3eb9c`) goes from Lua arguments
  straight into `my_upload_file` — no session or password check.
- `do_lua_script` (`0x42b08`) → `my_execute_lua` — no auth check.
- The C server is a **thttpd** derivative (`httpd_got_request`,
  `httpd_parse_request`, `really_start_request`, `handle_newconnect` are
  thttpd's own names). thttpd's `_parseCookie` (`0x32b30`) merely stores a
  pointer to the raw `Cookie:` header; it validates nothing.

So all authentication is implemented **in the Lua layer** (thinklua).

### 5.2 The Lua gate

`thinklua/page_mgr/login_page_logic.lua`, prototype 1, is the per-request
decision. Its logic, from bytecode constants:

```
checkAccessFrom()            -> if false, reason = 'checkAccessFrom'
getStatus()                  -> 'logined' | 'unchecked' | 'timeout'
   'logined'   -> authorized (return false = no login page needed)
   'unchecked' -> set cookie _TESTCOOKIESUPPORT=1
   'timeout'   -> ...
checkIfNeedAuth()            -> if false, reason = 'autoAuth'
   else if 'chpwd' ...        -> forced password change
   else -> look up the item, read fileName, check file exists,
           return (true, {fileName})   -- i.e. serve the LOGIN PAGE
```

`usermgr_logic_impl.checkIfNeedAuth` (proto#9) decides from **`needAuth`**:

| `needAuth` | requires auth |
|---|---|
| `ALL` | always |
| `NO` | never |
| `LAN` | only when access is from LAN |
| `WAN` | only when access is from WAN |

**The compiled default is `needAuth = 'ALL'`** (`usermgr_table_conf.lua`,
main chunk: `SETTABLE R2 K['needAuth'] = 'ALL'`). So out of the box every
request — LAN or WAN — requires a logged-in session.

`curAccessFrom()` resolves LAN vs WAN via `cmapi.nocsrf.IsWANAccess(remote_addr)`,
and `checkAccessFrom()` additionally enforces `fromLANorWAN`, so a WAN-side
request is refused entirely unless explicitly permitted.

Session mechanics: `user_mgr/session_mgr.lua` keeps **file-backed sessions**
under `lua_session` (path template `/var/lua_session/?.lua`), with a `SID`
cookie (`set_sess_client_cookie('SID', ...)`), IP pinning
(`makeSaferByIPAddress`: if `client_ip` changes the cookie is dropped and the
browser is sent to the login page), and rights checks
(`isRightsMeeted` / `checkRightPassed`).

**Conclusion so far:** the upload endpoint is *not* unauthenticated. Reaching
`my_upload_file` requires a valid `SID` session that `getStatus()` reports as
`logined`, which in turn requires passing `doLogin` → `__authLogin` →
`__isUserNamePwdCorrect` against the `cmapi` user DB.

(TBD: whether the specific `do_firmware_upgrade` path is classified as a
`data` endpoint with `needLogin` unset — which would be an exemption worth
checking; and the exact URL.)

### 5.3 `do_firmware_upgrade` is not exempt

Two independent checks agree:

1. **URL routing is driven by login status.** `router/urlpath_2type_conf.lua`
   registers exactly one rule (the empty path `''`), and its handler is:

   ```
   getLoginStatus()
     == 'loginAlready' -> wizardViewWholePage / menuViewWholePage
     == 'loginTimeout' -> loginView
     otherwise         -> loginView
   ```

   i.e. **not logged in ⇒ `loginView`**, regardless of which script the path
   maps to. There is no path that escapes this.

2. **The `hidden` (data) endpoint table is a closed whitelist.** Only these are
   `basicType = data`: `switchlang_entry`, `sntp_data`, `accessdev_data`,
   `captcha_data`, `checkcaptcha_data`, `security_data`, plus the two
   `*.lp` view redirects. **`do_firmware_upgrade` is not in it.**

So the firmware-upload endpoint sits behind the normal authenticated page flow.
It requires a valid `SID` cookie whose session reports `logined`.

### 5.4 What that means

There is **no unauthenticated upgrade trigger**. The premise "if stock will
accept a crafted image we never need code execution" does not hold: stock will
not accept the image without a login first. The attack surface is therefore
reduced to *obtaining a session*, i.e. the admin password — which is exactly
the "cracking the web login" path the question hoped to avoid.

Note also `needAuth` is a config value, not a compile-time constant: an
attacker who could set `needAuth='NO'` would open everything. But setting it
requires an authenticated `cmapi` write — circular.

## 6. What it writes, and where

`fw_flashing` is a **dual-bank (A/B) updater**, driven by the kernel's
`/proc/zte/verinfo/versionstates` interface. From `SetVersionHeader` and
`WriteVersion`:

| proc field | used for |
|---|---|
| `currentverphyaddr` | the **running** bank's start address |
| `curverheaderaddr` | the running bank's header address |
| `curverheader_highstart` | high header start |
| `backverheaderaddr` | the **other** bank's header |
| `maxversionum` | version slot count |

Write sequence in `WriteVersion`:

1. `SetVersionHeader` — reads the proc fields above and computes
   `g_ver_towrite`, `g_upgrade_startaddr`, `g_upgrade_endaddr`. It logs
   `Info:g_ver_towrite=%d, g_upgrade_startaddr=0x%x, g_upgrade_endaddr=0x%x`.
2. Erase nonzero runtime `backverheaderaddr` first (`0xa324..0xa33c`), then
   `CspUserMtdErase(mtd0, g_upgrade_startaddr, ...)` — erase the target bank.
   Logs `start erase ,start addr=0x%x,end addr=0x%x`.
3. `lseek(image, 0x214)` then stream-copy the body to flash
   (`firmware_size=%d, firmware_offset=0x%x`). The `0x214` is
   `hdr[+0x38] - 0x20`: it skips the 20-byte preamble plus the uImage header.
4. `CheckFile` — read the flash back and `memcmp` against the source.
5. `Checkheader` — read 512 B back and compare with the header.
6. If `hdr[+0x8c] != 0` -> `WriteBoot` (bootloader). **Our header has `0x0000`.**
7. Write the version header / update version state.

### Safety assessment

- **Bootloader:** only written when `hdr[+0x8c] != 0`. A header with `0` never
  touches `mtd1`/boot. This is under our control in the image.
- **`tag` / `wifi` / calibration:** never referenced by `fw_flashing` at all —
  no code path reads or writes those partitions.
- **Bank B:** addressed via `backverheaderaddr`, i.e. it is the *alternative*
  bank for the A/B rollback state machine, not a blind overwrite. It is used to
  write the version header/state, not to reflash bank B's kernel/rootfs unless
  the state machine selects that bank.
- **Bank A:** selected only when the running stock bank is B. Header `+0x4c`
  does not force the target. A successful web installation from verified B was
  measured; a stock-A upload instead overwrote B and required UART recovery.

The one thing this does that our sysupgrade does **not** is manipulate the
**version-state / dual-bank header state** (`/proc/zte/verinfo/versionstates`).
That state lives in the header region and is what the bootloader uses to choose
a bank. A failed or interrupted vendor upgrade can leave the bootloader
selecting bank B (stock) instead of bank A (OpenWrt) — recoverable, but it means
the upgrade is **not** a clean single-partition operation.

**Verdict on safety:** the vendor path is materially riskier than our current
UART flow, but it does not touch the bootloader, tag, or calibration, and the
bootloader-update flag is ours to keep at zero.

## 7. Feasibility verdict

### The good news (all confirmed by static analysis)

1. **A web upgrade path exists and is the same one the vendor's own UI uses.**
   Endpoint: the `VersionUpload` upload handler
   (`webmodules/modules/do_firmware_upgrade.lua` -> `file_upload_logic.UploadFile`
   -> `cmapi.callUploadDownloadProc` -> httpd `my_upload_file`), which stages the
   file and invokes `bin/fw_flashing`.
2. **No signature check.** Validation is structural (magic + the three CRC32s we
   already compute) plus read-back `memcmp` of what was written.
3. **The image container is one we can build.** `fw_flashing` wants
   `[20-byte preamble][...][512-byte header at 0x20+hdr[+0x08]][body]`, with
   `hdr[+0x3c]`/`hdr[+0x48]`/`hdr[+0xa4]` as plain `zlib.crc32` — exactly the
   contract in `docs/INSTALL.md` §3 and `tools/h199a-header-regen.c`.
4. **The bootloader is not touched** as long as `hdr[+0x8c] == 0`, which is what
   the unit's own header already has.
5. **`tag` and `wifi` are never referenced** by the flasher.

### The blocker

**The endpoint is not reachable without a logged-in web session.** There is no
unauthenticated trigger:

- `needAuth` defaults to `ALL`, so LAN access needs a session too.
- URL routing returns `loginView` for any request when
  `getLoginStatus() != 'loginAlready'`.
- The upload endpoint is not in the `hidden`/`data` whitelist.

So the "no code execution needed" hope is half-right — we do not need code
execution — but we **do** need a valid admin login first.

### Is that login obtainable? Yes — it is already documented for this unit

`docs/SESSION-JOURNAL.md` §2 records that a previous session logged into this
exact unit's stock web UI as **`multipro` / `multipro`** (the Multilaser default
build), reaching *System Mgmt -> upgrade*, with the login flow:

```
GET  /?_type=loginData&_tag=login_token      -> returns a token
POST /?_type=loginData&_tag=login            Password = sha256(password + token)
```

That flow is confirmed verbatim in the stock code
(`thinklua/template/login_js.lp` computes `sha256(Password+xmlObj)` and posts to
`/?_type=loginData&_tag=login`; `login_token_lua.lua` serves `logintoken`).
Caveats from that journal: the UI was only reachable over **IPv6 link-local**
(`http://[fe80::1%br0]/`) on that boot because the stock DHCPv4 server failed to
register, and the device rejects non-IP-literal `Host` headers.

**So: viable, but only if the user knows (or the unit still has) the admin
password.** It is not a "no credentials" installer.

### Recommended installer shape

Given all of the above, a web installer is buildable but it is **not** a clean
upgrade of our current UART flow:

1. User connects to the stock LAN and logs into the web UI (IPv4
   `http://192.168.1.1/` normally; IPv6 link-local if DHCPv4 is dead).
2. The installer script performs the token/login handshake, then POSTs the
   multipart `VersionUpload` body containing our container.
3. `fw_flashing` erases and rewrites bank A and updates the version-state so the
   bootloader selects the new bank.

**Risks that must be weighed before shipping it to users:**

- It rewrites the **dual-bank version state**. An interrupted run can leave the
  bootloader preferring bank B (stock), so the unit comes back up as stock — not
  bricked, but not installed either.
- It requires the admin password, which most owners have changed or forgotten.
- It is strictly *more* invasive than the UART flow, and it is the vendor's code
  doing the writing, so a bug in it is not ours to fix.

**Honest recommendation:** the format work is genuinely reusable — the container
+ CRC knowledge from §4 lets us produce a vendor-acceptable image — but the
web path's value is limited because it still needs credentials and it moves the
version state. It is a reasonable *fallback* for units whose owner has the admin
password and no UART, not a replacement for the UART installer.

### What else might work (not investigated here)

- **Config-file upload/restore** (`db_usrcfg_upload`, `db_defcfg_upload`) shares
  the same `my_upload_file` path and the same auth gate, so it is no better.
- **TR-069 ACS via DHCP option 43 — the most promising untested lead, and it is
  real.** `bin/cspd` contains `source/dhcp4c_opt43.c` with `parseOpt43` and
  `tr069Opt43` (cspd `0x45878`). Recovered behaviour: it parses DHCP option 43
  vendor-specific sub-options and sends `EV_TR069_SET_OPT43_INFO` to the
  TR-069 core. Sub-options are indexed `bCode-1` for codes 1..4; **code 1 is a
  URL string** (copied with a 64-byte cap), codes 3 and 4 are byte-swapped
  32-bit integers. It logs `bCode:%d, bLen:%d, pbValue:%s, ...` and runs at
  **power-on** (`packageCSPDHCP4COpt43Poweron`).

  This path has **no authentication at all** — a DHCP server on the LAN can
  hand the ONU an ACS URL at boot. If the ACS URL can then drive
  `TR069RpcRequestDownload` -> `CmUpgradeStart` -> the same `fw_flashing`
  backend described in §3-§6, that is a genuine no-credential, no-UART install
  path, and it would bypass the session gate entirely.

  **Not yet verified** (needs the TR-069 core traced: `UpgradesManaged` /
  `Tr069Enable` defaults, whether download-to-upgrade is enabled out of the
  box, and whether the ONU will act on an ACS URL it did not already trust —
  `RemoteUpgradeCertAuth` exists as a config knob). This is the recommended next
  investigation; it is the only path found that is both unauthenticated and
  capable of reaching the flasher.
- **Factory-mode / vendor service ports** — previously tried and failed on this
  unit (288 credential combinations).
