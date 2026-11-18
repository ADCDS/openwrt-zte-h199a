> **Historical record — reviewed 2026-11-18.** This is an archived investigation,
> not a procedure for the current release. “Current”, “shipped” and “remaining”
> below refer to the image or experiment discussed at that point. Commands,
> register writes and erase addresses can be obsolete or destructive; old
> staging/test areas overlap the live UBI overlay. Use [current docs](../README.md),
> [installation](../INSTALL.md) and [validation](../../VALIDATION.md) instead.
> Local commit IDs belong to pre-release work and are absent from the squashed
> published history. Private binaries, captures and rig tools are not bundled.

# Why the port wedges — analysis and fix (2026-09-24)

> **Merged into `main` on 2026-11-17; read this first.** This document was
> written against the September (R204/R206) driver and is kept as written.
> What changed in the merge:
>
> - **Restart (row 5, §5):** not taken from this branch. `main` already has a
>   dedicated restart driver (`zte,zx279128s-reboot`, `POWER_RESET_ZX279128`,
>   the same `TOPCRM+0x44 = 1`) with `PANIC_TIMEOUT=1`, and a CPU0 TWD watchdog
>   driver, both hardware-qualified (`WATCHDOG.md`). The `topcrm` syscon and
>   `syscon-reboot` node below were dropped: TOPCRM is now owned by the CRM
>   clock/reset provider. The lockup/hung-task/WQ detectors and serial SysRq
>   (`0x1a`) were kept. `ARM_ERRATA_764369` was already enabled in `main`.
> - **`tx_drain_us`:** `main` had already made the post-doorbell spin opt-in
>   (`tx_drain_probe`, off by default, debug builds only), which removes the
>   per-frame IRQs-off spin this document suspects. `tx_drain_us` survives only
>   as the bound of that diagnostic probe.
> - **`zx_dp_reset_work()`** now replays the whole of the current probe's
>   post-init sequence — software port policy (bridge isolation, FDB clear,
>   VLANs), CPU protocols, `gap_add`, BPPE seed, IRQ mask — not just the
>   September subset, and refuses to run under live PP tables
>   (`CONFIG_ZX279128_PP_TABLES` diagnostic builds).
> - The R201/R202/R204 freeze suites were **not** re-pointed at a frozen copy
>   (`tests/frozen_driver.py` dropped); `main` already pins them to
>   `artifacts/r206/validated-driver.c`. Their one-call-site assertions now name
>   the reset as the second, intended caller.
>
> The bench results for the recovery are in the 2026-11-17 acceptance record,
> not here.

This is a read of the whole record — `ETHERNET.md`, `ETHERNET-JOURNAL.md`,
`TM-IRQ-ARCHITECTURE.md`, `WIFI*.md`, `BRINGUP.md`, the r199–r207 artifacts, the
vendor U-Boot disassembly and the sibling ZX279133 driver — done without bench
access. Every number below comes from those records or from the source. Anything
inferred is labelled **(inference)**. The code changes on this branch are
compile-checked against Linux 6.6.151/ARM and covered by host harnesses, **but
none of them has been run on the board**. §6 is the bench plan that decides them.

## 1. The answer in one screen

"The wedge" has named five different failures. Keeping them apart is most of the
answer.

| # | Symptom | Seen on | Mechanism | Status |
|---|---|---|---|---|
| 1 | RX stops for good at ~5,100 cumulative frames | pre-2026-09-07 driver | RX descriptors were never returned, so the CPU queue's RED admission space filled and RED dropped every later frame | **Fixed**, `145fe80` (`desc_release`) |
| 2 | RX stops for good after ~3,000 frames of an unpaced flood (`BM+0xdc = 0xc0000111`) | the old scanning driver only, **one** run | Not established. §2.2 lists three defects in that driver, any of which can do it | Absent from the current cold path; **never re-tested** |
| 3 | Whole box: wired 100% loss, the console echoes keys but runs nothing, only a power cycle recovers | 2026-09-06 only, old driver, no diagnostics | A CPU stuck on a bus access that never completes, or tasks asleep behind one (§3) | **Undiagnosable from the record** |
| 4 | Whole box hangs at the 5 GHz firmware load | `mt7615e`: 4 of 6 autoloaded boots, 2 of 4 deferred | Both cores stuck on PCIe. Candidates: A9 erratum 764369 not enabled; no PCIe completion timeout (§3.3) | Open |
| 5 | Any oops or panic leaves the box dead | every image | **There is no restart handler**: `reboot` prints "Reboot failed -- System halted" (`INSTALL.md`), and with `PANIC_ON_OOPS=y` every oops ends there | Fixed here, needs one bench check |

