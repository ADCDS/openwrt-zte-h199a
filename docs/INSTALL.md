# Installing OpenWrt on the ZTE ZXHN H199A

This guide describes the bank-aware production image as qualified on one H199A
on 2026-11-18. Read [VALIDATION.md](../VALIDATION.md) before installation.
The build uses OpenWrt 24.10-SNAPSHOT, kernel 6.6.151, target `armsr/armv7`.
Wired SSH/LuCI, routing and the 2.4 GHz AP work; 5 GHz remains unreliable.

The stock web updater installs into the inactive bank: stock A → OpenWrt B,
stock B → OpenWrt A. Native `sysupgrade` replaces the running OpenWrt bank.
The peer stays read-only under OpenWrt. See [BANKS.md](BANKS.md).

## Before the first production boot

1. Save and verify a complete backup of **your own unit**, including OOB,
   bootloader, vendor configuration, both firmware banks, `tag` and `wifi`.
   Preserve raw and ECC-corrected captures as distinct files. Follow
   [NAND.md](NAND.md#backups-and-private-inputs); a successful `dd` alone does
   not establish that NAND had no uncorrectable read errors.
2. Obtain an exact **131,072-byte header template** and the supported original
   `MT7603E_EEPROM.bin` from your own stock firmware. See the extraction steps
   in [NAND.md](NAND.md#backups-and-private-inputs) and [WIFI.md](WIFI.md).
   Keep backups, extracted header/calibration and per-unit builds private. The
   separately reviewed bench-reference release assets are an explicit exception,
   not generic images for other units.
3. Inspect the complete intended UBI window, physical
   `[0x05400000,0x06400000)` (84–100 MiB), in that verified backup. Confirm it
   is erased, or explicitly disposable after preserving its contents. Do this
   **before booting production**, which can initialize that window.
4. Establish a recovery path and a known bootable peer firmware. For UART,
   follow [UART-PADS.md](UART-PADS.md): 3.3 V, 115200 8N1, RX/TX/GND only.
   One candidate pad is a boot strap. Do not connect adapter VCC.

The overlay hook protects an existing UBI image from an attach-failure format
when it finds an erase-counter header. Its fallback checks only for `UBI#` at
each eraseblock start; it does **not** prove that all other bytes are blank.
An unknown non-UBI payload can be formatted. Never assume this area is free
because it was free on the bench unit.

The web upload itself needs no UART. Obtaining the private inputs and a full
stock backup is a separate prerequisite; this repository does not provide a
turnkey backup extractor for an unmodified stock web UI.

Release binaries are a matched **reference build from the tested unit**.
They do not replace your own header/calibration or prove another unit's flash
layout is disposable. Build with your own inputs before installation on
another unit; do not upload the reference web image to unrelated hardware.

## Build and validate

Use a Linux OpenWrt build environment with Python 3, host binutils and
`device-tree-compiler` (`dtc`, `fdtget`, `fdtput`). Calibration extraction also
requires OpenSSL libcrypto. Run the recipe from the repository root:

```sh
H199A_HEADER=/private/header-template.bin \
H199A_MT7603_EEPROM=/private/calibration/MT7603E_EEPROM.bin \
BOOT_PROFILE=production JOBS=1 ./build.sh
```

Set the profile explicitly: bare `./build.sh` defaults to `normal`, whose
storage policy differs. Use `build.sh` for every distributable build so the
pinned sources, overlay, calibration and profile checks are applied.

Outputs are under `openwrt/bin/targets/armsr/armv7/`:

| Output | Purpose |
|---|---|
| `openwrt-armsr-armv7-zte_h199a-squashfs-sysupgrade.tar` | Native upgrade archive |
| `…-sysupgrade-parts/{kernel,rootfs,header}` | Matching loose parts for the web builder or bank-A U-Boot installer |
| `…-sysupgrade-production.json` | Part hashes, payload/header CRCs and comparison against your header template |
| `…-sysupgrade-calibration.json` | Calibration, DTB and image checks |

Keep reports and parts together. The build preserves all template bytes except
the kernel, rootfs and inner-header CRC fields; the stock flasher or native
upgrade helper subsequently prepares bank/version metadata. A static template
is not an automatically incremented recovery header.

To validate an existing matching tar and extract its parts on the host:

```sh
python3 tools/verify-production-image.py /path/to/sysupgrade.tar \
  --header-template /private/header-template.bin \
  --extract-dir /private/parts
```

This validates the archive against the supplied template. It cannot establish
that the template belongs to the connected unit or inspect its flash.

## First installation through stock web firmware

Follow [INSTALL-NO-UART.md](INSTALL-NO-UART.md) for the UI/client sequence.
Build a verified vendor container from your matching production parts:

```sh
python3 tools/h199a-netinstall.py --parts /private/parts \
  --out /private/h199a-webflash.bin
```

The stock UI takes this `.bin`, not the sysupgrade tar. `--out` writes the
file and exits without network access. To upload using the Python client,
omit `--out`; the password is prompted for or read from `H199A_PASSWORD`:

```sh
python3 tools/h199a-netinstall.py --parts /private/parts
```

Use a fresh stock boot and complete the upload before its default 300-second
`syn_version` synchronization timer. That process clones the running stock
firmware into the peer and can race an upload or overwrite OpenWrt after a
fallback. The client does not detect synchronization or switch stock banks.

Maintain power through validation, flashing and reboot. Require actual OpenWrt
LuCI after reboot; HTTP 200 alone proves no installation. On a fresh overlay,
log in as `root` with an empty password and set a password immediately. An
existing shared UBI overlay can retain previous credentials and configuration.

## Verify the installed system

Confirm OpenWrt's version, board identity, active-bank mapping and persistent
overlay. These observations are read-only:

```sh
cat /etc/openwrt_release
uname -r
cat /tmp/sysinfo/board_name
cat /proc/mtd
mount
```

Active labels must be `kernel1`, `rootfs`, `header`; their physical offsets
must match one complete bank in [BANKS.md](BANKS.md). Check the exact writable
MTD set and compiled `write_policy_map` there. The overlay should be UBIFS
`rootfs_data` on `overlay_ubi`, not a temporary RAM overlay or old raw JFFS2.
Save configuration, reboot, and verify persistence before relying on it.

## Native upgrades over LAN

Use the matching production sysupgrade tar. Wired file transfer works; use
`/tmp`, not flash, to stage the archive. On the host:

```sh
sha256sum /path/to/sysupgrade.tar
scp -O /path/to/sysupgrade.tar root@192.168.1.1:/tmp/sysupgrade.tar
ssh root@192.168.1.1 'sha256sum /tmp/sysupgrade.tar'
```

Compare the two hashes before continuing. Then validate and upgrade:

```sh
ssh root@192.168.1.1 'sysupgrade -T /tmp/sysupgrade.tar'
ssh root@192.168.1.1 'sysupgrade /tmp/sysupgrade.tar'
```

An SSH disconnect during reboot is expected. Reconnect and verify the new
image, overlay, configuration and active bank. Normal upgrades preserve the
separate UBI overlay, including edited files that can shadow the new SquashFS.
`sysupgrade -n` recreates only the `rootfs_data` UBI volume and discards its
configuration; that reset path was host-tested, not exercised on the owner's
release installation. Do not force validation with `-F`.

The helper prepares a header from this unit's current/peer headers, chooses a
serial above both selectable banks, then writes and verifies **rootfs → kernel
→ header last**. Bank B refuses legacy A-only kernels before any erase.
See [BANKS.md](BANKS.md) for checks and power-loss limits.

Never erase the old `staging` range `[0x05000000,0x06400000)` or use its old
write-test block as scratch: both include the live UBI overlay.

## Guarded UART installation/recovery: physical bank A only

`tools/install-bank-a-uboot.py` writes physical A and preserves B. Use it only
when replacing **A is intended**, B is independently known bootable, all backup
and UBI preflights above passed, and the header/parts belong to this unit.
It is not a bank-B recovery tool, and erasing A's header is not a general
instruction to boot stock.

Before writing A, establish that its prepared version serial selects it above
both freshly inspected selectable headers. The guarded installer validates
CRC/template agreement but **does not promote serials**. Never erase the peer
header merely to force A selection. Prefer the stock web path for first install.

For expert offline recovery preparation, the packaged C helper can be compiled
on the host and run as `h199a-upgrade-header-host a CURRENT_A BACKUP_B KERNEL
ROOTFS NEW_OUTPUT`. It needs a valid own-unit A header and freshly inspected B
header, creates only a new RAM/host file, and checks payloads/serial overflow.
Create a new matching tar with that prepared header, then use the **same
prepared header as `--header-template`** when validating/extracting and running
the guarded installer. Replacing only a loose TFTP header fails matching checks.
This host composition is source-supported, not a separately hardware-qualified
recovery workflow. If identity, peer bootability or selection is uncertain,
stop before erase and establish a reviewed recovery plan.

This helper integrates with the original bench: it requires an active systemd
unit named `h199a-tftp`, whose `ExecStart` contains the matching `--root`,
and an executable power controller accepting `on` and `off`. The TFTP root
must already serve byte-identical files named `kernel`, `rootfs`, `header`.
The existing U-Boot `ipaddr`, `serverip` and enabled `verify` setting must
match its checks. `--serverip` checks the existing value; it does not set it.
Review these dependencies and the source before adapting it to another bench.

The actual CLI is shown below; replace every example path and checksum with
verified local values, and use a new output directory and fresh raw log:

```sh
python3 tools/install-bank-a-uboot.py --execute \
  --device /dev/serial/by-id/YOUR_UART_ADAPTER \
  --raw-log /private/uart-install-A.raw \
  --sysupgrade-tar /private/sysupgrade.tar \
  --header-template /private/header-template.bin \
  --tftp-root /srv/h199a-tftp \
  --expect-tar-sha256 REPLACE_WITH_VERIFIED_64_HEX_DIGITS \
  --output /private/install-A-NEW \
  --serverip 192.168.1.100 --ipaddr 192.168.1.1 \
  --relay /path/to/power-controller
```

Its closed command allowlist contains only A's three regions and read-only
environment inspection. It confirms each UART command's exact echo before
executing it, downloads each part twice and compares both copies before erase,
then requires full readback equality. It aborts on skipped/bad blocks, error
text, wrong sizes or short comparisons. It writes rootfs, kernel, then header.
Success and failure both end with power off; boot acceptance is separate.
It neither changes environment variables nor issues `saveenv` or a boot command.

After a controlled boot, require kernel/filesystem CRC success, OpenWrt,
the expected bank and the persistent overlay. Stop and inspect any fallback;
stock must not remain unattended while its synchronization timer runs. Preserve
recovery evidence privately: stock UART output can contain Wi-Fi keys.

Recovering OpenWrt in B or restoring an entire original stock bank requires
a separately reviewed plan using its own saved image and physical ranges.
Do not mirror A's commands by replacing digits. Never write the bootloader,
`tag`, `wifi`, vendor configuration or shared UBI merely to recover firmware.


## Historical investigation

Earlier measurements, withdrawn hypotheses and old commands are preserved in
[the archived notebook](history/INSTALL-BRINGUP.md). They are not current installation instructions.
