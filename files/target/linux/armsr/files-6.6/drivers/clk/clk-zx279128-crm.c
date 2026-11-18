// SPDX-License-Identifier: GPL-2.0-only
/*
 * ZTE ZX279128S clock/reset manager (CRM).
 *
 * The SoC spreads its clock and reset controls over several CRM blocks:
 * TOPCRM (0x94000000), CRM1 (0x94100000), CRM2 (0x94200000), LSP0CRPM
 * (0x94400000) and LSP1CRPM (0x9a100000). Nothing about them is documented.
 * Every field modelled here is an entry of the stock kernel's own clock
 * tables (zx279127_{top,lsp0,lsp1}_clocks_init, decoded from the stock
 * vmlinux), restricted to the ones a node in this port's device tree uses.
 * Everything else (PLLs, source muxes, the other gates, CRM2) stays exactly
 * as the boot firmware left it and is not touched.
 *
 * Clocks (one-cell specifier, include/dt-bindings/clock/zte,zx279128s-crm.h):
 *
 *   lsp0-wclk  gate TOPCRM+0x14 bit 13, parent clocks[0] (LSP0 100 MHz)
 *   lsp0-pclk  gate TOPCRM+0x14 bit 11, parent clocks[1] (APB 125 MHz)
 *   spi-div    divider LSP0CRPM+0x18 [16:11], divisor = field + 1
 *   spi-wclk   gate LSP0CRPM+0x18 bit 1, parent spi-div
 *   spi-pclk   gate LSP0CRPM+0x18 bit 0, parent lsp0-pclk
 *   lsp1-wclk  gate TOPCRM+0x14 bit 7, parent clocks[0] (100 MHz)
 *   lsp1-pclk  gate TOPCRM+0x14 bit 5, parent clocks[1] (APB)
 *   mdio-div   divider LSP1CRPM+0x04 [17:11], divisor = field + 1
 *   mdio-wclk  gate LSP1CRPM+0x04 bit 1, parent mdio-div
 *   mdio-pclk  gate LSP1CRPM+0x04 bit 0, parent lsp1-pclk
 *   gpio-pclk  gate LSP0CRPM+0x1c bit 0, parent lsp0-pclk
 *
 * The stock tables give lsp0-wclk and lsp1-wclk the same parent (clk_100m)
 * and lsp0-pclk and lsp1-pclk the same parent (matrix_pclk), so the two
 * "clocks" inputs serve both LSP blocks.
 *
 * These are the parents, registers, bits and divider parameters of the
 * single-register zte,zx279128s-spi-clocks driver this one replaces, so the
 * SPI flash controller (which the board boots from) sees the same rates
 * from the same parents. The one difference is that spi-wclk and spi-pclk
 * are now CLK_IS_CRITICAL too (they were flags 0).
 *
 * Resets (one-cell specifier, include/dt-bindings/reset/zte,zx279128s-crm.h):
 * CRM1+0x74 bit 0 (PCIe port 0) and bit 3 (PCIe port 1), active low: a
 * clear bit holds the controller in reset. The other bits of the register
 * are unidentified and are not exposed.
 *
 * Safety: every gate here is on when Linux starts, and gating some of them
 * hangs the board (an access to an unclocked block raises an imprecise
 * abort with no oops). So every gate is CLK_IS_CRITICAL; nothing can turn
 * one off, including clk_disable_unused. The register windows are mapped but
 * not claimed: TOPCRM is shared with the reboot node (TOPCRM+0x44, which
 * claims its word) and the PCIe driver maps TOPCRM, CRM1 and CRM2 too.
 * Probe writes nothing except what the framework does to enable the
 * critical gates, a read-modify-write that sets a bit already set.
 */
#include <linux/clk-provider.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/reset-controller.h>
#include <linux/sizes.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <dt-bindings/clock/zte,zx279128s-crm.h>
#include <dt-bindings/reset/zte,zx279128s-crm.h>

#define ZX_CRM_NR_CLKS			9
#define ZX_CRM_NR_RESETS		2

