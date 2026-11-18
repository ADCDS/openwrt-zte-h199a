> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# Watchdog — ZX279128S / ZXHN H199A

Driver: `files/target/linux/armsr/files-6.6/drivers/watchdog/zx279128_wdt.c`
(`CONFIG_ZX279128_WATCHDOG=y`, hooked in by `patches-6.6/998-zx279128-watchdog.patch`).
The register evidence is the instruction-level audit of the stock `wdt_zx.c` in
`logs/analysis-20261115/watchdog-twd-verification.md` (parent workspace).

**Status, 2026-11-15:** **hardware-qualified** on the owner's unit (RAM-root
`normal-wd` build; results in the next section). The plan that produced them
is kept below as "Hardware qualification procedure".

## Hardware qualification — RESULTS (2026-11-15, `normal-wd`)

Evidence (parent workspace): `logs/normal-wd-qual-20261115/` and the runs
`logs/ram-normal-wd-20261115-142223/` (+ `-poweroff-`, `-reboot-`).

| step | result |
|---|---|
| 0 / 7 U-Boot registers | TOPCRM `0x94000004 = 0x1fb` (bits `0x18` set, as SPL leaves them). After an expiry the whole CPU0 TWD bank (LOAD/COUNTER/CONTROL/INTSTAT/RESETSTAT) reads **0** at U-Boot |
| 1 probe | `CPU0 bank, 3906250 Hz, timeout 30 s, hardware maximum 1099 s`; `/dev/watchdog0`; cold `bootstatus` 0; **no "stopped inherited watchdog"** ⇒ the boot chain does not arm it |
| 2 procd | `ubus call system watchdog`: running, timeout 30, frequency 5 |
| 3 reload | `timeleft` sawtooths `25 29 28 27 26 25 29 …` ⇒ **a LOAD write reloads COUNTER** on this A9 |
| 4 rate | exactly 1 count per host second ⇒ the 3,906,250 Hz derivation is right |
| 5 magic close | stop with magic → `inactive`, **no reset in 65 s (> 2× 30 s)**; re-arm OK |
| 6 expiry | timeout 15 s, stop without magic → fresh BootROM **14.74 s** later ⇒ **CPU0 WDRESETREQ resets the whole board** |
| 7 CARDRESET | RESETSTAT does not survive (bank reads 0 after the reset, a power-on-class reset) ⇒ **CARDRESET cannot be reported on this board**; the driver's reporting path is harmlessly inert |
| 8 orderly | `reboot` → BootROM 3 ms later via the restart driver; `poweroff` → `System halted`, **0 resets in 75 s** |
| 9 timer | no watchdog IRQ handler; timekeeping normal |

Open questions 1, 2, 4 and 6 below are therefore answered (whole-board reset;
not armed by the boot chain; LOAD reloads; flag does not survive). Still open:
PERIPHCLK under cpufreq (cpufreq is off, N/A) and pretimeout (deferred).

⚠ With a watchdog image, a hang resets after 30 s into whatever bank A holds.
For hang forensics stop it first:
`ubus call system watchdog '{"magicclose":true}'` then `'{"stop":true}'`.

## Hardware, as verified from the stock binary

The watchdog is the Cortex-A9 TWD watchdog half at `0x800620`
(PERIPHBASE `0x800000`, TWD base `0x800600` + `0x20`). Its registers are banked
per CPU: an access reaches the bank of whichever core runs it.

| Offset | Register | Use |
|---|---|---|
| +0x00 | LOAD | `rate * timeout - 1`. The stock feed rewrites it. |
| +0x04 | COUNTER | Read for time left. |
| +0x08 | CONTROL | `0x7f09` = prescaler /128, watchdog mode, enable. `0` = disabled. |
| +0x0c | INTSTAT | Write 1 to clear. |
| +0x10 | RESETSTAT | Bit 0 set means the last reset came from the watchdog. Write 1 to clear. |
| +0x14 | DISABLE | Write `0x12345678`, then `0x87654321`, to leave watchdog mode. Write-only. |

The rate is PERIPHCLK / 128. At 500 MHz that is 3,906,250 Hz, and a 32-bit LOAD
covers up to 1099 s. The stock driver computes the rate as `clk_get_rate() >> 7`.

