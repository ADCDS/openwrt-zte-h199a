> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](README.md),
> [installation](INSTALL.md) and [validation](../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.
> **Storage supersession:** the deleted raw shim and its no-ECC/BCH experiments
> are not the production SPI-NAND path. Production uses Micron on-die ECC and
> UBIFS. Do not erase old staging or block 799: they include the live overlay.

# NAND - investigation journal

> **This is a chronological record, not a description of the current system.**
> It contains hypotheses that were tested and later **withdrawn**; several
> confident conclusions here are wrong and are corrected further down.
>
> For what is true now, read [`NAND.md`](NAND.md).
>
> It is kept because the failure modes proved more reusable than the results:
> instruments that could not fire, controls that did not exist, fixes validated
> against something the build does not produce, and rig faults misread as device
> faults. Those mistakes are the most transferable thing here.

# NAND (spifc) on the ZTE ZXHN H199A

> ## ⚠️ Two things before you use anything in this file
>
> **1. There is NO error correction.** The chip's on-die ECC (8 bits per 512 B)
> is deliberately disabled by this driver and nothing replaces it, and there is
> no persistent bad-block table. Every bit flip is silent. Treat data written by
> this driver - especially the JFFS2 overlay - as expendable.
>
> **2. The `/dev/mtdN` numbers in this document are historical and have already
> shifted once** (adding the `header` partition renumbered everything after it).
> Never hardcode them. Look the partition up by label:
>
> ```sh
> R=/dev/$(sed -n 's/^\(mtd[0-9]*\):.*"rootfs"/\1/p' /proc/mtd)
> ```
>
> **3. What the missing ECC actually exposes.** The JFFS2 overlay is the
> *better*-protected half: JFFS2 carries three CRC32s per node, so corruption
> there is detected - but at mount a bad node is **discarded**, and because JFFS2
> is log-structured, dropping a newer node makes **older data silently
> reappear**. A setting reverts rather than erroring.
>
> The real exposure is the **squashfs rootfs**: constantly read, never erased (so
> read disturb accumulates with nothing to reset it), and with no CRC layer of
> its own.
>
> Note also that the on-die ECC *status* is still polled and logged even though
> correction is off, so counts of corrected/uncorrectable events do appear - but
> the parity those counts derive from was written raw, so only trends on
> never-rewritten pages mean anything.
>
> The rest of this file is a chronological investigation journal and contains
> hypotheses that were later retracted.

# NAND / flash controller (spifc) — RE notes & plan

## Controller identity

- **ZTE `spifc`** (SPI-NAND controller), compatible `zte,ZX279127-spifc`,
  registers @ `0x94406000`. Flash: Micron **MT29F1G01ABAFDWB** SPI-NAND,
  128 MiB, page 2048 B, OOB 64 B, erase 128 KiB, 8-bit HW ECC.
- The `denali,denali-nand-dt` node @0xd80000 in the stock DTB is **NOT the
  controller** — it is a 124 MB `nand_data` window. `md.b 0xd80000` **hangs**
  from U-Boot → the window is not a passive map; spifc must be configured
  (memory-map enable / ECC mode) before reads work.
- **No public source exists** (GitHub code search auth-gated, DDG/grep.app
  empty; ZX279133 moved to standard `spi-nand` so cnjn's tree doesn't apply).

## Stock driver (Linux 4.1, extracted from `ref/stock-vmlinux.bin`)

Function names (from strings):
`spifcnand_nand_int`, `spifcnand_nand_read_page`, `spifcnand_nand_wait`,
`spifcnand_nand_wait_common`, `spifcnand_nand_write_page_pre`,
`spifcnand_nand_remove`, `spifc_read_fifo`, `spifc_write_fifo`,
strings `spifc->io_base`, `zte_spifc_reg`, `ECC_ctrl_for_read`,
`EccProcessbyManu`, `spifc fail to insert oob page %d`, `spifc error cmd %d`.

→ It is a **raw NAND** driver (`spifcnand`) doing FIFO-based page
read/write with vendor BCH ECC and OOB insertion.

### Register map — CORRECTED & VALIDATED (READID returns Micron 2c 14 ✓)

| offset | role (validated on hardware) |
|---|---|
| +0x04 | trigger (|=1 after programming) |
| +0x08 | ctrl (|=1 before command) |
| +0x0c | init (|= 0x1c400 \| 0x40 every command) |
| +0x10 | cmd config word: `f5<<2 \| f1<<4 \| f3 \| f4<<1` (descriptor fields) |
| +0x14 | cmd config 2: `f6<<12 \| f2<<5`, then clear 0x700 |
| +0x18 | transfer count = `desc.count - 1` |
| +0x1c | cmd mode (0 for 0x60/0x90/0x9f id-class) |
| +0x20 | **SPI opcode byte** |
| +0x2c | status: bit1 = done (poll), bit2 = busy |
| +0x30 | ECC reg — write 0x3f when !(status & 2) |
| +0x38 | FIFO (read results words) |
| +0x380 | page buffer |

### Command descriptor table (68 B/entry @0xc0430210 in stock; subset re-encoded in driver)

| cmd | SPI op | f1 | f2 | f3 | f4 | f5 | f6 | cnt | meaning |
|---|---|---|---|---|---|---|---|---|---|
| 0x00 | 0x06 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | WRITE ENABLE |
| 0x01 | 0x04 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | WRITE DISABLE |
| 0x02 | 0xD8 | 1 | 2 | 0 | 0 | 0 | 0 | 0 | **BLOCK ERASE** |
| 0x03 | 0x9F | 0 | 2 | 0 | 1 | 0 | 0 | 4 | READ ID |
| 0x05 | 0x03 | 1 | 2 | 0 | 1 | 0 | 0 | 0 | READ FROM CACHE |
| 0x07 | 0x02 | 1 | 2 | 1 | 0 | 0 | 0 | 0 | PROGRAM LOAD |
| 0x08 | 0x3B | 1 | 2 | 0 | 1 | 1 | 1 | 0 | READ X4 |
| 0x09 | 0x6B | 1 | 2 | 0 | 1 | 1 | 1 | 0 | READ X4 |
| 0x0A | 0x32 | 1 | 2 | 1 | 0 | 0 | 0 | 0 | PROG LOAD X4 |
| 0x0C | 0x35 | 0 | 2 | 0 | 1 | 0 | 0 | 1 | internal data move |
| 0x0D | 0x05 | 0 | 2 | 0 | 1 | 0 | 0 | 1 | RANDOM DATA INPUT |
| **0x0E** | **0x9F** | 1 | 0 | 0 | 1 | 0 | 0 | 5 | **READ ID (JEDEC) — VALIDATED** |
| 0x0F | 0x84 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | RANDOM DATA READ |
| 0x10 | 0x34 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | PROG LOAD RANDOM X4 |
| 0x11 | 0x10 | 1 | 2 | 0 | 0 | 0 | 0 | 0 | **PROGRAM EXECUTE** |
| 0x12 | 0x13 | 1 | 2 | 0 | 0 | 0 | 0 | 0 | **PAGE READ → cache** |
| 0x13 | 0x03 | 1 | 1 | 0 | 1 | 1 | 1 | 0 | READ CACHE X4 |
| 0x14 | 0x3B | 1 | 1 | 0 | 1 | 1 | 1 | 0 | READ X4 |
| 0x15 | 0x6B | 1 | 1 | 0 | 1 | 1 | 1 | 0 | READ X4 |
| 0x16 | 0x0F | 1 | 0 | 0 | 1 | 0 | 0 | 1 | GET FEATURE |
| 0x17 | 0x1F | 1 | 0 | 1 | 0 | 0 | 0 | 1 | SET FEATURE |
| 0x18 | 0xFF | 0 | 0 | 0 | 0 | 0 | 0 | 0 | **RESET** |
| 0x19 | 0x02 | 1 | 1 | 1 | 0 | 0 | 0 | 0 | ? |
| 0x1E | 0x98 | 1 | 2 | 0 | 0 | 0 | 0 | 0 | READ ID X4 |

Field meanings: f1 (data-in/addr?), f2 (x4 mode?), f3 (write?), f4
(dummy/addr?), f5+f6 (x4 output enable). Page read flow: WREN(0x00) →
PAGE READ 0x13 (addr) → READ X4 0x6B (data+OOB) — the classic SPI-NAND
read dance. **Status: READID validated on hardware; page-read path next.**

## Round 2 findings (2026-08-20): dual-engine architecture

- **Two access paths to the flash:**
  1. **spifc @0x94406000** — SPI-NAND command engine (registers +0x04..+0x38,
     decoded + validated via READID). Used by the stock Linux 4.1 driver.
  2. **denali @0xd00000** — second engine (registers +0x000..+0x410) with a
     124 MB memory-mapped data window @0xd80000 (`nand_data`). **U-Boot's
     `nand read` uses THIS path** (bootloader code at file 0x2098/0x2100/
     0x21d4: init = `[0xd00000+0x410]=0xffff; [0xd00000]=1` + poll
     `[+0x410]&0x2008`; read setup writes ~50 registers +0x150..+0x230).
- Raw `md.b 0xd80000` from U-Boot **hangs** without the full denali setup —
  the window is gated, not passive.
- `+0x380` region on the spifc **mirrors the +0x00..+0x3c registers**
  (observed: 01040000 00000003 00010440 …), not a data buffer.
- spifc post-read register state from U-Boot (ground truth for the data
  phase): CFG=0x16, CFG2=0x1024, CNT=0x83f (2048+64−1), ADDR(+0x1c)=0,
  OPCODE=0x3b, +0x24=0x889 (fixed), ECC(+0x30)=0x100020 (raw mode),
  INIT(+0x0c)=0x10440.
- **Open problem: the page-read row address.** Tested: +0x1c, +0x18, FIFO —
  none change the result (rows 0–3 return identical zeros). The stock
  kernel's dispatch stores its 3rd argument into +0x1c for non-ID commands;
  the exact argument flow ([dev+0x5e4]-based) is not yet fully traced.
- Next: decode U-Boot's transfer engine @file 0x2018 + the three command
  structs used by the read function @0x2100 (literals at [pc,#0xa8]/#0x94/
  #0x84) — U-Boot's complete read recipe; and/or finish tracing the stock
  kernel's address argument chain into dispatch.

## Round 3 findings (2026-08-20): three drivers, two engines, one recipe

There are THREE flash drivers in the bootloader partition:
1. **secondboot** (file 0x2018-0x2360, runs from SRAM): denali-window engine.
2. **U-Boot's `nand` command driver** (file ~0x3e680+, pool at 0x3ee74-0x400f4):
   spifc command engine (its post-read state is the 0x3b/0x840 we saw).
3. **stock Linux 4.1** spifc driver (the 0x94406000 +0x04..+0x38 engine).

### secondboot's transfer recipe (file 0x2018) — denali window
```
read_transfer(flash_addr, dest, len):
  [denali+0x410] = 0xffff           # denali = 0xd00000
  [0xd80000]   = flash_addr | 0x08000000
  [0xd80010]   = 0x41               # cmd 1
  [denali+0xe0] = 0
  [0xd80000]   = flash_addr | 0x08000000
  [0xd80010]   = 0x2001             # cmd 2 (read data)
  [0xd80000]   = flash_addr | 0x04000000
  poll [denali+0x410] & 0x48        # until nonzero
  copy words: dest[i] = [0xd80010]  # data comes word-by-word from +0x10
```
**Tested manually from the U-Boot prompt: HANGS** (denali+0x410 reads back 0;
the engine is clock-gated or needs init beyond this — the window registers
0xd80000/0xd80010 also hang on read when unpowered).

### U-Boot's chip-init (file 0x3e680) — descriptor table, 0x34 B/entry
Per-chip table (indexed like the stock kernel's 0x44-byte one) with fields
at +0x24..+0x51; programs BOTH engines:
- spifc: +0x00=desc24, +0x04=desc28, +0x08=desc2c, +0x0c=desc30, +0x10=desc34,
  +0x14=desc28+desc24, +0x18=desc24*desc2c, +0x1c=desc3c, +0x20=desc40(byte),
  +0x21=desc41(byte)
- denali: +0x100=desc48<<8|desc49, +0x110=desc4c<<8|desc4d, +0x120=desc4b,
  +0x150=desc2c, +0x160=desc3c, +0x170=desc24, +0x180=desc28, +0x1b0=desc38,
  +0x1f0=desc4f, +0x200=desc50, +0x220=desc51, +0x290=desc4a,
  +0x350=desc24*[denali+0x250], +0x360=desc28*[denali+0x250]
- also reads topcrm+0x40 (flash clock config).

### Open: the row-address register for page reads
Tested on hardware (spifc path): +0x1c, +0x18, FIFO — rows 0-3 identical ⇒
address not landing. Next candidates: **denali+0x170** (init writes geometry
there; the read may overwrite it with the row), spifc+0x20/+0x21 (byte-wide),
or a shift in expectations (row<<11). Round-3 task: find U-Boot's actual
page-read function (search for writes to denali+0x170 / spifc trigger in the
0x3e000-0x40100 region) and decode it.

## Round 4 findings: post-read register states (the address is transient)

Dumped BOTH engines after U-Boot `nand read` at offsets 0x0 and 0x100000:
- spifc (0x94406000): identical (0x16/0x1024/0x83f/0x3b — stale-ish config)
- denali (0xd00000): identical; nonzero values post-read:
  +0x100=0x1432, +0x110=0x1432, +0x120=0x32, +0x190=1, +0x1b0=4,
  +0x1f0=0x12, +0x200=0xc, +0x220=3, +0x240=0xffff
- ⇒ **no register retains the row address.** It flows transiently through
  the 0xd80000 window write (secondboot's `addr|0x08000000` pattern) or an
  equivalent.

### Chip descriptor (U-Boot search-table, file 0x53668, entry[6] = our chip)
- JEDEC ID `2c f1 80 95` (4-byte; the "2c,14" in the boot log is the 2-byte
  legacy-ID read). page=2048 (+0x04), OOB=64 (+0x08), +0x0c=0x40,
  +0x10=0x400, +0x14=1, +0x18=4, +0x20=0x202, +0x24=template ptr.
- The 0x3e680 init fills a RAM struct @0x47f55be0 + programs denali
  (+0x100..+0x360) — but post-read most of those read 0 (cleared or
  never run at prompt time).

### Round-4 addendum: denali liveness + window FIFO behavior
- After `nand read`, the denali is **live**: [0xd00410]=0x8 (done bit),
  [0xd000e0]=0x1 (transfer counter). Before any read in a boot, denali
  registers read 0 and writes don't stick (uninitialized/reset state).
- Running secondboot's recipe manually (post-read, denali live) still
  **hangs on reading [0xd80010]** ⇒ the window data register is a
  **blocking FIFO** — reads hang when no data is staged. My 0x41/0x2001
  command sequence apparently didn't start a transfer (status unchanged).
- `0xd80010` literals exist in U-Boot's region (0x3df5c, 0x3eb2c) but no
  ARM-mode PC-relative refs found ⇒ likely referenced from **Thumb code**
  (U-Boot region mixes ARM/Thumb — also why earlier full-region scans
  under-reported).

### Round-5 plan (pick ONE, in priority order)
0. **TEST FIRST (cheapest, high probability): the +0x1c |= 0x1000 flag.**
   Re-reading the stock dispatch: for cmds 0x13..0x19, when the caller's
   first argument has bit 0x40 set, the dispatch ORs **0x1000 into the
   value written to [spifc+0x1c]** (`tst r0,#0x40; orrne r3,r3,#0x1000;
   str r3,[ip,#0x1c]`). My driver wrote bare `row` to +0x1c with no flag —
   the controller may require the 0x1000 bit to latch the address at all
   (which would explain rows 0-3 returning identical data: address ignored,
   a default page read every time). Next build: phase 1 writes
   `spifc_w(SPIFC_ADDR, row | 0x1000)`.
1. **Finish the stock-kernel spifc address trace** (closest to working —
   READID already validates this engine): disassemble 0xc020aa68 callers
   fully in order; determine exactly which value lands in [spifc+0x1c] on
   a real page read and what [dev+0x5e4] holds at that moment. Consider
   dumping [dev+0x5e4]-adjacent memory from a running stock kernel via
   /dev/mem (stock has full shell? — no, serial login unknown). Better:
   patch my driver to also try [spifc+0x18]=row<<11 and [spifc+0x1c]=row<<11.
2. Thumb-disassemble U-Boot's read function around literals 0x3df5c/0x3eb2c
   (CS_MODE_THUMB) to get its exact window-transfer sequence.
3. Denali-init replication: program the post-read register values, then
   secondboot's recipe — with the poll BEFORE any window read.

## Round 6 (2026-08-20): READ PATH DONE — page-read row address SOLVED

The read path is now **byte-exact against the July dump** (verified pages
0, 1, 2, 64, 4096, 65535 — all match `h199a-firmware/h199a-flash-full.bin`), `nand_scan`
detects the Micron chip, the BBT scan finds **zero** bad blocks, and the 9
DT partitions register (`mtd0`=whole flash … `mtd9`=rootfs2).

Three bugs, each proven on hardware:

1. **Row address goes to `+0x1c` as the RAW page number** — no `0x1000`
   flag, no FIFO write. Decoded from the stock dispatch `0xc0208be4` +
   `issue-page-read` `0xc0208fb8` (called from `0xc020aa68` ←
   `0xc020ab1c`): `dispatch(dev, dev, cmd=0x12, r3=addr)` stores `r3`
   into `[io_base+0x1c]`. The `+0x1c |= 0x1000` in the dispatch only fires
   when `[0xc05e5b58]≠0 && cmd∈[0x13..0x19] && r0&0x40` — the *normal*
   read path passes `r0=0`, so 0x1000 is **not** set. Writing
   `row | 0x1000` shifted every read to `row+4096` (empirically: page 0
   returned the bytes of flash offset 0x800000). The FIFO 3-byte write was
   spurious (the row lives in +0x1c, not the TX FIFO).

2. **`exec_op` parsed the COLUMN as the row.** The 6.6 framework emits
   `[col_lo, col_hi, row_lo, row_hi, ...]` (`nand_lp_exec_read_page_op`).
   The driver computed `page = addrs[0]<<8 | addrs[1]` = column, so the BBT
   scan (which reads OOB at column 2048) read the wrong page → every block
   "Bad eraseblock". Fix: `col = a[0]|a[1]<<8`, `page = a[2]|a[3]<<8`.

3. **Partitions need `nand_set_flash_node()`.** The `ofpart` parser reads
   `mtd->dev.of_node`; setting it manually wasn't enough in this flow —
   `nand_set_flash_node(chip, dev->of_node)` (before `nand_scan`) made
   `mtd_device_parse_register` find the `partitions` node. (The debug print
   `of_node=spifc@94406000 partitions_child=yes` proved `dev->of_node` was
   never NULL — the earlier "of_node is NULL" theory was a misread of a
   stale boot log.)

Driver now reads the full 2112-byte page into `sp->pagebuf` and slices the
requested `col..col+len` for the framework (handles data, OOB and 2-byte
bad-block-marker reads).

**End-to-end validated (2026-08-20, soft-float initramfs on the device):**
`root@OpenWrt:~# cat /proc/mtd` lists mtd0…mtd9; `dd if=/dev/mtd1` returns the
`"128s"` bootloader header and `dd if=/dev/mtd7` returns the `"SBU&"` ZTE
rootfs container — both byte-identical to `h199a-firmware/mtd0-bootloader.bin` /
`h199a-firmware/mtd6-rootfs.bin`. (The stock rootfs is a ZTE `"SBU&"` container, not a
bare jffs2/squashfs, so a plain `mount -t jffs2` fails on the header — that
is expected, not a driver bug.)

## Write/erase path (stock 4.1, decoded 2026-08-20 — NOT yet implemented in driver)

Same command engine as read; every command is `cmd_begin → dispatch → 
INIT |= 0x1c440 → post-command(ECC=0x3f if !(status&2)) → trigger |= 1 →
poll status&1` (the stock's three `generic cmd exec` functions 0xc020a2b4 /
0xc020a108 / 0xc020a000 are byte-identical to `issue-page-read` except the
dispatch cmd index):

- **BLOCK ERASE** `0xc020a2b4`: dispatch(cmd=0x02, addr=row) — row = first
  page of the block (block << 6). No WREN inside; caller does it.
- **PROGRAM EXECUTE** `0xc020a108`: dispatch(cmd=0x11, addr=row).
- **WRITE PAGE** `0xc020a1a0` (`spifcnand_nand_write_page_pre`):
  WREN(cmd wrapper 0xc0209dc8 cmd 1) → PROG LOAD with data (0xc0209fdc,
  FIFO-TX via 0xc0208b20, chunk loop; if [dev+0x618]≠0 uses an ECC path
  0xc0208838) → PROGRAM EXECUTE (0xc020a108) → FIFO verify (0xc0209244).
- **PROG LOAD** `0xc0209fdc`: dispatch(cmd=0x19, addr=column) + data words
  pushed to FIFO-TX, CNT = bytes-1; the OIP wait is via feature 0xC0.

## Write/erase IMPLEMENTED & VERIFIED (2026-08-20)

The write path is now working, verified by a probe self-test on blank tail
block 896 (off 0x7000000): `WRITE selftest: OK` + `ERASE selftest: OK`
(write a pattern → read-back verify → erase → read-back verify blank).

Three more hardware-proven details beyond the read fix:

1. **Write commands need `INIT |= 0x1c440`** (bits 14-15 = write/TX-FIFO
   enable), not the read path's idle `0x10440`. The stock's `generic cmd
   exec` (0xc020a2b4/0xc020a108/0xc020a000) all do `INIT |= 0x1c440`; the
   driver's `spifc_finish_w()` mirrors it. WREN → BLOCK ERASE now works.

2. **PROG LOAD uses descriptor cmd 0x19 (f16a=1), not 0x07 (f16a=2).**
   `0xc0209fdc` dispatches `r2=#25` = 0x19. (f16a → CFG2 bits 5-7; the
   difference is CFG2 0x20 vs 0x40.)

3. **The TX FIFO is only 16 words deep.** `FIFOST` read `0x00100020` (TX
   count 16). A blocking per-word write deadlocks: it fills the 16-word FIFO
   then waits for space that only appears after the trigger. The stock
   writes the first chunk, then `trigger |= 1`, then keeps feeding as the
   controller drains. The driver now triggers after word 15 and continues.

Driver status: read ✅ write ✅ erase ✅ — all raw mode. The probe self-test
is gated behind `zx_spifc_nand.wtest=1` (off by default). Remaining for the
driver: HW BCH ECC (8b/1024B) decode so bit-flipped pages read correctly.

## Flash image format (kernel partitions — for the sysupgrade step)

The A/B kernel partitions (`kernel1` @0x700000, `kernel2` @0x2000000) hold the
same image, which is:

```
+0x00  16 B  ZTE "128s" magic: 33333333 cccccccc 88888888 dddddddd
+0x10  16 B  0xFF padding
+0x20  ...   standard U-Boot uImage (magic 0x27051956, load/entry 0x40008000)
```

Both banks are byte-identical up to +0x40 (verified from the dump).

## Firmware header + kernel CRC (cracked 2026-08-21 — needed for a bootable flash)

A plain `uImage` wrapped with the 32-byte header does **not** boot: `zteboot`
rejects it with `Kernel CRC check failed`. The boot chain (from the boot log)
is: `csp_crc` computes a CRC over the kernel data and compares it to a value
stored in the **firmware header** at `0x1720000` (bank A) / `0x3020000`
(bank B). Decoded:

- **Kernel CRC** = standard **`zlib.crc32`** over the kernel data starting at
  flash offset `+0x20` (i.e. right after the 32-byte `"128s"` header), length
  `0x2ffdcc` (stored in the header), with the region after the uImage
  **zero-padded**. Verified: `zlib.crc32(stock_kernel1[0x20 : 0x20+0x2ffdcc])
  == 0x107dd7f0`, exactly the bootloader's `Want`.
- **The header has its OWN CRC.** `zteboot_verify_header` CRCs `hdr[0:0xa4]`
  and compares against a u32 stored at **`+0xa4`**. Because the kernel-CRC
  field (`+0x3c`) is *inside* that range, patching the kernel CRC without
  recomputing the header CRC makes the search log
  `header crc error, ofs=0x1720000` and the bank silently disappears
  (`Total found 1 firmwares`). Both must be written.
- The header at `0x1720000` (BootPara) fields:
  ```
  +0x34  u32  kernel data length (0x2ffdcc)
  +0x3c  u32  kernel CRC        (0x107dd7f0)     ← what csp_crc checks
  +0x40  u32  rootfs size       (0xd20000)
  +0x44  u32  rootfs offset     (0x300214)
  +0x48  u32  rootfs CRC        (0x7bc2f9e9)
  +0x4c  u32  kernel offset     (0x700000)
  +0x10  str  version "V9.1.0P3N2_MUL"          +0x70 str "ZXHN H199AV9.1"
  ```
- Bank selection: `validImgNum`/`bootWhichImg` in the bootpara; a bank whose
  kernel CRC fails is marked invalid and the other bank boots. So a correct
  image needs BOTH the kernel written and its CRC written into the header.

**Kernel size limit:** `zteboot` reads `0x300000` (3 MiB) from the kernel
offset, so the uImage (after the 32-byte header) must be ≤ ~`0x2fffe0`. The
stock uImage is 0x2f83fe. The armsr default kernel was 3.26 MiB (too big);
disabling the ARM64-server drivers it inherits (EFI, VIRTIO, SCSI/SATA/NVMe,
USB, HID/INPUT, eBPF, ext4/f2fs, KALLSYMS_UNCOMPRESSED — see
`files/target/linux/armsr/armv7/config-6.6`) brings it to **2.48 MiB**, which
fits.

## ✅ BOOT FROM FLASH ACHIEVED (2026-08-21)

`tools/flash-prep.py` produces both files; flash them over U-Boot TFTP:

```
tftp 0x42000000 h199a-flash-kernel.bin ; nand erase 0x700000  0x300000 ; nand write 0x42000000 0x700000  0x300000
tftp 0x42000000 h199a-flash-header.bin ; nand erase 0x1720000 0x20000  ; nand write 0x42000000 0x1720000 0x20000
```

Verified autoboot (no TFTP, no U-Boot interaction):

```
Total found 2 firmwares(valid:2), start from ver 0
zteboot_do_settings: select=0            <- bank A = our image
   Image Name:   h199a-openwrt           <- our kernel, not stock
9 fixed-partitions partitions found on MTD device 94406000.spifc
```

Bank B still holds the stock firmware as a fallback. Known issue: the spifc
probe intermittently hits `nand_scan failed (-110)` on a flash boot (the
bootloader has just driven the controller); a retry/reset at probe is needed.

## Rootfs (squashfs) — mounts from NAND (2026-08-21)

The rootfs bank is validated the same way as the kernel:

- FS CRC = `zlib.crc32` over `fs_size` bytes read from `fs_start`, stored at
  header **`+0x48`**. Verified: `zlib.crc32(flash[0xa00000 : +0xd20000]) ==
  0x7bc2f9e9`, matching the stock header.
- **`fs_size` (+0x40) must stay `0xd20000`**: zteboot derives
  `HeaderOffset = fs_start + fs_size` (0xa00000 + 0xd20000 = 0x1720000), so
  shrinking it moves the header and the bank disappears. Zero-pad instead.
- The OpenWrt `squashfs-rootfs.img` is padded to 104 MiB by the image builder;
  take the real length from the superblock (`bytes_used`, u64 at +0x28) before
  padding to `fs_size`. Ours is 2.99 MiB.

`tools/flash-prep.py KERNEL.uImage DUMP OUT ROOTFS.squashfs` emits
`.kernel`, `.rootfs` and `.header` with all three CRCs correct. Result:

```
zteboot_verify_fs:242 verify fs success!!        <- bootloader accepts our rootfs
mtd: setting mtd7 (rootfs) as root device
1 squashfs-split partitions found on MTD device rootfs
VFS: Mounted root (squashfs filesystem) readonly on device 31:7.
Run /sbin/init as init process
```

### Open blocker: userspace stalls (NOT ECC, NOT the driver)

Round 11 settled this with an in-kernel diagnostic (`zx_spifc_nand.rtest=1`,
read-only) that reads the flashed rootfs region twice per page and CRCs it,
both through the internal raw read and through `mtd_read()` (the `exec_op`
path mtdblock/squashfs actually use):

```
rtest:     pages=1536 errs=0 mismatch=0 crc=0xaf3225c7   (raw)
rtest-mtd: errs=0            crc=0xaf3225c7   (mtd_read -> exec_op)
expected (zlib.crc32 of the flashed image)  = 0xaf3225c7
```

Both match the host-computed CRC exactly. So over 3 MiB: **zero read errors,
zero nondeterminism, zero bit flips, and the exec_op path is byte-identical to
the raw path.** Therefore:

- HW BCH ECC is **not** required to read this flash correctly, and is **not**
  what blocks booting. (It is still worth adding for long-term bit-rot, but it
  is not on the critical path.)
- The driver, the flashed image and the poll timing are all exonerated.

Other suspects checked and ruled out:

| suspect | check | verdict |
|---|---|---|
| truncated/invalid squashfs | host `unsquashfs -s/-l` lists every file | image valid |
| missing XZ BCJ filter | image uses `Filters selected: arm`; kernel has `XZ_DEC_ARM=y`, `XZ_DEC_BCJ=y` | supported |
| L2 cache misconfig | our `l2cc` node is identical to the stock DTB (same `arm,data-latency`, `tag-latency`, `double-linefill`) | matches stock |

What actually happens: the root squashfs **mounts fine**, then the first
userspace binary stalls forever. With `init=/bin/sh` the kernel prints
`Run /bin/sh as init process`, the tty echoes typed input, but no command ever
executes — i.e. exec succeeds and then demand paging never completes. With
`/sbin/init` the same point fails as
`Error loading shared library libjson-c.so.5: I/O error`.

### Round 12: the controller WEDGES after any failed transfer

Booting the same trimmed kernel with an **initramfs** gives a fully working
OpenWrt shell (`SHELL_OK`, `uname -r` = 6.6.151, `/proc/mtd` populated), so the
aggressive config trim is **not** the problem — userspace is healthy. Using that
live shell the failure was reproduced and pinned down:

```
# mount -t squashfs /dev/mtdblock7 /mnt/r
mtdblock: MTD device 'rootfs' is NAND, please consider using UBI block devices instead.
   ...10 seconds later...
I/O error, dev mtdblock7, sector 0 op 0x0:(READ)
SQUASHFS error: Failed to read block 0x0: -5
unable to read squashfs_super_block

# for b in 2048 4096 16384 65536; do dd if=/dev/mtd7 bs=$b count=1; done
dd: /dev/mtd7: Operation timed out      <- ALL sizes, including 2048
```

So **one failed transfer poisons the controller**: every later read returns
`-ETIMEDOUT` until a power cycle. mtdblock reads a whole 128 KiB erase block at
once, which is what trips it, while the 4 KiB `mtd_read()`s of `rtest` succeed.
This single bug explains all three symptoms: the userspace stall, the
`SQUASHFS ... -5` errors, and the intermittently "hung" BBT scan.

Also measured: the BBT scan degraded from 12.4 s to **70 s** during this round
but still completed — so the earlier "hangs" were partly very long timeout
retries. Wait >90 s before declaring a boot dead.

Tried and rejected (do not repeat): draining the RX FIFO in `spifc_cmd_begin()`
(`while FIFOST & 0x1f00: read SPIFC_FIFO`) made it strictly worse — the BBT scan
then failed in 0.13 s instead of completing, so those status bits do not mean
"RX words pending" as assumed.

Next steps, in order:

1. Recover the stock driver's controller **reset/re-init** sequence and run it on
   the error path, so a single timeout cannot wedge the block.
2. Suspect the on-chip ECC feature toggle (feature `0xB0` bit `0x10`) that the
   read path disables before PAGE READ and re-enables afterwards.
3. Longer term, move the rootfs to **UBI + ubiblock** (OpenWrt's supported NAND
   layout) so 128 KiB mtdblock reads are not on the critical path.

## Round 13: wedge FIXED, and ECC is now proven REQUIRED

Three driver changes, each verified on hardware:

1. **Recovery on timeout.** `spifc_poll()` sets `sp->wedged`; `spifc_cmd_begin()`
   then kicks the controller (drop/re-assert `CTRL` bit 0, clear status, rewrite
   `INIT`), issues a chip `RESET` (0xff) and waits for OIP to clear.
   Verified from a live shell — previously *every* read after a failure timed
   out; now:
   ```
   dd bs=131072 count=8 -> Operation timed out   (large read still failed)
   dd bs=2048   count=1 -> 1+0 records out RC=0   (next read SUCCEEDS)
   ```
2. **Read retry** (`SPIFC_READ_RETRIES = 4`): MTD never retries `-ETIMEDOUT`, and
   a 128 KiB mtdblock request is 64 pages, so it almost always hit one failure.
3. **Short timeouts**: the STATUS poll went from 5 s to 100 ms. A "command done"
   completes in microseconds; 5 s only made every spurious failure ruinous.

Measured result — this fixed the large-read failure outright:

| metric | before | after |
|---|---|---|
| BBT scan | 12.4 s (degraded to 70 s) | **3.2 s** |
| `dd bs=128K count=16` (2 MiB) | always `Operation timed out` | **1.94 s, OK** |
| boot to `Run /sbin/init` | 13 s | **3.7 s** |

Boot from NAND now reaches init with the squashfs mounted:
`valid:2` / `select=0` / `Image Name: h199a-openwrt` /
`VFS: Mounted root (squashfs filesystem) readonly on device 31:7`.

### ECC is required (corrects the round-11 conclusion)

init still fails, repeatedly, at one deterministic spot
(`SQUASHFS error: Unable to read metadata cache entry [2fcd90]`). Cause proven
by checksumming the *same* 3 MiB region on host and device:

```
host   md5 (image as written) : 50804777f4fdedd220064443a454e7e9
device md5 (raw read of mtd7) : 4b9dca17c199f114b07c81ec29660101   <- MISMATCH
```

Meanwhile `zteboot_verify_fs` CRCs that region successfully, because the
bootloader reads **with the hardware BCH engine**. So the flash holds real bit
flips that ECC corrects and our raw reads do not. Round 11's `rtest` CRC match
was a flip-free sample, not proof of correctness — freshly written MLC pages
carry correctable errors by design.

**Therefore the 8b/1024B HW BCH decode is now the critical path**, not an
optional bit-rot nicety.

## Round 14: ECC attempts (both rejected), and a key control

Two ECC approaches were implemented and measured. Fingerprint used throughout:
md5 of the first 3 MiB of `mtd7`, **expected `50804777f4fdedd220064443a454e7e9`**
(md5 of the image actually written).

| attempt | config | md5 | verdict |
|---|---|---|---|
| baseline raw | `ECC=0x100020`, `INIT=0x10440` | `4b9dca17` | mounts; fails on late blocks |
| on-die ECC | set feature `0xB0` bit `0x10` **before** PAGE READ | `a0db4db8` | worse |
| controller BCH | `ECC=0x3f`, `INIT\|=0x1c440`, FIFO-before-poll | `75b6dafa` | worse: superblock unreadable (`mount: Invalid argument`) |

The controller-BCH values are not guesses — they come from the stock read path
(`0xc0209050` sets `CFG2=(CFG2&~5)|4` then `INIT |= 0x1c440`, and `0xc020894c`
writes `ECC = 0x3f` when `STATUS & 2` is clear). The stock also **drains the
FIFO before polling STATUS**, the opposite order to ours. Reproducing all of
that still did not decode ECC, so something else in the layout is missing —
most likely the per-manufacturer **ECC descriptor table at `0xc0430210`**
(0x110-byte entries, selected by chip ID in `0xc020a4ec`). That is the next lead.

On-die ECC cannot work here regardless: U-Boot writes the *controller's* BCH
parity, so the chip's on-die parity was never generated.

### Control: the flash is NOT corrupt

Important check before trusting any of the above — after all the experiments the
bootloader still reports:

```
zteboot_verify_kernel:175 verify kernel success!!
zteboot_verify_fs:242     verify fs success!!
Total found 2 firmwares(valid:2), start from ver 0
```

It CRCs both regions with the hardware ECC engine and passes, so the data on
flash is intact and **every md5 difference above is our read path, not flash
damage**.

### Methodology note

Do **not** use `/dev/mtdblockN` for diagnostics: it is a read-write cached block
device and can write cached blocks back, which corrupted the rootfs earlier in
this port. Use the char device `/dev/mtdN` for read tests.

### Reliability (round 13 fixes) still holds

`BBT scan 3.18 s`, `dd bs=128K count=16` (2 MiB) `1.83 s`, boot to init `3.7 s`.
Driver is left on the raw data phase, which is the only variant that mounts.

## Round 15: READS ARE NON-DETERMINISTIC — ECC is not the blocker

The single most important measurement so far. Reading the **same** 1 MiB of
`/dev/mtd7` three times in a row, from one shell session:

```
# for i in 1 2 3; do dd if=/dev/mtd7 bs=4096 count=256 2>/dev/null | md5sum; done
0293f610fa3521cb8bf2c04a4cbdf2d2
6529962fe953a77db4eb6cfba59f76a3
ed1f3e0efee8ee259247501dd6c013b0
```

Three different results. Meanwhile `zteboot` CRCs that same flash region with the
hardware ECC engine and passes on **every** boot, so the medium is intact.

**Conclusion: the read data path silently corrupts, and that — not missing ECC —
is what breaks userspace.** This supersedes the round 13/14 framing: the md5
"mismatch vs host" that motivated the whole ECC hunt is explained by
non-deterministic reads, not by bit flips. (It also explains why every ECC
variant produced a *different* wrong md5: each run was simply a different
corruption.)

Tried and rejected this round:

| attempt | rationale | result |
|---|---|---|
| on-die ECC before PAGE READ | chip corrects array->cache | worse (`a0db4db8`) |
| `ECC=0x3f`, `INIT\|=0x1c440`, FIFO-before-poll (stock-exact) | from `0xc0209050`/`0xc020894c` | worse: superblock unreadable |
| `local_irq_save()` around the transfer | RX FIFO is 16 words vs 528/page; stock has an irq-save helper at `0xc0209f04` | no change — 3 md5s still differ |

Also useful: `0xc020abd4` writes a *global* (`0xc05e5b30+0x30`), not the ECC
register — it is the driver's bit-flip counter, zeroed before the read and
checked at `+0x34` afterwards, branching to error handling when non-zero.

Next: instrument the FIFO drain itself (count words actually consumed per page,
compare against 528, and log `FIFOST` when the count is short). The stock loop
(`0xc02089e4`) is structurally identical to ours except it bounds the wait by
jiffies and retries once, which suggests short/over-long transfers are expected
and must be detected rather than assumed.

## Round 16: feature-register semantics pinned down; corruption is structured

The chip's feature `0xB0` reads **`0x10` — ECC_EN is SET at power-up**, which is
the state the bootloader reads the flash in. The stock per-page *toggle* (clear
before PAGE READ, restore after) turns out to be functionally required. Both
"configure once" simplifications fail, and each failure is informative:

| feature 0xB0 handling | result |
|---|---|
| toggled per page (stock, current) | works: zero bad blocks, squashfs mounts |
| set once at probe **cleared** (0x00) | every block reads bad — `Bad eraseblock 729...`; OOB parity lands on the bad-block marker byte |
| set once at probe **set** (0x10) | reads return *nothing* (`dd` produced 0 bytes, md5 = `d41d8cd9…` = empty) |

So on-die ECC is real and enabled by default, but the data is read with it
disabled — the parity in OOB is the controller's, and the marker byte is only
meaningful while ECC_EN is off.

Genuine bug found and fixed (kept): the OIP wait ignored
`spifc_get_feature()`'s return value —

```c
spifc_get_feature(sp, 0xc0, &feat);   /* return ignored */
if (!(feat & 1)) break;               /* garbage -> exit early */
```

so a failed status read could end the wait early and transfer the *previous*
page still in the chip cache. It now requires a successful read and sees ready
twice before believing it. This did **not** fix the non-determinism, so it was
not the root cause, but it is a real robustness fix (BBT still 3.9 s, zero bad
blocks).

Ruled out so far for the non-determinism: ECC/bit flips (flash provably intact),
interrupt latency (`local_irq_save`), feature-register garbage, and OIP
early-exit. Remaining suspect: the FIFO drain / transfer framing.

Useful new clue: the corruption is **structured, not random** — md5
`ed1f3e0efee8ee259247501dd6c013b0` recurred across separate boots and rounds.
A small set of repeatable wrong results points at word-level shift/duplication
in the drain (e.g. reading a word when `FIFOST` is stale), not bit noise.

## Round 17: ROOT CAUSE FOUND — reads are now byte-exact

The structured corruption was a **logic bug in `exec_op`**, not electrical. The
ADDR handler did:

```c
page = 0;                       /* unconditional reset */
if (n >= 3) page = a[2];        /* only set when a row is supplied */
```

But two very common operations carry no row:

- `nand_read_data_op()` — the OOB fetch after every page — sends `DATA_IN`
  with **no ADDR instruction at all**;
- `nand_change_read_column_op()` sends a **2-byte column-only** address.

In both cases `page` fell back to 0, so we re-read **page 0** and handed those
bytes back as the requested page/OOB. That is exactly why the wrong results were
a small repeatable set rather than noise, and why probe-time full-page reads
(which always carry a 5-byte address) looked perfect.

Fix: keep the row sticky (only update it when `n >= 3`) and add a real page
cache (`cached_page`/`cache_valid` in the device struct) so a `DATA_IN` without
a fresh row reuses the page already in `pagebuf`. The cache is invalidated on
erase/program.

On top of that, reads are **self-verifying**: each page is read twice and the
two copies must agree, retrying on disagreement (`SPIFC_READ_RETRIES = 6`).

Result — three reads of the same 1 MiB, and a host comparison:

```
ed1f3e0efee8ee259247501dd6c013b0     <- read 1
ed1f3e0efee8ee259247501dd6c013b0     <- read 2
ed1f3e0efee8ee259247501dd6c013b0     <- read 3
ed1f3e0efee8ee259247501dd6c013b0     <- host md5 of the flashed image
```

Deterministic **and** byte-exact. Functional proof, mounting the NAND squashfs
and running a binary out of it:

```
MOUNT_OK
bin dev etc init lib mnt overlay proc rom root sbin sys tmp usr var www
EXEC_FROM_NAND_OK
```

### Remaining

Booting entirely from flash still hits occasional
`SQUASHFS error: Unable to read fragment cache entry` under the heavier
mount-root workload — the verifier is detecting corruption it cannot always
resolve within 6 attempts. Next: raise the retry budget (each retry is cheap now
that timeouts are 100 ms) and chase the residual controller flakiness in the
FIFO drain.

## ✅ Round 18: OpenWrt BOOTS FROM NAND TO A SHELL

Final piece: on a verify mismatch the driver now forces the controller reset
path (`sp->wedged = true`) before retrying, instead of re-reading the same
corruption, and the retry budget went 6 → 12 (cheap at 100 ms timeouts).

Validation of the read path under load, from a live shell, reading **every file**
in the NAND squashfs:

```
# find /mnt -type f | wc -l          -> 936
# find /mnt -type f -exec cat {} + > /dev/null 2>/tmp/e
CAT_DONE rc=0
# wc -l < /tmp/e                     -> 0        (zero errors)
```

Full autoboot from flash, no TFTP and no initramfs:

```
zteboot_verify_kernel:175 verify kernel success!!
zteboot_verify_fs:242     verify fs success!!
Total found 2 firmwares(valid:2), start from ver 0
zteboot_do_settings: select=0
   Image Name:   h199a-openwrt
[ 7.52] 9 fixed-partitions partitions found on MTD device 94406000.spifc
VFS: Mounted root (squashfs filesystem) readonly on device 31:7
init: Console is alive
kmodloader: ... done

root@OpenWrt:~# echo NAND_BOOT_SHELL_OK; uname -a; df -h /
NAND_BOOT_SHELL_OK
Linux OpenWrt 6.6.151 #30 armv7l GNU/Linux
overlayfs:/tmp/root      59.5M     36.0K     59.4M   0% /
```

Zero `SQUASHFS error` lines in that boot. The `kmodloader: N modules could not
be probed` entries are expected and harmless — they are the armsr stock drivers
(atlantic/ena/stmmac/vmxnet3) missing `bpf_*` symbols after the size trim, none
of which exist on this SoC.

**Driver status: read ✅ write ✅ erase ✅ partitions ✅ boot-from-NAND ✅.**
The spifc NAND objective is complete. HW BCH ECC remains unimplemented but is
*not* required for correctness — with the row bug fixed, raw reads are byte-exact
against the host image; ECC is only worth adding later for long-term bit-rot.


## Function map (vmlinux vaddrs, Linux 4.1 stock)

| vaddr | symbol (string-trace) | role |
|---|---|---|
| 0xc0208a90 | `spifc_read_fifo` | FIFO read helper |
| 0xc0208be0 | `spifc_write_fifo` | FIFO write helper |
| 0xc0208be4 | — | spifc **command dispatch** (r2 = opcode: 0x19, 0x11, 0x18, 0x0E, 0x02, …) |
| 0xc0208b20 | — | FIFO read into buffer (loop until len 0) |
| 0xc020894c | — | post-command setup |
| 0xc0209dc8 | — | command wrapper (lock + trigger + poll 0x2c) |
| 0xc0209f04 | — | lock/irq-save helper |
| 0xc020a000 | — | generic cmd exec (cmd 0x19 = PROG LOAD RANDOM?; FIFO-TX data path via 0xc0208b20) |
| 0xc020a108 | — | generic cmd exec (cmd 0x11 = **PROGRAM EXECUTE**): dispatch + INIT|0x1c440 + ECC + trigger + poll |
| 0xc020a1a0 | `spifcnand_nand_write_page_pre` | **write page**: WREN wrapper (0xc0209dc8 cmd 1) → PROG LOAD w/ data (0xc0209fdc) → PROGRAM EXECUTE (0xc020a108) → FIFO verify (0xc0209244) |
| 0xc020a2b4 | — | generic cmd exec (cmd 0x02 = **BLOCK ERASE**): dispatch + INIT|0x1c440 + ECC + trigger + poll |
| 0xc0209fdc | — | PROG LOAD data path (FIFO TX, multi-chunk loop; ECC path via 0xc0208838 if [dev+0x618]) |
| 0xc020a34c | `spifcnand_nand_int`-ish | **SPI cmd emulator**: 0x90=READ ID, 0xFF=RESET, 0x60; READ ID reads 2 bytes → device+manu ID |
| 0xc020a4ec | — | **chip init**: ID dispatch (0xEF Wb, 0x2C24 Micron, 0xE5, 0x72BA, 0x26C2, 0xE5A1) → per-manu ECC table (0x110-byte descriptors @0xc0430210) |
| 0xc020ab1c | `spifcnand_nand_read_page` | **page read**: issue → FIFO → ECC bit-flip count loop → retry/status |
| 0xc020aa68 | — | read-page command sequence (0x9f04→0x8fb8→0x9244→0x9050→0x9c68) |

### Read-page sequence (0xc020ab1c, decoded)

1. lock (0xc0209f04)
2. 0xc0208fb8 — issue page-read command
3. 0xc0209244 — FIFO read of data+OOB into buffer @priv+0x380
4. 0xc0209050 — ECC decode
5. 0xc0209c68 — ECC/fifo post-process (spifc_read_fifo)
6. bit-flip verification loop (0xc020ad20: XOR two buffers, count set bits
   per byte → bitflips; compares against ECC strength; retries via 0xc0208580)

The 0x110-byte-per-entry flash descriptor table (base 0xc0430210) holds
{device-id, manu-id, ecc strength, step size, …} per supported chip — the
Micron 0x2C/0x14 entry is what our H199A uses.

## Plan (from-scratch driver, no prior art)

Phase 1 — **READ-ONLY** (highest value, enables dump re-verify + jffs2 read):
1. Trace `spifcnand_nand_read_page` fully: command sequence (page read via
   FIFO), how the 0xd80000 window is enabled, OOB/ECC layout.
2. Minimal MTD `nand_controller` driver: read_page using the FIFO + skip/
   soft-ECC initially (verify against the known-good dump byte-for-byte).
3. Add HW ECC decode once the BCH register semantics are clear.

Phase 2 — write/erase (sysupgrade): `spifcnand_nand_write_page_pre` + erase
sequence, bad-block management (stock prints "spifc fail to insert oob page").

Phase 3 — integrate partitions (mtd0-bootloader … mtd8-rootfs2, see
`../h199a-firmware/PARTITIONS.md`), then a flashable sysupgrade image.

Effort: Phase 1 ≈ 1–2 focused days of RE; Phase 2/3 ≈ several days more.
This is the largest single remaining piece of the port.


## The stock Linux driver is interrupt-driven (round 63)

Our driver busy-polls the FIFO status register for every one of the 528 words in
a page. That is why the second CPU breaks it: the CPU must keep pace with the
controller and IPI latency makes it miss (see docs/BRINGUP.md rounds 57-62).

The stock kernel does it differently. Its symbol table contains:

```
spifcnand_nand_read_page
spifc_read_fifo      spifc_write_fifo
spifcnand_nand_int          <-- interrupt handler
spifcnand_nand_wait         spifcnand_nand_wait_common
```

So the vendor driver still uses the FIFO (no DMA engine), but drives it from an
**interrupt** rather than a poll loop. The DT already carries the line, and our
node declares it too:

```dts
/* stock */  interrupts = <0x00 0x0d 0x04>;
/* ours  */  interrupts = <GIC_SPI 13 IRQ_TYPE_LEVEL_HIGH>;
```

The driver was located at **`0xc0208260`** (platform_driver probe, found via the
`of_device_id` table at `0xc0430084` referenced from `0xc05c701c`), and
`spifcnand_nand_wait_common` suggests the wait path is a completion woken by the
handler.

### Why this matters

An interrupt-driven FIFO path removes the CPU from the tight polling loop and is
the architecturally correct fix for the SMP corruption — better than the
`local_irq_save()` experiment of round 62, which reduced errors (34 -> 21) but
was unsafe.

### What is still needed

The interrupt **enable** and **status** register bits are not yet identified.
`0x94406000 + 0x2c` is the status register we already poll (bit0 done, bit1
busy); whether the same register gates the interrupt, and which bit enables it,
has to come from `spifcnand_nand_int` and the probe's register writes. That is
the next concrete RE task before any code change.


### Round 64: the interrupt line is wired but masked

The driver now claims SPI 13 (diagnostic handler that only counts). Results on
hardware:

```
zx-spifc-nand 94406000.spifc: claimed irq 26 for diagnostics
zx-spifc-nand 94406000.spifc: spifc irq fired 0 times during nand_scan
 26:  0  GIC-0  45 Level  zx-spifc          <- /proc/interrupts
```

So the routing is correct (Linux IRQ 26 -> GIC 45 = SPI 13 + 32) but the
controller never asserts the line with our current programming: **interrupts are
masked**, and an enable bit we do not set is missing.

### Full register block (read after nand_scan)

```
+00 = 01040000      <- previously unknown
+08 = 00000003      ctrl
+0c = 00010440      init
+10 = 00000016      cfg
+14 = 00001024      cfg2
+18 = 0000083f      count (n-1)
+20 = 0000003b      opcode
+24 = 00000889      <- previously unknown
+2c = 000000c1      status
+34 = 00100020      fifo status
```

Two registers had never been identified: **`+0x00`** and **`+0x24`**.

Tried and rejected: writing `0xffffffff` to `+0x24`. It is writable (reads back
`0x000039cf`, so bits 0-3, 6-8, 11-13 exist) but interrupts still did not fire,
so it is not the interrupt enable.

Remaining candidate: **`+0x00`** (reads `0x01040000`). That is the next thing to
try, followed by locating `spifcnand_nand_int` properly in the stock image.

The diagnostic IRQ claim is left in place — it is harmless (the line never
asserts) and is the foundation for converting the read path once the enable bit
is known. Verified after cleanup: 0 SQUASHFS errors, 9 MTD partitions, ping 0%
packet loss.


### Round 65: hunting the interrupt enable — three dead ends

| candidate | result |
|---|---|
| `+0x00` (reads `0x01040000`) | **read-only** — writing `0xffffffff` leaves it unchanged. An ID/capability register, not control. |
| `+0x24` (reads `0x00000889`) | writable (`0xffffffff` -> `0x000039cf`) but enabling every bit does not make SPI 13 assert. |
| zero-reading offsets `0x28`, `0x3c..0x7c` | **HANGS THE CONTROLLER.** Writing `0xffffffff` to them faulted the probe (`PC is at zx_spifc_probe+0x2e4`) and it never returned. |

The reasoning behind the third attempt was sound — an interrupt-enable register
reads 0 while masked, so it would not appear in a non-zero dump — but this
controller does not tolerate blind writes. **Do not probe unknown spifc
registers by writing to them.**

Conclusion: the interrupt enable must be recovered from the stock driver
(`spifcnand_nand_int` and the probe path at `0xc0208260` / `0xc020a4ec`), not by
experiment on the hardware.

State after reverting: 9 MTD partitions, `ping` 0% packet loss, driver otherwise
unchanged.


## Round 87: the intermittent boot failures are silent read corruption (no ECC)

Three different causes have been asserted for the recurring "boots but userspace
is broken" failure: NAND wear (round 85), overlay/JFFS2 corruption (round 86).
Both are wrong. The evidence, captured before reflashing:

```
/etc/preinit: line 37:  mount_root: No error information
/etc/preinit: line 530: cat: No error information
/etc/preinit: line 18:  uci: No error information
/etc/preinit: line 188: grep: No error information
SQUASHFS errors: 0
```

`mount_root` fails **at line 37, before any overlay is mounted**, and so do
`cat`, `grep` and `uci` — all base binaries in the read-only squashfs. Every
executable fails while SquashFS reports zero errors.

That combination has one explanation: **the data read back is wrong, and nothing
detects it.** SquashFS only reports an error when decompression fails outright; a
handful of flipped bits inside an already-decompressed block produce a corrupt
ELF that simply will not run.

### This was predicted at bring-up

The kernel says so on every boot:

```
nand: NAND_ECC_ENGINE_TYPE_NONE selected by board driver. This is not recommended!
nand: WARNING: the ECC used on your system (0b/2048B) is too weak compared to
      the one required by the NAND chip (8b/1024B)
```

The chip requires 8-bit-per-1024-byte correction and we provide none. Reads that
are *mostly* right have been good enough to boot for most of this bring-up, which
is exactly why it looked intermittent and got mis-attributed twice.

Reflashing "fixes" it because it rewrites the affected pages, not because it
repairs an overlay.

### Consequence

**HW BCH ECC is no longer a nice-to-have.** It was listed as a long-term item;
it is in fact required for the flash boot to be dependable, and it is now the
main source of noise in every other experiment - a failed boot has to be
distinguished from a genuine regression before any conclusion can be drawn.


## Round 89: the silent corruption was a stale CHIP cache, and it is fixed

### Root cause

The driver verified reads by reading the same page twice and requiring the two
to agree. Those two reads are **not independent**. The Micron chip holds one page
in an internal cache; a `PAGE READ` (0x13) transfers array -> cache, and the
driver then streams the cache out over the FIFO.

If the `PAGE READ` command does not take effect, the chip simply stays idle with
the **previous** page still in its cache. `OIP` reads clear immediately (the chip
is not busy - it never started), the readiness wait is satisfied, and both
"verification" reads stream out the same stale page. The result is valid,
well-formed data from the wrong offset, which:

- decompresses fine, so **SquashFS reports zero errors**, and
- produces binaries that will not exec (`mount_root: No error information`).

That is exactly the failure that has been misdiagnosed three times in this
project (NAND wear, JFFS2 overlay, ECC).

The readiness wait already required seeing ready twice in a row, but it never
required seeing the chip **busy** first, so a command that never executed was
indistinguishable from one that completed instantly.

### Fix

Make the two verification reads genuinely independent by forcing the chip cache
to be reloaded between them:

```c
read(page,     buf);
read(page ^ 1, vbuf);   /* evict: any other page will do */
read(page,     vbuf);
if (!memcmp(buf, vbuf, ...)) return 0;
```

If the second read of `page` still matches, the data demonstrably came from the
array and not from a cache that never changed.

### Result

Four consecutive cold boots from flash:

```
boot1: squashfs=5  preinit_fail=0  shell=ok
boot2: squashfs=0  preinit_fail=0  shell=ok
boot3: squashfs=0  preinit_fail=0  shell=ok
boot4: squashfs=0  preinit_fail=0  shell=ok, ping 4/5
```

Previously this failure hit roughly every other boot. Cost is three array reads
per page miss; the driver-side page cache was restored (round 88 proved it was
not the cause) so the OOB fetch does not repeat the work.

### Note on the ECC conclusion from round 87

Round 87 concluded the corruption was uncorrected bit rot because the chip needs
8b/1024B ECC and we provide none. That reasoning was plausible but wrong as the
explanation for *this* failure - the data was never corrupt on the flash, it was
the wrong page. ECC is still worth having, but it is no longer the top defect.


## Round 90: the round-89 fix is a partial mitigation, measured

Round 89 claimed the boot-reliability problem was fixed on the strength of four
clean boots. The scheduled review called that overclaimed and asked for a proper
sample. Seven cold boots of the same image:

| boot | result |
|---|---|
| 1 | clean, shell responsive, ping 0% loss |
| 2 | clean, shell responsive, ping 0% loss |
| 3 | clean, shell responsive, ping 25% (ARP warm-up) |
| **4** | **kernel panic in userspace, reboot, halted** |
| 5 | clean, shell responsive |
| 6 | clean, shell responsive |
| **7** | **hung — no response on the console at all** |

**5/7 clean, ~29% failure rate.** Before the round-89 change it was roughly 50%,
so the evicting-read verification helps materially but the problem is **not
fixed**. The claim is downgraded accordingly.

Note also that the two failures had *different* signatures (panic vs hang),
which is further evidence for the review's point that more than one mechanism is
in play:

1. **stale chip cache** — mitigated in round 89 (this is the part that improved);
2. **non-deterministic reads** — three reads of one region once produced three
   different md5s; a stale cache is deterministic, so this is a separate fault
   and the evicting-read does not catch it;
3. **SMP FIFO underrun** — rounds 62-63, scales with CPU count, untouched.

Only (1) has a mitigation. Chasing (2) is the next NAND task: it is the one that
can still hand back arbitrary wrong data with no error reported.


## Round 93: review corrections, the on-die ECC experiment, and corrected chip facts

### Review corrections (red-team)

- **"Non-deterministic reads" is a dead bug, not a live mechanism.** The
  three-different-md5s observation dates from round 15; the driver was fixed
  afterwards (three identical, byte-exact md5s are recorded later in this very
  file), and nothing since has re-demonstrated nondeterminism. Rounds 90-92
  listed it as an unmitigated mechanism - that was reciting history as if it
  were current. The `zx_spifc_nand.c` comment written in the present tense has
  been superseded.
- **The driver has no bad-block handling at all** - no BBT, no ooblayout, no
  isbad checks - on a part whose datasheet guarantees only 1004/1024 blocks and
  ships with factory-marked bad blocks (round 15 recorded one). This is the
  top-ranked hypothesis for the residual ~25% failures, ahead of the barely
  tested write path (which rewrites the JFFS2 overlay every boot).

### Corrected chip facts (Micron M78A datasheet + mainline micron.c)

| premise held since bring-up | actual |
|---|---|
| OOB is 64 bytes (page 2112) | **OOB is 128 bytes (page 2176)** |
| required ECC is 8b/1024B | **8b/512B, 4 sectors/page** |
| we run with "no ECC" | **ECC_EN powers up SET; a driver that never touches 0xB0 runs WITH on-die ECC** |

Our driver *does* clear ECC_EN per read, so we genuinely read raw - but the
"no ECC" state was an active choice of the vendor design, not an omission:
U-Boot's spifc driver also writes raw.

Feature 0xC0 ECC status bits [6:4]: 000 = clean, 001/011/101 = 1-3/4-6/7-8 bits
corrected, **010 = uncorrectable**. (Matches micron_8_ecc_get_status.)

### On-die ECC: tested and NOT usable with the existing flash content

Leaving ECC_EN set (the chip default) and decoding status:

- one page reported corrected bits (the decode works), then
- `nand_scan failed (-5)` - almost every page reports uncorrectable, because
  **everything on this flash was written raw**, so the parity area contains no
  valid parity.

Conclusion: raw-write/raw-read is self-consistent and is what both U-Boot and
this driver do. On-die ECC would require rewriting the entire flash with ECC
enabled, including everything the bootloader writes - not viable while U-Boot
remains the flashing tool. Reverted, with the reasoning in the source.

### Infrastructure note (cost half the round)

`tftpd-hpa` died mid-flash and the host interface lost its address. U-Boot's
tftp then timed out (`Loading: *T T T...`) and the subsequent `nand write`
wrote stale RAM as the bank-A header -> CRC fail -> silent stock-firmware
fallback. Recovery: restart tftpd, re-add the address, re-transfer (verify
`Bytes transferred`!), reflash header. **Lesson: always check for
`Bytes transferred` after every tftp, not just `bytes written` after nand
write.** Also: the UART logger had died silently; commands sent to the board
were flying blind. Check both before interpreting any "failure".

### New observation on the RX latency gap

This round's cold flash boot shows **8.3 ms average RTT** - the same as a
bootloader-initialised boot - where round 91's cold boots showed 264-381 ms.
The "40x cold-init latency gap" is therefore NOT a fixed property: some cold
inits produce a fast datapath, some a slow one. Whatever differs is
per-boot-nondeterministic, not a missing constant.


## Round 94: both leading hypotheses for the residual failures eliminated

### Bad blocks: not the cause

The red-team review ranked "no bad-block handling" as the top hypothesis. It is
wrong on both halves:

- `nand_scan()` **does** build a RAM BBT - the boot log shows
  `Scanning device for bad blocks` and the scan completes (it takes ~12 s,
  because our read path does three array reads per page).
- The device reports **zero** bad blocks:

```
dmesg | grep -i "bad eraseblock"   -> (nothing)
/sys/class/mtd/mtd7/bad_blocks     -> 0
/sys/class/mtd/mtd7/bbt_blocks     -> 0
```

(The `nand_bbt: can't scan flash and build the RAM-based BBT` message that
prompted this hypothesis came from the **ECC-enabled** boot, where every page
read failed - not from a normal boot.)

An `ooblayout` and explicit BBT options are still worth adding for correctness,
but bad blocks do not explain the residual ~25% boot failures.

### The write path is not being exercised either

```
mount | grep overlay
overlayfs:/tmp/root on / type overlay (rw,noatime,
             lowerdir=/,upperdir=/tmp/root/upper,workdir=/tmp/root/work)
```

The overlay is **tmpfs**, not the JFFS2 `rootfs_data` partition - OpenWrt failed
to bring up persistent storage and fell back to RAM. So Linux is not writing to
NAND on every boot, which removes the "overlay rewrites corrupt the flash"
hypothesis as well.

This is worth fixing in its own right: **configuration does not persist across
reboots** on the current image. That is a functional gap for a router, separate
from the corruption question.

### Where that leaves the residual failures

Eliminated so far: bad blocks, overlay/write-path wear, non-deterministic reads
(a dead bug), on-die ECC (unusable, flash is written raw), SMP FIFO underrun
(not applicable at `maxcpus=1`), and the driver page cache (round 88).

Still standing: the round-89 stale-chip-cache mitigation is **incomplete** - it
detects "same stale page twice" and retries, but does not address why a
`PAGE READ` sometimes fails to take effect in the first place. That remains the
best-supported explanation and the next thing to attack directly, e.g. by
requiring the readiness wait to observe the chip BUSY before accepting it as
ready.


### Busy-observation fix: implemented, did NOT help

The readiness wait accepted "OIP clear twice" without ever confirming the chip
had gone busy, so a `PAGE READ` that never executed was indistinguishable from
one that finished instantly. That is logically unsound, so the wait now records
whether OIP was ever observed set and, if not, re-issues the PAGE READ once.

Measured over four cold boots: **2/4 clean**, against 5/7 for the previous
build. The samples are too small to separate, but there is certainly no
improvement. The change is kept because the previous logic was genuinely wrong,
not because it fixed anything.

So the residual failure rate (~25-50%) is still unexplained after eliminating:
bad blocks, overlay/write-path wear, non-deterministic reads, on-die ECC, SMP
FIFO underrun, the driver page cache, and now the missing busy-observation.

### Tooling loss and recovery

`/tmp/h199a-rootfs-nopppoe.img` - the pppoe-free rootfs used for every flash -
was removed by tmp cleanup, and its absence broke a shell `&&` chain so a whole
flash sequence silently did nothing (`$P: ambiguous redirect`). Regenerated from
`build_dir/.../root-armsr` with:

```
cp -a root-armsr /tmp/h199a-root
rm -f  /tmp/h199a-root/usr/sbin/pppd /tmp/h199a-root/usr/sbin/pppoe-discovery
rm -rf /tmp/h199a-root/usr/lib/pppd /tmp/h199a-root/etc/ppp
rm -f  /tmp/h199a-root/lib/netifd/proto/ppp.sh
mksquashfs4 /tmp/h199a-root /tmp/h199a-rootfs-nopppoe.img -nopad -noappend \
  -root-owned -comp xz -Xpreset 9 -Xe -Xlc 0 -Xlp 2 -Xpb 2 \
  -Xdict-size 256K -Xbcj arm -b 256k
```

**Build artefacts needed for flashing must not live only in /tmp.**


## Round 95: health counters largely EXONERATE the NAND read path

Instrumented the driver and printed counters every 20 s. Three consecutive cold
boots of the same image:

```
boot1 (shell OK)     reads=5822 retry=33 mismatch=2 wedge=98 nobusy=348 fail=0
boot2 (shell DEAD)   reads=5557 retry=34 mismatch=0 wedge=75 nobusy=324 fail=0
boot3 (shell OK)     reads=5668 retry=34 mismatch=0 wedge=82 nobusy=312 fail=0
```

Two things follow immediately:

1. **`fail=0` on every boot, including the failing one.** No page read ever
   exhausted its retries and returned an error. Every read that completed was
   verified by two independent reads with a cache-evicting read between them.
2. **The failing boot had FEWER anomalies than a working one** - zero verify
   mismatches against boot1's two, and fewer wedges.

So the boot failures do not correlate with NAND read trouble at all. After seven
eliminated hypotheses, this is the strongest evidence yet that **the NAND read
path is not what is breaking these boots**, and that rounds 89-95 have been
chasing the wrong subsystem.

### What the counters DO reveal

`wedge=75-98` and `nobusy=312-348` **per boot** are large numbers that had never
been measured. The controller wedges ~90 times per boot - each one triggering a
controller disable, chip RESET and re-init - and ~330 PAGE READs complete without
OIP ever being observed. Neither is fatal (recovery works, `fail=0`), but both
say the controller is being driven in a way it does not like. Worth fixing on
its own merits; not the boot-failure cause.


## Round 97: erase was broken by a bogus status byte — fixed; and why config still cannot persist

### The bug: no NAND_CMD_STATUS handler

`mtd erase rootfs_data` failed:

```
Failed to erase block on rootfs_data at 0xa00000
Failed to erase block on rootfs_data at 0xa20000
```

The erase itself was fine. The driver had **no `NAND_CMD_STATUS` case in
`exec_op`**, so when nand_base issued STATUS followed by a one-byte read, the
read fell through to the *page-read* path and returned **page data as the status
byte**. Whenever that byte happened to have bit 0 set, nand_base read it as
`NAND_STATUS_FAIL` and reported an erase failure.

The two status encodings are unrelated:

| bit | ONFI status (what nand_base expects) | SPI-NAND feature 0xC0 |
|---|---|---|
| 0 | FAIL | OIP (busy) |
| 2 | - | E_FAIL |
| 3 | - | P_FAIL |
| 6 | READY | ECCS2 |
| 7 | WP# | CRBSY |

Now synthesised properly: `WP#` always set, `READY` from `!OIP`, `FAIL` from
`E_FAIL | P_FAIL`. After the fix `mtd erase rootfs_data` completes with no
errors at all.

This also means every erase and program this driver has ever done was being
status-checked against page contents - it is a wonder writes worked as well as
they did.

### But config persistence needs more than a working erase

Erasing `rootfs_data` made the board fall back to **stock firmware** on the next
boot. The reason is structural:

```
mtd7  rootfs        0x00d20000   <- bootloader CRCs this ENTIRE partition
mtd8  rootfs_data   0x00a40000   <- lives INSIDE it (squashfs-split)
```

The vendor image header carries a CRC over the whole rootfs partition, and the
bootloader validates it on every boot. OpenWrt's overlay lives in the tail of
that same partition, so **any write to the overlay invalidates the CRC** and the
bootloader rejects the bank. (Round 86 hit the identical trap from the other
direction.)

So persistence needs one of:

1. shorten the CRC'd length in the header to cover only the squashfs, leaving
   the `rootfs_data` tail outside it - `flash-prep.py` writes that length at
   header `+0x40`, but the same value appears to determine where the bootloader
   expects the header, so this needs care; or
2. move the overlay to a partition outside the CRC - `usercfg` (mtd4, 2 MiB) or
   `defcfg` (mtd5, 2 MiB) are the obvious candidates and are what the vendor
   firmware uses for configuration.

Option 2 is almost certainly the right answer and matches the vendor layout.

Bank A restored and re-verified after the experiment: boots clean, 9 partitions,
ping works.


## Round 98: overlay relocated and four blockers fixed; write path proven broken

Config persistence turned out to be blocked by a chain of five separate
problems. Four are fixed.

### 1. Overlay was inside the CRC-protected partition (fixed)

OpenWrt's `squashfs-split` carved `rootfs_data` out of the tail of `rootfs`,
which the bootloader CRCs in full - so any overlay write made the board fall
back to the stock bank.

Fixed by giving the overlay its own partition **outside every CRC**. The factory
dump is erased from `0x3040000` to the end of the 128 MiB device (last vendor
data is bank B's header at `0x3020000`), so:

```dts
partition@4000000 { label = "rootfs_data"; reg = <0x4000000 0x1000000>; };
```

and `# CONFIG_MTD_SPLIT_SQUASHFS_ROOT is not set` so no competing split is made.

### 2. Erase reported failure (fixed, round 97)

The missing `NAND_CMD_STATUS` handler returned page data as the ONFI status byte.

### 3. No OOB layout (fixed)

`mtd->oobavail` was 0, and JFFS2 needs OOB room for cleanmarkers. Added an
`mtd_ooblayout_ops` reserving the bad-block marker bytes and exposing the rest;
`oobavail` is now 62.

### 4. The chip was detected as MLC (fixed)

```
nand: 128 MiB, MLC, erase size: 128 KiB
```

Our ID-table entry has `id_len = 2`, so nand_base fell back to reading
`id_data[2]` as the ONFI cell-info byte. READID returns `2c 14 2c 14`, so it saw
`0x2c` and computed `((0x2c >> 2) & 3) + 1 = 4` bits/cell. **JFFS2 refuses to
mount an MLC NAND**, failing with `-EINVAL` on a perfectly erased partition.

Fixed with an `attach_chip` callback that forces `bits_per_cell = 1` before
`nand_scan_tail()` derives `mtd->type`. After this:

```
zx-spifc-nand: correcting cell type: 4 bits/cell -> 1 (SLC)
mount_root: switching to jffs2 overlay
/dev/mtdblock10 on /overlay type jffs2 (rw,noatime)
overlayfs:/overlay on / ... upperdir=/overlay/upper
```

The root overlay is now on real flash instead of tmpfs.

### 5. The write path does not work (OPEN - this is the remaining blocker)

Files still do not survive a power cycle. Tested at the raw MTD level, bypassing
the RW-cached `mtdblock` device:

```
mtd erase rootfs_data
dd if=/dev/urandom of=/tmp/pat bs=2048 count=1 ; md5sum /tmp/pat
dd if=/tmp/pat of=$(SEED) bs=2048 count=1   # SEED from a label lookup - see the banner
dd if=$(SEED) of=/tmp/rb  bs=2048 count=1 ; md5sum /tmp/rb

written:   0f271f5d0aeb95fb3f80030195390ffa
read back: e0deebd3c3f560212af17c68b9344bae
```

**Programming does not land.** Note this also invalidates an earlier
umount/remount test that appeared to show durable writes - that was served from
the `mtdblock` cache, exactly the trap recorded in the early rounds.

The program path has never been exercised in anger: everything on this flash was
written by U-Boot, and until round 97 the driver's own status checks were
reading page data. Fixing `zx_spifc_program_page()` is now the single blocker
for configuration persistence.


## Round 99: RETRACTION — the write path works; round 98's test was invalid

Both reviewers independently identified the flaw, and the evidence confirms it:
`/dev/mtdblock10` was **mounted as the live JFFS2 root overlay** while I raw-wrote
to it, and the erase in that test had its output discarded.

The decisive tell was already in my own data: the read-back md5
`e0deebd3c3f560212af17c68b9344bae` was **identical** in both the random-pattern
and the busybox-page tests. I was reading JFFS2's data, not my writes. NAND
programming can only clear bits, so writing into non-erased content yields
`pattern AND existing` - neither the pattern nor `0xff`, exactly what I saw.

Redone properly (partition unmounted, erase verified, blank state confirmed):

```
umount /overlay
mtd erase rootfs_data                 -> no failures
dd if=/dev/mtd10 bs=64 count=1        -> all ff
dd if=/bin/busybox of=/tmp/pv bs=2048 count=1
dd if=/tmp/pv of=/dev/mtd10 bs=2048 count=1
dd if=/dev/mtd10 of=/tmp/rv bs=2048 count=1

/tmp/pv  911408227b2f6a2a9465199ba590a9c0
/tmp/rv  911408227b2f6a2a9465199ba590a9c0
```

**Program, erase and read all work correctly** on structured data. The round-98
conclusion is withdrawn.

### Defects the review found anyway (worth fixing, not yet done)

- `zx_spifc_write_page()` triggers the transfer **twice** - at word 15 and again
  after the fill loop. The stock flow triggers once.
- **No P_FAIL check**: the write path ends in `zx_spifc_wait_ready()`, which
  polls only OIP. Feature `0xC0` bit 3 is never examined, so a chip-reported
  program failure returns success. The round-97 ONFI status work never reached
  this path.
- Only 2112 of the chip's 2176 page bytes are programmed (`SPIFC_OOB_SIZE` is
  still 64 where the die has 128).
- The round-20 write self-test reads back **into the same buffer holding the
  pattern** and ignores the read's return value, so a failed read still prints
  `WRITE selftest: OK`. It proved less than it appeared to.

### Config persistence: still failing, and now bounded

With the overlay on flash (`upperdir=/overlay`, `mount_root: switching to jffs2
overlay`), a file written and `sync`ed still does not survive a power cycle.

Since raw MTD program/read is now proven correct, the remaining suspect is the
**JFFS2-on-NAND usage pattern versus this die's NOP limit**: the datasheet is
explicit that "only one partial-page program is allowed on a single page", and
JFFS2 writes data pages and cleanmarkers separately. That would corrupt on the
second program of a page without any error being reported.

Per both reviewers' explicit advice this is where I stop: the device boots
reliably (6/6 since round 96) and networks at ~9 ms RTT without persistence, and
Wi-Fi and SMP remain untouched at round 99. Documented as a known gap.


## Round 109: a larger rootfs exposes read failures at higher offsets

Adding mt76 grew the squashfs from ~3.0 MB to ~4.7 MB. The image flashes
cleanly - all three writes report OK and every TFTP transfer is verified - but
the board now fails to boot:

```
SQUASHFS error: Unable to read metadata cache entry [484700]
SQUASHFS error: Unable to read inode 0xf33
SQUASHFS error: Unable to read directory block [481fb8:49e]
```

Two consecutive boots failed the same way (6 errors, then stock fallback).

**The failing offsets are ~0x481fb8-0x484700, i.e. right at the end of the new
4.7 MB rootfs and well beyond the 3.0 MB the previous image ever touched.** In
absolute flash terms that is around `0xa00000 + 0x484700 = 0xe84700`.

This is important and was previously invisible: **every earlier "NAND reads are
byte-exact" result was measured over a region the small rootfs happened to
cover.** The read path may well be failing at higher offsets, and nothing until
now exercised them.

### Next step (cheap and decisive)

TFTP-boot a known-good kernel and read the whole `rootfs` MTD partition on the
device, comparing its md5 against the host's copy of the flashed image. That
isolates NAND reads from the boot path entirely and will show whether reads
degrade past a particular offset. If they do, likely suspects are the page/row
address computation at higher rows, or a block the BBT should have excluded.

### Status of the Wi-Fi work

Unaffected and complete up to this point: `pcie-zx279128.c` is in the recipe with
its Kconfig/Makefile patch, `CONFIG_PCIE_ZX279128=y`, and the full OpenWrt build
produces `mt76.ko`, `mt7615e.ko`, `mt76-connac-lib.ko` plus the correct MT7663
firmware (`mt7663pr2h_rebb.bin`, `mt7663_n9_rebb.bin` - note `kmod-mt7615-firmware`
does NOT ship these; `kmod-mt7663-firmware-ap` is required). Whether mt76 binds
cannot be tested until the rootfs boots.

### Build note

`CONFIG_TARGET_ROOTFS_INITRAMFS=y` means `build_dir/.../arch/arm/boot/zImage` is
the **initramfs** kernel (7.1 MB, far too large for the 3 MB partition). The
plain kernel is `bin/targets/armsr/armv7/openwrt-armsr-armv7-generic-kernel.bin`
(2.65 MB). Use that one for flashing.


## Round 110: the read defect is ACCESS-PATTERN dependent, not address dependent

Ran the decisive isolation this round, using the **initramfs kernel over TFTP**
so the test does not depend on NAND at all.

### 1. Our driver misreads; the flash is fine

Per-MiB checksums of the `rootfs` partition against the host image:

| chunk | host | device |
|---|---|---|
| 0-3 | match | match |
| 4 (part 0x400000) | `0393fec4...` | `271135ec...` |
| 5 | `b6d81b36...` | `361536fb...` |

U-Boot reads the same region **correctly**:

```
U-Boot  @0xe00000 : ab039807 55b53a21 2f89a2b9 61d12cfa
host    @0x400000 : ab039807 55b53a21 2f89a2b9 61d12cfa   <- match
```

So the data on flash is right and **the Linux driver is misreading it**.
`nand bad` reports **no bad blocks**, which kills the "U-Boot skips bad blocks,
we do not" hypothesis.

### 2. It is not an address boundary - it is the access pattern

Reading the *same* region block by block gives **correct** data everywhere,
including the block that fails inside a larger read:

```
blk28..blk35 (part 0x380000..0x460000)  -> all 8 match the host exactly
blk32 alone                             -> 3172ffb47ea06146   CORRECT
```

but the moment those blocks are read as one stream:

```
dd bs=1048576 skip=4          -> 271135ec3975a4cc   WRONG
8x dd bs=131072 (one pipe)    -> 271135ec3975a4cc   WRONG
dd bs=4096 count=256          -> 271135ec3975a4cc   WRONG
```

**A single short read is correct; a continued read drifts.** That is why every
earlier byte-exactness measurement passed: they were single reads of a region
the small rootfs happened to cover.

### 3. Prime suspect

The only state that persists between reads is the driver page cache:

```c
u32 target = have_row ? page : sp->cached_page;
```

A `DATA_IN` instruction with no address reuses the previously cached page. That
is correct for the OOB fetch after each page (`nand_read_data_op()` sends
DATA_IN with no address). But if nand_base issues any *continuation* data read
without re-sending the row, this hands back the previous page's bytes - which
produces exactly the observed signature: first page right, subsequent pages
stale, no error reported anywhere.

Next: instrument `have_row`/`page`/`len` per DATA_IN to confirm, then either key
the cache on something that cannot go stale or drop the cache for full-page
reads.


## Round 111: correcting round 110, and a three-way disagreement at the tail of the image

### Correction: round 110's "access-pattern dependent" conclusion was WRONG

Round 110 compared per-block reads of blocks **28-35** against a failing 1 MiB
read spanning blocks **32-39**, and concluded the defect depended on access
pattern rather than address. That was an error of my own making - blocks 36-39
were never checked. Re-tested properly:

| block | part offset | host | device |
|---|---|---|---|
| 34, 35 | 0x440000, 0x460000 | match | match |
| **36** | 0x480000 | `aa67c41a...` | `41d2e2c0...` |
| **37** | 0x4a0000 | `0dfbe8aa...` | `41d2e2c0...` |
| 38 | 0x4c0000 | `0dfbe8aa...` | match |

So it IS address-localised after all, to blocks 36-37, and the SquashFS errors at
`0x481fb8`/`0x484700` fall exactly there. Blocks 36 and 37 also return
**identical** content to each other, which is an aliasing signature.

The DATA_IN/DATA_OUT cursor fix made in this round changed nothing measurable
(chunk4/chunk5 md5s were bit-identical before and after). It is kept because the
old code was still wrong - `nand_read_data_op()` means "continue from the current
position", and copying from a stale `col` every time cannot be right - but it is
**not** the cause of this defect.

### Three readers, three answers

For absolute `0xe80000` (= partition 0x480000, block 36):

| reader | result |
|---|---|
| host image (what we flashed) | `13681cf5 de2607da e27c9ad4 d4f3db34` |
| U-Boot `nand read` | `ffffffff ffffffff ffffffff ffffffff` (erased) |
| our Linux driver | a third value (`41d2e2c0...` block digest) |

U-Boot - the independent reader that read block 32 correctly earlier - says these
blocks are **erased**, i.e. the data never landed, even though
`nand write ... 0xd20000` reported `13762560 bytes written: OK`.

Note also that block 38 reads back as zeros in Linux and matches the host, so
blocks *after* the suspect pair were written. That rules out a simple "write
stopped early" explanation and points at specific blocks being skipped.

The obvious candidate is bad-block skipping: U-Boot's `nand write`/`nand read`
skip blocks marked bad, our driver does not, so a bad block in this region would
shift U-Boot's data relative to ours and leave the block we read as never-written.
`nand bad` printed an empty list, but that listing should be re-checked - it is
the only evidence against this explanation and it is a single observation.

### Next step

Erase the whole rootfs partition, rewrite it, and **verify byte-exactness across
the entire 4.7 MB before attempting to boot** - the mistake this round was
trusting `bytes written: OK` and a partial verification.


## Round 112: THERE WAS NO READ DEFECT - a three-round investigation collapses

The off-cycle review (triggered by my own "3 rounds without a fix" rule) killed
this investigation in one step. The two "mysterious" digests are constants:

```
md5(128 KiB of 0xff) = 41d2e2c0c0edfccf76fa1c3e38bc1cf2   <- "device blk36/37"
md5(128 KiB of 0x00) = 0dfbe8aa4c20b52e1b8bf3cb6cbdf193   <- "host blk37/38"
```

Decoded, my own table says our driver and U-Boot **agree**: blocks 36 and 37 were
simply **erased**. They "returned identical content" because blank blocks are
identical by definition. There was no aliasing, no row-address bug, no stale page
cache, and no three-way disagreement - the "third reader" was the host image,
which is not a reader at all but what we *intended* to write.

Confirmed empirically: after `nand erase` + rewrite, U-Boot reads block 36 as
`13681cf5 de2607da ...` (matching the host), and from Linux every 1 MiB chunk
matches the host image exactly, **including the chunk that previously failed**:

```
c0 998910de  c1 5cf60b37  c2 1097cce2  c3 f356f95b  c4 0393fec4   <- all match
```

### The real defect: a silent write failure

The squashfs ends at `0x48470e`, inside block 36. Block 36 and 37 were blank
while block 38 *was* written - so the erase covered the range and the **program
silently failed on those blocks**. U-Boot's `nand write` does not check the
chip's P_FAIL bit (our own driver did not either until round 100), so it printed
`13762560 bytes written: OK` regardless. Rewriting fixed it.

### Method failure worth recording

I treated md5 digests of unknown NAND regions as opaque identifiers and built
three rounds of investigation on them. **Any digest of a flash region must be
compared against the blank (0xff) and zero (0x00) fill constants before it is
called anomalous.** Round 110's "access-pattern dependent" conclusion and round
111's "three-way disagreement" were both artifacts of skipping that one check.
The round-111 cursor fix was independently correct but was written chasing a bug
that did not exist.

Corollary for the flashing procedure: `bytes written: OK` proves nothing.
**Verify content, not the write call's return value** - and verify all of it.

### Still open

With a current kernel and a verified-correct rootfs, the board now boots to the
**stock** firmware, i.e. the bootloader rejects bank A before OpenWrt runs. The
SquashFS errors are gone, but the bank-A header/CRC now needs checking - the
kernel and header were reflashed together, so the mismatch is likely in the fs
CRC recorded in the header versus what is actually on flash.

### Two corrections from the research agent, worth acting on later

- The verify path's eviction read uses `page ^ 1`, which stays **inside the same
  block**; it should toggle a higher bit (e.g. `page ^ 0x40`) to force a genuine
  reload from a different block.
- The driver reports `NAND_ECC_ENGINE_TYPE_NONE` while reading the chip's ECC
  status manually, so bitflip information never reaches MTD. Declaring
  `NAND_ECC_ENGINE_TYPE_ON_DIE` would let MTD (and later UBI) see real bitflip
  and `-EBADMSG` results.


## Round 113: data proven correct; reads fail under load, not because of content

Two things were established this round, and they separate cleanly.

### 1. The write path really was losing blocks - and a clean cycle fixes it

Verifying the WHOLE partition (not a prefix) showed several silently-failed
regions after the round-109 write:

| chunk | host | device (before) |
|---|---|---|
| c5 | zeros | `361536fb` (wrong) |
| c7, c9, c11 | zeros | match |
| c13 (last 128 K) | zeros | `41d2e2c0` = **erased 0xff** |

After a fresh `nand erase` + `nand write`, the full 13.7 MB partition verifies
**byte-exact from Linux**:

```
device: 06479218fbd4e096abc91bed025e194c
host:   06479218fbd4e096abc91bed025e194c
```

So U-Boot's writer does drop blocks silently (it does not check P_FAIL), and a
repeat cycle can land them. **Always verify the entire image, never a prefix.**

### 2. But the boot still fails - and now it CANNOT be the data

With the partition verified byte-exact, a flash boot still produces 671 SquashFS
errors at exactly `0x481fb8` and `0x484700`. The same kernel/driver reads those
same offsets correctly from an initramfs boot minutes earlier.

So this is **not** a content problem and **not** an addressing problem. The
difference is the operating context:

- initramfs: a single sequential `dd` over an otherwise idle system;
- flash boot: SquashFS demand-paging through `mtdblock` while the rest of
  userspace is starting.

That points squarely at driver robustness under load - the health counters
already showed **~90-130 controller wedges per boot**, each one a poll timeout
plus a chip RESET. If a read exhausts its 12 retries during that churn, the
driver returns `-EIO` and SquashFS reports exactly this.

### Next

Attack the wedge/retry behaviour rather than the data: raise
`SPIFC_READ_RETRIES`, make `zx_spifc_recover()` cheaper and verify it actually
re-establishes a usable state, and instrument how many retries a failing read
actually consumes. The counters exist already (`n_retry`, `n_wedge`, `n_fail`) -
`n_fail` should now be non-zero on a failing boot, which would confirm the path.

### Side finding: initramfs kernel cannot use Ethernet

`zx279128-eth: probe of 92200000.ethernet failed with error -12` (ENOMEM) on the
initramfs build - the ~12.5 MB cpio leaves too little for the driver's
allocations. Not a regression (the plain kernel is fine), but it means the
initramfs test image cannot fetch files over the network; use U-Boot TFTP for
that.


## Round 116: two findings - stock boot destroys our rootfs, and the read failure is context-dependent

### 1. Booting the stock firmware CORRUPTS our rootfs

The rootfs was verified byte-exact in round 113 (`06479218...`). After round 115
- in which bank A was rejected and the **stock firmware booted** - it read back
as `3be22357...`, the same wrong value seen before that repair.

The stock kernel's command line explains it:

```
Linux version 4.1.25 ...
Kernel command line: console=ttyAMA0,115200n8 root=/dev/mtdblock8 ro
                     rootfstype=jffs2 mem=128M
```

In the **stock** partition map `mtdblock8` covers the region we use for our
rootfs, and the vendor system mounts and services it. So every failed boot that
falls back to stock damages our image.

**This explains a great deal of the churn in rounds 109-115**: a failed boot was
not merely a failed boot, it actively corrupted the thing being tested, so the
next attempt started from a worse state. Any experiment that ends in a stock
fallback must be followed by re-verification, and preferably by re-flashing,
before drawing conclusions.

### 2. The read failure is real, and it is context-dependent

With **all three partitions verified byte-exact immediately beforehand**
(kernel `a2337c0b...`, header `b4360016...`, rootfs `06479218...`), a flash boot
still produces ~700 SquashFS errors at exactly `0x481fb8` and `0x484700`.

The same driver reads those same offsets correctly minutes earlier from the
initramfs kernel. So this is neither data corruption nor addressing:

| context | result |
|---|---|
| initramfs, sequential `dd` of the whole partition | correct |
| flash boot, SquashFS demand-paging via `mtdblock` | fails at fixed offsets |

Both offsets sit within the last few KiB of the squashfs image
(which ends at `0x48470e`), so the failing accesses are SquashFS reading its
final metadata and directory blocks - small, random reads near the end of the
image, rather than the large sequential reads the verification path uses.

That difference in *access shape* is the thing to chase: small random reads
exercise the driver's column-change and address-less `DATA_IN` paths (the
`have_row ? page : sp->cached_page` fallback) far more than a linear `dd` does.


## Round 117: small reads are FINE - the tail blocks are being erased by the boot cycle

### Small/random reads are not the bug

Round 116 hypothesised that SquashFS's small random reads exercised a broken
path. Tested directly on the initramfs system, in a region with real data:

| read | device | host |
|---|---|---|
| `bs=512 skip=2048` (page-aligned) | `2172d82670d2` | `2172d82670d2` |
| `bs=512 skip=2049` (unaligned) | `65e15b561221` | `65e15b561221` |
| `bs=512 skip=2052` | `f930e65fdb47` | `f930e65fdb47` |
| `bs=512 skip=4096` | `015b623a0cc9` | `015b623a0cc9` |
| `bs=512 skip=4097` | `200d242b9320` | `200d242b9320` |

**Every small read matches exactly, aligned or not.** The hypothesis is dead.

The reads that returned a constant digest near the squashfs tail were returning
`md5(512 bytes of 0xff)` - i.e. they were faithfully reading **erased flash**.
(Again: check digests against the fill constants first.)

### What is actually happening: the tail blocks get erased during the boot cycle

Sequence in round 116, with no stock boot in between:

1. rewrite rootfs, verify from initramfs -> `06479218...` **correct**
2. power-cycle, boot from flash -> ~700 SquashFS errors
3. now, from initramfs again -> `3be22357...`, and **block 36 = 128 KiB of 0xff**

So between a verified-good image and the following boot, blocks 36-37 end up
**erased**. The data was provably correct before the boot and provably erased
after it.

Candidates, in order:

1. **The stock firmware**, which the bootloader falls back to after our boot
   fails, and which mounts our region as a writable JFFS2 (`root=/dev/mtdblock8
   ... rootfstype=jffs2`). JFFS2 erases blocks it considers garbage - this fits
   the observation exactly, and would mean the erasure is a *consequence* of the
   failure rather than its cause.
2. Our own OpenWrt during `mount_root`, though the overlay now lives in a
   dedicated partition at `0x4000000` and should not touch this region.

### Next experiment (cheap, decisive)

Write a verified-good rootfs, boot from flash, and **cut power the moment the
SquashFS errors appear** - before the system can reboot into stock. Then verify
from initramfs. If the tail is still intact at that point, the erasure is the
stock fallback (consequence); if it is already erased, something in our own boot
does it (cause).


## Round 118: the rootfs boot failure was mtdblock read-modify-write

The off-cycle review found the answer in instrumentation I had added in round 95
and then failed to read. From the **failing** round-116 boot:

```
zx-spifc HEALTH: reads=5055 retry=2 mismatch=0 wedge=15 nobusy=208 fail=0
```

**`fail=0`.** The driver never returned `-EIO`, so the SquashFS `-5` errors never
came from the read path at all. Rounds 113-117 - "reads fail under load",
"access-shape dependent", "small random reads", "wedge/retry robustness" - were
aimed at a subsystem that was reporting itself healthy in the log the whole time.
This is the second time these counters have exonerated the driver and I needed a
review to notice.

### The actual mechanism

`CONFIG_MTD_BLOCK=y` makes `/dev/mtdblock7` read-**write**, with
read-modify-write semantics: any write erases the whole 128 KiB block and writes
it back. If the write-back does not land, the block is left **erased** - exactly
the state blocks 36-37 were found in, on an image that verified byte-exact
minutes earlier.

### The fix: one line of DTS

```dts
partition@a00000 {
	label = "rootfs";
	reg = <0x0a00000 0x0d20000>;
	read-only;
};
```

Result on the next boot from flash:

```
squashfs errors = 0
erases logged   = 0
zx-spifc HEALTH: reads=7905 retry=54 mismatch=0 wedge=141 nobusy=3531 fail=0 erase=0
```

OpenWrt boots to a shell from NAND, and Wi-Fi comes up (see docs/WIFI.md).

### Corrections to earlier rounds

- **"The read failure is real and context-dependent" (round 116) - RETRACTED.**
  The driver never failed a read.
- **"The stock fallback corrupts our rootfs" (round 116)** - remains a real
  hazard worth avoiding, but it is NOT the cause of the boot failure; round
  116's own data (verified-good -> boot -> erased, with no stock boot between)
  argued against it and I did not follow that through.
- The comparison "same driver reads it fine from initramfs" was never controlled:
  the initramfs and flash kernels are different binaries, and only one runs the
  PCIe bring-up that writes the CRM block which also clocks the NAND controller.


## Round 121: persistence re-tested - it is a WRITE problem, reproducible without JFFS2

The review suggested re-testing persistence before committing to UBI, since the
round-99 failure predates both the dedicated `rootfs_data` partition and the
`read-only` rootfs fix. Done, and the result is much sharper than before.

### The overlay is correctly set up

```
mount_root: switching to jffs2 overlay
/dev/mtdblock10 on /overlay type jffs2 (rw,noatime)
overlayfs:/overlay on / ... upperdir=/overlay/upper
jffs2: ... complete building xattr subsystem ... (no errors)
```

### But nothing reaches flash

Writing a file and syncing leaves the partition **completely erased**:

```
before  2fdd6851b32ae931      <- md5(1 MiB of 0xff)
after   2fdd6851b32ae931      <- unchanged
HEALTH: ... erase=0           <- JFFS2 never even erased a block
```

Writing directly to the JFFS2 mount (bypassing overlayfs) behaves the same: the
file appears in the mount, flash is untouched.

### The decisive test: it fails without JFFS2 at all

With the overlay unmounted, a plain raw write to the partition:

```
dd if=/bin/busybox of=/dev/mtd10 bs=2048 count=1     -> "1+0 records out"
read back md5 e0deebd3c3f56021
busybox page md5 911408227b2f6a2a                    -> MISMATCH
```

So this is **not** a JFFS2 flushing problem. A single page written to an erased
region of `rootfs_data` does not read back as written, and the write reports
success. That is the same silent-write-failure class seen with U-Boot in rounds
109-116, but now inside our own driver, which does check P_FAIL - and it did not
fire.

Note round 112 ran this exact test on this exact partition and it **passed**
(`911408227b2f6a2a` both sides), so the failure is not deterministic.

### What this changes

Config persistence is not a filesystem-choice problem, so **switching to UBI
would not have fixed it** - UBI on top of a write path that silently loses data
would corrupt just as thoroughly, as the review warned. The write path itself is
the thing to fix, and on-die ECC is likely part of that story: with
`NAND_ECC_ENGINE_TYPE_NONE` there is no correction and no way to detect a
marginal program.

Also worth recording: the driver declares `ecc.strength = 8, ecc.size = 1024`
while the chip specifies **8 bits per 512 bytes**, so even the advertised
geometry is wrong.


## Round 122: RETRACTION - the write path works; persistence fails because mount_root erases the overlay

### Retraction of round 121

Round 121 claimed a "silent write failure" in our own driver, from this test:

```
dd if=/bin/busybox of=/dev/mtd10 bs=2048 count=1   -> reported success
read back e0deebd3c3f56021, expected 911408227b2f6a2a
```

Both halves of that were wrong:

1. **`e0deebd3c3f560212af17c68b9344bae` is md5 of 2048 bytes of `0xff`** - an
   erased page. It was not corrupt data.
2. **`dd` to `/dev/mtdN` does not erase**, and the target page still held JFFS2
   data. Programming over a non-erased page cannot work: NAND only clears bits.

Run correctly - `mtd erase` first - the write path is perfect:

```
mtd erase rootfs_data ; read page 0 -> e0deebd3 (erased, correct)
write busybox page    ; read page 0 -> 911408227b2f6a2a (matches source)
```

and the new write-verify counters agree: `wverify=0 wfail=0` over the whole run,
i.e. **no program has ever failed verification**.

This is the THIRD investigation in this session derailed by not checking a digest
against the blank/zero fill constants (rounds 110-111, 117, 121), despite the
rule being written down in round 112. A constants table is now in HANDOFF.md so
the check is mechanical rather than remembered.

### The actual reason config does not persist

With a working write path, JFFS2 data demonstrably reaches flash and survives a
remount:

```
mount jffs2 ; echo persist-r122 > /overlay/ptest ; sync ; umount
block 0 md5 = b6679d9d9764f04b        (not the erased constant - data is there)
remount ; cat /overlay/ptest -> persist-r122
```

But it does **not** survive a power cycle, and the health counters say why:

```
mount_root: no usable overlay filesystem found, using tmpfs overlay
HEALTH: ... erase=128
```

**128 erases in one boot is the entire 16 MiB `rootfs_data` partition.**
`mount_root` decides the overlay is unusable and reformats it, destroying
whatever was written on the previous boot. The write path, the driver and JFFS2
are all fine; the data is being deliberately erased by userspace at boot.

### Next

Find why fstools rejects the volume: it is a plain JFFS2 that mounts cleanly by
hand, so the rejection is in `mount_root`'s own validation (it wants a specific
layout/marker). Options are to satisfy that check, or to stop using the
squashfs+JFFS2 overlay model here. This is now a userspace/config problem, not a
driver problem.


## Round 123: persistence root cause (fstools state machine), and three corrections to round 122

### Corrections forced by review

Round 122 claimed "`mount_root` erases the overlay". Three errors:

1. **Timing refutes it.** `mount_root` logs at t=29.9 s; the erases run at
   t=75-137 s. Different events, 45-107 s apart.
2. **`erase=128` was a cumulative counter sampled at one moment, not a
   measurement of one wipe.** Counting the per-erase log lines per boot gives
   **384, 384, 256** - the partition is erased *three times* in a boot. The
   "128 = exactly the partition" arithmetic was coincidence.
3. **Wrong log line quoted.** The boots that lost data say
   `overlay filesystem has not been fully initialized yet`, not
   `no usable overlay filesystem found`. Different code path.

I had added a per-erase log line printing the block number and then built a
causal claim on the aggregate counter without reading those lines.

### The actual mechanism (source-level)

`fstools-2024.07.14/libfstools/overlay.c:451`:

```c
case FS_STATE_PENDING:
    ULOG_INFO("overlay filesystem has not been fully initialized yet\n");
    overlay_delete(overlay_mp, true);      /* deletes overlay contents */
    break;
case FS_STATE_READY:
    break;
```

**fstools deliberately wipes the overlay on every boot where the state is not
READY.** READY is set only by `mount_root done`, invoked from
`/etc/init.d/done` (present, and linked as `S95done`).

Confirmed on the device:

```
cat /overlay/.fs_state   -> No such file or directory
ls /etc/rc.d | grep done -> S95done          (the service exists)
```

So the state machine never advances past PENDING, and every boot deletes the
previous boot's data. The driver, JFFS2 and the flash are all innocent.

### Why the state never sticks

`mtd_volume_identify()` (libfstools/mtd.c) reads the first four bytes:

```c
if (__be16_to_cpu(x) == 0x1985 || __be16_to_cpu(x >> 16) == 0x1985) return FS_JFFS2;
if (v->type == UBIVOLUME && x == 0xffffffff)                        return FS_JFFS2;
return FS_NONE;
```

An **erased raw-MTD** partition reads `0xffffffff` and is only accepted as JFFS2
for *UBI* volumes - for raw MTD it is `FS_NONE`, so mount_root falls back to a
**tmpfs** overlay, and `mount_root done` then writes `.fs_state` into RAM where
it evaporates. OpenWrt's image builder normally writes a `deadc0de` marker at the
start of `rootfs_data` for exactly this reason; `flash-prep.py` never has.

### Test invalidated by a stale kernel

Attempts this round to write that marker appeared to fail silently. The health
line explains why the evidence is worthless: it printed
`fail=0 erase=512` with **no `wverify`/`wfail` fields**, i.e. the running kernel
is the round-120 image flashed on the board, which predates the write-verify code
added in round 122. Every write test this round ran against the old driver.

**Re-run on a current kernel before drawing any conclusion about those writes.**

### Fix to implement

Have `flash-prep.py` emit a `rootfs_data` image whose first page begins with
`de ad c0 de`, and flash it alongside the kernel/rootfs, so fstools sees
`FS_DEADCODE` on first boot, formats a real JFFS2, and can then reach
`FS_STATE_READY`.


## Round 124: overlay volume now recognised; one gap left in the state machine

### The deadc0de seed works

`flash-prep.py` now emits a `rootfs_data` seed - one page beginning
`de ad c0 de` - flashed to `0x4000000`. fstools' behaviour changes immediately:

| boot | before the seed | with the seed |
|---|---|---|
| 1st | `no usable overlay filesystem found, using tmpfs overlay` | `jffs2 not ready yet, using temporary tmpfs overlay` + format (erase=128) |
| 2nd | same (tmpfs forever) | **`switching to jffs2 overlay`**, `/dev/mtdblock10 on /overlay type jffs2`, `erase=0` |

So the volume is now recognised, formatted once, and mounted from flash on every
subsequent boot. That was the whole purpose of the marker.

### JFFS2 writes really do reach flash

Verified by looking at the bytes rather than a digest:

```
before: page 1 of mtd10 = ff ff ff ff ...
write a file + sync
after:  page 1 = 85 19 02 e0 44 00 00 00 ...      <- JFFS2 magic 0x1985 + node
```

and the write counters stay clean throughout: `wverify=0 wfail=0`.

### The remaining gap

User files still do not survive a power cycle, and the boot log says why:

```
mount_root: overlay filesystem has not been fully initialized yet
mount_root: switching to jffs2 overlay
```

`fs_state_get()` is not returning READY, so fstools runs `overlay_delete()` -
which unlinks files rather than erasing blocks, which is why `erase=0` on those
boots and why the earlier "no erases, so nothing was wiped" reasoning was wrong.

`.fs_state` **is** being created. Note it is a **symlink whose target is the
value**, not a regular file:

```
lrwxrwxrwx  .fs_state -> 2         (2 = FS_STATE_READY)
```

`cat /overlay/.fs_state` therefore always fails - it is a dangling symlink by
design - and my earlier "`.fs_state` does not exist" readings were simply the
wrong tool. `readlink` shows `2` both before and after a power cycle, so the
marker itself persists.

So: the state file persists with the right value, yet `fs_state_get()` at boot
does not see READY. Next step is to find which path fstools reads it from during
early boot (`overlay_mp` at that point) versus where `mount_root done` writes it
(`/overlay` absolute), and whether the two refer to the same filesystem instance
at those moments.


## Round 125: state machine traced; persistence still fails; one self-inflicted confound

### What the code actually does

`fs_state_get()` is a plain `readlink` of `<dir>/.fs_state`; `fs_state_set()`
`unlink`s and re-creates it as a **symlink whose target is the decimal value**.
READY (2) is written from two places: the tail of the overlay mount path
(`overlay.c:343`) and `mount_root done` (`mount_root.c:122`, run by `S95done`).

`overlay_delete()` is `foreachdir(dir, handle_rmdir)` - it **unlinks files**, it
does not erase blocks. So a boot that wipes the overlay shows `erase=0`, and my
round-122 reasoning in both directions from erase counts was unsound.

### Live observation

On a running flash boot:

```
readlink /overlay/.fs_state   -> 2          (READY)
dmesg | grep mount_root       -> "overlay filesystem has not been fully
                                  initialized yet" + "switching to jffs2 overlay"
```

So the state reads READY *at runtime* while that same boot logged not-READY -
i.e. the symlink is (re)created after the check, and the check itself saw
UNKNOWN or PENDING.

### And the persistent filesystem is empty

Mounting the overlay volume from an initramfs kernel, with no `mount_root`
involved:

```
mount -t jffs2 /dev/mtdblock10 /mnt/o
ls -la /mnt/o/     ->  only . and ..
```

Raw flash pages 0-3 all read `0xff`, including page 0 where the `deadc0de` seed
was written and verified.

### Confound - my own doing

I mounted that JFFS2 **read-write** immediately before dumping the pages, and
JFFS2 erases blocks it considers obsolete at mount/GC time. So "the partition is
erased" may be a consequence of my inspection rather than of the boot cycle.
This is the same uncontrolled-observation mistake the round-123 review called
out, made again in the act of investigating it.

### The controlled experiment to run next

No manual mounts, no manual `mount_root done`, nothing interactive:

1. Flash kernel + header + rootfs + `rootfs_data` seed; verify each by digest.
2. Boot 1 (expect `jffs2 not ready yet`, format).
3. Boot 2 (expect `switching to jffs2 overlay`); write ONE marker file; `sync`.
4. Power-cycle.
5. Boot 3: read the marker **before touching anything else**, and capture the
   full `mount_root` line set.

Only step 5's first command may touch the overlay. Anything else invalidates the
result.


### Controlled three-boot test (no manual intervention)

Reseeded the overlay, then three boots with only one command issued per boot:

| boot | mount_root output | action |
|---|---|---|
| 1 | `jffs2 not ready yet, using temporary tmpfs overlay` | (formats) |
| 2 | `overlay filesystem has not been fully initialized yet` + `switching to jffs2 overlay` | wrote `/etc/persist125`, `sync` |
| 3 | `overlay filesystem has not been fully initialized yet` + `switching to jffs2 overlay` | **marker gone** |

So **every** boot takes the `FS_STATE_PENDING` branch and calls
`overlay_delete()`, which unlinks the previous boot's files. That is the whole
persistence failure, and it is now reproduced cleanly with no interference from
my own commands.

After boot 3, `readlink /overlay/.fs_state` returns `2` (READY) again - so the
value is written *during* each boot but is **not what the next boot reads**.
Since `fs_state_get()` is a bare `readlink` of `<overlay_mp>/.fs_state`, the two
must be looking at different filesystem instances or different points in the
mount sequence: `mount_root done` writes to the absolute path `/overlay` after
the pivot, while the boot-time check runs against `overlay_mp` before it.

That is the precise question to answer next, and it is entirely a userspace
path/ordering issue - the driver, JFFS2 and the flash are all behaving.


## Round 126: the state-machine theory is dead - nothing survives power-off

### Correction: the log line does not mean what I said it meant

`libfstools/overlay.c:444`:

```c
case FS_STATE_UNKNOWN:
        fs_state_set(overlay_mp, FS_STATE_PENDING);
        if (...) { ... break; }
        /* NO break - falls through */
case FS_STATE_PENDING:
        ULOG_INFO("overlay filesystem has not been fully initialized yet\n");
        overlay_delete(overlay_mp, true);
```

`FS_STATE_UNKNOWN` **falls through** into the PENDING case, so that message is
printed when `readlink` fails entirely (no `.fs_state`) just as it is when the
state is genuinely PENDING. **The round-125 claim that "every boot takes the
FS_STATE_PENDING branch" was never established** and is withdrawn.

### The decisive test (read-only, no mount)

After a power cycle, booted the initramfs kernel - which never runs `mount_root`
and never mounts the volume - and scanned the raw partition:

```
dd if=/dev/mtd10 bs=131072 count=128 | strings | grep -cE 'MARK125|fs_state|persist'
   -> 0
dd if=/dev/mtd10 bs=131072 count=128 | strings | head -5
   -> (nothing at all)
```

**The partition is blank.** Nothing written during a boot - not the marker file,
not `.fs_state`, not even JFFS2 node headers - survives the power cycle. So the
overlay state machine is irrelevant: fstools reports UNKNOWN because there is
genuinely nothing there.

### The blind spot in my own instrumentation

The write verification added in round 122 compares **2048 bytes**, not 2112:

```c
if (!memcmp(sp->vbuf, sp->pagebuf, SPIFC_PAGE_SIZE))   /* SIZE = 2048 */
```

`CONFIG_JFFS2_FS_WRITEBUFFER=y`, so JFFS2-on-NAND writes **cleanmarkers into the
OOB**, and a block without a valid cleanmarker is one JFFS2 will not trust and
will re-erase. So `wverify=0 wfail=0` is evidence about the data area only and
says nothing about the region that decides whether blocks survive - especially
with `SPIFC_OOB_SIZE` declared as 64 on a chip that has 128 bytes of OOB, and no
ECC.

That is the leading hypothesis now, and the existing counters are structurally
unable to see it.

### Struck from the record

Round 125's "the partition is erased" observation is **withdrawn**, not merely
annotated: it was produced by mounting the filesystem under test read-write
first, and JFFS2 erases blocks at mount/GC time.

### Method change (four occurrences is a pattern, not bad luck)

Rules written in HANDOFF have failed because they are recall-time while the
errors are action-time. All four errors share one shape: **a mutating command's
output cited as evidence about the state that preceded it** (rounds 110/111, 117,
121, 125). New per-command discipline:

1. Classify every DUT command as READ-ONLY or MUTATES *before* running it. A
   MUTATES command can never be evidence about prior state.
2. Prefer the least-privileged observation: raw `dd | hexdump`/`strings` over a
   mount; `-o ro` over rw; a digest only to compare two things already
   characterised by eye.
3. Predict the expected bytes before executing. All four errors fail at this step
   ("I expect JFFS2 nodes; I got `ff ff ff ff`" is a blank-flash finding, not a
   corruption finding).


## Round 127: OOB ruled out, and a contradiction that points at the write buffer

### OOB is not the problem

Extended the write verification from 2048 to the full 2112 bytes (data + OOB),
with separate counters for which region mismatched. Over two full boots
including a JFFS2 format and normal userspace activity:

```
wverify=0 wfail=0 wdata=0 woob=0
```

So OOB contents read back exactly as written, and the round-126 hypothesis
(JFFS2 cleanmarkers being lost in unverified OOB) is **not** supported.

### JFFS2 still commits nothing

Wrote a marker on a boot where the overlay was mounted from flash
(`switching to jffs2 overlay`, `erase=0`), synced, power-cycled, then scanned the
raw partition read-only from an initramfs kernel:

```
strings /dev/mtd10 | grep -c MARK127   ->  0
```

with `erase=0` on both boots, so nothing erased it - JFFS2 simply never put it
there.

### The contradiction worth chasing

A raw page write, immediately verified:

```
mtd erase rootfs_data
dd if=/bin/busybox of=/dev/mtd10 bs=2048 count=1
dd if=/dev/mtd10 bs=2048 count=1 | md5sum   ->  e0deebd3...  (= md5 of 2048 x 0xff, ERASED)
source page md5                             ->  911408227b2f6a2a
```

yet the driver reports `wverify=0 wfail=0` - it believes every program succeeded.

Those two facts are only consistent if **the driver is verifying a buffer that
never received the data**. `zx_spifc_write_page()` compares `vbuf` against
`sp->pagebuf`; the SEQIN handler pre-fills `pagebuf` with `0xff`. If the
`DATA_OUT` payload never lands in `pagebuf`, the driver programs an all-`0xff`
page (a no-op on erased flash), reads back `0xff`, and the comparison **passes
trivially**.

That would explain every observation in rounds 121-127 at once: writes "verify",
nothing appears on flash, no errors anywhere, and JFFS2 quietly loses everything.

Prime suspect is the `pos` cursor added in round 111 (`pos = col` on ADDR,
`pos += len` on DATA_OUT) interacting with how nand_base issues the program
sequence.

**Next: instrument `DATA_OUT` directly** - log `pos`, `len` and the first bytes
of the payload, and log the first bytes of `pagebuf` at PAGEPROG. That
distinguishes "payload never arrived" from "payload arrived at the wrong offset"
in one boot.


## Round 128: THE BUG - a page program spans two exec_op calls

### Found by reading, not measuring

`nand_prog_page_op()` in Linux 6.6 is **two** `exec_op` calls:

```
nand_prog_page_begin_op()  ->  SEQIN + ADDR + DATA_OUT
nand_prog_page_end_op()    ->  PAGEPROG + WAITRDY
```

The driver kept `writing` and `page` as **locals of `exec_op`**, and guarded the
program on them:

```c
else if (opcode == NAND_CMD_PAGEPROG && writing) {
        ret = zx_spifc_write_page(sp, page);
}
```

On the second call `writing` is `false`, so the guard fails and
**`zx_spifc_write_page()` is never called**. No program is issued, no error is
returned, and no counter moves.

That single defect explains everything in rounds 121-127 at once:

- writes "succeed" and report nothing;
- nothing ever appears on flash;
- `wverify=0 wfail=0` - because the verify code was never reached;
- JFFS2 loses all state, so `.fs_state` never persists and fstools reports
  UNKNOWN, which prints the same message as PENDING.

It also means the write-verify added in round 122 could never have caught this:
it lives inside the function that was not being called.

### Fix

Move the program state into the driver struct so it survives between calls:

```c
bool prog_pending;   /* set at SEQIN  */
u32  prog_row;       /* captured from the ADDR that carries a row */
```

and trigger on `(writing || sp->prog_pending)`, using `prog_row` when the
PAGEPROG call carries no address of its own.

### Result

Raw page write, previously reading back as erased, now round-trips:

```
mtd erase rootfs_data
dd if=/bin/busybox of=/dev/mtd10 bs=2048 count=1
read back  911408227b2f6a2a
source     911408227b2f6a2a        <- match
```

and the program path is demonstrably live (`zx_spifc_write_page: N callbacks
suppressed` in dmesg, where before it never appeared).

### Follow-on: OOB verification must not be fatal

With writes actually happening, JFFS2 immediately hit:

```
jffs2: jffs2_flush_wbuf(): Write failed with -5
kernel BUG at fs/jffs2/wbuf.c:484!
```

because round 127 had extended the verify to compare OOB, and the OOB does not
read back as staged. **Round 127's `woob=0` was vacuous** - it was measured while
no program was being issued at all. The comparison is now data-area only, with an
OOB mismatch counted (`woob`) as a diagnostic rather than failing the write.


## Round 130: CONFIG PERSISTENCE WORKS

With both exec_op lifetime bugs fixed (round 128 `prog_pending`/`prog_row`,
round 129 `pos`), configuration survives power cycles:

```
# write on one boot
echo MARK130 > /etc/persist130
uci set system.@system[0].hostname=H199A-P130 ; uci commit system ; sync

# after a power cycle
root@H199A-P130:~#                     <- hostname persisted (visible in the prompt)
cat /etc/persist130        -> MARK130
uci get ...hostname        -> H199A-P130
readlink /overlay/.fs_state-> 2        (READY)
mount_root: switching to jffs2 overlay (no "not fully initialized")
```

Confirmed stable over two consecutive power cycles, with clean driver counters
throughout (`fail=0 wverify=0 wfail=0 wdata=0 woob=0`) and no JFFS2 errors.

### What actually fixed it

Three things, in order of significance:

1. **`sp->prog_pending` / `sp->prog_row`** (round 128) - a page program spans two
   `exec_op` calls, so the program was never issued at all.
2. **`sp->pos`** (round 129) - `nand_write_page_raw()` sends the OOB as a
   standalone `exec_op` with no ADDR, so OOB was being written over the start of
   the data area.
3. **The `deadc0de` seed** in `flash-prep.py` (round 124) - without it an erased
   raw-MTD volume is `FS_NONE` to fstools, so the overlay was never adopted.

The fstools "state machine" investigation of rounds 122-126 was chasing a
symptom: fstools behaved correctly throughout, on a filesystem whose writes were
being silently discarded.

## Round 190: `nand write` reported success while writing wrong data

A cold boot from flash landed in **stock firmware**, and the bootloader said why:

```
zteboot_verify_fs:210 Romfs CRC check failed. fs@42340000 len=d20000
                      Real crc 6f9fe0ca, Want 81dd3819
```

`Want` (`0x81dd3819`) is exactly the CRC of the rootfs image that was flashed, so
the header was correct and **the flash content was not** - despite U-Boot having
reported:

```
 13762560 bytes written: OK
```

Rewriting the same image and verifying with `cmp.b` against the RAM copy:

```
Total of 13762560 byte(s) were the same
```

after which the bootloader's `Real crc` became `81dd3819` and the Romfs check
stopped failing.

### Why this matters more here than on other hardware

This flash has **no ECC and no persistent bad-block table**. A write that
silently lands wrong has nothing underneath it to detect or correct the
difference, and `bytes written: OK` is not a verification - it means the
controller accepted the data, not that the data reads back.

**Always verify a flash write by reading it back.** `cmp.b <ram> <readback>
<len>` costs a few seconds. This U-Boot has no `crc32` command, so `cmp.b`
against the freshly TFTP'd copy in RAM is the practical check.

### Two further notes from the same investigation

* **The header self-CRC mismatch is a red herring.** The bootloader prints
  `crc=<computed>, <stored>` and they differ for bank A - but they also differ
  for bank B, which boots. It is not the rejection criterion; the filesystem CRC
  is.
* **A header only matches the exact kernel+rootfs it was generated for.** After
  fixing the rootfs, the boot failed again with `Want 7bc2f9e9` because an older
  header was still in place. Restore all three parts from one image, as
  `INSTALL.md` says.


## Round 191: the kernel write was wrong too - and this is the resolution

After fixing the rootfs, the device still booted stock. The kernel had never been
verified, so it was checked the same way:

```
tftp 0x42000000 v189-kernel.bin
nand read 0x44000000 0x700000 0x300000
cmp.b 0x42000000 0x44000000 0x300000

byte at 0x42000024 (0xe2) != byte at 0x44000024 (0x27)
Total of 36 byte(s) were the same
```

**CORRECTION (round 192): this was misread.** U-Boot's `cmp.b` stops at the
first difference and reports how far it got, so "Total of 36 byte(s) were the
same" is the **offset of the first mismatch** (36 = 0x24), not a match count.
The remaining 3,145,692 bytes were never compared.

And 0x24 is precisely the earliest byte at which two *valid* images of this
format can differ: `0x00-0x1f` is the constant ZTE header, `0x20-0x23` the
constant uImage magic `27051956`, and `0x24-0x27` the per-build uImage header
CRC. Verified across three surviving kernel images, which share their first 0x24
bytes exactly and differ at 0x24.

So the read-back showed a **different, structurally valid kernel** - not
corrupted data. The region did not contain the image that had just been written.
That is a different failure, and the cause is **not established**: candidates
include the write not taking effect, and something rewriting bank A afterwards
(fourteen stock-firmware boots occurred in between, and the bootloader writes
`bootpara` on every boot).

What remains true and is the operationally important part: **`bytes written: OK`
is not proof**, read-back verification caught it, and rewriting fixed it.

Re-erasing and rewriting gave `Total of 3145728 byte(s) were the same`, and the
next cold boot from flash reached OpenWrt:

```
root@H199A-P130:~#
2          <- both CPU cores
14         <- MTD partitions
6.6.151
```

### The lesson, stated once

Three separate partitions - kernel, rootfs and header - each failed to contain
what had been written to them, and each failure
presented as a *different* symptom: a bootloader CRC mismatch, a fallback to
stock firmware, an apparently stale header. Several rounds went into explaining
those symptoms before the writes themselves were doubted.

On flash with **no ECC and no bad-block retirement**, `bytes written: OK` means
the controller accepted the data. It says nothing about what a subsequent read
returns. Verify every write:

```
nand read <other_addr> <offset> <len>
cmp.b <src_addr> <other_addr> <len>
```


## Round 192: this was a REDISCOVERY, and that is the real finding

`docs/BRINGUP.md` already contained this, written around round 114:

> "The kernel partition write did not land, exactly like the rootfs writes in
> **rounds 109-113**, and `3145728 bytes written: OK` was again meaningless."
>
> "**Rule going forward: Verify every partition after every write, by reading it
> back and comparing a full digest - kernel included.** Round 113 established
> this for the rootfs and I did not apply it to the kernel this round, which cost
> the whole round."

The identical failure, the identical misleading message, and an explicit rule -
followed by roughly seventy-six rounds of flashing without verification, and then
three rounds spent rediscovering it as though it were new.

The knowledge was never missing. **A rule written in prose inside a
thousand-line journal did not survive contact with the next seventy-six rounds.**
That is an argument for putting the rule in the *procedure* rather than in the
narrative, which is what `INSTALL.md` now does.


## Round 193: the erase/program wait had the same defect the read path was fixed for

Research into SPI-NAND silent-write failures found the answer inside this
driver rather than on the web.

`zx_spifc_wait_ready()` - used by **both erase and program** - looked like this:

```c
for (i = 0; i < 1000; i++) {
        ret = spifc_get_feature(sp, 0xc0, &feat);
        if (ret) return ret;
        if (!(feat & 1)) return 0;      /* OIP clear -> "done" */
        udelay(100);
}
```

No initial delay, and no check that the chip was ever seen **busy**. Called
immediately after issuing an erase or program, it can return "done" before the
operation has started - after which the caller programs a block that is still
erasing, or reads back a page that was never written.

**The read path was fixed for exactly this in round 89**, with `saw_busy` plus a
requirement to see ready twice in a row, and a comment describing the mechanism
in detail. The write path was never audited, and the defect survived roughly a
hundred rounds.

This is not theoretical on this hardware: the driver's own `nobusy` counter
records **hundreds to thousands** of missed busy windows per boot on the read
side, because with ECC off an array transfer takes ~25 us and the poller is
faster than that. And `tERS` is up to **10 ms** against `tPROG` ~600 us, so the
erase path has by far the widest window.

**CORRECTION (round 195): this does NOT explain the rounds 189-191 failures.**
Those writes were `nand erase` / `nand write` typed at the `=>` prompt, which run
**U-Boot's own, independent spifc driver**. `zx_spifc_nand.c` was not loaded and
not executing. A change to the Linux driver can have had no bearing on them, and
two reviewers caught the claim independently.

What is true: the Linux path had the *same class* of defect, found while
investigating the U-Boot failures. The U-Boot failures themselves remain
**unexplained**, and their practical mitigation is the `cmp.b` read-back
verification, not this patch. The "region reads back as a valid previous image"
fingerprint does fit an erase that never took effect - but that is a hypothesis
about a different driver, in a bootloader this repository does not build.

Fixed by mirroring the read path: an initial delay, require the busy phase to be
observed, require ready twice consecutively, and count the cases where OIP was
never seen (`nobusyw` in the HEALTH line) so the frequency is visible rather than
assumed. First boot with it reports `nobusyw=2`.


## Round 195: three more defects of the same class, and a correction

Two reviewers audited the round-193 fix. Both found the attribution wrong (see
the correction above), and between them found three further live defects.

**1. The erase path was the exposed one, and it was the one left returning
success.** Program has a downstream safety net - `zx_spifc_write_page()` reads
the page back and compares, retrying - so a program that never happened is
caught. **Erase has no verification at all**: nothing reads the block back. Yet
tERS is up to 10 ms against tPROG ~600 us, so the window is widest exactly where
the checking is weakest. Erase now returns `-EIO` when the busy phase was never
observed; program still only counts, because this die permits **one** program per
page and re-issuing would be actively wrong.

**2. Both P_FAIL checks treated a failed status read as "no failure".**

```c
if (!spifc_get_feature(sp, 0xc0, &feat) && (feat & 0x08)) {
```

If `spifc_get_feature()` fails, the `&&` short-circuits and the operation is
reported as having **succeeded** - an operation whose verdict could not be read.
This is the same defect as the one just fixed in `wait_ready`, sitting four lines
below it in both callers. The read path learned this in round 89 ("failed read
!= ready"); these two sites kept the older form. Now they return the error.

**3. `nobusyw` had no denominator.** A count of 2 could be 2-of-2 or 2-of-10000.
The HEALTH line now reports `nobusyw=<missed>/<total>`.

Also backported to the read path: its round-89 "ready twice in a row" check had
**no delay between the two reads**, making it two back-to-back SPI transactions
rather than a debounce. The write path added `udelay(50)` first; the read path
now matches. The copy turned out to be better than the original.


## Round 198: the erase and program paths exercised on hardware with the fix

A reviewer pointed out that the round-193/195 changes had never actually
executed - every boot carrying them reported `erase=0`, so the erase path, which
is the one with no downstream verification, had never run once.

Run now, on the `staging` partition:

```
mtd erase staging                     -> rc=0, erase=160, nobusyw=1/162
mtd -f write /tmp/p staging           -> rc=0
dd if=/dev/mtd12 ... ; md5sum

  d36e37f307a755de931200a48273650a    (source)
  d36e37f307a755de931200a48273650a    (read back from flash)

erase=324  nobusyw=128/582  wverify=0  wfail=0
```

Byte-exact, with no program-verify retries and no failures.

### The counter justifies the fix

`nobusyw=128/582` means **22% of erase/program waits never observed the busy
phase at all**. Before this change every one of those returned success
immediately, and the caller went straight on to the next operation. That is not
a rare race - it is the common case on this hardware, exactly as the read-side
`nobusy` counter had been showing for a hundred rounds without anyone checking
whether the write side had the same problem.

The data is correct now because the two paths fail differently and deliberately:
erase returns `-EIO` when it never saw busy (nothing downstream would catch a
silent failure), while program only counts it and relies on its read-back verify
(re-issuing would violate the one-program-per-page rule this die enforces).

### A test that was wrong before the driver was

The first attempt wrote with `dd ... of=/dev/mtdblock12` and read back a
different digest, which looked like a driver fault. It was not: this build sets
`CONFIG_MTD_BLOCK_RO=y`, so the block device is **read-only** and the write
silently did nothing. The tell was in the counters - `nobusyw` did not move at
all, meaning no program wait had happened. Writing through the char device with
`mtd -f write` gave the exact match above.
