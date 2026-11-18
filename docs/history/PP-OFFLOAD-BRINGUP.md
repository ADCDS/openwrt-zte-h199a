> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# Packet-processor table access (groundwork for hardware flow offload)

Status, 2026-11-15: **implemented and host-tested. Not hardware-qualified. Off by
default** (`CONFIG_ZX279128_PP_TABLES`, `# ... is not set` in `config-6.6`, enabled
by no profile). This is the first gated software step toward hardware flow
offload. It offloads nothing.

> **2026-11-17 — the exact-match install is measured insufficient; see PP-KEY §21.**
> A bare CLA exact-match table install does NOT forward a routed frame on this
> silicon. With the WAN port declared (so the frame is correctly classified
> downstream), the exact-match is measured not-consulted — hit=0, dn fwd
> `0x9238c3cc`=0 — independent of every CLA-side lever (WAN decl, all config bits
> incl. `dn_unicast_ctrl`, `oth_l3_pkt_action`, the DPA at max, the per-direction
> extra-index enable, the key encoding, the winmask-zeroed case, the flow_info
> install direction, and the dn default-flow configs). The frame traps on the dn
> default action before it is submitted to flow lookup; submission lives in the
> vendor's session-add path (`zte_api_fast_l3_session_add` → `tm_add_acl_flow_rule`),
> not in any table this driver writes. Reproducing it is a materially larger port
> and an owner decision vs. the current 358/304 plain, 399/380 software-flow-offload
> throughput. PP-KEY §21.1 is the permanent counter-map correction (0x9238c3c0 is
> upstream-only); the runtime `flow_dir` param (commit a7a7e4b) is kept.

Code: `files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-pp.c`
(+ `zx279128-pp.h`), linked into the Ethernet driver only when the symbol is set.
Tests: `tests/test_pp_tables.py`. Design background: the session notes
`offload-cla-pm-offsets.md` (register protocol, treated as the spec) and
`offload-cla-pm-design.md` (overall offload design).

## What it does

With the symbol set, the Ethernet probe calls `zx_pp_tables_init()` after
`zx_eth_datapath_init()` and before any netdev is registered, and only if that
call's packet-processor bring-up block ran (`ze->pp_bring_up`). A debug warm attach therefore never enables it. A failure
is logged and is not fatal, because the datapath does not use the tables.

1. **Gate 1 (reads only).** Poll the CLA and PM ready flags (`0x9238c018`,
   `0x9239c018`, bit 0, at most 20 reads each). If either is not ready, stop.
2. **Gate 2.** `dma_set_coherent_mask(32)`, then `dma_alloc_coherent` a 1 MiB PM
   table and a 4 MiB ACL table. Each must be 128 KiB aligned and must end below
   4 GiB, or both are freed and nothing is written.
3. **Gate 3.** Program PM base `0x923a0020` and then ACL base `0x923a0024`, the
   vendor's order, as read-modify-write. Read both back. If either differs, clear
   both, free both, stop. Only after this do the engines accept indirect
   operations.
4. Register a devres teardown, then create a read-only debugfs directory.

At boot the driver touches only these registers: two STATUS reads (a third and
later read only if an engine is busy), and a read, a write and a readback of
each base register. No CMD or DATA register is accessed until debugfs is read.

**Indirect accessors.** These are kernel-internal: `zx_pp_{cla,pm}_{read,write}()`,
with no caller yet apart from the debugfs reader. Each call holds the engine
mutex and checks the vendor bounds before any register access (`-EINVAL`):

| | CLA | PM |
|---|---|---|
| CMD | `0x9238c014`, mask `0x0fffffff` | `0x9239c014`, mask `0x0fcfffff` |
| STATUS (ready = bit 0) | `0x9238c018` | `0x9239c018` |
| DATA word i | `0x9238c01c + 4i`, i ≤ 16 | i ≤ 3: `0x9239c01c + 4i`; 4 ≤ i ≤ 7: `0x9239c100 + 4(i-4)` |
| CMD = addr \| sel<<22 \| op<<27 | addr < 0x400000, sel ≤ 9 | addr < 0x100000, sel ≤ 31 |

