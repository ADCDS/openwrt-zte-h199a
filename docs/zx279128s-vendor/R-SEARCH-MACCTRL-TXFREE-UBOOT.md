> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# R-search: MAC_CTRL fields, TX-buffer freeing, ZX27912x U-Boot board code

Answers to three targeted search requests. Rule followed: every claim names its source and whether
it is vendor code, GPL-released, or community reverse engineering. Explicit "nothing found" is
recorded where that is the answer; nothing is padded.

---

## TARGET 1 — MAC_CTRL `0x00bbe003` bit fields (is `0xe000` speed / port-enable / loopback?)

### Public definition: NOTHING FOUND

- **grep.app** (`https://grep.app/search?q=0x00bbe003`) → "No results found".
  Caveat that limits its value: grep.app's index does not include the small ZTE repos at all — it
  also returns 0 for `zx279133`, a string we know is public in
  `cnjn/linux-mainline-zte-zxslc-sr1010`. So this is a weak negative, not proof.
- **Baidu** (Chinese), query `ZX279128 MAC_CTRL 寄存器 环回`. The results page's own summary states
  verbatim: *"当前公开资料里没有直接给出 ZX279128 芯片 MAC_CTRL 寄存器的环回位定义，也没找到该芯片
  的寄存器手册原文"* ("current public material does not give the ZX279128 MAC_CTRL loopback bit
  definition, and the chip's register manual is not found"). Generic GMAC loopback articles
  (Phytium D2000, TI CPSW, Huawei S-series) came back instead — none about ZX27912x.
- Sanechips product pages are marketing only (no register documentation).

### Vendor evidence (binary, not documentation) — this is the real answer

Source: **vendor U-Boot binary** `uboot-F610GV9.bin` (ZTE ZX279127S/ZX279128S U-Boot 2013.04,
from `celeron633/ZX279127S-Reverse`), load base `0x47EDF800`, our own disassembly. Class: vendor
binary, not recovered GPL source; the analysis is project reverse engineering.

`0x00bbe003` occurs exactly twice in the image — at `0x47f33420` and `0x47f35ae0`, the literal
pools of the **two `smac_init` copies**. Each writes it to offset `+0x00` of a per-port MAC window:

```
47f33354: ldr r3, [pc, #196] @ 0x47f33420   ; r3 = 0x00bbe003
47f33358: add r0, r0, #0x92000000
47f3335c: add r0, r0, #0x1c0000             ; r0 = 0x921c0000 + port*0x40000
47f33364: str r3, [r0]                       ; writel(0x00bbe003, ...+0x00)
```
and the second copy at base `0x92200000 + port*0x40000`
(`47f359e0`–`47f359f4`).

The bit semantics come from the shared helper **`smac_set_speed_duplex` at `0x47f33120`**, which
reads the live register and adjusts three bits:

```
47f33138: ldr  r3, [r0]                ; current MAC_CTRL
47f3313c: biceq r3, r3, #0x8000        ; speed==2 (1000M): clear bit15
47f33140: orreq r3, r3, #0x2000        ;                    set   bit13
47f33144: beq  0x47f33164             ; gigabit skips duplex/bit14 path
47f33148: cmp  r2, #0                  ; duplex
47f3314c: biceq r3, r3, #0x2000        ; duplex==0: clear bit13
47f33150: orrne r3, r3, #0xa000        ; duplex!=0: set bits 15 and 13
47f33154: orreq r3, r3, #0x8000        ; duplex==0: set bit15
47f33158: cmp  r1, #1                  ; speed
47f3315c: orreq r3, r3, #0x4000        ; speed==1 (100M): set bit14
47f33160: bicne r3, r3, #0x4000        ; else clear bit14
```

**Answer: `0xe000` (bits 13,14,15) is the SPEED/DUPLEX field.** Decoded:
- bit13 = full duplex (forced 1 for 1000M)
- bit14 = 100 Mbps versus 10 Mbps in the non-gigabit path; gigabit leaves it unchanged
- bit15 = 1 for 10/100 Mbps, 0 for 1000 Mbps

