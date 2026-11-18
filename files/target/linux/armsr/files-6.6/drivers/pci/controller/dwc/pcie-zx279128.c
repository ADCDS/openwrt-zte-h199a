// SPDX-License-Identifier: GPL-2.0
/*
 * PCIe host controller driver for the ZTE/Sanechips ZX279128S.
 *
 * The SoC integrates a Synopsys DesignWare PCIe core (pre-v4.70a: the version
 * register at DBI+0x8F8 reads 0, and DBI+0x900 is a real register, so the core
 * uses the legacy iATU viewport rather than the unrolled space).
 *
 * Nothing about this hardware is documented. The bring-up sequence below was
 * recovered by disassembling the vendor kernel's driver and then verified
 * step-by-step on hardware; see docs/WIFI.md rounds 100-108. Every register
 * access here is load-bearing, and the ordering and delays matter:
 *
 *   - Until the CRM sequence has run, ANY access to the DBI or the PCIe glue
 *     raises an imprecise external abort that wedges the CPU with no oops.
 *   - Port-0 clock/reset waits follow the verified vendor kernel: its delay
 *     argument 0x066665b0 represents 1000 us, repeated 50 or 500 times.
 *     Both PERST pulses and both domain sequences precede either bus scan.
 *   - The sequence is NOT idempotent (CRM1+0x74 is cleared and later set), so
 *     it must run exactly once.
 *
 * Verified on an H199A: link trains to Gen1 x1, and the MediaTek MT7613BE
 * endpoint (14c3:7663) enumerates at bus 1 device 0.
 */

#include <linux/bitfield.h>
#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/gpio/consumer.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/of_device.h>
#include <linux/platform_device.h>
#include <linux/reset.h>
#include <linux/resource.h>
#include <linux/sizes.h>
#include <linux/slab.h>
#include <linux/sysfs.h>
#include <linux/types.h>

#include "pcie-designware.h"

/* Clock/reset manager blocks. These are ordinary SoC peripherals, not part of
 * the PCIe core; the vendor reaches them through a static IO mapping. The
 * device tree names them "crm0".."crm2" in reg; these addresses are the
 * fallback for a device tree that does not.
 */
#define ZX_CRM0_PHYS		0x94000000
#define ZX_CRM1_PHYS		0x94100000
#define ZX_CRM2_PHYS		0x94200000
/* GPIO block, used only to drive PERST# when the device tree has no
 * reset-gpios for a port.
 */
#define ZX_GPIO_PHYS		0x94407000

#define ZX_CRM0_CLKEN		0x08	/* BIT(15|13|14) enable the PCIe domain */
#define ZX_CRM0_MISC		0x24	/* BIT(26) cleared during bring-up      */
#define ZX_CRM1_CFG		0x70	/* |= 0xb5, later &= ~BIT(8)            */
#define ZX_CRM1_RST		0x74	/* port-0 bit 0, port-1 bit 3            */
#define  ZX_CRM1_RST_BIT(port)	((port) ? BIT(3) : BIT(0))
#define ZX_CRM2_MUX3		0x0c	/* vendor clears port-0 bit 14 / port-1 bit 1 */
/* SerDes/PLL configuration written by the vendor's port-1 path (disassembled at
 * 0xc00164b0..0xc001651c). Absolute constants, not read-modify-write - the shape
 * of PHY lane/PLL setup. The vendor also uses them on port 0 for product VID1.
 * This board reports VID6; a private opt-in permits a contained comparison.
 *
 * Round 136: these go to the block at [priv+0x14], which the port-0 tail proves
 * is the GLUE base, NOT CRM2 - at 0xc0016374 the same pointer is used for
 * `|= BIT(5)` at offset 0, which is the LTSSM enable we already know lives in
 * glue+0x00. Round 134 wrote them to CRM2 and had no effect.
 */
#define ZX_GLUE_SERDES0		0x1b0	/* = 0x0046c24a on port 1 */
#define ZX_GLUE_SERDES1		0x1b4	/* = 0x00202d5a on port 1 */
#define ZX_SERDES0_VAL		0x0046c24a
#define ZX_SERDES1_VAL		0x00202d5a

/* The SoC's two controllers, told apart by their DBI address. Port N's
 * glue ("app") block is at ZX_APP_PHYS(N).
 */
