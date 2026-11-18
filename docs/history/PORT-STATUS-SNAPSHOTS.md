> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# Port Status and Acceptance Gates

## Current bank-aware work — 2026-11-18

The production kernel now captures the bootloader-selected bank before
initializing decompressor page tables, maps the active MTD names and rootfs,
and permits writes only to that bank plus UBI. Stock A → web upload → OpenWrt
B and stock B → web upload → OpenWrt A passed on hardware using the same
container and Python client without a bank override. Native image 03 → 04
upgrades passed on each bank with all 13 original configuration/host-key
hashes retained. Exact MTD flags, transport maps, peer and protected/payload
hashes passed. Native upgrades prepare a unit-specific header with a serial above both banks and reject an
A-only downgrade when running B. See [BANKS.md](../BANKS.md) and
[VALIDATION.md](../../VALIDATION.md) for completed trials.

5 GHz associated and passed local 279/290 Mbit/s transfers, then failed with
root-port configuration loss and PCIe flow-control/replay errors. A permanent
board fault is not established. It stays disabled; see [WIFI.md](../WIFI.md).

The dated sections below retain earlier acceptance history; their A-only
write-policy and permanent-fault statements do not describe the current design.

## Status — 2026-11-16: running from NAND (production profile)

The owner's unit runs the **production image from NAND bank A**, with the
owner's migrated configuration in a UBI overlay. Stock bank B is intact as the
fallback. All results are from that one unit. Bench details are in
`codex-handoff.md` (private bench record, not distributed) and the parent workspace's
`logs/analysis-20261115/session-20261115-progress.md`.

