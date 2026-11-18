// SPDX-License-Identifier: GPL-2.0
/*
 * ZX279128S PCIe bring-up validation.
 *
 * NOT a driver. This runs the reverse-engineered PHY/PCIe bring-up sequence
 * once at late_initcall and then reads a few DesignWare registers, printing
 * before and after every step.
 *
 * Why a test and not the driver: round 102 established that touching the DBI
 * before the PHY block is enabled raises an imprecise external abort that wedges
 * the CPU with no oops and no console output. If any step of the sequence is
 * wrong, the board simply stops. Printing before each step means the last line
 * on the console identifies the offending step exactly, which a full driver
 * would not.
 *
 * Sequence (docs/WIFI.md round 104), from the vendor driver at 0xc0016100:
 *   A = 0x09500000 port-0 glue, B = 0x09400000 shared PHY/PLL,
 *   C = 0x09600000 port-1 glue
 *     A[0x70] |= 0xb5
 *     B[0x08] |= BIT(15), then BIT(13), then BIT(14)
 *     A[0x74] &= ~BIT(0)
 *     C[0x0c] &= ~BIT(14)
 * then poll glue +0xDC bits 17..22 for 0x11 (L0).
 */

#include <linux/bitfield.h>
#include <linux/delay.h>
#include <linux/init.h>
#include <linux/io.h>
#include <linux/kernel.h>
#include <linux/moduleparam.h>
#include <linux/sizes.h>

/* CORRECTED (round 106). The vendor sequence operates on statically-mapped
 * virtual addresses, and the kernel's map_desc table (found at 0xc059ba80)
 * gives their real physical addresses:
 *
 *   virt 0xf0400000 -> phys 0x94000000   (topcrm, clock/reset manager)
 *   virt 0xf0500000 -> phys 0x94100000
 *   virt 0xf0600000 -> phys 0x94200000
 *
 * Round 103 guessed 0x094/095/096 00000 from a numeric pattern; that was wrong,
 * and round 105's test hung on the first access because of it. The sequence is
 * a CLOCK/RESET bring-up in the CRM blocks, which is exactly the missing enable
 * that made every PCIe register access wedge the CPU.
 */
#define ZX_CRM0_BASE	0x94000000	/* topcrm  (was "phy")   */
#define ZX_CRM1_BASE	0x94100000	/* (was "glue0")         */
#define ZX_CRM2_BASE	0x94200000	/* (was "glue1")         */
#define ZX_GLUE0_PHYS	0x09500000	/* real PCIe port-0 glue */

/* GPIO controller (round 107).
 *
 * The stock DT has no gpio node; the vendor driver holds a statically
 * initialised pointer at 0xc05c1aac = virt 0xf0707000, which the map_desc table
 * resolves to phys 0x94407000 - the same lsp0crpm block as the UART (0x94404000)
 * and spifc (0x94406000).
 *
 * Layout, from zx_gpio_set()/zx_gpio_get() at 0xc01996d8/0xc0199660:
 *   bank   = gpio >> 4, each bank 0x40 bytes apart
 *   bit    = gpio & 15
 *   +0x14  input value      +0x18  set output      +0x1c  clear output
 *
 * PERST#: GPIO 53 -> bank 3 bit 5, GPIO 55 -> bank 3 bit 7.
 */
#define ZX_GPIO_PHYS	0x94407000
#define ZX_GPIO_BANK(g)	(((g) >> 4) * 0x40)
#define ZX_GPIO_SET	0x18
#define ZX_GPIO_CLR	0x1c

static void zx_gpio_out(void __iomem *gpio, unsigned int g, int val)
{
	void __iomem *bank = gpio + ZX_GPIO_BANK(g);
	u32 bit = BIT(g & 15);

	if (val)
		writel(readl(bank + ZX_GPIO_SET) | bit, bank + ZX_GPIO_SET);
	else
		writel(readl(bank + ZX_GPIO_CLR) | bit, bank + ZX_GPIO_CLR);
}
#define ZX_DBI0_BASE	0x0f000000	/* DesignWare DBI, port 0 */

#define ZX_GLUE_LTSSM	0xdc
#define ZX_LTSSM_MASK	GENMASK(22, 17)
#define ZX_LTSSM_L0	0x11

static bool zx_pcie_test_enable;
static int __init zx_pcie_test_setup(char *s)
{
	zx_pcie_test_enable = true;
	return 1;
}
__setup("zx_pcie_test", zx_pcie_test_setup);

