> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.
> This records a dated search, not proof that vendor source never existed or
> a current legal/product conclusion. The later [portal investigation](ZTE-GPL-PORTAL.md)
> supersedes the singular-domain availability findings.

# ZX279128S / ZXIC TM-BM Ethernet — public source hunt (2026-09-11)

**Recorded search result:** no matching vendor source for the ZX279128S
TM/BM Ethernet block was found in the sources queried on 2026-09-11.
This is not proof that no source existed, and the present recipe now contains
a project-developed driver. The sibling ZX279133 GPL driver was useful for
architectural comparison, not as a portable register map.

---

## 1. ZTE contact and availability observations at the search date

The queried singular-domain addresses returned NXDOMAIN during that search.
The later plural-domain portal investigation superseded the availability
conclusion. A source-request notice found then included an e-mail route; its
applicability to a particular product/firmware was not established here. Verbatim from ZTE's own Open Source Software Notice
(<https://support.zte.com.cn/support/news/NewsDetail.aspx?newsId=1037164>,
mirror <https://supporthk.zte.com.cn/support/news/NewsDetail.aspx?newsId=1037164>):

> 1 OFFER of Source for Open Source
> This product from ZTE contains software whose rights holders license it on the
> terms of open source software licenses. We will provide you and any third
> party with the source code of the software licensed under an open source
> software license which requires to do so, if you want to obtain a copy of this
> kind of open source code contained in this product shipped on CD-ROM for a
> charge no more than the cost of performing such distribution, please contact
> us with email, detailing the name of the product and the firmware version for
> which you need the source code and indicating how we can contact you.
>
> THIS OFFER IS VALID FOR THREE YEARS FROM THE MOMENT WE DISTRIBUTED THE PRODUCT
> AND VALID FOR AS LONG AS WE OFFER SPARE PARTS OR CUSTOMER SUPPORT FOR THAT
> PRODUCT MODEL.
>
> Contact information for requesting source code
> E-mail: Open.Source@zte.com.cn

The offer is version-scoped. For the H199A / ZX279128S the request must name the
product (e.g. `ZXHN H199A`) **and the firmware version string**, and the unit
must still be within the 3-year / spare-parts window. Note `SESSION-JOURNAL.md`
records an earlier guess of `tech.sp@zte.com.cn`; the address printed in the
notice itself is `Open.Source@zte.com.cn`.

---

## 2. Ranked candidates

### #1 — `cnjn/linux-mainline-zte-zxslc-sr1010` (GPL-2.0, the only real driver source)
<https://github.com/cnjn/linux-mainline-zte-zxslc-sr1010> — branch `codex/sr1010-mainline`
(also `build`). Linux 6.18.38 base, ~465 MB tree, 31 stars, pushed 2026-09-05.

Ethernet driver inventory (`drivers/net/ethernet/zte/`, 12,459 lines total):

| file | lines | role |
|---|---|---|
| `zx279133.h` | 808 | full register map + vendor provenance comments |
| `zx279133-tm.c` | 909 | **traffic manager**: NPPT reset, GREG, DMA, **BMU**, QMG, RED, SCH, UOPC |
| `zx279133-np.c` | 1965 | NPPT/SPA/PPU tables |
| `zx279133-idm.c` | 1344 | IDM packet DMA |
| `zx279133-netdev.c` | 1695 | netdev, page_pool RX, TX reclaim |
| `zx279133-mac.c` | 687 | XMAC/SMAC, XPCS SGMII/2.5G |
| `zx279133-main.c`, `-offload.c`, `-ptp.c`, `-lan-conduit.c`, `-rtl8372n.c` | | probe, flow offload, PTP, LAN conduit, RTL8372N DSA |

The header comments prove it was reverse-engineered from the **ZX279133 vendor
kernel modules** — `np.ko`, `switch.ko`, and `kernel-2b5.elf` are named
explicitly (11 references to `np.ko`). Recovered vendor function names quoted in
the comments include:

```
tm_red_buffer_initial()      tm_sw_lan_up_pon_set()      spa_init()
np_ppu_init()                idm_init()                  idm_cfg_int()
idm_cpu_nb_tx_update()       idm_get_tx_done()           smac_reset()
xmac_flow_send_ctrl_set()    xmac_init_by_work_mode()    xamc_init_conf_by_speed()
xpcs_2p5gbase_x_conf()       red_ind_write()             se_smmu0_read()
se_smmu0_write()             se_hash_ddr_init()          ppu_cluster_set_me_val_by_flow_num()
```

`tm_red_buffer_initial` and `tm_sw_lan_up_pon_set` are **the same `tm_` module
family** as the ZX279128S `tm.ko` — strong evidence of a shared TM design
lineage. Verbatim register-level sample (`zx279133-tm.c`):

```c
writel(1, eth->base + ZX279133_BMU_ENABLE);
writel(0x01058080, eth->base + ZX279133_BMU_BPPI_THRESH);
...
/* tm_red_buffer_initial(): 401-queue RED buffer configuration. */
static void zx279133_red_buffer_prepare(struct zx279133_eth *eth)
```

**Caveat:** this is the *ZX279133*, an ARM64 A53 SoC. Its bases are
`nppt@0x19000000` + `pps@0x18000000`; it is **not** the ZX279128S map (see §3).

### #2 — `Zlion-Y/e2631-mainline-zx279128s` (exact SoC, driver NOT started)
<https://github.com/Zlion-Y/e2631-mainline-zx279128s> — Linux 6.18.38 tree for
the ZTE ZXHN E2631 / **ZX279128S**, boots to busybox on hardware. 278 MB.

Contains `arch/arm/boot/dts/zte/zx279128s-e2631.dts` (NAND/SPIFC/PCIe/MDIO/
GEPHY nodes present but `status = "disabled"`) and
`arch/arm/configs/zx279128s_e2631_defconfig`. It vendors cnjn's 16-patch
ZX279133 series under `upstream-series/` (patch 0013 =
`net-ethernet-zte-add-ZX279133-NPPT.patch`, 206 KB) purely as *reference*.

Its own README states the truth plainly:

> | **Wired network driver** | ❌ not started (next goal) | GEPHY (4x 1G PHY) + `zx279128s-mdio` controller + TM/NPP/PP packet engine. Reference: reverse-engineer vendor `tm.ko` (1.2MB)/`switch.ko` (223KB) |

So as of 2026-08-31 the ZX279128S TM/BM port had **not been written by anyone**.

### #3 — `celeron633/ZX279127S-Reverse` (binary evidence, no source)
<https://github.com/celeron633/ZX279127S-Reverse> — 3 stars.
`mtd-img/F610GV9/kernel1.bin` (39,845,888 B) and U-Boot images for
ZX279127S/ZX279133. No source code. Two things are still useful:

* The **unencrypted appended FDT** at offset `0x2aa510` (2,794,768) is a
  `ZTE ZX279128S` device tree. Already extracted and documented in
  `docs/ETHERNET.md` §"The ZX279128S datapath memory map"; a clean `dtc`
  decompile is checked in beside this file as `zx279128s-vendor.dts`.
* `uboot-img/ZX279127S/uboot-F610GV9.bin` (2 MiB) is **not** encrypted: entropy
  is 4.8 over the first 600 KB and the tail is padding. Its `.rodata` string at
  offset ~413,000 exposes the vendor's own Ethernet init sequence:

```
412858 init fe_phy first!
412878 failed to rls rx desc
412901 red queue %d cfg ram 0 failed,%d
413020 init bmu moduel failed %d
413435 sqmg queue %d cfg failed,%d
413464 mac %d phy status changed: %s %s
413498 -----smac_init
413766 after pon_tm_qmg_init
413911 invalid rx bp %u
413929 pon_tm_tx_dn_index=0x%x
413990 bp %u gem %u len  %u dir %u Pkt_Len_Changed %u
```

That is a directly disassemblable ARM image containing `pon_tm_*`, `smac_init`,
`bmu`, `red queue` and `qmg` code for the **same TM/BM block** — and unlike
`kernel1.bin` it is not AES-CBC wrapped.

### #4 — `xuejian1354/openwrt_cc` @ `gateway-3.0` (targets only, no drivers)
<https://github.com/xuejian1354/openwrt_cc> — vendor ChaosCalmer fork with
`target/linux/{zx2791,zx279100,zx279127,zx279128,zx279131,zxic127,zxic128}/Makefile`.
All are stubs: `ARCH:=arm`, `KERNEL_PATCHVER:=3.18`, Cortex-A9/A5, no
`config-3.18`, no patches directory, no SDK tarball URL. Confirms the ZTE SDK is
not reachable from the repo.

### #5 — stubs / dead
* `yanleic/immortalwrt-zxic27913x` — 25-byte README, `LICENSE` only.
* `ynbl07/openwrt-zx279128-e2631` — already tracked by this project; UART-only.
* `Zlion-Y/openwrt-zx279128-e2631` — appears in search-engine indexes but the
  GitHub API and HTTPS both return **404** (deleted/renamed); not in Software
  Heritage either.

---

## 3. Is the ZX279133 Ethernet block the same design? — related, not identical

Observed (vendor DTS, `dtc` output checked in as `zx279128s-vendor.dts`):

```dts
npp@921c0000       reg = <0x921c0000 0x8000>, <0x921cc000 0x34000>;  "zte,zx279128s-npp"
sw@92300000        reg = <0x92300000 0x34000>;                        "zte,zx279127-sw"
tm@92340000        reg = <0x92340000 0x40000>;                        "zte,zx279128s-tm"
pp@92380000        reg = <0x92140000 0x40000>, <0x92380000 0x40000>;  "zte,zx27912x-pp"
idm@921c8000       reg = <0x92334000 0x4000>, <0x921c8000 0x4000>;    "zte,zx27912x-idm"
mdio@9a101000      reg = <0x9a101000 0x18>;                           "zte,zx279128s-mdio"
gephy128s@9b000000 reg = <0x9b000000 0x100000>, ... x4;               "zte,zx279128s-gephy"
```

The ZX279133 driver's `ZX279133_BMU_*` / `QMG_*` / `SCH_*` offsets all sit in
`0x20000..0x3c000` relative to its NPPT base. Placed in the ZX279128S `tm@`
window (`0x92340000`, size `0x40000`) they would land at `0x92360000..0x9237c000`
— whereas the addresses tracked for this board (TMC `+0x0`, TMD `+0x4000`,
BM `+0x8000`, QMG `+0xc000`, TMQ `+0x10000`, SCH `+0x14000`) sit in the **low**
part of the same window. Also, the ZX279133 has no `SBRG`/`CLA` symbols at all
(grep for `qnum`, `pri_qtab`, `sbrg` in the whole driver returns nothing), while
the ZX279128S vendor driver has `sbrg_set_qnum_map_mode`,
`sbrg_set_sbrg_pri_qtab_pon` and `spa_set_loopback_en`.

**Conclusion (inference):** same *architecture* — SPA/PPU packet parser → QMG
queue manager → SSCH/WSCH/USCH schedulers → RED → BMU buffer manager, fed by an
IDM DMA engine, with XMAC/SMAC ports and X-PCS SerDes. **Different register map,
different block aperture addresses, extra ZX279128S-only blocks (SBRG, CLA).**
The ZX279133 driver is a *structural* reference and a source of vendor idiom, not
a portable map.

---

## 4. Historical searches with no result in the queried sources

Search engines / APIs queried with 25+ distinct terms:
GitHub REST (`search/repositories`, `in:name`, orgs `hack-gpon`): only the four
repos above. GitHub code search (auth-only) unavailable. Gitee v5 API (`zx279`,
`zx279128`, `zxylzb`, `sanechips`, `ZXIC`, `中兴微`, `光猫`, `gpon`) → 0.
GitLab `/projects?search=` → 0. Codeberg → 0. Software Heritage origin search →
no ZXIC origins; `openwrt-zx279128-e2631` not archived. Sourcegraph
(`zxylzb`, `sbrg_set_qnum_map_mode`, `pon_tm_net_tx`, `zx279128`, `fork:yes
archived:yes`) → 0. grep.app → Vercel bot wall. searchcode.com API → 404.
DuckDuckGo lite/html (GET + POST) and Bing → bot-walled, no parseable results.
Mojeek, Searx → 0. CSDN search API (`ZX279128`, `ZX279128S`, `ZX279133`) → 16/14/6
hits, all consumer unboxing/teardown articles, no source. Exact-symbol web
queries for `pon_tm_data_raw_send`, `sbrg_set_sbrg_pri_qtab_pon`,
`pp_bmu_free_bp`, `pon_tm_bmu_init`, `soft_release_rx_desc`,
`pon_tm_get_next_txdesc`, `zxylzb`, `plat-zxylzb`, `zx279128sevb` → nothing
vendor-derived.

Portals: `opensource.ztedevice.com`, `www.ztedevice.com`,
`opensource.zte.com.cn`, `www.ztedevice.com.cn` → **NXDOMAIN**.
`www.zte.com.cn/global/gpl.html` → 404 redirect.
**At the recorded search time, the Internet Archive endpoint was unavailable** ("Internet Archive services are temporarily
offline") — Wayback CDX for the ZTE GPL portal could not be queried; retry later.
`get.ipnetwork.com.br/files/ZTE/ROTEADORES_ZTE/H199A/` (Brazilian ISP mirror with
H199A files) → DNS resolves to `127.0.0.1`, unreachable from here.
`right.com.cn` threads are behind a WAF; `chinadsl.net` thread 169478 (H2-2 /
ZX279128S research) was read in full — firmware + DTB only, no driver source.
kanxue thread 276970 documents the firmware container (uImage → gzip → lzma →
`rootfs.cpio`, AES + certs) but publishes no driver source.

---

## 5. Follow-up proposed at the time

1. **E-mail `Open.Source@zte.com.cn`** naming the product and firmware version.
   It was a possible source-request contact for `tm.ko`, `switch.ko` and
   `plat-zxylzb_9128S.ko`; product/offer applicability was not established by
   this search. The later portal note records another acquisition route.
2. Keep **cnjn's ZX279133 driver** open as the structural reference (it already
   supplies the vendor's own naming and sequencing for BMU/QMG/RED/TM).
3. If more register evidence is needed before ZTE answers, **disassemble
   `uboot-F610GV9.bin`** — it is unencrypted ARM and contains `pon_tm_qmg_init`,
   `smac_init`, `init bmu moduel` and `red queue %d cfg` for this exact TM/BM
   block, which `kernel1.bin` (AES-CBC) does not yield.
