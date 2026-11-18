# OpenWrt for the ZTE ZXHN H199A

An OpenWrt 24.10-SNAPSHOT build recipe for the **ZTE ZXHN H199A** Ethernet
router: ZTE/Sanechips ZX279128S, two Cortex-A9 CPUs, 128 MiB SPI-NAND, one GE
WAN and three GE LAN jacks. The pinned kernel is **6.6.151**, target
`armsr/armv7`. The pinned upstream tree lacks this board support; `build.sh`
applies this repository's platform and peripheral drivers.

This is a **one-unit port**, not an upstream-supported device. Read
[VALIDATION.md](VALIDATION.md) for the actual tests and their limits.

## Working and qualified

- Wired management, routing and NAT; three LAN interfaces and one WAN interface
  are configured. The latest-image wired checks use LAN1 and WAN; earlier
  production tests covered the other LAN jacks.
- Calibrated **2.4 GHz Wi-Fi** using the unit's own stock EEPROM and OTP trims.
- NAND boot and native upgrades from either firmware bank, with persistent
  UBIFS configuration and separate MTD/SPI write-protection layers.
- Stock web installation from **either active bank**, using the same image.

Earlier short-transfer measurements on the bench unit:

| Path | Toward WAN | From WAN |
|---|---:|---:|
| Wired NAT, software flow offload disabled | 360.2 Mbit/s | 307.1 Mbit/s |
| Wired NAT, software flow offload enabled | 378.7 Mbit/s | 375.7 Mbit/s |
| Through the 2.4 GHz AP and NAT | 44.5 Mbit/s | 58.3 Mbit/s |

These are workload measurements, not an hours-long or full-duplex guarantee.
Both CPUs are enabled. Software flow offload is available; the recipe does not
force the lab's enabled setting onto a fresh installation.

## Installing

Start with [docs/INSTALL.md](docs/INSTALL.md). Before the first production boot,
back up your own unit, obtain its **128 KiB header template and MT7603 stock
calibration**, and verify that the reserved UBI window at **84–100 MiB** is
safe to initialize. Its absence of UBI markers does not prove it contains no
other data.

Release downloads are a matched **bench-unit reference build**. They do not
replace another unit's private inputs or flash-layout preflight. Build an image
with your own header and calibration for another router.

The stock updater writes the inactive bank: stock A installs OpenWrt B; stock B
installs OpenWrt A. The kernel identifies and mounts the selected bank. Native
`sysupgrade` updates the running bank and keeps its peer read-only. See
[bank behavior](docs/BANKS.md) and [stock web installation](docs/INSTALL-NO-UART.md).
The web upload itself needs no UART; backup/input acquisition and recovery are
separate tasks. [UART-PADS.md](docs/UART-PADS.md) documents the boot-strap pad trap.

## Remaining limitations

**5 GHz is unreliable and should stay disabled for normal use.** It associated
and passed about 279/290 Mbit/s local transfers, then lost PCIe accessibility.
Other boots fail port-0 link initialization, including stock-firmware boots.
Matching software control registers and failed reset experiments do not prove
a permanent board fault. The underlying electrical or retained-state trigger
remains unresolved. See [WIFI.md](docs/WIFI.md).

**Hardware per-flow offload is disabled and unqualified.** Experiments did not
produce working exact-match GE-to-GE flow offload. Vendor `pon` terminology does
not establish an optical connector or prove future Ethernet acceleration is
impossible. [PP-OFFLOAD.md](docs/PP-OFFLOAD.md) separates measurements from hypotheses.

**Stock fallback can replace OpenWrt.** Stock's `syn_version` clones its running
firmware into the peer after a default 300-second timer. Avoid concurrent
synchronization/upload and inspect a fallback promptly. Fresh power-cut
qualification of the bank-aware release has not been performed.

**Some hardware acceptance remains open.** Earlier tests cover LEDs, button
GPIOs, watchdog expiry and manual datapath recovery; repeat integrated controls
and LAN2/LAN3 tests on the latest image. Automatic full datapath recovery after
a genuine persistent stall has not been induced. Details are in
[VALIDATION.md](VALIDATION.md) and [PORT-STATUS.md](docs/PORT-STATUS.md).

## Documentation

- [Installation and recovery](docs/INSTALL.md)
- [NAND layout, backups and overlay preflight](docs/NAND.md)
- [Firmware banks and native upgrade safety](docs/BANKS.md)
- [Ethernet](docs/ETHERNET.md), [Wi-Fi](docs/WIFI.md), [watchdog](docs/WATCHDOG.md), [GPIO](docs/GPIO.md)
- [v1.0.0 release notes](docs/releases/v1.0.0.md)
- [Complete documentation index](docs/README.md)

Historical investigations are explicitly marked and linked from the current
guides. Their old commands, test counts and local commit IDs are not current
release instructions or published Git history.

## Licence

[GPL-2.0-only](LICENSE). Patches retain their original attribution.