| Area | Status on the unit | Evidence / open item |
|---|---|---|
| Boot/platform | ✅ NAND boot of the production image. procd, WAN DHCP, the 2.4 GHz AP and the console come up. Reboot/poweroff are correct | [INSTALL.md §12.8](../INSTALL.md) |
| Watchdog | ✅ hardware-qualified. Whole-board reset at expiry, procd-owned, magic close works. CARDRESET is not reportable on this board | [WATCHDOG.md](../WATCHDOG.md) |
| NAND install / upgrade / recovery | ✅ all six ladder steps. Guarded U-Boot install; verified sysupgrade with config preserved; a power cut mid-upgrade falls back to stock bank B; header-erase drill and restore. Every byte outside bank A was verified unchanged after each mutation | [INSTALL.md §12](../INSTALL.md), [NAND.md](../NAND.md) |
| Write protection | ✅ Two independent layers: DT read-only, plus a compiled transport allowlist (bank A + UBI window only, latching). A live bank-A erase was refused in qualify mode | [INSTALL.md §12.2](../INSTALL.md) |
| Persistent config | ✅ UBIFS overlay. The migrated owner config survives hard power cuts and sysupgrade | INSTALL §12.8 |
| Ethernet / routing / NAT | ✅ **WAN + all three LAN jacks on the NAND production image** (2026-11-15). Each LAN port: 1 Gb/s, DHCP, exact 32 MiB both ways through NAT, ~358 up / ~304 down Mbit/s NAT. Software flow offload gives 399/380. Single-core bound | progress log §6ad |
| 2.4 GHz (MT7603) | ✅ owner's AP; real client at 59/47 Mbit/s | [WIFI.md](../WIFI.md) |
| 5 GHz (MT7663) | ⚠ **unreliable on this unit**: the endpoint drops off PCIe port 0 25 s to 5 min into traffic, whatever the TX power or cool-down. Contained by the 990 guard (no panic; 2.4 GHz unaffected). Afterwards port 0 often fails cold-boot link training until a held-PERST init. Below-driver (board/PCIe) defect. Disabled in the owner's config | [WIFI.md](../WIFI.md) |
| LEDs / buttons | ✅ owner-observed: all indicators, WPS tap → WPS blink, reset tap → reboot. Factory-reset hold not exercised (it would wipe the overlay) | — |
| Hardware NAT / flow offload | 🟡 **the CLA tables are decoded and correct; a live flow still does not match.** The 45-byte key, the window's IPv4 match words, the hash and the placement are decoded and in C; the ternary `extra_rule` the exact-match entry points at is decoded and installs byte-exact; the aging table has a proven positive control. Eleven hypotheses were eliminated on hardware, and with everything verified by readback the aging bit still stays 0 — so the open question is no longer the entry but **whether the PP block sees ingress frames at all**. Also found: the switch's per-port destination mask is zeroed (CPU-controlled forwarding), which would block forwarding even after a match | [PP-KEY.md](../PP-KEY.md) §7-9, [PP-OFFLOAD.md](../PP-OFFLOAD.md) |
| Upstream readiness | 🟡 **Most of the hygiene is done.** One `zx279128s` prefix everywhere (24 files, 10 bindings renamed); a board compatible with all five `board_name` consumers moved with it; `zte,iram` replaced by `mmio-sram` plus a SoC child; the watchdog now puts the SoC compatible first; the raw NAND shim and its patch deleted; the PCIe bring-up scaffolding off in the shipped config. A 20-patch per-subsystem series is written up in [upstream/SERIES.md](../upstream/SERIES.md), with the policy that must not ship listed and the checkpatch/get_maintainer numbers measured. **Still open:** a CRM clock/reset provider (the reviewers' first question), a per-unit-agnostic image header (the tool exists and is host-verified; it needs wiring after a bench check), and calibration from flash | 560 host tests pass |

The rest of this file is the **2026-11-11 checkpoint**, kept for history.
Where it disagrees with the table above, the table wins.

## Active full-board completion goal — 2026-11-11

The owner requests complete, reproducible open-source support for this board,
including both radios, all Ethernet ports, indicators, buttons, storage,
upgrades/recovery and performance/acceleration. Ethernet WAN is the first test
milestone, not the completion boundary. Historical evidence below is retained;
each feature must be qualified on the final integrated image.

The owner confirmed this unit has **four Ethernet ports only**, with no USB or
fiber connector. The [H199A/RE942 datasheet](https://mkt.multilaser.com.br/emkt/mkt/2021/Datasheet_MultilaserPRO/RE942/re942_lamina.pdf)
identifies one GE WAN, three GE LAN, 2x2 2.4 GHz and 2x2 5 GHz WiFi, reset/WPS,
and Power/WAN/LAN/2.4G/5G/WPS indicators. Describing this board as a GPON ONT
confuses SoC blocks with exposed board hardware. Packet-processor acceleration
remains in scope; a non-existent fiber connector is not an acceptance gate.

| Area | Current baseline | Required final evidence |
|---|---|---|
| Boot/platform | Cold RAM boot, Linux 6.6.151, two CPUs; direct software restart passes in read-only U; CPU0 TWD watchdog **hardware-qualified** (whole-board reset at expiry, procd-owned, magic close, orderly reboot/poweroff; CARDRESET not reportable on this board) | Normal OpenWrt/NAND boot, procd shutdown, repeated lifecycle checks ([WATCHDOG.md](../WATCHDOG.md) has the watchdog results) |
| Ethernet/routing | All LAN jacks carryIPv4; S adds CPU-controlled forwarding and passes IPv6/VLAN exact32MiB transfers and raw-frame WAN/LAN isolation probes | Final-image all-jack regression, sustained mixed traffic, recovery and repeated lifecycle checks |
| Performance | Q reaches426/440Mbit/s routing,393/418NAT,433/442software-offloadedNAT; CPU0saturates; RPS reduced throughput | Repeat onS/finalimage, full-duplex/long-load tests, hardware acceleration implementation/qualification |
| WiFi | M passed both-band traffic; full DC/UART disconnect restored U, then a 5G upload lost DMA access and exposed a recovery crash. Guard patch builds and passes host fault tests; not yet loaded | Initial failure diagnosis, guarded hardware recovery/lifecycle tests, reliable PCIe initialization, final-image soak/regulatory checks, BCM43569 2G interoperability |
| LEDs/buttons | Eight active-low channels mapped; WPS41/Reset39 inputs verified. Full WPS daemon and bounded green indicator built/tested in software; GPIO48/red WPS unresolved | Integrated trigger/button/enrollment tests, red WPS explanation, reset actions |
| NAND/configuration | Bounded UBI/UBIFS data, metadata and whiteouts survive cold remount and an interrupted atomic update; outside flash matches the original before the later WiFi panic | Recheck after panic/old-image boots, normal overlay integration, configuration migration and upgrades |
| Installation/upgrade | Historical bank-A flash/readback; bank B retained | Generic distributable images, own-unit data preservation, upgrade and recovery qualification |
| Reproducibility/upstream | Integrated normal-X kernel/rootfs build and owner-calibration checks; 353 host tests pass | Hardware qualification, distributable release images, driver/binding cleanup and submission preparation |

Bench capture is continuously recorded in the parent workspace at
`logs/uart.log` (timestamped view) and `logs/uart.raw` (exact bytes). Host checks
now pass 353 tests, including actual-C fault injection for Ethernet probe
cleanup, NAND transaction/error paths, invalid radio queue indices, teardown
ordering and DMA allocation quarantine. The initial stale fixtures and private
backup dependencies have been repaired. Kernel builds use at most two workers,
reduced to one when host memory is constrained. Hardware tests use RAM boots
with array writes denied except the completed block799 test and the current,
fenced 84–100 MiB UBI qualification area. All original partitions stay read-only.

Normal procd/netifd qualification now has a built SquashFS RAM-root image,
release Ethernet initialization, normal radio module autoload and an explicit
guarded UBI preinit hook. It has not booted yet. Its disposable qualification
volume must first become an empty `rootfs_data` volume. The RAM-boot controller's
second-payload, memory and normal-userspace acceptance path now passes simulated
failure tests and still needs its first hardware run. The old overlay is
preserved as `legacy_overlay`; no automatic format or fallback is allowed.
The immutable normal-X candidate includes the mt76 recovery guard, full WPS
support and the bounded green WPS observer. It passed finished-image checks
and is packaged with its separate checksum envelope, but has not booted.

The native SPI-NAND prototype replaces the raw shim and keeps all original
partitions read-only. Corrected captures are repeatable; raw reads of older
flash contain correctable differences. The UBI test window's raw and corrected
captures match exactly. Existing overlay and occupied staging data are backed
up and preserved. See [NAND qualification](../NAND.md).

A **production build profile** (`BOOT_PROFILE=production`) now exists and builds,
but **has never written a device**. It adds a production write policy enforced at
two independent layers — a production device tree (`kernel1`/`rootfs`/`header`/
`overlay_ubi` writable, everything else read-only, partitioned master withdrawn)
and a compiled transport allowlist (`CONFIG_SPI_ZX279128_PRODUCTION_POLICY`,
`spi_zx279128.production=1`) permitting program/erase only to bank A
`[0x00700000,0x01740000)` and the UBI window `[0x05400000,0x06400000)`, latching
on the first refusal. Production writes and reads use **Micron on-die ECC with
per-request status** (the design doc's "no-ECC" describes the retired raw shim).
`platform.sh` does a board-name check before any erase, writes
rootfs→kernel1→header (header last) with a read-back `mtd verify` between parts,
preserves config into `ubi0:rootfs_data`, resets it (for `-n`) by recreating the
UBI volume rather than seeding `deadc0de`, and never touches bank B. A RAM-only
`PRODUCTION_QUALIFY=1` variant exercises the allow/deny matrix without writing
bank A. Everything is gated behind the hardware qualification ladder in
[INSTALL.md §12](../INSTALL.md); see also host tests `test_production_policy.py`,
`test_production_image.py`, `test_platform_upgrade.py`, `test_production_dts.py`,
`test_production_overlay.py` and `test_production_build_guards.py`.

M's standard coherent PL310 mode removes frequent outer-cache synchronization
from MMIO barriers while preserving CPU barriers and explicit cache maintenance.
The isolated property-off control still hangs on CPU1. Correct PAGE13 preparation
was required for this mode to boot reliably. See [the platform evidence](../BRINGUP.md).

Candidate C completed a 60-second, 100 Mbit/s routed transfer while hashing the
entire corrected rootfs and reading module/firmware files. Its rootfs SHA256 is
`633fe4d4e8c4f12dfd8e40c8769cf8b4faca96b95bd0fcdd092e1b3e1f40db75`,
matching the archived R206 artifact. This concurrent-read test used plain IPv4
routing, not NAT or offload.

Separate 30-second tests in the same C boot measured 100.019 Mbit/s received with
source NAT, then 100.018 Mbit/s with NAT plus software flow offload. A WAN-side
SYN capture and conntrack reply tuple confirm address translation. Conntrack
`OFFLOAD` flags and forward-rule counters staying at two packets establish
software flowtable use. No hardware offload was requested or implemented. CPU
sampling windows were unequal, so their aggregate percentages are not a valid
comparison; maximum throughput and quantified CPU savings remain unmeasured.

One C boot later became unresponsive after a 2G AP test and enabling GPIO51's
throughput trigger. A repeat kept working through 150 pings with that trigger
enabled. Static GPIO51 transitions changed only bit3; both PCIe reset lines
stayed high and SET/CLR read zero. The hang remains unassigned to a cause.

Both PCIe hosts now advertise the driver's intended Gen1 maximum. All-region
read-only native ECC recovered the complete stock bank B; header, kernel,
filesystem and gzip CRCs all pass. The verified kernel enabled offline stock
filesystem extraction and recovery of the correct 2G EEPROM base. A private RAM
DTB supplied it with native OTP merging; the live EEPROM hash matches exactly.

Candidate F restores four measured port0 50 ms waits and its retrain request.
It enumerated all 5G BARs on one boot, but probing later failed configuration
access while the link entered recovery. Actual vendor port1 reset/PHY/config
settings contradicted earlier inferred masks and were corrected in G. M's later
PCIe/radio results supersede those failures, while repeated-boot qualification
still remains. Subsequent unchanged-M cold boots again fail port0 training, so
the earlier traffic passes do not establish repeatable initialization.

The new development branch starts from `34e0ccd`. The published vendor-tree
drivers and per-device backup data remain distinct: private calibration, keys
and credentials must not enter the public recipe.

## Historical milestone notes

The dated entries below describe earlier builds, not the current acceptance
matrix above. Retained failures and hypotheses must not override newer evidence.

Updated 2026-09-10. **Milestone reconciliation against verified results.** M8's
payload requirement is met on the cabled port: 1 MB of sustained bidirectional TCP
completes byte-exact at 2.28 Mbit/s, forward RX is ~100% (998/1000 UDP), and ping
is 0.25 ms at sustainable rates. M7 now has a working fix (non-bound ports' MACs
were never enabled - three of four ports were inert in every build) and a newly
characterised gap (non-bound-port receive is absent). The residual ~20% loss on
the cabled link is bidirectional and has no software explanation on either side
after five deterministic exclusions; it needs a different host path to settle.
See [TM-IRQ-ARCHITECTURE.md](../TM-IRQ-ARCHITECTURE.md) rounds 59-86.

Updated 2026-09-08. The objective is a complete functional OpenWrt port,
including M0 through M8. The original M0-M12 plan is retained in the bench's
Claude plan `okay-my-goal-is-clever-shore.md`. This table brings its milestone
names and verification obligations into the recipe; historical success is not
a substitute for regression testing the final image.

Updated 2026-09-10. **The TX/ARP blocker is resolved.** The IRQ rewrite had dropped
`zx_datapath_warm()`, so the driver re-initialised a datapath U-Boot had already
configured - which stopped every transmit, both directions, on every image built
from this tree. Restoring the function (it requires both a plausible ring-base
pair and at least one configured MAC) fixed it. Verified in a RAM shell on the
cabled port: host->device ping 5/5 0% loss at 0.198-0.508 ms, device->host 3/3
across three consecutive rounds, idle 6 s with `irq=0 rx=0`, and a 30-packet burst
with `irq=33 rx=33 err=0 drop=0`. See
[the IRQ architecture doc](../TM-IRQ-ARCHITECTURE.md#2026-09-10-root-cause-found-tx-fixed-first-validation-runs).

Updated 2026-09-10 (round 31). **RX root cause found: every received frame lands in
buffer 0.** A new per-descriptor trace (`rx_trace` module parameter) shows `idx=0`
on all 32 descriptors across four bursts, and byte 42 of buffer 0 matches the
label of the datagram the sink receives - so the frames genuinely are all in one
2 KiB buffer. All received frames therefore share a buffer, which produces the
observed duplication, loss and TX/RX collision (TX uses buffer 0 too), and makes
the outcome depend only on whether hardware overwrote the buffer before the
driver copied it. That intermittency is why the same script produced 1/8, 3/8,
6/8, 7/8 and 8/8 with no code change. **RX is diagnosed but not yet fixed.** See
[the IRQ architecture doc](../TM-IRQ-ARCHITECTURE.md).

Earlier, same day: the labelled-burst payload-integrity gate ran and FAILED, and
the "**RX corrupts frames**" reading of it was **RETRACTED** (round 30 -> round 40:
0 label/sport mismatches over 63 consecutive datagrams, and an *intact* frame found
in buffer 0). What is real is not corruption but **sequence scrambling**: the
driver consumes descriptors out of step with the producer, which is why the same
script produced 1/8, 3/8, 6/8, 7/8 and 8/8 with no code change.

This did not advance the milestone matrix below - it removed the datapath blocker
that made the matrix unmeasurable. Labelled-burst payload integrity, ring wraps,
simultaneous ports, sustained bidirectional TCP, hardware stop/reopen and a cold
boot with no bootloader network use are all still outstanding.

Paused at the user's request on 2026-09-08. The IRQ-driven sequential RX draft
builds, passes 13 host tests and receives packets on its first RAM boot.
TX/ARP replies and the full hardware validation matrix remain unresolved.
See [the current IRQ checkpoint](../TM-IRQ-ARCHITECTURE.md#irq-draft-and-paused-bench).

| Milestone | Current Evidence | Remaining Acceptance Gate |
|---|---|---|
| [M0 Documentation](#m0-documentation) | Index and milestone table present; status reconciliation underway | README, install and subsystem claims agree with current verified results |
| [M1 Bring-up image](#m1-bring-up-image) | Debug RAM kernels built and used; release/debug configuration separation exists | Final debug/release artifacts verified, drift guards and removal paths checked |
| [M2 PHY/jack map](#m2-phyjack-map) | Four netdevs, MDIO 10-13; observed ports map MAC index +1 in RX descriptor | Regress all physical jacks and factory MACs on final image |
| [M3 Block probes](#m3-block-probes) | IDM and GE PHY decode; old global-init interpretation came from sibling | Preserve register snapshots, correct block identification using actual H199A SDK |
| [M4 SPA access](#m4-spa-access) | Stock and OpenWrt reads pass; inactive nonzero pattern readback, address isolation and restore pass | Register access gate met; final-image regression remains |
| [M5 Vendor access](#m5-vendor-access) | Eight modules extracted with validated gzip CRC; Ghidra imports work | Bank-B raw readback differs from backup; investigate integrity; offline key unresolved |
| [M6 Register model](#m6-register-model) | SPA and TX model started from H199A modules | Named fields/sequences implemented in driver, initialization and ownership verified |
| [M7 Multi-port](#m7-multi-port) | **Non-bound ports' MACs were never enabled** (fixed 2026-09-10); eth1 transmits. **Non-bound-port RX is PRESENT on the product path (r96/r97) and absent on a warm RAM boot that skips the init (r86)** - the isolated variable is the driver's warm check, not a missing binding. **The "TM queue-to-port binding" hypothesis is withdrawn** - the vendor decompilation shows no such binding exists (the ingress port rides per descriptor and is demuxed in software) | Reliable per-port RX on the product path; a genuinely simultaneous two-port test; all-port regression |
| [M8 TCP](#m8-tcp) | **Warm dev bench only (INIT-SKIPPED, not the product path):** 1 MB byte-exact at 2.28 Mbit/s, ping 0.94 ms, forward RX 998/1000 UDP. These are **not** product-path figures - see the platform-corrected matrix in `docs/TM-IRQ-ARCHITECTURE.md`. The **product path** (flashed image, init ran) has measured **multi-second ping RTT (3475-6048 ms) and 20-60% loss** | Close the ~4000x latency gap between the two platforms; re-measure every row on the product path with the radios verifiably off; intermittent stalls |
| M9 RX robustness | Descriptor-release fix survived paced floods | Burst recovery and sustained traffic without wedge |
| M10 Router integration | Historical non-TCP LAN/WAN NAT, DHCP/DNS and WiFi management | Full TCP-capable LAN/WAN and wireless workflow on final image |
| M11 Hardening | Staging BCH correction/cold-read tests pass; WiFi hangs remain | Cold-boot repetition, stable radios, NAND migration, buttons, reboot, soak |
| M12 Upstream | Recipe exists; drivers contain bring-up hypotheses | Clean drivers/bindings, clock/reset ownership and upstream-quality series |

## M0 Documentation

Current status must distinguish successful trials from repeatable behavior.
Retractions remain in journals; current docs must not repeat them as fact.
Register claims should link to the model, not unqualified sibling constants.

## M1 Bring-up Image

`BRINGUP=1` enables privileged debug controls; release artifacts must not expose
them. Validate generated images, not only source configuration. Diagnostic BCH
and WiFi-blacklist images are not default release artifacts.

## M2 PHY/Jack Map

See [Ethernet](../ETHERNET.md). Per-port RX identifiers are MAC index plus one,
not one-hot flags. Verify link, traffic attribution and MAC identity separately.

## M3 Block Probes

Read-only probes established decoding, not the meaning of every register.
The old inference that an NPP word must equal a sibling's init mask is not
proof of incomplete initialization on this SoC.

## M4 SPA Access

See [the register model](../ZX279128S-DATAPATH.md). Vendor module analysis places
SPA at 0x921d4000 with RAM ID shifted by 22. The old 0x921cc000/shift-20
experiments did not test this interface. No clock change was needed for the
stock-shell read test. OpenWrt nonzero-pattern/address-isolation/readback and
restore subsequently passed without a clock change.

## M5 Vendor Access

Original plan sought a rootfs key to obtain drivers. A RAM-only stock kernel
with all init fallbacks patched to `/bin/sh` provided read-only bank-B access
without decrypting the saved container offline. `tm.ko`, `switch.ko` and the
platform module now provide the required implementation evidence. Do not
describe the at-rest encryption key as recovered. Bank B must remain untouched.

## M6 Register Model

`ZX279128S-DATAPATH.md` is the canonical register artifact in progress. Vendor
Linux uses different pool placement from U-Boot; use configuration registers
and owned memory, not copied stock physical addresses. Preserve explicit
uncertainty where decompiler types need assembly confirmation.

## M7 Multi-port

Four netdevs and RX attribution are implemented. Current wire-level failures
prevent treating historical ping/bridge success as final completion. All ports
share the TX hardware and must share resource locking/accounting too.

**2026-09-10: the multi-port path is now understood as four separate layers, and
three of them were broken.**

| layer | state | evidence |
|---|---|---|
| PHY / link on a non-bound port | works | eth1 reaches 1Gbps with carrier |
| MAC enabled by the driver | **was never enabled** - the enable block was gated on `!zx_split_ports`, and `split_ports` ships true. Fixed by removing that term | three of four ports were inert in every build |
| transmit to the wire | works on eth1 after the fix | frames from eth1 arrive at host `tiny` |
| **receive to the CPU** | **PRESENT on the cold boot (r96), absent on a warm RAM boot (r86)** | cold: `eth1` `rx_packets` 0 -> 15 and a proven round trip from `tiny`; warm: `eth1` rx = 0 while `eth2` rx = 18 in the same boot. The variable is not yet isolated - the flashed image is a different driver generation (r96) |

**Corrected in round 96.** `datapath_init()` is skipped only on the *warm* path
(a RAM boot after U-Boot has used the network). On a real NAND boot it runs, and
round 96 measured that cold boot: **the non-bound port receives** (`eth1`
`rx_packets` 0 -> 15, and a round trip proven from `tiny`). The earlier
"forcing the cold path does not help (round 35)" was a **confound** - round 35
forced the cold path with `force_dp_init=1` on a datapath U-Boot had *already*
configured, which is the destructive combination, not a cold boot. The vendor
decompilation also shows there is no port->queue binding to reconstruct: rings are
per queue and the ingress port rides per descriptor. What remains open is which of
two changed variables causes the warm-path absence - see the R96 entry in
`../../docs/ROUNDS-JOURNAL.md`.

**A four-port ONT that drives one port is not yet a port.** Per-port RX
initialisation is the remaining M7 work, and it should not be attempted until a
second port can be measured - which is what it is trying to build.

## M8 TCP

An RX census increment is necessary evidence, not a sufficient functional
acceptance test. Require inbound and outbound established flows with verified
payloads, then SSH/LuCI and LAN-WAN routing, with no malformed/stale frames.
Repeat from independent cold boots and distinguish RAM boot from flash boot.

**2026-09-10: the payload requirement is MET on one port.**

A 4 MB stream does not complete, but the failure is intermittent rather than
structural, and a full megabyte does complete:

```
   32 KB : completes, byte-exact
    1 MB : completes in 3.685 s = 2.28 Mbit/s, receiver verifies 1048576 bytes
  256 KB : stalled (while 1 MB succeeded in the same session)
    4 MB : stalls partway (17376 / 57920 / 128872 bytes across repeats)
```

So **inbound and outbound flows with verified payloads are demonstrated at
megabyte scale**, which is the substance of this gate. What is not yet
demonstrated is *reliability*: ~20% of exchanges fail at ordinary rates.

That residual loss has been localised but not explained:

* it is **bidirectional** on the eth2 link (forward ~13%, return ~31%, round 79);
* the **device's TX driver is deterministically clean** (37/37 correct slots, no
  duplicates, correct lengths, round 75);
* the **traffic manager consumes every descriptor** the driver queues (round 79);
* the **host NIC (RTL8153) and the host kernel's softnet both count nothing**
  (rounds 76, 80);
* and **latency is not the explanation** - it is a queueing artefact of test rate;
  at sustainable rates ping is 0.25 ms (round 78).

With every software layer excluded on both sides, the remaining candidates are
physical (cable, connector, PHY) or the host USB NIC. **The carrying test is to
repeat round 79's forward/return split with the device on a different host path** -
which needs a switch putting the box and the host's second NIC on one segment, not
a code change.

**Measurement protocol for this gate** (established the hard way, rounds 62-77):
ping at 2 s intervals with a 5 s timeout; report loss and latency separately; and
repeat every result before treating it as a property of the code.
