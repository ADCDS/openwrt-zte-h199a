# Install through the stock web interface

The current production kernel follows either bootloader-selected bank.
The stock updater writes its inactive bank: stock A → OpenWrt B,
stock B → OpenWrt A. The same image03 container passed both directions on
one H199A on 2026-11-18, in about 98 seconds each using the Python client.
Neither upload used a source-bank override or sent UART bytes; UART was used
for controlled test setup and boot observation.

Read [INSTALL.md](INSTALL.md) first. You need your own verified full backup,
exact 128 KiB header template, supported calibration and matching production
build. Before its first boot, verify the complete 84–100 MiB UBI window is
blank or explicitly disposable after backup. The production overlay fallback
does not prove every byte is blank. Reference release binaries were built
from the tested unit's inputs and are not generic factory images for other units.

The upload needs no UART. This does not supply a backup/calibration extraction
path for an unmodified stock web UI or remove the need for recovery planning.

## Build or check the web container

Use freshly built **bank-aware production** parts, not repacked legacy kernels:

```sh
python3 tools/h199a-netinstall.py --parts /private/parts \
  --out /private/h199a-webflash.bin
```

`--parts` names a directory containing exactly sized `kernel`, `rootfs` and
`header` files. The stock UI takes the resulting `.bin`, not a sysupgrade tar.
The verified container is 16,908,820 bytes. Hash your own build; its header
and calibration came from your private inputs.

To assemble/check without a network upload or output file:

```sh
python3 tools/h199a-netinstall.py --parts /private/parts --dry-run
```

`--out` writes a file and always exits before network access, even with a
password set. `--dry-run` by itself only checks; **combining it with `--out`
still writes the output file**. Neither mode performs the legacy-kernel
source-bank upload gate. Thus a successfully built container is not proof
that an old A-only kernel can boot the updater's chosen bank.

For legacy kernels, network upload requires `--source-bank b` after verifying
the current stock boot is B. That option is only an operator assertion, not
a detector or bank switch. Use a current production build for new installs.

## Avoid stock synchronization

Stock `cspd` starts `/bin/syn_version` after a default 300-second timer.
It clones the running stock image into the peer. It can overwrite OpenWrt
after fallback or race an upload. Start from a fresh stock boot, prepare
everything beforehand and complete the upload before synchronization begins.
The client does not detect that process or automatically select a stock bank.

## Upload through the stock UI

1. Connect a LAN cable and open `http://192.168.1.1/`.
2. Log in with the unit's stock administrator credentials. The tested
   Multilaser firmware used `multipro` / `multipro`; use your unit's credentials.
3. Open **Gerenciamento & Diagnóstico → Gerenciamento de sistema → Upgrade
   de Software**.
4. Select the verified webflash `.bin`, click **Upgrade**, and confirm.
5. Keep power connected through validation, flashing and reboot.
6. Require actual OpenWrt LuCI and check its board/version and persistent
   overlay as described in [INSTALL.md](INSTALL.md). HTTP 200 alone is not
   proof of validation or installation.

A fresh overlay uses `root` with an empty password; set a password through
LuCI. An existing shared OpenWrt overlay can preserve previous credentials.

## Upload using the Python client

Omit `--out` and `--dry-run`:

```sh
python3 tools/h199a-netinstall.py --parts /private/parts \
  --host 192.168.1.1 --user multipro
```

The password is prompted for, or read from `H199A_PASSWORD`; it is not accepted
as a command-line argument. The client uses the promoted SID session cookie,
fetches the upgrade page's CSRF token, supplies the exact POST-body `Check`
digest and follows upload/reboot status. A reboot disconnect or stock reboot
flag alone is insufficient: success requires real OpenWrt LuCI afterwards.

The client does not acquire a NAND backup or validate the connected unit's
calibration/UBI-window ownership. Complete those preflights separately.

## Failures and recovery

After a failed/interrupted upload, inspect the fresh boot and physical-bank
state before retrying. Avoid leaving stock unattended during its synchronization
timer. Never repair an upload by aliasing bank windows or erasing bootloader,
calibration, vendor configuration or shared UBI.

The public guarded UART recovery helper described in [INSTALL.md](INSTALL.md)
writes **physical bank A only**. It must not be applied blindly to B. Keep
all raw stock UART captures private; they can contain Wi-Fi credentials.

The container format and vendor write boundaries are documented in
[WEB-UPGRADE.md](WEB-UPGRADE.md); OpenWrt's bank selection, write barriers
and native upgrade rules are in [BANKS.md](BANKS.md).
