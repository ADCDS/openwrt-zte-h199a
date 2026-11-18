> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# NAND (spifc) — ZX279128S / ZXHN H199A

Native transport: `files/target/linux/armsr/files-6.6/drivers/spi/spi-zx279128.c`.
The earlier raw-NAND shim remains in source history/diagnostics but is disabled
in the current kernel configuration.
History and withdrawn hypotheses: [`NAND-JOURNAL.md`](../NAND-JOURNAL.md).


## Current production bank selection — 2026-11-18

Physical bank addresses stay fixed. Logical `kernel1` / `rootfs` / `header`
labels follow the validated bootloader-selected bank; the peer has
`kernel2` / `rootfs2` / `header2` and stays read-only. `overlay_ubi` remains
mtd13; the added physical B header is mtd14. Older tables below describe
physical A-first layouts, not guaranteed active names. Production transport
permits only the selected firmware window plus UBI. See [BANKS.md](../BANKS.md)
for exact ranges, fail-closed selection and native upgrade behavior.

## 2026-11-15: the bootloader sees every UBI PEB as an empty "boot" header

With bank A's header erased (recovery drill), `zteboot_search_firmware` kept
scanning past bank B and logged `found boot … correct header has been found
@5400000` (`FwClass:0x1`, `crc_len:0x0`). From the unit's bootloader
(`zteboot_verify_header` @0x47f12640): the word at +4 selects the class.
**0 = firmware**: needs magic words at +0xf4/+0xf8/+0xfc/+0x100 and the
crc32 over `hdr[0:0xa4]` at +0xa4. **1 = boot**: the upgrade-key compare is
skipped when +8 is 0 or 0xffff, the entry count at +0x2c must be ≤ 4, and the
CRC covers 20×count bytes against +0x30.

A UBI EC header (`UBI#`, version 1, three zero pad bytes, 64-bit big-endian
EC) has +4 = 1, +8 = 0 (EC < 2³²), +0x2c = 0 and +0x30 = 0, so it matches
as an empty boot-class header. Effects:

- It only shows when a bank's header is missing. The search stops after two
  headers, and with both banks valid it never gets past 0x3020000.
- Firmware selection uses firmware-class headers only. The drill still booted
  bank B, and the 5b power-cut test (bank A header present but CRC-invalid)
  never reached the window.
- A UBI block cannot impersonate a firmware header, because its class word is 1.

## ECC: "no-ECC" was the retired raw shim; the production path uses on-die ECC

Resolved from the driver source (2026-11-15), because the install/sysupgrade
design note and the older sections below call the flash "no-ECC":

- **Deleted raw shim** (`drivers/mtd/nand/raw/zx_spifc_nand.c`, compatible
  `zte,ZX279127-spifc`, `CONFIG_MTD_NAND_ZTE_SPIFC`): used
  `NAND_ECC_ENGINE_TYPE_NONE` and deliberately disabled the chip's on-die ECC.
  That is the source of every "no ECC, silent bit flips" statement. It was
  never in a shipping config, had no DTS user, and was removed on 2026-11-16
  together with its patch, its Kconfig symbol and its host tests - it was also
  the only file in the tree that `checkpatch --strict` reported errors for.
  Its ECC experiments are in the history if they are ever wanted again.
- **Production / native path** (`CONFIG_SPI_ZX279128` SPI-mem transport under
  the stock Linux SPI-NAND core `CONFIG_MTD_SPI_NAND`): the core selects the
  chip's **Micron 8-bit/512 B on-die ECC** (`NAND_ECC_ENGINE_TYPE_ON_DIE`,
  `micron_8_ecc_get_status`). `spinand_ondie_ecc_prepare_io_req` enables
  `CFG_ECC_ENABLE` for every non-raw page request, so bank-A `mtd write` and
  every UBI write store parity, and reads report **per-request** status
  (0/3/6/8-bit corrected or `-EBADMSG`). The transport only moves bytes — it
  rejects host-ECC requests (`op->data.ecc`) and never changes the ECC mode.

So production writes **and** reads are on-die-ECC protected, and the vendor
bootloader reads bank A with ECC enabled too (B0 = 0x18, ECC_EN), so its
kernel/fs CRC sees the same corrected bytes `flash-prep.py` hashed. The
round-231 "on-die ECC not viable" finding below applied only to the raw shim
(parity-less pages read with ECC on) and does not apply to the native path.
Read-back `cmp` after every bank-A write is still required: ECC corrects flips,
it does not make `nand write ... OK` self-proving.

## 2026-11-11: bounded write qualification passed

Candidate P passed the reserved-block test: 64 full-page programs each matched
through normal ECC and raw reads, with zero corrections and OOB 0–63 preserved.
The final erase restored all data and OOB to `ff`. After a cold boot into the
fully read-only O image, a complete corrected data+OOB capture matched both
pre-test backups exactly: SHA256
`525fda3e8fbb82f90064f986c3fe9672f24d4a1af1094f1970f65f4ed25edd32`.
This verifies unchanged contents outside the test window as well. Private
`logs/native-staging-write-qualification.json` records image/hash provenance.
This does not yet qualify a writable filesystem or upgrade procedure.

The default native transport still denies all array writes. An explicit
`spi_zx279128.write_test=1` diagnostic mode permits erase only at physical
`0x063e0000`, and program only within that 128 KiB block (block 799). It records
one program attempt per page before sending the command; neither erase nor a
failed transaction clears that boot's bitmap. The driver cannot be rebound
through sysfs. This is a conservative test restriction, not a chip limit.

The private test DTB makes all twelve original partitions read-only and appends
`write-test` as mtd13. The RAM boot verifier checks the flags, exact window,
geometry and runtime guard. `tools/nand-staging-test.c` refuses any other device
or geometry, verifies the entire block's data and OOB are erased, then tests 64
full-page programs, corrected/raw readback, and erase/readback. Failures stop
without retry or automatic cleanup. The transport tests exercise FIFO capacity,
short tails, exact bounds, failure latching and the page-attempt bitmap.

The existing overlay has also been mounted read-only and logically archived;
the full physical backups retain filesystem metadata beyond the tar archive.
Its old radio/init overrides must not be blindly restored into the final image.

### Manufacturer constraints and overlay migration

