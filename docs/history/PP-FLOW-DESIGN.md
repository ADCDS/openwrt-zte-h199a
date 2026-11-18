> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# Installing one hardware flow on the ZX279128S packet processor

Status, 2026-11-16: **decoded spec + a strictly-gated, test-only write path,
and the 45-byte match key is now decoded too** (`docs/PP-KEY.md`). Not
hardware-qualified. Off by default (`CONFIG_ZX279128_PP_FLOW_TEST`,
depends on the diagnostic-only `CONFIG_ZX279128_PP_TABLES`). This document is
the evidence the write path in
`files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-pp-flow.c`
rests on. Read `docs/PP-OFFLOAD.md` first (the register protocol and the
read-path qualification), then this, then `docs/PP-KEY.md`.

All evidence is static, read-only disassembly of the stock vendor modules in
`h199a-firmware/stock-flow-audit/` (`tm.ko`, `switch.ko`,
`plat-zxylzb_9128S.ko`), ARM `objdump -dr` / `readelf`. No hardware was
touched. Addresses are tm.ko `.text` offsets unless noted. Every claim is
tagged **proven** (read from instructions / data tables), **likely** (inferred
from naming + partial decode), or **unknown**.

The vendor installs a "fast L3 session" through this call chain (proven from
the saved call graphs and `switch.ko-calls.json`):

```
npu_drv_create_flow (switch.ko)
  -> sw_acl_l3_hardfast_session_add -> zte_api_fast_l3_session_add (tm.ko 0x54868)
       -> tm_acl_setMtchInfo            build a match-info struct per direction
       -> tm_add_acl_flow_rule (0x4ef14)
            -> addFlowOperInfo (0x4adf0) -> operInfoAdd (0x48b58)   build PM entries
            -> tm_acl_fast_add (0x4ee1c) -> tm_acl_fast_add_v4v6 (0x4bd8c)  build CLA entry
```

`zte_api_fast_l3_session_add` calls `tm_acl_setMtchInfo` twice, once per
direction (ORIGINAL + REPLY) — the two-tuple model a real `nf_flow_table`
offload would follow. This spec and the test driver install **one direction,
one entry** (forwarding only); the second direction and NAT are later work.

---

## 1. Register and table map (proven)

Read directly from the vendor register-descriptor tables in `tm.ko .data`
(entry = `{u16 id; u32 type; u32 word_addr; u32 mask; u16 shift; u16 max_idx;
u32 stride}`; phys = `0x92000000 + 4*(word_addr + stride*idx)`). This confirms
and extends `offload-cla-pm-offsets.md`:

| engine | table (`.data`) | CMD | STATUS | DATA |
|---|---|---|---|---|
| CLA | `claRegTable` @0x70 | 0x9238c014 (mask 0x0fffffff) | 0x9238c018 bit0 | 0x9238c01c + 4i, i≤16 |
| PM  | `ppPmRegTable` @0x42d0 | 0x9239c014 (mask 0x0fcfffff) | 0x9239c018 bit0 | 0x9239c01c + 4i (i≤3); 0x9239c100 + 4(i-4) (4≤i≤7) |
| ADM | `AdmRegTable` @0x3c48 | indirect port in the 0x92394000 window (see §6) | | |
| PonPp | `PonPpRegTable` @0x336c | PM base id14 = **0x923a0020**, ACL base id15 = **0x923a0024** (RW, 32-bit) | | |

CMD = `addr | sel<<22 | op<<27` (op 0 write, 1 read). Writes go DATA[n-1]…DATA[0],
RMW, no completion poll; reads re-poll then read DATA high→low. This is the
protocol the hardware-qualified read path already uses — the flow write path
calls straight into `zx_pp_cla_write` / `zx_pp_pm_write`, so it inherits it.

**CLA table selects** (sel in CMD): 0 extra_index, 1 extra_rule, 2–6 exact-hash
(idx<520, bank split 0-255→sel2, 256-383→3, 384-447→4, 448-511→5, 512-519→6;
bank address = idx − bank base), 7 cpu_queue_id, **8 acl_aging** (1 word, the
hit bit), 9 dscp_tc_qid.
**PM table selects**: 0 flow_info (addr = `dir<<10 | idx`, idx<1024, 3 words),
1 next_hop (idx<512, 3 words), 2 vlan_modify, 3 cmd_ram (idx<8192, 1 word),
6 sub_ram (2 words). (proven, from the `mov r1,#sel` before each call and the
`cmp` bounds.)

