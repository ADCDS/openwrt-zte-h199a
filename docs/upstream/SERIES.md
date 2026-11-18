# Upstream preparation and source inventory

Status as of 2026-11-18. This repository carries a local OpenWrt port based on
Linux 6.6.151. The tables below describe existing sources and a possible
submission order. They are not a submitted patch series, an acceptance claim or
a current checkpatch/schema-validation report.

The older mainline ZTE platform covered ZX296702/ZX296718. Its removal does
not mean that the ZX279128S drivers in this repository previously existed
upstream. This port adds a distinct ARM32 Cortex-A9 platform.

## Existing kernel sources

Paths in this table are relative to
[`files/target/linux/armsr/files-6.6`](../../files/target/linux/armsr/files-6.6/).
OpenWrt integration patches are under
[`patches-6.6`](../../files/target/linux/armsr/patches-6.6/).

| Area | Sources | Existing integration |
|---|---|---|
| ARM platform, coherency and SMP | `arch/arm/mach-zx279128/{platform.c,platsmp.c,headsmp.S,Makefile}` | `993-zte-smp-support.patch` |
| Clock/reset manager | `drivers/clk/clk-zx279128-crm.c`; `include/dt-bindings/{clock,reset}/zte,zx279128s-crm.h` | `995-zx279128-crm.patch` |
| UART variant and early console | Changes to the generic PL011 driver | `998-pl011-zx279128-uart.patch` |
| GPIO | `drivers/gpio/gpio-zx279128.c` | `991-zte-gpio-driver.patch` |
| SPI memory controller | `drivers/spi/spi-zx279128.c` | `995-zx279128-native-spi.patch` |
| MDIO and Ethernet | `drivers/net/mdio/mdio-zx279128.c`; `drivers/net/ethernet/zte/{zx279128-eth.c,Kconfig,Makefile}` | `994-zte-mdio-driver.patch` |
| PCIe | `drivers/pci/controller/dwc/pcie-zx279128.c` | `992-zte-pcie-driver.patch` |
| Watchdog | `drivers/watchdog/zx279128_wdt.c` | `998-zx279128-watchdog.patch` |
| System restart | `drivers/power/reset/zx279128-reboot.c` | `998-zx279128-reboot.patch` |
| Board device trees | `arch/arm/boot/dts/zte/zx279128s-zte-h199a{,-production,-production-qualify}.dts` and `Makefile` | `999-zte-dts-subdir.patch` |
| Vendor boot-bank handoff | `arch/arm/boot/compressed/zx279128-boot.c`; `arch/arm/mach-zx279128/boot-bank.c`; `include/linux/soc/zte/zx279128-boot.h` | `994-zx279128-boot-bank.patch` patches decompressor `head.S` and `Makefile`; the machine Makefile includes `boot-bank.o` |

The vendor-bank code captures validated BootPara before decompressor page-table
initialization, updates active-bank MTD labels/permissions before probing and
shares the selected bank with the independent SPI write policy. Both web-install
directions and changed-payload native upgrades on both banks passed on the test
unit. See [BANKS.md](../BANKS.md) and [VALIDATION.md](../../VALIDATION.md).
An upstream firmware-interface design for this handoff remains to be developed.

## Existing OpenWrt image and upgrade integration

The production profile is downstream integration. It includes
[`platform.sh`](../../files/target/linux/armsr/base-files/lib/upgrade/platform.sh),
the image recipe and production device tree, the UBI preinit hook, and the
[`h199a-upgrade`](../../files/package/utils/h199a-upgrade/Makefile) package.
Its installed `h199a-upgrade-header` program comes from
[`h199a-upgrade-header.c`](../../files/package/utils/h199a-upgrade/src/h199a-upgrade-header.c).
The similarly named host tools are not a substitute for this packaged helper.

The helper validates the running unit's headers and the incoming kernel,
prepares a new header in RAM and refuses invalid identity/geometry or serial
overflow. It does not write flash itself. The native upgrade writes and verifies
the active bank, with the header last, and preserves or resets the separate UBI
configuration volume according to the upgrade request.