**Port enable is bit0, not in `0xe000`.** `smac_enable` at `0x47f3316c` does
`orr r3, r3, #3` (sets bit0 **and** bit1); the disable path at `0x47f33438` does
`bic r3, r3, #1` (clears bit0 only). So enable = bit0, with bit1 set alongside it.

### Which bit is MAC loopback? — none found in MAC_CTRL

No MAC-level loopback bit exists in the code paths I have. Where loopback actually lives on this
family, per vendor binaries:

1. **PHY level.** The only `loopback` string in `uboot-F610GV9.bin` (offset 380208),
   `uboot-F663NV9G.bin` (355475) and `uboot-SG631Z.bin` (484434) sits inside the standard IEEE
   802.3 PHY bit-name table:
   `link status / jabber detect / extended capabilities / **loopback** / speed selection / A/N enable / power-down`.
   That is **MII BMCR bit 14 (0x4000)** — the PHY's own loopback, not a MAC register bit.
2. **PCS / SerDes level (newer generation).** The **ZX279132** U-Boot (`uboot-G7615.bin`,
   `CPU : ZX279132@A53`, U-Boot 2016.01-rc3) carries explicit loopback paths:
   ```
   enter loop back PATH1_TX2RX_PCS_LOOP0 / LOOP1 / LOOP2
   enter loop back PATH2_TX2RX_CABLE_LOOP
   enter loop back PATH3_TX2RX_PMA_LOOP
   enter loop back PATH4_RX2TX_PCS_LOOP
   enter loop back PATH5_RX2TX_PMA_LOOP
   enter loop back PATH6_RX_RECEIVE
   ```
   i.e. TX-to-RX, cable, and PMA loopback are **XPCS/SerDes** functions, not MAC_CTRL fields.
3. Our own recovered `spa_set_loopback_en` sits at SPA `0x921d4088` bit 1 — a third, different block.

**Confidence:** high for "`0xe000` = speed/duplex, bit0 = enable" (read directly from vendor
machine code). High for "no MAC_CTRL loopback bit in the ZX279128S family U-Boot"; the loopback
mechanisms found are PHY-BMCR and PCS/SerDes.

---

## TARGET 2 — does any public ZTE Ethernet driver free completed TX buffers?

**Yes — two of them, both ZTE-authored.** This partially contradicts the "vendor never frees TX"
reading, but the architecture is different (see the caveat).

### 2a. `zx29_gmac.c` — ZTE zx2975xx GMAC

URL: <https://github.com/zx297520v3-mainline/linux-5.10/blob/master/drivers/net/ethernet/zte/zx29_gmac.c>
(1853 lines; also `zx29_gmac_event.c`, 298 lines). Class: **GPL / ZTE-authored.**

Header, verbatim:
```c
/*
 * Ethernet driver for zte zx2975xx gmac on chip network device
 * (c)2008 http://www.zte.com.cn
 * Authors:	zhang dongdong <zhang.dongdong16@zte.com.cn>
 *
 * This program is free software; you can redistribute it and/or
```

TX completion, `zx29_gmac_tx()`, verbatim:
```c
static void zx29_gmac_tx(struct net_device *ndev)
{
	...
	struct bd_tx *tx = get_txed_bd(ndev);

	while (tx) {
		status = tx->TDES0;
		if (tx->TDES0 & ERR_TX_ES) {
			... tx_errors / tx_carrier_errors / tx_fifo_errors ...
		}
		dev_kfree_skb_any(tx->skb);
		tx->skb = NULL;
		tx = get_txed_bd(ndev);
	}

	if (netif_queue_stopped(ndev))
		netif_wake_queue(ndev);
}
```
`get_txed_bd()` walks a BD ring (`txed_bd` consumer index, `DMA_OWNER` bit test). It also applies
back-pressure: `netif_stop_queue(ndev)` at lines 841/934/970/1199 and `netif_wake_queue` at
286/537/942.

### 2b. `zx_gmac.c` — same platform, from ZTE's own GPL release

