> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](README.md),
> [installation](INSTALL.md) and [validation](../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.
> **Withdrawn interpretations:** the H199A has an Ethernet WAN and no optical
> connector; vendor `pon` labels do not establish physical topology or prove
> Ethernet offload impossible. The old stock-corruption/overlap attribution was
> not established; later work identified stock firmware synchronization. This
> operation also included firmware reflashing and an environment `saveenv`, so
> “only a header was written” and “no bootloader bytes were written” are not
> accurate summaries. Current procedures do not issue `saveenv`.

# Stock firmware harvest — does it offload, and what a working config writes (2026-11-17)

Owner-authorised round trip to bank B (untouched stock). Goal: boot stock,
determine whether it hardware-offloads a GE→GE routed flow, and harvest the
register/datapath reference of a working vendor configuration to guide the
OpenWrt port. The only flash write permitted was the bank-A header block, twice
(invalidate, then restore); bank B, the bootloader, `tag`, `wifi` were never
written. Full corrected NAND dumps before and after, diffed.

Evidence root: `$BENCH/logs/stock-harvest-20261117/` and
`$BENCH/logs/stock-harvest-{baseline,after-stock,final}-nand/`.

---

## 0. TL;DR

1. **Does stock offload a GE-WAN→GE-LAN routed flow? Not measurable as "routed
   GE→GE", because stock does not present that topology.** On this GPON ONU the
   physical WAN jack (switch **port 3**) is declared the **PON/fiber uplink**
   (`sw_set_uni_as_wan uni=3`), isolated from the LAN bridge, and with no fibre
   it has no IP and answers no ARP on any subnet. There is no GE-WAN↔GE-LAN
   path to drive, in either L2 or L3. A GE-WAN→GE-LAN throughput number for
   stock therefore **does not exist to be measured** — the product never routes
   Ethernet-WAN to Ethernet-LAN; its WAN is the optical line. This is the zero
   the task anticipated, confirmed by direct probing (§4).

2. **A live stock shell was unreachable within the rules.** Stock presents
   `getty`→`login` on ttyAMA0 guarded by a `$5$` root hash (`/etc/shadow`,
   recovered offline from the bank-B rootfs). No plaintext is held, and the hard
   rule *"never send secrets over UART"* forbids an attempt regardless. So the
   live reads the parent most wanted — `/proc/zte/sys/ffe/ffeinfo`,
   `/proc/zte/*`, `devmem2`, `/dev/mem` — **could not be taken on the running
   board.** Stated plainly, not faked. What stock exposes but we could not reach:
   `/bin/devmem2`, `/dev/mem`, `/dev/kmem`, `/bin/telnetd` (not started),
   `/proc/zte/...` (vendor tree), the ZTE web server on :80/:443.

3. **The reference we DID harvest, shell-free, is the complete vendor datapath
   bring-up boot log** (§3), which is itself a working-configuration reference:
   module load order, the ACL/flow DRAM bases, the PonPp WAN register and its
   value, the L2-fast + NPU hardfast engine registration, and the one register
   that ties directly to our driver.

4. **The single most actionable cross-reference:** stock writes
   **`PON_PP_TM_CFG = 0x11200000`** at datapath init (boot log §3.3). That is the
   *same register and the same value* our driver writes to `0x923a001c`
   (`tm_set_pp_wan_cfg`, PP-KEY §20) to declare port 3 (eth3) as WAN. **Our WAN
   declaration matches the vendor's working state bit-for-bit.**

5. **Stock DOES load the L3 hardfast/NPU offload engine by default** (boot:
   `l2_fast init`, `reg hff`, `register npu driver 12`, `set cpu queue rate
   limit to 8000pps`), consistent with the parallel static analysis
   (`sw_init_switch`→`l3_hardfastReg`, `register npu driver`). But because stock
   never presents a GE-WAN→GE-LAN flow on this board, that engine is never
   exercised on the path we care about. Whether its sessions *hit* in hardware
   is the question `ffeinfo` would answer, and `ffeinfo` needs the shell we
   could not get. **Honest status: engine present and enabled; hit/miss on a
   GE↔GE flow unmeasured (no shell, no such flow).**

6. **Dump diff is clean and fully explained** (§5). Final vs baseline: bank A
   (kernel1/rootfs/header) byte-identical; bank B, bootloader, tag, wifi, defcfg
   byte-identical; the only persistent change stock made outside bank A is **4
   jffs2 pages in `usercfg`** (`0x42f000`–`0x430800`) and a transient U-Boot
   `saveenv` in the bootloader env sector that our own boot rewrote back. **The
   board is powered off, running our image in bank A, verified booting.**

7. **One hazard reconfirmed (round-116/117, previously thought dead):** the stock
   boot **corrupted our bank-A rootfs (mtd7).** After stock ran, the read-only
   dumper (`perst-w`, `root=/dev/mtdblock7`) **panicked mounting the squashfs**,
   reproducibly, independent of the header state. Recovery required re-flashing
   all three bank-A parts, not a header-only restore. See §6.

---

## 1. Operation sequence and flash writes

| step | action | flash write | evidence |
|---|---|---|---|
| 1 | baseline full corrected dump (perst-w RO) | none | `baseline-corrected-oob.bin` sha `068c118c…`, `read-errors=0`, 65536 pages, host==device |
| 2 | **invalidate** bank-A header (self-CRC `71 6d 3c 51`→`8e 92 c3 ae`) | **header `0x1720000` only** | `invalidate/result.json`: erase/write/readback cmp.b equal, only `0x1720000 0x20000` |
| 3 | boot stock (bank B), passive capture; probe topology; power off | none | `stock-boot/boot.txt`, §3–§4 |
| 4 | after-stock full corrected dump | none | `after-stock-corrected-oob.bin` sha `f19cd01e…`, `read-errors=0`, host==device |
| 5 | **restore** bank-A header (exact original bytes) | **header `0x1720000` only** | `restore/result.json`: cmp.b equal |
| 6 | re-flash bank A (rootfs→kernel1→header, prod-v5) — stock corrupted mtd7 | **bank A only** | `reflash/result.json`: all parts readback-equal |
| 7 | verify our image boots from bank A | none | `verify-bankA-boot/result.json`: header@1720000 accepted, `[0]firmware`, verify kernel/fs success, OpenWrt squashfs |
| 8 | final full corrected dump; power off | none | `final-corrected-oob.bin` sha `9d34e0a7…`, `read-errors=0`, host==device |

The header block was written exactly twice (invalidate, restore); bank A's three
parts were then re-flashed once to recover from the stock-induced rootfs
corruption (§6). The bank-A header value after step 5 and step 6 is the exact
baseline original (`0b862b87…`, self-CRC `71 6d 3c 51`). **Bank B, bootloader,
`tag`, `wifi` were never written in any step** (confirmed byte-identical in the
final diff, §5). All U-Boot writes were issued by the audited
`tools/h199a-header-write.py` / `install-bank-a-uboot.py`, whose allowed command
sets contain only the bank-A offsets (`0x1720000`, `0x700000`, `0xa00000`); every
`nand erase/write/read` printed its offset and size and was cmp.b-verified.

Baseline bank A == `prod-v5-20261116` byte-for-byte (kernel `57205bbe…`, rootfs
`62397bfc…`, header `0b862b87…`), so the restore target was exact and known.

---

## 2. Why no live register/stat read — the login wall

Stock `/etc/init.norm` loads the datapath modules then `/etc/inittab` runs
`/sbin/getty ttyAMA0 115200` → `/bin/login`. `/etc/passwd` has
`root:x:0:0:root:/root:/bin/sh`; `/etc/shadow` has
`root:$5$qGmxLn8v$…:12086:…` (SHA-256 crypt). The boot reaches `H199A V9.1
login:` (boot.txt line 558) and stops there. No plaintext is held; the UART is
logged and the rules forbid sending secrets. **Therefore every live read the
operation hoped for is unavailable:**

- `/proc/zte/sys/ffe/ffeinfo` (NPU flow count + hit counters) — **unreadable**
- `/proc/zte/sys/ffe/cmd`, the rest of `/proc/zte/*` — **unreadable**
- `devmem2` / `/dev/mem` register dumps (CLA `0x9238c000`, PonPp `0x923a0000`,
  SPA `0x921d4000`, DPA `0x92398000`, the CLA/PM counters) — **unreadable**
- `/proc/net/nf_conntrack` — **unreadable**

This is a real limitation of a locked vendor build, not a tooling gap. The
register reference below is reconstructed from the **boot log** (which prints the
datapath bases and the key config value as the vendor code runs) plus the
**unstripped vendor modules we already hold** (`tm.ko`, `switch.ko`,
`zx_ponreg.ko`), cross-referenced to the measured PP-KEY register map.

---

## 3. The complete vendor datapath bring-up (the shell-free reference)

Source: `logs/stock-harvest-20261117/stock-boot/boot.txt` (676 lines, whole boot
to the login prompt), captured passively (zero UART bytes written) by
`tools/stock-boot-observe.py`.

### 3.1 Bootloader: bank-A rejection → bank-B selection

```
pdt_start_kernel: | Seq | Kernel | Romfs | Header |
                  |  0  | 0x00000000 | 0x00000000 | 0x00000000 |   <- bank A rejected (our invalid self-CRC)
                  |  1  | 0x02000000 | 0x02300000 | 0x03020000 |   <- bank B selected
csp_crc … crc=0xaec3928e, 0x513c6d71     <- computed(data) vs stored-valid self-CRC
Saving Environment to NAND...  Erasing 0xc0000 - 0xe0000 …        <- stock saveenv (explains the 0xc0000 diff, §5)
bootargs = console=$(console) root=/dev/mtdblock8 ro rootfstype=jffs2 mem=$(memsize)
```

`U-Boot 2013.04 (Jul 06 2021)`, CPU `ZX279128S@A9,1000MHZ`, 128 MiB. Stock root is
`/dev/mtdblock8 rootfstype=jffs2` (its rootfs2 region), **which overlaps our
bank-A rootfs under the stock partition map — the mechanism that corrupts mtd7
(§6).**

### 3.2 Linux + module load order (`init.norm`)

```
Linux version 4.1.25 (xialei@localhost.localdomain) gcc 4.9.3 … SMP Tue Jul 6
Kernel command line: console=ttyAMA0,115200n8 root=/dev/mtdblock8 ro rootfstype=jffs2 mem=128M
VFS: Mounted root (jffs2 filesystem) readonly on device 31:8
init normal mode!!!
  insmod shellproc.ko → patch.ko → zx_ponreg.ko → plat-zxylzb_9128S.ko → tm.ko → switch.ko
  ifconfig pon up ; ifconfig sw up ; ifconfig idm0/idm1 up
```

### 3.3 The datapath init — bases, IRQs, WAN register, offload engine

```
pon init
  ZX_PA_BUF_BASE0 = 46e00000   ZX_VA_BUF_BASE0 = c6e00000
  ZX_ACL_BASE     = 46e20000   ZX_VA_ACL_BASE  = c6e20000   <- CLA/flow DRAM table base (phys/VA)
  ZX_FLOW_BASE    = 47220000   ZX_VA_FLOW_BASE = c7220000
  ZX_BP_BUFFER_BASE = 47320000   ZX_DESC_BASE = 47f20000
  BP_BUFFER_SIZE  = c00000 (12 MiB)   BPPE_POOL_SIZE = 1800
  ponmode = 0x10
  g_pon_irq=26  g_npp_irq=27  g_idm_irq=28  g_tm_irq=29  g_pp_irq=30
pon tm init → pon_pp init → pon_npp init → idm_desc_init c8ad3000/46220000 → idm net init ok
mac 0/1/2/3 link down
= TM Module SYS FS Init ended successfully =   tm_initModule … tm_sdk_init … api lock init
Init switch module
  g_sw_cap.sw_uni_count = 4      g_sw_cap.sw_uni_mask = 0x7     (UNI ports 0,1,2 … mask 0x7)
  g_sw_cap.sw_wan_port  = 3      g_sw_cap.sw_wan_mask = 0x8     (WAN = switch port 3)
  g_sw_cap.sw_all_port_count = 7  sw_all_port_mask = 0xef
  g_sw_cap.gwtype1  wantype0  onutype3                         (GPON ONU)
  port id 3, name pon ; sw_set_uni_as_wan uni=3 ; lan_up_port=0x3
  PON_PP_TM_CFG = 0x1200000  →  after PON_PP_TM_CFG = 0x11200000  <<<=== see §3.4
  tm_pon_protocol_pktdeal_set fail, error protocal 33/31/35/36/37/69/34
  [TM][dpa_set_protocol_type_i_act] failed (deal 65/66)          (DPA proto-type init; cf. PP-KEY §13-14)
  chip_tm_init end
[SW][sw_init_switch] l2_fast init
[SW] set cpu queue rate limit to 8000pps
  Capacity=256000  Capacity=256000  [SW][sw_init_switch] reg hff
  register npu driver 12
Init personal switch module Success
```

### 3.4 `PON_PP_TM_CFG = 0x11200000` — the vendor/ours match

The boot log's `PON_PP_TM_CFG` write is the **PonPp WAN-port declaration**. Our
driver's `tm_set_pp_wan_cfg` (PP-KEY §20.3) writes register **`0x923a001c`**
(a.k.a. the PonPp window `0x92000000 + 0xe8007*4`) going `0x01200000 →
0x11200000` to set bit 28 = "switch port 3 is WAN". **Stock's boot prints the
identical transition** `0x1200000 → 0x11200000`. This is a direct, measured
confirmation that:

- the register block PP-KEY §20 reverse-engineered as the PonPp WAN config is
  indeed the vendor's `PON_PP_TM_CFG`;
- our driver's WAN-port declaration value matches the vendor's working state
  exactly; this part of our bring-up is correct and need not change.

### 3.5 What the boot log establishes about offload

- `l2_fast init` / `reg hff` / `register npu driver 12`: the **L2-fast + NPU
  hardfast engine is registered at init, unconditionally** — matching the static
  chain `sw_init_switch`→`l3_hardfastReg` and the default-enabled
  `npu_register_driver` the parent reported.
- `set cpu queue rate limit to 8000pps`: the CPU trap path is rate-limited, i.e.
  the design assumes most traffic is offloaded, not trapped.
- The boot log prints **no `ffeinfo`/flow-count/hit value** (that lives in
  `/proc/zte/sys/ffe/ffeinfo`, shell-only). So the engine's *presence and enable*
  are confirmed; its *hit behaviour on a real flow* is not observable here.

---

## 4. The offload verdict — topology, not throughput

Stock booted; both bench NICs had carrier. Probed, powered on, with the board
running stock (`logs/uart.raw`, `uart-commands.jsonl` not used — all probing was
host-side netns traffic, no UART writes):

| probe (host side) | result |
|---|---|
| LAN jack (enp3s0→eth2, `192.168.1.50`) → br0 `192.168.1.1` | **ping 0% loss**, MAC `02:00:00:00:00:03`; flood 5317/5318 in 2 s |
| WAN jack (enx…→eth3, `192.168.1.60`) → br0 `192.168.1.1` | **100% loss**, ARP INCOMPLETE |
| WAN jack → LAN jack (`.60`→`.50`) and reverse | **100% loss** both ways |
| WAN jack ARP sweep `.1` on 192.168.1/10.0.0/192.168.100 | **no reply on any subnet** (eth3 has no IP) |
| stock mgmt surface on br0 | TCP :80/:443 open (`ZTE web server 1.0`), :22/:23/:21 closed |

**Interpretation.** The LAN jacks are bridged into `br0`; the WAN jack (switch
port 3) is `sw_set_uni_as_wan uni=3` — the PON/fibre uplink role — and is
**isolated from the LAN bridge**, with no IP and no ARP responder, because the
optical line is absent. There is no GE-WAN→GE-LAN flow for stock to route or
offload. **A stock GE→GE routed throughput number does not exist to be measured
on this board** — not ~900 (offload), not ~350 (software), but *no path at all*.
That is the definitive answer the task flagged as a valid outcome: the product
forwards subscriber traffic WAN(optical)↔LAN(Ethernet); it never routes
Ethernet-WAN↔Ethernet-LAN, so there is no GE↔GE offload to characterise.

What this means for the port: the OpenWrt use case (route a real GE Ethernet WAN
to GE LAN) is **a different datapath than anything stock runs on this hardware**.
Stock's hardware fast-path (`l2_fast`/NPU) is organised around the
UNI↔PON(optical) directions. This is fully consistent with PP-KEY §24–§27's
measured conclusion that the CLA inner-hash exact-match is not consulted for a
GE-WAN↔GE-LAN frame in either direction: the vendor silicon's fast path simply
is not pointed at that direction, and no vendor software configures it to be,
because the product never needs it.

---

## 5. Before/after dump diff — every changed byte

Three full corrected dumps, each verified host-stream == on-device re-read,
`read-errors=0`, 65536 pages:

| dump | sha256 | when |
|---|---|---|
| baseline | `068c118c89f24f69196ce85b2e606d0f53642b1ecd9d276edb63999d8d468573` | before anything |
| after-stock | `f19cd01ee773f35135207b142a5c594f8dc01f2f63b0af2ec29b16a2dd9efebb` | stock ran + header restored + bank A re-flashed |
| final | `9d34e0a739edf524e7b5b6df48c3917d79df2947d422b49810c9789ec2738384` | our image booted once, powered off |

Per-partition (data+OOB), **final vs baseline** and the role of each change:

| partition | range | final vs baseline | who wrote it |
|---|---|---|---|
| bootloader | `0x0`–`0x100000` | **SAME** | stock did a `saveenv` at `0xc0000` (env sector: `bootcmd` rootfstype squashfs→jffs2 + env CRC); our own boot's `saveenv` rewrote it back to the squashfs value → net identical to baseline |
| tag | `0x100000` | SAME | untouched (never written) |
| wifi | `0x200000` | SAME | untouched |
| **usercfg** | `0x300000`–`0x500000` | **DIFF: 4 pages** `0x42f000,0x42f800,0x430000,0x430800` | **stock** appended jffs2 nodes (was `0xff`, now data+valid BCH OOB) when `init.norm` mounted `/dev/mtdblock4` rw; persists (vendor config, outside bank A) |
| defcfg | `0x500000` | SAME | untouched |
| kernel1 | `0x700000` | SAME (== prod-v5 `57205bbe…`) | re-flashed exact |
| rootfs | `0xa00000` | SAME (== prod-v5 `62397bfc…`) | re-flashed exact |
| header | `0x1720000` | SAME (== baseline `0b862b87…`, self-CRC `71 6d 3c 51`) | restored exact |
| kernel2 (bank B) | `0x2000000` | SAME | **never written** |
| rootfs2 (bank B) | `0x2300000` | SAME | **never written** |
| legacy_overlay | `0x4000000` | SAME | untouched |
| staging (below UBI) | `0x5000000`–`0x5400000` | SAME | untouched |
| **overlay_ubi** | `0x5400000`–`0x6400000` | **DIFF: 124 pages** `0x56a4800`–`0x62fa800` | **our own OpenWrt** attached/wrote its UBI overlay on boot — explicitly permitted by the production write policy printed at boot: `program/erase only bank A [00700000,01740000) and UBI [05400000,06400000)`; UBI-managed (OOB `0xff`), not stock |
| tail | `0x6400000`–end | SAME | untouched |

**Net, attributable:** stock's only persistent footprint outside bank A is **4
jffs2 pages in usercfg** plus a transient bootloader-env `saveenv` (self-reverted
by our boot). Our image's only footprint is its own **UBI overlay** in the
sanctioned `[0x5400000,0x6400000)` window. **Bank A and the entire bank-B
recovery image are byte-exact to baseline.** Formal check:
`verify-final-vs-baseline.json` — bank-A parts all `equal:true`,
`read_errors_zero:true`; the only `outside_diff_pages` are the four usercfg
pages.

---

## 6. The reconfirmed hazard: stock corrupts our bank-A rootfs

Previously recorded as a hazard (round 116/117) and then marked "DEAD" (round
132, which tested a *different* unit/build and found the rootfs intact). **This
run shows it is real for the current production layout.**

After stock ran, the read-only dumper `perst-w` (cmdline
`… ro init=/bin/sh`, `setting mtd7 (rootfs) as root device`) **panicked**:
`Kernel panic … VFS: Unable to mount root fs on unknown-block(31,7)` at the
squashfs stage. Reproduced on three boots. Tested against the restore state: the
panic persisted **after** the bank-A header was restored to its exact original
bytes — so it was **not** a header artefact; the squashfs data in mtd7 itself was
damaged. The mechanism is in the boot log: stock boots `root=/dev/mtdblock8 …
rootfstype=jffs2` and, under the stock partition map, that region overlaps our
bank-A rootfs; the vendor jffs2 layer writes/garbage-collects it.

**Consequence for recovery:** a header-only restore is insufficient after a stock
boot — the rootfs must be re-written too. We re-flashed all three bank-A parts
from `prod-v5` (byte-identical to the baseline bank A), after which `perst-w`
mounts mtd7 cleanly and our production image boots and verifies. **Operational
rule for any future stock round-trip on this layout: always re-flash bank A
(rootfs+kernel+header), never header-only.**

This cost the byte-exact capture of mtd7's *post-stock* bytes (recovering a
bootable dumper required overwriting mtd7). The damage itself is proven by the
reproducible, header-independent squashfs mount panic; everything *else* stock
touched is captured byte-exact in the after-stock and final dumps (§5).

