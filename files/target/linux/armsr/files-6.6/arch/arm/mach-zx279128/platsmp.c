// SPDX-License-Identifier: GPL-2.0
/*
 * SMP support for the ZTE/Sanechips ZX279128S (ZXHN H199A).
 *
 * Reverse-engineered from the stock ZX279128S vmlinux (Linux 4.1.25).
 * The recovered vendor smp_operations is:
 *
 *   CPU_METHOD_OF_DECLARE("zte,zx279128s-smp") -> 0xc059bc18
 *      .smp_prepare_cpus   = 0xc05782b0  zx_smp_prepare_cpus
 *      .smp_secondary_init = 0xc001750c  zx_secondary_init
 *      .smp_boot_secondary = 0xc0017470  zx_boot_secondary
 *      .cpu_kill/.cpu_die  = NULL        (vendor ships no hotplug)
 *
 * Scheme: the BootROM parks CPU1 in a holding pen in on-chip SRAM
 * (DT "zte,zx279128s-smp-sram", phys 0x200800). smp_prepare_cpus enables the A9 SCU
 * (base from CBAR/PERIPHBASE, NOT from a DT scu node -- the stock DTB has
 * no scu node at all), copies the trampoline into SRAM and patches in the
 * physical addresses of secondary_startup and pen_release.
 * smp_boot_secondary then writes the CPU id into pen_release, flushes it,
 * and issues BOTH a wakeup IPI and an SEV.
 */
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/smp.h>

#include <asm/cacheflush.h>
#include <asm/cputype.h>
#include <asm/smp_plat.h>
#include <asm/smp_scu.h>
#include <asm/spinlock.h>	/* dsb_sev() */

extern void zx_secondary_trampoline(void);
extern void zx_secondary_trampoline_end(void);

/*
 * Written by smp_boot_secondary, polled by the trampoline running in SRAM
 * with the MMU and D-cache off. Must sit in its own cache line and be
 * flushed to memory by hand after every write.
 */
volatile int zx_pen_release __cacheline_aligned = -1;

static void __iomem *zx_scu_base;

static void zx_write_pen_release(int val)
{
	zx_pen_release = val;
	smp_wmb();
	sync_cache_w(&zx_pen_release);
	outer_clean_range(__pa(&zx_pen_release),
			  __pa(&zx_pen_release) + sizeof(zx_pen_release));
}

static void zx_secondary_init(unsigned int cpu)
{
	/* Vendor does scu_power_mode(scu_base, SCU_PM_NORMAL) here. */
	if (zx_scu_base)
		scu_power_mode(zx_scu_base, SCU_PM_NORMAL);

	/* Release the pen so the next CPU can use it. */
	zx_write_pen_release(-1);
}

static int zx_boot_secondary(unsigned int cpu, struct task_struct *idle)
{
	unsigned long timeout;

	zx_write_pen_release(cpu_logical_map(cpu));

	/*
	 * The vendor kernel raises a GIC wakeup IPI here (bl 0xc000f170)
	 * as well as relying on the event. Do both: the trampoline is a
	 * pure spin, so the IPI is what un-wedges a CPU that is still
	 * sitting in the BootROM's own WFE pen.
	 */
	arch_send_wakeup_ipi_mask(cpumask_of(cpu));
	dsb_sev();

	timeout = jiffies + (1 * HZ);
	while (time_before(jiffies, timeout)) {
		smp_rmb();
		if (zx_pen_release == -1)
			return 0;
		udelay(10);
	}

	pr_err("zx279128: CPU%u failed to come online\n", cpu);
	zx_write_pen_release(-1);
	return -ENOSYS;
}

static void __init zx_smp_prepare_cpus(unsigned int max_cpus)
{
	struct device_node *np;
	void __iomem *iram;
	size_t len;

	/*
	 * SCU base comes from CBAR/PERIPHBASE (mrc p15, 4, rX, c15, c0, 0),
	 * exactly as the vendor kernel does. Do NOT mask it: PERIPHBASE is
	 * already the SCU base (0x00800000 here, corroborated by the GIC
	 * distributor at 0x801000 and CPU interface at 0x800100).
	 */
	zx_scu_base = ioremap(scu_a9_get_base(), SZ_256);
	if (!zx_scu_base) {
		pr_err("zx279128: failed to map SCU\n");
		return;
	}
	scu_enable(zx_scu_base);
	pr_info("zx279128: SCU ctrl %08x, cores %u\n",
		readl_relaxed(zx_scu_base), scu_get_core_count(zx_scu_base));

	np = of_find_compatible_node(NULL, NULL, "zte,zx279128s-smp-sram");
	if (!np) {
		pr_err("zx279128: no zte,zx279128s-smp-sram node, cannot start secondaries\n");
		return;
	}

	iram = of_iomap(np, 0);
	of_node_put(np);
	if (!iram) {
		pr_err("zx279128: failed to map iram\n");
		return;
	}

	len = (size_t)zx_secondary_trampoline_end -
	      (size_t)zx_secondary_trampoline;
	memcpy_toio(iram, zx_secondary_trampoline, len);

	/* Patch words: +4 secondary entry (phys), +8 &pen_release (phys). */
	writel_relaxed(__pa_symbol(secondary_startup), iram + 4);
	/*
	 * zx_pen_release is a data object, not a text symbol: __pa_symbol()
	 * is only valid for kernel *symbols* in the linear text mapping and
	 * carries a debug check that can fire (or silently mis-translate)
	 * for data. Use __pa()/virt_to_phys().
	 */
	writel_relaxed(__pa(&zx_pen_release), iram + 8);

	/*
	 * The IRAM window is an ioremap() mapping - Device memory, uncached -
	 * and the stub and patch words went out through memcpy_toio/writel,
	 * so they are already visible to a CPU running with caches off. A
	 * barrier is all that is required.
	 *
	 * Do NOT call outer_flush_all() here. It faults on this SoC at this
	 * point in boot:
	 *
	 *   PC is at l2c210_flush_all+0x5c/0x60
	 *   LR is at zx_smp_prepare_cpus+0x108/0x11c
	 *
	 * and it is meaningless for a Device mapping in any case. The one
	 * object that DOES live in normal cached memory - zx_pen_release - is
	 * handled separately by zx_write_pen_release(), which uses
	 * sync_cache_w() plus outer_clean_range() on its PHYSICAL address.
	 */
	wmb();

	iounmap(iram);

	/* Wake CPU1 out of the BootROM pen so it starts running our stub. */
	dsb_sev();
}

static const struct smp_operations zx279128_smp_ops __initconst = {
	.smp_prepare_cpus = zx_smp_prepare_cpus,
	.smp_secondary_init = zx_secondary_init,
	.smp_boot_secondary = zx_boot_secondary,
};

CPU_METHOD_OF_DECLARE(zx279128_smp, "zte,zx279128s-smp", &zx279128_smp_ops);