#define ZX_DBI_PHYS(port)	(0x0f000000 + (port) * 0x100000)
#define ZX_APP_PHYS(port)	(0x09500000 + (port) * 0x100000)

/* Vendor glue, per port. */
#define ZX_GLUE_CTRL		0x00	/* BIT(5) starts LTSSM                  */
#define  ZX_GLUE_LTSSM_EN	BIT(5)
#define ZX_GLUE_LTSSM		0xdc	/* bits 17..22 = LTSSM state            */
#define  ZX_LTSSM_STATE		GENMASK(22, 17)
#define  ZX_LTSSM_L0		0x11

/* PCIe capability sits at config offset 0x70 on this core, so LNKCTL2 (cap+0x30)
 * is at 0xa0. The low nibble is the target link speed; the vendor forces Gen1.
 */
#define ZX_DBI_LNKCTL2		0xa0
#define ZX_DBI_LNKCTL		0x80

/* PERST# lines, used when a port has no reset-gpios. The SoC's GPIO block has
 * 16-pin banks 0x40 bytes apart, with separate set (+0x18) and clear (+0x1c)
 * registers. PERST# is active low.
 */
#define ZX_PERST_GPIO0		53
#define ZX_PERST_GPIO1		55
#define ZX_GPIO_BANK(g)		(((g) >> 4) * 0x40)
#define ZX_GPIO_IN		0x14
#define ZX_GPIO_SET		0x18
#define ZX_GPIO_CLR		0x1c

static bool zx_hold_perst;
module_param_named(hold_perst, zx_hold_perst, bool, 0444);
MODULE_PARM_DESC(hold_perst, "qualification: hold both endpoints in reset through shared clock setup");

struct zx_pcie {
	struct dw_pcie		pci;
	u32			port;		/* 0 or 1 */
	void __iomem		*glue;
	void __iomem		*crm0;
	void __iomem		*crm1;
	void __iomem		*crm2;
	/* PERST#, held only during the shared preparation: the port's
	 * reset-gpios, or, without one, pin perst_pin of the GPIO block.
	 */
	struct gpio_desc	*perst;
	void __iomem		*gpio;
	unsigned int		perst_pin;
	bool			serdes_override;
	/* The port's line in CRM1+0x74, from the node's resets, held only
	 * during the shared preparation. NULL: a device tree without resets,
	 * which falls back to the direct register write.
	 */
	struct reset_control	*rst;
};

#define to_zx_pcie(x)	dev_get_drvdata((x)->dev)

/* PERST# pin state: 1 asserted (low), 0 released, negative on error. */
static int zx_perst_get(struct zx_pcie *zx)
{
	if (zx->perst)
		return gpiod_get_value(zx->perst);
	return !(readl(zx->gpio + ZX_GPIO_BANK(zx->perst_pin) + ZX_GPIO_IN) &
		 BIT(zx->perst_pin & 15));
}

static int zx_perst_set(struct zx_pcie *zx, bool asserted)
{
	int state;

	if (zx->perst) {
		gpiod_set_value(zx->perst, asserted);
	} else {
		void __iomem *bank = zx->gpio + ZX_GPIO_BANK(zx->perst_pin);
		u32 off = asserted ? ZX_GPIO_CLR : ZX_GPIO_SET;
		u32 bit = BIT(zx->perst_pin & 15);

		writel(readl(bank + off) | bit, bank + off);
	}
	/* SET/CLR read zero. Observe the pin, allowing its synchronizer to
	 * settle, before starting the reset interval. Never replay a pulse.
	 */
	return read_poll_timeout_atomic(zx_perst_get, state, state == asserted,
					1, 1000, false, zx);
}

static int zx_pcie_perst(struct zx_pcie *zx)
{
	int ret;

	ret = zx_perst_set(zx, true);
	if (ret)
		return ret;
	mdelay(10);
	ret = zx_perst_set(zx, false);
	if (ret)
		return ret;
	mdelay(200);
	dev_info(zx->pci.dev, "port%u PERST# low/high levels verified\n", zx->port);
	return 0;
}

static void zx_crm_writel(u32 value, void __iomem *reg)
{
	writel(value, reg);
	/* Start settling delays after completion of the posted register write.
	 * Reset bits may self-clear; a readback is not a full equality test.
	 */
	readl(reg);
}