URL: `https://download.ztedevices.com/device/global/support/opensource/9/20211013_01/ZTE_MF296R_opensource_code.tgz`
→ `TSPV3_opensource_code/platform_sdk/tsp/tsp7520v3/replace_code/linux_plat/base/linux-3.4.x/drivers/net/gmac/zx_gmac.c`
(1360 lines). Class: **GPL-released by ZTE** (opensource.ztedevices.com). Same reclaim pattern,
verbatim:
```c
	dev_kfree_skb_any( tx->skb);  //wl
	tx->skb = NULL;
	tx = get_txed_bd(dev);
	...
   if(netif_queue_stopped(dev))
    {
        netif_wake_queue(dev);
    }
```
(The `for (i...) dev_kfree_skb_any(tx_bd[i].skb)` at line 379 is the *teardown* path on close, not
the runtime reclaim.)

### Caveat — this does not directly contradict our finding

Both are **BD-ring** designs in which each TX buffer descriptor owns an skb. "Freeing a TX buffer"
there means `dev_kfree_skb_any()`, **not** returning a buffer pointer to a BM pool. There is no BM
in either driver. So:

- Our observation that `dma_tx_free` has zero callers remains a statement about the **TM/BM
  buffer-pointer** architecture, and these drivers neither confirm nor refute it.
- What they *do* establish: **a ZTE Ethernet driver reclaiming TX on completion and waking the
  queue is normal for this vendor**, and ZTE drivers do apply back-pressure. So "ZTE never frees
  TX" is not a family-wide rule — it is specific to the TM path in the modules analysed.

**Confidence:** very high (both are complete, quotable source files).

---

## TARGET 3 — U-Boot board code for any ZX27912x EVB

### Upstream: definitively nothing

I enumerated the complete `u-boot/u-boot` tree (41,576 entries) and searched for
`zxic` / `zx279` / `zx29` / `sanechips` in any path: **0 matches.** No upstream board port, no
`board_init`, no `ft_board_setup`, no board Ethernet init for this family.

### Public source of the vendor U-Boot: none found (consistent with all earlier rounds)

What exists publicly is **binaries and board strings**, not source:

| Board string | Where |
|---|---|
| `Board: ZXIC zx279128sevb` | `uboot-F610GV9.bin` (and Kanxue ZX279128S log) |
| `Board: zxic zx279128evb` | GM620 bootlog (`AlienWolfX/GM620`) |
| `Board: ZXIC zx279128revb` | OpenWrt STRONG-router bootlog (MF296R attribution unverified) |
| `Board: ZTE zx279127evb` | ChinaDSL ZX279127 log |
| `Board: ZTE zx279132evb` | `uboot-G7615.bin` (ZX279132, A53, U-Boot 2016.01-rc3) |

The board-level Ethernet init for our SoC **is** inside those binaries and is what I disassembled
for Target 1 — vendor machine code, not source. Config file name `zxic_pubconfig.bcb`.
U-Boot version string: `U-Boot 2013.04 (Nov 20 2021 - 12:01:13)`, `GNU ld (GNU Binutils) 2.27`.

---

## Chinese-language searches

Query set: `ZX279128 寄存器`, `ZX279127S 数据手册`, `中兴微 ZX279128 MAC`, `ZX279128S 以太网`,
`MAC_CTRL 环回`.

**Result: nothing found.** Baidu's own summary (quoted in Target 1) states plainly that no public
ZX279128 MAC_CTRL/loopback bit definition and no register manual exist. Returned results were
teardowns, firmware-mod threads, and generic non-ZTE MAC loopback articles. A Chinese forum thread
titled *"ZX27912X这是啥芯片"* (`right.com.cn/thread-8306802`) is only a photo-based "which model is
this?" post with no technical content.

## A search-result artifact to disregard

Search engines repeatedly return an entry titled
`zte/zxic zx279128s onu 芯片 硬件手册 (hardware manual)` whose target is a **local filesystem path**
(`/hdd/m0103/deepseek/datasets/pilimi-zlib/libgen_rs_non_fic/...`), not a URL. It is not
retrievable, and it looks like the search backend surfacing a path from its own dataset. It should
**not** be treated as a source or chased. No such public hardware manual was found.
