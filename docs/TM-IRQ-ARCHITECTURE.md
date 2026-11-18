> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](README.md),
> [installation](INSTALL.md) and [validation](../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# TM Interrupt-Driven Receive Architecture

Target: vendor-style interrupt-driven NAPI, not a production timer scanner.
This reconstruction records verified facts separately from unresolved startup
and race semantics. The first-found cursor experiment was removed unbooted.

Latest result: [queue-state initialization](#queue-state-initialization-recovered)
now clears stale bootloader occupancy and restores RX on a fresh forced-init
RAM boot. The IRQ consumer is implemented and has passed its initial RAM
delivery test; full traffic and lifecycle validation remain outstanding.

## Evidence

Stock `plat-zxylzb_9128S.ko`, functions `pon_tm_net_poll`, `zx_pon_tm_int`,
`pon_tm_net_int`, `pon_tm_int_init`, `pon_tm_queue_init`,
`soft_release_rx_desc`, `pp_bmu_free_bp`, and the stock DTS. ARM disassembly
was independently reviewed; Ghidra output is retained in private artifacts.

## IRQ Source and Lifecycle

* `tm@92340000` declares SPI 36, level high: GIC INTID 68. Obtain its Linux
  IRQ through the IRQ domain; do not hardcode 68 as a Linux IRQ number.
* The PON control interrupt is separate: SPI 34. Its handler does not dispatch
  TM RX. Existing IDM/PHY-only probes did not test the TM interrupt.
* TMC+0x100 is status. Dispatcher computes `(status & 3) & ~mask`.
* TMC+0x104 is an active-high mask: initialize to all ones; RX handler ORs 7;
  open/poll completion clear bits 0 and 1. Bit 2 remains masked.
* Handler masks, records the cause, then schedules NAPI if eligible.
* Vendor poll drains queues and completes NAPI before unmasking with local
  interrupts disabled. The vendor timer handles TX completion, not RX polling.
* No explicit write-to-clear status operation appears in this lifecycle.
  Do not invent W1C semantics. Live repeated status reads returned 0x7711,
  then 0x11: fields need individual characterization, not a blanket COR claim.

### Live Routing Probe

With CPU delivery for INTID 68 disabled (GIC enable word 0x000007c0), changing
TMC mask from 0xffffffff to 0xfffffffe changed GIC pending word
0x00500000 -> 0x00500010. Restoring the device mask returned pending to
0x00500000. The GIC enable register was never written. This validates device
mask polarity and routing, not ISR behavior under sustained traffic.

## Queue Counts and Rings

For q=0..7, pending register is **TMQ+0x100+4*q**. Low 16 bits count direction
0 descriptors; high 16 bits count direction 1 descriptors. A raw value 0x0a
therefore means ten pending direction-0 descriptors, not an idle queue.

Let B be `readl(TMC+0xf0)`. Each ring contains 1024 descriptors of 16 bytes:

`ring(direction, q) = B + direction*0x20000 + q*0x4000`.

The vendor maintains a separate sequential software consumer for every ring.
The poll budget bounds consumed descriptors, including discarded packets.
It does not scan descriptors for a first nonzero length or ownership marker.

### Live Count Measurements

With timer polling temporarily delayed, eight injected frames changed q0
pending 14 -> 22, then draining restored 14. TMQ+0x170 changed 0x7b -> 0x83
and remained 0x83 after draining. A 260-frame trial changed pending
14 -> 274 -> 14, while +0x170 changed 0x8e -> 0x92. Thus its observed
production value wraps at 256, below the 1024-entry ring size. It cannot alone
identify a safe full producer position or warm consumer. Old credit writes to
this address also contaminated earlier interpretations; they were disabled
for these measurements.

## Release Protocol

Descriptor return uses TMD+0x64/0x68 (TMC+0x4064/0x4068): wait for GO bit 0
to clear, write `(direction << 14) | (count << 4) | (class << 3) | q`, then GO=1.
Class is descriptor byte 6 bit 0. Buffer pool is separately byte 9 bit 0.

Vendor buffer return writes `index | (pool << 15)` to BM+0x10, with software
credits replenished from BM+0xdc bits 8:3. It handles each pool separately.
Payload and descriptor metadata must be captured before ownership is returned.
Timeouts must retain retryable ownership/debt, not silently discard a release.

### Consumer Ownership Design

Each ring needs a cursor, a cached pending-count snapshot and a durable release
record. A consumed descriptor still occupies the hardware queue until its
return completes. Refreshing a count while that return is pending would count
it again and advance into an unproduced slot. Decrement the cached count once
per consumed descriptor; block the ring on its release debt, and refresh only
after the snapshot is exhausted and its returns have completed.

Capture index, pool and descriptor class before any release. Follow the vendor
Linux order: copy payload and metadata, return the buffer using one credit,
then return the descriptor. An accepted buffer return must never be retried
because a later descriptor return stalls. The shared TMD command port needs
one global in-flight owner; GO clear retires that command, not an arbitrary
ring's debt. GO-clear ordering relative to pending-count updates still needs
live verification.

Keep cursors and debt across interface stop/reopen, which is not a DMA reset.
Budget zero must perform no RX work or NAPI completion. Bound debt retries
separately from packet work; a stalled release must retain a guaranteed retry
without creating an unbounded softirq loop. A release-retry work item is not
a periodic RX scanner. This design remains gated on verified initialization.

## Initialization: Not Yet Resolved

The vendor initializes all software queue consumers to zero after PON reset and
full datapath setup. Warm attachment cannot copy that assumption. Current
startup's blind ring wipe also discards ownership information and must go.

A quiesced live reset test stopped all four interfaces, cleared PON+0x08,
held reset for three seconds, then restored all ones. Pending count and the
observed producer cleared to zero; the ring base stayed 0x41a00000. NPP enable
and MAC configuration changed too. Interface reopen plus a limited restoration
of known NPP/MAC settings did not recover SSH. This proves reset-only startup
is insufficient. Full reset/reinitialization, or a verified complete hardware
cursor handoff, is required before activating the new consumer.

## Implementation Obligations

* Map every configured ring and both buffer pools within owned reserved memory.
* Initialize cursors from verified state, never first-found entries or an
  eight-bit counter alone. Validate ring depth/layout before enabling DMA/IRQs.
* Consume strictly from each queue's pending count and cursor, including slot
  zero. Apply required DMA barriers and count drops against the NAPI budget.
* Serialize IRQ mask changes and running state across IRQ, NAPI, and stop.
* Honor `napi_complete_done()` success. Never unmask after shutdown; use a
  nondestructive pending recheck to cover arrivals around completion/re-arm.
* On stop: mask, synchronize IRQ, disable NAPI, and retain or explicitly drain
  owned descriptors/buffers. Reopen must not reset cursors over live state.
* Timer polling may remain a temporary diagnostic, not the production RX path.

## Required Validation

Cold/warm startup with and without traffic; idle-to-burst; several ring wraps;
simultaneous ports and observed queue IDs; sustained bidirectional TCP; repeated
interface stop/reopen. Record IRQ counts/storms, masked arrivals and wakeups,
queue occupancy, retransmissions, byte-exact payloads and release failures.

The source-MAC/buffer-reuse anomaly is a separate test track. Repeat identical
labeled bursts before and after the rewrite, including quiet TX and reply-
producing traffic. Neither ordered consumption nor IRQ delivery proves that
anomaly fixed. All hardware changes remain RAM-only with recovery artifacts.

### Independent Pre-Rewrite Baseline

`tools/udp-burst-sink.c` provides a five-second, no-reply UDP receiver. It was
cross-compiled, uploaded to /tmp, and SHA256 verified before use. Two identical
eight-frame bursts used source MAC labels 01..08 and 64-byte payloads filled
with the corresponding label, first to closed UDP port 49001 and then to a
listening socket on that same port.

Both descriptor traces showed label 6 six times at buffer index zero, followed
by labels 7 and 8 at other buffer indices. The listening socket received
`6,6,6,6,6,6,7,8`. Thus payload duplication does not require UDP reply traffic.
The router-own-source-MAC symptom was not reproduced in these two arms; do not
claim its exact cause established. Saved evidence:
`artifacts/2026-09-08/udp-anomaly-pre-irq.log` in the private bench repository.
After-rewrite acceptance requires all eight distinct labels exactly once,
matching payloads and source identities, in both arms and repeated cold boots.

### Live Native Reference

The RAM-only stock shell loaded zx_ponreg, the platform module, tm and switch,
without running vendor rc/pc or mounting writable configuration partitions.
Root remained read-only. The platform reported 6144 normal 2048-byte buffers,
zero jumbo buffers, RX base 0x47f20000 and TX bases 0x47fe0000/0x47ff0000.
These are reference-owned addresses, not values to copy into OpenWrt's layout.

Stock sysfs was used to enable/autonegotiate physical port 2. Its handler
emitted a bottom-half warning and an additional VLAN-related message, so this
is a minimally configured reference, not a clean full vendor boot. Native IP
RX and TM IRQ delivery worked; ping reply delivery remained unverified.

With the same UDP/TCP selector value used by OpenWrt, the no-reply UDP sink
received labels 1..8 exactly once through native IRQ/NAPI. A second test held
TMC+0x104 at 0xffffffff while injecting eight frames: TMQ+0x110 reported 8
(direction 0, queue 4), other queue counts were zero, and the mask remained
set. Restoring 0xfffffffc delivered all eight labels exactly once. This
validates a positive native reference under deferred consumption as well as
ordinary IRQ delivery. It does not establish which OpenWrt difference causes
duplication. Evidence: native-irq-udp-labels.log and native-irq-masked-burst.log
in the private artifacts directory.

## Initialization Candidate Result

The initialization-only OpenWrt candidate corrected BM ordering/counts, removed
duplicate direct free-list injection and the forced TX buffer override, added
second-pool addressing/release, restored verified NPP/DMA/MAC settings, and
prevented live reinit. Review caught and corrected decimal 11 (0x0b) for SMCT,
stale software BM state after reset, and ingress-before-datapath-start ordering.

The forced-init RAM image booted but produced no RX pending descriptors. A MAC
bit-16 probe, verified RED SDK settings and the LAN-uplink clock-mask setting
did not recover SSH. Thus initialization is still incomplete. Do not activate
the new IRQ consumer or call the candidate a functional initialization path.
The missing switch/SDK operating-mode setup must be reconstructed against the
live native reference; the current timer code is only a diagnostic baseline.

### Bridge and Queue Initialization Audit

The next initialization-only candidate seeds BRG indirect RAM type 4 entries
0 and 1. Vendor `pon_pp_add_port_to_vlan` and `brg_ram_get/set` establish valid
bit 0, eight two-bit port modes at bits 1..16, read command bit 27, type at
bits 26..22, ready bit 0 at BRG+0x18, and descending data writes
BRG+0x24/+0x20/+0x1c. All ports in mode 3 gives low 17 bits 0x1ffff.
Stock VLAN 0 readback confirmed that value. The candidate preserves the other
fields, verifies readback, and returns bounded timeout errors. Host tests
exercise transaction order, preservation, each wait failure and failed writes.
The RAM boot completed initialization and VLAN 0 read back 0x1ffff, but the
hardware reception test failed as described below.

Further vendor audit established:

* TMC+0xfc is **buffer slice size**, not ring depth: normal bytes in bits
  13..0 and secondary bytes in bits 29..16. Vendor `pon_tm_set_bp_slice_size`
  and its register-table mask 0x3fff3fff agree. Current 0x08000800 configures
  two 2048-byte pools; stock uses 0x800 with its secondary pool disabled.
* Platform `tm_pon_tm_init` writes TMC+0x128=0x1fff and +0x130=0x1fffff,
  waits 1 ms, then initializes RED, DMA and BMU. OpenWrt omits these writes.
  Stock readback is zero for both. Their exact effects remain unknown;
  neither the sequence nor zero readback alone proves ring-pointer reset.
* TMC+0xc004 bit 0 selects external-DDR-only mode; bit 1 enables DDR cache.
  TMC+0xc008 bits 1..0 are `qmg_trap_cfg`, whose enum meanings remain unknown.
  These are distinct registers. Stock ends with +c004=2 and +c008=0;
  OpenWrt currently writes only +c004=0.

Saved native readbacks: `native-bridge-readback.log` and
`native-qmg-readback.log` in the private artifacts directory. Legacy `rx_heal`
and `/proc/zx_eth_reprime` must not be used: they return indices without
ownership proof and can duplicate buffers in the fully seeded pool.

### Bridge Candidate Hardware Result

`h199a-bridge-shell.kernel` SHA256:
`08cf19e68a50a17c8b7639e45efe2f7374d8cd1f3bf266e42a7864cd8b853eaf`.
The full build, direct shell-only kernel rebuild, 11 host tests and checkpatch
passed. TFTP transferred 3145728 bytes into RAM. The forced command line used
`ro init=/bin/sh`; root stayed squashfs read-only, with only proc, sysfs and
tmpfs mounted. No normal init, writable overlay or flash operation was run.

With only eth2 manually up at 192.168.1.1/24 (MAC 06:20:84:2f:87:b5), the PHY
negotiated 1 Gbit/s and MAC control was 0x00ba6003. BM was enabled, TM IRQs
masked, and VLAN 0 matched its programmed value. Eight pings received no
replies. Eight labeled UDP frames left all eight pending registers (both
directions) and TMQ+0x170 at zero; all netdev RX counters stayed zero.

A separate stopped-interface probe enabled the verified QMG DDR-cache bit
(TMC+0xc004: 0 -> 2), reopened eth2, and sent eight labels to its MAC and
another eight to the factory Ethernet MAC. Pending counts and production
remained zero. The cache bit was restored to zero with eth2 stopped, then
eth2 reopened. This negative result does not isolate a packet-duplication
mechanism: this candidate did not receive packets at all.

Evidence is saved as `bridge-shell-*.log`, with source and kernel config beside
the RAM image. The sysupgrade tar is a build artifact only, not installed.
Startup, the IRQ rewrite, and the required post-rewrite validation remain open.

## Queue-State Initialization Recovered

The subsequent pipeline trace localized the startup failure. Eight labeled
frames increased MAC2 total/good-unicast, SDET transport, SPA UNI2 SOP/EOP,
SBRG RX/TX and CLA trap counts by eight. RED trap input and output-drop counts
also rose by eight, while trap output and TM production stayed zero. NPP's
verified port-close register at 0x921c004c was zero, so port2 was not closed.

Relevant verified RED registers:

| Register | Meaning |
|---|---|
| 0x92344208 / 0x92344214 | Trap input / output counts |
| 0x92344218 | Output-drop count |
| 0x92344004 bits 4/3/2 | open_out_en / trap_color_en / share_mode |
| 0x92344004 bits 1..0 | cfg_enable: red_en plus color_en shifted by one |
| 0x92344040 bits 12..0 | Input shared limit |
| 0x92344074 bits 14..0 | Upstream output shared limit |

RED indirect RAM type0 is output-queue configuration; type1 is used space.
Both decode data0 bits10..0 as guard space and bits25..11 as shared/max space.
Wait for +0x18 bit0, issue BIT(27) plus type shifted22 plus queue index at
+0x14, wait ready again, then read +0x1c. The vendor only reads type1 status;
do not clear it by inventing a status-RAM write.

Queue 0 configuration and used space were both 0x400 (1024 guard units), while
the other 15 CPU queues reported zero used. Enabling RED open_out alone, then
all verified SDK global values (control0xde, limits0x3ff/0x3fff), did not
change the trap-to-drop behavior. A 0x400 queue limit does not truncate to 0.

With MAC ingress disabled, BM disabled and TM IRQs masked, the vendor's
TMC+0x128=0x1fff command changed queue 0 used space from 1024 to 0. Its immediate
readback was 0x1e7f and settled to 0; +0x130=0x1fffff read 0x4000 then 0. A full
reinitialization after those commands restored packet production. Restoring
the original RED globals (0xc0,0x400,0x2000) did not break reception again.
This identifies stale queue accounting as the observed startup failure;
individual initialization-command bit meanings remain unrecovered.

The driver now issues **both** commands before the vendor's 1 ms delay, then
checks their written bits clear with bounded 20 ms polls. It disables ingress
again after fabric reset, before state/pool initialization. Errors propagate
while BM and ingress remain disabled. Host tests exercise ordering and both
timeout exits. The unsafe bulk `rx_heal` and `zx_eth_reprime` paths and their
parameters were removed, with a regression check against reintroduction.

### Fresh RAM-Boot Evidence

`h199a-tm-state-shell.kernel` SHA256:
`1c77ef7816f808b61fe0b30ccabb8f9edd5f7b4645bcf495c145e5a1af42ccf6`.
Kernel build, 13 host tests and checkpatch pass. The box was power-cycled and
TFTP-loaded, then the kernel forced full initialization. No manual recovery
writes were used. This tests reset of a warm bootloader handoff, not a boot
without any prior bootloader network initialization.

Before opening interfaces, all 16 CPU RED occupancies, all 8 RX pending words
and TMQ+0x170 were zero. All 4 MACs had ingress disabled; BM was enabled and
TM IRQs masked. With IPv6 disabled and the diagnostic timer deferred 600 s,
the first controlled 106-byte frame changed q0 pending 0->1 and production 0->1,
and occupied descriptor slot 0: words 000001bb,01190000,2000d400,002401a8.
It decoded to normal-pool index 0 and length 106. This verifies the starting
slot for the tested queue; other queue positions and wraps still need tests.

A separate no-consumption labeled burst changed q0 pending 5->13. Slots 5..12
used distinct normal-pool indices 5..12, source MAC labels 01..08 in order,
and all 64 payload bytes matched each label. No RX poll ran during this test.
Thus this is a positive pre-IRQ ownership baseline, not evidence that ordered
consumption fixed the anomaly. Reply-producing traffic and the original
router-own-source-MAC symptom remain separate acceptance tests.

The interface was then stopped, canceling the diagnostic timer and preserving
pending descriptors. Root remains read-only with only proc/sysfs/tmpfs mounts.
Evidence: `bridge-shell-*-counter.log`, `bridge-shell-red-*.log`,
`bridge-shell-tm-init-command-probe.log`, and `tm-state-shell-cold1-*.log` in
the private artifacts directory. The IRQ consumer/release rewrite is next;
no IRQ throughput, wrap, reopen or missed-wakeup acceptance is claimed yet.

## IRQ Draft and Paused Bench

Work paused at the user's request on 2026-09-08. The new draft removes the RX
scanner, periodic hrtimer, slot-zero exclusion, producer-counter seeding and
consume-credit writes to 0x170. It maps all 16 rings, always initializes the
datapath at probe, and requests named TM SPI 36 before registering netdevs.

Each ring retains its cursor, cached count and release debt. Payload is copied
before buffer return; a failed credit acquisition retains buffer ownership.
One global owner tracks an in-flight descriptor-return command. Cached counts
are not refreshed over debt. A bounded busy retry is followed, if necessary,
by one-shot work; there is no periodic RX timer. Stop/reopen retains ownership.
IRQ entry masks before scheduling NAPI; completion honors napi_complete_done
and rechecks counts after unmasking under the lifecycle lock. Teardown closes
all ports before devres can free any netdev referenced by shared RX.

Runtime debug reinit now returns EOPNOTSUPP. The old BM-credit logging endpoint
was removed. Raw debug pokes can still violate ownership and must not be used
to reset or manipulate queues during normal IRQ operation.

Host tests compile the actual poll/release and IRQ/lifecycle functions against
MMIO models. Cases cover snapshots with later arrivals, slot zero, wraparound,
both directions, shared-command serialization, both pools, credit and GO
timeouts, invalid descriptors/counts, budget zero, masked interrupts, arrivals
during rearm, and state preservation across stop/reopen. All 13 tests, kernel
build and checkpatch pass. These are not substitutes for hardware load tests.

An additional quiesced hardware return test copied slot0's packet, returned its
normal buffer using a BM credit, then issued descriptor return0x18. On GO clear,
pending changed17->16, production stayed17, and descriptor bytes were unchanged.
No status acknowledgment or descriptor-memory wipe was needed.

RAM image `h199a-irq-shell.kernel` SHA256:
`66858a85c41bf2ebf5c26562eb512cdf56b286e00673b786c2834bdba9c0d248`.
Boot used `ro init=/bin/sh`, no normal userspace startup or writable overlay.
TM appeared as Linux IRQ27, GIC INTID68. Incoming test packets incremented IRQ
and RX counters, and pending queues drained to zero. A separate quiet2s sample
held IRQ count16->16. The earlier file named `irq-shell-cold1-idle.log` overlaps
ping injection and is not idle evidence; use `irq-shell-cold1-quiet.log`.

Twelve pings received no replies. The router's host-neighbor entry remained
incomplete, so TX/ARP remains a separate unresolved path. The no-reply UDP
sink was uploaded to /tmp and SHA256 verified, but **was not executed** before
the pause. No post-IRQ labeled-burst, wrap, simultaneous-port, sustained TCP,
payload-integrity, missed-wakeup, or hardware stop/reopen acceptance is claimed.

At pause, all interfaces were down, TM mask was0xffffffff, MAC2 was0x00ba6002,
q0 pending was0. IRQ count20 matched eth2 RX packets20 (2896 bytes); RX errors
and drops were0. Root remained read-only with only proc/sysfs/tmpfs mounts.
Source, config, DTS, image, checksums and logs are in private artifacts dated
2026-09-08; see the parent bench handoff for exact resume commands. No flash
writes were performed. Do not resume experiments until the user asks.

## 2026-09-10: root cause found, TX fixed, first validation runs

**The TX/ARP path was never a TX bug.** This driver lost `zx_datapath_warm()` in
the IRQ rewrite. The working-era revision required BOTH a plausible ring-base pair
(`TMC+0xf0`, `TMQ+0x60` inside the reserved window) AND at least one MAC whose
control word has its top half set. Without it the driver re-initialised a datapath
U-Boot had already configured, and that re-initialisation is what stopped every
transmit. Why the MAC half matters here: the device tree binds **eth0** while the
cable is on **eth2**, so U-Boot configures the MACs it carried TFTP over and the
bound MAC can read 0.

Restored verbatim from `artifacts/2026-09-08/h199a-tm-state-eth.c:840`. This is
NOT "initialising is destructive" - the flashed bank-A image runs a full cold init
(`init_mask=0x3ff`) and transmits (measured 2026-09-10). The failure is specific to
re-initialising an **already-configured** datapath.

Kernel `artifacts/2026-09-10/h199a-warmfull2.kernel`, SHA256
`922bbac73f261fad72b5ee386b83499fe483f0c5ebf97c98ee657217234082db`.

### Validation runs so far (RAM shell, eth2, IRQ driver)

| test | result |
|---|---|
| host -> device ping | 5/5, 0% loss, 0.198-0.508 ms |
| device -> host ping | 3/3 x3 consecutive rounds, 0% loss, 0.216-0.456 ms |
| idle, 6 s, no traffic | `irq=0 rx=0` - no interrupt storm, no missed-wakeup loop |
| burst, 30 x 1024-byte pings | `irq=33 rx=33 err=0 drop=0` - exactly one IRQ per frame |

**The burst's 16% ping loss is NOT a datapath measurement and must not be quoted
as one.** A 1024-byte ICMP payload exceeds the MTU, so those pings were
fragmented by the host and the loss occurred in fragment reassembly, not in the
driver. `irq == rx` at 33 is the real result: the driver delivered every frame the
hardware produced, with zero errors and zero drops.

**Benches notes that cost time and should be pre-empted:**
* busybox `ping` on this image rejects fractional intervals - `-i 0.1` fails with
  `invalid number '0.1'`, and because the failure is silent in a redirected
  pipeline it looks like a dead datapath. Use whole seconds.
* A single-shot ping immediately after `ip neigh del` measures ARP, not egress.
  Send several rounds, or wait for the neighbour to reach REACHABLE.

### Still not validated

Labeled-burst payload integrity against `tools/udp-burst-sink.c`, ring wraps,
simultaneous ports, sustained bidirectional TCP, and hardware stop/reopen are
still outstanding. The genuine cold-boot path (no bootloader network use) has not
been re-measured with the restored check; the flashed image shows a full cold init
works, but that is another build.

### 2026-09-10 validation update (rounds 20-23)

The TX blocker is fixed (see above). Validation matrix movement since:

| obligation | state |
|---|---|
| idle, no interrupt storm | PASS - `irq=0 rx=0` over 6 s |
| exactly one IRQ per frame | PASS - `irq=33 rx=33` over a 30-packet burst |
| both directions, sub-ms RTT | PASS - host<->device, 0.2-0.6 ms |
| inbound reaches userspace | PASS via TCP - host `nc -vz` to a closed port returns `Connection refused`, i.e. the device received the SYN and returned its RST; census agreed (`tcp=2`) |
| interface stop/reopen | PASS - down/up, then both directions again; `err=0 drop=0`, cursors and ownership preserved |
| labelled-burst payload integrity | NOT RUN |
| ring wraps | NOT RUN |
| simultaneous ports | NOT RUN |
| sustained bidirectional TCP | NOT RUN |
| cold boot with no bootloader network use | NOT RUN |

**New instrument: the RX protocol census.** The IRQ rewrite had left
`c_icmp`/`c_udp`/`c_tcp_bare`/`c_tcp_data` declared but unused, so the driver
could not report what it was receiving - which cost several rounds to a
misdiagnosis. `/proc/zx_eth_regs` now prints:

```
RXCENSUS icmp=8 udp=8 tcp=1 other=0 nonipv4=6
```

Prefer this over `rx_packets` for any ingress question.

**Testing cautions that repeatedly produced false failures here:**

* The shell has **no `/dev/null`**, no fractional `ping -i`, and **no `nc`**.
  A listener test written with any of those fails in a way that looks exactly
  like a dead datapath. Confirm the test tool exists before interpreting a
  negative.
* The host's PERMANENT ARP entry for `192.168.1.1` survives `ip neigh flush` and
  must be removed with `ip neigh del` after TFTP work.
* After an interface reopen the device's own ARP entry may be empty; prime it
  with a host->device ping before testing device->host.

### 2026-09-10 validation update (round 30): RX corruption confirmed at the ring, not the host

The payload-integrity gate is no longer "NOT RUN", and it **failed**. The frame
reaches the driver intact and is corrupted on the way out of the RX ring.

**Evidence chain for one unpaced burst of 8 labelled frames** (`sport = 49020+n`,
64-byte payload of `n`, `dport = 49010`), all measured in the same run:

| counter | delta |
|---|---|
| host `tx_packets` | +8 |
| `eth2` rx_packets | +8 |
| driver `RXCENSUS udp` | +8 |
| `Ip: InReceives` | +8 |
| `Ip: InDelivers` | +3 |
| `Udp: InDatagrams` | +3 |

Every error counter stayed at zero - `Ip InHdrErrors`, `Ip InDiscards`,
`Ip InAddrErrors`, `Ip InUnknownProtos`, `Udp InErrors`, `Udp RcvbufErrors`,
`Udp InCsumErrors`, `eth2 rx_errs`, `eth2 rx_drop`, and `NoPorts` was unchanged.
**Five of eight frames are discarded between IP receive and delivery with no
counter moving.**

**Pacing the same 8 frames 350 ms apart did not help**, which rules out burst
overflow and proves corruption. That capture contains all three defects at once:

```
len=64 label=1 sport=49021
len=64 label=7 sport=49027
len=64 label=7 sport=49010     <- source port equals the DESTINATION port
len=64 label=5 sport=49025
len=64 label=5 sport=49025
len=64 label=5 sport=49025
```

* duplication - label 5 delivered three times, label 7 twice; labels 2,3,4,6,8 never arrive;
* header corruption - a frame delivered to port 49010 whose *source* port reads 49010;
* silent loss - 8 on the wire, 7 in the driver census, 6 at UDP.

**Interpretation.** This is RX descriptor/buffer aliasing: descriptors are being
recycled to hardware while the driver still reads the buffers behind them, so it
re-reads stale content (repeats), reads partially-overwritten buffers (scrambled
header), and loses real frames to overwrite. It is the **same two-resource class
as the TX wedge** - descriptor release versus buffer ownership - which
`desc_release` fixed on the transmit side. RX needs the equivalent.

Because the host is proven to transmit exactly 8 distinct frames, the historical
`6,6,6,6,6,6,7,8` anomaly in `artifacts/2026-09-08/udp-anomaly-pre-irq.log` is the
**same pre-existing RX defect**. The IRQ rewrite neither caused nor fixed it; it
was previously misattributed to the sender.

**Root cause candidate (code audit, same round).** The checksum-offload theory is
**dead**: `grep ip_summed` over the driver returns nothing, so skbs keep
`CHECKSUM_NONE` and the stack validates checksums itself - which makes the
uncounted drop *more* anomalous, not less. The strong candidate is buffer
geometry:

```
ZX_RX_RINGS = 16, RING_ENTRIES = 1024   -> 16384 descriptors
BUF_COUNT   = 2048, BUF2_COUNT  = 512   ->  2560 buffers
```

Payload is read from one global pool at `bufs + idx * BUF_SIZE + BUF_HDR`,
validated only by `idx < BUF_COUNT`/`BUF2_COUNT`. With 16384 descriptors
addressing 2560 buffers, a buffer index appears in several descriptors at once,
so `idx` is not a stable identity for the frame the descriptor describes.
Compounding it, `zx_rx_release` calls `zx_bm_free` on the buffer **before**
returning the descriptor via `TMD_PAYLOAD`, so the BM may reassign the buffer
while descriptors still reference it. Re-reading a reassigned buffer yields
exactly what was observed: an older frame delivered again, a half-overwritten
buffer (scrambled `sport`), and real frames overwritten before the copy.

**Sharper finding: the live RX free lists contradict their own comments.**
`init_mask` is **959** on the running board (confirmed via sysfs), so
`ZXI_FREELIST` (BIT 4) and `ZXI_RINGS` (BIT 7) are set and the free-list init at
lines 1960-2023 is on the **active** path. In it:

* **Bug 1.** The comment at line 1960 says "do NOT hand buffer 0 to the RX free
  list" and line 1979 says to stop before index 2047 (the TX scratch), but the
  loop is `for (i = 0; i < BUF_COUNT; i++)` - writing **0 through 2047
  inclusive**, i.e. both indices the comments exclude. Per the same comment,
  `zx_bm_alloc()` always returns index 0, so every TX frame is copied into
  buffer 0 while RX may also own it.
* **Bug 2.** Line 1999 says "Free list 2 is DELIBERATELY left empty" and explains
  that pool-2 indices alias list 1's while addressing 0x41400000, so a frame from
  pool 2 is "read from the wrong 2 KiB and handed up as valid-looking data with a
  valid ethertype - which no detector in this driver can catch". Line 2010
  populates it anyway with `for (i = 0; i < BUF2_COUNT; i++)`.

That second description is exactly the observed failure: structurally valid
IPv4/UDP frames that pass the ethertype and IP-protocol checks (hence
`RXCENSUS udp +8` and `Ip: InReceives +8`) yet carry the wrong payload, so only 3
of 8 reach UDP and one shows `sport == dport`. **Neither bug is fixed.**

**Correction, same round: Bug 1 is exonerated as the cause.** `sendp` builds
layer-2 frames directly, so the host never ARPs and the device is never provoked
into a reply. Bracketing a paced burst with the device's `/proc/net/dev`:

```
D0  eth2:  169332  237 ... 8854  90
D1  eth2:  170570  245 ... 8854  90
            rx +8            tx +0        <- the device transmitted NOTHING
RXCENSUS udp +8,  Udp: InDatagrams +7
```

Zero transmits, and a frame is still lost. TX/RX buffer sharing therefore cannot
explain the corruption, and that same run was **mostly clean** - labels
1,2,3,5,6,7,8 with every source port matching, versus the earlier paced run's
`label=5` x3 and `sport=49010`. The fault is **intermittent** and has at least two
faces: a steady unexplained drop and an occasional duplication with header
scramble.

Because the census increments *before* `napi_gro_receive` and every counted frame
has already been copied into a fresh skb, a counted frame cannot be a stale buffer
read - so the steady drop lives in **GRO or IP**, above the driver, still with no
error counter moving.

**Statistics: eight repeated paced bursts (64 frames).** One burst proves nothing,
so the same burst was run eight times against chained sink windows:

```
total sent ............ 64
total delivered ....... 63
label/sport mismatches .. 0      <- no byte corruption anywhere
```

Delivered label sequence: `1,2,2,2,8,6,7,8, 2,8,2,4,5,6,7,8, ... 1,2,3,4,5,6,7,8`
(the final burst was perfect). Histogram is lopsided the way duplication predicts:
labels 2, 4, 8 over-delivered (10, 9, 11 vs 8) and 1, 3 under-delivered (5 each).

**Interpretation: the defect delivers the wrong *sequence* of otherwise perfect
frames.** Sixty-three consecutive datagrams with not one payload/source-port
disagreement rules out byte corruption as the dominant effect - the earlier
`sport=49010` line was not representative. Frames are re-delivered and a *later*
frame appears early (`8` in position 5 of a 1-8 burst), which means the driver
read a descriptor whose buffer index the hardware had not yet reached in
sequence: descriptor consumption out of step with the producer.

Lead suspect is therefore the pending-count read at the top of `zx_eth_poll`
(line ~1079), `(pending >> (ring / ZX_RX_QUEUES * 16)) & 0xffff` with
`ZX_RX_RINGS = 16`, `ZX_RX_QUEUES = 8`. If `q->remaining` ever exceeds the number
of descriptors actually published, the driver reads unwritten descriptors, which
are stale from an earlier pass, and delivers their buffers as current.

**Revised follow-ups:**

1. **Instrument, don't change behaviour.** Add a temporary printk in
   `zx_eth_poll` logging `q->remaining`, `q->cursor`, the descriptor `idx` and the
   census label; re-run the 8-burst loop. Narrow question: does `idx` repeat
   within a lap or arrive out of order? This confirms or kills the mechanism.
2. **Only if confirmed**, check whether `TMQ_PENDING` can over-report, and whether
   the ring/half mapping (rings 0-7 low half, 8-15 high half) is correct.
3. Bug 1 (TX/RX share buffer 0) is **latent, not causal** - the device transmits
   nothing during these bursts (`tx_packets +0`). Bug 2 predicts byte corruption
   and none was seen. Both are later, one-at-a-time cleanups, not the next build.

**Bench precondition discovered this round:** `ignore_loglevel=Y` makes
`dmesg -n 1` useless, so `zx-spifc`'s periodic `pr_info` HEALTH line
(zx_spifc_nand.c:1387) corrupts UART transfers with input overruns. Set
`echo N > /sys/module/printk/parameters/ignore_loglevel` first; transfers then
verify first try.

| validation item | status |
|---|---|
| unidirectional ping, host<->device | PASS |
| labelled UDP burst, small | **FAIL - frames duplicated/omitted, bytes intact** |
| burst paced at 350 ms | **FAIL - not burst overflow** |
| 8 repeated paced bursts (64 frames) | **FAIL - 63/64 delivered, 0 label/sport mismatches, sequence scrambled** |
| device TX during burst | **NONE (`tx_packets +0`) - TX/RX collision excluded as the *pure-RX* cause** |
| per-descriptor buffer identity (`rx_trace`) | **FAIL - `idx=0` on all 32 descriptors: every frame lands in buffer 0 (ROOT CAUSE)** |
| ring wraps | NOT RUN |
| simultaneous ports | NOT RUN |
| sustained bidirectional TCP | NOT RUN |
| cold boot with no bootloader network use | NOT RUN |

### 2026-09-10 round 31: ROOT CAUSE - every RX frame lands in buffer 0

A per-descriptor trace (`rx_trace` module parameter, added this round) settles it.
**Every RX descriptor reports `idx=0`, and the frame data really is in buffer 0.**

```
RXTRACE r=0 cur=180 rem=1 idx=0 pool=0 len=215 valid=1 b42=05
len=64 label=5 sport=49025
RXTRACE r=0 cur=181 rem=1 idx=0 pool=0 len=215 valid=1 b42=06
len=64 label=6 sport=49026
```

Across four bursts and 32 descriptors (`cur` 168..199) **`idx` is 0 in every
line**. The trace reads byte 42 of the buffer `idx` selects - the UDP payload's
first byte - and `b42` **matches the label the sink then received**. A wrong `idx`
decode would read unrelated memory and could not track the labels, so the hardware
genuinely delivers every frame into buffer 0.

**This is the root cause of the round 29-30 corruption:**

* duplication - buffer 0 is overwritten by frame N+1 while frame N is being copied;
* loss - a frame is overwritten before it is copied;
* TX/RX collision - `txdbg` shows TX using buffer 0 too, so a transmit clobbers a receive;
* intermittency - the result depends only on whether hardware overwrote buffer 0
  before or after `memcpy_fromio`, which is why one script produced 1/8, 3/8, 6/8,
  7/8 and 8/8 with no code change.

The descriptor `len` is unreliable too: it alternates 215/82, neither being the
106-byte frame sent. Delivered datagrams still carry a correct 64-byte payload
because UDP takes its length from the IP header, not the skb.

**Why the allocator keeps returning 0:** the driver returns the index it read to
the pool - `zx_bm_free(ze, q->buffer | (q->pool << 15))` with `q->buffer = idx =
0` - so 0 goes back to the head of the pool and the next frame is allocated into 0
again. Self-perpetuating. The free list is primed with 0..2047 at init and the
hardware appears never to advance past the first entry.

**Next:** read the free-list table and BM allocation index back after traffic
(read-only via `/proc/zx_eth_poke`) to confirm the allocator never advances, then
make each frame get a distinct buffer. The success criterion is already
instrumented - `idx` must take many distinct values across a burst, not 0.

**Bench preconditions that each cost a failed transfer** (a RAM boot with
`init=/bin/sh` mounts nothing):

1. `mount -t tmpfs tmpfs /tmp` - without it `/tmp` is read-only, `done >/tmp/sink3`
   fails, the `while read` loop never engages, and the UART blob tool appears to
   corrupt its payload while actually failing to redirect.
2. `mount -t proc proc /proc; mount -t sysfs sysfs /sys` - otherwise the module
   parameters and `/proc/net/snmp` appear not to exist.
3. `echo N > /sys/module/printk/parameters/ignore_loglevel` - it is `Y` in the
   cmdline and overrides `console_loglevel` entirely, so writing `0 0 0 0` to
   `/proc/sys/kernel/printk` does not quiet the console. Contrariwise a `pr_info`
   trace needs `echo 8 4 1 7 > /proc/sys/kernel/printk` **and** `ignore_loglevel=N`.
4. `echo 0 > /sys/module/zx279128_eth/parameters/tx_dbg_max` before any UART
   transfer; `txdbg` fires per transmit and corrupted one mid-flight.

### 2026-09-10 round 32: the RX free list DOES drive buffers - the ENCODING is the suspect

Register map recovered via `/proc/zx_eth_poke` (`TMC = 0x92340000`,
`BM = 0x92348000`):

```
TMC+0xe8 = 0x41800000   free list 1 base      TMC+0xf4 = 0x41000000   pool 1 base
TMC+0xec = 0x41808000   free list 2 base      TMC+0xf8 = 0x41400000   pool 2 base
TMC+0xf0 = 0x41a00000   RX ring base          TMC+0xfc = 0x08000800   2048 / 2048 lengths
```

The driver's list bases are correct and the length is registered as 2048, so the
list is pointed at, sized and filled. **A first test that rewrote only `fl1[0]`
was INVALID** - the list is consumed from the head forward and the head was
already past entry 0 - so it proved nothing and must not be repeated.

**The decisive test: fill the WHOLE list.** One device-side shell loop overwrote
all 2048 entries with the constant 600 (`0x02580258` repeated), verified by
readback. Then:

```
RXTRACE r=0 cur=223 rem=1 idx=80 pool=0 len=60 valid=1 b42=45
RXTRACE r=0 cur=224 rem=1 idx=83 pool=0 len=60 valid=1 b42=07
RXTRACE r=0 cur=225 rem=1 idx=85 pool=0 len=60 valid=1 b42=00
RXTRACE r=0 cur=227 rem=1 idx=90 pool=0 len=60 valid=1 b42=00
RXTRACE r=0 cur=228 rem=1 idx=89 pool=0 len=60 valid=1 b42=00
```

**`idx` stopped being a constant 0 and became varied non-zero values.** The free
list therefore does select the RX buffer, and its *contents* are what made the
hardware pick index 0.

The values are 80-90, **not** the 600 written, so the hardware is not reading the
entries as the big-endian u16 the driver writes (`writew(cpu_to_be16(i), ...)`).
A wrong width or endianness would make most of the original 0..2047 entries decode
out of range or to zero, leaving a single usable index - exactly the constant-0
behaviour. Writing a constant removes that range variation, which is why some
entries then decode to valid non-zero indices.

**Prime suspect: the free-list entry encoding (width/endianness).** Not the list
base, not the length register, not the BM pool size - all three are known good.

Also confirmed from `research/UBOOT-WORKING-DATAPATH-REFERENCE.md`: `BM+0x40..0x4c`
are **counters, not configuration**, so the driver's `BUF_COUNT << 16` writes to
`BM+0x48` are meaningless (hence reading back `0x80`). On this warm boot
`BM+0xc8 = 0x400` and `BM+0xdc = 0x50000111` already match the working reference;
`BM+0xd8 = 0x4000` (reference `0x6000`) refuses writes, so it is gated rather than
settable - a secondary question.

**Next:** change `writew(cpu_to_be16(i), ...)` to little-endian (or to a byte-wide
list) and re-run. Success is unchanged and already instrumented: `idx` must take
many distinct values across a burst.

### 2026-09-10 round 33: free-list ENDIANNESS fixed (partial), STRIDE now the question

The driver filled the RX free list with big-endian u16 entries
(`cpu_to_be16(i)`); the hardware reads it little-endian. Filling the whole table
both ways through `/proc/zx_eth_poke` and reading `rx_trace` showed it directly:

```
big-endian    -> idx = 0,0,0,0,0,0,0,0                 (stuck: one usable buffer)
little-endian -> idx = 97,98,99,100,102,103,104,105    (advances)
```

Fix applied to list 1 (`writew(i, ...)`), rebuilt, RAM-booted, verified:

```
RXCENSUS udp  8 -> 16          (+8, exactly the burst)
RXTRACE r=0 cur=8  idx=94  len=1514 b42=00
RXTRACE r=0 cur=9  idx=96  len=1514 b42=00
RXTRACE r=0 cur=10 idx=98  len=1514 b42=00
... through cur=15 idx=108
Udp: InDatagrams 0 -> 0        (nothing reached UDP)
```

**Fixed:** `idx` is no longer constant - it advances monotonically and distinctly.
**Still broken:** delivery; `len=1514` and `b42=00` say the buffers read do not
hold the frames that arrived.

**The stride is the new lead: `idx` advances by 2, not 1.** One entry per frame
should step by one. A stride of two is what a width mismatch produces, and the
mapping sizes agree: `fl1 = ioremap_wc(0x41800000, SZ_8K)` for 2048 entries is
**4 bytes per entry**, not the 2 the driver writes. With BE u16 pairs, a 32-bit
LE read of entries 0..1 gives `0x01000000`, far outside `BUF_COUNT` - every entry
rejected, allocator falls back to one buffer. That matches the original constant 0.

**Next: write 32-bit little-endian entries at a 4-byte stride** (`writel(i, fl1 +
i*4)`). Expected `idx` step 1, `len` ~106, sink labels 1..8, `Udp: InDatagrams +8`.
Do not revert the endianness change - it is an improvement and it is what made the
stride visible.

### 2026-09-10 round 34: RETRACTION of round 33 - the fix never ran, and the test was confounded

**Round 33's "the free list is little-endian, verified" is withdrawn and the code
change reverted.** Two independent faults:

1. **The fill never executes on a warm boot.** It lives in `datapath_init()`, which
   the warm path skips - every recent boot logged
   `datapath warm (rx ring 41a00000 tx ring 41c00000) - init skipped` (16 times in
   the log, including the trace33 boot). Every measurement in rounds 30-33 was
   therefore made against **U-Boot's** table, not the driver's, and the driver's
   init code was never exercised.
2. **The round-32 comparison was confounded.** The big-endian fill was a
   **constant** (`0x02580258` repeated) and the little-endian fill was
   **sequential**. A constant cannot advance under any encoding, so that test
   compared constant-vs-sequential, not BE-vs-LE, and proves nothing about byte
   order.

U-Boot's datapath works, and the table it leaves behind reads as big-endian u16
entries (entry1 = `0x0100` little-endian, i.e. bytes `00 01`). That is consistent
with the driver's original `cpu_to_be16(i)`, so the code has been **reverted to
it** with a comment forbidding another flip without a clean test.

**Still true:** the register map; `BM+0x40..0x4c` are counters; the warm path skips
`datapath_init()`; `rx_trace` makes buffer identity visible.

**Still unexplained and now the strongest lead:** `idx` was a constant 0 in rounds
30-32 yet advanced by 2 in round 33 - both warm boots against U-Boot's table. The
free list is not the only variable; find what else differed.

**Next:** force the cold path (`force_dp_init`), then compare two *sequential*
fills (BE vs LE) with `rx_trace` armed. Until the fill executes, no free-list
property is being tested at all - the precondition every round 30-33 measurement
silently lacked.

### 2026-09-10 round 35: the driver's own cold init leaves RX DEAD

Round 34 showed `datapath_init()` never runs on a warm boot. Forcing it
(`zx279128_eth.force_dp_init=1` in `CONFIG_CMDLINE`, verified present in vmlinux
before booting) gives an emphatic answer:

```
zx279128-eth 92200000.ethernet: datapath init at probe (cold)
zx-eth: freelist1 readback [0]=0000 [1]=0001 [2047]=07ff
zx-eth: freelist2 readback [0]=0000 [511]=ff01
```

The fill runs and reads back correctly - and then receive is **completely dead**:

```
RXCENSUS icmp=0 udp=0 tcp=0 other=0 nonipv4=0     (before and after an 8-frame burst)
Udp: InDatagrams 0, NoPorts 0                     (nothing reached UDP at all)
host ping: 2 transmitted, 0 received, 100% loss
```

while the interface is healthy in every other respect:

```
4: eth2: <BROADCAST,MULTICAST,UP,LOWER_UP> ... state UP
txdbg mode=0 slot=166 len=70 buf=257 ...
```

**`datapath_init()` produces a datapath that transmits and cannot receive.** The
warm path is therefore load-bearing, not a convenience: the working RX
configuration is the one U-Boot leaves behind, and the driver's cold init does not
reproduce it. That is why `zx_datapath_warm()` exists and why every RX measurement
in rounds 30-34 was made against U-Boot's state.

**Consequence for the work: fixing the free-list fill cannot help.** The fill's
code path is inside the init that kills RX, so its byte order is moot. The
productive direction is to diff U-Boot's working datapath state against the
driver's warm-attach state and find what U-Boot configures that the driver neither
sets nor preserves - `research/UBOOT-WORKING-DATAPATH-REFERENCE.md` already holds a
U-Boot register dump taken after a working TFTP.

On a ZTE flash boot the bootloader has already initialised the datapath, so the
warm path is the normal path - hardening the warm attach is the realistic target.

Also fixed this round: `files/target/linux/armsr/config-6.6` carried a shorter
`CONFIG_CMDLINE` than the working one (missing `module_blacklist` and
`ro init=/bin/sh`), and `build.sh` does `cp -a files/. openwrt/`, so that overlay
would clobber the working cmdline on the next full build. Both configs and all
three copies of the driver are now synced.

### 2026-09-10 round 36: `idx` is a function of the CURSOR - the descriptor STRIDE is wrong

The clean one-variable test round 34 demanded: replace the whole free list with a
verified sequential little-endian fill (`[41800000] = 00010000`) and re-run the
same burst on the warm path.

```
baseline (U-Boot's list)   RXCENSUS udp +10,  NoPorts +1,  idx = 0,0,80,82,84,...,96
sequential LE fill         RXCENSUS udp +8,   NoPorts +0,  idx = 106,108,110,...,120
```

**Nothing changed.** A list reading back as 0,1,2,...,2047 cannot leave `idx` at
106 while the cursor is at 15. So the descriptor's `idx` is **not** sourced from the
free list, and four rounds of free-list work were aimed at the wrong object.

**The real finding:**

```
idx == 2 * cursor + 76      for 20 of 21 descriptors (only outlier: cur=19)
```

A per-frame buffer index cannot be an exact linear function of the software
cursor. This is the signature of a **descriptor stride mismatch**. The sibling
ZX279133 driver uses **32-byte** descriptors (`research/SIBLING-DRIVER-RX-AND-SPA.md`
section 1.6: `__le32 address; __le32 length_flags; __le32 metadata[6]`); this
driver assumes **16** (`DESC_SIZE`). Reading every other half of each descriptor
would explain, all at once:

* `idx` advancing by exactly 2 per driver step;
* `len` pinned at a constant 1514 rather than the frame's ~106;
* `b42 = 0` - the payload is not where the driver looks;
* delivery of 0-1 in 8-10 with **no error counter**, because the bytes the census
  reads (ethertype, IP protocol) still decode plausibly while the body is wrong.

**Next: set `DESC_SIZE = 32` and re-run the trace.** Success is `idx` no longer
being `2*cur+76`, `len` ~106, and `NoPorts` advancing by 8. If that lands, the
`idx`/`len`/`pool` field offsets must be re-derived from the 32-byte layout rather
than patched onto the 16-byte decode.

### 2026-09-10 round 37: the RX descriptors hold NO per-frame fields - round 36 retracted

Raw ring memory at `cur = 22,23,24` (base 0x41a00000):

```
desc 22:  000001bb  f1180000  200bd400  002417a8
desc 23:  000001bb  f5180000  200bd400  002417a8
desc 24:  000001bb  f9180000  200bd400  002417a8
```

**Only one byte differs across all three** - the top byte of word 1, counting
`f1 -> f5 -> f9` (+4 per descriptor). No per-frame buffer index, no per-frame
length.

That explains round 36 exactly and is **not** a stride problem. The driver decodes
`idx = desc[7] >> 1`, and `desc[7]` *is* that counter byte: `0xf1 >> 1 = 120`,
matching the trace's `idx=120` at `cur=22`. So `idx == 2*cursor + 76` is a
**free-running sequence counter read as a buffer index**, and `len` (1514) is a
constant template field in word 3.

**The 32-byte-stride hypothesis from round 36 is retracted.** A stride error would
give alternating garbage halves; it cannot give three descriptors differing in one
counter byte.

**Also untrustworthy now:** everything derived from `idx`/`len` in rounds 30-36 -
the "one buffer" story, the duplication mechanism, the free-list encoding, and the
delivery statistics. The RXCENSUS and `/proc/net/snmp` counters remain valid (they
come from payload and stack, not the descriptor), so *"~0-1 of 8-10 frames are
delivered"* is still a real, unexplained result.

**Next:** diff a run of memory across the ring region before and after a burst and
find what actually changes per frame - that locates the real descriptor store and
its true stride. No rebuild needed.

### 2026-09-10 round 38: ring diff attempted - INCONCLUSIVE, sampled behind the cursor

Sampling the descriptor at 0x180 (`cur = 24`) before and after a burst gave
identical bytes, but that proves nothing: the software cursor has advanced past 24,
so it is a **consumed** descriptor and cannot change. Sampling behind the cursor can
only ever return "no change" - the same error as round 32's `fl1[0]` test.

**Correct method for any future ring diff:** read the cursor first, sample
`cursor + N` (N = 2..8) ahead, burst, then re-read the cursor and the same absolute
addresses. Only addresses still ahead of the new cursor carry information.

The round-37 conclusion stands on its own evidence (three consecutive descriptors
differing only in one counter byte), and so does the real unexplained result:
**receive works at the netdev and only ~0-1 of 8-10 frames reaches UDP.**

Also: every raw-memory probe so far read single words at 16-byte spacing, which
samples 4 of every 64 bytes. Read whole descriptors.

### 2026-09-10 round 39: the descriptor region is a TEMPLATE - word1 is not a counter

Round 37 saw word 1's high byte run `f1 -> f5 -> f9` and called it a counter.
Widening to eight consecutive descriptors (`cur = 24..31`) refutes that:

```
cur 24  f9180000     cur 28  01180000
cur 25  fd180000     cur 29  01180000
cur 26  4d180000     cur 30  01180000
cur 27  01180000     cur 31  01180000
```

Not monotonic (`fd -> 4d` breaks the +4 run), and it collapses to `0x01` and
stays. **`0x01` decodes to `idx = 0x01 >> 1 = 0`** - which is exactly the constant
`idx=0` of rounds 30-32. Those rounds were not seeing an allocator reuse one
buffer; they were reading a template field.

The descriptor at `TMC+0xf0` is a template -
`000001bb / 01180000 / 200bd400 / 002417a8` - with occasional variants in word 1
during traffic. The driver's `idx` and `len` decode that template, so both are
constants and every conclusion built on them since round 30 is void.

**Solid:** word 0 of that region is a constant `0x000001bb`; `idx`/`len` are a
template field and a constant; `RXCENSUS` and `/proc/net/snmp` remain valid; and
**only ~0-1 of 8-10 frames reaches UDP** - the real, unexplained defect.

**Next:** sample *ahead of the cursor* with whole descriptors; if 0x41a00000 stays
templated, scan 0x41000000-0x41ffffff for the region that changes per frame. Work
from raw bytes only - four consecutive rounds have been retracted by reasoning
about decoded fields.

### 2026-09-10 round 40: RX MECHANISM ESTABLISHED - a DMA race on a single shared buffer

**Two raw probes settled what nine rounds of descriptor reasoning could not.**

**(1) The buffer contains an intact frame.** Reading the address the driver
computes (`ze->bufs + idx*BUF_SIZE + BUF_HDR` with `idx=0` -> `0x41000010`):

```
dst MAC 06:20:84:2f:87:b5   src MAC 02:00:00:00:00:05   ethertype 0800
IPv4, total length 92, protocol 17 (UDP)
```

A complete, correct frame from the bench burst, in buffer 0. So `idx = 0` is
**correct**, there is **no byte corruption**, and the descriptor is not a
meaningless template - the hardware genuinely uses buffer 0.

**(2) Spacing alone decides success.** Same 8 frames, same kernel, only the
interval changed:

```
fast (350 ms):  RXCENSUS udp +8..10   NoPorts +0..+1    ~0-1 of 8 delivered
slow (1500 ms): RXCENSUS udp +9       NoPorts +8        8 of 8 DELIVERED
```

**The mechanism:**

1. every frame is written into **buffer 0**;
2. the driver's `memcpy_fromio` of buffer 0 races the DMA writing the next frame
   into that same 2 KiB;
3. copy wins -> frame delivered; DMA wins -> the driver copies the wrong frame,
   which appears as duplication (a later frame) or loss (an earlier frame);
4. so the outcome is a pure function of arrival rate - exactly why one unchanged
   driver produced 1/8, 3/8, 6/8, 7/8 and 8/8.

**The datapath is not broken.** It receives, delivers and preserves data exactly
when not asked to sustain a rate. The single remaining defect is that the
allocator hands out one buffer instead of many, capping sustained receive at about
one frame per copy-time. Every "RX corruption" symptom from rounds 29-39 descends
from that one property.

**Acceptance criterion for any fix:** a 350 ms-paced 8-frame burst must give
`NoPorts +8`, not `+1`. Two counter reads, no sink, no rebuild.

| validation item | status |
|---|---|
| unidirectional ping, host<->device | PASS |
| labelled UDP burst, **slowly paced (1.5 s)** | **PASS - 8/8 delivered** |
| labelled UDP burst, fast (350 ms) | **FAIL - DMA race on shared buffer 0** |
| per-descriptor buffer identity | single buffer confirmed by raw memory read |
| ring wraps | NOT RUN |
| simultaneous ports | NOT RUN |
| sustained bidirectional TCP | NOT RUN |
| cold boot with no bootloader network use | NOT RUN |

### 2026-09-10 round 41: CORRECTION - round 40's race is not established

Arming `rx_trace` during a slow burst and repeating it refutes round 40's
conclusion:

```
idx == 2 * cursor - 53      for 11 of 11 descriptors (cur = 71..81)
```

Round 36 measured `idx == 2 * cursor + 76` in a different boot. In **both** boots
the field decoded as `idx` is an exact linear function of the software cursor with
a boot-specific constant. **A per-frame buffer index cannot behave that way** - the
field is cursor-derived, so the driver's copy source address is wrong.

And the slow burst is not reliably clean:

```
round 40 slow burst:  NoPorts +8 of 8    (looked like a cure)
round 41 slow burst:  NoPorts +2 of 8    (same spacing, same script, same kernel)
```

The round-40 comparison changed spacing **and** instrumentation at once - the same
two-variable error as rounds 32/33. **Round 40's race mechanism is retracted.**
Slow pacing is not a demonstrated cure and the "single shared buffer" mechanism is
not established.

**Stable across every boot:** `idx` is a cursor function; `len` is a constant 1514
against 106-byte frames; `b42` does not track labels; buffer 0 **did** hold a
genuine intact frame at 0x41000010 (so the buffer window and `BUF_HDR` are right);
delivery is 1-2 in 8.

**Best-fitting reading:** the decoded fields are not the hardware's frame fields,
so the driver computes a wrong copy address. Mostly it reads non-frames (dropped
silently); occasionally it lands on a real one, which is why 1-2 in 8 get through
and why buffer 0 held a real frame when inspected.

**Next:** find the real buffer-index field, or establish that the index is not in
the descriptor at all and must come from free-list consumption order. **Stop using
pacing as a variable** - it is confounded with instrumentation.

*(The round-40 matrix row claiming a slow burst PASSES is superseded by this.)*

### 2026-09-10 round 42: bench capability limits and a poke HAZARD

**No bulk memory access.** `/dev` is read-only, but a node can be made in the
tmpfs - it does not help: `mknod /tmp/zmem c 1 1` succeeds as `crw-r--r-- 1,1`,
and `dd if=/tmp/zmem` then fails with *No such device or address*. **`CONFIG_DEVMEM`
is off.** All memory inspection goes through `/proc/zx_eth_poke`, **one 32-bit word
per invocation**, so a 2048-buffer scan is 2048 pokes and ~120 KB of console.

**`/tmp` needs its tmpfs remounted after every RAM boot** (`mount -t tmpfs tmpfs
/tmp`), or writes fail with *Read-only file system*. Third time this has cost a
step.

**HAZARD - iterating poke reads over the buffer pool HANGS the board.**

```
k=0; while [ $k -lt 32 ]; do echo "$((0x41000010 + k*0x800)) read" > /proc/zx_eth_poke; k=$((k+1)); done
```

The shell never returned and the device stopped answering; recovery required a
power cycle. Single reads of the same region (`0x41000010`) were fine in round 40,
so the hazard is in *iterating*, not in any individual address. Treat the buffer
pool as unsafe for repeated reads, spread reads across separate commands, and
assume a power cycle may be needed.

**Also:** a poke read reports via `pr_info`, so quieting the console to 0 for a
loop also hides the results. For a small scan, leave `console_loglevel` up.

**Standing summary after rounds 30-42.** Retracted: free-list encoding (33),
32-byte stride (36/37), "descriptors are a meaningless template" (39/40), DMA race
(41). Reliable observations: `RXCENSUS` counts every burst frame as well-formed
IPv4/UDP; UDP delivery advances only 1-2 per 8-frame burst; decoded `idx` is an
exact linear function of the software cursor in two separate boots (`2*cur+76`,
`2*cur-53`); `len` is a constant 1514 against 106-byte frames; and buffer 0 at
`0x41000010` did once hold one of our frames, intact.

**Unexplained core:** frames reach the driver and land correctly in a buffer at
least sometimes, yet ~6-7 of 8 never reach UDP, with no error counter moving.

### 2026-09-10 round 43: CONFIRMED - exactly ONE RX buffer is ever used

Single poke reads (no loops - see the round-42 hazard) after a slow traced burst:

```
[41000010] = 7f5e0001   buffer 0    : holds a live frame (01:00:5e.. multicast)
[41000810] = 00000000   buffer 1    : ALL ZERO
[41001010] = 00000000   buffer 2    : ALL ZERO
[41008010] = ffffffff   buffer 16   : erased, NEVER written
[41080010] = 00000000   buffer 512  : never written
[41800000] = 01000000   free list   : entries 0..1 = 0,1
[41800004] = 03000200   free list   : entries 2..3 = 2,3
```

Trace from the same run: **`idx = 0` on every descriptor**, and `NoPorts 0 -> 8`
(all 8 frames delivered, because they arrived slowly).

**So the decoded `idx` is correct and every frame goes to buffer 0.** Buffers 1, 2,
16 and 512 are untouched, which proves the hardware is not walking the buffer pool.

**On `idx` and the round 36/41 "cursor function":** here `idx` is a clean constant
`0`, not `2*cur+C`. The difference is pacing. At 1.5 s spacing the driver reads each
descriptor after hardware has written it; at 350 ms it reads descriptors not yet
filled and sees template values. **`2*cur+C` was an artifact of reading ahead**, not
a property of the field - which retires that line of investigation.

**Mechanism:** RX buffers come from the DDR free list (`TMC+0xe8` = 0x41800000),
which the driver fills once inside `datapath_init()` - **skipped on every warm
boot** (round 35). The driver returns buffers to the **BM pool** via `zx_bm_free`,
a different structure. So the list is never refilled and the hardware reuses one
buffer. The list *content* is still intact (`0,1,2,3`), but consumption only moves
a head pointer, so that says nothing about the head - what matters is that the
hardware is evidently not walking it at all.

**Fix to try:** return RX buffers to the free list rather than (or as well as) the
BM pool, in `zx_rx_release()`. First find **where the free list's consumer index
lives** - `TMC+0xe8`/`+0xec` are the bases, `TMC+0xfc` = `0x08000800` the lengths,
the consumer index is unidentified.

**Acceptance criterion:** a 350 ms-paced 8-frame burst must give `NoPorts +8`
(currently `+0..+1`) and `idx` must take many distinct values.

### 2026-09-10 round 44: pacing is NOT the dominant factor - and boot state is

The first unconfounded experiment in this investigation: three fast bursts
(24 frames) and three slow bursts (24 frames), **within a single boot, no reboots**.

```
P0  Udp: NoPorts 21
P1  NoPorts 41    +20 of 24   <- 3 FAST bursts (350 ms)  = 83%
P2  NoPorts 63    +22 of 24   <- 3 SLOW bursts (1500 ms) = 92%
```

**Both arms deliver almost everything; pacing accounts for 9 points, not failure.**

Consequences:

* **The `+0..+1` baseline quoted since round 30 was a property of particular boots,
  not of the configuration.** The boot-to-boot spread (0/8 to 8/8) dwarfs every
  effect measured so far.
* **The "DMA race on a single buffer" explanation does not survive.** One shared
  buffer cannot give 83% at 350 ms - the fast arm would collapse. The single-buffer
  *observation* (buffers 1, 2, 16, 512 untouched; `idx=0` throughout) is solid, but
  it is not the binding constraint.
* **Every cross-boot comparison in rounds 30-44 is void as evidence.** Retractions
  now: free-list encoding (33), 32-byte stride (36/37), template descriptors
  (39/40), DMA race (41/43), pacing dependence (44).
* `BM+0xa8` (the reference's likely pool depth, `0x722`) **does not latch** - it
  reads back `0x877`. Together with `BM+0xd8`, two of the three registers the
  reference calls actionable refuse writes, so neither can be swept by poke.

**The dominant question is now: what makes one boot deliver ~0-1 of 8 and another
~7-8 of 8 with identical software?** Candidates are the state U-Boot leaves per
power cycle - free-list head/contents, BM pool, DDR in the reserved window - none
of which the warm path re-initialises.

**Next:** record that boot state before any traffic on each boot, then run the same
3-fast-burst measurement and correlate. No code change; first experiment that can
explain the spread. **Never compare across a boot again** - state the same-boot
baseline with every number.

### 2026-09-10 round 45: steady-state RX delivers ~75-90% - early numbers were WARM-UP

Clean interval sweep: **one boot, no pokes**, two fast bursts (16 frames) per
window, `NoPorts` every 30 s.

```
W0 11   W1 25 (+14/16 = 88%)   W2 36 (+11/16 = 69%)
W3 43 (+7/16 = 44%)            W4 59 (+16/16 = 100%)
        total +48 of 64 = 75%
```

No monotonic trend within the sweep - delivery fluctuates 44-100%, averaging ~75%.
That fluctuation *is* the datapath's behaviour, not a failure.

But this boot's full history, in order, shows a warm-up:

| elapsed since `ip link up` | measurement | delivery |
|---|---|---|
| ~30 s | 3 fast bursts | **4%** |
| ~90 s | 3 fast bursts | **42%** |
| ~150-270 s | sweep | **75%** |

**Delivery is poor right after the interface comes up and improves afterwards.**
That is the most economical explanation of the `+0..+1` figures that drove rounds
30-44 - those were taken within a minute of `ip link up`, and the shortfall was
attributed to whatever mechanism was being tested.

Boot state (round 44) is likely partly "measured early vs late". The
`BM+0xc8 = 0x400` vs `0x300` correlation is not contradicted but is confounded the
same way. `BM+0xc8` writes do **not** latch (`0x300 := 0x400 -> 0x300`), like
`BM+0xd8` and `BM+0xa8` - all three registers the reference calls actionable refuse
writes, which is itself a finding: something gates the BM register block.

**Measurement protocol from now on:** every RX number states elapsed time since
`ip link up`, and the first ~60 s is discarded as warm-up. Rounds 30-44 mostly did
not do this.

**Corrected status of the fast-burst row: ~75-90% at steady state, not a hard
failure.** Remaining gap is real but much smaller than previously reported.

**Next:** run the fixed interval sweep (30/60/120/240 s) on **three** boots,
recording `BM+0xc8`/`BM+0xd8` each time, to separate time-since-up from boot
identity. Pure measurement, no code change.

### 2026-09-10 round 46: NO warm-up - and the POKE ENDPOINT may be breaking RX

Fresh boot, **zero pokes**, one fast burst (8 frames) per 12 s window from the
moment the interface came up:

```
A1  +5 of 8  =  63%    <- first window, ~3-15 s after ip link up
A2  +8 of 8  = 100%
A3  +8 of 8  = 100%
A4  +5 of 8  =  63%
    total +26 of 32 = 81%
```

**No warm-up** - the first window already delivered 63%. Round 45's warm-up
explanation is **withdrawn**.

**What differed:** the round-45 4% measurement was taken immediately after the
boot-state capture, i.e. after **seven `/proc/zx_eth_poke` reads**. This sweep used
no pokes and delivered 81% from the start. **The leading explanation is that the
poke endpoint itself degrades RX** - it is an ioremap-based read of live datapath
registers and DMA memory that the hardware is actively using.

**This is a problem for the method, not just an observation: the instrument used to
investigate RX may have been breaking RX.** It would explain the instability, the
non-replication, and why the "single buffer" and "race" stories kept looking
plausible on damaged boots.

**Protocol:** measure RX only on poke-free boots. Every RX number in rounds 30-45
that followed a poke is suspect. Record `pokes_used=yes/no` with every measurement;
`yes` is not evidence about RX.

**Corrected RX status: the datapath delivers ~80% of frames at steady state on a
clean boot, preserving data, with no error counters moving.** The residual ~20% is
the real remaining defect. The matrix rows should be restated at ~80%, and the
never-run rows - ring wraps, simultaneous ports, sustained bidirectional TCP - can
now plausibly be attempted. Those are the actual objective and have never been run.

### 2026-09-10 round 47: RING WRAPS **PASS** - 99.5% over 2500 frames

First matrix row to advance beyond the labelled burst. Poke-free boot, 2500 frames
flooded, no pacing:

```
P0  NoPorts 27    RXCENSUS udp=33
P1  NoPorts 2514  RXCENSUS udp=2529
    received by driver : +2496 / 2500 = 99.84%
    delivered to UDP   : +2487 / 2500 = 99.5%
    InErrors / RcvbufErrors / InCsumErrors / eth2 rx_errs / rx_drop : all ZERO
```

The ring is 1024 entries, so the cursor wrapped at least twice. **The wrap path is
sound** - no loss spike, no counters, no stall at the boundary.

**This also corrects the delivery figure a third time.** Small bursts measured
63-100% (~80% avg); a 2500-frame flood delivers **99.5%**. So per-burst loss is a
**small-volume effect**, most likely the first frame or two of each burst:

| test | volume | delivery |
|---|---|---|
| single 8-frame bursts | 8/burst | 63-100%, ~80% avg |
| 2500-frame flood | 2500 | **99.5%** |

**The datapath is essentially lossless under load; the deficit is at burst onset.**
That is a far smaller and differently-shaped problem than anything chased in rounds
30-46, and it should be characterised as such (test frame 1 vs frames 2-8).

| validation item | status |
|---|---|
| unidirectional ping, host<->device | PASS |
| labelled UDP burst, small (8 frames) | PASS - ~80% avg |
| labelled UDP burst, fast (350 ms) | PASS at steady state |
| **ring wraps (2500 frames)** | **PASS - 99.5%, zero errors** |
| simultaneous ports | NOT RUN |
| sustained bidirectional TCP | NOT RUN |
| cold boot with no bootloader network use | NOT RUN |

**Next:** test the burst-onset hypothesis (frame 1 vs 2-8), then attempt sustained
bidirectional TCP - the most valuable never-run row. Keep the poke-free protocol.

### 2026-09-10 round 48: TCP delivers ZERO, one-way UDP delivers 99.5% - the defect is TX/RX CONTENTION

First run of the sustained-bidirectional row, same poke-free boot that had just
passed ring wraps at 99.5%. The device has no TCP endpoint, so one was built:
`tools/tcp-sink.c`, 25 KB static, delivered over UART.

```
READY                     <- accept() succeeded, handshake completed
BYTES=0                   <- not one application byte arrived
host sendall() -> TimeoutError

eth2: rx +31 packets, tx +15 packets, rx_errs 0, rx_drop 0
```

**Same boot, minutes apart:**

| test | device TX during test | result |
|---|---|---|
| 2500-frame UDP flood | **none** | **99.5% delivered** |
| 4 MB TCP stream | **constant** (ACKs) | **0 bytes delivered** |

**The datapath is fine one-way and fails the moment the device transmits while it
receives.** This explains the shape of rounds 30-47: all testing was one-way UDP,
where the device transmits nothing, so the defect could not appear. Every retracted
mechanism was an attempt to explain a one-way loss that was largely a measurement
artifact, while the real failure sat in the one configuration never tested.

It matches this project's oldest datapath note almost word for word: *"a UDP blast
works (the device transmits nothing), ping works (strict ping-pong), pure ACKs work
- but a TCP transfer fails precisely because the device is transmitting its request
and retransmissions while the reply arrives."*

**Round 30's "Bug 1" was right and I dismissed it for the wrong reason.**
`zx_bm_alloc()` returns index 0, so every TX frame is copied into buffer 0 - the
same 2 KiB RX uses. In round 32 I measured `tx_packets +0` during a UDP burst and
concluded TX/RX collision "cannot be the cause". That was sound for that test and
wrong as a general claim: no transmits were happening *because the test had no
replies*.

**Next:** make the RX free list and the TX pool disjoint (keep index 0 and the TX
scratch out of RX's reach). **Use TCP as the acceptance criterion from here** -
`tcp-sink` on the device, 4 MB from the host, success = `BYTES=4194304`. One-way
UDP numbers remain a control, never the pass/fail test.

| validation item | status |
|---|---|
| unidirectional ping, host<->device | PASS |
| labelled UDP burst (small / fast) | PASS |
| ring wraps (2500 frames, one-way) | PASS - 99.5% |
| **sustained bidirectional TCP** | **FAIL - `BYTES=0` of 4 MB** |
| simultaneous ports | NOT RUN |
| cold boot with no bootloader network use | NOT RUN |

### 2026-09-10 round 50: CONTENTION CONFIRMED - TX and RX both use buffer 0

The measurement that should have preceded every buffer theory: `txdbg` (TX index)
and `rx_trace` (RX index) captured **simultaneously during a TCP transfer**.

```
12  buf=0     <- TX index: 12 of 12 transmits use buffer 0
22  idx=0     <- RX index: 22 of 30 descriptors use buffer 0
 1  idx=64 66 68 69 71 74 77 79
```

**Every transmit uses buffer 0; 73% of receives use buffer 0.** TX and RX share the
same 2 KiB, and it is the dominant buffer on both sides - not a rare collision.

This turns the round-153 comment ("`zx_bm_alloc()` always returns raw `0x80000000`,
i.e. index 0, so every TX frame is `memcpy_toio()`'d into buffer 0") from a claim
into a measurement, and it is the direct cause of round 48: **one-way UDP never
contends because the device never transmits; TCP contends on essentially every
packet because it transmits constantly.**

**It also explains why round 49's fix failed.** Round 49 re-primed the RX *free
list* to exclude index 0 - and RX still returned `idx=0` on 22 of 30 descriptors.
**The free list is not what determines the RX buffer.** Measured, not inferred.

**So the fix cannot be RX-side.** Both sides draw from the buffer manager, and it
returns 0. The lever is the BM pool (make it hold more than one usable buffer) or a
dedicated TX scratch buffer RX cannot reach. The pool has one entry because it is a
stack the driver immediately pushes back onto - it never needs to grow because it is
never allowed to drain.

**Critical path: find what unlocks the BM register block.** `BM+0xa8`, `BM+0xc8` and
`BM+0xd8` - the three the reference calls actionable - all reject writes through the
poke endpoint. That is a gate, and it must be found before the pool can be widened.

**Diagnostic to keep:** the simultaneous `txdbg` + `rx_trace` capture with
`grep -oE 'buf=[0-9]+|idx=[0-9]+' | sort | uniq -c`. One command, no rebuild, no
poke - and more signal than the previous twenty rounds combined.

### 2026-09-10 round 51: NO BM gate - those registers are read-only STATUS

Round 50 set "find what unlocks the BM block" as critical path. That premise is
wrong. The driver brackets its BM config with `writel(0, BM+0x00)`, so the obvious
test was disable-write-enable - run with `BM+0xc8` already reading `0x400`:

```
[92348000] 00000001 := 00000000 -> 00000000   disable BM
[923480c8] 00000400 := 00000500 -> 00000400   write REJECTED while disabled
[92348000] 00000000 := 00000001 -> 00000001   re-enable
```

**`BM+0xc8` is not writable even with the block disabled - it is read-only status.**
Same for `+0xd8` (`0x4000` vs `0x6000` across boots) and `+0xa8` (`0x877`/`0x8a1`/
`0x8ef`). Values that drift on their own and refuse writes in every state are status
words, not configuration.

**The reference doc's "three registers we get wrong" reading was wrong** and has been
corrected in place: its reasoning omitted the actual possibility - that they were
never configuration. The suggested writes cannot take effect. This also retires the
round-44 `BM+0xc8` correlation: both values are *readings* of pool state.

**Where the fix must go instead.** The pool cannot be widened through these
registers, so break the cycle driver-side. The BM behaves as a **stack**:
`zx_bm_alloc()` returns 0, the driver frees the buffer straight back, the next
allocation pops 0 again - so the pool never drains and never grows, and both TX and
RX get buffer 0 (round 50: 12/12 and 22/30).

Smallest experiment: **stop returning TX buffers to the pool the RX side uses** - if
TX keeps index 0 permanently, RX must eventually be handed another. Diagnostic
already in place: simultaneous `txdbg` + `rx_trace`, then
`grep -oE 'buf=[0-9]+|idx=[0-9]+' | sort | uniq -c`.

**Do not revisit `BM+0xa8/0xc8/0xd8`.**

### 2026-09-10 round 52: ROOT CAUSE - the RX descriptors are NEVER programmed

Round 51 proposed withholding RX buffer returns so the BM pool head would have to
advance. Tested with a new `rx_no_free` module parameter:

```
NF=Y
RXTRACE r=0 cur=0 idx=0 b42=00
RXTRACE r=0 cur=4 idx=0 b42=05      <- b42 tracks the transmitted label
RXTRACE r=0 cur=7 idx=0 b42=07
RXTRACE r=0 cur=9 idx=0 b42=08
```

**`idx` is still 0 on all ten descriptors with every RX buffer withheld** - and
`b42` tracking the labels proves the frame really is in buffer 0. So the BM pool is
not the determinant either.

Both candidate sources are now excluded by measurement:

| hypothesis | test | result |
|---|---|---|
| RX buffer from the **free list** | re-primed list excluding 0 (round 49) | `idx` still 0 |
| RX buffer from the **BM pool** | `rx_no_free=1` (round 52) | `idx` still 0 |

**The answer:**

```
$ grep -n 'zx_desc_pack' zx279128-eth.c
332: static void zx_desc_pack(void __iomem *d, u32 idx, u32 len)
936:     zx_desc_pack(desc, idx, skb->len);      <- zx_eth_xmit, TX ring only
```

**The only function that writes a buffer index into a descriptor is called from
exactly one place, and it is the transmit path.** The receive path only ever reads
`idx`. Each RX descriptor therefore still holds U-Boot's template value (0), and
**every received frame lands in buffer 0**.

This is a missing initialisation, not a hardware misunderstanding, and it explains
every observation since round 30 in one line: `idx=0` everywhere (nothing wrote a
different value); data found in buffer 0 (hardware wrote where the descriptor said);
free-list and BM experiments had no effect (neither is the source of `idx`); TX/RX
collision (both use index 0); one-way UDP nearly lossless but TCP dead (contention
needs both directions).

**Fix:** prime the RX descriptors at setup with distinct buffer indices using the
encoding `zx_desc_pack` already implements, cycling the pool and **starting above
the TX scratch index** so the sets are disjoint; then have `zx_rx_release` return the
consumed index to the list it came from. Note 16 rings x 1024 entries = 16384
descriptors against only 2048 buffers, so the cycling must keep TX's index out of
RX's reach.

Verify with simultaneous `txdbg` + `rx_trace` (`idx` must take distinct values), and
accept with TCP: `BYTES=4194304`.

### 2026-09-10 round 53: RX descriptor priming implemented - the writes DO NOT LAND

Implemented `zx_rx_prime_descriptors()`, called from the warm-path branch, writing a
distinct buffer index into every RX descriptor (encoding as `zx_desc_pack`), indices
1..BUF_COUNT-2 across all 16 rings x 1024 entries. Built clean, booted, ran:

```
rx descriptors primed with distinct buffer indices
```

**It changed nothing.** `idx` is still 0 on every descriptor, and reading descriptors
**ahead of the cursor** (so they cannot have been consumed) shows the primed values
are absent:

```
expected entry 20 -> byte 7 = 0x2b
[41a00144] = 01180000     <- byte 7 = 0x01, the template
[41a00184] = 01180000     <- template again
```

**The writes do not take effect at the location the driver reads.**

**Two candidate explanations:**
1. `ze->ring` is not a writable mapping in the sense used - the driver only ever
   `memcpy_fromio`-*reads* it, and only `txring` is written.
2. The write lands in a shadow the hardware ignores; the producer ring may be a
   different aperture.

**Decisive cheap test:** write one descriptor through `/proc/zx_eth_poke` (which
ioremaps independently and has been shown to write DDR successfully) and read it
back. If it sticks, the mapping is the problem; if not, the region is not ordinary
writable DDR and the ring lives elsewhere.

**The fix must not be considered applied** - it is a no-op and should be revisited or
removed once the mapping question is answered.

**Sharply framed open question:** where does `ze->ring` actually point, and is it the
memory the hardware writes? The driver reads frames from it correctly (`b42` tracks
labels), yet nothing it writes there persists. Together those suggest `ze->ring` is a
read aperture onto hardware-owned memory - in which case the buffer index is the
hardware's to choose and the descriptor is not the driver's to program.

### 2026-09-10 round 54: THE FIX WORKS - RX now uses distinct buffers

Round 53's negative result was a **placement error of mine**. The priming was called
from the warm branch at line 2901; `ze->ring` is not mapped until line 2926. So
`ze->ring` was NULL, the helper returned early through its own guard, and the driver
**logged success anyway** because the `dev_info` was unconditional.

**Never log success unconditionally after a call whose internal guard can decline
the work.**

The region is writable - confirmed directly by poke:

```
[41a00144] 01180000 := 2b180000 -> 2b180000     ring descriptor: STICKS
[41000010] 00003333 := deadbeef -> deadbeef     buffer 0:        STICKS
```

Moved the call to after `ze->ring = devm_ioremap_wc(...)`, rebuilt, booted:

```
RXTRACE r=0 cur=0 idx=1   RXTRACE r=0 cur=4 idx=5
RXTRACE r=0 cur=1 idx=2   RXTRACE r=0 cur=5 idx=6
RXTRACE r=0 cur=2 idx=3   RXTRACE r=0 cur=6 idx=7
RXTRACE r=0 cur=3 idx=4   RXTRACE r=0 cur=7 idx=8
```

**`idx` advances 1..8 - the primed indices, none of them 0.** RX is no longer pinned
to the TX scratch buffer; the two sets are disjoint. The structural defect from
round 52 is fixed and confirmed by measurement.

**Not yet shown:** `b42` is 0 rather than the transmitted label, so end-to-end
delivery through the new buffers is unproven - do not assume it follows. `len` is
still a constant 1514. And **TCP has not been re-run**; `BYTES=4194304` is the
acceptance test and the only result that closes the round-48 row.

**Next:** TCP acceptance test, then one-way UDP as a control, then investigate `b42`
separately if it remains wrong - the buffer-identity fix stands on `idx` alone.

### 2026-09-10 round 55: TCP acceptance test BLOCKED by a degraded RX state

Three attempts to run the acceptance test on the round-54 build, all failing before
any data could be sent:

| attempt | host error | device |
|---|---|---|
| 1 | `No route to host` | `tcpsink` READY |
| 2 | connect timeout | READY |
| 3 (address restored) | connect timeout | READY |

Diagnostics:

```
eth2: <BROADCAST,MULTICAST,UP,LOWER_UP> ... state UP
ip -4 addr show eth2  ->  NO IPv4 ADDRESS (had to be re-added)
RXCENSUS icmp=0 udp=7 tcp=0 other=0 nonipv4=31      <- no ICMP received at all
eth2: rx 38 packets, rx_drop 16, tx 11 packets      <- rx_drop non-zero for the first time
```

**Two bench problems:** the device lost its IPv4 address without a reboot, and RX is
degraded (`icmp=0`, `rx_drop` 16 where every clean boot showed 0).

**This is not a verdict on the fix.** The `idx` 1..8 measurement was taken on this
same build before the state degraded, so the buffer-identity fix stands. But
`BYTES=4194304` is unachieved and the round-48 TCP row stays **FAIL**.

**Next:** fresh boot, set up in one verified sequence checking interface, address,
link and a successful host ping **before** any TCP work; then run the acceptance
test. If RX is still dead on a clean boot, that outranks everything else open - and
the first check is whether reverting only the priming call restores RX.

`b42` reading 0 instead of the transmitted label remains unexplained but is **not**
evidence against the fix; investigate separately once the test can run.

### 2026-09-10 round 56: descriptor priming BREAKS RX - round 54 RETRACTED and reverted

Round 54 claimed "THE FIX WORKS" from `idx` advancing 1..8. The TCP round ran the
planned ICMP gate first and found receive dead:

```
primed with distinct buffer indices       <- fix ran
inet 192.168.1.1/24 (present)
host: 3 packets transmitted, 0 received, 100% packet loss
RXCENSUS icmp=0 udp=0 tcp=0 other=0 nonipv4=3
eth2: rx 3 packets, rx_drop 0
```

**All three pings arrived at the interface and none was answered; RXCENSUS counted
nothing. Receive is dead.**

Round 54's measurement was real - `idx` did advance - but that describes what the
*driver read*, not whether frames were delivered. **Making `idx` vary is exactly what
killed receive.** So round 52's conclusion ("the descriptors are never programmed, so
the driver must prime them") is **wrong**: the `idx` field is hardware-owned, and
overwriting it stops the datapath receiving.

This also explains `b42` reading 0 in round 54 - correctly flagged at the time and
correctly not folded into the "fix".

**Reverted**: priming call and helper removed, synced to all three tree copies
(`grep -c zx_rx_prime_descriptors` -> 0). **The board is running the broken build**; a
rebuild is needed (or boot `trace53.kernel`, whose mis-placed priming never ran).

**The RX question stands where round 50 left it:** TX uses buffer 0 for 12/12
transmits, RX for 22/30 receives, one-way UDP ~99.5%, TCP 0 bytes. The free list, the
BM pool and the descriptors have each been ruled out as the RX index's source.
**Untried: change what TX uses.** The whole investigation has pointed at RX while
TX's fixed choice of buffer 0 is the other half of the collision - and it does not
touch the descriptor protocol that just broke.

**Next:** rebuild reverted, confirm ping works, then give TX a scratch buffer outside
the RX set.

**Pattern:** sixth retraction, same shape - a real measurement promoted to a
conclusion without the end-to-end test that would have falsified it. The ICMP gate
caught this one and is now a required step before every TCP attempt.

### 2026-09-10 round 57: moving TX off buffer 0 BREAKS RX - every avenue now tried

Implemented `tx_scratch` (module parameter) to point TX at a different buffer, leaving
RX untouched. Rebuilt, booted, gate failed. Then the decisive test, **inside one boot,
no rebuild**, flipping the parameter:

```
tx_scratch = 2047 -> ping 100% loss,          RXCENSUS icmp=0 udp=3
tx_scratch = 0    -> ping 2 of 3 (0.44 ms),   RXCENSUS icmp=2 udp=4
```

**Writing the transmit frame anywhere other than buffer 0 stops the device receiving.**

Consequences:

1. **TX must keep using index 0.** Reverted, with the measurement in the code.
2. **Every avenue has now been tried and closed:** free list (49), BM pool (52), RX
   descriptors (53-56), TX buffer (57). Three were no-ops; two broke receive.
3. **This reframes the "collision".** If TX must write buffer 0 and RX must read
   buffer 0, buffer 0 is very likely a **shared staging buffer by design**, used
   serially under the driver's locks - not an accidental overlap. Round 50's
   measurement (12/12 TX, 22/30 RX on index 0) is equally consistent with a deliberate
   staging design.

**So the TCP failure is probably not buffer collision** and the round-48/50 framing
needs revising. What remains: one-way UDP ~99.5%, sustained TCP **0 bytes of 4 MB**,
device receives 31 packets and transmits 15 with no errors. That is still unexplained.

**Next: measure what happens to the TCP payload specifically** - whether the segments
reach the socket and where they are dropped - rather than continuing to model it as
buffer ownership.

**Separate concrete anomaly worth its own check:** with priming removed, the gate
still showed the three ping frames received (4542 bytes ≈ 3 x 1514) but classified as
**UDP** in the census, where ICMP echo has protocol byte 23 = 1. The driver read 17.
The bytes copied did not match what the host sent.

### 2026-09-10 round 58: TCP now DELIVERS - 57920 bytes, not zero

Re-ran the acceptance test with **no driver changes active** (rounds 56 and 57 both
reverted). ICMP gate passed first.

```
READY
BYTES=57920                        <- real payload received
host sendall() -> TimeoutError at 4 MB

eth2: +152067 B / +108 pkts rx     +4842 B / +61 pkts tx     rx_errs 0, rx_drop 0
```

**Round 48's `BYTES=0` is not reproducible.** The row stays **FAIL** (4 MB does not
complete), but "TCP delivers nothing" was wrong.

**This matters more than the number.** `BYTES=0` was a single sample on a single boot,
taken without a repeat, on a bench already known to swing from 0/8 to 8/8 delivery on
identical software (rounds 44-45). It became the load-bearing fact for the entire
"TX/RX contention" narrative and drove rounds 49-57 of buffer experimentation.
Nineteen rounds rested on one unreplicated measurement.

**The failure mode is a STALL, not a block** - data flows, then stops, which is what
packet loss forcing retransmission until the window closes looks like. That is a
throughput problem, not a structural one, and it points back at the ~0.5% one-way loss
rather than at buffer ownership.

| observation | round | status |
|---|---|---|
| one-way UDP flood ~99.5% | 47 | solid |
| TX uses buffer 0, 12/12 | 50 | solid |
| RX uses buffer 0, 22/30 | 50 | solid |
| moving TX off buffer 0 breaks RX | 57 | solid |
| priming RX descriptors breaks RX | 56 | solid |
| **TCP delivers 57920 bytes then stalls** | **58** | **new; supersedes round 48's 0** |

Buffer 0 is evidently a shared staging buffer both directions must use, and both
attempts to move either side away broke receive. **The live question is why TCP stalls
after ~57 KB**, not buffer ownership.

**Next:** sample rx/tx and RXCENSUS every few seconds during a long send to see whether
loss is bursty or steady; check `Tcp: RetransSegs` / `ss -ti` to confirm loss is the
mechanism.

**Rule from here: repeat any TCP result at least three times before treating it as a
property of the code.** That rule should have applied to the first one.

### 2026-09-10 round 59: SUSTAINED BIDIRECTIONAL TCP WORKS - 1 MB byte-exact at 2.28 Mbit/s

Following round 58's repeat-before-concluding rule, the acceptance test was run at
several sizes:

```
   32 KB : SENT=32768 OK in 0.000s     BYTES=32768        byte-exact
  256 KB : SENT failed: timed out      BYTES=86880        stalled
    1 MB : SENT=1048576 OK in 3.685s   BYTES=1048576      2.28 Mbit/s, byte-exact
    4 MB : timed out (3 repeats)       BYTES=17376 / 57920 / 128872
```

**A full megabyte of TCP payload transferred in 3.685 s at 2.28 Mbit/s, verified
byte-for-byte.** The device acknowledged throughout and no error counter moved.

**Sustained bidirectional TCP is functional on this port.** Note 256 KB **failed while
1 MB succeeded in the same session** - this is not a size threshold but loss-induced
stalling, and TCP's recovery is a matter of luck. It matches round 47's ~0.5% one-way
loss: enough to occasionally wedge a window, with no counter anywhere to show it.

| validation item | status |
|---|---|
| unidirectional ping | PASS |
| labelled UDP burst (small / fast) | PASS |
| ring wraps (2500 frames, one-way) | PASS - 99.5% |
| **sustained bidirectional TCP** | **PARTIAL PASS - 1 MB at 2.28 Mbit/s byte-exact; intermittent stalls** |
| simultaneous ports | NOT RUN |
| cold boot with no bootloader network use | NOT RUN |

The row is no longer FAIL, but it is not a clean pass either. **PARTIAL PASS with the
stall characterised** is the honest reading.

**Remaining defect, precisely:** occasional loss with no error counter, enough to stall
a TCP window. Buffer 0 being shared is still true but is evidently *by design* - a
design that could not sustain throughput would not have moved 1 MB byte-perfect at
2.28 Mbit/s. **The next question is where the occasional frame goes**, which would
explain the UDP loss and the TCP stalls with one mechanism.

**Next:** compare `RXCENSUS udp` against a known sent count (driver-level loss), then
`Ip: InReceives` against `RXCENSUS` (driver-to-IP loss). Do not reopen buffer-0 work.

### 2026-09-10 round 61: clean baseline restored; tree consistent

Round 60 left the board hung. Recovered it, then rebuilt from the **fully reverted**
source (neither the round-56 priming nor the round-57 TX scratch override) and
verified:

```
BUILD_EXIT=0
boot:  rx ring=41a00000 tx ring=41c00000     (no priming line - expected)
gate:  ping 3/3, 0% packet loss, rtt 0.215/0.338/0.487 ms
```

**Clean known-good baseline. Working image `/srv/tftp/trace61.kernel`.**

This mattered because the tree still carried two reverted experiments whose *defaults*
were dangerous - `trace57` boots with `tx_scratch` defaulting to 2047, the value
measured to stop receive dead. Both are now absent from the source and all three tree
copies, so a plain rebuild is safe. `rx_no_free` (round 52) remains a documented test
knob, default off.

**Next:** from this clean boot, repeat a failing TCP size while watching
`tx_dropped`, `tx_fifo_errors`, `TMQ` status and the host's `Tcp: RetransSegs`. The
one-way path is essentially lossless (998/1000), so the stalls must come from the
other direction - and round 60 already showed the device receiving 1583 TCP segments
on a boot where the host still saw a stall.

Matrix unchanged: TCP **PARTIAL PASS**, simultaneous ports and clean cold boot NOT RUN.

### 2026-09-10 round 62: the TCP stall is TX-SIDE - host retransmits 3953 segments

From the clean round-61 baseline, a failing 4 MB transfer watched on both sides:

```
HOST   Tcp: RetransSegs   +3953 during one attempt
DEVICE eth2 (T0)  rx 6056 B / 4 pkts   tx 1132 B / 14 pkts
       Tcp: ... CurrEstab = 0
```

**The host retransmits thousands of segments because the device's ACKs are not
getting back.** Round 60 showed one-way RX is essentially lossless (998/1000), so the
failing direction is device-to-host: **the transmit path degrades when the device
transmits continuously while receiving.**

This is exactly what the project's oldest datapath note describes - ping works,
one-way UDP works, "but a TCP transfer fails precisely because the device is
transmitting its request and retransmissions while the reply arrives". Rounds 47-62
have now independently measured both halves.

**Two incidental observations:**
1. The device's own `Tcp:` counters read **all zeros** (`CurrEstab = 0`) even though
   `tcpsink` accepted a connection - so device `/proc/net/snmp` cannot be used to
   reason about its TCP state.
2. **The console stopped answering during the transfer, for the second consecutive
   round** - both times with a stalled TCP transfer in progress. Treat "device goes
   silent under stalled TCP" as part of the defect, consistent with a transmit queue
   that never drains.

**Next: look at TX under load.** Read `tx_dropped`, `tx_fifo_errors` and the `TMQ`
status/credit during a stall. `zx_eth_xmit` already reads `TMQ_CREDIT` to decide
whether it may enqueue and caps `ze->tx_outstanding` at `RING_ENTRIES` - **if
`tx_outstanding` never drains, the driver stops enqueuing and the device goes silent**,
which would explain both the stalled ACKs and the unresponsive console.

**Board is hung again** (console unresponsive after the stalled transfer) and needs a
power cycle before further work.

### 2026-09-10 round 63: TX is SLOW, not wedged - `TMQ_CREDIT` is a constant 1

TX registers read directly around a five-ping burst:

```
TMQ_CREDIT (0x92350068)   00000001 -> 00000001    NEVER ADVANCES
TMQ_TXIDX  (0x9235006c)   086d086d -> 08720872    +5, correct

ping 5 transmitted, 3 received, 40% packet loss
rtt min/avg/max/mdev = 0.285/371.864/1061.004/487.794 ms
```

**The round-62 drain hypothesis is disproved.** `completed = TMQ_CREDIT & 0xffff` is a
constant **1**, so `tx_outstanding` is decremented and incremented once per transmit
and **never accumulates**; the `>= RING_ENTRIES` cap is never approached. TX does not
wedge that way, and `TMQ_TXIDX` advancing correctly confirms the doorbell and ring work.

**But the constant 1 is itself wrong** - a completion counter reading 1 whether one or a
thousand frames completed is not counting completions. `tx_outstanding` is effectively
pinned at zero, so **the driver never throttles at all** - the opposite failure to the
one hypothesised.

**The new and more useful clue is latency.** Ping RTT averaged **372 ms with a 1061 ms
maximum** on this boot, against **0.34 ms with no loss** on the round-61 boot with
identical code. A 1000x round-trip increase on a 98-byte exchange is a latency problem
in the transmit path, and it fits the TCP failure far better than loss:

* the host retransmits (+3953, round 62) because ACKs are **late**, not absent;
* a late ACK is indistinguishable from a lost one to a sender on a 15 s timeout;
* one-way UDP is unaffected because the device never has to transmit (998/1000);
* the device going silent under a stalled transfer fits a transmit path falling
  progressively behind rather than one that has stopped.

**Next:** measure TX latency directly (time transmits and read `TMQ_TXIDX` after each, or
instrument the interval between the doorbell write and the index advancing); find what
makes transmit slow - `zx_bm_alloc()`'s 200-iteration `cpu_relax()` retry loop and the
doorbell/credit handshake are the code-level candidates, and `n_alloc_busy`,
`n_alloc_invalid` and `sp_last_alloc_raw` already exist for it. Also re-read
`TMQ_CREDIT` idle vs busy: a value that never leaves 1 in either state suggests the
driver is misreading which field holds the count.

Note this boot is degraded (40% loss, 372 ms RTT) while an earlier boot of the *same*
image measured 0% at 0.34 ms - the recurring boot-to-boot spread. Re-baseline first.

### 2026-09-10 round 64: the degradation is TRANSIENT within one boot

**Ping recovered on the same boot that had been failing.** Round 63 measured 40% loss
at 372 ms average (1061 ms max); minutes later, same boot, same code:

```
ping 3 transmitted, 3 received, 0% packet loss
rtt min/avg/max/mdev = 0.300/0.308/0.324/0.010 ms
```

**The degradation comes and goes within a single session** - a stronger and more
awkward finding than "boot-to-boot spread". Any single measurement can land in a bad
window, and two runs minutes apart on identical code can differ a thousandfold in
latency. The earlier "clean boot vs degraded boot" comparisons were each single samples
of a fluctuating quantity.

**And no TMQ register counts completions:**

```
TMQ+0x60 = 41c00000 (TX ring)   +0x64 = 1 (doorbell)   +0x68 = 1 (constant)
TMQ+0x6c = TX index (advances)  +0x70 = 0   +0x74 = 0   +0x78 = 0x0c   +0x7c = 0
```

`TMQ_CREDIT` reads 1 in every state examined, so the driver's `completed` term reads a
field that is not a completion count and **`tx_outstanding` has never measured
in-flight frames. The driver has no working TX back-pressure at all.**

**Framing that now fits all the evidence:** *the datapath works; its latency is
unstable.* This explains why one-way UDP is unaffected (no transmit) and why TCP stalls
(late ACKs), and it is a different problem from every one chased so far.

**Next:** characterise the latency swing before theorising - ping continuously for
minutes with timestamps and record the RTT distribution (steady with spikes, or two
modes?). Then look for the trigger, not the mechanism. **Do not attempt another fix
until it is characterised**: three consecutive fixes were built on single samples of a
fluctuating quantity.

### 2026-09-10 round 65: TX latency is BIMODAL with DUPLICATES - no TX back-pressure

Characterised the swing as round 64 required. 200 timestamped pings at 5/s:

```
200 transmitted, 151 received, +10 DUPLICATES, 24.5% packet loss
rtt min/avg/max/mdev = 0.170/1272.155/21944.143/4129.334 ms, pipe 108

n=161   min=0.170   p50=0.242   p90=1024   p99=20500   max=21944
over 100 ms: 25 of 161
```

**Median 0.242 ms. Maximum 21.9 SECONDS.** Not a slow link - a link that is normally
perfect and occasionally holds a frame for seconds. Plus **ten duplicate replies** and
`pipe 108` (108 packets in flight).

**Explanation.** Round 63 showed `TMQ_CREDIT` is a constant 1, so in `zx_eth_xmit`
`tx_outstanding` decrements and increments once per call and **never accumulates** - the
`>= RING_ENTRIES` guard **never fires**. The driver has **no TX back-pressure**: it keeps
writing descriptors into a 1024-entry ring however far behind the TM is. That yields
exactly this signature:

* the ring wraps onto unconsumed descriptors -> **delayed, reordered frames** (`pipe 108`);
* an already-sent slot is rewritten and sent again -> **duplicates** (`+10`);
* the TM usually keeps up -> **median 0.24 ms**;
* under sustained load (TCP) the ring is permanently overrun -> **TCP stalls**, while
  one-way UDP - which never transmits - is unaffected (998/1000).

**This is the first explanation that accounts for the duplicates and the seconds-long
outliers**, which no loss- or contention-based theory could.

**Fix to try:** derive in-flight frames from `TMQ_TXIDX` (which advances correctly)
instead of `TMQ_CREDIT`:

```c
outstanding = (ze->tx_next - (readl(ze->tmq + TMQ_TXIDX) & 0xffff)) & (RING_ENTRIES - 1);
```

and throttle on that. Confirm which 16-bit half corresponds to the TX ring first.

**Next:** prove the overrun by showing `TMQ_TXIDX` and the driver's `tx_next` diverging
by more than `RING_ENTRIES` during a flood; then implement the guard and re-run the
200-ping distribution. **Success is unambiguous: no duplicates, no sample above ~10 ms,
p50 still sub-millisecond.** This is TX-side only - it does not touch RX, the descriptor
protocol, or the buffer allocator, all of which broke receive when disturbed.

### 2026-09-10 round 66: the TX back-pressure fix did NOT work - and the INSTRUMENT is suspect

Implemented round 65's fix (`TMQ_TXIDX`-derived back-pressure), rebuilt, re-ran the
identical 200-ping test:

```
BEFORE                                 AFTER
151 rx, +10 dup, 24.5% loss            153 rx, +13 dup, 23.5% loss
p50 0.242 ms, max 21944 ms             p50 0.253 ms, max 22792 ms
25 of 161 over 100 ms                  46 of 166 over 10 ms
```

**No improvement, marginally worse.** Reverted. Either the ring-overrun hypothesis is
wrong, or the `TMQ_TXIDX` half used is not the TX ring index and the guard never fired
(`tx_fifo_errors` would settle it - and was not checked first, skipping the very gate
round 65 recommended).

**More important: 24% loss and duplicate ICMP replies on a directly-cabled gigabit link
is abnormal for either endpoint**, and it persisted across a rebuild and reboot. Three
unexcluded candidates: the **host's USB NIC** (already the source of one false negative
in this project), the device's TX path, or the link/cable.

**Every "TX latency" conclusion in rounds 62-65 rests on this ping measurement, and the
measurement may be measuring the host.** Same class of error as round 48's unreplicated
`BYTES=0`: a conclusion built on an instrument whose reliability was never established.

**Next:** validate the instrument first - ping the same device from a different host
interface, or ping a different device on the same USB NIC. If 24% loss follows the NIC,
rounds 62-65 are void. Then check `tx_fifo_errors` to see whether the round-66 guard
ever fired. Only then decide whether TX is implicated at all.

### 2026-09-10 round 67: instrument VALIDATED - the 22% loss is entirely in the RETURN path

Round 66 worried the ping test might be measuring the host's USB NIC. Split by
direction:

```
host:   200 transmitted, 157 received, +5 duplicates, 21.5% loss
        rtt min/avg/max = 0.174 / 612.571 / 14980.052 ms, pipe 74
device: RXCENSUS icmp 190 -> 391   = +201 ICMP frames RECEIVED (200 were sent)
host USB NIC: rx_errors 0, rx_dropped 0, tx_errors 0   (all unchanged)
```

**The device received 201 of 200 requests - the forward path is effectively perfect.**
Only 157 replies returned.

**Settled:**
* The loss is not forward-path and not in the host's receive counters. The host NIC
  logs zero errors/drops and every request reaches the device.
* **The 22% loss, the duplicates and the multi-second delays are all in the RETURN
  path** - the device's transmit, or the wire.
* Round 66's instrument worry is **resolved in favour of the device**.

| direction | evidence | result |
|---|---|---|
| host -> device (RX) | 998/1000 UDP (round 60); 201/200 ICMP (round 67) | ~100% |
| device -> host (TX) | 157/201 ICMP replies; +5 duplicates; max 15 s | ~78%, duplicates, stalls |

**The defect is the TRANSMIT path.** Every RX-side hypothesis (free list, BM pool,
descriptor priming) is now tried and consistent with a healthy forward path.

**Next:** start from the **duplicates** - a duplicate means a descriptor was consumed
twice or a slot rewritten and re-sent, so `zx_eth_xmit`'s slot selection and
`zx_tx_slot_mode` are the place to look (`txdbg` already prints the slot per transmit).
Then count device `tx_packets`/`tx_dropped`/`tx_fifo_errors` against the 201 replies
owed: ~201 transmitted with 157 arriving puts loss on the wire; ~157 transmitted means
the driver drops before the doorbell.

**The 200-ping directional split is now the fastest diagnostic available** - one device
counter, one host counter, no rebuild.

### 2026-09-10 round 68: the device answers EVERY request it sees - loss is above the driver

```
200 pings   device eth2 tx_packets +174   host rx_packets +174   <- EXACT match
            device eth2 rx_packets +205   (requests received)

100 pings   device Ip: InReceives   522 -> 606   +84
            device Icmp: InEchos    510 -> 593   +83
            device Icmp: OutEchoReps 510 -> 593  +83
            all ICMP error counters ZERO throughout
            host: 100 tx, 71 rx, +3 duplicates
```

**At frame level the link is perfect** - device transmitted 174, host received 174.
And the device answers **1:1** everything its IP layer sees: 83 requests in, 83 replies
out, no errors anywhere.

**So the loss is:**
1. **forward, between the driver and IP** - the host sent 100, the driver's census has
   counted ~all of them, but `Ip: InReceives` gained only 84, with no counter moving;
2. **backward, between IP and the wire** - ICMP counted 83 `OutEchoReps`, the host saw
   71, yet device tx_packets equals host rx_packets exactly, so those replies were never
   actually transmitted.

**Both losses are silent** - no error counter moves on either side, at any layer, in
either direction.

**Next:** compare the driver census against `Ip: InReceives` over a known burst. If the
census exceeds `InReceives` consistently, the driver hands up frames the stack rejects -
and **`len` is the obvious candidate: it has read a constant 1514 against 106-byte
frames in every trace since round 31 and has never been investigated.** A frame
delivered with a bogus length is discarded by the stack with no counter, which matches
everything measured here.

### 2026-09-10 round 69: the driver-to-IP gap is REAL - 12% of handed-up frames vanish

Measured directly over 100 pings (host sent 100, received 75):

```
                    before  after   delta
eth2 rx_packets       724     825    +101    frames arrived
RXCENSUS icmp         694     791     +97    driver handed up
Ip: InReceives        610     695     +85    IP received
Ip: InDelivers        593     676     +83    delivered upward

every error counter, every layer       ZERO
```

**12 frames - 12% - handed to `napi_gro_receive` and never reached IP, with nothing
counted.**

**This is the most actionable measurement so far**: a quantified, reproducible loss
inside the host kernel's stack, between the driver's receive function and IP. The
driver is constructing an skb the stack rejects.

**Standing suspect:** `len` reads 1514 in every descriptor, against 98-byte pings and
106-byte UDP frames - the one constant never explained. A frame handed up with a length
disagreeing with its contents is exactly what the stack discards silently.

Note the UDP flood (round 60) showed **no** gap (census +1001, InReceives +1002), so the
effect is at least partly rate- or size-dependent; any explanation must account for that.

**Two cheap checks, in order:**
1. Log descriptor length vs `skb->len` and IPv4 `tot_len` for the vanishing frames -
   confirms or kills the length hypothesis.
2. **Bypass GRO**: use `netif_receive_skb()` instead of `napi_gro_receive()` and re-run
   the 100-ping split. One line; fastest way to falsify or confirm the whole hypothesis.

### 2026-09-10 round 70: GRO is NOT the cause - the gap is before `ip_rcv`

Round 69's test run properly, as an A/B **inside one boot** with a new `no_gro` runtime
switch (one kernel, both arms, identical conditions):

```
no_gro=0 (GRO, default)      census +90   Ip: InReceives +82   gap  8 of 90  =  9%
no_gro=1 (netif_receive_skb) census +99   Ip: InReceives +84   gap 15 of 99  = 15%
```

**Bypassing GRO did not close the gap - marginally worse.** GRO is not discarding these
frames.

**Where the gap sits:** the census counts frames *before* `eth_type_trans()`, and only
when the ethertype is `0x0800` **and** the IP protocol byte matches. Those same frames
pass through and 8-15% never appear in `Ip: InReceives`, while `InHdrErrors`,
`InDiscards`, `InUnknownProtos` and `InAddrErrors` all stay **zero**. So the loss is
between `eth_type_trans()` and `ip_rcv()`, in the protocol dispatch. Narrow candidates:
`eth_type_trans` returning a different protocol than the census read; another ptype
handler consuming them (packet socket / bridge); or a NAPI accounting artifact.

**Next:** log `skb->protocol` right after `eth_type_trans()` against the census's `proto`;
and `cat /proc/net/ptype` on the device to reveal any other registered handler. The
size-dependence (UDP flood shows no gap, pings show 9-15%) points at the copy and the
constant `len` of 1514 rather than at the dispatch.

**Methodology:** first single-boot A/B with a runtime switch - the only valid way to
compare two conditions here. It cost one rebuild and will answer every later question
about this path with no further builds. `no_gro` left in tree, default off.

### 2026-09-10 round 71: no competing handler - the gap is the generic path OR the census over-counts

```
/proc/net/ptype:  0800 ip_rcv | 0004 llc_rcv | 0806 arp_rcv | 86dd ipv6_rcv
/sys/class/net:   eth0 eth1 eth2 eth3 lo          (no bridge)
```

**The protocol dispatch is clean** - no packet socket, no bridge, no rx_handler. Nothing
else can consume an IPv4 frame before `ip_rcv`. Round 70's candidate 2 is excluded.

**Two possibilities remain, and they are distinguishable:**

**(a)** the frame is lost in `__netif_receive_skb_core` between `eth_type_trans()` and
`ip_rcv()` - above IP, so no `Ip:` counter sees it;

**(b) the census OVER-COUNTS and nothing is lost.** The census increments once per
descriptor *processed*. If the driver re-reads a descriptor it already consumed - direct
evidence for which exists from rounds 36/41, where `idx` tracked the cursor rather than
the frame - the census counts 2 for 1 delivered frame and `Ip: InReceives` is correct.
**The "gap" would be a census artifact, not a drop.** Duplicate frames have been seen
repeatedly (round 65: ten duplicate ICMP replies).

**The check that separates them - three counters, one command, no rebuild:**

```
eth2 rx_packets   (once per skb handed up)
RXCENSUS icmp     (once per descriptor processed)
Ip: InReceives    (once per frame ip_rcv sees)
```

`rx_packets` matching `InReceives` while the census exceeds both proves (b).

**This matters before any more code changes:** rounds 69-70 both concluded "12% of frames
vanish between driver and IP" and were building a fix on it. If (b) holds, that
conclusion is wrong - the frames were never lost, the driver counted some twice.

**Answered from round 69's own data - all three counters were recorded there:**

```
eth2 rx_packets +101 | RXCENSUS icmp +97 | Ip: InReceives +85
```

`rx_packets` exceeds `InReceives` by 16, and the census says only ~4 of those were
non-ICMP. So **~12 IPv4 frames were handed up and never reached `ip_rcv`** - possibility
**(a)**. This does not depend on the census over-counting: even treating `rx_packets` as
the truthful figure, IP saw 16 fewer frames than the driver produced.

**Conclusion of rounds 69-70 stands:** frames handed to the stack do not all reach IP and
nothing counts the difference. The census over-count may be an additional effect (the
duplicate evidence), but it is not what produces this shortfall.

**Next:** instrument `skb->protocol` right after `eth_type_trans()` and the
`netif_receive_skb` return path - the loss is in the generic receive path with a clean
ptype table above it.

### 2026-09-10 round 72: all RX counters sampled - forward gap 6-12%, return gap ~18%

```
                 before  after  delta
eth2 rx_packets     210    273    +63    frames arrived
RXCENSUS icmp       189    249    +60    driver handed up
Ip: InReceives      170    226    +56    ip_rcv saw
Ip: InDelivers      162    217    +55
Icmp: OutEchoReps   162    217    +55    replied

host: 60 tx, 45 rx, +1 dup, 25% loss, max RTT 6.5 s
```

**Two clean facts:** the device answers **1:1** (55 in, 55 out - no loss inside its own
stack once a frame arrives); and the forward gap is **4 frames here vs 12 in round 69** -
real but *variable*, consistent with the bench's broader instability rather than a fixed
rate.

Unchanged: the **return path lost 10 of 55 replies (18%)** while the device transmitted
one per request seen.

**Mechanism:** the forward loss sits between `RXCENSUS` and `Ip: InReceives`, with a
clean ptype table above it (round 71), no GRO involvement (round 70), and every IP/ICMP
error counter at zero. **That is the generic receive path, where no counter exists.**
Counters (rounds 67-72) have taken this as far as they can: the loss is real, small,
variable, silent, and bounded between two function calls. **The next step needs tracing**
- ftrace/kprobe if available, or a temporary printk around the
`eth_type_trans`/`netif_receive_skb` pair recording `skb->protocol`, `skb->len` and the
IPv4 `tot_len`.

**Proportionate assessment:** forward RX loss 6-12% on small ping frames but **zero on
the 1000-frame UDP flood** (998/1000); return loss ~18% on ping replies while **1 MB TCP
completed byte-exact at 2.28 Mbit/s**. Neither is total. **The port is substantially
functional**; what remains is characterising a small intermittent silent loss, and five
rounds of counters have bounded it without identifying it.

### 2026-09-10 round 73: protocol mismatch DISPROVED, and the "12% forward gap" RETRACTED

Added a `protomismatch` counter (census-classified IPv4 frames whose `skb->protocol`
was not IPv4 after `eth_type_trans()`):

```
60 pings:  RXCENSUS icmp +51, protomismatch = 0, Ip: InReceives +50, InDelivers +50
```

**`protomismatch` is 0** - `eth_type_trans()` returns IPv4 for every frame the census
calls IPv4. Rounds 70/71's leading candidate is disproved.

**And the gap is 1 frame, not 12:**

```
round 69  gap 12      round 72  gap  4      round 73  gap  1
```

**The "driver-to-IP gap" is not a stable defect.** It shrank on repetition to
negligible. Most likely explanation: three counters read from three different files at
different instants while frames are still in flight - a 12-frame variance across reads
of a live system is not evidence of a 12% drop.

**Rounds 69-72 chased an artifact, and that should be stated plainly.** A `no_gro`
switch and a `protomismatch` counter were built on a single sample of a quantity already
twice established as noisy on this bench - round 48's `BYTES=0` in a different costume.

**Standing evidence:** TX latency bimodal (0.24 ms to 22 s) with duplicates (solid, 3x);
return path loses ~18% of replies (solid); device answers 1:1 what it processes (solid);
forward path ~100% (998/1000 UDP, 201/200 ICMP). **The single remaining defect is the
transmit path.** Everything measured on receive is clean or was an artifact.

**Next:** TX only. `protomismatch`/`no_gro` are settled negatives - do not revisit. The
200-ping distribution (no rebuild) is the acceptance test; **duplicates are the sharpest
clue** - a duplicated frame means a descriptor or slot was consumed twice, i.e. a defect
in `zx_eth_xmit`'s slot handling.

### 2026-09-10 round 74: the slot-mode "improvement" was a single-sample artifact

Interleaved and repeated A/B of `tx_slot_mode`:

```
mode=0  36.7% loss  avg 480.5 ms  max 5528   pipe 28
mode=1  35.0% loss  avg  41.2 ms  max 1436   pipe  8
mode=0  28.3% loss  avg  42.4 ms  max 1648   pipe  9    <- same as mode 1
mode=1  31.7% loss  avg  65.2 ms  max 2664   pipe 14
```

**The first `mode=0` run showed 480 ms; the next `mode=0` run showed 42 ms.** So the
earlier "mode 1 is 10x better" was **the fluctuating condition, not the slot mode** -
arms run sequentially, first one in a bad window. Loss is **28-37% in every arm**, the
worst this bench has measured, confirming this boot is degraded throughout.

`tx_slot_mode` makes **no reliable difference**. Slot handling is **not** cleared as the
duplicate source - with ~30% loss this test cannot resolve a few-frame effect.

**This is the fourth single-sample artifact in this stretch** (rounds 32, 48, 69, 74).
Two rules now have direct evidence and should be treated as requirements:
1. **Never compare arms sequentially** - interleave A B A B so drift affects both.
2. **A 60-frame sample cannot resolve a few-frame effect here.** Use hundreds, or repeat.

**Cleanup:** `tx_scratch` still exists as a module parameter but is **unused** (round 57
reverted its use, left the declaration). Harmless but should be removed so a future
session does not think a TX-buffer change is in play.

**Next:** stop A/B-ing on 60-frame samples. **Measure the TX ring indices directly**
(`ze->tx_next` vs `TMQ_TXIDX` over a burst) - a deterministic counter comparison is
immune to the fluctuation that has now invalidated four conclusions.

### 2026-09-10 round 75: the driver's TX path is CLEAN - deterministic, machine-checked

`txdbg` prints the driver's slot and the TM's index per transmit, so round 74's
"deterministic index comparison" needed no new code. All 37 transmits from a 40-ping
burst, machine-checked:

```
slot == (idx & 0xffff) % 1024      for ALL 37     slot tracks the TM exactly
distinct slots                     37 of 37       NO duplicates
lengths                            60, 98         correct (98-byte ping)
buffer use                         27/37 = 0, rest 64/68/69/71/72/73/75
```

**The transmit driver does everything right**: every slot is the one the TM is waiting
for (no drift, no reuse), lengths are correct (unlike the RX side's constant 1514), and
TX uses buffers other than 0 - so round 50's "12/12 transmits use buffer 0" was itself a
single-sample reading.

**Therefore the duplicates and the ~19% reply loss are NOT the driver's.** The driver
wrote 37 correct, distinct descriptors into the slots the TM requested; whatever happens
to those frames happens downstream - traffic manager, MAC/PHY, wire, or the host NIC.

This **retires every TX-driver hypothesis** in this stretch: ring overrun (66),
back-pressure (66), slot mode (74), and TX/RX buffer sharing as a *driver* defect (50-57).

| layer | verdict |
|---|---|
| driver RX | mostly clean (delivery matches; the 1514 length unexplained but not fatal) |
| driver TX | **clean** |
| TM / MAC / wire | **suspect** - duplicates and ~19% loss occur after the driver |
| host USB NIC | not excluded; already caused one false negative |

**Next:** (1) test the host side - same ping against a different peer/interface on that
USB NIC; if the loss follows the NIC, all "return loss" measurements since round 67 are
void. (2) If it survives, the fault is below the driver on the device and needs a wire
capture, not more driver instrumentation. **Do not reopen TX driver code** - round 75 is
the strongest class of evidence this project has produced.

### 2026-09-10 round 76: the host NIC counts NOTHING - the loss is below both drivers

The bench link is a **Realtek RTL8153** USB adapter (`0bda:8153`, driver `r8152`) on the
host. Read across a 100-ping run (28% loss, avg 587 ms, max 13.7 s):

```
rx_errors 0, rx_dropped 0, rx_missed_errors 0, rx_fifo_errors 0,
rx_over_errors 0, rx_length_errors 0, rx_crc_errors 0, rx_frame_errors 0,
rx_nohandler 0, tx_errors 0, tx_dropped 0, tx_aborted_errors 0,
tx_carrier_errors 0                                  ALL ZERO
```

**28% of pings vanished and the host NIC counted none of them.**

| layer | verdict |
|---|---|
| device TX driver | **excluded** - 37/37 correct slots, no duplicates, correct lengths (r75) |
| device RX driver | largely excluded - forward delivery ~100% |
| host NIC (RTL8153) | **excluded** - every error counter zero across 28% loss |
| host NIC as a *latency* source | open - zero errors is not zero buffering |

**The loss is on the wire or in the device's MAC/PHY.** Candidates: the device's MAC/PHY
transmit; the physical link (cable/port pair); or **link-level handling - duplex or
flow-control mismatch, which drops frames with no counter on either side.** The third
best explains the latency too: one-sided flow control or a duplex mismatch delays frames
via pause and drops them silently - exactly the observed 0.24 ms median with multi-second
outliers and silent loss.

**Next:** (1) determine flow-control/duplex on both ends (the device logged
`Link is Up - 1Gbps/Full - flow control off`; the RTL8153 side is unknown and needs no
`ethtool`); (2) vary the physical layer one item at a time - a different cable, or a
different device port; (3) a wire capture would settle it in one measurement.

**Environment note:** the bench has one usable host interface and no capture port, so
the remaining questions are physical and need a workstation change. **Driver work is
complete pending those measurements** - rounds 67, 75 and 76 are three consecutive
deterministic results excluding the drivers on both sides.

### 2026-09-10 round 77: the ping timeout was 1s on a link with multi-second latency

Every figure in rounds 62-76 used `ping -W 1`. The same runs showed RTT maxima of 5-22 s.
Those are incompatible: **the release-timeout filter was discarding late replies and I was
reading them as loss.**

Same traffic, only the timeout changed:

```
-W 1    100 tx, 70 rx, +4 dup, 30% loss, avg 498 ms, max 13512 ms, pipe 67
-W 10   100 tx, 78 rx, +2 dup, 22% loss, avg 259 ms, max  7588 ms, pipe 38
```

**Eight points of the reported "loss" were replies arriving after one second.** Widening
the timeout also halves the apparent average RTT and `pipe` depth.

* Part of the "loss" since round 62 was a **timeout artifact**; the true figure is ~22%.
* **The latency problem is larger than the loss problem and was hidden by it.**
* **~22% still never arrives within 10 s** - a genuine loss remains, now separated.

**Rule added: match the instrument's timeout to the phenomenon being measured.** A 1 s
timeout on a link whose maximum is 22 s measures the timeout, not the loss. Fifth
instrument error in this stretch (32, 48, 69, 74, 77), same root cause - choosing a
convenient tool setting and then reasoning about the number.

**Next:** re-baseline with `-W 10` throughout; report loss and latency separately; the
round-76 physical-layer conclusion stands but should be restated with corrected figures.

### 2026-09-10 round 78: LATENCY IS PURE QUEUEING - ~20% loss is real and rate-independent

```
fast  -i 0.2 (5/s)   60 tx, 42 rx, 30% loss  avg 568.6 ms  max 8425 ms  pipe 42
slow  -i 2   (0.5/s) 30 tx, 24 rx, 20% loss  avg   0.248 ms max  0.317 ms pipe  0
```

**At 0.5 req/s the device answers in 0.248 ms average, 0.317 ms maximum, zero in flight.**
There is no multi-second latency at all.

**Latency is a queueing artefact of the test rate.** Driving 5/s into a device that needs
>200 ms per exchange builds a backlog, and the backlog produced the 5-22 s RTTs. **Every
"TX is slow" conclusion in rounds 62-77 is an artefact of my own test load**; round 65's
"bimodal latency" is what an overdriven queue looks like from outside.

**But 20% of exchanges still fail at 0.5/s** with a 5 s timeout - real, rate-independent,
and now free of both artefacts (the 1 s timeout and the backlog). **This is the defect.**

Combining r67 (loss is on the **return** path: 201/200 requests received, 157 replies
arrived), r75 (driver TX **clean**: 37/37 correct slots), r76 (host NIC **counts
nothing**), and r78 (loss is **rate-independent**): **one frame in five that the driver
correctly queued never reaches the host, is not corrupted, is counted by nobody, and does
not depend on load - i.e. it was never put on the wire.**

**Next:** the device's MAC/TM transmit path is the prime suspect - does the TM fetch every
descriptor the driver queued? Cheap deterministic check: compare `tx_packets` from
`/proc/net/dev` against the TM consumed index over a slow ping run. 30 transmitted vs 24
consumed would mean the TM drops descriptors, closing the loop opened in round 63 when
`TMQ_CREDIT` was found constant. **Do not chase latency further** - it is characterised,
not a defect at sustainable rates, and has consumed six rounds.

**Method note:** two test-configuration artefacts - a 1 s timeout on a 20 s phenomenon,
and a test rate the device cannot sustain - produced most of the "defects" investigated in
rounds 62-77. Both were settings I chose and never questioned. **Correct settings for this
link: 2 s interval, 5 s timeout.**

### 2026-09-10 round 79: the TM consumes EVERY descriptor - the loss is bidirectional and physical

Deterministic check with corrected settings (2 s interval, 5 s timeout):

```
30 pings at 0.5/s                    host: 18 received, 40% loss
TMQ_TXIDX  0b830b83 -> 0b9d0b9d      +26
RXCENSUS icmp  904 -> 930            +26
```

**The TM's consumed index advanced by exactly 26 and the driver received exactly 26
requests** - the device transmitted one reply per request processed, and the TM consumed
**every descriptor the driver queued**. No descriptor drop, no missed doorbell, no TM-side
loss. This closes the question opened in round 63 when `TMQ_CREDIT` was found constant.

**And the loss is in BOTH directions:** forward 4/30 (13%), return 8/26 (31%). Every
counter on both ends reads zero (`eth2` rx_errs/rx_drop, `Ip: InHdrErrors`/`InDiscards`,
and the RTL8153's rx_errors/missed/crc/fifo/over/length).

**Conclusion: silent bidirectional loss at ordinary rates, with the driver verified clean
and every counter zero, is a physical-layer signature** - a marginal cable, connector or
PHY. Software-side is now excluded by five deterministic results:

| layer | evidence |
|---|---|
| driver TX | 37/37 correct slots, no duplicates, correct lengths (r75) |
| driver RX | forward delivery matches the census (r68/72/79) |
| TM descriptor consumption | exact 1:1 with the driver (r79) |
| host NIC | all error counters zero across 28% loss (r76) |
| latency | fully explained as queueing from the test rate (r78) |

**Next - a bench action, not code:** (1) **replace the cable** - the cheapest physical
variable, never yet changed; (2) **move the device to a different port** (eth0/eth1/eth3);
(3) re-run the round-79 measurement after each change - forward loss implicates
host->device, return loss device->host, and a clean run ends the investigation.
**No further driver instrumentation.**

### 2026-09-10 round 80: host softnet drops zero - software exclusion COMPLETE

Checked the last host-side counter never examined, per-CPU softnet (which drops frames
under load without touching any NIC counter):

```
26.7% loss run: /proc/net/softnet_stat, all 16 CPUs
    dropped 0 -> 0        time_squeeze 0 -> 0
```

Also: `r8152` exposes no flow-control parameter; the device logs
`1Gbps/Full, flow control off` consistently.

| end | layer | verdict |
|---|---|---|
| device | driver TX (37/37 slots, no dups, correct lengths) | clean (r75) |
| device | TM consumption (index +26 vs received +26) | 1:1 (r79) |
| device | driver RX (delivery matches census) | clean |
| device | eth2 rx_errs/rx_drop, IP InHdrErrors/InDiscards | 0 |
| host | RTL8153 all error counters | 0 (r76) |
| host | softnet dropped, time_squeeze, all CPUs | 0 (r80) |
| both | latency | queueing artefact (r78) |

**Nothing in software accounts for a 13-31% bidirectional frame loss.**

**The residual loss needs a physical intervention** - cable swap or a different device
port - which is outside this session's reach. That blocks *this question*, not the whole
objective.

**Still testable in software:** (1) the **cold-boot** matrix row - never run, needs no new
hardware; (2) re-read the **M0-M8 gates** in `docs/PORT-STATUS.md` against what is now
established (ring wraps PASS 99.5%, 1 MB TCP byte-exact at 2.28 Mbit/s, ping 0.25 ms at
sustainable rates, forward RX ~100%) - several may already be met and simply unmarked;
(3) hand over the physical test explicitly: round 79's procedure after a cable swap.

**Latent defect noted, not closed:** the **RX descriptor length reads a constant 1514** in
every trace against 98/106-byte frames, since round 31. It does not cause the measured loss
but means the driver copies ~1.4 KB of stale bytes per frame and hands the stack an skb
whose length disagrees with its contents.

### 2026-09-10 round 81: the 1514 constant RESOLVED - the hardware never writes a length

Raw RX descriptor for a received 98-byte ping:

```
bb 01 00 00 00 00 18 f1 00 d4 0b 20 a8 17 24 00
```

Searching those 16 bytes for 98 in any plausible encoding (0x62, 0x188, 0xc4): **absent**.
**The frame length is nowhere in the descriptor.** The hardware writes word 1 (port + slot
counter) but never the length, so the driver copies the *template's* constant:

```c
len = ((desc[12] | ((u32)desc[13] << 8)) >> 2) & 0x3fff;   /* 1514 - template value */
memcpy_fromio(skb_put(skb, len), bufs + idx*BUF_SIZE + BUF_HDR, len);
```

* **Not corruption, not a decode error** - the driver copies a fixed maximum because it has
  no source for the true length. It passes the driver's own sanity check.
* **Still a real defect**: every frame costs a ~1.4 KB copy instead of ~100 bytes, and ~93%
  of what is copied is stale bytes from a concurrently-written buffer - the race
  hypothesised in rounds 40/43, now with a concrete mechanism.
* **Benign for delivery**, which is why it survived: the stack derives the real length from
  the IPv4 header. Delivery matches the census on every run since round 60.
* **Explains the driver's inability to detect a truncated or oversized frame** - it never
  reads a length to check.

**A correct RX path needs the real length from somewhere** (descriptor, buffer, or a
per-frame register). That is a protocol question about the hardware, not a bug to patch -
find where the SoC records the received length before changing the copy. **It does not
explain the residual loss** (round 80), which remains physical.

**Objective status:** ring wraps PASS 99.5%; TCP PARTIAL PASS (1 MB byte-exact, 2.28 Mbit/s);
ping 0.25 ms at sustainable rates; forward RX ~100%; residual loss **physical (cable
swap)**; simultaneous ports NOT RUN (needs a second cable); cold boot NOT RUN (**testable in
software**); RX length handling **resolved**.

### 2026-09-10 round 81 addendum: the second cable is on eth1, and eth1 passes NO traffic

Host `tiny` has a cable into a box LAN port - the second-host comparison round 80 wanted.

```
device:  eth0 NO-CARRIER   eth1 UP,LOWER_UP   eth2 UP,LOWER_UP (USB NIC)   eth3 NO-CARRIER
device eth1 192.168.7.1/24   tiny eth0 192.168.7.2/24

tiny -> device:  100 tx, 0 rx, +90 errors, 100% loss
device -> tiny:    3 tx, 0 rx, 100% loss
tiny ARP:        192.168.7.1 FAILED
```

**ARP fails in both directions.** The link is up, both ends are on the same subnet, and no
frame crosses - the failure is above the PHY, in the port's datapath.

**Consistent with round 35:** `zx_datapath_warm()` attaches to the datapath **U-Boot**
configured, and `datapath_init()` - which would configure the other ports' MACs - is
**skipped on every boot**. So **only eth2 has a working datapath** (the port the bootloader
brought up); the other three come up at the PHY but their MAC side was never configured.

**"Simultaneous ports" is therefore not merely unrun - it is probably non-functional**, and
should be recorded as such.

**The second-host loss comparison cannot be made as things stand.** tiny cannot reach the
box on eth1, leaving eth2 to the USB NIC - the very path in question. Options: (1) make the
warm path bring up every port's MAC (a real, separate defect and the prerequisite for both
the second-host test and the simultaneous-ports row); (2) put the box and `enp4s0` on one
segment via a spare switch to isolate the USB NIC without touching the driver.

**Highest-value software work is now bringing up the non-bootloader ports**, which unblocks
both the second-host measurement and the simultaneous-ports row.

### 2026-09-10 round 82: the non-bound ports are NEVER MAC-enabled - gate found

eth1 (cabled to host `tiny`) has carrier but passes no traffic (round 81). The cause:

```c
if (zx_all_ports && !zx_split_ports && zx_cpu_mode) {   /* every other port */
        for (p = 0; p < ZX_NPORTS; p++) { ... writel(v | MAC_CTRL_EN, ...); }
}
```

The driver's own comment: *"Every other port too - **this is what makes them ingress at
all**."* The conditions as shipped:

```
all_ports   = Y      cpu_mode = Y      split_ports = true (default)
                          -> !zx_split_ports is FALSE -> block SKIPPED
```

**With shipping defaults the driver never enables a non-bound port's MAC.** And
`zx_mac_enable()` is called from exactly **one** place, with `on = false`, on close - it is
**never called with `on = true` anywhere**. eth2 works only because **U-Boot** enabled it and
the warm path preserves that (the round-35 dependency).

**Three of four ports have never been functional in any build.** They register as netdevs
and their PHYs come up, which is why the failure is invisible until traffic is sent.

**Runtime test inconclusive:** `split_ports=0` brings eth1's PHY link up, but traffic still
fails (ARP both ways) and re-opening eth1 produced no `port mode:`/`port N enabled:`
messages - so the block did not execute even with the gate satisfied. Reason not
established.

**Fix direction:** call `zx_mac_enable(ze, p, true)` for every port on open (and `false` on
close) - what the function exists for. Removes the `!split_ports` coupling, which looks like
an artefact of the two modes being developed separately. If the gate is deliberate,
establish why first. **Verify by reading each port's `MAC_CTRL` bit 0**, not by pinging -
the poke endpoint is documented to hang the board on the MAC apertures.

**Priority, because it unblocks three things:** eth1 gives the **second-host loss
comparison** round 80 wanted (different host, NIC and device port); it makes
**simultaneous ports** testable rather than void; and a four-port ONT that drives one port
is not a port.

### 2026-09-10 round 83: MAC-enable fix WORKS - eth1 alive and transmitting; TX port attribution next

Removed the `!zx_split_ports` gate from the all-ports MAC enable in `zx_eth_open()`.
Rebuilt, booted:

```
port 1 -> eth1 ... eth1: Link is Up - 1Gbps/Full
eth1: txdbg mode=0 slot=160 len=90 buf=123 idx ...
```

**eth1 is no longer dead** - it comes up at gigabit and the driver actively queues
transmits on it. Before this round it had carrier and never passed a frame. **The MAC-enable
fix is real and landed; this is the first functional change to multi-port support.**

**But traffic still does not reach tiny** (20 tx, 0 rx, 100% loss), and the descriptors show
why:

```
desc 00000080 f6010000 2100b400 0000016a
```

**word 1 carries the destination port in bits [21:19] and is a constant** - the field the
driver has a parameter for (`zx_tx_dest`, word1 bits 13:8; "0 keeps the template exactly as
it was"). A frame queued on **eth1** is written with a descriptor naming the **template's**
destination port - the one the bootloader configured - not the port that sent it.

**Same class as the RX descriptor template (rounds 37-39): the TX descriptor's port field is
never set per-port.**

**Next:** set the TX descriptor's destination port from the transmitting netdev.
`zx_eth_xmit` already has its `ndev`; `zx_tx_dest` shows the bits. Success test: `tiny`
pinging eth1 at 0% loss.

**Two layers are now separable:** `all_ports` fixes ingress for all four ports (done); TX
attribution fixes egress per port (next). Round 82 conflated them because with no MAC enabled
nothing could be measured.

**Value:** eth1 working gives the **second-host loss comparison** (different host, NIC and
device port) that has been blocked since round 80 - the cleanest discriminator for the
residual ~20%.

### 2026-09-10 round 84: eth1 reaches the wire; blocker is TX attribution + tiny's bridge

**(1) `tx_dest` is NOT the egress selector.** All four plausible values fail from tiny:

```
tx_dest = 0/1/2/3  ->  100% loss every time
```

Round 83's inference from the parameter's existence was reasonable and **wrong**.

**(2) Frames from the device DO reach tiny** - during a device-side ping, tiny's `eth0`
`rx_packets` went **466 -> 472 (+6)**. The device's transmit reaches the port and the wire;
tiny's cable and link are good.

**(3) tiny's `eth0` is enslaved to bridge `br0`** - an address on a bridged *port* does not
behave like one on a routed interface, which is why every earlier attempt failed with ICMP
errors rather than silence. Moving the address to `br0` removed the errors but **the ping
still fails**, so that was a real bench fault, not the whole story.

| fact | status |
|---|---|
| non-bound ports' MACs enabled | **FIXED (r83)** - eth1 up and transmitting |
| device TX reaches tiny's NIC | **confirmed** (+6 frames) |
| complete ARP round trip | **NO** - `192.168.7.1 FAILED` |
| `tx_dest` as egress selector | **disproved** |
| tiny's bridged eth0 | **found and worked around** |

**Next:** watch tiny's `eth0` **and** `br0` rx counters during a device-initiated ping. If
`eth0` increments but `br0` does not, the bridge drops it; if both do and the device still
sees nothing, the return path from tiny is the problem. Run it from the device console so
the whole exchange is observable in one place.

**Position:** multi-port work has landed its first real fix; the residual-loss question is
still blocked on a working second path, now **one debugging step away** rather than a cable
swap away (better than round 80).

### 2026-09-10 round 85: eth1 is TRANSMIT-ONLY - device sends fine, receives nothing

Counter comparison during a device-initiated ping to tiny:

```
tiny eth0 rx  472 -> 478  +6     frames arrived from the device
tiny br0  rx  452 -> 458  +6     the bridge forwarded them
tiny eth0 tx  276 -> 282  +6     tiny REPLIED
device        8 transmitted, 0 received     <- replies never arrived
```

**Everything works except the last hop.** eth1 transmits to the wire; tiny receives,
forwards and answers; the device receives nothing. **eth1 is transmit-only.**

This matches the driver's `MAC+0x00` bit-0 note (`0` = egress, `1` = CPU receives) only
partially - eth1 behaves as though transmits egress *and* receives go nowhere, i.e. like
bit0=0 in both halves.

**More likely, and consistent with round 35:** `datapath_init()` is skipped on every boot and
the driver attaches to U-Boot's datapath, configured for the **single port the bootloader
used**. Round 83 enabled the other ports' **MACs** - but **the receive datapath (TM rings and
queue configuration feeding the CPU) is configured once, for that one port.** Enabling a
second port's MAC lets frames reach the wire and the wire reach the MAC; it does not create a
CPU receive path for that port.

**Ordering: `all_ports` fixed the MAC (r83); non-bound-port RX is the next layer - the same
warm-path limitation, one level deeper.**

**Second-host comparison still blocked**, now for a well-understood reason. Two routes:
1. Configure the RX datapath per port - the natural extension of r83, but larger; needs
   separating per-port (rings, queue mapping) from global in `datapath_init()`.
2. **Recommended:** put the box and host `enp4s0` on one segment via a switch, keeping eth2
   as the device port. That answers the host-NIC question - what the second host was for -
   without needing non-bound-port RX at all.

### 2026-09-10 round 86: non-bound-port RX is ABSENT - the census sees nothing

```
RXCENSUS icmp=0 udp=0 tcp=0 other=0 nonipv4=0 protomismatch=0
ping -c 5 192.168.7.2 -> 5 transmitted, 0 received
   (tiny received, forwarded and replied - round 85)
RXCENSUS icmp=0 udp=0 tcp=0 other=0 nonipv4=0 protomismatch=0
```

**The census counts nothing across the whole exchange.** It is global across all ports, so
this is not attribution - **frames arriving at eth1 never reach the driver.**

| layer | eth1 state | round |
|---|---|---|
| PHY / link | works | 81 |
| MAC enabled by the driver | **fixed** (was never enabled) | 83 |
| transmit to the wire | works | 83-85 |
| **receive to the CPU** | **absent** | 86 |

**This is round 35's warm-path limitation one level deeper.** `datapath_init()` is skipped on
every boot, so the datapath is U-Boot's - configured for **one port**. Enabling a port's MAC
(r83) gives physical presence; it does not give a **receive ring and queue mapping into the
CPU**. Making other ports receive means initialising the per-port RX datapath on the warm
path - substantial work, and now the correct next task rather than a guess.

**Round 35 + 86 together: the driver has never had a working cold-init RX path at all**
(forcing `force_dp_init=1` killed RX on the port that normally works).

**Next, in order:** (1) **do not** attempt per-port RX initialisation yet - it touches exactly
the path round 35 showed kills receive, and it cannot be measured without the second port we
are trying to build; (2) **close out the residual-loss question using the one working port** -
put the box and host `enp4s0` on one segment via a switch and repeat round 79's
forward/return split, which decides whether the ~20% follows the USB NIC and needs no driver
change; (3) re-read the **M0-M8 gates** against what is established and mark what is met.

### 2026-09-10 round 88: the NPP per-port classifier is ALSO warm-skipped

Following round 86, the per-port receive configuration was located - in the same place the
MAC enable was:

```c
for (port = 0; port < 4; port++) {
        u32 v = readl(npp + 0x60 + port * 4);
        writel(v & ~zx_npp_port_mask, npp + 0x60 + port * 4);   /* bits 25:23 */
}
```

The driver's own comment names `npp + 0x60 + port*4` as "the only per-port
classification-shaped field this driver touches". **It is inside the init block a warm boot
skips** (round 35), so on every boot the NPP holds U-Boot's values - configured for the port
U-Boot used.

| layer | warm-boot behaviour | consequence |
|---|---|---|
| port MAC | never enabled (gated on `!split_ports`) - **fixed r83** | non-bound ports inert |
| RX datapath | never configured (init skipped) | non-bound ports never reach the CPU |
| **NPP per-port classifier** | **never written (init skipped)** | **steering is the bootloader's** |

**One cause: everything that configures a port lives in a block that only runs cold, and this
board always boots warm.**

**Do not apply it wholesale.** Round 35: `force_dp_init=1` left RX **completely dead on the
working port**. The NPP block clears bits 25:23 on all four ports *including the working one*,
and U-Boot's values there are what make eth2 receive today.

**Correct experiment, incremental:**
1. **Read** `npp + 0x60 + port*4` for ports 0-3 and record U-Boot's values - read-only, shows
   whether the working port differs. The NPP aperture is recorded as safe for poke (the risky
   ones are the MAC apertures).
2. If it differs, change **one non-bound port** toward the working port's value and test
   whether it starts receiving. eth2 stays untouched.
3. Only then do it for all ports in the driver.

**Multi-port model after rounds 81-88:** PHY works; MAC enable **FIXED** (r83); NPP per-port
classifier **never written on a warm boot** (r88); receive to CPU absent. **The remaining work
is bounded** - read the registers, compare, apply incrementally - rather than open-ended.

### 2026-09-10 round 88 result: NPP hypothesis DISPROVED - all four ports identical

```
npp = ioremap(0x921c0000, SZ_128K)

[921c0060] = 00201000   port 0      [921c0068] = 00201000   port 2
[921c0064] = 00201000   port 1      [921c006c] = 00201000   port 3
[921cc060..6c] = 0      (second range, unused)
```

**All four ports read identically**, and `zx_npp_port_mask`'s field (bits 25:23) is **already
zero on every port** - so the NPP writes would be no-ops even if they ran. **The NPP per-port
classifier is NOT the cause**; the hypothesis is disproved by measurement, one command and no
rebuild.

**Layered model, one candidate eliminated:**

```
PHY / link                    works
MAC enabled by driver         FIXED (r83)
NPP per-port classifier       IDENTICAL - not the cause (r88)
RX datapath (rings/queues)    configured once by U-Boot for one port  <- remaining suspect
receive to CPU on eth1        absent
```

**Remaining suspect: the receive datapath itself** - TM rings and queue-to-port mapping that
`datapath_init()` sets up cold and the warm path skips. Round 35 showed running that
initialisation **kills RX on the working port**, so this is delicate rather than an oversight.

**M7 honest state:** four-layer model; one real fix landed (MAC enable - three of four ports
were inert in every build); one candidate excluded by measurement; one area identified as
delicate. Working single-port delivers 1 MB TCP byte-exact at 2.28 Mbit/s.

**Next:** the per-port RX datapath, approached read-compare-change-incrementally - the
discipline that just settled a plausible theory in one command.

### 2026-09-10 round 89: no safe read path for per-port MAC registers

Round 88 narrowed M7 to the **receive datapath**, and the next step is comparing the working
port's MAC registers against the non-working ones. **That cannot be done with the tools
present:**

* `/proc/zx_eth_poke` **hangs the board** on the MAC apertures (since round 32) - MAC reads
  are off limits.
* `/proc/zx_eth_regs` **exposes no per-port MAC state** - no MAC/port `seq_printf` exists.

The one register set that matters for the next step is readable **only by the driver**.

**Attempted fix:** a `MACCTRL p0=.. p1=.. p2=.. p3=..` line in `/proc/zx_eth_regs`, reading
each port's `MAC_CTRL` through the driver's own `ioremap` (safe by construction). **The build
failed (`BUILD_EXIT=2`) and the log contains no compiler diagnostic** - the kernel compile
step never appears, only `target/linux failed to build`. The change is **reverted** in source
and all three tree copies, so the tree stays buildable and matches the last known-good state.

**Next:** re-apply and build with **`make -j1 V=s`** to surface the error - the change is small
and the failure is almost certainly a C scoping detail in how the block was inserted. Then run
`grep MACCTRL /proc/zx_eth_regs` with eth1 cabled to `tiny`: that decides whether the
non-working ports' MAC registers differ from the working one. Only then change anything, one
non-bound port at a time.

**Process note:** `-j$(nproc)` is right for a build expected to succeed and wrong for one
being tried for the first time - it hides the diagnostic that matters.

### 2026-09-10 round 90: MAC config IDENTICAL on working and non-working ports

Round 89's reporting line re-applied (using the function's existing loop variable - the first
attempt declared its own inside a nested block and failed to compile, diagnostic hidden by
`-j$(nproc)`; `V=s` built it first time):

```
MACCTRL  p0=00000000  p1=00bb6003  p2=00bb6003  p3=00000000
```

**1. Round 83's fix confirmed at register level.** Port 1 reads `0x00bb6003` (enabled) where
the driver's own comment records `0x00000000` before. Ports 0/3 read zero simply because they
were never opened - expected, not a gap.

**2. The MAC is NOT the discriminator for missing per-port RX:**

```
port 1 (eth1, cabled to tiny, does NOT receive)  0x00bb6003
port 2 (eth2, cabled to bench, DOES receive)     0x00bb6003      <- IDENTICAL
```

Same register, bit 0 set on both. The "bit0 is a MODE bit" note cannot explain this, since
both ports are in the same mode.

```
PHY / link                   works
MAC enabled by driver        FIXED (r83), confirmed identical to working port (r90)
NPP per-port classifier      IDENTICAL - not the cause (r88)
RX datapath (rings/queues)   configured once by U-Boot for one port  <- SOLE remaining suspect
```

**Next:** the receive datapath is the TM ring and its queue-to-port mapping. Round 35 is the
hazard - `force_dp_init=1` leaves RX **dead on the working port**, so that initialisation is
destructive as written and cannot simply be enabled. **Do not run it.** Instead, extend the
same safe-read technique to the **TM ring/queue registers** and compare against U-Boot's live
state - the instrument that made this round work is reusable, and building it for the TM
registers is the concrete next task.

### 2026-09-10 round 91: regression check - working port is PERFECT at sustainable settings

```
ping -c 20 -i 2 -W 5 192.168.1.1
20 transmitted, 20 received, 0% packet loss
rtt min/avg/max/mdev = 0.221/0.938/13.706/2.929 ms
```

**Zero loss, sub-millisecond average**; the round-90 MACCTRL change did not regress the
working port.

**This reframes the "residual ~20% loss".** The same nominal rate has previously produced
20-40%. It is **not a constant property of the link** - it fluctuates and can be zero. The
honest description is **"delivers perfectly in good windows, loses heavily in bad ones"**;
the bad windows are what remains unexplained, and every software layer on both sides has been
excluded as their cause (rounds 67-80).

| capability | status |
|---|---|
| single port, sustainable rate | **PASS - 0% loss, 0.94 ms avg** (r91) |
| single port, TCP payload | **PASS - 1 MB byte-exact, 2.28 Mbit/s** (r59) |
| ring wraps | **PASS - 99.5% over 2500 frames** (r47) |
| forward RX | ~100% (998/1000 UDP) (r60) |
| multi-port MAC enable | **FIXED** - three of four ports were inert in every build (r82-83, confirmed r90) |
| multi-port receive | absent - RX datapath is per-bootloader-port only (r86, r90) |
| bad-window loss | intermittent, **no software cause found on either side** (r63-80) |

**Next:** (1) extend the round-90 safe-read technique to the **TM ring/queue registers** and
compare U-Boot's live state against what `datapath_init()` would write - **without running
it** (round 35: running it kills the working port); (2) the bad-window loss needs the
**switch route** (round 85) to test whether it follows the USB NIC. **Neither is a code change
away**, and both have a specific next action rather than being open-ended.

### 2026-09-10 round 92: SPA steering is protocol-based - third candidate eliminated

```
SPA_BASE = 0x921d4000     [921d41c0] = 11060000   SPA_TRAP_PROTOCOLS
```

`0x11060000` = `FIELD_PREP(31:24, IPPROTO_UDP) | FIELD_PREP(23:16, IPPROTO_TCP)` - exactly
what the driver writes, **with no port field**. **CPU steering is by protocol, not port**, so
it cannot explain one port receiving and another not. (ICMP is not in the trap list yet
reaches the CPU, so at least one more steering path - likely NPP/PPU - exists and has never
been identified.)

**Three of four candidates now eliminated by direct register inspection:**

| candidate | exclusion | round |
|---|---|---|
| per-port MAC config | identical on both ports (`0x00bb6003`) | 90 |
| NPP per-port classifier | identical on all ports; masked field already zero | 88 |
| SPA CPU steering | protocol-based, no port field | 92 |
| **RX datapath (TM rings / queue mapping)** | **not excluded - sole remaining suspect** | - |

**Next actions:**
1. Extend the round-90 safe-read technique to the **TM ring/queue registers**; compare
   U-Boot's live state against what `datapath_init()` *would* write - **without running it**
   (round 35: running it kills the working port). Read-only, bounded, instrument proven.
2. Test the **bad-window loss on a different host path** (switch route, round 85) to decide
   whether it follows the USB NIC - hardware, not code.

---

## Validation matrix — platform-corrected, round 97

**This table supersedes the round-30-93 table below it, and invalidates most of its
verdicts.** The reason is not a new measurement; it is a new fact about the
*instrument*. Round 96 established that the driver's `zx_datapath_warm()` returns
true if **any** of the four ports has `readl(mac + MAC_CTRL) & 0xffff0000`, and that
a TFTP RAM boot leaves the cabled port's MAC configured. So on a TFTP RAM boot the
driver **skips `zx_eth_datapath_init()`** — and every measurement the project has
ever taken on this bench was a TFTP RAM boot.

Round 96 proved the consequence causally, one kernel and one U-Boot write:

| boot | logged decision | `eth1` (non-bound) rx | `eth2` (bound) rx |
|---|---|---|---|
| TFTP RAM, untouched | `datapath warm (rx ring 41a00000 tx ring 41c00000) - init skipped` | **0** | 18 |
| TFTP RAM, `MAC_CTRL` cleared in U-Boot | `datapath init at probe (cold)` | **9** | 16 |

**A PASS measured on an INIT-SKIPPED boot is not evidence about the product.** The
platform of every row below is taken from the logged decision string, which is the
only authority:

* **INIT-RAN** — `datapath init at probe (cold)` or `(forced)`. A NAND cold boot, or
  a RAM boot with `MAC_CTRL` cleared. This is what the product does.
* **INIT-SKIPPED** — `datapath warm ... init skipped`. The datapath is U-Boot's,
  not the driver's.
* **UNKNOWN** — the boot recorded no decision line (pre-r3 and IRQ-shell revisions).

Round 97 audited all 36 sessions in `logs/uart.log` (548,733 lines). Between the
only two cold boots — `uart.log:537871` (`trace35`, the R35 confound) and
`uart.log:546209` (the R95 NAND boot) — there are **17 consecutive INIT-SKIPPED
boots** and no cold line. **R36-R94, and R28-R34, were measured exclusively on
INIT-SKIPPED boots.**

| validation item | round | platform | verdict stands? | must be re-measured |
|---|---|---|---|---|
| unidirectional ping, sustainable rate | r91 | INIT-SKIPPED (`uart.log:545676`) | **NO** | yes, on INIT-RAN |
| labelled UDP burst, small | r46 | INIT-SKIPPED | **NO** | yes |
| labelled UDP burst, fast (350 ms) | r43-r47 | INIT-SKIPPED | **NO** | yes |
| ring wraps (2500 frames) | r47 | INIT-SKIPPED | **NO** | yes |
| forward RX, large volume | r60, r67 | INIT-SKIPPED (`trace61`) | **NO** | yes |
| sustained bidirectional TCP | r59 | INIT-SKIPPED (`trace57/61`) | **NO** | yes, and repeat >=3x |
| device TX driver correctness (37/37) | r75 | INIT-SKIPPED | CONDITIONAL — bookkeeping logic, init-independent in principle | confirm on INIT-RAN |
| TM descriptor consumption (1:1) | r79 | INIT-SKIPPED | CONDITIONAL — same reasoning | confirm on INIT-RAN |
| multi-port MAC enable (fixed) | r83, r90 | INIT-SKIPPED | **PARTIAL** — the fix is a source fact; r90's readback `p0=0 p1=00bb6003 p2=00bb6003 p3=0` is a warm-state read | re-read on INIT-RAN (**done r97: `p0=00bae002 p1=00bae002 p2=00ba6003 p3=00bae002` — all four carry the full config word**) |
| **multi-port receive** | r86 | INIT-SKIPPED | **DEAD — retracted by R96's causal A/B** | replaced by the INIT-RAN result below |
| multi-port receive, INIT-RAN | r96, r97 | **INIT-RAN** | **PASS** — `eth1` rx 0 -> 9 with the same kernel | repeat on the product path |
| simultaneous ports | — | — | **UNRUN** — premise was dead, not blocked | yes: concurrent traffic on >=2 ports |
| cold boot, no bootloader network use | r95/r96 | **INIT-RAN** | **PASS** — the only row the old table got right | repeat x3; bound port poor (2/5 @6048 ms) |
| intermittent bad-window loss | r67-r80, r91 | INIT-SKIPPED | **NO** — both the 20-40% and the 0% readings are warm-platform | yes, on INIT-RAN + a clean host path |
| IRQ RX validation (1 IRQ/frame, idle no storm) | r9-r15 | **UNKNOWN** — the irq-shell boots print only `rx ring=... tx ring=...`, no decision line | unknown | yes, on INIT-RAN |
| interface stop/reopen | r23 | INIT-SKIPPED (`uart.log:525673`) | **NO** | yes, on INIT-RAN |
| M6 "initialization and ownership verified" | — | — | **NO** — warm-skip is precisely the removal of that initialisation | yes, on INIT-RAN |

**Platform-independent, still trustworthy:** the descriptor decode (port = MAC index
+1 via `desc[6] >> 3`), the geometry (DESC_SIZE 16, ZX_RX_RINGS 16, RING_ENTRIES
1024, RX ring `0x41a00000` / TX ring `0x41c00000`), `TMQ_CREDIT` is not a completion
counter, BM registers are read-only status, the hardware writes no RX length, the
`port N -> ethN` enumeration, the R96 causal A/B itself, the R95/R96 NAND cold-boot
facts, and the whole vendor decompilation.

**Minimal boot set that closes the platform gap** (three boots, no flash write):

* **BOOT I** — `trace90.kernel` over TFTP, with `mw.l 0x92200000/0x92240000/0x92280000/0x922c0000 0x00000000`
  before `bootm`. Predict `datapath init at probe (cold)`. **Answers rows 1-11, 13, M6 and M9 in one boot.**
* **BOOT C** — relay-only power cycle into the flashed image, radios held off. The product path. Repeat x3.
* **BOOT W** — the control: the same kernel untouched. Predict `init skipped`. Run its arms interleaved inside BOOT I, never sequentially.
* Row "intermittent bad-window loss" needs a **switch + `enp4s0` host path**, not a boot.

**Instrument settings for any future RX/TX measurement on this bench:**
`ping -i 2 -W 5`. A 1 s timeout on a link whose measured maximum was 22 s measures the
timeout, not the loss; and 5 pings/s overdrives the device and manufactures latency.

### The superseded round-30-93 table, kept verbatim for the record

Every row below was measured on hardware in a RAM boot; **nothing in this stretch was
written to flash**. It is retained exactly as written so that the retraction above can
be diffed against it - **none of its PASS verdicts are valid on the product path.**

| validation item | status | evidence |
|---|---|---|
| unidirectional ping, sustainable rate | **PASS** | 20/20, 0% loss, 0.94 ms avg (r91) |
| labelled UDP burst, small | PASS | ~80% avg; the shortfall is at burst onset |
| labelled UDP burst, fast (350 ms) | PASS at steady state | superseded the round-30 "FAIL", which was measured on poke-damaged boots |
| ring wraps (2500 frames) | **PASS** | 99.5% delivered, zero errors (r47) |
| forward RX, large volume | **PASS** | 998/1000 UDP (r60); 201/200 ICMP (r67) |
| **sustained bidirectional TCP** | **PARTIAL PASS** | 1 MB byte-exact at 2.28 Mbit/s (r59); 32 KB completes; 256 KB and 4 MB stall intermittently |
| device TX driver correctness | **PASS** | 37/37 correct slots, no duplicates, correct lengths (r75) |
| traffic-manager descriptor consumption | **PASS** | index advance exactly matches frames received (r79) |
| multi-port MAC enable | **PASS (fixed)** | all four ports enabled by the driver (r83), confirmed at register level (r90); three of four had been inert in every build |
| **multi-port receive** | **FAIL** | absent, not lossy - the driver census counts nothing from a non-bound port (r86); three alternative explanations eliminated (r88/r90/r92/r93) |
| simultaneous ports | **BLOCKED** | by multi-port receive above; previously mis-recorded as "NOT RUN" |
| cold boot with no bootloader network use | **RUN (r95/r96)** | boots to userspace; `eth2` receives; **`eth1` (non-bound) receives**; bound port is poor (2/5 at 6048 ms) |
| intermittent bad-window loss | **UNEXPLAINED** | not a constant rate (0% measured in r91); every software layer on both sides excluded (r67-r80); needs a different host path |

### The three defects that remain, and their exact next actions

1. **Non-bound-port receive.** **The old framing is withdrawn (r96).** There is no
   traffic-manager queue-to-port binding to reconstruct - vendor decompilation shows rings are
   per *queue* and the ingress port rides per *descriptor*. `0x921d9068` was falsified causally
   (clearing every bit did not stop `eth1` receiving). And on the cold boot `eth1` **does**
   receive. What is open is whether the warm-path absence is caused by the skipped init or by
   the driver generation, because the flashed image is a different driver generation. The
   blanket "**do not run `datapath_init()`**" is also wrong as stated: only re-initialising an
   **already-configured** datapath is destructive (r13), and r35's evidence for the blanket
   version was exactly that confound.
2. **Intermittent bad-window loss.** Needs the box and host `enp4s0` on one segment through a
   switch, to decide whether it follows the USB NIC. Hardware, not code.
3. **Cold-boot row.** Let U-Boot autoboot into the flashed image and test there; no flashing
   involved, and it has never been run.

### What is not a defect, recorded to prevent re-investigation

* `len = 1514` on RX - the hardware writes **no** frame length, so the driver copies a fixed
  maximum; benign for delivery, wasteful, and it means the driver cannot detect a truncated
  frame (r81).
* Buffer 0 shared by TX and RX - **by design**; both attempts to move either side away
  (r56 priming, r57 TX scratch) broke receive.
* The `2*cursor + C` pattern in the RX descriptor - an artefact of reading descriptors ahead
  of the hardware; not a property of the field (r78).
* `TMQ_CREDIT` reading a constant - it is not a completion counter; `tx_outstanding` has
  never measured in-flight frames (r63/r64).
* Multi-second ping latency - **queueing from the test rate**, not a device property (r78).

### 2026-09-10 round 95: cold-boot row attempted - platform boots, connectivity inconclusive

Powered the relay directly (`tomada off; tomada on`, no "press 1") so autoboot ran
uninterrupted and the flashed image booted with **no bootloader network use**:

```
cspboot:1300 Booting image ......
## Booting kernel from Legacy Image at 42020020 ...
Linux version 6.6.151 ... #0 SMP Tue Aug 11 23:45:11 2026
zx279128-eth 92200000.ethernet: datapath init at probe (cold)     <- COLD init path
```

The flashed image is **a full OpenWrt, not an initramfs**: `kmdloader`, `urngd`,
`OpenWrt`, `root@OpenWrt:~#`, `eth2 ... master br-lan state UP`, and the driver's own
`heal: 20000 idle polls, re-priming pool` runs. **Substantially more than the RAM-boot shell
this project has been testing in.** (The heal/re-prime strings match the current source tree,
so the flashed image is not built from divergent code - checked.)

**Connectivity: inconclusive.** Ping failed, but the console was flooded by `mt7615e` WiFi
firmware init throughout, so the setup commands did not complete and the address was never
confirmed. **This is an unfinished test, not a negative result.**

**To finish:** boot with the radios held off (`zx-wifi-late` is the driver's own delay knob)
for a usable console; confirm `ip -4 -br addr`; ping the bridge; then record PASS or FAIL.

**Row status: no longer "NOT RUN".** The structural half - a full OpenWrt cold boot from NAND
with no network help - **passed**.