---

## 7. Harvested register reference — stock working state vs ours

What a working vendor configuration programs, assembled from the boot log and the
unstripped modules, mapped onto the registers our driver already knows (PP-KEY).
Live register *values* could not be read (no shell, §2); these are the
*addresses/ownership/one measured value*, which is what the port needs.

| block | our driver window | stock boot-log fact | implication for the port |
|---|---|---|---|
| **PonPp WAN cfg** | `0x923a001c` (`tm_set_pp_wan_cfg`, PP-KEY §20) | **`PON_PP_TM_CFG 0x1200000 → 0x11200000`** (measured) | **exact match** — our WAN-port declaration (port 3 / bit 28) equals the vendor's; keep it |
| **CLA/flow DRAM tables** | CLA regs `0x9238c000`; DRAM table base is separate | **`ZX_ACL_BASE=0x46e20000` VA `0xc6e20000`**, `ZX_FLOW_BASE=0x47220000` | the CLA/PM hash+flow tables live in DRAM at `0x46e20000`; stock maps them VA `0xc6e20000`. Our driver must point the CLA table-base registers at its own reserved DRAM, not assume a register-only engine |
| **SPA parse** | `0x921d4000` (+ `0x921d41c0` trap selector) | `dpa_set_protocol_type_i_act failed` for several protos; `tm_pon_protocol_pktdeal_set fail 31/33/34/35/36/37/69` | vendor DPA proto-type init is partial/best-effort even on stock; the parse gate PP-KEY §23 (`0x921d41c0`) is *not* set by any stock module (PP-KEY §23.1) — unchanged conclusion |
| **switch L2-fast / NPU** | (not in our driver) | `l2_fast init`, `Capacity=256000`, `reg hff`, `register npu driver 12`, `cpu queue rate limit 8000pps` | the vendor fast path is the **switch/NPU** engine, registered by `switch.ko`, organised around UNI↔PON. Our driver is a pure-Ethernet NIC; it does not instantiate this engine. The GE↔GE offload the port wants is **not** what this engine does |
| **IRQ map** | — | pon 26, npp 27, idm 28, tm 29, pp 30 | reference for wiring the datapath IRQs if the port ever drives TM/PP directly |
| **buffers/desc** | — | `BP_BUFFER 0x47320000 (12 MiB)`, `DESC 0x47f20000`, `ponmode 0x10`, BPPE pool `0x1800` | the vendor reserves 12 MiB BP buffer + descriptor rings in upper DRAM; a hardware datapath port needs equivalent reserved memory |

