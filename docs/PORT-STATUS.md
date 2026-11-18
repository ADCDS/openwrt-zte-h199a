# Port status and remaining qualification

Status as of 2026-11-18: OpenWrt 24.10-SNAPSHOT with Linux 6.6.151 runs from
either NAND firmware bank on the author's ZTE ZXHN H199A. Wired routing and
2.4 GHz Wi-Fi work. The 5 GHz radio remains unreliable and should stay disabled
for normal use. Hardware flow offload is experimental and disabled.

This is a one-unit port. Successful trials establish the tested behavior;
they do not establish reliability across other units, firmware revisions or
long-duration workloads. [VALIDATION.md](../VALIDATION.md) records the measured
results and distinguishes the latest-image checks from earlier qualification.

## Verified behavior

| Area | Evidence and current limit |
|---|---|
| Platform | NAND boots, two Cortex-A9 CPUs, soft-float userspace, UART and normal OpenWrt startup. Reboot and orderly poweroff passed. |
| Bank selection | Bootloader-selected BootPara is validated and captured before decompressor page tables overwrite it. Board code assigns the active MTD labels/rootfs and the SPI transport independently selects the same bank's write window. Unknown production selection fails closed. |
| Stock web installation | The same bank-aware image passed stock A → OpenWrt B and stock B → OpenWrt A through the Python client without a bank override. Fresh v1.0.0 trials repeated both directions in about 99 seconds with zero UART writes during upload. |
| Native upgrade | Changed-payload image 03 → 04 upgrades passed on A and on B, stayed in the running bank and preserved all 13 original configuration/SSH-host-key hashes. Fresh v1.0.0 checks also passed a changed-payload A upgrade and an exact-release same-payload B reinstall. Active payload, peer stock image, boot/calibration hashes, exact MTD flags and compiled write-policy maps passed. |
| Upgrade header | The packaged `h199a-upgrade-header` helper builds a unit-specific header in RAM from validated inputs and selects a serial above both banks. The upgrade verifies rootfs, kernel and header writes, with the header last. Older A-only kernels are rejected when upgrading a running B installation. |
| NAND and configuration | Native SPI-NAND uses Micron on-die ECC, required at 8 bits per 512 bytes. The UBIFS overlay occupies 84–100 MiB (`overlay_ubi`, mtd13); bank B's separate header partition is mtd14. Configuration persists across the completed upgrades. |
| Ethernet | WAN DHCP, routing and NAT passed. All three LAN jacks passed exact bidirectional NAT transfers on an earlier production image; LAN1 was rechecked in the newer release qualification. Repeat LAN2/LAN3 checks on the final integrated image remain open. |
| Performance | Short wired NAT tests and software-flow-offload tests passed; the recorded figures are in VALIDATION.md. They do not establish full-duplex or hours-long performance. |
| 2.4 GHz | Real-client association and traffic passed. The final v1.0.0 A check retained the original wireless configuration and passed association, ten pings and LuCI access over Wi-Fi. Earlier throughput results are listed separately in VALIDATION.md. |
| Watchdog | CPU0 TWD hardware qualification established whole-board reset at expiry, procd ownership and magic close. CARDRESET is not reportable on this board. |
| LEDs and buttons | Observed working on an earlier production image. Repeat all indicators, WPS and reset actions on the final image; a destructive factory-reset hold has not been qualified. |

Physical partition order does not change with the selected bank. In particular,
the logical label `rootfs` does not always identify mtd7. Use validated labels
and offsets. [BANKS.md](BANKS.md) documents both physical windows, the independent
write barriers and the differing stock/native upgrade behavior.

## Unresolved behavior

**5 GHz PCIe reliability.** Association and local transfers passed before a
runtime failure lost root-port configuration and endpoint accessibility, with
flow-control/replay errors. Boot-time port-0 link initialization is also
intermittent and has failed under stock firmware. The tested reset/timing
experiments have not repaired it. These observations do not prove a permanent
board fault or exclude a software trigger. See [WIFI.md](WIFI.md) and
[diagnostic notes](../tools/diagnostics/README.md).

**Hardware acceleration.** Table access, key construction and individual
packet-processor controls have experimental evidence; a useful hardware-offloaded
Ethernet flow has not been qualified. Software flow offload is the available
acceleration. The board has an Ethernet WAN and three Ethernet LAN jacks, with
no fiber connector. Vendor `pon` terminology and an unconfigured stock WAN do
not prove that the silicon cannot accelerate Ethernet traffic. See
[PP-OFFLOAD.md](PP-OFFLOAD.md) and [PP-KEY.md](PP-KEY.md).

**Automatic datapath recovery.** Manual reset and a first-stage NAPI/watchdog
kick have hardware evidence. Automatic full reset after a genuine persistent
stall has not been demonstrated. See [WEDGE-ANALYSIS.md](WEDGE-ANALYSIS.md).

**Power loss and stock fallback.** Earlier A-only power-cut/recovery drills
passed. They are not a fresh power-cut qualification of the bank-aware kernel.
Stock can synchronize its image into the peer bank after boot; retaining the
peer's bytes during an upgrade does not prevent that later stock behavior.
Follow [BANKS.md](BANKS.md) and [INSTALL.md](INSTALL.md) for the recovery scope.

## Release defaults and host checks

Production disables `CONFIG_ZX279128_ETH_DEBUG`, `CONFIG_ZX279128_PP_TABLES`,
`CONFIG_ZX279128_PP_FLOW_TEST`, `CONFIG_ZX279128_PP_OFFLOAD` and
`CONFIG_ZX279128_PCIE_PROBE_TEST`. Diagnostic images and arbitrary-MMIO tools
are separate development artifacts.

Earlier development regression CI passed 677 tests without skips. The
recreated release checkout ran 677 tests with 151 bench/build-dependent cases
skipped. The separate PCIe diagnostic harness passed 13 actual-C cases. Host tests support the implementation
checks above and do not replace the outstanding hardware trials.

Upstream support has not been submitted or accepted as part of this release.
[upstream/SERIES.md](upstream/SERIES.md) inventories the local sources and the
preparation still required, including a schema for the SoC-specific watchdog
compatible. Historical journals retain earlier failures, policies and test
counts; those snapshots are not the current acceptance matrix.

## Historical investigation

Earlier measurements, withdrawn hypotheses and old commands are preserved in
[the archived notebook](history/PORT-STATUS-SNAPSHOTS.md). They are not current installation instructions.