op 0 is write and op 1 is read. Every CMD and DATA write is a read-modify-write,
as the vendor's `tmOnuRegWrite` does it: CMD keeps the bits outside the mask (CLA
31:28; PM 31:28 and 21:20). The DATA mask is full, so the read is replayed but
the written value is exact.

- **Write:** pre-poll, CMD, DATA from the highest word down to DATA[0] (+0x1c),
  which is the last access. There is no completion poll, as in the vendor driver;
  the next operation's pre-poll sees completion.
- **Read:** pre-poll, CMD, poll again, DATA from the highest word down. The
  vendor's post-CMD poll is dead code. This driver keeps the second poll anyway,
  because it can only wait longer.
- **Poll:** at most 20 STATUS reads, 1 µs apart. The vendor does 20 reads with no
  delay and accepts only reads 1–19, so this bound is the same and never less
  patient. A timeout returns `-ETIMEDOUT` and **latches** the engine. Every later
  operation on that engine returns `-EIO` with no register access, until reboot.
- `-ENODEV` means the tables are not live: init failed, the probe did not run
  the bring-up, or the driver is being removed.

**Teardown.** `zx_pp_tables_remove()`, called from `zx_eth_remove()` after the
ports close, or the devres action if a later probe step fails. It runs in this
order: remove debugfs (which waits for readers in flight), disable both engines
under their mutexes, clear ACL then PM base to 0, then free each table. If a base
register still points into its table after the clear, that table is **leaked**
rather than freed, so memory the engine may reach is never handed back to the
allocator.

**debugfs** (`/sys/kernel/debug/zx279128-pp/`, every file mode 0400, no file
has a write method):

- `status` shows each base register's DMA address, the value found before
  programming, the value programmed and the current value. It also shows each
  engine's STATUS, enabled and faulted flags, and its read, write and timeout
  counters.
- One binary file per table. Entry *n* is at file offset *n* × entry size,
  stored as little-endian u32 words, word 0 first. The file offset is the only
  selector, so there is no write path. A `read()` must start on an entry boundary
  and ask for at least one entry. It returns at most 64 entries, and each entry
  costs one indirect read. For example, entry 5, one 4-byte word:
  `dd if=/sys/kernel/debug/zx279128-pp/cla_cpu_queue_id bs=4 skip=5 count=1 | hexdump -C`.
  **Do not `cat` a table during qualification**, because that reads every entry.

| file | engine sel | words | entries | vendor reader (tm.ko) |
|---|---|---|---|---|
| `cla_extra_index` | CLA 0 | 5 | 16 | `cla_get_extra_index_table` 0x4420 |
| `cla_extra_rule` | CLA 1 | 17 | 160 | `cla_get_extra_rule_table` 0x5038 |
| `cla_hash0..4` | CLA 2..6 | 15 | 256/128/64/64/8 | `cla_get_hash_table` 0x5f20 (bank split of idx < 520) |
| `cla_cpu_queue_id` | CLA 7 | 1 | 1024 | `cla_get_cpu_queue_id` 0x6abc |
| `pm_flow_info` | PM 0 | 3 | 2048 | `pp_pm_get_flow_info` 0x1d114 (addr = dir<<10 \| idx) |
| `pm_next_hop` | PM 1 | 3 | 512 | `pp_pm_get_next_hop_ram_info` 0x1d890 |
| `pm_vlan_modify` | PM 2 | 1 | 1024 | `pp_pm_get_vlan_modify_ram_info` 0x1dc74 |
| `pm_cmd_ram` | PM 3 | 1 | 8192 | `pp_pm_get_cmd_ram_info` 0x1de50 |
| `pm_sub` | PM 6 | 2 | 1024 | `pp_pm_get_sub_ram_info` 0x1e914 |
| `pm_diag` | PM 13 | 8 | 4 | `pp_pm_get_diag_ram_info` 0x1fe08 (the only reader of DATA[4..7]) |

A table is listed only if its vendor reader bounds both the word count and the
index, as read from that reader's loop and compare instructions in tm.ko. CLA dscp_tc_qid
(it always uses addr 0), acl_aging (its address formula is not verified), and the
PM e8_qos, modify, pri, v6rd, pppoe, b4, aftr and onu_mac tables are left out.

## Evidence for the DRAM table sizes and placement

