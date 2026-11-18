# NAND storage on the ZXHN H199A

This describes the current bank-aware production path. Historical raw-NAND
shim and software-BCH experiments in [NAND-JOURNAL.md](NAND-JOURNAL.md) are
not current instructions. Their old staging/test regions overlap today's
live overlay and must not be reused.

## Controller, chip and ECC

The ZTE SPI controller at `0x94406000` uses
`files/target/linux/armsr/files-6.6/drivers/spi/spi-zx279128.c` and Linux's
SPI-mem/SPI-NAND core. The flash is Micron MT29F1G01ABAFDWB, SLC:

| Property | Value |
|---|---|
| Main data | 128 MiB, `0x08000000` bytes |
| Page | 2048 data + **128 OOB** bytes |
| Eraseblock | 128 KiB, 64 pages |
| Blocks / pages | 1024 / 65,536 |
| On-die ECC | 8 bits per 512-byte step |

Production normal reads and writes use Micron on-die ECC through the Linux
SPI-NAND core. Raw reads remain available for distinct diagnostic backups.
The vendor bootloader's normal read/program path also enables on-die ECC;
the old assertion that all existing flash was written without parity was
withdrawn. The deleted raw-NAND shim's no-ECC/software-BCH notes do not apply.

Corrected reads report success, a correction bound, or an uncorrectable error.
Micron's status encodes ranges; accumulated 3/6/8-bit bounds are not exact
physical bit counts. Preserve mode and ECC diagnostics with every backup.
The modeled SPI working clock is 50 MHz; this is not a measured SCK waveform.

## Physical layout and active labels

| Physical region | Offset | Bytes | Production treatment |
|---|---:|---:|---|
| Bootloader/environment | `0x00000000` | `0x00100000` | Read-only from OpenWrt; immutable code and bootloader-managed environment are distinct |
| `tag` | `0x00100000` | `0x00100000` | Read-only factory identity, MACs and private stock settings |
| `wifi` | `0x00200000` | `0x00100000` | Read-only calibration |
| `usercfg` | `0x00300000` | `0x00200000` | Read-only vendor configuration |
| `defcfg` | `0x00500000` | `0x00200000` | Read-only vendor defaults |
| A kernel | `0x00700000` | `0x00300000` | Writable only when A is selected |
| A rootfs | `0x00a00000` | `0x00d20000` | Writable only when A is selected |
| A header | `0x01720000` | `0x00020000` | Writable only when A is selected |
| B kernel | `0x02000000` | `0x00300000` | Writable only when B is selected |
| B rootfs | `0x02300000` | `0x00d20000` | Writable only when B is selected |
| B header | `0x03020000` | `0x00020000` | Writable only when B is selected |
| `legacy_overlay` | `0x04000000` | `0x01000000` | Read-only old raw-MTD overlay |
| `staging` | `0x05000000` | `0x01400000` | Read-only; **contains the UBI window below** |
| `overlay_ubi` | `0x05400000` | `0x01000000` | Writable shared UBI overlay |

Unlisted gaps are not automatically blank or disposable. `staging` and
`overlay_ubi` overlap physically; never erase staging to transfer an upgrade.

Validated BootPara selection moves `kernel1`, `rootfs`, `header` to the active
bank and gives its peer the `*2` names. Physical partition order stays fixed:
UBI is mtd13 and B's header is mtd14. Exact MTD flags and independent SPI
write ranges are in [BANKS.md](BANKS.md). Unknown production selection fails
closed. The whole-flash master is read-only.

## UBI overlay and first-boot preflight

`overlay_ubi` spans 84–100 MiB, `[0x05400000,0x06400000)`. Production preinit
attaches UBI with VID offset 2048, then uses its dynamic `rootfs_data` volume
of 104 LEBs as a UBIFS overlay over the SquashFS root. Existing configuration
is shared between OpenWrt banks and preserved by ordinary sysupgrade.

Before the **first production boot**, verify the entire window in your own
complete corrected backup is erased, or establish that its contents are
disposable after saving them. An attach failure over detected UBI metadata
enters recovery instead of formatting; foreign attached volumes without
`rootfs_data` also enter recovery. The fallback blank test checks only for
`UBI#` at eraseblock starts. It does not detect arbitrary non-UBI data and
can format such a window. A free window on one router proves nothing about
another router's contents.

Do not write a `deadc0de` seed, run old software-BCH migration commands, or
erase old block 799 (`0x063e0000`) on production. These belong to retired
layouts. `sysupgrade -n` resets only the UBI `rootfs_data` volume and discards
its configuration; it does not erase the whole UBI device.

## Backups and private inputs

Back up before installation, using a read-only acquisition environment. An
unmodified stock web UI does not provide a complete backup path in this
repository. Establishing a suitable RAM boot/transport may require UART and
bench preparation; the scripts with private images, relay controls or network
namespaces are not generic first-install utilities.

Use an acquisition environment that keeps the entire array read-only and does
not mount a writable overlay. A read-only master node alone does not prevent
writes through writable child partitions. Do not take a consistency backup
while stock synchronization, flashing or filesystem writes can change it.

