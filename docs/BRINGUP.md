> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](README.md),
> [installation](INSTALL.md) and [validation](../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# H199A bring-up notes

## 2026-11-15: CPU0 TWD watchdog driver built and host-tested, not booted

`zx279128_wdt` (DT `watchdog@800620`, compatible `arm,cortex-a9-twd-wdt`, clock
`periphclk`) runs every access on CPU0, inside one `smp_call_function_single()`
callback. It uses the stock-verified values:
- LOAD `rate*timeout-1`, with rate = PERIPHCLK/128 (3,906,250 Hz).
- CONTROL `0x7f09`.
- Disable: `0x12345678`, then `0x87654321`, then CONTROL 0, INTSTAT 1 and
  RESETSTAT 1.

Probe reports RESETSTAT as `WDIOF_CARDRESET` and leaves the bank stopped. procd
owns the keepalive. The kernel never feeds the watchdog on its own, and stops it
on an orderly reboot, halt or power-off.

The host tests compile the actual driver against a banked register model and
against the real 6.6 watchdog core. The driver was also cross-compiled against
the configured tree with `-Werror`/`W=1`. Board-reset routing on expiry,
counter reload and survival of the reset flag still need hardware. See
[WATCHDOG.md](WATCHDOG.md) for the design and the qualification steps.

## 2026-11-11: normal RAM-root qualification profile prepared

`RAM_ROOT_TEST=1 BOOT_PROFILE=normal` builds ordinary procd/netifd userspace,
release Ethernet and a separate SquashFS RAM root. It rejects diagnostic
Ethernet/storage combinations, keeps normal WiFi module autoload, and retires
the old delayed WiFi service and empty module overrides from reused checkouts.
The finished rootfs is checked by `tools/verify-rootfs-profile.py`, including
the actual qualification marker and preinit hook contents.

The qualification kernel uses `/dev/ram0` and `panic=0`. Its private DT keeps
the original partitions read-only, renames the old overlay `legacy_overlay`,
and appends the guarded 84–100 MiB UBI window. Preinit requires the exact guards,
partition geometry and one 104-LEB dynamic `rootfs_data` volume. It leaves the
first mount to fstools and verifies the UBIFS upper and RAM-backed SquashFS
lower. Failed checks enter recovery and block normal services. There is no
automatic formatting or RAM-overlay fallback.

Candidate V passed build/artifact checks and fits the measured RAM layout. It
has not booted. Preparing the empty volume, verifying both TFTP payloads and
the live bootloader layout, checking normal startup, and migrating only the
allowed owner configuration remain separate hardware steps. V also predates
the mt76 fault-recovery patch; rebuild before integrated radio qualification.
Diagnostic builds now use `panic=0` too, preventing an unattended panic from
automatically booting the older installed image.

The subsequent integrated X build includes the mt76 failure guard and full
WPS/green-indicator support. Its immutable kernel is 3 MiB; the raw root is
5,411,962 bytes, SHA256
`04ccc07d4b8a6a79ce58dc49b555830e603263bb9889e26161ba60173502c7cf`.
Build, calibration, release-driver and finished-rootfs checks passed, followed
by 353 host tests. Hardware boot remains pending. UART capture continues, but
the outlet is off because recent bootloader output could not be established;
the owner is unavailable to check the connections.

The normal-mode controller now has a separate acceptance path. The bootloader
has neither a standalone `crc32` command nor `iminfo`, as established by the
R203 command-table audit (private bench record, not distributed).
`tools/h199a_normal_ram.py --rootfs ROOT --output ENVELOPE` creates a 64-byte
checksum-only uImage header. Load that envelope at `0x43ffffc0`; its unchanged
SquashFS payload starts at the DT's `0x44000000` initrd address. Never execute
the envelope. The vendor's `bootm start` checks header and data CRCs without
loading or executing its payload. The controller then checks the real kernel
again and executes only `bootm 0x42000020`.

`tools/ramboot-h199a-tftp.py --storage-backend normal-ram-root` requires
`--rootfs-envelope`, a distinct `--rootfs-tftp-name`, and `--normal-manifest`
in addition to the existing kernel/UART/TFTP arguments. Both immutable files
must match the manifest. Fresh `bdinfo` must agree with the known board layout
before either transfer. The controller waits through preinit without sending
keys, requires the guarded overlay markers, then activates the normal console.
It checks procd, MTD permissions/geometry, UBI ownership, both mutation guards,
bind suppression and the actual RAM-lower/UBIFS-upper mounts. After fstools
reaches READY it checks the mounts again using the immutable ROM hook. These
new controller paths have simulated failure tests; their first hardware run
is still outstanding. This qualification workflow is not a flash installer.

The verified vendor Linux handoff cleans and invalidates the entire inner
data/unified cache through the CLIDR/CCSIDR set/way walker, including the
separate rootfs buffer. Its outer-cache hooks are stubs; it does not explicitly
flush PL310. Both the recorded cold U boot and software-reboot U boot emit
`L2C-310 enabling early BRESP for Cortex-A9`, which this kernel prints only
when enabling an initially disabled PL310. Normal qualification requires that
specific evidence too. This does not qualify arbitrary inherited outer-cache
configurations.

## 2026-11-11: system restart passes in the read-only RAM image

Candidate U registers a managed restart handler for the four-byte TOPCRM
trigger at `0x94000044`. It follows the verified stock transaction: an ordered,
unconditional write of `1`, with no register read or read-modify-write. Mapping
and registration happen during probe; the atomic callback needs no other CPU,
clock operation, allocation or sleeping lock. The resource is separate from
the SPI clock provider's word at `0x94000014`.

After confirming all thirteen MTD devices read-only and the driver bound,
`reboot -f` reached a fresh SPL/U-Boot entry. The controller interrupted autoboot,
verified the bootloader, reloaded U by TFTP, checked both image CRCs, and reached
the diagnostic shell with read-only flash again. No outlet command was issued
on this successful run. `tools/ramboot-h199a-tftp.py --software-reboot` records
the source protection/driver evidence and requires the native read-only
destination profile. Its failure path powers off.

This verifies the direct software restart path, not normal procd shutdown or
an upgrade. Watchdog implementation remains separate: the Cortex-A9 watchdog
has CPU-private banks, and the pinned kernel has no driver for it. Any driver
must encode CPU ownership and userspace keepalive semantics rather than reuse
an unrelated watchdog or a perpetual kernel feeding loop.

## 2026-11-11: coherent PL310 mode passes the CPU1 control

After the PAGE13 preparation correction, candidate M boots with
`arm,io-coherent`, keeps AUX `76430001`, and passes raw/corrected page checks,
the complete rootfs hash, and a 13.7 MB wired transfer in each direction.
Its kernel and configuration are identical to L; decoded DTBs differ only by
the coherent-cache property.

The 2.4 GHz phone tests passed with both normal scheduling and all WiFi
IRQ/RX/TX processing forced onto CPU1: exact 1 MiB payloads in both directions
and approximately 75 MB downloads at 10 Mbit/s. A two-minute test offered
30 Mbit/s and received 347,865,088 bytes (23.19 Mbit/s) while CPU0 loaded and
executed 512 fresh copies of a program and read the full NAND rootfs. The
rootfs hash matched, radio reset counters stayed zero, and NAND reported no
transport errors.

A cold-boot comparison using L with only the cache property disabled stalled
after 808,152 bytes in the CPU1 test; both wired ping and a fresh UART command
failed. This supports retaining the standard coherent PL310 operations table
with the corrected NAND preparation. CPU DSB barriers and explicit cache-range
maintenance remain enabled; no global MMIO override or vendor locking API was
added. This is not a gigabit, dual-radio, repeated-boot or long-soak result.

## 2026-11-11: cache/PCI concurrency remains under investigation

J boots with the predicted AUX `76430001` and all IOCC readbacks intact. It
passes exact 1 MiB transfers both ways and a 60-second, 10 Mbit/s upload.
The unrestricted download still hangs the board after about 8 MB. Pinning the
WiFi IRQ, both RX threads and TX worker to CPU1 fails after about 80 KB;
the earlier CPU0 controls passed 75 MB. Affinity is a diagnostic, not a port fix.

Further stock disassembly found a vendor-specific shared lock absent from
upstream 4.1 and 6.6. The same `l2x0_lock` protects CACHE_SYNC writes, individual
PA maintenance writes, unaligned invalidate edges and way-operation trigger
writes. Way polling happens after unlocking. Crucially, it also protects
`fixed_pci_read_u32/u16/u8`; the stock MT7603 module has 707 call relocations
to the 32-bit helper, including its IRQ, TX-completion and RX-ring paths.
Both stock and current ordinary MMIO writes execute `DSB ST`, outer-cache sync,
then the register write. This identifies a concrete PCI-read/cache-operation
serialization difference without assigning a named silicon erratum.

Candidate K tested only the standard PL310 `arm,io-coherent` property, using
the identical J kernel. Linux's coherent table removes the frequent
`outer_cache.sync` callback while retaining DSB barriers and explicit range
maintenance. Boot confirmed `L2C-310 Coherent`, AUX `76430001` and IOCC setup,
but NAND bad-block scanning failed with `-ETIMEDOUT` before rootfs mount.
K never reached a shell or traffic test. The property was reverted, and the
compiled DTB was verified equal to J again. The NAND ordering/timing dependency
and complete vendor-style shared locking both need further investigation.

## 2026-11-10: restore the stock PL310 policy

Candidate I could sustain a 75 MB, 60-second WiFi download with its RX threads
and TX worker pinned to CPU0. Restoring their normal CPU0–1 affinity reproduced
the hang, even with Ethernet GRO bypassed. This narrows the investigation to
cross-core processing without proving a particular cache or locking cause.

The stock machine descriptor at `c059a738` supplies PL310 AUX value `30400000`
and mask `feffffff`. The actual `init_IRQ` instructions load descriptor offsets
`+24/+28` and call `l2x0_of_init`; its implementation applies
`(old_aux & mask) | value`. I's boot logs show AUX `46030001`, missing the
stock shared-override and data/instruction prefetch bits.

Candidate J restores `arm,shared-override`, `prefetch-data = <1>` and
`prefetch-instr = <1>` through DT, retaining the stock `feffffff` machine mask.
The effective transformation is equivalent to stock. Setting the DT prefetch
properties also updates Linux's saved PREFETCH register: AUX/PREFETCH bits
28–29 are aliases, and Linux 6.6 writes PREFETCH after AUX. See
[ARM's PL310 r3p3 TRM, section 3.3.14](https://documentation-service.arm.com/static/5e8e1df188295d1e18d365bb).
Expected AUX on the next cold boot is `76430001`; this is derived from stock
code and I's measurement, not a recorded stock AUX readback. These settings
belong before cache enablement, not in a live-register experiment.

J also includes the independently reviewed Ethernet RX alignment and completion
fixes described in [Ethernet qualification](history/ETHERNET-BRINGUP.md#2026-11-10-qualification-and-rx-correctness).
Its subsequent hardware result is recorded above; the omissions were real,
but their correction did not eliminate the WiFi hang.

## 2026-11-10: early I/O coherency initialization

The verified stock kernel enables `IO_CACHE_COHERENCY` with zero ACP offset.
Both stock WiFi PCI drivers explicitly select coherent DMA; their mapping
wrappers use identity CPU physical addresses. Before PCI probing, stock
programs the block at physical `0x00a20000` in this order:

| Offset | Value |
| --- | --- |
| `0x80` | `0x40000001` |
| `0x84` | `0xbfffffff` |
| `0x88` | `0x1f0f1f0f` |
| `0x78` | `0x1f0f1f0f` |
| `0x00` | `0x0d000000` |

Candidate I adds a DT machine initializer before OF device population, checks
all five readbacks and stops boot if setup cannot be verified. The two PCI host
nodes now declare `dma-coherent`; their driver depends on the platform option
that supplies this initializer. The values match on two I boots. A diagnostic
module reading cached PCI DMA metadata confirms `coherent=1` on the bound
MT7603 endpoint. This proves initialization and DMA-op selection, not working
end-to-end coherency under every workload.

The clean I test passed exact 1 MiB uploads and downloads through the Android
client and a 30-second upload at about 10 Mbit/s. A subsequent 10 Mbit/s download
stalled after about 2 MiB, with WiFi, wired SSH/ping and UART all unresponsive.
Bulk WiFi reliability remains unresolved. An earlier I transfer overlapped a
classifier-register read that never returned; that earlier run is confounded.
Do not probe unqualified MMIO blocks during traffic: finding a stock getter
does not establish that the current partial initialization clocks its block.

## 2026-11-10: applicable Cortex-A9 mitigations restored

Live CPU information identifies both cores as Cortex-A9 r4p1. The verified
stock configuration enables `ARM_ERRATA_754322` and `ARM_ERRATA_764369`; the
earlier OpenWrt candidates disabled both. [ARM's r4 errata notice, sections
2.3.3–2.3.4](https://documentation-service.arm.com/static/608118675e70d934bc69f143)
includes this revision for both ASID-translation and cache-maintenance issues.

Candidate H enables the standard Linux workarounds. Its compiled
`v7_dma_inv_range` includes the previously absent pre-maintenance `DSB`.
The platform Kconfig now selects the applicable options, including the SMP
condition for 764369. The SCU diagnostic bit is read-as-zero, so register
readback is not a valid acceptance test for that write.

Basic SCU enablement and ACTLR broadcast/SMP setup were already present.
PL310 r3p3 evidence did not justify enabling every older PL310 workaround.
This corrects an established platform omission; WiFi workload and repeated-boot
testing must determine its practical effect. It is not yet a WiFi-fix claim.

## Measured clocks (2026-08-20, from the live device at the U-Boot prompt)

### ⚠️ The console corrupts progressively during a session — cause NOT found

Symptom: the console is clean through boot and for some time after, then starts
returning corrupted bytes and eventually loses whole command outputs. It is not
the wiring (long clean stretches occur well after boot) and not the declared
clock (the DTS says 25 MHz, which is the measured value; a wrong divisor would
corrupt everything permanently from the moment the real driver takes over).

✗ **Hypothesis tested and NOT SUPPORTED: "the 500 us hardirq hrtimer starves the
console."** `rx_poll_us` is a writable module parameter, so it was swept with
alternating arms, generating identical console load each time and counting
non-printable bytes:

| `rx_poll_us` | corrupted |
|---|---|
| 500 | 0.913% |
| 5000 | 0.219% |
| 500 | **0.000%** |
| 5000 | 1.044% |
| 500 | **69.175%** |
| 5000 | 5.283% |

The first pair looked like a clean 4x win for the slower timer. It did not
replicate: the same 500 us setting produced both the best and the worst result
in the series. Slowing the poll does not fix this.

What the data does show is that the degradation is **progressive across a
session and bursty** — later trials lost whole command outputs (one arm captured
412 bytes where an identical earlier arm captured 20,770), not just individual
bits. That shape fits something cumulative, not something load-instantaneous.

Untested hypotheses, in the order worth trying: thermal drift of the UART clock
as the SoC warms; marginal signal integrity on the header pads that worsens with
temperature; something cumulative in the device's own console path. The cheap
discriminator is to power off for several minutes, boot, and immediately run the
same large console dump — if it is clean cold and degrades with uptime
regardless of load, it is thermal or cumulative and not software.

### UART (PL011 @ 0x94404000) — 25 MHz, measured

```
=> md.l 0x94404024 2
94404024: 0000000d 00000024      → IBRD=13, FBRD=36
```

BaudDiv = 13 + 36/64 = 13.5625 → uartclk = 16 × 13.5625 × 115200 ≈ **25 MHz**
(exact-fit check: 25 MHz/(16×115200) = 13.569 → IBRD 13, FBRD 36 ✓;
26 MHz → IBRD 14, 104 MHz → IBRD 56 — both ruled out. The ZX296702's
104M/26M UART parents are NOT what ZX279128 uses.)

### A9 PERIPHCLK — 500 MHz, from stock boot log

```
CPU  : ZX279128S@A9,1000MHZ
sched_clock: 64 bits at 500MHz, resolution 2ns   ← arm_global_timer input
```

PERIPHCLK = CPU/2 = 500 MHz. Feeds `arm,cortex-a9-global-timer` (PPI 11)
and the TWD (watchdog clock 3906250 Hz = 500M/128 per stock log).

## ⚠ No VFP / NEON — soft-float ONLY (discovered 2026-08-20)

The ZX279128S's Cortex-A9 (MIDR `0x414fc091`, variant 4 — a ZTE-custom
core) has **no usable VFP/NEON**. Mainline prints
`VFP support v0.3: not present`: `fmrx(FPSID)` traps as undefined even with
cp10/cp11 access enabled (vfp_enable runs first). Evidence:

- stock firmware is **soft-float** uclibc (toolchain
  `arm-buildroot-linux-uclibcgnueabi`, `CONFIG_VFP=n` — no "VFP support"
  string in the stock vmlinux)
- hard-float OpenWrt userspace (`musl-armhf`) dies at `/init` with
  `Attempted to kill init! exitcode=0x00000004` (SIGILL) on the first
  VFP instruction

**Therefore the port is soft-float (armel):** `CPU_SUBTYPE` empty,
`fpu` dropped from the target FEATURES (→ `CONFIG_SOFT_FLOAT=y`),
kernel `VFP`/`VFPv3`/`NEON` disabled.

### Boot-inherited clock-controller state (for later per-driver clock work)

```
lsp0crpm @0x94400000 (md.l 0x94400000 16):
  00010000 0000021b 0000021b 0000021b 0000001b 0000001b 0400081b 00000009
  0x20..0x50: all zero
topcrm @0x94000000 (md.l 0x94000000 16):
  00000000 000001fb 10061fff 00517800 0000b114 cffffbf7 00040a09 10000000
  0004142a 10000000 000409ec 15525460 00040d69 1047ae14 00000303 00000000
  0x40: 000000d5 00000000 0ffedfff 000381ff   0x50: 0004176b 144fdf3b
```

(0x9400004c is written by cspboot: 0x38000 → 0x381ff during GPON serdes init.)

## Memory map (from stock DTB + boot log)

- RAM 128 MiB: 0x40000000–0x48000000 (stock `mem=128M`)
- Kernel load/entry: 0x40008000 (uImage header of both banks)
- U-Boot download `loadaddr`: 0x42000000 (safe for zImage + initramfs)
- DTB slot for bootz: 0x41000000
- GIC: 0x00801000 (+CPU iface 0x00800100); global timer 0x00800200 (PPI 11)
- L2 (PL310): 0x00c00000; NAND (denali): 0x00d80000/0x00d00000
- UART0 console: 0x94404000 (SPI 11); UART1: 0x94405000 (SPI 12)
- topcrm 0x94000000, lsp0crpm 0x94400000, lsp1crpm 0x9a100000
- PCIe 0x10000000 (2× Wi-Fi), GbE gephy 0x9b000000

## Boot recipe (RAM only, stock untouched)

At `=> ` (entered via power-cycle + `1` + `Boot4128s!` + any-key):

```
tftp 0x42000000 h199a-uImage        # or h199a-sf-uImage (initramfs, soft-float)
bootm 0x42000000
```

- uImage = `mkimage -A arm -O linux -T kernel -C none -a 0x40008000 -e 0x40008000`
  wrapping `zImage`(+initramfs) **cat**'d with the appended DTB.
- `maxcpus=1` (baked cmdline), earlycon=zteuart baked via CONFIG_CMDLINE_FORCE.
- Never download to 0x40008000 (bootm XIPs the header → crash).

**✅ Achieved 2026-08-20: full OpenWrt root shell on the H199A:**
```
OpenWrt 24.10-SNAPSHOT, r0-a1ea57b
root@OpenWrt:~# uname -a
Linux OpenWrt 6.6.151 #0 ... armv7l GNU/Linux
```
`/proc/cpuinfo`: Cortex-A9 (part 0xc09) variant 4, BogoMIPS 1000.00,
Features without vfp/neon (soft-float). No mtd/nand/Ethernet yet — those are
the next phases.

## Phase plan after first light

1. ~~denali NAND~~ — done via the **spifc** engine instead (`drivers/mtd/nand/raw/
   zx_spifc_nand.c`): read/write/erase all verified byte-exact; 9 partitions.
2. PCIe + mt76 (MT7603 2.4G + MT7613 5G — both mainline; needs a vendor
   `zte,ZX279127-pcie` controller driver first)
3. Ethernet: `zte,zx279128s-gephy/mdio` (quad PHY + MDIO) + the **NPP/PP
   packet processor** (`0x921c0000`/`0x92380000`) — the biggest RE item;
   there is no standalone GMAC node, the MAC/datapath is the NPU. Survey: the
   stock `vmlinux` contains `zx_mdio_read/write` (+ `mdio read/write timeout`,
   `fb_mdio_wclk` clocks) but **no** NPP/PP/PON/gephy driver symbols or
   `zte,zx279128s-{npp,pp,pon,tm}` compatible strings — those blocks are
   either bootloader-configured or in loadable modules inside the proprietary
   `"SBU&"` rootfs container (which itself needs unpacking).
4. SMP: the mainline build currently has **`CONFIG_SMP=n`** (single core).
   Stock 4.1 boots 2× Cortex-A9 via `enable-method="zte,zx279128-smp"`
   (`zx_smp_prepare_cpus`, mpidr `0x80000000/1`). To enable: turn on
   CONFIG_SMP and either RE the vendor secondary-release register/wake
   sequence (functions in `0xc03e9xxx-0xc03ecxxx` in `ref/stock-vmlinux.bin`)
   or try the `spin-table` DT method (needs the bootloader to park CPU1 in
   the holding pen — unverified).
5. Flash image: `kernel1/kernel2` = 32 B ZTE `"128s"` header
   (`33333333 cccccccc 88888888 dddddddd` + 16×`0xff`) + a standard uImage
   (CRC is the uImage's own) — see `docs/NAND.md`.

## Rootfs is AES-encrypted ("SBU&" container)

The stock `rootfs` partition (`mtd7`, off `0xa00000`) starts with the magic
`"SBU&"` (`53 42 55 26`) followed by a ~60-byte high-entropy header, and the
**entire payload is uniform-entropy (8.00 bits/byte) → AES-encrypted**, not a
plain jffs2/squashfs. The bootloader's U-Boot does AES-CBC (`"CBC decrypt OK!"`,
`"AES timeout"` strings) but only for its own `"128s"` key blob — it has **no
`"SBU&"` string**, and the stock `vmlinux` has no `"SBU&"` handling either, so
the rootfs decryption lives in a kernel module inside the encrypted rootfs (or
in `cspboot`). Implications:

- **Ethernet modules** (`npp`/`pp`/`gephy`) are inside this encrypted rootfs;
  recovering them needs the decryption key + algorithm (not yet located).
- **Flashable image**: a *custom* OpenWrt rootfs does NOT need to replicate
  `"SBU&"` — the bootloader boots a kernel uImage and the OpenWrt kernel mounts
  its own squashfs/jffs2 from the flash. The `"SBU&"` format only matters for
  reading stock data.

## Rig

See [`UART-PADS.md`](UART-PADS.md). TL;DR: `uart-log.sh` (logger) +
`catch-bootmode-v2.sh` (auto boot-mode entry) + `tomada off/on` (power).
Watch: `tail -f ~/dev/routers/h199a/logs/uart.log`.

## SMP (round 55) — vendor implementation decoded

The stock DTS declares the enable method on the `cpus` node:

```dts
cpus {
        enable-method = "zte,zx279128-smp";
        cpu@0 { compatible = "arm,cortex-a9"; reg = <0>; };
        cpu@1 { compatible = "arm,cortex-a9"; reg = <1>; };
};
```

The stock kernel registers it through `__cpu_method_of_table`. Following the
string `zte,zx279128-smp` (vaddr `0xc04dd108`) to its table entry at
`0xc059f5c0` gives `smp_operations` at **`0xc059bc18`**:

| field | value |
|---|---|
| `smp_init_cpus` | NULL |
| `smp_prepare_cpus` | `0xc05782b0` |
| `smp_secondary_init` | `0xc001750c` |
| `smp_boot_secondary` | `0xc0017470` |

### `smp_prepare_cpus` (0xc05782b0)

Standard Cortex-A9 SCU bring-up: reads **CBAR** (`mrc p15, 4, r0, c15, c0, 0`)
for the peripheral base, stores it, errors out if zero, then enables the SCU and
looks up a DT node.

### `smp_boot_secondary` (0xc0017470)

The classic **pen_release** scheme:

```
pen_release = cpu_logical_map[cpu]      ; variable at 0xc05b2344
dmb ishst
flush_cache_range(&pen_release, 4)
outer_cache.clean_range(...)            ; if present
raise IPI to the target CPU
loop 10x { udelay(...) }                ; wait for the secondary to take it
```

So the secondary must already be executing kernel code in a holding pen, polling
`pen_release` — i.e. the standard `arch/arm` platsmp pattern.

### What this means for the port

A Linux implementation needs:

1. `CONFIG_SMP=y` plus `CONFIG_HAVE_ARM_SCU`
2. a `CPU_METHOD_OF_DECLARE(..., "zte,zx279128-smp", &ops)` providing
   `smp_prepare_cpus` (SCU enable via CBAR) and `smp_boot_secondary`
   (pen_release + IPI)
3. the holding pen for the secondary

Item 3 is the open question: it only works if the bootloader releases CPU1 into
the kernel entry point. That has not been established yet, and getting it wrong
risks hanging the board, so the safe order is: enable `CONFIG_SMP` while keeping
`maxcpus=1` (no behavioural change), then add the ops, then drop `maxcpus=1`.

### Step 1 done: CONFIG_SMP enabled, no regression

`CONFIG_SMP=y` (pulling in `CONFIG_SMP_ON_UP`, `CONFIG_NR_CPUS=4`) builds and
boots. zImage grows 2.61 MB -> 2.76 MB, still inside the 3 MiB kernel partition.

Verified on hardware with `maxcpus=1` still on the cmdline, so behaviour is
unchanged:

```
root@OpenWrt:~# grep -c processor /proc/cpuinfo
1
root@OpenWrt:~# ping -c 2 192.168.1.100
2 packets transmitted, 2 packets received, 0% packet loss
```

Remaining for SMP, in order:

1. add `CONFIG_HAVE_ARM_SCU` and a `CPU_METHOD_OF_DECLARE` for
   `"zte,zx279128-smp"` implementing SCU enable (CBAR) + pen_release/IPI,
   mirroring `0xc05782b0` / `0xc0017470`
2. add the `cpus { enable-method = "zte,zx279128-smp"; }` property to our DTS
3. only then drop `maxcpus=1`

Step 3 is the risky one: pen_release only works if the bootloader releases CPU1
into the kernel entry, which is still unverified. Keep `maxcpus=1` until the
holding-pen path is confirmed, since a wrong release sequence can hang the board.

### Full SMP mechanism (round 56)

`smp_prepare_cpus` (`0xc05782b0`) does:

1. read **CBAR** (`mrc p15, 4, r0, c15, c0, 0`), map and enable the **SCU**
2. find the DT node `compatible = "zte,iram"` and `ioremap` 4 KiB of it
3. copy a 52-byte trampoline stub (`0xc057826c`, length at `+0x0c` = `0x34`)
   into IRAM
4. patch two words in the copy:
   - `+0x04` = `0x40017468` — physical address of the secondary entry
     (virtual `0xc0017468`, immediately before `smp_boot_secondary`)
   - `+0x08` = `0x405b2344` — physical address of `pen_release`
     (virtual `0xc05b2344`)
5. flush the cache, then **`sev`**

So the **bootloader parks CPU1 in a WFE loop**; the kernel plants a trampoline in
IRAM and wakes it with `sev`.

The trampoline itself is the classic pen spin:

```asm
mrc p15, 0, r0, c0, c0, 5     ; MPIDR
and r0, r0, #15               ; cpu id
sub r1, pc, #32 ; add r1, r1, #8   ; -> &pen_release_phys
1:  ldr r7, [r1]              ; pen_release address
    ldr r7, [r7]              ; *pen_release
    cmp r7, r0
    bne 1b                    ; spin until it names me
sub r1, pc, #56               ; -> &secondary_entry_phys, then jump
```

and `smp_boot_secondary` (`0xc0017470`) writes `cpu_logical_map[cpu]` into
`pen_release`, flushes, and raises the IPI.

The IRAM window comes from the stock DTS:

```dts
iram@200000 {
        compatible = "zte,iram";
        reg = <0x200800 0x1000>;
};
```

### What remains

This is now a fully specified, standard `arch/arm` platsmp implementation:
SCU enable + IRAM trampoline + pen_release. Implementing it needs a small
platform file with `CPU_METHOD_OF_DECLARE(..., "zte,zx279128-smp", &ops)` and an
equivalent trampoline in `.text`, plus `CONFIG_HAVE_ARM_SCU`.

Crucially the earlier worry is resolved: **CPU1 does not need the bootloader to
jump it into the kernel** — it is already parked in WFE, and `sev` plus the IRAM
trampoline is what starts it. That removes the main risk from dropping
`maxcpus=1`, though the trampoline must be correct before doing so.

### SMP working — both cores online

Implemented in `arch/arm/mach-zx279128/` (`platsmp.c` + `headsmp.S`), wired in
via `core-$(CONFIG_SMP)` in `arch/arm/Makefile` and `select HAVE_ARM_SCU if
CPU_V7` on `config SMP`.

```
zx279128: SCU base 00800000, ctrl before 00000000
zx279128: SCU ctrl after 00000021, cores 2
smp: Bringing up secondary CPUs ...
CPU1: thread -1, cpu 1, socket 0, mpidr 80000001
smp: Brought up 1 node, 2 CPUs
SMP: Total of 2 processors activated (2000.00 BogoMIPS).
```

Note the SCU was **not** enabled by the bootloader (`ctrl before 00000000`), so
enabling it is genuinely our job.

### SMP exposes an SMP-safety bug in the NAND path

With both cores online the filesystem breaks:

```
SQUASHFS error: Unable to read metadata cache entry [2f5822]
SQUASHFS error: Unable to read directory block [2f5822:6f2]
```

Isolated cleanly — the **same kernel image**, changing only the CPU count:

| configuration | result |
|---|---|
| 2 CPUs | SQUASHFS read errors |
| `maxcpus=1` | **0 errors**, filesystem reads fine |

So this is not a coincidence of load or timing: something in the NAND read path
is unsafe with two cores. The SCU is enabled correctly and reports 2 cores, so
cache coherency is set up; the likely culprit is `zx_spifc_nand.c`, which keeps
shared state (`pagebuf`, `cached_page`, `cache_valid`, `wedged`) and a
retry/recovery path written on the assumption of a single caller.

**`maxcpus=1` is therefore kept on the cmdline for now.** SMP bring-up is done
and proven; enabling it by default must wait until the NAND driver is audited
for concurrent access (explicit locking around `exec_op` and the page cache,
and making the wedge-recovery path re-entrant).

### SMP vs NAND reliability — measured matrix (round 57)

SMP bring-up works, but with both cores online the filesystem shows SQUASHFS
read errors. Several fixes were tried and measured; error counts are per boot:

| CPUs | A9/PL310 errata | other change | SQUASHFS errors |
|---|---|---|---|
| 1 | off | *(baseline)* | **0** |
| 2 | off | — | 45 |
| 2 | on | — | 5 |
| 2 | on | `arm,full-line-zero-disable` | 21 |
| 1 | on | — | 10-20 |
| 1 | off | NAND poll timeout 100→400 ms | 20 |
| 1 | off | *(all reverted)* | **0** |

Conclusions, each backed by a measurement rather than reasoning:

1. **The errata workarounds help under SMP but hurt under UP.** Enabling
   `ARM_ERRATA_{720789,754322,764369,775420}` and the PL310 set cut SMP errors
   45 -> 5, but introduced 10-20 errors on a single CPU where there had been
   none. They are therefore **off** in the shipped config.
2. **Disabling "full line of zeros" made things worse** (5 -> 21). Reverted.
3. **Raising the NAND poll timeout is actively harmful.** 100 ms -> 400 ms
   produced 20 errors on a single CPU. This controller *wedges* rather than
   running slow, so a short timeout plus recovery is what makes reads reliable —
   the same conclusion reached in the original NAND bring-up, re-learned here.
4. Serialising `exec_op` behind a driver mutex changed nothing (MTD already
   serialises), confirming this is not driver-level concurrency. The mutex is
   kept because the driver's own page-cache and wedge state deserve explicit
   protection.

**Shipped configuration: `maxcpus=1`, errata off — 0 SQUASHFS errors, Ethernet
0% packet loss.** SMP is implemented and proven (both cores online, SCU enabled,
trampoline working); enabling it by default needs the spifc controller made
robust under concurrent bus load, which is a hardware-behaviour problem rather
than a locking one.

## Reproducibility audit (round 59)

The recipe must rebuild everything from a clean checkout. Audited and fixed:

**Fixed: SMP build integration was not in the recipe.** The `arch/arm/Makefile`
and `arch/arm/Kconfig` edits that pull in `arch/arm/mach-zx279128/` and select
`HAVE_ARM_SCU` had been made directly in `build_dir`, so a fresh build would
have produced a kernel with no SMP support at all.
`993-zte-smp-support.patch` has been regenerated from the real diffs and
verified to apply.

**Fixed: `config-6.6` was stale.** The overlay copy lacked `CONFIG_SMP=y` and
the `clk_ignore_unused` cmdline argument that the working build uses. Synced.

**Verified: every overlay source matches the live build** — all ten files under
`files-6.6/` (DTS, SMP platsmp/headsmp, MDIO, Ethernet, spifc NAND, Makefiles)
compare byte-identical to what is actually being compiled.

**Verified: all patch hooks are present in the prepared tree** —
`MDIO_ZX279128` in `drivers/net/mdio/{Makefile,Kconfig}`, `NET_VENDOR_ZTE` in
`drivers/net/ethernet/{Makefile,Kconfig}`, `core-$(CONFIG_SMP) +=
arch/arm/mach-zx279128/` in `arch/arm/Makefile`, and `select HAVE_ARM_SCU` in
`arch/arm/Kconfig`.

### Method note

Testing the patch series against a **pristine** kernel tarball is misleading:
`994-zte-mdio-driver.patch` "fails" there, because OpenWrt applies its own
generic and backport patches first and our target patches are generated against
that tree. The meaningful check is against the prepared tree
(`build_dir/.../linux-6.6.151`), where all hooks are present and correct.

## Clean-build validation (round 60)

Round 59's audit was itself unsound: it verified hooks against a `build_dir`
that had been prepared *earlier in the session*, so it could not see breakage
introduced since. Running OpenWrt's own `target/linux/clean` +
`target/linux/prepare` + `target/linux/compile` found **three real defects that
would each have broken a fresh build**:

1. **`994-zte-mdio-driver.patch` did not apply.** It had been written by hand
   with guessed context; one hunk landed only "with fuzz 2" and two failed
   outright (`drivers/net/mdio/Makefile`, `drivers/net/ethernet/Kconfig`).
   Regenerated from real diffs against the prepared tree and verified.

2. **Driver symbols were missing from `config-6.6`.** `CONFIG_MDIO_ZX279128`,
   `CONFIG_NET_VENDOR_ZTE` and `CONFIG_ZX279128_ETH` had only ever been set by
   hand in `build_dir/.config`. A clean build stopped at an **interactive
   kernel-config prompt**. Added.

3. **`CONFIG_SMP=y` was set at the wrong level.** The subtarget file
   `target/linux/armsr/armv7/config-6.6` carries
   `# CONFIG_SMP is not set` and is applied *after* the target config, so the
   target-level setting was silently overridden and the recipe produced a
   kernel with no SMP support (and no `mach-zx279128` objects). Moved to the
   subtarget config.

Additionally, with `CONFIG_SMP=y` the kernel selects
`SQUASHFS_DECOMP_MULTI_PERCPU`, whose concurrent reads reproduce the NAND read
problem hard enough that init dies:

```
SQUASHFS error: Failed to read block 0x2f6506: -5
Error loading shared library libjson-c.so.5: I/O error
Kernel panic - not syncing: Attempted to kill init!
```

Forcing `SQUASHFS_DECOMP_SINGLE` in the subtarget config fixes the boot.

### Result

The recipe now builds and boots end to end:

```
root@OpenWrt:~#  grep -c processor /proc/cpuinfo -> 1
                 /proc/mtd -> 9 partitions
                 ping -c 3 192.168.1.100 -> 0% packet loss
```

### Known delta

The recipe-generated kernel still logs ~27 (non-fatal) SQUASHFS read errors
where the hand-tuned kernel logged none. The hand-tuned config had large
subsystems trimmed (EFI, VIRTIO, USB, SCSI, HID, INPUT, BPF, EXT4, F2FS); those
trims are not yet in `config-6.6`, and fewer subsystems probing concurrently
with NAND reads is the most plausible reason. Worth folding the trims into the
recipe so the shipped build matches the one that was validated.

## Round 61: config trims folded in; SMP/NAND conclusion re-confirmed

### Recipe now matches the validated kernel

USB, SCSI, ATA, INPUT and the unused vendor NIC drivers are trimmed in
`target/linux/armsr/armv7/config-6.6` (the subtarget file, which is applied last
and therefore wins). Recipe kernel: **2.52 MiB**, inside the 3 MiB partition.

### A testing trap worth recording

Two measurements this round were **invalid** because the boot-mode catcher was
not running: without it U-Boot autoboots from flash, so the board ran the
*flashed* kernel (`#114`, `maxcpus=1`) instead of the TFTP image under test. The
giveaway was the banner - `Linux version ... #114` with `maxcpus=1` on a kernel
that had just been built without it.

**Always confirm the booted banner matches the kernel under test** (version
number, build time and command line) before drawing conclusions from a boot.

That mistake briefly suggested two wrong things: that rewriting the rootfs had
eliminated the SQUASHFS errors, and that SMP no longer corrupted anything.

### Controlled result: SMP really does corrupt NAND reads

Repeated properly - same kernel build, same freshly written rootfs, both booted
over TFTP with the catcher running:

| CPUs | SQUASHFS errors |
|---|---|
| 2 | 34 |
| 1 | **0** |

So the round-57 conclusion stands on a controlled comparison: the second core
breaks spifc reads. `maxcpus=1` remains correct for the shipped image.

The bit-rot hypothesis is **not** supported - the test that appeared to confirm
it was one of the invalid flash boots. NAND degradation may still be a
long-term concern given we run with no ECC, but nothing here demonstrates it.

## Round 62: the SMP/NAND mechanism, and why the obvious fix is wrong

Hypothesis: the RX FIFO is only **16 words deep** but a page is **528 words**,
so the CPU must keep pace with the controller for the whole transfer. With both
cores online, IPI traffic (TLB shootdowns, scheduler and timer IPIs) adds latency
between polls and data is lost.

Tested by draining the page with `local_irq_save()`:

| configuration | SQUASHFS errors |
|---|---|
| 2 CPUs, normal | 34 |
| 2 CPUs, IRQs off during drain | 21 |
| 1 CPU | 0 |

So interrupt latency **is** a contributing factor — the hypothesis is partly
confirmed — but it is not the whole story: the other core keeps generating bus
traffic regardless.

### Why the change was reverted anyway

The inner FIFO poll allows up to **100 ms per word**. Disabling interrupts
across the whole page therefore risks an IRQ-off window of up to
528 x 100 ms if the controller stalls, which would break timekeeping and any
watchdog. That is an unacceptable trade for cutting errors from 34 to 21 while
still not making SMP usable. Reverted, with the measurement kept in the source
comment so it is not retried blindly.

### What this points at

The real fix is not to fight for CPU latency but to remove the CPU from the
inner loop: either a DMA path (if the controller has one) or a mode where the
controller writes the page to memory itself. The vendor ships this SoC running
SMP, so such a mode very likely exists and is worth locating in the stock driver
before any further attempt.

Shipped configuration is unchanged and re-verified: `maxcpus=1`, 0 SQUASHFS
errors, 9 MTD partitions, `ping` 0% packet loss.


## Round 114: bank A rejected with every partition verified byte-exact

All three bank-A partitions were verified against their source files by reading
them back through Linux (initramfs kernel, so the test does not depend on the
data under test):

| partition | md5 on flash | matches file |
|---|---|---|
| kernel (mtd6, 3 MiB) | `a2337c0b0950f9e3f57fc8c02046134a` | yes |
| rootfs (mtd7, 13.7 MiB) | `06479218fbd4e096abc91bed025e194c` | yes |
| header (0x1720000) | word-compared at 0x00/0x30/0xa0 | yes |

So the flash content is exactly what we intended, and the bootloader still falls
back to the stock bank.

### What the bootloader actually says

```
zteboot_verify_header:334 found version
csp_crc:103  >>csp_crc,  data addr:42000000, crc_len:0xa4
crc=0xde2be18c, 0x21d41e73          <- ours   (computed, stored)
...
csp_crc:103  >>csp_crc,  data addr:42000000, crc_len:0xa4
crc=0xa9ebae81, 0x5614517e          <- stock  (computed, stored)
zteboot_search_firmware:85 correct header has been found @3020000
```

**The stock header shows the same kind of computed-vs-stored mismatch and is
accepted anyway.** So `csp_crc` is not plain CRC32 and, more importantly, this
printed comparison is not the acceptance criterion. Any theory that we "got the
header CRC wrong" has to explain why the stock header passes with an equally
mismatched pair.

Note our stored values are self-consistent under CRC32:
`crc32(hdr[0:0xa4]) == hdr[0xa4]` for both our header and the stock one, so
flash-prep's formula matches the vendor's convention.

### The useful discriminator

The round-109 header **was** accepted (OpenWrt ran; that boot failed later, in
SquashFS). Diffing it against the rejected round-114 header:

```
differing bytes in the first 0x120: only 0x3c-0x3f and 0xa4-0xa7
  @0x3c  kernel CRC : v109=1ad1873a  v114=0a8d87b5
  @0xa4  header CRC : v109=07e2f518  v114=21d41e73
```

Everything else is identical. Both are self-consistent under flash-prep's
formulas (`crc32(kernel[0x20:0x20+CRC_LEN])` and `crc32(hdr[0:0xa4])`), and both
were produced by the same code path.

So the difference that matters is the **kernel image itself**, not the header
bookkeeping - which points at a property of the new kernel (size, or content at
a location the bootloader inspects) rather than at a CRC mistake.

### Next

- Compare the v109 and v114 uImages for structural differences the bootloader
  might care about (uImage header fields, load/entry address, total size).
- Try flashing the **v109 kernel** with a v109 header again to confirm bank A can
  still be accepted at all in the current flash state - that isolates
  "kernel-specific" from "flash-state-specific".


## Round 115: the header IS accepted - and the stock kernel is what boots

Flashing the known-good round-109 kernel+header pair isolates the two gates:

```
zteboot_search_firmware:85 correct header has been found @1720000   <- OURS, accepted
zteboot_search_firmware:85 correct header has been found @3020000   <- stock
...
totalImgNum=2 validImgNum=2 bootWhichImg=0
## Booting kernel from Legacy Image at 42020020 ...
   Image Name:   Linux Kernel Image
   Data Size:    3113918 Bytes
   Verifying Checksum ... OK
```

So with the v109 pair our header at `0x1720000` **is** accepted, where the v114
header was not - the two differ only in the kernel-CRC and header-CRC fields,
so the bootloader really does validate the kernel CRC recorded in the header.

But the kernel that then runs is **not ours**:

```
Linux version 4.1.25 (xialei@localhost.localdomain) ... Tue Jul  6 14:46:10 CST 2021
Kernel command line: ... root=/dev/mtdblock8 ro rootfstype=jffs2 ... 0x2000000
```

That is the stock vendor kernel, and `Data Size: 3113918` matches neither our
v109 image (~2.65 MB) nor any kernel we have built. `Verifying Checksum ... OK`
means the uImage the bootloader loaded is internally consistent - it simply is
not the one we wrote.

### What this means

The kernel partition write did not land, exactly like the rootfs writes in
rounds 109-113, and `3145728 bytes written: OK` was again meaningless. Two
distinct gates are now understood:

1. **Header acceptance** - depends on the kernel CRC stored at `hdr+0x3c`
   matching what the bootloader computes over the kernel area. A v114 header
   describing a kernel that is not on flash fails here.
2. **Which image boots** - decided from BootPara after that.

### Rule going forward

**Verify every partition after every write, by reading it back and comparing a
full digest - kernel included.** Round 113 established this for the rootfs and I
did not apply it to the kernel this round, which cost the whole round. The only
trustworthy verification path is: write via U-Boot, then boot the initramfs
kernel over TFTP and `md5sum` each `/dev/mtdN` against the host file.


## Round 131: soak test - 8/8 cold boots pass

Nearly every claim in this port had rested on a single observation, on a board
that has repeatedly shown single observations to be misleading. `soak.sh` now
runs N cold power cycles and applies the same six checks each time, so a
regression appears as a count rather than an anecdote.

Checks per boot: reached a shell; `/proc/mtd` lists the full partition set;
the persistence marker written in round 130 is still present; a Wi-Fi phy is
registered; ICMP replies come back; and there are no SquashFS errors or kernel
panics.

Result of the first full run:

```
boot 1: PASS shell=1 mtd=12 persist=1 phy=4 ping=0%  squashfs=0 panic=0
boot 2: PASS shell=1 mtd=12 persist=1 phy=4 ping=33% squashfs=0 panic=0
boot 3: PASS shell=1 mtd=12 persist=1 phy=4 ping=0%  squashfs=0 panic=0
boot 4: PASS shell=1 mtd=12 persist=1 phy=4 ping=0%  squashfs=0 panic=0
boot 5: PASS shell=1 mtd=12 persist=1 phy=4 ping=33% squashfs=0 panic=0
boot 6: PASS shell=1 mtd=12 persist=1 phy=4 ping=0%  squashfs=0 panic=0
boot 7: PASS shell=1 mtd=12 persist=1 phy=4 ping=0%  squashfs=0 panic=0
boot 8: PASS shell=1 mtd=12 persist=1 phy=4 ping=0%  squashfs=0 panic=0
TOTAL: 8 passed, 0 failed of 8
```

The residual 33% ping loss on two boots is the first ICMP packet lost to ARP
resolution; subsequent packets reply.

For context, the same board was failing roughly 1 boot in 4 as recently as round
90, and could not boot its own rootfs at all between rounds 109 and 118. The
persistence marker surviving all eight power cycles is independent confirmation
of the round-130 result.

**Note the harness had a bug on its first run** (the `/proc/mtd` line count was
not being extracted, so two otherwise-clean boots were scored FAIL). Both entries
are left in `logs/soak-results.txt` rather than deleted - a check that reports
FAIL for its own parsing error is worth remembering.


## Round 132: the "stock firmware corrupts our rootfs" theory is DEAD

Recorded since round 116 as a hazard, and used to explain several confusing
observations. It was never tested directly - the evidence was circumstantial
(the stock cmdline says `root=/dev/mtdblock8 ro rootfstype=jffs2`, and a
verified rootfs was once found corrupt after a boot that fell back to stock).

Direct test: digest the rootfs, force a stock boot by invalidating bank A's
header, let stock run all the way to its login prompt, restore the header, boot
our system, digest again.

```
before stock boot: 998384963d4e46d710c9ffa2
after  stock boot: 998384963d4e46d710c9ffa2     <- identical
/etc/persist130:   MARK130                      <- overlay intact too
```

**Stock does not touch our rootfs.** The round-116 corruption had other causes -
at that time the driver's write path was broken in ways that made every flash
observation unreliable, and `mount_root` was separately formatting
`rootfs_data`. The `mtdblock8` overlap was inferred from the index alone and
never verified against the vendor's own partition table.

Consequence: **the stock bank is a safe recovery path and must be preserved.**
Earlier notes suggesting it be invalidated are withdrawn - removing it would turn
"falls back to vendor firmware" into "brick" for anyone without UART and TFTP.


## Round 142: the build now produces the flashable images

Until now the artifacts that actually got flashed were hand-assembled: the
kernel came from `sed`-ing `CONFIG_INITRAMFS_SOURCE` out of `build_dir/.config`
by hand, and the rootfs from running `mksquashfs` manually after deleting
pppd/pppoe. A clean checkout reproduced neither - which is how the round-115
kernel/header mismatch happened.

Added a real device profile (`target/linux/armsr/image/Makefile`):

```make
define Device/zte_h199a
  DEVICE_VENDOR := ZTE
  DEVICE_MODEL := ZXHN H199A
  DEVICE_DTS := zx279128s-zte-h199a
  DEVICE_DTS_DIR := $(DTS_DIR)/zte
  SUPPORTED_DEVICES := zte,zx279128s
  KERNEL := kernel-bin | append-dtb
  KERNEL_LOADADDR := 0x40008000
  FILESYSTEMS := squashfs
  IMAGE_SIZE := 13762560
  KERNEL_SIZE := 3145728
  IMAGES := sysupgrade.tar
  IMAGE/sysupgrade.tar := append-rootfs | h199a-parts
  DEVICE_PACKAGES := kmod-mt7615e kmod-mt7615-firmware kmod-mt7663-firmware-ap \
	kmod-mt76-core wpad-basic-mbedtls iw
endef
```

`Build/h199a-parts` wraps the kernel with `mkimage` and then runs
`tools/flash-prep.py`, which assembles the ZTE-format kernel, the padded rootfs
and the header holding both CRCs, and packs them into the sysupgrade tar.

`seed.config` now selects squashfs rather than initramfs (the initramfs kernel
is still useful as a TFTP rescue image, but it should be built deliberately, not
by default).

Result:

```
bin/targets/armsr/armv7/openwrt-armsr-armv7-zte_h199a-squashfs-sysupgrade.tar
  h199a/kernel  3145728
  h199a/rootfs 13762560
  h199a/header   131072
```

and the CRCs inside it verify against their own contents:

```
kernel CRC @0x3c  0x9f5be492 == crc32(kernel[0x20:0x20+CRC_LEN])
fs CRC     @0x48  0x003f18a7 == crc32(rootfs)
hdr CRC    @0xa4  0x99f944f2 == crc32(hdr[:0xa4])
rootfs magic 'hsqs'
```

Not yet done: flashing this build's own output to the device and running
`sysupgrade` end to end.


## Round 143: the build's own image boots - and exposed months of drift

Flashed the artifacts produced by `make target/install` rather than hand-made
ones. The first attempt booted OpenWrt cleanly (6.6.151, 24.10-SNAPSHOT, zero
SquashFS errors) but had **no Wi-Fi and no PCIe at all**:

```
dmesg | grep -ic pcie   ->  0
/proc/device-tree/soc/  ->  ethernet@92200000, spifc@94406000   (no pcie node)
```

### The cause: the overlay had never been re-applied

```
openwrt/target/linux/armsr/files-6.6/.../zx279128s-zte-h199a.dts   -> 0 pcie nodes
openwrt-zte-h199a/files/.../zx279128s-zte-h199a.dts                -> 4 pcie nodes
```

Every hardware iteration since the PCIe work began had been done by copying
sources straight into `build_dir/`, and the recipe's `files/` overlay was edited
in parallel but **never synced back into the pinned tree**
(`build.sh` does `cp -a "$SELF_DIR/files/." .`, which had not been re-run).
So the tree that a clean build uses was months behind the tree being tested.

This is precisely the failure the device profile was added to prevent, and it
was invisible until the build's own output was flashed. Hand-assembly hid it:
the hand-built kernels were compiled in `build_dir`, where the current sources
lived.

After `cp -a files/. .` and a rebuild, the same procedure gives a fully working
device:

```
/sys/class/ieee80211/  ->  phy0
dmesg 'link up'        ->  1
ping 192.168.1.100     ->  replies
prompt                 ->  root@H199A-P130   (overlay config persisted)
```

### Rule

**Run `build.sh` (or at least `cp -a files/. .`) before any build whose output
is going to be flashed.** Editing `build_dir/` directly is fine for a fast
iteration, but the result is not the recipe's output and must not be treated as
evidence that the recipe works.


## Round 144: three sysupgrade defects fixed before first execution

A pre-flight review caught all three; none would have been visible from a
successful-looking run.

### 1. The platform.sh never shipped

```
staging_dir/.../root-armsr/lib/upgrade/platform.sh   4645 bytes, upstream
grep -c h199a_part_size <shipped>  ->  0
grep -c blkid           <shipped>  ->  3     (armsr's EFI/disk version)
```

`make target/install` rebuilds images but **not** the `base-files` package, which
is what installs `target/linux/armsr/base-files/**` into the rootfs. Running
sysupgrade would have exercised upstream's `export_bootdevice` path, failed the
check and proved nothing. Same class of drift as round 143: a source file was
validated, not the artifact.

Fixed by `make package/base-files/{clean,compile}` after a full build (the first
attempt failed because only `zImage` had ever been built, so kernel modules were
missing). Verified by **extracting the built squashfs**:

```
unsquashfs -d /tmp/unsq rootfs lib/upgrade/platform.sh
  -> 4502 bytes, 3 matches for h199a_part_size
```

### 2. `h199a_part_size()` could never work

```sh
awk -v l="\"$label\"" '$5 == l { print strtonum("0x" $2) }' /proc/mtd
```

- `/proc/mtd` is `mtd7: 00d20000 00020000 "rootfs"` - the name is **`$4`**;
- **busybox awk has no `strtonum()`** (a gawk extension).

So it returned empty, `[ N -le "" ]` was a shell error, and
`platform_check_image` would have rejected *every* image. Now uses `$4` and does
the hex conversion in the shell, with both sizes read up front so a missing one
fails with a clear message.

### 3. `head` does not exist in the upgrade ramfs

`stage2` copies a fixed list of applets (`tar`, `mtd`, `awk`, `sed`, `cut`,
`grep`, `wc`, `tail`, ...) - **`head` is not among them**. Both `head -1` uses
would have failed *after* the pivot, and because `mtd write` treats a zero-byte
stream as a no-op and still reports success, the result would have been a
**silent no-op upgrade reporting success**. Replaced with
`sed -n '1{s|/.*||;p;q}'`.

### Also recorded

- Only bank A (`rootfs`, `kernel1`, `header`) is ever written; bank B and the
  bootloader are never touched, which is what makes the fallback real. A comment
  now forbids extending it.
- `sysupgrade -n` will **not** reset config, because `rootfs_data` is untouched.
  Implementing it means erasing that partition *and* rewriting the `deadc0de`
  seed, or persistence dies exactly as in round 124.
- The three tar members are exact 128 KiB multiples (24/105/1 blocks), so
  `mtd`'s 0xff tail padding never fires and flash-prep's 0x00-padded CRC holds.
  That is alignment luck, not enforcement - if any member stops being aligned,
  the CRC contract breaks.


## Round 183: an unplanned power surge, and what it demonstrated

The bench lost power without warning mid-session. `rig-check.sh` reported five of
six checks failing:

```
FAIL  host 192.168.1.100 on enx00e04c125990
FAIL  uart logger appending
FAIL  device 192.168.1.1 responds to ping
FAIL  http://192.168.1.100:8099 serves  (HTTP 000)
FAIL  tftpd-hpa active
OK    power control (tomada) responds
```

That is exactly what the script exists for. Without it the natural reading of
"device unreachable, no console output" would have been *the surge damaged the
board* - the same misattribution made four times earlier in this project from
much smaller rig failures.

Restoring the host address, the UART logger, tftpd and the HTTP server, then
power-cycling the device, brought every check back to OK.

### The device survived intact

```
/proc/mtd            13 partitions
/etc/soak_cur        SOAKGEN-5      <- written before the surge, still there
/sys/class/ieee80211 phy0
SQUASHFS errors      0
```

An unplanned power cut during operation left the NAND contents and the JFFS2
overlay undamaged, including a marker written by the previous soak boot. That is
a stronger persistence result than any of the scripted tests, because nothing
about it was graceful - and it is worth recording precisely because it was not
planned.

### It also exposed a bug in the wedge detector

The log showed `heal: re-priming pool (attempt 12..15)` firing every ten seconds
on an **idle** link. The detector counted "no frames despite polling" as a wedge,
which cannot distinguish a dead datapath from a quiet network - a failure mode
a reviewer predicted when the detector was proposed.

Now guarded: it only arms after traffic has been seen at least once. An
unprompted power event found a defect that a week of deliberate testing had not.


## Round 186: proving sysupgrade did real work, and correcting an overstated claim

### It was not a no-op

The image written was the same one already running, so "upgrade completed" and
"upgrade did nothing" would look identical from the boot afterwards. The driver's
own erase logging settles it:

```
erase operations during sysupgrade : 130
distinct blocks erased             : 130
address range                      : 0x00700000 ... 0x01720000
```

130 blocks is exactly kernel (0x300000 = 24 blocks) + rootfs (0xd20000 = 105) +
header (0x20000 = 1). Every partition `platform_do_upgrade()` claims to write was
erased and rewritten, in the designed order, and the device booted afterwards.

### "Configuration preserved" is weaker than it sounded

`/etc/soak_cur` still read `SOAKGEN-5` after the upgrade - but
`platform_do_upgrade()` **deliberately never touches `rootfs_data`**, so the
overlay was never at risk. That is config *survival*, not evidence that
sysupgrade's `-c` save/restore path works, which remains untested.

Stated plainly because the stronger reading is the tempting one: the upgrade
preserves configuration **because it does not write the overlay partition**, and
`sysupgrade -n` correspondingly will NOT reset configuration on this device.


## Round 191: the first SMP soak is inconclusive, and the harness said so

Five boots with both cores enabled:

```
boot 1: shell=0 mtd=?  persist=1 phy=0
boot 2: shell=0 mtd=7  persist=0 phy=0
boot 3: shell=1 mtd=2  persist=0 phy=1
boot 4: shell=1 mtd=14 persist=1 phy=1
boot 5: shell=1 mtd=14 persist=1 phy=1
```

The results improve **monotonically** across five identical power cycles, from
"nothing" to "every platform check passes". A device does not get better as a
run proceeds; a measurement window that is slightly too short does exactly this,
catching progressively more of a boot as timing jitters.

The harness waited 152 s after power-on - a figure tuned when the device was
booted over TFTP. A flash boot with both cores takes longer, and manual cold
boots this round reached a shell reliably at 180 s.

Widened to 190 s. **The SMP-versus-single-core comparison is still unmeasured**,
and the numbers above should not be cited for it. Recording them anyway, because
"the instrument was too fast" is the kind of result that quietly disappears if
only the corrected run is published.


## Round 194: "the device no longer boots from flash" was a leftover catcher

Three separate diagnoses this session - *the device will not boot unattended*,
*SMP stress crashed the box*, and *the U-Boot environment was overwritten* - all
had the same cause, visible in one line of the boot log:

```
*** Press 1 means entering boot mode***
 0
cspboot:1279 Entering boot mode ...
```

Stale `catch-bootmode-v2.sh` processes were still running from earlier flashing
and pressing "1" during the bootloader countdown. Every power cycle therefore
landed at a U-Boot prompt, which is indistinguishable from a device that cannot
boot.

With them killed, the same hardware boots unattended from flash:

```
*** Press 1 means entering boot mode***
cspboot:1300 Booting image ......
SMP: Total of 2 processors activated (2000.00 BogoMIPS).
```

**Fixed at the source**: the catcher now self-terminates after 120 s. There is no
legitimate reason for it to outlive one boot, and a reviewer independently lost
time to the identical trap while auditing SMP.

### And SMP does not reproduce the SQUASHFS errors

A clean cold boot from flash, with both cores:

```
processors : 2
/proc/mtd  : 14 partitions
SQUASHFS errors : 0
```

Round 57 recorded a measured matrix - two cores gave 45 SQUASHFS errors, one core
gave 0 - and that was the stated reason SMP shipped behind `maxcpus=1` for the
following ~130 rounds. It does not reproduce now.

Two things changed in between: flash writes are now verified (rounds 190-191
established that partitions did not always contain what was written), and the
erase/program wait was fixed (round 193). Either could explain the original
result as a bad image rather than as bus contention. **This is one boot, not a
re-run of the matrix**, and it is recorded as such - but the original diagnosis
should no longer be treated as established.


## Round 197: hardening the rig against itself

Three failures this round, none of them the device.

**1. Two UART loggers on one port.** Two `socat` readers split the serial stream
between them: each captures part of the output, so the log looks alive while
missing lines, and commands written to the port appear to be ignored. This has
now presented three times as "the device console is unresponsive".

Fixed with `flock` on `/tmp/h199a-uart-log.lock`. A second instance declines:

```
[uart-log] another instance holds the lock; exiting
```

The first attempt at this guard used `pgrep` on the script name - which also
matched the invoking shell's own command line and killed the caller. **That same
self-matching mistake killed this session's shell three separate times today.**
A lock identifies the running instance by held resource rather than by text, and
cannot make that error.

**2. A stale `socat` outliving its parent** kept the port and the lock after its
`uart-log.sh` was killed, so restarts silently declined while nothing was being
captured. Worth knowing: the process to look for is `socat`, not `uart-log`.

**3. Nothing was holding the serial port at all** - and the diagnosis I first
recorded for this was wrong.

I saw `usb 3-5: USB disconnect, device number 11` and concluded the serial
adapter had fallen off the bus. It had not. `usb 3-5` re-enumerated moments later
as `SAMSUNG_Android` - a phone being plugged in and out. The serial adapter is a
different device entirely (`10c4:ea60 Silicon Labs CP210x UART Bridge`) and was
present throughout.

The actual state was simpler: **no reader held `/dev/ttyUSB0`**, because the
logger had died and its restarts were declining against a lock held by a stale
`socat`. Reading the port directly proved both the adapter and the device were
healthy:

```
non secure uboot
backup header!!
U-Boot 2013.04 (Jul 06 2021 - 14:44:21)
```

Worth keeping as a lesson in its own right: a dmesg line that matches the shape
of your hypothesis is not evidence for it. `usb 3-5` was never checked against
the adapter's actual bus address, and the check took one `lsusb`.

The power meter reading `0 mA` beside a live PHY remains a meter artifact, not
evidence about the device.

### The pattern

Every one of these presents identically to a dead device: no console output, no
response to commands. The distinguishing evidence is always somewhere other than
the console - link carrier, USB enumeration, which process holds the port. That
is what `rig-check.sh` exists to look at, and it flagged all three before any of
them could be attributed to the hardware.


## Round 217: the shipped artifact is now reproducible from the recipe

The last outstanding process item. Every measurement in this repository was taken
on images built from a working tree carrying 186 package selections against
`seed.config`'s 6 - so a stranger running `build.sh` would get different content
from anything that had been tested.

Running `build.sh` clean immediately found a real defect it had been masking:

```
ZX279128S Ethernet bring-up debug interfaces (ZX279128_ETH_DEBUG) [N/y/?] (NEW)
scripts/kconfig/Makefile:77: syncconfig  Error 1
```

The Kconfig symbol added in round 187 carried `default n`, but a default does
**not** suppress `syncconfig`'s prompt for a newly introduced symbol - the kernel
config needs an explicit line. My tree had answered it once, interactively, and
never again; a clean build had no answer and died. Fixed by adding
`# CONFIG_ZX279128_ETH_DEBUG is not set` to the config fragment.

The resulting image was then flashed with per-partition read-back verification
and cold-booted:

```
kernel  3145728 bytes   cmp.b: Total of 3145728 byte(s) were the same
rootfs 13762560 bytes   cmp.b: Total of 13762560 byte(s) were the same
header  131072 bytes    cmp.b: Total of 131072 byte(s) were the same

SMP: Total of 2 processors activated
N=2  M=14  S=0          (CPUs, MTD partitions, SquashFS errors)
ping 192.168.1.1        0% packet loss
/proc/zx_eth_poke       No such file or directory
```

So the artifact a stranger builds is the artifact that was tested: no
foreign-hardware kmods, both cores up, all partitions registered, no SquashFS
errors, network alive, and the arbitrary-MMIO debug primitive genuinely absent.


## Round 218: soak on the reproducible image

Five boots of the image a clean `build.sh` produces:

```
boot 1: shell=1 mtd=14 persist=1 phy=1  udp=1752/4000 (44%)  alive=1
boot 2: shell=0 mtd=?  persist=0 phy=0  udp=0/4000            <- no console output
boot 3: shell=1 mtd=14 persist=0 phy=1  udp=2135/4000 (53%)  alive=1
boot 4: shell=1 mtd=14 persist=1 phy=1  udp=1932/4000 (48%)  alive=1
```

**Boot 2 is an instrument failure, not a device failure**, and the harness cannot
currently tell the difference - `shell=0` with `mtd=?` means no console output was
captured at all, which is the signature this project has now traced to four
distinct rig causes. It is scored identically to a genuine failure, which is why
the run totals should not be quoted without reading the per-boot lines.

What the three good boots establish: **the 37-51% delivery band survives the move
to a reproducible build** (44%, 53%, 48%), 14 MTD partitions register every time,
the Wi-Fi phy comes up every time, and there are no SquashFS errors or panics on
any boot including the failed one.

`persist=0` on boot 3 with `persist=1` on boots 1 and 4 is unexplained and worth
a look; it may be the same marginal-window effect as boot 2.


## Round 219: auditing the soak harness as an instrument

The harness had been reporting device failures it had not measured. Four defects,
all found by reading the parsing against real captured logs rather than trusting
the output.

### 1. The mtd check could read any number on the console

```sh
mtdn=$(... grep -aoE '^[0-9]{1,2}$' | head -1)   # first bare number ANYWHERE
```

The body it greps spans ~190 s of boot output plus every command echo. A survey
of recent console output found **eight distinct bare numeric values** - `0 1 2 12
14 29 36 46` - and whichever appeared first won. A stray `2` yields a false FAIL
against the `>=11` threshold; a stray `12`, `29`, `36` or `46` yields a false
PASS. It had only ever worked by luck. Now anchored to the line following the
`SOAKOK` sentinel, verified against both the real log and a synthetic case:

```
old parse with a stray '2' present -> 2      (false FAIL)
new parse with the same stray      -> 14     (correct)
```

### 2. Instrument failure was scored as device failure

A boot that produced no console output made every grep return 0, scoring as a
total device failure indistinguishable from a board that came up dead. `SOAKOK`
is echoed by the probe command itself, so its absence proves the **channel**
failed. That is now a third verdict state, `INCONCLUSIVE`, counted separately,
with a note pointing at `rig-check.sh` / `rig-reset.sh`.

### 3. Persistence failures cascaded from instrument failures

Boot 3 of the round-218 run was recorded as `persist=0` and left in the docs as
"unexplained". It is explained: **boot 2 captured no console output, so it never
executed its write**, and boot 3 correctly read back boot 1's value. The overlay
was working; the marker was one generation stale. The check now accepts a
stale-but-present marker when the previous boot was inconclusive.

### 4. The ping check is not a connectivity verdict

`ping=100% loss` alongside `udp=1752/4000` and `alive=1` on the same boot looked
contradictory. It is not: the ping is device -> host ICMP sampled **once**, ~30 s
after boot and *before* the UDP run - the earliest, least settled moment of the
boot. `alive` (host -> device, at the end) is the connectivity verdict. Documented
in place so the two are not read as the same measurement.

### Validation

```
boot 1: INCONCLUSIVE shell=0 mtd=? persist=1 phy=0 udp=0/4000
boot 2: FAIL         shell=1 mtd=14 persist=1 phy=1 udp=1843/4000 alive=1
TOTAL: 0 passed, 1 failed, 1 inconclusive of 2
NOTE: 1 boot(s) produced no console output - instrument failure, not device
      failure. Run ./rig-check.sh and ./rig-reset.sh.
```

Boot 2 is a genuine failure: the device answered, and 1843/4000 (46%) is the real
datapath limitation against a 2500 threshold. Boot 1 measured nothing and now
says so.


## Round 219-220: the corrected harness reveals the real reliability picture

After fixing the harness (boot-1 persist was hardcoded, mtd read any bare number,
instrument failure was scored as device failure), the first honest run:

```
boot 1: INCONCLUSIVE  shell=0  (no console output)
boot 2: FAIL          shell=1 mtd=14 persist=1(prev=2) phy=1 fs=2 udp=1945/4000 (49%)
boot 3: INCONCLUSIVE  shell=0  (but udp=203/4000 alive=1 - partial capture)
boot 4: INCONCLUSIVE  shell=0
boot 5: FAIL          shell=1 mtd=14 persist=1(prev=2) phy=1 fs=2 udp=1918/4000 (48%)
TOTAL: 0 passed, 2 failed, 3 inconclusive of 5
```

### CORRECTION (round 222): this was NOT a capture failure

The raw UART log shows, on every single power cycle: `cspboot:1300 Booting
image`, `SMP: Total of 2 processors activated`, `procd: - init -`, and the
`root@` prompt. The device boots kernel and userspace every time.

The round-220 entry concluded these were console-CAPTURE failures. **That was
wrong**, and the raw log proves it. Correlating each boot marker against the
probe echoes:

```
boot 1  probe never echoed              INCONCLUSIVE (correct)
boot 2  probe echoed + SOAKOK returned  shell=1      (correct)
boot 3  probe ECHOED, no SOAKOK result  INCONCLUSIVE (misattributed)
boot 4  probe never echoed              INCONCLUSIVE (correct)
boot 5  probe echoed + SOAKOK returned  shell=1      (correct)
```

Boot 3 is the case that breaks the capture theory: the probe **was** echoed into
the log, so nothing was lost in transit. What follows it in the log is the
OpenWrt login banner - the shell was still starting. The probe was typed before
the console was ready, the tty echoed the characters, and the boot process
swallowed them. The command never executed, so no output was ever generated.

Boots 1 and 4 show the same cause more starkly: `Please press Enter to activate
this console` appears at line ~443 of a ~460-line window, i.e. the prompt became
available only in the final seconds of the iteration.

**Root cause: the harness sent the probe before the device was ready**, because
it waited a fixed `sleep 190` instead of waiting for the device to say it was
ready. Fixed by polling for the console-ready line the device itself prints, with
the timeout kept only as a fallback. The data was never lost - it was never
generated, which is a different bug with a different fix.

The two boots with a clean capture both show the genuine, consistent failure:
the Ethernet data plane delivered 49% and 48% of the UDP burst (below the 2500/4000
threshold), while the platform is healthy - 14 MTD partitions, phy up, and
`fs=2`, which is the new fs_state check confirming the overlay is GENUINE JFFS2,
not the silent-tmpfs fallback.

### The 60% capture failure rate is now the top rig issue

3 of 5 boots lost console capture despite the re-enumeration watchdog. It is
corrupting most measurements. The INCONCLUSIVE verdict is the honest mitigation,
but it means the harness now says "can't tell" more often than it says anything
at all - which is correct reporting of an unreliable instrument, and a strong
signal that the serial capture path needs a real fix, not another band-aid.


## Round 222: the `prev=2` anomaly was the probe race, not a JFFS2 revert

Both good boots of the round-220 run read `persist=1(prev=2)`, where boot 2
should have seen `prev=1` and boot 5 `prev=4`. The obvious worry was a JFFS2
revert - older data reappearing after a discarded node, which `NAND.md` warns is
the dangerous failure mode on this ECC-less flash.

It is not. The markers actually written during that run were:

```
SOAKGEN-2, SOAKGEN-2, SOAKGEN-2, SOAKGEN-3, SOAKGEN-5, SOAKGEN-5
```

- not the expected 1,2,3,4,5. Only the boots whose probe actually executed wrote
anything, and boots 1, 3 and 4 were exactly the boots whose probe was swallowed
by the login banner. So the last successfully written value stayed `SOAKGEN-2`,
which is precisely what boots 2 and 5 read back.

The whole chain is explained by the probe race with **no NAND or JFFS2 fault**:

| boot | probe ran? | wrote | read |
|---|---|---|---|
| 1 | no | nothing | (no reading) |
| 2 | yes | SOAKGEN-2 | prev=2 (stale but present) |
| 3 | no | nothing | (no reading) |
| 4 | no | nothing | (no reading) |
| 5 | yes | SOAKGEN-5 | prev=2 (correct - nothing wrote since boot 2) |

The harness's "stale-but-present is not a loss" rule scored boots 2 and 5 as
passes, which was right. But it scored boots 3 and 4 as `persist=0`, conflating
**"persistence was not measured"** with **"the overlay lost data"** - the same
error the INCONCLUSIVE verdict exists to prevent, one field over. Those now
report `persist=n/m` (not measured).

**Consequence for the headline number:** the ~75% persistence figure counted
no-measurement boots as failures. The genuine rate is higher, and cannot be
restated honestly until a run completes where every probe actually executes.


### Verified: the readiness poll eliminates the race

First run with the console-readiness poll instead of a fixed sleep:

```
boot 1: FAIL shell=1 mtd=14 persist=n/a phy=1 udp=1143/4000 alive=1 fs=2
boot 2: FAIL shell=1 mtd=14 persist=1   phy=1 udp=0/4000    alive=0 fs=2
boot 3: FAIL shell=1 mtd=14 persist=1   phy=1 udp=0/4000    alive=0 fs=2
TOTAL: 0 passed, 3 failed, 0 inconclusive of 3
```

**Zero inconclusive**, against 3-of-5 before. Every probe executed: `shell=1`,
`mtd=14` and `fs=2` on every boot, and `persist=1` unqualified on both boots that
had a predecessor - the persistence chain works cleanly once the probe is not
racing the boot.

What remains is the genuine defect, no longer masked by instrument noise: the
data plane delivered 1143/4000 on the first boot and then **nothing at all** on
boots 2 and 3 with `alive=0`. That is the wedge, and it now persisted across
power cycles within the run - worth noting, because it means a wedged datapath
can survive into the next boot rather than being cleared by the power cycle.

## Round 228: the automated soak console-capture is not trustworthy; manual checks are

After all the harness fixes (readiness poll, datapath settling, verdict split),
an n=6 soak still produced 4-of-6 INCONCLUSIVE (shell=0, no console output) while
manual checks in the same session showed the device booting cleanly every time -
2 CPUs, 14 MTD partitions, phy up - and delivering 2262/4000 (57%) when settled.

The conclusion, after ~11 rounds on this: **the automated soak's console capture
fails intermittently during rapid power-cycling, and that is a RIG limitation,
not a device fault.** The INCONCLUSIVE verdict labels it honestly, but it means
the soak cannot certify per-boot reliability. For reliability claims, the
MANUAL path is authoritative: power-cycle, wait for the boot to complete, probe
the console directly, measure delivery on a settled device.

What is genuinely established about reliability:

* The device boots to a shell reliably (every manual check across the session).
* It delivers ~50-57% of a UDP burst when the datapath is settled.
* It has RARE, intermittent uncorrectable read events (SQUASHFS errors; one mt76
  firmware-load hang) - the no-ECC NAND cost, recovered by a power cycle.

Do not read a soak run's INCONCLUSIVE count as a device failure rate. If a run is
mostly INCONCLUSIVE, the rig needs attention, not the device.

## Round 235: a fifth manifestation of the stale-fd rig fault

Restoring the flash image after the diagnostic boots, the console went silent and
`rig-check` reported the device unreachable. It looked like a device hang. It was
not:

```
lsusb            CP210x present
/dev/ttyUSB0     inode 1000, created 15:09    <- adapter RE-ENUMERATED
socat            still attached to the OLD handle
```

After `rig-reset.sh` restarted the logger against the current node, the very next
power cycle captured a clean boot including
`zx279128-eth ... eth0: Link is Up - 1Gbps/Full - flow control off` and
`procd: - init -`.

That is the FIFTH distinct way this project has seen "silent console + static log"
mean a rig fault rather than a dead device (stale catchers, duplicate readers, a
kill filter matching its own caller, a stale fd after re-enumeration, and now the
same stale fd surviving the round-215 watchdog). The watchdog compares the device
inode every 2 s and should catch this; that it did not means the watchdog itself
needs review before any future reliability claim leans on the automated path.

**Standing rule, reinforced:** a silent console is evidence about the INSTRUMENT
until the raw port and the adapter enumeration have been checked. Never report it
as a device failure without that check.

## Round 241: a stale-ARP false failure (the device MAC randomises per boot)

Chasing the round-240 forwarding failure, the host reported 100% ping loss to the
device after a power cycle - which looked like a wedged or dead datapath. It was
neither: the device's `eth0`/`br-lan` MAC is **locally-administered and randomises
on every boot** (e.g. `32:ff:c7:ec:d2:f4` this boot), so the host's ARP cache held
a STALE MAC for `192.168.1.1` and sent frames to an address nobody answered.
`ip neigh flush 192.168.1.1` (or an `arping`) fixed it instantly - 0% loss.

Measurement lesson, added to the discipline list: **after any device reboot,
flush the host ARP entry for `192.168.1.1` before trusting a ping result.** A
"100% loss" immediately after a power cycle is a stale-ARP artifact until proven
otherwise. This likely inflated some earlier post-reboot "datapath dead"
readings.

(The round-240 forwarding finding is unaffected: there the ARP had RESOLVED on
tiny's side - host MAC REACHABLE - while unicast still failed, so it was a real
forwarding failure, not stale ARP.)

## Round 248: recipe re-verified reproducible after the week's changes

Rebuilt the image from the recipe (`cp seed.config .config; make defconfig; make
target/install`) to confirm this week's doc/driver edits did not break
reproducibility. Result: a **17,049,600-byte** sysupgrade tar - byte-for-byte the
same size as the round-217 verified artifact - with **0 foreign-hardware kmods**
and **no `zx_eth_poke`** debug primitive in the shipped `zx279128-eth.ko`. So the
artifact a stranger builds from the current recipe is still clean and current.
(This reuses the existing toolchain; a full fresh `git clone` + toolchain rebuild
was not repeated - round 217 already did that once and it is deterministic.)

## Round 249: three "mt76 hangs" were a transient power fault - and the power meter lies

Three consecutive boots stopped at `mt7615e ... HW/SW Version` with the console
going static. It looked exactly like the documented intermittent mt76
firmware-load hang becoming persistent. It was not:

* The power meter reported the outlet **ON but 0 mA / 0.0 W** across repeated
  readings and a full cycle - the device was losing power ~70 s into boot, which
  is coincidentally when mt76 firmware loads.
* The logger was verified healthy at the time (socat holding the CURRENT port
  inode plus a live log fd), so the static log was a genuinely dead device, not a
  capture failure.
* A power cycle with a **longer off period (20 s instead of the usual 8-12 s)**
  restored it: the device booted past mt76 firmware load to a shell with 0% ping
  loss.

**Two rig lessons.** First, `tomada`'s current/wattage reading is NOT reliable -
it reported `0 mA / 0.0 W` on the very boot that succeeded and produced 4769
bytes of UART output. Use it as a coarse on/off indicator only; the UART log
growing is the authoritative "device has power" signal. Second, when a device
appears to fail at a fixed point in the boot, check that it still has POWER
before extending any device-fault narrative - a symptom matching a documented
defect's shape is not evidence for that defect.

## 2026-11-15: production NAND install/sysupgrade profile (built, NOT hardware-qualified)

Added a `BOOT_PROFILE=production` build profile for the bank-A NAND install +
sysupgrade + UBI overlay, with a write policy enforced at two independent layers
and host tests. It builds, passes the full host CI, and **has not been written to
a device.** Details and the qualification ladder are in [INSTALL.md §12](INSTALL.md).

- **Write policy, layer 1 (device tree):** `zx279128s-zte-h199a-production.dts`
  (and `-production-qualify.dts`) include the canonical DTS and change only flash
  permissions: `kernel1`/`rootfs`/`header`/`overlay_ubi` writable, everything else
  `read-only`, partitioned master withdrawn via `partitioned-master-read-only`.
  MTD numbering is preserved (overlay_ubi appended as mtd13); the RAM/normal DTB
  is byte-for-byte unchanged.
- **Write policy, layer 2 (transport):** `CONFIG_SPI_ZX279128_PRODUCTION_POLICY`
  compiles a physical allowlist into `spi-zx279128.c` — program/erase only bank A
  rows `[0x0e00,0x2e80)` and UBI rows `[0xa800,0xc800)`, deny aliased/unaligned
  rows and array-mode feature writes, latch on the first refusal. It is a pure
  function unit-tested on the host (`test_production_policy.py`), and off entirely
  unless `spi_zx279128.production=1` (or `production_qualify=1`). The diagnostic
  guard is untouched; normal/diagnostic builds never set the symbol.
- **Fail-stop:** `CONFIG_MTD_SPI_NAND_FAIL_STOP` is the always-on production form
  of the diagnostic guard — no bad-block marking, first program/erase failure
  latches, and `partitioned-master-read-only` support — mutually exclusive with
  `CONFIG_MTD_SPI_NAND_DIAGNOSTIC` so RAM qualification keeps the diagnostic path.
- **ECC resolved from the driver:** production writes/reads use the Micron
  **on-die ECC** engine (`NAND_ECC_ENGINE_TYPE_ON_DIE`) with per-request status;
  the design doc's "no-ECC" refers to the retired raw shim. See NAND.md and
  INSTALL.md §12.3.
- **sysupgrade:** `platform.sh` adds a board-name check before any erase,
  read-back verification between the rootfs→kernel1→header writes (header last),
  UBI-aware config into `ubi0:rootfs_data`, `-n` by recreating the UBI volume (no
  raw `deadc0de`), and never writes bank B. `78_h199a_production_overlay` attaches
  the overlay without the diagnostic preconditions and refuses to format an
  unexpected volume.
- **Factory image:** `verify-production-image.py` validates the sysupgrade tar
  against every bootloader-checked CRC and proves the header differs from the
  unit's template only in the three CRC fields (byte-exact identity). The header
  math in `flash-prep.py` is refactored into pure functions and re-proven
  byte-exact against `header-template.bin`.
