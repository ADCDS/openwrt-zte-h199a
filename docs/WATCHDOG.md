# Watchdog — ZX279128S / ZXHN H199A

Current status, **2026-11-18**: the CPU0 Cortex-A9 TWD watchdog is enabled and
owned by procd. Hardware qualification on 2026-11-15 demonstrated counter
reload, rate, magic close, whole-board expiry reset, orderly reboot and halted
shutdown. The release-image checks also confirmed procd ownership, stop and
re-arm; see [VALIDATION.md](../VALIDATION.md). All hardware results are from
one unit.

Source:
[`zx279128_wdt.c`](../files/target/linux/armsr/files-6.6/drivers/watchdog/zx279128_wdt.c),
enabled by `CONFIG_ZX279128_WATCHDOG=y` through
[`998-zx279128-watchdog.patch`](../files/target/linux/armsr/patches-6.6/998-zx279128-watchdog.patch).
The DTS uses primary compatible `zte,zx279128s-wdt` with
`arm,cortex-a9-twd-wdt` as a fallback. The driver accepts both.

## Normal operation

Probe leaves the hardware stopped. Procd opens `/dev/watchdog` during preinit,
sets a **30-second timeout** and feeds it every **5 seconds**. The driver has no
periodic feeder. With this timeout below the hardware maximum, no watchdog-core
worker is needed to extend the interval.

Query ownership and state with:

```sh
ubus call system watchdog
cat /sys/class/watchdog/watchdog0/identity
cat /sys/class/watchdog/watchdog0/state
cat /sys/class/watchdog/watchdog0/timeout
cat /sys/class/watchdog/watchdog0/timeleft
cat /sys/class/watchdog/watchdog0/bootstatus
```

The normal state is active, timeout 30 and a `timeleft` sawtooth near 25–30
seconds. A stopped bank retains a stale counter, so `timeleft` is meaningful
only while `state` is active. `bootstatus=0` does not exclude watchdog expiry
on this board: its reset flag did not survive the observed reset.

Once procd has armed the bank, a panic with `panic=0`, hard hang or stalled
procd can reset the board after the remaining timeout. The bootloader then
boots according to its current bank selection; bank A is not guaranteed.
Experiments relying on a halted board must account for the watchdog.

For an experiment that requires it stopped, the default build allows magic
close:

```sh
ubus call system watchdog '{"magicclose":true,"stop":true}'
cat /sys/class/watchdog/watchdog0/state
```

Expect `inactive`. This does not remove the earlier armed preinit window.
Restore normal operation afterwards:

```sh
ubus call system watchdog '{"timeout":30,"frequency":5,"magicclose":false,"stop":false}'
ubus call system watchdog
```

Stopping procd's feed without magic close leaves the watchdog armed and causes
an expiry reset. A rebuilt `nowayout=1` configuration does not allow userspace
magic close to stop it. For an image that must never arm it, omit
`CONFIG_ZX279128_WATCHDOG` or disable the DT node in a private build.

## Hardware qualification results

The 2026-11-15 `normal-wd` RAM-root qualification observed:

| Check | Observed result |
|---|---|
| Cold takeover | No inherited armed watchdog; cold `bootstatus` 0 |
| Register clock | TOPCRM `0x94000004 = 0x1fb`, including bits `0x18`, as left by SPL |
| Probe | CPU0 bank, 3,906,250 Hz, timeout 30 s, hardware maximum 1099 s |
| Reload | `timeleft` repeated `25 29 28 27 26 25 29 …`; a LOAD write reloads COUNTER |
| Rate | One displayed second per host second |
| Magic close | Inactive for 65 seconds with no reset, then re-armed |
| Controlled expiry | With timeout 15 seconds, fresh BootROM output followed 14.74 seconds after stopping without magic close |
| Reset scope | Expiry reset the whole board |
| Reset flag | CPU0 LOAD/COUNTER/CONTROL/INTSTAT/RESETSTAT all read zero at U-Boot after expiry |
| Orderly reboot | Fresh BootROM output about 3 ms after the restart operation |
| Poweroff | `System halted`, no reset during a 75-second observation |
| Timer coexistence | Normal timekeeping, no watchdog IRQ handler |

The expiry result establishes WDRESETREQ routing on this unit. The cleared
bank means CARDRESET cannot identify that expiry on the tested boot chain.
The driver still correctly reports the flag if a future boot preserves it;
the existing reporting path must not be presented as a qualified board reset
reason. The observed lack of an inherited armed bank describes the tested
boot chain, not every possible bootloader configuration.