/* TOPCRM: gates of the shared LSP0 clock parents */
#define ZX_TOPCRM_LSP0_GATE		0x14
#define ZX_TOPCRM_LSP0_WCLK_BIT		13
#define ZX_TOPCRM_LSP0_PCLK_BIT		11
#define ZX_TOPCRM_LSP1_WCLK_BIT		7
#define ZX_TOPCRM_LSP1_PCLK_BIT		5

/* LSP0CRPM: SPI flash controller divider and gates */
#define ZX_LSP0_SPI			0x18
#define ZX_LSP0_SPI_DIV_SHIFT		11
#define ZX_LSP0_SPI_DIV_WIDTH		6
#define ZX_LSP0_SPI_WCLK_BIT		1
#define ZX_LSP0_SPI_PCLK_BIT		0

/* LSP0CRPM: GPIO controller register clock */
#define ZX_LSP0_GPIO			0x1c
#define ZX_LSP0_GPIO_PCLK_BIT		0

/* LSP1CRPM: MDIO controller divider and gates (stock fb_mdio_wclk_div,
 * fb_mdio_wclk, fb_mdio_pclk). Stock divider flags are zero (divisor =
 * field + 1). The MDIO driver does not use the rate; the divider is modelled
 * so the rate is reported, never changed.
 */
#define ZX_LSP1_MDIO			0x04
#define ZX_LSP1_MDIO_DIV_SHIFT		11
#define ZX_LSP1_MDIO_DIV_WIDTH		7
#define ZX_LSP1_MDIO_WCLK_BIT		1
#define ZX_LSP1_MDIO_PCLK_BIT		0

/* Stock divider flags are zero: divisor is field + 1, not 2^field. The
 * bootloader's field 1 gives a 50 MHz working clock from 100 MHz. Read the
 * field every time, and refuse a rate change while the SPI clock runs.
 */
#define ZX_LSP0_SPI_DIV_FLAGS		(CLK_GET_RATE_NOCACHE | CLK_SET_RATE_GATE)
#define ZX_LSP0_SPI_DIVIDER_FLAGS	0
/* The MDIO divider is read-only: nothing in this port sets the MDC rate,
 * so the clock core cannot write the field at all.
 */
#define ZX_LSP1_MDIO_DIV_FLAGS		CLK_GET_RATE_NOCACHE
#define ZX_LSP1_MDIO_DIVIDER_FLAGS	CLK_DIVIDER_READ_ONLY

/* Every gate is on at boot; see the header comment. */
#define ZX_CRM_GATE_FLAGS		CLK_IS_CRITICAL

/* CRM1: reset register, bit per reset line */
#define ZX_CRM1_RST			0x74

static const u8 zx_crm_reset_bits[ZX_CRM_NR_RESETS] = {
	[ZX_CRM_RST_PCIE0] = 0,
	[ZX_CRM_RST_PCIE1] = 3,
};

struct zx_crm {
	struct device *dev;
	spinlock_t lock;
	void __iomem *topcrm;
	void __iomem *crm1;
	void __iomem *lsp0;
	void __iomem *lsp1;
	struct reset_controller_dev rcdev;
	struct clk_hw_onecell_data *data;
};

static const struct clk_parent_data zx_crm_parent_data[] = {
	{ .index = 0 }, /* inherited LSP0 100 MHz working-clock reference */
	{ .index = 1 }, /* inherited matrix peripheral-clock reference */
};

static struct zx_crm *to_zx_crm(struct reset_controller_dev *rcdev)
{
	return container_of(rcdev, struct zx_crm, rcdev);
}

static void zx_crm_reset_update(struct zx_crm *crm, unsigned long id, bool set)
{
	void __iomem *reg = crm->crm1 + ZX_CRM1_RST;
	unsigned long flags;
	u32 value;

	spin_lock_irqsave(&crm->lock, flags);
	value = readl(reg);
	if (set)
		value |= BIT(zx_crm_reset_bits[id]);
	else
		value &= ~BIT(zx_crm_reset_bits[id]);
	writel(value, reg);
	/* Complete the posted write before the caller starts its delay. */
	readl(reg);
	spin_unlock_irqrestore(&crm->lock, flags);
}

