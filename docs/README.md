# Documentation guide

Start with the repository [README](../README.md) for the release scope and
[VALIDATION.md](../VALIDATION.md) for the hardware results and limitations.
All hardware evidence comes from one ZTE ZXHN H199A.

## Install, build and recover

| Document | Use it for |
|---|---|
| [INSTALL-NO-UART.md](INSTALL-NO-UART.md) | Stock web upload after own-unit backup/build preflight; the upload sends no UART commands |
| [WEB-UPGRADE.md](WEB-UPGRADE.md) | Stock upload format, Python client and web-updater behavior |
| [INSTALL.md](INSTALL.md) | Build prerequisites, guarded bank-A UART installation and recovery |
| [BANKS.md](BANKS.md) | BootPara capture, active-bank naming, write protection and native upgrades on A or B |
| [NAND.md](NAND.md) | Native SPI-NAND, on-die ECC, partition geometry and the UBI overlay |
| [UART-PADS.md](UART-PADS.md) | Header wiring, including the boot-strap pad |

The stock web updater writes the inactive bank. Native OpenWrt upgrades replace
the running bank. Read [BANKS.md](BANKS.md) before using commands that identify a
partition by number or physical offset. The UART recovery procedure in
INSTALL.md has explicit bank-A offsets.

## Current subsystem references

| Document | Covers |
|---|---|
| [PORT-STATUS.md](PORT-STATUS.md) | Verified capabilities, outstanding qualification and release defaults |
| [ETHERNET.md](ETHERNET.md) | Four-port Ethernet, routing, performance and datapath behavior |
| [WEDGE-ANALYSIS.md](WEDGE-ANALYSIS.md) | Datapath failure modes, diagnostics and limits of recovery qualification |
| [WIFI.md](WIFI.md) | Radio calibration, working 2.4 GHz support and unresolved 5 GHz PCIe failures |
| [WATCHDOG.md](WATCHDOG.md) | CPU0 watchdog ownership, reset behavior and hardware qualification |
| [GPIO.md](GPIO.md) | GPIO, LEDs and buttons |
| [ZX279128S-DATAPATH.md](ZX279128S-DATAPATH.md) | Historical register model; superseded protocol inferences are identified |
| [PP-OFFLOAD.md](PP-OFFLOAD.md) | Experimental packet-processor work and qualification limits |
| [PP-KEY.md](PP-KEY.md) | Historical classifier experiments and bounded final conclusions |
| [PP-FLOW.md](PP-FLOW.md) | Experimental flow-management implementation |
| [upstream/SERIES.md](upstream/SERIES.md) | Source inventory and proposed upstream preparation |
| [upstream/bindings/README.md](upstream/bindings/README.md) | Draft binding coverage and unresolved schema work |
| [tools/diagnostics](../tools/diagnostics/README.md) | PCIe diagnostic tools and experiments |
| [tools/luadump](../tools/luadump/README.md) | Limited stock Lua-bytecode disassembly tool |

Hardware flow offload remains experimental and disabled. The H199A has one
Ethernet WAN jack and three Ethernet LAN jacks; it has no fiber connector.
Vendor block names containing `pon` do not establish the board's physical
uplink or prove that Ethernet hardware offload is impossible.

## Research and historical records

| Document | Scope |
|---|---|
| [BRINGUP.md](BRINGUP.md) | Historical platform bring-up, clocks, SMP and early boot experiments |
| [REVERSE-ENGINEERING.md](REVERSE-ENGINEERING.md) | Reusable methods and lessons from the investigation |
| [RESEARCH.md](RESEARCH.md) | Dated prior-art and external-project research |
| [TM-IRQ-ARCHITECTURE.md](TM-IRQ-ARCHITECTURE.md) | Historical interrupt and descriptor investigation |
| [STOCK-HARVEST.md](STOCK-HARVEST.md) | Dated stock-boot observations and their evidential limits |
| [ETHERNET-JOURNAL.md](ETHERNET-JOURNAL.md) | Ethernet experiment history |
| [NAND-JOURNAL.md](NAND-JOURNAL.md) | NAND experiment history, including retired raw-driver approaches |
| [WIFI-JOURNAL.md](WIFI-JOURNAL.md) | PCIe and radio experiment history |
| [SESSION-JOURNAL.md](SESSION-JOURNAL.md) | Early dump acquisition and cross-subsystem session history |
| [GPL-SOURCE-HUNT.md](zx279128s-vendor/GPL-SOURCE-HUNT.md) | Dated search for vendor source |
| [VENDOR-ARCHAEOLOGY-R2.md](zx279128s-vendor/VENDOR-ARCHAEOLOGY-R2.md) | Public sibling-board artifacts and research leads |
| [ZTE-GPL-PORTAL.md](zx279128s-vendor/ZTE-GPL-PORTAL.md) | Follow-up portal discovery and archive observations |
| [UBOOT-TM-DISASM.md](zx279128s-vendor/UBOOT-TM-DISASM.md) | Public U-Boot datapath disassembly |
| [R-SEARCH-MACCTRL-TXFREE-UBOOT.md](zx279128s-vendor/R-SEARCH-MACCTRL-TXFREE-UBOOT.md) | Dated MAC-control and TX-release research |

Read the historical banner and date before following any experiment. Old
`maxcpus=1`, raw-NAND/no-ECC, A-only upgrade, `deadc0de` overlay and fixed MTD
instructions describe earlier builds. Current installation and recovery
instructions take precedence.

Journals also name private captures, per-unit firmware/calibration, old commit
identifiers and bench scripts outside this release. Those references identify
the original evidence; they are not files supplied by a public checkout. Source
hunts describe what was found on their research dates, not a guarantee about
today's external services or all possible vendor releases.

## Historical investigation

Earlier measurements, withdrawn hypotheses and old commands are preserved in
[the archived notebook](history/DOCS-INDEX-SNAPSHOT.md). They are not current installation instructions.

The [history index](history/README.md) lists archived versions of replaced
guides. The [v1.0.0 release notes](releases/v1.0.0.md) describe the matched
reference downloads and their qualification.