---

## 2. CLA match key and hash placement

### Key build — `tm_acl_get_fastHashRule` (0x46c48)

Builds a **45-byte bit-packed key** from the match-info struct (the `memzero`
of 45 bytes at 0x4bdc0 names the size). The key carries the 5-tuple, the IP
protocol, the **ingress port** (`aclGetExtIdxRuleRamAddrByPort` 0x4841c selects
per-port rule RAM — ingress-port scoping is real), L2 type, tag level and
pppoe flag. The exact 45-byte bit layout is ~450 instructions of `bfi`/`ubfx`
packing.

- **Proven:** the key is 45 bytes, is ingress-port-scoped, and includes the
  IPv4 5-tuple + protocol. TCP vs UDP both take rule type 3
  (`zte_api_fast_l3_session_add` 0x54968: `cmp r3,#6; cmpne r3,#17; moveq r3,#3`).
- **Decoded (2026-11-16):** the full 45-byte layout, in `docs/PP-KEY.md`. Two
  corrections to what this section used to say: `tm_acl_get_fastHashRule` fills
  the **60-byte window**, not the key (the caller repacks the key from window
  bytes 17..56), and the key is scoped per port **and per direction**, so an
  ORIGINAL and a REPLY entry for one tuple hash to different buckets.

### Hash function — `cla_acl_hash_addr_gen` (0x6cdc)

A byte-wise **CRC-32** over the 45-byte key (the classic
`crc = (crc<<8) ^ table[(crc>>24) ^ byte]` loop, `CRC_32` 0x6c58), result
truncated to 16 bits (`uxth`), init 0. The polynomial table is selected by a
hash "mode":

| mode | table (`.data`) | polynomial |
|---|---|---|
| way0 | `crctable_04C11DB7` @0xaec | 0x04C11DB7 (CRC-32) |
| way1 | `crctable_1EDC6F41` @0xeec | 0x1EDC6F41 (CRC-32C) |
| 2 | `crctable_F4ACFB13` @0x12ec | 0xF4ACFB13 (CRC-32K) |
| 3 | `crctable_32583499` @0x16ec | 0x32583499 (CRC-32Q) |

(**proven**: the four tables are present verbatim in `.data`; their first
non-zero word equals the polynomial. The LANCHOR offsets in
`cla_acl_hash_addr_gen` resolve to these four addresses.)

### Bucket placement — `aclGetAvailableHashAddr` (0x4b6c8)

Tries way0 → way1 → the outer table, masking the CRC to each bank
(`&0x7f +0x100` for way1, `&0x3f +0x180` for way2, `+0x1c0` for bank3, overflow
to the outer table), then a **linear scan of 512..519** with no hash at all
(mode 2). (**proven** structure; depends on the key, so **unknown** in practice.)

The free-slot test is a **software occupancy byte** (`s_aclHashUsedCnt`), not a
read of the aging table: the vendor keeps its own map and the hardware exposes
none. So a driver has to keep one too. An earlier revision of this section said
"checks the aging table" and "overflow to the external hash at idx+0x208"; both
were wrong, and the difference matters, because a driver that believed the
occupancy were readable would install over a live entry.

### Placement used by the test driver (superseded)

The test driver writes its entry at a **fixed reserved slot** — `cla_hash4`
(sel 6), bank address 7, global hash address 519 — precisely because the key
encoding was unknown, so a real packet could never hash there. That is no
longer necessary: `docs/PP-KEY.md` decodes the key, `zx_pp_build_key()` builds
it from the window, and `zx_pp_hash_buckets()` yields the four buckets a live
packet will look in. The fixed slot stays as the *never-matching* control the
first hardware write test needed, not as the placement strategy.

---

## 3. CLA hash window (the 60-byte entry) — `cla_set_hash_table` (0x5a14)

The 60-byte window (15 LE u32 words) is written to a hash address with sel 2–6
(`cla_set_hash_table` 0x5af0: `add r6,r6,#60; mov r5,#14; … cla_set_indirect_rw_data`
word 14→0). The field→byte/bit map below is the **inverse of the function's own
debug decoder** (it reads each field back out of the window to print it), so it
is the exact RAM layout. Byte N = word[N/4] byte N%4 (little-endian). The
read-path debugfs file `cla_hash4` returns these same LE words.