/* The port's CRM1+0x74 line: clear (assert) or set (deassert) its bit. The
 * zte,zx279128s-crm reset provider does exactly the read-modify-write and
 * readback this driver used to do itself, so the register traffic is the
 * same either way.
 */
static void zx_pcie_core_reset(struct zx_pcie *zx, bool assert)
{
	u32 value;

	if (zx->rst) {
		if (assert)
			reset_control_assert(zx->rst);
		else
			reset_control_deassert(zx->rst);
		return;
	}
	value = readl(zx->crm1 + ZX_CRM1_RST);
	if (assert)
		value &= ~ZX_CRM1_RST_BIT(zx->port);
	else
		value |= ZX_CRM1_RST_BIT(zx->port);
	zx_crm_writel(value, zx->crm1 + ZX_CRM1_RST);
}

/* No DBI/glue access is safe until the corresponding domain is enabled. */
static void zx_pcie_domain_enable(struct zx_pcie *zx)
{
	/* The ports use different fields in shared CRM registers. Port 1's
	 * SerDes setup falls between clock bit 27 and clock bits 25/26 in the
	 * verified vendor sequence; it is not a simple mirrored port-0 mask.
	 */
	if (zx->port) {
		/* Own-unit vendor preinit, c0016424..c0016738. The older
		 * mirror-bit substitutions did not match that implementation.
		 */
		zx_crm_writel(readl(zx->crm1 + ZX_CRM1_CFG) | 0x1aa00,
		       zx->crm1 + ZX_CRM1_CFG);
		mdelay(50);
		zx_crm_writel(readl(zx->crm0 + ZX_CRM0_CLKEN) | BIT(27),
		       zx->crm0 + ZX_CRM0_CLKEN);
		mdelay(50);

		writel(ZX_SERDES1_VAL, zx->glue + ZX_GLUE_SERDES1);
		writel(ZX_SERDES0_VAL, zx->glue + ZX_GLUE_SERDES0);
		zx_crm_writel(readl(zx->crm0 + ZX_CRM0_CLKEN) | BIT(25),
		       zx->crm0 + ZX_CRM0_CLKEN);
		mdelay(50);
		zx_crm_writel(readl(zx->crm0 + ZX_CRM0_CLKEN) | BIT(26),
		       zx->crm0 + ZX_CRM0_CLKEN);
		mdelay(50);

		zx_pcie_core_reset(zx, true);
		mdelay(50);
		zx_crm_writel(readl(zx->crm2 + ZX_CRM2_MUX3) & ~BIT(1),
		       zx->crm2 + ZX_CRM2_MUX3);
		mdelay(50);
		zx_crm_writel(readl(zx->crm0 + ZX_CRM0_MISC) & ~BIT(26),
		       zx->crm0 + ZX_CRM0_MISC);
		mdelay(50);
		zx_pcie_core_reset(zx, false);
		zx_crm_writel(readl(zx->crm1 + ZX_CRM1_CFG) & ~BIT(17),
		       zx->crm1 + ZX_CRM1_CFG);

		dev_info(zx->pci.dev,
			 "port1 CRM before link: clken=%08x misc=%08x cfg=%08x rst=%08x mux3=%08x\n",
			 readl(zx->crm0 + ZX_CRM0_CLKEN),
			 readl(zx->crm0 + ZX_CRM0_MISC),
			 readl(zx->crm1 + ZX_CRM1_CFG),
			 readl(zx->crm1 + ZX_CRM1_RST),
			 readl(zx->crm2 + ZX_CRM2_MUX3));
		return;
	}

	zx_crm_writel(readl(zx->crm1 + ZX_CRM1_CFG) | 0xb5, zx->crm1 + ZX_CRM1_CFG);
	mdelay(50);

	zx_crm_writel(readl(zx->crm0 + ZX_CRM0_CLKEN) | BIT(15), zx->crm0 + ZX_CRM0_CLKEN);
	mdelay(50);
	/* Exact optional vendor VID1 path, c0016808..c0016868. Never enabled
	 * by the release tree for the bench unit's VID6 hardware.
	 */
	if (zx->serdes_override) {
		writel(ZX_SERDES1_VAL, zx->glue + ZX_GLUE_SERDES1);
		writel(ZX_SERDES0_VAL, zx->glue + ZX_GLUE_SERDES0);
	}
	zx_crm_writel(readl(zx->crm0 + ZX_CRM0_CLKEN) | BIT(13), zx->crm0 + ZX_CRM0_CLKEN);
	mdelay(50);
	zx_crm_writel(readl(zx->crm0 + ZX_CRM0_CLKEN) | BIT(14), zx->crm0 + ZX_CRM0_CLKEN);
	mdelay(50);

	zx_pcie_core_reset(zx, true);
	mdelay(50);

	zx_crm_writel(readl(zx->crm2 + ZX_CRM2_MUX3) & ~BIT(14), zx->crm2 + ZX_CRM2_MUX3);
	mdelay(500);

	/* Second phase, after the core is reachable. */
	zx_crm_writel(readl(zx->crm0 + ZX_CRM0_MISC) & ~BIT(26), zx->crm0 + ZX_CRM0_MISC);
	mdelay(50);
	zx_pcie_core_reset(zx, false);
	mdelay(1);
	zx_crm_writel(readl(zx->crm1 + ZX_CRM1_CFG) & ~BIT(8), zx->crm1 + ZX_CRM1_CFG);
	mdelay(1);
}

