> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# ZX279128S TM/BM Ethernet driver inside ZTE U-Boot — disassembly notes

Source binary: `uboot-img/ZX279127S/uboot-F610GV9.bin`
(from https://github.com/celeron633/ZX279127S-Reverse)
2,097,152 bytes. **Not encrypted** (plain ARM A32, no Thumb).

Load base **0x47EDF800** — independently confirmed: computing `VA = 0x47EDF800 + file_offset`
for the Ethernet debug strings yields pointers that really occur as literal-pool words in the image.

Reproduce:

```sh
BASE=0x47EDF800; START=0x47f30000; END=0x47f36200
dd if=uboot-F610GV9.bin of=region.bin bs=1 skip=$((START-BASE)) count=$((END-START))
arm-none-eabi-objdump -D -b binary -m arm --adjust-vma=$START region.bin
```

`file_offset = VA - 0x47EDF800`. Full listing kept as `uboot-F610GV9-TM-region.asm`.

The image contains vendor code for **both** SoCs and branches on the chip-ID strap at
`0x92040000` against `0x27912810` (ZX279128) and `0x27912710` (ZX279127).
Everything below is the **ZX279128** path.

## Register bases found as literals

| Address | Meaning |
|---|---|
| `0x92040000` | chip-ID / strap register |
| `0x92340000` | TMC |
| `0x92344000` | TMD |
| `0x92348000` | BM (BMan) |
| `0x92350000` | TMQ |
| `0x41000000` | normal buffer pool (TX payload = base + bp*2048 + 16) |
| `0x41400000` | second buffer pool base |
| `0x41800000` | normal BPPE free-list table |
| `0x41808000` | jumbo BPPE free-list table |
| `0x41A00000` | RX ring |
| `0x41C00000` | TX ring (ZX279128) |

## Function map

| VA | Role |
|---|---|
| `0x47f342ec` | **BMU init** (thresholds, index-max, BPPE seeding) |
| `0x47f345d4` / `0x47f345e8` | `bm_disable()` / `bm_enable()` — `BM+0x00 = 0 / 1` |
| `0x47f345fc` | **`alloc_bp()`** |
| `0x47f3466c` | **`free_bp()`** |
| `0x47f346d4` | RED indirect write helper |
| `0x47f347e4` | **TMD command + GO** (`TMD+0x68`, `TMD+0x64`) |
| `0x47f3486c` | RED queue init (ram 0 x400, ram 2 x384, ram 4 x384) |
| `0x47f34964` | **`insert_desc()`** — flush + `TMQ+0x64` doorbell |
| `0x47f349f4` | queue/TMQ config |
| `0x47f34a4c` | **top-level TM init** (calls the above in order) |
| `0x47f34ae8` | **TX reclaim** — reads `TMQ+0x68` |
| `0x47f3507c` | debug dumper printing `pon_tm_tx_dn_index` |
| `0x47f35104` | **ZX279128 TX build + send** |
| `0x47f35228` | ZX279127 TX build + send (other encoding) |
| `0x47f35350` | **`get_next_txdesc()`** — TX index, ring depth, template |
| `0x47f354e8` | ring-base table init |
| `0x47f355a8`, `0x47f3567c` | later init stages |

## BM registers (ZX279128)

| Offset | Value written | Meaning |
|---|---|---|
| `+0x00` | 0 then 1 | enable |
| `+0x04` | `0x0104c040` | BPPI threshold |
| `+0x08` | `0x0104c040` | BPO threshold |
| `+0x0c` | read | alloc index; **bit31 = valid**, low 16 bits = index |
| `+0x10` | index | free |
| `+0x14` | 1 (request) / 0 | request handshake |
| `+0x48` | `0x08000000` | — |
| `+0x4c` | `0x02000000` | — |
| `+0x58` | `63` | index max = (2048 >> 5) - 1 |
| `+0x5c` | `15` | index max = (512 >> 5) - 1 |
| `+0xdc` | read | free credit, decode `(v >> 3) & 0x3f` |

ZX279127 uses `+0x58 = 511`, `+0x60 = 0x40000000`, `+0x64 = 0x02000000`.

## TMQ / TMC / TMD (ZX279128)

| Register | Value |
|---|---|
| `TMQ+0x54` | doorbell on ZX279127 |
| `TMQ+0x58` | completion counter on ZX279127 |
| `TMQ+0x60` | TX ring base = `0x41C00000` |
| `TMQ+0x64` | **doorbell — `writel(1, ...)`, a bit not a count** |
| `TMQ+0x68` | **completion counter (16-bit), ZX279128** |
| `TMQ+0x1fc` | status, masked with 3 before enqueue |
| `TMC+0x04` | `16` |
| `TMC+0xe8` | `0x41800000` normal BPPE base |
| `TMC+0xec` | `0x41808000` jumbo BPPE base |
| `TMC+0xf0` | `0x41A00000` RX ring |
| `TMC+0xf4` | `0x41000000` buffer pool |
| `TMC+0xf8` | `0x41400000` second pool |
| `TMC+0xfc` | `0x08000800` |

## The BPPE seeding (ZX279128S, `0x47f3438c`-`0x47f343b8`)

```asm
47f34368: ldr  r3,  [pc, #580] @ 0x47f345b4   ; r3  = 0x47f62308 (driver RAM)
47f3436c: ldr  r1,  [pc, #580] @ 0x47f345b8   ; r1  = 0x41800000
47f34370: ldr  r12, [pc, #580] @ 0x47f345bc   ; r12 = 0x417ffffe
47f34374: str  r1,  [r3]                       ; drv[0x00] = 0x41800000
47f34378: str  r1,  [r3, #4]                   ; drv[0x04] = 0x41800000
47f3437c: add  r1,  r1, #32768  @ 0x8000       ; r1 = 0x41808000
47f34380: str  r1,  [r3, #8]                   ; drv[0x08] = 0x41808000
47f34384: str  r1,  [r3, #12]                  ; drv[0x0c] = 0x41808000
47f34388: mov  r1,  #0
47f3438c: rev16 lr, r1                         ; big-endian 16-bit index
47f34390: add  r1,  r1, #1
47f34394: cmp  r1,  #2048  @ 0x800
47f34398: strh lr,  [r12, #2]!                 ; store at r12+2, r12 += 2
47f3439c: bne  0x47f3438c                      ; -> 2048 entries at 0x41800000
47f343a0: ldr  r12, [pc, #536] @ 0x47f345c0   ; r12 = 0x41807ffe
47f343a4: mov  r1,  #0
47f343a8: rev16 lr, r1
47f343ac: add  r1,  r1, #1
47f343b0: cmp  r1,  #512   @ 0x200
47f343b4: strh lr,  [r12, #2]!
47f343b8: bne  0x47f343a8                      ; -> 512 entries at 0x41808000
```

The `strh ..., [r12, #2]!` pre-increment is why the literals are `base - 2`.
Net effect: `*(u16_be *)(0x41800000 + 2*i) = i` for i in 0..2047, and
`*(u16_be *)(0x41808000 + 2*i) = i` for i in 0..511 — written **before** the BM is enabled.

ZX279127 seeds **16384** normal entries (`cmp lr, #16384`, `0x47f34404`) plus 512 jumbo,
and uses `drv[0x14]/[0x1c]/[0x24]/[0x2c]` as the base pair.

## TX descriptor (ZX279128, template written at `0x47f35480`)

```asm
47f35470: mov  r0, #128        @ 0x80          ; word0 = 0x00000080
47f35474: mov  r1, #32768      @ 0x8000        ; word1 = 0x00008000
47f35478: mov  r3, #16777216   @ 0x1000000     ; word2 = 0x01000000
47f3547c: mov  lr, #2                          ; word3 = 0x00000002
47f35480: stm  r2, {r0, r1, r3, lr}
```

ZX279127 template is `{0x02000080, 0x00010000, 0x00200000, 0x00000002}`.
The word0 destination field (bits[25:20]) is **0** on ZX279128S and is never rewritten.

bp / length packing in `0x47f35104`:

```asm
47f35148: lsl  r5, r6, #11          ; bp * 2048
47f35150: add  r5, r5, #0x41000000
47f35158: add  r5, r5, #16          ; buf = 0x41000000 + bp*2048 + 16
47f35170: bfi  r3, r6, #1, #7       ; desc[7] bits[7:1] = bp & 0x7f
47f35178: asr  r3, r6, #7
47f3517c: strb r3, [r4, #8]         ; desc[8] = bp >> 7
47f35184: bfi  r3, r2, #2, #14      ; halfword[+12] bits[15:2] = len
```

i.e. `bp = (desc[7] >> 1) | (desc[8] << 7)`, `len = (u16 at desc+12) >> 2` — this is the
**ZX279128** encoding. ZX279127 uses `halfword[+8] bits[14:0] = bp` instead.

Ring geometry: **depth 1024**, **stride 16 bytes** (`lsl #4`), base `0x41C00000`.
`TMQ+0x68` completion is read as a 16-bit count and subtracted from a software pending
counter (`drv[0x00]`) which is compared against 1024 to decide "ring full".

## Strings (file offsets are decimal)

| file off | VA | string |
|---|---|---|
| 412858 | `0x47f444ba` | `init fe_phy first!` |
| 412901 | `0x47f444e5` | `red queue %d cfg ram 0 failed,%d` |
| 412935 | `0x47f44508` | `red queue %d cfg ram 2 failed,%d` |
| 412969 | `0x47f4452b` | `red queue %d cfg ram 3 failed,%d` |
| 413020 | `0x47f4455c` | `init bmu moduel failed %d` |
| 413292 | `0x47f4466c` | `alloc bp failed` |
| 413337 | `0x47f44699` | `send len %u, BP %d ,addr %x` |
| 413366 | `0x47f446b6` | `insert desc failed` |
| 413386 | `0x47f446ca` | `get tx desc failed` |
| 413435 | `0x47f446fb` | `sqmg queue %d cfg failed,%d` |
| 413498 | `0x47f4473a` | `-----smac_init` |
| 413766 | `0x47f44846` | `after pon_tm_qmg_init` |
| 413825 | `0x47f44881` | `bp %u gem %u len %u total_rx_cnt_128s=%d` |
| 413867 | `0x47f448ab` | `bp %u gem %u len %u   total_rx_cnt_127s=%d` |
| 413929 | `0x47f448e9` | `pon_tm_tx_dn_index=0x%x` |
| 413990 | `0x47f44926` | `bp %u gem %u len  %u dir %u Pkt_Len_Changed %u` |
| 414038 | `0x47f44956` | `invalid tx bp %d` |

Descriptor field names from the dumper at `0x47f3507c`:
`bp` = halfword[+8] & 0x7fff, `gem` = halfword[+4] & 0xfff, `len` = halfword[+12] >> 2,
`dir` = desc[10], `Pkt_Len_Changed` = desc[11] >> 7.

`pon_tm_tx_dn_index` is **not** an MMIO read — the dumper loads `*(drv + 0x50)` from the
driver's own RAM struct at `0x47f6235c`, and `0x50` is the TX descriptor index incremented
mod 1024 by `get_next_txdesc`. The hardware completion source is `TMQ+0x68` (ZX279128) or
`TMQ+0x58` (ZX279127), read at `0x47f34afc` / `0x47f34b18`.

## Not yet analysed

`0x47f342ec` is done. Still unread: `0x47f349f4`, `0x47f355a8`, `0x47f3567c`, and the
SMAC/MAC init reached from `0x47f33428` / `0x47f35ae4` (`-----smac_init`, two copies).