| field | byte.bit (width) | evidence (addr / instr) | tag |
|---|---|---|---|
| valid_en | b16.6 (1) | 5cb4 `ubfx r2,[r6,#16],#6,#1` | **proven** |
| direct | b16.5 (1) | 5cbc `ubfx r3,…,#5,#1` | **proven** |
| rule_mode | b16.4 (1) | 5cb0 `ubfx ip,…,#4,#1` | **proven** |
| da_known | b18.4 (1) | 5cc0 `ubfx r1,[r6,#18],#4,#1` | **proven** |
| modify_en | b5.6 (1) | 5e58 `ubfx r3,[r6,#5],#6,#1` | **proven** |
| cmd_flow_id | b3[7:1]+b4[2:0] (10) | 5e98 `lsl r2,[r6,#4],#7`; 5e9c `orr r2,r2,[r6,#3],lsr #1` | **proven** |
| inport | b12[7:5]+b13[1:0] (5) | 5d38/5d48/5d4c | likely |
| outport | b14[5:0] (6) | 5d44 `and r3,[r6,#14],#0x3f` | likely |
| windata0..19 (match key) | b16[7]..b58 | LC234–LC239 | unknown encoding |

The low bytes (0–16) hold the action (queue/act/cmd_flow_id/ports/valid/rule);
the high bytes (17–58) hold windata0..19, the stored match key. **cmd_flow_id
links the CLA entry to the PM flow_info entry** (index into PM sel 0).
**windata's tuple encoding is the same unknown as the 45-byte key** — the test
driver fills windata with the 5-tuple in a *driver-defined* order (for readback
only, clearly not the vendor encoding).

The test driver sets: `valid_en=1`, `rule_mode=1` (exact match), `modify_en=1`,
`cmd_flow_id=` the flow_info index, `inport=`ingress, `outport=`egress; it
zeroes everything else and stores the tuple in the driver-defined key region.

---

## 4. PM entries (proven word layouts)

### next_hop — `pp_pm_set_next_hop_ram_info` (0x1d66c), sel 1, 3 words

A 10-byte record = next-hop **DMAC[6]** + next-hop **DIP[4]**
(LC36 "`next_mac: …, next_dip: %d.%d.%d.%d`"), packed (0x1d760–0x1d7ac):

```
word0 = b2<<24 | b3<<16 | b4<<8 | b5
word1 = b6<<24 | b7<<16 | b8<<8 | b9       (b6..b9 = next-hop IP)
word2 = b1<<8  | b0                         (16-bit)
```

**proven.** (SMAC is not here; see smac_en below.)

### cmd_ram — `pp_pm_set_cmd_ram_info` (0x1dfec), sel 3, 1 word

One rewrite micro-op (0x1e0e8–0x1e0fc):

```
word = modify_data[15:0] | offset[20:16] | ip_cksum[21] | tcp_cksum[22]
       | last_cmd[23] | dat_type[25:24]
```

`offset ≤ 28` (0x1e06c `cmp r3,#28`). `writeCmdInfoToRam` (0x48714) streams an
array of 12-byte descriptors `{dat_type, last_cmd, tcp_cksum, ip_cksum,
u32 offset, u16 data}` into consecutive cmd_ram indices.

- **proven:** the word packing and the descriptor array format.
- **unknown:** the **packet offset** each NAT field maps to (the base reference
  point for `offset` depends on L2/VLAN/PPPoE encapsulation; it is computed in
  `operInfoAdd`, not a constant). Source-IP/port rewrite routes through here, so
  **header rewrite rests on this unknown** → the test driver refuses it.

### flow_info — `pp_pm_set_flow_info` (0x1cef8), sel 0, addr = `dir<<10 | idx`, 3 words

The central per-flow modify descriptor. addr encoding is
`orr r2, flow_ram_addr, dir, lsl #10` (0x1cfa8, **proven**: `dir<<10 | idx`,
idx<1024). The 12-byte field map is the inverse of its debug decoder
(0x1d004–0x1d0e0, **proven**):

| field | byte.bit (width) |
|---|---|
| dmac_en | b0.0 |
| smac_en | b0.1 |
| nat_dport | b0[7:2]+b1+b2[1:0] (16) |
| nat_sport | b2[7:2]+b3+b4[1:0] (16) |
| tcp_udp_chk_en | b4.3 |
| ip_chk_en | b4.4 |
| dport_en | b4.5 |
| sport_en | b4.6 |
| dip_en | b4.7 |
| sip_en | b5.0 |
| subnet_id | b5[4:1] |
| pri_dscp_tc_en | b6.1 |
| next_hop_idx | b6[7:2]+b7[2:0] (9) |
| sub_ram_index | b7[7:3]+b8[4:0] (10) |

