> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](README.md),
> [installation](INSTALL.md) and [validation](../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# Session journal — ZTE ZXHN H199A port

> **This is a chronological record, not a description of the current system.**
> Much of it is superseded: it contains a dump-era resume point, a repository
> plan for a remote that no longer matters, feasibility predictions that turned
> out wrong in both directions, and several "current state" sections that
> contradict each other because each was current when written.
>
> For what is true now, read [`../README.md`](../README.md) and the per-area
> documents linked from it.
>
> It is kept for the parts that are not reconstructible: how the flash dump was
> obtained and every fast path that failed first, the bench rig, the access
> paths into the stock firmware, and the device identification work.

## TL;DR — what's true right now

- **✅ FLASH DUMP CAPTURED AND PUBLISHED.** The full 128 MiB NAND image, per-
  partition slices, and the extracted **stock DTB** are committed to
  **`adriel/h199a-firmware`** (private) on Gitea. This was the session's goal — DONE.
- **We have an UNLOCKED U-Boot shell on the device** (`=>` prompt). Boot-mode
  entry: send `1` during the cspboot `Press 1` window, then password
  **`Boot4128s!`**. Automated by `~/h199a-build/try-bootmode-password.sh`.
- **Dump method:** serial `md.l` over UART (only method that works — see
  "DUMP: HOW IT WAS DONE" below). ~5 h at 115200. Verified bit-exact by re-reading
  random regions from live NAND (4/4 matched; U-Boot has no `crc32`).
- **The stock DTB is the prize for the port:** `model="ZTE ZX279128S"`,
  `compatible="zte,zx279128-smp"`, dual Cortex-A9. Uses mainline-driver blocks
  (GIC, PL011, pl310 L2, **denali NAND**, dwc3/dwc2 USB) + vendor clock/GPON
  blocks. See `h199a-firmware/extracted/README.md` for the full port roadmap.

## DUMP: HOW IT WAS DONE (and every fast path that FAILED)

Only working method: **`nand read <off> → md.l → parse hex LE on host`**
(`flash-dump.py mddl`). ~2.7 KiB/s. Dumped only real data [0,0x3100000) (49 MiB);
tail is verified-erased 0xFF, reconstructed locally to a true 128 MiB.

Ruled out (do NOT retry): bare-metal dumper via `go` (D-cache staleness, hangs)
or `bootm` (resets); no `dcache`/`icache` flush cmd exists; baud hard-capped at
115200; network egress impossible (U-Boot download-only, no tftpput; stock Linux
ignores `init=/bin/sh` — cspstart overrides bootargs from in-flash BootPara).

**Gotcha:** closing the serial port reboots the router (HUPCL drops DTR). Dump
script holds port open whole run + self-catches boot mode. Software reset is
flaky — twice needed a physical power-cycle / USB replug (adapter dropped off bus
mid-dump at 44%; resumed cleanly, chunk-aligned, zero loss).

---

## DEVICE IDENTIFICATION (all CONFIRMED from boot log / status page)

| | |
|---|---|
| Model | ZTE ZXHN **H199A**, Ethernet router (Multilaser rebrand, Brazilian ISP; earlier GPON classification withdrawn) |
| Software | **V9.1.0P3N2_MUL** |
| Hardware | **V9.1.1** |
| Bootloader | **V1.0.0** — U-Boot 2013.04, built `Jul 06 2021 - 14:44:21` |
| Serial No. (this unit) | `ZTEYH86N3714965` |
| **SoC** | **ZTE/Sanechips ZX279128S**, dual-core ARM **Cortex-A9** @ 1 GHz, ARMv7 `[414fc091]` |
| Board string | `ZTE zx279128sevb`, `current_board=c05b320c`, `arch_number = 0x00044258` |
| Flash | **Micron SPI-NAND MT29F1G01ABAFDWB, 128 MiB** (page 2048, OOB 64, erase 128KiB, 8-bit ECC) |
| RAM | **128 MiB** DDR (`mem=128M`), 0x40000000–0x48000000 |
| Wi-Fi | **MediaTek MT7603 + MT7613** (AC1200, 2× PCIe links) — *believed from sibling H196A; not yet visually confirmed on this unit* |
| Console UART | **ttyAMA0 = ARM PL011 @ 0x94404000**, 115200 8N1 (2nd PL011 ttyAMA1 @ 0x94405000) |
| Ethernet MAC | `00:41:71:00:00:50` |
| Stock kernel | **Linux 4.1.25** (Buildroot 2015.08.1, gcc 4.9.3), built by `xialei@localhost` 2021-07-06 |
| Rootfs | **jffs2** on `/dev/mtdblock8`, squashfs also present |

### NAND partition map (from kernel boot log)
```
0x000000-0x8000000  Whole flash  (128 MiB)
0x000000-0x100000   Bootloader   (1 MiB)   <- mtd0
0x100000-0x200000   tag          (1 MiB)
0x200000-0x300000   wifi         (1 MiB)
0x300000-0x500000   usercfg      (2 MiB)
0x500000-0x700000   defcfg       (2 MiB)
0x700000-0xa00000   kernel1      (3 MiB)
0xa00000-0x1720000  rootfs       (~13 MiB)
0x1720000-0x2000000 (gap)
0x2000000-0x2300000 kernel2      (3 MiB)   <- A/B dual-bank
0x2300000-0x8000000 (rest, ~100 MiB, likely blank/2nd rootfs)
```
Boot is A/B dual-bank via ZTE's `zteboot`/`cspboot` wrapper around U-Boot
(CRC-verified image headers, `zteboot_search_firmware` finds headers at
0x1720000 and 0x3020000).

---

## THE FEASIBILITY REALITY (read before promising a "port")

**The ZX279128S is ZTE's own in-house SoC with ZERO mainline Linux/OpenWrt
support** — no kernel target, no clk/pinctrl/spi-nand/switch/PCIe drivers, no
public datasheet, no public BSP. The only existing "OpenWrt" is a vendor
ChaosCalmer fork (Linux 3.18, closed `arm-zxic2791` toolchain). No GPL tarball
found (ZTE portal opensource.ztedevices.com has nothing; would have to email
tech.sp@zte.com.cn).

User explicitly chose to **attempt the real port anyway** (eyes open). Realistic
outcomes: a mainline kernel booting to a UART **prompt** is plausible; a
*functional* router (WAN/switch/Wi-Fi) is unlikely without months of per-driver
RE. **Wi-Fi is NOT the blocker** (MT7603/MT7613 are mainline `mt76`).

The **single most valuable asset for any port is the stock DTB** — Linux 4.1.25 is
device-tree-based, so a stock DTB lives in the firmware dump (gives exact memory
map/clocks/IRQs/pinmux). **Capturing the flash dump is therefore the priority.**

---

## ACCESS PATHS ACHIEVED

### 0. UART WIRING (2026-08-20 — READ BEFORE UNPLUGGING)

The board header's two candidate pads are NOT equivalent:
- **One pad = boot-strap pin.** Driving it at power-on (adapter TX connected) forces
  the mask ROM into UART-download mode: prints `Boot UART` / `ROM# ` in a loop,
  never reaches cspboot, ignores input. **Do not connect TX there.**
- **The other pad = router RX.** Normal boot, catcher works, `=> ` reached.
- Adapter RX + GND pads were always right (RX capture never broke).

Current working mapping (CP210x adapter, 2026-08-20):
adapter-TX → router-RX (the "good" pad), adapter-RX → router-TX, GND ↔ GND.

### 0b. REMOTE POWER (2026-08-20)

`tomada` (smart plug, `~/.local/bin/tomada`) power-cycles the router from the host:
`tomada off && sleep 6 && tomada on`. Its mA/W metering is WRONG (reads 0) — only
trust the UART log to know if the box is up. Full rig: `uart-log.sh` (socat logger,
auto-reopens) + `catch-bootmode-v2.sh` (state-machine catcher: `Press 1` → `1`,
password prompt → `Boot4128s!\r`, autoboot → CR; ends at `=> `) + `tomada`.
Catcher v1 (`try-bootmode-password.sh`) fires too early (on cspboot-init banner) —
use v2.

### 1. UART → U-Boot shell (PRIMARY, unlocked) ✅
- Capture rig on `/dev/h199a-uart` (udev symlink, world-rw). Two adapters used
  this session: CP2102 (TX died mid-session) then **CH340/CH341** (current,
  healthy). udev rule `/etc/udev/rules.d/99-h199a-uart.rules` matches BOTH
  `10c4:ea60` (CP210x) and `1a86:7523` (CH340).
- **TX was flaky/dead for a long stretch** — root cause was a loose/missing
  ground wire between adapter and router (NOT a dead adapter; loopback confirmed
  the replacement CH340's TX is fine, and echo confirmed TX reaches the router).
  **All three lines (TX, RX, GND) must be connected.** If "no echo," check GND first.
- Boot-mode entry sequence (works reliably now): power on → cspboot prints
  `*** Press 1 means entering boot mode***` with a 3-2-1 countdown → send `1` →
  it prints `*** Please input bootmode password: ***` → send **`Boot4128s!`** +
  Enter → drops to `cspboot` menu, then U-Boot's own `Hit any key to stop autoboot`
  → `=>` prompt.
- Password source: `Boot4128s!` found by research agent, confirmed by two
  independent sources (H3600P teardown with identical `ZX279128S@A9` CPU string,
  + H196A sibling forum). **It worked on the H199A.**

### 2. Web admin UI ✅ (full control, no shell)
- Credentials: **`multipro` / `multipro`** (Multilaser default). Login flow is
  `sha256(password + token)` where token comes from `GET /?_type=loginData&_tag=login_token`.
- Reachable **only over IPv6 link-local** `http://[fe80::1%br0]/` via **tiny (RPi)**,
  which is bridged (`br0`) to the H199A's LAN port. **No IPv4 DHCP** on the H199A LAN
  (its dhcp server failed to register at boot: `dhcp4sIFRegister fail`).
- Access from the PC: SSH local-forward tunnel + a Host-header-rewriting proxy
  (the device rejects non-IP-literal Host headers). See "Network access setup" below.
- Sections explored: Status, Account Mgmt (only `multipro` account), System Mgmt
  (backup/restore/upgrade), TR-069 (ACS = `0.0.0.0`, already neutralized),
  Network Diagnostics (ping/traceroute — **server-side input validation defeats
  shell injection**), Default Cfg Mgmt. **No exposed telnet/SSH toggle anywhere.**
- **Factory-mode telnet backdoor FAILED**: `douniwan5788/zte_modem_tools`
  (`zte_factroymode.py`) — tried 288 credential combos incl. all built-in defaults
  + Brazil guesses. `multipro/multipro` does NOT work on factory-mode (separate
  cred space). The tool needs an IPv6 zone-id monkeypatch to run (requests
  re-encodes `%`→`%25`); see `~/h199a-build/zte_modem_tools/` and scratchpad `zte_brute.py`.

### 3. Config backup ✅
- `~/Downloads/config.bin` (14862 bytes, AES-encrypted, entropy 7.97). Page JS uses
  CryptoJS AES-CBC, key/iv = SHA256(seed), ZeroPadding. Seed unknown — not yet decoded.

---

## EXACT RESUME POINT (what to do first in the new session)

1. **The device is HUNG.** Power-cycle it. `try-bootmode-password.sh` +
   `uart-log.sh` were left running (armed) to re-enter boot mode automatically.
   Verify you're back at `=>`:
   ```
   tail -20 ~/h199a-build/logs/uart.log   # look for "=> " at the end
   ```
2. Stop the background logger + catcher (free the port for pyserial):
   ```
   ps -eo pid,args | grep -E 'socat -u /dev/h199a-uart|try-bootmode|uart-log' | grep -v grep
   # kill those PIDs
   ```
3. Run the **diagnostic** that was queued (verifies whether the dumper code
   actually lands in RAM, and retries `go`):
   ```
   cd ~/h199a-build && python3 dump-h199a.py testgo
   ```
   - It XMODEM-uploads `h199a-firmware/dumper-attempt-abandoned/dump.bin` to 0x41000000, runs `md.b 41000000 10`
     (should show `10 d0 9f e5 00 00 a0 e3 ...` matching dump.bin), then `go`.
   - Looks for signature bytes `55 AA 55 AA`. **If absent** → the dumper won't
     execute even though loaded (see "BLOCKER ANALYSIS").

---

## BLOCKER ANALYSIS — bare-metal dumper won't execute

**Symptom:** `go 0x41000000` prints `## Starting application at 0x41000000 ...`
then hangs. The dumper's first act is to emit signature `0x55 0xAA 0x55 0xAA` to
the UART — never appears. So `main()` never runs.

**Dumper** (`~/h199a-build/dumper/`, 344 bytes): `_start` sets sp=0x41ff0000,
**invalidates I-cache** (`mcr p15,c7,c5,0` + ISB), `bl main`. `main` emits
signature, then streams `CTRL_LEN` bytes from `CTRL_ADDR` out the PL011
(@0x94404000) raw, sets `CTRL_DONE=0xDEADBEEF`, emits tail signature, loops.
Control block at 0x41ffe000/4/8. D-cache deliberately untouched (coherency with
nand-read staging). Compiled with `arm-none-eabi-gcc -mcpu=cortex-a9 -marm -ffreestanding -nostdlib`.

**Confirmed working:** XMODEM upload (`xmodem <addr>` receive mode; host sends via
`dump-h199a.py`'s built-in XMODEM-CRC 1K-block sender). `nand read`/`mw`/`go` all
run. **`go` does NOT return to prompt** (verified) → any dumper strategy must
reset between invocations OR dump everything in one shot.

**Not yet checked:** the `md.b 41000000` verification (queued in testgo). Outcomes:
- If `md.b` shows wrong bytes → XMODEM not landing at 0x41000000 (address bug).
- If `md.b` matches but no signature → execution failure. Suspects:
  1. **MMU XN (execute-never)** on the 0x41000000 page (ARMv7 permission fault).
  2. **Prefetch/undefined exception** → U-Boot's handler hangs silently.
  3. `go` on this vendor fork doesn't actually jump / expects a U-Boot image header.

**FALLBACK if dumper stays broken — `md.b` hex dump (reliable, slow):**
`md.b addr len` dumps RAM as hex, **returns to prompt** (no reset per chunk), no
cache/MMU issues, no bare-metal. Overhead ~3-4× (each byte→"xx "). At 115200:
**~12 h for full 128 MiB**, ~2.4 h for the essential first 24 MiB (bootloader→rootfs).
The porting-critical data is all in the first ~24 MiB; the rest (~100 MiB) is
largely blank/2nd-bank. Recommend: `md.b` the first 32 MiB now, defer/skip the blank tail.
Other untried idea: write a dumper that **reads SPI-NAND directly** in bare metal
(RE the ZX279127 spifc @ 0xf0706000) so it streams all 128 MiB in one `go` — big effort.

---

## NETWORK ACCESS SETUP (to reach the web UI from the PC)

The H199A is L2-attached to **tiny's `br0`** (bridged to eth0). tiny = RPi,
reachable `ssh tiny` (IPv6 ULA `fda4:3bcc:fdee::caa`, also Tailscale 100.64.0.14).
From the PC, the chain is:

```
PC browser → localhost:8200 (host-rewrite-proxy.py, rewrites Host:→192.168.1.1)
          → localhost:8199 (ssh -L forward)
          → tiny → [fe80::1%br0]:80  (the H199A)
```

Setup commands (run from PC, port may need recreating after tiny reboots):
```bash
ssh -f -N -L "8199:[fe80::1%br0]:80" tiny
python3 ~/h199a-build/host-rewrite-proxy.py &   # listens :8200 → :8199
```
Then drive via chrome-devtools MCP (`mcp__chrome-devtools__*`) at
`http://localhost:8200/`. Login script logic (from the page's own JS) is encoded
in the session history; the browser-driven login worked.

**tiny caveat:** tiny's Wi-Fi (`wlan0`) dropped once mid-session (both LAN + Tailscale
unreachable). If tiny is down, that path is down; passive UART (RX) still works.

---

## THE CAPTURE RIG (all in `~/h199a-build/`)

| File | Purpose |
|------|---------|
| `logs/uart.log` | **persistent passive RX capture** (socat, survives power-cycles). Tail with `tail -f`. Gets BIG (MB). |
| `uart-log.sh` | the background logger (115200 8N1) |
| `console.sh` | interactive picocom console (exit `Ctrl-A Ctrl-X`) |
| `uart-send.sh` | one-shot byte injector |
| `try-bootmode-password.sh` | **the working boot-mode catcher**: on seeing cspboot init, sends `1` → 400ms → `Boot4128s!`\r |
| `dump-h199a.py` | **pyserial orchestrator**: XMODEM upload + raw-stream capture. Modes `testgo` / `dump`. |
| `h199a-firmware/dumper-attempt-abandoned/{dump.c,dump.ld,dump.bin,dump.elf}` | the bare-metal UART-streaming helper (won't execute yet) |
| `host-rewrite-proxy.py` | Host-header-rewriting proxy for web-UI tunnel |
| `h199a-firmware/dump-session/` | dump output dir (`h199a-flash-full.bin`, per-chunk files) |
| `zte_modem_tools/` | cloned `douniwan5788/zte_modem_tools` (factory-mode exploit, failed here) |
| `bin/`,`doc/` | empty staging dirs |

**Port exclusivity:** only ONE reader may own `/dev/h199a-uart`. `uart-log.sh`
(socat) and `dump-h199a.py` (pyserial) CANNOT run simultaneously — kill the
logger before running the orchestrator, and vice versa.

**Known flakiness:** the socat logger has died a few times during USB
disconnect/reconnect churn (the CP2102 + loose-GND era). With the CH340 + solid
GND it's been stable. Always verify the logger is alive before assuming "no
output" means the device is silent.

---

## GITEA REPO PLAN (the deliverable)

Mirror `adriel/ax3000t-firmware` and `adriel/dir842-firmware` (both **private**).
Create **`adriel/h199a-firmware`** (private) with:
```
README.md           what this is (device id, SoC, how dumped)
PARTITIONS.md       the partition table above
RESTORE-TO-STOCK.md how to write the dump back (nand write / xmodem)
MANIFEST.txt        file list + sha256 + sizes
h199a-flash-full.bin   full 128 MiB dump (once captured)
mtdX-*.bin             per-partition slices (bootloader/kernel1/rootfs/tag/...)
logs/                  uart.log boot captures
boot-info.txt          printenv / bdinfo / nand info / help output
```
Gitea MCP tools: `mcp__gitea__create_repo`, `mcp__gitea__create_or_update_file` (or
just `git clone` the ssh_url `ssh://git@gitea.adr:2222/adriel/h199a-firmware.git`
and push). Don't commit until the dump is captured and verified.

---

## OTHER NOTES

- **Baud is fixed at 115200** by U-Boot/console; can't easily raise it for the dump.
- **Watchdog:** U-Boot `watchdog disable` (the `watchdog` cmd with no subcmd just
  prints usage). Kernel watchdog is 8s heartbeat. We disabled it in U-Boot.
- **U-Boot `help`** lists: `nand` (read/write/read.raw/erase/dump/bad),
  `md/mw/cp/cmp`, `go`, `bootm/bootz/bootk`, `xmodem <addr>` (RECEIVE only),
  `tftp/dhcp/ping`, `fdt`, `gpiotest`, `i2c`, `mii`, `mtest`, `cspnand/cspnor/cspboot`,
  `setenv/saveenv/printenv`. **No `tftpput`, no `xmodem send`, no `imi`-style image boot verified.**
- `loadaddr=0x42000000`, `ipaddr=192.168.1.1`, `serverip=192.168.1.100` (TFTP
  config already set — could TFTP a kernel into RAM and `bootz` it for bring-up experiments).
- Two ZTE-specific cmds worth exploring later: `cspnand` (may give raw page access
  incl. OOB/bad blocks for a true bit-exact dump) and `fdt` (is there an FDT blob
  in RAM/flash we can directly `fdt addr`/print?).

## OPEN QUESTIONS / NEXT EXPERIMENTS (beyond the dump)
1. Get the dump (dumper fix OR `md.b` fallback).
2. Extract the **stock DTB** from the dump → real memory map for porting.
3. Try `tftp`+`bootz` of a minimal mainline Cortex-A9 kernel (DTB handoff) → can
   we reach a UART prompt on ZX279128S?
4. Visually confirm Wi-Fi chips (MT7603/MT7613) by opening the case.
5. Decode `config.bin` (CryptoJS AES, need the seed).
6. Email tech.sp@zte.com.cn for GPL source of the ZX279128 family.


# Session state (round 54)

## Delivered and verified on hardware

1. **spifc NAND driver** (`zx_spifc_nand.c`) — reads byte-exact against the July
   dump, `nand_scan` works, 9 MTD partitions register, write/erase verified.
   Root causes fixed along the way: column/row address split, controller wedge
   (recovery + retry + short timeouts), and an `exec_op` bug where a column-only
   or absent address reset the row and re-read page 0.

2. **Flashable image** — `tools/flash-prep.py` produces a kernel + rootfs +
   firmware header the vendor bootloader accepts (kernel CRC, fs CRC and the
   header's own CRC at `+0xa4`). OpenWrt boots from NAND to a shell with no TFTP.

3. **Ethernet** (`zx279128-eth.c` + `mdio-zx279128.c`) — MDIO, four GE PHYs,
   full datapath reverse-engineered from the bootloader, TX and RX both working.
   `ping` with 0% packet loss over a TFTP boot; on a flash boot the link comes up
   at 1 Gbps, `eth0` is bridged into `br-lan` and TX works.

## Open items

- **Flash-boot RX — working as of round 88, evidence hardened in round 90.**
  Cold NAND boot, no bootloader help: `ping -c 60` gives 60/60, 0% loss, and RX
  survives `ifdown`/`ifup`. Latency after the round-90 hrtimer fix:
  min 0.34 / avg 8.9 / max 19.3 ms (was 27/174/315 ms — the "1 ms poll" was
  really 10 ms because `msecs_to_jiffies(1)` rounds to a jiffy at HZ=100).
  The fix was the PP bring-up (round 84), TMC/TMQ writes (round 85) and the full
  NPP bring-up incl. `[0x921cc000] = 17` (round 87), all found by statically
  decoding the `eth_init` call tree. Historical notes below.
- **Flash-boot RX (historical)** — the single Ethernet defect. **Round 74 proved the driver
  itself is correct**: booting the flashed kernel after running `ping` at the
  U-Boot prompt (so the bootloader runs `eth_init`) gives full RX with 0% packet
  loss. The gap is entirely in `zx_eth_datapath_init()`. Usable workaround:
  `ping <addr>` then `nand read 0x42000000 0x700000 0x300000` then
  `bootm 0x42000020`.
  **Round 82's TrustZone/station-MAC root cause was RETRACTED in round 83**:
  U-Boot cannot write those registers either, and `0x923a0078` reads zero even
  on a boot where RX works. The PP region is hardware-maintained and read-only
  to the CPU from both U-Boot and Linux. See docs/ETHERNET.md round 83. See `docs/ETHERNET.md`
  "State of the Ethernet port" for the reduced symptom (`BM+0xdc`) and the list
  of hypotheses already eliminated on hardware.
- **SMP second core** — implemented and proven, but held off with `maxcpus=1`.
  Root cause of the corruption is understood: our spifc driver busy-polls a
  16-word FIFO for all 528 words of a page, and IPI latency from the second core
  makes it miss data. The stock driver drives the same FIFO from an **interrupt**
  (`spifcnand_nand_int`, GIC SPI 13, already in our DT). Implementing that is the
  fix; the interrupt enable/status bits still need to be identified. See
  `docs/NAND.md`.
- **RX latency** — NAPI is driven by a 1 ms timer; the `pon@92000000` interrupt
  (SPI 34) has not been decoded. Ping latency is 60-500 ms as a result.
- **Wi-Fi: the PCIe core is Synopsys DesignWare** (round 101, from the vendor
  driver's own strings — round 90's "not DesignWare" was wrong). Two ports.
  DBI at 0x0f000000 / 0x0f100000, ZTE glue at 0x09500000 / 0x09600000, LTSSM
  state at glue+0xDC bits 17..22 (0x11 = L0), link speed at DBI+0x80. Plan: thin
  DesignWare glue driver, INTx only, mt76 calibration from NAND via
  `mediatek,mtd-eeprom`. **The bring-up sequence is now fully decoded**
  (round 104): enable the shared PHY block at phys 0x09400000 (`+0x08` set
  BIT(15), BIT(13), BIT(14) in order), `0x09500000+0x70 |= 0xb5`,
  `0x09500000+0x74 &= ~BIT(0)`, `0x09600000+0x0c &= ~BIT(14)`, toggle PERST# on
  GPIO 53 and 55, then poll glue `+0xDC` bits 17..22 for 0x11 (L0).
  **SOLVED in round 106.** The sequence operates on CRM blocks, not PCIe glue:
  the vendor's static virtuals map (via the kernel map_desc table at 0xc059ba80)
  to phys 0x94000000 / 0x94100000 / 0x94200000. Verified on hardware:
    crm1[0x70] |= 0xb5 ; crm0[0x08] |= BIT(15),BIT(13),BIT(14) ;
    crm1[0x74] &= ~BIT(0) ; crm2[0x0c] &= ~BIT(14)
  After this the DesignWare DBI at 0x0f000000 reads correctly:
  vendor/device 0x1cf2:0x6830, PCIe capability at +0x70 (cap id 0x10),
  version reg 0 (core older than v4.70a), iATU viewport at +0x900 (legacy path).
  **Round 107: LINK IS UP (LTSSM = 0x11 = L0).** Remaining steps found:
  CRM0[0x24] &= ~BIT(26); CRM1[0x74] |= BIT(0); CRM1[0x70] &= ~BIT(8);
  GLUE(0x09500000)[0x00] |= BIT(5) starts training; DBI[0xa0] = (v & ~0xf)|1
  sets Gen1; then PERST# via GPIO 53/55. GPIO controller is at phys 0x94407000
  (banks 0x40 apart, +0x18 set / +0x1c clear). Full sequence in docs/WIFI.md
  round 107.
- **Round 108: ENDPOINT ENUMERATED.** A hand-programmed legacy-viewport iATU
  CFG0 window reads bus1.dev0 = **14c3:7663 = MediaTek MT7613BE**, class 0x0280,
  BAR0 64-bit prefetchable. Link confirmed independently: DEBUG1 (DBI+0x72C)
  bit4 LINK_UP=1, bit29 IN_TRAINING=0, LNKSTA negotiated Gen1 x1.
  MT7613BE is driven by mainline **mt7615e** (firmware mt7663pr2h.bin).
- **Round 108b: PCIe HOST DRIVER WORKING.** `pcie-zx279128.c` + DT node
  `pcie@f000000` bring the bus up under the standard Linux PCI stack:
  `iATU: unroll F, 5 ob, 5 ib, align 64K`, `PCIe Gen.1 x1 link up`,
  `pci 0000:01:00.0: [14c3:7663] type 00 class 0x000280`.
  Key fix: provide `.msi_host_init` returning 0 (no MSI receiver on this SoC),
  else dw_pcie_host_init fails -ENXIO looking for an "msi" DT interrupt. INTx
  needs no driver code in 6.6 - the PCI core resolves it from `interrupt-map`.
  Remaining: rebuild rootfs against this kernel config (module ABI mismatch),
  then CONFIG_MT7615E + firmware mt7663pr2h.bin + mediatek,mtd-eeprom on mtd3.
  See docs/WIFI.md rounds 100-104.
- **mt76 Wi-Fi** — untouched. Scoped in `docs/WIFI.md`: the part is
  MediaTek/Ralink (OUI `00:0c:43` from the Wi-Fi flash partition) and mt76 is
  already in OpenWrt, but it sits behind a **custom, non-DesignWare** PCIe root
  complex (`zte,ZX279127-pcie`) whose DT node carries no `reg`. A full
  reverse-engineered PCIe host driver is required first.
- **SMP** — **implemented and working** (`arch/arm/mach-zx279128/`): SCU enable
  from CBAR, pen-release trampoline copied into `zte,iram`, `sev` to wake CPU1.
  Both cores come online. Held behind `maxcpus=1` because the spifc controller
  produces SQUASHFS read errors under two-core bus load; see the measured matrix
  in `docs/BRINGUP.md`.
- **Intermittent boot failures — FIXED in round 96.** Root cause was NOT NAND:
  `zx_eth_datapath_init()` had been deferred to PHY link-up (round 79), so it
  ran at an unpredictable 27-65 s and sometimes collided with `preinit` reaching
  `mount_root` at ~27 s, corrupting binaries as they were paged in. Correlation
  was 9/9 across recorded boots. Fixed by running the init at probe (11.35 s,
  deterministic, before `init` starts). **0 failures in 6 consecutive cold
  boots**, against ~25-50% before. See docs/ETHERNET.md round 96. Cause was a stale *chip*
  page cache, not ECC: when a `PAGE READ` did not take effect the chip returned
  the previous page, and the driver's two verification reads agreed because the
  cache never changed. Fixed by reading a different page between the two
  verification reads. Four consecutive clean cold boots. See docs/NAND.md
  round 89.
- **On-die ECC — tested round 93, NOT usable**: the whole flash is written raw
  (U-Boot writes raw too), so the chip reports uncorrectable on nearly every
  page when ECC is enabled. Raw/raw is self-consistent. Chip facts corrected:
  OOB is 128 B (we use 64), required ECC is 8b/512B, ECC_EN powers up SET.
- **Bad-block handling — MISSING ENTIRELY** (no BBT, no isbad, no ooblayout) on
  a part guaranteed only 1004/1024 valid blocks. Top-ranked hypothesis for the
  residual ~25% boot failures. See docs/NAND.md round 93.
- **sysupgrade** — still outstanding.

## Known gaps

- **NAND read defect — RETRACTED (round 112). There was no read defect.** The
  suspect digests were md5(0xff-fill) and md5(0x00-fill): the blocks were simply
  erased, and our driver and U-Boot agreed all along. The real fault was a
  **silent write failure** (U-Boot's `nand write` does not check P_FAIL), fixed
  by erase+rewrite; all chunks then verified byte-exact from Linux. LESSON:
  compare any flash-region digest against the blank/zero constants before
  calling it anomalous, and verify written CONTENT rather than trusting
  `bytes written: OK`.
- ~~NAND read defect (round 110)~~ Reads are correct for a
  single short read but drift during a *continued* read: `dd bs=1048576` and
  even 8 chained 128 KiB reads return wrong data for a region that every
  individual 128 KiB read returns correctly. U-Boot reads the same region
  correctly and `nand bad` shows no bad blocks, so the flash content is fine and
  the bug is ours. Prime suspect is the driver page cache reusing
  `sp->cached_page` for `DATA_IN` instructions that carry no address. This is
  why the port cannot boot a rootfs larger than ~3 MB (mt76 pushes it to 4.7 MB).
  See docs/NAND.md round 110.

- **Config persistence — WORKING (round 130).** Verified across two power
  cycles: files under /etc and `uci` settings survive, `.fs_state` stays READY,
  and `mount_root` reports "switching to jffs2 overlay". Required all three of:
  `sp->prog_pending`/`sp->prog_row` (r128), `sp->pos` (r129), and the `deadc0de`
  seed written by flash-prep (r124).
- ~~round 122: "mount_root erases the overlay"~~ - timing refutes it (mount_root
  at t=29.9s, erases at t=75-137s) and `erase=128` was a cumulative-counter
  sample; real per-boot counts were 384/384/256. The boot logs `no usable overlay filesystem
  found, using tmpfs overlay` together with `erase=128` - exactly the 128 blocks
  of the 16 MiB `rootfs_data`. JFFS2 data does reach flash and survives a
  remount; it is wiped at the next boot by userspace. The driver write path is
  verified working (`wverify=0 wfail=0`). Fix belongs in fstools/config, not the
  driver.
- ~~Config persistence — round 121 "write-path problem"~~ RETRACTED: that test
  wrote to a non-erased page and compared against md5(2048 x 0xff). The overlay mounts correctly as JFFS2 on
  `/dev/mtdblock10`, but nothing reaches flash (partition stays all-0xff,
  `erase=0`). Reproduced WITHOUT JFFS2: a raw `dd` of one page to the erased
  partition reads back wrong while reporting success, and our P_FAIL check does
  not fire. Round 112 ran the same test on the same partition and it passed, so
  it is intermittent. **UBI would not fix this** - fix the write path first.
- ~~Config persistence — PLAN CHANGED (round 108): use UBI/UBIFS, not JFFS2.~~
  The round-99 "JFFS2 violates NOP=1" diagnosis was never tested, and review
  showed the driver's DATA_OUT does honour column offsets (so OOB writes land,
  oobavail=62 is ample). UBI handles NOP limits, wear levelling and bad blocks
  properly and is OpenWrt's first-class NAND backend. This is a MORE fundamental
  gap than Wi-Fi: a router that forgets config on every power cycle is not
  deployable.
- **Config persistence — 4 of 5 blockers fixed (round 98).** Overlay moved to a
  dedicated `rootfs_data` partition at 0x4000000 (outside every CRC),
  squashfs-split disabled, OOB layout added, and the chip's bogus MLC detection
  corrected (JFFS2 refuses MLC). `mount_root` now reports "switching to jffs2
  overlay" and root runs on real flash. **Remaining blocker: the NAND program
  path does not work** — a raw `/dev/mtd10` write reads back different data.
  See docs/NAND.md round 98.
- **spifc controller wedges ~90x per boot** (each a poll timeout + chip RESET),
  costing several seconds; `nobusy` ~400/5800 reads. Not fatal (`fail=0`) but it
  explains the slow BBT scan and boot.

## CURRENT STATE (paused at round 119 to fit antennas)

**On the board right now:**

| partition | contents | verified |
|---|---|---|
| kernel `0x700000` | `v119b` = 6.6.151 + PCIe + mt76 + calibration DT | written OK |
| header `0x1720000` | `v119b` header (hdr CRC 0x01c3c617) | written OK |
| rootfs `0xa00000` | `/tmp/h199a-rootfs-109.img` (4.7 MB squashfs, md5 of the
  padded partition image = `06479218fbd4e096abc91bed025e194c`) | byte-exact |

Rebuild inputs, if needed: `/tmp/h199a-v119b.{kernel,header}`,
`/srv/tftp/v119b-{kernel,header}.bin`, rootfs image `/tmp/h199a-rootfs-109.img`
(regenerate per docs/NAND.md round 94 if /tmp is cleared;
`openwrt-zte-h199a/images/h199a-rootfs-nopppoe.img` (now in the port repo's images/ dir) is the 3.0 MB pre-mt76 copy).

**Wi-Fi status (round 121): TX and RX confirmed by hardware counters.**
`iw dev phy0-ap0 survey dump` reports `channel transmit time: 47 ms` (beaconing),
`noise: -92 dBm` and `channel receive time: 469 ms` - the transmitter keys and
the receiver demodulates. No client has associated yet, so throughput/range are
unmeasured. Earlier detail: `mt7615e` binds to `14c3:7663`,
firmware `mt7663pr2h_rebb.bin` loads, `phy0` registers, `phy0-ap0` joins `br-lan`
in forwarding state, calibration from `mtd3+0x20000` gives the vendor MAC
`00:0C:43:26:60:00` and **24 dBm** on channel 36 VHT80.
**Not verified over the air** - the board had no antennas fitted, and an external
scan from the `tiny` Raspberry Pi did not see the SSID (that scan was taken while
the radio was still at 3 dBm).

**Antennas are now fitted.** External verification is still blocked: the USB
adapter available on the host is a Ralink RT3070 (2.4 GHz only) and our radio is
5 GHz; the `tiny` Pi is 5 GHz-capable but is reached over Wi-Fi and must not be
disturbed (passive `iw dev wlan0 scan dump` only - its cache holds just the
connected AP). A 5 GHz-capable scanner (phone, laptop) is the cheapest way to
confirm the SSID `H199A-TEST` on channel 36.

**PCIe port 1 (2.4 GHz MT7603E) hangs the board** - see docs/WIFI.md round 120.
Its DT node exists but is `status = "disabled"`.

**To resume:**
1. Power on, wait ~140 s for the flash boot.
2. `uci set wireless.radio0.disabled=0; uci set wireless.radio0.country=BR; uci commit wireless; wifi up`
3. Confirm `iwinfo phy0-ap0 info` still shows 24 dBm and the vendor MAC.
4. External check from `tiny`: **passive only** - `nmcli -f SSID,BSSID,CHAN,SIGNAL dev wifi list`.
   Do NOT run `nmcli dev wifi rescan` or change anything on `tiny`: it is reached
   over Wi-Fi and a disruption could lock us out.

## STATUS: Wi-Fi PROVEN END TO END (round 140)

A phone associated to the board's AP and passed traffic: DHCP lease issued
(192.168.1.112), 3072 rx / 214 tx packets, VHT80 at 433.3 Mbit/s tx and
390.0 Mbit/s rx, signal -37 dBm, 2 retries and 0 failures, and 5/5 ICMP replies
through the bridge. This closes the last unproven **Wi-Fi** claim. Note 433.3 Mbit/s is the
negotiated link rate, not measured throughput - Wi-Fi throughput is still
unmeasured. Still outstanding overall: sysupgrade, SMP, 2.4 GHz.

**Scope note:** this device is currently an **access point plus dumb switch**,
not a router. The four PHYs sit behind a single `eth0` with no switch/DSA driver,
and the GPON uplink is unsupported. There is also no GPIO driver, so no reset
button and no LEDs.

## STATUS: Wi-Fi WORKING as of round 118

OpenWrt boots from NAND with zero SquashFS errors and brings up the MediaTek
MT7613BE behind the reverse-engineered DesignWare PCIe root complex:

```
mt7615e 0000:01:00.0: N9 Firmware Version: 7663mp1827
/sys/class/ieee80211/phy0
```

The rootfs boot failure (rounds 109-118) was **`CONFIG_MTD_BLOCK` read-modify-write**
erasing the squashfs tail block, fixed with `read-only;` on the rootfs partition
in the DTS. The driver was never at fault - its own health counters read
`fail=0` throughout, which is what the review used to redirect the search.

## ROOT CAUSE NARROWED (round 160): ANY TCP payload is dropped

Measured at the driver boundary with the firewall stopped, so netfilter and
conntrack are excluded:

```
3 x TCP with a 1-byte payload  ->  rx_packets +0   (never reach the driver)
3 x UDP with a 1-byte payload  ->  rx_packets +3   (arrive normally)
```

Both are 60 bytes on the wire (Ethernet minimum padding), differing only in the
protocol byte. Payload-free TCP - SYN, SYN-ACK, ACK, FIN, RST - passes, as do
ICMP and UDP at any size up to 1442 bytes for management traffic (NOT line rate - see the state block).

So the delivered set is exactly the payload-free control frames (SYN, SYN-ACK,
ACK, FIN, RST), which is why connections establish but never carry data. This
kills every resource-based explanation - nothing about buffers, rates or DMA can
distinguish a 40-byte frame from a 41-byte one by protocol - and points at a
hardware classifier steering TCP data into an acceleration path the driver never
configured (`qmap[8]` and the queue config at 0x921d4000 are in the driver,
unexplained).

## LIMITATION: no TCP session terminating on the device works (rounds 145-158)

ICMP, UDP, ARP, DHCP and DNS all work over Ethernet at every size and at line
rate. **TCP connections that carry data do not** - in either direction, at any
size, including a 5-byte HTTP response - although the connection establishes and
crafted TCP frames to a closed port are answered with an RST.

Eliminated by measurement: frame size, rate, bursts, buffer-manager depletion,
free-list exhaustion, descriptor credits, scan window, ownership status, buffer-0
aliasing, GRO, checksums, IP discards, corruption, protocol classification, TCP
timestamps, concurrent TX during RX, netfilter, and the bridge.

Two real fixes did come out of the investigation: the RX consume-credit write
(round 150, cured a reboot-only wedge) and the poll interval (round 151, 4000 pps
from 48/400 to 399/400).

Capped at 13 rounds on both reviewers' recommendation. Practical consequence:
installing and updating still go through U-Boot TFTP, not scp/sysupgrade
in-band.

## (superseded) Ethernet RX wedge under load (round 149) - FIXED in round 150

Sustained line-rate receive does not merely drop frames - it kills the receive
path until a reboot. After a 2000-packet UDP blast: 63% delivered, then
`rx_packets` frozen, RXPROD (TMQ 0x170) stuck, 100% ping loss at every size, and
`ifconfig down/up` does NOT recover it. This explains every "bulk stalls"
observation since round 145. ICMP at ~80 pps never reaches the threshold, which
is why ping-based testing (including the soak harness) always looked healthy.

## Superseded: Ethernet does not carry bulk traffic (round 145)

ICMP at any size works (0% loss, 3.7-14.5 ms) and TCP connections establish and
exchange small messages - verified with tcpdump on the host. But **any bulk
transfer stalls**: `wget` of a 4 KiB file times out, as do 1 MiB and 17 MB.
Consistent with RX being driven by a 1 ms hrtimer poll over a 64-slot bounded
ring scan with no RX interrupt.

This invalidates the earlier "Ethernet is complete" claim: all of that evidence
was ICMP. **No throughput has ever been measured on any interface.**

## The stock fallback is SAFE (round 132 - corrects round 116)

Directly tested: rootfs digest identical before and after letting the stock
firmware boot to its login prompt (`998384963d4e46d710c9ffa2` both times), with
the JFFS2 overlay intact. The round-116 "stock corrupts our rootfs" warning is
**withdrawn** - it was inferred from a partition index and confounded by a
broken driver write path and mount_root formatting rootfs_data.

Keep bank B intact: it is the only recovery path without UART+TFTP.

## READ THIS BEFORE CALLING ANY DIGEST "ANOMALOUS"

Three separate multi-round investigations in this session (rounds 110-111,
round 117, round 121) were chasing digests that were simply **blank or
zero-filled flash**. Check every digest against this table FIRST:

| read size | md5 of 0xff fill (ERASED) | md5 of 0x00 fill (padding) |
|---|---|---|
| 512 B | `de03fe65a6765caa8c91343acc62cffc` | `bf619eac0cdf3f68d496ea9344137e8b` |
| 2 KiB | `e0deebd3c3f560212af17c68b9344bae` | `c99a74c555371a433d121f551d6c6398` |
| 4 KiB | `6ae59e64850377ee5470c854761551ea` | `620f0b67a91f7f74151bc5be745b7110` |
| 128 KiB | `41d2e2c0c0edfccf76fa1c3e38bc1cf2` | `0dfbe8aa4c20b52e1b8bf3cb6cbdf193` |
| 1 MiB | `2fdd6851b32ae931637d4845c037b550` | `b6d81b360a5672d80c27430f39153e2c` |

An erased NAND page reads `0xff`; `flash-prep.py` pads with `0x00`. A digest
matching either is not evidence of corruption - it is evidence of blank or
padded flash.

Also: `dd` to `/dev/mtdN` does **not** erase. Writing over a non-erased page
cannot work (NAND only clears bits), and the read-back will look like corruption.
Always `mtd erase <partition>` first.

## Flashing rule (rounds 109-115, learned the hard way)

U-Boot's `nand write` reports `bytes written: OK` even when blocks silently fail
to program (it does not check the chip's P_FAIL bit). This has now corrupted the
rootfs (rounds 109-113) and the kernel (round 115) in ways that cost several
rounds each.

**After every flash, verify every partition in full**: boot the initramfs kernel
over TFTP (`h199a-init.uImage`, self-contained so it does not depend on NAND)
and compare `md5sum` of each `/dev/mtdN` against the host file. A prefix check is
not enough - round 113's failure was in the last 128 KiB. If a partition
mismatches, `nand erase` + rewrite and re-verify; a repeat cycle usually lands.

## Soak testing (added round 131)

`./soak.sh [n]` runs n cold power cycles and checks shell, MTD partitions,
config persistence, Wi-Fi phy, ICMP and the absence of SquashFS errors/panics,
appending to `logs/soak-results.txt`. First full run: **8/8 pass (RETRACTED - see note)**.

Run it after any change that touches the driver, DTS or image layout - single
observations on this board have been wrong more often than right.

## Version control (added round 129)

`~/h199a-build` is now a git repo tracking the recipe, docs and this
handoff. `openwrt/` (the pinned upstream checkout), captured images, logs and
build artefacts are gitignored - `openwrt-zte-h199a/build.sh` reproduces them.

**Commit after every hardware-verified change.** Rounds 121-129 were made much
harder by having no history: a review could not determine when the `&& writing`
guard entered the driver, which left an unresolved contradiction between a
round-112 measurement and the round-128 diagnosis.

## Working practice

Every 3 rounds (90, 93, 96, ...) spawn a red-team reviewer and a web researcher
in parallel — see `REVIEW-CADENCE.md`. This is a standing user instruction and
is also recorded in the session goal. It exists because several multi-round
rabbit-holes in this project were only broken by outside review.

## Bench notes

- Flash only from U-Boot (catcher running); confirm `bytes written: OK`.
  Sending `tftp`/`nand` to a running Linux shell silently does nothing.
- Kill the boot-mode catcher by process name (`ps -eo pid,comm`), not `pkill -f`,
  which matches its own command line.
- The rootfs must be built **without** `kmod-pppoe`; its notifier dereferences a
  NULL `dev_net()` and panics when netifd configures the interface.