The stock firmware does not allocate these tables. It carves them out of a
reserved block **R**, the top `ZX_RESERVE_MEM_SIZE` MiB of DRAM. All of the
following was read statically from the stock images, without hardware:

- Stock kernel `cal_reserve_mem` (0xc0015834): with 128 MiB DRAM,
  `ZX_RESERVE_MEM_SIZE` = 18. `zx279128_reserve_mem` memblock-reserves
  `R = 0x40000000 + pdt_mem_size - 18 MiB` = `0x46e00000` on this board.
- tm.ko `tm_pon_pp_reg_initial` (0x3d594): PM base = R + 0x420000 and ACL base =
  R + 0x20000, written through `pon_pp_set_pm_base_addr` (0x19718, PonPpRegTable
  id 14) and `pon_pp_set_acl_base_addr` (0x19894, id 15). These are the only
  callers. PonPpRegTable (tm.ko `.data` + 0x336c): id 14 is word 0xe8008, which is
  **0x923a0020**, and id 15 is word 0xe8009, which is **0x923a0024**. Both are
  type 3 (read-write), with mask 0xffffffff and shift 0.
- plat-zxylzb_9128S.ko `pon_tm_bmu_init` (0x7f2c) fills in the rest of R: BPPE
  free lists at R + 0 and R + 0x10000 (TM +0xe8/+0xec), normal packet buffers at
  **R + 0x520000** (TM +0xf4), and jumbo buffers after them.
- Stock `zx_map_io` (0xc0578058) adds iotable entry 19, which maps virt
  0xf1000000 to R with length **0x520000** (MT_DEVICE). That is exactly
  R..R + 0x520000.
- tm.ko `cla_set_external_hash_table` (0x64e0) writes ACL entries at virt
  `0xf1020000 + idx * 64`, with idx a u16. That is at most 65536 × 64 B = **4 MiB**,
  which is R + 0x20000 .. R + 0x420000, the full gap up to the PM base.
- tm.ko `pp_pm_set_external_flow_info` (0x1d3d0) writes PM entries at virt
  `0xf141c000 + idx * 16` for dir 0 and `0xf149c000 + idx * 16` for dir 1.
  `operInfoAdd` takes that path only for idx ≥ 1024 (`cmp r5, #1024; bcs`). Both
  per-direction allocators bound idx < 32768 (0x490a4 and 0x4a230). So the
  entries fill pm_base + dir × 0x80000 + (idx - 1024) × 16, which stays inside
  R + 0x420000 .. R + 0x520000 = **1 MiB**.
- The vendor's bases are therefore 128 KiB aligned, with the low 17 bits zero.
  `dma_alloc_coherent` aligns these allocations to their own size, so they meet
  that alignment and more.

**Proven:** the vendor's region sizes, 4 MiB ACL and 1 MiB PM, and the CPU-side
layout. **Inferred:** that the engine itself never addresses beyond those
regions. The vendor places packet buffers right after the PM region, so a larger
hardware reach would corrupt stock traffic.

The hardware read in session §6u matters here. Under this image the two base
registers held `0x56409000` and `0x5f600000`, which are outside DRAM. Nothing had
programmed them, and the software datapath worked anyway.

## Proven vs unproven

| claim | status |
|---|---|
| CLA/PM CMD, STATUS and DATA offsets; the CMD encoding and bounds; the PM DATA[4..7] split; RMW semantics; the 20-read poll; the write and read order | proven statically from tm.ko (offsets file §1–4) |
| CLA and PM STATUS read 1 (ready) under this image, with no hang | **proven on hardware**, both before and after the bases are programmed |
| Base register addresses, width and read-write type; region sizes and alignment | proven statically (above) |
| The base registers accept CPU writes | **proven on hardware** (2026-11-15): the driver readback and an independent `zx_eth_poke` read both return the programmed values. 0x923a0078 in the same page ignoring writes does not apply to +0x20/+0x24 |
| An indirect operation after programming completes and does not stall the bus | **proven on hardware** for reads (74 reads, 0 timeouts, 60 min soak) and for writes (single-flow install, readback and delete) |
| DATA[0] (+0x1c) is the write commit trigger | consistent with hardware: writes ending at +0x1c read back exactly (flow test) |
| A read needs no wait between CMD and DATA | unknown. The driver polls again anyway |
| Whether the engine walks the DRAM tables with no external flows installed; whether writing 0 on teardown is safe | unknown. The stock image never clears them. Before this driver they held non-DRAM values and nothing failed; with them programmed, forwarding ran unchanged for an hour |
| Clock and reset gating of the PP block (which TOPCRM bit) | unknown. Precondition: the bring-up in `zx_eth_datapath_init` must have run, and this driver never gates or resets the block |
| The callers' locking discipline in the vendor code | unknown. This driver uses one mutex per engine |