★ U-Boot's `watchdog` command uses `0x09`, a /1 prescaler and a hardcoded
`300000`. Never copy those values into Linux.

The timer half (`0x800600`–`0x80061f`) is not described in this DTS, and Linux
does not use it: `CONFIG_HAVE_ARM_TWD` is unset. Clock events and the
clocksource come from the A9 global timer at `0x800200`. The driver maps only
`0x800620`/`0x20`. A host test fails on any access outside that window.

## What the driver does

- **Binding.** The driver uses the mainline compatible `arm,cortex-a9-twd-wdt`.
  The 6.6 binding `watchdog/arm,twd-wdt.yaml` exists, and no in-tree driver
  matches it. The stock DT uses the same compatible. The node reuses
  `&periphclk`, because the stock DT gives the global timer and the watchdog the
  same specifier `<0x03 0x1d>`. Its interrupt is `<GIC_PPI 14 (CPU0 mask |
  rising edge)>`, which equals the stock `<1 0x0e 0x101>`. The driver never
  requests the interrupt: watchdog mode resets directly. The SoC-specific CPU0
  policy is enforced by Kconfig (`depends on ARCH_ZX279128 || COMPILE_TEST`),
  not by a vendor compatible.
- **CPU0 ownership.** Every register sequence runs inside one
  `smp_call_function_single(0, …)` callback, with interrupts off on CPU0. If the
  callback ever runs on another CPU, it raises `WARN_ON_ONCE` and touches
  nothing. Running on one CPU with interrupts off also serializes the sequences.
  This matters because the core's reboot notifier calls `stop` without the core
  lock.
- **No CPU hotplug callback.** None is needed, for four reasons:
  - `zx279128_smp_ops` has no `cpu_die`, so `platform_can_hotplug_cpu()` is 0
    for every CPU.
  - ARM never offers CPU0 for hotplug by default.
  - CPU1's bank is never armed. U-Boot runs on CPU0, and the stock per-core
    feeder is not part of this image.
  - If CPU0 were ever offline, every operation would fail with `-ENXIO` without
    touching any bank.
- **Probe order.** Probe runs these steps in order:
  1. Map the registers.
  2. Get the clock. A deferral happens here, before any register access, so a
     deferred probe cannot clear RESETSTAT.
  3. On CPU0, read CONTROL, COUNTER and RESETSTAT, then run the full disable
     sequence and verify CONTROL.
  4. Check the rate, then register the device.

  RESETSTAT bit 0 becomes `WDIOF_CARDRESET`. An inherited armed bank and the
  reset flag are both logged.
- **Operations.**
  - Start writes LOAD, then `0x7f09`, and reads CONTROL back. If the prescaler did
    not latch, the watchdog would expire 128 times early, so start backs out and
    returns `-EIO`.
  - Ping writes LOAD only, as the stock feed does.
  - Stop writes the unlock pair, then CONTROL 0, INTSTAT 1 and RESETSTAT 1, and
    reads CONTROL back. If the stop fails, the driver keeps `WDOG_HW_RUNNING` set
    so the core still treats the bank as running.
  - `set_timeout` reprograms only a running bank.
  - Time left is `COUNTER / rate`, rounded down. It is meaningful only while
    `state` is `active`; a stopped bank keeps a stale COUNTER.
- **Barriers.** `writel()` issues `dsb st` plus the outer-cache sync before each
  store. The compiled object was disassembled and matches the stock
  instruction stream.
- **Limits.**
  - Minimum timeout is 1 s.
  - `max_hw_heartbeat_ms` is `floor(2^32 / rate) * 1000`, which is 1,099,000 ms
    at 500 MHz. It is clamped so the millisecond value fits in a `uint`.
  - The watchdog core covers longer software timeouts, and only up to the
    userspace deadline. At procd's 30 s, no kernel worker runs.
  - The default timeout is 30 s. The module parameters are
    `zx279128_wdt.timeout=` and `zx279128_wdt.nowayout=`. `nowayout` defaults to
    `CONFIG_WATCHDOG_NOWAYOUT`, which is unset. `CONFIG_CMDLINE_FORCE` ignores
    bootloader arguments, so a parameter needs a rebuilt `CONFIG_CMDLINE`.
