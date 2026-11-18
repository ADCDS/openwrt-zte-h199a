> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](README.md),
> [installation](INSTALL.md) and [validation](../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.
> **Scope of the final conclusion:** tested GE-to-GE paths and programmed
> states did not produce exact-match hits or working per-flow offload. A
> default-flow forwarding result was observed. SPA DATA readback is a write
> latch, not independent proof of RAM contents. These results do not prove
> that future hardware acceleration is impossible. See [current status](PP-OFFLOAD.md).

# The 45-byte CLA match key: decoded layout

Status, 2026-11-16: **decoded.** This is the top unknown listed in
`docs/PP-FLOW.md` and `HANDOFF-2026-11-16.md` §3.2, and it was what stopped an
installed flow from ever matching live traffic. Three earlier attempts to
recover it from `objdump` output were cut off partway; the material is the
owner's own vendor module and the purpose is an open-source driver, so the
work was redone with Ghidra decompilation, which is compact enough to read
whole. Only field→offset facts are recorded here, in prose and tables.

Evidence: `tm.ko` from `$BENCH/h199a-firmware/stock-flow-audit/` (ARM LE
relocatable, **not stripped**), loaded into Ghidra headless. Ghidra addresses
are the `.text` offsets used in `docs/PP-FLOW.md` plus the image base
`0x10000`: `tm_acl_get_fastHashRule` at Ghidra `0x56c48`, and
`tm_acl_fast_add_v4v6` at Ghidra `0x5bd8c`.

---

## 1. There are three different buffers, and the names mislead

`tm_acl_get_fastHashRule` does **not** produce the hash key. It fills the
**60-byte CLA window**. The caller then repacks 20 words out of that window
into the 45-byte key. Getting this wrong is what made the earlier readings
inconsistent, so the three buffers are named explicitly here:

| buffer | size | who fills it | evidence |
|---|---|---|---|
| the match-info struct | — | the caller, upstream of both | `tm_acl_fast_add_v4v6` arg 3 |
| the **CLA window** | 60 B | `tm_acl_get_fastHashRule` (its 4th arg) | caller memsets `auStack_64, 0x3c` = 60 |
| the **45-byte hash key** | 45 B | `tm_acl_fast_add_v4v6`, by repacking the window | caller memsets `&uStack_91, 0x2d` = 45 |

The window's own split, from the caller's local layout: bytes 0–16 are action
fields (`auStack_64[15]`, `bStack_55`, `bStack_54`), and bytes 17–56 are the
twenty match words `windata0..19` as little-endian u16 (`uStack_51` …
`uStack_2b`). That confirms the `windata0..19` region of `docs/PP-FLOW.md` §3
and pins it to bytes 17–56 rather than the 16–58 that section estimated.

## 2. The port/type field

Before the hash is computed, the caller overwrites an 8-bit field that spans
**`key[2]` bit 7 and `key[3]` bits 6:0**, written as a rotated byte:

```
key[3] = field >> 1        (bits 6:0 of key[3])
key[2] bit 7 = field & 1
```

so `field = ((key[2] >> 7) & 1) | ((key[3] & 0x7f) << 1)`. The value is

```
field = (extIdx << 4) | type_nibble
```

where `extIdx` is what `aclGetExtIdxRuleRamAddrByPort` returns for the ingress
port (its output is also the `uStack_b8` used as `extIdx * 0x10` throughout),
and `type_nibble` is:

| type_nibble | meaning | evidence |
|---|---|---|
| 4 | IPv4, direction 0 (ORIGINAL) | `uVar3 = extIdx * 0x10 + 4` |
| 0 | IPv4, direction 1 (REPLY) | `uVar3 = (extIdx & 0xf) << 4` |
| 6 | IPv6, direction 0 | `uVar3 = extIdx * 0x10 + 6` |
| 2 | IPv6, direction 1 | `uVar3 = extIdx * 0x10 + 2` |

This confirms the design note's "action payload packs `(port<<4) | type_nibble`"
and settles the ingress-port scoping: the key is per-port and per-direction, so
an ORIGINAL and a REPLY entry for the same tuple hash to different buckets.

The inner probe writes `field` with the outer bit clear; the outer probe sets
`key[2]` bit 7 from `field & 1` and leaves `key[3]` as `field >> 1`. Because the
inner probe runs first and the outer only on a collision, a driver that places
entries in the inner table never needs the outer form.

## 3. The key bit layout

`key[0]` and `key[1]` are zero. `key[2]` and `key[3]` carry the field above.
From `key[4]` on, the twenty window words are packed **one bit out of phase
with the byte grid**, little-endian within each word:

| key bit | source |
|---|---|
| `key[4]` bit 0 | `window[16]` bit 5 (the ingress-port bit set by `tm_acl_get_fastHashRule`) |
| `key[4]` bits 7:1 | `windata0` bits 6:0 |
| `key[5]` bits 7:0 | `windata0` bits 14:7 |
| `key[6]` bit 0 | `windata0` bit 15 |
| `key[6]` bits 7:1 | `windata1` bits 6:0 |
| `key[7]` bits 7:0 | `windata1` bits 14:7 |
| `key[8]` bit 0 | `windata1` bit 15 |
| … | … |
| `key[42]` bit 0 | `windata18` bit 15 |
| `key[42]` bits 7:1 | `windata19` bits 6:0 |
| `key[43]` bits 7:0 | `windata19` bits 14:7 |
| `key[44]` bit 0 | `windata19` bit 15 |
| `key[44]` bits 7:1 | preserved from the caller's buffer |

In closed form: **`windata_j` occupies key bits `33 + 16j` … `48 + 16j`**, with
bit 0 of the word at the lowest key bit. The twenty words therefore fill key
bits 33–352; `key[44]` bits 1–7 are the only bits in the 45-byte key that the
repack does not define, and the vendor leaves them at whatever the memset left.

The decompiled arithmetic that establishes the pattern is a chain of the form
`key[n] = (windata_i >> 15) | ((windata_{i+1} & 0x7f) << 1)` alternating with
`key[n+1] = (windata_{i+1} << 17) >> 24`, which is "1 bit from the previous word
in bit 0, 7 bits of the next in bits 7:1" and "bits 14:7 of the next" — the
one-bit shift `docs/PP-FLOW.md` had already spotted, now with its origin and
direction pinned.

## 4. Where the window's match words come from

`tm_acl_get_fastHashRule` copies **80 bytes from `match-info + 0x60`** onto the
stack (`func_0x000d901c(auStack_78, param_2 + 0x60, 0x50)`) and then assembles
the twenty words from named bytes of that copy, plus two 16-bit fields
(`uStack_30`, `uStack_2e`) written to window bytes 0x35–0x38.

So the tuple encoding inside the window is a *second* mapping, from the
match-info struct's `+0x60` block. That mapping is not needed to place an entry
for a flow the driver constructs itself: the driver writes the window, and §3
turns that window into the key. It is only needed to interoperate with entries
the vendor installed.

## 5. What this changes in the driver

`zx_pp_build_key()` in `zx279128-pp-hash.c` implements §2 and §3. Given the
60-byte window the driver is about to write, and the port/type field, it
produces the 45-byte key, and `zx_pp_hash_buckets()` then yields the four
buckets. `tests/test_pp_hash.py` pins the packing against the bit-position
table above, so a transcription error in either shows up as a test failure
rather than as an entry that silently never matches.

Two things are still unproven and need hardware:

1. **`extIdx` is the port number.** The vendor feeds
   `aclGetExtIdxRuleRamAddrByPort(port)`'s output into `field`, and that
   function returns a per-port rule-RAM index whose relation to `eth<N>` is not
   established. The spray test in §6 settles it in 16 trials.
2. **The engine hashes the same key the driver builds.** Everything here is a
   static reading of the vendor's own placement path, which is strong evidence
   but not a measurement. The hit bit is the measurement.

## 6. The measurement that closes it

No disassembly is needed for this, and it is fully reversible.

1. Build a diagnostic RAM image (`BOOT_PROFILE=diagnostic BRINGUP=1
   PP_TABLES=1 PP_FLOW_TEST=1`), boot it.
2. Spray one way's bank with a candidate window, using `zx_pp_build_key()` to
   pick the bucket. Spraying a whole bank needs no hash at all and tests the
   window encoding on its own.
3. Send datagrams from the WAN host to a TEST-NET-1 destination nobody is on.
4. Read the aging table. The set index is the bucket the engine computed for
   that packet, so a hit proves both the key and the placement; a miss on a
   different port is the negative control.
5. Repeat with one tuple bit flipped at a time. The CRC is linear over GF(2)
   (`zx_pp_hash16(a ^ b) == zx_pp_hash16(a) ^ zx_pp_hash16(b)`), so each flip
   isolates where that field sits — which is what confirms §3 end to end.

`docs/PP-FLOW.md`'s "Placement used by the test driver" section, which parks the
single test entry at slot 519 because the key was unknown, is superseded: an
entry can now be placed at the bucket a live packet will hash to.

---

## 7. Hardware results, 2026-11-16 — the key is not enough

Three RAM boots of a diagnostic image (`BOOT_PROFILE=diagnostic BRINGUP=1
PP_TABLES=1 PP_FLOW_TEST=1`) were used to test a live IPv4 flow. **No flow
matched.** The negative result is recorded here because it eliminates most of
the search space and the remaining hypotheses are specific.

Evidence: `$BENCH/logs/offload-20261116/{en1,key2,key3}`.

### What worked on hardware

| step | result |
|---|---|
| tables live | `pp: tables live, pm 0x42600000 acl 0x43000000 (were 0x56409000 0x5f600000)` |
| hash selectors read | `cla hash poly way0..3=0,1,2,3 outer=0,1,2,3 num=0 space=0`, `usable=1` — matches the recorded reset value `0x00e400e4` exactly, and confirms reading rather than assuming |
| `cla_aging` exposed | the file is present and reads/writes |
| hashed install | `hashed id 1: in3 proto17 198.51.100.2:40001 -> 192.0.2.77:40002 egress0 bucket 68 (sel 2 bank 68) key field 0x34` — four indirect writes, no stall, no timeout |
| per-port enable | `extra_index[3] word4 0x00000000 -> 0x00000030` |
| spray | 256 + 128 + 64 + 64 slots written, no stall |
| packets arrive | `eth3` `rx_packets` 0 → 20, twice, with a raw IPv4/UDP frame carrying the exact tuple |

### What was eliminated

1. **Placement and the hash.** With the window sprayed into **all 512 inner
   slots**, a matching packet still set no aging bit in any bank. So neither
   the bucket arithmetic nor `extIdx` can be the blocker for a *match*; the
   hash only decides where the engine looks, and it was told to look
   everywhere.
2. **The SPA UDP/TCP trap.** `0x921d41c0` read `0x11060000`. Clearing the UDP
   field changed nothing: packets still reached the CPU and the hit bit stayed
   0. The trap is not what gates the CLA.
3. **Source/destination orientation.** Both orderings of the tuple in the
   window were sprayed; neither matched. So a plain address/port swap is not
   the explanation (though the *field positions* could still be wrong).
4. **The per-port enable.** `EN_V4FAST_EXTIDXTBL`'s word-4 bits 5:4 were set
   (`0x00` → `0x30`) and the entry re-read back; still no hit.
5. **The CLA global config.** `cla_set_config` writes CLA register **id 3**,
   which the register table resolves to **`0x9238c080`** (`id 3 → word
   0xe3020`). It read `0x0000301a`; the vendor's `tm_pon_pp_cla_initial` sets
   the fields that map to **bits 9, 10 and 11**, which were clear. Setting
   them (`0x0000301a` → `0x00003e1a`) still produced no hit.
6. **MTU.** `0x9238c098` read `0x47d047d0`, i.e. two non-zero 16-bit limits,
   so frames are not being treated as oversize.

### Second hardware round, 2026-11-16 (after the window fixes)

Four more things were eliminated, each by its own measurement:

7. **The action-side ingress field.** All sixteen candidate values of
   `inport` were tried (0..15), each with its own `extra_index` enable and the
   window sprayed into all 512 slots, with 80 packets arriving. Zero hits. The
   port field is not the blocker.
8. **The window bytes this driver omitted.** The vendor writes the port/type
   field into window[15] bits 7:4 and window[16] bits 3:0, sets window[16] bit
   6, and leaves window[18] at 0x10. All of that is now written, and it
   changed the computed bucket (68 -> 157), so the key really did change. A
   full spray with the corrected window still matched nothing.
9. **`rule_mode`.** The spec recorded window[16] bit 4 as "1 = exact match"
   and the driver set it. The vendor does not: `tm_acl_get_fastHashRule` ends
   its window[16] handling with `param_4[0x10] & 0xc0 | ((uVar8 & 1) << 5)`,
   which clears bits 5:0, and `uVar8` is zero for every rule type it builds
   (rule+0x1c is 0x301600 for TCP/UDP, 0x401600 or 0x1600 otherwise, and bit 2
   is clear in all three). So a fast-path entry has rule_mode 0. Setting it to
   0 is correct and is now the driver's behaviour - and it is still not
   sufficient on its own.
10. **The CLA global config.** `cla_set_config` writes CLA register id 3 =
    `0x9238c080` (id 3 -> word 0xe3020 in `claRegTable`). Its packing was
    decoded and the vendor's exact value computed from
    `tm_pon_pp_cla_initial`'s field settings: **0x00000e0a**, not the 0x0000301a
    the register held. Writing that value still produced no hit.

### What remains

Everything the driver can express has now been varied. What is left is the
context the engine needs before it will consult the exact-match table at all:

1. **The match-word semantics are not what §4 assumes.** §4 derives the word
   assignment from `tm_acl_get_fastHashRule`'s IPv4 branch reading the
   match-info struct. That tells us what the vendor *stores*, not what the
   engine *compares*. The comparison may include words this driver leaves
   zero — notably `windata0` (window bytes 17–18), which the vendor's IPv4
   branch does not write either, but which may carry an L2-type or ethertype
   discriminator set elsewhere. Worth reading back a window the vendor
   installed, if a stock boot can be made to install one.
2. **The ternary default rules are missing - now the leading candidate.** The
   design note says the
   exact-match hash sits *above* the defaults installed by `tm_acl_fast_init`
   / `tm_acl_3tuple_fast_init`, and this driver installs neither. A hit may
   require that lookup context to exist. `tm_acl_fast_init` writes
   `extra_rule` entries at indices `0x90`, `0x91`, `2`, `3` and enables
   `extra_index` entries 9 and 10 — a bounded, self-contained sequence to
   port.

Both are reachable with the same method used here: decompile the vendor
function, port the sequence behind the existing gate, and re-run the spray.

### Method note

The spray is what made this tractable. Without it, a single non-matching
install cannot distinguish "wrong bucket" from "wrong key" from "engine never
looked". With it, those three collapse into one, and the remaining question is
only what the engine compares.

---

## 8. What section 7 was missing, 2026-11-16: the field is a rule index

Section 7 ended with two candidates. Both were right, and they are the same
mistake seen from two sides: **the exact-match hash is not a standalone
lookup**. The window's port/type `field` is an *index into the ternary
`extra_rule` table*, and that rule is what tells the engine which packet bytes
to compare. With the rule absent, an exact-match entry refers to a program
that extracts nothing — which is exactly consistent with every measurement in
section 7, including the spray across all 512 inner slots.

Three static findings, all from the unstripped `tm.ko`, none needing hardware.

### 8.1 `extIdx` is not the ingress port

`aclGetExtIdxRuleRamAddrByPort` (Ghidra `0x5841c`) does not consult its
per-port map when the fast path is active. It begins:

```
if (port < 0x20) {
    if (g_ipv4FastEn) { *out = 9;  return 0; }
    if (g_ipv6FastEn) { *out = 10; return 0; }
    ... s_aclPortExtIdxTblMap lookup ...
}
```

and `tm_acl_fast_add_v4v6` (`0x5bd8c`) sets `g_ipv4FastEn` immediately before
calling it, for rule type 3 — which is what both TCP and UDP become. So every
IPv4 5-tuple fast flow, on every port, uses **extIdx 9**. The per-port map
`s_aclPortExtIdxTblMap` is only reached when neither fast flag is set.

This retracts section 2's "the key is per-port": the hashed bucket is
port-*independent*. Hardware result 7 in section 7 — all sixteen `inport`
values tried, zero hits — is explained: none of them was ever the right thing
to vary.

### 8.2 The field is the `extra_rule` index, and the nibble is 0

`field = (extIdx << 4) | nibble`, so for the 5-tuple IPv4 path it is
`9*16 + 0` = **0x90**. And `tm_acl_fast_init` (`0x5e8e0`) writes its IPv4 rule
pair at **`extra_rule[0x90]` and `[0x91]`**. The field and the rule index are
the same number; that is the link that was missing.

The nibble is 0, not 4. `tm_acl_fast_add_v4v6` takes the
`(uStack_b8 & 0xf) << 4` branch for this case; nibble 4 belongs to the
*3-tuple* path, the one guarded by `g_v4OutUsed_3t`.

The enable bit differs too: `tm_acl_fast_init` sets **bit 0** of word 4 of
`extra_index[9]`, while `EN_V4FAST_EXTIDXTBL`'s bits 5:4 — what the driver was
setting, on `extra_index[<port>]` — are a different control on a different
entry. Hardware result 4 in section 7 was therefore enabling the wrong thing.

### 8.3 An `extra_rule` entry is an extraction program

This is the part that also answers section 7's first candidate. The field
names come from `cla_set_extra_rule_table`'s own debug strings:

```
rule_id, winoffset0..19, winmask0..19, outport_mask, inport_mask,
taglevel_mask, l2info_mask, pppoe_mask, no_match_act, rule_mode,
hash_len, mem_ctrl
```

So the rule is not a value/mask pair over a fixed key. **`winoffset_j` says
which packet byte-pair becomes `windata_j`, and `winmask_j` says which of its
bits are compared.** Decoding the IPv4 rule through that decoder:

| field | value | meaning |
|---|---|---|
| `winoffset0..6` | 8, 12, 14, 16, 18, 20, 22 | IPv4 header byte offsets |
| `winoffset7..19` | 0 | unused |
| `winmask0` | `0x00ff` | keeps protocol at IP+9, **drops TTL** at IP+8 |
| `winmask1..6` | `0xffff` | the addresses and ports, whole |
| `winmask7..19` | `0x0000` | masked out |

Those offsets are the IPv4 5-tuple exactly: `{TTL,proto}`, the two halves of
each address, then the two ports. The `0x00ff` on word 0 is what lets one
stored entry match packets whose TTL differs.

**The cross-check that makes this trustworthy.** The same decoder, unchanged,
applied to the *other* rule `tm_acl_fast_init` builds (the IPv6 one, written
at `extra_rule[2]`/`[3]`) gives `winoffset0..18` =
6, 8, 10, 12, …, 40, 42 — nineteen consecutive halfwords starting at the IPv6
next-header field, covering the 16-byte source address, the 16-byte
destination address and both ports. A mis-decode could not land on the other
protocol's header fields. Evidence:
`$BENCH/logs/offload-20261116/rule-decode-evidence.txt`.

### 8.4 What this changes in the driver

Two corrections, both committed:

1. `field` is `(ZX_PP_EXTIDX_V4FAST << 4) | 0` = 0x90, not
   `(ingress << 4) | 4`, and the driver installs the ternary rule pair at
   `extra_rule[0x90]`/`[0x91]` plus `extra_index[9]` bit 0 before expecting a
   match (`rule init`).
2. The match words move: `windata0` carries the protocol, the source address
   starts at `windata1`, and the whole tuple shifts one word earlier. The
   previous layout also wrote a constant `0x10` into `window[18]`, which is
   `windata0`'s TTL byte — a match word being used as an action field.

`tests/test_pp_flow.py` pins the rule by running the driver's built entry back
through the *vendor's* winoffset/winmask decoders, so the layout is anchored
to tm.ko rather than to this driver's belief.

**Status: still a static decode.** No hardware measurement yet; the aging bit
has still never been observed set. The next step is one RAM boot with
`rule init` before the install.

---

## 9. Hardware round 3, 2026-11-16 — the first positive control, and a miss

Two more RAM boots. **Still no match.** But this round produced the control
the whole investigation was missing, which changes how every result reads.

Evidence: `$BENCH/logs/offload-20261116/rule-round/RESULTS.md`.

### 9.1 The aging table can hold a 1

```
pp-flow: aging poke 178: wrote 1, read 0x1 -> the table CAN hold a 1
```

Until now nothing had ever put a 1 in the CLA aging table on this unit: the
vendor's path is read-to-clear, this driver only ever wrote 0, and the engine
never set one. So `hit=0` was an **unfalsifiable** reading — it was equally
consistent with the table being write-only-zero, being at a different address
than believed, or not being the hit table.

It is the hit table, it is at the believed address, and it holds a 1 written
through the same accessor pair every measurement uses. Every `hit=0` in
sections 7 and 8 is therefore a real negative. That is worth more than it
sounds: it retires a whole class of "maybe we were never able to see a hit"
doubt, and it means the next person can trust the instrument.

### 9.2 What was installed and verified, and still did not match

| thing | hardware says |
|---|---|
| `extra_rule[0x90]` before | all 68 bytes zero — the gap in section 8 was real |
| `extra_rule[0x90]` after | byte-for-byte the host-computed rule |
| window at its bucket | word4 `0x33001149` — `valid_en` 1, `rule_mode` 0, field **0x90**, `windata0` = **17 (UDP)**, TTL byte 0 |
| engines | `timeouts=0`, `faulted=0` across both boots |
| traffic | `rx_packets` +41; with forwarding on, `ForwDatagrams` +30 |

With the rule present, the corrected layout stored, and all 512 inner slots
sprayed: **zero hits in every bank.**

### 9.3 Also eliminated this round

11. The missing ternary rule (installed and read back).
12. The corrected match-word layout (stored and read back).
13. `extIdx` 9 *and* `extIdx` 4 (the per-port map value for port 3), each with
    its own rule pair and its own enabled extra-index entry.
14. Every bit of the extra-index enable word, ending with all 32 set at once.
15. **A real methodology error, found mid-round:** `ip_forward` was 0, so the
    probe traffic to a routed destination was being dropped
    (`InAddrErrors`), not forwarded. Earlier rounds therefore tested less
    than they appeared to. Fixed; still zero hits.

### 9.4 Where the evidence now points

`pm_diag` holds the last frame the PM engine touched. It **updated** for
locally-originated and locally-terminated traffic on eth3, and it **did not
update** for the forwarded probe frames. The PM/CLA datapath is alive and
processing traffic, but the forwarded test tuple does not appear to reach it.

That moves the question off the CLA's table contents — which are now known
good by readback — and onto **whether the PP block is in the path of this
traffic at all**, i.e. the switch-side ingress binding: which ports are
attached to the PP pipeline, and whether the CPU-bound receive path bypasses
it. That lives in `zx279128-eth.c` and the DTS, outside the files this work
owns.

---

## 10. Hardware round 4, 2026-11-16 — the CLA IS in the ingress path

Section 9 ended pointing at "whether the PP block is in the path of this
traffic at all". **It is.** This round answers that question directly, with the
vendor's own per-block packet counters rather than the aging bit.

Evidence: `$BENCH/logs/offload-20261116/ingress-vis/MEASUREMENTS.md`.

### 10.1 The instrument: the pipeline trap counters

`tm_up_statistics_get` (tm.ko `0x51f20`) dumps a per-block packet-counter chain.
Each counter is a direct-MMIO register at `fpga_word*4 + 0x92000000`, so it is
readable at runtime through `/proc/zx_eth_poke ... read` with **no rebuild** and
no indirect-port protocol:

| block / counter | fpga word | phys |
|---|---|---|
| SBRG `brg_rx` | 0xe2300 | 0x92388c00 |
| CLA `fwd pkts` | 0xe30f0 | 0x9238c3c0 |
| CLA `trap pkts` | 0xe30f1 | 0x9238c3c4 |
| CLA `drop pkts` | 0xe30f2 | 0x9238c3c8 |
| CLA `copy pkts` | 0xe30f6 | 0x9238c3d8 |
| PM `recv/send/fwd` | 0xe7020/2/8 | 0x9239c080/88/a0 |

These are the same counters the native-stock pipeline trace used (the
"CLA trap counts +8" line in `docs/TM-IRQ-ARCHITECTURE.md`).

### 10.2 The CLA sees and traps every GE-ingress frame, 1:1

With **no flow installed**, `CLA trap pkts` tracked injected frames exactly:

```
baseline                 0x000
+200 routed frames       0x0c8   (+200)
+200 locally-terminated  0x190   (+200)
```

and a later causality check: `0x320` → inject 50 → `0x352` (**+50 exactly**).
`cla fwd/drop/copy` stayed 0 throughout. So the classification engine **is in
the GE-port ingress datapath**: it classifies every ingress frame, finds no
installed flow, and traps it to the CPU. This retires the whole "the PP may be
bypassed on ingress" branch.

### 10.3 `pm_diag` was an egress signal, not an ingress one

Section 9.4's "`pm_diag` updates for local traffic but not forwarded probes"
was read as the PM (in series with the CLA) not seeing ingress frames. The
counters show otherwise: the **PM recv/send/fwd** counters moved ~200 only for
the **routed** round (which the CPU software-forwarded back out), and 0 for the
locally-terminated round. The PM is the **egress** rewrite/forward engine; it is
not in series ahead of the CLA on ingress. The CLA saw both classes identically
(`trap +200` each). `pm_diag` reflecting TX-side traffic is consistent and is no
longer evidence about ingress classification.

### 10.4 The exact-match specifically fails — now on a live instrument

With the flow installed, the ternary rule present, `extra_index[9]` enabled, and
all 512 inner slots sprayed, 200 matching frames gave:

```
CLA trap  0x190 -> 0x258   (+200, still trapped)
CLA fwd   0x000 -> 0x000   (never forwarded)
aging[244] = 0, stat hit = 0
```

Forcing the CLA config `0x9238c080` `0x301a → 0x3e1a` (the vendor's bits 9/10/11
from `tm_pon_pp_cla_initial`, fields 7/8/9 of `cla_set_config`) did not change
it: `trap +200`, `fwd` stays 0. So the engine runs the exact-match for every
frame and matches none. With all 512 inner slots holding the **same** window,
this cannot be a bucket/placement problem — **the key the engine derives from
the packet differs from the key the driver stores**. That is the match-word /
key-encoding gap of §8, isolated now to the comparison itself, with every
other stage (ingress binding, engine enable, table presence, placement) ruled
out by direct measurement.

`cla fwd pkts` is a strictly better hit instrument than the aging bit: it counts
matches as they happen, needs no read-to-clear, and is a single direct-MMIO
read. Future key-encoding attempts should watch `0x9238c3c0` (fwd) vs
`0x9238c3c4` (trap) per injection rather than polling `aging[bucket]`.

### 10.5 Aging index sanity

`tm_get_acl_flow_status` (`0x5e760`) reads the aging table at the bucket, at
`bucket|0x200` (`flow[8]&0x10000`), or at `(flow[4]&0x1ff)+0x400`
(`flow[0xc]&0x1000000`). `cla_get/set_acl_aging_table` reject index ≥ `0x400`,
so the table is 1024 deep and the fast-path index is the bucket itself — the
driver's `aging[244]` read was the right index all along. The off-by-0x400 is a
downstream/DS-Lite path, not the IPv4 fast path.

---

## 11. Hardware round 5, 2026-11-16 — it is not the key encoding

Section 10 narrowed the problem to "the key the engine derives disagrees with
the key the driver stores." Round 5 tested that directly and **falsified it**:
the exact-match never hits even when there is nothing to compare.

Evidence: `$BENCH/logs/offload-20261116/keyenc-bisect/FINDINGS.md`.

### 11.1 The all-masked-rule bisection

New gated pokes `rulew`/`winw` write one word of an extra_rule or window entry
in place, so a hypothesis costs a `pipe` read, not a rebuild. The decisive test:
zero every `winmask` word of the ternary rule. `winmask` bit 1 means "compare
this bit" (§8: `winmask0=0x00ff` keeps proto, drops TTL), so an all-zero winmask
compares nothing and any packet must match any sprayed slot — *if* the engine
runs the inner-hash exact-match for it.

| rule state (flow installed, all 512 slots sprayed) | cla fwd | cla trap |
|---|---|---|
| real winmask | 0 | +200 |
| winmask zeroed (compare nothing) | 0 | +200 |
| + extra_index[9] valid_en=1 and ext_mode=1 | 0 | +200 |

`cla fwd` never moved; `cla trap` counted every frame. With nothing to compare,
the stored-vs-derived key is irrelevant, so **the key encoding is not the
blocker**. Placement is not either (every slot holds the same valid window,
word4 `0x33001149`). The inner-hash exact-match is simply not engaging for these
frames — they are classified and trapped upstream of the lookup.

This also retires the extra_index flags: `index_valid` bit 0 (the vendor's, via
`tm_acl_fast_init`'s `uStack_b4 |= 1`), `valid_en` (byte 0x12 bits 5:4) and
`ext_mode` (byte 0x12 bit 0) were set together with no change.

### 11.2 The leading candidate: `trap_acl_en`, never set

Decoding `claRegTable` (28-byte entries `[id, type, word, mask, shift]`) shows
register **`0x9238c080` carries three overlaid fields**, not one:

| id | field | mask | shift | bit |
|---|---|---|---|---|
| 3 | `cla_set_config` | `0x000fffff` | 0 | 0..19 |
| 4 | **`trap_acl_en`** (`cla_set_trap_acl_en_config`) | `0x1` | 17 | **17** |
| 5 | `mac_lookup_en` (`cla_set_mac_req_ctrl_config`) | `0x1` | 11 | **11** |

Hardware read `0x301a`: **bit 17 = 0** (`trap_acl_en` OFF) and bit 11 = 0
(`mac_lookup_en` OFF). Round 5 set `0x3e1a`, which turns on bits 9/10/11
(`mac_lookup_en`), with no change — but **bit 17 (`trap_acl_en`) has never been
set on this unit.** `cla_set_trap_acl_en_config` is an *exported-but-uncalled*
symbol in every shipped module, i.e. set by a higher layer or a tool, never by
the fast-add path itself. If it is the master that lets an ACL/exact-match hit
override the default trap action, the engine would consult the hash but never
act on a hit — exactly the "classified, looked-up-or-not, always trapped"
signature of round 5. **It is the cheapest untested thing (one poke,
`0x9238c080 or 0x20000`) and the top candidate for the next session**; watch
`cla fwd` vs `cla trap`.

Correcting §11.1's earlier lead: `cla_set_external_hash_table`
(`0xf1020000 + bucket*0x40`) is **overflow only**. `aclGetAvailableHashAddr`
mode 0 (inner, buckets 0..511 across four ways) is the normal path and matches
the driver's spray banks exactly; mode 1 (external) is reached only when the
inner ways are full. A single fresh flow uses the inner path, so the empty
external table is not the blocker.

The full ranked candidate list (H1 `trap_acl_en`, H2 `local_ipv4_addr`,
H3 the DPA parse gate) is in
`$BENCH/logs/offload-20261116/keyenc-bisect/NEXT-HYPOTHESES.md`.

`rulew`/`winw`/`pipe` are committed and gated behind `flow_test_enable`; the
`$BENCH/tools/pp-keyenc-bisect.sh` harness drives the whole sequence.

---

## 12. Hardware round 6, 2026-11-16 — the CLA config register is not it either

`trap_acl_en` (bit 17 of `0x9238c080`), §11.2's leading candidate, was tested on
hardware. **Negative.**

Evidence: `$BENCH/logs/offload-20261116/trapacl-test/RESULT.md`.

| config `0x9238c080` | cla fwd | cla trap (delta) |
|---|---|---|
| `0x0000301a` (baseline) | 0 | +200 |
| `0x0002301a` (bit 17 `trap_acl_en`) | 0 | +200 |
| `0x0002381a` (+ bit 11 `mac_lookup_en`) | 0 | +200 |
| `0x000bfe1f` (all config bits + bit 17) | 0 | +200 |

The readback matched the prediction exactly — bit 17 alone gives `0x0002301a` —
so the poke is provable and `trap_acl_en` is provably set and provably inert.
`cla fwd` never moved in any combination, including every config bit set at once.

**The CLA config register `0x9238c080` is not the blocker, in any bit.** Together
with rounds 4–5 this rules out everything the CLA side can express: config,
`trap_acl_en`, `mac_lookup_en`, the ternary rule (even all-masked), the key
encoding, placement, and the extra_index flags. The exact-match miss is upstream
of all of it — the frames are classified and trapped without the inner-hash
lookup ever acting on a hit.

### What is left: the parse/forwarding gate (H3)

The only remaining structural explanation is that the engine never marks these
GE-ingress frames as **L3-flow candidates**, so the exact-match is not consulted
for them at all. That decision lives in the parse/DPA stage
(`dpa_set_protocol_pkt_aly_en` / `dpa_set_protocol_cpu_pps_en`,
`tm_pon_pp_dpa_initial`, DPA block `0x92398000`) and/or the SBRG L2-vs-L3
forwarding decision — context the OpenWrt Ethernet bring-up replays only
partially (it ports the bootloader's subset, not the vendor's full
`tm_pon_pp_initial`). This is no longer a one-poke test: it needs the DPA/parse
register map decoded and a bring-up change in `zx279128-eth.c` (outside this
work's file scope), then the same `pipe` measurement.

This is a GPON ONU packet processor; its fast path is architecturally the
UNI↔PON datapath, and "upstream" means UNI→PON. Whether a GE3→GE0 *bridged* (or
even routed) frame is ever presented to the L3 flow classifier on this silicon —
as opposed to only PON-bound traffic — is the open question, and it is a
datapath/parse question, not a CLA-table one.

---

## 13. Hardware round 7, 2026-11-16 — the DPA parse gate, and why it is not pokeable

Round 6 left the parse/DPA L3-candidate gate (H3) as the only remaining
structural explanation. Round 7 read the DPA block and tried to set it.

Evidence: `$BENCH/logs/offload-20261116/dpa-gate/RESULT.md`.

### 13.1 The DPA analysis enables are partially set, not fully

`tm_pon_pp_dpa_initial` sets `dpa_set_protocol_pkt_aly_en(0..6)` and
`dpa_set_protocol_cpu_pps_en`. Decoding `dpaRegTable` (28-byte entries), those
are: ids 0..6 → **`0x92398000` bits 6..12**, id 7 → `0x92398014` bit 0. Read on
hardware:

```
0x92398000 = 0x000010c0   bits 6,7,12 SET; bits 8,9,10,11 CLEAR
0x92398014 = 0x0000001f   bit 0 set (+ 1..4)
```

So protocol analysis is enabled for indices 0,1,6 but **not 2,3,4,5** — the
OpenWrt bring-up (or the bootloader) left four of the seven off, where the
vendor sets all seven. The missing ones are a real, specific difference and a
plausible reason the engine never treats the probe as an analysable L3 flow.

### 13.2 But the block will not take a CPU write

```
echo "0x92398000 or 0x1fc0" > /proc/zx_eth_poke
-> [92398000] 000010c0 |= 00001fc0 -> 000010c0     (UNCHANGED)
```

`cla fwd` stayed 0, `cla trap` kept counting, `eth3 rx_packets` tracked 1:1
(so the `cpu_pps_en` write produced no CPU-redirect artifact either). The write
simply did not latch.

This is **not** a wrong-address problem: the stock `0xf4000000` mapping is just
the stock kernel's virtual view of the same physical datapath (WIFI-JOURNAL:
`0xf4000000` → phys `0x92000000`), and `tmOnuRegWrite` is a plain
`fpga_read_reg`/`fpga_write_reg` RMW with no command protocol — it writes the
exact physical address the poke wrote. The bits do not accept a CPU write under
our image while they presumably do under the vendor's. The difference is block
**state**: the DPA block is in a different clock/enable/reset state under the
partial bring-up than under the vendor's full `tm_pon_pp_initial`, so its config
latches are frozen — the same "PP-range config writes are dropped / runtime
state maintained by hardware" behaviour `zx279128-eth.c` already documents.

### 13.3 Where this leaves it

Every CLA-table and CLA-config avenue is exhausted and measured. The miss is
upstream, in the parse/forwarding stage, and that stage's config does not accept
runtime pokes — it has to be programmed by the Ethernet **bring-up**, in the
right order relative to the PP clock/enable, as the vendor's `tm_pon_pp_initial`
does. Concretely, the bring-up is missing the DPA init (`protocol_pkt_aly_en`
for all seven protocols, `protocol_cpu_pps_en`, and the `dpa_set_tpid_i_sel_i`
grid) and likely the rest of `tm_pon_pp_initial` (SADM, the full CLA/BRG init)
that establishes the context in which a GE-ingress frame becomes an L3-flow
candidate. That is `zx279128-eth.c` and the `zx_ponreg` write path — **outside
this work's file scope** — so it is specified here rather than attempted:

- DPA: `0x92398000 |= 0x1fc0` (protocol_pkt_aly_en 0..6), `0x92398014 |= 1`
  (protocol_cpu_pps_en), written through whatever path the block accepts during
  bring-up; plus the TPID-select grid.
- This must run where the vendor runs it in `tm_pon_pp_initial`, after the PP
  pulse and with the table bases programmed, since a post-boot poke is refused.

The CLA-side instrument (`pipe`: `cla fwd` vs `cla trap`) stays the right
measurement for whoever lands that bring-up change: a correct parse gate should
flip frames from `trap` to `fwd` by the same count.

---

## 14. Hardware round 8, 2026-11-16 — the DPA write does not latch in bring-up either

§13 proposed programming the DPA `protocol_pkt_aly_en` enables during PP
bring-up, where the block might accept them, since a runtime poke was refused.
Round 8 built that (branch `agent/dpa-init`, gated by `CONFIG_ZX279128_PP_TABLES`)
and booted it. **The bring-up write does not latch either.**

Evidence: `$BENCH/logs/offload-20261116/dpa-boot/RESULT.md`.

### 14.1 The latch check, at bring-up time

```
zx-eth: dpa pkt_aly_en 000010c0 -> 000010c0 (want bits 6..12), cpu_pps_en 0000001f -> 0000001f
zx-eth: dpa pkt_aly_en did not latch (000010c0 & 0x1fc0 != 0x1fc0) - ordering wrong
zx-eth: packet processor bring-up done
```

`writel(0x000010c0 | 0x1fc0, dpa+0x000)` left `0x92398000` at `0x000010c0`,
UNCHANGED, immediately after the `PP+0x00 = 2; udelay(1000)` pulse that resets
the block. The readback `pr_warn` fired as designed (a silent no-op is the
failure mode that got us here). Flow installed + sprayed, 200 frames: `cla fwd=0,
trap=200, rx=200` — no match, no artifact.

So it is **not** a timing/ordering problem. The register at `0x92398000` does not
accept a plain CPU `writel` in any state reachable from the Ethernet driver.

### 14.2 It is a sub-block property, not a write-path bug

The asymmetry is the key fact. The CLA **config** register `0x9238c080` accepts
writes both at bring-up (`writel` at the existing line) and at runtime (rounds
5/6 latched `0x301a -> 0x3e1a`). The DPA register `0x92398000` accepts **neither**.

And it is not that the vendor uses a cleverer write: `fpga_write_reg` in
`zx_ponreg.ko` decodes (20 bytes) to a plain `str r1, [r3, r0, lsl #2]` —
`*(base + word*4) = value`, where `base` is the module's mapping of the datapath
(reads via `fpga_read_reg`, the symmetric `ldr`, work at `0x92000000 + word*4`,
which is where our counter reads already succeed). So the vendor's DPA write is
the *same MMIO store* our `writel` performs. If ours does not latch, the bits
need a **precondition the write itself does not provide** — most plausibly the
DPA sub-block's own clock/enable, established by the parts of `tm_pon_pp_initial`
(and the TOPCRM clock/reset domain) that the OpenWrt bring-up does not run.

### 14.3 Where this leaves the whole investigation

The answer to the original question stands and is stronger than ever: the PP/CLA
block sees every GE ingress frame (§10), and the exact-match never acts on a hit
because the frame is never made an L3-flow candidate — a parse/DPA-stage gate.
That gate's register is present and half-configured (`0x92398000 = 0x10c0`, four
of seven protocol-analysis enables missing) but **it does not accept the enabling
write** from a partially-brought-up datapath, at boot or at runtime. Closing it
needs the DPA sub-block brought fully up — its clock/enable and the rest of the
vendor's `tm_pon_pp_initial` — before the enables are written, which is a
datapath/clock bring-up effort spanning `zx279128-eth.c` and the CRM/TOPCRM
clock-reset domain, not a CLA-table or a single-register change.

The `agent/dpa-init` branch is kept as the instrument: the latch check will tell
whoever brings the DPA block up whether the enables finally stick, and `pipe`
(`cla fwd` vs `cla trap`) will tell them whether that flips the match. It should
**not** be merged as-is — it is a proven no-op whose only current value is the
loud warning that the write did not take.

---

## 15. The TOPCRM gate for the datapath, decoded — 2026-11-16

§14 concluded the DPA sub-block needs a clock/enable precondition the write does
not provide. This decodes where that precondition lives.

Evidence: `$BENCH/logs/offload-20261116/crm-gate/RESULT.md`.

### 15.1 The only datapath clock-gate the platform module sets (measured)

`plat-zxylzb_9128S.ko` references `top_crm_base` at exactly three code sites
(full ARM decode of the three functions):

| function | op | meaning |
|---|---|---|
| `ref_clk_set` | `TOPCRM+0x50 &= ~0x2` | reference-clock mode (bit 1) |
| `zx_pon_clk_reset_init` | `TOPCRM+0x8` clear then set bits 4,5 | a **reset pulse** |
| `zx_pon_clk_reset` | `TOPCRM+0xc |= 0x1e` | **gate enable, bits 1..4** |

`init_module` order (measured): `pon_reset → tm_pon_tm_init → tm_pon_pp_init →
tm_pon_npp_init → zx_pon_clk_reset`. So the `TOPCRM+0xc |= 0x1e` gate is the
**last** step, after the PP/NPP block inits. It is the only clock-gate enable the
module performs; `TOPCRM+0x8` is a reset register. One gate register means CLA
and DPA share this gate domain (inferred from there being a single gate write).

### 15.2 On our boot the gate is clear, and the VENDOR sets it, not U-Boot (measured)

```
TOPCRM+0x8  = 0x1e06ffff   (reset bits 4,5 set -> out of reset)
TOPCRM+0xc  = 0x00517800   bits 1..4 CLEAR  <- zx_pon_clk_reset never ran
```

So U-Boot/OpenWrt leaves `TOPCRM+0xc` bits 1..4 clear; the vendor sets them in
`zx_pon_clk_reset` at the end of its module init. **This is a real, specific,
measured difference** and it is the same mechanism round 70 saw ("the register
does not accept the write, so the PP block is not clocked or not out of reset").

### 15.3 But setting it did not unblock the DPA — and why I stopped

```
0x9400000c 00517800 |= 0x1e -> 00517810   (only bit 4 latched; bits 1,2,3 did NOT)
0x92398000 000010c0 |= 0x1fc0 -> 000010c0 (DPA still refuses the write)
```

Bit 4 of `TOPCRM+0xc` is writable; bits 1-3 are not in this state; and bit 4
alone did not make the DPA enable register take its write. Two live
possibilities, not yet distinguished:

- (a) the full gate needs bits 1-3, which need the vendor's **reset ordering**
  (`TOPCRM+0x8` pulse) applied first — which I did **not** attempt, because
  `TOPCRM+0x8` is the reset register and pulsing datapath reset on a live,
  bootloader-initialised datapath is exactly what rounds 49/71 found harmful and
  the hazard rule forbids; or
- (b) the DPA bits 8-11 are not clock-gated but need a DPA-internal precondition
  (e.g. the `dpa_set_tpid_i_sel_i` protocol-type grid the vendor writes before
  the enables). Note bits 6,7,12 of `0x92398000` ARE set on our boot, so the
  register is not globally frozen — which mildly favours (b).

### 15.4 Risk (as asked)

Enabling `TOPCRM+0xc` bits 1-4 is the safe direction in principle: `orr`-only,
the vendor's exact op, enabling a clock rather than gating one. Bit 4 latched
with no observable harm (board up, RX unaffected). The danger is any write to
`TOPCRM+0x8` (reset): pulsing datapath reset on a live datapath is the known
hang. **If the full gate needs the reset ordering, it must be done at cold
bring-up — before U-Boot configures the datapath — not on a warm TFTP boot.**
So the clean place for this is the cold-init path in `zx279128-eth.c`, gated,
with the gate taken as a proper clock from the new `zte,zx279128s-crm` provider
rather than a blind poke; and it should be qualified on a cold boot, not warm.

### 15.5 The full cold sequence (static, resolves toward (a))

`zx_pon_clk_reset_init` contains the gate with its reset ordering. Complete
ordered TOPCRM ops (`r6` = `top_crm_base`; serdes ops on `pon_serdes_base`, the
PON optics, omitted — almost certainly not needed for GE-only):

```
1. TOPCRM+0x8 &= ~0x20     assert reset, bit 5
2. TOPCRM+0x8 &= ~0x10     assert reset, bit 4
3. delay
4. TOPCRM+0x8 |= 0x20      deassert bit 5
     [serdes: pon_serdes_base +0x44/+0x40/+0x10 — PON optics, skippable for GE]
5. TOPCRM+0x8 |= 0x10      deassert bit 4
6. TOPCRM+0xc |= 0x1e      GATE enable bits 1-4  (AFTER the reset pulse)
```

So the gate bits 1-4 are armed only after a full clear→delay→set pulse on
`TOPCRM+0x8` bits 4,5. On our boot those bits are already set (U-Boot deasserted)
but WITHOUT the pulse, and `+0xc` bits 1-4 are clear — which is exactly why bits
1-3 did not latch warm. This favours interpretation (a): the gate needs the reset
ordering, and that ordering cannot be done warm.

The fix is the bounded sequence above in the COLD bring-up path of
`zx279128-eth.c`, with `+0xc` modelled as a clock from `zte,zx279128s-crm`, then
the DPA enables, then re-measure with `pipe`. Qualify on a COLD boot only; the
`+0x8` reset writes must never run on a warm TFTP boot (rounds 49/71's hang).

---

## 16. Owner decision required: hardware offload needs a datapath reset

This section is addressed to the owner, because the last step of this
investigation runs into a rule that is yours and that I am not going to
override on my own authority.

### Where the offload stands

Everything on the CLA side is now proven or eliminated by measurement, not by
argument:

- The CLA **is** in the GE ingress path. Its trap counter increments 1:1 with
  injected frames, so every ingress frame is classified and unmatched ones trap
  to the CPU.
- The key encoding, the placement, the `extra_index` flags, the ternary rule
  (even with every mask zeroed), the config register and `trap_acl_en` are all
  ruled out, each by its own hardware measurement (§§7-12).
- The blocker is that a frame is never made an **L3-flow candidate**, because
  the DPA `protocol_pkt_aly_en` enables are only half set — four of the seven
  protocols are off, against the vendor's all-seven (§13).

### Why it cannot be fixed the obvious way

The DPA register `0x92398000` refuses the write at runtime **and** during
bring-up. `fpga_write_reg` in `zx_ponreg.ko` was decoded and is a plain MMIO
store, so the vendor is not using a cleverer write path — the sub-block is
simply not in a state to accept configuration.

The reason is `TOPCRM+0xc` bits 1..4, the datapath gate. The vendor sets it in
`zx_pon_clk_reset` as the **last** step of its module init. On this board it
reads `0x00517800` — **bits 1..4 clear**. U-Boot and this port never run that
step, so the gate has never been armed.

Arming it requires a pulse on `TOPCRM+0x8` bits 4 and 5 first: clear, delay,
set. Only then do the `+0xc` gate bits take effect. Measured warm, only bit 4
latched and the DPA write still refused, which is consistent with the pulse
being the missing precondition (§15.5 has the exact sequence).

### The conflict, stated accurately

**`TOPCRM+0x8` is a datapath reset register**, and the standing rule for this
project is: *never gate or reset the PP block.* But that rule is stricter than
the measurements behind it, and the difference matters, so it is worth writing
down properly rather than quoting.

**What is actually evidenced.** The handoff's hazard line reads: *"An access to
the PP/CLA window with its clock gated has hung the board. Never gate or reset
the PP block. The eth bring-up must run first."* The measurement there is the
first sentence: an access to an **unclocked** block never returns and the CPU
stalls. That is a real, general hazard and it is why the bring-up has to run
before anything touches the window.

**What was retracted.** The reset half came from round 49, and round 71
explicitly corrected it (`ETHERNET-JOURNAL.md`):

> Round 49 bisected the datapath reset (`0x92000008`) as "destructive" and
> removed it. That bisection forced our init to run on a **TFTP boot** — i.e. on
> a datapath the bootloader had already brought up and was actively using.
> Resetting a live datapath is obviously harmful and says nothing about the cold
> case, which is the only case where this init actually runs. Re-enabled for
> cold boots and verified: TX is unaffected.

So: **the reset is harmful on a warm boot against a live datapath, and was
measured safe from cold.** The rule generalises the warm finding to all cases.
An earlier draft of this section said the reset was "the operation behind the
hangs in rounds 49 and 71" — that is wrong, and the journal says so.

**What is genuinely dangerous about a PP reset, and remains true.** Not the
reset itself but what the tables point at afterwards. From the handoff:
*"Program the table bases before any operation that could walk the DRAM tables.
At reset they point outside DRAM (0x56409000 and 0x5f600000)."* A reset returns
the bases to garbage physical pointers, and an engine that walks them is the
real hazard. That is addressable — reprogram the bases immediately after the
reset, before anything can walk them — but it has to be designed for, not
assumed away.

**One correction to round 71 while we are here.** It concluded *"the packet
processor is not held in reset or clock-gated by topcrm"* from `0x94000000`
being identical on a cold flash boot and a working TFTP boot. Both of those are
*our* boots, and both leave `TOPCRM+0xc` bits 1..4 clear. It had no vendor
baseline, so it could not see that the vendor sets them and we never do. That
conclusion is overreaching, and §15 supersedes it.

### The owner has authorised it, 2026-11-16

**The owner has explicitly lifted the "never gate or reset the PP block" rule
for this work: hardware offload is wanted, and the reset is permitted.** That
supersedes the caution below and in the handoff. The constraints that survive
are the ones with evidence behind them:

- **Never gate a clock and then touch the window.** That is the hang that is
  actually measured. The bring-up runs first, always.
- **Program the table bases immediately after any reset**, before anything can
  walk them — at reset they point at `0x56409000` and `0x5f600000`, which is
  outside DRAM.
- **Cold boot only.** Never on a warm boot against a live datapath; that is the
  case round 49 actually measured and round 71 did not retract.

The vendor performs this reset-then-gate sequence on every cold boot of every
unit, which is the strongest argument that it is safe in the case it runs in.

### Is it a boundary?

It was treated as one. With the owner's authorisation it is a
**cold-boot-only engineering task** with a known hazard (the table bases) and a
known cost (several recoverable bad cold boots while the serdes interleave and
delays are pinned down).

It is a **cold-boot-only** change, not a forbidden one. What is forbidden and
stays forbidden is gating a clock and then touching the window, and pulsing the
reset on a warm boot. The vendor does exactly this reset-then-gate sequence on
every cold boot of every unit, which is the strongest possible argument that it
is safe in the case it would actually run in.

What I am not able to do is promise it works first time: the serdes interleave
and delays are inferred, so it would take several recoverable cold boots to get
right, and each one is a board that does not route until it is power-cycled.

### What it would cost and buy

- **Buy:** hardware flow offload, which is the remaining acceleration step
  beyond what the port already has.
- **Cost:** a datapath reset re-ordered into the cold bring-up, on a board
  whose bring-up was written against a U-Boot-initialised datapath and which
  currently routes at 358/304 Mbit/s with software flow offload at 399/380.
- **Risk, stated precisely.** Not "bricks the unit": nothing writes flash, so
  the worst case is a datapath that comes up wrong and does not route until a
  power cycle back to the working NAND image. The risk is to the *session*, not
  to the device. But it would be repeated: the serdes interleave, the delays,
  and whether the GE path needs the PON-optics steps at all are inferred, so
  getting a cold reset and reinit right would take several recoverable bad cold
  boots on a UART-only board. Confidence in first-boot success is moderate, not
  high. And the cold-boot path is the one thing in this port that has never
  been wrong and must not start being wrong.

### My recommendation

**Do not do it, unless hardware offload is worth a datapath reset to you.**

The honest arithmetic: software flow offload already gives 399/380 Mbit/s
against 358/304 plain, and the hardware path would have to beat that by enough
to justify re-ordering the reset and gate sequence of a working router. On the
evidence so far we cannot even promise it will beat software offload, because
the CLA path has never carried a single frame.

If you do want it, the work is bounded and fully specified: `TOPCRM+0x8` pulse,
then `TOPCRM+0xc |= 0x1e` modelled as a clock from `zte,zx279128s-crm`, then
the DPA enables, then re-measure with the `pipe` instrument. It must be
qualified on **cold boots only**, and it must never run on a warm boot.

What would change my mind: a measurement showing the hardware path is worth
materially more than 399/380. Nothing so far suggests it is, and I would rather
say that than spend the board's reliability finding out.

The right thing to do with this path is therefore to **leave it exactly where
it is** — fully characterised, with the `pipe` instrument and the branch
preserved — so it can be picked up if the calculus changes: a multi-core
datapath, or a need to free the CPU rather than to win raw Mbit/s. The work is
not wasted; it is a decoded, measured, ready-to-finish feature whose remaining
step is one the owner has to authorise.

**Nothing has been written to `TOPCRM+0x8`, and no gate has been armed.**

---

## 17. The cold TOPCRM reset+gate+DPA sequence — implemented, 2026-11-16

The owner lifted the "never gate or reset the PP block" rule for this work
(§16). This section records the implementation that acts on §15.5's decoded
sequence. It is written before the hardware measurement; the measured result is
appended at the end, and everything above the measurement line is either source
fact or explicitly-labelled inference.

### 17.1 What was written (source fact)

In `zx_eth_datapath_init()` in `zx279128-eth.c`, inside the existing PP
bring-up block, immediately **after** the PP command pulse (`PP+0x00 = 2;
udelay(1000)`) and **before** the SBRG/CLA config writes, gated by
`#ifdef CONFIG_ZX279128_PP_TABLES`:

1. Read `TOPCRM+0x8` and `+0xc` (before values).
2. Reset pulse on `TOPCRM+0x8`: clear bit 5, clear bit 4, `mdelay(10)`, set bit
   5, set bit 4. Discrete sub-steps matching the `plat-zxylzb_9128S.ko` decode,
   with the serdes interleave point marked and **skipped** (PON optics).
3. Arm the gate: `TOPCRM+0xc |= 0x1e` (bits 1..4), `orr`-only, after the pulse.
4. **Park the table bases** (§16 hazard): `PonPp+0x20` (PM) and `PonPp+0x24`
   (ACL) `= ze->ddr_phys`, so that with the gate now armed no engine can walk
   the reset-garbage pointers (`0x56409000`/`0x5f600000`, outside DRAM) before
   `zx_pp_tables_init()` later reprograms them to the real allocated tables.
5. DPA enables: `0x92398000 |= 0x1fc0` (protocol_pkt_aly_en 0..6), `0x92398014
   |= 1` (protocol_cpu_pps_en).
6. Read back `+0x8`, `+0xc`, both bases, `0x92398000`, `0x92398014` (after
   values), log all three before→after pairs, and `pr_warn` loudly if the gate
   did not fully arm, or either DPA enable did not latch. A silent no-op is the
   failure mode §14 was built to catch; the warning is deliberate.

It is **cold-only by construction**: `zx_eth_datapath_init()` runs only at
probe; the debug warm-attach path (`goto warm`) never reaches it, so a warm
TFTP boot against a live datapath — the rounds 49/71 hang — cannot execute any
`TOPCRM+0x8` write. It is gated by `CONFIG_ZX279128_PP_TABLES`, so a release
image's bring-up is byte-identical (the symbol is off in the shipped config).

### 17.2 Why raw `writel`, not a clk from `zte,zx279128s-crm` (decision)

The task offered the clock-framework shape with a raw-`writel` fallback. I chose
the fallback, for four reasons grounded in `clk-zx279128-crm.c` and its test:

- **Contract violation.** That driver's entire safety argument is "every gate
  here is on at boot, so every gate is `CLK_IS_CRITICAL`." `TOPCRM+0xc` bits
  1..4 read **clear** at boot (`0x00517800`, §15.2). A normally-off gate cannot
  be a critical always-on clock without contradicting the tested contract.
- **The clock core cannot express the ordering.** §15.3 measured that the gate
  bits only latch *after* the `TOPCRM+0x8` pulse. A gate is enabled at
  registration (critical) or at `clk_prepare_enable`, with no ordering relative
  to an external pulse the eth driver drives. That ordering is the whole point.
- **Wrong domain / frozen test.** Every field in that driver is a stock LSP0/
  LSP1 peripheral gate or a PCIe reset, decoded from the stock vmlinux clock
  tables; `tests/test_crm_clocks.py` asserts an exact frozen set of 9 clocks / 2
  resets against the replaced driver. `TOPCRM+0x8`/`+0xc` datapath bits come
  from a different module (`plat-zxylzb_9128S.ko`) and a different (PON
  datapath) domain; adding them would break that test and mix domains.
- **It is one ordered sequence across three blocks** (`+0x8` pulse → `+0xc`
  gate → DPA) with delays, interleaved with the existing PP pulse. A
  straight-line, loudly-instrumented inline block is the reviewable shape for
  the several recoverable cold boots the tuning will take.

### 17.3 What is inferred, not measured (to be pinned on the bench)

- The **`mdelay(10)`** between assert and deassert. The vendor's nearby resets
  use `mdelay(10)`; the exact datapath-reset settle time is not pinned.
- **Skipping the serdes writes** (`pon_serdes_base +0x44/+0x40/+0x10`). Those
  are the PON optical-transceiver SERDES; a GE-only path (eth3→eth0) should not
  need them. If `TOPCRM+0x8` bits 4,5 also gate something the GE path needs, GE
  TX/RX dies visibly and recovers on a power cycle — a recoverable, measurable
  outcome distinct from a DPA-latch failure.
- Whether arming the gate is **sufficient** for the DPA write to latch. §15.3
  left two live possibilities: (a) the gate needs the full reset ordering, or
  (b) the DPA bits need a DPA-internal precondition (e.g. the
  `dpa_set_tpid_i_sel_i` grid). This sequence tests (a). The readback warnings
  distinguish the outcomes.

### 17.4 Measured result — cold RAM boot, 2026-11-16 (image `cold-dpa-gate-1`)

**The sequence ran cold, exactly as written, and did not unblock the DPA. No
match.** The gate bits 1..3 refuse the write even cold, with the reset pulse
applied first — reproducing §15.3's warm result in the cold case the owner
authorised. Evidence below is all measured (boot `pr_info` + live `/proc/
zx_eth_poke`), on one unit, RAM boot of the `BOOT_PROFILE=diagnostic BRINGUP=1
PP_TABLES=1 PP_FLOW_TEST=1` image.

**Boot-time before→after (the sequence's own readback, `t≈0.93s`):**

```
topcrm reset +8 10061fff -> 10061fff
topcrm gate  +c 00517800 -> 00517810   bits 1..4 wanted; ONLY bit 4 latched
pp table bases parked at ddr 41000000: pm +20=41000000 acl +24=41000000
dpa pkt_aly_en 000010c0 -> 000010c0    |0x1fc0 wanted; DID NOT latch
dpa cpu_pps_en 0000001f -> 0000001f    bit 0 already set
WARN: topcrm gate did not fully arm (00517810 & 0x1e != 0x1e)
WARN: dpa pkt_aly_en did not latch (000010c0 & 0x1fc0 != 0x1fc0)
```

The loud warnings fired as designed — a silent no-op (the §14 failure mode) did
not happen; the failure is visible and precise.

**The §16 hazard mitigation worked.** Bases were parked at `0x41000000` right
after the gate write, and `zx_pp_tables_init()` later reprogrammed them to the
real allocated tables (`pp: tables live, pm 0x42600000 acl 0x43000000 (were
0x41000000 0x41000000)`). No engine ever saw the reset-garbage pointers.

**Live poke, post-boot, confirms the block is stuck, not mistimed:**

- `TOPCRM+0x8` accepts bit-5 clear/set (`1e06ffff → 1e06ffdf → 1e06ffff`) — the
  reset register is writable; the pulse mechanism is not the problem.
- `TOPCRM+0xc |= 0x1e` → stays `0x00517810`. Each of bits 1, 2, 3 written
  **individually** also refuses (`00517810 |= 0x2/0x4/0x8` all → `00517810`).
  Bit 4 is writable; bits 1..3 are not, in any state reachable here.
- A full live clear→clear→set→set pulse on `+0x8` bits 4,5 immediately before
  `+0xc |= 0x1e` still leaves bits 1..3 clear.
- `0x92398000 |= 0x1fc0` live → stays `0x000010c0`. The DPA still refuses the
  enable while the gate is not fully armed — the §13/§14/§15.3 behaviour, now
  also measured cold.

**CLA instrument + match test (`pipe`, `cla fwd` vs `cla trap`):**

| step | cla fwd | cla trap | eth3 rx_packets |
|---|---|---|---|
| baseline, no flow | 0 | 0 | 0 |
| inject 20, no flow | 0 | **20** | 20 |
| `addh` flow id 1 (sel 2 bucket 244), `spray 0` (256 sel-2 slots), inject 20 | **0** | **40** | 40 |

The CLA classifies every GE ingress frame and traps the unmatched ones 1:1
(baseline control reproduces §10). With the flow installed and sprayed, the
second 20 frames still trap 1:1 (`trap` 20→40), `cla fwd` stays 0, and every
frame still reaches the CPU (`eth3 rx_packets` 20→40). **No frame was ever made
an L3-flow candidate**, because the DPA enable never latched, because the gate
never armed — the exact causal chain §16 predicted.

### 17.5 Anomaly worth recording

The sequence read `TOPCRM+0x8 = 0x10061fff` at `t=0.93s`; the resting value
measured live (`t≈61s`) is `0x1e06ffff` (xor `0x0e00e000`, bits 27..25 and
15..13). So `+0x8` is still being driven by *later* bring-up after
`zx_eth_datapath_init` returns — my pulse ran while the register was in a
transient state, not its final one. Whether that matters to the gate is not
established; it is logged because it means the "before" I pulsed from was not
the stable `0x1e06ffff` the handoff quoted.

### 17.6 What still blocks it, and what I would do next

The gate bits 1..3 are gated behind a precondition the `+0x8` bits-4,5 pulse and
the `+0xc` orr do not provide — measured cold, measured live, measured
per-bit. The one vendor step in `zx_pon_clk_reset_init` I deliberately did
**not** reproduce is the **serdes interleave** on `pon_serdes_base`
(`+0x44/+0x40/+0x10`), which the vendor issues *between* the deassert of bit 5
and bit 4. I skipped it (PON optics, argued unnecessary for GE); this result
removes that as a safe assumption — it is now the leading unmet precondition.

Next, in order, each bounded:

1. **Recover `pon_serdes_base`.** It is not in the decoded materials (§15.5
   omitted it as "a different base"). It needs a decode of
   `zx_pon_clk_reset_init` in `plat-zxylzb_9128S.ko` (not loaded in the Ghidra
   session, which has only `tm.ko`). With the base and the three writes, add the
   serdes interleave to the sequence at its marked point and re-measure the gate
   arm + DPA latch.
2. **Pin the `+0x8` transient.** Find what sets `+0x8` bits 27..25/15..13 after
   `zx_eth_datapath_init` and whether the pulse must run after it, so the pulse
   starts from `0x1e06ffff` not `0x10061fff`.
3. If bits 1..3 still refuse with the serdes writes in, they are likely
   **status/strap** bits, not gate-enable bits — i.e. the datapath clock is
   gated by a different field, and the `+0xc |= 0x1e` decode (or its meaning on
   this SoC vs the vendor's) is wrong. That would reopen §15.1's "one gate
   write" inference.

The `pipe` instrument and this image are the measurement for all three; a
correct precondition flips `cla trap` to `cla fwd` by the injected count.

## 18. The gate mask was mis-decoded — it is 0x1e0, not 0x1e — 2026-11-17

§17 ran the §15.5 sequence exactly and the gate refused to arm; §17.6 nominated
the skipped serdes interleave as the leading unmet precondition. That inference
is **wrong**, and this section corrects it with a measured decode of
`plat-zxylzb_9128S.ko` (loaded here via the OpenWrt ARM toolchain `objdump`;
`zx_pon_clk_reset` and `zx_pon_clk_reset_init` are both present, not stripped).

### 18.1 The measured defect (source fact)

Both gate writes — `zx_pon_clk_reset` (`0xc0a0`) and the tail of
`zx_pon_clk_reset_init` (`0xc04c`) — are the **same ARM instruction**:

```
c04c:  e3833e1e   orr r3, r3, #480  @ 0x1e0      (objdump's own comment)
c0a0:  e3822e1e   orr r2, r2, #480  @ 0x1e0
```

`e3833e1e` is a data-processing immediate: imm8 = `0x1e`, rotate field = `0xe`,
so the actual operand is `0x1e ROR (2*0xe=28) = 0x1e0`. **The gate is
`TOPCRM+0xc |= 0x1e0`, bits 5..8 — not `|= 0x1e`, bits 1..4.** §15.1's decode
read the raw imm8 (`0x1e`) and dropped the barrel-shifter rotation; every
section after it inherited the error.

### 18.2 Why this explains every §17.4 negative exactly

`TOPCRM+0xc` resting `0x00517800`; `& 0x1e0 = 0` (gate genuinely clear). The old
code wrote `|= 0x1e` and measured `00517800 -> 00517810`:

- **bit 4** (`0x10`) latched — it is a writable bit, but it is **not a gate
  enable**; it sits below the real gate field. Its latching was a red herring.
- **bits 1..3** (`0x0e`) refused, warm and cold, individually — because they are
  read-only strap/status bits, not gate bits. §17.4's per-bit live pokes were
  measuring the wrong bits the whole time.
- the **real gate bits 5..8** were never written, so the DPA stayed gated and
  `0x92398000 |= 0x1fc0` never latched. §17.4's entire causal chain is intact;
  only the mask constant was wrong.

`00517800 | 0x1e0 = 0x005179e0` is the wanted post-arm value.

### 18.3 `pon_serdes_base` recovered (as asked), and why it stays skipped

Recovered by decode, not assumed: `init_module` matches the
`zte,zx279128s-pon` node and calls `of_iomap` five times, storing the results
at consecutive struct offsets that are the exported globals in `.bss` order —
`pon_base` (reg 0), `top_crm_base` (reg 1), `sys_ctrl_base` (reg 2),
`pin_mux_base` (reg 3), **`pon_serdes_base` (reg 4)**. So `pon_serdes_base` is
**`of_iomap(pon node, reg index 4)`** — a DT-derived virtual base, not a fixed
literal; its physical address lives in the vendor DT's `pon` node `reg[4]`,
which is not present in our in-tree materials (we have no vendor DTB; U-Boot
drives npp/tm/pp but not the serdes).

The three writes in `zx_pon_clk_reset_init`, between deassert-bit-5 and
deassert-bit-4:

| off | op (measured) | meaning (inferred) |
|---|---|---|
| poll | `ldr [+0x68]; tst #0x10; beq` (spin, no timeout) | wait serdes ready |
| `+0x44` | `bic #0x3f0000; orr (temp_code<<16)` | TX-bias temp trim, 6 bits 21..16, from `temp_ctrl_read`/`ubfx #18,#6` |
| `+0x40` | `orr #0x04000000` | enable bit 26 |
| poll | `ldr [+0x70]; tst #0x1000000; bne` (20 tries) | PRBS/rx-ready |

These are the **GPON optical-transceiver** SERDES bring-up (temperature-
compensated TX bias + a ready handshake). Two measured reasons they stay out of
the GE-only cold path: (1) §18.1 shows the mask error, not a missing serdes
write, caused the §17.4 negative — "change one thing" says fix the mask alone
and re-measure; (2) the first poll (`+0x68 & 0x10`) has **no timeout**, so with
no optical module on this unit it would hang the cold boot outright. If the
corrected mask still leaves the DPA gated, the serdes interleave is the next
thing to add — but only with a bounded poll.

### 18.4 The `+0x8` transient (§17.5), resolved as not-the-blocker

§17.5 flagged that the pulse ran from `0x10061fff` while the resting value is
`0x1e06ffff`. With §18.1 in hand this is a non-issue for the gate: the pulse
only ever touches bits 4,5 (`0x30`), and both the transient `0x10061fff` and the
resting `0x1e06ffff` have bits 4,5 = **1** (`...1f` low nibble), so the pulse
clears-then-sets the same two bits from the same starting state either way. The
upper-bit drift (bits 27..25/15..13) is unrelated to the `0x30` reset field. It
is logged but does not gate; no reorder is needed.

### 18.5 What was changed in the port

`zx279128-eth.c`: `ZX_TOPCRM_GATE_BITS` `0x1e -> 0x1e0`, comments/log/warn
strings updated to "bits 5..8 (0x1e0)". Nothing else in the sequence moved: the
pulse, the §16 base-park (kept exactly in place), and the DPA enables are
unchanged. Gated by `CONFIG_ZX279128_PP_TABLES` (off in the shipped config), so
release bring-up is byte-identical. `git grep` confirms `0x1e0` is the only gate
constant; the DPA mask `0x1fc0` (bits 6..12, seven protocols) is unchanged and
was never in question.

### 18.6 MEASURED RESULT — cold RAM boot, 2026-11-17 (image `gate-mask-1e0`)

**The corrected gate mask (0x1e0) now arms the gate fully, cold. The DPA still
refuses its enable. No match.** Everything below is measured on one unit, cold
RAM boot of the `BOOT_PROFILE=diagnostic BRINGUP=1 PP_TABLES=1 PP_FLOW_TEST=1`
image, via boot `pr_info` and live `/proc/zx_eth_poke`.

**Boot-time before→after (the sequence's own readback, `t≈0.92s`):**

```
topcrm reset +8 10061fff -> 10061fff
topcrm gate  +c 00517800 -> 005179e0   bits 5..8 wanted; ALL FOUR latched
pp table bases parked at ddr 41000000: pm +20=41000000 acl +24=41000000
dpa pkt_aly_en 000010c0 -> 000010c0    |0x1fc0 wanted; DID NOT latch
dpa cpu_pps_en 0000001f -> 0000001f    bit 0 already set
WARN: dpa pkt_aly_en did not latch (000010c0 & 0x1fc0 != 0x1fc0)
```

Note what is GONE versus §17.4: there is **no "gate did not fully arm" warning**.
`+0xc` moved `00517800 -> 005179e0`, i.e. exactly `| 0x1e0`, all of bits 5..8
set. The old `| 0x1e` image produced `00517810` (bit 4 only) and warned. §18.1's
decode is confirmed by hardware: the gate is bits 5..8 and they are writable.

**Live poke, post-boot (`t≈335s`), the register-by-register picture:**

| reg | §17.4 (mask 0x1e) | §18.6 (mask 0x1e0) | meaning |
|---|---|---|---|
| TOPCRM+0x8 | `1e06ffff` | `1e06ffff` | resting; pulse field bits 4,5 unchanged |
| TOPCRM+0xc | `00517810` | **`005179e0`** | gate now fully armed (was: bit 4 only) |
| 0x92398000 | `000010c0` | `000010c0` | DPA pkt_aly_en: still refuses `\|= 0x1fc0` |
| 0x92398014 | `0000001f` | `0000001f` | DPA cpu_pps_en: still refuses `\|= 0x20` |

The DPA register is write-LOCKED, not strap-masked: live `0x92398000 |= 0x80000000`
(a scratch high bit) also refused (`-> 000010c0`), and `0x92398014 |= 0x20`
refused too. The whole DPA config window rejects writes while reading its
reset/strap defaults. That is a frozen-sub-block signature, independent of the
specific enable bits.

**CLA instrument + match test (`pipe`, flow id 1 = sel 2 bucket 244, sprayed):**

| step | cla fwd | cla trap | eth3 rx_packets |
|---|---|---|---|
| baseline, flow+spray installed | 0 | 0 | 0 |
| inject 20 (198.51.100.2:40001 -> 192.0.2.77:40002) | **0** | **20** | 20 |

Every ingress frame still traps 1:1; `cla fwd` stays 0. No frame was made an
L3-flow candidate, because the DPA enable never latched — same terminal outcome
as §17.4, now reached with the gate provably, fully armed.

### 18.7 What this settles, and what now blocks it

**Settled (measured):**

- The §15.1 "single gate at +0xc bits 1..4" decode was wrong on the mask. The
  gate is +0xc **bits 5..8 (0x1e0)**. The §17.4 "only bit 4 latched, bits 1..3
  refuse" was the artefact of writing the wrong field: bit 4 is a writable
  non-gate bit, bits 1..3 are read-only (strap/status), and the real gate bits
  5..8 were never touched. Fixing the constant makes the gate arm completely,
  cold, with no reset-ordering or serdes write added.
- The serdes interleave is **not** the missing precondition for the gate. The
  gate arms without it. `pon_serdes_base` is recovered and documented (§18.3)
  but its writes are PON-optics-only and stay skipped (and one serdes ready-poll
  has no timeout, so adding it blindly would hang a cold boot).
- The `+0x8` transient (§17.5) is a non-issue for the gate (§18.4): the pulse
  only touches bits 4,5, set in both the transient and resting values.

**Now blocks it (measured, and this is the honest open question):** with the
clock gate fully armed the DPA config window `0x92398000`/`0x92398014` is STILL
write-locked, refusing even a scratch bit. So TOPCRM+0xc was necessary (its
decode was simply wrong before) but is **not sufficient**. This is §15.3's
interpretation (b), now isolated because the gate confound is removed: the DPA
sub-block needs a DPA-internal precondition — a soft-reset or an enable the
vendor applies through `tm.ko` (`tm_pon_pp_adm_initial` and the `adm_*` /
`tm_protocol_pkt_limit_pps_set` helpers drive this window, not raw writes), OR a
second clear step `zx_pon_clk_reset_init` does that this port does not:
**`sys_ctrl_base +0x10 &= ~0x800`** (clear bit 11), issued immediately before the
gate (init decode `c028..c054`). `sys_ctrl_base` = `of_iomap(zte,zx279128s-pon
node, reg index 2)`; its physical base is not in our in-tree materials (no vendor
DTB), so pinning it is the next bounded step — recover reg[2]'s address (vendor
DTB or U-Boot), add the `&= ~0x800`, re-measure the DPA latch. If the DPA window
stays locked after that too, the enable path is `tm.ko`-internal (adm soft-reset
/ turn-on), not a TOPCRM/sys_ctrl clock gate at all.

## 19. The DPA window is not frozen — bits 8..11 are UNIMPLEMENTED silicon — 2026-11-17

§18 closed on "the DPA config window `0x92398000` is write-LOCKED, refusing even
a scratch high bit — a frozen-sub-block signature." That conclusion is **wrong**,
and this section overturns it with a direct walking-bit measurement on hardware.
The two candidates handed to this round (sys_ctrl bit 11; a tm.ko ADM turn-on)
are both measured and both fail — but for a reason that dissolves the question
rather than answering it.

### 19.1 Candidate 1 recovered and measured — a verified no-op

`sys_ctrl_base = of_iomap(zte,zx279128s-pon, reg index 2)`, recovered exactly:
`init_module` stores the five `of_iomap` results at `[r6+0,+16,+20,+24,+28]`,
i.e. reg indices 0,1,2,3,4 → `pon_base, top_crm_base, SYS_CTRL_BASE, pin_mux_base,
pon_serdes_base`. The **vendor DTB was recovered from the flash dump**
(`h199a-flash-full-unverified-20261110.bin` @ 0x22f6a98, a valid FDT): the `pon`
node `reg` is `<0x92000000 0x400000, 0x94000000 0x100000, 0x94100000 0x100000,
0x94200000 0x100000, 0x9fe00000 0x100000>`. reg[1]=0x94000000 matches the known
`top_crm_base` (cross-check), so **reg[2] = 0x94100000** — which is CRM1.

The omitted op (`c038`): `e3c22b02 = bic r2, r2, #0x800`. Decoded by hand against
the §18 rotation trap: imm8=0x02, rot=0xb, operand = 0x02 ROR 22 = **0x800, bit 11**
(objdump prints no rotate comment because the operand is small; checked anyway).
So candidate 1 is **`0x94100010 &= ~0x800`**.

**Measured, cold RAM boot of `gate-mask-1e0` (gate armed, 0x9400000c=0x005179e0),
live `/proc/zx_eth_poke`:**

```
0x94100010 = 0x00000000     <- bit 11 ALREADY CLEAR on our boot
0x94100070 = 0x0001aab5     (CRM1 live, matches WIFI-JOURNAL - window is real)
0x94100074 = 0x0000001b     (CRM1 live)
0x94100000 = 0x00000000     (genuine zero, not an unmapped read)
```

`sys_ctrl_base +0x10` bit 11 is **already 0**. The vendor's `&= ~0x800` is a
no-op on this board. Clearing it (or confirming it clear) leaves `0x92398000`
exactly as frozen. Candidate 1 is falsified by measurement, not argument.

### 19.2 Candidate 2 (ADM turn-on) recovered and measured — writable, no effect

The ADM register is pinned by decoding `AdmRegTable` + `fpga_write_reg`:
`fpga_write_reg(idx,val)` is `*(base + idx<<2) = val` with `base = ioremap(pon)`
= 0x92000000. `AdmRegTable[0].word_index = 0xe5000` → `0xe5000*4 = 0x394000` →
**ADM = 0x92394000**, bit 0 (`adm_set_turnon_enable(1)` writes mask 0x1 shift 0).
Cross-checked the same way, `dpaRegTable` idx6 word_index 0xe6000 → **0x92398000**,
exactly the DPA register — so the table decode is sound.

**Measured live:**
```
0x92394000 = 0x00000000 ; |= 0x1 -> 0x00000001   ADM turn-on LATCHES (writable)
0x92398000 = 0x000010c0 ; |= 0x1fc0 -> 0x000010c0  DPA still "refuses"
0x92398000 |= 0x80000000 -> 0x000010c0            scratch bit still "refuses"
```

The ADM sub-block at 0x92394000 is freely writable and the turn-on bit latches,
but it does **not** change the DPA register. `tmOnuRegWrite` (the vendor's only
write path, incl. ADM and DPA) was decoded: a plain `fpga_read_reg`/`fpga_write_reg`
read-modify-write — no unlock handshake. So nothing in the vendor's write path
differs from our raw `writel`. Candidate 2 is measured-negative.

### 19.3 The real measurement — `0x92398000` implements ONLY bits 6,7,12

The §18.6 "frozen window" rested entirely on `|=` tests that cannot distinguish
"write refused" from "bit unimplemented, reads back 0." Walking-bit writes settle
it. All on the live board, gate armed, reset+ADM applied:

```
0x92398000 := 0xffffffff -> 0x000010c0     only bits 6,7,12 survive all-ones
0x92398000 := 0xaaaaaaaa -> 0x00000080     of 0xaaaaaaaa, only bit 7 implemented
0x92398000 := 0x55555555 -> 0x00001040     of 0x55555555, only bits 6,12
0x92398000 := 0x00000100 -> 0x00000000     bit 8 alone: does NOT set (and clears 6,7,12)
0x92398000 &= ~0x40      -> 0x00001080     bit 6 CLEARS cleanly (writable)
0x92398000 |= 0x40       -> 0x000010c0     bit 6 RE-SETS cleanly (writable)
0x92398000 &= ~0x80 ; |= 0x80 -> 0x10c0    bit 7 clears and re-sets cleanly
```

`0x92398000` physically implements **exactly bits 6, 7, 12** — nothing else, over
the whole 32-bit word. Writing all-ones yields `0x10c0`. Per the decoded
`dpaRegTable` (id i → bit 6+i), these are `protocol_pkt_aly_en` slots **0, 1, 6**.
Slots 2,3,4,5 (bits 8,9,10,11) are **unimplemented read-as-zero** on this SoC.

`0x92398014` (`cpu_pps_en`) is the same story: `:= 0xffffffff -> 0x0000001f`,
only bits 0..4 implemented, all already set. The §18.6 "refuses `|= 0x20`" was
bit 5 — unimplemented. The §18.6 "scratch bit `|= 0x80000000` refused" was bit 31
— also unimplemented in this register. **Both DPA registers were already at their
full hardware maximum the entire time.** There is no frozen window and never was;
there is a register that only has three protocol slots.

### 19.4 Why "the vendor sets all seven" was always a mirage

`tm_pon_pp_dpa_initial` loops `dpa_set_protocol_pkt_aly_en(i,1)` for i=0..6, i.e.
it *attempts* bits 6..12. On silicon that implements only 6,7,12, the vendor's own
writes to bits 8,9,10,11 are no-ops too — the vendor ends at `0x10c0` exactly like
us. "Four of seven protocols off" (§13, the whole premise of §13-§18) was reading
a 3-slot register against a 7-slot driver loop and calling the four missing slots
a bug. They are not configured-off; they do not exist in this part. This is the
cost-reduced GE variant (H199A / ZX279128S), not the full 7-protocol GPON SKU the
tm.ko loop was written for.

### 19.5 MEASURED match test — DPA at hardware max, still no forward

With `0x92398000 = 0x10c0` (its maximum), flow installed and sprayed exactly as
§18.6:

```
rule init                                   extra_rule[144,145], extra_index[9] 0->1
addh 3 udp 198.51.100.2:40001 192.0.2.77:40002 -> 0 ...   hashed id 1, sel 2 bucket 244, field 0x90
spray 0                                     256 slots into sel 2
pipe (baseline)                             cla fwd=0 trap=0 drop=0 copy=0
inject 20 (198.51.100.2:40001 -> 192.0.2.77:40002)
pipe (after)                                cla fwd=0 trap=20 drop=0 copy=0
eth3 rx_packets                             0 -> 20
```

`cla fwd = 0`, `cla trap = 20`, 1:1. Same terminal outcome as §18.6 — but now with
the DPA **proven to be at its implemented maximum**, so the DPA is conclusively
**not** the blocker. The frame is not made an L3-flow candidate for a reason that
is downstream of (or orthogonal to) `protocol_pkt_aly_en`, which was already fully
enabled for every slot this silicon has.

### 19.6 Register before/after (deliverable), all MEASURED

| reg | before | after (our writes) | note |
|---|---|---|---|
| `sys_ctrl_base+0x10` (0x94100010) | `00000000` | `00000000` | bit 11 already clear; `&~0x800` is a no-op |
| `TOPCRM+0xc` (0x9400000c) | `00517800` | `005179e0` | gate bits 5..8 arm (unchanged from §18) |
| `0x92398000` pkt_aly_en | `000010c0` | `000010c0` | already max: ONLY bits 6,7,12 exist |
| `0x92398014` cpu_pps_en | `0000001f` | `0000001f` | already max: ONLY bits 0..4 exist |
| `0x92394000` ADM turnon | `00000000` | `00000001` | writable, latches, no DPA effect |

Counter deltas: `cla fwd 0->0`, `cla trap 0->20`, `cla drop 0`, `cla copy 0`,
`eth3 rx_packets 0->20`, for 20 injected frames with flow id 1 installed+sprayed.

### 19.7 What is settled, what is inferred, and where this leaves offload

**Measured (hardware, one unit, cold RAM boot `gate-mask-1e0`):**
- `0x92398000` implements exactly bits 6,7,12; `0x92398014` exactly bits 0..4;
  both already hold their full implemented value. The "frozen DPA window" of
  §13-§18 does not exist; it was unimplemented bits mistaken for refused writes.
- Candidate 1 (`sys_ctrl_base+0x10 &= ~0x800`) is a no-op: bit 11 already clear.
- Candidate 2 (ADM `0x92394000` bit 0) latches but does not affect the DPA or
  forwarding.
- With the DPA at maximum, an exact-match flow still traps 1:1 (`fwd=0 trap=20`).

**Inferred:** that bits 8..11 are unimplemented *silicon* (vs. permanently
strapped off) — the walking-bit + all-ones measurement cannot tell "no flip-flop"
from "flip-flop held 0 by a strap", but either way the register is at the only
value it can hold and no software step this port could add changes it. The vendor
DTB and `init_module` decode behind candidate 1 are source-measured; whether CRM1
reg[2] is literally named "sys_ctrl" on this SKU is the vendor's label, taken as
given.

**Where offload stands:** the code change for candidate 1 is committed (an
`orr`-free, no-op-on-this-board `bic` placed exactly where the vendor issues it,
cold-only, gated by `CONFIG_ZX279128_PP_TABLES`) so the sequence matches the
vendor init byte-for-byte; it is harmless and correct, but it is **not** the
unlock, because there is nothing to unlock. The DPA is not what stops `cla fwd`.
Per the stop rule I did not open a third DPA hypothesis: the measurement says the
DPA window was a dead end from §13 onward, and the remaining blocker is in the CLA
match/action path (the exact-match never acts on a hit), which is a different
sub-block and a different investigation. **No `cla fwd` was produced; the DPA is
measured out as the cause.**

### 19.8 Authoritative bring-up readback — candidate-1 image, cold RAM boot 2026-11-17

The §19.1 "bit 11 already clear" was first measured live (post-boot poke). The
task notes a poke is not fully conclusive for a BRING-UP-time write, so the
candidate-1 code (sys_ctrl bic in its vendor-exact position, + the corrected
impl-bit warn) was built and booted. Its own `pr_info`, at t≈0.93s, is the
authoritative bring-up measurement:

```
zx-eth: sysctrl 0x94100010 00000000 -> 00000000 (want bit 11 clear, &~0x800)
zx-eth: topcrm reset +8 10061fff -> 10061fff, gate +c 00517800 -> 005179e0 (bits 5..8)
zx-eth: pp table bases parked at ddr 41000000: pm +20=41000000 acl +24=41000000
zx-eth: dpa pkt_aly_en 000010c0 -> 000010c0 (want bits 6..12), cpu_pps_en 0000001f -> 0000001f
```

- `0x94100010` is `0x00000000` BEFORE the bic, at the real bring-up instant — so
  bit 11 is clear independent of any later activity; candidate 1 is a confirmed
  no-op at bring-up, not just post-boot.
- The gate arms (`00517800 -> 005179e0`).
- The DPA is unchanged at `0x10c0` / `0x1f` (its maxima).
- **No `WARN: dpa pkt_aly_en did not latch` fired** — the corrected impl-bit
  check (`0x10c0 & 0x10c0 == 0x10c0`) correctly reports the register at its
  implemented maximum instead of false-warning on the 4 absent bits.

Match test on this same image: `rule init`, `addh` id 1 (sel 2 bucket 244),
`spray 0`, inject 20 → `cla fwd=0 trap=20 drop=0 copy=0`, `eth3 rx 0->20`.
Identical terminal outcome, DPA proven maxed and candidate 1 proven no-op at
bring-up. The DPA is measured out as the blocker; `cla fwd` stays 0 downstream.

---

## 20. The structural answer: the PP WAN-port declaration, unset on our boot — 2026-11-17

§19 measured the DPA out as the blocker and said the remaining cause is
"downstream of, or orthogonal to, `protocol_pkt_aly_en`." This section answers
the structural question the task posed — *does a GE-ingress routed frame ever
reach the L3 classifier on this part?* — and the answer is **yes, but only once
an ingress port is declared WAN**, a bring-up register our port never writes and
the vendor always does.

All findings here are static decodes of the **unstripped vendor modules**
(`tm.ko`, `switch.ko`) plus one **measured** register read already in the logs.
No new boot was needed to reach the hypothesis; a boot is needed only to confirm
the fix.

### 20.1 What `sbrg_set_pt_da_lookup_en` actually is (the named candidate)

The task named `sbrg_set_pt_da_lookup_en` (`0x9a48`). Decoded: it is SBRG
register index 44 (`0x2c`), one bit per port, the **L2 destination-MAC lookup**
enable. `tm_pon_pp_brg_initial` (`0x3edd4`) calls it for all 8 ports in its
per-port loop, alongside `pt_smac_look_en`, `unknown_unicst_fwd`, etc. It is an
L2-bridging control, **not** the L3-flow-candidate gate, and it is not a
precondition for L3 classification. So the named candidate is a red herring; the
real gate is elsewhere, found by following the direction model.

### 20.2 The vendor's model is directional, and "WAN" is a declared port

Every CLA flow path is split up/dn: `cla_set_up_l3_default_flow_cfg` (reg 30),
`cla_set_dn_l3_default_flow_cfg` (reg 32), `cla_set_up_l2_uni_default_flow_cfg`
(reg 23), `up/dn_unicast_flow_cfg`, `up/dn_mtu`. "up" = UNI→uplink, "dn" =
uplink→UNI. The switch's fast-add path (`sw_acl_l3_hardfast_session_add.part.2`,
`0x238c`) computes a direction byte = `!TO_WAN(outdev)` and the session carries
it; `TO_WAN` (`0x2270`) matches `nas*`/`ppp*`/`pon*` by name, else the ethN that
equals the configured WAN port. So the datapath is organised around **which port
is the uplink/WAN**, and that is a *software-declared* value, not fixed to PON.

### 20.3 The register: `0x923a001c`, bit (port+25)

`tm_set_pp_wan_cfg(port)` (`tm.ko 0x36094`) is a bare `fpga_read_reg` /
`fpga_write_reg` RMW on word index **`0xe8007`** → phys
`0x92000000 + 0xe8007*4 = 0x923a001c` (inside the PonPp window the driver already
maps as `ZX_REG_PONPP`), OR-ing **bit `(port+25)`**. Its only caller is
`tm_set_p2pmode` (`0x360f0`), which stores the port into the global `lan_up_port`
and passes it straight through, then calls `spa_set_port_pkt_filter`.

`switch.ko`'s `sw_other_set_wan_lan_switch` (`0x6254`) writes the **same**
register: it first **clears bits 25..29** (`bic r1, r0, #0x3e000000`), then calls
`tm_set_pp_wan_cfg` to set bit `(port+25)`. `ethdrv_set_wanportid` (`0x4a0`)
stores `g_sw_cap[0x68] = port`; the string `sw_set_uni_as_wan uni=%d` and the
vendor boot log line `si_gpon_lanup_set_db lan_up_mode=0x0 lan_up_port=4`
(`docs/zx279128s-vendor/VENDOR-ARCHAEOLOGY-R2.md`) confirm the WAN port is a
software field and a **GE/UNI port can be the WAN** — this is not a PON-only part.

So `0x923a001c` bits 25..29 are the **WAN-port bitmap**: they declare which
ingress port feeds the uplink/routed datapath, i.e. which port's frames are
candidates for the upstream L3 flow path.

### 20.4 MEASURED: our boot declares no WAN port

`logs/probe-i-pp-ddr-config.txt` (our OpenWrt image, PP-DDR config probe):

```
[923a0008] = 00000000
[923a0014] = 00000000
[923a001c] = 01200000     <- WAN-port field (bits 25..29) = 0
[923a0020] = 56409000
[923a0024] = 5f600000
```

`0x01200000` = bits 21 and 24 only; **bits 25..29 are all clear**. No ingress
port is declared WAN. This is the exact signature that ties §10–§19 together:
the CLA sees and classifies every GE-ingress frame (§10, trap 1:1), but with no
uplink port declared the parse/forwarding stage never marks a GE→GE routed frame
as an **upstream L3-flow candidate**, so the inner-hash exact-match is never
consulted for a hit — which is why it traps even with the ternary winmask zeroed
(§11), with every CLA config bit set (§12), and with the DPA at its implemented
maximum (§19). The blocker was never in the CLA tables; it is this one
PP-datapath declaration that our bring-up leaves at zero and the vendor sets.

### 20.5 Answer to the structural question

**Yes — a GE-ingress routed frame *can* reach the L3 classifier on this part**,
but only when its ingress port is declared WAN in `0x923a001c`. This is **not**
an architectural UNI↔PON-only limitation: the WAN port is a software field, a GE
port is a legal WAN (`sw_set_uni_as_wan`, `ethdrv_set_wanportid`), and the whole
directional fast path (`up_l3`/`dn_l3`) is defined relative to that declared
uplink, with no PON dependency in the decode. The reason offload has never
fired is the mundane one the earlier rounds were structurally unable to see
(they stayed inside the CLA): the OpenWrt bring-up ports the bootloader's subset
and omits the vendor's `tm_set_p2pmode`/`tm_set_pp_wan_cfg` step, so **no port is
WAN and nothing is ever an upstream L3 candidate.**

### 20.6 The enable (committed), and the measurement that will confirm it

Implemented in `zx_eth_datapath_init()`'s PP bring-up, gated by
`CONFIG_ZX279128_PP_TABLES` (off in the shipped config; release bring-up
unchanged), placed with the DPA enables so it lands in the freshly-reset,
now-clocked block, using the already-mapped `ppa` (PonPp) window:

```c
wan_b = readl(ppa + 0x1c);
writel((wan_b & ~0x3e000000) | BIT(3 + 25), ppa + 0x1c);  /* eth3/mac3 as WAN */
wan_a = readl(ppa + 0x1c);
```

mirroring the vendor's clear-field-then-`tm_set_pp_wan_cfg(3)`. eth3 (mac3) is
the WAN jack and the routed-traffic ingress (the `pp-udp-probe` injector). The
bring-up `pr_info` reports `wan_b -> wan_a` and warns if bit 28 does not latch.

**How it will be known (unchanged instrument, PP-KEY §10 / task):** with the flow
installed and sprayed, inject the probe tuple and read `pipe`. A correct WAN-port
declaration flips frames from `cla trap` to **`cla fwd`** by the same count; the
match is `cla fwd` incrementing with `cla trap` flat. `eth3 rx_packets` should
stop tracking the forwarded flow.

**Status: static hypothesis + one measured register, building for a cold RAM
boot.** The register is in the CPU-writable PonPp window (the driver already
writes `+0x20`/`+0x24` there), so unlike the DPA (§13/§19) it should latch; the
boot both confirms the latch and runs the `pipe` match test. This is the first
candidate upstream of the CLA that is (a) a single, decoded bring-up register,
(b) measured-unset on our boot and measured-set in the vendor model, and (c) the
exact missing step between "classified" and "forwarded." If `cla fwd` moves, it
is the match; if it does not, the WAN declaration is necessary-but-insufficient
and the next gap is `spa_set_port_pkt_filter`/`tm_set_p2pmode`'s companion SPA
writes, decoded and ready.

### 20.7 MEASURED result — the WAN bit IS consulted, trap→different action, still no fwd (2026-11-17)

Built `wancfg-ge` (= the §19 `gate-mask-1e0` image **plus only** the one
`0x923a001c |= bit28` write — `git show 4b3d810` is a one-hunk diff), cold RAM
boot, same `pipe` instrument.

**Bring-up readback (MEASURED, driver pr_info, t=0.967s):**
```
zx-eth: pp wan_cfg 0x923a001c 01200000 -> 11200000 (want bit 28, port 3 as WAN)
```
Bit 28 **latched**; no "did not latch" warning; runtime re-reads at t=37s and
t=402s still show `11200000`. So the PonPp window **is** CPU-writable at bring-up
(contrast the DPA, §19), our prior boots genuinely left no WAN port declared
(`0x01200000`), and the vendor's declaration is now replicated.

**The clean A/B (MEASURED).** Same flow installed + sprayed, same injector:

| image | `0x9238c3c4` up trap | `0x9238c3d0` | eth3 rx |
|---|---|---|---|
| §19 `gate-mask-1e0` (no WAN) | **+20 (1:1)** | — | +20 |
| this `wancfg-ge` (eth3 WAN) | **0 (flat)** | **+N, 1:1** (0x6e→0x8c→0xb4 over +30,+40) | +N (1:1) |

The **only** code difference is the WAN-cfg write, so the change is wholly
attributable to it. Declaring eth3 WAN **removes the upstream trap** that every
round since §10 saw and moves the per-frame CLA action onto a different counter
(`0x9238c3d0`, a CLA action slot outside the upstream fwd/trap/drop/copy quartet
the `pipe` verb reads). **This is direct proof that the WAN-port bit is consulted
by the ingress classifier** — a GE port's frames take a direction-dependent path,
and that path is not the plain CPU trap.

**But it is not the match.** `cla fwd` (`0x9238c3c0`) stays 0; `eth3 rx_packets`
still +1 per frame; `/proc/net/snmp` shows `InReceives == ForwDatagrams ==
OutTransmits` (the CPU software-forwards every frame); `flow stat id 1: hit=0`,
bank scan 0 hits. So the frame is still delivered to the CPU, not
hardware-forwarded, and the exact-match flow is still not consulted for a hit.

**What this settles (answer to the task's structural question).** A GE-ingress
routed frame on this silicon is **not** hard-walled off from the L3 path: the
WAN-port declaration (`0x923a001c`) measurably changes its classification, so the
part *does* treat a GE-WAN ingress frame differently from a plain LAN frame. The
earlier "UNI↔PON only" worry is falsified — the gate is a software-settable
register, not fixed silicon. What remains is that declaring the port WAN is
**necessary-but-not-sufficient**: it changes the action from trap to a
CPU-directed slot but does not yet route the frame through the exact-match
forward. The remaining gap is the rest of the vendor's uplink bring-up that
`tm_set_p2pmode` triggers around the WAN write — `spa_set_port_pkt_filter(port)`
(the per-port parse filter it calls next) and the never-called
`cla_set_up_l3_default_flow_cfg` (reg 30) / `cla_set_up_unicast_flow_cfg`
(reg 47/48) that set the *default upstream L3 action*. Those are the decoded,
ready next steps; `0x9238c3d0` → `0x9238c3c0` (fwd) by the same count remains the
pass criterion.

**Status: measured partial advance, not a match.** The WAN bit is proven
consulted and the upstream trap is proven removed; `cla fwd` is still 0. Change
committed (gated by CONFIG_ZX279128_PP_TABLES, cold-only); board powered off.

---

## 21. The counter was UPSTREAM-only; the frame is DOWNSTREAM — and the exact-match is still not consulted (2026-11-17)

§20.7 drew its "necessary-but-not-sufficient" conclusion from `cla fwd`
(`0x9238c3c0`) staying 0, and flagged `0x9238c3d0` as an unidentified "action
slot outside the upstream fwd/trap/drop/copy quartet." **Both are now pinned, and
they overturn the reading of §20.7: `0x9238c3c0` is upstream-ONLY, and our test
flow is downstream, so that counter could never have moved for this flow.**

Evidence: `$BENCH/logs/offload-20261117/dir1-downstream/RESULT.md`.

### 21.1 THE COUNTER MAP — read this before trusting any `cla fwd`/`cla trap` number in §10–§20

The CLA per-action packet counters are **two banks, up and dn**. Decoded from the
unstripped `tm.ko`: `tm_up_statistics_get` (`0x51f20`) reads words
`0xe30f0/1/2/6`; `tm_dn_statistics_get` (`0x5298c`) reads words `0xe30f3/4/5/7`;
both print them through the same four formats `_LC469/470/471/472` =
`cla fwd/trap/drop/copy pkts`. Phys = `0x92000000 + word*4`:

| action | UP word | **UP phys** | DN word | **DN phys** |
|--------|---------|-------------|---------|-------------|
| fwd    | 0xe30f0 | **0x9238c3c0** | 0xe30f3 | **0x9238c3cc** |
| trap   | 0xe30f1 | **0x9238c3c4** | 0xe30f4 | **0x9238c3d0** |
| drop   | 0xe30f2 | **0x9238c3c8** | 0xe30f5 | **0x9238c3d4** |
| copy   | 0xe30f6 | **0x9238c3d8** | 0xe30f7 | **0x9238c3dc** |

**`0x9238c3c0` ("cla fwd", the `pipe` verb's readout) is UPSTREAM-ONLY.** The
`pipe` verb reads only the up bank; it is blind to the dn bank. Every §10–§20
"cla fwd=0 / cla trap=+N" was the **upstream** bank. §20.7's `0x9238c3d0`
tracking injects 1:1 is **word 0xe30f4 = the DOWNSTREAM trap counter** — the
frame did not "move to an obscure slot," it moved to the **dn trap**, which is
exactly right for a WAN(eth3)→LAN(eth0) = uplink→UNI = **dn** flow.

The correct pass criterion for this flow is **`0x9238c3cc` (dn fwd) incrementing
with `eth3 rx` flat**, not `0x9238c3c0`.

### 21.2 Direction is `!TO_WAN(outdev)` = 1 (dn), confirmed on hardware

`switch.ko sw_acl_l3_hardfast_session_add.part.2` (`0x238c`) computes the session
direction byte = `!TO_WAN(outdev)`; `TO_WAN(eth0)=0` ⇒ dir **1 (dn)**. The
per-direction exact-match enable `EN_V4FAST_EXTIDXTBL(dir,extIdx,en)` (`0x57738`)
writes `extra_index` word4 **bits 5:4 for up (dir0)**, **bits 1:0 for dn (dir1)**;
`tm_acl_fast_add_v4v6` passes the dir from its first argument (the session's).
Our driver installs dir0 only (`rule init` sets fastinit bit 0; `flow_info` is
written at `ZX_PP_FLOW_DIR=0`). eth3 MAC = `02:00:00:00:00:06` = the injector's
`--peer-mac`, so the frame IS addressed to the ONU for routing — direction, not
addressing, is the variable.

### 21.3 MEASURED (RAM boot wancfg-ge, no rebuild) — every dn lever, still dn trap

| step (each: inject 20) | up fwd/trap | dn fwd | dn trap | hit |
|---|---|---|---|---|
| dir0 install only | 0 / 0 | 0 | +20 | 0 |
| + `enable 9 1 1` (dir-1 extra-index, word4 0x1→0x3 latched) | 0 / 0 | 0 | +20 | 0 |
| + `dn_unicast_ctrl` (0x9238c080 0x301a→0x701a) | 0 / 0 | 0 | +20 | 0 |
| + `oth_l3_pkt_action` 0x9238c0cc walked 1→2→3 | 0 / 0 | 0 | +20 | 0 |
| + **winmask fully zeroed** (`rulew` 144/145 w4–7=0) + dir1 | 0 / 0 | 0 | +20 | 0 |

`/proc/net/snmp Ip:` InReceives == ForwDatagrams (CPU forwards all 180 frames);
`stat id 1: hit=0 (aging[244]=0)`; `hits 0..4`: no HIT in any bank.

### 21.4 What this settles

**MEASURED:** The WAN-declared GE→GE routed frame is correctly classified
**downstream** (only `0x9238c3d0` moves, 1:1) and trapped by the **downstream
default action BEFORE the inner-hash flow lookup is consulted**. Zeroing the
winmask ("compare nothing," §11's decisive lever) in the dn context with the
dir-1 enable set still yields **no hit anywhere** — reproducing §11 with the
direction now correct. So the blocker is confirmed **upstream of the hash
comparison**, and is independent of: WAN declaration, every CLA-config bit
(incl. `dn_unicast_ctrl`), `oth_l3_pkt_action`, the DPA (maxed, §19), the
per-direction extra-index enable, the key encoding, and the winmask.

**INFERRED (next test, needs a rebuild):** the one dn-direction piece the console
cannot write is **`flow_info` at dir 1**. The driver writes it only at
`ZX_PP_FLOW_DIR=0`; `pp_pm_set_flow_info` takes a `dir` param ("up[0],dwn[1]")
and a dn frame's flow_info is fetched at dir 1. That — and/or a per-direction
"fast L3 submit" the vendor's `tm_add_acl_flow_rule`/`zte_api_fast_l3_session_add`
programs that `zte_zx_api_pp_global_init` does not set for a GE-WAN port — is the
first unreproduced step. The decoded dn configs (claRegTable base `0xb8448`,
validated id3→`0x9238c080`): `dn_l3_default_flow` regs 33–36
(`0x9238c124`/`0x9238c42c` bits 11/12/13), `dn_unicast_flow` regs 49–52
(`0x9238c144`/`0x9238c44c`), are recorded in RESULT.md for that rebuild.

**Correction to §20.7's "next step":** the leads named the **up** configs
(`cla_set_up_l3_default_flow_cfg` reg30, `up_unicast` reg47/48). For a WAN→LAN
flow those are the **wrong direction**; the **dn** equivalents are the relevant
ones. Also: `tm_set_p2pmode` does NOT call `spa_set_port_pkt_filter` — decompiled
(`0x460f0`), it only stores `lan_up_port` and calls `tm_set_pp_wan_cfg`; the two
are independent exported symbols. The WAN declaration our driver does is the
complete hardware equivalent of the vendor's (`sw_other_set_wan_lan_switch`
`0x6254` adds only a software port-mask and LED beyond the same bitmap write +
`tm_set_p2pmode`).

**Status: measured, no forward produced.** Direction model confirmed; exact-match
proven not-consulted for the dn frame independent of every pokeable lever and of
the key/mask; the untested piece is dir-1 `flow_info` (rebuild). Board powered
off.

### 21.5 The dir-1 `flow_info` was built and tested — also NOT the gate (2026-11-17)

The one dn piece §21.4 could not test from the console — `flow_info` installed at
**dir 1** — was built (runtime `flow_dir` module param, 0=up/1=dn, default 0;
commit `a7a7e4b`) and A/B'd against dir 0 **in one boot**, direction the only
variable. Evidence: `$BENCH/logs/offload-20261117/flowdir-ab/RESULT.md`.

| flow_dir | flow_info addr (logged) | dn fwd `0x9238c3cc` | dn trap `0x9238c3d0` | hit |
|---|---|---|---|---|
| 0 | `0x3ff` = (0<<10)\|1023 | 0 | +20 | 0 |
| 1 | `0x7ff` = (1<<10)\|1023 | 0 | +20 | 0 |

Each row: dn fwd=0, dn trap +20 exactly, every upstream counter 0, eth3 rx +20,
`stat hit=0 (aging[244]=0)`, no HIT in any bank, SNMP `InReceives==ForwDatagrams`
(CPU forwards all). The install direction written is MEASURED (the hashed-install
log now prints `flow_info dir N addr 0x…`), not assumed.

**MEASURED: the PM flow_info install direction is not the gate.** Installing the
flow_info at dir 1 — the address a downstream frame fetches it from — changes
nothing. So the exact-match is now measured not-consulted for a WAN→LAN GE routed
frame independent of **every** CLA-side lever: WAN declaration, CLA config
(incl. `dn_unicast_ctrl` and all §12 bits), `oth_l3_pkt_action`, the DPA (§19),
the per-direction extra-index enable, the key encoding, the winmask, **and the
flow_info direction**. The frame is trapped by the dn default action *before* a
dn L3 unicast frame is submitted to the flow-lookup pipeline; the gate is the
parse decision of "is this a flow-lookup candidate," which no table the
exact-match install touches expresses.

**Next unreproduced step (named, not yet tested).** The install reproduces the
CLA tables but NOT the vendor's *session* install `zte_api_fast_l3_session_add`
(`0x64868`) → `tm_add_acl_flow_rule`, the only path that marks a 5-tuple as a
live routed session (it builds a flow-control word + `tm_acl_setMtchInfo`
descriptor). Priority candidates:
1. **dn default-flow configs** — `cla_set_dn_l3_default_flow_cfg` regs 33–36
   (`0x9238c124` packed / `0x9238c42c` bits 11/12/13), `cla_set_dn_unicast_flow_cfg`
   regs 49–52 (`0x9238c144` / `0x9238c44c`). Never called by `tm_pon_pp_cla_initial`
   or our bring-up; set the dn default *action*. If the dn-unicast default gates
   "submit-to-flow-lookup vs trap," this is it. One decoded register pair in the
   CLA window, testable in one boot — **try this next.**
2. The full session-add flow-control word / match descriptor: if (1) also does
   not move `0x9238c3cc`, a bare exact-match install is insufficient on this
   silicon and the frame must traverse the full `zte_api_fast_l3_session_add`
   path — a materially larger port, and the point where "manual exact-match
   install" stops being the right model for this part.

### 21.6 The dn default-flow configs were tested — also NOT the gate. FINAL. (2026-11-17)

Candidate 1 (the dn default-flow configs, the last CLA-side lever) was written on
hardware and **does not move `0x9238c3cc`.** Evidence:
`$BENCH/logs/offload-20261117/dn-default-flow/RESULT.md`.

All four dn default-flow registers read `0x00000000` at boot (vendor init never
sets them). With the flow installed at dir 1, `dn_unicast_ctrl` set, and the dn
default-flow packed registers written to every plausible forward value —
`0x9238c124`/`0x9238c144` walked `0x1`, `0x80000000` (del_en), `0x00020000`
(default_uni_port), `0x000e0000`, `0xe0020001`; `0x9238c42c`/`0x9238c44c` |= `0x3800`
(da_known+) — **every inject still traps:** dn fwd `0x9238c3cc`=0, dn trap
`0x9238c3d0` += 20 each, `hit=0`, SNMP `InReceives==ForwDatagrams` (CPU forwards
all). The registers latch (final `0x9238c124`=`0x9238c144`=`0xe0020001`,
`0x9238c080`=`0x701a`) but no value engages the forward.

**FINAL CONCLUSION (the list is the finding).** A bare exact-match table install
does not forward a routed frame on this silicon. The exact-match is measured
not-consulted (hit=0, dn fwd=0) independent of **every** CLA-side lever, each by
its own measurement: WAN declaration, every CLA config bit (incl.
`dn_unicast_ctrl` and the §12 all-bits case), `oth_l3_pkt_action`, the DPA at its
implemented maximum (§19), the per-direction extra-index enable (both dir0 and
dir1), the key encoding, the winmask-zeroed "compare nothing" case (§11/§21), the
flow_info install direction (dir0 `0x3ff` and dir1 `0x7ff`, §21.5), and the dn
default-flow configs (regs 33–36, 49–52, every value tried, §21.6).

The frame traps on the downstream default action **before** it is submitted to
the flow-lookup pipeline. The submission lives in the vendor's **session-add**
path — `zte_api_fast_l3_session_add` (`0x64868`) → `tm_add_acl_flow_rule`, which
builds a flow-control word and a `tm_acl_setMtchInfo` match descriptor and the
`0x4c`-byte `g_FastList` session object — **not in any table this driver writes.**
No pokeable or bring-up register opens that gate; submission is a property of the
full session object. Reproducing it is a materially larger port (the session
descriptor construction + call path, replacing hand-written CLA table writes),
and an **owner decision** against the board's current measured throughput —
358/304 Mbps plain, 399/380 with software flow offload (`docs/PP-OFFLOAD.md`).
This investigation stops here: it has converted "the offload doesn't work" into
"the offload needs this one named, larger piece of work, and here is the measured
evidence for every smaller thing it is not." The `flow_dir` param and the §21.1
counter-map correction are the durable artifacts kept.

---

## 22. The session-add path decoded, and what it actually writes — 2026-11-17

§21.6 named `zte_api_fast_l3_session_add` as the one unreproduced step and called
it "a materially larger port … the session descriptor construction + call path,
replacing hand-written CLA table writes." This section decodes that path
completely from the unstripped `tm.ko` (Ghidra, image base `0x10000`) and reaches
a **sharper, and partly corrective, structural conclusion**: the session-add path
writes hardware through *exactly the same CLA/PM indirect-RAM ports* the
diagnostic driver already uses — **there is no standalone gate register in it** —
and the one thing it writes that the diagnostic path omits is the **action
descriptor chain** (sub_ram + cmd_ram), to which the exact-match's `cmd_flow_id`
points. All static decode; no new boot. Nothing here contradicts §10–§21's
measurements; it explains what they could not see from inside the CLA.

### 22.1 MEASURED (static): the whole subtree writes only indirect RAM, no gate register

Every hardware write reachable from `zte_api_fast_l3_session_add` was enumerated
from the call graph and each leaf's decompilation. The complete set of
hardware-touching leaves:

| leaf | port it writes | mechanism |
|---|---|---|
| `cla_set_hash_table` (`0x15a14`) | CLA hash window, sel 2..6 | `cla_set_indirect_rw_cmd/data` → `tmOnuRegWrite` |
| `cla_set_external_hash_table` | CLA overflow window | same |
| `EN_V4FAST_EXTIDXTBL` (`0x57738`) | `extra_index[extIdx]` word4 | `cla_set_extra_index_table` → same |
| `pp_pm_set_next_hop_ram_info` (`0x2d…`) | PM next_hop, sel 1 | `pp_pm_set_indirect_cmd/data_set` → `tmOnuRegWrite` |
| `pp_pm_set_flow_info` (`0x1cef8`) | PM flow_info, sel 0, addr `dir<<10\|idx` | same |
| `pp_pm_set_sub_ram_info` | PM sub_ram, sel 6 | same |
| `pp_pm_set_cmd_ram_info` | PM cmd_ram, sel 3 | same |
| `pp_pm_set_vlan_modify_ram_info` | PM vlan, only if VLAN edit | same |
| `pp_pm_set_{pppoe,dslite,b4/aftr ipv6}` | PM aux, only for those protos | same |

`tmOnuRegWrite` (`0x…`) is a plain `fpga_read_reg`/`fpga_write_reg` RMW through a
descriptor table (`claRegTable`/`ppPmRegTable`); the indirect accessors compute
`ram_addr + ram_id*0x400000 + rw_en*0x8000000` and strobe it. **No leaf writes a
standalone control/enable/gate MMIO register.** So the earlier model — "session
submission is opened by a register the bring-up or the table writes miss" — is
**false**: there is no such register in this path. Submission is a property of the
*table contents*, specifically the action descriptor the exact-match points at.

### 22.2 The g_FastList session object (0x4c bytes) — MEASURED layout

`zte_api_fast_l3_session_add` allocates a 0x4c-byte node from a kmem_cache and
links it into `g_FastList[(hash&0x1ff)*4]` / `g_FastList_Tail`. It is **software
bookkeeping** (del/stat/aging lookups walk it), **not a hardware table**. Layout,
from its own stores:

| offset | field |
|---|---|
| `+0x00` u8 | match-info[0] = address-family/type select |
| `+0x04` u32 | rule-type (`iVar14`: 1/2/3 = the flow_info/cmd class) |
| `+0x08..0x2c` | 36-byte copy of match-info[4..0x2c]: the 5-tuple + MACs + proto |
| `+0x30..0x40` | the five result words from `tm_add_acl_flow_rule` (flow-ctrl word, hash addr\|dir, extIdx) |
| `+0x44` / `+0x48` | prev / next list links |

The caller fills a ~0xbc-byte **match-info struct** (`param_1`) first: the
5-tuple at `+0x3b..0x41` (dst) / `+0x35..0x3b` (src ports/addrs region), proto at
`+0x28`, MACs at `+0x13`/`+0x3`, egress/ingress at `+0x44`/`+0x4`. `uStack_140`
is the **flow-control word**: a bitmask of which sub-features this flow uses
(`0x10000`=IPv4, `0x20000`=PPPoE, `|4`=VLAN present, `|3`/`|0x400003`=rule-type,
`|0x20`=inner-VLAN, `|0x800000`/`0x40000`=DS-Lite, etc.), consumed by
`addFlowOperInfo`/`operInfoAdd` to decide which PM tables to populate.

### 22.3 tm_acl_setMtchInfo (0x60918) — MEASURED descriptor

`tm_acl_setMtchInfo(match_info, desc)` fills a match descriptor used by
`tm_add_acl_flow_rule`:
- `desc+0x1c` = a packed action/port word: `0x301600` for TCP/UDP 5-tuple,
  `0x401600` (orig) / `0x1600` (reply) otherwise;
- `desc+0x08` = `match_info[0x9e]` (a priority/qid byte) for the non-5-tuple case;
- `desc+0x6b..0x6f` = dst MAC (from `match_info+0x13`), each byte mirrored with a
  `0xff` mask byte at `+5`; `desc+0x63..0x67` = src MAC (from `match_info+0x3`);
- `desc+0x62` = proto; `desc+0x74/0x76` = the two L4 ports.

This is the input to `tm_add_acl_flow_rule` → `addFlowOperInfo` → `operInfoAdd`,
**not** a direct hardware write.

### 22.4 The one thing the diagnostic path omits: the action descriptor chain

`operInfoAdd` (`0x58…`) is where the action is actually built and written. For a
plain IPv4 forward it:
1. writes **next_hop** (`pp_pm_set_next_hop_ram_info`) — *diag path does this*;
2. builds a **cmd_ram** program (`writeCmdInfoToRam` → `pp_pm_set_cmd_ram_info`,
   sel 3, up to 0x1c 12-byte micro-ops) describing the header edits — *diag path
   does NOT*;
3. builds a **sub_ram** entry (`pp_pm_set_sub_ram_info`, sel 6) that ties the
   flow to its cmd_ram index, vlan index and next_hop — *diag path does NOT*;
4. writes **flow_info** (`pp_pm_set_flow_info`, dir `g_direction`) whose fields
   pack the sub_ram index, the cmd/flow ids and the L2/checksum enables — the
   diag path writes a flow_info, but one that **points only at a next_hop and
   leaves the sub_ram/cmd_ram indices it should carry unwritten**.

So the diagnostic install writes a hash window whose `cmd_flow_id` action field,
and a flow_info, **refer to sub_ram/cmd_ram entries that were never populated.**
`cla_set_hash_table`'s own decoder confirms the window carries `cmd_flow_id`
(byte3[7:1]+byte4[2:0]) and `flow_sta_info`, i.e. the window is an *index into the
action chain*, exactly as the ternary rule is an index into the extraction
programs (§8). Two indirections, both of which must resolve to populated RAM.

### 22.5 What this does — and does not — change about the §21 blocker

It does **not** overturn §21.4's core measurement: the dn frame is trapped by the
dn default action **before** the flow lookup, and zeroing the winmask still
produced no hit. The action chain is *downstream* of the hit — the engine must
first decide to consult the exact-match and act on a hit, and §10–§21 show it does
not for this frame. A populated sub_ram/cmd_ram cannot, on its own, make an
un-consulted lookup fire. **So reproducing the action chain is necessary for a
correct forward but is not proven sufficient to move `0x9238c3cc`.**

What it *does* settle is the shape of the remaining work and removes a wrong
mental model: there is **no missing gate register** and **no missing bring-up
register** inside session-add (the WAN declaration of §20, already done, is its
only register write-equivalent, and it lives in bring-up, not session-add). The
remaining port is: (a) build the sub_ram (sel 6) and cmd_ram (sel 3) entries for a
plain IPv4 forward and the flow_info that indexes them, and (b) only then is the
exact-match's action fully resolvable. If, with that chain populated, the dn
default still traps (as §21.6's dn-default-flow sweep suggests it will), the gate
is confirmed to be the **parse-stage "is this a flow-lookup candidate" decision**
— set by the DPA/SBRG context the bring-up establishes, which §13/§14 measured as
*not runtime-pokeable* — and not anything the session-add path expresses at all.

### 22.6 Instrument correction landed (committed)

The `pipe` verb read **only the upstream counter bank** (`0x9238c3c0/4/8/d8`),
which is why every §10–§20 row watched `cla fwd=0` for a frame whose action was
landing on the **downstream** bank (§21.1). `pipe` now reads and prints **both**
banks (`zx_pp_cla_counters_dn`, CLA offsets `0x3cc/0x3d0/0x3d4/0x3dc`, decoded
from `tm_dn_statistics_get` `0x5298c` words `0xe30f3/4/5/7`). A single `pipe` read
can no longer watch the wrong side of a downstream A/B. This is the durable
instrument fix this round adds; the dn fwd line (`0x9238c3cc`) is the pass
criterion and is now printed directly.

### 22.7 Status

**Static decode complete; no forward produced or claimed.** The session-add path
is fully mapped: it writes only CLA/PM indirect RAM (no gate register), builds the
`g_FastList` software object (0x4c, layout above) and the `tm_acl_setMtchInfo`
descriptor, and its sole hardware difference from the diagnostic install is the
**sub_ram (sel 6) + cmd_ram (sel 3) action chain** the diagnostic flow_info points
at but never populates. That chain is the named next port. It is necessary but,
given §21.4/§21.6, **not measured-sufficient**: the dn frame is trapped upstream of
the lookup, and no table in the session-add path expresses the parse-stage
candidate decision (§13/§14 measured it as not runtime-writable). The `pipe`
dual-bank fix is committed; the board was not powered for this round.

---

## 23. The parse-stage gate is the SPA IP-protocol soft-trap; first hardware forward (2026-11-17)

Evidence: `$BENCH/logs/offload-20261117/onu-mac/RESULT.md` (+ pcaps). One cold
RAM boot of the unchanged `flowdir` image; every change a runtime
`/proc/zx_eth_poke` write; WAN bit latched at bring-up (`0x923a001c=11200000`).
20 frames `198.51.100.2:40001 -> 192.0.2.77:40002` into eth3 per row.

### 23.1 The gate: `0x921d41c0` (SPA `trap_protocol_type0..3`) — MEASURED A/B

| `0x921d41c0` | dn fwd `3cc` | dn trap `3d0` | eth3 rx |
|---|---|---|---|
| `11060000` (our bring-up) | +0 | **+20** | +20 |
| `00060000` (UDP byte cleared) | **+20** | +0 | +20 |
| `11060000` (restored) | +0 | +20 | +20 |
| `00060000` | +20 | +0 | +20 |

Repeated three more times in the same boot, same result every time. The
downstream trap that §21–§22 attributed to "the dn default action" is the SPA
**IP-protocol soft-trap**: a frame whose IP protocol matches one of the four
selector bytes is marked trap-to-CPU at parse time, ahead of the CLA's dn action.
Our driver writes `UDP|TCP` there (`SPA_CPU_PROTOCOLS`, inherited from U-Boot's
`0x11000000` plus TCP for host RX, `docs/ZX279128S-DATAPATH.md`). The probe is
UDP, so every probe frame in §10–§22 was soft-trapped before classification.

Vendor side: `tm_soft_protocol_iptype_set` → `spa_set_trap_protocol_type0..3`
has **no caller in `tm.ko` and is not imported by any stock module**
(relocation scan of tm/switch/plat/zx_ponreg/patch/idmfdb/shellproc). The
vendor never sets this selector; U-Boot's `0x11` is a bootloader convenience.

§7 item 2 ("clearing the UDP field changed nothing") was the **upstream** bank
watched for a downstream frame — the §21.1 counter error, not a property of the
register.

### 23.2 With the gate open the CLA really forwards — and rx goes flat

Selector cleared, then the decoded dn unicast default flow
(`cla_set_dn_unicast_flow_cfg`, reg 49 = `0x9238c144`: `del_en` b31,
`pkt_change_len` b30:29, `default_uni_port` `<<17`, tcont b16:12, queue b11:9,
flow_id b8:0; regs 50/51/52 = `0x9238c44c` bits 11/12/13 = gemport_valid /
tcont bit 5 / **da_known**):

| `c44c` | `c144` | rx | RED fwd-in `92344204` | RED trap-in `92344208` | SMAC3 tx `922c0718` | captured at injector |
|---|---|---|---|---|---|---|
| 0 | 0 | +20 | 0 | +20 | 0 | 0 |
| `0x800` / `0x1000` | 0 | +20 | – | – | – | – |
| `0x2000` | uni 0,1,2,3,5,6,7 | **+0** | +20 | 0 | 0 | 0 |
| `0x2000` | **uni 4** (`0x80000`) | **+0** | +20 | 0 | **+20** | **20** |
| `0x2000` | uni 4, selector `11060000` | +20 | 0 | +20 | 0 | 0 |
| `0x2000` | uni 4, **flow deleted** | +0 | +20 | 0 | +20 | 20 |

So **`da_known` (reg 52) selects fwd-to-queue vs. trap for a dn unicast frame**,
`default_uni_port` picks the egress MAC (uni 4 = MAC3 = eth3, so hw uni numbering
is eth N → uni N+1), and the frame leaves the wire with eth3 `rx_packets` flat and
`ForwDatagrams` flat. This is the **first measured hardware forward** on this
board: dn fwd counted, RED fwd queue, SMAC3 transmit, frame on the wire.

**What it is not:** it is the dn unicast *default* flow, not the exact-match.
The flow-deleted row forwards identically; `stat`/`hits` stayed 0 in every
bank, in every row, including with the winmask zeroed and a second install at
`in4/egress4` with `extra_index[4]` both directions. The forwarded frame is
byte-identical to the injected one (no MAC/TTL rewrite), reflected out the
ingress port because uni 4 is the only egress the default flow was pointed at
that the bench can capture (eth0 has no carrier; SMAC0 stayed 0).

### 23.3 Measured negatives this round

- Own-MAC tables (`tm_onu_mac_addr_set`): SPA `onu_mac[0]` `0x921d4120/4124`
  `0/0 → 840f87b6/0420` and PM `onu_mac` RAM (sel 0xc) written and read back
  (idx 1 reads 0, so real storage). No counter change. Not the gate.
- PonPp station MAC `0x923a0090/94`: write reads back 0 (as round 83).
- `0x9238c080 := 0xffffffff` (→ `0x000bfe1f`, all implemented CLA config bits)
  with selector cleared: dn trap +20, hit 0.

### 23.4 Vendor-vs-ours, the parse/bring-up writes

| vendor write | ours | status |
|---|---|---|
| `0x921d41c0` trap_protocol: never written by any stock module | `0x11060000` (UDP\|TCP) | **the gate**; measured A/B above |
| `tm_pon_npp_spa_initial`: `spa_set_up/dn_reg_pkt_en` all (regs 0/1, `0x921d4000`/`4040`), `802x_trap_en` 1..7, `[0x921d4054] |= 0x3000000`, `port_dft_pri` 0, `port_pkt_filter(0..8, 0)` (reg 0x39+p), `match_mode 1`, SPA match/hash RAM | partly (`+0/+4/+40/+44` only) | not tested; not needed to open the gate |
| `tm_set_pp_wan_cfg` `0x923a001c` bit port+25 | done (§20) | consulted |
| `tm_onu_mac_addr_set` SPA+PM onu_mac | none | measured no effect |
| `cla_set_dn_unicast_flow_cfg` regs 49–52 | none | **controls default fwd vs trap** (§23.2); vendor init never sets it — switch.ko does at runtime |
| `tm_pon_pp_dpa_initial`, `adm`, `sadm`, `cla_initial`, `pm_initial` | DPA/ADM measured §19 | not the gate |

`spa_set_port_pkt_filter`'s real callers: `tm_pon_npp_spa_initial` (all ports,
value 0) and `tm_port_pkt_filter_set` ← `zte_api_sw_vlan_set_port_inframemode` /
`spa_info_store` (VLAN frame-mode filter, reg `0x39+port`). It is a VLAN accept
filter, not an L3 candidate mark.

### 23.5 What remains (inferred, not measured)

1. **Host RX tradeoff.** Clearing the UDP/TCP soft-trap is what lets the PP see
   the frame, but `docs/ZX279128S-DATAPATH.md` measured (on an older bring-up
   without the WAN bit) that TCP to the host needs the TCP selector. With the
   gate open, host-bound traffic must reach the CPU by the CLA path instead
   (dn default trap with `da_known` clear, as row 1 shows: rx +20). A release
   change of the selector needs a host-TCP regression test first; nothing was
   changed in the bring-up this round.
2. **The exact-match still never hits**, now with the parse gate open and the
   CLA forwarding — so the remaining gap is in the exact-match key/scoping
   (ingress-port numbering: hw uni = ethN+1 per §23.2; the `in`/extIdx the key
   carries) or the action chain (§22: sub_ram/cmd_ram), not the parse stage.
   That is now a CLA-internal question with a working instrument: a hit should
   move `aging[]` and diverge from the default-flow egress chosen by `c144`.

---

## 24. The exact-match matrix with the gate OPEN — measured not-consulted; it is a different engine path (2026-11-17)

§23 opened the parse gate and produced the first hardware forward, but left
"the exact-match still never hits" as a CLA-internal question with two named
suspects: the ingress-port scoping (§24 suspect 1) and the sub_ram/cmd_ram
action chain (§24 suspect 2). This round ran the whole matrix on one cold boot,
**gate open the entire time**, and the answer is structural: the inner-hash
exact-match is **not consulted** for a downstream WAN→LAN frame, by direct
measurement, independent of every pokeable lever — and the action chain cannot
change that, by decode.

Evidence: `$BENCH/logs/offload-20261117/exactmatch-matrix/RESULT.md`.

### 24.1 The positive control needed one more bit: `c080` bit 14

§23.2's forwarding row is reproduced, and the bring-up detail that was easy to
miss is pinned: the dn unicast default flow forwards only with **`0x9238c080`
(dn_unicast_ctrl) = `0x701a`**, i.e. bit 14 set, in addition to `c44c=0x2000`
(da_known) and `c144=0x80000` (default_uni_port = uni 4). With `c080=0x301a` the
frame still traps even though da_known and the port are set. With `0x701a`:
dn fwd +20, eth3 rx **flat**, SMAC3 (`0x922c0718`) **+20** — frame off the wire.
That is the default flow, and it is the forwarding baseline for every row below.

### 24.2 The matrix — every row, all counters (20 frames each, gate open)

| row | state | dn_fwd | dn_trap | rx | SMAC3 | hit / banks0..4 |
|---|---|---|---|---|---|---|
| A2 | default flow uni4, c080=701a | +20 | 0 | 0 | +20 | — (default fwd) |
| B1 | + exact-match **in3**/eg4 installed | +20 | 0 | 0 | +20 | **0** |
| B2 | exact-match **in4**/eg4 (hw uni=ethN+1) | +20 | 0 | 0 | +20 | **0** |
| C1 | in4, default **TRAP** (da_known=0) | 0 | +20 | +20 | 0 | **0** |
| D1 | **winmask0 + spray all 512**, default fwd | +20 | 0 | 0 | +20 | **0 /0/0/0/0** |
| D2 | + every extra_index[0..15] enabled both dirs | +20 | 0 | 0 | +20 | **0 /0/0/0/0** |
| E1 | trap_acl_en (c080 bit17) set | +20 | 0 | 0 | +20 | **0** |
| E2 | all CLA config bits (c080=0bfe1f), default trap | 0 | +20 | +20 | 0 | **0** |

Install bucket is **244 for both in3 and in4** — the ingress port is not in the
hash (confirms §8.1: the key is port-independent). The +20 dn_fwd/SMAC3 in B/D
is the *default* flow, identical with the flow installed or not; it is not the
exact-match. `aging poke 244` read back 1 and sel2[244] word4 = `0x33001149`
(valid_en=1, field 0x90), so hit=0 is a real negative on a live instrument.

### 24.3 Why this settles suspects 1, 2 and 3 — each measured or decoded

- **Suspect 1 (ingress-port numbering).** in3 and in4 both miss, and they hash
  to the same bucket anyway. The decisive **winmask-zeroed + spray-all-512**
  rows (D1/D2) make the key irrelevant: comparing nothing, across every slot,
  with every per-port extra_index enabled both directions — still zero hits.
  Every prior winmask-zero test (§11/§21) ran with the SPA selector *set*, so
  the frame was soft-trapped before classification; those were false negatives.
  D1/D2 are the first valid "compare nothing" runs, and they are negative.
- **Suspect 3 (default-flow interaction).** Tested both regimes: default
  forwarding (da_known=1, B/D) and default trapping (da_known=0, C1/E2). The
  exact-match is not consulted in either. It is not gated on the default action.
- **Suspect 2 (sub_ram/cmd_ram action chain).** Decoded, not needed empirically:
  the aging/hit bit is set by the hardware **classify** stage when the inner
  hash matches. `tm_get_acl_flow_status` (`0x5e760`) only *reads and clears*
  aging; nothing in software sets it. `operInfoAdd` (`0x58b58`) builds
  sub_ram/cmd_ram/flow_info as the **action** of an already-matched session —
  it runs *after* a hit, to program the egress rewrite. An unpopulated action
  chain cannot stop a lookup from firing or a hit bit from setting. So suspect 2
  cannot produce a hit; it was never the gate for `aging[]`.

### 24.4 The structural conclusion

The **dn unicast default flow** (MAC-DA-lookup forward; `da_known`/`mac_lookup_en`)
and the **CLA ACL inner-hash exact-match** are two different engine paths. A
downstream (uplink→UNI) routed frame is forwarded by the default flow and is
never submitted to the inner hash. On this GPON ONU the inner-hash fast path is
architecturally the **UNI→PON (upstream)** datapath; a GE-WAN→GE-LAN frame does
not enter it. This is now measured with the parse gate open and the CLA actually
forwarding, closing the last ambiguity §10–§23 carried (that the earlier
negatives might be soft-trap artifacts). The per-flow offload for the WAN→LAN
direction would require driving the frame onto the upstream path or reproducing
the vendor's full session-submit, not any CLA table or config bit this driver
can write.

### 24.5 Host-TCP: the selector is NOT changed in the bring-up, and TCP still works cleared

Because the exact-match is unreachable regardless, **the bring-up SPA selector
is left as UDP|TCP** — no release change, no regression risk. The regression test
was still run (the matrix uses the gate-open regime): selector cleared
`0x921d41c0=00060000`, WAN bit latched, 5 WAN→ONU TCP connects to the ONU's own
IP — `/proc/net/snmp Tcp:` InSegs +5 and OutSegs +5 in lockstep (every SYN
reached the host CPU stack, every RST reply left the WAN jack; ICMP ping also 0%
loss). **Host-bound TCP is fully reachable with the selector cleared** — so even
if a future direction (upstream offload) needed the gate open, host TCP via the
CLA trap path is measured intact. Board powered off at end.

---

## 25. The UPSTREAM direction, gate open — the exact-match is not consulted there either (2026-11-17)

§24 concluded the inner hash is "architecturally the UNI→PON upstream
datapath" and every prior test had been downstream. This round tested
upstream. Evidence: `$BENCH/logs/offload-20261117/upstream/RESULT.md`
(`rows.jsonl`, every UART command, instrument `$BENCH/tools/pp-upstream-matrix.py`).
Image `flowdir.kernel`, one cold RAM boot, runtime pokes only.

### 25.1 Getting an upstream frame without a cabled LAN jack

At boot only eth3 has carrier; the bench host has one cable to the router (the
WAN jack). A frame cannot enter eth0..2 without the owner re-cabling. Instead
the WAN declaration (§20, `0x923a001c` bits 25..29) was moved off eth3, which
makes eth3 a UNI ingress. MEASURED, gate open, same injector frame:

| `0x923a001c` | up fwd | up trap | dn fwd | dn trap | eth3 rx |
|---|---|---|---|---|---|
| `11200000` (eth3 WAN) | 0 | 0 | +20 | 0 | +20 |
| `03200000` (eth0 WAN) | 0 | **+20** | 0 | 0 | +20 |
| `01200000` (none)     | 0 | **+20** | 0 | 0 | +20 |

The frame moves wholly to the **upstream bank**: it is in the UNI→uplink
path. (A physical LAN-jack ingress remains untested — caveat, not hidden.)

### 25.2 The matrix — no hit in any row

Gate `0x921d41c0=00060000` throughout; 20 frames per row; hw ingress uni 4.

| row | state | up fwd/trap/drop/copy | dn fwd/trap/drop/copy | RED fwd/trap | SMAC3 tx | rx | hit |
|---|---|---|---|---|---|---|---|
| P1–P4 | up default flow: c080 b15 (`0xb01a`), c140=`0x80000`, c448 `0x800`/`0x1800` | 0/+20/0/0 | 0/0/0/0 | 0/+20 | 0 | +20 | — |
| X1 | + `flow_dir=0`, `addh 4 ...` (bucket 244, flow_info `0x3ff`), `enable 9 0 1` | 0/+20/0/0 | 0/0/0/0 | 0/+20 | 0 | +20 | 0 |
| D1 | + winmask zeroed + spray 512 | 0/+20/0/0 | 0/0/0/0 | 0/+20 | 0 | +20 | **0, banks 0..4** |
| D2 | + every extra_index[0..15] both dirs | 0/+20/0/0 | 0/0/0/0 | 0/+20 | 0 | +20 | **0, banks 0..4** |
| E1 | + c080=`0x000bfe1f` | 0/+20/0/0 | 0/0/0/0 | 0/+20 | 0 | +20 | 0 |
| E2 | up default cleared, compare-nothing kept | 0/+20/0/0 | 0/0/0/0 | 0/+20 | 0 | +20 | 0 |
| D3 | no WAN declared, compare-nothing kept | 0/+20/0/0 | 0/0/0/0 | 0/+20 | 0 | +20 | **0, banks 0..4** |

Instrument live: `aging poke 244` read back 1; sel2[244] word4 `0x33001149`.
Nothing came back on the host jack in any row.

### 25.3 Conclusion

With the frame measured in the upstream CLA bank, the parse gate open, the
exact-match at dir 0 with the dir-0 extra-index, and the valid upstream
"compare nothing" control (winmask zero, 512 slots, all extra_index both
dirs), `aging[]` never moved and `up fwd` stayed 0. Together with §24
(downstream, same control): **the CLA inner-hash exact-match is measured not
consulted in either direction** by any lever this driver can write. §24.4's
"it is the upstream path" inference is therefore not borne out for a
UNI-classified GE ingress either. Also measured: the up unicast default flow
(reg46–48 + `up_unicast_ctrl`) does not forward with the values that make the
dn default flow forward; `up trap` is the only up counter that ever moved.

---

## 26. Physical LAN-jack ingress, gate open — the exact-match is not consulted from a real UNI either (2026-11-17)

§25's caveat was that "upstream" meant eth3 re-declared as a UNI, never a frame
entering a LAN jack. The owner cabled one; this round closes that gap.
Evidence: `$BENCH/logs/offload-20261117/lan-ingress/RESULT.md` (`rows.jsonl`,
every UART command, instrument `$BENCH/tools/pp-lan-matrix.py`). Image
`flowdir.kernel`, one cold RAM boot, runtime pokes only, board off at end.

### 26.1 The cabled jack is eth2

Carrier after `ip link set ethN up`: eth0 0, eth1 0, **eth2 1**, eth3 1.
Toggling eth2 down/up drops/restores host `enp3s0` carrier, so the LAN cable
lands on the netdev **eth2** (hw uni 3 by §23.2's ethN+1). Router configured by
hand (eth2 `192.0.2.1/24`, eth3 `192.168.1.1/24`, `198.51.100.0/24` via the host
WAN NIC, `ip_forward=1`); both legs ping. Probe: 20x UDP
`192.0.2.2:40001 -> 198.51.100.77:40002` into eth2, capture on the WAN jack.

### 26.2 The matrix — no hit in any row

| row | state | up fwd/trap | dn trap | eth2 rx | ForwDgrams | SMAC3 tx | WAN wire | hit |
|---|---|---|---|---|---|---|---|---|
| R0 | gate `11060000` (bring-up) | 0/+20 | bg | +20 | +20 | +20 | 20 | — |
| R1 | gate open `00060000` | 0/+20 | bg | +20 | +20 | +20 | 20 | — |
| X1 | `flow_dir=0`, `addh 3 ... -> 4` (bucket 93), `enable 9 0 1`, `enable 3 0 1` | 0/+20 | bg | +20 | +20 | +20 | 20 | 0 |
| X2 | `addh 2 ...` (bucket 93), extra_index[2] dir0 | 0/+20 | bg | +20 | +20 | +20 | 20 | 0 |
| D1 | + winmask zeroed + spray 512 | 0/+20 | bg | +20 | +20 | +20 | 20 | **0, banks 0..4** |
| D2 | + every extra_index[0..15] both dirs | 0/+20 | bg | +20 | +20 | +20 | 20 | **0, banks 0..4** |
| E1 | + `c080 = 0x000bfe1f` | 0/+20 | bg | +20 | +20 | +20 | 20 | **0** |
| F1 | + vendor SPA init: match_mode `0x921d407c` 0->1, port_pkt_filter `0x921d42a8` 0x154->0, `0x921d4054 |= 0x3000000` | 0/+20 | bg | +20 | +20 | +20 | 20 | **0, banks 0..4** |

`bg` = +3/+4 background host traffic, the same in every row including R0. up
drop/copy, dn fwd/drop/copy and SMAC2 tx stayed 0 in every row; full columns are
in the evidence file. Instrument live: `aging poke 93` read back 1, sel2[93] word4
`0x00001149` (valid, field 0x90). F1's addresses were decoded from `tm.ko`
`spaRegTable` (word `0x75000+n` -> `0x921d4000+4n`, checked against regs 0/1
= `4000`/`4040`): reg 0x12 (`spa_set_match_mode`) = `0x921d407c`, reg 0x39+p
(`spa_set_port_pkt_filter`) = `0x921d42a8` 2 bits per port. The SPA match/hash
RAM loads in `tm_pon_npp_spa_initial` were not reproduced.

### 26.3 Conclusion

A real LAN-jack frame is classified **upstream** (`up trap` 1:1, gate open or
closed) and goes to the CPU, which routes it out the WAN jack in software. With
the exact-match installed for dir 0 at both candidate ingress unis, and then
the valid upstream "compare nothing" control from a real UNI (winmask zero, all
512 slots, every extra_index both directions, every CLA config bit, vendor SPA
match_mode/port filter), `aging[]` never set and `up fwd` never moved. Together
with §24 (downstream) and §25 (eth3 as UNI): **the CLA inner-hash exact-match
is measured not consulted from any ingress port this bench can drive**, by any
lever this driver can write. Remaining unreproduced vendor state: the SPA
match/hash RAM contents, plus whatever the vendor's runtime session-submit
writes outside the CLA.

---

## 27. The SPA match/hash RAM loaded — no exact-match hit in the tested states (2026-11-17)

§26 closed every table/config lever but left one piece of
`tm_pon_npp_spa_initial` unreproduced: the SPA **match RAM** and **hash RAM**
loads. The hypothesis was that the SPA protocol parser builds the lookup key,
and with its match/hash RAMs unloaded it might never produce a key — so a
lookup with no key cannot happen, explaining every prior negative. This round
decoded those RAMs completely, loaded them on the bench, and measured. The
answer is the same: **no hit**. The SPA RAM is not the gate either.

Evidence: `$BENCH/logs/offload-20261117/spa-key-ram/RESULT.md` (`rows.jsonl`,
instrument `pp-lan-matrix.py`). Image `spa-key-ram.kernel`, one cold RAM boot,
real LAN-jack ingress on eth2 (hw uni 3), board off at end.

### 27.1 The decode — match RAM and hash RAM, how they are written

`tm_pon_npp_spa_initial` (`0x4e858`), after `spa_set_match_mode(1)`, copies a
0x160-byte `.rodata` table (`.LANCHOR1` sec12 off 0x1980 = 11 x 32-byte
descriptors), re-packs each into a 10-byte entry, and calls `spa_set_matchram`
per entry; then calls `spa_set_hashram(0..7)` from a 48-byte `.rodata` source
(off 0x1ae0). Both go through the SPA **indirect** interface, addressed via
`spaRegTable` (word 0x75000+n -> 0x921d4000+4n, §26):

| role | spaRegTable id | word | phys | notes |
|---|---|---|---|---|
| CMD | 4 | 0x75005 | `0x921d4014` | `rw_en<<27 \| ram_id<<22 \| addr` (`spa_set_indirect_rw_cmd`) |
| STATUS | 5 | 0x75006 | `0x921d4018` | bit0 access_done; read 1 = ready (readiness gate, not busy) |
| DATA0..5 | 6 | 0x75007 (stride 1) | `0x921d401c..0x4030` | write latch (`spa_set/get_indirect_rw_data`) |
| match_mode | 0x12 | 0x7501f | `0x921d407c` | 2 bits (`spa_set_match_mode`) |

`spa_set_matchram` writes DATA5..DATA0 then `cmd(rw=0, ram_id=0, addr=line)`;
`spa_set_hashram` writes DATA1=word1, DATA0=word0 then
`cmd(rw=0, ram_id=5, addr=entry)`. Each is preceded by the vendor's
"wait STATUS bit0 == 1" poll (up to 0x13 tries), then the command issues with
no further check — i.e. STATUS is a ready-gate, confirmed on the bench where it
sits at 1 and never dips.

The **match RAM** holds 11 protocol-parser rules packed four per 192-bit line
(three lines). Each rule is `{valid, v4v6_flag, offset_mode=2, offset,
compare_mode, mask, data}`; decoded values are the IP-protocol/L4 recognizers
proto 0x11 (UDP, rule0), ctrl ports 0x208/0x76c/0x13e/0x141 (rules1-4),
0x43/0x44 (DHCP, rules5-8), proto 0x06 (TCP, rule9), 0xb3 (rule10). The word
images were produced by a byte-exact port of the vendor packer (all four slot
cases of `spa_set_matchram`) and **validated against its inverse**
(`spa_get_matchram` field print expressions) for all 11 rules — a closed
round-trip, so the on-wire RAM image is provably the vendor's. The **hash RAM**
maps a matcharray to a (valid, action, action_rsn) triple; the hardware latches
`word1 & 0xffff`.

Driver gap vs §26: our `zx_eth_datapath_init` wrote SPA +0/+4/+40/+44 + the
trap selector, plus (F1) match_mode/port_filter/`+0x54`. It never wrote the
match or hash RAM. This round is the first time they have been loaded.

### 27.2 Loaded and measured — still not consulted

A new gated trigger `/proc/zx_eth_spa_ram` (diagnostic build, behind
`poke_allow_write`, outside the frozen init trace) loads match_mode=1 + 3 match
lines + 8 hash entries through the sequence above. On the bench the full load
was also reproduced by hand via `/proc/zx_eth_poke` (same register writes), and
`match_mode` read back `0x1`. With the exact-match installed at dir 0 for the
real ingress (in3, bucket 93, extra_index dir0+dir1, sel2[93] word4 `0x00001149`
valid):

| state | up fwd/trap | eth2 rx | ForwDgrams | wire | aging[93] / banks |
|---|---|---|---|---|---|
| exact-match only (no SPA RAM) | 0/+20 | +20 | +20 | 20 | 0 |
| **+ SPA match RAM + hash RAM + match_mode=1** | **0/+20** | +20 | +20 | 20 | 0; bank2 0 hits |
| + winmask 0 + spray all 512 (compare nothing) | 0/+20 | +20 | +20 | 20 | **0; banks 0..4 all 0 hits** |

Every LAN-jack frame still lands in the **upstream** bank as `up trap` (+20,
1:1), reaches the CPU (eth2 rx +20) and is software-routed out the WAN jack
(ForwDatagrams +20, eth3 tx +21, SMAC3 +21, 20 captured). `up fwd` never moved
and `aging[]` never set — not with the SPA RAM loaded, and not under the valid
"compare nothing" control layered on top of it.

One caveat recorded honestly: the SPA DATA registers are a write latch — a read
command does not repopulate them from RAM (a read of line 0 returns the last
*written* word), so there is no register-level RAM read-back to independently
prove the bytes reached the array. But the write sequence is byte-for-byte the
vendor's, STATUS gated ready on every command, match_mode latched, and the CLA
`up trap` counter shows the SPA *did* parse and classify every frame (just not
to the exact-match). The negative is on a live instrument (`aging poke 93`
reads back 1), across all 512 slots with the key made irrelevant.

### 27.3 Conclusion — no demonstrated per-flow offload in these trials

Across §§23–27, the tested GE-to-GE ingress paths and programmed states did
not produce an exact-match aging/hit indication or working per-flow offload.
The positive default-flow hardware-forwarding result is distinct from an
exact-match hit. Loading the decoded SPA RAM did not change those observations.

This narrows the tested hypothesis; it does not establish that no future
hardware integration can work. SPA DATA is a write latch, so independent RAM
contents were not read back. Other vendor runtime/session state was not fully
reproduced. The H199A has Ethernet WAN/LAN connectors; symbolic PON names do
not prove an optical uplink or a silicon-wide impossibility. See
[the current offload status](PP-OFFLOAD.md).
