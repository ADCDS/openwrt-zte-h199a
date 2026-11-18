"""Execute the actual ZX279128S watchdog C against a banked Cortex-A9 TWD model.

The driver's constants, structures, CPU0 callbacks, ops/info tables and probe
are compiled verbatim with boundary stubs. The register model follows the
verified stock semantics:
  - Watchdog mode in CONTROL stays set until the unlock pair.
  - INTSTAT and RESETSTAT are write-1-to-clear.
  - Writing LOAD also reloads COUNTER.
The model keeps one bank per CPU. It fails on any access that is not made by
CPU0 inside one CPU0 call, on any read of the write-only DISABLE register, and
on any address outside the 0x18-byte register window. That makes an access to
the TWD timer half (0x800600-0x80061f) a test failure.

When the pinned kernel tree is present, the real 6.6 watchdog core is compiled
against the driver as well: start, stop, ping, set_timeout, init_timeout and
the reboot notifier. The Kconfig/Makefile patch and the DTS node are also
checked.

These tests prove software order and policy, not silicon behaviour. The
hardware qualification plan is in docs/WATCHDOG.md.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from test_tx_origin_r204 import function, require, tokens

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / 'files/target/linux/armsr'
SOURCE = TARGET / 'files-6.6/drivers/watchdog/zx279128_wdt.c'
PATCH = TARGET / 'patches-6.6/998-zx279128-watchdog.patch'
CONFIG = TARGET / 'config-6.6'
DTS = TARGET / 'files-6.6/arch/arm/boot/dts/zte/zx279128s-zte-h199a.dts'
TREES = sorted((ROOT / 'openwrt/build_dir').glob('target-*/linux-armsr_armv7/linux-6.6.151'))

DRIVER_FUNCTIONS = ('zx_wdt_load', 'zx_wdt_owner', 'zx_wdt_disable', 'zx_wdt_start_cpu0',
                    'zx_wdt_stop_cpu0', 'zx_wdt_reload_cpu0', 'zx_wdt_counter_cpu0',
                    'zx_wdt_takeover_cpu0', 'zx_wdt_call', 'zx_wdt_start', 'zx_wdt_stop',
                    'zx_wdt_ping', 'zx_wdt_set_timeout', 'zx_wdt_get_timeleft')
HEADER_HELPERS = ('watchdog_active', 'watchdog_hw_running', 'watchdog_set_nowayout',
                  'watchdog_stop_on_reboot', 'watchdog_stop_on_unregister',
                  'watchdog_timeout_invalid', 'watchdog_set_drvdata', 'watchdog_get_drvdata')
CORE_DEV = ('watchdog_need_worker', '__watchdog_ping', 'watchdog_ping', 'watchdog_start',
            'watchdog_stop', 'watchdog_set_timeout')
CORE_CORE = ('watchdog_check_min_max_timeout', 'watchdog_init_timeout', 'watchdog_reboot_notifier')
UAPI_FLAGS = {'WDIOF_CARDRESET': 0x0020, 'WDIOF_SETTIMEOUT': 0x0080,
              'WDIOF_MAGICCLOSE': 0x0100, 'WDIOF_KEEPALIVEPING': 0x8000}

PRELUDE = r'''
#include <assert.h>
#include <errno.h>
#include <limits.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef long long ktime_t;
#define __iomem
#define BIT(n) (1U << (n))
#define BIT_ULL(n) (1ULL << (n))
#define U32_MAX UINT32_MAX
#define min(a, b) ((a) < (b) ? (a) : (b))
#define min_t(t, a, b) ((t)(a) < (t)(b) ? (t)(a) : (t)(b))
#define EPROBE_DEFER 517
#define GFP_KERNEL 0x10
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define THIS_MODULE ((struct module *)0)
#define WATCHDOG_NOWAYOUT 0
#define WDIOF_CARDRESET 0x0020
#define WDIOF_SETTIMEOUT 0x0080
#define WDIOF_MAGICCLOSE 0x0100
#define WDIOF_KEEPALIVEPING 0x8000
#define container_of(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
static unsigned warnings_on;
#define WARN_ON_ONCE(c) ({ bool warn_ = (c); if (warn_) warnings_on++; warn_; })
#define PRINTF(f, a) __attribute__((format(printf, f, a)))
struct module;
struct device { void *of_node; };
struct platform_device { struct device dev; };
struct clk { int unused; };
struct notifier_block { int priority; };
struct watchdog_info { u32 options; u32 firmware_version; u8 identity[32]; };
struct watchdog_core_data { unsigned long status; ktime_t last_keepalive, last_hw_keepalive; int timer; };
struct watchdog_device;
struct watchdog_ops {
 struct module *owner;
 int (*start)(struct watchdog_device *);
 int (*stop)(struct watchdog_device *);
 int (*ping)(struct watchdog_device *);
 unsigned int (*status)(struct watchdog_device *);
 int (*set_timeout)(struct watchdog_device *, unsigned int);
 int (*set_pretimeout)(struct watchdog_device *, unsigned int);
 unsigned int (*get_timeleft)(struct watchdog_device *);
 int (*restart)(struct watchdog_device *, unsigned long, void *);
 long (*ioctl)(struct watchdog_device *, unsigned int, unsigned long);
};
struct watchdog_device {
 int id;
 struct device *parent;
 const struct watchdog_info *info;
 const struct watchdog_ops *ops;
 unsigned int bootstatus, timeout, pretimeout, min_timeout, max_timeout;
 unsigned int min_hw_heartbeat_ms, max_hw_heartbeat_ms;
 struct notifier_block reboot_nb;
 void *driver_data;
 struct watchdog_core_data *wd_data;
 unsigned long status;
};
typedef void (*smp_call_func_t)(void *info);
static inline void set_bit(int nr, unsigned long *addr) { *addr |= 1UL << nr; }
static inline void clear_bit(int nr, unsigned long *addr) { *addr &= ~(1UL << nr); }
static inline bool test_bit(int nr, const unsigned long *addr) { return (*addr >> nr) & 1; }
'''

# Per-CPU banks, the CPU0 dispatcher and the platform/devm boundary.
MODEL = r'''
#define WDT_WINDOW 0x18
struct bank { u32 load, counter, control, intstat, resetstat; int unlock; };
struct access { int cpu, write; unsigned call, reg; u32 value; };
static struct bank bank[2];
static unsigned char twd[0x40] __attribute__((aligned(4))); /* 0x800600..0x80063f */
static struct access trace[128];
static unsigned accesses, calls, in_call;
static int current_cpu, cpu0_offline, misroute, ignore_unlock, drop_prescaler;
static u32 noise;
static int smp_processor_id(void) { return current_cpu; }
static int smp_call_function_single(int cpu, smp_call_func_t fn, void *info, int wait) {
 assert(cpu == 0 && wait && !in_call);
 calls++;
 if (cpu0_offline)
  return -ENXIO;
 int caller = current_cpu;
 if (!misroute)
  current_cpu = cpu;
 in_call = calls;
 fn(info); /* Runs to completion with interrupts off: nothing interleaves. */
 in_call = 0;
 current_cpu = caller;
 return 0;
}
static unsigned reg_of(const volatile void *addr) {
 const volatile unsigned char *p = addr;
 /* Every access: CPU0, inside one CPU0 call, inside the watchdog window. */
 assert(in_call && current_cpu == 0);
 assert(p >= twd + 0x20 && p < twd + 0x20 + WDT_WINDOW && (p - twd) % 4 == 0);
 return (unsigned)(p - (twd + 0x20));
}
static void record(int write, unsigned reg, u32 value) {
 assert(accesses < sizeof(trace) / sizeof(trace[0]));
 trace[accesses++] = (struct access){ current_cpu, write, in_call, reg, value };
}
static void writel(u32 value, volatile void *addr) {
 unsigned reg = reg_of(addr);
 struct bank *b = &bank[current_cpu];
 record(1, reg, value);
 if (reg != ZX_WDT_DISABLE)
  b->unlock = 0; /* the unlock pair must be back to back */
 switch (reg) {
 case ZX_WDT_LOAD: b->load = b->counter = value; break;
 case ZX_WDT_COUNTER: b->counter = value; break;
 case ZX_WDT_CONTROL:
  b->control = (value & 0xff0f) | (b->control & ZX_WDT_CTRL_WD_MODE);
  if (drop_prescaler)
   b->control &= ~0xff00U;
  break;
 case ZX_WDT_INTSTAT: b->intstat &= ~value; break;
 case ZX_WDT_RESETSTAT: b->resetstat &= ~value; break;
 case ZX_WDT_DISABLE:
  if (value == ZX_WDT_UNLOCK2 && b->unlock && !ignore_unlock)
   b->control &= ~ZX_WDT_CTRL_WD_MODE;
  b->unlock = value == ZX_WDT_UNLOCK1;
  break;
 default: assert(!"unmodelled register");
 }
}
static u32 readl(const volatile void *addr) {
 unsigned reg = reg_of(addr);
 struct bank *b = &bank[current_cpu];
 record(0, reg, 0);
 b->unlock = 0;
 switch (reg) {
 case ZX_WDT_LOAD: return b->load;
 case ZX_WDT_COUNTER: return b->counter;
 case ZX_WDT_CONTROL: return b->control | noise;
 case ZX_WDT_INTSTAT: return b->intstat;
 case ZX_WDT_RESETSTAT: return b->resetstat;
 }
 assert(!"DISABLE is write-only");
 return 0;
}
static struct platform_device pdev;
static struct clk periphclk;
static struct watchdog_core_data core_data;
static struct watchdog_device *registered;
static unsigned long clk_rate;
static int alloc_fail, map_error, clk_error, register_error;
static unsigned maps, clk_gets, registrations, infos, warns, errs;
static void *allocations[8];
static unsigned nalloc;
static void *devm_kzalloc(struct device *dev, size_t size, int gfp) {
 assert(dev == &pdev.dev && gfp == GFP_KERNEL && !accesses && nalloc < 8);
 return alloc_fail ? NULL : (allocations[nalloc++] = calloc(1, size));
}
static void __iomem *devm_platform_ioremap_resource(struct platform_device *p, unsigned int index) {
 assert(p == &pdev && index == 0 && !accesses);
 maps++;
 return map_error ? ERR_PTR(map_error) : (void *)(twd + 0x20);
}
static struct clk *devm_clk_get_enabled(struct device *dev, const char *id) {
 assert(dev == &pdev.dev && !id && maps && !accesses);
 clk_gets++;
 return clk_error ? ERR_PTR(clk_error) : &periphclk;
}
static unsigned long clk_get_rate(struct clk *clk) { assert(clk == &periphclk); return clk_rate; }
static u64 div_u64(u64 dividend, u32 divisor) { return dividend / divisor; }
static PRINTF(2, 3) void dev_info(const struct device *dev, const char *fmt, ...) { infos++; }
static PRINTF(2, 3) void dev_warn(const struct device *dev, const char *fmt, ...) { warns++; }
static PRINTF(2, 3) void dev_err(const struct device *dev, const char *fmt, ...) { errs++; }
static PRINTF(3, 4) int dev_err_probe(const struct device *dev, int err, const char *fmt, ...) {
 errs++;
 return err;
}
static int devm_watchdog_register_device(struct device *dev, struct watchdog_device *wdd) {
 assert(dev == &pdev.dev && wdd->info && wdd->ops && wdd->ops->start && wdd->ops->stop);
 registrations++;
 if (register_error)
  return register_error;
 wdd->wd_data = &core_data;
 registered = wdd;
 return 0;
}
'''

# Boundary copies of include/linux/watchdog.h helpers, used without a tree.
LOCAL_HELPERS = r'''
#define WDOG_ACTIVE 0
#define WDOG_NO_WAY_OUT 1
#define WDOG_STOP_ON_REBOOT 2
#define WDOG_HW_RUNNING 3
#define WDOG_STOP_ON_UNREGISTER 4
static inline bool watchdog_hw_running(struct watchdog_device *w) { return test_bit(WDOG_HW_RUNNING, &w->status); }
static inline void watchdog_set_nowayout(struct watchdog_device *w, bool n) { if (n) set_bit(WDOG_NO_WAY_OUT, &w->status); }
static inline void watchdog_stop_on_reboot(struct watchdog_device *w) { set_bit(WDOG_STOP_ON_REBOOT, &w->status); }
static inline void watchdog_stop_on_unregister(struct watchdog_device *w) { set_bit(WDOG_STOP_ON_UNREGISTER, &w->status); }
static inline void watchdog_set_drvdata(struct watchdog_device *w, void *d) { w->driver_data = d; }
static inline void *watchdog_get_drvdata(struct watchdog_device *w) { return w->driver_data; }
static unsigned init_param, inits;
static int watchdog_init_timeout(struct watchdog_device *w, unsigned int param, struct device *dev) {
 /* The driver must publish its limits and default before validation. */
 assert(dev == &pdev.dev && w->parent == dev && w->min_timeout == 1);
 assert(w->max_hw_heartbeat_ms && w->timeout == 30 && w->driver_data);
 inits++;
 init_param = param;
 if (param && param >= w->min_timeout && param <= UINT_MAX / 1000)
  w->timeout = param;
 return 0;
}
'''

# Stubs that the real watchdog core functions need.
CORE_STUBS = r'''
#define SYS_DOWN 0x0001
#define SYS_RESTART SYS_DOWN
#define SYS_HALT 0x0002
#define SYS_POWER_OFF 0x0003
#define NOTIFY_DONE 0x0000
#define NOTIFY_BAD 0x8002
#define HRTIMER_MODE_REL_HARD 0
#define trace_watchdog_start(w, e) do { (void)(w); (void)(e); } while (0)
#define trace_watchdog_stop(w, e) do { (void)(w); (void)(e); } while (0)
#define trace_watchdog_ping(w, e) do { (void)(w); (void)(e); } while (0)
#define trace_watchdog_set_timeout(w, t, e) do { (void)(w); (void)(t); (void)(e); } while (0)
#define ktime_add(a, b) ((a) + (b))
#define ktime_sub(a, b) ((a) - (b))
#define ktime_after(a, b) ((a) > (b))
static unsigned core_logs, worker_updates;
static bool worker;
static ktime_t now_ns;
static ktime_t ktime_get(void) { return now_ns += 1000; }
static ktime_t ms_to_ktime(u64 ms) { return (ktime_t)ms * 1000000; }
static void hrtimer_start(int *timer, ktime_t t, int mode) { }
static void watchdog_hrtimer_pretimeout_start(struct watchdog_device *w) { }
static void watchdog_hrtimer_pretimeout_stop(struct watchdog_device *w) { }
static PRINTF(1, 2) void pr_info(const char *fmt, ...) { core_logs++; }
static PRINTF(1, 2) void pr_warn(const char *fmt, ...) { core_logs++; }
static PRINTF(1, 2) void pr_err(const char *fmt, ...) { core_logs++; }
static const char *dev_name(const struct device *dev) { return "800620.watchdog"; }
static int of_property_read_u32(const void *np, const char *name, u32 *value) { return -EINVAL; }
'''

# Records whether the real core would run its keepalive worker.
CORE_WORKER = r'''
static void watchdog_update_worker(struct watchdog_device *wdd) {
 worker_updates++;
 worker = watchdog_need_worker(wdd);
}
'''

COMMON_CASES = r'''
#define R(r) { .write = 0, .reg = ZX_WDT_##r }
#define W(r, v) { .write = 1, .reg = ZX_WDT_##r, .value = (v) }
#define STOP_SEQUENCE W(DISABLE, 0x12345678), W(DISABLE, 0x87654321), W(CONTROL, 0), \
 W(INTSTAT, 1), W(RESETSTAT, 1), R(CONTROL)
#define EXPECT_CALLS(n, ...) do { const struct access e_[] = { __VA_ARGS__ }; \
 expect(e_, sizeof(e_) / sizeof(e_[0]), n); } while (0)
#define EXPECT(...) EXPECT_CALLS(1, __VA_ARGS__)
static const struct bank zero_bank;
static void expect(const struct access *e, unsigned count, unsigned ncalls) {
 assert(accesses == count && calls == ncalls);
 for (unsigned i = 0; i < count; i++) {
  assert(trace[i].cpu == 0 && trace[i].call >= 1 && trace[i].call <= ncalls);
  assert(!i || trace[i].call >= trace[i - 1].call);
  assert(trace[i].write == e[i].write && trace[i].reg == e[i].reg);
  if (e[i].write)
   assert(trace[i].value == e[i].value);
 }
}
static void clear_trace(void) { accesses = calls = 0; }
static void reset_bench(void) {
 while (nalloc)
  free(allocations[--nalloc]);
 memset(bank, 0, sizeof(bank));
 memset(&core_data, 0, sizeof(core_data));
 clear_trace();
 current_cpu = 1; /* callers run on CPU1 unless a case says otherwise */
 cpu0_offline = misroute = ignore_unlock = drop_prescaler = 0;
 noise = 0;
 alloc_fail = map_error = clk_error = register_error = 0;
 clk_rate = 500000000;
 maps = clk_gets = registrations = infos = warns = errs = warnings_on = 0;
 registered = NULL;
 timeout = 0;
 nowayout = 0;
}
static struct zx_wdt *probe_ok(void) {
 unsigned before = registrations;
 assert(zx_wdt_probe(&pdev) == 0 && registered && registrations == before + 1);
 return registered->driver_data;
}
static void timer_half_untouched(void) {
 for (unsigned i = 0; i < sizeof(twd); i++)
  assert(twd[i] == 0xa5);
 assert(!memcmp(&bank[1], &zero_bank, sizeof(zero_bank)));
}
'''

CASES = r'''
int main(void) {
 struct zx_wdt *wdt;
 struct watchdog_device *wdd;

 _Static_assert(ZX_WDT_CTRL_START == 0x7f09, "verified stock control word");
 memset(twd, 0xa5, sizeof(twd));

 /* Probe on CPU1 takes over a bank U-Boot left armed (CONTROL 0x09: /1,
  * watchdog mode, enable). It reads the bank, then unlocks and stops it. */
 reset_bench();
 bank[0].control = 0x09;
 bank[0].load = bank[0].counter = 300000 * 5;
 bank[0].intstat = 1;
 wdt = probe_ok();
 EXPECT(R(CONTROL), R(COUNTER), R(RESETSTAT), STOP_SEQUENCE);
 assert(current_cpu == 1 && !bank[0].control && !bank[0].intstat);
 assert(wdt->base == (void *)(twd + 0x20) && wdt->rate == 3906250 && wdt->hw_max == 1099);
 wdd = registered;
 assert(wdd == &wdt->wdd && wdd->parent == &pdev.dev && wdd->driver_data == wdt);
 assert(wdd->ops == &zx_wdt_ops && wdd->info == &zx_wdt_info);
 assert(wdd->min_timeout == 1 && wdd->max_hw_heartbeat_ms == 1099000 && !wdd->max_timeout);
 assert(wdd->timeout == 30 && !wdd->bootstatus && warns == 1 && inits == 1 && !init_param);
 assert(test_bit(WDOG_STOP_ON_REBOOT, &wdd->status) && test_bit(WDOG_STOP_ON_UNREGISTER, &wdd->status));
 assert(!test_bit(WDOG_HW_RUNNING, &wdd->status) && !test_bit(WDOG_ACTIVE, &wdd->status));
 assert(!test_bit(WDOG_NO_WAY_OUT, &wdd->status) && infos == 1 && !errs);

 /* The stock enable word is stopped the same way. */
 reset_bench();
 bank[0].control = 0x7f09;
 bank[0].load = bank[0].counter = 1234;
 probe_ok();
 assert(!bank[0].control && warns == 1);

 /* RESETSTAT is read before the takeover clears it and becomes CARDRESET. */
 reset_bench();
 bank[0].resetstat = 1;
 probe_ok();
 EXPECT(R(CONTROL), R(COUNTER), R(RESETSTAT), STOP_SEQUENCE);
 assert(registered->bootstatus == WDIOF_CARDRESET && !bank[0].resetstat && warns == 1);

 /* A deferred clock must not consume the reset flag. */
 reset_bench();
 bank[0].resetstat = 1;
 bank[0].control = 0x09;
 clk_error = -EPROBE_DEFER;
 assert(zx_wdt_probe(&pdev) == -EPROBE_DEFER && !accesses && !calls && !registrations);
 assert(bank[0].resetstat == 1 && bank[0].control == 0x09);
 clk_error = 0;
 probe_ok();
 assert(registered->bootstatus == WDIOF_CARDRESET && !bank[0].control);

 /* Resource failures touch no register. */
 reset_bench();
 map_error = -EBUSY;
 assert(zx_wdt_probe(&pdev) == -EBUSY && !clk_gets && !accesses && !registrations);
 reset_bench();
 alloc_fail = 1;
 assert(zx_wdt_probe(&pdev) == -ENOMEM && !maps && !accesses);

 /* Below the /128 prescaler there is no usable rate. The bank is already
  * stopped, so the failed probe leaves the board safe. */
 reset_bench();
 bank[0].control = 0x09;
 clk_rate = 127;
 assert(zx_wdt_probe(&pdev) == -EINVAL && !registrations && !bank[0].control && calls == 1);
 reset_bench();
 clk_rate = 0;
 assert(zx_wdt_probe(&pdev) == -EINVAL && !registrations);

 /* Silicon that ignores the unlock pair keeps watchdog mode: fail loudly. */
 reset_bench();
 bank[0].control = 0x09;
 ignore_unlock = 1;
 assert(zx_wdt_probe(&pdev) == -EIO && !registrations && errs == 1);
 assert(bank[0].control & ZX_WDT_CTRL_WD_MODE);
 reset_bench();
 register_error = -ENOMEM;
 assert(zx_wdt_probe(&pdev) == -ENOMEM && registrations == 1 && !bank[0].control);

 /* CPU0 unavailable, or a dispatcher that ran the callback on CPU1: neither
  * bank is touched. */
 reset_bench();
 cpu0_offline = 1;
 assert(zx_wdt_probe(&pdev) == -ENXIO && !accesses && !registrations);
 reset_bench();
 misroute = 1;
 assert(zx_wdt_probe(&pdev) == -EIO && !accesses && warnings_on == 1 && !registrations);

 /* Rate and limits: clk >> 7 like stock, so a fraction truncates.
  * LOAD = rate * timeout - 1 must fit in 32 bits. */
 reset_bench();
 clk_rate = 500000001;
 wdt = probe_ok();
 assert(wdt->rate == 3906250 && wdt->hw_max == 1099);
 assert(zx_wdt_load(wdt, 1) == 3906249 && zx_wdt_load(wdt, 30) == 117187499);
 assert(zx_wdt_load(wdt, 1099) == 4292968749U && (u64)3906250 * 1100 - 1 > U32_MAX);
 assert(zx_wdt_load(wdt, 1100) == 4292968749U && zx_wdt_load(wdt, UINT_MAX) == 4292968749U);
 reset_bench();
 clk_rate = 1UL << 31; /* a power-of-two rate fills LOAD exactly */
 wdt = probe_ok();
 assert(wdt->rate == 1U << 24 && wdt->hw_max == 256 && registered->max_hw_heartbeat_ms == 256000);
 assert(zx_wdt_load(wdt, 256) == U32_MAX && zx_wdt_load(wdt, 257) == U32_MAX);
 reset_bench();
 clk_rate = 128; /* the core's millisecond arithmetic is the limit here */
 wdt = probe_ok();
 assert(wdt->rate == 1 && wdt->hw_max == UINT_MAX / 1000);
 assert(registered->max_hw_heartbeat_ms == UINT_MAX / 1000 * 1000);
 assert(zx_wdt_load(wdt, UINT_MAX) == UINT_MAX / 1000 - 1);

 /* Module parameters reach the core. */
 reset_bench();
 timeout = 45;
 probe_ok();
 assert(registered->timeout == 45 && init_param == 45);
 reset_bench();
 nowayout = 1;
 probe_ok();
 assert(test_bit(WDOG_NO_WAY_OUT, &registered->status));

 /* Operations: identical CPU0 traffic whether the caller runs on CPU1
  * (IPI) or on CPU0 itself. WDOG_* updates stand in for the core. */
 for (int cpu = 1; cpu >= 0; cpu--) {
  reset_bench();
  wdt = probe_ok();
  wdd = registered;
  current_cpu = cpu;
  clear_trace();
  assert(zx_wdt_start(wdd) == 0);
  EXPECT(W(LOAD, 117187499), W(CONTROL, 0x7f09), R(CONTROL));
  assert(bank[0].control == 0x7f09 && bank[0].counter == 117187499 && current_cpu == cpu);
  set_bit(WDOG_ACTIVE, &wdd->status);
  set_bit(WDOG_HW_RUNNING, &wdd->status);

  /* Feed: rewrite LOAD, which reloads COUNTER, and nothing else. */
  bank[0].counter = 7;
  clear_trace();
  assert(zx_wdt_ping(wdd) == 0);
  EXPECT(W(LOAD, 117187499));
  assert(bank[0].counter == 117187499 && bank[0].control == 0x7f09);

  /* Time left rounds down to whole seconds. */
  bank[0].counter = 3906250 * 7 - 1;
  clear_trace();
  assert(zx_wdt_get_timeleft(wdd) == 6);
  EXPECT(R(COUNTER));
  bank[0].counter = 3906250 * 7;
  assert(zx_wdt_get_timeleft(wdd) == 7);

  /* A running bank takes a new timeout at once. Beyond the hardware
   * maximum, LOAD holds the maximum and the core covers the rest. */
  clear_trace();
  assert(zx_wdt_set_timeout(wdd, 60) == 0 && wdd->timeout == 60);
  EXPECT(W(LOAD, 3906250U * 60 - 1));
  clear_trace();
  assert(zx_wdt_set_timeout(wdd, 5000) == 0 && wdd->timeout == 5000);
  EXPECT(W(LOAD, 4292968749U));
  clear_trace();
  assert(zx_wdt_ping(wdd) == 0);
  EXPECT(W(LOAD, 4292968749U));

  /* Stop: unlock pair, CONTROL, both flags, one verifying read. Reserved
   * CONTROL bits that read as ones do not affect the check. */
  noise = 0xffff00f0;
  bank[0].intstat = bank[0].resetstat = 1;
  clear_bit(WDOG_HW_RUNNING, &wdd->status);
  clear_trace();
  assert(zx_wdt_stop(wdd) == 0 && !test_bit(WDOG_HW_RUNNING, &wdd->status));
  EXPECT(STOP_SEQUENCE);
  assert(!bank[0].control && !bank[0].intstat && !bank[0].resetstat);
  clear_bit(WDOG_ACTIVE, &wdd->status);

  /* A stopped bank is programmed by the next start, not by set_timeout. */
  clear_trace();
  assert(zx_wdt_set_timeout(wdd, 20) == 0 && wdd->timeout == 20 && !accesses && !calls);
  clear_trace();
  assert(zx_wdt_start(wdd) == 0);
  EXPECT(W(LOAD, 3906250U * 20 - 1), W(CONTROL, 0x7f09), R(CONTROL));
  assert(!warnings_on && !errs);
 }

 /* An arm that drops the prescaler would expire 128 times early: back out. */
 reset_bench();
 wdd = &probe_ok()->wdd;
 drop_prescaler = 1;
 clear_trace();
 assert(zx_wdt_start(wdd) == -EIO && errs == 1);
 EXPECT(W(LOAD, 117187499), W(CONTROL, 0x7f09), R(CONTROL), STOP_SEQUENCE);
 assert(!bank[0].control);

 /* A refused stop leaves the bank running, and the core is told so. */
 reset_bench();
 wdd = &probe_ok()->wdd;
 assert(zx_wdt_start(wdd) == 0);
 ignore_unlock = 1;
 clear_trace();
 assert(zx_wdt_stop(wdd) == -EIO && test_bit(WDOG_HW_RUNNING, &wdd->status) && errs == 1);
 EXPECT(STOP_SEQUENCE);
 assert(bank[0].control & ZX_WDT_CTRL_WD_MODE);

 /* Without CPU0 every operation fails without access. A timeout that was
  * not applied is not recorded. */
 reset_bench();
 wdd = &probe_ok()->wdd;
 set_bit(WDOG_HW_RUNNING, &wdd->status);
 cpu0_offline = 1;
 clear_trace();
 assert(zx_wdt_ping(wdd) == -ENXIO && zx_wdt_get_timeleft(wdd) == 0);
 assert(zx_wdt_set_timeout(wdd, 90) == -ENXIO && wdd->timeout == 30);
 assert(zx_wdt_start(wdd) == -ENXIO && zx_wdt_stop(wdd) == -ENXIO && !accesses);
 cpu0_offline = 0;
 misroute = 1;
 assert(zx_wdt_ping(wdd) == -EIO && zx_wdt_stop(wdd) == -EIO && !accesses && warnings_on == 2);

 /* Tables: keepalive/settimeout/magic close/CARDRESET (procd reads the boot
  * status only when CARDRESET is advertised), and no restart operation. */
 assert(zx_wdt_ops.owner == THIS_MODULE && zx_wdt_ops.start == zx_wdt_start);
 assert(zx_wdt_ops.stop == zx_wdt_stop && zx_wdt_ops.ping == zx_wdt_ping);
 assert(zx_wdt_ops.set_timeout == zx_wdt_set_timeout && zx_wdt_ops.get_timeleft == zx_wdt_get_timeleft);
 assert(!zx_wdt_ops.restart && !zx_wdt_ops.set_pretimeout && !zx_wdt_ops.status && !zx_wdt_ops.ioctl);
 assert(zx_wdt_info.options == (WDIOF_SETTIMEOUT | WDIOF_KEEPALIVEPING | WDIOF_MAGICCLOSE | WDIOF_CARDRESET));
 assert(!strcmp((const char *)zx_wdt_info.identity, "ZX279128S A9 TWD watchdog"));

 timer_half_untouched();
 return 0;
}
'''

CORE_CASES = r'''
int main(void) {
 struct watchdog_device *wdd;

 memset(twd, 0xa5, sizeof(twd));

 /* The real init_timeout with the driver's limits. Timeouts above the
  * hardware maximum are valid because the core bridges them. */
 const unsigned params[] = { 0, 1, 30, 1099, 5000, UINT_MAX / 1000, UINT_MAX / 1000 + 1 };
 const unsigned results[] = { 30, 1, 30, 1099, 5000, UINT_MAX / 1000, 30 };
 for (unsigned i = 0; i < sizeof(params) / sizeof(params[0]); i++) {
  reset_bench();
  timeout = params[i];
  probe_ok();
  assert(registered->timeout == results[i]);
 }

 /* After probe the core has nothing to feed: the bank is stopped and no
  * worker would run before userspace opens the device. */
 reset_bench();
 wdd = &probe_ok()->wdd;
 assert(!watchdog_hw_running(wdd) && !watchdog_need_worker(wdd));

 /* procd's open, from CPU1: the real watchdog_start arms CPU0's bank and
  * needs no kernel worker for a 30 s timeout. */
 clear_trace();
 assert(watchdog_start(wdd) == 0 && watchdog_active(wdd) && watchdog_hw_running(wdd) && !worker);
 EXPECT(W(LOAD, 117187499), W(CONTROL, 0x7f09), R(CONTROL));
 assert(current_cpu == 1);
 clear_trace();
 assert(watchdog_ping(wdd) == 0);
 EXPECT(W(LOAD, 117187499));

 /* WDIOC_SETTIMEOUT is set_timeout followed by a ping. 5000 s is bridged in
  * hardware-maximum steps until the userspace deadline. */
 clear_trace();
 assert(watchdog_set_timeout(wdd, 5000) == 0 && watchdog_ping(wdd) == 0 && worker);
 EXPECT_CALLS(2, W(LOAD, 4292968749U), W(LOAD, 4292968749U));
 clear_trace();
 assert(watchdog_set_timeout(wdd, 30) == 0 && watchdog_ping(wdd) == 0 && !worker);
 EXPECT_CALLS(2, W(LOAD, 117187499), W(LOAD, 117187499));
 clear_trace();
 assert(watchdog_set_timeout(wdd, 0) == -EINVAL && !calls);
 assert(watchdog_set_timeout(wdd, UINT_MAX / 1000 + 1) == -EINVAL && !calls && wdd->timeout == 30);

 /* Magic close without nowayout stops the bank. */
 clear_trace();
 assert(watchdog_stop(wdd) == 0 && !watchdog_active(wdd) && !watchdog_hw_running(wdd) && !worker);
 EXPECT(STOP_SEQUENCE);
 assert(!bank[0].control);
 clear_trace();
 assert(watchdog_reboot_notifier(&wdd->reboot_nb, SYS_RESTART, NULL) == NOTIFY_DONE && !calls);

 /* nowayout: userspace cannot stop it. An orderly restart, halt or power-off
  * still stops it on CPU0 through the core's reboot notifier. */
 const unsigned long codes[] = { SYS_RESTART, SYS_HALT, SYS_POWER_OFF };
 for (unsigned i = 0; i < 3; i++) {
  reset_bench();
  nowayout = 1;
  wdd = &probe_ok()->wdd;
  assert(watchdog_start(wdd) == 0);
  clear_trace();
  assert(watchdog_stop(wdd) == -EBUSY && !calls && watchdog_active(wdd) && watchdog_hw_running(wdd));
  assert(bank[0].control == 0x7f09);
  clear_trace();
  assert(watchdog_reboot_notifier(&wdd->reboot_nb, codes[i], NULL) == NOTIFY_DONE);
  EXPECT(STOP_SEQUENCE);
  assert(!bank[0].control && current_cpu == 1);
 }

 /* When the hardware refuses a stop, the device stays active and the core
  * still sees it running, so the reboot notifier retries and reports it. */
 reset_bench();
 wdd = &probe_ok()->wdd;
 assert(watchdog_start(wdd) == 0);
 ignore_unlock = 1;
 clear_trace();
 assert(watchdog_stop(wdd) == -EIO && watchdog_active(wdd) && watchdog_hw_running(wdd));
 clear_trace();
 assert(watchdog_reboot_notifier(&wdd->reboot_nb, SYS_RESTART, NULL) == NOTIFY_BAD);
 EXPECT(STOP_SEQUENCE);

 timer_half_untouched();
 return 0;
}
'''


def defines(text, prefix):
    """Return every #define with the prefix, including continuation lines."""
    lines, out, i = text.splitlines(), [], 0
    while i < len(lines):
        if lines[i].startswith(prefix):
            out.append(lines[i])
            while lines[i].endswith('\\'):
                i += 1
                out.append(lines[i])
        i += 1
    require(out, f'no {prefix} definitions')
    return '\n'.join(out) + '\n'