The current driver (R204/R206, `477ba61a…`) has not wedged in any recorded run.
It has also only ever been run lightly: at most 200 pps ICMP, 4 MiB TCP, ~14 Mbit/s
bridged iperf, with Wi-Fi blacklisted and `init=/bin/sh`. It still has five ways
to stop that nothing detects, plus a transmit spin that is probably costing most
of its TX throughput (§2.3). And whatever does hang the box today leaves no trace
and no way back but the power switch (§3.1).

So this branch does three things:

1. **Detect and recover from an RX stop in the driver** instead of latching it
   forever (§4.1).
2. **Make a hang leave evidence and a panic reboot** (§4.2).
3. **Leave a bench plan** that decides every open item with a measurement
   instead of an argument (§6).

## 2. The RX datapath wedge

### 2.1 ★ The one that was fixed, and the number that explains it

Every frame the TM hands to the CPU occupies RED admission space in its queue
until the driver returns the descriptor through TMD+0x64/+0x68. Until `145fe80`
the driver never did. The queue therefore filled once, and after that RED dropped
every frame. `desc_release` was shown "necessary and sufficient" in a 2x2 of cold
boots (`ETHERNET.md` §"THE WEDGE IS FIXED").

What sets the size of that one fill? U-Boot programs every RED type-0 entry,
the CPU queues included, with `{0x00800400, 0, 0, 0}`
(`zx279128s-vendor/uboot-F610GV9-TM-region.asm`, 0x47f3486c–0x47f34928). The old
driver's cold init wrote the same value. In the decode recorded in
`TM-IRQ-ARCHITECTURE.md` (§"Queue-State Initialization Recovered": guard space is
bits 10:0, shared space is bits 25:11), that is 1024 + 4096 = **5120 per queue**.
The pre-fix stop sat at `BM+0xb0 = 5121 = 5 × 1024 + 1` and ~5097 frames delivered
in five of five controls. **(inference)** That is the 5120 limit being reached.
It does not explain the 2,608-frame stop with the pool fill masked, which stays
unexplained.

### 2.2 The old driver had three more ways to wedge

These apply to every image built before `3ec342b` (2026-09-10). That includes the
bank-A image flashed before R206. The r207 captures show it running, with its
`heal:` and `census` lines and the `Aug 11` build stamp
(`artifacts/r207/enum-probe.rx.txt`, `poweron-delay.rx.bin`).

1. **Slot 0 was never read.** `TX_DESC_SLOT = 0` was skipped unless
   `rx_full_ring` was set, which it was not by default. The hardware writes slot 0
   on every lap, so each lap lost one frame and leaked one unreturned descriptor.
   The published throughput table shows that rate:

   | Paced rate | Lost | Offered / 1024 |
   |---|---:|---:|
   | 8 kpps | 154 | 156 |
   | 16 kpps | 312 | 313 |
   | 4 kpps | 72 | 78 |

   **(inference)** The leak is a slow copy of §2.1. At one RED unit per lap it
   wedges after about 5,120 laps (~5 M frames), well past the 1.34 M frames of the
   longest recorded boot.