Production enables `CONFIG_SPI_ZX279128_PRODUCTION_POLICY` together with the
SPI-NAND fail-stop/master-read-only policy. The physical allowlist is selected
from the validated running bank. The write allowlist and fail-stop behavior are implemented by
`996-zx279128-spi-production-policy.patch`, `997-spinand-readonly-master.patch`,
`998-spinand-production-fail-stop.patch` and the SPI driver. Diagnostic mutation
guards are in `998-spinand-diagnostic-mutation-guard.patch` and
`drivers/mtd/nand/spi/diagnostic.h`. These policies must be reviewed separately
from a generic SoC-controller submission.

## Proposed dependency order

1. Review the hardware model and binding coverage first. The existing drafts are
   listed in [bindings/README.md](bindings/README.md). Add the missing
   `zte,zx279128s-wdt` binding coverage and retain the restart binding in the
   inventory. Resolve resource ownership before declaring the schemas final.
2. Submit reviewed bindings before, or together with, their dependent platform
   and driver changes. Platform/SMP/coherency, clock/reset, UART, GPIO, SPI,
   MDIO/Ethernet, PCIe, watchdog and restart each need their own reviewable scope.
3. Add the board DTS after its required bindings and providers. Propose a
   maintainer entry and obtain current recipient lists from the target upstream
   tree when the patches are ready.
4. Keep the OpenWrt image format, production write policy and vendor-bank
   integration in their appropriate downstream series until their interfaces
   have an agreed upstream design.

The precise patch count and subsystem routing will follow that review. A table
of local integration patches is not a ready-to-send upstream series.

## Remaining preparation

- Validate the current drafts and examples against the actual submission
  baseline. Earlier validation logs predate some provider and compatible changes;
  they do not prove the current set passes.
- The CRM provider and MDIO/GPIO/PCIe-reset consumers have RAM-boot evidence.
  That does not finish resource modelling: PCIe still shares CRM windows and
  performs order-sensitive clock/configuration writes; Ethernet's datapath
  clock/reset sequence is not represented by provider properties.
- Resolve the watchdog's SoC-specific compatible in a schema. The existing
  generic ARM watchdog schema alone does not document that new first entry.
- Review the dedicated restart driver. A `syscon-reboot` experiment hung the
  unit; its failure did not establish that every possible generic implementation
  is unsuitable.
- Remove or justify legacy fixed-address fallbacks and deprecated properties,
  probe-time register dumps, full-bus scans, debug parameters and arbitrary-MMIO
  interfaces before submission.
- Review concurrency, teardown, timeout/error paths and memory ownership in the
  actual driver changes. Run the submission baseline's checkpatch and
  get_maintainer tools on the final files and patches; no historical count is a
  current result.
- Reliable 5 GHz operation remains unresolved. State that limitation explicitly
  in any board-support cover letter.

## Experimental code outside the initial submission scope

`zx279128-pp.c`, `zx279128-pp.h`, `zx279128-pp-flow.c`,
`zx279128-pp-hash.c` and `zx279128-pp-offload.c` are local experimental work.
The production configuration disables `CONFIG_ZX279128_PP_TABLES`,
`CONFIG_ZX279128_PP_FLOW_TEST` and `CONFIG_ZX279128_PP_OFFLOAD`.
Useful hardware-offloaded traffic has not been qualified. The optional
offload path also requires a compatible `NF_FLOW_TABLE` link-time configuration;
the Ethernet hookup is retained separately in
[`docs/offload/eth-hookup.patch`](../offload/eth-hookup.patch).

`zx_pcie_probe_test.c` is gated by `CONFIG_ZX279128_PCIE_PROBE_TEST`;
Ethernet bring-up interfaces are gated by `CONFIG_ZX279128_ETH_DEBUG`. Both
symbols are disabled in production. These and the PCIe diagnostic patches are
bench instruments. The retired raw NAND shim `zx_spifc_nand.c` is absent from
this tree and is not part of the source inventory.

## Historical investigation

Earlier measurements, withdrawn hypotheses and old commands are preserved in
[the archived notebook](../history/UPSTREAM-SERIES-NOTES.md). They are not current installation instructions.
