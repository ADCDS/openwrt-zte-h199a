# Ethernet stall detection and recovery

The driver contains RX stall detection, a first-stage NAPI kick and bounded
datapath-reset recovery. Earlier hardware tests demonstrated the kick and a
manual reset. **Automatic reset after a genuine persistent stall was not
induced on the release image and remains unqualified.** A working manual
trigger does not prove that automatic detection and recovery will handle every
hardware failure.

The historical cumulative-frame failure is not the release's networking
baseline. Wired SSH, LuCI, payload transfers and native firmware-image delivery
work. Release Ethernet coverage is LAN1/WAN; LAN2/LAN3 have earlier-image
qualification. See [Ethernet](ETHERNET.md) and [Validation](../VALIDATION.md).

## Current implementation

Source:
`files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c`,
particularly `zx_rx_stall_check()`, `zx_wd_work()`,
`zx_dp_request_reset()` and `zx_dp_reset_work()`.

RX normally runs through TM interrupts and NAPI. Each of sixteen receive rings
has a sequential cursor, cached pending count and durable release debt.
Buffer return and descriptor return are distinct. Deferred retries avoid an
unbounded softirq loop when a return cannot complete. The one-second watchdog
observes pending descriptors and the driver's descriptor-return counter; an
idle link with no pending work is not a stall.

| Condition | Implemented response |
|---|---|
| Pending descriptors with no new return since the prior watchdog observation | Schedule NAPI as the first recovery step |
| Persistent lack of progress reaching `rx_stall_ms` (3,000 ms by default) | Request a datapath reset |
| Pending count exceeding ring depth, confirmed by a second read | Latch RX fault and request reset |
| Continued failure without RX progress | Rate-limit automatic resets and stop after the configured retry budget |

Recovery defaults on in the source. Automatic resets are spaced by at least
10 seconds; the retry limit is three resets without RX progress. Renewed RX
progress allows a later fault to start a new recovery sequence. The reset
worker runs under RTNL, closes open ports and stops the TX completion timer
before reinitializing the datapath.

Reinitialization checks queue/command state and replays the probe's software
port policy: learning disabled, physical-port isolation, unknown-unicast CPU
delivery, forwarding-entry clear and software VLAN admission. It also restores
CPU protocol selectors, queue settings, free lists, interrupt masks and
software ownership state. Ports reopen only after successful initialization;
a failed reset leaves them down.

The worker refuses a reset while diagnostic PP tables are live, because their
memory and hardware bases have independent ownership. Those tables are absent
from the release configuration.

## Hardware evidence and limits

An earlier manual-reset trial returned links in about five seconds. A ping
running across it lost 2 of 150 replies. A separate induced interrupt-stall
trial recovered through the first-stage NAPI kick and passed 75 of 75 pings.
These qualify the exercised paths on that image, not the complete automatic
stall-reset sequence or recovery from a CPU stuck in an inaccessible MMIO read.

The diagnostic manual endpoint queues the same reset worker, but bypasses the
automatic rate-limit and give-up accounting. It is compiled only with
`CONFIG_ZX279128_ETH_DEBUG`, which is unset in the release. Its availability
on a bench image is not a production recovery interface.

The RX watchdog is separate from the platform hardware watchdog and reboot
driver. A datapath reset is also separate from PCIe/radio recovery. The 5 GHz
accessibility failures remain unresolved; Ethernet recovery does not establish
a fix for them. See [Watchdog](WATCHDOG.md) and [Wi-Fi](WIFI.md).

Host tests exercise stall decisions, NAPI kicks, retry limits, close/init/reopen
ordering and failure exits. They do not reproduce stalled silicon or prove
that a reset clears all possible hardware faults. The complete qualification
status remains in [Validation](../VALIDATION.md).

## Historical investigation

Earlier measurements, withdrawn hypotheses and old commands are preserved in
[the archived notebook](history/WEDGE-ANALYSIS.md). They are not current installation instructions.
