> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# Ethernet — ZX279128S / ZXHN H199A

Driver: `files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c`,
reverse-engineered from vendor U-Boot. No datasheet, no vendor GPL source.
History and withdrawn hypotheses: [`ETHERNET-JOURNAL.md`](../ETHERNET-JOURNAL.md).

## 2026-11-11: Linux forwarding and VLAN qualification

The owner's jack test established LAN1=`eth2`, LAN2=`eth1`, LAN3=`eth0`,
WAN=`eth3`. Q passed IPv4 traffic on all three LAN ports; LAN1 and LAN2 also
passed exact 32 MiB uploads and downloads through WAN with a software LAN bridge.

Broader testing exposed a real isolation gap: Q delivered IPv6 multicast to
Linux but flooded unicast IPv6 arriving on WAN onto LAN without delivering it
to the IPv6 stack. Hardware VLANs 0/1 admitted every port, learning and flooding
remained enabled, and the TX path ignored the requested netdev's physical port.
The earlier IPv4 TCP/NAT results did not qualify this behavior.

Candidate S adds a Linux-controlled forwarding baseline:

- Raw TX selects `0x28 + MAC index` in descriptor word0[25:20], paired with
  word3 control value3. Separate runtime WAN/LAN2 trials each sent 125 MB at 100 Mbit/s
  and confined ARP broadcasts to the intended side.
- Probe disables and verifies MAC ingress before changing classification.
  Physical GE learning is disabled; forwarding masks exclude every other GE
  port; unknown unicast is trapped to CPU; inherited ordinary FDB entries are
  cleared with the vendor's completion check at BRG+0x190 bit0.
- The stock DISNONE admission recipe and valid/unmodified rows for all 4096
  VLAN IDs permit software VLAN handling. Other register fields and VLAN data
  words are preserved and read back. No CLA/PP-PM domain was added to this path.

S boots read-only and passes routed IPv4 and IPv6 pings. Exact 32 MiB transfers
pass both directions over IPv6 and between LAN VLAN 100 and WAN VLAN 200.
The LAN capture shows VLAN 100 tags, and both host VLAN interfaces count the
payload. Raw experimental-EtherType probes for peer-addressed unicast, unknown
unicast, broadcast and multicast do not cross WAN/LAN in either direction.
The earlier WAN IPv6 leak is absent. Drops from these deliberately unsupported
raw probes must not be confused with data-transfer errors.

This remains RAM qualification with forced datapath initialization. A normal
boot, additional cold/warm repetitions, all-port testing on the final image,
and long mixed-load qualification remain open.

### Q performance baseline

These 20-second TCP tests used the original untagged LAN3/WAN path before the
S isolation fix. They are not final-image performance claims.

| Mode | Upload Mbit/s | Download Mbit/s |
|---|---:|---:|
| Routing, 100 Mbit/s offered | 100.02 | 99.98 |
| Routing, 250 Mbit/s offered | 250.00 | 249.98 |
| Routing, 500 Mbit/s offered | 426.38 | 439.51 |
| NAT, uncapped | 393.30 | 418.49 |
| NAT + software flowtable, uncapped | 433.49 | 442.29 |
| Routing with receive steering to CPU 1, uncapped | 345.23 | 312.27 |

The high-rate baseline saturates CPU 0 while CPU 1 is mostly idle. Steering
receive processing to CPU 1 reduced throughput and was reverted. WAN SYN capture
establishes NAT; live conntrack OFFLOAD flags and two slow-path packets per
test establish software offload. Hardware offload is not implemented, and
gigabit forwarding has not been demonstrated. ARM32 compatibility byte counters
wrap; the short-run summary records modulo2^32 deltas explicitly.

The first gated step toward hardware offload, a packet-processor table-access
layer (CLA/PM indirect ports, PM/ACL DRAM tables, read-only debugfs), is in the
tree behind `CONFIG_ZX279128_PP_TABLES`, off by default and not hardware-qualified.
See [`PP-OFFLOAD.md`](../PP-OFFLOAD.md) for the evidence and the qualification steps.

### Debug/release and parser checks

Debug controls now follow `CONFIG_ZX279128_ETH_DEBUG`, whose default is off.
Both ARM objects were compiled: the diagnostic object has a parameter table;
the release object has none and does not advertise experimental parameters.
The build checks its merged config and compiled object. Release builds now
always rebuild the datapath; warm-attachment and skip paths require the debug
configuration. Before reset and again after reset, initialization disables all
four MAC gates, TM admission and the buffer manager, then checks their known
enable bits. A failed check aborts probe before publishing interfaces. Host C
tests inject gate failures and exercise a warm bootloader state with a nonzero
TX cursor. The release ARM object passes the debug-symbol check, but the final
release profile still requires a hardware boot and data regression.

RX diagnostic classification checks Ethernet/IP bounds, IPv4 header length,
IP total length and ICMP length/fragmentation before reading fields. Actual-C
guard-page tests cover truncated input and IPv4 options. These diagnostics do
not modify packet contents or delivery decisions.

## 2026-11-10: qualification and RX correctness

Wired SSH, routed TCP, NAT and software flow offload now pass bounded hardware
tests. Candidate C sustained 99.994 Mbit/s for 60 seconds while reading the
corrected rootfs and firmware, with matching hashes and no NAND transport
errors. NAT tests delivered about 100 Mbit/s in both directions. A WAN capture
verified source translation; conntrack `OFFLOAD` flags and unchanged slow-path
forward counters verified software flow offload. These paced tests do not
establish gigabit throughput, hardware offload, every jack or a long soak.

Candidate J corrects two further RX defects:

- `napi_alloc_skb()` already reserves IP-alignment headroom. A second reserve
  misaligned network headers; allocation now uses the actual frame length.
- `napi_complete_done()` can flush GRO and forward packets synchronously.
  It now runs outside the driver's IRQ lock. An explicit RCU section protects
  the callback tail, and final-port stop waits through `synchronize_net()`.
  Pending queue state is captured before completion so a newly scheduled poll
  cannot race the previous callback's queue inspection.

Actual-C models cover alignment, deferred GRO delivery, completion/stop
interleaving and queue changes after ownership release. The corrected allocator
model fails with the previous double reserve. Independent review found no
remaining blocker in this change. J's hardware qualification is pending;
the WiFi hang also occurred with GRO bypassed, so the completion fix alone
is not established as its cause.

## Historical verification note, 2026-09-08

The `rx_heal` and `/proc/zx_eth_reprime` bulk-free paths have been removed.
They could return indices still owned by hardware; an idle or stalled link
does not make such returns safe. Historical experiments below are not current
recovery instructions. See [the IRQ architecture audit](../TM-IRQ-ARCHITECTURE.md)
for the verified queue model and remaining initialization failures.

Historical tests below demonstrated per-port RX and bridging, but recent wire
captures found stale U-Boot ACKs and malformed Linux ARP lengths. A subsequent
vendor-derived selector fix restored wired SSH and TCP payload in a runtime
trial, and SSH on the first rebuilt cold RAM boot. Bulk transfer then timed out;
reliable throughput and routed TCP are not established. The RX descriptor leak
was fixed; burst-overrun
recovery remains open. Do not read the earlier throughput results as final
end-to-end throughput guarantees.

The stock vendor modules are now available for analysis. Their SPA indirect
interface is at **0x921d4000**, with RAM ID shifted by **22**, not the sibling
layout used in older experiments. See [the register model](../ZX279128S-DATAPATH.md)
for verified fields, OpenWrt table readback and TCP selector tests.

## Hardware

| Block | Address | Notes |
|---|---|---|
| MAC | `0x92200000` | stride `0x40000` |
| MDIO | `0x9a101000` | separate node |
| GE PHYs | MDIO addr 10–13 | four, ID `84b9:5031` |
| NPP (packet processor) | `0x921c0000` | sub-block semantics under vendor-code review |
| SPA | `0x921d4000` | vendor SDK base; previously called queue config |
| TMC / TMQ | `0x92340000` / `0x92350000` | traffic manager |
| BM (buffer manager) | `0x92348000` | `BM_FREECNT` at `+0xdc` |
| Buffer pool | `0x41000000` | 4 MiB, reserved in DT |
| **GE PHY block** | **`0x9b000000`** | **four windows, stride `0x100000`, IRQs 0x27-0x2a — never mapped by this driver** |
| **IDM** | **`0x921c8000`** | **`status = "disabled"` in the stock DTS; a distinct block, not the NPP gap round 166 took it for** |
| **CRM x3** | **`0x94000000` / `0x94100000` / `0x94200000`** | **clock/reset; `CRM0+0x08` is a clock-enable word (proved by `pcie-zx279128.c`)** |

> The last three rows come from the **stock vendor DTS** in the `h199a-firmware`
> dump (`extracted/h199a-stock.dts`), which names `gephy@9b000000`,
> `idm@921c8000`, `tm@92340000`, `pp@92380000` and `topcrm@94000000`. None of
> the three is touched by this driver today. The four per-port `gephy`
> interrupts also raise the possibility of a **real RX interrupt**, which would
> retire the 500 µs hrtimer poll.

Descriptors are 16 bytes with bit-packed index/length. The RX ring holds 1024
entries. Slot 0 is still skipped by default, a legacy behavior under review;
TX has its own ring. The buffer pool holds 2048 × 2 KiB. Index 2047 remains
withheld from the initialized free list, but TX now defaults to allocated buffers.

## ★ Four port netdevs, real PHYs, real MACs — SHIPPED 2026-09-06

The driver now registers **one netdev per physical port**, named from the port
index so `eth0..eth3` always mean `mac0..mac3` (and MDIO address `10..13`),
regardless of which port the device tree binds. Each netdev drives its **own
PHY** and carries a stable unique MAC. `split_ports` defaults on.

Historical measurement before factory addresses were reassigned to both radios
(the current allocation is documented below):

```
port 1 -> eth1 (descriptor id 2) 02:00:00:00:00:04
port 2 -> eth2 (descriptor id 3) 02:00:00:00:00:05
port 3 -> eth3 (descriptor id 4) 02:00:00:00:00:06

eth0 carrier=0 mac=02:00:00:00:00:03     eth2 carrier=1  Link is Up - 1Gbps/Full
eth1 carrier=0 mac=02:00:00:00:00:04     eth3 carrier=1  Link is Up - 1Gbps/Full
```

The two ports reporting carrier are exactly the two U-Boot independently
announces as `mac 2 phy status changed: 1000M full-duplex` and `mac 3 ...`. Link
state is now *discovered* rather than assumed, which is what retires `ETH_PORT=`
from `build.sh`.

### ✗ RETRACTED: "`all_ports` compensates for a bound port with no cable"

`HANDOFF.md` said the datapath "still works, because `all_ports` enables every
MAC", and told the reader not to treat `eth0: Link is Down` as a fault. **That is
wrong.** Measured with the driver bound to `mac1` and the cable on `mac2`:

```
device -> workstation : 8 packets transmitted, 0 received, 100% packet loss
workstation -> device : 4 packets transmitted, 0 received, 100% packet loss
                        (Destination Host Unreachable - ARP never resolved)
```

Enabling `MAC_CTRL_EN` on every port makes the other ports *ingress*; it does not
give the bound netdev a working path when its own PHY is down. After the per-port
change, with no configuration and no cable moved, the same host gets:

```
6 packets transmitted, 6 received, 0% packet loss, rtt min/avg/max 1.894/5.632/9.531 ms
```

### Where the MAC addresses come from

The `tag` partition (`mtd1`) holds four sequential factory MACs as TLV records at
`0x1e + 0x18*n`, each preceded by its two-byte index (`00 01`, `01 01`, `02 01`,
`03 01`). Verified against a full 128 MiB dump: exactly four binary occurrences
of the OUI, no ASCII copies. They are exposed as `nvmem-cells` on the partition
node and consumed with `of_get_ethdev_address()`.

The current DTS allocates record 0 to 2.4 GHz, record 1 to 5 GHz, record 2 to
eth0 (and therefore `br-lan`) and, since 2026-11-15, record 3 to eth3, the WAN
jack, so every externally visible address is a genuine factory MAC. The two LAN
member ports eth1 and eth2 derive locally administered addresses from record 2,
setting the local bit and inserting the port index in byte 3's high nibble.
This avoids duplicating the radio MACs. eth0 is the DT-bound port and is probed
first, so record 2 remains the derivation base. On this bench the resulting
Ethernet addresses are `02:00:00:00:00:05` (eth0/br-lan), `06:20:84:1f:87:b5`,
`06:20:84:2f:87:b5`, and `02:00:00:00:00:06` (eth3/WAN). Before this change
eth3 was the derived `06:20:84:3f:87:b5` (normal-X, 2026-11-15). This is
intentional, not an nvmem read failure.

**This is the single source of truth.** `board.d/02_network` deliberately does
*not* set MACs — two independent writers is what made the address
non-deterministic on the dir842 port. Before this the driver called
`eth_hw_addr_random()` for every netdev, so every boot had different addresses.

### Firewall zones

`board.d/02_network` puts `eth0 eth1 eth2` in `lan` and `eth3` (the
vendor-labelled WAN jack) in `wan`, so every port lands in a zone. **A per-port
netdev in no zone is silently eaten by fw4's default `input` DROP while its rx
counters climb** — it reads exactly like a broken datapath.

The `hotplug.d/net/20-zx279128-hairpin` script is **deleted**. It existed because
all four ports shared one netdev; with a netdev per port the bridge can express a
port choice, and hairpin would be a genuine loop.

## ★ PHY / MAC / jack map — MEASURED 2026-09-06

Previously undocumented and *assumed*. Measured directly, from the U-Boot prompt,
by driving the MDIO controller by hand (`mw.l`/`md.l` on `0x9a101000`, the same
register sequence `mdio-zx279128.c` uses) and reading each PHY's BMSR.

| DTS node | MDIO addr | U-Boot "mac N" | BMSR | cabled to |
|---|---|---|---|---|
| `phy0` | 10 | mac0 | `0x7949` | — nothing |
| **`phy1`** | **11** | **mac1** | **`0x796d`** | **the workstation** (`enx00e04c125990`, 192.168.1.100) |
| `phy2` | 12 | mac2 | `0x7949` | — nothing |
| **`phy3`** | **13** | **mac3** | **`0x796d`** | **`tiny`** (the WAN-labelled jack) |

BMSR bit 2 is link, bit 5 is autoneg-complete: `0x796d` has both, `0x7949` has
neither. So **MAC index N corresponds to MDIO address 10+N**, confirmed twice
over — U-Boot independently announced `mac 1` and `mac 3` as
`1000M full-duplex` on the same two ports.

