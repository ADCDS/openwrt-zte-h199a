> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](README.md),
> [installation](INSTALL.md) and [validation](../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.
> **Protocol corrections:** current experimental SPA code writes DATA in
> descending order, then CMD. The earlier CMD-first interpretation below is
> superseded. DATA readback does not independently verify the table RAM.

# ZX279128S Datapath Register Model

This is the M6 register model in progress. It distinguishes the actual H199A
vendor module evidence from sibling-SoC hypotheses. It is not yet a complete
initialization sequence or proof of functional Ethernet.

## SPA Indirect Access

The H199A SPA base is **0x921d4000**, not 0x921cc000. The latter was previously
treated as SPA using a sibling's layout. Its value 0x11 does not establish
anything about the H199A SPA indirect state machine.

Source: stock `tm.ko` spaRegTable, spa_set_indirect_rw_cmd,
spa_get_indirect_rw_status, spa_get_hashram, and `zx_ponreg.ko` fpga_read_reg.
Ghidra analysis is retained in the private bench artifacts. SDK table entries
are 28 bytes and store word addresses relative to physical 0x92000000;
fpga_read_reg multiplies those addresses by four.

| Register | Physical Address | Semantics |
|---|---|---|
| SPA_IND_CMD | 0x921d4014 | Address [21:0], RAM ID [24:22], read bit 27 |
| SPA_IND_STATUS | 0x921d4018 | Bit 0: access done/ready |
| SPA_IND_DATA0 | 0x921d401c | First data word |
| SPA_IND_DATA1..5 | 0x921d4020..0x921d4030 | Remaining data words, stride 4 |

Hash RAM is ID 5, eight entries. Wait for ready, issue
`BIT(27) | (5 << 22) | entry`, wait for ready, read DATA1 then DATA0. Stop on
timeout; a zero data word without completed access is not a valid result.
Only the command register is written for a read transaction. Do not run this
sequence concurrently with vendor SDK accesses to the shared indirect port.

Stock setters poll ready before a write, issue a write command, then write
data words descending, finishing with DATA0. This differs from assuming a
command write is itself a complete table update. Table writes are not yet
implemented in the OpenWrt driver and must not be inferred from this read test.

### Hardware Evidence, 2026-09-08

RAM-only stock shell, bank B mounted read-only, no vendor modules loaded:

* SPA_IND_STATUS initially 1, SPA_IND_CMD initially 0.
* Read command 0x09400000: command readback matches, ready 1, DATA1/DATA0 zero.
* Read command 0x09400001: command readback matches, ready 1, DATA1/DATA0 zero.
* The old candidate at 0x921cc000 still reads 0x11.
* `spa-read --hash` compiled for soft-float ARM and ran twice successfully:
  ready 1, all eight hash entries zero, no timeout. Its upload was validated
  with the gzip CRC before execution. No vendor modules were loaded.

An OpenWrt RAM boot also reported ready 1. A reversible test wrote an inactive
pattern (valid bit clear) to hash entry 7: DATA1=0x100, DATA0=0x16a9. Reading
entry 6 returned zero; reselecting entry 7 returned the exact pattern. Entry 7
was then restored and verified zero. This validates nonzero storage and address
selection, not just a latched data register. No clock changes were needed.

This resolves the address/protocol mistake behind the earlier M4 clock hunt.
It does not by itself establish correct packet classification.
`tools/spa-read.c` provides a bounded eight-entry read diagnostic. It requires
exclusive access, `/dev/mem`, and the H199A; it has no table-write mode.

## IP Protocol Trap Selectors

`SPA_TRAP_PROTOCOLS` is **0x921d41c0**. SDK register IDs 0x1a..0x1d select
four eight-bit fields at shifts 24, 16, 8 and 0. These are IP protocol numbers,
not queue addresses. U-Boot sets 0x11000000: selector 0 is UDP (17), the rest
zero. `spa_set_trap_protocol_type0..3` and spaRegTable establish the layout.

### TCP Experiment, 2026-09-08

On the WiFi-blacklisted warm OpenWrt RAM boot, with rx_heal and rx_credit
disabled for the experiment:

* Baseline 0x11000000: twelve injected UDP controls delivered; injected TCP
  SYN and 64-byte TCP payload frames did not increment the TCP census.
* Expanding protocol-enable registers +0, +4, +0x40, +0x44 to all ones did
  not change that result. All four original values were restored and verified.
* Changing selector 0 to TCP (0x06000000) made TCP payload reach the census.
* Keeping UDP in selector 0 and adding TCP in selector 1 (0x11060000) delivered
  both protocols with the original enable masks. No custom match rule needed.
* Wired SSH executed `uname -r`, HTTP returned the entire 664-byte redirect
  page, and /cgi-bin/luci/ returned its login form (HTTP 403, not an authenticated
  UI test). A 65536-byte binary SSH upload/download matched SHA256
  `7daca2095d0438260fa849183dfc67faa459fdf4936e1bc91eec6b281b27e4c2`.
* Restoring 0x11000000 made a fresh SSH connection time out; restoring
  0x11060000 immediately recovered its banner, within the same boot.
* Five-second TCP tests paced at 5 Mbit/s completed both directions but with
  heavy retransmissions: receiver rates 1.26 Mbit/s host-to-router and
  3.15 Mbit/s router-to-host. This is connectivity evidence, not healthy
  throughput. RX also logged frames with the bridge's own source MAC.

Driver code now programs and verifies UDP/TCP selectors on warm attachment,
and uses the same value during cold initialization. The rebuilt diagnostic image
passed its first full-power-cycle RAM-boot SSH banner check before runtime
adjustment. Its probe logged 0x11060000 and wired SSH executed `uname -r`.
The subsequent 65536-byte upload completed, but the download timed out after
30 seconds. This contradicts any claim of reliable bulk TCP on the new image.
The host used a pinned ARP neighbor; both radios were blacklisted. Recipe
default command line is unchanged. Further cold boots, flash-boot initialization,
ARP, WAN/routing, IPv6 and sustained-load tests remain required.

## Traffic Manager

| Register | Physical Address | Semantics |
|---|---|---|
| BM_ALLOC_IDX | 0x9234800c | Bit 31 valid, index in low 16 bits |
| BM_REQUEST | 0x92348014 | Request bit 0; vendor waits for low two bits clear |
| BM_FREE | 0x92348010 | Buffer release, separate from descriptor release |
| TX_UP_RING | 0x92350050 | Upstream descriptor ring base |
| TX_UP_ENQUEUE | 0x92350054 | Number of descriptors enqueued |
| TX_UP_COMPLETED | 0x92350058 | Low 16 bits subtracted from outstanding count |
| TX_DN_RING | 0x92350060 | Downstream descriptor ring base |
| TX_DN_ENQUEUE | 0x92350064 | Number of descriptors enqueued |
| TX_DN_COMPLETED | 0x92350068 | Low 16 bits subtracted from outstanding count |

Vendor TX uses a shared lock, a software cursor per 1024-entry ring, and the
allocated buffer index. Allocation polls up to 200 times and preserves a
timed-out request for recovery on the next call.

The current candidate implements that handshake and shared TX serialization.
It initializes a software cursor from the warm hardware position, advances it
only on enqueue, and increments outstanding only for submitted frames. It
also linearizes and pads frames before copying. The default buffer override
is now zero (use allocated indices); the legacy forced-index diagnostic remains
available and limits that mode to one outstanding frame. The candidate passed
one cold RAM boot, SSH command execution and a 65536-byte byte-exact round trip
in 0.65 seconds with allocated buffers. Five-second TCP tests paced at 5 Mbit/s
received 1.89 Mbit/s forward and 4.19 Mbit/s reverse, with 199/156 retransmissions.
Driver error/drop counters stayed zero; heavy loss remains unexplained. These
are single-boot results, not evidence of a repeatable throughput improvement.

The host test in `tests/test_eth_tx.py` compiles the actual transmit function
with instrumented stubs to verify locking, cursor wrap, failure accounting,
completion clamping, bounds and padding. It does not validate hardware MMIO
semantics or the buffer manager itself; those still require bench tests.

## Descriptor Fields

Descriptors are 16 bytes. Vendor downstream transmission packs:

| Field | Position |
|---|---|
| Buffer index | Byte 7 bits 7:1 plus byte 8 shifted left 7 |
| Length | Halfword at byte 12, bits 15:2 |
| Ordinary second length field | Word at byte 8, bits 22:9 |
| Payload offset | Byte 11 becomes `(old & 1) | 0x20` for 16-byte headroom |
| Explicit downstream destination | Halfword at byte 2 bits 9:4, `(port + 0x28) & 0x3f` |

The ordinary downstream template has word 3 equal to 3. The vendor's
`test_da_unknown` path uses 2, as does our U-Boot-derived driver. Destination
selection and allocation/ring changes still need controlled wire-level tests.

## Remaining Work

* Derive and test SPA protocol enable, match/hash, and per-port action fields.
* Replace guessed initialization with the H199A reset/ready sequence.
* Validate RX queue layout and interrupt ownership, not just register names.
* Implement shared TX ownership and real buffer lifetime accounting.
* Prove TCP ingress and bidirectional payload delivery on LAN and WAN.

## RX Ownership Candidate

Two independent read-only reviews confirmed that the old poll path cleared and
released a descriptor before its final queue/ingress reads. Whole-descriptor
clearing deterministically erased those fields; other modes could race reuse.
The candidate snapshots queue and ingress before mutation, copies payload before
returning ownership, and uses one completion helper for success and drops.

Every consumed descriptor now counts against the NAPI budget. The old error
paths could consume unbounded work without advancing it. Separate RX deficit
accounting and the now-inert `rx_credit_repay` parameter were removed.

Automatic pool re-priming defaults off: an idle period does not establish that
hardware has relinquished its buffers. The diagnostic remains opt-in and is
not a safe recovery guarantee.

One cold RAM boot passed SSH and a 65536-byte byte-exact round trip in 1.01 s.
The live default rx_heal value was verified zero. Five-second TCP tests paced
at 5 Mbit/s received 1.89 Mbit/s forward and 3.98 reverse, with 300/208 sender
retransmissions. Router TCP InErrs and InCsumErrors were both zero afterwards.
An idle read of the eight vendor-derived RX queue registers showed queue 0
raw 0x0a and the others zero. These results do not establish a throughput fix
or eliminate transient queue overflow; more controlled burst/ownership work
is needed.

Focused host tests exercise the actual completion helper in all clearing modes,
queue preservation, invalid buffer indices and descriptor-before-buffer order.
Structural poll checks guard metadata-before-release and budget placement; they
do not simulate DMA. Release timeout debt and slot-zero exclusion remain open.