The test driver programs a **forwarding + L2-rewrite** descriptor: `dmac_en=1`,
`smac_en=1`, `ip_chk_en=1`, `tcp_udp_chk_en=1`, `next_hop_idx=` the reserved
next_hop entry; all header-rewrite enables (`sip_en`/`dip_en`/`sport_en`/
`dport_en`) **0** (those drive cmd_ram, the unknown above). `smac_en=1` inserts
the **egress port's** MAC (the window carries no SMAC; `next_hop` carries only
DMAC). The spec's `src_mac` argument is therefore advisory and recorded in the
log, not placed — a custom SMAC ≠ port MAC is **unknown** and not attempted.

- `sub_ram` (sel 6) was checked (`pp_pm_set_sub_ram_info` 0x1e758): it carries
  dscp/dei/dslite/pppoe flags and `cmd_addr`/`vlan_addr`/`modi_dat_addr`
  pointers — it is a *chain to* cmd_ram, not where a new IP lives. So there is
  no rewrite path that avoids the cmd_ram-offset unknown. (proven it is not the
  IP store.)

---

## 5. Hit / byte counters

### CLA aging hit bit — `tm_get_acl_flow_status` (0x4e760) + `cla_get_acl_aging_table` (0x7318), sel 8

The reliable **per-flow** signal. The aging index is the entry's hash address:
internal → `hash_addr`; external/overflow → `hash_addr + 0x400`
(0x4e788 `tst … #0x10000; addne r4,#0x400`; 0x4e7e8 external path). The vendor
**reads the bit then writes 0** (0x4e7a0 read, 0x4e7c8 `cla_set_acl_aging_table(addr,0)`)
— read-to-clear. (**proven.**) The test driver's `stat` reads `aging[519]`,
logs `hit`, and clears it the same way.

### ADM packet/byte counters — `adm_get_pkt_stastc` (0x1c4ac)

Returns `{pass_pkts, pass_bytes}` from the ADM indirect port
(`AdmRegTable` id7 DATA @0x9239401c). `zte_api_fast_l3_session_stat` (0x52ec8)
calls it twice (dir 0 = down, dir 1 = up). **But the index is bounded to ≤31**
(0x1c4e8 `cmp r8,#31`), i.e. per-WAN / per-queue, **not per-flow**. So ADM
gives truthful aggregate byte/packet counts but **its per-flow semantics are
unknown** (design-note risk §(d)3). The test driver uses the CLA aging bit as
the flow hit indicator and leaves ADM to a later, measured step.

---

## 6. Deletion and making an entry inactive — `delAclRule` (0x47e58)

Deletion writes a **zeroed 60-byte window** back to the same hash address via
`cla_set_hash_table` (0x47fe8–0x480ec: the shadow entry at `[r6, #0x6c..0x78]`
is cleared, then re-written), which drops `valid_en` to 0; it also clears the
extra-index table and the aging bit. (**proven.**) An entry is made inactive
simply by rewriting its window with `valid_en = 0` — the test driver's delete
writes an all-zero window, clears `aging[519]`, then zeroes the flow_info and
next_hop entries it pointed at, in that order (CLA first, so the engine stops
considering the entry before the PM entries behind it disappear).

---

## 7. Trap-to-CPU default

The exact-match hash sits **above** the ternary "extra_rule" / "extra_index"
defaults installed by `tm_acl_fast_init` (0x4b…) / `tm_acl_3tuple_fast_init`.
A packet that matches no installed exact flow falls through to those defaults,
whose action is **trap-to-CPU** → the normal netfilter/bridge path. So an
installed forwarding flow only ever *adds* a hardware fast-path over the
existing software path; removing it (or never matching) leaves traffic trapping
to the CPU exactly as today. (Consistent with `offload-cla-pm-design.md` §(b)
"Trap precedence"; the default-rule action itself is **likely** trap-to-CPU,
not re-read instruction by instruction here.)

---

## 8. What the test write path does (and refuses)

