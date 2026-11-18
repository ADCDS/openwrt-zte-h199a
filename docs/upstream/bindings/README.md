# Draft device-tree bindings

Status as of 2026-11-18. These are local binding drafts for the ZX279128S port
on Linux 6.6.151. They have not been submitted or accepted upstream. They
describe the current port and record unresolved hardware modelling; they are
not a claim that every custom compatible is already documented.

The board is a ZTE ZXHN H199A with one Ethernet WAN jack, three Ethernet LAN
jacks and two PCIe Wi-Fi radios. It has no fiber connector. Vendor `pon` block
names describe SoC internals and do not change the exposed board hardware.

## Files and coverage

`F/` below means
[`files/target/linux/armsr/files-6.6/`](../../../files/target/linux/armsr/files-6.6/),
and `P/` means
[`files/target/linux/armsr/patches-6.6/`](../../../files/target/linux/armsr/patches-6.6/).

| Draft | Compatible or property | Implementation / remaining concern |
|---|---|---|
| [arm/zte.yaml](arm/zte.yaml) | Root `zte,zxhn-h199a`, `zte,zx279128s`, `zte,zx279128` | The DTS names the board first; board-name consumers accept it and the SoC fallback. Review whether the broader family fallback is justified. |
| [sram/zte,zx279128s-smp-sram.yaml](sram/zte,zx279128s-smp-sram.yaml) | `zte,zx279128s-smp-sram` | `platsmp.c` finds the child of `mmio-sram`; trampoline +0x04 is the secondary entry and +0x08 is the pen-release address. |
| [arm/zte,zx279128s-iocc.yaml](arm/zte,zx279128s-iocc.yaml) | `zte,zx279128s-iocc` | `platform.c` replays and checks the early coherency sequence. Bit meanings and the appropriate upstream ownership still need review. |
| [clock/zte,zx279128s-crm.yaml](clock/zte,zx279128s-crm.yaml) | `zte,zx279128s-crm` | Clock/reset provider for TOPCRM, CRM1, LSP0CRPM and LSP1CRPM; other drivers still access overlapping blocks. |
| [spi/zte,zx279128s-spifc.yaml](spi/zte,zx279128s-spifc.yaml) | `zte,zx279128s-spifc` | `spi-zx279128.c` implements SPI-mem, with on-die NAND ECC handled by the SPI-NAND core. The old raw NAND shim is deleted. |
| [net/zte,zx279128s-mdio.yaml](net/zte,zx279128s-mdio.yaml) | `zte,zx279128s-mdio` | MDIO bus, optional `pclk`/`wclk`; probe scans and fixed-address debug dumps need driver cleanup. |
| [net/zte,zx279128s-eth.yaml](net/zte,zx279128s-eth.yaml) | `zte,zx279128s-eth` | Named register blocks, `memory-region`, TM interrupt and per-port PHY/MAC data; clock/reset ownership and the combined block model remain provisional. |
| [gpio/zte,zx279128s-gpio.yaml](gpio/zte,zx279128s-gpio.yaml) | `zte,zx279128s-gpio` | GPIO provider and optional register clock; a complete pin-control model is absent. |
| [pci/zte,zx279128s-pcie.yaml](pci/zte,zx279128s-pcie.yaml) | `zte,zx279128s-pcie` | DesignWare host with shared CRM resources, `reset-gpios` and core `resets`; port index comes from DBI, with deprecated legacy-property support. |
| [power/reset/zte,zx279128s-reboot.yaml](power/reset/zte,zx279128s-reboot.yaml) | `zte,zx279128s-reboot` | Dedicated TOPCRM reset-trigger word. A failed `syscon-reboot` trial is hardware history, not an upstream design decision. |
| **Missing draft** | `zte,zx279128s-wdt` | The DTS puts this before `arm,cortex-a9-twd-wdt`. Add SoC-specific coverage or an appropriate generic-schema extension before submission. |

The draft tree also includes three proposed modifications to schemas from the
pinned 6.6.151 baseline:

- [arm-cpus.yaml.diff](upstream-schema-changes/arm-cpus.yaml.diff): the
  `zte,zx279128s-smp` enable-method. Check the location used by the real CPU
  nodes, including the `/cpus` fallback.
- [serial-pl011.yaml.diff](upstream-schema-changes/serial-pl011.yaml.diff):
  `zte,zx279128s-uart` and its AMBA peripheral ID. Review the `arm,pl011`
  fallback for this variant register layout and the extra unused earlycon
  compatible in the driver patch.
