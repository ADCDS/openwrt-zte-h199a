> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.
> The MF296R attribution and same-wafer conclusion were not established.
> Domain/portal availability observations are historical and were superseded
> by the later [plural-domain portal investigation](ZTE-GPL-PORTAL.md).

# Vendor archaeology, round 2 — new public artifacts

Research artifact. Everything here is quoted from public sources; nothing is from our own
dump. Where a claim is inference it is labelled.

Companion files:
- `zx279128r-vendor.dts` — full vendor DTS for ZX279128R (the headline find)
- `zx279128s-vendor.dts` / `dtb1_2794768.dtb` — the E2631-era ZX279128S vendor DTB we already had
- `UBOOT-TM-DISASM.md` + `uboot-F610GV9-TM-region.asm` — our own U-Boot TM/SMAC disassembly
- `GPL-SOURCE-HUNT.md` — the negative-result sweep for a public BSP

---

## 1. Headline: a complete vendor device tree for ZX279128R

Source: OpenWrt forum, *"OpenWRT support for STRONG 4G+ ROUTER1200"*, post #1, 2024-06-14 —
<https://forum.openwrt.org/t/openwrt-support-for-strong-4g-router1200/201056>
(full thread also retrievable as `https://forum.openwrt.org/t/201056.json`).

The thread suggested a **rebadged ZTE MF296R**, but that attribution was not
established and later archive research contradicted it —
i.e. a router SoC configuration, the closest public sibling to our H199A.

```
U-Boot 2013.04-svn214847 (Jul 20 2022 - 20:17:43)
CPU  : ZX279128R@A9,800MHZ
Board: ZXIC zx279128revb
Linux version 4.1.25+ (david@ubuntu12) (gcc 4.9.4 (Buildroot 2017.05-svn2186)) #2 SMP PREEMPT
Machine model: ZTE ZX279128R
DRAM: 256 MiB    NAND: ESMT F50L1G41LB 128MiB SPI-NAND
toolchain: arm-buildroot-linux-gnueabi-gcc.br_real 4.9.4, GNU ld (GNU Binutils) 2.27
```

### 1.1 Block map (authoritative, from the DTS `aliases` + node `reg`)

```
pon    @ 0x92000000   reg 0x92000000+0x2000000, +0x140000, 0x94000000, 0x94100000,
                           0x94200000, 0x9fe00000      IRQ 0x1e, 0x1c, 0x22
npp    @ 0x921c0000   reg 0x921c0000+0x8000, 0x921cc000+0x34000   IRQ 0x23, 0x26
idm    @ 0x921c8000   reg 0x92334000+0x4000, 0x921c8000+0x4000   IRQ 0x52, 0x26
sw     @ 0x92300000   reg 0x92300000+0x34000                     IRQ 0x51
tm     @ 0x92340000   reg 0x92340000+0x40000                     IRQ 0x24
pp     @ 0x92380000   reg 0x92140000+0x40000, 0x92380000+0x40000  IRQ 0x50, 0x25
mdio   @ 0x9a101000   reg 0x9a101000+0x18
gephy  @ 0x9b000000   reg 0x9b000000+0x400000                    IRQ 0x20
gephy128/128s         reg 0x9b000000/0x9b100000/0x9b200000/0x9b300000, each +0x100000
fephy  @ 0x9b400000                                                IRQ 0x1d,0x1e,0x1f
```

**This resolves the structure of our own map.** Our driver's sub-blocks all live inside two windows:

- `TMC 0x92340000`, `TMD +0x4000`, `BM +0x8000`, `QMG +0xc000`, `TMQ +0x10000`, `SCH +0x14000`
  are sub-blocks of the single **`tm` window `0x92340000`–`0x9237ffff`** (size `0x40000`), IRQ 0x24.
- Our `SBRG 0x92388000` and `CLA 0x9238c000` are inside the **`pp` window `0x92380000`** (size 0x40000).
- `NPP 0x921c0000` is correct and separate; there is also a second `npp` bank at `0x921cc000+0x34000`.
- `idm` is a *different* block at `0x921c8000` (plus `0x92334000`) — the DMA engine.
- The switch is its own block at `0x92300000` (size `0x34000`), IRQ 0x51.

