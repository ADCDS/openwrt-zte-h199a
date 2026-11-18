> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# The kernel series, per subsystem

Status, 2026-11-16. This is the submission shape for the ZX279128S port: what
goes in which patch, in what order, and what each patch still needs before it
can be sent. It is written to be checked against the tree, not to be admired -
every list below is derived from the files that exist.

Read `bindings/README.md` first for the per-compatible concerns, and
`../PP-KEY.md` for why the offload work is not in this series yet.

## What this port is, in upstream terms

A single-board port of an ARM Cortex-A9 SoC whose vendor tree is gone: the
`ARCH_ZX` platform was removed from mainline in 5.12. So the series is a
*platform re-add*, not a driver addition, and reviewers will read it that way.
That is why the machine descriptor, the SMP bring-up and the IOCC replay have
to come first: without them nothing else can be evaluated.

There is no `zte` entry in the 6.6 `MAINTAINERS` at all (the only match for
"zte" is an unrelated media radio). A new entry is part of the series, not an
afterthought.

## Order

Bindings before code, and within that, the things other patches depend on
first. Each numbered item is one patch.

| # | patch | subsystem | files |
|---|---|---|---|
| 1 | `arm64`/`arm: add ARCH_ZX279128` | arch/arm | `arch/arm/Kconfig`, `arch/arm/Makefile`, `arch/arm/mach-zx279128/{Makefile,platform.c,platsmp.c,headsmp.S}` |
| 2 | `dt-bindings: arm: add ZTE ZX279128S` | dt-bindings | `Documentation/devicetree/bindings/arm/zte.yaml` |
| 3 | `dt-bindings: sram: ZX279128S SMP SRAM` | dt-bindings | `.../sram/zte,zx279128s-smp-sram.yaml` |
| 4 | `dt-bindings: arm: ZX279128S IOCC` | dt-bindings | `.../arm/zte,zx279128s-iocc.yaml` |
| 5 | `dt-bindings: clock: ZX279128S clock/reset manager` | dt-bindings | `.../clock/zte,zx279128s-crm.yaml` (+ `include/dt-bindings/clock/zte,zx279128s-crm.h`, `include/dt-bindings/reset/zte,zx279128s-crm.h`) |
| 6 | `dt-bindings: spi: ZX279128S SPI flash controller` | dt-bindings | `.../spi/zte,zx279128s-spifc.yaml` |
| 7 | `dt-bindings: net: ZX279128S Ethernet` | dt-bindings | `.../net/zte,zx279128s-eth.yaml` |
| 8 | `dt-bindings: net: ZX279128S MDIO` | dt-bindings | `.../net/zte,zx279128s-mdio.yaml` |
| 9 | `dt-bindings: gpio: ZX279128S GPIO` | dt-bindings | `.../gpio/zte,zx279128s-gpio.yaml` |
| 10 | `dt-bindings: pci: ZX279128S PCIe host` | dt-bindings | `.../pci/zte,zx279128s-pcie.yaml` |
| 11 | `clk: add ZX279128S clock/reset manager` | clk | `drivers/clk/clk-zx279128-crm.c` |
| 12 | `gpio: add ZX279128S GPIO driver` | gpio | `drivers/gpio/gpio-zx279128.c` |
| 13 | `spi: add ZX279128S SPI flash controller` | spi | `drivers/spi/spi-zx279128.c` |
| 14 | `net: mdio: add ZX279128S MDIO bus driver` | net | `drivers/net/mdio/mdio-zx279128.c` |
| 15 | `net: ethernet: add ZX279128S Ethernet driver` | net | `drivers/net/ethernet/zte/{zx279128-eth.c,Kconfig,Makefile}` |
| 16 | `pci: dwc: add ZX279128S host controller` | pci | `drivers/pci/controller/dwc/pcie-zx279128.c` |
| 17 | `watchdog: add ZX279128S watchdog` | watchdog | `drivers/watchdog/zx279128_wdt.c` |
| 18 | `power: reset: add ZX279128S restart` | power | `drivers/power/reset/zx279128-reboot.c` |
| 19 | `ARM: dts: add ZXHN H199A` | arm/dts | `arch/arm/boot/dts/zte/*` |
| 20 | `MAINTAINERS: add ZTE ZX279128S` | — | `MAINTAINERS` |

Patches 1-10 are independent and can go in one series; 11-18 each depend only
on their binding; 19 depends on all of them; 20 last.

## What must NOT be in the series

These are board policy or bench scaffolding. They stay in the OpenWrt patches,
which is where they already are.