- [mtd-spi-nand.yaml.diff](upstream-schema-changes/mtd-spi-nand.yaml.diff):
  local whole-chip `read-only` and `partitioned-master-read-only` policy. These
  are downstream schema changes, not proposed upstream hardware bindings.

## Relationship to the build overlay

`F/Documentation/devicetree/bindings/` contains four schemas: IOCC, CRM, SPI and
restart. The CRM copy is shared with this draft tree; the other drafts include
additional explanatory text or example constraints. Audit both locations when
editing them. Having a draft here does not automatically copy it into a kernel
build or establish that the board DTB validates.

The old `zte,zx279128s-spi-clocks` provider was replaced by the CRM provider.
The old `zte,iram` node became `mmio-sram` plus a SoC-specific child. The deleted
raw NAND driver and its `zte,ZX279127-spifc` compatible are not current users.

## Remaining hardware and interface questions

The CRM provider and its SPI, MDIO, GPIO and PCIe-reset consumer wiring have
RAM-boot evidence. They preserve the boot firmware's clock configuration and
keep the represented gates critical. This verifies the tested implementation,
not a complete clock/reset model. Still outside the provider model are CRM2
pin muxing, several order-sensitive PCIe clock/configuration writes, unknown
CRM1 reset bits and Ethernet's datapath gate/reset sequence. PCIe, restart and
the CRM provider still map overlapping register blocks.

Ethernet's reserved DDR window is described by `memory-region`, but the layout
uses fixed offsets and only the existing base has hardware evidence. The NPP
register entry spans a block the vendor describes separately as IDM. Experimental
packet-processor code still uses fixed physical mappings. Decide the proper
block boundaries and ownership before treating the draft as a final ABI.

The PCIe nodes currently need both host instances for shared initialization.
Legacy address/PERST fallbacks, the deprecated `zte,pcie-port` property and
partly inferred interrupt routing need review. Reliable port-0/5 GHz operation
is unresolved; schema conformance would not repair or qualify that hardware
behavior.

The dedicated watchdog driver uses a SoC-specific first compatible, while the
restart trigger has its own small node. Review both binding models explicitly.
The failed generic restart experiment does not establish its cause or prove
that another generic design cannot work.

## Downstream policy and diagnostic interfaces

The production bank-aware MTD flags, independent SPI physical write allowlist,
fail-stop behavior and UBI configuration are OpenWrt board policy. In particular,
the meaning of `partitioned-master-read-only` depends on
`CONFIG_MTD_SPI_NAND_FAIL_STOP`; that conditional meaning is unsuitable for an
upstream binding as written. Keep downstream policy changes distinct from
hardware descriptions.

Module parameters, ETH_DEBUG `/proc` access, MDIO dumps, diagnostic mutation
guards, PCIe trace experiments and the optional PP modules also require driver
review. None should become a device-tree property merely to preserve a bench
control. Production disables ETH_DEBUG, PP table/flow/offload options and the
PCIe probe-test driver.

Vendor BootPara capture and active-bank handling are additional local firmware
integration, described in [BANKS.md](../../BANKS.md) and
[SERIES.md](../SERIES.md). The checked, four-byte `/chosen/zte,boot-bank`
handoff property needs an upstream firmware-interface design if that mechanism
is proposed; it is not documented by these ten hardware drafts.

## Validation still required

Earlier notes recorded checks with dtschema 2023.9 against particular draft and
board snapshots. Subsequent CRM and compatible changes mean those results do
not establish validation of the current files. No fresh all-schema or
all-example validation is asserted here.

Before submission, run `dt-doc-validate`/kernel `dt_binding_check`, compile and
validate each current example, and run `dtbs_check` on all board variants against
the chosen upstream baseline. Include the missing watchdog compatible and the
relevant generic-schema changes. Resolve maintainer placeholders and report
remaining failures explicitly, including any PCI endpoint/mt76 schema conflicts.
Use a pristine baseline when checking which properties are already upstream;
the OpenWrt build tree contains this port's overlay schemas and downstream
patches.

## Historical investigation

Earlier measurements, withdrawn hypotheses and old commands are preserved in
[the archived notebook](../../history/UPSTREAM-BINDINGS-NOTES.md). They are not current installation instructions.