- **Reboot and shutdown.** `watchdog_stop_on_reboot()` stops the bank on
  restart, halt and power-off, even with `nowayout`; the core always does this.
  `watchdog.stop_on_reboot=0` keeps it armed through a reboot. The driver also
  calls `watchdog_stop_on_unregister()`. It has no `.restart` operation:
  `zx279128-reboot` (TOPCRM `0x94000044`) owns restart. It has no suspend
  hooks, because `CONFIG_PM` is off on this target.
- **No kernel feeder.** After probe the bank is stopped and `WDOG_HW_RUNNING` is
  clear, so nothing feeds the watchdog until userspace opens it.
- **procd.**
  - procd opens `/dev/watchdog` in preinit, sets a 30 s timeout and writes every
    5 s.
  - It logs `Watchdog has previously reset the system` only if the driver
    advertises `WDIOF_CARDRESET`, which this driver does.
  - `CONFIG_WATCHDOG_SYSFS=y` exposes `/sys/class/watchdog/watchdog0/{bootstatus,
    timeleft,timeout,state,identity}` for qualification.

## Verification done (host only)

The evidence is in the parent workspace, in
`logs/watchdog-host-verification-20261115T161355Z.log` (compile, checkpatch,
tree-untouched and mutation results) and `logs/ci-watchdog-20261115T161241Z.log`
(`ci/check.sh`: 362 tests, OK).

- **Host tests.** `tests/test_watchdog.py` has seven tests. They compile the real
  driver code against a banked register model, in which watchdog mode stays set
  until the unlock pair, the two flags are write-1-to-clear and LOAD reloads
  COUNTER. With the pinned tree present, they also compile the real 6.6 core
  functions:
  - `watchdog_start`, `watchdog_stop` and `watchdog_ping`
  - `watchdog_set_timeout` and `watchdog_init_timeout`
  - `watchdog_reboot_notifier`

  The tests also check the patch and the compiled DT node. A one-off mutation run
  outside CI injected 30 driver bugs, and every one was caught. Examples include
  the wrong unlock order, U-Boot's control word, a missing `-1`, unpinned access,
  reading RESETSTAT after the clear, probing the clock after the takeover, and
  touching the timer half.
- **Cross-compile.** The driver was built as an external module against the
  configured normal-X tree, with `-Werror` and `W=1`, and the tree was left
  unmodified. The only `W=1` note is modpost's "missing MODULE_DESCRIPTION". That
  note comes from `CONFIG_MODULE_STRIPPED` (OpenWrt `hack-6.6/204`) and appears
  identically for `zx279128-reboot`. `checkpatch --strict` is clean.
- **Device tree.** The DTS compiles. The only dtc warning is the existing
  `timer@8000200` unit-address mismatch.

## ★ Bench impact once an image contains this driver

procd arms the watchdog during preinit. After that, a kernel panic (the RAM
profiles use `panic=0`), a hard hang or a stalled procd no longer leaves the
board halted for inspection. If WDRESETREQ is routed, the board resets about
30 s later and autoboots the installed NAND image, unless the controller stops
autoboot. Controllers and experiments that rely on "panic, then hang" must
expect this.

For experiments that need the old behaviour, use one of these:
- Leave `CONFIG_ZX279128_WATCHDOG` out of the build.
- Set the node to `status = "disabled"` in a private DT variant.
- Run `ubus call system watchdog '{"magicclose": true, "stop": true}'` once
  userspace is up. This leaves the preinit window armed.

## Hardware qualification procedure (as executed)

Use a read-only RAM boot only, with every MTD read-only and the UART captured.
An expiry resets the board, which then autoboots the installed NAND image, so the
controller must catch the fresh SPL/U-Boot output and stop autoboot, as the
`--software-reboot` test does. No current controller mode covers an expiry, so
add one before step 6.

0. **U-Boot, before Linux.**
   - `md.l 0x94000004 1` should show bits `0x18` set. SPL writes `0x1fb`, and the
     stock `zx_wdt_probe` ORs `0x18` into this shared word; this driver does not
     write it.
   - `md.l 0x800620 5` shows CPU0's LOAD, COUNTER, CONTROL, INTSTAT and RESETSTAT.
     This answers whether the boot chain arms the watchdog. Do not read `+0x14`.
