> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# docs/

> **Start at [`INSTALL.md`](../INSTALL.md).** It carries the capability table, the
> prerequisites and the flashing procedure. The repo [`README.md`](../../README.md)
> is the product entry point and is not restated here — this file only routes you.

## What this directory is

Two kinds of file live here:

- **Current docs** — maintained to describe the verified state of a subsystem.
  Read these for the answer.
- **Historical journals** — chronological, self-correcting logs written while the
  answer was still unknown. Kept unsanitised. Read these for *how* the answer was
  found, and for the dead ends you would otherwise re-walk.

Everything here is engineer-to-engineer and evidence-first: a register name and
value, a `file:line`, a commit hash, or a measured number. Where a claim was later
shown to be wrong, **the retraction stays in the file** rather than being quietly
edited out.

## Status in one paragraph

As of 2026-11-15 the author's unit runs the **production image from NAND bank
A**, with its configuration in a UBI overlay and stock bank B as the fallback.
The guarded install, a verified sysupgrade, power-loss injection and recovery
all passed on that unit ([INSTALL.md §12.8](../INSTALL.md)).

Hardware state:
- **Ethernet:** WAN DHCP, routing and NAT work, at 314/357 Mbit/s NAT; one CPU
  core is the limit.
- **2.4 GHz:** serves real clients.
- **5 GHz:** works, but under sustained TX port 0 takes a PCIe link-down reset.
  The driver contains it, but the endpoint stays latched until a full power
  removal ([WIFI.md](../WIFI.md)).
- **Watchdog, LEDs, buttons:** watchdog hardware-qualified; LEDs and buttons
  verified.
- **Hardware NAT:** not implemented. The classifier/packet-modify engines'
  table interface is proven on hardware, nothing more.

Draft upstream bindings are in [upstream/bindings/](../upstream/bindings/README.md).
The per-area table is in [PORT-STATUS.md](../PORT-STATUS.md).

## Reading order, by what you came for

**(a) Build and flash it**
1. [`INSTALL.md`](../INSTALL.md) — read the whole page before touching the device
2. [`UART-PADS.md`](../UART-PADS.md) — **one header pad is a boot strap**
3. [`NAND.md`](../NAND.md) — partitions, and why config is expendable

**(b) Understand the datapath (and why it is not a router yet)**
1. [`ETHERNET.md`](../ETHERNET.md) — the TCP defect, the wedge, the port model
   ([`WEDGE-ANALYSIS.md`](../WEDGE-ANALYSIS.md) — why it wedges, in one place)
2. [`ZX279128S-DATAPATH.md`](../ZX279128S-DATAPATH.md) — vendor-derived register model
3. [`RESEARCH.md`](../RESEARCH.md) — the sibling ZX279133 driver, the closest thing
   to a datasheet this SoC has
4. `ETHERNET-JOURNAL.md` — the measurements behind all of it

**(c) Future maintainer picking this back up**
1. [`REVERSE-ENGINEERING.md`](../REVERSE-ENGINEERING.md) — the transferable method
2. [`BRINGUP.md`](../BRINGUP.md) — clocks, register dumps, the boot recipe
3. `SESSION-JOURNAL.md` — the round-by-round record

## The current docs

| file | covers |
|---|---|
| [`PORT-STATUS.md`](../PORT-STATUS.md) | Milestones and outstanding verification gates |
| [`ZX279128S-DATAPATH.md`](../ZX279128S-DATAPATH.md) | H199A vendor-derived registers, fields and sequences |
| [`INSTALL.md`](../INSTALL.md) | Capability table, prerequisites, flashing, recovery, `sysupgrade` |
| [`BRINGUP.md`](../BRINGUP.md) | Measured clocks, register dumps, boot recipe |
| [`ETHERNET.md`](../ETHERNET.md) | Datapath, the TCP defect, the wedge, the port model |
| [`PP-OFFLOAD.md`](../PP-OFFLOAD.md) | Packet-processor table access (off by default): evidence, proven vs unproven, qualification plan |
| [`WEDGE-ANALYSIS.md`](../WEDGE-ANALYSIS.md) | Every failure called "the wedge", what causes each, the recovery and hang diagnostics, and the bench plan |
| [`WIFI.md`](../WIFI.md) | `mt7615e` bring-up, calibration data, AP configuration |
| [`NAND.md`](../NAND.md) | `zx_spifc_nand`, partition map, the missing ECC |
| [`WATCHDOG.md`](../WATCHDOG.md) | CPU0 TWD watchdog driver, its host evidence and the hardware qualification plan |
| [`REVERSE-ENGINEERING.md`](../REVERSE-ENGINEERING.md) | Transferable method notes |
| [`RESEARCH.md`](../RESEARCH.md) | Prior art, sibling SoCs, external references |
| [`UART-PADS.md`](../UART-PADS.md) | Board header pad map and the rig scripts |

## The historical journals

Read the dated banner at the top of a journal before trusting anything below it.

- `ETHERNET-JOURNAL.md` — the datapath investigation, including several
  hypotheses that were later withdrawn and two eliminations that did not survive
  scrutiny.
- `NAND-JOURNAL.md` — SPI-NAND bring-up, the silent-write-failure hunt, the ECC
  decision.
- `WIFI-JOURNAL.md` — PCIe training, `mt7615e`, the calibration-data hunt.
- `SESSION-JOURNAL.md` — the round-by-round record for the whole port. Paths in
  it refer to the pre-2026-09 workspace layout (`~/h199a-build/`); they are left
  as written because a journal is a record, not a current document.

## Conventions used in these docs

- **★** marks the load-bearing finding of a section — the one thing that, if you
  skip it, makes the rest not work.
- **✗ RETRACTED** means a claim made *earlier in the same file* has been
  falsified; the correction follows immediately. It is a pointer backwards, not a
  warning about the current text.
- Measured numbers are always from hardware, with the bench and the method named.
  Ranges are given as ranges; a single run is labelled as a single run.
- **No single-trial conclusions.** On this hardware the wedge point varies enough
  between boots that a one-off comparison means nothing — twice, a striking
  single measurement evaporated under replication. Alternating arms, each from
  its own cold boot.

## Cross-references you will not be able to follow

Some documents cite files that live outside this repository:

- `../../rig-check.sh`, `../../soak.sh`, `../../uart-log.sh`, `tomada` — the test
  rig, in the workspace root. They are not published because they encode one
  particular bench.
- `h199a-firmware` — the full 128 MB flash dump, the stock DTB
  (`extracted/h199a-stock.dts`) and the partition map. Per-unit data, so a dump of
  someone else's device will not substitute for your own.
- `REVIEW-CADENCE.md`, `handoff.md` — working-process documents in the workspace
  root.

The citations are left in place because they name the evidence behind a claim,
and knowing which instrument produced a number is worth more than a dead link
costs.
