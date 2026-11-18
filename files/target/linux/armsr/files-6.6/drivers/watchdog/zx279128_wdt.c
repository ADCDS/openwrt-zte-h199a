// SPDX-License-Identifier: GPL-2.0-only
/*
 * ZTE ZX279128S Cortex-A9 TWD watchdog.
 *
 * This driver uses only the watchdog half of the A9 TWD at PERIPHBASE + 0x620.
 * It never touches the timer half at +0x600. The registers are banked per CPU,
 * so an access reaches the bank of whichever core runs it. The stock kernel
 * arms, feeds and disables only CPU0's bank. Here, every access runs on CPU0
 * inside one smp_call_function_single() callback, with interrupts off. That
 * also serializes the register sequences without a lock.
 *
 * No CPU hotplug callback is needed. The platform's smp_operations have no
 * cpu_die, so no CPU can go offline, and ARM never offers the boot CPU for
 * hotplug by default. CPU1's bank is never armed, so CPU1 has nothing to
 * save or restore.
 *
 * The register semantics were checked instruction by instruction against the
 * stock wdt_zx.c:
 *   - LOAD = rate * timeout - 1.
 *   - CONTROL 0x7f09 sets the /128 prescaler, watchdog mode and enable.
 *   - Disable is 0x12345678 then 0x87654321, then CONTROL 0, INTSTAT 1 and
 *     RESETSTAT 1.
 *   - A feed rewrites LOAD.
 * writel() issues the same dsb and outer-cache sync before each store as the
 * stock code. U-Boot's own "watchdog" command uses different values; do not
 * copy them.
 *
 * Userspace, normally procd, keeps the watchdog alive through /dev/watchdog.
 * Probe leaves the hardware stopped, and nothing here feeds it on a timer.
 * The watchdog core pings only to cover a timeout longer than the hardware
 * maximum, and it stops at the deadline userspace set.
 */
#include <linux/bits.h>
#include <linux/build_bug.h>
#include <linux/clk.h>
#include <linux/io.h>
#include <linux/limits.h>
#include <linux/math64.h>
#include <linux/minmax.h>
#include <linux/mod_devicetable.h>
#include <linux/module.h>
#include <linux/moduleparam.h>
#include <linux/platform_device.h>
#include <linux/smp.h>
#include <linux/watchdog.h>

#define ZX_WDT_LOAD		0x00
#define ZX_WDT_COUNTER		0x04
#define ZX_WDT_CONTROL		0x08
#define ZX_WDT_INTSTAT		0x0c
#define ZX_WDT_RESETSTAT	0x10
#define ZX_WDT_DISABLE		0x14

#define ZX_WDT_CTRL_ENABLE	BIT(0)
#define ZX_WDT_CTRL_WD_MODE	BIT(3)
#define ZX_WDT_CTRL_FIELDS	0xff0f	/* prescaler[15:8] and bits [3:0] */
#define ZX_WDT_PRESCALER	0x7f
#define ZX_WDT_RATE_DIV		(ZX_WDT_PRESCALER + 1)
#define ZX_WDT_CTRL_START	((ZX_WDT_PRESCALER << 8) | ZX_WDT_CTRL_WD_MODE | \
				 ZX_WDT_CTRL_ENABLE)
#define ZX_WDT_FLAG		BIT(0)	/* INTSTAT event, RESETSTAT reset flag */
#define ZX_WDT_UNLOCK1		0x12345678
#define ZX_WDT_UNLOCK2		0x87654321

#define ZX_WDT_CPU		0
#define ZX_WDT_DEFAULT_TIMEOUT	30	/* procd's default timeout */

static_assert(ZX_WDT_CTRL_START == 0x7f09);

static unsigned int timeout;
module_param(timeout, uint, 0);
MODULE_PARM_DESC(timeout, "Initial timeout in seconds (default "
		 __MODULE_STRING(ZX_WDT_DEFAULT_TIMEOUT) ")");