2. **CPU queues admitted five times their ring.** Under the 5120 limit a burst
   can build more than 1024 unreturned descriptors. The producer then laps the
   consumer, and the descriptors it overwrites are never returned and their buffers
   never freed. **(inference)** This is the likeliest mechanism for wedge 2. Bit
   31 of `BM+0xdc`, set at that stop, had otherwise appeared only when the pool
   was under-filled, so a pool-level cause fits. No bit of `BM+0xdc` has a known
   meaning, though. For comparison, the sibling ZX279133 driver (cnjn
   `zx279133-tm.c`, whose comments cite the vendor's `np.ko`) caps its CPU-facing
   queues at 272 (`red_np1_config(256, 0x100)`). Its pool size equals its ring
   size, so a ring there cannot be lapped.
3. **It wrote a software "credit" into TMQ+0x170 on every poll.** The vendor
   code never writes that register. Round 150 had credited the write with curing
   an earlier stop. The IRQ-era measurements identify the register as the
   hardware's own 8-bit production counter and dropped the writes as
   contaminating (`TM-IRQ-ARCHITECTURE.md` §"Live Count Measurements").

The old `heal` also returned all 2,047 buffers to the pool after 10 s of idle on a
link that had seen traffic, whether or not the hardware still owned them. In r207
it fired twice on a healthy, receiving link. `BM+0xdc` then read
`0x40000431/429/421`, which is the same signature the "reprime a healthy
datapath" test produced (`ETHERNET.md` §"READING B WINS"). **(inference)** That
pool now holds duplicate indices.

**If any unit still runs a pre-R204 image, reflash it.** Each of these defects
is already enough to wedge it.

### 2.3 What the current driver still does

The IRQ/NAPI rewrite removed all four defects above. It reads every slot in
order, returns every descriptor, never writes TMQ+0x170 and has no heal. Its cold
init writes type-0 entries 0–15 as `0x400` (guard only), which caps each CPU queue
at 1024, its ring size. The value appears to follow a readback of queue 0's
configuration (`TM-IRQ-ARCHITECTURE.md` §"Queue-State Initialization Recovered").
No commit records the choice, and it has not been measured under a burst.

What remains, from a line-by-line audit of `zx279128-eth.c`:

| Defect | Effect | Reachable how |
|---|---|---|
| `rx_fault` was terminal | A pending count above 1024 masks the TM IRQ, stops NAPI and makes every later `ifup` return `-EIO` until reboot. Nothing in `/proc` showed it | A **warm attach** (TFTP boot after U-Boot used the network, the default `force_dp_init=0`) keeps U-Boot's 5120 limit, so any backlog past 1024 trips it. So does a single bad read |
| No stall detection | A return that never retires (TMD GO stuck) or a BM free the hardware keeps refusing stops RX. `zx_rx_rearm()` then reschedules NAPI forever: one CPU pinned in softirq, no log line | Hardware fault; never observed |
| Refresh right after a carried return retires | The pending count is re-read within a microsecond of GO clearing. If the count lags GO, one descriptor is counted twice. That produces a stale slot, a double free, and later an underflow to `0xffff`, which sets `rx_fault` | Race; **(inference)** |
| Warm attach keeps U-Boot's TM IRQ mask | A source left unmasked makes `zx_eth_irq()` answer `IRQ_NONE` until the kernel disables the whole TM line | Warm boots only |
| TX spins up to 500 µs per frame with IRQs off, under the global `tx_lock` | See below | Every transmitted frame |
| TX buffers have no software owner | Any frame the TM discards without recycling leaks a pool buffer, and RX eventually starves | Untested: TX to an unplugged or congested port |

**★ The TX spin is the most consequential of these, and it is measurable today.**
TMQ+0x6c is documented as advancing "per doorbell" (`TMQ_TXIDX`). So the value
sampled right after the doorbell likely already includes the advance, and nothing
can move it again while `tx_lock` is held. **(inference)** Every frame then burns
the full 500 µs. That caps TX near 2,000 frames/s for the whole box, with
interrupts off for most of that time, and the other CPU spins on the lock too.
All 14 recorded device-side 4 MiB uploads in R204/R206 took 2.22–2.29 s, about
14.7–15.1 Mbit/s or ~1,290 data frames/s. That spread is suspiciously tight, and it
fits the cap. Nothing else in the TX path costs anywhere near 0.5 ms per frame.

The spin is also the only thing pacing TX against a ring with no back-pressure.
Removing it blind could let TX lap its ring. So this branch only makes the bound
a runtime knob. `TXGATE` in `/proc/zx_eth_regs` decides it (§6, step 3).

**Not a wedge:** the flashed-image "ICMP 25% loss, avg 662 ms"
(`artifacts/r206/flashed-iperf-1`). In the per-packet data:
- pings 1–5 are *host-side* "Destination Host Unreachable": ARP did not resolve
  while the three port carriers were still coming up;
- pings 6–10 arrived together, 200 ms apart, as queued ARP releases;
- every later ping took 1.70–1.82 ms.

## 3. Whole-device hangs

### 3.1 ★ Why no hang has ever been diagnosed or recovered from

The kernel that was built (`artifacts/r204/forced.config`) has:

- **no soft-lockup, hard-lockup, hung-task or workqueue watchdog.** The only
  reporter is the RCU stall check, at 60 s;
- **`MAGIC_SYSRQ_SERIAL` off**, so a UART BREAK does nothing, and a wedged shell
  cannot run `echo w > /proc/sysrq-trigger`;
- **no restart handler**, so `reboot`, every panic and every oops end in
  "Reboot failed -- System halted";
- **no watchdog driver.** The stock DTS declares the Cortex-A9 private
  watchdog (`arm,cortex-a9-twd-wdt`), and the stock kernel runs an 8 s watchdog
  heartbeat (`SESSION-JOURNAL.md`). Mainline 6.6 has no driver for that block.

A hang therefore prints nothing and lasts until someone pulls the plug. That is
why the record holds no stack trace for any of wedges 3 and 4.

### 3.2 What the console signature does prove

- **Echo without execution means the shell is waiting on a stuck foreground
  job.** BusyBox `ash` with line editing turns off tty echo while it reads a
  command. So if the kernel is echoing, `ash` is in `wait4()` on a job that never
  finishes. That job is either asleep in D or runnable on a CPU that never
  returns.
- **CPU0 is alive.** With no irqbalance, every device interrupt sits on CPU0 by
  GIC default, UART included (confirm with `/proc/interrupts`). The echo itself
  runs from an unbound kworker, and printks keep appearing.
- **On this SoC a bad access usually stalls rather than faults.** The record
  shows five accesses that hung the board:
  - poking `BM_REQUEST` (`ETHERNET.md`);
  - a loop of pokes over the buffer pool (`TM-IRQ-ARCHITECTURE.md`);
  - writing U-Boot's value to `CRM+0x08`;
  - blind writes to spifc offsets (`zx_spifc_nand.c`);
  - PCIe DBI reads before its clocks were on (`WIFI.md`).
  A CPU stuck like that takes no more interrupts. Anything that waits on it waits
  forever: locks it holds, RCU grace periods, NAPI queued on it. The exception is
  a fresh-mapping read of MAC2, which did raise an imprecise external abort. With
  `PANIC_ON_OOPS` and no restart handler, that halts the board just the same
  (wedge 5).

**(inference)** The most likely reading of wedge 3: CPU1 is stuck in a device
access that never completes, and the shell's job either runs there or sleeps
behind something CPU1 holds (RTNL, an RCU grace period). The candidate accesses
are:
- an `mt76` BAR read after the radio or its link died, in the Wi-Fi cases;
- a datapath register read otherwise.

A cheap check on the old captures: that state prints
`rcu: INFO: rcu_sched detected stalls` about 60 s in, and the mt76 variant prints
`Message … timeout` every 20 s.

`/proc/zx_eth_regs` is the driver's own riskiest reader. It fresh-ioremaps and
reads about 25 register windows with no lock, including:
- `IDM`, which the stock DTS marks disabled;
- `MAC1–3` (a fresh-mapping read of MAC2 is recorded in the driver as having
  halted the board);
- the read-clear TMQ counters.

It is world-readable and always built (`ZX_HAVE_DEBUG_IFACES 1`).

### 3.3 The Wi-Fi firmware-load hang (wedge 4)

**(inference)** Both cores stall on PCIe reads during the firmware download. That
fits total silence with no RCU report. Two configuration gaps make it likely:

- **`ARM_ERRATA_764369` is off.** The CPU is a dual Cortex-A9 r4p1 (`414fc091`).
  The erratum affects every revision of the multi-core part: cache maintenance by
  address can fail to reach the point of coherency while the other core is busy.
  The firmware is streamed through `dma_map_single()`, which relies on exactly
  that maintenance. A corrupted chunk crashes the MT7663 loader, and the next BAR
  read never completes. The pattern "hangs 20–30 s into boot, never at an idle
  shell" fits a race that needs the other core busy.
- **The DesignWare root port has no completion timeout or error response
  configured.** A dead endpoint therefore stalls the CPU instead of returning all
  ones.

### 3.4 Current bench images cannot reproduce 3 or 4

The committed `CONFIG_CMDLINE` is forced and ends in
`module_blacklist=mt7615e,mt7603e ro init=/bin/sh` (`config-6.6:355`). Every image
built from HEAD boots to a bare shell with both radios blacklisted. That was right
for the R199–R206 Ethernet work, and it is also why none of those rounds could
hang the way 2026-09-06 did. `ignore_loglevel` in the same line sends every printk
through the 115200-baud console with interrupts off, about 20 ms per `zx-spifc
HEALTH` line.

## 4. What this branch changes

### 4.1 Driver (`zx279128-eth.c`)

| Change | Addresses | Default |
|---|---|---|
| `rx_fault` asks for a reset instead of latching. A pending count above 1024 is re-read once before it counts | §2.3 rows 1 and 3 | on |
| 1 Hz stall watchdog. If descriptors are pending and none has been returned since the last period, kick NAPI; after `rx_stall_ms` (3 s), request a reset | §2.3 row 2 | on |
| **Datapath reset** (`zx_dp_reset_work`). Closes every open port, runs the cold `zx_eth_datapath_init()` including the TM queue-state reset, resets cursors, debt and TX origin to what a cold probe leaves, then reopens the ports. At most one every 10 s; stops after 3 in a row with no RX in between, and gets that budget back once RX moves | any RX stop the above detect, including wedge 2 if it recurs | `rx_recover=1` |
| `/proc/zx_eth_reinit` queues the same reset (it returned `-EOPNOTSUPP`) | bench testing | root-only |
| After 8 empty polls blocked on a refused return, back off on the retry work (1→10 jiffies) instead of rescheduling NAPI | §2.3 row 2, CPU pinned in softirq | on |
| A ring whose carried-over return retires in this visit refreshes its count on the next visit | §2.3 row 3 | on |
| All TM IRQ sources masked before `request_irq()`, on warm attach too | §2.3 row 4 | on |
| `timer_setup()` moved before the devm action that deletes the timer | `artifacts/r206/PRODUCTION-REVIEW.md` §1 | — |
| `local_bh_disable()` around process-context `napi_schedule()` | latency | — |
| `tx_drain_us` knob for the TX spin | §2.3, TX spin | **500, unchanged** |
| `RXSTOP` now shows `fault`, `desc_rls` and `desc_busy`; a new `RXRECOVER` line; `/proc` reads skip MMIO while a reset holds the fabric; NULL check in the MACCTRL loop | observability | — |

The reset reuses code that already runs on every boot: the ordinary
`ndo_stop`/`ndo_open` pair that R206's reopen tests exercise, and the probe-time
init that R206's cold runs exercise. It adds no register write the driver did
not already make.

### 4.2 Kernel configuration and device tree

| Change | Why |
|---|---|
| DTS `topcrm` syscon plus `syscon-reboot` at `+0x44 = 1` | The stock kernel's `zx279128_restart()` is exactly `writel(1, 0x94000044)`. With it, `reboot` works and `PANIC_TIMEOUT=1` turns a panic into a reboot |
| `SOFTLOCKUP_DETECTOR`, `HARDLOCKUP_DETECTOR` (buddy), `DETECT_HUNG_TASK`, `WQ_WATCHDOG` | Warn only; the `*_PANIC` bootparams stay off. The next hang names its CPU and its blocked tasks on the console |
| `MAGIC_SYSRQ_SERIAL` with `MAGIC_SYSRQ_DEFAULT_ENABLE=0x1a` | BREAK + `w`/`l`/`t` works with userspace dead. The mask allows log level, sync and dumps only, so line noise cannot reboot or kill anything |
| `ARM_ERRATA_764369` | §3.3; dual A9 r4p1 |

Every Kconfig symbol these options make visible is already pinned in OpenWrt's
generic config, so no build-time prompt appears (checked with `listnewconfig`
against the real R204 `.config`). The kernel partition has 466 KiB of headroom.

### 4.3 Tests

- `tests/test_eth_recover.py` compiles the real watchdog, reset request and reset
  worker against a stub kernel. It covers stall detection, kicks, rate limit,
  give-up and re-arm, the close → init → reset-state → reopen order, and every
  failure exit.
- `test_eth_rx.py` gained the re-read, carried-deferral and backoff cases.
- `test_eth_tx.py` compiles again and covers `tx_drain_us`.
- A deliberately broken copy of the driver fails the new cases: an off-by-one in
  the give-up cap, the deferral removed, the backoff removed.
- The R201/R202/R204 round-freeze suites byte-pin the source those rounds
  validated. They now read that frozen source (`477ba61a…`) from
  `artifacts/r205/sources-and-notes.tgz`, hash-checked (`tests/frozen_driver.py`),
  so they keep proving what they proved without forbidding every later change.

## 5. What was checked and found clean

- **Locking.** `tx_lock → bm_lock` is the only nesting, and `irq_lock` never
  nests. Nothing sleeps in atomic context, and every software loop is bounded.
- **`napi_disable()` cannot hold RTNL forever on its own.** `running` is cleared
  and the IRQ masked under `irq_lock` first. The core refuses new schedules once
  disable is pending, and every poll is bounded. It can hang only behind a CPU
  that is itself stalled on the bus (§3.2).
- **TX pool leak (in the tested paths).** R206 sent 12,889 frames in one boot with
  zero drops, and the packet traces show TX buffer indices being reused. The TM
  recycles TX buffers on egress.
- **Process-context `napi_schedule()`** wakes ksoftirqd in 6.6.151
  (`raise_softirq_irqoff`), so it was never a stall, only latency.

## 6. Bench plan — pre-registered

Each step states its prediction before it is run. Alternate arms and cold-boot
each trial (`docs/README.md` conventions). Flash nothing to test steps 1–5: a TFTP
RAM boot of a kernel built from this branch is enough.

1. **Restart.** Run `reboot`. *Predict:* the SoC resets into U-Boot within 1 s.
   Then run `echo c > /proc/sysrq-trigger`. *Predict:* panic, then reboot after
   1 s. If either still ends in "Reboot failed", `0x94000044` is not the reset on
   this unit; revert the DTS node and nothing else changes.
2. **Serial SysRq.** Send BREAK then `h` (pyserial `send_break(0.25)`, picocom
   `C-a C-\`). *Predict:* the SysRq help text. This proves the ZTE UART reports
   BREAK at all.
3. **TXGATE.** Boot cold, run one 4 MiB device-side upload, then
   `grep TXGATE /proc/zx_eth_regs`.
   - `slow ≈ n` confirms the dead-time reading. Set
     `echo 20 > /sys/module/zx279128_eth/parameters/tx_drain_us` and repeat.
     *Predict:* throughput well above 14.7 Mbit/s. Then run 10 minutes of
     bidirectional traffic and confirm `RXPROD alloc_*` stays at 0 and RX still
     works; that is the ring-lapping check.
   - `prompt ≈ n` refutes it. Leave 500.
4. **Recovery on demand.** Traffic running, `echo 1 > /proc/zx_eth_reinit`.
   *Predict:* `datapath reset #1: requested…`, ports flap for about 3 s, traffic
   resumes, `RXRECOVER resets=1`, `TXORIGIN_R204 … selected=0`. Run it 5 times.
   Failing this blocks default-on `rx_recover`.
5. **Burst, cold path.** Run the 2026-09-07 unpaced generator for 30 s at a cold
   boot.
   - *Predict:* RED tail-drops, `badpend=0`, no reset, RX alive afterwards.
   - Record `RXQPEND`, `RXRECOVER` and the RED counters at `0x92344208/214/218`.
   - A reset here means the 0x400 cap does not hold.
6. **Burst, warm path.** Same generator, same duration, on a TFTP boot whose
   U-Boot used the network.
   - *Predict:* `invalid pending count` once, then `datapath reset #1`, then RX
     alive.
   - If it wedges without a reset, the 5120-limit reading is wrong.
7. **Erratum A/B for wedge 4.** Two builds, one with `ARM_ERRATA_764369` and one
   without, with the radios enabled.
   - Six cold boots each, alternating builds.
   - Score each boot at least 240 s after the firmware load (`WIFI.md` Trap 1).
   - Also run the erratum-off build with `maxcpus=1`.
8. **Whenever anything hangs:** leave it logging for 2 minutes (the detectors
   report by themselves), then send BREAK + `w`, BREAK + `l` and BREAK + `t`, and
   save the capture. That turns wedge 3 from folklore into a stack trace.

## 7. Not done, and why

- **TX back-pressure.** It needs a trustworthy consume index, and step 3 is the
  way to find one. The R66–R68 history shows what gating a queue on an unverified
  register does.
- **PCIe completion timeout and error response.** The DWC register semantics on
  this core are unverified, and a wrong write to that block hangs the board.
- **A9 private-watchdog driver.** Needs the reset routing through `CRM+0x04`,
  which the stock `zx_wdt_probe` sets `|= 0x18`, verified first.
- **Production image hygiene.** The debug `/proc` files should go back behind
  `CONFIG_ZX279128_ETH_DEBUG`. The forced command line should lose
  `init=/bin/sh`, the blacklist and `ignore_loglevel` once the bench no longer
  needs them. Both are decisions for whoever owns the bench, not a side effect of
  this change.
- **spifc** reads its FIFO with a sleeping poll, which is the likely source of its
  ~90 recoveries per boot (`NAND.md`). That costs flash latency, not a wedge, and
  is out of scope here.