def declaration(text, head):
    """Return a top-level brace declaration that starts with head and ends at '};'."""
    found = re.findall(r'^' + re.escape(head) + r'.*?^\};\n', text, re.M | re.S)
    require(len(found) == 1, f'Expected one declaration starting {head!r}')
    return found[0]


def driver():
    text = SOURCE.read_text()
    params = re.findall(r'^static unsigned int timeout;$|^static bool nowayout = WATCHDOG_NOWAYOUT;$',
                        text, re.M)
    require(len(params) == 2, 'module parameter declarations changed')
    state = '\n'.join(params) + '\n' + declaration(text, 'struct zx_wdt {') + \
        declaration(text, 'struct zx_wdt_call {')
    code = '\n'.join(function(text, name) for name in DRIVER_FUNCTIONS) + '\n' + \
        declaration(text, 'static const struct watchdog_info zx_wdt_info = {') + \
        declaration(text, 'static const struct watchdog_ops zx_wdt_ops = {') + \
        function(text, 'zx_wdt_probe') + '\n'
    return defines(text, '#define ZX_WDT_'), state, code


def run_c(test, code, name):
    with tempfile.TemporaryDirectory() as directory:
        source, executable = Path(directory) / f'{name}.c', Path(directory) / name
        source.write_text(code)
        run = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                              '-Wno-unused-parameter', str(source), '-o', str(executable)],
                             capture_output=True, text=True)
        test.assertEqual(run.returncode, 0, run.stderr)
        run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=20)
        test.assertEqual(run.returncode, 0, run.stdout + run.stderr)