1. **Boot.** dmesg shows
   `zx279128-wdt 800620.watchdog: CPU0 bank, 3906250 Hz, timeout 30 s, hardware maximum 1099 s`
   and no `did not arm` or `did not stop`. `/dev/watchdog0` exists. On a cold
   boot, `bootstatus` is 0.
2. **procd ownership.** `ubus call system watchdog` reports `running`, timeout 30,
   frequency 5. `state` reads `active`.
3. **Counter reload.** Sample `timeleft` every second for at least 60 s. It must
   sawtooth between about 25 and 30. A steady decline means a LOAD write does not
   reload COUNTER, and ping must also write COUNTER. Then soak for at least
   10 minutes with no reset, while CPU1 is busy (`taskset -c 1`) and NAND reads
   run.
4. **Rate.** At `timeout` 60, `timeleft` must fall one second per host second
   between pings, for example 60 → 55 over procd's 5 s interval.
   `CONFIG_CPU_FREQ` is off, so PERIPHCLK should not move.
5. **Magic close.** Run `ubus call system watchdog '{"magicclose": true, "stop": true}'`.
   procd applies `magicclose` before `stop`. `state` becomes inactive, and there
   must be no reset for at least 2× the timeout. Then
   `'{"magicclose": false, "stop": false}'` re-arms it.
6. **Controlled expiry.** Set `'{"timeout": 10}'`, then `'{"stop": true}'`. With
   magic close off, procd closes the device without sending `V`, and the kernel
   prints `watchdog0: watchdog did not stop!`. Pass: within about 10 s, a fresh
   BootROM/SPL/U-Boot appears on the UART, which shows a whole-board reset.
   - No reset after 3× the timeout means WDRESETREQ is not routed. Recheck step 0.
   - A silent hang means only a core reset. Recover by outlet, with owner
     approval.
7. **CARDRESET.** After step 6, at the U-Boot prompt, run `md.l 0x800630 1`. Then
   boot the same image and expect all three:
   - the `reset flag set` warning in dmesg
   - `bootstatus` = 32
   - procd's `previously reset` log line

   A later orderly `reboot` must show 0. If the flag is already 0 after a real
   expiry, then the SoC reset or the boot chain clears it, and CARDRESET is
   unsupported on this board. Record that rather than guessing a fix.
8. **Orderly paths.**
   - `reboot` must reset through `zx279128-reboot`, with `bootstatus` 0 afterwards.
     The generic `syscon-reboot` was tried and hangs the board: `reboot -f`
     prints `Restarting system` and stops, with no U-Boot banner. See
     docs/upstream/bindings/README.md.
   - After `poweroff` or `halt`, no watchdog reset may occur for at least 2× the
     timeout.
9. **Timer unaffected.**
   - The clocksource is `arm_global_timer`, and its PPI counts rise on both CPUs.
   - No PPI 14 (hwirq 30) handler appears in `/proc/interrupts`.
   - Uptime keeps pace with the host clock.
10. **Optional.** If devmem exists, `taskset -c 1 devmem 0x800628` reads CPU1's
    CONTROL, which should be 0.

### Open hardware questions

1. **WDRESETREQ routing.** Does CPU0 expiry reset the whole board? The routing is
   in `mg-crm@0x804000`/TOPCRM. Step 6 answers this. The `0x18` bits in
   `0x94000004` are the first suspect, but they are unverified.
2. **Boot-chain arming.** Does the production boot arm the watchdog before Linux?
   Step 0 and the probe's `stopped inherited watchdog` warning answer this.
3. **PERIPHCLK under cpufreq.** If cpufreq is ever enabled, the rate scales with
   the CPU clock. The driver reads it once, at probe.
4. **Counter reload.** Does a LOAD write reload COUNTER on this ZTE-custom A9
   (MIDR `0x414fc091`)? Step 3 answers this.
5. **Pretimeout.** Could PPI 14 deliver an interrupt in timer mode before the
   reset? Deferred; not implemented.
6. **Reset flag.** Does RESETSTAT survive the expiry reset, and does SPL or U-Boot
   clear it? Step 7 answers this.