Two source tools perform read-only acquisition when compiled for the router
and copied to RAM:

- `tools/nand-dump.c`: `nand-dump --raw|--corrected MTD`. It requires a
  read-only 128 MiB master with exact 2048+128 geometry, streams physical pages
  without bad-block skipping, and rejects short/uncorrectable corrected reads.
- `tools/nand-read-range.c`: `nand-read-range MTD offset length /tmp/new-file`.
  It uses ECC-reporting `MEMREAD`, requires page alignment, refuses existing
  outputs, and publishes the RAM filename only after a complete corrected read.

For example, once an identified read-only RAM environment has working SSH and
an ARM-compiled dumper at `/tmp/nand-dump`, stream the master directly to a
private **host** file; a whole capture will not fit in the router's RAM:

```sh
ssh root@192.168.1.1 '/tmp/nand-dump --corrected /dev/mtd0' \
  > /private/nand-corrected-1.partial \
  2> /private/nand-corrected-1.log
```

Confirm the command succeeded, the completion record reports zero read errors,
and the host file is exactly **142,606,336 bytes**: 65,536 records of 2048 data
bytes followed by 128 OOB bytes. Repeat independently into new filenames and
require identical corrected hashes. Retain the complete interleaved captures
and diagnostics. Raw captures can differ where ECC repairs bits; do not label
raw data as corrected or silently substitute it on an uncorrectable read.

Create a separate **134,217,728-byte data-only** view on the host by retaining
the first 2048 bytes of each 2176-byte record. Keep the interleaved original.
This example refuses to overwrite its output:

```sh
python3 - <<'PY'
from pathlib import Path
source = Path('/private/nand-corrected-1.partial').read_bytes()
assert len(source) == 65536 * 2176
with Path('/private/nand-corrected-data.bin').open('xb') as output:
    for offset in range(0, len(source), 2176):
        output.write(source[offset:offset + 2048])
start = (0x05400000 // 2048) * 2176
end = (0x06400000 // 2048) * 2176
print('UBI window data and OOB completely erased:',
      source[start:end] == b'\xff' * (end - start))
PY
```

Only do this after the acquisition checks passed. On this data-only view,
the fixed physical offsets in the table apply directly. Extract the complete
128 KiB physical A header as the canonical build template. For example:

```sh
python3 - <<'PY'
from pathlib import Path
data = Path('/private/nand-corrected-data.bin').read_bytes()
assert len(data) == 0x08000000
with Path('/private/header-template.bin').open('xb') as output:
    output.write(data[0x01720000:0x01740000])
PY
```

A `False` blank result is a reason to inspect and preserve the contents,
not an instruction to erase them. The template must come from a valid header
on this unit; byte count alone does not establish validity or identity.
Do not feed an interleaved data+OOB image to `flash-prep.py` as a data-only dump.
The canonical production-build input is the extracted exact 128 KiB template.

Extract the **complete corrected stock** kernel/rootfs from a bank verified
to contain stock, using its physical addresses above. Do not assume B is stock
after a stock-A web installation. `tools/extract-stock-calibration.py` accepts
a 3 MiB stock kernel bank (or its supported raw vmlinux), a complete
`0xd20000`-byte encrypted stock rootfs, and a new private output directory:

```sh
python3 tools/extract-stock-calibration.py \
  /private/stock-kernel-ecc.bin /private/stock-rootfs-ecc.bin \
  /private/calibration
```

It supports the hash-identified July 2021 stock firmware only, rejects other
versions, validates decryption and filesystem CRCs, and writes a completion
report. Use its original 512-byte `MT7603E_EEPROM.bin` as the build input.
The device supplies its own calibration trims and MACs at runtime. See
[WIFI.md](WIFI.md) for the calibration contract; do not substitute a random
EEPROM or make up missing trims.

## Writes, fallback and recovery

ECC corrects bounded bit errors; it is not proof a write landed. The native
upgrade writes rootfs, kernel, then header last, verifying each readback. The
guarded U-Boot bank-A installer additionally verifies two independent TFTP
copies and exact UART echoes before erase. Its CLI and physical scope are in
[INSTALL.md](INSTALL.md).

An incomplete firmware image can fail bootloader CRC checks and select a valid
peer. Fresh power-cut qualification of this bank-aware release is not claimed.
Stock `syn_version` can overwrite OpenWrt after its default 300-second timer;
avoid unattended fallback and synchronization/upload races. The bootloader
may update environment bytes during normal bank selection even while immutable
boot code and calibration remain unchanged.

An earlier A-header-erasure drill also found that UBI EC headers can be logged
as empty **boot-class** headers because their class word is 1. Firmware
selection uses class 0; this observation did not make a UBI block bootable or
authorize changing UBI metadata. Keep historical drill results distinct from
the current release's validation in [VALIDATION.md](../VALIDATION.md).


## Historical investigation

Earlier measurements, withdrawn hypotheses and old commands are preserved in
[the archived notebook](history/NAND-BRINGUP.md). They are not current installation instructions.