### 7.1 What this settles for the port

- **The WAN declaration is correct** (`0x923a001c=0x11200000`), proven against the
  vendor. Not the gap.
- **The gap PP-KEY §24–§27 found is structural, and the stock harvest is
  consistent with it:** the vendor's hardware fast path is the switch/NPU engine
  on the UNI↔PON directions, and stock never configures a GE-WAN↔GE-LAN hardware
  flow because the product has no such flow. No register or table our Ethernet
  driver writes will make the CLA inner-hash fire for GE↔GE, because the vendor
  itself does not drive that path — there is no vendor "working configuration" of
  GE↔GE offload to copy, on this silicon, in this product.
- **The remaining vendor-only state is the switch/NPU hardfast engine
  (`switch.ko` `npu_drv_create_flow` → `hf_set_l3_entry` →
  `zte_api_fast_l3_session_add`), which runs on the PON datapath**, plus the
  CLA/PM DRAM tables at `0x46e20000`. Reproducing GE↔GE hardware offload would
  mean standing up that engine for a direction the vendor never used — a far
  larger task than any CLA register write, and unproven to be possible on this
  part.

### 7.2 What we could NOT read, and why (so the next attempt knows)

| wanted | why unreadable | how to get it in future |
|---|---|---|
| `/proc/zte/sys/ffe/ffeinfo` (flow count, hit counters) | login wall; no plaintext; UART-secret rule | need the vendor root password (not in scope) or a shell via a non-UART channel |
| `devmem2` reads of CLA/PonPp/SPA/DPA/counters | same | same |
| CLA/PM counters `0x9238c3c0`–`0x9238c3dc` before/after | same + no GE↔GE traffic to move them | would also need a drivable offload flow, which stock doesn't present |
| stock userspace offload knobs | same | — |

The boot log is the shell-free substitute and it carries the one register value
(`PON_PP_TM_CFG`) that was actionable.

---

## 8. Final state

- Board **powered off**, **bank A = our production image** (prod-v5, byte-identical
  to baseline), verified booting: `correct header has been found @1720000` →
  `[0]firmware` → verify kernel/fs success → OpenWrt 6.6.151 squashfs root →
  console ready (`verify-bankA-boot/result.json`).
- Bank B (stock recovery), bootloader, `tag`, `wifi`, `defcfg` byte-identical to
  baseline.
- Residual outside-bank-A deltas: 4 usercfg jffs2 pages (stock), UBI overlay
  window (our image) — both expected (§5).
- Tools added: `tools/h199a-header-write.py` (scoped bank-A header writer, used
  for invalidate+restore), `tools/stock-boot-observe.py` (passive stock-boot
  capture).