static int zx_pcie_link_up(struct dw_pcie *pci)
{
	struct zx_pcie *zx = to_zx_pcie(pci);
	u32 val = readl(zx->glue + ZX_GLUE_LTSSM);

	return FIELD_GET(ZX_LTSSM_STATE, val) == ZX_LTSSM_L0;
}

static void zx_pcie_train(struct zx_pcie *zx)
{
	struct dw_pcie *pci = &zx->pci;
	u32 val;
	u16 ctrl;

	/* Vendor order: LTSSM enable, Gen1 target, then retraining. */
	writel(readl(zx->glue + ZX_GLUE_CTRL) | ZX_GLUE_LTSSM_EN,
	       zx->glue + ZX_GLUE_CTRL);
	val = dw_pcie_readl_dbi(pci, ZX_DBI_LNKCTL2);
	dw_pcie_writel_dbi(pci, ZX_DBI_LNKCTL2, (val & ~0xfu) | 1);
	ctrl = dw_pcie_readw_dbi(pci, ZX_DBI_LNKCTL);
	dw_pcie_writew_dbi(pci, ZX_DBI_LNKCTL, ctrl | PCI_EXP_LNKCTL_RL);
}

static int zx_pcie_wait_l0(struct zx_pcie *zx)
{
	u32 val = 0;
	int i;

	/* The stock loop waits one millisecond before each of at most 2000
	 * reads. Endpoint availability is separate from shared initialization.
	 */
	for (i = 0; i < 2000; i++) {
		mdelay(1);
		val = readl(zx->glue + ZX_GLUE_LTSSM);
		if (FIELD_GET(ZX_LTSSM_STATE, val) == ZX_LTSSM_L0)
			return 0;
	}
	dev_err(zx->pci.dev, "port%u link timeout, LTSSM=%08x\n", zx->port, val);
	return -ETIMEDOUT;
}

static int zx_pcie_prepare_held_perst(struct zx_pcie *pair)
{
	int i, ret;
	u32 value;

	for (i = 0; i < 2; i++) {
		ret = zx_perst_set(&pair[i], true);
		if (ret)
			return ret;
	}
	mdelay(10);
	for (i = 0; i < 2; i++) {
		zx_pcie_domain_enable(&pair[i]);
		/* This port is now accessible. Use its temporary glue mapping
		 * directly; pci.dev belongs to the common preparation owner.
		 */
		value = readl(pair[i].glue + ZX_GLUE_CTRL);
		writel(value & ~ZX_GLUE_LTSSM_EN, pair[i].glue + ZX_GLUE_CTRL);
		if (readl(pair[i].glue + ZX_GLUE_CTRL) & ZX_GLUE_LTSSM_EN)
			return -EIO;
	}
	writel(0x3f, pair[0].crm1 + ZX_CRM1_RST);
	dev_info(pair[0].pci.dev, "held-PERST final shared reset readback=%08x\n",
		 readl(pair[0].crm1 + ZX_CRM1_RST));
	for (i = 0; i < 2; i++) {
		if (zx_perst_get(&pair[i]) != 1)
			return -EIO;
		/* Shared reset can restore controller defaults. Keep training off
		 * until the endpoints have been released with stable clocks.
		 */
		value = readl(pair[i].glue + ZX_GLUE_CTRL);
		writel(value & ~ZX_GLUE_LTSSM_EN, pair[i].glue + ZX_GLUE_CTRL);
		if (readl(pair[i].glue + ZX_GLUE_CTRL) & ZX_GLUE_LTSSM_EN)
			return -EIO;
	}
	/* A conservative settling interval, not a measurement of REFCLK lock. */
	mdelay(100);
	for (i = 0; i < 2; i++) {
		ret = zx_perst_set(&pair[i], false);
		if (ret)
			return ret;
	}
	mdelay(200);
	for (i = 0; i < 2; i++)
		zx_pcie_train(&pair[i]);
	dev_info(pair[0].pci.dev, "PERST held through both domains; releases verified before training\n");
	return 0;
}