Device-tree compatibles confirm the multi-generation lineage (same pattern the E2631 DTS shows):
`zte,zx279128s-tm`, `zte,zx27912x-pp`, `zte,zx27912x-idm`, `zte,zx279127-sw`, `zte,zx279128s-npp`,
`zte,zx27912x-pon`, `zte,zx279128s-mdio`, `zte,zx279128-gephy`, `zte,zx279128s-gephy`,
`zte,zx279127-fephy`, `zte,ZX279127-uart`, `zte,ZX27912x-spifc`, `zte,zx279127-i2c`,
`zte,ZX279127-topcrm`, `zte,ZX279127-lsp0crpm`, `zte,ZX279127-lsp1crpm`, `zxic,tempsensor`.

New naming detail worth recording: `spifc@94406000` carries
`reg-names = "spifc_reg_127", "spifc_reg_128s"` — the driver selects a register bank by SoC.

### 1.2 Vendor module list on that device (from `lsmod`)

```
mtk7613e_ap 4602956 2   mt7603e_ap 2083814 3   switch 115501 0
multicast 132436 3      gpondrv 17187 0        netdriver 22737 2
ffe 92891 1             iprt 14365 0           tm_128s 1322953 2
plat_zxic_128s 177685 6 zx_ponreg 2481 3       wan_bridge 42137 1
qos_mod 54280 3         bspdriver 55447 5
```