static int zx_crm_reset_assert(struct reset_controller_dev *rcdev,
			       unsigned long id)
{
	zx_crm_reset_update(to_zx_crm(rcdev), id, false);
	return 0;
}

static int zx_crm_reset_deassert(struct reset_controller_dev *rcdev,
				 unsigned long id)
{
	zx_crm_reset_update(to_zx_crm(rcdev), id, true);
	return 0;
}

static int zx_crm_reset_status(struct reset_controller_dev *rcdev,
			       unsigned long id)
{
	struct zx_crm *crm = to_zx_crm(rcdev);

	return !(readl(crm->crm1 + ZX_CRM1_RST) & BIT(zx_crm_reset_bits[id]));
}

static const struct reset_control_ops zx_crm_reset_ops = {
	.assert = zx_crm_reset_assert,
	.deassert = zx_crm_reset_deassert,
	.status = zx_crm_reset_status,
};

/* Map one window without claiming it; other drivers share these blocks. */
static void __iomem *zx_crm_map(struct platform_device *pdev, const char *name)
{
	struct resource *res;
	void __iomem *base;

	res = platform_get_resource_byname(pdev, IORESOURCE_MEM, name);
	if (!res)
		return IOMEM_ERR_PTR(-EINVAL);
	if (resource_size(res) < SZ_4K)
		return IOMEM_ERR_PTR(-EINVAL);
	base = devm_ioremap(&pdev->dev, res->start, resource_size(res));
	return base ? base : IOMEM_ERR_PTR(-ENOMEM);
}

/* Every gate is registered critical, under the one CRM lock, and named
 * "<device>.<name>" as the replaced zte,zx279128s-spi-clocks driver did.
 */
static const char *zx_crm_name(struct zx_crm *crm, const char *name)
{
	return devm_kasprintf(crm->dev, GFP_KERNEL, "%s.%s", dev_name(crm->dev),
			      name);
}

static struct clk_hw *zx_crm_gate_pd(struct zx_crm *crm, const char *name,
				     const struct clk_parent_data *parent,
				     void __iomem *reg, u8 bit)
{
	const char *full = zx_crm_name(crm, name);

	if (!full)
		return ERR_PTR(-ENOMEM);
	return devm_clk_hw_register_gate_parent_data(crm->dev, full, parent,
						     ZX_CRM_GATE_FLAGS, reg,
						     bit, 0, &crm->lock);
}

static struct clk_hw *zx_crm_gate_hw(struct zx_crm *crm, const char *name,
				     struct clk_hw *parent, void __iomem *reg,
				     u8 bit)
{
	const char *full = zx_crm_name(crm, name);

	if (!full)
		return ERR_PTR(-ENOMEM);
	/* 6.6 has no devm_clk_hw_register_gate_parent_hw() wrapper. */
	return __devm_clk_hw_register_gate(crm->dev, NULL, full, NULL, parent,
					   NULL, ZX_CRM_GATE_FLAGS, reg, bit, 0,
					   &crm->lock);
}

static struct clk_hw *zx_crm_divider(struct zx_crm *crm, const char *name,
				     struct clk_hw *parent, unsigned long flags,
				     void __iomem *reg, u8 shift, u8 width,
				     u8 divider_flags)
{
	const char *full = zx_crm_name(crm, name);

	if (!full)
		return ERR_PTR(-ENOMEM);
	return devm_clk_hw_register_divider_parent_hw(crm->dev, full, parent,
						      flags, reg, shift, width,
						      divider_flags, &crm->lock);
}