Micron's exact M78A datasheet permits four partial programs per page but limits
programming of main data and ECC-protected metadata areas to once. It describes
OOB 0–3 as reserved, 4–31 as unprotected metadata, 32–63 as protected metadata,
and 64–127 as parity. No ascending-page requirement was found in this revision.
See [Micron M78A, Rev. G, pages 29, 44–46 and 54](https://www.farnell.com/datasheets/3151163.pdf).

Pinned Linux 6.6.151 exposes OOB 2–63 in `micron_8_ooblayout_free()`. JFFS2 writes
an eight-byte AUTO_OOB cleanmarker after erase, then separately writes first-page
data. SPI-NAND fills the entire cache and enables ECC for that first OOB-only
operation. Two programs do not alone prove corruption, but the reserved-byte
overlap and protected-area programming behavior remain unqualified. UBI/UBIFS
with full-page EC/VID headers avoids the JFFS2 OOB cleanmarker and is the preferred
next migration candidate, with the existing configuration preserved separately.

### Guarded UBI qualification preparation

Candidate T's private RAM image reserves physical `[0x05400000,0x06400000)`
(84–100 MiB, 128 eraseblocks) inside staging. It preserves the twelve original
MTD partitions as read-only and appends `ubi-test` as mtd13. This avoids the
existing 64–80 MiB overlay and the occupied start of staging. It is a filesystem
test area, not a migration of the live overlay. First attachment and initial
filesystem tests pass; repeated boots and outside-region verification remain.

`NAND_UBI_TEST=1 BOOT_PROFILE=diagnostic BRINGUP=1` builds the diagnostic support;
the canonical DTB remains entirely read-only. A separately checked private DTB
is required to expose the test window. The controller permits only programs
inside rows `[0xa800,0xc800)` and aligned erases there. This mode is mutually
exclusive with the one-block `write_test` mode.

The independent `spinand.diagnostic_write_guard=1` option is mandatory. Under
the SPI-NAND device mutex, it latches the first program/erase failure and
returns `-EROFS` for that and all later mutations. It preserves the original
errno and physical location in the diagnostic log. Bad-block marking is denied
before either physical markers or the generic RAM BBT can change. Both the core
and transport are built in, and sysfs bind/unbind controls are suppressed, so
the latch lasts until reboot. Default production builds omit the diagnostic
core option. The unselected normal I/O path keeps its original error behavior.

Before attachment, the RAM boot gate and bootstrap check the exact window,
original partition protections, both guards, no conflicting test mode and no
attached UBI device. `tools/nand-ubi-preflight.c --check-blank` then reads all
8192 pages through both corrected and raw modes, requiring every data/OOB byte
to be `ff`, no ECC corrections or read failures, and all 128 blocks good. It
opens only `/dev/mtd13`, read-only, and contains no mutation operation. Create
the device node from verified sysfs identity after the diagnostic `/dev` tmpfs
is mounted. Mock-syscall tests include corruption on the last page and spare
byte, so sampling cannot satisfy this check.

UBI attachment itself writes EC/VID metadata; it must follow that live preflight.
Use explicit attachment with VID offset 2048, then an empty dynamic test volume
and UBIFS with compression disabled. Do not automatically attach via `ubi.mtd=`
or DT `linux,ubi`, and do not use an attachment-failure-to-`ubiformat` fallback.
Persistence, metadata/whiteout behavior, garbage collection, repeated boots and
unchanged flash outside the window remain acceptance gates.

The live preflight passed all 8192 raw and corrected pages with every byte
erased. Attachment found 128 good PEBs and no bad/corrupted PEBs; VID offset
2048, data offset 4096 and LEB size 126976 match the intended layout. The dynamic
test volume has 104 LEBs after reservations. UBIFS mounted with `compr=none`.
Thirty-two rewrites of sixteen 256 KiB payloads exercised erase/reuse, reaching
maximum erase counter 17. Final file hashes match independently generated host
hashes. Permissions, uid/gid, hard links, symlinks, renames and user xattrs pass;
OverlayFS copy-up and deletion/rename whiteouts also pass. The volume was
cleanly unmounted and detached before the next read-only physical check.

The partition ECC counter reports 15 corrected bits and zero uncorrectable
errors during that workload. Micron's status reports ranges, and the pinned
driver adds their upper bound (3, 6 or 8), so this is not an exact physical bit
count. The later U cold boot uses fully read-only flash and disables the
diagnostic core option. Two complete corrected captures are identical, SHA256
`68ea929fcaeb02f1426f669f1a5ff03df23eb956c45ec5befdfeb98fea5cc11a`.
Their data+OOB before and after the test window match the pre-test backup.
The raw capture is byte-identical to the corrected capture inside the window;
its differences are confined to older flash contents. A repeat dump with
per-request ECC locations records zero correction events in the test window
and 60 outside it, all in preserved regions. Aggregate partition counters do
not locate individual corrections; the core derives them from shared master
statistics around each operation.

Returning to the unchanged T image after the U cold boot and software-restart
test reattaches the same UBI image sequence and UBIFS UUID. All sixteen files
still match the independent host hashes. Mode, uid/gid, hard links, symlinks,
renames, user xattrs and overlay whiteouts all survive. Cold attachment reports
zero bad/corrupted PEBs, maximum/mean erase counts 17/11. Private
`logs/native-ubi-qualification.json` indexes the provenance. Unclean-power-loss
recovery, normal OpenWrt overlay integration and owner-configuration migration
remain unfinished.

## 2026-11-11: native SPI-NAND read-only qualification

Candidate N uses Linux's Micron SPI-NAND implementation: 128 MiB SLC,
2048-byte pages, **128-byte OOB**, ECC strength 8 per 512 bytes and bitflip
threshold 6. It mounts the existing rootfs at about four seconds of kernel
uptime. Factory Ethernet addresses are preserved. The SPI clock provider owns
the verified divider/gate fields while retaining the boot PLL/source profile;
its modeled working clock is 50 MHz, not a direct SCK measurement.

The transport advertises the write templates needed for core discovery but
rejects WREN, LOAD, UPDATE, PROGRAM EXECUTE and ERASE before MMIO. A local core
extension honors flash-level `read-only`, skips automatic block unlocking and
clears master `MTD_WRITEABLE` before partition registration. Boot verification
checks all thirteen MTD devices and native geometry. All partitions are
read-only in the default image; general writable promotion is not implemented.

The known page-6947 normal/raw data hashes match the earlier references, and
full 128-byte OOB reads work. Complete rootfs, stock kernel and header reads
also match their independently verified hashes. Two complete ECC-corrected
physical captures, including OOB, are byte-identical:

```text
format: 65536 records, each 2048 data bytes followed by 128 OOB bytes
bytes: 142606336
SHA256: 525fda3e8fbb82f90064f986c3fe9672f24d4a1af1094f1970f65f4ed25edd32
```

Two raw captures differ by one data bit each on pages 16497 and 19564. Three
corrected reads of each page match the verified stock image; their ECC reports
vary between zero and the 3-bit bound. Raw OOB is stable between those captures.
The corrected view also repairs two parity-area OOB bits. Preserve the mode
metadata: raw snapshots and corrected captures are distinct evidence.

The bootloader's old raw SHA `cc520f18…` is preserved, but native ECC corrects
one bit at physical offset `0x5a73b` (XOR `0x08`). A separate corrected read
matches SHA `2fe63ecb06700d6cf326bd57790b2b03fe8bd9df25834153a0c1836fa3d72ada`.
Factory tag and WiFi data match the existing backups. These are read results;
the bootloader and bank B have not been rewritten.

The verified dump contains existing data in `rootfs_data` and the first four
staging blocks. Do not treat either entire partition as blank. The sampled
first/second/last-page marker bytes are all `ffff`; transport failures must
still be distinguished from physical bad-block evidence. The native core's
bad-block query does not propagate every transport error.

`tools/nand-dump.c` streams raw or corrected pages read-only, rejects short or
uncorrectable reads, and keeps binary data on stdout with diagnostics on
stderr. Private dumps and `logs/native-full-backup-verification.json` retain
the complete provenance. Write/erase qualification, configuration preservation,
normal userspace startup and upgrades remain unfinished.

## 2026-11-11: PAGE READ preparation restored

Removing the frequent PL310 outer-sync callback in candidate K exposed a NAND
scan timeout before rootfs mount. Stock Linux `page_read_to_cache` and own-unit
U-Boot both prepare PAGE13 with `INIT |= 0x1c440` and an interrupt clear at
offset `0x30` before triggering. The old driver omitted both steps on its
initial and repeated PAGE READ paths. Candidate L restores the shared helper
and records the first polling failure from cached command/page/FIFO-position
metadata and the poll's last value, without extra MMIO or FIFO reads.

With the prior J cache policy retained, L passed startup, the known page-6947
raw/corrected comparison, the complete 13,762,560-byte rootfs hash and the
3 MiB stock bank-B kernel hash. A 13.7 MB wired download and upload also matched
exactly. NAND transport retry, mismatch, recovery and failure counters remained
zero. OIP was missed on many completed commands, exercising the existing
read-reissue heuristic; its count is not a transport-failure count.

Other command preparation still contains assumptions under investigation,
including STATUS acknowledgments and the old `0x10440`/`0x100020` writes.
M subsequently passed the same corrected rootfs and raw/corrected page checks
with coherent PL310 mode enabled, plus wired integrity and a concurrent WiFi
and NAND-read workload. See [the platform comparison](../BRINGUP.md#2026-11-11-coherent-pl310-mode-passes-the-cpu1-control).
The native SPI-NAND conversion remains required.

## Native architecture and remaining production work

The earlier read-only ECC experiments validate existing native parity. Linux
6.6 already supports this exact Micron SPI-NAND: 2048-byte pages, **128-byte
OOB**, 128 KiB erase blocks and native ECC strength 8 per 512 bytes. A SPI-mem
controller now exposes the read-only transport to that core, including all three ID
discovery shapes, 2176-byte cache transfers, nonzero OOB columns and update-cache
opcode `84` as a supported template. Keep the controller's array-write denial during read qualification;
do not silently reset the chip behind SPI-NAND's cached feature configuration.

Verified stock code identifies these clock fields:

| Function | Register and field |
| --- | --- |
| LSP0 100 MHz working-clock parent gate | `94000014`, bit 13 |
| LSP0 APB parent gate | `94000014`, bit 11 |
| SPI divider | `94400018`, bits 16:11, divisor = field + 1 |
| SPI working/peripheral gates | `94400018`, bits 1 / 0 |

Own U-Boot sets divider field 1, yielding a **modeled 50 MHz working clock**;
the SCK relationship is not directly measured. Its source selection at
`9400000c[21:20] = 1` remains unidentified. Preserve that selection and unrelated
register bits initially; do not invent reset lines or advertise arbitrary SPI
rates. The stock SPI probe enables its working clock but requests no external
reset. The function named `spifc_clear_fifo` ORs `1c440` into controller INIT,
whose bit 16 separately controls clock pause.

Native read-only boot, full-OOB/raw/ECC checks, corrected component checksums
and concurrent traffic precede writable promotion. Existing overlay format,
backup/migration, partial-program constraints and upgrade/recovery behavior
still need explicit qualification. The only array modifications during this
goal's diagnostic work are the completed block-799 test above.

## 2026-11-10: bootloader ECC assumptions retracted

The own-unit bootloader's **normal path enables on-die ECC**. The older claims
below that U-Boot always writes raw, and that enabling ECC necessarily requires
rewriting the entire chip, are not supported by the actual bootloader code.
Linux currently disables ECC for PAGE READ, then sets it again for cache reads;
its write path does not explicitly select the ECC mode. Fixing those state
transitions and measuring raw versus corrected reads precedes any migration.

Read-only disassembly used a freshly copied bootloader with SHA256
`cc520f1845c393676122dd85472c73ae046c2a46807909b7bbeeb6ad8ab8fecb`.
Addresses are unrelocated; subtract `0x47edf800` for file offsets:

- SET FEATURE helper `0x47f1e9ac` uses opcode `0x1f`; GET FEATURE helper
  `0x47f1ea00` uses `0x0f`.
- Initialization reaches `0x47f1f290` via `0x47f1f388`, and at
  `0x47f1f35c..0x47f1f364` writes **B0 = 0x18**, including ECC_EN bit 4.
- Page reader `0x47f1f04c` clears ECC only when global `0x47f57e28` is set.
  That flag starts zero in BSS and is set by the diagnostic `ecc off` command.
  Its branch also reads 2176 bytes, prints 128 OOB bytes and restores ECC.
- Program callbacks `0x47f1eee4` and `0x47f1ee58` preserve the enabled mode.

Live evidence: the bootloader verified the complete 0xd20000-byte rootfs with
CRC32 `0x3d20317e` (complement `0xc2dfce81`), matching the saved R206 artifact.
A later Linux raw dump differs by one bit at absolute page 6947, byte 509:
`0xf7` instead of `0xd7`. Eight repeated reads with a neighboring-page eviction
returned the same changed page. The driver's persistent cache makes repeats
without eviction insufficient evidence of independent array reads.

This supports testing whether U-Boot corrects a bit Linux reads raw; it does
not yet prove a media fault or that every page has valid on-die parity. The
full 128 MiB data dump also disagreed with a separate whole-device checksum
and remains marked unverified. Bootloader, header, tag and WiFi partitions
were independently transferred and matched their on-device checksums.

The next RAM-only experiment must preserve raw bad-block/OOB access and test
normal corrected reads in a bounded region, initially rootfs. Controller timing
and cache-transfer settings must remain fixed during that comparison.

Source review also found unchecked feature/status errors, a read-reissue loop
that can fall through without readiness, the wrong erase-failure bit, aliased
write-verification scratch storage, and health work surviving failed probe.
These source defects have been corrected and covered by host fault-injection
checks. Write-path fixes remain unqualified on hardware. Existing BCH staging
results below are not proof of a complete ECC/upgrade integration.

### First RAM result: existing native parity recovers the original rootfs

The read-only candidate `h199a-ecc-probe-a` booted through TFTP into RAM with
`zx_spifc_nand.ondie_probe=1`. Runtime reported the parameter as `Y` and both
master/rootfs MTD flags as `0x0`. No array writes were performed.

`MEMREAD` with data and OOB buffers produced these results for page 6947:

| Mode | Byte 509 | SHA256 of the 2048-byte page | ECC result |
|---|---|---|---|
| Normal, corrected | `d7` | `cae4a5320c889685c7e2e631c7fa1d4503f08bfd063b3abf55b7923a5d2ec5bf` | corrected; bound 3 bits, no failure |
| Raw | `f7` | `61253f7fdfc82088b370c2e16b56efefc4af023c86dcff811710f79f779d60cd` | correction bypassed |

The normal page equals the saved R206 page. The corrected whole rootfs SHA256 is
`633fe4d4e8c4f12dfd8e40c8769cf8b4faca96b95bd0fcdd092e1b3e1f40db75`, also exactly
matching R206. The full read reported no uncorrectable errors. The status value
3 is the Micron encoding's upper bound; the reference comparison shows one
changed bit in this page.

Image SHA256: `d340aa076a8b1da451af66cef69be2539b5c3cddb01f73c8886b895d7e577b88`.
This is one independent RAM boot and a bounded rootfs-read experiment. It does
not yet qualify corrected reads for every partition, writes, upgrades or the
final production ECC architecture. The earlier raw full-flash dump stays
unverified. Write/erase readiness now aborts on status errors and detected
controller resets; a writable candidate still requires separate qualification.

### Concurrent traffic exposed two SPI sequence defects

Candidate B repeated the exact corrected-rootfs checksum, then routed TCP at
100 Mbit/s in both directions. Listing module files during that traffic caused
two transport failures and cached SquashFS metadata errors at rootfs offsets
`0x4e34ce` and `0x4e3cf4`. ECC failure counters remained zero. The affected
128 KiB region (`0x4e0000..0x500000`) subsequently matched its reference in
three idle MTD character reads; repeated filesystem errors alone are therefore
not fresh media-error evidence.

The own-unit bootloader establishes two sequence corrections:

- Cache read: `0x47f1f120` triggers, `0x47f1f12c` drains FIFO, then
  `0x47f1f130` polls DONE. Linux had waited for DONE before draining its finite
  FIFO.
- SET FEATURE at `0x47f1e9ac`: setup, one trigger, FIFO write, DONE. Linux
  triggered once, fed data, then called a finish helper that triggered again.

Both sequences are now corrected with register values and sleepable polling
policy preserved. Actual-C regressions fail with the old sequence and pass with
the correction. Candidate C then completed a 60-second routed TCP test at
99.994 Mbit/s while listing modules, hashing firmware and reading the entire
corrected rootfs. All hashes matched; retries, wedges and transport/ECC failures
remained zero. This does not establish an IRQ-latency explanation: the NAND
diagnostic IRQ count was also zero during B's observed failure.

### Read-only recovery beyond bank A's rootfs

`NAND_ONDIE_PROBE_ALL=1` requires `NAND_ONDIE_PROBE=1` and the diagnostic boot
profile. It adds the boot-only `zx_spifc_nand.ondie_probe_all=1`, extending normal
ECC reads across the array. Raw page reads and both OOB callbacks remain raw;
`NAND_ROM`, cleared write flags, denied write callbacks and program/erase guards
remain in force. The driver rejects an all-region request without the read-only
probe mode before hardware initialization. This remains a diagnostic interface,
not the permanent SPI-NAND architecture.

`tools/nand-read-range.c` opens MTD read-only and uses `MEMREAD` statistics. It
accepts corrected data (`EUCLEAN`) but rejects `EBADMSG`, nonzero uncorrectable
counts, transport errors and short reads. It publishes a new RAM filename only
after the complete range is saved. Ordinary `read()`/`dd` can return bytes even
for an uncorrectable MTD error and cannot certify a dump alone.

Bank B's own header at `0x03020000` declares a filesystem length of `0x00d20000`,
CRC32 `0x7bc2f9e9`. The current `rootfs2` partition is 128 KiB shorter, so recovery
must read the master range `[0x02300000,0x03020000)`. Kernel B occupies
`[0x02000000,0x02300000)`. Check ECC statistics, exact sizes, uImage/gzip CRCs,
the filesystem CRC and the header self-CRC before using recovered files.
Array-wide correction may expose raw/no-parity regions; do not silently replace
failed corrected reads with raw data or describe a partial dump as verified.

Candidate D recovered all three bank-B components with zero uncorrectable
errors. Kernel/rootfs/header corrected-bit upper bounds were 27/153/0. Host
copies matched target SHA256, and all independent checks passed:

| Component | Verified check |
|---|---|
| Kernel area | CRC32 `107dd7f0`, matching bank header |
| uImage header / payload | CRC32 `27ed3175` / `b4ac6149` |
| Kernel gzip | Complete 6,087,328-byte output, valid gzip CRC |
| Full filesystem | CRC32 `7bc2f9e9` |
| Firmware header | Self-CRC32 `5614517e` |

Corrected kernel/rootfs/header SHA256 values are respectively
`da53645b7f312941d30bc5d852a864e510b8dff35dfc0ff560a37d54b8d319a1`,
`dd8c7c61c6056c481726f1417fdd02ca69104572997a7857b483f18049033712`, and
`e5cd84b78b1faac0d7f8119f65b3f2ab4a52bf057f4f7a53b9db39f5b7463b6b`.
This establishes these component backups; it does not retroactively verify the
earlier raw whole-flash dump. No flash writes were used. The verified stock
kernel also enabled [offline calibration extraction](WIFI-BRINGUP.md#original-base-recovered-and-merged).

## Hardware

- ZTE **spifc** SPI-NAND controller, compatible `zte,ZX279127-spifc`, registers
  at `0x94406000`.
- Micron **MT29F1G01ABAFDWB**, SLC, 128 MiB: 2048 B page, 128 KiB erase, 1024
  blocks × 64 pages. MTD sees a 64 B OOB.
- The `denali,denali-nand-dt` node at `0xd80000` in the stock DTB is **not** the
  controller — it is a data window that hangs on access before spifc is set up.

## What the driver does

- Reads byte-exact against a reference dump of the device. **This was verified
  during bring-up against a July NAND dump not shipped in this repo, so the check
  is historical and not reproducible from a clean clone.** What a reader can
  reproduce today is self-consistency (`md5sum /dev/mtd<n>` against the flashed
  artifact - see "How to verify"), which proves the read path is stable, not that
  it matches the original dump.
- `nand_scan` identifies the chip; MTD partitions register.
- Erase, and program with read-back verification and retry.
- In-memory bad-block table from factory markers, rebuilt each boot.
- Forces 1 bit/cell when the chip reports otherwise, so JFFS2 will mount.
- Requires the chip's **busy phase to be observed** before believing an
  operation finished, on both the read and the erase/program paths.

## ⚠️ There is NO error correction

The chip's on-die ECC (8 bits per 512 B) is **deliberately disabled** and nothing
replaces it — no controller ECC, no software ECC. Every bit flip is silent.

This cannot be fixed from Linux alone: **U-Boot's own spifc driver also programs
with ECC disabled**, so everything already on the flash was written raw. Enabling
on-die ECC makes `nand_scan` fail, because existing pages carry no parity.

There is also **no persistent bad-block table**: a block that fails a program is
retried rather than retired.

What that exposes:

- **JFFS2 overlay** — detects corruption (three CRC32s per node) but *discards*
  bad nodes at mount. Because JFFS2 is log-structured, dropping a newer node
  makes older data silently reappear: a setting reverts rather than erroring.
- **squashfs rootfs** — the real exposure. Constantly read, never erased, so read
  disturb accumulates with nothing to reset it, and it has no CRC layer.

**Treat configuration on this device as expendable.**

## Verify every write

`bytes written: OK` means the controller accepted the data. It does **not** mean
a later read returns it, and with no ECC nothing underneath will tell you. Three
partitions in one session were written "successfully" with wrong contents.

From U-Boot (which has no `crc32` command):

```
=> nand write 0x42000000 <off> <len>
=> nand read  0x44000000 <off> <len>
=> cmp.b 0x42000000 0x44000000 <len>
   # REQUIRED: "Total of <len> byte(s) were the same"
```

A smaller total is the **offset of the first difference**, not a count of
matching bytes — `cmp.b` stops at the first mismatch.

Measured on hardware: **22% of erase/program waits never observe the busy phase**
(`nobusyw=128/582`). The driver therefore fails an erase loudly when it never saw
busy, and relies on read-back verification for programs.

## Partition layout

| Label | Offset | Size |
|---|---|---|
| `bootloader` | `0x0000000` | 1 MiB |
| `tag` | `0x0100000` | 1 MiB — per-unit serial, SSID, Wi-Fi key |
| `wifi` | `0x0200000` | 1 MiB — calibration at `+0x20000` |
| `usercfg` | `0x0300000` | 2 MiB |
| `defcfg` | `0x0500000` | 2 MiB |
| `kernel1` | `0x0700000` | 3 MiB — bank A |
| `rootfs` | `0x0a00000` | 13.125 MiB — bank A |
| `header` | `0x1720000` | 128 KiB — bank A CRCs |
| `kernel2` | `0x2000000` | 3 MiB — bank B, stock |
| `rootfs2` | `0x2300000` | 13 MiB — bank B, stock |
| `rootfs_data` | `0x4000000` | 16 MiB — JFFS2 overlay |
| `staging` | `0x5000000` | 20 MiB — sysupgrade images |

**Never hardcode `/dev/mtdN`.** Runtime numbering is DT index + 1 (a master device
occupies mtd0) and has already shifted once when `header` was added:

```sh
R=/dev/$(sed -n 's/^\(mtd[0-9]*\):.*"rootfs"/\1/p' /proc/mtd)
```

`0x03000000-0x04000000` is **not free** — it holds vendor data on the author's
unit. `0x05000000` onward was erased there, which is why `staging` lives at that
offset; verify it on your own device before erasing.

## How to verify

```sh
cat /proc/mtd                      # expect 14 lines (master + 12 partitions + header line)
md5sum /dev/mtd<n>                 # compare against the flashed artifact
cat /etc/<marker> ; reboot         # config persists from the SECOND boot onward
dmesg | grep 'zx-spifc HEALTH'     # retry/mismatch/nobusyw counters
```

## Open questions

- On-die ECC and a persistent BBT — see the warning above for why both are hard.
- `ecc.strength = 8` / `ecc.size = 1024` are cosmetic under
  `NAND_ECC_ENGINE_TYPE_NONE`, and the die actually uses 512-byte ECC steps.
- The U-Boot-side write failures of rounds 189–191 remain **unexplained**; the
  mitigation is `cmp.b`, not any change in this driver.

## Runtime read errors are real and intermittent (the no-ECC cost, measured)

Round 227 soak: one boot in a short run showed 8 SQUASHFS errors during runtime:

```
SQUASHFS error: xz decompression failed, data probably corrupt
SQUASHFS error: Failed to read block 0x462ec2: -5    (-EIO)
SQUASHFS error: Unable to read inode 0x68e0515
```

with the driver's own HEALTH line reporting `mismatch=13` (reads that differed
on retry). This is the no-ECC limitation manifesting: a rootfs block reads back
with bit errors the driver cannot correct, its read-retry sometimes does not
recover it, and SQUASHFS then fails to decompress the block.

It is **intermittent** - the next boot in the same run showed `mismatch=0` and 0
SQUASHFS errors - and it is exactly what "no ECC, no bad-block retirement"
predicts. The round-57 observation of SQUASHFS errors was therefore real, not an
artifact; the round-194 clean boot was simply a boot that read cleanly. Both are
consistent with a marginal block that reads correctly most of the time.

The soak's PLATFORM verdict counts any SQUASHFS error as a failure, so this
lowers the honest platform reliability below 100%: the device usually boots
cleanly but occasionally hits an uncorrectable rootfs read. Treat this as a
property of the hardware choice (the vendor disabled on-die ECC and U-Boot writes
raw), not a driver bug - though a driver-side software ECC or a read-verify-retry
with more attempts could reduce its frequency, and is the one open mitigation.

## Intermittent boot hang at mt76 firmware load (round 228)

On one power cycle the boot reached the mt76 Wi-Fi firmware load and hung there
with no further console output and no network:

```
mt7615e 0000:01:00.0: mediatek/mt7663pr2h.bin not found, switching to mediatek/mt7663pr2h_rebb.bin
mt7615e 0000:01:00.0: HW/SW Version: 0x65322d31, Build Time: ...
<console goes silent, device never reaches a usable state>
```

The next clean power cycle booted normally. This is very likely the same no-ECC
read-reliability issue as the SQUASHFS errors: `mt7663pr2h_rebb.bin` is read from
the SQUASHFS rootfs, and an uncorrectable read error during firmware load would
stall the mt76 driver. It is intermittent and recovered by a power cycle. It is
recorded here rather than under Wi-Fi because the root cause is the storage read
path, not mt76.

**Round 249 - the three "reproductions" are RETRACTED; cause not established.**
Three consecutive cold boots stopped at `mt7615e ... HW/SW Version` (~70 s
uptime), console then silent, no network. Two explanations were proposed and both
were discarded:

1. *Flash degradation / a worsening uncorrectable read* - not supported; nothing
   distinguished these boots from the hundreds that read the same firmware fine.
2. *A power-delivery fault* - proposed because the `tomada` meter read
   **0 mA / 0.0 W** with the outlet ON. **That evidence is void:** the same meter
   reports `0 mA / 0.0 W` for a device verified pinging at 0% loss with `rig OK`
   on all seven checks. It cannot distinguish a powered device from an unpowered
   one.

What is actually established: the device recovered after a **longer power-off**
(20-30 s versus the usual 8-12 s), booting past mt76 firmware load to a shell
with `eth0` link up and 0% ping loss. Why a longer cold period helped is NOT
known, and this note deliberately does not invent a mechanism.

**Consequence for the earlier finding:** the round-245 "2nd observation" had this
same signature and may have been the same unexplained transient. The mt76-hang
finding is therefore downgraded to a **single unconfirmed observation (round 228)
whose cause is not established** - not the "recurring intermittent fault" that
round 245 recorded.

**Practical rule:** if the device stops at the mt76 firmware line on consecutive
boots, power it off for 20-30 s rather than retrying short cycles.

Two lessons, both ones this project keeps relearning:
* **A symptom matching a documented defect's shape is not evidence for that
  defect.** Twice here a narrative was extended onto a matching signature.
* **The `tomada` wattage/current reading is unreliable.** It reported
  `0 mA / 0.0 W` on the very boot that succeeded and answered the network - i.e.
  0 W on a device provably drawing power. Treat it as a coarse on/off indicator
  only; **UART log growth is the authoritative "has power / is alive" signal.**
* A symptom matching a documented defect's shape is not evidence for that defect.
  The three "hangs" were a transient boot/power condition, not media wear.

The mt76-hang finding is therefore **downgraded to a single unconfirmed round-228
observation with cause not established**, and the round-245 "reproduction" (same
signature, recovered by a power cycle) is retracted as probably the same
transient condition. Standard practice going forward: use a longer power-off, and
trust the UART log, not the meter. The Wi-Fi AP evidence in `WIFI.md` was captured
on healthy boots and is unaffected.

## Why the read-retry cannot fix the SQUASHFS errors (round 230)

The driver already reads every page TWICE with a cache-eviction read in between,
and retries on any disagreement (`zx_spifc_read_page_raw`). This is very
effective against the controller's *transient* corruption: across a session the
HEALTH counters show `fail=0` on 2315 of 2318 lines - the read path almost never
exhausts its retries.

Yet SQUASHFS still errors. The reason is a DIFFERENT failure mode the retry
cannot catch: a **stable media bit-flip**. If a flash cell has actually flipped,
both reads return the *same* wrong value, they agree, and the driver reports
success with corrupt data - which SQUASHFS then fails to decompress. The
read-twice-compare only catches corruption that DIFFERS between two reads
(controller glitches), not bit errors that are stable in the array.

This is why more retries would not help, and why ECC is the only fix for this
class: only ECC can correct a bit that is genuinely wrong in the media. It also
explains the otherwise-puzzling pair "SQUASHFS error but `fail=0`".

## On-die ECC for the rootfs: NOT VIABLE (audited round 231)

An earlier note proposed writing the rootfs with on-die ECC and reading it with
ECC enabled, on the premise that "the rootfs is read only by our kernel, never by
the bootloader." **That premise is false, and the plan does not work.** Verified:

* **The bootloader CRC32s the ENTIRE rootfs partition on every boot.**
  `tools/flash-prep.py` computes `zlib.crc32` over the whole 13.125 MiB rootfs and
  stores it at header `+0x48`; the bootloader's `zteboot_verify_fs` recomputes it
  and rejects the bank on mismatch (`verify fs success!!` on good boots;
  `Romfs CRC check failed ... booted stock` observed in round 190). An
  ECC-written rootfs changes those bytes, so bank A would be rejected and the
  device would fall back to stock - guaranteed, on the first boot.
* **The driver structurally cannot touch the parity area.** Every transfer is
  hardcoded to 2112 bytes (2048 data + 64 OOB); on-die ECC parity lives in OOB
  bytes 64..127, which the driver never reads or writes. It could neither store
  nor verify the parity.
* **ECC_EN is a global chip feature** (0xB0 bit 4), and the driver's
  `spifc_set_feature` return values are ignored - a single dropped feature write
  would leave the chip in the wrong ECC mode for whatever partition is read next,
  including the kernel and header.

So on-die ECC is not a "risky" mitigation - it is not viable. The correct
mitigations are read-path and image-layout changes with no flash-layout risk;
see below.

## The viable reliability mitigations (ranked, round 231)

The failure is a stable media bit-flip that the read-twice-compare cannot catch
(both reads agree on the wrong value). Ranked by reliability gain / brick risk:

1. **Split `-EBADMSG` from `-ETIMEDOUT` in the retry accounting** (done this
   round). Until now the driver could not tell controller flakiness from genuine
   bit rot - both were counted the same. This is the prerequisite for choosing
   any further mitigation intelligently. Zero flash-write risk.
2. **Sweep `SPIFC_READ_RETRIES`** (currently 12) - CONSIDERED AND REJECTED
   (round 232). The retry loop only catches TRANSIENT controller corruption (two
   reads disagree). The HEALTH counters already show `fail=0` on 2315 of 2318
   lines, so 12 retries almost never exhaust - more would not help the cases that
   already succeed, and cannot touch stable bit rot (which produces no mismatch
   and no fail, only a downstream SQUASHFS error). Zero expected benefit.
3. **Move the mt76 firmware out of squashfs** - CONSIDERED AND REJECTED
   (round 232). It would reduce a bit error's blast radius (one flipped bit vs a
   whole xz block) but not eliminate it: the raw firmware is still read from the
   same ECC-less NAND and mt76's own integrity check would fail on a corrupted
   image just the same. Marginal gain against real build-layout risk, and it does
   not touch the SQUASHFS class at all.
4. **Software BCH/Hamming in the MTD layer** is the only *correct* long-term fix,
   but it is a multi-round project and must first confirm whether the bootloader
   CRCs only the 2048-byte data stream (so parity in OOB would not break the
   header CRC). Not for the rounds remaining.

## ★★★ 2026-09-07 — the blocking question for software BCH is ANSWERED: OOB is free

Item 4 above has been gated for many rounds on one unanswered question: does the
bootloader's CRC cover only the 2048-byte data area of each page, or the full
2112-byte page including OOB? **It covers the data stream only. OOB is not
CRC'd, so software BCH parity can live there without breaking the bootloader.**

Established from `h199a-firmware/mtd0-bootloader.bin` (plaintext ARM; U-Boot
proper starts at file offset `0x20800`, links at `0x47f00000`), by two
independent routes.

**Empirical, and decisive.** The full flash dump `h199a-flash-full.bin` is
134,217,728 bytes = 65536 × 2048 exactly - a *data-only* image with no OOB
interleaved. All three CRC32s stored in the stock header reproduce from it
byte-for-byte with `zlib.crc32`:

| header field | stored | computed over the data-only dump |
|---|---|---|
| `+0x3c` kernel | `0x107dd7f0` | `flash[0x700020 : +0x2ffdcc]` — match |
| `+0x48` rootfs | `0x7bc2f9e9` | `flash[0xa00000 : +0xd20000]` — match |
| `+0xa4` header self | `0x5614517e` | `hdr[0 : 0xa4]` — match |

The rootfs CRC alone spans 6720 pages. If OOB bytes were part of the CRC'd
stream, a pure-data image could not reproduce it.

**Static.** `nand_read_skip_bad_` (`0x47f114bc`) calls `nand_read`
(`0x47f1c444`), which sets `ops.datbuf = buf` and **`ops.oobbuf = NULL`** before
`nand_do_read_ops`; the stock read path then copies `writesize` (2048) bytes per
page into the caller's buffer and skips the OOB memcpy entirely. `csp_crc`
(`0x47f16884`) walks that contiguous buffer. It is standard CRC-32/IEEE
(poly `0x04C11DB7` reflected, init `0xFFFFFFFF`, final complement) — identical
to `zlib.crc32`, which is why the reproductions above work.

### The constraints software BCH must respect

* **OOB byte 0 (page byte 2048) must stay `0xFF`.** It is the bad-block marker.
  `nand_read_skip_bad_` calls `block_isbad` before every erase block, and a
  block that looks bad is skipped **without advancing the destination pointer** —
  so one false marker shifts the entire remaining data stream and guarantees a
  CRC failure and a fallback to the stock bank. The chip driver leaves
  `chip->block_bad` unset, so the stock large-page default
  (`NAND_LARGE_BADBLOCK_POS` = 0) applies; `spifc_default_block_markbad`
  (`0x47f1e554`) confirms the position by zeroing byte 0 of the OOB it writes.
* Keep byte 1 reserved too, as this tree's `ooblayout_free` already does.
* That leaves **OOB[2..63] = 62 bytes**. BCH-8 over 512-byte steps needs
  4 × 13 = **52 bytes**. It fits, with room to spare.

### Two further facts worth having

* The CRC'd lengths come **from the header, not from the partition size**:
  kernel is `csp_crc(base + 0x234, hdr[0x34])` compared against `hdr[0x3c]`;
  rootfs is `csp_crc(base + hdr[0x44], hdr[0x40])` against `hdr[0x48]`. The
  bootloader also asserts `total == hdr[0x40] + hdr[0x44]`, which is exactly why
  `tools/flash-prep.py` warns not to change the fs size. Note the last `0x214`
  bytes of `kernel1` are not covered by any CRC.
* `zteboot_verify_signature` (`0x47f1249c`) is a **stub** — it prints and
  returns 0. There is no signature check to satisfy.

### The bench test to run before touching bank A

Prove the layout constraint on real silicon rather than on inference. In the
`staging` region, write one page with data plus non-`0xFF` OOB bytes 2..63 and
`0xFF` at bytes 0..1, then from U-Boot `nand read` the data area and `cmp.b`
against what was written: the data must be identical and no "Skipping bad block"
may appear. Repeat with OOB byte 0 set to `0x00` and confirm the block *is*
skipped. That pins both halves of the constraint before any of it is applied to
`kernel1` or `rootfs`.

**Item 4 is therefore no longer blocked.** It is a real project rather than an
open question, and the sequencing is: prove the layout on `staging`, apply BCH
to `rootfs_data` first (the overlay the bootloader never reads, and the
partition that takes every configuration write), then extend to `rootfs` and
`kernel1` with a whole-device rewrite, keeping bank B untouched throughout.

## 2026-09-07 — software BCH is IMPLEMENTED (Phase 7.2), off by default

The engine from the section above now exists in `zx_spifc_nand.c`. It is gated
behind `zx_spifc_nand.bch=1` on the kernel command line and does nothing at all
when off, so it ships inert until the bench test below has been run.

### Where the parity lives, and why not the obvious place

| bytes | contents |
|---|---|
| page `[0 .. 2047]` | data — the only thing the bootloader CRCs |
| OOB `[0]` | manufacturer bad-block marker, must stay `0xFF` |
| OOB `[1]` | reserved margin (unchanged from before) |
| OOB `[2 .. 11]` | free — JFFS2 cleanmarkers |
| OOB `[12 .. 63]` | **BCH parity**, 4 steps × 13 bytes |

BCH-8 over 512-byte steps: `m = 13` is the smallest field with `2^m − 1 > 512×8`,
so each step costs `⌈13×8/8⌉ = 13` bytes and the page costs 52. That is the
configuration the section above budgeted for, and it corrects up to 8 bits per
512 bytes — 32 bits per page.

Parity sits at the **end** of the OOB rather than at byte 2 so that the free
region keeps the offset it has always had. Ten free bytes is enough for JFFS2,
which clamps its cleanmarker to `min(oobavail, OOB_CM_SIZE)` and `OOB_CM_SIZE`
is 8.

### NAND core integration (corrected 2026-09-08)

The initial implementation used `NAND_ECC_ENGINE_TYPE_NONE` and corrected data
inside `exec_op`. Review against the pinned NAND core found three problems:
the core overwrote ECC strength with zero, raw MTD operations also applied BCH,
and returning `-EBADMSG` from `exec_op` could stop the core before it copied a
partial page or OOB to the caller.

The revised implementation uses controller-managed host ECC with full-page
callbacks, backed by Linux's BCH library. Normal reads correct the caller's
buffer and return the largest per-step bitflip count. Failed steps increment
`ecc_stats.failed`, letting the core return the available data and `-EBADMSG`.
Raw reads, raw writes, bad-block scans and the driver's internal page cache
remain raw. Normal protected writes generate parity in `chip->oob_poi` before
the existing full-page transfer; parity verification failures now fail those
writes. This integration still requires the on-device tests below.

Three details that are load-bearing:

* **Decode does NOT happen inside `zx_spifc_read_page_raw()`**, even though that
  is the tidier-looking place. The write path verifies its own programs through
  that function, and correcting there would let a program that landed one bit
  wrong pass verification — hiding exactly the marginal cell the ECC exists to
  find.
* **An uncorrectable read still returns available data**, with `-EBADMSG`
  alongside. Correctable steps are corrected even when another step fails.
  Bad-block scans use raw OOB and do not interpret absent parity as a bad block.
* **The erased-page mask does double duty.** Parity is XORed with the inverted
  parity of an all-`0xFF` step, the standard trick that makes an erased page a
  valid codeword. Here it also means an all-`0xFF` data area encodes to
  all-`0xFF` parity, which is a no-op on flash — so JFFS2's post-erase
  cleanmarker (an OOB-only write, which arrives with the data area memset to
  `0xFF`) cannot damage the parity that a later data write puts in the same
  page. No special case is needed for it, but the property is what makes that
  true, and changing the mask would break it silently.

### Turning it on requires erasing the range

Pages written before the switch carry no parity and can decode as
uncorrectable. A kernel without BCH can read subsequently written data but
cannot correct it, and its writes do not maintain parity. The parameter is
read-only (`0444`) — the decision belongs to the boot,
not to a later sysfs write — and the transition is:

```
# kernel command line
zx_spifc_nand.bch=1
# first boot, before the overlay is trusted
mtd erase rootfs_data
```

Default range is `rootfs_data` (`0x4000000`, 16 MiB → pages 32768..40960),
overridable with `bch_first` / `bch_pages`. `bch_pages=0` means "to the end of
the device", which is what extending to `rootfs`/`kernel1` will use once the
whole device is rewritten — the boot CRCs cover only the data area, so parity in
OOB[12..63] is invisible to the bootloader either way.

### What to measure

The 60 s `HEALTH` print gains a second line when the engine is on:

```
zx-spifc BCH: corrected=N bits=N worst=N uncorrectable=N range=[32768,40960)
```

`corrected` moving off zero is the first **direct** evidence this device rots at
all. Every existing counter is blind to a stable media bit-flip: both verify
reads agree on the wrong value, so it produces neither `-EBADMSG` (on-die ECC is
off) nor a `mismatch`, and surfaces only downstream as a SquashFS error. This is
the counter that closes that gap. Corrections are also added to
`mtd->ecc_stats`, so `/sys/class/mtd/mtdN/corrected_bits` and `ecc_failures`
become meaningful.

### Still to do before this is finished

* Run the bench test from the previous section on `staging` — the layout
  constraint is still inference, not silicon.
* Boot with `bch=1`, erase `rootfs_data`, confirm the overlay formats, mounts,
  survives a power cycle, and that `uncorrectable` stays 0.
* Deliberately corrupt a byte in a `rootfs_data` page from U-Boot and confirm
  `corrected` moves and the data reads back right. Without this the engine is
  untested in the only case it exists for.
* Only then: Phase 7.3, the whole-device rewrite. Bank B stays untouched.

`tools/nand-oob-probe.c` implements the first layout check. It accepts only a
`staging` MTD character device and an aligned block offset, checks the entire
block's data and OOB are erased, programs one page with distinct data and
OOB[12..63] patterns, and checks three cache-evicted reads. On success it erases
and verifies the block again. On a mismatch it leaves the test block intact for
inspection. With `--bch`, it also writes a separate page through normal MTD,
clears eight data bits through raw MTD while preserving parity, requires a
corrected read to reproduce the original bytes and report eight corrected bits,
and confirms a subsequent raw read still sees the damaged bytes. BCH must
already be enabled for that block; the tool does not change its configuration.

The final staging block is partition offset `0x13e0000`, physical offset
`0x63e0000`. Its test-only kernel parameters are
`zx_spifc_nand.bch=1 zx_spifc_nand.bch_first=51136 zx_spifc_nand.bch_pages=64`.
These parameters do not cover either firmware bank or `rootfs_data` and are
not part of the default recipe command line.

### 2026-09-08: layout and correction verified on silicon

The first RAM boot exposed another integration issue: `nand_dt_init()` resets
the ECC geometry from DT before scanning. Strength, step size and placement
are now established in `attach_chip`, after that reset. The revised RAM kernel
booted with BCH enabled only for pages `[51136,51200)`; both WiFi modules were
blacklisted for the test.

On `staging` (`mtd12` in this boot), at partition offset `0x13e0000`:

* Raw layout test: 2048 data bytes and all 64 OOB bytes matched across three
  cache-evicted reads. The block was erased and verified blank afterwards.
* BCH test: eight deliberately cleared bits in one 512-byte step were corrected
  back to the original page, with eight corrected bits and max_bitflips=8.
  A raw read still showed the damaged data and unchanged parity.
* Cold-boot test: `--bch-keep` retained the fixture. After power-off and a fresh
  RAM boot, reading page 10179 of staging returned the original 2048-byte page
  (SHA256 `6f700d0f84becd4656d8542e6d84647e573e2fb38b27f730658f5a2121fd2f83`).
  The driver's boot counters started at zero; `mtd0/corrected_bits` then read 8.
* `--erase-fixture` checked every page against the known retained fixture,
  erased only that block, and verified all data/OOB bytes were erased again.

Neither firmware bank nor rootfs_data was reformatted. Configuration migration,
uncorrectable-error injection and sysupgrade validation remain outstanding.

The test executable was transferred over UART with SHA256 verification because
Linux TFTP timed out, although U-Boot TFTP worked at roughly 10 MiB/s. The first
UART copy failed its checksum and logged RX overruns coincident with kernel
console prints. Setting `printk.ignore_loglevel=N` and console_loglevel=1 made
subsequent transfers byte-exact. `tools/uart-blob.py` captures that transfer
method and refuses to report success without the received checksum.

Extending parity to kernel/rootfs does not make the existing bootloader correct
errors: it still reads raw data for its CRC checks. A corrupted boot image can
therefore fail its CRC before Linux has a chance to apply BCH. Boot-time recovery
and Linux runtime correction are separate requirements.