static bool nowayout = WATCHDOG_NOWAYOUT;
module_param(nowayout, bool, 0);
MODULE_PARM_DESC(nowayout, "Watchdog cannot be stopped once started (default="
		 __MODULE_STRING(WATCHDOG_NOWAYOUT) ")");

struct zx_wdt {
	struct watchdog_device wdd;
	void __iomem *base;
	u32 rate;		/* counter ticks per second after the prescaler */
	unsigned int hw_max;	/* longest timeout LOAD can hold, in seconds */
};

/* One CPU0 transaction: its input and the registers it read back. */
struct zx_wdt_call {
	struct zx_wdt *wdt;
	unsigned int timeout;	/* start, reload: seconds to program */
	u32 inherited;		/* takeover: CONTROL as the boot chain left it */
	u32 armed;		/* start: CONTROL read back after arming */
	u32 control;		/* start, stop, takeover: final CONTROL */
	u32 counter;		/* takeover, counter: COUNTER */
	u32 resetstat;		/* takeover: RESETSTAT before it is cleared */
	int ret;
};

static u32 zx_wdt_load(const struct zx_wdt *wdt, unsigned int seconds)
{
	return (u32)((u64)wdt->rate * min(seconds, wdt->hw_max) - 1);
}

static bool zx_wdt_owner(struct zx_wdt_call *call)
{
	/* Any other core would program its own bank, not CPU0's. */
	if (WARN_ON_ONCE(smp_processor_id() != ZX_WDT_CPU)) {
		call->ret = -EIO;
		return false;
	}
	return true;
}

/* Stock hw_watchdog_disable order: unlock pair, CONTROL, then both flags. */
static int zx_wdt_disable(struct zx_wdt_call *call)
{
	void __iomem *base = call->wdt->base;

	writel(ZX_WDT_UNLOCK1, base + ZX_WDT_DISABLE);
	writel(ZX_WDT_UNLOCK2, base + ZX_WDT_DISABLE);
	writel(0, base + ZX_WDT_CONTROL);
	writel(ZX_WDT_FLAG, base + ZX_WDT_INTSTAT);
	writel(ZX_WDT_FLAG, base + ZX_WDT_RESETSTAT);
	call->control = readl(base + ZX_WDT_CONTROL);
	if (call->control & (ZX_WDT_CTRL_WD_MODE | ZX_WDT_CTRL_ENABLE))
		return -EIO;
	return 0;
}

static void zx_wdt_start_cpu0(void *info)
{
	struct zx_wdt_call *call = info;
	void __iomem *base = call->wdt->base;

	if (!zx_wdt_owner(call))
		return;
	/* Stock hw_watchdog_enable: LOAD first, then arm in watchdog mode. */
	writel(zx_wdt_load(call->wdt, call->timeout), base + ZX_WDT_LOAD);
	writel(ZX_WDT_CTRL_START, base + ZX_WDT_CONTROL);
	call->armed = readl(base + ZX_WDT_CONTROL);
	call->control = call->armed;
	call->ret = 0;
	if ((call->armed & ZX_WDT_CTRL_FIELDS) != ZX_WDT_CTRL_START) {
		/* A dropped prescaler would expire 128 times early: back out. */
		zx_wdt_disable(call);
		call->ret = -EIO;
	}
}

static void zx_wdt_stop_cpu0(void *info)
{
	struct zx_wdt_call *call = info;

	if (zx_wdt_owner(call))
		call->ret = zx_wdt_disable(call);
}

static void zx_wdt_reload_cpu0(void *info)
{
	struct zx_wdt_call *call = info;

	if (!zx_wdt_owner(call))
		return;
	/* Stock feed: writing LOAD also reloads the counter. */
	writel(zx_wdt_load(call->wdt, call->timeout),
	       call->wdt->base + ZX_WDT_LOAD);
	call->ret = 0;
}