## Hardware qualification, in order; each step bounded and stopped on surprise

Run on a RAM boot with UART attached. Do not run from NAND. Stop at the first
unexpected result and record it. Never write table contents: the driver offers
no path for that.

1. **Build only.** Build a RAM-boot image with `CONFIG_ZX279128_PP_TABLES=y`, for
   example a BRINGUP image. Never enable it in a production profile. Confirm the
   symbol in the merged `.config` and that `zx279128_eth.o` contains
   `zx279128-pp.o`.
2. **Boot, init only.** Expect `pp: tables live, pm <dma> acl <dma> (were
   0x56409000 0x5f600000)` in dmesg. The alternatives are `bases did not stick`
   (expected if the PonPp page ignores CPU writes; that ends this approach until
   the write path is understood) or `not ready`. Check
   `/sys/kernel/debug/zx279128-pp/status`: `now` equals `programmed` for both bases,
   and both engines show `enabled=1 faulted=0`. Then run the existing wired
   routing smoke test and confirm forwarding is unchanged with the bases
   programmed.
3. **First indirect command: one CLA read.**
   `dd if=.../cla_cpu_queue_id bs=4 skip=0 count=1 | hexdump -C`. Expect 4 bytes
   back and `cla ... reads=1 timeouts=0`. A timeout latches the engine and
   returns an error, by design. A bus hang means the clock-domain precondition is
   wrong; power-cycle and stop.
4. **Widen the CLA read path, one entry at a time.** Read entry 0 of
   `cla_extra_index` (bs=20), `cla_hash0` (bs=60) and `cla_extra_rule` (bs=68).
   Then read a few more entries, then a single `count=64` read of
   `cla_cpu_queue_id`.
5. **PM, low words.** Read entry 0 of `pm_cmd_ram` (bs=4), then `pm_flow_info`
   (bs=12).
6. **PM, high bank.** Read entry 0 of `pm_diag` (bs=32), the first access to
   `0x9239c100..0x9239c10c` through an operation.
7. **Teardown.** `CONFIG_ZX279128_PP_TABLES` is a `bool` that depends on the
   Ethernet tristate, so it can never be `=y` in an `=m` build: the `rmmod`
   step this section used to prescribe is unreachable as written. The
   equivalent, and what to run, is an unbind/rebind cycle, which does call
   `zx_eth_remove()` and therefore `zx_pp_tables_remove()`:
   `echo <pdev> > /sys/bus/platform/drivers/zx279128-eth/unbind`, then
   `…/bind`. Expect both base registers cleared (read them through a BRINGUP
   `zx_eth_poke` image) and no `leaking its table` message. Repeat three times.
8. **Soak.** Leave the image routing for at least an hour with `status` sampled
   periodically. Expect `timeouts=0` and no change in forwarding.

Only after all eight steps can the next design steps start: a single offloaded
flow with its ADM counter checked, then the rest of design note §(d). Each needs
its own reviewed write path.

## Flow write path qualification (`CONFIG_ZX279128_PP_FLOW_TEST`)

This is the **first write** to the PP tables on hardware. Everything above only
read. The decoded spec is `docs/PP-FLOW.md`; the code is
`zx279128-pp-flow.c`. Build a diagnostic RAM-boot image with
`PP_TABLES=1 PP_FLOW_TEST=1` (the flag refuses any non-diagnostic profile and
refuses `PP_FLOW_TEST=1` without `PP_TABLES=1`). Never enable it in a
production profile. Prerequisite: steps 1–8 above pass on this unit and this
image, so reads, base programming and the soak are already trusted.