On-disk `.ko` names and sizes (post #1):

```
tm_128s.ko        1336884      tm_127128.ko      1678408
plat-zxic_128s.ko  157144      plat-zxylzb_12x.ko 189136
switch.ko          155944      ffe.ko             98256
iprt.ko             21516      netdriver.ko       32468
gpondrv.ko          26040      zx_ponreg.ko        5132
wan_bridge.ko       58124      qos_mod.ko         71428
bspdriver.ko        72940      multicast.ko      164216
mapfilter.ko        39396
```

Two observations:
- There are **two TM variants** — `tm_128s.ko` and `tm_127128.ko`. Our stock module `tm.ko`
  (~1.2 MB per Zlion-Y's notes) corresponds to the `tm_128s` size class.
- `plat-zxylzb_12x.ko` / `plat-zxic_128s.ko` are the same family as the `plat-zxylzb_9128S.ko`
  we already have in Ghidra. The `plat-zxylzb_<suffix>` naming is the platform glue for a given
  die variant.

The thread poster also uploaded a **full flash dump** (`rootfs0/rootfs1/kernel0/kernel1/wlan/
middleware`, JFFS2) to Proton Drive, and posted the partition table:

```
mtd1 u-boot   0x000000-0x200000     mtd7  usercfg   0x0c00000-0x1400000
mtd3 kernel0  0x200000-0x700000     mtd9  wlan      0x1500000-0x1800000
mtd4 kernel1  0x700000-0xc00000     mtd10 middleware 0x5800000-0x6000000
mtd5 rootfs0  0x1800000-0x3800000   mtd11 versionbackup 0x6a00000-0x8000000
mtd6 rootfs1  0x3800000-0x5800000
```

**Value to us: moderate, not high.** We already have our own dump of the same silicon family
(`/tm.ko`, `/plat-zxylzb_9128S.ko` in the `h199a-vendor` Ghidra project). This is a *second
sample* — a different build of the same architecture, useful as a cross-check for register
sequences and for the `tm_127128` variant we do not have. The **DTS was the real prize**, because
it is metadata our own dump did not give us cleanly.

---

## 2. GM620 bootlog — vendor symbol names and the BM allocator call chain

Source: <https://github.com/AlienWolfX/GM620> — *"Reverse Engineering of China Mobile GM620"*,
BSD-3-Clause, created 2026-02-09, single 141 KB `bootlog.txt`. SoC `ZX279128@A9,800MHZ`,
board `zxic zx279128evb`, Linux `4.1.25+ #10`.

### 2.1 Full module list

```
Modules linked in: dsp_dev voip_codec kudp optical switch multicast gpondrv zte_gpon
                   netdriver ffe iprt tm zx_ponreg wan_bridge qos_mod bspdriver
```

### 2.2 A real kernel oops, with the BM allocator call chain

```
WARNING: CPU: 1 PID: 658 at kernel/softirq.c:150 __local_bh_enable_ip+0xb0/0xdc()
Hardware name: ZTE ZX279128 (Device Tree)
[<c0033ea4>] (__local_bh_enable_ip) from [<c00206d0>] (pp_bmu_alloc_bp+0x8c/0xec)
[<c00206d0>] (pp_bmu_alloc_bp) from [<c0021b00>] (lower_alloc_skb_bp+0x14/0x54)
[<c0021b00>] (lower_alloc_skb_bp) from [<c037782c>] (__alloc_skb+0x78/0x1e4)
[<c037782c>] (__alloc_skb) from [<c03cdba8>] (MontorSendMsgInner+0xb0/0x21c)
[<c03cdba8>] (MontorSendMsgInner) from [<c03cdd78>] (monitor_timer_handler+0x64/0x104)
```

This is directly relevant to our work:
- **`pp_bmu_alloc_bp` is the vendor's BM allocator** — the same function family as the
  `pp_bmu_free_bp` we recovered. Its **size is `0xec` bytes** and it begins at `0xc0020644`
  in that build.
- **`lower_alloc_skb_bp` (size `0x54`) is its caller**, and it is called *from inside
  `__alloc_skb`*. The vendor has interposed the BM on the skb allocation path at the "lower"
  (lower-MAC) layer.
- The warning is `local_bh_enable` from softirq context — i.e. the BM allocator performs a
  bottom-half-enabling operation that is illegal when called from a timer softirq. That is a
  **vendor bug**, and it tells us `pp_bmu_alloc_bp` does a spin_unlock_bh-style sequence.

Our `zx_bm_alloc()` is the reimplementation of `pp_bmu_alloc_bp`; the `0xec`-byte size is a
useful sanity bound when re-reading the disassembly.

### 2.3 Port numbering and netdev mapping

```
ethdrv_dev_ioctl, brdev_set.port_id 0, brdev_set.name eth0
ethdrv_dev_ioctl, brdev_set.port_id 1, brdev_set.name eth1
ethdrv_dev_ioctl, brdev_set.port_id 2, brdev_set.name eth2
ethdrv_dev_ioctl, brdev_set.port_id 3, brdev_set.name eth3
```

**`port_id N → ethN`.** Our board's netdev is `eth2`, so under the vendor mapping that is
`port_id 2`. The same log shows `si_gpon_lanup_set_db lan_up_mode=0x0 lan_up_port=4`, consistent
with the port range 0..4 we found in our own U-Boot SMAC code (`cmp r0, #4`).

Also present (RX-side port ids in an skb metadata field):

```
pdt_ethdrv_recv meet error pdev==NULL || pdev->reg_state== 0, skb->pdt_info.port=15.
pdt_ethdrv_recv meet error pdev==NULL || pdev->reg_state== 0, skb->pdt_info.port=23.
```

So the vendor carries a **`port` field in `skb->pdt_info`** and values 15 (0x0f) and 23 (0x17)
appear on receive. These are *not* the 0..3 LAN port ids — (inference) they are internal
PON/CPU port ids in a different numbering space, which is consistent with the destination field
being an internal port id rather than a PHY index.

### 2.4 Vendor source filenames leaked in log lines

`zte_sw_api.c` (2×), `dbl_api.c`, `oss_timer.c`, `osgid_comm.c`, `e8_dhcps.c`, `my_dmenu.c`,
`oss_sche.c`, `oss_comm.c`, `oss_common.c`, `ifs_notifier.c`, `route_mgr.c`, `route6_mgr.c`,
`igmp_proxy.c`, `dss_main.c`, `dns_mgr.c`, `cfgchk_mgr.c`, `qos_mgr.c`, `rm_mgr.c`,
`samba_mgr.c`, `tr069_main.c`, `wlan_config.c`, `pdt_*`.

`zte_sw_api.c` is the switch API source file — a good fingerprint for a leaked tree.

### 2.5 Network bring-up sequence (verbatim ordering)

```
[TM][ppglb_set_acl_base]input: base=0x5da20000
upa_set_rr_mask_cfg input: upa_rr_mask = 0x2ab
tm_pp_initial start / finish
tm_switch_initial----start / finish
tm_initial successed !!!
enter tm_sdk_init / exit tm_db_init / tm_initModule end...
iprt_data_init success!
ethdriver_init....
g_mii_dev_name[0] sw        g_mii_dev_name[1] pon
zteGpmac_initModule begin   GponMac Supported MaxTcont: 16 MaxPLI: 800B
zx279100_gpon_Init ok
Init switch module
zy switch detected boardtype:192
zy uni num:4
switch config 9127/9128 GPON mode!
[SW][sw_init_switch] reg hff
[zte_sw_api.c] tm_add_acl_flow_rule FAIL!
```

Notes: the switch driver self-identifies as handling **"9127/9128"** (ZX279127 / ZX279128), and the
GPON init function is named **`zx279100_gpon_Init`** — matching the historical OpenWrt target names
`zx2791` / `zx279100`. `tm_pp_initial` runs before `tm_switch_initial`.

---

## 3. The Kanxue "279128 SDK source" claim — verified, but weak

Thread: <https://bbs.kanxue.com/thread-276970.htm> (98 replies; several pages).

**Post #78, 2024-07-25 23:03, user `mb_buiexhfs`:**

> 本人有279128芯片产品sdk源代码，可以无偿提供，哪位大神需要分析可以联系我

*"I personally have the 279128 chip product SDK source code, and can provide it free of charge;
any expert who wants to analyse it can contact me."*

Context that matters:
- That account has **1 post, 0 coins, 3 followers, joined for that single message** — and never
  posted again in the thread.
- **Nobody in the thread reported receiving anything.**
- Two people asked for contact details and got no visible reply:
  - **post #81, 2025-03-03, `mb_liyhznlb`** — "请问如何联系 我的邮箱 chihaya-anon@outlook.com。
    我手里有279128开发板和带调试口的光猫。" (*how do I contact you; I have a 279128 dev board and
    an ONU with a debug port*) — email `chihaya-anon@outlook.com`.
  - **`jschwart` = Julius Schwartzenberg**, `julius.schwartzenberg@eclipso.eu` — a *legitimate*
    mainline contributor (author of the `zx297520v3` kernel fork on GitLab,
    <https://gitlab.com/jschwartzenberg/zx297520-kernel>). He wrote: *"I am looking around for SDKs
    related to the ZX27/ZX29 chips... Devices with these chips are quite common, but source code
    does not seem to be available despite the GPL requirements."* He appears on page 4 and again
    around 2025-11-02, i.e. **still asking a year later** — so he most likely never got it either.

**Assessment:** the offer is real as a post but unverified and apparently unfulfilled. A
single-post throwaway account that nobody could reach is not a credible source. However,
Schwartzenberg is a genuine, reachable person working the same problem, and `mb_liyhznlb` has a
dev board plus a debug-port ONU — both are more useful contacts than the original claimant.

---

## 4. Assessment of the third-party "deep research report"

A separate researcher's report (`~/Downloads/deep-research-report.md`) reached the same central
conclusion: no public vendor BSP; a mosaic of scaffolding, binaries, recovered configs and one
partial mainline port. Points where it needs correcting:

| Report claim | Status |
|---|---|
| `https://opensource.ztedevices.com/` is the ZTE open-source portal | **Superseded availability inference.** The plural-domain portal was later found working; see `ZTE-GPL-PORTAL.md`. `www.ztedevices.com/opensource` → 404; `opensource.ztedevice.com` (singular) is NXDOMAIN. The working channel is `Open.Source@zte.com.cn` per ZTE's own notice, newsId=1037164. |
| U-Boot source breadcrumb `board/zxic/zx279128sevb/`, `arch/arm/cpu/zx279128s/` | **Uncited and not reproducible.** GitHub repo + commit searches return nothing. Treat as unverified; possibly fabricated. |
| `Zlion-Y/openwrt-zx279128-e2631` exists | It **404s** now (deleted). Software Heritage had not indexed it when I checked (SWH rate-limited; retry worthwhile). |
| Chip/board facts (`ZX279128R` = same wafer as S, router SoC; EVB names; U-Boot 2013.04 lineage) | **Partly supported programming similarities; same-wafer identity was not established.** |
| The Kanxue SDK lead | **Confirmed with post number and date** (see §3), but weaker than "low-to-medium" suggests — it is an unreachable one-post account. |
| No mention of the ZX279133 driver tree | **Omission.** `cnjn/linux-mainline-zte-zxslc-sr1010` is the closest public *source* for a sibling chip and the origin of our BMU/BPPE insight. |

---

## 5. New search fingerprints (all currently returning nothing public)

From our own work and the artifacts above. Any leak will contain one of these:

**Kernel config symbols** (from the recovered ZX279128S `.config`):
`CONFIG_ZX_TM`, `CONFIG_ZX_PON`, `CONFIG_ZX_MDIO`, `CONFIG_ZX_RESERVE_MEM`,
`CONFIG_ZX_NET_ZERO_COPY`, `CONFIG_ZX_NET_MAX_MTU`, `CONFIG_ZX_EX_SHAREINFO`,
`CONFIG_ZXICKERNEL_NET`, `CONFIG_ZXICKERNEL_FLOW_CMCC`, `CONFIG_ZXICKERNEL_CMCC_VLANDROP`,
`CONFIG_CMCC_SMART`, `CONFIG_ZX279128S_ASIC`, `CONFIG_ARCH_ZX279128S`,
`CONFIG_MTD_NAND_ZTE_DENALI`, `CONFIG_MTD_NAND_ZTE_SPIFC`, `CONFIG_USB_DWC3_ZX279128S`,
`CONFIG_PRINTK_SLICE_SUPPORT`, `CONFIG_GN25L95_MCU_MODE`

**Function / file names** (from the GM620 bootlog and our disassembly):
`zte_sw_api.c`, `pdt_ethdrv_recv`, `lower_alloc_skb_bp`, `pp_bmu_alloc_bp`, `pp_bmu_free_bp`,
`tm_switch_initial`, `tm_pp_initial`, `tm_initModule`, `zx279100_gpon_Init`,
`zteGpmac_initModule`, `g_mii_dev_name`, `sw_init_switch`, `ethdrv_dev_ioctl`,
`pon_tm_net_tx`, `pon_tm_bmu_init`, `sbrg_set_qnum_map_mode`, `spa_set_loopback_en`, `smac_init`

**Board / build names:**
`zx279128evb`, `zx279128sevb`, `zx279128revb`, `zx279127evb`, `zx279127sevb`,
`zxic_pubconfig.bcb`, `arch/arm/cpu/zx279128s`, `board/zxic/zx279128sevb`,
`arm-buildroot-linux-gnueabi`, `zxylzb`, `plat-zxylzb_9128S`

**Register constants:** `0x00bbe003` (vendor SMAC MAC_CTRL), `0x0104c040` (BMU BPPI/BPO threshold)

**Search surfaces tried and exhausted:** GitHub (repos + commits; *code* search needs auth),
grep.app (index too small — returns 0 even for `zx279133`), gitcode/AtomGit (0), Gitee (hard
captcha), Sourcegraph (firewall block), Software Heritage, CSDN, lore.kernel.org (0 for both
`zx279128` and `zx279133`, validated against `zx296702`), patchwork, DuckDuckGo, Baidu, Bing,
Yandex, Mojeek, searchcode (product pivoted), 一牛网/16rd (paywalled), ZTE GPL portal addresses that failed during that search; later plural-domain discovery superseded this result.

---

## 6. Best remaining routes to actual source

1. **ZTE's GPL compliance channel — `Open.Source@zte.com.cn`.** From ZTE's own Open Source
   Software Notice (<https://support.zte.com.cn/support/news/NewsDetail.aspx?newsId=1037164>):
   *"We will provide you and any third party with the source code of the software licensed under
   an open source software license which requires to do so ... detailing the name of the product
   and the firmware version ... THIS OFFER IS VALID FOR THREE YEARS FROM THE MOMENT WE
   DISTRIBUTED THE PRODUCT ... E-mail: Open.Source@zte.com.cn"*. Name the product (ZXHN H199A)
   and the exact firmware version. This is the only route with a legal obligation behind it.
2. **Sanechips technical support** — `zxicsupport@sanechips.com.cn` (from the third-party report;
   not independently verified by me), plus the PON-chipset support page. Ask by chip + board +
   firmware and name the blocks: `ZX_TM`, `ZX_MDIO`, GEPHY, PCHY, `ZX279127-*` compatibles.
3. **Julius Schwartzenberg** (`julius.schwartzenberg@eclipso.eu`) — legitimate mainline
   contributor chasing ZX27/ZX29 SDKs; knows the terrain and may have partial artifacts.
4. **`mb_liyhznlb`** (`chihaya-anon@outlook.com`) — has a 279128 dev board and a debug-port ONU.
5. **Retry Software Heritage** for the deleted `Zlion-Y/openwrt-zx279128-e2631`.