static int zx_pcie_start_link(struct dw_pcie *pci)
{
	/* Both domains and PERST lines are already prepared. Never reset the
	 * shared fabric here: the peer may already have published its bus.
	 */
	zx_pcie_train(to_zx_pcie(pci));

	return 0;
}

static void zx_pcie_stop_link(struct dw_pcie *pci)
{
	struct zx_pcie *zx = to_zx_pcie(pci);

	writel(readl(zx->glue + ZX_GLUE_CTRL) & ~ZX_GLUE_LTSSM_EN,
	       zx->glue + ZX_GLUE_CTRL);
}

static const struct dw_pcie_ops zx_dw_pcie_ops = {
	.link_up	= zx_pcie_link_up,
	.start_link	= zx_pcie_start_link,
	.stop_link	= zx_pcie_stop_link,
};

static int zx_pcie_host_init(struct dw_pcie_rp *pp)
{
	return 0;
}

/*
 * This controller has no MSI receiver wired up, and the endpoints we care about
 * (mt76) work happily over legacy INTx. Providing this callback stops
 * dw_pcie_host_init() from calling dw_pcie_msi_host_init(), which would look for
 * an "msi" interrupt in DT and fail the whole probe with -ENXIO.
 *
 * INTx itself needs no code here: in 6.6 the DesignWare host layer builds no
 * legacy IRQ domain at all - the PCI core resolves INTx from the DT
 * interrupt-map via of_irq_parse_and_map_pci().
 */
static int zx_pcie_msi_host_init(struct dw_pcie_rp *pp)
{
	return 0;
}

static const struct dw_pcie_host_ops zx_pcie_host_ops = {
	.host_init	= zx_pcie_host_init,
	.msi_host_init	= zx_pcie_msi_host_init,
};

/* Fixed, read-only observations after shared preparation. In particular, keep
 * root-controller state separate from an endpoint firmware failure report.
 */
static ssize_t link_snapshot_show(struct device *dev, struct device_attribute *attr,
				 char *buf)
{
	struct zx_pcie *zx = dev_get_drvdata(dev);
	u32 value;
	unsigned int offset;
	int at;

	at = sysfs_emit(buf, "port=%u clken=%08x misc=%08x cfg=%08x rst=%08x mux3=%08x\n",
		zx->port, readl(zx->crm0 + ZX_CRM0_CLKEN),
		readl(zx->crm0 + ZX_CRM0_MISC), readl(zx->crm1 + ZX_CRM1_CFG),
		readl(zx->crm1 + ZX_CRM1_RST), readl(zx->crm2 + ZX_CRM2_MUX3));
	value = readl(zx->glue + ZX_GLUE_LTSSM);
	at += sysfs_emit_at(buf, at, "ctrl=%08x ltssm=%08x state=%02x serdes0=%08x serdes1=%08x\n",
		readl(zx->glue + ZX_GLUE_CTRL), value,
		(unsigned int)FIELD_GET(ZX_LTSSM_STATE, value),
		readl(zx->glue + ZX_GLUE_SERDES0), readl(zx->glue + ZX_GLUE_SERDES1));
	for (offset = 0; offset < 0x40; offset += 4)
		at += sysfs_emit_at(buf, at, "dbi%02x=%08x\n", offset,
			dw_pcie_readl_dbi(&zx->pci, offset));
	at += sysfs_emit_at(buf, at, "dbi80=%08x dbia0=%08x\n",
		dw_pcie_readl_dbi(&zx->pci, ZX_DBI_LNKCTL),
		dw_pcie_readl_dbi(&zx->pci, ZX_DBI_LNKCTL2));
	return at;
}
static DEVICE_ATTR_RO(link_snapshot);