def tree():
    if len(TREES) != 1:
        raise unittest.SkipTest('requires the pinned prepared kernel tree')
    return TREES[0]


class WatchdogDriverTests(unittest.TestCase):
    def test_cpu0_register_sequences_probe_takeover_and_limits(self):
        constants, state, code = driver()
        run_c(self, PRELUDE + constants + MODEL + state + LOCAL_HELPERS + code +
              COMMON_CASES + CASES, 'watchdog')

    def test_real_watchdog_core_nowayout_reboot_and_bridging(self):
        kernel = tree()
        header = (kernel / 'include/linux/watchdog.h').read_text()
        core = (kernel / 'drivers/watchdog/watchdog_core.c').read_text()
        dev = (kernel / 'drivers/watchdog/watchdog_dev.c').read_text()
        private = (kernel / 'drivers/watchdog/watchdog_core.h').read_text()
        uapi = (kernel / 'include/uapi/linux/watchdog.h').read_text()
        for name, value in UAPI_FLAGS.items():
            found = re.search(rf'^#define\s+{name}\s+(0x[0-9a-fA-F]+)', uapi, re.M)
            self.assertTrue(found and int(found.group(1), 16) == value, name)
        helpers = defines(header, '#define WDOG_') + defines(private, '#define _WDOG_') + \
            '\n'.join(function(header, name) for name in HEADER_HELPERS) + '\n' + CORE_STUBS + \
            '\n'.join(function(core, name) for name in CORE_CORE[:2]) + '\n'
        functions = '\n'.join(function(dev, name) for name in CORE_DEV[:1]) + CORE_WORKER + \
            '\n'.join(function(dev, name) for name in CORE_DEV[1:]) + '\n' + \
            function(core, CORE_CORE[2]) + '\n'
        constants, state, code = driver()
        run_c(self, PRELUDE + constants + MODEL + state + helpers + code + functions +
              COMMON_CASES + CORE_CASES, 'watchdog_core')

    def test_userspace_only_keepalive_and_mmio_contract(self):
        text = SOURCE.read_text()
        code = set(tokens(text))
        # No feeder, no pretimeout IRQ, no relaxed MMIO (writel supplies the
        # stock dsb), no restart handler and no other CPU's bank.
        forbidden = {'kthread_create', 'kthread_run', 'timer_setup', 'mod_timer', 'hrtimer_start',
                     'schedule_delayed_work', 'queue_work', 'queue_delayed_work', 'cpuhp_setup_state',
                     'writel_relaxed', 'readl_relaxed', 'restart', 'register_restart_handler',
                     'request_irq', 'devm_request_irq', 'request_percpu_irq', 'platform_get_irq',
                     'on_each_cpu', 'smp_call_function'}
        self.assertFalse(code & forbidden, code & forbidden)
        # SoC first, generic second: the driver is SoC-specific and must not
        # claim a generic ARM compatible as its primary match.
        self.assertEqual(re.findall(r'\.compatible = ("[^"]+")', text),
                         ['"zte,zx279128s-wdt"', '"arm,cortex-a9-twd-wdt"'])
        self.assertIn('smp_call_function_single', code)
        for snippet in ('module_param(nowayout, bool, 0);', 'watchdog_set_nowayout(&wdt->wdd, nowayout);',
                        'watchdog_stop_on_reboot(&wdt->wdd);', 'watchdog_stop_on_unregister(&wdt->wdd);',
                        'devm_clk_get_enabled(dev, NULL)', '#define ZX_WDT_CPU\t\t0'):
            self.assertEqual(text.count(snippet), 1, snippet)

    def test_kernel_config_and_patch_text(self):
        config = CONFIG.read_text().splitlines()
        for line in ('CONFIG_WATCHDOG_CORE=y', 'CONFIG_WATCHDOG_SYSFS=y', 'CONFIG_ZX279128_WATCHDOG=y'):
            self.assertEqual(config.count(line), 1, line)
        # nowayout stays at OpenWrt's default so procd's magic close can stop it.
        self.assertFalse([line for line in config if 'WATCHDOG_NOWAYOUT' in line])
        patch = PATCH.read_text()
        self.assertEqual(re.findall(r'^--- a/(\S+)$', patch, re.M),
                         ['drivers/watchdog/Kconfig', 'drivers/watchdog/Makefile'])
        for line in ('+config ZX279128_WATCHDOG\n', '+\tselect WATCHDOG_CORE\n',
                     '+\tdepends on OF && (ARCH_ZX279128 || COMPILE_TEST)\n',
                     '+obj-$(CONFIG_ZX279128_WATCHDOG) += zx279128_wdt.o\n'):
            self.assertEqual(patch.count(line), 1, line)
        self.assertEqual(SOURCE.name, 'zx279128_wdt.c')

    def test_patch_applies_exactly_to_pinned_tree(self):
        kernel = tree()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('Kconfig', 'Makefile'):
                target = root / 'drivers/watchdog' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(kernel / 'drivers/watchdog' / name, target)
            if 'config ZX279128_WATCHDOG' not in (root / 'drivers/watchdog/Kconfig').read_text():
                subprocess.run(['patch', '-p1', '--batch', '--fuzz=0', '--input', str(PATCH)],
                               cwd=root, check=True, capture_output=True, text=True)
            kconfig = (root / 'drivers/watchdog/Kconfig').read_text()
            makefile = (root / 'drivers/watchdog/Makefile').read_text()
            self.assertEqual(kconfig.count('config ZX279128_WATCHDOG\n'), 1)
            self.assertEqual(makefile.count('obj-$(CONFIG_ZX279128_WATCHDOG) += zx279128_wdt.o\n'), 1)
            arm = kconfig.index('# ARM Architecture')
            self.assertTrue(arm < kconfig.index('config ZX279128_WATCHDOG') <
                            kconfig.index('# X86 (i386 + ia64 + x86_64) Architecture'))

    def test_dts_node_text(self):
        text = DTS.read_text()
        node = re.search(r'^\t\twatchdog@800620 \{\n(.*?)^\t\t\};', text, re.M | re.S)
        self.assertTrue(node)
        self.assertEqual([line.strip() for line in node.group(1).splitlines()], [
            'compatible = "zte,zx279128s-wdt", "arm,cortex-a9-twd-wdt";',
            'reg = <0x00800620 0x20>;',
            'interrupts = <GIC_PPI 14 (GIC_CPU_MASK_SIMPLE(1) | IRQ_TYPE_EDGE_RISING)>;',
            'clocks = <&periphclk>;'])

    def test_compiled_device_tree_node(self):
        kernel = tree()
        if not all(shutil.which(tool) for tool in ('cpp', 'dtc', 'fdtget')):
            self.skipTest('requires host cpp, dtc and fdtget')
        with tempfile.TemporaryDirectory() as directory:
            source, blob = Path(directory) / 'h199a.dts', Path(directory) / 'h199a.dtb'
            subprocess.run(['cpp', '-nostdinc', '-undef', '-D__DTS__', '-x', 'assembler-with-cpp',
                            '-I', str(TARGET / 'files-6.6/include'), '-I', str(kernel / 'include'),
                            str(DTS), '-o', str(source)], check=True, capture_output=True)
            run = subprocess.run(['dtc', '-I', 'dts', '-O', 'dtb', '-o', str(blob), str(source)],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertNotIn('watchdog', run.stderr)

            def get(node, prop, kind='x'):
                return subprocess.run(['fdtget', '-t', kind, str(blob), node, prop], check=True,
                                      capture_output=True, text=True).stdout.split()
            node = '/soc/watchdog@800620'
            self.assertEqual(get(node, 'compatible', 's'),
                             ['zte,zx279128s-wdt', 'arm,cortex-a9-twd-wdt'])
            # Watchdog half only: the 0x800600-0x80061f timer half is outside.
            self.assertEqual(get(node, 'reg'), ['800620', '20'])
            # Stock <1 0x0e 0x101>: PPI 14, CPU0 mask, rising edge.
            self.assertEqual(get(node, 'interrupts'), ['1', 'e', '101'])
            # The stock DT gives the global timer and this node one clock.
            self.assertEqual(get(node, 'clocks'), get('/soc/timer@800200', 'clocks'))
            self.assertEqual(get(node, 'clocks'), get('/clocks/clock-periph', 'phandle'))
            self.assertEqual(get('/clocks/clock-periph', 'clock-frequency', 'u'), ['500000000'])


if __name__ == '__main__':
    unittest.main()