Run on a RAM boot with UART attached, **after** the read-path steps, with a
wired LAN-side host and a WAN host available. Each step is bounded; stop at the
first surprise and record it. The module parameter arms the path:
`echo 1 > /sys/module/zx279128_eth/parameters/flow_test_enable` (the default 0
refuses every write).

1. **Install a flow that can never match real traffic.** Pick a 5-tuple that
   cannot occur on this network — a TEST-NET-1 source
   (`192.0.2.0/24`, RFC 5737) and an unused port — so even a hash collision
   cannot match a live packet. Write one line:
   `echo 'add 2 tcp 192.0.2.1:1 198.51.100.2:1 -> 4 192.0.2.1:1 \
   02:00:00:00:00:01 02:00:00:00:00:02' > /sys/kernel/debug/zx279128-pp/flow`.
   Expect `pp-flow: installed id 1 … (hash slot 519, flow_idx 1023, nh 511)` in
   dmesg and no stall. The driver writes PM next_hop[511], PM flow_info[1023],
   CLA hash4[519] and clears CLA aging[519] — four indirect writes. Confirm
   `/sys/kernel/debug/zx279128-pp/status` still shows both engines
   `enabled=1 faulted=0` and `timeouts=0`, and that **wired forwarding is
   unchanged** (run the routing smoke test). This is the write-commit test the
   read path could not do: if the board survives four indirect writes with the
   datapath intact, DATA[0] commit works.
2. **Read it back.** The write path has no reader of its own; use the read-path
   debugfs files, which return the same little-endian words:
   `dd if=/sys/kernel/debug/zx279128-pp/cla_hash4 bs=60 skip=7 count=1 | hexdump -C`
   (slot 519 = bank cla_hash4 address 7) must show word 4 byte 0 = `0x50`
   (`valid_en` + `rule_mode`) and the stored tuple in the key region;
   `dd … of pm_next_hop bs=12 skip=511`, `pm_flow_info bs=12 skip=1023` must
   show the next_hop and flow_info words from `docs/PP-FLOW.md §8`. A readback
   that matches what was written proves the write path end to end.
3. **Read the hit bit.** `echo 'stat 1' > …/flow`. Expect
   `pp-flow: stat id 1: hit=0 …` (nothing has matched). This is the counter
   read and read-to-clear.
4. **Delete it, read it back.**
   `echo 'del 1' > …/flow` → `pp-flow: deleted id 1 (0)`. Re-read cla_hash4[519]
   and expect all zero (`valid_en` cleared), and pm_flow_info[1023] /
   pm_next_hop[511] zero. Confirm forwarding still unchanged.
5. **Teardown deletes before free.** Install a flow, then unbind the driver
   (`echo <pdev> > /sys/bus/platform/drivers/zx279128-eth/unbind`) — an `=m`
   build is impossible here, see step 7 above. Expect
   `pp-flow: deleted installed flow at teardown` **before** the `pp: …`
   base-clear messages, and no `leaking its table`. The engines must never walk
   a freed table. A clear that *fails* must now also keep the tables: expect
   `pp: … table kept: a flow could not be cleared at teardown` and no
   `dma_free_coherent` for either table. Repeat three times.

**Results (2026-11-16, one unit, diagnostic `PP_TABLES=1 PP_FLOW_TEST=1` RAM boot):**
a write with `flow_test_enable=0` is refused (EPERM, no engine write). Step 1:
the install completes four indirect writes with 0 timeouts and no stall, and
exact 32 MiB transfers run both ways with the flow installed. Step 2: every
field reads back exactly as encoded (`b16 = 0x50`, cmd_flow_id 1023,
inport 2 / outport 4, the stored tuple, the next_hop and flow_info words), so
the indirect write commits on hardware. Step 3: `hit=0`, read-to-clear.
Step 4: delete, then all three entries read back zero and forwarding is
unchanged. Step 5 (teardown on unbind) has not run.

Only once 1–5 pass on a never-matching flow should a **matching** flow be
attempted — and that needs the top unknown (the 45-byte CLA key encoding,
`docs/PP-FLOW.md §2`) decoded first, so that the entry can be placed in the
bucket the hardware computes for a real packet. Header rewrite (SNAT) needs the
cmd_ram packet-offset unknown (§4) and is refused until then.