| item | where it lives now | why it cannot go upstream |
|---|---|---|
| `read-only` on the spi-nand node | `patches-6.6/997-spinand-readonly-master.patch` | boot-time write policy; upstream has `read-only` on partitions only |
| `partitioned-master-read-only` | `patches-6.6/998-spinand-production-fail-stop.patch` | its meaning depends on `CONFIG_MTD_SPI_NAND_FAIL_STOP`, which a binding cannot express |
| `CONFIG_SPI_ZX279128_PRODUCTION_POLICY` | `patches-6.6/996-zx279128-spi-production-policy.patch` | a compiled physical-address allowlist: board policy inside a SoC driver |
| module parameters (`write_test`, `ubi_test`, `production*`, `hold_perst`, `ondie_probe`, eth debug) | the drivers | bench knobs |
| `/proc/zx_eth_poke` and the other ETH_DEBUG interfaces | `zx279128-eth.c` behind `CONFIG_ZX279128_ETH_DEBUG` | arbitrary physical read-modify-write |
| `zx_pcie_probe_test.c` | `CONFIG_ZX279128_PCIE_PROBE_TEST`, now off in the shipped config | replays a reverse-engineered PHY sequence at `late_initcall` |
| `zx279128-pp.c`, `zx279128-pp.h`, `zx279128-pp-flow.c`, `zx279128-pp-hash.c`, `zx279128-pp-offload.c` | `CONFIG_ZX279128_PP_TABLES` / `CONFIG_ZX279128_PP_FLOW_TEST` / `CONFIG_ZX279128_PP_OFFLOAD` | not hardware-qualified; see `../PP-KEY.md` §7. The offload path (`zx279128-pp-offload.c`) additionally `depends on NF_FLOW_TABLE`; see item 6 |
| ~~the raw NAND shim~~ (`zx_spifc_nand.c`, `zte,ZX279127-spifc`) | **deleted** | superseded by the SPI-mem path, no DTS user, and the only file in the tree with `checkpatch` errors. Removed with its patch, its Kconfig symbol and its tests |

The per-subsystem drivers also need their bench knobs stripped before
submission; that is per-patch work, not a separate patch.

## checkpatch --strict, measured

