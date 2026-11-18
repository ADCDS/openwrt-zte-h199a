> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](README.md),
> [installation](INSTALL.md) and [validation](../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.
> **Radio supersession:** DesignWare host support implements both ports;
> calibrated 2.4 GHz works. The empty-eFuse/no-calibration conclusion was
> withdrawn after own-stock calibration and OTP recovery. 5 GHz remains
> unreliable. Some entries retain only round labels; exact dates are unknown.

# WIFI - investigation journal

> **This is a chronological record, not a description of the current system.**
> It contains hypotheses that were tested and later **withdrawn**; several
> confident conclusions here are wrong and are corrected further down.
>
> For what is true now, read [`WIFI.md`](WIFI.md).
>
> It is kept because the failure modes proved more reusable than the results:
> instruments that could not fire, controls that did not exist, fixes validated
> against something the build does not produce, and rig faults misread as device
> faults. Those mistakes are the most transferable thing here.

# Wi-Fi (mt76) — scoping

Status: **not started in code.** This documents what the hardware is and what
standing up Wi-Fi actually requires, so the work can be picked up without
repeating the investigation.

## The Wi-Fi part is MediaTek/Ralink

The flash dump has a dedicated 1 MiB Wi-Fi partition, `h199a-firmware/mtd2-wifi.bin`. It
is almost entirely erased — 1 non-blank 4 KiB page out of 256, at offset
`0x20000`:

```
@0x20000: 63760001 000c4326 6000 6376 c314 0080 0200 6376 c314 ...
```

`00:0c:43:26:60:00` — OUI **00:0C:43 is Ralink Technology (now MediaTek)**,
which is consistent with an mt76-class device. The partition holds the MAC
rather than a full EEPROM/calibration blob in any recognisable format.

mt76 itself is already in OpenWrt, so the driver side of Wi-Fi is not the
problem.

## The blocker is the SoC PCIe controller

The Wi-Fi part sits behind the SoC's PCIe root complex. From the stock DTS:

```dts
pcie@10000000 {
        compatible = "zte,ZX279127-pcie";
        interrupts = <0 0x3f 4  0 0x4e 4  0 0x3b 4  0 0x4a 4>;
        status = "okay";
};
```

Two things make this awkward:

1. **There is no `reg` property.** The vendor driver hardcodes its register
   bases, so they have to be recovered from the stock kernel rather than read
   out of the device tree.
2. **It is not DesignWare IP.** The stock kernel contains no
   `dw_pcie`/iATU/Synopsys PCIe strings, only a vendor message
   (`"pcie%d link up,gen%d,cnt %d!"` at `0xc04dd2f0`) alongside the generic
   Linux PCI host-bridge strings. So mainline's `pcie-designware-host` cannot
   simply be reused with a small glue layer — which *would* have been plausible,
   since the USB block on this SoC is Synopsys (`zte,zx279127-dwc2`).

## What implementing it involves

A full PCIe host controller driver, reverse-engineered: register bases, link
training, config-space access (type 0/1), address windows/translation, INTx and
MSI routing for the four interrupts above, plus a `pci_host_bridge` and DT
bindings. Only once a PCI device enumerates can mt76 bind to it.

That is a substantially larger piece of work than the NAND, MDIO, Ethernet or
SMP drivers in this port, and it is the reason Wi-Fi is untouched rather than
partially done.

## Starting points for a future session

- vendor link-up message: `0xc04dd2f0` (`"pcie%d link up,gen%d,cnt %d!"`)
- compatible strings in the stock image: `zte,ZX279127-pcie` (`0xc03ed5a0`) and
  `zte,zx279127-pcie` (`0xc04dd310`); the latter is referenced from a driver
  match table at `0xc05b2a58`
- node name implies a window at `0x10000000`
- GIC SPIs `0x3f`, `0x4e`, `0x3b`, `0x4a`
- MAC for the Wi-Fi interface: `00:0c:43:26:60:00` at `mtd2 + 0x20000`


## Round 90 research: the PCIe host driver is buildable, and mt76 needs nothing exotic

### No mainline ZTE PCIe driver has ever existed

The removal commit `89d4f98ae90d` ("ARM: remove zte zx platform") deleted
`arch/arm/mach-zx`, `drivers/soc/zte`, `reset-zx2967` and the DTS files — and
**nothing under `drivers/pci/`**, because there was never a ZTE PCIe host driver
upstream. The pre-removal `zx296702.dtsi` and `zx296718.dtsi` have no `pcie`
node at all. So there is no upstream code to reuse; the vendor binary is the
only register reference.

### The node is canonical, and the base address is 0x10000000

An independent bring-up for the E2631 (also ZX279128S) carries the **identical**
node, including the missing `reg` and the stale "ZX279127" name:

```dts
pcie@10000000 {
    compatible = "zte,ZX279127-pcie";
    interrupts = <0 63 0x4>, <0 78 0x4>, <0 59 0x4>, <0 74 0x4>;
    status = "disabled";
};
```

With no `reg` and no syscon phandle, the vendor driver cannot be using
`of_iomap()`; it must hardcode `ioremap(0x10000000, ...)` — the classic pre-DT
vendor pattern, consistent with our finding that the driver matches on DT but
carries its address internally. The four SPIs (63/78/59/74) are most likely
INTA-INTD.

### What to model it on

- **`drivers/pci/controller/pcie-altera.c`** (~700 lines) if config access is
  TLP-based: it builds TLPs by hand into `RP_TX_REG0/1` + `RP_TX_CNTRL`, polls
  `RP_RXCPL_STATUS`, waits for `RP_LTSSM == LTSSM_L0 (0xf)` for link-up, and
  does legacy INTx via an irqdomain with **no MSI**.
- **`drivers/pci/controller/pci-ftpci100.c`** if it is a classic indirect
  address/data pair (`FTPCI_CONFIG` @0x28 / `FTPCI_DATA` @0x2c).
- Not `pcie-rockchip` — it drags in GRF syscon, PHY and reset frameworks.

Minimum to implement: `struct pci_ops` (map_bus/read/write), a MEM window from
DT `ranges` programmed into the RC, link training, INTx irqdomain +
`of_irq_parse_and_map_pci()`, then `pci_host_probe()`. I/O space and MSI can be
skipped entirely for a single-function endpoint.

### mt76 requires nothing unusual

- **No MSI needed.** `mt7615/pci.c` uses `pci_alloc_irq_vectors(..., PCI_IRQ_ALL_TYPES)`
  and falls back to INTx; `mt7603/pci.c` is pure legacy INTx.
- **32-bit DMA** (`dma_set_mask(DMA_BIT_MASK(32))`) — fine with RAM at 0x40000000.
- **Calibration from NAND is supported directly**: the mt76 binding takes
  `mediatek,mtd-eeprom = <&partition offset>`, which matches our layout (the
  Wi-Fi MAC lives at `mtd2 + 0x20000`). No need to fake an on-chip EEPROM.
- **The endpoints are already supported**: MT7603E is `14c3:7603`; the MT7613E
  in this device family enumerates as `14c3:7663`, already handled by
  `mt7615e`. The vendor module names on the sibling ZX279128R device are
  `mt7603e_ap` and `mtk7613e_ap`, consistent with that.

### Another vendor binary to cross-reference

`github.com/celeron633/ZX279127S-Reverse` hosts vendor kernel images
(`mtd-img/F610GV9/kernel1.bin`) for the closely related ZX279127S. A second copy
of the same PCIe driver is useful for confirming register offsets found in our
H199A binary.

### Realistic assessment

No public port has ever enumerated Wi-Fi on any ZTE ZXHN ONT. The endpoint side
is routine; the host controller is the entire job, and it is a genuine RE task,
not a port. It should be time-boxed and sequenced behind the cheaper wins
(reliability confirmation, SMP).


## Round 100: the vendor PCIe driver located and its register map recovered

### Correcting round 90

Round 90 concluded (mine and the researcher's inference) that the DT unit
address `pcie@10000000` was the register base and that the driver hardcoded
`ioremap(0x10000000, ...)`. **That is wrong.** There is no `0x10000000` literal
anywhere in the stock kernel; the driver builds its constants with `mov`/`movt`
immediates, which a literal-pool scan cannot see.

### Locating the driver

```
compat "zte,ZX279127-pcie"   @ 0xc03ed5a0
of_device_id table           @ 0xc03ed560
platform_driver              @ 0xc05b2a44
  .probe                     = 0xc0015de0
  .remove                    = 0xc0015a58
  .driver.name               -> 0xc04dd310
  .driver.of_match_table     = 0xc03ed560
private state struct         @ 0xc05d77f8
```

The probe begins with a **board-ID gate** - it reads a byte at `0xc05d786c` and
bails for a list of board types - then fetches **four IRQs** via
`platform_get_irq(pdev, 0..3)`, matching the four `interrupts` entries in DT.
So IRQs come from DT; every address is compiled in.

### Register regions (all hardcoded, via ioremap at 0xc00126a4)

| region | size | stored at | notes |
|---|---|---|---|
| `0x0f000000` | `0x4000` | priv+0x08 | controller registers |
| `0x09500000` | `0x10000` | priv+0x14 | |
| `0x1c000000` | `0x4000` | priv+0x18 | |
| `0x0f100000` | `0x4000` | priv+0x40 | second controller instance? |
| `0x09600000` | ... | ... | pairs with 0x09500000 |

Plain values stored without ioremap (address-space bases, not CPU-mapped):

| value | stored at |
|---|---|
| `0x10000000` | priv+0x04 |
| `0xf0500000` | priv+0x0c, priv+0x44 |
| `0xf0400000` | priv+0x10, priv+0x48 |
| `0x20000000` | priv+0x3c |

The duplication at +0x40..+0x48 mirroring +0x08..+0x10 strongly suggests **two
root complexes** (the SoC serves both a 2.4 GHz and a 5 GHz Wi-Fi part, which
matches the vendor's two modules `mt7603e_ap` and `mtk7613e_ap`).

### What this changes

The Wi-Fi work is no longer blocked on "where are the registers". The next steps
are to decode the link-training and config-access sequences inside this probe,
then write the host bridge against the `pcie-altera` / `pci-ftpci100` model
(legacy INTx, no MSI - mt76 does not need MSI, and calibration comes from NAND
via `mediatek,mtd-eeprom`).


## Round 101: it IS a DesignWare core, and link training is decoded

### Correcting round 90 again

Round 90's research concluded the controller is "NOT DesignWare" (based on the
DT lacking `snps,dw-pcie` and any dbi/config ranges). The driver's own strings
settle it:

```
"synopsys pcie port%d controller debug print"
"synopsys pcie%d controller waitting L0 state"
"pcie%d link up,gen%d,cnt %d!"
"pcie0 mem space"  "pcie1 mem space"  "pcie0 reg"  "pcie1 reg"
```

It is a **Synopsys DesignWare PCIe core**, and there are **two ports**. The DT
node simply omits the standard properties - absence of `snps,dw-pcie` in a
vendor DT says nothing about the silicon.

This is a large simplification: Linux has a mature DesignWare host framework
(`drivers/pci/controller/dwc/`), so the work becomes a **thin vendor glue
driver** rather than a from-scratch host bridge. The `pcie-altera` /
`pci-ftpci100` models from round 90 are no longer the right template.

### Link training (from the L0-wait routine at 0xc0016a80)

```asm
r4 = 2000                       ; retry budget
loop:
  delay()
  ip = [priv+0x14]              ; = ioremap(0x09500000), the ZTE glue block
  r2 = [ip + 0xDC]
  ubfx r2, r2, #17, #6          ; LTSSM state = bits 17..22
  cmp r2, #17                   ; 0x11 = L0
  beq up
  subs r4, r4, #1 ; bne loop
up:
  r3 = [priv+0x08]              ; = ioremap(0x0f000000), the DesignWare DBI
  r2 = [r3 + 0x80]              ; link speed / generation
  printk("pcie%d link up,gen%d,cnt %d!")
```

So:

| what | where |
|---|---|
| DesignWare DBI (core registers) | `0x0f000000` (port 0), `0x0f100000` (port 1) |
| ZTE glue / PHY / LTSSM status | `0x09500000` (port 0), `0x09600000` (port 1) |
| LTSSM state field | glue `+0xDC`, bits 17..22, `0x11` = L0 |
| link speed | DBI `+0x80` |
| third region | `0x1c000000` (size 0x4000) |

### Revised plan

Write `pcie-zx279128.c` as a DesignWare glue driver: supply `dbi_base`, drive
the glue block for reset/PHY/link-up, poll LTSSM at glue `+0xDC` for `0x11`, and
let `dw_pcie_host_init()` do config space, ATU windows and enumeration. Legacy
INTx only (mt76 needs no MSI); calibration comes from NAND via
`mediatek,mtd-eeprom`.


## Round 102: DesignWare confirmed structurally; PCIe block is UNCLOCKED

### The DesignWare call is now proven, not inferred from strings

The red-team found two structural confirmations in the vendor driver, which is
much stronger than the string evidence:

1. **`ldr r2,[r3,#0x80]; ubfx r2,r2,#16,#4`** decodes as
   `PCI_EXP_LNKSTA.Current Link Speed` **iff the PCIe capability sits at config
   offset 0x70** - the canonical DesignWare layout.
2. **Full legacy iATU programming** at `0xc0015994`-`0xc0015a48` on the *same*
   base: `[0x900]` viewport, `[0x904]` CR1, `[0x908]` CR2 = `0x80000000`
   (`PCIE_ATU_ENABLE`), `[0x90C/0x910]` base, `[0x914]` limit, `[0x918/0x91C]`
   target. Nothing but a DWC core uses that layout.

Because the same base carries both config space and the iATU, **`0x0f000000` is
definitively the DBI** and `0x09500000` is the glue.

### Two of my earlier readings were wrong

- **The probe does NOT "bail for a list of board types" (round 100).**
  `0xc0015fec` is a **GPIO reset sequence** - `gpio 53` low, delay, high, then
  `gpio 55` - i.e. PERST#/power-enable. The board-ID check merely selects which
  sequence to run. So the H199A is not excluded, but **GPIO 53/55 are part of
  bring-up and are not in our DT**.
- **`0xf0400000`/`0xf0500000` are not per-port MEM windows** - they are stored
  *identically* for both ports, which per-port windows would not be. Their
  purpose is unknown; recorded as a guess, not a finding.

### The block is not clocked - and reading it hangs the board

Following the review's advice to gather information before writing code, I added
the PCIe regions to the `/proc/zx_eth_regs` dump. Reading them **hung the board**
with no oops and no console output.

On this SoC an access to an unclocked/reset region raises an **imprecise external
abort** that wedges the CPU. So:

- the PCIe block is **not** clocked or is held in reset after boot;
- any driver must release clocks/resets **before** touching DBI or glue;
- and probing unknown regions from a running kernel is dangerous here - the same
  lesson the spifc register probe taught in round 65.

The board recovers on power-cycle (the test kernel was TFTP-booted; flash was
untouched).

### Corrected implementation plan (from the research)

- **Model on `pcie-visconti.c`** (329 lines) - structurally near-isomorphic: a
  glue block separate from DBI, `.link_up` reading the *glue* register and
  comparing LTSSM against `0x11`. Use `(val & mask) == 0x11`, not Visconti's
  buggy bitmask test.
- `.link_up`/`.start_link`/`.stop_link` live in **`dw_pcie_ops`**, not
  `dw_pcie_host_ops`; `pp->ops` must be non-NULL even if empty.
- **A `config` reg-space is mandatory** and cannot be supplied from driver code
  (`dw_pcie_host_init()` hard-fails without it), so the DT node must carry
  `reg`/`reg-names` - a node with no `reg` (as the vendor DT has) cannot work.
- **Omit `"atu"`**: `dw_pcie_iatu_detect()` reads `PCIE_ATU_VIEWPORT` (0x900) and
  auto-selects legacy viewport vs unrolled. Map DBI generously (4 MiB) so the
  provisional `dbi_base + 0x300000` can never be dereferenced past the mapping.
- **Do not hardcode DBI+0x80** for link speed - dwc walks the capability list.
- **INTx is the most likely failure**: the legacy IRQ domain is only created if
  the DT node has an `interrupt-controller` subnode, otherwise `pdev->irq` is
  bogus and mt76 enumerates but never takes an interrupt.
- MT7613E binds via **mt7615** as PCI ID `0x7663`, firmware `mt7663pr2h.bin`;
  MT7603E is `0x7603`. Both use BAR0 only and 32-bit DMA.

### Honest scope

The unbounded risk is the PHY/glue bring-up in `0x09500000` plus the clock/reset
enable that must precede any register access - and the hang above shows we
cannot even look at those registers until that is solved. Probability of a
working mt76 interface: roughly even, better than round 90's "research project"
because the DWC framework removes most of the code.


## Round 103: the "mystery" bases decoded, PERST# lines, and a PHY reset bit

### 0xf04/f05/f06 are static VIRTUAL mappings, not PCI addresses

Round 100 recorded `0xf0400000`/`0xf0500000` as "plain values stored without
ioremap - address-space bases", and round 102 noted they were suspiciously
identical for both ports. Both readings were wrong. The vendor code does:

```asm
mov  r3, #0
movt r3, #0xf060          ; r3 = 0xf0600000
ldr  r5, [r3, #12]        ; direct access, NO ioremap
```

A physical address cannot be dereferenced directly from kernel code, so these are
**statically-mapped virtual addresses**, and the mapping is the obvious one:

```
virt 0xf0400000  <->  phys 0x09400000
virt 0xf0500000  <->  phys 0x09500000    (port-0 glue - also ioremapped)
virt 0xf0600000  <->  phys 0x09600000    (port-1 glue - also ioremapped)
```

Confirmed by the ioremap argument list, which contains exactly `0x09500000` and
`0x09600000` alongside `0x0f000000`/`0x0f100000`. So there is no unexplained
address space: everything is the two glue blocks, the two DBIs, and the outbound
windows.

### Full physical map (ioremap arguments, from the probe)

| physical | purpose |
|---|---|
| `0x0f000000` / `0x0f100000` | DesignWare DBI, port 0 / port 1 |
| `0x09500000` / `0x09600000` | ZTE glue (LTSSM at +0xDC bits 17..22, PHY ctrl at +0x0c) |
| `0x10000000` / `0x20000000` | outbound MEM window, port 0 / port 1 |
| `0x1c000000` / `0x2c000000` | second window per port (config aperture?) |

The `0x1c000000`/`0x2c000000` pairing per port makes the earlier lone
`0x1c000000` sensible: it is per-port, not a singleton.

### PERST# lines

```
gpio_set(53, 0); delay x10;  gpio_set(53, 1); delay x200;
gpio_set(55, 0); delay x10;  gpio_set(55, 1); delay x200;
```

Two reset lines, one per port. Neither is in our DT.

### PHY / reset release

```asm
r5 = [0xf0600000 + 0x0c]     ; glue port1 + 0x0c
r5 &= ~(1 << 14)
[0xf0600000 + 0x0c] = r5
delay x500
```

So **glue + 0x0c bit 14** is an active-high reset (or PHY disable) that must be
cleared. This is the first concrete piece of the bring-up sequence that has to
run before the DBI is accessible - which matches round 102's finding that
touching DBI while unclocked hangs the CPU.

### Where this leaves the driver

Known: DBI and glue addresses, the outbound windows, LTSSM polling, the PERST#
GPIOs, and one PHY reset bit. Still unknown: the rest of the glue init sequence
between reset release and LTSSM reaching L0, and whether a clock gate outside
these blocks also needs enabling.


## Round 104: the PCIe/PHY bring-up sequence, decoded

Extracting every register access in the init path (`0xc0016100`-`0xc0016290`),
using the base pointers the probe stored: `priv+0x0c` = `0xf0500000`
(phys `0x09500000`) and `priv+0x10` = `0xf0400000` (phys `0x09400000`).

```
    A = phys 0x09500000      (port-0 glue)
    B = phys 0x09400000      (shared PHY / PLL block)
    C = phys 0x09600000      (port-1 glue)

 1.  A[0x70] |= 0xb5                          ; delay
 2.  B[0x08] |= BIT(15)                      ; delay
 3.  B[0x08] |= BIT(13)                      ; delay
 4.  B[0x08] |= BIT(14)                      ; delay x50
 5.  A[0x74] &= ~BIT(0)                      ; delay
 6.  C[0x0c] &= ~BIT(14)                     ; delay x500
```

Each step is separated by a delay loop, and every access is bracketed by `dsb`
barriers - the vendor treats this as timing-sensitive.

**`phys 0x09400000` is the block that was previously unaccounted for.** It is not
per-port: bits 15/13/14 of its `+0x08` are set in sequence, which reads like
PLL/PHY enable, then de-assert. That is almost certainly the clock/PHY gate whose
absence makes DBI accesses hang the CPU (round 102).

### Complete picture for the driver

| step | register | operation |
|---|---|---|
| PHY/PLL enable | `0x09400000 + 0x08` | set BIT(15), BIT(13), BIT(14) in order, with delays |
| port cfg | `0x09500000 + 0x70` | set bits `0xb5` (read-modify-write) |
| port release | `0x09500000 + 0x74` | clear BIT(0) |
| PHY reset release | `0x09600000 + 0x0c` | clear BIT(14) |
| PERST# | GPIO 53, GPIO 55 | low, delay, high, delay |
| link poll | glue `+0xDC` bits 17..22 | wait for `0x11` (L0) |
| link speed | DBI capability + `PCI_EXP_LNKSTA` | (walk cap list, do not hardcode +0x80) |

That is a complete first-cut bring-up sequence: enable the PHY block, configure
and release the port, release the PHY reset, toggle PERST#, then poll LTSSM.

### Remaining unknowns

- ~~The value written to `A[0x70]`~~ **resolved**: it is a read-modify-write,
  `A[0x70] |= 0xb5` (`ldr r4,[r3,#0x70]` at `0xc00160dc`, then
  `orr r4, r4, #0xb5`). So step 1 of the sequence is
  `A[0x70] |= 0xb5`.
- Whether `0x09400000` also needs a clock gate outside these three blocks.
- Whether the port-1 path uses `A = 0x09600000` symmetrically (very likely, given
  the probe mirrors every base at `priv+0x40..0x48`).


## Round 105: bring-up test written, and it hung at the FIRST access

Rather than write a ~400-line DesignWare glue driver against an unvalidated
sequence, I wrote a ~120-line opt-in test (`zx_pcie_probe_test.c`, enabled only
with `zx_pcie_test` on the cmdline) that runs the round-104 sequence with a
`pr_info` before **every** step, so a hang identifies the offending step exactly.

Result:

```
[   13.969685] zx-pcie-test: START
[   13.972870] zx-pcie-test: mapped phy/glue0/glue1
[   13.977540] zx-pcie-test: step1 reading glue0+0x70...
                                      <- board wedged here
```

**It hung on the very first register access**, `0x09500000 + 0x70` - before any
write, before the PHY block, before the DBI.

### What this proves and disproves

- The glue block at `0x09500000` is **also unclocked**, not just the DBI. The
  inaccessible region is wider than round 102 established.
- It **disproves the round-103 conclusion** that the sequence operates on
  `phys 0x09400000/0x09500000/0x09600000`. The vendor sequence uses the
  statically-mapped virtuals `0xf0400000/0xf0500000/0xf0600000`, and I inferred
  their physical addresses from a numeric pattern (`0xf05` -> `0x095`). That
  inference is unproven, and the hang is consistent with it being wrong.
- Note the probe *does* `ioremap(0x09500000)` and `ioremap(0x09600000)`, so those
  are real regions. Both statements can hold: the addresses are real but
  unclocked, **and** the static virtuals may map somewhere else entirely.

### The actual blocker, stated precisely

Something enables the PCIe/PHY clock domain, and it is **not in the PCIe driver**
- the driver's whole text region contains no reference to any CRM/clock block
  (round 103 checked: no `0x94xxxxxx` constants). It is done elsewhere: board
init, a platform driver, or the bootloader on a path we do not take.

Searching for a `map_desc` table to resolve the static virtuals found nothing
with the expected layout, so that remains open too.

### Method note

This is the second time a cheap staged probe has saved a long debug session
(round 102 was the first). The test cost one boot and one power-cycle, produced
an unambiguous answer, and left flash untouched because it was TFTP-booted. It
stays in the tree, opt-in and disabled by default, for the next attempt.


## Round 106: PCIe controller ALIVE - clock enable found, DesignWare confirmed on hardware

### The missing piece was a wrong address, and the map_desc table gave it up

The vendor sequence operates on statically-mapped virtual addresses. Round 103
guessed their physical addresses from a numeric pattern (`0xf05` -> `0x095`) and
round 105's test hung on the first access as a result. The kernel's ARM
`map_desc` table (at `0xc059ba80`) gives the truth:

| virt | phys | note |
|---|---|---|
| `0xf0400000` | **`0x94000000`** | topcrm - clock/reset manager |
| `0xf0500000` | **`0x94100000`** | |
| `0xf0600000` | **`0x94200000`** | |
| `0xf0700000` | `0x94400000` | lsp0crpm (UART) |
| `0xf0800000` | `0x9a100000` | lsp1crpm (MDIO) |
| `0xf4000000` | `0x92000000` | Ethernet datapath |

So the "PHY bring-up sequence" is not in the PCIe glue at all - it is a
**clock/reset bring-up in the CRM blocks**, which is exactly the missing enable
that made every PCIe access wedge the CPU in rounds 102 and 105.

### The corrected sequence, verified on hardware

```
[   12.865] step1 reading crm1+0x70...
[   12.870] step1 crm1+0x70 = 00002814        <- readable, no hang
[   12.875] step2 phy+0x08  = 10061fff
[   12.932] step2 done, phy+0x08 = 1006ffff   <- BIT(15|14|13) set
[   12.939] step3 crm1+0x74 0000001b -> 0000001a   <- reset released
[   13.445] step4 crm2+0x0c 003dbf85 (BIT(14) already clear)
```

then the DesignWare DBI at `0x0f000000` becomes readable:

```
DBI+0x00  (vendor/device) = 68301cf2
DBI+0x08  (class/rev)     = 00000001
DBI+0x70  (cap)           = 00420010
DBI+0x80                  = 10110000
DBI+0x8f8 (version)       = 00000000
DBI+0x900 (atu viewport)  = 00000000
pcie glue LTSSM raw=00008000 state=00
```

### Every prediction confirmed

- **`DBI+0x70` low byte = `0x10` = `PCI_CAP_ID_EXP`.** This is precisely the test
  the round-102 red-team named as decisive: the PCIe capability really does sit
  at config offset 0x70, so the DesignWare identification and the whole register
  map are confirmed **on hardware**, not by inference.
- **`DBI+0x8f8` reads 0** - the research said a zero here means a core older than
  v4.70a, which is what a Cortex-A9-era part should be. Not a failure.
- **`DBI+0x900` reads 0, not `0xFFFFFFFF`** - so `dw_pcie_iatu_detect()` will
  select the **legacy viewport** iATU path, as predicted.
- Root port identifies as vendor **`0x1cf2` (ZTE)**, device `0x6830`.
- LTSSM state is `0x00` - the link is not trained, which is expected: the test
  does not toggle PERST# (GPIO 53/55) or start link training.

### What remains for a working link

1. Toggle PERST# on GPIO 53/55 (needs the GPIO controller working in our port).
2. Start link training and poll glue `+0xDC` bits 17..22 for `0x11`.
3. Then the DesignWare host framework can enumerate: `config` reg-space in DT,
   legacy iATU, INTx domain, and mt76 binds as `14c3:7603` / `14c3:7663`.


## Round 107: PCIe LINK UP (LTSSM = L0)

The complete bring-up sequence is now decoded **and verified on hardware**. The
link reaches L0 immediately after training is enabled.

```
[   13.744] extra CRM steps done
[   13.749] glue[0]=00000008 -> set BIT(5)
[   13.755] DBI[0xa0] 00010002 -> 00010001
[   13.763] toggling PERST# gpio53/55
[   14.191] LTSSM raw=00228000 state=11 after 0 polls   <- L0
```

### The full verified sequence

```
CRM0 = phys 0x94000000   (topcrm)
CRM1 = phys 0x94100000
CRM2 = phys 0x94200000
GLUE = phys 0x09500000   (PCIe port-0 glue)
DBI  = phys 0x0f000000   (DesignWare core)
GPIO = phys 0x94407000

 1. CRM1[0x70] |= 0xb5                       ; delay
 2. CRM0[0x08] |= BIT(15) ; BIT(13) ; BIT(14) ; staged, delay 50 ms
 3. CRM1[0x74] &= ~BIT(0)                    ; delay
 4. CRM2[0x0c] &= ~BIT(14)                   ; delay 500 ms
    --- DBI is now accessible ---
 5. CRM0[0x24] &= ~BIT(26)                   ; delay 50 ms
 6. CRM1[0x74] |= BIT(0)
 7. CRM1[0x70] &= ~BIT(8)
 8. GLUE[0x00] |= BIT(5)                     ; LTSSM enable / start training
 9. DBI[0xa0]   = (v & ~0xf) | 1             ; LNKCTL2 target speed = Gen1
                                             ; (cap@0x70 + PCI_EXP_LNKCTL2 0x30)
10. PERST#: GPIO 53 low/10ms/high/200ms, then GPIO 55 the same
11. poll GLUE[0xDC] bits 17..22 until 0x11 (L0)
```

### GPIO controller

No GPIO node exists in the stock DT. The vendor holds a statically initialised
pointer at `0xc05c1aac` = virt `0xf0707000`, which the map_desc table resolves to
**phys `0x94407000`** - the same `lsp0crpm` block as UART0 (`0x94404000`) and
spifc (`0x94406000`).

```
bank  = gpio >> 4      (banks are 0x40 bytes apart)
bit   = gpio & 15
+0x14 input   +0x18 set output   +0x1c clear output
```

PERST# lines: GPIO 53 = bank 3 bit 5, GPIO 55 = bank 3 bit 7.

### State of play

Confirmed on hardware: clock/reset bring-up, DesignWare identity (vendor `0x1cf2`
device `0x6830`, PCIe capability at config offset 0x70), legacy iATU viewport,
GPIO/PERST# control, LTSSM reaching **L0**.

Next: enumerate. That needs the DWC host framework (config reg-space in DT,
iATU CFG window, INTx domain) so `mt76` can bind to the endpoint as
`14c3:7603` / `14c3:7663`.


## Round 108: ENDPOINT IDENTIFIED - MediaTek MT7613BE enumerated over the RE'd link

Reading the endpoint's config space by hand, through a legacy-viewport iATU CFG0
window programmed directly:

```c
writel(0,          db + 0x900);   /* viewport 0        */
writel(0x1c000000, db + 0x90c);   /* lower base        */
writel(0x1c0fffff, db + 0x914);   /* limit             */
writel(0x01000000, db + 0x918);   /* target: bus1 dev0 fn0 */
writel(0x4,        db + 0x904);   /* CTRL1 = type CFG0 */
writel(BIT(31),    db + 0x908);   /* CTRL2 = enable    */
```

Result:

```
DEBUG1=08000010 link_up=1 in_training=0
LNKSTA speed=1 width=1
ENDPOINT bus1.dev0 ID = 766314c3 (vendor 14c3 device 7663)
ENDPOINT class/rev = 00028000  BAR0 = 0000000c
```

### What this establishes

- **The device is a MediaTek MT7613BE** (`14c3:7663`). Round 99's research
  predicted exactly this: MT7613E enumerates as `0x7663` and is handled by the
  **`mt7615e`** driver in mainline (there is no `mt7613` directory), with
  firmware `mt7663pr2h.bin`.
- **`class 0x0280`** = network controller, other - correct for a wireless part.
- **`BAR0 = 0x0000000c`** = 64-bit prefetchable memory BAR, unsized (matches
  mt76, which uses BAR0 only).
- **The link is genuinely up**, confirmed independently of LTSSM:
  `DEBUG1` bit 4 `LINK_UP = 1` and bit 29 `IN_TRAINING = 0`, with
  **LNKSTA negotiated Gen1 x1**. The instant-L0 result from round 107 was real,
  not a coincidental bit pattern - config reads returning a valid MediaTek ID
  through the link settle it beyond doubt.
- The iATU legacy viewport works exactly as documented, which validates the
  window programming the real driver will do.

### Remaining work is ordinary Linux integration

Everything SoC-specific is now solved and verified on hardware. What is left:

1. `pcie-zx279128.c` DWC glue driver wrapping the verified bring-up sequence.
2. A DT node with the mandatory `config` reg-space, `ranges` MEM window,
   `bus-range`, and an `interrupt-controller` subnode for INTx.
3. `CONFIG_MT7615E` plus firmware `mt7663pr2h.bin`.
4. Calibration from NAND via `mediatek,mtd-eeprom = <&wifi 0x...>` (mtd3).

No public port of any ZTE ZXHN ONT had ever enumerated its Wi-Fi chip under a
custom kernel; this one now does.


### Round 108 review corrections

The red-team reviewed the round-107 state and its decisive recommendation - run
the endpoint test before writing any driver - was executed this round with the
favourable outcome (`14c3:7663` answered). Its criterion for continuing Wi-Fi
("if a real mt76 vendor ID answers, finish it; it is then a bounded integration
job") is therefore met. The rest of its findings stand and are recorded here.

**Corrections accepted:**

- **Port 1 has never been brought up.** The sequence sets `BIT(5)` only in
  **port 0's** glue (`0x09500000`). So MT7613BE is on **port 0**; the 2.4 GHz
  MT7603E is presumably on port 1 (`0x09600000` glue, `0x0f100000` DBI,
  `0x2c000000` aperture) and its absence has **not** been demonstrated - it has
  simply never been probed.
- **`clk_ignore_unused` is an unpinned dependency.** It is on our kernel cmdline,
  so the bring-up may be relying on a clock U-Boot left running. We have no clock
  driver for this domain. If that flag is dropped or U-Boot changes, PCIe could
  break for reasons that look unrelated.
- **The sequence is not idempotent**: `CRM1[0x74]` is cleared then set, and
  `CRM1[0x70]` gets `|= 0xb5` then `&= ~BIT(8)`. The test at `late_initcall` and
  a driver at probe must never both run.
- **The delays are my invention.** The vendor passes an opaque loop count
  (`0x66665b0`), not microseconds. Our `mdelay(1/50/500)` are almost certainly
  longer - the safe direction - but the sequence is NOT validated at shorter
  delays and must not be "optimised" later.
- **Treat `0xffffffff` explicitly as "no device"** in any config read.
- **INTx is the top remaining risk**, and the acceptance test is
  `/proc/interrupts` after bringing the interface up - **not** `lspci`. The
  documented failure mode is: enumerates fine, BAR0 reads fine, handler never
  fires.
- **`config` aperture must not overlap the MEM `ranges` window**, or CFG and MEM
  outbound windows fight and BAR0 reads `0xffffffff` after a successful probe.

**Overclaim corrected:** "the remaining work is ordinary Linux integration" was
too strong. Hand-wiring INTx for an undocumented glue block on an SoC with no
public PCIe port is not routine. The DesignWare finding improved the odds; it did
not make the work mechanical.

### On priorities: persistence versus Wi-Fi

The review argues - correctly - that **a router which forgets its configuration
on every power cycle is not deployable, while one without Wi-Fi is merely
limited**. It also found a flaw in the round-99 stopping point: the driver's
`DATA_OUT` path *does* honour the column offset (`memcpy(sp->pagebuf + col, ...)`),
so in-page OOB writes at columns >= 2048 do land and `oobavail = 62` is ample for
cleanmarkers. **"OOB writes are broken" is therefore not the explanation, and the
NOP=1 hypothesis remains plausible but unproven.**

The likely right answer is not to patch JFFS2 at all but to use **UBI/UBIFS**,
which handles NOP limits, wear levelling and bad blocks properly and is
OpenWrt's first-class NAND `rootfs_data` backend. That is plausibly less work
than the Wi-Fi tail and removes a whole class of problems.

Plan: finish the Wi-Fi integration (now bounded), then move to UBI-based
persistence rather than further JFFS2 debugging.


## Round 108b: PCIe host driver WORKING - MT7613BE enumerated by Linux

`pcie-zx279128.c` (a DesignWare glue driver wrapping the verified bring-up
sequence) plus a proper DT node now bring the bus up under the standard Linux
PCI stack:

```
zx279128-pcie f000000.pcie: host bridge /soc/pcie@f000000 ranges:
zx279128-pcie f000000.pcie:      MEM 0x0010000000..0x001bffffff -> 0x0010000000
zx279128-pcie f000000.pcie: iATU: unroll F, 5 ob, 5 ib, align 64K, limit 4G
zx279128-pcie f000000.pcie: PCIe Gen.1 x1 link up
zx279128-pcie f000000.pcie: PCI host bridge to bus 0000:00
pci_bus 0000:00: root bus resource [mem 0x10000000-0x1bffffff]
pci 0000:01:00.0: [14c3:7663] type 00 class 0x000280
```

`iATU: unroll F, 5 ob, 5 ib, align 64K` confirms the legacy viewport path with
five outbound and five inbound windows - exactly what the research predicted for
a pre-v4.70a core, and it answers the open question about window count.

### Two problems solved on the way

- **`IRQ index 0 not found` / `-ENXIO`.** `dw_pcie_host_init()` calls
  `dw_pcie_msi_host_init()`, which looks for an `"msi"` interrupt in DT. This
  controller has no MSI receiver. Fixed by providing a `.msi_host_init` that
  returns 0, which suppresses the built-in MSI setup. INTx needs no code: in 6.6
  the DesignWare layer builds **no** legacy IRQ domain, and the PCI core resolves
  INTx from the DT `interrupt-map`.
- **DT `interrupt-map` phandle** must reference the GIC by its actual label
  (`&gic`), not an invented one.

### Driver shape

- `.link_up` reads glue `+0xDC` bits 17..22 and compares against `0x11` (L0).
- `.start_link` forces Gen1 via `DBI+0xa0` (LNKCTL2), sets glue `+0x00` BIT(5)
  to enable LTSSM, then toggles PERST# on GPIO 53 and 55.
- The CRM clock/reset sequence runs in probe, **before** `dw_pcie_host_init()`,
  because any DBI access before it wedges the CPU - including the ones dwc makes
  while detecting the core version and iATU.
- The sequence is not idempotent, so the standalone `zx_pcie_probe_test.c` must
  stay disabled when the driver is built in.

### Remaining for a working wlan0

The rootfs on flash carries kernel modules built against the previous config, so
module loading fails with "section size must match" - the rootfs needs
rebuilding against this kernel. Then: `CONFIG_MT7615E`, firmware
`mt7663pr2h.bin`, and `mediatek,mtd-eeprom` calibration from mtd3.


## Round 109: Wi-Fi wired into the build recipe

The driver and its dependencies are now part of the reproducible recipe rather
than hand-patched into `build_dir`:

- `files/target/linux/armsr/files-6.6/drivers/pci/controller/dwc/pcie-zx279128.c`
- `files/target/linux/armsr/patches-6.6/992-zte-pcie-driver.patch` - adds the
  Kconfig entry and Makefile rule for the driver.
- `config-6.6`: `CONFIG_PCIE_ZX279128=y`
- `seed.config`: `kmod-mt7615e`, `kmod-mt7615-firmware`, `kmod-mt76-core`,
  `wpad-basic-mbedtls`, `iw`

`make defconfig` pulls in the full dependency set:

```
CONFIG_PACKAGE_kmod-mt76-connac=y
CONFIG_PACKAGE_kmod-mt76-core=y
CONFIG_PACKAGE_kmod-mt7615-common=y
CONFIG_PACKAGE_kmod-mt7615-firmware=y
CONFIG_PACKAGE_kmod-mt7615e=y
```

A full rebuild is required regardless of Wi-Fi: the flash rootfs carries modules
built against the previous kernel config, so module loading fails with
"section size must match the kernel's built struct module size". That is an ABI
mismatch from testing hand-built kernels against an older rootfs, not a defect.


## Round 118: Wi-Fi WORKING - mt76 bound, firmware loaded, phy0 registered

Booting OpenWrt from NAND:

```
mt7615e 0000:01:00.0: mediatek/mt7663pr2h.bin not found,
                      switching to mediatek/mt7663pr2h_rebb.bin
mt7615e 0000:01:00.0: HW/SW Version: 0x65322d31, Build Time: 2009041715da1a1
mt7615e 0000:01:00.0: N9 Firmware Version: 7663mp1827, Build Time: 20200904171623

# ls /sys/class/ieee80211/
phy0
# iw phy phy0 info
Wiphy phy0
	wiphy index: 0
	max # scan SSIDs: 4
```

The MediaTek MT7613BE behind the reverse-engineered DesignWare PCIe root complex
is now a fully initialised mac80211 device: driver bound, firmware uploaded, and
a wiphy registered.

### What it took

| piece | rounds |
|---|---|
| locate + identify the vendor PCIe driver | 100-101 |
| decode clock/reset bring-up (CRM blocks, not PCIe glue) | 103-106 |
| link training to L0, PERST# via undocumented GPIO block | 107 |
| enumerate the endpoint by hand-programming an iATU CFG0 window | 108 |
| DesignWare glue driver + DT node | 108 |
| recipe integration, mt7615e + MT7663 firmware packaging | 109 |
| boot the rootfs that carries it | 110-118 |

No public port of any ZTE ZXHN ONT had previously enumerated its Wi-Fi chip under
a custom kernel.


## Round 119: calibration loaded - real MAC and full TX power

### The problem

With mt76 bound and `phy0` registered, the AP came up but was invisible to an
external scanner. Two causes, found in order:

1. **Regulatory domain was `country 00`** (world), which caps 5 GHz hard. Setting
   `wireless.radio0.country=BR` moved the limit to 27 dBm - but the PHY still
   reported 3.0 dBm per channel, so this was not the binding constraint.
2. **No calibration data.** mt76 falls back to 3 dBm and a random MAC when it
   cannot find an EEPROM:
   ```
   mt7615e 0000:01:00.0: Invalid MAC address, using random address 9e:a6:a6:3a:e7:ec
   ```

### The calibration blob

The vendor stores an mt76 EEPROM at **`wifi` partition + 0x20000** (`mtd3`):

```
63 76 00 01 00 0c 43 26  60 00 63 76 c3 14 00 80
^^^^^ 0x7663 = MT7663    ^^^^^^^^^^^^^^^^^ MAC 00:0c:43:26:60:00
```

Chip id then MAC - exactly the mt76 EEPROM layout.

### DT wiring, and the mistake worth recording

A flat `wifi@0,0` directly under the controller node does **not** match. The
endpoint sits on bus 1 behind the root port, and the DT must mirror that:

```dts
pcie@f000000 {
	...
	pcie@0,0 {                       /* root port: bus 0, dev 0 */
		reg = <0x0000 0 0 0 0>;
		#address-cells = <3>;
		#size-cells = <2>;
		device_type = "pci";
		ranges;

		wifi@0,0 {               /* endpoint: bus 1, dev 0 */
			compatible = "mediatek,mt76";
			reg = <0x0000 0 0 0 0>;
			mediatek,mtd-eeprom = <&wifi_cal 0x20000>;
		};
	};
};
```

### Result

```
Access Point: 00:0C:43:26:60:00      <- vendor MAC from flash, not random
Tx-Power: 24 dBm                     <- was 3 dBm
Mode: Master  Channel: 36 (5.180 GHz)  HT Mode: VHT80
```

### Not yet verified: over the air

An external scan (a Raspberry Pi, `tiny`) did **not** see the SSID while the
radio was at 3 dBm. **The board currently has no antennas fitted**, so
over-the-air association is untested and the 24 dBm result is only what the
driver reports. Antennas are being fitted; re-run the external scan afterwards.

Note also that transmitting at 24 dBm with unterminated antenna ports reflects
most of the power back into the front end - do not leave the radio beaconing
without antennas.


## Round 120: PCIe port 1 attempted - it hangs, and needs its own clock enable

The USB adapter fitted for external verification is a **Ralink RT3070, 2.4 GHz
only**, while our working radio (MT7613BE) is 5 GHz - so it can never see our
AP. The vendor ships a 2.4 GHz part too (`mt7603e_ap`), which should sit on PCIe
**port 1**, so bringing that up would give a radio the adapter can verify.

Added a `pcie@f100000` node mirroring the vendor's port-1 bases (DBI
`0x0f100000`, glue `0x09600000`, MEM window `0x20000000`, config aperture
`0x2c000000`), and guarded the chip-wide CRM sequence so it runs exactly once
across both port instances (it is not idempotent).

**Result: the board hangs.** The probe prints its ranges and then wedges:

```
zx279128-pcie f100000.pcie: PCIe domain already enabled, skipping CRM sequence
zx279128-pcie f100000.pcie: host bridge /soc/pcie@f100000 ranges:
zx279128-pcie f100000.pcie:      MEM 0x0020000000..0x002bffffff -> 0x0020000000
                                  <- console dead from here
```

No iATU detection line, no link-up, no response to input afterwards. That is the
same imprecise-external-abort signature as rounds 102 and 105: **the first DBI
access to an unclocked region wedges the CPU**.

**Conclusion: the CRM sequence that enables port 0 does NOT enable port 1.**
Port 1 needs its own clock/reset bring-up, which has not been decoded. The
node is kept in the DTS with `status = "disabled"` and this explanation, since
the addresses are believed correct and only the enable sequence is missing.

The port-0 driver change (running the CRM sequence once across instances) is
correct regardless and is kept.

State restored afterwards: port 0 boots and the AP comes up as before -
`H199A-TEST`, MAC `00:0C:43:26:60:00`, 24 dBm.


## Round 121: RF output CONFIRMED by hardware counters

The review correctly refused to accept "Wi-Fi works" on driver-reported state
(`iwinfo` output, hostapd running, bridge forwarding) - none of which proves RF
energy leaves the chip. It suggested a local measurement that needs no external
device, and it settles the question:

```
# iw dev phy0-ap0 survey dump
	frequency:			5180 MHz [in use]
	noise:				-92 dBm
	channel active time:		14891 ms
	channel busy time:		343 ms
	channel receive time:		469 ms
	channel transmit time:		47 ms
```

These are **hardware counters**, not configuration read-back:

- **`channel transmit time: 47 ms`** - the MAC/PHY is keying the transmitter.
  Over ~15 s of active time, at a 100 ms beacon interval, ~150 beacons of a few
  hundred microseconds each is ~45 ms. The number matches beaconing precisely.
- **`noise: -92 dBm`** - a plausible noise floor means the receive chain is alive
  and on-channel; a dead RX cannot synthesise this.
- **`channel receive time: 469 ms`** - it is demodulating other people's traffic.

So the radio transmits and receives. What remains unproven is only **link
quality / range** - i.e. whether a client can associate and pass traffic, which
still wants an external 5 GHz device.

### Claim wording corrected

Previously: "Wi-Fi works." Now: **the driver, MAC and RF layers are all
functional - TX and RX confirmed by hardware counters - but no client has
associated, so throughput and range are unmeasured.**

### Calibration blob: reviewed and accepted

The review dumped the full `MT7615_EEPROM_FULL_SIZE` (19880 B) range and found it
92.3% `0xff`, which looks alarming but is almost certainly correct:

- `MT_EE_CALDATA_FLASH @0x052 = 0x0000` is the standard "no pre-calibration in
  flash, calibrate at runtime" marker, so blank DCOC/TXDPD regions are expected.
- A scan of the whole 1 MiB `wifi` partition found exactly one non-blank 4 KiB
  chunk, at `+0x20000` - our offset is right and there is no better blob.
- Populated and plausible: chip id `0x7663`, version `0x0100`, MAC
  `00:0c:43:26:60:00`, and per-chain 5 GHz target power tables at `0x070`/`0x098`.

One field worth cross-checking later: `NIC_CONF_0/1 @0x034/0x036` both read
`0x0000`, so **no external PA/LNA is declared**. If this board has an ePA, it is
not being enabled - which would cap real-world range without affecting any of the
counters above.

## Round 121: PCIe port 1 still hangs, with the right registers

The vendor's port-index branch gives port 1 a *different bit pattern in the same
CRM registers* as port 0:

```
port 0:  CRM1[0x70] |= 0xb5      CRM0[0x08] |= BIT(15)|BIT(13)|BIT(14)
port 1:  CRM1[0x70] |= 0x1AA00   CRM0[0x08] |= BIT(27)
```

(Independently derived twice - by disassembly here and by the review.)
Implemented as a per-port sequence selected by a `zte,pcie-port` DT property.

**It still hangs** at the first DBI access, so more of the port-1 bring-up is
missing than these two writes. The node stays `status = "disabled"` with the
findings recorded. Worth resuming later - 2.4 GHz is half this product's Wi-Fi,
and most clients prefer it - but not as test scaffolding for a 2.4 GHz-only USB
scanner.


## Round 132: protocol-level RX PROVEN - the board demodulates real 802.11

I had been treating Wi-Fi verification as blocked on not having a second 5 GHz
device. That was wrong: the board has a 5 GHz radio and the environment has
5 GHz APs, so the radio can be pointed at them.

```sh
iw phy phy0 interface add scan0 type station
ifconfig scan0 up
iw dev scan0 scan
```

Result - **15 BSSs found**, including:

```
BSS 50:4f:3b:32:68:9f   freq 5180.0   signal -68.00 dBm     <- "BRAVO"
BSS 8c:83:94:6d:9b:81   freq 5180.0   signal -91.00 dBm
SSIDs: BRAVO, BRAVO-IOT, condominio2irmao5G, Desktop_F0725371_5G,
       Desktop_F7761304_5G, Desktop_F0026305_5G, Ap24, ...
```

`50:4f:3b:32:68:9f` on 5180 MHz is **the exact BSSID an independent machine
(the `tiny` Raspberry Pi) reported for that AP on channel 36**, so this is
corroborated by a second observer.

This proves far more than the survey counters did: the receive chain
demodulates real 802.11 frames, parses beacons, extracts SSIDs and BSSIDs, and
reports plausible per-BSS RSSI across both bands.

### Claim status

| layer | evidence |
|---|---|
| PCIe enumeration, driver bind, firmware load | logs |
| TX keying | `channel transmit time` counter |
| **RX at protocol level** | **this scan, corroborated externally** |
| association / throughput | still unproven |

Remaining for a complete Wi-Fi claim: associate as a client (or have a client
associate to our AP) and measure throughput.


## Round 133: the MT7663 is dual-band, but only its 5 GHz path has an antenna

### The chip supports 2.4 GHz

`iw phy phy0 info` lists 2.4 GHz channels at 20 dBm, and an AP configured on
channel 6 comes up correctly:

```
ESSID: "H199A-24G"   Mode: Master   Channel: 6 (2.437 GHz)   HT Mode: HT20
Tx-Power: 27 dBm     Encryption: WPA2 PSK (CCMP)
```

So this looked like a way to finish the association test using the 2.4 GHz-only
USB adapter available on the host.

### But nothing can hear it, and it can barely hear anything

The USB adapter scans fine (it lists a dozen local APs) and never sees
`H199A-24G`. The board's own survey counters show why - it transmits, but its
receiver is deaf:

| band | channel active | channel receive | receive / active |
|---|---|---|---|
| 5 GHz ch36 | 23 758 ms | **1839 ms** | 7.7% |
| 2.4 GHz ch6 | 118 979 ms | **14 ms** | 0.012% |

A ~640x difference in relative receive time, in a band that is far busier than
5 GHz here. TX keys in both cases (`channel transmit time` 2084 ms on 2.4 GHz),
so the MAC/PHY is working - the energy simply is not reaching an antenna.

### Conclusion (corrected - all antennas ARE connected)

My first conclusion here was "the 2.4 GHz antenna is not wired to this chip".
The board owner confirms **every antenna is connected**, so that wording was
wrong, and the better explanation is simpler:

**This module is an MT7613BE - the 5 GHz-ONLY member of the family.** The vendor
firmware names its driver `mtk7613e_ap`, and MT7613BE has no 2.4 GHz RF
front-end at all. The PCI ID reads `14c3:7663` and `mt7615e` advertises both
bands generically from shared code, so `iw phy` lists 2.4 GHz channels that the
silicon cannot actually radiate or receive on.

That fits the measurements better than an antenna fault: the MAC/PHY keys the
transmitter normally (2084 ms of TX) while the receiver is essentially dead
(14 ms) - which is what a missing RF path in the part itself looks like, not a
disconnected antenna.

The 2.4 GHz antennas on this board therefore belong to the **separate MT7603E**,
which the vendor drives via `mt7603e_ap` - and which sits on PCIe port 1.

This **corrects the inference made earlier this round** that a dual-band MT7663
made PCIe port 1 unnecessary. The opposite is true: 2.4 GHz on this device
requires bringing up port 1 and its MT7603E, because that is the only part with
a 2.4 GHz radio.

It also means the association test cannot be done with the 2.4 GHz-only USB
adapter, and still needs either a 5 GHz client or port 1.


## Round 134: port-1 SerDes writes found and tried - still hangs

Disassembling further into the vendor's port-1 branch (0xc00164b0..0xc001651c)
turned up writes that port 0 never makes - absolute constants, not
read-modify-write, which is what PHY/PLL lane setup usually looks like:

```
[blk+0x1b4] = 0x00202d5a
[blk+0x1b0] = 0x0046c24a
```

The block pointer is `[priv+0x14]`, which by the established pattern
(`+0x0c` = CRM1 @0x94100000, `+0x10` = CRM0 @0x94000000) should be
CRM2 @0x94200000.

Implemented for port 1 as: CRM1[0x70] |= 0x1AA00, CRM0[0x08] |= BIT(27),
CRM2[0x1b4] = 0x00202d5a, CRM2[0x1b0] = 0x0046c24a, then the same reset release
port 0 performs (CRM1[0x74] toggle around CRM2[0x0c] &= ~BIT(14)).

**Result: unchanged.** Port 0 still trains and enumerates the MT7613BE; port 1
prints its ranges and then wedges the CPU on the first DBI read at 0x0f100000.

So either `[priv+0x14]` is not CRM2, or these registers are not the missing
enable, or an additional step earlier in the vendor's flow (power domain,
reference clock select, or PHY bifurcation from x2 to 1+1) has not been found.

Node left `status = "disabled"`. Web research on multi-port DWC bring-up is
pending; the specific question is whether a shared PHY defaults to x2 (both
lanes on port 0) and needs an explicit 1+1 bifurcation before port 1's register
block is clocked at all.


### Round 134 addendum: what the zero-risk probes established

Research (see `research/PCIE-PORT1-BRINGUP-RESEARCH.md`) recommended reading the
CRM registers before spending more effort on sequencing. Done from **U-Boot**,
where a hang costs only a power cycle:

```
md 0x94100070      -> 00002814
mw 0x94100070 0x0001aa14 ; md   -> 0001aa14      <- port-1 bits STICK
md 0x94000008      -> 10061fff
mw 0x94000008 0x18061fff ; md   -> 18061fff      <- BIT(27) STICKS
```

So the port-1 configuration bits are writable and persist; the CRM registers are
not read-only or absent.

A useful control fell out of the same session: **reading port 0's DBI
(`md 0x0f000000`) from U-Boot also hangs**, because U-Boot never runs the
enable sequence. That confirms the hang is simply "DBI not clocked yet" and that
our port-0 CRM sequence is exactly what makes that region readable - it is not
something peculiar to port 1's address.

### Open leads, ranked (from the research report)

1. ~~The vendor DT declares only one PCIe node, so port 1 may be dead code for a
   sibling die.~~ **REFUTED (round 135) by evidence already in our own logs.**
   The stock firmware brings up BOTH ports on THIS board:

   ```
   pcie0 irq is 37                     pcie1 irq is 38
   synopsys pcie0 controller setting   synopsys pcie1 controller setting
   pcie0 link up,gen1,cnt 11!          pcie1 link up,gen1,cnt 10!
   PCI host bridge to bus 0000:01
   pci_bus 0000:01: root bus resource [mem 0x20000000-0x27ffffff]
   pci 0000:01:00.0: BAR 0: assigned [mem 0x20000000-0x200fffff]
   ```

   Port 1 trains to L0 and has a device behind it, with a single 1 MiB BAR - a
   different layout from port 0's device (BARs 0/2/4), consistent with an
   MT7603E. Our guessed MEM window (0x20000000) was also correct. The vendor DT
   node carries no `reg` at all, so it never described either port; its absence
   was never evidence.
2. **Our port-1 path returns early** and never performs the second phase the
   port-0 path calls "after the core is reachable" - it never clears
   `CRM0[0x24] BIT(26)` or `CRM1[0x70] BIT(8)`.
3. Port 0 sets a contiguous triple in `CRM0[0x08]` (bits 13/14/15); port 1 sets
   only BIT(27) - the analogous triple would be 25/26/27.
4. Port 1 re-pulses the chip-wide `CRM1[0x74]` reset underneath a live port 0,
   which our own header says must run exactly once.
5. Unexplored and probably richest: four ZTE U-Boot images under
   `ref/ZX279127S-Reverse/uboot-img/ZX279127S/`.

Also worth recording, because it invalidates a debugging approach I would
otherwise have tried: on ARM in this tree every external-abort FSR code binds to
`do_bad`, which returns 1, so `do_DataAbort()` never calls `fixup_exception()`.
`get_kernel_nofault()` and friends **cannot** trap this fault - they handle
translation faults only. The mechanism that works is `hook_fault_code()`.


## Round 136: block identities corrected; port 1 still hangs, but the fault is narrowed

### Correction: [priv+0x14] is the GLUE block, not CRM2

Disassembling the vendor bring-up end-to-end from its anchored entry
(`0xc00160a4`, found via the `synopsys pcie%d controller setting` string) instead
of sampling windows shows the port-0 tail:

```
CRM1[0x74] |= BIT(0)
CRM1[0x70] &= ~BIT(8)
[priv+0x14][0x00] |= BIT(5)      <- the LTSSM enable, which we already know is glue+0x00
```

So `[priv+0x14]` is the **GLUE** base. Round 134 therefore wrote the SerDes
constants (`0x00202d5a`, `0x0046c24a` at +0x1b4/+0x1b0) to CRM2, which was simply
the wrong block - explaining why they had no effect.

### What was tried this round

Port-1 sequence, corrected: CRM1[0x70] |= 0x1AA00, CRM0[0x08] |= BIT(27),
GLUE1[0x1b4] = 0x00202d5a, GLUE1[0x1b0] = 0x0046c24a, then the **second phase**
the port-0 path performs and round 134's branch returned before reaching:
CRM0[0x24] &= ~BIT(26), CRM1[0x74] |= BIT(0), CRM1[0x70] &= ~BIT(8).

**Still hangs** on the first DBI read at 0x0f100000.

### ~~But the fault is now narrower~~ - WITHDRAWN (round 138)

I wrote that the GLUE writes to `0x09600000` "complete without hanging", so port
1's glue must be clocked while only its DBI is gated. **That does not follow.**
ARM stores are posted: a `writel` to a mapped-but-wrong address, or into a region
whose writes are swallowed, completes silently and never faults. A write can
never demonstrate that a region is alive.

Worse, `0x09600000` appears nowhere in the vendor binary (nor does `0x09500000`,
the port-0 glue that demonstrably works), so **port 1's glue base is an
unverified mirror-guess**. If it is wrong, every port-1 write attempted in rounds
134 and 136 went into a hole - which would explain all of those rounds with no
gating mystery at all.

### Next

The vendor has a register-dump routine at **`0xc0016890`** (string: `synopsys
pcie port%d controller debug print`). It enumerates exactly which registers the
vendor considers part of a port's state - the cheapest available map of what is
still missing. Disassemble that rather than guessing further.


## Round 137: port-1 config aperture confirmed; the DBI base is still a guess

### Confirmed from the vendor binary

The config-space accessor selects the aperture per port with a conditional pair
(`0xc0015bb4`/`0xc0015bbc`):

```
port 0:  r1 = 0x1c000000     (movteq r2, #0x1c00)
port 1:  r1 = 0x2c000000     (movtne r2, #0x2c00)
```

Both match what our DT already declares, so the config windows are right.

### What is NOT confirmed - and matters

**Port 1's DBI base has never been observed anywhere.** `0x0f100000` is a guess
I made by mirroring port 0's `0x0f000000`, and every port-1 attempt since round
120 has assumed it. A wedge on the first read is equally consistent with:

- a correct address whose clock gate we have not found, or
- **an address that simply does not decode** - reading port 0's DBI from U-Boot
  also hangs, so "hang" does not distinguish these two cases at all.

Attempts to extract the real value from the binary so far:

- the static `map_desc` table at `0xc059ba80` maps CRM/periph blocks but no PCIe
  DBI, so the vendor ioremaps it dynamically;
- searching for `0x0f000000`/`0x09500000` as literal words finds only unaligned
  byte coincidences - the GLUE base has no literal at all;
- the per-port base pointers live at `0xc05a92a4`, which is BSS (all zeros in the
  image) and therefore filled at runtime.

So the next step is to find the `ioremap` call sites that populate
`0xc05a92a4`, and read the constants passed to them, rather than assuming a
mirrored layout. Until that is done, further bring-up sequencing work on port 1
is premature - it may be aimed at the wrong address.


## Round 138: the DBI address was right all along - and two real DTS bugs found

### The answer was stored as data, not encoded in instructions

The vendor keeps a **named `struct resource` array** at `0xc05b2aa8`:

```
0xc05b2aa8: 0x0f000000-0x0f003fff  "pcie0 reg"
0xc05b2ac4: 0x0f100000-0x0f103fff  "pcie1 reg"
0xc05b2ae0: 0x10000000-0x17ffffff  "pcie0 mem space"
0xc05b2afc: 0x20000000-0x27ffffff  "pcie1 mem space"
```

The MEM entries match the captured stock boot log exactly, so the table is
authoritative. **`0x0f100000` - the original round-120 guess - is correct.**

This round I had reasoned that the confirmed windows use a 0x10000000 stride
(config `0x1c000000`->`0x2c000000`, MEM `0x10000000`->`0x20000000`) and moved the
DBI to `0x1f000000`. That was wrong and the board crashed on it. The earlier
guess had been right by luck: two different deltas had been applied across four
regions with no justification, and the only *confirmed* port-1 address used the
delta that was NOT applied to the DBI.

### Two real bugs the table exposed

| item | was | should be |
|---|---|---|
| DBI window (both ports) | `0x1000` | **`0x4000`** - the hardware presents 16 KiB |
| MEM window (both ports) | `0x0c000000` | **`0x08000000`** - vendor decodes 128 MiB, we advertised 192 |

Port 0 survived both because the legacy iATU viewport sits at DBI+0x900 and
nothing was ever allocated above `0x17ffffff`. The DBI size matters directly for
the port-1 work: the earlier note incorrectly said `+0x1b0/+0x1b4` fell outside a 4 KiB
mapping. Both offsets are inside it; that was not evidence for the proposed
base-address explanation. Later work identified the glue block.

### Glue base still unverified, and U-Boot cannot check it

The read-only probe recommended by review is inconclusive here: reading **port
0's** glue at `0x09500000` from U-Boot - an address known to work - also hangs,
because U-Boot never runs the enable sequence. So the glue block is gated exactly
like the DBI, and the two bases cannot be told apart from U-Boot.

To settle it, the read must happen from our Linux **after** port 0's sequence has
run. That needs a small debug read exposed from the driver, since the image has
no `devmem`.

### Method note

Three rounds went into instruction-level reconstruction while the decisive fact
sat in a named data structure in the same binary. In round 135 the decisive fact
sat in a log I had already captured. Before the next disassembly session, ask
first: **is this stored somewhere as data?**


## Round 139: port 1's glue base is WRONG - which explains every failed attempt

### The test writes could never have performed

Added an opt-in probe (`zx_pcie_glueprobe`) that **reads** candidate glue bases
after port 0's enable sequence has run, printing a marker before each read so a
wedge identifies its own cause. Reads are the right instrument here: ARM stores
are posted, so writes cannot distinguish a live region from a hole.

```
glueprobe: about to read 0x09500000
glueprobe: 0x09500000 +0x00 = 0x00000008      <- port 0, known good
glueprobe: 0x09500000 +0xdc = 0x00008000
glueprobe: about to read 0x09600000
                                              <- wedged here
```

**`0x09600000` does not decode.** Port 1's glue base has been wrong since round
120, so every port-1 write in rounds 134 and 136 - the CRM bits, the SerDes
constants, the second-phase sequence - went into a hole. There was never a
gating mystery; the driver was writing to nothing.

Two placement lessons from getting this test right:

- the probe must run **after** `zx_pcie_domain_enable()`; before it, even port
  0's known-good base wedges (verified - the first attempt hung there);
- `CONFIG_CMDLINE_FORCE` means DT `bootargs` are ignored; the flag has to go in
  `CONFIG_CMDLINE` (the running cmdline contained `clk_ignore_unused`, which is
  not in the DT, and that discrepancy was the giveaway).

### Where the real base might be

Not in the vendor resource table: a scan of the region around `0xc05b2aa8` finds
exactly four named entries (`pcie0/1 reg`, `pcie0/1 mem space`) and no glue
entry. `0x09500000` and `0x09600000` both appear nowhere in the binary as
literals, so these bases are computed at runtime from something not yet located.

### Status: capped

Per review, port 1 was capped at one more bounded round, and this was it. The
outcome is a real result - the failure is explained and the address is known to
be wrong - but the correct base is still unknown, and each wrong candidate costs
a boot because an external abort cannot be trapped without `hook_fault_code()`.

**Parked.** 5 GHz works; 2.4 GHz is a second band, not a missing feature. Next
work is client association, sysupgrade, and the `zx_bm_alloc` locking fix.


## Round 140: WI-FI PROVEN END TO END - a client associated and passed traffic

The last unproven claim in the project is now closed. A phone connected to the
board's AP (`H199A-TEST`, channel 36, VHT80):

```
# iw dev phy0-ap0 station dump
Station fa:87:6a:1f:1b:15 (on phy0-ap0)
	rx bytes:    378043        rx packets: 3072
	tx bytes:     25274        tx packets:  214
	tx retries:       2        tx failed:     0
	signal:         -37 [-39, -40] dBm
	tx bitrate:  433.3 MBit/s VHT-MCS 9 80MHz short GI VHT-NSS 1
	rx bitrate:  390.0 MBit/s VHT-MCS 9 80MHz VHT-NSS 1

# cat /tmp/dhcp.leases
1786537791 fa:87:6a:1f:1b:15 192.168.1.112 A32-de-Adriel ...

# ping -c 5 192.168.1.112
5 packets transmitted, 5 packets received, 0% packet loss
round-trip min/avg/max = 3.331/48.444/104.585 ms
```

That is the complete chain: **association, DHCP, bidirectional data, and IP
reachability through the bridge** - with 2 retries and 0 failures, at -37 dBm.

**Wording correction:** 433.3 Mbit/s is the negotiated **link rate** reported by
`station dump`, not measured throughput. ~378 KB moved is trivial traffic.
**Wi-Fi throughput has never been measured** - that needs an `iperf3` or a large
transfer, and is still outstanding.

### What this closes

This closed the last unproven **Wi-Fi** claim - not the project's last unproven
claim. Still outstanding: sysupgrade, SMP, 2.4 GHz, Wi-Fi throughput, and Wi-Fi
soak data.

Every prior Wi-Fi claim was an inference from driver state or hardware counters:

| layer | previously | now |
|---|---|---|
| PCIe enumeration, firmware load | logs | unchanged |
| TX keying | `channel transmit time` counter | real frames, 214 tx packets |
| RX | scan of neighbouring APs | 3072 packets from a real client |
| association / DHCP / throughput | **never demonstrated** | **demonstrated** |

The reviewers were right to keep ranking this first: everything else about the
radio had been proven for rounds, and this was the one step that turned
"reverse-engineered successfully" into "works".

### Note on the 5 GHz-only finding

This also confirms round 133's conclusion from the other direction: the 5 GHz
path carries a full-rate VHT80 link with an excellent signal, while the 2.4 GHz
band on the same phy could not even be heard by a scanner - consistent with
MT7613BE silicon that has no 2.4 GHz front end, not with an antenna problem.


## Round 200: re-verified on the current image - what that does and does not prove

The association result this document rested on was recorded long before the
current image existed. Since then the second CPU core was enabled, the rootfs was
replaced by a `sysupgrade`, all three flash partitions were rewritten, and the
NAND driver's wait path changed. None of the Wi-Fi claims had been re-checked
against any of that.

Re-checked now, on a dual-core boot of the current build:

```
processors                 2
/sys/class/ieee80211       phy0
wireless.radio0.disabled   0
wireless.radio0.channel    36

wifi up
phy0-ap0  ESSID: "H199A-TEST"
          Access Point: 00:0C:43:26:60:00
          Mode: Master  Channel: 36 (5.180 GHz)  HT Mode: VHT80
          Tx-Power: 24 dBm   Noise: -92 dBm
br-lan: port 2(phy0-ap0) entered forwarding state
```

**Proven on this image**: the driver binds, the radio comes up in Master mode on
a 5 GHz channel at VHT80, calibration is loaded from flash (24 dBm rather than
the reduced default), and the interface is bridged and forwarding. SMP did not
break any of it.

**NOT proven on this image**: association, DHCP lease, and any traffic through a
client - the 5 GHz client used for the original test is no longer available to
this bench. Those were verified earlier, on an earlier build, and that is how
they should be cited.

**Withdrawn historical conclusion**: the entry claimed 2.4 GHz did not exist on this hardware (MT7613BE
is 5 GHz-only silicon; the MT7603E sits behind a PCIe port that does not train),
and the frequently quoted 433.3 Mbit/s is a negotiated **link rate**, never a
measured throughput.