## Hardware results (2026-11-15, one unit, RAM boot of a diagnostic `PP_TABLES=1` image)

| step | result |
|---|---|
| 1 build | `CONFIG_ZX279128_PP_TABLES=y` in the merged kernel config; `zx279128-pp.o` linked |
| 2 init | `pp: tables live, pm 0x42500000 acl 0x43000000 (were 0x56409000 0x5f600000)`. `now == programmed` for both bases, and **independently confirmed through `/proc/zx_eth_poke`** (0x923a0020/24), so the PonPp page accepts CPU writes. Engines `enabled=1 faulted=0`. Exact 32 MiB transfers in both directions with the bases programmed |
| 3 first CLA read | `cla_cpu_queue_id[0]` → 4 bytes, `reads=1 timeouts=0`, no stall |
| 4 CLA widened | `cla_extra_index`, `cla_hash0`, `cla_extra_rule` and 64× `cla_cpu_queue_id` all read zero (empty); 71 reads, 0 timeouts |
| 5 PM low | `pm_cmd_ram[0] = 0x00008100` (the 802.1Q TPID: a real non-zero value); `pm_flow_info[0] = 0` |
| 6 PM high bank | `pm_diag[0]` is 32 non-zero bytes. Read with the word order reversed, it is the last forwarded frame's header (destination = bench host MAC, source = router WAN MAC, EtherType 0x0800, `45 00`), so DATA[4..7] at +0x100 returns live state |
| 7 teardown | not run (needs an `=m` build) |
| 8 soak | 60 min: 12 samples, `timeouts=0`, bases stable, 4 exact 32 MiB transfers |

Resolved open questions: the base registers accept CPU writes, and indirect
**read** commands complete without stalling. Still open: write commit
semantics, teardown base clearing, and whether the engine walks the tables
with no flows installed (no change in forwarding was seen over an hour).

## Open questions that block qualification

- Does the PonPp page (0x923a0000) accept CPU writes at +0x20/+0x24? Step 2
  answers this. If it does not, find out how the vendor's own write reaches it
  (`zx_ponreg` `fpga_write_reg` through the same 0xf4000000 mapping), before
  anything else.
- Is clearing the bases to 0 safe while the engine is live, or should the
  teardown restore the found values? The stock image never clears them.
- Will a 4 MiB physically contiguous `dma_alloc_coherent` always succeed at
  probe? CMA is off; this relies on MAX_ORDER = 11 and boot-time memory that is
  not yet fragmented. A failure here is non-fatal, but it would make the feature
  unavailable. A DT `reserved-memory` pool is the fallback.
- Which TOPCRM gate feeds the PP block (design risk §(d)2)? This decides whether
  a module reload can ever see the block gated.

## Hardware forwarding is disabled by design, 2026-11-16

Found while chasing why a correct CLA entry still would not forward. It is a
separate blocker from the match, and it would have bitten whoever got the match
working first.

`zx_eth_software_ports()` deliberately puts the switch into CPU-controlled
forwarding. Among the registers it writes:

```c
/* Vendor mode0 disables source learning. GE0..3 are BRG ports1..4. */
zx_eth_update_bits(brg, 0x1c4, 0x3fc, 0);
for (port = 1; port <= ZX_NPORTS; port++)
        zx_eth_update_bits(brg, 0x3c0 + 4 * port, 0x1e, 0);
```

That second loop zeroes each port's **destination mask**: which other switch
ports a frame from this port may be forwarded to in hardware. Zero means
"forward nowhere in hardware, send everything to the CPU" — which is exactly
what a software router wants and exactly what a hardware offload cannot live
with.

Measured on hardware, ingress GE3 (BRG port 4), row `brg + 0x3c0 + 4*4 =
0x923883d0`:

```
before: 0x000000e1   -> bits 1..4 (the 0x1e destination mask) are all clear
after:  0x000000e3   -> bit 1 set, i.e. GE3 may forward to GE0
```

Setting the bit did **not** produce a CLA match — the classification decision
is upstream of the bridge, so this is not the match blocker. But it is
necessary for a matched flow to be forwarded rather than trapped, and any
offload implementation has to program it per (ingress, egress) pair.

