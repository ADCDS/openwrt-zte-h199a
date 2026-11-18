> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](README.md),
> [installation](INSTALL.md) and [validation](../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# Prior art & resources (researched 2026-08-20)

## Directly relevant projects

### celeron633/ZX279127S-Reverse — ⭐⭐ flashing/secure-boot (found 2026-08-20)
<https://github.com/celeron633/ZX279127S-Reverse>

Thorough RE of the **ZX279 系列 secure-boot chain** (F610GV9, F663NV9G, SG631Z,
G7615 — ZX279127S/ZX279133). Same family as our ZX279128S. Key findings:

- Boot chain: BootROM →(AES-CBC + verify)→ secondboot →(verify)→ U-Boot
  →(SHA256+RSA2048)→ kernel+rootfs.
- **CRC32 (header/kernel/fs) is recomputable** — `script/fix_binheader_crc.py`
  parses the binheader (magic `99999999 44444444 55555555 aaaaaaaa`) and fixes
  the CRC fields (+0x3C kernel, +0x48 fs, +0xCC header).
- **RSA-2048 signature cannot be forged** (vendor private key); the verify
  public key is an AES-CBC blob in the U-Boot image header (decrypted by
  BootROM into SRAM `0x40080000`, modulus at +0x1C4).
- Container: "127s" magic (ZX279127S) = dual digest-header blocks.
- **Legit modification path**: modify *unsigned* writable partitions
  (`userconfig`/`tagparam`/`usercfg`/`wlan`) + hook rootfs startup scripts.

**Our H199A is luckier than their devices**: boot log shows
**`non secure boot` / `non secure uboot`** (99×) — the RSA chain is NOT
enforced on this unit (eFuse not blown). Magic is **"128s"** (0x73383231,
seen in `mtd0-bootloader.bin` @0x10) — the ZX279128S sibling of "127s".
→ **CRC-correct unsigned images should boot**; only the binheader CRC needs
to be right. Their `fix_binheader_crc.py` is directly adaptable (128s magic).

### cnjn/linux-mainline-zte-zxslc-sr1010 — ⭐ primary reference
<https://github.com/cnjn/linux-mainline-zte-zxslc-sr1010> (Linux 6.18.38 base, actively updated)

Mainline port for the **ZX279133** (ZX279128's direct successor, SR1010 router,
ARM64). 60+ commit series implementing, from scratch:
pinctrl, top clock tree + LSP clocks (incl. UART wclk=25M parent + UART reset),
watchdog, eFuse/nvmem, PVT hwmon, PWM, MDIO controllers, xHCI CCI clock,
SPI-NAND **strict read-only mode** (safe dump philosophy), DTS.

Key commits for us:
- `b858b3823` tty: serial: pl011: add ZTE ZX279133 support
  → **backported to our 6.6 tree** (patches-6.6/998): vendor_zte offset table,
  AMBA id 0x001feffe, `zteuart` earlycon. Upstream 6.6/6.18 have NONE of it
  (mainline got a variant post-6.18 with id 0x0008c011, no earlycon).
- `e7963a8c9` clk: zte: add ZX279133 clock and UART reset support → future
  clock driver template (their DTS confirms UART wclk parent = topcrm 25M —
  matches our live-measured 25 MHz).
- SPI-NAND read-only + fail-closed partitions — pattern for our dump-verify ethos.

### ynbl07/openwrt-zx279128-e2631 — same-SoC bring-up (abandoned)
<https://github.com/ynbl07/openwrt-zx279128-e2631> (kernel 6.12, updated 2026-08-11)

ZTE E2631 (ZX279128S!) OpenWrt scaffold. **Abandoned at the exact wall we
avoided**: they used `earlycon=pl011` (wrong registers — ZTE layout), kernel
hung silently after `Starting kernel ...`. Their README pins the root cause
(ZTE UART compatible / register layout / periphid / zteuart earlycon) and
references the ZX279133 project for the fix. Their DTS independently chose
the same fixed clocks we measured: uart 25M, apb 100M, timer 500M.
Their loss = our roadmap: DON'T use pl011 earlycon; periphid 0x001feffe.

### xuejian1354/openwrt_cc @ gateway-3.0 — vendor ChaosCalmer fork (limited)
<https://github.com/xuejian1354/openwrt_cc> (branch gateway-3.0)

ISP buildsystem with thin targets for zx2791/279100/279127/279128/279131/
zxic127/128 + `zte-279128.config`. Kernel drivers NOT in-repo (downloads
ZTE SDK tarball, needs closed toolchain `/opt/zte/cross_compiler`). Useful
mainly as evidence of target matrix/naming, not as driver source.

## Mainline kernel ZTE history
- `drivers/clk/zte/clk-zx296702.c`, `clk-zx296718.c` — exist through v5.10,
  removed later; fetched copies in `ref/`. Architecture (topcrm/lsp0crpm/
  lsp1crpm, UART wclk mux 104M/26M on 702) informed our clock reasoning —
  though live measurement proved ZX279128 uses a 25M UART parent instead.
- `include/linux/amba/serial.h` has `ZX_UART011_*` offsets since forever
  (DR@0x04, FR@0x14, IBRD@0x24/FBRD@0x28 — the last two standard, which is
  why the live divisor measurement at 0x94404024 was valid).
- Current master pl011.c has vendor_zte with invented id 0x0008c011
  (post-6.18); cnjn's 0x001feffe is ZTE's JEDEC-ish variant used by DTS.

## Other resources
- OpenWrt forum: "Support for zx279128s" thread (exists; not yet read —
  low signal expected, E2631/cnjn cover the ground).
- 看雪 (kanxue) thread: ZX279128S firmware decryption research (Chinese,
  iot-security context) — potential encryption insight for ZTE image headers.
- China Telecom RAX1800Z: ZX279128S + MT7905/MT7975 (mt76 mainline) — same
  SoC different Wi-Fi gen, boot logs circulate on right.com.cn (恩山).
- orca.pet ZTE H3600P hacking — ZX279128S@A9 GPON ONT, source of the
  `Boot4128s!` bootmode password (already unlocked here).
- douniwan5788/zte_modem_tools — factory-mode telnet (failed on this unit).

## Local artifacts
- `ref/linux-mainline-zte-zxslc-sr1010/` — full clone (63 commits of drivers)
- `ref/openwrt-zx279128-e2631/` — clone
- `ref/vendor-openwrt-cc/` — clone (thin targets only)
- `ref/clk-zx296702.c`, `ref/zx296702.dtsi`, `ref/zx296702-clock.h`
- `ref/stock-vmlinux.bin` — 6 MB stock kernel (4.1.25) for driver RE