static int __init zx_pcie_probe_test(void)
{
	void __iomem *phy, *glue0, *glue1, *dbi;
	u32 v;

	/* Opt-in only: this can hang the board if the sequence is wrong, so it
	 * must never run on a normal boot. Enable with zx_pcie_test=1.
	 */
	if (!zx_pcie_test_enable)
		return 0;

	pr_info("zx-pcie-test: START\n");

	phy   = ioremap(ZX_CRM0_BASE, SZ_4K);
	glue0 = ioremap(ZX_CRM1_BASE, SZ_4K);
	glue1 = ioremap(ZX_CRM2_BASE, SZ_4K);
	if (!phy || !glue0 || !glue1) {
		pr_err("zx-pcie-test: ioremap failed\n");
		return 0;
	}
	pr_info("zx-pcie-test: mapped phy/glue0/glue1\n");

	/* Step 1: read glue0+0x70. This is the FIRST access to any of these
	 * blocks - if the console stops here, the glue itself is unclocked and
	 * the whole approach needs a clock enable we have not found.
	 */
	pr_info("zx-pcie-test: step1 reading crm1+0x70...\n");
	v = readl(glue0 + 0x70);
	pr_info("zx-pcie-test: step1 crm1+0x70 = %08x\n", v);
	writel(v | 0xb5, glue0 + 0x70);
	mdelay(1);

	pr_info("zx-pcie-test: step2 phy+0x08 = %08x\n", readl(phy + 0x08));
	writel(readl(phy + 0x08) | BIT(15), phy + 0x08);
	mdelay(1);
	writel(readl(phy + 0x08) | BIT(13), phy + 0x08);
	mdelay(1);
	writel(readl(phy + 0x08) | BIT(14), phy + 0x08);
	mdelay(50);
	pr_info("zx-pcie-test: step2 done, phy+0x08 = %08x\n", readl(phy + 0x08));

	v = readl(glue0 + 0x74);
	writel(v & ~BIT(0), glue0 + 0x74);
	mdelay(1);
	pr_info("zx-pcie-test: step3 glue0+0x74 %08x -> %08x\n",
		v, readl(glue0 + 0x74));

	v = readl(glue1 + 0x0c);
	writel(v & ~BIT(14), glue1 + 0x0c);
	mdelay(500);
	pr_info("zx-pcie-test: step4 glue1+0x0c %08x -> %08x\n",
		v, readl(glue1 + 0x0c));

	/* Now the DBI should be reachable. This is the moment of truth: if the
	 * PHY sequence did not clock the core, this read hangs the CPU.
	 */
	pr_info("zx-pcie-test: step5 mapping DBI and reading...\n");
	dbi = ioremap(ZX_DBI0_BASE, SZ_4K);
	if (dbi) {
		pr_info("zx-pcie-test: DBI+0x00 (vendor/device) = %08x\n",
			readl(dbi + 0x00));
		pr_info("zx-pcie-test: DBI+0x08 (class/rev)     = %08x\n",
			readl(dbi + 0x08));
		pr_info("zx-pcie-test: DBI+0x70 (cap id exp?)   = %08x\n",
			readl(dbi + 0x70));
		pr_info("zx-pcie-test: DBI+0x80 (lnkcap/sta)    = %08x\n",
			readl(dbi + 0x80));
		pr_info("zx-pcie-test: DBI+0x8f8 (version)      = %08x\n",
			readl(dbi + 0x8f8));
		pr_info("zx-pcie-test: DBI+0x900 (atu viewport) = %08x\n",
			readl(dbi + 0x900));
		iounmap(dbi);
	}

	/* Further CRM steps from the vendor sequence (0xc00162c0-0xc0016350). */
	writel(readl(phy + 0x24) & ~BIT(26), phy + 0x24);
	mdelay(50);
	writel(readl(glue0 + 0x74) | BIT(0), glue0 + 0x74);
	mdelay(1);
	writel(readl(glue0 + 0x70) & ~BIT(8), glue0 + 0x70);
	mdelay(1);
	pr_info("zx-pcie-test: extra CRM steps done\n");

	/* Link training start (0xc0016354-0xc00163ac):
	 *   pcie_glue[0x00] |= BIT(5)                  -> LTSSM enable
	 *   DBI[0xa0] = (DBI[0xa0] & ~0xf) | 1         -> LNKCTL2 target speed Gen1
	 *     (cap at 0x70 + PCI_EXP_LNKCTL2 0x30 = 0xa0)
	 */
	{
		void __iomem *pg = ioremap(ZX_GLUE0_PHYS, SZ_4K);
		void __iomem *db = ioremap(ZX_DBI0_BASE, SZ_4K);

		if (pg && db) {
			u32 g = readl(pg + 0x00);

			pr_info("zx-pcie-test: glue[0]=%08x -> set BIT(5)\n", g);
			writel(g | BIT(5), pg + 0x00);
			mdelay(1);
			v = readl(db + 0xa0);
			writel((v & ~0xfu) | 1, db + 0xa0);
			pr_info("zx-pcie-test: DBI[0xa0] %08x -> %08x\n",
				v, readl(db + 0xa0));
		}
		if (pg)
			iounmap(pg);
		if (db)
			iounmap(db);
	}

	/* PERST# toggle, exactly as the vendor probe does it:
	 * gpio 53 low, delay, high, delay; then gpio 55 the same.
	 */
	{
		void __iomem *gpio = ioremap(ZX_GPIO_PHYS, SZ_4K);

		if (gpio) {
			pr_info("zx-pcie-test: toggling PERST# gpio53/55\n");
			zx_gpio_out(gpio, 53, 0);
			mdelay(10);
			zx_gpio_out(gpio, 53, 1);
			mdelay(200);
			zx_gpio_out(gpio, 55, 0);
			mdelay(10);
			zx_gpio_out(gpio, 55, 1);
			mdelay(200);
			iounmap(gpio);
			pr_info("zx-pcie-test: PERST# done\n");
		}
	}

	{
		void __iomem *pglue = ioremap(ZX_GLUE0_PHYS, SZ_4K);

		if (pglue) {
			int i;

			for (i = 0; i < 200; i++) {
				v = readl(pglue + ZX_GLUE_LTSSM);
				if (FIELD_GET(ZX_LTSSM_MASK, v) == ZX_LTSSM_L0)
					break;
				mdelay(5);
			}
			pr_info("zx-pcie-test: LTSSM raw=%08x state=%02lx after %d polls (L0=%02x)\n",
				v, FIELD_GET(ZX_LTSSM_MASK, v), i, ZX_LTSSM_L0);
			iounmap(pglue);
		}
	}

	/* Independent link checks + endpoint identification.
	 *
	 * LTSSM alone is not proof: verify with DEBUG1 (DBI+0x72C) bit4 LINK_UP /
	 * bit29 IN_TRAINING, and with LNKSTA (cap 0x70 + 0x12 -> DBI+0x82) for
	 * negotiated width/speed. Then program a legacy-viewport iATU CFG0 window
	 * and read the endpoint's vendor/device ID at bus 1, dev 0, fn 0.
	 */
	{
		void __iomem *db = ioremap(ZX_DBI0_BASE, SZ_4K);
		void __iomem *cfg;
		u32 dbg1, lnksta, id;

		if (db) {
			dbg1 = readl(db + 0x72c);
			lnksta = readl(db + 0x80);
			pr_info("zx-pcie-test: DEBUG1=%08x link_up=%d in_training=%d\n",
				dbg1, !!(dbg1 & BIT(4)), !!(dbg1 & BIT(29)));
			pr_info("zx-pcie-test: LNKSTA(hi16 of +0x80)=%04x speed=%d width=%d\n",
				lnksta >> 16, (lnksta >> 16) & 0xf,
				((lnksta >> 16) >> 4) & 0x3f);

			/* legacy viewport iATU, outbound window 0, type CFG0 */
			writel(0, db + 0x900);				/* viewport 0 */
			writel(0x1c000000, db + 0x90c);			/* lower base   */
			writel(0, db + 0x910);				/* upper base   */
			writel(0x1c0fffff, db + 0x914);			/* limit        */
			writel(0x01000000, db + 0x918);			/* target: b1 d0 f0 */
			writel(0, db + 0x91c);				/* upper target */
			writel(0x4, db + 0x904);			/* CTRL1 = CFG0 */
			writel(BIT(31), db + 0x908);			/* CTRL2 enable */
			wmb();
			mdelay(10);

			cfg = ioremap(0x1c000000, SZ_4K);
			if (cfg) {
				id = readl(cfg + 0x00);
				pr_info("zx-pcie-test: ENDPOINT bus1.dev0 ID = %08x (vendor %04x device %04x)\n",
					id, id & 0xffff, id >> 16);
				pr_info("zx-pcie-test: ENDPOINT class/rev = %08x  BAR0 = %08x\n",
					readl(cfg + 0x08), readl(cfg + 0x10));
				iounmap(cfg);
			}
			iounmap(db);
		}
	}

	pr_info("zx-pcie-test: DONE\n");
	iounmap(phy);
	iounmap(glue0);
	iounmap(glue1);
	return 0;
}
late_initcall(zx_pcie_probe_test);
