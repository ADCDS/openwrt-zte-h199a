> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# ZX279128S / ZXHN H199A: draft dt-schema bindings

Draft YAML bindings for every compatible string (and custom property) in the
H199A device tree that Linux 6.6 does not already document. These drafts were
written from a read-only analysis of the port repo
(`openwrt-zte-h199a`, HEAD `e1b62f5`). Nothing in the repo was modified.

Upstream preparation step 1 (branch `agent/dt-resources`) then changed the
PCIe and Ethernet drivers to take the resources they hard-coded from the
device tree, added those properties to the H199A DTS, and updated the
`pci`, `net` and `gpio` drafts to match. See "Step 1" under Validation and
concern 1.

Step 2 (branch `agent/dt-resources-2`) made the Ethernet driver take its DDR
window from `memory-region` and the PCIe driver take the port index from the
node's `dbi` address, dropped `zte,pcie-port` from the DTS (still accepted,
deprecated), and updated the `net` and `pci` drafts. See "Step 2" under
Validation.

Paths below use these prefixes:

- `F/` = `files/target/linux/armsr/files-6.6/`
- `P/` = `files/target/linux/armsr/patches-6.6/`

Baseline "upstream" means the pristine `linux-6.6.151` tarball in
`openwrt/dl/`. The OpenWrt build tree is not a valid baseline: it already
contains this port's four in-repo bindings, copied in from
`F/Documentation`.

## Layout

```
arm/zte.yaml                          root/board compatibles (new; upstream has no arm/zte.yaml since the ZX platform was removed)
arm/zte,zx279128s-iocc.yaml            supersedes the in-repo copy
sram/zte,zx279128s-smp-sram.yaml      the mmio-sram child the DTS now uses
clock/zte,zx279128s-crm.yaml          CRM clock/reset provider; same text as the in-repo copy (replaced zte,zx279128s-spi-clocks)
spi/zte,zx279128s-spifc.yaml           supersedes the in-repo copy (adds description, example, child constraints)
power/reset/zte,zx279128s-reboot.yaml  supersedes the in-repo copy
gpio/zte,zx279128s-gpio.yaml          new
net/zte,zx279128s-mdio.yaml           new
net/zte,zx279128s-eth.yaml            new
pci/zte,zx279128s-pcie.yaml            new
upstream-schema-changes/              unified diffs against pristine 6.6.151 schemas (apply with patch -p1 in a kernel tree)
  arm-cpus.yaml.diff                  enable-method "zte,zx279128s-smp"
  serial-pl011.yaml.diff              "zte,zx279128s-uart" in front of arm,pl011
  mtd-spi-nand.yaml.diff              read-only, partitioned-master-read-only (same text as P/997 and P/998-spinand-production-fail-stop, plus a TODO)
```

`maintainers` is the placeholder `TBD`, as requested. dtschema 2023.9 did not
reject it, but upstream needs `Name <email>`. The in-repo bindings already
name a maintainer, so use that.

## Compatible -> driver -> binding

