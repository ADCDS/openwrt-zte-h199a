# Ethernet — ZX279128S / ZXHN H199A

The H199A has **one GE WAN jack and three GE LAN jacks**. The release
configures `eth3` as WAN and `eth0 eth1 eth2` as LAN bridge members. Wired
SSH and LuCI work, and native firmware images of approximately 17 MB can be
delivered over Ethernet. The earlier TCP-payload and cumulative-frame failures
describe superseded drivers.

All hardware results are from one H199A. The release checks cover LAN1 and WAN;
LAN2 and LAN3 passed earlier all-jack tests on a previous production image, but
were not repeated on the release image. See [Validation](../VALIDATION.md) for
the exact coverage and [Installation](INSTALL.md) for supported upgrade paths.

## Ports and configuration

| Physical jack | Linux interface | MAC index | MDIO address | Default role |
|---|---|---:|---:|---|
| LAN1 | `eth2` | 2 | 12 | LAN bridge |
| LAN2 | `eth1` | 1 | 11 | LAN bridge |
| LAN3 | `eth0` | 0 | 10 | LAN bridge |
| WAN | `eth3` | 3 | 13 | WAN |

The driver names interfaces by physical MAC index. Each interface has its own
PHY and link state. Factory MAC addresses come from `tag` partition nvmem
cells; the remaining LAN member addresses are derived in the driver. The board
network script sets interface roles without assigning a second set of MACs.

Source: `files/target/linux/armsr/base-files/etc/board.d/02_network`, the H199A
device tree, and
`files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c`.

## Measured performance

These are short, separate upload and download tests on the bench unit with an
earlier production image. They are not a new throughput qualification of the
bank-aware release image, simultaneous full-duplex results, or a long-load soak.

| Routed path / setting | Upload | Download |
|---|---:|---:|
| Wired NAT, software flow offload disabled | 360.2 Mbit/s | 307.1 Mbit/s |
| Wired NAT, software flow offload enabled for the test | 378.7 Mbit/s | 375.7 Mbit/s |
| 2.4 GHz client through NAT | 44.5 Mbit/s | 58.3 Mbit/s |

The wired tests were limited by processing on one CPU core. A 1 Gb/s link
does not establish gigabit routing throughput. Software flow offload is an
opt-in firewall setting: the recipe does not explicitly enable it. Its measured
benefit is independent of the experimental hardware packet-processor code.

## Driver architecture

Ethernet uses the SoC's buffer manager and traffic manager. It is not a
conventional GMAC DMA-ring driver. Linux controls forwarding: physical-port
learning and GE-to-GE forwarding masks are disabled, unknown unicast is sent
to the CPU, inherited forwarding entries are cleared, and raw TX selects the
requested physical port. VLAN handling is left to Linux. Earlier qualification
covered IPv4/IPv6, software VLANs and WAN/LAN isolation on the images used for
those trials; it does not replace release-image regression coverage.

Receive processing uses the TM interrupt and NAPI. The stock interrupt is
SPI 36; Linux obtains its IRQ number through the IRQ domain. TMC status is
`0x92340100` and its active-high mask is `0x92340104`. The handler masks RX
sources and schedules NAPI; completion re-arms them with a pending-count
recheck. The TX completion timer and deferred release retries are separate
from RX interrupt delivery. There is no periodic descriptor-scanning RX loop.

The reserved DDR window is 16 MiB, normally based at `0x41000000`. Its RX
region starts at offset `0xa00000` and contains sixteen rings: eight queues
in each of two directions. Every ring has 1,024 descriptors of 16 bytes.
The driver consumes each ring sequentially, including slot zero, using the
hardware pending counts and a software cursor. It copies packet data and
metadata before returning ownership. Buffer release through BM and descriptor
release through TMD are distinct operations; incomplete returns retain debt
for bounded retry. Ordinary interface stop/reopen retains ring ownership state.

Release builds initialize the datapath rather than attaching to inherited
U-Boot state. Initialization verifies disabled gates before rebuilding state,
and failure prevents interfaces from being published. UDP and TCP CPU-trap
selectors are programmed as `0x11060000` at SPA `0x921d41c0`.

## Recovery and acceleration limits

RX stall detection, a NAPI kick and bounded datapath-reset recovery are compiled
into the driver. Earlier hardware tests demonstrated a manual reset and the
first-stage NAPI kick. Automatic reset after a genuine persistent stall was
not induced on the release image; it remains unqualified. See
[Recovery](WEDGE-ANALYSIS.md).

The release kernel leaves `CONFIG_ZX279128_ETH_DEBUG`,
`CONFIG_ZX279128_PP_TABLES`, `CONFIG_ZX279128_PP_FLOW_TEST` and
`CONFIG_ZX279128_PP_OFFLOAD` unset. Experimental `/proc` controls, PP tables
and hardware-flow integration are therefore absent from this configuration.
Diagnostic experiments demonstrated default-flow hardware forwarding, but no
working per-flow exact-match offload for the tested GE-to-GE paths. See
[Packet-processor status](PP-OFFLOAD.md).

[The Ethernet journal](ETHERNET-JOURNAL.md) preserves the investigation history.
Its old register hypotheses, failures, parameters and recovery commands do not
describe the release.

## Historical investigation

Earlier measurements, withdrawn hypotheses and old commands are preserved in
[the archived notebook](history/ETHERNET-BRINGUP.md). They are not current installation instructions.