static void zx_wdt_counter_cpu0(void *info)
{
	struct zx_wdt_call *call = info;

	if (!zx_wdt_owner(call))
		return;
	call->counter = readl(call->wdt->base + ZX_WDT_COUNTER);
	call->ret = 0;
}

static void zx_wdt_takeover_cpu0(void *info)
{
	struct zx_wdt_call *call = info;
	void __iomem *base = call->wdt->base;

	if (!zx_wdt_owner(call))
		return;
	/* Read what the boot chain left before the disable clears the flag. */
	call->inherited = readl(base + ZX_WDT_CONTROL);
	call->counter = readl(base + ZX_WDT_COUNTER);
	call->resetstat = readl(base + ZX_WDT_RESETSTAT);
	call->ret = zx_wdt_disable(call);
}

static int zx_wdt_call(struct zx_wdt *wdt, smp_call_func_t fn,
		       struct zx_wdt_call *call)
{
	int ret;

	call->wdt = wdt;
	call->ret = -EIO;
	ret = smp_call_function_single(ZX_WDT_CPU, fn, call, true);
	return ret ? ret : call->ret;
}

static int zx_wdt_start(struct watchdog_device *wdd)
{
	struct zx_wdt_call call = { .timeout = wdd->timeout };
	int ret;

	ret = zx_wdt_call(watchdog_get_drvdata(wdd), zx_wdt_start_cpu0, &call);
	if (ret)
		dev_err(wdd->parent,
			"CPU0 watchdog did not arm (control %#x, then %#x)\n",
			call.armed, call.control);
	return ret;
}

static int zx_wdt_stop(struct watchdog_device *wdd)
{
	struct zx_wdt_call call = {};
	int ret;

	ret = zx_wdt_call(watchdog_get_drvdata(wdd), zx_wdt_stop_cpu0, &call);
	if (ret) {
		/* The core cleared this before calling; the bank may still run. */
		set_bit(WDOG_HW_RUNNING, &wdd->status);
		dev_err(wdd->parent, "CPU0 watchdog did not stop (control %#x)\n",
			call.control);
	}
	return ret;
}

static int zx_wdt_ping(struct watchdog_device *wdd)
{
	struct zx_wdt_call call = { .timeout = wdd->timeout };

	return zx_wdt_call(watchdog_get_drvdata(wdd), zx_wdt_reload_cpu0, &call);
}

static int zx_wdt_set_timeout(struct watchdog_device *wdd,
			      unsigned int new_timeout)
{
	struct zx_wdt_call call = { .timeout = new_timeout };
	int ret;

	/* A stopped bank is programmed by the next start instead. */
	if (watchdog_hw_running(wdd)) {
		ret = zx_wdt_call(watchdog_get_drvdata(wdd), zx_wdt_reload_cpu0,
				  &call);
		if (ret)
			return ret;
	}
	wdd->timeout = new_timeout;
	return 0;
}

static unsigned int zx_wdt_get_timeleft(struct watchdog_device *wdd)
{
	struct zx_wdt *wdt = watchdog_get_drvdata(wdd);
	struct zx_wdt_call call = {};

	if (zx_wdt_call(wdt, zx_wdt_counter_cpu0, &call))
		return 0;
	return call.counter / wdt->rate;
}

static const struct watchdog_info zx_wdt_info = {
	.options = WDIOF_SETTIMEOUT | WDIOF_KEEPALIVEPING | WDIOF_MAGICCLOSE |
		   WDIOF_CARDRESET,
	.identity = "ZX279128S A9 TWD watchdog",
};

/* No .restart: the board resets through the zx279128-reboot driver. */
static const struct watchdog_ops zx_wdt_ops = {
	.owner = THIS_MODULE,
	.start = zx_wdt_start,
	.stop = zx_wdt_stop,
	.ping = zx_wdt_ping,
	.set_timeout = zx_wdt_set_timeout,
	.get_timeleft = zx_wdt_get_timeleft,
};