static struct attribute *zx_pcie_attrs[] = {
	&dev_attr_link_snapshot.attr,
	NULL,
};

static const struct attribute_group zx_pcie_group = {
	.attrs = zx_pcie_attrs,
};

static DEFINE_MUTEX(zx_prepare_lock);
static enum {
	ZX_PREPARE_NEW,
	ZX_PREPARE_READY,
	ZX_PREPARE_FAILED,
} zx_prepare_state;
static int zx_prepare_error;

static void __iomem *zx_map_named(struct device_node *np, const char *name,
				 resource_size_t expected, resource_size_t size)
{
	struct resource res;
	int index;

	index = of_property_match_string(np, "reg-names", name);
	if (index < 0 || of_address_to_resource(np, index, &res) ||
	    res.start != expected || resource_size(&res) < size)
		return ERR_PTR(-EINVAL);

	/* Temporary mappings only: do not reserve the peer's resources against
	 * this device or retain pointers owned by its devres after probe.
	 */
	return of_iomap(np, index) ?: ERR_PTR(-ENOMEM);
}

/* Port index of a controller node: 0 or 1 from its dbi address, or -EINVAL.
 * A zte,pcie-port property (deprecated) is still accepted but must name the
 * same port; *legacy reports whether the node has one.
 */
static int zx_pcie_port_of(struct device_node *np, bool *legacy)
{
	struct resource res;
	unsigned int port;
	int index;
	u32 val;

	*legacy = of_property_present(np, "zte,pcie-port");
	index = of_property_match_string(np, "reg-names", "dbi");
	if (index < 0 || of_address_to_resource(np, index, &res))
		return -EINVAL;
	if (res.start == ZX_DBI_PHYS(0))
		port = 0;
	else if (res.start == ZX_DBI_PHYS(1))
		port = 1;
	else
		return -EINVAL;
	if (*legacy && (of_property_read_u32(np, "zte,pcie-port", &val) || val != port))
		return -EINVAL;
	return port;
}

/* Take the port's PERST# from reset-gpios. Without one, fall back to the fixed
 * pin through a temporary mapping of the GPIO block, as before reset-gpios was
 * described. GPIOD_ASIS: the line keeps its inherited direction and level until
 * the first pulse. Both are released again once preparation ends.
 */
static int zx_pcie_get_perst(struct zx_pcie *zx, struct device_node *np)
{
	struct gpio_desc *desc;

	desc = fwnode_gpiod_get_index(of_fwnode_handle(np), "reset", 0,
				      GPIOD_ASIS, "PERST#");
	if (!IS_ERR(desc)) {
		zx->perst = desc;
		return 0;
	}
	if (PTR_ERR(desc) != -ENOENT)
		return PTR_ERR(desc);

	zx->perst_pin = zx->port ? ZX_PERST_GPIO1 : ZX_PERST_GPIO0;
	zx->gpio = ioremap(ZX_GPIO_PHYS, SZ_4K);
	if (!zx->gpio)
		return -ENOMEM;
	dev_info(zx->pci.dev, "port%u: no reset-gpios, driving built-in PERST# GPIO%u\n",
		 zx->port, zx->perst_pin);
	return 0;
}