| Compatible / property | Driver (what it parses from DT) | Binding | Notes |
|---|---|---|---|
| `zte,zx279128s`, `zte,zx279128` (root) | `F/arch/arm/mach-zx279128/platform.c`: `DT_MACHINE_START` matches `zte,zx279128s` only | `arm/zte.yaml` | **No board compatible.** Draft proposes `zte,zxhn-h199a` (TODO: confirm the name). The `zte,zx279128` family fallback is unproven, since an "R" variant DT exists. |
| enable-method `zte,zx279128s-smp` | `F/arch/arm/mach-zx279128/platsmp.c`: `CPU_METHOD_OF_DECLARE` | `upstream-schema-changes/arm-cpus.yaml.diff` | The DTS sets it on `/cpus`. ARM Linux supports that as a fallback, and Rockchip does the same. The enum that the diff extends is in the per-`cpu@N` schema. The SCU base comes from CBAR, not DT. |
| `zte,zx279128s-smp-sram` | platsmp.c: `of_find_compatible_node` + `of_iomap(np, 0)` | `sram/zte,zx279128s-smp-sram.yaml` | **Done.** The node is now `mmio-sram` with this child, which is the upstream form; the vendor's generic `zte,iram` named no SoC and had no binding. The controller's region is exactly the window the driver already mapped (0x200800, 4 KiB), so nothing new is claimed. The stock DT's second window at 0x200000 is still unused and still not described. |
| `zte,zx279128s-iocc` | platform.c: `of_find_compatible_node`, reg[0] must be >= 0x8c bytes, panics otherwise | `arm/zte,zx279128s-iocc.yaml` | Replays a vendor write sequence with unknown bit meanings (TODO). Reviewers will ask what the block is and may want a driver instead of machine code. |
| `zte,zx279128s-uart` (+ `arm,pl011`, `arm,primecell`) | `P/998-pl011-zx279128-uart.patch`: AMBA ID `0x001feffe` -> `vendor_zte` register map. The compatible is used **only** by `OF_EARLYCON_DECLARE`. | `upstream-schema-changes/serial-pl011.yaml.diff` | AMBA binding works only through `arm,primecell-periphid = <0x001feffe>`, which the diff requires for this compatible. The value is `AMBA_LINUX_ID(0x00, 0x1, 0xffe)`. To my recollection the upstream ZX296718 support used the same ID before the ZX platform was removed in 5.12 (verify in a 5.10 tree). The 6.6 `include/linux/amba/serial.h` does still carry the `ZX_UART011_*` defines that support left behind. The patch also declares an earlycon for `zte,zx279133-uart`, which no DTS uses: drop it or document it. |
| `zte,zx279128s-eth` | `F/drivers/net/ethernet/zte/zx279128-eth.c`: `reg[0]` (bound port's MAC), `reg-names` `mac0..3`, `fabric`, `glb`, `npp`, `tmc`, `tmd`, `bm`, `qmg`, `tmq`, `pp`, `sbrg`, `cla`, `ponpp` (byname; fixed-address fallback per missing name), IRQ `"tm"` (required), IRQs `idm`/`gephy0..3` (debug IRQ probe only), `ethernet-ports/port@N` {`reg`, `phy-handle`, `phy-mode`, nvmem `mac-address` via `of_get_ethdev_address`}, legacy top-level `phy-handle`/`phy-mode`, `memory-region` (`of_reserved_mem_lookup`: must be no-map, >= 16 MiB, 1 MiB aligned, below 4 GiB; the rings, pools and free lists are fixed offsets from its base; fallback 0x41000000) | `net/zte,zx279128s-eth.yaml` | `phy-mode` must be `rgmii` (anything else is `-EINVAL`). SPA and port attach are offsets in `npp`. The experimental PP table code still maps CLA/PM/PonPp by address. See concern 1. |
| `zte,zx279128s-mdio` | `F/drivers/net/mdio/mdio-zx279128.c`: `reg[0]`, optional clocks `pclk`/`wclk`, `of_mdiobus_register` | `net/zte,zx279128s-mdio.yaml` | Same compatible as the vendor DT. The Ethernet driver also looks this compatible up for PHY keepalive. The probe ioremaps MAC/BM/TM for a debug dump. The stock DT's `clocks = <&lsp1crpm 1>` is `fb_mdio_wclk`, now `ZX_CRM_MDIO_WCLK`. |
| `zte,zx279128s-gpio` | `F/drivers/gpio/gpio-zx279128.c`: `reg[0]`, one optional clock; ngpio hard-coded 96 | `gpio/zte,zx279128s-gpio.yaml` | No IRQ, pull or debounce in hardware. Pinmux (CRM2) is not modeled. The PCIe driver takes GPIO 53/55 as `reset-gpios`; it writes these registers directly only for a DT without them. |
| `zte,zx279128s-reboot` | `F/drivers/power/reset/zx279128-reboot.c`: `reg[0]` | `power/reset/zte,zx279128s-reboot.yaml` | A single TOPCRM word. The upstream route is `syscon-reboot` under a TOPCRM syscon. TODO: syscon-reboot does read-modify-write where stock writes blindly, so check that +0x44 reads 0 first. The node name `reset-controller@` implies `#reset-cells`. |
| `zte,zx279128s-crm` | `F/drivers/clk/clk-zx279128-crm.c`: reg by name `topcrm`/`crm1`/`lsp0crpm`/`lsp1crpm` (mapped, not claimed; each must be >= 4 KiB), parents **by index** (`clock-names` unused), one-cell clock provider (SPI, MDIO and GPIO clocks and the LSP0/LSP1 parent gates) and one-cell reset provider (PCIe 0/1 in CRM1+0x74). Headers `F/include/dt-bindings/{clock,reset}/zte,zx279128s-crm.h` | `clock/zte,zx279128s-crm.yaml` | Replaced `zte,zx279128s-spi-clocks` with the same parents, registers, bits, divider shift/width/flags and rates. One deliberate difference: the two SPI gates, which the old driver registered with flags 0, are now `CLK_IS_CRITICAL` like every other gate. **Not dt-doc-validated** (dtschema was not installed when it was written) and not boot-qualified. See concern 2. |
| `zte,zx279128s-spifc` | `F/drivers/spi/spi-zx279128.c` (built): `reg[0]`, clocks `pclk`/`wclk` by name. Interrupt not used. 1 CS, RX dual, SCK fixed at the wclk rate (`spi-max-frequency` must equal it). Also matched by `F/drivers/mtd/nand/raw/zx_spifc_nand.c`, which Kconfig excludes and which uses a different child layout. | `spi/zte,zx279128s-spifc.yaml` | The write allowlist is module params plus Kconfig, not DT. Only the SPI-mem model should go upstream. |
| `zte,ZX279127-spifc` | `zx_spifc_nand.c` only (`CONFIG_MTD_NAND_ZTE_SPIFC` is not set) | none | Upper-case and names the sibling SoC. **Do not upstream.** Delete it with the raw driver. |
| `zte,zx279128s-pcie` | `F/drivers/pci/controller/dwc/pcie-zx279128.c`: `reg-names` `app`, `crm0`/`crm1`/`crm2` (byname; fixed-address fallback), `dbi` (its address gives the port index, 0x0f000000 = port 0, 0x0f100000 = port 1; `app` must be that port's glue block), `config` (via the DWC core), `reset-gpios` (gpiod, both ports during the shared preparation; fixed-pin fallback), `zte,pcie-port` (deprecated: still accepted with a warning, must agree with `dbi`). The DWC/PCI core parses `num-lanes`, `max-link-speed`, `bus-range`, `ranges`, `interrupt-map*`, `dma-coherent`. | `pci/zte,zx279128s-pcie.yaml` | Both nodes must exist and be enabled. The CRM windows are shared, interim reg entries until a CRM clock/reset provider exists. Refs `pci-bus.yaml` + `snps,dw-pcie-common.yaml`, not `snps,dw-pcie.yaml`, whose reg-names list rejects the CRM names. No MSI. INTC/INTD are aliased (TODO). See concern 1. |
| spi-nand `read-only` | `P/997-spinand-readonly-master.patch` | `upstream-schema-changes/mtd-spi-nand.yaml.diff` | Policy, not hardware. It also skips the chip's block-unlock step. Keep it downstream. |
| spi-nand `partitioned-master-read-only` | `P/998-spinand-production-fail-stop.patch`: honoured only with `CONFIG_MTD_SPI_NAND_FAIL_STOP=y` | same diff | **The meaning depends on Kconfig, which is not acceptable in a binding.** Keep it downstream. See "Non-upstreamable knobs". |
| `arm,cortex-a9-twd-wdt` (upstream) | `F/drivers/watchdog/zx279128_wdt.c`: `reg[0]`, one unnamed clock | none needed: upstream `watchdog/arm,twd-wdt.yaml` (6.6, YAML) already allows reg, interrupts and clocks | The DTS node validates as is. Driver concern: a SoC-named driver claims a generic ARM compatible, so upstream it would be a generic TWD watchdog driver or need a SoC compatible in front. |

### Upstream compatibles reused, not redocumented

`fixed-clock`, `gpio-keys-polled`, `gpio-leds`, `simple-bus`, `arm,cortex-a9`,
`arm,cortex-a9-gic`, `arm,cortex-a9-global-timer`, `arm,cortex-a9-twd-wdt`,
`arm,pl310-cache` (all the PL310 properties used are in `l2c2x0.yaml`),
`arm,pl011`/`arm,primecell` (+ `arm,primecell-periphid` in
`primecell.yaml`), `spi-nand`, `fixed-partitions`, `nvmem-cells`,
`mediatek,mt76` (+ `mediatek,mtd-eeprom`, `mediatek,eeprom-merge-otp`),
reserved-memory `no-map`, partition `linux,rootfs`. `linux,rootfs` is in the
6.6 `partition.yaml` binding. Its kernel implementation is OpenWrt's.

## Validation (dtschema 2023.9, contemporary with 6.6; in a scratch venv)

The bindings tree was pristine 6.6.151, plus the three diffs, plus these drafts.

- `dt-doc-validate`: all 10 drafts and the 3 patched upstream schemas pass.
- Examples: all 10 compile (cpp + dtc) and pass `dt-validate` with zero
  findings.
- The real H199A DTS (base, `-production` and `-production-qualify`) was
  compiled to DTB in scratch with cpp + dtc only, with no kernel or OpenWrt
  build. **Every ZTE node passes.** As a control, the same DTB against pristine
  6.6 schemas reports exactly the 13 ZTE nodes in the table above, plus
  `partitioned-master-read-only`, as undocumented.
- The remaining findings are in the board DTS or in upstream schemas, not in
  these bindings:
  - `keys`: children `reset` and `wps` must be named `key-*` or `button-*`,
    for example `key-reset`.
  - `leds`: `power_c1`, `wan_c1`, `lan`, `wlan2g`, ... must contain `led`,
    for example `led-0` or `led-power-green`. Labels such as `&led_power`
    keep working.
  - `wifi@0,0` (both radios): the 6.6 `mediatek,mt76.yaml` allows only
    `nvmem-cell-names = "eeprom"`, and the DTS uses `"mac-address"`, which the
    driver handles. `pci-bus.yaml` also wants a `pciVVVV,DDDD` compatible on
    PCI device nodes, while `mt76.yaml` allows only `mediatek,mt76`. These
    are upstream-schema conflicts. Check the target kernel's `mt76.yaml`
    before submitting. For this reason the PCIe example omits the endpoint.
  - dtc: `timer@8000200` should be `timer@800200` (unit address vs reg).

### Step 1 (driver resources from DT), re-validated

Same dtschema 2023.9 and bindings tree, with the updated `pci`, `net` and
`gpio` drafts:

- `dt-doc-validate`: the three updated drafts pass.
- Examples: all three pass `dt-validate` with zero findings. A mutated
  example (`reg-names` "crmx", `phy-mode` "rgmii-id") is rejected, so the
  drafts do constrain the nodes.
- The board DTBs (base, `-production`, `-production-qualify`) built from
  this branch report exactly the findings the pre-step-1 DTBs report against
  the pre-step-1 drafts: only the two `wifi@0,0` endpoint conflicts above.
  The `keys`, `leds` and `timer` findings above no longer occur; the DTS
  was fixed before step 1. dtc prints no warnings.
- The updated drafts reject a pre-step-1 DTB (no CRM entries, no
  `reg-names` on the Ethernet node). The drivers still accept one and fall
  back to the fixed addresses.

### Step 2 (memory-region, port from dbi), re-validated

Same dtschema 2023.9 and bindings tree, with the updated `net` and `pci`
drafts:

- `dt-doc-validate`: both updated drafts pass.
- Examples: both pass `dt-validate` with zero findings. Mutations are
  rejected: two `memory-region` entries ("too long"), no `memory-region`
  ("required"), `zte,pcie-port = <2>`. `zte,pcie-port = <0>` is accepted
  (deprecated, not forbidden).
- The board DTBs built from this branch report exactly the findings the
  step-1 DTBs report against the step-1 drafts (the two `wifi@0,0` endpoint
  conflicts). A step-1 DTB, which still has `zte,pcie-port`, reports the
  same findings against the step-2 drafts. dtc prints no warnings.
- The compiled DTBs differ from the step-1 ones only by the two removed
  `zte,pcie-port` properties (decompiled and diffed; 46 bytes smaller).
  `/reserved-memory/eth-datapath@41000000` (0x41000000 + 16 MiB, `no-map`)
  and `/memory@40000000` (128 MiB) are unchanged, so the kernel memory map
  is unchanged. That node is the only carve-out: there are no
  `/memreserve/` entries, the forced `CONFIG_CMDLINE` has no `mem=`, and
  `mach-zx279128` reserves nothing. The stock kernel's top-18 MiB block at
  0x46e00000 (see `docs/PP-OFFLOAD.md`) is ordinary RAM in this port.

To reproduce (no kernel build needed):

```sh
python3 -m venv venv && venv/bin/pip install 'dtschema==2023.9'
# B = pristine 6.6 Documentation/devicetree/bindings + diffs + these drafts
venv/bin/dt-doc-validate -u $B $B/net/zte,zx279128s-eth.yaml
venv/bin/dt-mk-schema -j -u $B > processed.json
venv/bin/dt-extract-example $B/net/zte,zx279128s-eth.yaml > ex.dts
cpp -nostdinc -I include -undef -D__DTS__ -x assembler-with-cpp -P ex.dts ex.pp.dts
dtc -O dtb -o ex.dtb -Wno-interrupt_provider ex.pp.dts
venv/bin/dt-validate -s processed.json ex.dtb
```

(`include/` needs `dt-bindings/` from the kernel, plus
`F/include/dt-bindings/clock/zte,zx279128s-crm.h` and
`F/include/dt-bindings/reset/zte,zx279128s-crm.h` (`zte,zx279128s-spi.h` at
the time of these runs), plus
`dt-bindings/input/linux-event-codes.h`, a copy of
`uapi/linux/input-event-codes.h`.)

## Non-upstreamable knobs and how to handle them

| Item | Why it is a problem | Suggested handling |
|---|---|---|
| `partitioned-master-read-only` | Write policy, not hardware. The meaning changes with `CONFIG_MTD_SPI_NAND_FAIL_STOP`. | Keep it as an OpenWrt target patch. If an upstream equivalent is wanted, `CONFIG_MTD_PARTITIONED_MASTER=n` removes the master device without any DT, but it renumbers the MTDs (the production layout relies on mtd0 being the master). Otherwise propose a generic, unconditional MTD property and expect pushback. |
| `read-only` on the `spi-nand` node | Qualification policy. It also suppresses the core's block unlock. Upstream has `read-only` only on partitions. | Keep it downstream and drop it from the upstream DTS. Partition-level `read-only` is upstream already. |
| `zte,pcie-port` | Index property. Step 2 removed it from the DTS and derives the index from the `dbi` address; the driver still accepts it (warns, must agree with `dbi`) and the draft marks it `deprecated`. The index still selects bits in the shared CRM registers (the `crm0..2` reg entries). | Drop it from the binding at submission. Replace the CRM bit selection with per-port `clocks`, `resets` and possibly `phys` (SerDes words at glue +0x1b0/+0x1b4). |
| Ethernet `interrupts` `idm`, `gephy0..3` | Requested only by the debug IRQ probe. IDM is a separate block and the gephy lines look like PHY interrupts. | Drop them from the MAC node. Move gephy lines to `ethernet-phy@N` `interrupts` once confirmed. |
| Ethernet top-level `phy-handle`/`phy-mode` | Legacy single-port fallback. The driver parses `phy-mode` per port and uses the top-level one only for a port without its own. | Marked `deprecated` in the draft. Remove them from the DTS. |
| Ethernet MAC derivation for ports without nvmem cells | Driver policy that invents locally-administered addresses. | Fine downstream. Upstream reviewers may prefer one nvmem cell per port or a documented `mac-address-increment`-style scheme. |
| Module parameters (spi `write_test`/`ubi_test`/`production`/`production_qualify`, eth debug params, pcie `hold_perst`, nand `ondie_probe`...) | Not DT, but bench knobs in driver code. | Must never become DT properties. Strip or gate them before submission. The compiled H199A allowlist (`CONFIG_SPI_ZX279128_PRODUCTION_POLICY`) is board policy in a SoC driver and is not upstreamable as is. |
| MDIO probe debug dump and full-bus scan, eth `/proc` interfaces | Map other devices' registers and expose a physical poke primitive. | Driver cleanup. No binding impact. |
| `zte,zx279133-uart` earlycon | No DTS user. | Drop it, or add it to the pl011 diff with a real user. |
| Mixed `zx279128-` vs `zx279128s-` prefixes | The SoC is the ZX279128S (root compatible `zte,zx279128s`). Upstream wants one consistent SoC name. | Pick one, presumably `zte,zx279128s-*`, before the first submission. Renaming later is an ABI break. |

## Relationship to the in-repo bindings

`F/Documentation/devicetree/bindings/` already has the iocc, reboot,
spi-clocks and spifc bindings, and the spi-nand.yaml hunks in P/997 and
P/998. The drafts here are supersets of those:

- added the missing examples (spi-clocks, spifc);
- added register maps, descriptions and TODOs;
- added spifc child constraints (CS 0, RX width 1/2, TX width 1);
- added the Kconfig-dependency TODO to `partitioned-master-read-only`.

Copy the drafts back into `F/Documentation` if wanted. They were not written
to the repo.

## Top upstreaming concerns

1. **Drivers use hardware the device tree does not describe, so these bindings
   cannot be final.** Step 1 resolved the register blocks, PERST# and
   `phy-mode`, and step 2 the DDR window (`memory-region`) and the PCIe
   port index. The drivers keep a fixed-address fallback, with one log
   line, for a DT that predates the properties. Still open:
   - Ethernet: the DDR window comes from `memory-region`, but its internal
     layout is fixed (U-Boot's) and only the base 0x41000000 has run on
     hardware. `phy-mode` is parsed but only `rgmii` is supported. The
     `npp` entry is the 128 KiB window the driver maps, which spans the IDM
     block the vendor DT keeps separate. The experimental PP table code
     (`zx279128-pp.c`, off by default) still maps CLA, PonPp and PM
     (0x9239c000) by address, and PM has no reg entry. The MDIO driver's
     debug dump maps MAC/BM/TM/attach by address.
   - PCIe: the CRM blocks are reg entries shared by both nodes and by other
     drivers' registers (see concern 2). The port index comes from the
     `dbi` address, matched against the driver's table of this SoC's two
     controllers, and both ports must exist.
   - Upstream bindings must list every resource the driver uses.
2. **No model of the clock/reset blocks.** These are TOPCRM 0x94000000,
   CRM1 0x94100000, CRM2 0x94200000, LSP0CRPM 0x94400000 and LSP1CRPM
   0x9a100000.
   - **The CRM clock/reset provider is boot-qualified, 2026-11-16.** A RAM
     boot of a diagnostic image carrying it, with the old
     `zte,zx279128s-spi-clocks` driver removed, produced:

     ```
     zx279128-spifc 94406000.spi: inherited working clock 50000000 Hz; array writes disabled
     94000000.clock-controller.spi-wclk    2  2  0  50000000  ...  Y  94406000.spi  wclk
     94000000.clock-controller.spi-pclk    2  2  0 125000000  ...  Y  94406000.spi  pclk
     94000000.clock-controller.spi-divider 1  1  1  50000000  ...  Y
     94000000.clock-controller.wclk-parent 2  2  1 100000000  ...  Y
     94000000.clock-controller.pclk-parent 2  2  0 125000000  ...  Y
     ```

     Same rates as the driver it replaced, both clocks taken by the SPI
     controller, every gate critical and enabled. The MTD partitions still
     enumerate (so the boot flash still works), `/proc/iomem` still shows
     `94000044-94000047 : reset-controller` with no conflict from the CRM
     node's wider reg (the CRM maps with `devm_ioremap`, which does not
     reserve), `zx279128-reboot` binds, and `reboot -f` resets the board.
     So concern 2 is closed as far as the clocks and the reset provider go.
   - **Consumers wired and boot-qualified, 2026-11-16.** Recovered
     from the stock vmlinux: its clock driver registers its tables with
     plain `clk_register_gate`/`_divider`/`_mux` calls in
     `zx279127_{top,lsp0,lsp1}_clocks_init`, so the register, bit, shift,
     width and parent of every vendor clock can be read off the call
     arguments. The provider now maps LSP1CRPM too and adds, each straight
     from those tables: the LSP1 parent gates (TOPCRM+0x14 bits 7, 5), the
     MDIO divider and gates (LSP1CRPM+0x04 [17:11], bits 1, 0 - the stock
     `<&lsp1crpm 1>` is `fb_mdio_wclk`), and the GPIO register gate
     (LSP0CRPM+0x1c bit 0, `fb_gpio_pclk`). All are `CLK_IS_CRITICAL`, and
     the MDIO divider is read-only. MDIO and GPIO take them as optional
     clocks; the PCIe nodes take their CRM1+0x74 line from `resets`, with
     register traffic identical to the old direct writes
     (`tests/test_pcie_crm_resets.py`). Left as they are, with reasons:
     - Ethernet: the stock tables have no clock for it. The one datapath
       gate known (TOPCRM+0x0c bits 1-4, `PP-KEY.md` section 15) needs a
       reset pulse that hangs a warm boot, so it belongs to cold init, not
       to a provider that only ever keeps gates on.
     - CRM2: no entry in the stock clock tables; its only field used here
       (+0x0c) is a pin-mux word.
     - The PCIe clock enables (TOPCRM+0x08) and configuration words
       (TOPCRM+0x24, CRM1+0x70): not in the clock tables, and the sequence
       is order- and delay-sensitive.
     - The final `writel(0x3f, CRM1+0x74)`: a whole-register write that
       also sets bits 1, 2, 4 and 5, which are not identified. Reset lines
       cannot express it, so it stays a raw write.

     Verified on a RAM boot rather than left at "should be identical":

     ```
     mdio-zx279128 9a101000.mdio: ZX279128S MDIO bus registered
     zx279128-pcie f000000.pcie: preparing both PCIe ports before bus discovery
     zx279128-pcie f000000.pcie: port1 CRM before link: clken=1e06ffff misc=10000000 cfg=0001aab5 rst=0000001b mux3=003dbf85
     zx279128-pcie f000000.pcie: final shared reset readback=0000001b
     ```

     Those PCIe register values are byte-identical to what the driver wrote
     when it poked CRM1 itself, which is the strongest evidence available that
     the reset provider changed nothing. `clk_summary` shows `mdio-wclk` at
     **2.5 MHz** taken by `9a101000.mdio` - the IEEE MDC rate, which is
     independent confirmation that the decoded divider field is right - plus
     `mdio-pclk` and `gpio-pclk` at 125 MHz taken by their consumers and the
     SPI clocks unchanged at 50/125 MHz. MTD still enumerates and `reboot -f`
     still resets the board.

     Not verifiable in a diagnostic image: the radios, because that profile
     blacklists `mt7603e`/`mt7615e`. The PCIe register identity above stands in
     for it until a production image is booted with this change.

   - **`syscon-reboot` was tried and does not work on this board.** The
     conversion is the obvious one: a `syscon` node covering TOPCRM+0x44 with a
     `syscon-reboot` child at `offset = <0>`, `value = <1>`,
     `mask = <0xffffffff>`, so `regmap_update_bits()` writes `value` verbatim
     instead of read-modify-writing. It was built with
     `CONFIG_POWER_RESET_SYSCON=y`; the node and child both appeared in
     `/proc/device-tree`; and `reboot -f` printed `Restarting system` and then
     stopped - no U-Boot banner, no network, the board hung with the plug on.
     So either the handler did not register or its write never reached the
     trigger; distinguishing those is the first step if it is tried again.
     Until then the dedicated one-register driver stays.
   - `zte,zx279128s-crm` covers TOPCRM, CRM1, LSP0CRPM and LSP1CRPM and
     replaced the single-register `zte,zx279128s-spi-clocks`. Every gate is
     `CLK_IS_CRITICAL`. Its binding has not been through `dt-doc-validate`.
   - `zte,zx279128s-reboot` is still a single-register slice of TOPCRM, and
     stays one because syscon-reboot hangs the board.
   - Still unmodelled: CRM2, the PCIe clock enables and configuration
     fields (TOPCRM+0x08/+0x24, CRM1+0x70, CRM2+0x0c) and the blind 0x3f
     write, which the PCIe driver still does through its `crm0..crm2` reg
     entries. Ethernet declares no clocks or resets (see above).
   - Reviewers will ask for a CRM clock + reset (+ syscon) binding first.
     The spi-clocks binding is now replaced; the reboot node cannot become
     `syscon-reboot` (above).
3. **Compatible hygiene and policy-in-DT.**
   - Mixed `zx279128`/`zx279128s` prefixes (now fixed), the generic `zte,iram` (now mmio-sram), no
     board compatible at the root, and the upper-case `zte,ZX279127-spifc`.
   - An `arm,pl011` fallback on a UART that is not PL011 register-compatible
     and is identified by an invented AMBA ID.
   - A SoC-named watchdog driver that claims `arm,cortex-a9-twd-wdt`.
   - `read-only` and `partitioned-master-read-only` express boot-time write
     policy, one of them conditional on Kconfig. They belong in downstream
     patches, not in an upstream binding.