static int zx_crm_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct zx_crm *crm;
	struct clk_hw *wparent, *pparent, *divider, *wclk, *pclk, *gpio;
	struct clk_hw *l1wparent, *l1pparent, *mdiv, *mwclk, *mpclk;
	int ret;

	crm = devm_kzalloc(dev, sizeof(*crm), GFP_KERNEL);
	if (!crm)
		return -ENOMEM;
	spin_lock_init(&crm->lock);
	crm->dev = dev;
	crm->data = devm_kzalloc(dev,
		struct_size(crm->data, hws, ZX_CRM_NR_CLKS), GFP_KERNEL);
	if (!crm->data)
		return -ENOMEM;
	crm->data->num = ZX_CRM_NR_CLKS;

	crm->topcrm = zx_crm_map(pdev, "topcrm");
	if (IS_ERR(crm->topcrm))
		return dev_err_probe(dev, PTR_ERR(crm->topcrm), "topcrm window\n");
	crm->crm1 = zx_crm_map(pdev, "crm1");
	if (IS_ERR(crm->crm1))
		return dev_err_probe(dev, PTR_ERR(crm->crm1), "crm1 window\n");
	crm->lsp0 = zx_crm_map(pdev, "lsp0crpm");
	if (IS_ERR(crm->lsp0))
		return dev_err_probe(dev, PTR_ERR(crm->lsp0), "lsp0crpm window\n");

	crm->lsp1 = zx_crm_map(pdev, "lsp1crpm");
	if (IS_ERR(crm->lsp1))
		return dev_err_probe(dev, PTR_ERR(crm->lsp1), "lsp1crpm window\n");

	/* TOPCRM+0x14 gates feed other LSP0/LSP1 peripherals too (UART, I2C,
	 * timers). Keep them on until those consumers have proper clock
	 * references. Never overwrite the whole shared register or infer
	 * reset bits from its other fields.
	 */
	wparent = zx_crm_gate_pd(crm, "wclk-parent", &zx_crm_parent_data[0],
				 crm->topcrm + ZX_TOPCRM_LSP0_GATE,
				 ZX_TOPCRM_LSP0_WCLK_BIT);
	if (IS_ERR(wparent))
		return dev_err_probe(dev, PTR_ERR(wparent), "working parent gate\n");
	pparent = zx_crm_gate_pd(crm, "pclk-parent", &zx_crm_parent_data[1],
				 crm->topcrm + ZX_TOPCRM_LSP0_GATE,
				 ZX_TOPCRM_LSP0_PCLK_BIT);
	if (IS_ERR(pparent))
		return dev_err_probe(dev, PTR_ERR(pparent), "peripheral parent gate\n");

	divider = zx_crm_divider(crm, "spi-divider", wparent,
				 ZX_LSP0_SPI_DIV_FLAGS, crm->lsp0 + ZX_LSP0_SPI,
				 ZX_LSP0_SPI_DIV_SHIFT, ZX_LSP0_SPI_DIV_WIDTH,
				 ZX_LSP0_SPI_DIVIDER_FLAGS);
	if (IS_ERR(divider))
		return dev_err_probe(dev, PTR_ERR(divider), "SPI divider\n");

	/* The board boots from the SPI flash controller and U-Boot leaves
	 * both gates on. The SPI driver keeps them enabled, but a deferred or
	 * failed SPI probe must not let clk_disable_unused gate them under a
	 * later retry, so they are critical as well.
	 */
	wclk = zx_crm_gate_hw(crm, "spi-wclk", divider, crm->lsp0 + ZX_LSP0_SPI,
			      ZX_LSP0_SPI_WCLK_BIT);
	if (IS_ERR(wclk))
		return dev_err_probe(dev, PTR_ERR(wclk), "SPI working gate\n");
	pclk = zx_crm_gate_hw(crm, "spi-pclk", pparent, crm->lsp0 + ZX_LSP0_SPI,
			      ZX_LSP0_SPI_PCLK_BIT);
	if (IS_ERR(pclk))
		return dev_err_probe(dev, PTR_ERR(pclk), "SPI peripheral gate\n");

	/* GPIO drives PERST# of both radios, the LEDs and the buttons. */
	gpio = zx_crm_gate_hw(crm, "gpio-pclk", pparent, crm->lsp0 + ZX_LSP0_GPIO,
			      ZX_LSP0_GPIO_PCLK_BIT);
	if (IS_ERR(gpio))
		return dev_err_probe(dev, PTR_ERR(gpio), "GPIO peripheral gate\n");

	/* LSP1 parents, then the MDIO controller the four PHYs sit behind. */
	l1wparent = zx_crm_gate_pd(crm, "lsp1-wclk", &zx_crm_parent_data[0],
				   crm->topcrm + ZX_TOPCRM_LSP0_GATE,
				   ZX_TOPCRM_LSP1_WCLK_BIT);
	if (IS_ERR(l1wparent))
		return dev_err_probe(dev, PTR_ERR(l1wparent), "LSP1 working parent gate\n");
	l1pparent = zx_crm_gate_pd(crm, "lsp1-pclk", &zx_crm_parent_data[1],
				   crm->topcrm + ZX_TOPCRM_LSP0_GATE,
				   ZX_TOPCRM_LSP1_PCLK_BIT);
	if (IS_ERR(l1pparent))
		return dev_err_probe(dev, PTR_ERR(l1pparent), "LSP1 peripheral parent gate\n");
	mdiv = zx_crm_divider(crm, "mdio-divider", l1wparent,
			      ZX_LSP1_MDIO_DIV_FLAGS, crm->lsp1 + ZX_LSP1_MDIO,
			      ZX_LSP1_MDIO_DIV_SHIFT, ZX_LSP1_MDIO_DIV_WIDTH,
			      ZX_LSP1_MDIO_DIVIDER_FLAGS);
	if (IS_ERR(mdiv))
		return dev_err_probe(dev, PTR_ERR(mdiv), "MDIO divider\n");
	mwclk = zx_crm_gate_hw(crm, "mdio-wclk", mdiv, crm->lsp1 + ZX_LSP1_MDIO,
			       ZX_LSP1_MDIO_WCLK_BIT);
	if (IS_ERR(mwclk))
		return dev_err_probe(dev, PTR_ERR(mwclk), "MDIO working gate\n");
	mpclk = zx_crm_gate_hw(crm, "mdio-pclk", l1pparent, crm->lsp1 + ZX_LSP1_MDIO,
			       ZX_LSP1_MDIO_PCLK_BIT);
	if (IS_ERR(mpclk))
		return dev_err_probe(dev, PTR_ERR(mpclk), "MDIO peripheral gate\n");

	crm->data->hws[ZX_CRM_SPI_WCLK] = wclk;
	crm->data->hws[ZX_CRM_SPI_PCLK] = pclk;
	crm->data->hws[ZX_CRM_LSP0_WCLK] = wparent;
	crm->data->hws[ZX_CRM_LSP0_PCLK] = pparent;
	crm->data->hws[ZX_CRM_LSP1_WCLK] = l1wparent;
	crm->data->hws[ZX_CRM_LSP1_PCLK] = l1pparent;
	crm->data->hws[ZX_CRM_MDIO_WCLK] = mwclk;
	crm->data->hws[ZX_CRM_MDIO_PCLK] = mpclk;
	crm->data->hws[ZX_CRM_GPIO_PCLK] = gpio;

	/* Registering the reset controller writes nothing. */
	crm->rcdev.owner = THIS_MODULE;
	crm->rcdev.ops = &zx_crm_reset_ops;
	crm->rcdev.of_node = dev->of_node;
	crm->rcdev.nr_resets = ZX_CRM_NR_RESETS;
	crm->rcdev.dev = dev;

	ret = devm_of_clk_add_hw_provider(dev, of_clk_hw_onecell_get, crm->data);
	if (ret)
		return dev_err_probe(dev, ret, "clock provider\n");
	ret = devm_reset_controller_register(dev, &crm->rcdev);
	if (ret)
		return dev_err_probe(dev, ret, "reset provider\n");
	return 0;
}

static const struct of_device_id zx_crm_match[] = {
	{ .compatible = "zte,zx279128s-crm" },
	{ }
};
MODULE_DEVICE_TABLE(of, zx_crm_match);

static struct platform_driver zx_crm_driver = {
	.probe = zx_crm_probe,
	.driver = {
		.name = "zx279128-crm",
		.of_match_table = zx_crm_match,
		/* Unbinding would unregister the SPI flash clocks. */
		.suppress_bind_attrs = true,
	},
};
builtin_platform_driver(zx_crm_driver);

MODULE_DESCRIPTION("ZTE ZX279128S clock/reset manager");
MODULE_LICENSE("GPL");