static int zx_pcie_prepare_pair(struct zx_pcie *owner)
{
	struct device *dev = owner->pci.dev;
	struct device_node *np;
	struct zx_pcie *pair;
	u32 port, seen = 0, missing = 0;
	int i, ret = 0;
	bool legacy, hold_perst = zx_hold_perst;

	mutex_lock(&zx_prepare_lock);
	if (zx_prepare_state != ZX_PREPARE_NEW) {
		ret = zx_prepare_error;
		goto unlock;
	}

	pair = kcalloc(2, sizeof(*pair), GFP_KERNEL);
	if (!pair) {
		ret = -ENOMEM;
		goto unlock;
	}

	/* This SoC has one fixed two-controller fabric. Validate and map both
	 * enabled nodes before the first register write. Future support for
	 * independently disabled ports needs an explicit shared-resource owner.
	 */
	for_each_compatible_node(np, NULL, "zte,zx279128s-pcie") {
		void __iomem *p;

		if (!of_device_is_available(np))
			continue;
		/* Private qualification control, absent from release trees. */
		hold_perst |= of_property_read_bool(np, "zte,hold-perst");
		ret = zx_pcie_port_of(np, &legacy);
		if (ret < 0 || (seen & BIT(ret))) {
			ret = -EINVAL;
			goto put_node;
		}
		port = ret;
		seen |= BIT(port);
		pair[port].port = port;
		pair[port].serdes_override = !port &&
			of_property_read_bool(np, "zte,port0-serdes-init");
		pair[port].pci.dev = dev;
		pair[port].crm0 = owner->crm0;
		pair[port].crm1 = owner->crm1;
		pair[port].crm2 = owner->crm2;
		p = zx_map_named(np, "dbi", ZX_DBI_PHYS(port), SZ_16K);
		if (IS_ERR(p)) {
			ret = PTR_ERR(p);
			goto put_node;
		}
		pair[port].pci.dbi_base = p;
		p = zx_map_named(np, "app", ZX_APP_PHYS(port), SZ_4K);
		if (IS_ERR(p)) {
			ret = PTR_ERR(p);
			goto put_node;
		}
		pair[port].glue = p;
		ret = zx_pcie_get_perst(&pair[port], np);
		if (ret)
			goto put_node;
		/* Resolve the reset line before any mutation, so a provider
		 * that has not probed yet defers with nothing changed.
		 */
		pair[port].rst = of_reset_control_get_optional_exclusive(np, NULL);
		if (IS_ERR(pair[port].rst)) {
			ret = PTR_ERR(pair[port].rst);
			pair[port].rst = NULL;
			goto put_node;
		}
	}
	if (seen != (BIT(0) | BIT(1))) {
		ret = -EINVAL;
		goto unmap;
	}

	/* Once mutation begins, failure is permanent for this boot. A second
	 * probe must never replay shared resets after either host is visible.
	 */
	zx_prepare_state = ZX_PREPARE_FAILED;
	zx_prepare_error = -EIO;
	dev_info(dev, "preparing both PCIe ports before bus discovery\n");
	if (hold_perst) {
		ret = zx_pcie_prepare_held_perst(pair);
		if (ret) {
			zx_prepare_error = ret;
			dev_err(dev, "held-PERST preparation failed\n");
			goto unmap;
		}
		goto check_links;
	}
	ret = zx_pcie_perst(&pair[0]);
	if (!ret)
		ret = zx_pcie_perst(&pair[1]);
	if (ret) {
		zx_prepare_error = ret;
		dev_err(dev, "PERST pin level did not follow the requested edge\n");
		goto unmap;
	}
	for (i = 0; i < 2; i++) {
		zx_pcie_domain_enable(&pair[i]);
		zx_pcie_train(&pair[i]);
		if (i == 1) {
			/* Exact vendor tail command, before port 1's L0 wait.
			 * Deliberately NOT a reset_control call: it is a blind
			 * whole-register write (bits 6..31 to 0, bits 0..5 to 1)
			 * covering bits 1, 2, 4 and 5, which are not identified.
			 * Reads back 0x1b, the value it replaces, but bits 2 and
			 * 5 may be write-only, so it is kept as the vendor has it.
			 */
			writel(0x3f, owner->crm1 + ZX_CRM1_RST);
			dev_info(dev, "final shared reset readback=%08x\n",
				 readl(owner->crm1 + ZX_CRM1_RST));
		}
		zx_pcie_wait_l0(&pair[i]);
	}
	/* Recheck port 0 after port 1's shared writes. Neither bus has been
	 * scanned and no endpoint driver can yet be accessing this fabric.
	 */
check_links:
	for (i = 0; i < 2; i++) {
		if (zx_pcie_wait_l0(&pair[i]))
			missing |= BIT(i);
	}
	/* All shared writes are complete. A missing endpoint must not disable
	 * the healthy peer. DWC gates child configuration access on link_up
	 * and its later retraining never repeats our GPIO/shared reset writes.
	 */
	ret = 0;
	zx_prepare_error = 0;
	zx_prepare_state = ZX_PREPARE_READY;
	if (missing)
		dev_warn(dev, "shared preparation complete; initial missing-link mask=%#x\n", missing);
	else
		dev_info(dev, "shared preparation complete; both links initially up\n");
	goto unmap;

put_node:
	of_node_put(np);
unmap:
	for (i = 0; i < 2; i++) {
		if (pair[i].glue)
			iounmap(pair[i].glue);
		if (pair[i].pci.dbi_base)
			iounmap(pair[i].pci.dbi_base);
		if (pair[i].gpio)
			iounmap(pair[i].gpio);
		if (pair[i].perst)
			gpiod_put(pair[i].perst);
		reset_control_put(pair[i].rst);
	}
	kfree(pair);
unlock:
	mutex_unlock(&zx_prepare_lock);
	return ret;
}

