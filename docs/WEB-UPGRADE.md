# Stock web upgrade protocol and container

This is the current protocol reference. For installation steps and prerequisites
use [INSTALL-NO-UART.md](INSTALL-NO-UART.md). The bank-aware production kernel
supports either inactive-bank destination; the same image03 container passed
both stock web directions on one H199A on 2026-11-18.

## Authenticated upload

The stock upgrade path is `VersionUpload` → `do_firmware_upgrade.lua` →
`file_upload_logic` → `cmapi.callUploadDownloadProc` → httpd upload handling →
`CmUpgradeStart` → `cspd` validation → `fw_flashing`. Validation performed
before the flasher matters as much as the flasher's final file seeks.

The endpoint needs a logged-in stock administrator session. `needAuth`
defaults to `ALL`, normal routing returns the login view without a valid
session, and firmware upload is not an exempt hidden/data endpoint.
The Python client implements the tested sequence:

1. Obtain login/session tokens and hash the supplied password with the login
   token as required by stock firmware.
2. Retain the promoted `SID` cookie returned after login.
3. Fetch the upgrade view and its current CSRF token.
4. POST the preflight form with the upload token and current view CSRF token.
   Its `Check` header is SHA-256 of that exact form body.
5. Send multipart `VersionUpload` with the upload token. This firmware request
   does not use the preflight form's `Check` header.
6. Observe status/reboot and require actual OpenWrt LuCI after restart.

Passwords are prompted for or supplied by `H199A_PASSWORD`, never argv.
HTTP 200, upload acceptance and reboot flags are not completion evidence.
See `tools/h199a-netinstall.py` for the supported implementation.

## Verified container layout

| Region | File offset | Contents |
|---|---:|---|
| CSP magic | `0x000` | Little-endian words `99999999 44444444 55555555 aaaaaaaa` |
| Prefix length X | `0x010` | `0` |
| NAND header | `0x014` | First 512 bytes of the matching 128 KiB header block |
| Kernel container | `0x214` | `0x300000` bytes |
| Rootfs | `0x300214` | `0xd20000` bytes |
| End | `0x1020214` | 16,908,820 bytes |

NAND header `+0x08 = 0x266` is independent metadata and stays unchanged;
it is **not** the file prefix length. `cspd:verifyCspFwMagic` rejects missing
magic. `UpgradeCheckFirmware` reads the header at `X+20` and validates payload
CRCs at the absolute offsets in header `+0x38` and `+0x44`. The flasher reads
the body at `X+0x214`.

The builder checks exact part sizes, model, original geometry, absolute
payload offsets, kernel/rootfs CRCs, inner header CRC at `+0xa4`, NAND
extension magic and extended CRC at `+0x1fc`. Kernel/rootfs bytes remain
unchanged. `fw_flashing` prepares version metadata `+0x1f0..+0x1fc` before
appending the header to NAND. The identified path uses structural/CRC checks
and readback; it does not require an RSA/ECDSA firmware signature.

The original rejected format omitted CSP magic and copied `0x266` into X.
Staging space was not the cause. Do not reconstruct a container from the
superseded seek interpretation.

## Vendor write boundaries

`SetVersionHeader` reads `/proc/zte/verinfo/versionstates` to select the
inactive bank and its backup header:

| Running stock bank | Header window fields | Vendor write window |
|---|---|---|
| B | `+0x1e0`, `+0x1e4` | `[0x00700000,0x02000000)` |
| A | `+0x1e8`, `+0x1ec` | `[0x02000000,0x03900000)` |

The vendor erase windows are wider than OpenWrt's compiled firmware-write
ranges. The flasher separately erases runtime `backverheaderaddr`, writes and
verifies the inactive payload, then writes version metadata/header. Header
`+0x4c` does not force A. Preserve both original windows: U-Boot also uses
their geometry to classify headers. Never alias both windows to A.

Bootloader-update flag `+0x8c` must be zero; the builder refuses otherwise.
That avoids the flasher's optional bootloader-image write. The bootloader
itself can still update environment sectors while selecting a bank. Immutable
boot code, environment and firmware headers are separate regions.

The earlier stock-A trial used an A-only kernel: stock correctly wrote B,
but that kernel could not mount B's rootfs. Recovery restored the saved stock
B. Repacking that kernel cannot add bank awareness. Current production fixes
the boot-bank selection; it leaves vendor container geometry unchanged.

Stock `syn_version` can clone the running stock image into its peer after a
default 300-second timer. Avoid synchronization/upload races and unattended
fallback. The client neither detects synchronization nor switches banks.
OpenWrt's own MTD/SPI barriers apply once OpenWrt runs; they do not constrain
the vendor updater. See [BANKS.md](BANKS.md) and [NAND.md](NAND.md).


## Historical investigation

Earlier measurements, withdrawn hypotheses and old commands are preserved in
[the archived notebook](history/WEB-UPGRADE-ANALYSIS.md). They are not current installation instructions.
