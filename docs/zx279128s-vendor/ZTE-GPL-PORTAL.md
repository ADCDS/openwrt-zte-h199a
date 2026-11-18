> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.
> Catalogue counts, availability and first-entry fingerprints describe the
> recorded search only. They do not establish every archive’s complete contents
> or a current legal/product applicability conclusion.

# ZTE GPL portal — working acquisition route (and one wrong platform)

Research note, 2026-09-11. Supersedes the earlier claim in
`VENDOR-ARCHAEOLOGY-R2.md` §7 that ZTE's open-source portal is dead.

## 1. Correction: the portal was reachable during the 2026-09-11 search

I earlier tested `opensource.ztedevice.com` (**singular**) and `www.ztedevices.com/opensource`,
both of which failed in that search, and concluded the portal was dead. **That was wrong.** The reachable host in that search was
**`opensource.ztedevices.com` (plural)** — HTTP 200 — and it was the third-party report's A12 that
had it right.

Portal: <https://opensource.ztedevices.com/>
It hosts real GPL source tarballs under categories *Data Card, Mobile Hotspot, Module,
Smart Phones, Wireless Home Gateway*.

From the portal's own text:

> If your device is not listed here or if you wish that we send you the entire source code of the
> open source software components used in the firmware of your device that are subject to GNU
> General Public License Version 2 or later, you can contact us through the email
> **tech.sp@zte.com.cn** for a period of three years, beginning with the purchase date of your device.

Note this is a *different* address from the `Open.Source@zte.com.cn` in ZTE's other notice
(newsId=1037164). Both are worth using.

## 2. Reproducible recipe (this is the useful part)

The category/product dropdowns are JS-driven, but two endpoints make the whole catalogue
enumerable without a browser:

```sh
# per-category product list (JSON, includes sourceCodeFile paths)
curl -s "https://opensource.ztedevices.com/rest/product/tabDropDown?opensourceTitle=Wireless%20Home%20Gateway"
curl -s "https://opensource.ztedevices.com/rest/product/tabDropDown?opensourceTitle=Mobile%20Hotspot"
curl -s "https://opensource.ztedevices.com/rest/product/tabDropDown?opensourceTitle=Data%20Card"
curl -s "https://opensource.ztedevices.com/rest/product/tabDropDown?opensourceTitle=Module"
```

The returned `sourceCodeFile` paths are **not** served from the portal host (403 from
`opensource.ztedevices.com`). The site's own inline JS rewrites them:

```js
if (a.indexOf('http') < 0) $(this).attr('ddd', 'https://download.ztedevices.com' + a);
```

So the real base is **`https://download.ztedevices.com`**:

```sh
curl -L -o pkg.tgz "https://download.ztedevices.com/device/global/support/opensource/9/20211013_01/ZTE_MF296R_opensource_code.tgz"
```

Catalogue size observed: **132** Wireless Home Gateway, **197** Mobile Hotspot, **43** Data Card,
**29** Module products (many with source).

**Preliminary platform probe** — the sampled first tar entries can provide platform hints, so a 400 KB ranged
fetch identifies it without downloading the whole thing:

```sh
curl -sL -r 0-400000 "$URL" -o part.bin && tar -tzf part.bin 2>/dev/null | head -1
```

## 3. Search result: no identified ZX279128 package in the inspected catalogue

I downloaded and inspected `ZTE_MF296R_opensource_code.tgz` (104 MB / 108,932,244 bytes,
sha256 `5a5829a7ed34ce3d93327d028899a08b0a13bd32b95bb2147d1108964a9322f3`).

- Top-level tree is **`TSPV3_opensource_code/`**, platform `tsp/tsp7520v3` — i.e. **ZX297520V3**,
  a Linux 3.4.x BSP with `project/zx297520v3/`.
- **It contains zero occurrences of `279128` and zero of `zx279`.**

The "STRONG 4G+ ROUTER1200 is a rebadged ZTE MF296R" claim from the OpenWrt forum was a forum
*guess* (user `hecatae`), and it is wrong — or at least the MF296R GPL package is not the
ZX279128R platform that the same thread's boot log shows.

Probing other ZTE home gateways by first-tar-entry confirms they are not ZTE silicon either:

| Product | Platform |
|---|---|
| MF296R, MF296C, MF296D, MF283U, MF833U1, ZM8731M | `TSPV3_opensource_code/` (ZX297520V3) |
| MF269, MF297D | `IPQ8074_Opensource/` (Qualcomm) |
| MF286D (H3G) | `IPQ401X_Opensource/` |
| MF286D/MF286R (ZTE) | `AR956X_QSDK/` (Qualcomm Atheros) |
| MF286RA | `asr/` |
| Y2000 | `NXP_Opensource/` |

**Conclusion limited to this search:** the inspected package and catalogue
fingerprints did not identify a matching ZX279128 SDK. This is not a complete
content inspection of every archive or proof of present availability. The
H199A's Ethernet WAN/LAN topology cannot be inferred from portal categories.

### 3.1 Catalogue fingerprint search: no useful sibling identified