Repeat expiry tests only with UART capture and recovery/autoboot handling
prepared for the selected bank. See [BANKS.md](BANKS.md) for bank selection and
stock-firmware synchronization behavior.

## Register interface

The watchdog half of the A9 TWD is at **`0x00800620`**, mapped for `0x20`
bytes. The registers are banked by the CPU making the access.

| Offset | Register | Driver use |
|---|---|---|
| `+0x00` | LOAD | `rate * timeout - 1`, bounded by the hardware interval; write also feeds |
| `+0x04` | COUNTER | Remaining ticks |
| `+0x08` | CONTROL | `0x7f09` selects /128 prescaler, watchdog mode and enable |
| `+0x0c` | INTSTAT | Write bit 0 to clear |
| `+0x10` | RESETSTAT | Read bit 0 before clearing; write bit 0 to clear |
| `+0x14` | DISABLE | Write-only unlock: `0x12345678`, then `0x87654321` |

The rate is PERIPHCLK / 128. With PERIPHCLK 500 MHz it is 3,906,250 Hz, giving
a maximum whole hardware interval of 1099 seconds. The minimum timeout is one
second. `max_hw_heartbeat_ms` is bounded to a `uint`; the watchdog core can
bridge longer software timeouts while respecting the userspace deadline.
U-Boot's separate `watchdog` command uses a different control word and load;
its values are not the Linux configuration.

The driver does not touch the timer half at `0x00800600`–`0x0080061f`.
Linux uses the A9 global timer at `0x00800200`; `CONFIG_HAVE_ARM_TWD` is unset.
The watchdog DT declares PPI 14 to match the stock interrupt description, but
the driver requests no interrupt: watchdog mode resets directly. Pretimeout
support is not implemented.

## Driver guarantees and remaining limits

Every register transaction runs in one synchronous
`smp_call_function_single(0, …)` callback with CPU0 interrupts disabled. A
wrong-CPU callback warns and touches no bank. If CPU0 is unavailable, the call
fails without register access. The platform provides no CPU hotplug `cpu_die`
operation, so a separate hotplug callback is unnecessary; CPU1's bank is not
armed by this driver.

Probe acquires/enables the clock before reading any watchdog register, then
reads inherited CONTROL, COUNTER and RESETSTAT before running the disable
sequence. This preserves the flag through clock-probe deferral. The disable
sequence writes the unlock pair, CONTROL 0, INTSTAT 1 and RESETSTAT 1, then
verifies CONTROL. Start writes LOAD and CONTROL and verifies the prescaler
and enable fields; an incorrect readback backs out with `-EIO`. Failed stop
keeps `WDOG_HW_RUNNING` set. Ping rewrites LOAD, and `set_timeout` only reloads
a running bank. The driver uses ordered `writel()` operations.

The parameters are `zx279128_wdt.timeout=` and `zx279128_wdt.nowayout=`.
`nowayout` follows `CONFIG_WATCHDOG_NOWAYOUT`, unset in the shipped target.
Because `CONFIG_CMDLINE_FORCE` is enabled, bootloader arguments cannot change
these parameters; a command-line experiment needs a rebuilt kernel.

`watchdog_stop_on_reboot()` and `watchdog_stop_on_unregister()` are registered.
The normal reboot notifier stops the bank for restart, halt and poweroff;
the watchdog core's `watchdog.stop_on_reboot=0` override can keep it armed.
The driver has no `.restart` operation. The board's
[`zx279128-reboot`](../files/target/linux/armsr/files-6.6/drivers/power/reset/zx279128-reboot.c)
driver owns restart through TOPCRM `0x94000044`. The older generic
`syscon-reboot` attempt hung and is not the release restart path.

Host tests in [`test_watchdog.py`](../tests/test_watchdog.py) compile the actual
driver against a banked register model and, when the pinned kernel tree is
available, exercise real watchdog-core operations. They cover ownership,
unlock/readback failures, limits, reset-flag ordering and reboot/magic-close
behavior. They also check the DT and patch. Host tests supplement the measured
hardware results; they do not establish untested electrical behavior.

CPU frequency scaling is disabled. A future cpufreq implementation must account
for a changing PERIPHCLK because the driver samples its rate only at probe.
Suspend behavior is not qualified; the target does not enable system PM and
the driver supplies no suspend hooks.

## Historical investigation

Earlier measurements, withdrawn hypotheses and old commands are preserved in
[the archived notebook](history/WATCHDOG-QUALIFICATION.md). They are not current installation instructions.