**Instrument validated first** (per this project's standing rule): the same
manual sequence read PHYSID1 = `0x84b9` from all four addresses, matching the
Linux driver's own probe-time scan, before any BMSR value was trusted.

**Which cable is which, discriminated by measurement, not assumption:** with
`tiny`'s `eth0` administratively down, `phy3` dropped to `0x7949` while `phy1`
stayed at `0x796d`. (Note `ip link set … down` on the workstation's r8152 does
**not** drop its PHY, so the test had to be run from the `tiny` end.)

### ★ The port this project has always measured is NOT phy0

The driver attaches `phy0` and only `phy0` (`phy-handle = <&phy0>`), and `phy0`
has **no cable on it**. Every wired measurement in this repository was taken on
the workstation port, which is **`phy1` / `mac1`**.

Two consequences, both immediate:

1. **Under Linux the workstation link is DOWN.** Confirmed on both ends
   simultaneously: the device reports `eth0: Link is Down` and the host reports
   `NO-CARRIER`. Under **U-Boot** the same cable links at 1000M full-duplex and
   TFTP transfers fine. The difference is that phylib registers all four PHYs and
   only `phy_start()`s the attached one; the other three are left suspended, so
   the cabled port's PHY is powered down under Linux and powered under U-Boot.
2. **`docs/INSTALL.md`'s and this file's Ethernet results describe traffic that
   ingressed on `mac1` while the driver drove `mac0`.** That is consistent with
   what this file already documents — the NPP fabric carries frames from any port
   to the CPU through port 0's enabled MAC — but it means "the port is phy0" was
   never true, and the `HANDOFF.md` warning not to assume it was correct.

Whether the workstation cable has always been on this jack or was moved when the
`tiny` WAN link was added on 2026-09-06 is **not established**; only the current
state is measured. Do not retro-fit old results to this map without checking.

## Memory-safety audit of the driver (2026-09-06)

Run against the hypothesis that this port corrupts kernel memory — which would
have tied together the progressive console corruption, the wedge and the shell
hangs in one mechanism. **It mostly does not.** Recorded because a clean result
here redirects the investigation, and because two real defects fell out of it.

**Checked and clean:**

* RX `idx` and `len` decoded from the descriptor **are** bounds-checked
  (`idx >= BUF_COUNT`, `len` outside `[60, 2032]`) *before* `zx_buf()`,
  `memcpy_fromio()` and `zx_bm_free()` ever see them. The millions of zero-length
  descriptors `n_zerolen` counts are rejected safely, not turned into pointers.
* `ze->bufs` is `devm_ioremap_wc(BUF_BASE, BUF_COUNT * BUF_SIZE)` = exactly
  4 MiB, and index 2047 + `BUF_HDR` + the maximum accepted `len` lands exactly on
  the end of the mapping. No off-by-one.
* Every static DMA pointer the driver programs lands inside the 16 MiB `no-map`
  DTS reservation.
* The `dp_users` refcount added this session (shared ring/NAPI/timer across four
  port netdevs) has correct increment/decrement guards, correct teardown order,
  and `netif_napi_add()` exactly once. No double-enable, no use-after-free.

**Two real defects, both fixed:**

1. ★ **The BM fill loop handed the dedicated TX buffer to the RX pool.**
   `datapath_init()` did `for (i = 0; i < BUF_COUNT; i++) writel(i, bm + BM_FREE)`
   while the heal re-prime and the DDR free-list build both stop at
   `BUF_COUNT - 1`. Index 2047 is `zx_tx_buf_idx`, the buffer every transmit
   writes into, so an inbound frame could be placed in it while a TX was landing
   — reintroducing, for that one buffer, exactly the TX/RX aliasing that moving
   TX off buffer 0 was meant to fix. This ran on **every cold boot**. The
   driver's own comment already asserted the invariant this loop was breaking:
   *"Index 2047 is safe because the free list is filled 0..BUF_COUNT-2 and so
   never offers 2047 to RX."*
2. **TX never bounds-checked its buffer index**, though RX always has. It has two
   unchecked sources: `zx_bm_alloc()` returns a raw 16-bit hardware field, and
   `tx_buf_idx` is a writable module parameter. Either could name a buffer past
   the 4 MiB mapping and have `memcpy_toio()` write packet data over the next
   ioremap. Dormant under current defaults; now checked after the override, so
   the check covers both sources.

**Neither explains the console corruption.** Nothing found reaches kernel memory
outside the reserved DMA window or the driver's own MMIO mappings. The one
interface in this driver that genuinely could — `/proc/zx_eth_poke`, an arbitrary
physical read/modify/write — is compiled out unless `BRINGUP=1`, and the images
showing the corruption were all built with it off. So the console problem is not
this driver scribbling on RAM.

## ⚠️ Wedge frequency on 2026-09-06, and one thing NOT ruled out

Across this session the device wedged repeatedly and in the same shape every
time: the wired path goes to 100% loss, **and the serial console accepts
keystrokes without executing them** while kernel timers keep printing. Commands
queue up in the tty buffer un-run. Only a power cycle recovers it.

It happened after Wi-Fi client traffic (twice), after a `wifi up` (twice), and at
least once on a boot where the Wi-Fi driver was never loaded at all — so it is
not exclusively a Wi-Fi phenomenon. It is almost certainly the same wedge this
file already documents; what is new is only how often it turned up.

**Not ruled out, and stated because it would be convenient to omit:** this
session refactored `ndo_open`/`ndo_stop` so the shared datapath (RX ring, NAPI,
poll timer) is reference-counted across the four port netdevs instead of being
owned by one. That is a structural change to exactly the code path a wedge lives
in. Arguments that it is *not* the cause: the wedge is documented long before it,
the same console-hangs-but-timers-print signature was produced earlier the same
day on the OLD image, and the wired datapath passed 0% loss repeatedly after the
change. But no controlled A/B was run, so it is not exonerated either. Anyone
chasing the wedge should build with `split_ports=0` as a control arm before
assuming the refactor is innocent.

## ★★ One rule explains all of it: TCP PAYLOAD never crosses the wired path (2026-09-06)

Routing tests through the device, with the wired jack as the "internet" side and
a real 5 GHz client as the LAN, pin the defect down to a single sentence.

**Control — ICMP routes and NATs perfectly:**

```
Wi-Fi client 192.168.2.146  ->  wired host 192.168.1.100
4 packets transmitted, 4 received, 0% packet loss, ttl=63    <- one hop, NAT'd
```

**TCP handshakes cross:**

```
nc -vz 192.168.1.100 22 : Connection to 192.168.1.100 22 port [tcp/ssh] succeeded!
```

**TCP payload does not, in either direction:**

```
iperf3 -c 192.168.1.100 -t 5      (data in on Wi-Fi, out on the wire) : 0 bytes, timeout
iperf3 -c 192.168.1.100 -t 5 -R   (data in on the WIRED port)         : 0 bytes, timeout
```

Both connect — `Connecting to host 192.168.1.100, port 5201` — and then transfer
nothing at all before the timeout.

### The unified rule

Everything this project has recorded about TCP is one rule:

> **A TCP segment carrying payload does not survive the wired datapath.**
> Payload-free segments (SYN, SYN-ACK, ACK) do.

Check it against every observation:

| observation | explained? |
|---|---|
| `tcp_data` has never once been non-zero, over hundreds of samples | yes — that counter *is* this rule |
| `tcp_bare` climbs for device-opened flows | yes — payload-free |
| an unsolicited inbound SYN never arrives | ✗ **not** explained; a SYN is payload-free. This remains a separate, unexplained sub-case |
| outbound TCP from the device works, payload included | yes — that is TX, and TX was never the problem |
| a handshake crosses the router but the transfer stalls | yes |
| **LuCI and SSH work from a Wi-Fi client** | yes — that traffic never touches the wired path at all: client → AP → bridge → CPU |

So the earlier framing — "no SSH, no LuCI, no `opkg`" — was a *consequence*
mistaken for the rule. The rule is about payload on the wire, and it is why
management works over Wi-Fi: those bytes never enter the `zx279128-eth`
descriptor ring.

### What this means for using the device

* **As a Wi-Fi access point that clients use to reach the device itself
  (LuCI, SSH, DNS, DHCP): it works.**
* **As a router carrying real traffic: it does not**, on any path that crosses a
  wired port with TCP payload — which is essentially all internet traffic. ICMP,
  UDP, ARP, DHCP and DNS all route and NAT correctly.

That is a sharper and more useful statement than "inbound TCP does not
terminate", and it moves the target: the thing to fix is not a listening socket
or a firewall, it is why a descriptor carrying a payload-bearing TCP segment
never reaches the driver.

## ★ Inbound TCP is a WIRED-PATH defect — LuCI works over Wi-Fi (2026-09-06)

For most of this project's life the headline limitation has been stated as "TCP
to the device does not terminate, so there is no SSH, no LuCI and no `opkg`."
That is **too broad**. It is true of the wired path only.

Wi-Fi frames never enter the `zx279128-eth` descriptor ring at all: mt76 receives
by its own PCIe DMA on its own NAPI. So the NPP classifier that eats unsolicited
wired SYNs is simply not in that path. **Nobody had tested it.**

Measured from a real 5 GHz client associated to the device's own AP, both
interfaces bridged into `br-lan`:

```
wlan0 inet 192.168.1.146/24            <- lease from the device's dnsmasq
ping 192.168.1.1  : 4/4, 0% loss, avg 4.8 ms
nc -vz 192.168.1.1 22 : Connection to 192.168.1.1 22 port [tcp/ssh] succeeded!
curl http://192.168.1.1/ : HTTP=200 time=0.77s, and the body is LuCI's HTML
```

Simultaneously, from the wired host on `eth2`, ICMP was clean (0% loss) while
`nc -vz 192.168.1.1 22` and `curl http://192.168.1.1/` both timed out. Same
device, same second, same listening daemons — the transport works on one path and
not the other.

So the accurate statement is: **inbound TCP does not terminate over Ethernet; it
does over Wi-Fi.** LuCI, SSH and `opkg` are reachable over the 5 GHz AP. That is
why `luci` is now in `seed.config`.

### ⚠️ But it is not yet dependable, and the reason is not TCP

Three trials were run. **Only the first completed.** In trials 2 and 3 the client
associated and (in trial 3) got its DHCP lease, and then ICMP to the gateway went
to 100% loss before the TCP tests ran. Each time the device had **wedged**: the
wired path died *and the console shell stopped executing commands* while kernel
timers kept printing. Only a power cycle recovered it.

So: the TCP block is a wired-path defect and Wi-Fi genuinely bypasses it — that
part is solid, and it is supported by the wired/Wi-Fi contrast taken in the same
session. **Whether you can rely on the device staying up long enough to use LuCI
is a different and currently unsatisfied question.** Do not read this section as
"management works now"; read it as "the classifier is not what stands in the way,
stability is."

## ★ The TCP defect, characterised — 2026-09-06

Once the driver was pointed at the port that actually has a cable
(`reg = <0x92240000 …>`, `phy-handle = <&phy1>`; see the map above) the link
came up under Linux for the first time:

```
zx279128-eth 92240000.ethernet eth0: Link is Up - 1Gbps/Full - flow control off
```

ICMP is clean in both directions (4/4, 0% loss, rtt 2.6-18 ms). With
`CONFIG_ZX279128_ETH_DEBUG=y` the in-driver census — which increments ~75 lines
**upstream** of `netif_receive_skb`, and is therefore immune to `firewall4` —
gives this, **replicated across two independent cold boots**:

| case | user-visible | `tcp_bare` | `tcp_data` |
|---|---|---|---|
| baseline after ICMP | — | 0 | 0 |
| **inbound** connect to `:22` (dropbear `LISTEN`, fw4 `input_lan` accepts) | times out | **0, unchanged** | 0 |
| **outbound** connect + send payload | **works, `rc=0`, host got the bytes** | **0 → 5** / **0 → 3** | 0 |
| host sends payload **down an established flow** | device reads **0 of 570 bytes** | 3 → 8 | **0** |

### What that pins down

1. **Transmit is fine.** The device sends TCP, payload included, and the peer
   receives it. TX was never the problem.
2. **Payload-free TCP *does* reach the CPU** — but only for a flow the device
   itself opened. `tcp_bare` climbs by exactly the SYN-ACK + ACKs of that
   connection. This is the first time this project has seen `tcp_bare` move on a
   non-`cspboot` boot, which **retires the "boot-path-specific" caveat**: the
   behaviour is reproducible on a plain TFTP boot once the right port is driven.
3. **An unsolicited inbound SYN never reaches the CPU at all.** It is payload-free,
   exactly like the SYN-ACK that *does* arrive. So "payload-bearing TCP is
   dropped" is **not** the whole rule — the discriminator is **flow state**, not
   payload alone.
4. **No TCP segment carrying payload has ever reached the CPU.** `tcp_data` is
   still 0 after two more independent runs, now with a validated instrument, a
   healthy 1 Gbps link, and an *established* connection whose ACKs were arriving
   at the same time. This is as clean a demonstration as the hardware allows:
   the connection is up, the peer is sending, the ACK stream is being received,
   and the data is not.

### Why this matters for the fix

Points 2 and 3 together are new and they are the useful part. Two payload-free
TCP segments — an inbound SYN and an inbound SYN-ACK — get **opposite**
treatment. The only thing separating them is whether the device had already
opened that flow. That is precisely the shape of a **flow accelerator**: the
parser/classifier steers a packet to the CPU exception path only when it matches
established state, and everything else takes the hardware forwarding path and is
consumed before the DMA engine. It matches the sibling ZX279133 driver's model
(`research/ZX279133-SIBLING-DRIVER.md`) and it means the target is the SPA
classifier's per-port tables, not a single TCP-flags mask.

**Regime and limits, stated plainly.** These runs are TFTP boots, so
`datapath_init()` is skipped (`datapath warm - init skipped`) and the buffer pool
is never primed by us: `nocredit` climbs steadily and the datapath eventually
wedges (`heal: … re-priming pool (attempt 10)`, then 100% loss). Every result
above was taken from a freshly booted, still-healthy device, and the wedge is a
separate defect (see below). `force_dp_init=1` was tried and is **not** a way
around this — it is documented in the driver as tearing down a working
bootloader configuration, and in three attempts it produced a dead datapath and
a boot that hung, exactly as the source comment warns.

## ★ M3 block probe — 2026-09-06 (TFTP boot, `datapath_init` skipped)

Read-only, via `/proc/zx_eth_poke` on a `CONFIG_ZX279128_ETH_DEBUG=y` image.

| address | value | meaning |
|---|---|---|
| `0x921c0080` | **`0x00000000`** | sibling's `GLOBAL_INIT_DONE`; expected `0x1fd` |
| `0x921c0084` | `0x00000000` | |
| `0x921c00b8` | `0x00000000` | sibling's `SPA_AUTO_GATE` |
| `0x921cc000` | `0x00000011` | SPA global config — real content, as before |
| `0x921cc054/58/5c` | `0` / `0` / `0` | `IND_CMD` / `IND_STATUS` / `IND_DATA` — port not ready |
| **`0x9b000000`** | **`0x00003988`** | **gephy port 0 — decodes** |
| `0x9b000004` | `0x00000038` | distinct from +0x00, so a real register file |
| `0x9b100000` / `0x9b200000` / `0x9b300000` | `0x3988` each | gephy ports 1-3, all decode |
| **`0x921c8000`** | **`0x03c36766`** | IDM |
| **`0x921c8088`** | **`0x00290504`** | sibling's `RX_RELEASE` offset — non-zero |
| `0x921c8100` | `0x00000000` | sibling's `BP_REFILL` offset |
| `0x921c8004` | `0x00000000` | |

Three results worth acting on:

1. ★ **Global init has not completed.** `NPP+0x80` reads `0`, not `0x1fd`. On the
   sibling, `np_reset_prepare()` pulses a SIPC reset and then polls exactly this
   word for `(v & 0x1fd) == 0x1fd`, and **every later block assumes it passed** —
   including the SPA indirect port. So `IND_STATUS` bit 0 never setting is
   *downstream* of this, and **the clock-gate hunt was premature**: the thing to
   reproduce is the init/reset sequence, not a gate. (Measured on a TFTP boot
   where `datapath_init()` is skipped; it must be re-read on a flash boot, where
   it runs, before this is generalised.)

2. ✗ **Round 166's "`0x921c8000` is a non-decoding window" is RETRACTED.** That
   conclusion came from two different 4 KiB pages returning identical values.
   Within the page, different offsets now return **different** values
   (`0x03c36766`, `0x00290504`, `0`, `0`), which is a decoding register file, not
   an alias. The stock vendor DTS agrees: it declares `idm@921c8000` as its own
   block (`status = "disabled"`), not a gap in the NPP node. And `+0x0088` — the
   sibling's `RX_RELEASE` — holds real content, which is a direct lead for the
   wedge.

3. **The `gephy` block at `0x9b000000` is clocked and decoding on all four
   ports**, and this driver has never mapped it. Offset `+0x00` reads `0x3988`
   identically on all four, so it is not a link-status word; the per-port
   registers still need mapping. The stock DTS gives it four interrupts
   (0x27-0x2a), which is the most promising lead for replacing the 500 µs
   hrtimer poll with a real RX interrupt.

## ✗ RETRACTED — "NPPT global init never completed" (2026-09-06, later the same day)

The section below concludes that `NPP+0x80` reading `0` instead of `0x1fd` means
global init has not run, and treats everything downstream as blocked behind it.
**That conclusion is withdrawn.** The premise does not survive its own control.

`NPP+0x80` was read **from the U-Boot prompt, immediately after a 2.6 MB TFTP
transfer completed at 9.8 MiB/s** — i.e. on a datapath that had just demonstrably
worked, at thirteen times the throughput this driver has ever achieved:

| address | U-Boot, working datapath | our kernel |
|---|---|---|
| `0x921c0080` | **`0x00000000`** | `0x00000000` |
| `0x921cc080` | **`0x00000000`** | `0x00000000` |

Instrument validated first, per the standing rule: `0x921c8000` read
`0x03c36766`, `0x921cc000` read `0x00000011` and `0x921c8088` read `0x00290504`
from U-Boot, all matching the values recorded from Linux.

Two things follow.

1. **`0x921cc080` had never actually been read.** `research/ROUND-251-TCP-NPPT-PLAN.md`
   named it "the safe, decisive first experiment", but the read that was performed
   and recorded below was at `0x921c0080`, the other window. Both are now read and
   both are 0, so the choice of base was never the error.

2. **The `0x1fd` expectation is a ZX279133 property that does not transfer to this
   SoC.** The vendor's own bootloader runs a fast, wedge-free datapath with that
   word at zero. "Global init never completed" therefore describes nothing that is
   actually wrong, and the SPA indirect port's permanently-not-ready bit needs a
   different explanation.

What survives from the section below is the elimination table — `datapath_init()`,
the fabric reset, `SIPC_CFG`, `SIPC_RX_GAP` and the two CRM0 bits are all still
eliminated as levers. What does not survive is the framing that made `0x1fd` the
gate everything else waits behind.

### The buffer-manager comparison this read came from

The same session dumped the BM block from the U-Boot prompt straight after that
TFTP — i.e. a datapath that had just demonstrably worked — and compared it against
our own state on a **cold** flash boot, which is the regime where the buffer
manager starves. Only the differing offsets are shown; `BM+0x40..0x4c` are omitted
because they move with traffic on both sides and are counters, not configuration.

| offset | U-Boot (works) | Linux (cold) | what `datapath_init()` writes |
|---|---|---|---|
| `+0xa8` | **`0x00000722`** (1826) | `0` | **nothing — we never touch it** |
| `+0xb0` | `0x00000722` | `0x00000007` | nothing |
| `+0xb8` | `0x00000721` | `0x00000805` | nothing |
| `+0xc8` | **`0x00000400`** (1024) | **`0`** | **`0x00000200` — and it reads back 0** |
| `+0xd8` | **`0x00006000`** | `0x00004000` | **`0x00004000`** |
| `+0xdc` | **`0x50000111`** | `0x00000111` | nothing (we only read it) |
| `+0x90` | `0x00000e44` (3652) | `0x00000007` | nothing |
| `+0x98` | `0x00000e43` (3651) | `0x00000805` | nothing |

Three are directly actionable:

* **`BM+0xc8`: we write `0x200`, it reads back `0`, and the working reference holds
  `0x400`.** A configuration write that does not stick is not a tuning question —
  either the register is gated behind something we have not done, or `0x200` is not
  an accepted value. This is the clearest defect in the table.
* **`BM+0xd8`: we deliberately write `0x4000`; the working state is `0x6000`.** We
  are writing a different value from the reference, and the value we chose has no
  recorded justification.
* **`BM+0xa8` = `0x722` in U-Boot and `0` in ours** — and 1826 also appears at
  `+0xb0`, minus one at `+0xb8`, and again at `TMQ+0x68`/`+0x6c`. A quantity that
  consistent across four registers is a pool depth, and we set none of them.

Note also `BM+0xdc`, the word `zx_bm_free()` decodes as free credit with
`(v >> 3) & 0x3f`. Both sides yield 34 by that formula — but U-Boot has
`0x50000000` set in the top bits and we do not. Our decode masks that away
entirely, so if those bits are a validity or ready flag, the driver has been
reading a credit value it should have been rejecting.

All three are testable at runtime through `/proc/zx_eth_poke` on a `BRINGUP=1`
build, with no reflash. Alternate arms and cold-boot each trial.

## M4 attempt — global init is not reachable from software yet (2026-09-06)

`NPP+0x80` never leaves `0x00000000`. What was tried, all with `/proc/zx_eth_poke`
on the same boot, each verified by read-back:

| action | result |
|---|---|
| `/proc/zx_eth_reinit` — run the driver's **full** `datapath_init()` at runtime | all stages logged (`npp bring-up done`, `port attach 00000000 -> 0000000f`, `packet processor bring-up done`); `NPP+0x80` **unchanged at 0** |
| fabric reset `0x92000008` = 0 then `0xffffffff` | toggles correctly; `NPP+0x80` **unchanged** |
| `SIPC_CFG` `0x921c4000` bits[2:0] 7 → 3 (sibling's mode) | **write accepted**, reads back `0x0800001b`; `NPP+0x80` unchanged |
| `SIPC_RX_GAP` `0x921c4010` := `0x1042` | **write REJECTED**, stays `0x00000000`, before and after a fabric reset |
| CRM0 `0x94000048` bit 13, then bit 16 | **both writes rejected**, register stays `0x0ffedfff` |

### What that establishes

* ★ **The sibling's low NPPT offsets map 1:1 into our first window.**
  `SIPC_CFG` at NPPT`+0x4000` → `0x921c4000` holds `0x0800001f` — real content,
  with bits[2:0] = 7 where the sibling sets 3 — and it takes writes. Together
  with `GLOBAL_INIT_DONE` at `+0x0080` and `SPA_AUTO_GATE` at `+0x00b8`, the
  first `0x8000` of the register file transfers directly. It is the **high**
  offsets (`0x180000` XMAC, `0x280000` IDM, `0x2c0004` SYS_SOFT_RESET) that do
  not — they collide with our MAC ports 2 and 3.
* **`datapath_init()` is not the missing step.** It runs to completion and
  changes nothing about global init, so the gap is a *different* sequence, not a
  bug in what we already do.
* **`SIPC_RX_GAP` is not writable** while `SIPC_CFG` in the same window is. On
  the sibling that register is written *after* a reset pulse on
  `SYS_SOFT_RESET`, which is one of the offsets that does **not** map. So the
  most likely missing piece is our SoC's equivalent of that reset — and it is
  **not** `0x92000008`.
* **CRM0 `0x94000048` is not the gate.** Its value `0x0ffedfff` is bits 0-27 set
  except 13 and 16, which looked exactly like two disabled gates in the register
  the sibling uses for NPPT clocks. Both bits are **hardwired**: writes are
  silently dropped. So the sibling's `+0x48` gate map does not transfer, which
  is the same conclusion the PCIe driver's `CRM0+0x08` CLKEN word already
  implied.

**Where a fresh attempt should start:** find the PON/NPP *reset* controller. The
stock DTS puts `0x94000000`, `0x94100000` and `0x94200000` all inside the `pon`
node's `reg`, and `pcie-zx279128.c` already proves CRM1 `+0x70`/`+0x74` are a
config/reset pair for a different domain. Diffing all three CRMs between a
bootloader-initialised (TFTP) boot and a cold flash boot is the cheapest way to
name the word, and it does not require guessing from a foreign SoC.

## ★ M7 multi-port: ingress SOLVED, egress still not — 2026-09-06

Second live port for the first time: `tiny` cabled to the `phy3`/`mac3` jack, its
`eth0` pulled out of `br0` and isolated in a netns at `192.168.1.50/24`
(bench-isolated, per the rule `dir842/bench-wan-emu.sh` sets). Driver bound to
`mac1`.

| step | tiny link | device `rx_packets` |
|---|---|---|
| driver on mac1, mac3 untouched | **carrier 1, LOWER_UP** | **0** after 5 pings |
| after `/proc/zx_eth_reinit` (port-attach mask `00000000 -> 0000000f`) | carrier 1 | **0** after 5 more |
| **after `MAC3+0x00 \|= 1`** (`0x00bb6002 -> 0x00bb6003`) | carrier 1 | **0 → 6** |
| repeat | carrier 1 | **6 → 12**, and the device learns `192.168.1.50` in its ARP table |

### ★ Per-port `MAC_CTRL_EN` is what gates ingress

This is a controlled result: tiny's link was **already up** for both zero-packet
rounds, so link state is not the variable, and `datapath_init()`'s port-attach
mask `|= 0xf` — the register previously assumed to do this — **did not** enable
ingress on its own. Only setting bit 0 of that port's own `MAC_CTRL` did.

Two documented claims are corrected by this:

* ✗ *"Ingress from another port works because the second host's frames are
  broadcast and reach the CPU through the fabric via port 0's enabled MAC."*
  **Not reproducible here.** With only `mac1` enabled, frames from the `mac3`
  jack — ARP broadcasts included — produced **zero** `rx_packets`.
* Note `MAC3+0x00` read back `0x00bb6002` *before* we touched it, i.e.
  `datapath_init()` really does configure all four MACs (see "How much is
  actually missing"); the enable bit is the only per-port piece it omits.

### ✗ `tx_w1` bits [23:16] is NOT the egress destination-port field

Predicted from the sibling, where the destination port is a small integer at
`metadata0[21:16]`. Swept with values 0, 2, 3, 5, 6 while pinging tiny with a
static ARP entry. **tiny's `rx_packets` stayed at 155 for every value.**

**The first run of this test was invalid and is discarded.** It used `tcpdump`
inside the netns and reported "0 frames" — but a control run showed the capture
recorded **0 frames of tiny's own outgoing pings**, so the instrument never
fired. The result above is from interface counters instead, validated in the
same breath: tiny's `tx_packets` moved 88 → 91 for three pings while
`rx_packets` did not move at all.

So egress remains bound to whichever MAC the driver drives, and the destination
port is **not** selected by that descriptor field. Word 0 and bytes 4-6 are still
unswept.

### Unproven: the `phy_keepalive` change

A `phy_keepalive` module parameter was added to resume unattached PHYs by
clearing `BMCR_PDOWN`. On the test boot it reported **0 PHYs woken** — none had
that bit set — so whatever powers those ports down, it is not `BMCR_PDOWN`, and
**the change cannot be credited** with tiny's carrier appearing. The more likely
explanation is autonegotiation completing after the netns move. The parameter is
kept (default on, harmless, and it logs) but it is an untested experiment, not a
fix.

## ★★ TWO PORTS WORK CONCURRENTLY — "single-port by construction" is REFUTED (2026-09-06)

Setup: driver bound to `mac3`/`phy3` (`ETH_PORT=3` equivalent DTB), `tiny` on the
mac3 jack at `192.168.1.50`, the workstation on the mac1 jack at
`192.168.1.100`. One netdev, `eth0`, in `br-lan`.

| step | workstation (mac1) | tiny (mac3) |
|---|---|---|
| fresh boot, only mac3 bound | 100% loss, ARP fails | **4/4, 0% loss** |
| **after `MAC1+0x00 \|= 1`** (poke, one bit) | **4/4, 0% loss** | 4/4 |
| **concurrent, 6 pings each at once** | **6/6, 0% loss** | **6/6, 0% loss** |

**Both physical ports carried full bidirectional traffic at the same time, from a
single netdev, with nothing but `MAC_CTRL_EN` set on each.**

### What this overturns

* ✗ **"This is a single-port driver by construction."** Refuted. Two ports ran
  concurrently with a one-bit change per port.
* ✗ **"Egress always leaves port 0 / the bound port."** Refuted. Bound to
  `mac3`, replies still reached the workstation on `mac1` correctly. The fabric
  delivers a CPU-injected frame to the port its destination MAC lives on — so
  the NPP appears to do its own MAC learning, and **the "hard fourth piece",
  per-frame egress steering, is not needed for a port to work.**
* The earlier reading in this file that egress was confined to the bound MAC came
  from a run where the datapath had already degraded (`nocredit` ~12000,
  device→host ping also failing). Retested from a fresh boot, it does not hold.
  **Do not trust any datapath result taken more than a few minutes into a TFTP
  boot.**

### ★★ Port-to-port forwarding WORKS — the device is a 2-port switch (2026-09-06)

The bridge-hairpin fix, replicated:

```
echo 1 > /sys/class/net/eth0/brport/hairpin_mode
```

| path | result |
|---|---|
| tiny (mac3) → workstation (mac1), *through* the device | **5/5 then 6/6, 0% loss** |
| workstation (mac1) → tiny (mac3), fresh ARP | **6/6, 0% loss** |

Hairpin is normally wrong — on an ordinary board it is a forwarding loop, which
is why it defaults to off. Here it is **required**, because all four GE ports sit
behind one netdev, so the bridge sees a single port and will not send a frame
back out the port it came in on. With hairpin on, the bridge returns the frame to
`eth0` and **the NPP fabric delivers it to the correct physical port by
destination MAC** — the same MAC-learning behaviour that makes egress work
without per-port steering.

Shipped as
`files/target/linux/armsr/base-files/etc/hotplug.d/net/20-zx279128-hairpin`.
**It must be removed the day each port gets its own netdev**, or it becomes a
real loop.

This retires the headline limitation that the device "does not forward". It
forwards between wired ports today. (The Wi-Fi↔wired case is separate and has
not been re-tested against this finding.)

### The remaining structural limit

Port-to-port forwarding fails: tiny → workstation *through* the device is 100%
loss. But the frames **do reach the CPU** — `rx_packets` climbed 46 → 51 for
5 pings. So the hardware delivered them; the **Linux bridge** dropped them,
because both physical ports sit behind one netdev and a bridge will not send a
frame back out the port it arrived on.

That is the structural limit this file predicted ("with a single netdev over four
PHYs, `br-lan` cannot express a port choice"), and it is now the *only* thing
between here and a working switch: **give each port its own netdev.** The two
pieces that were assumed to be blockers — per-port enable and egress steering —
are respectively a one-bit write and apparently automatic.

### Shipped: the driver now enables all four ports itself

`all_ports` (module parameter, default **on**) maps all four MAC windows in probe
(`0x92200000 + N * 0x40000`) and sets `MAC_CTRL_EN` on each in `ndo_open`.
Verified on a boot bound to `mac1`, with **no manual register pokes**:

```
eth0: port mode: MAC+0x00 00bb6002 -> 00bb6003     (port 1, the bound one)
eth0: port 0 enabled: MAC+0x00 00000000 -> 00000001
eth0: port 2 enabled: MAC+0x00 00000000 -> 00000001
eth0: port 3 enabled: MAC+0x00 00bb6002 -> 00bb6003
```

and then **workstation 5/5 and tiny 5/5, 0% loss, both ports at once**.

(Ports 0 and 2 read `0x00000000` because this was a TFTP boot, where
`datapath_init()` is skipped; U-Boot's `smac_init` only configures the ports it
found linked. On a flash boot all four read `0x00bb6002`.)

### The revised recipe for multi-port

1. `MAC_CTRL_EN` on every port that has a PHY — **done, shipped, proven**.
2. Map the four MAC windows — `datapath_init()` already does.
3. One netdev per port, so the bridge can express a port choice — **the work
   that remains**, and it needs the RX descriptor's source-port field decoded so
   an arriving frame can be attributed to the right netdev.
4. Per-frame egress steering — **apparently not required**; the fabric resolves
   it. Worth re-testing once step 3 exists.

## ★★ The RX descriptor DOES carry an ingress-port field — w1 bits 20/21 (2026-09-06)

This file previously said the RX path reads nothing port-like and named word 0
and bytes 4-6 as the candidates. Both are wrong: the field is in **w1**, the word
the driver already reads for length.

Method: debug build dumping the four raw descriptor words per frame
(`rx_dump_max` module parameter), two live ports, and **single-source traffic in
each phase** so attribution is unambiguous.

| phase | traffic source | `w1` values seen | low field |
|---|---|---|---|
| A | workstation only (**mac1**) | `80100000` `06100000` `0a100000` `0e100000` `12100000` | **bit 20** |
| B | tiny only (**mac3**) | `1e200000` `22200000` `26200000` `2a200000` `2e200000` | **bit 21** |

Every frame in phase A carried bit 20 and every phase-B frame carried bit 21
(one stray bit-20 frame appeared in phase B, consistent with background traffic
from the still-connected workstation). The upper byte of `w1` is a rolling
counter and varies frame to frame; the port indicator is the low half.

**What is established:** an arriving frame can be attributed to its ingress port
from the descriptor alone. That is exactly what a per-port netdev model needs,
and it was the missing piece in the recipe above.

### ★★ RESOLVED with a third port: `port = ((w1 >> 19) & 7) - 1`

The workstation cable was moved to a third jack (phy1 → **phy2**, confirmed by
BMSR from U-Boot: phy11 went dark, phy12 lit). That gives the missing point:

| port | `w1` byte [23:16] | `(w1 >> 19) & 7` |
|---|---|---|
| mac1 | `0x10` = 16 | **2** |
| mac2 | `0x19` = 25 | **3** |
| mac3 | `0x20`/`0x21` = 32/33 | **4** |

16 / 25 / 32 looks irregular; bits **[21:19]** give 2 / 3 / 4, i.e. the **MAC
index plus one**. That is the same `getPort(n) = n + 1` convention the sibling
ZX279133 documents for its switch-UNI → PPU-port mapping — good corroboration
for a field recovered empirically.

Confirmed again in a **single boot** with single-source traffic per phase:
workstation on mac2 → `a4190000`… → 3; tiny on mac3 → `b2210000`… → 4.

Bit 16 is **not** part of the field (set on some frames of every port, clear on
others), and bits [31:24] are a rolling counter. So the earlier "one-hot at bits
20/21" reading was an artifact of having only two ports, both of which happened
to land on single bits.

### Shipped: per-port netdevs

`split_ports=1` now registers **one netdev per physical port** and attributes
each frame with the decoder above. Verified on hardware:

```
port 0 -> eth1 (descriptor id 1)     eth0 stays the DT-bound port (port 1)
port 2 -> eth2 (descriptor id 3)
port 3 -> eth3 (descriptor id 4)
```

| traffic | eth0 | eth1 | eth2 | eth3 |
|---|---|---|---|---|
| baseline | 0 | 0 | 0 | 0 |
| 6 pings from the workstation (**mac2**) | 0 | 0 | **6** | 0 |
| 6 pings from tiny (**mac3**) | 0 | 0 | 10 | **6** |

**A bug worth recording:** the first version skipped the DT-bound port by
comparing `ze->mac == ze->macs[n]`. Those are two independent `ioremap`s of the
same physical window, so the pointers never match and the bound port got a second
netdev. Compare by **port index** derived from the DT `reg`, not by pointer.

This is what `br-lan` needed to express a port choice, so the hairpin workaround
becomes unnecessary once every port has its own netdev.

Note this also means the sibling's layout does **not** transfer here: ZX279133
puts a 6-bit source port at `length_flags[21:16]`, and ours is not a 6-bit
integer in that position.

## ★★★ THE DEVICE ROUTES AND NATs BETWEEN TWO PHYSICAL PORTS (2026-09-06)

`split_ports=1` (module parameter, default **off**) registers a second netdev and
steers RX frames to it by the ingress-port bit in the descriptor. With
`eth0` on the mac1 jack and `eth1` on the mac3 jack:

```
zx279128-eth 92240000.ethernet: secondary port netdev eth1 registered (split_bit 0x200000)
```

| test | result |
|---|---|
| RX attribution — tiny (mac3) pings, 8 frames | **`eth0_rx=0`, `eth1_rx=8`** — every frame on the right netdev |
| workstation → `eth0` (192.168.1.1) | **5/5, 0% loss** |
| tiny → `eth1` (10.0.0.1) | **5/5, 0% loss** |
| **routed**: tiny 10.0.0.50 → workstation 192.168.1.100 | **6/6, 0% loss** |
| **routed, reverse**: workstation → tiny | **6/6, 0% loss** |
| **NAT**: masquerade on `br-lan`, UDP from tiny | workstation observed **`SRC_SEEN=192.168.1.1`** instead of `10.0.0.50` |

**Two physical ports, two netdevs, two subnets, IP forwarding and NAT — all
verified end to end on hardware.** The `README.md` line "as a router: not yet …
no NAT" is obsolete for the wired path.

### Two traps worth recording, both of which looked like hardware faults

* **`eth1` gets no firewall zone.** Frames arrived on it (`eth1_rx` climbing)
  and were silently dropped by `fw4`'s default `input` DROP policy, which looks
  exactly like a broken datapath. `nft insert rule inet fw4 input iifname "eth1"
  accept` fixed it instantly. Any per-port netdev needs a zone in
  `/etc/config/firewall` — this is `board.d`/`02_network` work, not driver work.
* **NAT must masquerade on `br-lan`, not `eth0`.** `eth0` is a bridge port, so
  the output interface for the LAN side is the bridge. Masquerading on `eth0`
  silently does nothing — the packet still arrives, just un-NATed, which reads
  as "NAT is broken" rather than "wrong interface".

### Caveat on the encoding — this is a 2-port proof, not a 4-port driver

`split_bit` defaults to `0x00200000` (w1 bit 21 = the mac3 jack) and the split is
**default off** because the bit→port mapping is known from only two cabled
ports. A third cabled port is needed before this becomes a general four-port
decoder. What is proven is the *architecture*: descriptor-based ingress
attribution works, one shared TX path is sufficient, and the fabric resolves
egress by destination MAC.

## M9: a third wedge point, on the correct port — 4092 = 4 x 1023 (2026-09-06)

Re-measured now that the driver drives the cabled port (mac1), with
`ping -f -c 6000 -s 1400`:

| run | starting `rx_packets` | wedge at | on the 1023 lattice? |
|---|---|---|---|
| contaminated — device had been up and degrading | 35 | 4017 | **no** (4×1023 = 4092) |
| **clean cold boot** | 2 | **4092** | **yes, exactly 4 × 1023** |

`rx_dropped` and `rx_errors` were **0** in both.

**The lattice holds.** Four independent stopping points are now on record, across
two boot types and two port bindings, and all are exact multiples of the 1023
usable ring slots:

```
3069 = 3 x 1023   (round 178,  flash boot, driver on mac0)
4092 = 4 x 1023   (2026-09-06, TFTP boot,  driver on mac1)
5115 = 5 x 1023   (round 251,  twice)
5115 = 5 x 1023   (2026-09-06, COLD FLASH boot, driver on mac1, err=0 drop=0)
```

The last of those is the authoritative regime — `datapath init at probe (cold)`,
the driver on the cabled port, measured from a settled cold boot. So the lattice
is not an artifact of the warm/TFTP regime, of `datapath_init` being skipped, or
of having driven the wrong MAC. It survives all three.

The multiplier varies between boots (3, 4, 5); the fact that it is an **exact
integer number of ring traversals** does not. That is a much tighter constraint
than "roughly N frames" and it survives the port correction, so it is not an
artifact of having driven the wrong MAC.

✗ **A preliminary reading of "4017 breaks the lattice" is withdrawn.** It came
from the first run above, on a device that had been up for a long time with
`nocredit` already past 20000. Replicating from a cold boot gave 4092 exactly.
This is the third time in this project that a striking single measurement
evaporated under replication — and the second time in this session.

## ★★★ The deferred cspboot experiment, finally run — boot path is NOT the variable

`docs/ETHERNET.md` recorded, after round 236's inconclusive attempt:

> "A clean answer needs a diagnostic kernel flashed to bank A and booted by
> cspboot — a flash write, deferred."

**Done, 2026-09-06.** A debug kernel (census + `/proc/zx_eth_poke`, all ports,
bound to mac1) was flashed to bank A — kernel and header both read back and
compared byte-exact — and cold-booted by `cspboot`. Boot log:
`datapath init at probe (cold)`, i.e. the real cold-init path, and every one of
the four MACs read `0x00bb6002` *before* being enabled (on a TFTP boot ports 0
and 2 read `0x00000000`), which independently confirms `datapath_init()`
configures all four.

Datapath health on the second cold boot: **ping 10/10, 0% loss, rtt 3.6-39 ms,
`nocredit` 1676**. (The *first* boot after any flash is atypical — 12.5% loss
and second-scale RTTs while the JFFS2 overlay is rebuilt. Do not measure on it.)

| on a cspboot FLASH boot | user-visible | `tcp_bare` | `tcp_data` |
|---|---|---|---|
| inbound connect to `:22` | times out | **0 → 0** | 0 |
| outbound connect + payload | **works, `rc=0`, 15 B delivered** | **0 → 3** | **0** |

**This is identical to the manual-TFTP regime**, so the "boot path co-varies
perfectly with the outcome" confound that stood in this file for ~20 rounds is
now **directly refuted by the experiment it asked for**. The real variable was
always which port the driver was bound to.

The rule that survives all regimes tested — TFTP-warm, TFTP-forced, and now
cspboot-cold:

* an unsolicited **inbound SYN never reaches the CPU**;
* **SYN-ACK/ACKs of a device-initiated flow do**;
* **`tcp_data` has never once been non-zero.**

So the discriminator is **flow state**, and the target is the SPA per-port
tables — not the bootloader.

## ★ Cold `datapath_init()` leaves the buffer manager credit-starved (2026-09-06)

Measured on the flashed image (cold `cspboot` boot, `datapath init at probe
(cold)`, driver on mac1). Health varies sharply **between boots**:

| boot | result |
|---|---|
| 2nd cold boot | ping 10/10, **0% loss**, rtt 3.6-39 ms, `nocredit` 1676 |
| others | 12.5%, 20%, 40% "loss" with multi-second RTTs |

The "loss" is a **misreading of the summary line**. Looking at the per-packet
output instead:

```
icmp_seq=1..18  ttl=64  time=1549 ms 1540 1536 1536 1532 ... 1015 1024
20 packets transmitted, 18 received, 10% packet loss
```

**Every packet is answered, at a near-constant ~1.5 s.** The two "lost" are
simply still in flight when the run ends. So this is not packet loss at all — it
is a fixed latency.

And the frames are **not** being dropped on receive: the census counted
`icmp=30` for 30 pings, i.e. every one reached the driver. What is wrong is
`nocredit=5766` after only those 30 packets — `zx_bm_free()`'s writes are being
rejected, buffers are not returning to the pool, and transmits then stall
waiting for one.

### What this pins on `datapath_init()`

* **Not `all_ports`.** Tested twice — once by clearing the three non-bound MACs
  after the fact, once by clearing them immediately at boot before any traffic.
  Identical result both times.
* The **warm** (bootloader-initialised) regime does not show it: TFTP boots gave
  0% loss and sub-40 ms RTTs on fresh boots, because U-Boot's own init leaves the
  buffer manager in a good state and `datapath_init()` is then skipped.

So this is direct evidence for what the driver's own source comment has claimed
since round 48 — *"the reset at the top tears down a working configuration that
the rest of this function cannot fully rebuild"* — and it localises the gap to
the **buffer-manager credit path** specifically, which is a much smaller target
than "datapath_init is incomplete".

**Consequence for anyone measuring:** quote the per-packet RTTs, not the ping
summary. On this hardware a "40% loss" line has twice meant "everything arrived,
1.5 s late".

## What the driver does

- MDIO bus and PHY discovery on all four addresses, but **only phy0 is attached
  and started** - `phy1/2/3` are declared in the DTS and never connected, so link
  detection reflects port 0 alone.
- TX through a dedicated buffer index.
- RX from an **hrtimer poll at 500 µs** — no RX interrupt has ever been decoded,
  so nothing else pulls frames out of the ring.
- Returns consumed descriptors with a credit write to `TMQ+0x170`.
- Frees every buffer it consumes, on success and on every error path.
- Re-primes the buffer pool after sustained silence following traffic
  (`rx_heal`, default 20000 idle polls), disarming after each attempt.

## What works

ARP, ICMP, UDP, DHCP and DNS, at any frame size including full MTU.

## One root cause behind every Ethernet limitation

Every wired-datapath symptom in this document traces to a single fact: **this is
a reverse-engineered driver for an undocumented MAC/classifier with no vendor
driver, and the wired datapath is fragile in every direction.** The distinct
symptoms are faces of that one cause:

| symptom | measured | where |
|---|---|---|
| RX delivery is partial | **RETRACTED** - ~99.8% at a moderate rate; the old 50-57% was a wedge in progress | below |
| RX wedges under load | dead under a *flood*; observed stops 3069 and 5115 = 3x and 5x 1023 | the wedge sections |
| Forwarding unusable | 87.5-100% client-visible loss Wi-Fi->wired; wired path also loses 15-35% for device-own traffic | `WIFI.md` |
| TCP does not terminate | boot-path-specific classifier behaviour | item 1 below |

So the device is usable for light, device-terminated UDP/ICMP/management traffic
and nothing heavier: it cannot sustain a transfer (RX wedge), cannot route
(TX loss), and cannot carry TCP (classifier). These are not four independent bugs
to fix one by one; they are what an incompletely-understood datapath looks like
without the vendor's `np.ko`/`switch.ko`.

## What does not work

**1. Inbound TCP does not reach the CPU; outbound TCP works.** ✗ The previous
text here — *"its exact shape is boot-path-specific and unexplained"* — is
**superseded**. It rested on a confound: every historical non-zero `tcp_bare`
came via `cspboot` and every zero via a manual `bootm`, so the boot path was
blamed. The real variable was **which port the driver was bound to**: it was
driving `mac0`, which has no cable. Driving `mac1` reproduces `tcp_bare` climbing
on a plain TFTP boot, so the boot path was never the discriminator.

The replicated behaviour is now (full table and method in "The TCP defect,
characterised" above):

* outbound, device-initiated TCP **works**, payload and all;
* the SYN-ACK/ACKs of such a flow **do** reach the CPU (`tcp_bare` climbs);
* an **unsolicited inbound SYN does not** reach the CPU — though it is just as
  payload-free as the SYN-ACK that does, so the discriminator is **flow state**;
* **no TCP segment carrying payload has ever reached the CPU** (`tcp_data` = 0
  across every regime tested, including an established connection whose ACKs
  were arriving concurrently).

The user-visible consequence is unchanged: no inbound SSH, no LuCI, no `opkg`.

**2. A flood wedges the receive path.** ✗ **RETRACTED (round 251):** the figures
that stood here - "roughly 50-57% of a 4000-frame burst delivered (best
2262/4000; earlier runs 37-51%)", and "after a few thousand *cumulative*
frames" - were both wrong, and wrong in the same way: they were **a wedge
already in progress during a flood, recorded as though it were a steady-state
rate**. Corrected:

* **Delivery below the wedge threshold is ~99.8%**, not 50-57%. Measured
  device-side from a settled device: 800 x 100 B @ 2 ms -> 0.125% loss;
  1200 -> 0.25%; 1500 -> 0.2%. `rx_errors`, `rx_dropped` and `tx_errors` were
  **0** throughout.
* **The trigger is offered rate, not cumulative frame count.** At 2 ms spacing
  the device passed **3677 cumulative frames** with 0.2% loss and kept going -
  well past the supposed ~3000 threshold. A flood kills it; a moderate rate does
  not. Reproduce with `ping -f -c 4000 -s 1400 192.168.1.1`.
* Under a flood, how much gets through before the wedge arrives varies widely
  between boots: 0.075%, 0.175%, 22.65%, 29.4%, 72.6%, plus runs that wedged
  mid-flood. That spread is not a rate.

Once wedged: 100% loss both directions, recoverable **only by a power
cycle**. `ifconfig down/up`, a fabric reset at `0x92000008`, a full
`zx_eth_datapath_init()` have each been tried and none recovers it. Re-priming
all 2047 buffers also failed to recover it, but that test is **inconclusive** -
see the closing summary, since a credit-starved free path would reject the
re-prime for the same reason it rejects everything else.

**3. No switch/DSA driver: this is a single-port driver.** The four PHYs sit
behind one `eth0`, and `br-lan` is a *software* bridge, so forwarded traffic uses
the same receive path.

Measured with a second host (a Raspberry Pi) cabled to a different physical port
from the workstation:

| boot type | ZTE receives from the second port | second host receives replies |
|---|---|---|
| TFTP boot (`zx_eth_datapath_init()` skipped) | **no** — `rx_packets` delta 0 for 53 frames | no |
| flash boot (`datapath_init` runs) | **yes** — `rx_packets` delta exactly 8 for 8 pings | **no** |

So the port only ingresses at all once `datapath_init` has configured the NPP
per-port registers, which never happens on a TFTP boot. Even then the path is
**one-way**: frames arrive from that port, and nothing the CPU sends comes back
out of it (the second host's `rx_packets` stayed at 0 throughout).

That is a concrete, reproducible characterisation of what "no switch driver"
costs here, and it means **only the port the workstation is cabled to is usable
for bidirectional traffic**.

Refined with controls:

* **Control arm** — with the second host idle, the ZTE's `rx_packets` delta over
  20 s is **0**, so the ingress counts above are that host's frames and not
  background traffic.
* **The device does transmit for the unreachable destination.** With a static ARP
  entry, five pings to the second host produced a `tx_packets` delta of **7**,
  against **11** for five pings to the reachable workstation. Meanwhile
  `tcpdump -i eth0` on the second host captured **0 packets**. So frames are
  emitted and leave by the wrong port: this is a **port-selection** fault, not a
  transmit fault. Those are different bugs and an earlier reading of this data
  had them confused.
* **The TX descriptor template is not the selector.** The three descriptor words
  were hardcoded constants copied from a working U-Boot transmit and had never
  been varied. Sweeping `w2` (`0x01000000` default) through `0x02`, `0x04`,
  `0x08` and `0x0f000000` — the obvious readings if it were a four-port bitmap —
  never delivered a frame to the second host.

  Worse, the sweep **broke egress to the working port too**, and restoring the
  original value did not recover it; the datapath then wedged. So `w2` does
  matter, but not as a port bitmap, and writing arbitrary values to it is
  destructive rather than merely ineffective.

**This is a single-port driver by construction** - and the round-206 claim that
the hardware differentiates the ports was wrong.

> ✗ **PARTIALLY RETRACTED (2026-09-06).** "By construction" overstates it, and
> one supporting fact below is false. See *"How much is actually missing"* at the
> end of this section.

The device tree maps one 4 KiB window:

```dts
reg = <0x92200000 0x1000>;      /* port stride is 0x40000 */
phy-handle = <&phy0>;           /* phy1/2/3 are declared but never connected */
```

So ports 1-3 are **outside the mapped window entirely** - the driver cannot reach
their MACs, and only `/proc/zx_eth_poke` ever did. One PHY is attached and
started; `Link is Up - 1Gbps/Full` describes port 0 alone and says nothing about
any other port.

That explains every observation without invoking a fabric fault:

* **Ingress from another port works** because the second host's ARP frames are
  **broadcast**, and reach the CPU through the fabric via port 0's enabled MAC.
  It worked before any register was touched.
* **Egress always leaves port 0**, because that is the only MAC the driver has
  enabled and the only PHY it has started.
* **The "one bit that differs"** was this driver's own write. `ndo_open` sets
  `MAC_CTRL_EN`, and the driver logs it every boot:

  ```
  port mode: MAC+0x00 00bb6002 -> 00bb6003
  ```

  Port 0 reads `0x00bb6002` in hardware - identical to ports 1-3 - until the
  driver enables it. Round 206 measured port 0 *after* configuring it and ports
  1-3 *before*, then attributed the difference to the bootloader.

  ✗ **This paragraph used to end**: *"It also claimed `datapath_init` writes
  these uniformly; `datapath_init` never touches `MAC_CTRL` at all."* **That is
  false.** `zx_eth_datapath_init()` writes `MAC+0x000 = 0x00bb6002` to **all four**
  MAC windows (`zx279128-eth.c:1826-1861`, `ioremap(0x92200000 + i * 0x40000)`).
  MAC_CTRL is offset `0x00`, so it is written on every port - with bit 0 clear.
  Round 206's "writes these uniformly" was right; the rebuttal was wrong.
* **The single frame** that appeared after setting bit 0 was one queued frame
  draining from a MAC that had never been enabled. Nothing sustained it because
  nothing else about that port is configured.

### How much is actually missing

Re-audited against the driver source on 2026-09-06. `zx_eth_datapath_init()`
already does **three of the four** things multi-port needs, for all four ports:

| already done, ports 0-3 | where |
|---|---|
| ioremaps each MAC window at `0x92200000 + i*0x40000` and writes the full per-port MAC config (`+0x00`, `+0x04`, `+0x08`, `+0x70`, `+0xb0`, `+0xb4`, `+0xd0`, `+0xe0`) | `zx279128-eth.c:1826-1861` |
| clears `npp_port_mask` in `NPP+0x60 + port*4` | `:1432-1439` |
| sets the port-attach mask `0x921d9000 +0x68 \|= 0xf` | `:1745` |

What is **not** done is `MAC_CTRL_EN` (bit 0) on anything but port 0 - that
happens only in `ndo_open` against the single `ze->mac` (`:1153-1158`). The DT
maps one window, so `ze->mac` is port 0 alone; `datapath_init` reaches the other
three only through its own temporary `ioremap`s.

So the honest statement is not "by construction" but: **the datapath is already
configured for four ports and the driver enables one of them.** The genuinely
unknown part remains egress steering (item 4 below).

Two never-tried experiments follow directly, both cheap:

* **`MAC+0x08` bit 31.** The driver's own comment at `:1845-1849` says it "looks
  like an enable", and it is written as `0x80000001` to every port. The sibling
  ZX279133 MAC has **two** independent enables - `TX_CTRL+0x00` bit 0 *and*
  `RX_CTRL+0x10` bit 0 - which would explain this driver's recorded A/B result on
  `MAC+0x00` bit 0 (`bit0=0` -> frames egress, nothing reaches the CPU;
  `bit0=1` -> CPU receives but transmits stop reaching the wire). One enable held
  wrong while the other is toggled produces exactly that.
* **TX descriptor `w1`, word 0, and bytes 4-6.** The round-204 sweep varied only
  `w2` ([31:24], read as a four-port bitmap) and broke egress. On the sibling the
  destination port is a **6-bit integer at [21:16] of a different word**, with a
  control flag immediately above it - and `zx_tx_w1` (default `0x00010000`, i.e.
  `1` at [23:16]) is already a `0644` module parameter that has **never been
  swept**. The RX poll loop likewise never reads word 0 or bytes 4-6, which is
  where a source-port field would live.

### What multi-port support would actually require

Three cheap pieces and one hard one:

1. map four MAC windows instead of one (DT `reg`),
2. attach and start all four PHYs,
3. set `MAC_CTRL_EN` per port,
4. **steer CPU-injected frames to a chosen port** - genuine switch-fabric
   configuration, which the vendor performs in `switch.ko`.

Only the fourth is unavailable, and it is the one that matters: with a single
netdev over four PHYs, `br-lan` cannot express a port choice in the first place.

### `force_dp_init`, and why this was untestable for 200 rounds

`zx_eth_datapath_init()` runs only when the MAC register reads "cold":

```c
if (!(readl(ze->mac ? ze->mac : ze->tmc) & 0xffff0000))
```

U-Boot's network stack leaves the MAC **warm**, so on any TFTP boot the init is
skipped — a 12/12 correlation observed in this project. Since nearly every driver
experiment here was run over TFTP, everything `datapath_init` configures,
including the NPP per-port registers that decide whether a second port ingresses
at all, was silently untestable.

`force_dp_init=1` runs it regardless. Multi-port work is now iterable over TFTP
rather than costing a full flash cycle per attempt.

> The delivery band was first measured with `maxcpus=1`. It **survives SMP**
> (dual-core boots delivered 45% and 48%) and it **survives the move to a
> reproducible build**: on the image a clean `build.sh` produces, three boots
> delivered 1752/4000 (44%), 2135/4000 (53%) and 1932/4000 (48%). The band is
> now anchored to the artifact a stranger can build, not to a hand-configured
> tree.

## Throughput: bounded by the wedge, not by the link

Measured with the timing done **on the device** (`rx_bytes` and `/proc/uptime`
sampled inside a single shell command, so console latency cannot dominate the
window) while the workstation blasted 1400-byte UDP frames as fast as it could:

```
host sent    384,786 frames in 4.50 s        <- host socket buffer, not the wire
device got   4,395,216 bytes over 6.01 s     <- device-measured window
           = 3,048 frames = 5.85 Mbit/s
```

Then `rx_packets` read **3069** and the interface stopped responding entirely.

That is the same wedge threshold recorded independently in earlier work, which
means **the figure is bounded by the wedge and not by the link**. Quoting
5.85 Mbit/s as a bandwidth would be misleading: under a flood the device does not
sustain any rate.

✗ **RETRACTED (round 251) - the "budget" reading of this measurement.** This
section used to conclude "**about 3000 received frames per boot**", i.e. a
one-shot cumulative allowance. That is wrong. At 2 ms spacing the device passed
**3677 cumulative frames** at 0.2% loss in perfect health and carried on, so
there is no per-boot frame allowance. **The trigger is offered rate.** The run
above wedged at 3069 because it was a flood, not because 3069 frames had
accumulated.

What survives from this measurement is narrower and still useful: **5.85 Mbit/s
is a floor set by the wedge, not a link bandwidth**, and a 17 MB transfer
(~12,000 frames) pushed at speed will not complete. A paced transfer at a
moderate rate is a different question and has not been measured to that size.

## How to verify

```sh
dmesg | grep census          # per-protocol arrivals; tcp_data has never been non-zero
cat /sys/class/net/eth0/statistics/rx_packets
ping -c 3 192.168.1.1        # after a load run, to see whether the path survived
```

`../../soak.sh` runs this per boot. It scores two independent verdicts -
`platform` (shell, MTD count, PHY, no SQUASHFS error, no panic, persistence) and
`dataplane` (**>= 1400** frames of 4000 delivered, and the interface still
answers afterwards) - and requires both to PASS. A boot with no `SOAKOK` at all
is scored INCONCLUSIVE, not FAILED, so instrument failures cannot masquerade as
device failures. (An earlier version of this file said the floor was 2500; the
combined 2500 bar was above the physical maximum and reported 0 passes forever,
which is why the verdicts were split.) Results are tracked in
`../../logs/soak-results.txt`.

## Open questions

- **The classifier.** Configured through an indirect port (`IND_CMD/STATUS/DATA`
  at `0x921cc054/58/5c`) whose ready bit reads 0. The sister-SoC reference
  implementation treats NPPT as firmware-initialised behind a single clock gate.
  See `research/ZX279133-SIBLING-DRIVER.md`.
- **A SOFTWARE-disable route is refuted; a hardware offload is not.** Binary RE
  (round 223) proved `ffe_get_npu_enable` reads a software flag in kernel RAM,
  not an MMIO register, and the vendor modules that install the accelerator do
  not run under this kernel - so there is nothing for us to disable from
  software. That does **not** refute a hardware offload: `npu->enable` is the
  vendor driver's own bookkeeping, and the hardware datapath state lives in
  ioremap'd tables the RE could not resolve (indirect callbacks, no recoverable
  MMIO addresses). A classifier configured by the BOOTLOADER would look static
  from our side and be an offload from the hardware's side - both at once.

  **Rounds 233-236 - a single-segment test, and then a CONFOUND that a review
  caught (rounds 233/234 conclusions downgraded).** On a manually-`bootm`-ed TFTP
  diagnostic boot: ICMP and UDP reach the CPU (census `icmp`/`udp` climb), but
  real OS-stack TCP SYNs produced `tcp_bare=0`.

  Two corrections, both from the round-235 review, both verified:

  * **The "no RST proves it never reached the CPU" argument is INVALID.**
    `firewall4` and `nftables-json` ship in this image (dependencies; not in
    `seed.config`), and OpenWrt's default policy silently DROPs unsolicited
    inbound - so "SYN in, nothing back" needs no classifier at all. The
    firewall-IMMUNE evidence is only the census: `c_tcp_bare++` is in the NAPI
    poll (~line 736) about 75 lines UPSTREAM of `netif_receive_skb` (line 812),
    so `tcp_bare=0` genuinely proves frames never reached the driver. Use the
    census, not the missing RST.
  * **A perfect boot-path confound.** Every historical NON-ZERO `tcp_bare`
    (3,4,7,8,11,12) came via `cspboot`; every recent zero came via manual
    `bootm 0x42000000`. The boot path co-varies perfectly with the outcome and
    was never controlled. So the honest statement is NOT "TCP is dropped
    entirely" - it is "on a manually-bootm'd TFTP boot, TCP does not reach the
    driver." Round 234's reinit test ran entirely inside that same dead-TCP
    regime, so it does NOT establish "set by cspboot" either.

  **Round 236 tried the deciding test** (cspboot enters at `bootm 0x42020020`,
  +0x20 past the header; mimic it with the diagnostic kernel, no flash write).
  The kernel booted, but its **datapath came up completely dead** (100% ping
  loss, device MAC would not even ARP-resolve), so no census traffic could be
  generated and the test was INCONCLUSIVE. That dead datapath is itself a
  boot-path difference. A clean answer needs a diagnostic kernel flashed to bank
  A and booted by cspboot - a flash write, deferred.

  **Current honest status: the TCP behaviour is boot-path-specific and
  unexplained.** On a manual TFTP boot TCP does not reach the driver; cspboot is
  the path where payload-free TCP historically did. Whether cspboot configures a
  classifier, or the manual boot simply leaves the datapath too broken to pass
  TCP, is not settled.

  The census supports "static" but more weakly than first recorded: `tcp_data`
  has never been non-zero, and the classification arithmetic was validated
  independently (synthetic frames with 1-1400 byte payloads, IP options and TCP
  options all classify as `tcp_data`), so the instrument genuinely can fire.
  However `tcp_bare` is a CUMULATIVE counter that is mostly frozen (values 3, 4,
  7, 8, 11, 12; parked at 12 for 109 samples), so the earlier "143 samples with
  TCP activity" overstated it - that is a handful of small bursts sampled
  repeatedly, not 143 independent observations. See
  `research/FFE-NPU-FLOW-ACCELERATOR.md`.
- **The wedge.** Cumulative rather than per-burst, mildly frame-size dependent
  (3069 frames at 1400 B, 2970 at 20 B), and unrecovered by every lever the
  driver owns.
- **TX allocates and discards a buffer per frame** — `zx_bm_alloc()`'s result is
  overwritten by `zx_tx_buf_idx`. A known leak, and *not* the cause of the wedge.
- `npp_port_mask` ships at `0x3800000`; its only test was invalid.


## The wedge: two corrections to earlier eliminations

### "3 x 1023 was coincidence" was retracted too early

The retraction rested on 20-byte frames wedging at 2970 rather than 3069. But
both numbers share a factor:

```
gcd(3069, 2970) = 99      3069 = 99 x 31      2970 = 99 x 30
```

and both are consistent with a processed-frame budget of **3072 = 3 x 1024** if
`rx_packets` counts only frames *delivered to the stack*: 3 missed for large
frames (0.10%), 102 for small (3.32%). Small frames arrive roughly 17x faster at
line rate and show 34x more losses - same order, right direction.

Note also which way the dependence runs: **small frames wedge EARLIER**, so the
per-frame cost is higher for small frames. That rules out every byte-, cell- and
buffer-size model (cells of 64 through 2048 bytes were checked; none equalises
the two points).

So the ring model is **unresolved**, and an attempt to settle it was invalid.

That attempt read `TMQ+0x170` with `rx_credit=0` and found it equal to
`rx_packets` (29 = 29), concluding the model was refuted. Three independent
reasons that does not follow:

* **Wrong register.** The model is about frames the hardware *processed* versus
  frames the driver *delivered*. This driver's own round-150 comment records a
  captured wedged state naming three registers - `0x168` "produced", `0x16c`,
  `0x170` "consumed" - and `0x170` is the smallest of the three. Reading a
  consumed counter to test a claim about a produced count confirms an identity,
  not a hypothesis. `0x168` was never read. Read since: it returns **0** in the
  current regime, which does not match the round-150 capture either, so the
  register semantics are themselves not settled.
* **The comparison is near-tautological.** `rx_packets++` and `done++` are
  incremented on adjacent lines of the same loop iteration, and the driver writes
  `done` into `0x170`. With the credit write enabled, that register holds the
  running sum of frames the driver itself put there - so round 147's "RXPROD and
  `rx_packets` advance in lockstep" was arithmetic, not measurement. **That
  earlier retraction of the artifact worry is itself retracted.**
* **The regime was destroyed by the change meant to protect the measurement.**
  Disabling the credit write ends the run at 29 frames, about 1% of the way to
  the phenomenon. The model predicts roughly 3 frames of divergence at 3069, so
  0.03 frames at 29 - undetectable even if real.

A valid version needs the datapath kept alive while `0x170` is left unperturbed,
and all three counters read together at the wedge.

### And the consume credit is what keeps the datapath alive at all

The same measurement produced a much larger finding by accident. With the credit
write disabled, the datapath delivered **29 frames** across a six-second blast
and then wedged - against ~3069 with it enabled.

So `writel(done, TMQ+0x170)` is not a tuning detail or an optimisation: it is the
mechanism that lets the receive path continue past a few dozen frames. Round 150
added it to cure a permanent load wedge and that reading was correct, but its
importance was understated - without it the usable budget is roughly **two orders
of magnitude smaller**.

What this does **not** establish is the mechanism of the ~3069 limit. "The
doorbell is required for sustained receive" and "the doorbell explains the wedge"
are different claims, and only the first has evidence: nothing here shows credit
ceasing to be accepted at 3069.

**Methodological trap in that measurement:** the driver *writes* its consume
credit to `TMQ+0x170`, the same address. Any reading must be taken with
`rx_credit=0` (a module parameter, no rebuild needed), or the driver is mutating
the counter being read - which also means the round-147 observation that "RXPROD
and rx_packets advance in lockstep" may be an artifact.

### The pool elimination did not test what it was believed to test

`zx_bm_free()` writes `BM_FREE` **unconditionally**, including when four
consecutive credit refills all return zero:

```c
for (i = 0; i < 4 && !ze->sw_free_credit; i++)
        ze->sw_free_credit = (readl(ze->bm + BM_FREECNT) >> 3) & 0x3f;
if (ze->sw_free_credit)
        ze->sw_free_credit--;
writel(idx, ze->bm + BM_FREE);      /* unconditional */
```

There is no return value, no retry, and until now no counter. Decoding
`BM_FREECNT` values already present in the captured logs with the driver's own
formula gives credits of 12, 34, 36 - **and 0**. The zero-credit state is
observed.

If the hardware requires credit to accept a free, those writes are discarded and
the buffers are lost invisibly. And the experiment recorded as eliminating pool
exhaustion - "re-priming all 2047 buffers revives nothing" - would have had its
re-prime rejected for exactly the same reason. **That elimination is downgraded
to inconclusive.**

A `nocredit` counter is now reported in the census line so the rate is visible
rather than assumed.


## The wedge: closing summary

This was investigated across roughly thirty rounds. It is **not solved**, and the
most useful thing to record is the shape of what is known, what was eliminated,
and which eliminations later proved unsound.

### What is solid

* Deterministic: `rx_packets = 3069` with 1400-byte frames, reproduced on three
  separate occasions including once through an unrelated throughput measurement.
* Frame-size dependent, in the **counter-intuitive direction**: 20-byte frames
  wedge *earlier*, at 2970. Per-frame cost is higher for small frames, which
  rules out every byte-, cell- and buffer-size model.
* Cumulative, not per-burst: individual 8000-frame bursts are survivable; the
  running total is what matters.
* Not recovered by `ifconfig down/up`, a fabric reset at `0x92000008`, or a full
  `zx_eth_datapath_init()`. Only a power cycle. (Re-priming the pool also failed,
  but that test is inconclusive - see below.)
* Unaffected by how the descriptor is released (three variants, identical
  threshold).
* `rx_errors` is 0 throughout, and the driver frees every buffer it consumes.
* The consume-credit write to `TMQ+0x170` is **load-bearing**: without it the
  budget collapses from ~3069 frames to 29.

### What was eliminated, and what that is worth

| hypothesis | status |
|---|---|
| byte-count limit | **eliminated** - 184 KB vs 4.3 MB at the same failure |
| descriptor not re-armed | **eliminated** - three release variants, identical threshold |
| TX buffer leak as the cause | **eliminated** - TX counts near the wedge are 50-60 frames |
| buffer pool drained | **inconclusive** - the re-prime test could have been rejected by the same credit starvation it was testing for |
| fixed ring traversals (3 x 1023) | **unresolved** - the test that "refuted" it read a consumed counter to answer a question about a produced count, and ran in a regime that ended at 29 frames |

Two of five eliminations did not survive scrutiny. That is the single most useful
thing here for whoever continues: **on this hardware, an elimination is only as
good as the register semantics it rests on**, and those are reverse-engineered
from a bootloader with no datasheet.

### Where a fresh attempt should start

1. Read `0x168` and `0x16c` - which the driver never writes - at the wedge,
   alongside `rx_packets`. If produced exceeds delivered, the ring model lives.
   Note `0x168` currently returns 0, which contradicts a round-150 capture, so
   the semantics need establishing first.
2. Sample `nocredit` (now in the census line) as a **time series** through a
   burst. Before/after cannot distinguish "credit collapse causes the wedge" from
   "the wedge causes credit collapse", and those imply opposite conclusions.
3. Only then consider changing credit frequency or amount. Writing arbitrary
   values into datapath registers has already destroyed a working state once.

### Was closed; REOPENED (2026-09-06)

This section previously read "Why this is being closed rather than pursued", and
rested on two claims that have since been corrected:

* *"an honest, documented budget of about 3000 received frames per boot"* -
  **retracted**, see the throughput section. There is no per-boot budget; the
  trigger is offered rate, and delivery below it is ~99.8%.
* *"blocked on vendor code that is not available"* - still true of `np.ko` /
  `switch.ko` (the vendor rootfs is an AES-ECB container and the key is unknown),
  but it was **not** true that no other route existed. Three concrete ones were
  never tried, and all three are now open work:

  1. The **stock vendor DTS** (in the `h199a-firmware` dump) declares blocks this
     driver has never touched: `gephy@9b000000` - four per-port windows at stride
     `0x100000`, each with its own interrupt (0x27-0x2a) - and `idm@921c8000`, a
     distinct block that is `status = "disabled"` in stock, not the "unmapped gap"
     round 166 took it for. IDM is where the sibling SoC keeps its descriptor
     rings, `RX_RELEASE (+0x0088)` and `BP_REFILL (+0x0100)`.
  2. The sibling driver uses **two separate registers** for the two jobs this
     driver does with one - release-consumed vs refill-buffers. We write one
     number to one register we are not certain is either.
  3. `NPP+0x80` is the sibling's `GLOBAL_INIT_DONE` (expect `(v & 0x1fd) ==
     0x1fd`). It has never been read here. If global init never completed, that
     explains the dead SPA indirect port without invoking clocks at all.

The wedge is therefore **not closed**. It is open work with named next steps.
What remains true is that fixing it alone does not produce a router: **TCP still
does not terminate on the device**, and that defect is separate and independently
fatal to the goal.

## 2026-09-07 — a clean wedge reproduction, read at the moment of failure

Bench rig for this session: `tiny` (an RPi, `ssh tiny`) cabled to the WAN jack
(`eth3`/`mac3`), a second host (`syd`) cabled to a LAN jack (`eth2`/`mac2` -
matches the cabling `handoff.md` last recorded). `network.wan` set to static
`10.200.0.1/24` for this session (ships as `dhcp` by default) so `tiny` didn't
need to run a DHCP server. Built and flashed a fresh `BRINGUP=1` image
(bank A, all three partitions `cmp.b`-verified byte-exact) to get
`/proc/zx_eth_poke` back - the previously-flashed image on the bench did not
have it.

### The wired-to-wired forwarded SYN was never tested before - it fails the same way

Every prior TCP characterisation in this file used a WiFi client as the LAN
side. With both sides wired (`syd` on `eth2` LAN, `tiny` on `eth3` WAN,
routed + NAT'd), a SYN from the LAN host to the WAN host never completes the
handshake either - `nc -vz`/`iperf3` from `syd` to `tiny` through the router
time out at connect, the same as an unsolicited SYN to the router's own IP.
ICMP routes and NATs cleanly both directions in the same setup (0% loss). This
is consistent with the existing flow-state rule (an unsolicited SYN is
unsolicited regardless of whether its destination is the router or a forwarded
peer) but it had not actually been measured before now.

### The documented flood repro did NOT wedge during the flood - twice

`sudo ping -f -c 6000 -s 1400 192.168.1.1` from `syd`, run twice from two
independent cold (flash) boots, completed both times without the historical
100%-loss wedge:

| trial | sent | received | loss | `nocredit` during run |
|---|---|---|---|---|
| 1 | 6000 | 5012 | 16.47% | 0 throughout |
| 2 | 6000 | 5029 | 16.18% | 0 throughout |

Both numbers are close enough to call the same result. This is well past the
previously-recorded wedge points (3069, 4092, 5115) with no wedge and no
credit exhaustion. **Do not read this as "the wedge is fixed"** - see below.

### The wedge showed up anyway, a few minutes after the flood, with no console freeze

On the second trial, a follow-up ping a couple of minutes after the flood
(no load in between) got `Destination Host Unreachable` from `syd`, and stayed
that way. This is the same shape as the round-206-era wedge, but this
instance is unusually clean because **the console never froze** - the
discriminator this file and `handoff.md` both warn is needed to rule out a
UART loopback fault:

```sh
# via UART, while syd's pings are failing:
echo CONSOLE_ALIVE_CHECK; date; cat /sys/class/net/eth2/statistics/{rx,tx}_packets
CONSOLE_ALIVE_CHECK
Wed Aug 12 00:13:58 UTC 2026
5108
5103              # tx_packets kept climbing; rx_packets did not, ever again
```

A static ARP entry for the router on `syd` (bypassing ARP resolution
entirely) still got 0/5 - so this is not an ARP-specific failure sitting on
top of a healthy datapath, it is the datapath itself. And the driver's own
per-second `census` line - which had been printing every second since boot -
**stopped appearing entirely** at the same moment `rx_packets` froze, and
never resumed. That line comes from the RX poll path, so its disappearance is
itself evidence the poll loop stopped running, independent of the netdev
counters.

### Read at the moment of the wedge - the experiment this file asked for

With the device wedged and the console still fully responsive, before trying
any recovery:

```
0x92350168 (TMQ, "produced" per the round-150 capture) = 0x00000000
0x9235016c (TMQ, the other of the pair)                = 0x00000000
0x92350170 (TMQ, "consumed" - the one the driver writes) = 0x00000000
0x923480dc (BM free-credit register)                     = 0x00000111
```

`rx_packets` was 5108 at the same moment. Decoded with the driver's own
formula, `BM+0xdc` = 34 free buffers - **identical to the idle baseline read
before any traffic this boot**, not the drained/zero state a credit-starvation
theory would predict. `nocredit` in the census had read 0 for the entire
session up to the point census stopped printing.

This does not resolve the open question about `0x168`/`0x16c`'s semantics -
they still read 0, exactly as every prior reading has, so the "produced vs.
delivered" comparison this file called for remains uninstantiated (0 vs. 0 is
not evidence either way). What it does add: **for this specific wedge
instance, the buffer-manager credit path was not exhausted and had not moved
from its idle value.** Credit starvation is not eliminated as a cause of *some*
wedges (the docs already record it as the confirmed regime on a cold
`datapath_init()` boot with different symptoms - fixed latency, not 100% loss),
but it did not accompany this one.

### `/proc/zx_eth_reinit` still does not recover it

Ran on the live wedge, all stages logged exactly as a healthy run
(`npp bring-up done`, `port attach 0000000f -> 0000000f`,
`packet processor bring-up done`) - and `rx_packets` stayed at 5108
afterward, ping still 0/4. Confirms the M4 finding independently, on a fresh
wedge instance, with the current image.

### Open, stated plainly

The flood no longer reproduces the wedge as reliably as `docs/INSTALL.md`
describes it - two clean runs through 6000 frames at the documented rate, then
a wedge that surfaced later with no load applied in between. Either the
trigger condition has shifted (different image, different port than most
historical measurements, background traffic from concurrent WiFi/NAND
activity), or "immediately during a flood" was never the whole story and a
delayed onset was always possible and just not caught before. No experiment
here distinguishes these. Whoever continues should not assume the `ping -f`
one-liner is still a reliable, fast repro - budget for it to wedge on a delay,
and watch `dmesg | grep census` specifically (not just packet loss) as the
earliest signal, since it stopped a full ping cycle before `rx_packets`
itself would have looked obviously stuck to a casual glance.

## ★★★ 2026-09-07 (later) — the vendor engine does NOT wedge, and IDM/gephy are not in its path

Four experiments from the U-Boot prompt on a demonstrably working datapath.
Method note: every figure below is a `md.l` read at the `=> ` prompt, and each
transfer's byte count was confirmed from the command's own output, never from
the echoed command line.

### ★★★ E1 — 40 MB through the vendor's engine, no wedge

The wedge reference in this repo has always been U-Boot's 2.6 MB TFTP. That is
**~1900 frames - below every wedge point this project has ever recorded**
(3069, 4092, 5115), so "U-Boot never wedges" was never actually tested. It has
been now:

```
=> tftp 0x42000000 big40.bin
   10 MiB/s
   done
   Bytes transferred = 41943040 (2800000 hex)
```

**~29 959 frames in one transfer, 5.9x the highest wedge point, at a sustained
10 MiB/s, with no stall.** Two smaller transfers in the same session brought the
boot's cumulative total to ~34 350 frames, still with no stall.

Two things follow, and they are the most useful facts in this file:

1. **The wedge is ours, not the silicon's.** The same MAC, PHY, cable, buffer
   manager and queue engine carry 6x the frames that kill our driver. A driver
   fix therefore exists. This retires "that points at a limit enforced on the
   hardware side" as the leading reading of `ROUND-251-RING-TRAVERSAL-LEAD.md`.
2. **The throughput ceiling is ours too**, and now measured over a long
   transfer rather than a short one: ~80 Mbit/s sustained versus this driver's
   5.85 Mbit/s.

### ★★★ E2 — RETRACTS the IDM lead: neither IDM nor gephy is in the working RX path

`handoff.md` and this file both name the **IDM engine** (`idm@921c8000`) as
"the untried lead" for the wedge, on the strength of the sibling ZX279133
keeping its descriptor rings there. Tested directly, by dumping both blocks
before and after the transfers above:

| block | before | after ~32 200 frames |
|---|---|---|
| IDM `0x921c8000` `+0x00..0x1FC` | see below | **byte-identical** |
| gephy `0x9b000000`/`9b100000`/`9b200000`/`9b300000` | see below | **byte-identical** |

Not one word in either block moved across thirty-two thousand received frames
on a datapath that was demonstrably working at 80 Mbit/s. **The vendor's fast
receive path does not touch IDM or gephy at all.** Porting the sibling's IDM
descriptor model would therefore have been a large rewrite aimed at an engine
this SoC's own working reference does not use.

That is a clean falsification of a lead that has stood for several rounds, and
it *narrows* the problem usefully: the working engine is the one this driver
already drives - BM, TMC, TMQ, NPP. We are not driving the wrong block. We are
driving the right blocks wrongly.

IDM's static content, for the record (it is a real, decoding register file, it
simply does not count frames):

```
921c8000: 03c36766 00000000 00000000 00000000
921c8010: 00000001 00000001 00000001 00001000
921c8020: 0000000a 0000001f 00000001 00000000
921c8080: 00000000 00000030 00290504 00290504
921c8090: 00290504 00000000 00000000 00000000
921c80c0: 00000000 08810101 08810101 00000000
921c8100: 00000000 00000000 00000001 00000001
```

### ★ gephy `+0x08` IS a per-port link-status word

The M3 probe read gephy `+0x00`, found `0x3988` identically on all four ports,
and concluded "so it is not a link-status word". Right block, wrong offset -
`+0x08` differs per port and tracks carrier exactly:

| window | `+0x08` | cable |
|---|---|---|
| `0x9b000000` (port 0) | `0x00000800` | none |
| `0x9b100000` (port 1) | `0x00000800` | none |
| `0x9b200000` (port 2) | `0x00000837` | **workstation** |
| `0x9b300000` (port 3) | `0x00000817` | **`tiny`** |

The two ports reading something other than `0x800` are exactly the two with a
cable on them. This driver has still never mapped the block, and the four
per-port interrupts (`0x27`-`0x2a`) remain unrequested.

### ★★★ `BM+0xa8` is a hardware RECEIVED-FRAME COUNTER — not a "pool depth"

The BM comparison table in this file records `BM+0xa8 = 0x722` (1826) in
U-Boot against 0 in Linux, and reasons: *"A quantity that consistent across
four registers is a pool depth, and we set none of them."* **That reading is
wrong.** It is a counter, and the earlier capture only looked like a depth
because it was taken after a single ~1900-frame transfer.

Three points, deliberately at very different frame counts:

| when | `BM+0xa8` | frames |
|---|---|---|
| historical reference, after 2.6 MB | 1826 | ~1900 |
| this session, after 2.6 MB + 40 MB | 30 721 | ~32 200 |
| **delta across one more 3 145 728 B transfer** | **+2146** | **expected ~2144** |

The third row is the measurement, not an inference: the counter advanced by
2146 for a transfer whose frame count at the observed ~1467 bytes/frame is
2144. `TMQ+0x68` advanced by **exactly the same 2146** in the same interval.
`TMQ+0x6c` carries the same value packed twice (`0x78017801`).

**Why this matters more than anything else here.** The wedge investigation has
wanted one thing for thirty rounds: a count of what the *hardware* received, to
compare against what the *driver* delivered. It looked for it at `TMQ+0x168`
and `+0x16c` and found zeros. It was in the buffer manager the whole time.
`BM+0xa8` read from Linux during a flood separates the two hypotheses that have
never been separable:

* `BM+0xa8` keeps climbing while `rx_packets` freezes -> the hardware is still
  receiving and **the driver stopped draining**. A driver bug, fixable.
* `BM+0xa8` freezes too -> the hardware stopped accepting, and the question
  moves to why.

### ✗ `TMQ+0x168`/`+0x16c` are not "produced" counters — the model built on them is void

On a datapath that had just moved 30 000 frames:

```
92350160: ff00ff00 00000000 00000000 00000000
92350170: 000000ff 00000000 00000000 00000000
```

`+0x168 = 0` and `+0x16c = 0` **while the engine was working perfectly**, which
is the same thing they read here at a wedge (2026-09-07, earlier section). A
register that is zero both when healthy and when wedged carries no information
about either. The round-150 note naming `0x168` "produced" and `0x170`
"consumed" does not survive this, and every "produced versus delivered"
argument resting on those two offsets should be treated as void.

**And a new wedge hypothesis falls straight out of `+0x170`.** The working
reference holds `0x000000ff` there. This driver writes its own *cumulative*
`done` count into that register on every poll (`writel(done, TMQ+0x170)`), a
number that grows without bound. If `+0x170` is a field rather than a counter -
and `0xff` on a 30 000-frame-old working engine says it is - then the driver has
been writing ever-larger values into a narrow field, and the interesting
question becomes what the engine does when that value wraps or overflows. This
is consistent with the one fact about the wedge that has survived everything:
the credit write is load-bearing (without it the budget collapses from ~3069
frames to 29), yet the wedge point is invariant under every value the driver
sweeps *into* it.

### The rest of the working reference, captured at ~32 200 frames

```
BM   923480c8: 00000400        (we write 0x200 and read back 0)
BM   923480d8: 00006000        (we write 0x4000)
BM   923480dc: 50000111        (our decode masks the top bits away)
BM   923480a8: 00007801   +b0: 00007800   +b8: 000077ff
BM   92348090: 0000f001   +98: 0000f000   (~2 per frame)
TMQ  92350068: 00007801   +6c: 78017801
NPP  921c0060: 00201000 00201000 00201000 00201000   +70: 00a01000
NPP  921c0080: 00000000        (again - the 0x1fd expectation stays retracted)
TMC  92340000: 00000100 00000010, rest of +0x00..0x7C zero
```

### What to do next, in order

1. Read `BM+0xa8` from Linux alongside `rx_packets` through a flood. This is
   now a two-outcome experiment and either outcome is progress.
2. Replay `BM+0xc8=0x400`, `+0xd8=0x6000` against the confirmed reference.
   `+0xc8` still does not stick from Linux - find out what gates it.
3. Treat `TMQ+0x170` as a field, not an accumulator, and test writing a bounded
   value.
4. Stop pursuing the IDM port. It is falsified.

## ★★★ 2026-09-07 — THE WEDGE, MEASURED: the hardware stops receiving, and the buffer accounting is inverted

Experiment 1 above gave the instrument; this is what it measured. A device-side
sampler read `BM+0xa8` (the hardware received-frame counter) once a second
alongside `rx_packets` while the workstation ran
`ping -f -c 8000 -s 1400 192.168.1.1`.

### ★★★ Both counters stop together — so the driver is not the one that stalls

| sample | `BM+0xa8` (hardware) | `rx_packets` (driver) |
|---|---|---|
| 19 | 244 | 227 |
| 34 | 2155 | 2138 |
| 55 | 4834 | 4821 |
| **58** | **5123** | **5111** |
| 61 | 5125 | 5111 |
| 64-121 (60+ s) | **5127, frozen** | **5111, frozen** |

The hardware counter creeps four counts past the driver's last delivery and then
**stops advancing entirely**, for over a minute, while the host is still
blasting 1400-byte frames at the port.

**This eliminates the whole "the driver stopped draining a still-filling ring"
family of hypotheses.** The receive engine itself stops accepting. Every
software-side fix aimed at how the NAPI poll walks the ring, releases
descriptors, or writes its consume credit is aimed at the wrong half of the
machine.

It also confirms the wedge point: 5111/5127 against the 5115 this file has
recorded three times.

### ★★★ The defect signature: two register pairs, inverted by exactly one pool

Read on the wedged device, against the working U-Boot reference captured the
same afternoon at 30 720 frames:

| register | U-Boot, working | Linux, wedged | delta within pair |
|---|---|---|---|
| `BM+0x90` | 61441 | 10248 | |
| `BM+0x98` | 61440 | 12285 | **U-Boot +1, ours −2037** |
| `BM+0xb0` | 30720 | 5121 | |
| `BM+0xb8` | 30719 | 7158 | **U-Boot +1, ours −2037** |

On the working engine each pair tracks its partner **within one**. On ours the
second register of each pair has run **2037 ahead** of the first - and it is the
*same* 2037 in both pairs.

2037 is ten short of **2047**, the number of usable buffers in the pool (2048
minus index 2047, the dedicated TX scratch buffer). The second of each pair has
run ahead by one entire pool.

### ★★★ This explains the 1023 lattice mechanically — and it is not the ring

`BM+0x90` counts **exactly 2.0 per frame** on the working reference
(61440 / 30720 = 2.000), and 10248 / 5127 = 1.999 on ours. So the datapath
consumes two buffers per received frame.

```
2047 usable buffers / 2 buffers per frame = 1023.5 frames per full pool cycle
```

**The "always an exact multiple of the 1023 usable ring slots" reading is a
coincidence of arithmetic.** The RX ring's 1023 usable descriptors and the
buffer pool's 2047-buffers-at-two-per-frame produce nearly the same number, and
this project attributed the period to the ring. The observed stopping points -
3069, 4092, 5115 - are **N complete traversals of the buffer pool**, and the
quantity that is actually wrong at the stop is the pool's alloc/free
bookkeeping, not the descriptor cursor. That is why round 251's sweep of
`rx_release`, `rx_credit_reg`, credit-repay and `rx_full_ring` moved the wedge
point not at all: every one of those knobs is on the ring side.

### Why "credit starvation" kept coming back inconclusive

At the wedge, `BM+0xdc` reads `0x00000111` - 34 free credits by the driver's own
`(v >> 3) & 0x3f` decode - and the census reports `nocredit=0` for the entire
run. **Credit is not exhausted.** The pool is not empty in the sense the driver
measures. What is wrong is that the free side of the accounting has overrun the
allocate side by a whole pool, which a "how many credits are left" read cannot
see. Both of this file's earlier readings were looking at the wrong quantity,
which is why the pool-exhaustion elimination could never be made to hold still.

The driver's two known buffer-accounting defects are now the prime suspects, and
both are on the free side:

* `zx_bm_free()` writes `BM_FREE` **unconditionally**, with no return value and
  no check that the buffer was ever allocated.
* TX allocates a buffer per frame via `zx_bm_alloc()` and then **discards the
  result**, overwriting it with `zx_tx_buf_idx` - so every transmit takes a
  buffer out of the pool's accounting and never puts that one back, while
  freeing a different index.

Either produces exactly this shape: frees outrunning allocations, drifting by
about one pool, until the engine stops.

### The three configuration registers we still get wrong

Unchanged at the wedge, and still differing from the working reference:

| register | working | ours |
|---|---|---|
| `BM+0xc8` | `0x400` | `0x200` (we write `0x200`; it now reads back, unlike the earlier note) |
| `BM+0xd8` | `0x6000` | `0x4000` |
| `BM+0xdc` | `0x50000111` | `0x00000111` |

Note `+0xc8` **did** read back `0x200` here, where this file previously recorded
it as reading back 0. Whatever gates that write, it is not permanent.

### What this makes the next experiments

1. Fix the TX allocate-and-discard leak so allocations and frees balance, and
   re-measure the `+0xb0`/`+0xb8` delta. If the delta stops growing, the wedge
   should move or vanish.
2. Make `zx_bm_free()` refuse to free a buffer the driver did not allocate.
3. Only then replay `BM+0xc8=0x400` and `+0xd8=0x6000`; they are configuration,
   and configuration is not what is drifting.
4. Watch `BM+0xb8 − BM+0xb0` as the health metric. On working hardware it is 1.
   It is the cheapest possible regression check and it needs no traffic
   analysis at all.

### ✗ RETRACTED, same day: "the pair is inverted by one pool" was a one-sample artifact

The section above reads the `+0xb0`/`+0xb8` and `+0x90`/`+0x98` gaps of 2037 as
a *drift* - frees outrunning allocations until the accounting overruns a whole
pool. **That is wrong, and it is wrong for the oldest reason in this file: it
was one sample, taken only at the wedge.** Sampled once a second through an
entire flood on a fresh cold boot, the gap is there from the very first sample
and does not move:

| sample | `+0xb0` | `+0xb8` | `+0xb8 − +0xb0` | `rx_packets` |
|---|---|---|---|---|
| 19 | 1689 | 3704 | **2015** | 1661 |
| 25 | 2466 | 4480 | **2014** | 2438 |
| 31 | 3239 | 5252 | **2013** | 3209 |
| 37 | 4018 | 6031 | **2013** | 3988 |
| 43 | 4801 | 6814 | **2013** | 4772 |
| 49 (wedge) | 5121 | 7134 | **2013** | 5087 |

Constant at ~2013 from start to finish. The `+0x90`/`+0x98` pair behaves
identically. So the gap is not drift at all - it is the **pool priming**:
`datapath_init()` frees the whole pool in at boot, so the free-side counter
starts ~2047 ahead and the two then advance in lockstep, one per frame, for the
rest of the run. 2047 primed minus the ~34 buffers `BM+0xdc` reports in flight
is 2013, which is exactly the observed offset.

**`BM+0xb8 − BM+0xb0` is therefore not a health metric and not a defect
signature.** Do not use it as the regression check recommended above. The U-Boot
reference reading of 1 reflects a differently-primed pool, not a healthier one.

### ★★ What the replication DID establish: allocation stops while frames keep arriving

The same run shows something the single sample could not. After the wedge,
across sixty-plus seconds:

* `BM+0xb0` and `BM+0xb8` are **frozen solid** - not one buffer allocated or
  freed.
* `rx_packets` is **frozen**.
* but `BM+0xa8`, the hardware frame counter, **keeps creeping**: 5039 → 5040 →
  5048 → 5054 → 5056.

So the MAC is still accepting frames off the wire after the wedge. What has
stopped is the step in between: **the datapath stops obtaining buffers.** Frames
arrive, no buffer is allocated to hold them, nothing is delivered, and nothing
is freed - which is also why the free-side counter freezes rather than running
away.

That is a much narrower target than "the RX path wedges", and it is consistent
with every previously confusing observation: `nocredit` stays 0 and `BM+0xdc`
still reports 34 free credits, because the driver's own credit accounting is
not what has failed. Something on the hardware side stops handing out buffers
while its own free counter still claims thousands are available.

The next experiments are therefore about the **allocation** path specifically -
`zx_bm_alloc()`'s `BM_REQUEST`/`BM_ALLOC_IDX` handshake, and what state the pool
is in when that handshake stops producing a valid index - not about descriptor
release, consume credit, or the ring cursor, all of which are downstream of a
buffer that was never obtained.

Note also, for whoever repeats this: the driver's own `zx_bm_alloc()` comment
records that the allocator "always returns raw `0x80000000` (index 0) and
`BM+0xdc` never moves". If the allocator never actually varied its answer, the
pool's real allocation state has never been visible to this driver at all.

## ✗ ELIMINATED 2026-09-07: `BM+0xc8` and `BM+0xd8` cannot be set to the reference values

`handoff.md` lists these as the **most actionable** open lever - three registers
that differ from the vendor's working datapath, "all testable at runtime through
`/proc/zx_eth_poke` on a `BRINGUP=1` build with no reflash". Both halves of that
turned out to be wrong, and the item is now closed.

**Runtime poke: rejected.**

```
zx-poke: [923480c8] = 00000200
zx-poke: [923480c8] 00000200 := 00000400 -> 00000200
zx-poke: [923480c8] = 00000200
```

The write is accepted by the bus and simply does not land. So these cannot be
swept at runtime, and the "no reflash needed" framing never applied to them.

**Written during cold `datapath_init()`: also rejected.** The obvious next step
was that the register latches, so the value has to be right at init. The driver
now writes both from module parameters defaulting to the reference values, and a
genuine cold power-cycle boot was used so that `datapath_init()` actually runs
(a `reset` from the U-Boot prompt leaves the MAC warm and the init is skipped -
that mistake cost one boot here):

```
zx279128-eth 92200000.ethernet: datapath init at probe (cold)
/sys/module/zx279128_eth/parameters/bm_cfg_c8 = 1024      <- 0x400 was written
zx-poke: [923480c8] = 00000200                            <- and did not stick
zx-poke: [923480d8] = 00004000                            <- nor did 0x6000
```

The parameter proves the code path executed with the intended value. The
register still reads the old one.

**So the difference from U-Boot is not something we can write.** `BM+0xc8` and
`BM+0xd8` are evidently derived or latched from some other configuration - pool
geometry, or a step in the vendor's init sequence we do not perform - rather
than being independently writable words. Chasing them directly is a dead end;
whatever sets them is upstream, and that is what would have to be found.

This leaves `BM+0xa8` as the only one of the three still worth anything, and its
value is now understood: it is the hardware received-frame counter (above), not
a pool depth we failed to set.

The parameters (`bm_cfg_c8`, `bm_cfg_d8`) are kept so the experiment is
repeatable and so the values are no longer unexplained constants in the source,
but they currently have no observable effect.

## ★ 2026-09-07 — the RX poll interval is a real throughput ceiling, but the wedge caps the run

The RX path has no interrupt; a 500 µs hrtimer stands in, and the poll *hunts* a
64-slot window rather than following a producer index. `rx_poll_us` is already a
module parameter, so this costs nothing to test.

Measured with a raw UDP blast (1400-byte datagrams, host-side sender) and
device-side `rx_bytes`/`rx_packets` sampled over a fixed window, each arm from
its own cold boot:

| `rx_poll_us` | window | bytes | packets | throughput |
|---|---|---|---|---|
| 500 (default) | 8 s | 5 785 304 | 4012 | **5.79 Mbit/s** |
| 100 | 4 s | 5 824 238 | 4039 | **11.65 Mbit/s** |

The 500 µs figure independently reproduces the 5.85 Mbit/s this file already
records, which validates the instrument.

**Two readings, and the second matters more.** Cutting the poll interval 5×
doubles the delivered rate (501 → 1010 packets/s), so the poller genuinely is a
throughput limiter and retiring it is worth real bandwidth. But note both arms
delivered **~4000 packets and then stopped** - the same total, reached in half
the time. The frame budget is what ends the run, not the clock. So:

* **Rate** is limited by the poller (and would be limited by it far less with a
  real RX interrupt, of which five are declared in the stock DTS and none has
  ever been requested).
* **Sustained transfer** is limited by the wedge, and no poll setting changes
  that. Speeding the poller up just reaches the wall sooner.

Note also the scaling is sub-linear: 5× the poll rate for 2× the delivery, so
the hunting scan is not the only cost in the path.

**Method note for whoever repeats this:** `iperf3` cannot measure the wired path
at all, in either direction, and this is not a configuration mistake. Its
control protocol exchanges JSON over TCP *with payload*, which is precisely what
does not cross - so the client connects and then hangs, blocking the shell it
was started from. (That is also the real explanation for this file's older
"iperf3 connects, then transfers 0 bytes" observation.) Use a raw UDP sender and
count bytes device-side. Write the results somewhere persistent, too: `/tmp` is
tmpfs, and the power cycle that recovers the wedge takes the measurement with
it.

## ✗ 2026-09-07 — the five declared datapath interrupts do NOT fire

`README.md` and this file have both carried "there is no RX interrupt" as a
lever waiting to be pulled: the stock DTS declares five datapath interrupts -
IDM `0x26` and one per GE port from gephy, `0x27`-`0x2a` - and this driver had
never requested any of them. The honest form of that claim was "we have never
wired one up". Now we have.

The DTS now lists all five on the ethernet node and a BRINGUP-only probe
requests them with a handler that does nothing but count (and muzzles its own
line past a bounded number of hits, because a level-triggered line we cannot
acknowledge would livelock the CPU with no console).

All five were granted, and map exactly as expected - GIC hwirq 70-74 for
`GIC_SPI 38`-`42`:

```
 27:  0  0  GIC-0  70  Level  idm
 28:  0  0  GIC-0  71  Level  gephy0
 29:  0  0  GIC-0  72  Level  gephy1
 30:  0  0  GIC-0  73  Level  gephy2
 31:  0  0  GIC-0  74  Level  gephy3
```

**All five stayed at zero** through a UDP blast of ~427 000 offered datagrams
(~4000 of which the device actually received before wedging). Not one assertion.

So there is no ready-made RX interrupt sitting unused on these lines. Either
they need an enable we have not found, or they serve something other than
receive. This is consistent with the other finding from the same day: neither
IDM nor gephy registers move at all on the vendor's own working datapath, so
both blocks appear inert in this configuration.

### ★ The synthesis that matters: an RX interrupt is not what stands between us and 80 Mbit/s

Put the two measurements together:

* Vendor U-Boot sustains **~80 Mbit/s across 40 MB** on this hardware.
* U-Boot has no interrupt handling in its network path at all - **it polls.**

So polling is demonstrably sufficient for 80 Mbit/s on this silicon, and the
gap between 5.79 Mbit/s and that figure is **not** explained by our lacking an
interrupt. It is explained by *how* we poll: a 500 us hrtimer driving a scan
that hunts a 64-slot window and jumps forward when it finds nothing, rather than
following a producer index the way the bootloader does.

That reorders the throughput work. "Wire up a real RX interrupt" drops down the
list - it may not even be possible on these lines. "Follow a producer index
instead of hunting" moves up, and it is the same subsystem the wedge lives in.

## ✗ 2026-09-07 — the wedge is flow-BLIND, so the flow accelerator does not explain it

`research/FFE-NPU-FLOW-ACCELERATOR.md` and this file both raise the possibility
that the vendor's flow accelerator learns a flow and forwards it nowhere, which
would be a different fix from anything in the driver. That is testable directly:
a flow-state-driven limit must care how many flows there are.

Two UDP blasts, each from its own cold boot, identical except for the
destination port:

| arm | distinct flows | frames received before the stop |
|---|---|---|
| single destination port | 1 | **4042** |
| destination port rotating over 20 000 | thousands | **4046** |

**A 0.1% difference.** The limit does not move at all.

So whatever stops the receive path is **flow-blind**, and the flow accelerator
is not what produces the wedge. Combined with the earlier finding that the wedge
is also content-blind (it stops UDP just as readily as anything else) while the
TCP defect is sharply *content-selective* - 1442-byte UDP accepted at 4000 pps
where 271 bytes of TCP payload never is - this is now solid on its own evidence:

> **The wedge and the TCP defect are two different mechanisms.** They should be
> worked, and reasoned about, separately. An earlier framing in this session
> that hoped one root cause would explain both is wrong, and this is the
> measurement that settles it.

It also narrows the wedge further in a useful direction: content-blind,
flow-blind, rate-insensitive in its stopping point (~4000 frames whether reached
in 4 s or 8 s), and landing on the buffer-allocation path. That is the profile of
a counter or a pool traversal, not of a classifier.

## ★★ 2026-09-07 — the SPA indirect port is INERT, and that closes the classifier route

`research/SIBLING-DRIVER-RX-AND-SPA.md` §2.4 identifies the sibling's actual TCP
fix: a 512-entry packet-type table written through the SPA indirect port with
`mem_id 0x40`, which decides what gets trapped to the CPU. That is the one
concrete lead this project has ever had for the TCP defect, so it was tried.

Our SPA base is `0x921cc000`; the sibling's `IND_CMD`/`IND_STATUS`/`IND_DATA`
sit at `+0x54`/`+0x58`/`+0x5c`.

**`IND_STATUS` never asserts**, for either transaction the sibling performs -
`mem_id 0x40` (the packet-type table) or the `mem_id 0` address 10 read that its
`spa_port_attr_init()` does first:

```
baseline      921cc000 = 00000011   (SPA global config - real content)
              921cc054 = 00000000   921cc058 = 00000000   921cc05c = 00000000
after CMD mem_id=0x40 addr=0 : 921cc058 = 0 x5 polls
after CMD mem_id=0   addr=10 : 921cc058 = 0 x5 polls, 921cc05c = 0
```

**And the command register does not even latch:**

```
zx-poke: [921cc054] 00000000 := 04000000 -> 00000000
```

So this is not a port that accepts a command and fails to complete it. It does
not accept the command at all. Every downstream question - polling order, which
`mem_id`, what to write into the table - is moot while the port is inert.

### Why it is inert, and why that is the end of this route

The sibling wakes its NP front-end in `zx279133_np_reset_prepare()`, and the
first thing that function does is a reset sequence on `SYS_SOFT_RESET` at NPPT
`+0x2c0004`. **That offset does not exist on this SoC** - it is one of the high
offsets this file already records as not transferring, because it collides with
our MAC ports 2 and 3. Past that gate the sibling then loads
`zte/zx279133/mcode_intel.bin` into the PPU cluster *before* the first SPA
access, and that blob lives in the AES-encrypted vendor rootfs whose key is
unknown after 288 credential combinations, a web-UI injection attempt and eight
eFuse key arrangements.

So the route needs two things we do not have: a reset controller whose address
did not transfer, and a firmware blob that is not extractable.

### Stop rule invoked

Per the plan this work was following: if the packet-type table does not move
`tcp_data` off zero, **record it as a hardware limitation rather than continue
indefinitely**. It cannot even be attempted - the port will not take a command.

**The wired TCP defect is therefore not fixable by this project as things
stand**, and the honest statement for users is the one already in `README.md`:
the device is an access point whose clients can reach it, not a general-purpose
wired router. WiFi remains the management path, and it is unaffected because
mt76 receives on its own PCIe DMA and never enters this driver's ring.

What would reopen it: the vendor rootfs key (which would yield both `np.ko` and
`mcode_intel.bin`), or finding this SoC's equivalent of `SYS_SOFT_RESET` -
`docs/ETHERNET.md`'s M4 section already suggests diffing the three CRM blocks
between a bootloader-initialised and a cold boot as the cheapest way to name it,
and that has not been done.

## ★★ 2026-09-07 — at the wedge: BM_FREECNT bit 30 asserts, and the handshake is NOT stuck

Read-only probe of the buffer-manager allocation path, healthy versus wedged,
WiFi absent so the firmware hang cannot confound the boot.

| register | healthy | wedged |
|---|---|---|
| `BM_REQUEST` `0x92348014` | `0x00000000` | **`0x00000000`** |
| `BM_ALLOC_IDX` `0x9234800c` | `0x00000000` | `0x00000000` |
| `BM_FREECNT` `0x923480dc` | `0x00000111` | **`0x40000111`** |
| `BM+0xa8` | `0x24` | `0x2c` |
| `BM+0xb0` | `0x31` | **`0x1401`** |
| `BM+0xb8` | `0x819` | `0x17e0` |

### The allocation handshake is not hung

`BM_REQUEST` reads **0** at the wedge, not 1. The driver's `zx_bm_alloc()`
writes 1 and polls for it to clear; a hardware that had stopped servicing
allocations would leave it set. It is clear, so the handshake completes - it
simply yields nothing (`BM_ALLOC_IDX` = 0, no VALID bit). That rules out
"allocation hangs mid-transaction" and points instead at the pool having nothing
to hand out, or refusing to.

### ★ BM_FREECNT's top bits are live state, and the driver masks them away

`zx_bm_free()` decodes free credit as `(v >> 3) & 0x3f`, which discards
everything above bit 8. The top bits are not idle:

```
U-Boot, working datapath : 0x50000111    (bits 28 and 30 set)
ours, healthy            : 0x00000111    (neither)
ours, wedged             : 0x40000111    (bit 30 set)
```

The low half is identical in all three - `0x111`, decoding to 34 credits - which
is exactly why every "is the pool starved?" reading came back the same whether
the device was working or dead. **The information that distinguishes them is in
the bits the driver throws away**, and bit 30 asserting is the first signal this
project has that correlates with the wedge rather than being invariant across it.

This file already suspected as much ("if those bits are a validity or ready flag,
the driver has been reading a credit value it should have been rejecting"). It
is now measured. Note also that the *working* reference has bit 28 set as well,
and we never have it in either state.

**Next experiment, and it is cheap:** log the full `BM_FREECNT` word rather than
the masked credit, sample it through a flood, and find out whether bit 30 sets
at the wedge or some time before it. That distinguishes a cause from a symptom,
and it needs no more than widening one existing debug line.

### ✗ A caveat on `BM+0xa8` that must not be swept under the rug

The section above identifies `BM+0xa8` as the hardware received-frame counter,
on three points at different frame counts. **This run does not fit that.**
`BM+0xa8` moved only 0x24 -> 0x2c (36 -> 44) across a flood that drove `BM+0xb0`
from 0x31 to 0x1401 (49 -> 5121) and wedged the device.

Either the register is not simply a frame counter, or something reset it between
the healthy read and the wedged one. The earlier identification stands on its own
measurements - including a delta of 2146 against an expected 2144 - so this is a
contradiction to resolve, not a retraction to make yet. Whoever picks this up
should re-establish `BM+0xa8`'s semantics before building on either reading.

### ⚠️ Do not drive BM_REQUEST from userspace on a live system

The first version of this probe *wrote* 1 to `BM_REQUEST` to exercise the
handshake by hand. It hung the box completely - console and network both dead -
because `zx_bm_alloc()` takes `bm_lock` around exactly that sequence and a
userspace poke races the driver's own allocator mid-handshake. Read the
registers; never drive them while the driver is running.

## 2026-09-07 — bit 30 tracked through a flood: confirmed, but 1 Hz is too coarse to call cause or symptom

Follow-up to the finding above. `BM_FREECNT` sampled once a second through a
flood, full word, alongside `BM+0xb0` and `rx_packets`:

| sample | `BM_FREECNT` | `BM+0xb0` | `rx_packets` |
|---|---|---|---|
| 1-13 | `0x00000111` | `0x4d` (77) | 53 |
| **14** | **`0x40000111`** | **`0x1401`** (5121) | **4070** |
| 15-80 | `0x40000111` | `0x1401` | 4070 |

**What this establishes:** bit 30 is clear before the flood, set afterwards, and
stays set for the remaining sixty-plus seconds. It is not noise and it is not
transient. `BM+0xb0` lands on `0x1401` for the **fourth consecutive run**, across
different traffic patterns and both with and without the WiFi driver loaded -
that constant is now about as well replicated as anything in this file.

**What it does NOT establish, and the honest reason:** the device absorbed
roughly four thousand frames, wedged, and set bit 30 **all inside a single
one-second sample**. Sample 13 has 53 frames and a clear bit; sample 14 has 4070
frames, the wedge, and a set bit. Nothing at 1 Hz can order those three events.

So the question this experiment was designed to answer - does bit 30 set *at*
the wedge (symptom) or some frames *before* it (cause) - is still open, and
claiming otherwise from this data would be exactly the kind of inference this
file keeps having to retract.

Incidentally the same numbers say the datapath takes frames far faster than the
paced measurements suggest: ~4000 frames inside one second under a full blast,
against the 500-1000 frames/s measured with `rx_poll_us` pacing. That is
consistent with a fixed frame budget consumed as fast as it is offered, rather
than a rate limit.

**The next experiment has to sample in the driver, not from userspace.** A
`/proc` poke read costs a console round trip and a `dmesg` parse, so 1 Hz is
about its ceiling. What is needed is a small in-driver ring that records the full
`BM_FREECNT` word on every NAPI poll and can be dumped afterwards - at poll rate
that is thousands of samples across the transition instead of one, and it would
settle cause versus symptom in a single run.

## ★★★ 2026-09-07 — ANSWERED: BM_FREECNT bit 30 is simultaneous with the wedge, not a precursor

The question left open above - does bit 30 set *before* the wedge (a cause) or
*at* it (a symptom)? - is now answered, with in-driver sampling at NAPI poll
rate rather than the 1 Hz userspace poking that could not order the events.

`/proc/zx_eth_fc` records the full `BM_FREECNT` word whenever it changes and
periodically otherwise, freezes when full so the interesting first events are
kept, and is re-armed by writing to it. Armed immediately before a flood:

| poll | `BM_FREECNT` | `BM+0xb0` |
|---|---|---|
| 1, 1024, 2048, 3072 | `0x00000111` | `0x34` (52) |
| **4089** | **`0x40000111`** | **`0x1401`** (5121) |
| 4096 onward | `0x40000111` | `0x1401` |

The entry at poll 4089 is **change-triggered**, not periodic (the periodic ones
land on multiples of 1024). So it fired the instant `BM_FREECNT` changed - and
at that same instant `BM+0xb0` already reads its terminal `0x1401`.

**Bit 30 and the wedge are simultaneous to within one poll, ~500 us.** There is
no window in which the bit is set and the datapath is still running. It is a
symptom or a co-indicator, not an early warning, and a driver that watched it
would learn nothing it could act on in time.

That closes off the most attractive reading of the earlier finding. What
survives is narrower but still useful: bit 30 is a **reliable, cheap wedge
detector** - one register read, no traffic analysis, unambiguous - which is
worth having for the heal path and for any future soak harness.

Note also `BM+0xb0` jumps from 52 to 5121 within at most 1017 polls. It is not
incremented once per poll, so it counts something faster than the poll loop or
advances in bursts.

### ✗ RETRACTED: `BM+0xa8` is NOT the hardware received-frame counter

Earlier the same day this file identified `BM+0xa8` as a hardware frame counter,
on three points including a delta of 2146 against an expected 2144, and built
the "produced versus delivered" instrument on it. **That identification is
wrong.**

Across this run - a flood that pushed roughly four thousand frames and wedged
the device - `BM+0xa8` moved **33 to 38**. Five. The previous run showed the
same shape (38 to 42). A counter of received frames cannot read 38 after four
thousand frames.

The three supporting points were all taken from **U-Boot**, where the register
plausibly means something else, or where the correlation with transfer size was
coincidental. The two contradicting observations are from Linux under load and
are unambiguous.

So `BM+0xa8` should be treated as **semantics unknown** until someone
establishes them deliberately, and the "hardware frame counter" instrument this
file proposed does not exist. The wedge-side conclusions that rested only on
`BM+0xb0` and on `rx_packets` are unaffected; anything resting on `BM+0xa8`
needs re-deriving.

This is the third claim from this session's own work to be withdrawn, and the
pattern is the same each time: a striking correlation from a handful of points
in one regime, contradicted the moment it was measured in another.

## ★★★ 2026-09-07 — `BM+0xb0` advances 64 per poll and halts at exactly 5 x 1024 + 1

Same instrument, ring widened to 256 entries and sampled every 16 polls, armed
immediately before the flood. Showing only the rows where `BM+0xb0` moves:

| poll | `BM_FREECNT` | `BM+0xb0` | decimal | delta |
|---|---|---|---|---|
| 1 | `0x00000111` | `0x39` | 57 | |
| 32 | `0x00000111` | `0x225` | 549 | +492 |
| 48 | `0x00000111` | `0xacb` | 2763 | +2214 |
| 64 | `0x00000111` | `0xecb` | 3787 | **+1024** |
| 80 | `0x00000111` | `0x12cb` | 4811 | **+1024** |
| **90** | **`0x40000111`** | **`0x1401`** | **5121** | +310, then stops |

Two things fall straight out, and both are new.

### The increment is exactly 64 per poll - the driver's own scan window

Between poll 48 and 64, and again between 64 and 80, `BM+0xb0` rises by exactly
**1024 across 16 polls**. That is **64 per poll**, and 64 is precisely the size
of the window this driver's RX poll hunts before giving up and jumping forward.

So `BM+0xb0` is not counting received frames, and not counting buffers the
hardware consumed. It tracks **ring slots the driver has walked** - it advances
whether or not those slots contained anything. That also explains why it climbs
steadily during an idle-ish period (57 -> 549 -> 2763 before the flood has
really started) while `rx_packets` barely moves.

### It halts at 5 x 1024 + 1, on the ring lattice

`5121 = 5 * 1024 + 1`. This file has recorded stopping points of 3069
(3 x 1023), 4092 (4 x 1023) and 5115 (5 x 1023) and called the pattern a "1023
lattice"; earlier today I argued the real quantity was the 2047-buffer pool at
two buffers per frame. **Both readings look wrong.** What actually halts at a
ring-quantised value is `BM+0xb0`, and it halts at a multiple of **1024** - the
full ring, not the 1023 usable slots and not the buffer pool - plus one.

That the multiplier is 5 here, and was 3, 4 and 5 in the historical
`rx_packets` observations, is consistent: those were counting delivered frames,
which is a lossy proxy for slots walked. `BM+0xb0` is the direct quantity and it
is exactly on the lattice.

### What this changes

The wedge is now much more specifically framed: **something stops after the
driver has walked five complete rings' worth of slots**, and `BM_FREECNT` bit 30
asserts at that same instant. It is a slot/traversal limit, not a frame budget,
not a rate limit, and not buffer-pool exhaustion - the pool still reports 34 free
credits throughout.

Note also the 64-per-poll coupling: the hunting scan is what advances this
counter, so the driver's own scanning strategy is directly implicated in
reaching the limit. A poll that followed a producer index instead of walking 64
slots blind would advance `BM+0xb0` far more slowly per frame - which makes the
producer-index change (already the top throughput item after E6) also the most
promising wedge intervention available without new register knowledge.

### ★ Replicated three times - the caveat is discharged

The paragraph that stood here asked for replication before anyone built on a
single run, and specifically whether the multiplier is always 5 or varies the
way the historical `rx_packets` numbers (3, 4, 5) did. Three independent cold
boots, same image, same flood:

| run | `b0` at poll 48 | at poll 64 | delta | halt value | bit 30 |
|---|---|---|---|---|---|
| original | 2763 | 3787 | **+1024** | **5121** | set |
| replicate 1 | 3525 | 4549 | **+1024** | **5121** | set |
| replicate 2 | 3670 | 4694 | **+1024** | **5121** | set |

* **64 per poll: confirmed three times.** Exactly 1024 across 16 polls in every
  run, from three different starting offsets.
* **The stop is 5121 = 5 x 1024 + 1 every time.** The multiplier does **not**
  vary. The historical spread of 3, 4 and 5 came from `rx_packets`, which counts
  delivered frames and is a lossy proxy; the direct quantity is fixed.
* **Bit 30 sets in the same entry** in all three.
* `BM+0xa8` read 37-51 throughout while thousands of frames flowed - a fourth
  independent observation against its retracted "frame counter" identification.

So the wedge fires at a fixed, exactly ring-quantised count of slots walked, and
that count is the same on every boot. That is a far tighter constraint than
anything previously recorded here, and it is what makes the producer-index
change testable as a wedge fix rather than only as a throughput change: if the
limit is slots walked, walking fewer slots per frame should move the wedge
further out in frames, proportionally and predictably.

## ✗ 2026-09-07 — FALSIFIED: "idle polling consumes the slot budget"

The `BM+0xb0` result above showed the counter climbing from 57 to 2763 across
the log's first 48 poll entries, seemingly *before* the flood delivered much.
Since `BM+0xb0` is a hardware register that never resets and the wedge fires at
a fixed 5121, that suggested an attractive and alarming reading: idle polling
burns the budget, so **a device that has been up a long time should wedge almost
immediately** when traffic finally arrives. It would also have explained the
historical spread in recorded stopping points.

Tested directly - two cold boots, identical flood, the only difference being how
long the device sat idle first:

| arm | idle before flood | frames delivered before the wedge |
|---|---|---|
| A | none, flooded as soon as it answered ping | **4074** |
| B | 150 s | **4071** |

**Three frames apart. The hypothesis is wrong.**

The error was reading the log's `poll=` numbers as wall-clock. `zx_eth_poll()`
only runs when NAPI is scheduled, so during genuine idle the poll counter barely
advances - polls 1 through 90 in those logs span the arm/flood/wedge window, not
a quiet period. Had idle really consumed 64 slots every 500 us, 150 s would be
19 million slots and the device would have wedged while doing nothing at all.
It plainly does not.

### What this strengthens

The budget is **not** a function of uptime, and it is not consumed by scanning
when there is nothing to scan. Collected with everything else measured today,
the frames-before-wedge figure is now invariant under a striking range of
conditions:

| varied | values seen | frames before wedge |
|---|---|---|
| offered rate / poll interval | 500 us, 100 us | ~4000 either way |
| flow count | 1 flow, ~20 000 flows | 4042 / 4046 |
| WiFi driver | loaded, absent | ~4070 both |
| idle before traffic | 0 s, 150 s | 4074 / 4071 |

Rate-blind, flow-blind, WiFi-blind, uptime-blind, and landing on 5121 slots
walked every time. Whatever the limit is, it is counted in the work actually
done and nothing else - which is exactly the shape of a fixed-size resource
being traversed, and it is why the producer-index change remains the intervention
worth testing: it is the only lever identified that changes *slots walked per
frame* rather than changing the rate at which they are walked.

## ✗✗ 2026-09-07 — RETRACTED: "BM+0xb0 counts ring slots walked, 64 per poll = the scan window"

The section above concluded that `BM+0xb0` advances 64 per poll because 64 is
the size of the RX scan window, and therefore that it counts **slots walked** -
which made the driver's scanning strategy directly implicated in the wedge and
made the producer-index change the obvious intervention. It replicated three
times, so it looked solid.

**It is wrong, and the coincidence was 64 appearing twice.**

The scan window is now a module parameter (`rx_window`). Set to **16** - a
quarter of the previous value - on a fresh cold boot, with the log armed
immediately before the flood:

| poll | `BM+0xb0` | delta over 16 polls |
|---|---|---|
| 3968 | 1377 | |
| 3984 | 3279 | |
| 4000 | 4303 | **+1024** |
| 4016 | **5121** | halt |

**Still exactly 1024 per 16 polls. Still 64 per poll.** The scan window has no
influence on it whatsoever.

The 64 is the **NAPI budget**, not the window: the poll loop is
`while (done < budget)` and the budget is 64, so a saturated poll processes at
most 64 descriptors. `BM+0xb0` therefore counts **descriptors consumed**, capped
at 64 per poll by NAPI - not slots examined.

That the two numbers were both 64 is exactly the kind of coincidence this file
keeps getting caught by, and the replication did not help because every replicate
used the same window.

### What the corrected reading says

* `BM+0xb0` = descriptors consumed. It halts at **5121 = 5 x 1024 + 1**, i.e.
  after **five complete traversals of the 1024-entry descriptor ring**.
* It exceeds delivered frames (~4070) by about 1050, or 26%. That gap is
  consistent with descriptors that are consumed but never become an skb - the
  rejected and zero-length ones the census counts in the millions.
* The scan window genuinely does not matter: window 64 delivered ~4070 frames
  before the wedge, window 16 delivered 4023. About 1% apart.

### Consequence for the intervention

**The producer-index change is no longer justified as a wedge fix.** The
argument for it was that it would reduce slots walked per frame; since the limit
is not slots walked, that argument is void. It remains worth doing for
throughput on the E6 evidence, but it should not be expected to move the wedge.

What the corrected reading points at instead is the **descriptor-consumption
path**: something stops after exactly five ring traversals' worth of consumed
descriptors, regardless of how those descriptors were found, how fast they
arrived, how many flows they belonged to, or how long the device had been up.
A five-traversal limit with a hard stop looks like a wrap or sequence-number
field being exceeded, not a resource being exhausted - and `BM_FREECNT` still
reporting 34 free credits at the stop supports that.

## ★ 2026-09-07 — the counter does not saturate: U-Boot drove the same register six times past our stop

Before chasing "five ring traversals" as a wrap or sequence limit, check it
against the working reference already captured this session. On the vendor
bootloader's datapath, after a 40 MB transfer:

```
BM+0xa8 = 30721    BM+0xb0 = 30720    BM+0xb8 = 30719
```

**`BM+0xb0` reached 30720 in U-Boot - six times our 5121 - with no stop.** So
the register is at least 15 bits wide, does not saturate at 5121, and the value
itself is not a hardware ceiling. Whatever ends our run is not the counter
running out of room.

That weakens the "wrap or sequence field exceeded" reading offered above. It
also rules out the ring-size test that would otherwise discriminate "five ring
traversals" from "5121 descriptors": the driver deliberately does **not**
reprogram `TMC_RING_BASE` (the bootloader sets the geometry and the driver's
`RING_ENTRIES 1024` is an assumption about it, not a configuration), so the ring
size cannot be varied from our side without desynchronising the driver from the
hardware.

### One arithmetic coincidence worth recording, not yet a claim

`5121 = 10 x 512 + 1`, and **512 = 0x200 is exactly the value we write to
`BM+0xc8`** - the register whose working-reference value is `0x400` (1024) and
which refuses every attempt to change it, at runtime and during cold
`datapath_init()` alike.

If `BM+0xc8` sizes something the datapath traverses, then a value half the
vendor's would give a proportionally smaller budget, and our stop being an exact
multiple of it would follow. Against that: U-Boot's own reference reached 30720
with `0xc8 = 0x400`, which is 30 x 1024, not 10 x 1024, so the multiplier is not
constant across the two regimes.

It is recorded because the two facts we cannot otherwise connect - a register we
provably cannot write, and a stop at an exact multiple of the value we write to
it - are worth one experiment if anyone finds what gates `BM+0xc8`. That gate is
now the single highest-value unknown in the wedge investigation.

## ★★★ 2026-09-07 — bit 30 is a LIVE status flag, and the credit count is lying

Web research turned up a structurally very close public analogue for this
buffer manager: **Broadcom's FPM**, GPL source in `RMerl/asuswrt-merlin.ng`
(`bcmdrivers/opensource/char/fpm/impl1/fpm_priv.h`). The correspondence is
close enough to be worth trusting for register *shape*:

| FPM | ours |
|---|---|
| token index with `FPM_TOKEN_VALID_MASK` at **bit 31** | `BM_ALLOC_IDX`, VALID in bit 31 |
| `__fpm_token_to_buffer()` = `base + index * chunk` | our fixed-stride 2 KiB buffer array |
| `pool1_alloc_dealloc`: read to allocate, write token to free | `BM_REQUEST` / `BM_FREE` |
| `pool1_stat2`: **count in the low bits, status in the high bits** | `BM_FREECNT` |

FPM's high bits are `POOL_FULL` (31), `FREE_FIFO_FULL` (29), `FREE_FIFO_EMPTY`
(28), `ALLOC_FIFO_FULL` (27), `ALLOC_FIFO_EMPTY` (26). **Bit 30 is undefined in
the public header, but every neighbour is a pool-or-FIFO full/empty status.**

### The test: bit 30 does not clear

If bit 30 were a latched error, a write-1-to-clear would clear it. Tested on a
wedged device:

```
zx-poke: [923480dc] = 40000111
zx-poke: [923480dc] 40000111 := 40000000 -> 40000111
zx-poke: [923480dc] = 40000111
```

**Unchanged.** The write does not clear bit 30, and does not zero the low bits
either. `BM_FREECNT` is read-only status, so bit 30 is a **live condition that is
true for as long as the datapath is dead** - exactly the FPM-style full/empty
flag its neighbours suggest, not an error latch.

### What that makes the mechanism

Put together with what was already measured:

* Allocation **completes but yields nothing**: `BM_REQUEST` clears (so the
  handshake is serviced) and `BM_ALLOC_IDX` reads 0 with no VALID bit.
* `BM_FREECNT`'s low bits still decode to **34 free credits**, unchanged from
  idle, and `nocredit` is 0 for the entire run.
* Bit 30 - by analogy, a pool/FIFO empty-or-full status - is asserted and stays
  asserted.

The coherent reading: **the credit count is lying.** The low bits report buffers
that the allocator cannot actually hand out, because the structure it allocates
*from* - an allocation FIFO, or the pool's own free list - is empty. Freed
buffers are being written to `BM_FREE` but are not finding their way back into
whatever the allocator draws on.

That reframes the target precisely. It is not "the pool ran out" (the count says
otherwise and the count is what every previous investigation trusted), and it is
not the allocation handshake (which is serviced correctly). It is the **refill
path between `BM_FREE` and the allocator**.

### Two named next experiments

1. **Dump `BM+0x60` and `BM+0x64` from U-Boot** after a working transfer. In the
   FPM layout the registers immediately around the count/status pair carry the
   pool and FIFO configuration; ours are unread in both regimes.
2. Re-read the driver's `zx_bm_free()` against this reading. It writes `BM_FREE`
   unconditionally and has no way to observe whether the free was accepted; if
   the free FIFO is full or gated, those writes are discarded silently and the
   allocator starves while the count stays flat - which is precisely the observed
   signature.

### Also from the research, and it settles an open design question

Descriptor slot index **is** the buffer index in this family, so descriptor
writeback is scattered by construction - there is no producer index to follow,
and the driver's scan-and-skip is a forced consequence of the hardware layout
rather than a poor choice. That independently confirms the retraction above:
the producer-index change is not available on this hardware at all, and the
sibling ZX279133 only escapes it by moving to 24 queues each with its own
hardware ready-count register.

## ★★★ 2026-09-07 — the "free credit" the driver tracks is a CONSTANT, not a count

Collecting every `BM_FREECNT` reading taken today across three genuinely
different machine states:

| state | `BM_FREECNT` |
|---|---|
| U-Boot, mid-40 MB transfer at 10 MiB/s | `0x50000111` |
| Linux, healthy and idle | `0x00000111` |
| Linux, wedged | `0x40000111` |

**The low 12 bits are `0x111` in all three.** They do not move between a
bootloader moving thirty thousand frames, an idle Linux, and a dead datapath.

`zx_bm_free()` decodes free credit from this register as `(v >> 3) & 0x3f`,
which on `0x111` yields 34 - and that is where the "34 free credits" figure that
appears throughout this file comes from. A quantity that is bit-identical in
every state a machine can be in is not a count of anything. **It is
configuration, and the driver has been reading it as a credit balance.**

That single fact retires a long line of investigation:

* It explains why `nocredit` has been 0 through every run ever recorded here,
  including runs that ended in a dead datapath - the code path that increments
  it is gated on a value that is never zero because it is never anything but
  `0x111`.
* It explains why "is the pool starved?" always came back the same whether the
  device was healthy or wedged.
* It means `ze->sw_free_credit`, the four-attempt refill loop above it, and the
  decrement bookkeeping are all operating on a constant. The comment in
  `zx_bm_free()` worrying that "a credit-starved free path would reject the
  re-prime for the same reason it rejects everything else" describes a mechanism
  that, on this evidence, does not exist.

The only part of `BM_FREECNT` that carries state is the **high** half - and that
is precisely the half the `(v >> 3) & 0x3f` mask discards. `0x5` in the top
nibble when the vendor's datapath is working, `0x0` when ours is healthy, `0x4`
when ours is wedged.

### What to do with this

1. **Stop treating `BM_FREECNT` as a credit count.** The `sw_free_credit`
   machinery in `zx_bm_free()` should be deleted or reduced to a status read; it
   is currently ceremony around a constant.
2. **Report the high bits.** The census should print the full word. Bit 30 is a
   live wedge indicator (proved by the write-1-to-clear test above) and is free
   to sample; the driver currently throws it away on every call.
3. The vendor's `0x5` versus our `0x0` in the top nibble on an otherwise healthy
   datapath is now the most concrete difference on record between their working
   configuration and ours, and it is **not** something we write - `BM_FREECNT`
   is read-only. Whatever sets it is upstream, and it is the same class of
   unknown as the gate on `BM+0xc8`.

Recorded with the caveat this session has earned: the three readings are one
observation each, from three states. Before deleting the credit code, sample the
word repeatedly under load and confirm the low half really never moves.

### The credit code is now removed, and the census reports the real word

`zx_bm_free()` no longer reads `BM_FREECNT` at all. Deleting the credit block
is provably behaviour-preserving - `writel(idx, BM_FREE)` was unconditional in
both branches, so the credit could never gate a free - and it removes up to four
uncached register reads per received frame from the hot path.

The census now prints the full status word in place of the useless `nocredit`:

```
census icmp=5  udp=12   ... zerolen=43190  rej=0 freecnt=00000111   <- healthy
census icmp=11 udp=4050 ... zerolen=113683 rej=0 freecnt=40000111   <- wedged
```

The wedge is now visible directly in the periodic log line, in the field that
previously always read `nocredit=0`.

**No throughput gain was measurable, and the reason matters more than the
result.** Before: 5 785 304 B / 8 s = 5.79 Mbit/s. After: 5 831 448 B / 8 s =
5.83 Mbit/s. Under 1% apart, which is noise.

That is not evidence the removed reads were free. **Every run is capped at
~4040 frames by the wedge**, so an 8-second window is mostly post-wedge dead
time and the figure it produces is "frames until the wedge divided by the
window", not a sustained rate. Per-frame cost cannot be measured on this
hardware until something survives a sustained transfer. Any throughput claim
made against a wedging run - including the 5.79 and 5.85 Mbit/s figures this
file has quoted for months - is measuring the wedge.

## ✗ 2026-09-07 — removing the BM_FREE fill does NOT make the DDR tables load

This driver's `datapath_init()` carries a long-standing note:

> U-Boot never writes BM+0x10 … its pool works - it is fed purely by the DDR
> free-list tables. We need the explicit fill, which means **our tables are
> never consumed, matching BM+0xdc never gaining its pool-loaded bits**.

Those "pool-loaded bits" are now identified: `BM_FREECNT` carries **`0x5` in the
top nibble** on the vendor's working datapath and **`0x0`** on ours. The note and
the measurement agree, which made the obvious experiment: drop the fill and see
whether the tables load.

`ZXI_MASK` is now a module parameter (`init_mask`), so with
`/proc/zx_eth_reinit` each stage can be masked out and the init re-run without a
rebuild per arm - the thing round 70 could not do, which is why it changed the
ordering and the fill together and isolated neither.

| state | `BM_FREECNT` |
|---|---|
| cold boot, normal init (fill enabled) | `0x00000111` |
| after `init_mask=0x3bf` (BMFILL masked) + `zx_eth_reinit` | **`0x00000111`** |

**No change.** Removing the fill does not cause the free-list tables to be
consumed, and the pool-loaded bits do not appear.

### The limitation, stated plainly

This was a **runtime re-init**, not a cold init, and those are not known to be
equivalent - this file already records that `zx_eth_reinit` "runs to completion
and changes nothing about global init". So the honest reading is narrower than
the table suggests: *the runtime re-init path cannot produce the pool-loaded bits
whether or not the fill runs*. It does not rule out that a genuine cold
`datapath_init()` without the fill would behave differently.

Testing that properly needs the parameter set before probe, which for a built-in
driver means `zx279128_eth.init_mask=0x3bf` on the kernel command line and
therefore a rebuild of `CONFIG_CMDLINE` - one build, and the cleanest remaining
experiment on this thread.

What the parameter does buy immediately: every stage of `datapath_init()` is now
individually maskable at runtime, so the ordering and content questions this file
has accumulated over dozens of rounds can be tested one variable at a time
instead of in pairs.

## ★★★ 2026-09-07 — the pool fill MOVES the wedge, and a different status bit asserts without it

The runtime re-init test above was inconclusive because a re-init is not a cold
init. Repeated properly, with `zx279128_eth.init_mask=0x3bf` on the kernel
command line so the mask applies **at probe**:

| | frames before the wedge | `BM_FREECNT` at the wedge |
|---|---|---|
| fill enabled (shipped behaviour) | ~4040 | `0x40000111` - **bit 30** |
| `ZXI_BMFILL` masked at probe | **2608** | `0x80000111` - **bit 31** |

Three things, and the first two are new facts about this hardware.

### 1. The fill is NOT required for RX, contrary to a long-standing note

`datapath_init()` has carried the claim "We need the explicit fill" for many
rounds. With the fill masked out at probe, the interface comes up and **RX works
normally** - 5/5 ping at 0% loss, `rx_packets` climbing, thousands of frames
delivered under load. The claim is wrong as stated. What the fill actually does
is change *how long* the datapath survives, not whether it functions.

### 2. This is the first change all session that moves the wedge point

Everything measured today - offered rate, poll interval, flow count, WiFi
presence, uptime, scan window - left the wedge at ~4000-4074 frames. Removing
the pool fill drops it to **2608**. That is a 35% reduction and far outside the
±1% spread of every other arm.

So the wedge **is** sensitive to pool priming, and the relationship is not
linear: priming 2046 buffers buys about 1430 extra frames, not 2046.

### 3. A different status bit asserts, and the FPM analogy predicts what it means

With the fill, the wedge carries **bit 30**. Without it, **bit 31**. In the
Broadcom FPM layout that this buffer manager otherwise matches closely, bit 31
is `POOL_FULL` and the neighbouring bits are the free/alloc FIFO full-empty
pair. Two different pool conditions produce two different terminal states, which
is strong support for reading these high bits as pool/FIFO status rather than as
an error code - and it is the first time this project has seen anything other
than bit 30 at a wedge.

### What this makes the next experiments

* **Sweep the fill depth.** The fill currently primes `0 .. BUF_COUNT-2`. If the
  wedge point moves with the number of buffers primed, that curve - and whether
  it saturates - is the most direct handle on the mechanism anyone has found
  here. `ZXI_BMFILL` is now maskable and the loop bound is one constant.
* **Read the high nibble as a state machine.** `0x0` healthy, `0x4` wedged with
  a primed pool, `0x8` wedged with an unprimed one, `0x5` on the vendor's
  working datapath. Four states, three of ours, and the vendor's is the only one
  with both a high bit and the low bits we never reproduce.

The shipped configuration keeps the fill: 4040 frames beats 2608. The cmdline
override was an experiment and is reverted.

## ★★★ 2026-09-07 (later) — the wedge SURVIVES a full software datapath re-init

Three interventions on a datapath that was already wedged, in order, on the same
boot. None restored reception. `eth2` sat at exactly **2608** RX packets
throughout — the wedge point of the `init_mask=0x3bf` (pool-prime masked out)
arm this image was booted with.

| # | intervention | RX after | ping |
|---|---|---|---|
| 1 | `echo 1 > /proc/zx_eth_reinit` | 2608 | 100% loss |
| 2 | `init_mask=0x3ff` (re-enable `ZXI_BMFILL`), then re-init | 2608 | 100% loss |
| 3 | `BM+0x000 := 0`, `:= 1`, then re-init | 2608 | 100% loss |

**The re-inits genuinely ran.** They are not no-ops that the datapath ignored:

* `BM+0xb0`, the counter that reaches 5121 at the wedge, was **reset to
  `0x00000001`** by re-init. Whatever it counts, re-init clears it and reception
  still does not resume — so the wedge is not that counter reaching a limit,
  which independently confirms the earlier elimination by a different route
  (U-Boot drove the same register to 30720 without stopping).
* The pool prime is visibly gated on the mask: `freelist1 readback [2047]` read
  `0000` with `ZXI_BMFILL` masked out, `d004` and then `4005` with it back on.
  `BM+0x010` reads `0x7fe` afterwards, the last index the prime loop writes.
* TX kept working across all three (35 → 36 frames). The device is alive, the
  console is responsive, only reception is dead.

**What this rules out.** Everything `zx_eth_datapath_init()` touches. It rewrites
the NPP block, re-primes the buffer pool, re-attaches the ports and resets
`BM+0xb0`, and reception does not come back. The stuck state therefore lives in
hardware that our init sequence does not reset — which is why every "fix" that
consists of writing configuration registers has failed, and why the next thing
worth trying is a block-level reset path recovered from the stock driver rather
than another candidate register.

`BM+0xdc` read `0x40000111` in this state: bit 30 set over the constant `0x111`
that it holds in every state, wedged or healthy.

### ✗ CORRECTION, one hour later: re-init breaks a HEALTHY datapath too

The section above says the wedge "survives" a re-init. That reading is **wrong**,
and the control arm caught it.

The fill-depth sweep's first arm is `2047r`: cold boot, set `fill_depth` to its
DEFAULT, re-init, then flood — an arm whose only purpose is to prove that
re-init changes nothing, so that re-init can be used to set up the other arms.
It reproduced nothing at all:

```
ARM label=2047r depth=2047 reinit=1 verdict=WEDGED
    before=30 mid=30 after=30 delivered=0   bm=BM 0b0 00000001, BM 0dc 40000409
```

**Zero frames delivered.** A cold-booted, working datapath that had just
answered pings stopped receiving the moment `datapath_init()` was re-run, at the
same parameters it had booted with.

So `/proc/zx_eth_reinit` is destructive, and the three "interventions" above were
never tests of the wedge. Each one ran a procedure that kills reception on its
own; that reception stayed dead afterwards says nothing about what the wedge is.

What survives from that section, and what does not:

* **SURVIVES:** re-init genuinely executes — it resets `BM+0xb0` to 1 and
  visibly re-primes the free list. That was read directly.
* **SURVIVES:** `BM+0x000` behaves like an enable, and toggling it does not
  restore a wedged datapath.
* **RETRACTED:** "the wedge survives a full software datapath re-init", and with
  it the inference that everything `datapath_init()` touches is ruled out. It is
  not ruled out. Nothing was tested.
* **NEW, and more useful:** `datapath_init()` cannot be re-run on a live
  datapath. Something it does is destructive in a way the cold-boot path is not
  — most likely because at cold boot the block is in reset and here it is not.
  That is a lead in its own right, and it lines up exactly with what the
  ZX279133 sibling does that we do not: its `bmu_prepare()` writes
  `BMU_ENABLE = 0` *before* re-seeding the pool and `= 1` after, and its
  `tm_prepare()` is always preceded by `np_reset_prepare()`, an MMIO
  `_RESET_N` pulse with a mandatory init-done handshake. Re-programming a live
  block is a sequence that appears nowhere in that driver.

### Consequence for the fill-depth sweep

Re-init cannot be used to recover between arms, and — per the correction above —
it cannot be used to *set up* an arm either. The vehicle is dead. `fill_depth`
has to be in effect at the driver's own probe-time init, which with
`CONFIG_CMDLINE_FORCE=y` means one build per arm.

The obvious cheaper fix — `CONFIG_CMDLINE_EXTEND`, so an arm becomes a
`setenv bootargs` at the `=>` prompt — was checked and **does not work on this
bootloader**:

```
=> printenv bootargs
bootargs=console=$(console) root=/dev/mtdblock8 ro rootfstype=squashfs mem=$(memsize)"
=> printenv bootcmd
bootcmd=setenv bootargs console=$(console) root=/dev/mtdblock8 ro rootfstype=squashfs  mem=$(memsize) ;
```

Three problems in four lines. `bootcmd` **overwrites `bootargs` on every boot**,
so a `setenv bootargs` does not survive to the kernel. The variables are not
expanded — the kernel would receive the literal `console=$(console)` and a stray
`"`. And it appends `root=/dev/mtdblock8`, which our command line deliberately
does not set. (Note also that `bootcmd` does not boot anything: it ends after
the `setenv`. The vendor's boot flow is compiled in, not driven from the
environment, so there is no `bootcmd` to edit into shape either.)

So `CONFIG_CMDLINE_FORCE=y` stays, and a command-line arm costs a build.

The way out is to make re-init non-destructive instead, which is what the
`bm_gate` parameter is for: if seeding the pool with `BM+0x00` disabled — the
order the sibling uses — lets `datapath_init()` run on a live block without
killing reception, the whole sweep goes back to costing one cold boot per arm
instead of one build per arm. That is the next thing to test.


## 2026-09-07 (evening) — the default wedge point replicates exactly; two register leads, one lethal

### The control, measured twice

Two cold boots of the same image, same 25 s / 4000 pps / 1442 B UDP offer:

| boot | `rx_packets` at the stop | `BM+0xb0` | `BM+0xdc` |
|---|---|---|---|
| 1 | 5097 | — | `0x00000111` |
| 2 | 5100 | `0x00001401` = 5121 | `0x00000111` |

0.06% apart. The default-depth wedge point is **~5100 delivered frames with
`BM+0xb0` at exactly 5121 = 5x1024+1**, and it is one of the most reproducible
numbers this project has. Against it, the no-prime arm's **2608** is a real
effect and not noise.

Note `BM+0xdc` reads the bare `0x111` at a genuine fresh wedge — **no bit 30, no
bit 31**. Both of those were seen only after a `/proc/zx_eth_reinit`, which is
now known to be destructive in its own right. Whatever bits 30/31 mean, they are
not the wedge indicator they were taken for.

### CRM+0x08 differs between the working engine and ours — and must not be "fixed"

Dumping the whole `topcrm@94000000` block from the `=>` prompt, with U-Boot's own
working datapath running, and comparing against `/proc/zx_eth_regs` on a fresh
Linux boot: **21 of 22 populated words are identical. Exactly one differs.**

| | U-Boot (working) | Linux (ours) |
|---|---|---|
| `CRM+0x08` | `0x10061fff` | `0x1e06ffff` |

Linux has six extra bits set (13, 14, 15, 25, 26, 27). That looked like the
cleanest single lever in the project.

**It is not one. Writing U-Boot's value under Linux hangs the SoC.** Poked on an
already-wedged device (so the only thing at risk was a boot about to end):

```
zx-poke: [94000008] 1e06ffff := 10061fff -> 10061fff
```

The write landed, and the console went silent immediately after — no further
command produced any output, and the device needed a power cycle. So `CRM+0x08`
is a live clock gate whose extra bits Linux genuinely needs (it drives more
peripherals than U-Boot does), the difference is explained by that rather than
by a datapath misconfiguration, and this is **not** a lever. Recorded so nobody
spends the same hour on it: do not write the U-Boot value here.

### Where the vendor's reset sequence is NOT

`ref/stock-vmlinux.bin` was searched exhaustively (kallsyms recovered, all 39213
symbols, plus every static-IO register access in `.text`). The datapath reset
code **is not in the stock kernel at all**: its embedded `.config` says
`# CONFIG_ETHERNET is not set`, and the BM/packet-processor/GEMAC driver is an
out-of-tree module in the AES-encrypted vendor rootfs, which is already
confirmed unobtainable.

What the stock kernel does contain, and all it contains, for these blocks:

* `zx279128_restart` -> `writel(1, 0x94000044)`, a whole-SoC reset. Not per-block.
* `zx_wdt_probe` -> `0x94000004 |= 0x18`.
* `zte_gpio_init` -> `0x92040018`: clear bit 8, set bit 6, and `0x94200090`:
  clear bit 1, set bit 0. `0x92040018` is inside the datapath aperture and is a
  sub-block this port may not touch at all - worth a look, though it sits in
  board/pin-setup code, not datapath code.
* `phy_enable`/`phy_disable`, `zx_mdio_read`/`zx_mdio_write` (MDIO at
  `0x9A101000`) - all `EXPORT_SYMBOL`'d with **zero in-kernel callers**, i.e.
  they exist purely for that missing module.

There is no reset-controller driver, no `reset_control_*` use outside MDIO, and
no ethernet clock in the built-in clock driver's name list. So "read the vendor's
reset sequence" is closed as a route, and the ZX279133 sibling source is the only
reset specification available locally.


### ✗ The two writes the vendor kernel makes and we do not: NO EFFECT

`zte_gpio_init` in the stock kernel performs exactly two register writes that
this port never makes. Both were read back from the `=>` prompt and confirmed
untouched on a fresh Linux boot, so the divergence is real:

| register | U-Boot and us | vendor Linux |
|---|---|---|
| `0x92040018` | `0x00000100` | `0x00000040` (clear bit 8, set bit 6) |
| `0x94200090` | `0x0000a28a` | `0x0000a289` (clear bit 1, set bit 0) |

Applied both by hand on a fresh boot, verified by read-back, then flooded:
**5097 frames.** The control is 5097 and 5100. No effect whatsoever, on the wedge
point or on anything else observable.

`0x92040018` sits inside the datapath aperture and was the more interesting of
the two; it is now eliminated. Three independent measurements of the
default-depth wedge point now read 5097 / 5100 / 5097.

### ⚠ TRAP: `/proc/zx_eth_poke`'s own documented `and ~MASK` syntax wrote ZERO

Setting this up clobbered a live register. The parser was
`sscanf(buf, "%lx %23s %lx", ...)`, which cannot read the `~0x100` form the
usage comment right above it documents: the `%lx` conversion fails, `n` comes
back 2, the `and` branch requires `n == 3` and is skipped, and the input falls
through to the plain-write branch — where `simple_strtoul("and")` is 0.

So `echo "0x94200090 and ~0x2" > /proc/zx_eth_poke` **set the register to zero**,
taking `0xa28a` to `0x00000001` while trying to clear one bit. The only reason it
was caught is that the log line says `:= 00000000` rather than `&=`.

Fixed: the value is parsed as a string with an optional leading `~`, and an
unparseable value is rejected instead of being written as 0. Anyone who used the
`and ~MASK` form before this fix should assume the register was zeroed, not
masked — and should re-check any conclusion drawn from it.


### ✗ Returning buffers to the pool does NOT un-wedge — so it is not simple exhaustion

The leading reading of the fill-depth effect was buffer exhaustion: the pool
holds N buffers, some fraction leaks per frame, and reception stops when the
pool empties. It predicts that handing buffers back on a wedged datapath should
let that many more frames through.

It does not. On a device wedged at 5097 frames, eight indices were written to
`BM+0x10` — the same register, in the same way, that `zx_bm_free()` uses:

```
zx-poke: [92348010] 00000068 := 00000069 -> 00000069
...                                          0000006b
```

Not one frame was delivered afterwards. `BM+0xb0` stayed at `0x1401`, `BM+0xdc`
at `0x111`.

Two things this establishes:

* **`BM+0x10` is a plain read/write register, not a push port.** It reads back
  exactly what was last written to it (`cur` on each successive poke is the
  previous value). Every "the free list has 2046 entries" reading taken from
  `BM+0x10` reading `0x7fe` was therefore reading *the last index the prime loop
  wrote*, not a depth.
* **The wedge is probably not the pool being empty** — with a caveat that has
  to stay attached. Eight buffers released nothing, but eight is a small number
  against a `BPPI` threshold register holding `0x0104c040`; a pool that only
  restarts above some occupancy would look exactly like this. The claim is
  therefore "eight buffers do not restart it", not "it is not exhaustion". The
  test that settles it is a reprime of the full 2047 on a **wedged** datapath,
  which `/proc/zx_eth_reprime` can now do and which has not been run yet.

That leaves a sharper description of what the priming depth actually does: it
sets a **budget that is consumed over the run** — more primed buffers means a
later stop, reproducibly — but once that budget is spent the block latches into
a state that returning buffers does not clear. A budget you can top up would not
behave that way, so whatever is counting is not the pool's free count.


### Pre-registered: what the fill-depth sweep can come back as

Written before the run, because this project's failure mode is fitting a story
to numbers after seeing them. Arms: depth 0, 64, 256, 1024, 2047, plus a
no-reprime cold-boot baseline, one cold boot each, same 25 s / 4000 pps offer.

Known points: **2608** delivered with the prime masked out entirely, and
**5097 / 5100 / 5097** with the full prime.

* **H1 — budget.** `delivered` is linear in depth: each primed buffer buys a
  fixed number of frames. Fitting the two known points gives intercept ~2600 and
  slope ~1.22 frames per buffer. Confirmed by depth 1024 landing near 3850.
  Would mean the pool is consumed at a fixed rate and the stop is exhaustion of
  something proportional to it — though note that **returning buffers to a
  wedged pool does nothing**, so it would be a budget that cannot be topped up.
* **H2 — saturation.** `delivered` rises with depth and then flattens, so above
  some depth the pool is not the limit and something else is. The knee is the
  interesting number.
* **H3 — binary.** Depths 64, 256, 1024 and 2047 all land near 5100 and only
  depth 0 gives 2608. Then priming depth is not a quantity at all: what matters
  is whether the prime ran, and the 2608/5100 difference is an artifact of the
  *absence* of the loop rather than of how many buffers it wrote. This is the
  outcome that would retract "priming depth is the lever", and it is entirely
  plausible - the only evidence for a quantity is two points, one of them at
  zero.

**Falsification criterion, stated up front:** if depth 64 delivers within 5% of
depth 2047, H1 is dead and the "depth moves the wedge" framing goes with it.

A fourth possibility that would matter more than any of these: an arm reports
**STILLMOVING**, i.e. no wedge inside 25 s. That has never happened and would be
the first sign of an actual fix rather than a description.


## The ZX279128S datapath memory map, from the vendor's own device tree

Recovered from an FDT embedded at file offset `0x2aa510` in
`ref/ZX279127S-Reverse/mtd-img/F610GV9/kernel1.bin`
(`model = "ZTE ZX279128S"`, `compatible = "zte,zx279128-smp"`). This is the
authoritative map for this SoC and it has not been written down here before.

```dts
topcrm@94000000    reg = <0x94000000 0x1000>;      "zte,ZX279127-topcrm", syscon
pon@92000000       reg = <0x92000000 0x02000000>, <0x92000000 0x00140000>,
                         <0x92000000 0x02000000>, <0x94000000 0x00100000>,
                         <0x94100000 0x00100000>, <0x94200000 0x00100000>,
                         <0x9fe00000 0x00100000>;  "zte,zx27912x-pon"
npp@921c0000       reg = <0x921c0000 0x00008000>, <0x921cc000 0x00034000>;
sw@92300000        reg = <0x92300000 0x00034000>;
tm@92340000        reg = <0x92340000 0x00040000>;  "zte,zx279128s-tm"
pp@92380000        reg = <0x92140000 0x00040000>, <0x92380000 0x00040000>;
idm@921c8000       reg = <0x92334000 0x00004000>, <0x921c8000 0x00004000>;
gephy128s@9b000000 reg = <0x9b000000 0x100000>, <0x9b100000 0x100000>,
                         <0x9b200000 0x100000>, <0x9b300000 0x100000>;
```

Four things this settles.

1. **Our "BM" at `0x92348000` is not its own block.** It is `tm@92340000 + 0x8000`
   — the buffer manager is a sub-block of the traffic manager, exactly as the
   BMU is a sub-block of the NPPT window on the ZX279133 sibling. So `BM+0xb0`
   and `BM+0xdc` are TM-window offsets `0x80b0` and `0x80dc`, and anything
   analogous to the sibling's reset word need not live in the BM aperture at
   all.
2. **Three second apertures have never been looked at.** `npp`, `pp` and `idm`
   each have two `reg` ranges and this driver maps one of each. They are in the
   `/proc/zx_eth_regs` dump now as `NPP2`, `PP2` and `IDM2`.
3. **No node in the vendor DTB has a `resets=` property, and there is no
   reset-controller node at all.** Whatever block reset exists is reached by
   MMIO. On the sibling it is an in-window active-low word
   (`NPPT+0x2c0004`, bits 4 and 31) with a mandatory init-done poll
   (`NPPT+0x0080`, mask `0x1fd`) — not a reset line. `topcrm@94000000` is mapped
   by the vendor's own `pon` node, so a CRM-level reset would live there.
4. `gephy128s` has four 1 MB windows with four interrupts, one per port —
   matching what our DTS declares.

The sibling's equivalent gating is a clock register, `TOPCRM_PON_GATE_CTRL` at
its topcrm `+0x48`, with bits 0/1/2/7/12 for `pon_idm_aclk`, `pon_tm_aclk`,
`pon_pclk`, `pon_smac_wclk` and `pon_mac_wclk`. Our `CRM+0x48` reads
`0x0ffedfff`. That is a lead for the clock driver Phase 8 needs, not for the
wedge.


### ✗ CORRECTION to the pre-registration, before any result came back

The sweep as built **cannot** test boot-time priming depth, and the
pre-registration above describes an experiment that is not running.

`/proc/zx_eth_reprime` writes indices into the pool. It cannot *un*-write the
2047 the driver already primed at probe. So an arm at "depth 0" is not "no
prime" — it is the normal boot-time prime plus a no-op, and an arm at depth 64
is the boot-time prime plus 64 more. Every arm therefore starts from the same
2047 the baseline has.

What is actually being measured is a **dose-response to ADDITIONAL priming**:

| arm | what it is |
|---|---|
| `base` | no reprime — the plain cold-boot baseline |
| `d0` | a reprime that writes nothing — a control for the harness itself, must equal `base` |
| `d64` | +64 buffers on top of the boot-time 2047 |
| `d2047` | +2047 buffers on top of the boot-time 2047 |

That is still worth running, and it is a sharper version of an earlier test:
writing eight indices back into a *wedged* pool did nothing, and this asks
whether writing two thousand into a *healthy* one buys anything. If `d2047`
pushes the stop past 5100, the consumable-budget reading survives and reprime is
a mitigation. If every arm lands at ~5100, extra buffers are irrelevant, which
is what the wedged-pool result already suggested.

The original question — does the *boot-time* depth move the wedge — still needs
one `CONFIG_CMDLINE` build per arm. Nothing cheaper works: `CONFIG_CMDLINE_FORCE`
is set and this bootloader's `bootcmd` overwrites `bootargs` on every boot.

Recorded before the numbers arrived, because the whole point of writing a
prediction down is that it is falsifiable, and a prediction about the wrong
experiment is not.


## Phase 8 inventory: exactly what has to come out before upstreaming

Written now, while the instruments are still in use, so the removal is a
mechanical task later rather than a judgement call. **Do not act on this list
until the datapath work is finished** — these twenty-eight parameters and five
`/proc` files *are* the instrument, and several results this week exist only
because they were there.

`zx279128-eth.c` is **3285 lines** with **15 literal-address `ioremap()` calls**
and **28 module parameters**:

```
rx_credit_reg rx_credit rx_credit_repay rx_full_ring force_dp_init rx_dump_max
all_ports phy_keepalive tx_w0 tx_w1 tx_w2 npp_port_mask rx_heal rx_heal_retx
rx_release irq_probe tx_buf_idx rx_window fill_depth bm_gate bm_thresh_post
bm_cfg_c8 bm_cfg_d8 split_ports rx_skip0 rx_gro rx_poll_us init_mask
```

Disposal, by kind:

* **Dead on measurement — delete outright, with the finding kept in this file.**
  `rx_credit*` (the "credit" is a constant `0x111` in every state, wedged or
  not, and the accounting they tuned has already been removed),
  `bm_cfg_c8`/`bm_cfg_d8` (the registers refuse the reference values at runtime
  and during cold init), `irq_probe` (none of the five declared IRQs ever fire).
* **Should become a fixed correct value, not a knob.** `tx_buf_idx`,
  `npp_port_mask`, `tx_w0`/`w1`/`w2`, `init_mask`, `fill_depth`, `rx_skip0`,
  `rx_full_ring`, `rx_heal*`, `rx_release`, `force_dp_init`.
* **Legitimate tunables that could survive as ethtool coalescing.** `rx_poll_us`
  and `rx_window` — but only if the poller survives at all; if a producer index
  is ever found, both go with the hunting scan.
* **Real features, keep.** `all_ports`, `split_ports`, `rx_gro`,
  `phy_keepalive`.
* **Never ship.** `rx_dump_max`, `bm_gate`, `bm_thresh_post`, and every
  `/proc/zx_eth_*` file. `zx_eth_poke` in particular is an unrestricted physical
  read/modify/write; it hung the SoC once this week by design working exactly as
  documented.

The 15 literal `ioremap()`s want DT `reg` entries, and the vendor's own node map
(above) is now the source for them — including the three second apertures this
driver has never mapped.

Also on the list, outside this file: `zx_pcie_probe_test.c` (295 lines,
`default y`), the MDIO driver's bare cross-driver `ioremap`s, and the
unconditional 60 s NAND `HEALTH` print.


## ✗ REFUTED within the hour: the BM_REQUEST jam is not the RX wedge

Proposed and withdrawn on 2026-09-07. Recorded in full because the reasoning was
attractive and somebody will think of it again.

**The claim.** `zx_bm_alloc()` writes 1 to `BM_REQUEST`, polls it back to 0,
reads `BM_ALLOC_IDX`, and clears `BM_REQUEST` **only on the success path**. Both
failure paths return with it still asserted. If the register is level-held
rather than an edge-triggered doorbell, the first failed allocation jams it
forever: every later call reads it non-zero, `continue`s through all four
retries, never reads the index, returns `-ENOMEM` permanently. That matched the
wedge's standing description exactly, and explained both why re-running
`datapath_init()` does not help (it never touches `BM_REQUEST`) and why writing
buffers back into the pool released nothing.

**Two facts kill it, and both were already on disk when it was proposed.**

1. **`zx_bm_alloc()` has exactly one caller and it is `ndo_start_xmit`.** The RX
   path never allocates through it — the hardware takes RX buffers from the pool
   itself, which is the whole reason the DDR free-list tables and the prime loop
   exist. A jam in this function cannot stop reception, whatever the register's
   latching behaviour.
2. **TX kept working across the wedge.** Four consecutive `/proc/net/dev`
   samples with `rx_packets` frozen at 2608:

   ```
   eth2: 3662562 2608 ... 7202 35
   eth2: 3662562 2608 ... 7202 35
   eth2: 3662562 2608 ... 7202 35
   eth2: 3662562 2608 ... 7376 36
   ```

   `tx_packets` 35 → 36, `tx_bytes` 7202 → 7376. A transmit requires
   `zx_bm_alloc()` to have returned ≥ 0, which requires `BM_REQUEST` to have read
   back **zero** and the VALID bit to have been set. It was not jammed.

**What survives.** The missing clear is still a real defect: leaving a request
asserted after failing to complete it is wrong however the hardware latches it,
and it is a plausible cause of *other* trouble on a device where TX allocation
does sometimes fail. The `bm_req_clear` parameter stays, still OFF by default.
So do the new `abusy` / `ainval` census counters, which are worth having for a
different reason than the one they were added for — they separate "the pool had
nothing to give" from "the request was never accepted", and no counter here has
ever distinguished those.

**What it cost, and the lesson.** Nothing but the time to check, because the
falsifying evidence was in a log already collected. The mistake was proposing a
mechanism for RX from a function that only TX calls — a caller check that takes
one `grep` and was not done before the claim was written down. Do that grep
first next time.

**Where this leaves the wedge.** Back to the hardware's own allocator. The
driver does not allocate RX buffers at all, so nothing in this driver's
allocation path can be the cause, and the search returns to what the *hardware*
does when it stops handing buffers to the receive engine.


## 2026-09-07, adversarial review — five corrections and a quantitative law

An independent reviewer was asked to refute today's conclusions. Most of what it
found is recorded at the code; these are the parts that change what this file
says.

### ✗ "`BM+0x10` is a plain read/write register, not a push port" — REFUTED

The inference was a non-sequitur. A write port on an ASIC is normally a real
flip-flop bank that both latches the value *and* triggers the action; reading
back the last value written is the default behaviour of such a port, not
evidence against it. And the evidence on disk says it **is** a command port:
removing the fill loop makes every transmit fail (`tx_packets=0`), and the wedge
point moves 5097 → 2608 when the only change is whether that loop runs. An inert
register does neither.

**What survives, and more strongly:** the "free list has 2046 entries" reading is
dead. `BM+0x10` reads back the last index written — observed at `0x780` (1920)
and `0x7b1` (1969) at various points, not a depth. `0x7fe` is exactly
`BUF_COUNT-2`, the last index the fill loop writes, which is the coincidence that
let the misreading survive.

### ✗ The delivered-vs-absolute bookkeeping error

The 5097 / 5100 / 5097 / 2608 series is **absolute `eth2` rx_packets**. The
harness printed `delivered = after - before`, which for the same event read 5074.
`before` is 20-30 and varies per boot. Anywhere this file says "~5100 delivered"
or "2608 delivered", read "absolute". The harness now prints both, labelled.

### ✗ `BM_FREECNT`'s low bits are NOT always `0x111`

The driver comment claimed `0x111` "in every state this hardware can be in". The
log has `BM 0dc 40000409`. Falsified.

### ✗ The CRM comparison: 19 words, not 22 — and U-Boot's value is a SUBSET

Two corrections to the `CRM+0x08` section. The populated set is 19 words, not 22.
More importantly: `0x10061fff` sets bits {0-12, 17, 18, 28} and `0x1e06ffff` sets
{0-15, 17, 18, 25-28}. **U-Boot's value is a strict subset of ours** — we already
have every bit the working engine has, plus six. This register could never have
been "the thing we are missing", and that was determinable from the two hex
values without risking a boot. The hang added nothing.

Also worth knowing for future comparisons: `zx_regs_show()` only prints non-zero
words, while U-Boot's `md.l` prints everything, so a register non-zero in U-Boot
and zero in Linux is structurally invisible to that diff. It happens not to bite
here (the non-zero offset sets match exactly), but the U-Boot dump covered only
`0x000-0x0fc` of a 256-word block.

### ✗ Why `n_zerolen` is high — the stated reason was wrong

The conclusion (not a leak indicator) stands, but not for the reason recorded.
The claim was that `st & 0x20` "passes on every slot". At **idle** the counter
climbs at only ~1300-1900/s — 1.4% of the 128000/s ceiling, not 94%. The real
mechanism: `st & 0x20` is set only on slots the hardware has written, and the
default `rx_release = 0` zeroes *only* the length halfword, leaving the status
byte set forever. A consumed slot therefore becomes a permanent zero-length hit,
and the rate is ≈ 125 × (slots ever consumed) — ~25 at idle, ~1023 under flood.
Both observed rates fit to within a few percent.

Two consequences: **`st & 0x20` IS meaningful ownership information** (the
"carries no ownership information" note came from one bring-up observation and
the idle arithmetic contradicts it), and "no buffer is allocated for these slots
so there is nothing to leak" is an over-claim — the counter is contaminated by
re-visits, which is not the same as showing there is no leak.

### ★★★ The wedge point is LINEAR in pool size, slope ~1.25, intercept ~0

The most useful thing the review produced. Compare the two arms against their
*actual* pool sizes rather than against the stale 4040 figure:

| arm | pool | absolute rx | frames per buffer |
|---|---|---|---|
| `ZXI_BMFILL` masked (DDR free list only) | 2046 | 2608 | 1.274 |
| default (DDR list + fill loop) | 2046 + 2047 = 4093 | 5097 | 1.245 |

Pool sizes in a **2.0005 : 1** ratio, delivered counts in a **1.954 : 1** ratio,
a common slope of ~1.25 and an intercept of ~0.

That is the signature of a **pure leak**: essentially every buffer the datapath
touches is permanently lost, and the run ends when the pool is empty. It also
makes the 1023/1024 lattice a coincidence (2046/2 ≈ 1023) rather than a ring
effect, which fits `rx_full_ring`, `rx_release`, `rx_credit_reg` and credit-repay
all having moved the wedge by nothing.

**This retracts an earlier line in this file** claiming "the relationship is not
linear: priming 2046 buffers buys about 1430 extra frames, not 2046". That was
computed against the stale 4040 figure. Against the replicated 5097 it buys 2489
frames from 2047 buffers = 1.216 each, matching the baseline's 1.274 within 5%.
**H1 is now the best-supported hypothesis and H3 is the one in trouble.**

### The single measurement that decides it

Push the full 2047 back into a **wedged** pool via `/proc/zx_eth_reprime`. The
linear law makes this quantitative rather than qualitative:

* reception resumes for **~2500 more frames** (1.25 × 2047) → the pool is a
  consumable `BM+0x10` can top up, the wedge is exhaustion, and the bug is on the
  free side;
* it resumes for a few hundred or not at all → `BM+0x10` is not the run-time
  return path, the buffers are lost inside the hardware's release engine, and the
  fix is programming the sibling's release configuration.

The sibling supports the second reading: `zx279133_bmu_prepare()` has **no
index-push step at all**. It seeds the pool in memory with `BMU_ENABLE = 0`, then
programs `NORMAL_BASE` / `NORMAL_CFG` / `NORMAL_INDEX_MAX` / `NORMAL_RLS_CFG` /
`NORMAL_COUNT_REG`, then enables. Our `BM+0x60` — where `NORMAL_RLS_CFG`
(sibling `0x3c060`) lands under the block-base alignment established at the top
of the driver — reads **zero in every dump**. We have never programmed the
release configuration, which would make `zx_bm_free()`'s per-frame write a no-op
and is exactly why eight of them released nothing.


## ★★★ 2026-09-07 — the decisive measurement: repriming a WEDGED pool changes NOTHING

The measurement the adversarial review identified, run twice, both arms with the
offered count captured rather than assumed.

Fifth replication of the stop first: `rx_packets` 22 → **5097**, with
`offered=99960` and a 5 s follow-up burst moving it not at all.

| intervention on the wedged device | offered | rx after |
|---|---|---|
| `/proc/zx_eth_reprime`, depth 2047, `bm_gate=0` | 99960 | **5097** |
| `/proc/zx_eth_reprime`, depth 2047, `bm_gate=1` (sibling order: `BM_ENABLE=0` → seed → `BM_ENABLE=1`) | 99960 | **5097** |

Zero frames gained, twice, from 2047 buffers each time — against a prediction of
**~2500** (1.25 × 2047) if the pool were a consumable that `BM+0x10` tops up.

**That kills the topping-up reading.** Whatever the initial pool size buys, it
cannot be bought again at runtime by writing indices, and it cannot be bought by
doing it in the order the sibling uses either. Note this is a much stronger
result than the earlier eight-buffer probe, which the caveat in this file rightly
said proved little: 2047 buffers is the entire pool, and the gated arm rules out
"you have to disable the block first" as the reason.

Two readings remain, and they are cleanly distinguishable:

* **A — the block latches.** Runtime pool writes *are* honoured, but the receive
  engine has stopped for some other reason and a full pool does not restart it.
* **B — runtime pool writes are ignored entirely.** Only the init-time load
  counts; `BM+0x10` is a load port that the hardware reads during a window we
  are outside of by the time traffic flows.

**The distinguishing measurement, stated before running it:** reprime a
**healthy** datapath with 2047 extra buffers, then flood.

* stop moves to **~7600** (1.25 × 4093 initial + 1.25 × 2047 added) → runtime
  writes are honoured, reading A, and the wedge is a latch rather than
  exhaustion;
* stop stays at **~5097** → runtime writes are ignored, reading B, and the linear
  law is about the *initial* pool only.

Reading B would make `zx_bm_free()`'s per-frame write a no-op — which is what the
sibling's design already suggests, since `zx279133_bmu_prepare()` has no
index-push step at all and returns buffers through a release engine configured by
registers our `BM+0x60` shows we have never written.


### ✗ The "we never program the release configuration" lead is dead — U-Boot does not either

The adversarial review's proposed mechanism for reading B was that `BM+0x60`
(where the sibling's `NORMAL_RLS_CFG` would land) reads zero in every dump of
ours, so buffers are lost inside a release engine we have never configured.

`research/UBOOT-WORKING-DATAPATH-REFERENCE.md` already contains the answer and it
is no. The U-Boot dump of the BM block, taken with the vendor's own
non-wedging datapath running, prints its non-zero rows and **`0x60`–`0x7c` are
absent from it**:

```
92348050: 00000000 00000000 00000040 00000010
92348080: 000007b0 000001b0 0000004f 0000004f
```

`BM+0x60` is zero in the working engine too. Whatever returns buffers on this
SoC, it is not a release configuration at that offset — and the sibling's BMU
offset map does not transfer there, despite `+0x00`/`+0x04`/`+0x08` matching.
Checked before spending a boot on it.

### What the same comparison DOES show

Setting the dead lead aside, U-Boot's working BM against a healthy Linux cold
boot (both already on file):

| offset | U-Boot (works) | Linux (ours) | note |
|---|---|---|---|
| `+0x48` | `0x00000050` | `0x07700080` | largest unexplained difference |
| `+0x4c` | `0x00000050` | `0x00000170` | |
| `+0xc8` | `0x00000400` | absent (0) | already ELIMINATED — refuses writes |
| `+0xd8` | `0x00006000` | `0x00004000` | already ELIMINATED |
| `+0xdc` | `0x50000111` | `0x00000111` | bits 28 and 30 set only in U-Boot |

The `+0xdc` row is worth stating carefully because it is easy to misread as a
wedge indicator: that Linux dump is a **healthy** cold boot, so bits 28/30 are
absent from our engine whether it is working or wedged. They are not the wedge.
This also finally explains where the bit-30 sighting after a re-init came from —
those bits are live status that our driver's init leaves in a different state
from the vendor's, not something the wedge sets.

`+0x48` and `+0x4c` are the only differences here that have not already been
eliminated. Before anyone writes them: both are plausibly live occupancy rather
than configuration (`0x0770` = 1904 is suspiciously close to a buffer count), and
this project's record on poking a differing register is `bm_cfg_c8` (refuses
writes), `bm_cfg_d8` (refuses writes) and `CRM+0x08` (hung the SoC). Establish
whether they latch before treating either as a lever.


## ★★★★ 2026-09-07 — READING B WINS: runtime writes to `BM+0x10` do nothing. `zx_bm_free()` is a no-op.

The discriminator, run with the prediction recorded beforehand: reprime a
**healthy** datapath with 2047 extra buffers, then flood. Reading A (the block
latches, runtime writes are honoured) predicted the stop moving to **~7600**.
Reading B (runtime writes are ignored, only the init-time load counts) predicted
it staying at **~5097**.

```
ARM label=d2047 depth=2047 gate=0 verdict=WEDGED offered=99960
    before=29 absolute=5096 final=5096 delivered=5067
    bm=BM 0b0 00001401, BM 0dc 40000431
```

**5096.** Against a control series of 5097 / 5100 / 5097 / 5097 / 5097. Adding
half a pool's worth of buffers to a working datapath bought **nothing**, and
`BM+0xb0` still stopped at exactly `0x1401`.

### What this establishes

**Writing indices to `BM+0x10` at runtime has no effect on anything.** Four
arms now say so: on a wedged pool with `bm_gate=0` and with `bm_gate=1`, and on
a healthy pool — plus the original eight-index probe. Yet the *same* writes
during `datapath_init()` demonstrably do work: removing the fill loop halves the
wedge point, 5097 → 2608. There is an init window, and outside it the register
is inert.

**Therefore `zx_bm_free()` is a no-op.** It is one `writel(idx, BM_FREE)`, called
once per received frame, and it has never returned a single buffer to the
hardware. The driver has believed it was recycling buffers for the entire life
of this port.

### This retroactively explains a long list of null results

Everything that works through `zx_bm_free()` was a no-op, which is why none of it
ever moved the wedge:

* `rx_release` and the whole credit-repay path
* `rx_credit_reg` / `rx_credit` / `rx_credit_repay`
* the RX **heal**, whose entire action is `for (i...) zx_bm_free(ze, i)` — it was
  doubly dead, since it was also carrier-gated on a port with no link
* the eight-index probe into a wedged pool, and both full reprimes

They were not weak effects or bad measurements. They were writes to a register
that was not listening.

### And it gives the wedge a complete mechanism

The pool is loaded once, at init, with 2046 (DDR free-list) or 4093 (plus the
fill loop) buffers. Nothing ever returns one. Reception consumes them at ~1.25
frames per buffer and stops when the pool is empty. That is exactly the linear
law — 2046 → 2608 and 4093 → 5097, slope ~1.25, intercept ~0 — and it is now a
mechanism rather than a curve fit.

It also explains why nothing recovers it: with no working return path, an empty
pool stays empty, and every "recovery" attempted so far went through the same
inert register.

### The sharpest question this project has had

**The vendor's engine does not wedge** — 40 MB / ~30 000 frames in one U-Boot
TFTP. With 4093 buffers and no return path it would have stopped near 5100 like
ours. So U-Boot's datapath **has a working buffer return** and ours does not.

The question is no longer "what stops reception". It is: **what does the vendor
do to return a buffer, given that it is not `BM+0x10` at runtime?**

Constraints on the answer, all already established:

* It is not a release configuration at `BM+0x60` — that is zero in U-Boot too.
* It is not `BM+0xc8` or `BM+0xd8` — both refuse writes at runtime and during
  cold init.
* `BM+0x10` reads back the last index written, so it is a real register; it is
  simply not consulted outside the init window.
* The remaining unexplained BM differences against the working engine are
  `+0x48` (`0x00000050` vs our `0x07700080`) and `+0x4c` (`0x50` vs `0x170`).

### What NOT to do next

Not another candidate-register poke. That approach has produced `bm_cfg_c8`
(refuses writes), `bm_cfg_d8` (refuses writes) and `CRM+0x08` (hung the SoC).
The right next step is to find the vendor's *free* path the way the fill path was
found — from the U-Boot binary, which is plaintext and disassembles, around the
allocator at `0x47f2f92c` whose address this driver already cites.


## The vendor's per-frame release sequence, recovered from U-Boot

Disassembled from `h199a-firmware/mtd0-bootloader.bin`. The whole Ethernet
datapath is one compilation unit at `0x47f2f6c8`–`0x47f30920`; `0x92348000`
appears in exactly five literal slots used by four functions, so this is
exhaustive rather than a sample.

### What the vendor does per received frame

```
NetReceive(buf, len)
rls_rx_desc(queue)      0x47f2fb14   block 0x92344000 = TM + 0x4000
rls_bp(index)           0x47f2f99c   BM+0x10, credit gated
```

**We do only the second, and ungated.** That is the entire difference in the
free path.

`rls_rx_desc` — a block this project had never characterised and this driver had
never written to. Poll `+0x64` bit0 clear (≤30 tries), write the payload to
`+0x68`, write `1` to `+0x64`. Payload fields are bits[2:0] queue, bit3,
bits[13:4], bits[31:14]; both vendor call sites pass `queue | (1 << 4)`. The
queue comes from descriptor byte 3 bits [4:2].

The asymmetry the vendor encodes is the tell: **on an invalid buffer index it
releases the descriptor and deliberately skips the buffer.** Descriptor and
buffer are independent resources, and we have been returning only one of them.

`rls_bp` — writes the plain index to `BM+0x10`, no valid bit, no tag, exactly as
we do. But it is gated: a software credit is spent per write and refetched from
**`BM+0xdc` bits [8:3]** (a 6-bit field; our own dumps give 34) when it reaches
zero, giving up after four refetches. `BM+0x10` is written by **exactly one
instruction in the entire binary** — there is no alternative free path anywhere
to go looking for.

### What this closes

* **Our allocator is byte-for-byte the vendor's.** Same order, same VALID-bit
  test, same low-16-bit extraction. It was never the problem, and the
  BM_REQUEST-jam hypothesis is dead for a third independent reason.
* **`BM+0x60`–`0x7c` are never written by the vendor either**, confirming from
  the code what the register dump already showed.
* Everything in our BM dump at `+0x28`–`+0x44`, `+0x80`–`+0x9c`, `+0xa8`–`+0xd8`
  is **never written by the vendor**. Those are reset defaults or
  hardware-maintained status, not configuration we are missing.

### The vendor's BM init, against ours

| offset | vendor writes | ours reads |
|---|---|---|
| `+0x04` | `0x0104c040` | `0x0104c040` ✓ |
| `+0x08` | `0x0104c040` | `0x0104c040` ✓ |
| `+0x48` | `0x08000000` | `0x50` |
| `+0x4c` | `0x02000000` | `0x170` |
| `+0x58` | `0x3f` | `0x40` |
| `+0x5c` | `0x0f` | `0x10` |

The last two are the vendor's values **plus one** — the kind of off-by-one that
is invisible in every other symptom. (`0x08000000 >> 16` = 2048 and
`0x02000000 >> 16` = 512 are exactly the two DDR index-table sizes, and `0x3f` is
the width of the `BM+0xdc` credit field. Suggestive, but nothing in the code
states either relationship, so it stays inference.)

### Pre-registered: what the test can come back as

Arms, one cold boot each, 60 s flood (2.4× the control's stop at 5097 so that
"did not wedge" cannot be confused with "had not got there yet"):

* **`both` (desc_release=1, free_credit=1)** — the vendor's full sequence.
  * **STILLMOVING** → the two-release sequence is the fix, and this port's oldest
    defect is closed.
  * **stops well above 5097** → partial; whichever half is missing still leaks.
  * **stops within 5% of 5097** → the two-release hypothesis is **dead as
    stated**, and the remaining difference is the init values or something not
    in the free path at all.
* **`desc` and `credit`** then attribute it, only if `both` moves.

A fourth outcome is possible and must be reported rather than retried quietly:
`desc_release` writes to a block this driver has never touched, so it may hang
the SoC. That would be a result too.


### The descriptor decode, verified byte-for-byte against a captured frame

Before trusting `zx_desc_rls()`'s queue extraction, the byte mapping was checked
against a real `rxdump` line already in the UART log:

```
idx=1873 len=215 w0=400001bb w1=a3190000 w2=2001ae0e w3=0024035c
```

Descriptor byte *N* is byte *N mod 4* of word *N div 4*, little-endian:

* `byte 7` = MSB of `w1` = `0xa3`; `byte 8` = LSB of `w2` = `0x0e`.
  `(0xa3 >> 1) | (0x0e << 7)` = `0x51 | 0x700` = **1873** ✓ matches `idx`.
* `readw(d+12)` = `0x035c` = 860; `860 >> 2` = **215** ✓ matches `len`.

So the mapping is right, and the vendor's `ubfx(desc[3], 2, 3)` reads the MSB of
`w0`:

* `byte 3` = `0x40`, queue = `(0x40 >> 2) & 7` = **0**.

Queue 0 is exactly right for this driver: it runs a single 1024-entry ring at
`0x41a00000`, which is the vendor's queue-0 base (`ring_base = 0x41A00000 +
q * 0x10000`). So `zx_desc_rls()` will release queue 0, and if the arm fails it
will not be because it released the wrong queue.

Established from data already on disk — no rebuild, no boot.


## ✗ RETRACTED: "the RX heal has never fired in any current-generation run"

Stated earlier today on the strength of an adversarial review, propagated into a
commit message and into `handoff.md`, and **not verified before writing it
down**. It is false.

```
$ grep -ao "9[0-9a-f]*\.ethernet eth0: heal:" logs/uart.log | sort | uniq -c
    758 92200000.ethernet eth0: heal:
     98 92240000.ethernet eth0: heal:
     25 922c0000.ethernet eth0: heal:
```

758 heal lines carry the **current** MAC base, spread throughout the log and
long predating today's carrier-gate change. The review's reading — that the last
heal lines came from an older build — was wrong, and I repeated it without
running the one command that checks it.

**What that costs.** The inference built on it goes too: the round-251
conclusion (the heal disarms itself, which is why only a power cycle recovers a
wedge) is **not** undermined by "the heal never ran". It ran. Whether it
deadlocks itself remains open on its own evidence.

**What survives.** The code changes stand on their own merits, independent of
the false premise:

* `rx_errors` / `rx_dropped` really were charged to `ze->ndev` while
  `rx_packets` goes to the ingress port. That is verifiable by reading the two
  lines and is now fixed.
* Gating the heal on *any* port having carrier, and summing TX across ports, is
  more correct than gating on `eth0` alone whatever `eth0`'s carrier happens to
  be — it just is not the bug fix it was described as.

**Why it fires despite the gate is now an open question**, not an answered one:
`netif_carrier_ok(ze->ndev)` was evidently true at those moments. Do not build
on either answer without checking.

**The lesson, which this project keeps re-learning:** an adversarial review is
not exempt from verification. Six of its findings were right and checkable in
seconds; this one was wrong and equally checkable, and it went in because the
rest of the report was strong.


# ★★★★★ 2026-09-07 — THE WEDGE IS FIXED: the driver never released the descriptor

The oldest defect in this port. A clean 2x2, four cold boots, one image, one
parameter apart, WiFi disabled and the RX heal disarmed so neither could
contribute.

| arm | `desc_release` | `free_credit` | absolute `rx_packets` | verdict |
|---|---|---|---|---|
| `both` | 1 | 1 | **239 696** | STILLMOVING |
| `desc` | 1 | 0 | **239 722** | STILLMOVING |
| `credit` | 0 | 1 | **5 097** | WEDGED |
| `control` | 0 | 0 | **5 097** | WEDGED |

Offered 239 903 in every arm. The two fixed arms received **99.9%** of it and
were still receiving when the run ended; the two unfixed arms stopped at 5 097,
which is exactly the historical control (5097 / 5100 / 5097 / 5097 / 5097).
`desc_rls` read 259 651 and 259 652 in the fixed arms and **0** in the unfixed
ones, so the parameter did what it says.

**`desc_release` is necessary and sufficient. `free_credit` does nothing** —
`nocredit=0` in every arm, so the credit never ran out and gating on it could
never have mattered.

## The bug

The vendor releases **two** resources per received frame, in this order:

```
rls_rx_desc(queue)   descriptor -> 0x92344000 + 0x68 / +0x64   (TM + 0x4000)
rls_bp(index)        buffer     -> BM + 0x10
```

**This driver released only the buffer.** Descriptors were consumed and never
returned, and reception stopped when they ran out. `0x92344000` is a block this
project had never characterised and this driver had never written to.

That single fact explains a great deal of this project's history:

* Why the stop was **linear in the buffer-pool size** (2046 → 2608, 4093 → 5097)
  and yet not fixed by adding buffers: the buffer pool was a *correlate*, not the
  limit.
* Why **nothing recovered a wedged datapath** — not re-init, not re-priming, not
  toggling `BM+0x00`, not writing the whole pool back.
* Why `rx_release`, `rx_credit_reg`, `rx_credit`, `rx_credit_repay` and the heal
  all moved the wedge by **nothing**. Every one of them works on the buffer.
* Why the vendor's own engine moved 30 000 frames without stopping.

Months of work were aimed at the wrong resource. The answer was not in any
register we had been staring at; it was in a block whose existence we had not
noticed, and it came out of the U-Boot binary in an afternoon once the question
became "what does the vendor do to return a buffer" instead of "what stops
reception".

## ⚠ It is NOT fixed under extreme overrun — a separate, open failure

Stated up front so nobody reads the table above as "solved". With
`desc_release=1`, an **unpaced** flood (17.9 M `sendto()` calls in 30 s, far
beyond line rate) stopped the datapath after **2 979 frames**:

```
census ... udp=2993 zerolen=360128 freecnt=c0000111 abusy=0 ainval=0
```

`BM+0xdc` reads `0xc0000111` there — bits **31 and 30** set — where an ordinary
pre-fix wedge reads `0x00000111` and the vendor's working engine reads
`0x50000111`. Allocation is not failing (`abusy=0 ainval=0`).

So this is a **different state** from the wedge that was just fixed, reachable
by overload rather than by cumulative frame count. Note also that the unpaced
generator is a poor instrument: most of those 17.9 M sends were dropped in the
host's own socket buffer, so "offered" there does not mean "put on the wire".
Finding the real saturation point needs a paced rate sweep, not a firehose.

## Throughput: still not honestly measured

At the paced 4000 pps the device received 239 696 frames in 60 s = **47.6
Mbit/s** — but the offer ceiling at that rate is *also* 47.6 Mbit/s. We received
essentially everything sent, so that figure measures the flood, not the link. It
is 8x the old 5.85 Mbit/s, and that old figure was itself taken against a
datapath that died after 5 097 frames, so it was measuring the wedge.

An honest number needs a rate sweep between 4 000 pps (comfortable) and the
overrun point (breaks). That sweep is the remaining work for this phase.


## ★★★ Throughput, honestly measured for the first time

Escalating paced rates on one cold boot, `desc_release=1`, heal disarmed, WiFi
off. Both ends of the link negotiate 1000 Mbit full duplex, so none of this is a
wire-speed cap. 1442-byte UDP payloads, 1488 bytes on the wire.

| offered pps | offered | delivered | loss | **rx Mbit/s** |
|---|---|---|---|---|
| 4 000 | 79 968 | 79 896 | 0.1% | 47.6 |
| 8 000 | 160 088 | 159 934 | 0.1% | 95.2 |
| 16 000 | 320 176 | 319 864 | 0.1% | **190.4** |
| 32 000 | 640 351 | 561 481 | 12.3% | **334.2** ← peak |
| 64 000 | 1 270 999 | 218 903 | 82.8% | 130.3 ← collapse |

**Lossless to ~190 Mbit/s. Peak ~334 Mbit/s. Congestion collapse beyond that.**

The generator kept up at every point (offered tracks `pps × seconds` to within
0.1% up to 32 000), so the losses are the device's, not the instrument's. That
distinction is the entire reason the harness records `offered` — an earlier
version discarded it, which would have made "the device stopped receiving" and
"the host never sent anything" indistinguishable.

The previous figure for this port was **5.85 Mbit/s**. The peak here is **57x**
that. And the old number was never a throughput measurement at all: it was taken
on a datapath that died after 5 097 frames, so it measured how fast we could
reach the wedge.

### Two standing conclusions this retires

* **"The poll interval is a real ceiling" (E6)** — measured 5.79 Mbit/s at
  500 µs against 11.65 at 100 µs. The *same* 500 µs hrtimer and the *same*
  64-slot hunting scan just moved 190 Mbit/s losslessly. E6 was measuring the
  rate at which the driver walked into the wedge. It does not establish anything
  about the poller's ceiling.
* **"Following a producer index instead of the hunting scan is the top
  throughput item" (Phase 2.3)** — that was ranked against a 5.85 Mbit/s
  baseline. The real baseline is 334 Mbit/s. The change may still be worth
  making (the vendor reads a pending count from `TMQ 0x92350100 + 4*q`, so we
  now know where the index is), but it has to be re-justified on the new
  numbers, not inherited from the old ranking.

### The overrun failure is bounded, and it is not this

At 64 000 pps the datapath lost 82.8% of the offer and **kept running** —
218 903 frames delivered, three orders of magnitude past the ~3 000 where an
unpaced firehose stopped it. So sustained rate alone does not trigger that
failure. The firehose offered roughly 600 000 pps nominal, most of it dying in
the host's own socket buffer and therefore arriving in bursts rather than at a
steady rate. The trigger is somewhere above 64 000 pps or is burst-shaped;
either way it is a distinct defect from the wedge and from ordinary saturation,
and graceful degradation up to 64 000 pps is the correct behaviour.

### Shipped and verified by default

`desc_release` now defaults to **on**, so the fix is in the image rather than
behind a parameter. Verified on a stock cold boot with nothing configured:

```
desc_release default: Y
delivered 479 636 frames in 30 s at 16 000 pps = 190.3 Mbit/s, 0.1% loss
```

Set `zx279128_eth.desc_release=0` to reproduce the wedge — every measurement in
this file above was taken in that state, so the control arm survives the change.