I enumerated every category and fingerprinted **all 308 non-phone source packages** by their first
tar entry. Only **five** portal categories exist (probed 22 candidate names including ONU, GPON,
EPON, xPON, CPE, Router, Home Gateway, FWA, STB — all return 0 products): Smart Phones 673,
Mobile Hotspot 197, Wireless Home Gateway 132, Data Card 43, Module 29. **There is no ONU/GPON/CPE
category.**

Platforms across the 308 packages:

| Platform root | count | vendor |
|---|---|---|
| `apps_proc` | 55 | Qualcomm |
| `TSPV3_opensource_code` | 37 | **ZXIC ZX297520V3** |
| `SDX65`/`SDX55`/`SDX24`/`sdx75`/`9x35`/`mu5020` | 54 | Qualcomm modems |
| `uSDK_TSP7520V3_RO` | 15 | **ZXIC ZX297520V3** |
| `IPQ8074`/`IPQ401X` | 22 | Qualcomm |
| `asr` | 15 | ASR |
| `AR956X_QSDK` | 5 | Qualcomm Atheros |
| `NXP_Opensource` | 2 | NXP |
| `opensource_9215` (MF90+) | 2 | generic, `linux-3.0.21.tar.bz2` |
| `code/`, `temp2/`, `downloads/`, `source_code/`, `V3V_opensource*` | 21 | Android/Qualcomm |

**The recorded ZTE-platform fingerprints pointed to TSP7520V3 /
`uSDK_TSP7520V3_RO` (ZX297520V3).** No matching ZX2791xx package was identified
by that method; deeper contents and later catalogue changes remain outside it.

## 4. What the TSP7520V3 BSP is actually good for

Even though the Ethernet block is wrong (`drivers/net/gmac/zx_gmac.c` + an external Realtek
RTL8306e switch driver, not TM/BM/PP), two things cross over:

1. **`drivers/mtd/nand/zxic_spifc.c` + `zxic_spifc.h`** — the ZTE SPI-NAND controller driver.
   The recovered ZX279128S vendor config selects `CONFIG_MTD_NAND_ZTE_SPIFC=y`, so this is very
   likely the same driver family. Directly useful for the SPI-NAND port.
2. **ZTE's delivery structure**: the tree is an *overlay*, not a full kernel —
   `platform_sdk/tsp/<soc>/replace_code/linux_plat/base/linux-3.4.x/...` plus
   `replace_code/project/zx297520v3/prj_mifi/...`. Knowing this shape tells us what to ask for and
   what a ZX279128 BSP would look like if we obtain one.

Not present: any TM/BM/PP/SBRG/CLA code, any `zx279` symbol, any U-Boot source.

## 5. Revised acquisition routes

1. `tech.sp@zte.com.cn` (this portal) **and** `Open.Source@zte.com.cn` (ZTE's other OSS notice) —
   ask for the *complete corresponding source for the binaries in firmware version X* of the
   ZXHN H199A specifically. The consumer portal will not cover it; the carrier/ONU side is a
   different distribution channel.
2. Ask the Brazilian carrier (Vivo/Claro) and ZTE Brazil for the corresponding source of the
   H199A firmware — the distributor obligation sits with them too.
3. Re-try the portal periodically: it is actively maintained (entries through 2025+), so a ZX279128
   device could appear.
4. Julius Schwartzenberg `julius.schwartzenberg@eclipso.eu` (mainline ZTE contributor, hunting
   ZX27/ZX29 SDKs); `mb_liyhznlb` `chihaya-anon@outlook.com` (has a 279128 dev board + debug ONU).
5. Software Heritage, once the API rate limit clears, for the deleted
   `Zlion-Y/openwrt-zx279128-e2631`.

## 6. Assessment of the supplied third-party material

`~/Downloads/ZX2791xx_partial_sources.zip` (19 KB) is **metadata only and contains no source** —
its own README says so: "No complete vendor SDK, BSP, driver tree, U-Boot source tree, firmware
binary, Git history, repository ZIP, or raw webpage snapshot is included." It holds three complete
files from `AlienWolfX/GM620` (README, LICENSE, .gitignore) and only **lines 1–150** of
`bootlog.txt`, plus Kanxue notes, 17 config strings, and a downloader script whose access attempts
all failed. We already hold the full 141 KB bootlog and all four Kanxue pages, so this bundle adds
nothing.

`~/Downloads/deep-research-report (1).md` is a re-focused version of the first report, aimed at
**CMCC attribution** rather than source availability. Its conclusions match mine, and it adds four
artifact leads (A6 GitLab toolchains, A7 ChinaDSL ZX279127 log, A10 blog.rop.la F680 dump, A12 the
ZTE portal). Its A12 led to the real find above. Its update on A4 is also worth keeping: as of
**2026-06-08** the Kanxue thread's principal reverse engineer, XYUU, stated that despite asking for
years **nobody ever sent him an SDK package** — which confirms the 2024 SDK claim should stay at
low confidence.

`xuejian1354/toolchains` on GitLab is real
(<https://gitlab.com/xuejian1354/toolchains/-/tree/master/src>) and lists
`ZX279100_cross_compiler.tar.gz`, `ZX27912X_cross_compiler.tar.gz`,
`zx279127-128-toolchain.tar.xz`, `zxic127-128-toolchain.tar.xz`, `skyworth-zxic-toolchain.tar.xz`.
These are **cross-compilers, not sources**; the blobs were not retrievable via the API (LFS).