Run with the pinned tree's own script (`scripts/checkpatch.pl --no-tree
--strict -f`), on the files as they are today:

```
arch/arm/mach-zx279128/platform.c           clean
arch/arm/mach-zx279128/platsmp.c            5 warnings, 1 check
drivers/clk/clk-zx279128-crm.c              7 checks
drivers/gpio/gpio-zx279128.c                clean
drivers/mtd/nand/raw/zx_spifc_nand.c        4 errors, 14 warnings, 26 checks   <- not submitted
drivers/mtd/nand/spi/diagnostic.h           5 checks                            <- not submitted
drivers/net/ethernet/zte/zx279128-eth.c     8 warnings, 35 checks
drivers/net/ethernet/zte/zx279128-pp*.c     2 warnings, 4 checks                <- not submitted
drivers/net/ethernet/zte/zx_pcie_probe_test.c 2 checks                          <- not submitted
drivers/net/mdio/mdio-zx279128.c            1 warning, 1 check
drivers/pci/controller/dwc/pcie-zx279128.c  11 checks
drivers/power/reset/zx279128-reboot.c       clean
drivers/spi/spi-zx279128.c                  3 checks
drivers/watchdog/zx279128_wdt.c             clean
include/dt-bindings/clock/zte,zx279128s-crm.h clean
include/dt-bindings/reset/zte,zx279128s-crm.h clean
```

No file that is actually submitted has an error. The warnings worth fixing
before sending:

- `platsmp.c`: `extern` in a `.c` (move the trampoline symbol to a header),
  `volatile` on `zx_pen_release` (use `READ_ONCE`/`WRITE_ONCE` and a proper
  barrier comment), and two memory barriers with no comment. The barriers are
  load-bearing for the SMP handshake, so the fix is a comment, not removal.
- `zx279128-eth.c`: 8 warnings; re-run and fix before splitting, since the
  file is 4.7k lines and the split touches most of it.
- `mdio-zx279128.c`: 1 warning.

The `CHECK`s are mostly `usleep_range` vs `udelay` and long-line notes.

## get_maintainer, measured

From the pinned tree, `get_maintainer.pl --no-git --no-roles -f`:

| file | goes to |
|---|---|
| `zx279128-eth.c` | David S. Miller, Eric Dumazet (netdev) |
| `mdio-zx279128.c` | Andrew Lunn, Heiner Kallweit (netdev/phy) |
| `platsmp.c` | Russell King (ARM) |
| `spi-zx279128.c` | Mark Brown (spi) |
| `zx279128_wdt.c` | Wim Van Sebroeck, Guenter Roeck (watchdog) |
| `pcie-zx279128.c` | Lorenzo Pieralisi, Krzysztof Wilczyński (PCI) |

Nothing resolves to a ZTE contact because there is no `zte` entry in
`MAINTAINERS`. Whoever owns the submission has to be the contact, which is
why patch 20 exists.

## What still blocks the series

1. **The CRM clock/reset provider is boot-qualified; the consumer wiring
   is not yet.** `zte,zx279128s-crm` (`drivers/clk/clk-zx279128-crm.c`) replaced
   the single-register `zte,zx279128s-spi-clocks` slice with identical clock
   parameters and adds the PCIe resets in CRM1+0x74. **Verified on a RAM
   boot, 2026-11-16:** `clk_summary` shows 50 MHz wclk and 125 MHz pclk with
   every gate critical and enabled, the SPI controller takes both, the MTD
   partitions still enumerate, `/proc/iomem` shows no conflict with the
   reboot node, and `reboot -f` resets the board.
   **Consumers wired, not yet boot-qualified:** the provider now also maps
   LSP1CRPM and gives MDIO (`fb_mdio_pclk`/`fb_mdio_wclk`) and GPIO
   (`fb_gpio_pclk`) their clocks, and the PCIe nodes take their core reset
   from `resets`. Every field is an entry of the stock kernel's own clock
   tables, every gate stays critical, and the PCIe register traffic is
   byte-identical to before in a host model. Not converted, on purpose: the
   Ethernet node (the stock tables have no clock for it; its gate in
   TOPCRM+0x0c is a cold-init question, `PP-KEY.md` section 15), CRM2 (no
   clock-table entry; its one field is a pin-mux word), the PCIe clock
   enables and configuration fields (not in the clock tables), and the blind
   `writel(0x3f, CRM1+0x74)` (it writes four unidentified bits).
   `zte,zx279128s-reboot` stays a separate single-word node.
2. **`syscon-reboot` does not work on this board** - it was tried and hangs
   the unit. So patch 18 is a bespoke driver that upstream would rather see
   replaced. See `bindings/README.md`.
3. **The board compatible has not been boot-qualified.** The DTS now names
   `zte,zxhn-h199a` first and every `board_name` consumer accepts both, but no
   image with that change has been booted.
4. **The per-unit image header is still host-generated.** That is an OpenWrt
   packaging problem, not a kernel one, but it is what stops a single public
   image working on every unit.
5. **The offload code cannot be sent at all** until it does something. The
   driver glue now exists (`zx279128-pp-offload.c`, `CONFIG_ZX279128_PP_OFFLOAD`,
   off by default): it registers `ndo_setup_tc`/`TC_SETUP_FT` and installs CLA
   exact-match + PM entries, but the hardware match itself is not qualified
   (`../PP-KEY.md` §9-16), so the symbol stays off and this file is not in the
   series. The Ethernet-side hookup is kept as a patch, not applied, because
   `zx279128-eth.c` is owned by the datapath-reset work: `docs/offload/eth-hookup.patch`.
6. **`nf_flow_table` must be built in, not a module, for the offload driver.**
   `zx279128_eth` is a bool, so it cannot link against `nf_flow_table` built
   as `=m` - and in this config it is `=m` (`nf_flow_table_offload.o` builds
   as a module). The offload symbol therefore has to `depends on
   NF_FLOW_TABLE` and the config has to build it in, or the link fails at the
   end of a long build. Recorded here because it is the kind of thing that
   only shows up once the driver is actually wired in. The Kconfig is written
   this way (`depends on ZX279128_PP_TABLES && NF_FLOW_TABLE`), and
   `tests/test_pp_offload.py` asserts the dependency so a future edit cannot
   silently drop it.

## Procedure

The vendor-bank integration is currently local OpenWrt work, pending hardware
qualification and an upstream firmware-interface design. `zx279128-boot.c`
preserves validated BootPara before decompressor page tables overwrite it;
`boot-bank.c` assigns active-bank MTD labels and permissions before probing;
`zx279128-boot.h` shares the validated selection with the independent SPI
write policy. These files are not part of the proposed upstream series yet.

```
K=openwrt/build_dir/target-*/linux-*/linux-6.6.*
perl $K/scripts/checkpatch.pl --no-tree --strict -f <file>     # per file, before splitting
perl $K/scripts/checkpatch.pl --strict <patch>                 # per patch, before sending
perl $K/scripts/get_maintainer.pl -f <file>                    # per patch, for the Cc list
```

`tests/test_patch_hunks.py` checks the OpenWrt patch set's hunk headers, which
is a different thing: those patches must apply to the pinned tree, and a
header that is off by one is tolerated by `patch` until the day it is not.