The rest of the zeroed bits in that register (0, 5, 6, 7) are not part of the
destination mask and were left alone.

### What this does not explain

With the ternary rule installed and verified by readback, the corrected match
words, the right enable bit, all 512 slots sprayed, `ip_forward` on and a route
to the probe destination, and this mask set, the aging bit still stayed 0. So
the remaining question is still whether the PP block sees ingress frames at
all — see `docs/PP-KEY.md` sections 8 and 9.

## Cold datapath reset+gate+DPA sequence, 2026-11-16 (owner-authorised)

The owner lifted the "never gate or reset the PP block" rule for this work. The
DPA parse gate (the measured match blocker: `0x92398000` half-set, `TOPCRM+0xc`
bits 1..4 clear) is now armed in the cold bring-up. Implementation, decision
(raw `writel` vs a clk from `zte,zx279128s-crm`), inferences, and the measured
result are in `docs/PP-KEY.md` §17. Summary:

- In `zx_eth_datapath_init()`, after the PP command pulse, gated by
  `CONFIG_ZX279128_PP_TABLES` (off in the shipped config; a release image is
  unchanged): `TOPCRM+0x8` reset pulse → `TOPCRM+0xc |= 0x1e` gate → park the
  PM/ACL bases at `ze->ddr_phys` (hazard mitigation: no engine walks the
  reset-garbage pointers) → DPA `0x92398000 |= 0x1fc0`, `0x92398014 |= 1`.
- Cold-only by construction (the warm-attach path never reaches it); the
  `TOPCRM+0x8` reset never runs on a warm TFTP boot.
- Loud readback: `pr_warn` if the gate does not arm or the DPA enables do not
  latch, so a silent no-op (the §14 failure mode) cannot pass unnoticed.

Note for whoever lands the forwarding half: even once the match flips frames
from `trap` to `fwd`, the per-(ingress,egress) **destination mask** at
`brg + 0x3c0 + 4*port` must be set (see "Hardware forwarding is disabled by
design" above), or a matched flow still will not leave by hardware.

## Stock firmware harvest, 2026-11-17 (owner-authorised bank-B round trip)

Booted the untouched stock firmware (bank B) to answer "does stock offload a
GE↔GE routed flow, and what does a working vendor config write?" Full writeup:
`docs/STOCK-HARVEST.md`. Headlines relevant here:

- **Stock does not present a GE-WAN→GE-LAN flow at all.** The WAN jack (switch
  port 3) is `sw_set_uni_as_wan uni=3` — the PON/fibre uplink — isolated from the
  LAN bridge, no IP, no ARP on any subnet (measured). So there is **no stock
  GE↔GE throughput to quote** (not 900, not 350; no path). The vendor product
  routes WAN(optical)↔LAN(Ethernet); it never routes Ethernet-WAN↔Ethernet-LAN.
  This is consistent with PP-KEY §24–§27: the CLA inner-hash fast path is pointed
  at UNI↔PON, and the vendor never configures it for GE↔GE because the product
  has no such direction.
- **The vendor L2-fast/NPU hardfast engine IS loaded and enabled by default**
  (boot: `l2_fast init`, `reg hff`, `register npu driver 12`), but it serves the
  PON datapath; our Ethernet driver does not instantiate it.
- **Direct register confirmation:** stock's boot prints `PON_PP_TM_CFG
  0x1200000 → 0x11200000`, the *same register and value* our driver writes to
  `0x923a001c` (`tm_set_pp_wan_cfg`, PP-KEY §20) to declare port 3 as WAN. **Our
  WAN declaration matches the vendor working state exactly.**
- **A live register/stat read (`/proc/zte/sys/ffe/ffeinfo`, `devmem2`, the CLA/PM
  counters) was impossible:** stock has a `login:` prompt with a `$5$` root hash
  and no plaintext, and the rules forbid sending secrets over the logged UART.
  The boot log is the shell-free reference; see `docs/STOCK-HARVEST.md` §3, §7.
- **Hazard reconfirmed:** a stock boot corrupts our bank-A rootfs (mtd7); recovery
  needs a full bank-A re-flash, not header-only. `docs/STOCK-HARVEST.md` §6.