static void __iomem *zx_map(struct device *dev, phys_addr_t base)
{
	void __iomem *p = devm_ioremap(dev, base, SZ_4K);

	if (!p)
		dev_err(dev, "failed to map %pa\n", &base);
	return p;
}

/* The CRM blocks are shared by both ports and by other drivers (reboot,
 * SPI clocks), so they are mapped without claiming the regions.
 */
static int zx_pcie_map_crm(struct platform_device *pdev, struct zx_pcie *zx)
{
	static const struct {
		const char *name;
		phys_addr_t fallback;
	} blocks[] = {
		{ "crm0", ZX_CRM0_PHYS },
		{ "crm1", ZX_CRM1_PHYS },
		{ "crm2", ZX_CRM2_PHYS },
	};
	void __iomem **maps[] = { &zx->crm0, &zx->crm1, &zx->crm2 };
	struct device *dev = &pdev->dev;
	bool fallback = false;
	int i;

	for (i = 0; i < ARRAY_SIZE(blocks); i++) {
		struct resource *res;
		phys_addr_t base;

		res = platform_get_resource_byname(pdev, IORESOURCE_MEM,
						   blocks[i].name);
		if (!res) {
			base = blocks[i].fallback;
			fallback = true;
		} else if (resource_size(res) < SZ_4K) {
			return dev_err_probe(dev, -EINVAL, "'%s' reg region too small\n",
					     blocks[i].name);
		} else {
			base = res->start;
		}
		*maps[i] = zx_map(dev, base);
		if (!*maps[i])
			return -ENOMEM;
	}
	if (fallback)
		dev_info(dev, "reg-names lacks crm0/crm1/crm2; using built-in CRM addresses\n");
	return 0;
}

static int zx_pcie_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct zx_pcie *zx;
	struct dw_pcie *pci;
	struct resource *res;
	bool legacy;
	int ret;

	zx = devm_kzalloc(dev, sizeof(*zx), GFP_KERNEL);
	if (!zx)
		return -ENOMEM;

	pci = &zx->pci;
	pci->dev = dev;
	pci->ops = &zx_dw_pcie_ops;
	pci->pp.ops = &zx_pcie_host_ops;

	ret = zx_pcie_port_of(dev->of_node, &legacy);
	if (ret < 0)
		return dev_err_probe(dev, ret, "invalid PCIe port\n");
	zx->port = ret;
	if (legacy)
		dev_warn(dev, "zte,pcie-port is deprecated; the port follows from the dbi address\n");
	platform_set_drvdata(pdev, zx);

	res = platform_get_resource_byname(pdev, IORESOURCE_MEM, "app");
	if (!res)
		return dev_err_probe(dev, -EINVAL, "missing 'app' reg region\n");
	zx->glue = devm_ioremap_resource(dev, res);
	if (IS_ERR(zx->glue))
		return PTR_ERR(zx->glue);

	ret = zx_pcie_map_crm(pdev, zx);
	if (ret)
		return ret;

	ret = zx_pcie_prepare_pair(zx);
	if (ret)
		return dev_err_probe(dev, ret, "shared PCIe preparation failed\n");
	ret = devm_device_add_group(dev, &zx_pcie_group);
	if (ret)
		return dev_err_probe(dev, ret, "cannot publish PCIe link observations\n");

	ret = dw_pcie_host_init(&pci->pp);
	if (ret)
		return dev_err_probe(dev, ret, "failed to initialise host\n");

	return 0;
}

static const struct of_device_id zx_pcie_of_match[] = {
	{ .compatible = "zte,zx279128s-pcie" },
	{},
};

static struct platform_driver zx_pcie_driver = {
	.probe	= zx_pcie_probe,
	.driver	= {
		.name			= "zx279128-pcie",
		.of_match_table		= zx_pcie_of_match,
		.suppress_bind_attrs	= true,
	},
};
builtin_platform_driver(zx_pcie_driver);