static int zx_wdt_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct zx_wdt_call call = {};
	struct zx_wdt *wdt;
	struct clk *clk;
	u64 rate;
	int ret;

	wdt = devm_kzalloc(dev, sizeof(*wdt), GFP_KERNEL);
	if (!wdt)
		return -ENOMEM;

	wdt->base = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(wdt->base))
		return PTR_ERR(wdt->base);

	/* Acquire the clock first: a deferred probe must not clear RESETSTAT. */
	clk = devm_clk_get_enabled(dev, NULL);
	if (IS_ERR(clk))
		return dev_err_probe(dev, PTR_ERR(clk), "cannot enable PERIPHCLK\n");

	/* The boot chain may have left the bank armed: force a stopped state. */
	ret = zx_wdt_call(wdt, zx_wdt_takeover_cpu0, &call);
	if (ret)
		return dev_err_probe(dev, ret,
				     "cannot stop CPU0 watchdog (control %#x)\n",
				     call.control);
	if (call.inherited & (ZX_WDT_CTRL_WD_MODE | ZX_WDT_CTRL_ENABLE))
		dev_warn(dev, "stopped inherited watchdog (control %#x, counter %#x)\n",
			 call.inherited, call.counter);
	if (call.resetstat & ZX_WDT_FLAG) {
		dev_warn(dev, "reset flag set: the last reset came from the CPU0 watchdog\n");
		wdt->wdd.bootstatus = WDIOF_CARDRESET;
	}

	/* The stock driver derives the rate as clk_get_rate() >> 7. */
	rate = clk_get_rate(clk) / ZX_WDT_RATE_DIV;
	if (!rate || rate > U32_MAX)
		return dev_err_probe(dev, -EINVAL, "unusable PERIPHCLK rate %lu\n",
				     clk_get_rate(clk));
	wdt->rate = rate;
	/* rate * timeout must fit in LOAD + 1, and timeout * 1000 in a uint. */
	wdt->hw_max = min_t(u64, div_u64(BIT_ULL(32), wdt->rate), UINT_MAX / 1000);

	wdt->wdd.info = &zx_wdt_info;
	wdt->wdd.ops = &zx_wdt_ops;
	wdt->wdd.parent = dev;
	wdt->wdd.min_timeout = 1;
	wdt->wdd.max_hw_heartbeat_ms = wdt->hw_max * 1000;
	wdt->wdd.timeout = ZX_WDT_DEFAULT_TIMEOUT;
	watchdog_set_drvdata(&wdt->wdd, wdt);
	watchdog_init_timeout(&wdt->wdd, timeout, dev);
	watchdog_set_nowayout(&wdt->wdd, nowayout);
	watchdog_stop_on_reboot(&wdt->wdd);
	watchdog_stop_on_unregister(&wdt->wdd);

	ret = devm_watchdog_register_device(dev, &wdt->wdd);
	if (ret)
		return ret;

	dev_info(dev, "CPU%d bank, %u Hz, timeout %u s, hardware maximum %u s\n",
		 ZX_WDT_CPU, wdt->rate, wdt->wdd.timeout, wdt->hw_max);
	return 0;
}

static const struct of_device_id zx_wdt_match[] = {
	{ .compatible = "zte,zx279128s-wdt" },
	/* Kept so a DT that predates the SoC string still probes. */
	{ .compatible = "arm,cortex-a9-twd-wdt" },
	{ }
};
MODULE_DEVICE_TABLE(of, zx_wdt_match);

static struct platform_driver zx_wdt_driver = {
	.probe = zx_wdt_probe,
	.driver = {
		.name = "zx279128-wdt",
		.of_match_table = zx_wdt_match,
	},
};
module_platform_driver(zx_wdt_driver);

MODULE_DESCRIPTION("ZTE ZX279128S Cortex-A9 TWD watchdog");
MODULE_LICENSE("GPL");