`zx279128-pp-flow.c`, behind `CONFIG_ZX279128_PP_FLOW_TEST`
(depends on `CONFIG_ZX279128_PP_TABLES`, default n), module parameter
`flow_test_enable` (default 0, must be 1 to accept any write), **one flow at a
time**. Root-only, write-only debugfs file `/sys/kernel/debug/zx279128-pp/flow`:

```
add <in> <tcp|udp> <sip>:<sport> <dip>:<dport> -> <out> <nsip>:<nsport> <dmac> <smac>
del <id>
stat <id>
```

**Install sequence** (each line is one indirect op; proven layouts only):

1. `zx_pp_pm_write(pm, sel 1 next_hop, idx 511, 3 words)` — DMAC + dst IP.
2. `zx_pp_pm_write(pm, sel 0 flow_info, addr (0<<10)|1023, 3 words)` — next_hop
   link + L2/checksum enables, no rewrite.
3. `zx_pp_cla_write(cla, sel 6 hash4, addr 7, 15 words)` — valid_en, rule_mode,
   cmd_flow_id=1023, inport, outport + driver-defined match key.
4. `zx_pp_cla_write(cla, sel 8 aging, addr 519, 1 word = 0)` — clear hit.

**Delete** reverses it: CLA window → 0, aging → 0, flow_info → 0, next_hop → 0.
**Stat** reads `aging[519]` (hit bit), logs it, clears it.

**Refused (`-EOPNOTSUPP`)**, because each would rest on an unknown:
source-IP or source-port rewrite (`nsip`/`nsport` ≠ original → cmd_ram offset),
non-TCP/UDP protocol, and (not expressible in the input) IPv6, DNAT, VLAN,
custom SMAC. `-EPERM` when `flow_test_enable=0`; `-EBUSY` when a flow is already
installed.

**Teardown** deletes the installed flow (if any) *after* its debugfs file is
gone and *before* the engines are disabled and the DRAM tables are freed, so
the engine never walks a table that is about to be returned to the allocator.

---

## Top unknowns (in priority order)

1. ~~**The 45-byte CLA match-key bit layout**~~ — **decoded**, `docs/PP-KEY.md`.
   Two residual questions, both settled by the spray test recorded there: that
   `extIdx` is the port number, and that the engine hashes the key the driver
   builds (static reading only so far).
2. **cmd_ram packet offsets for NAT field rewrite** (`operInfoAdd`). Blocks
   SNAT/DNAT. Until decoded, the write path forwards + rewrites L2 only.
3. **Per-flow byte/packet counting via ADM** (index ≤31 is per-WAN). The CLA
   aging *bit* is the only proven per-flow signal.
4. **inport/outport exact bit positions** in the CLA window (marked likely).
5. **Default-rule action = trap-to-CPU** (marked likely; not re-read here).

## CLA exact-match hash (decoded 2026-11-16; reset values read on hardware)

From tm.ko `cla_acl_hash_addr_gen` (0x6cdc) and the `crctable_*` data. The full
evidence is in the bench note `logs/analysis-20261115/pp-cla-hash.md`.

- **CRC:** table-driven and MSB-first, init 0, no final XOR. Only the **low 16 bits**
  are kept. The 45 key bytes are fed in **reverse order**, key[44] first. (Proven.)
- **Polynomial per way:** a 2-bit selector picks a constant table: 0 = 0x04C11DB7,
  1 = 0x1EDC6F41, 2 = 0xF4ACFB13, 3 = 0x32583499. Each table matches a freshly
  generated one byte for byte. (Proven.)
- **Config registers:** `0x9238c090` holds the inner selectors in bits 0–7 and the
  outer selectors in bits 16–23. `0x9238c094` holds the outer table count and
  size. The vendor never writes either; **on hardware the reset values are
  `0x00e400e4` and `0`**. So inner ways 0..3 use selectors 0..3, and the outer
  table is unconfigured.
- **Inner bucket (4 ways):** way 0 = `h & 0xff`, way 1 = `(h & 0x7f) + 256`,
  way 2 = `(h & 0x3f) + 384`, way 3 = `(h & 0x3f) + 448`. The first free way wins.
  If all four are taken, the outer table is used, and as a last resort entries
  512–519 are scanned. (Proven.)
- **Still unknown:** nothing about the layout — see `docs/PP-KEY.md`, decoded
  2026-11-16 from Ghidra decompilation of the unstripped vendor module. What
  remains is measurement: that `extIdx` is the port number, and that the engine
  hashes what the driver builds.
