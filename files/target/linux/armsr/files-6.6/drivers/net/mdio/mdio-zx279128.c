// SPDX-License-Identifier: GPL-2.0
/*
 * MDIO bus driver for the ZTE/Sanechips ZX279128S (ZXHN H199A).
 *
 * Reverse-engineered from the vendor U-Boot in the board's own bootloader
 * partition (the Linux-side vendor driver is not in the stock vmlinux; it
 * lives in the encrypted "SBU&" rootfs). The U-Boot MDIO read/write helpers
 * decode to this register map, relative to the block base (0x9a101000):
 *
 *   +0x04  W  write data (16-bit)
 *   +0x08  R  read data  (16-bit)
 *   +0x10  RW status; bit0 = transfer done, write 0 to clear
 *   +0x14  RW control:
 *              bit14      start
 *              bits11:10  opcode - 0b10 (0x800) read, 0b01 (0x400) write
 *              bits9:5    PHY address
 *              bits4:0    register address
 *
 * The vendor sequence is: clear start, clear status, set opcode, set phy,
 * set reg, (write: store data), set start, poll status bit0, clear status,
 * clear start, then read the data register.
 */
#include <linux/clk.h>
#include <linux/io.h>
#include <linux/iopoll.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/of_mdio.h>
#include <linux/phy.h>
#include <linux/platform_device.h>

#define ZX_MDIO_WDATA	0x04
#define ZX_MDIO_RDATA	0x08
#define ZX_MDIO_STATUS	0x10
#define ZX_MDIO_CTRL	0x14

#define ZX_CTRL_START	BIT(14)
#define ZX_CTRL_OP_MASK	(3 << 10)
#define ZX_CTRL_OP_READ	(2 << 10)
#define ZX_CTRL_OP_WRITE (1 << 10)
#define ZX_CTRL_PHY_MASK (0x1f << 5)
#define ZX_CTRL_REG_MASK 0x1f

#define ZX_MDIO_TIMEOUT_US	100000

struct zx_mdio {
	void __iomem *base;
};

static void zx_mdio_setup(struct zx_mdio *zm, int phy, int reg, u32 op)
{
	u32 v;

	/* clear start, then status */
	v = readl(zm->base + ZX_MDIO_CTRL) & ~ZX_CTRL_START;
	writel(v, zm->base + ZX_MDIO_CTRL);
	writel(0, zm->base + ZX_MDIO_STATUS);

	/* opcode */
	v = readl(zm->base + ZX_MDIO_CTRL) & ~ZX_CTRL_OP_MASK;
	writel(v | op, zm->base + ZX_MDIO_CTRL);

	/* register address */
	v = readl(zm->base + ZX_MDIO_CTRL) & ~ZX_CTRL_REG_MASK;
	writel(v | (reg & ZX_CTRL_REG_MASK), zm->base + ZX_MDIO_CTRL);

	/* phy address */
	v = readl(zm->base + ZX_MDIO_CTRL) & ~ZX_CTRL_PHY_MASK;
	writel(v | ((phy << 5) & ZX_CTRL_PHY_MASK), zm->base + ZX_MDIO_CTRL);
}

static int zx_mdio_go(struct zx_mdio *zm)
{
	u32 v;
	int ret;

	writel(readl(zm->base + ZX_MDIO_CTRL) | ZX_CTRL_START,
	       zm->base + ZX_MDIO_CTRL);

	ret = readl_poll_timeout(zm->base + ZX_MDIO_STATUS, v, v & 1,
				 10, ZX_MDIO_TIMEOUT_US);

	writel(0, zm->base + ZX_MDIO_STATUS);
	writel(readl(zm->base + ZX_MDIO_CTRL) & ~ZX_CTRL_START,
	       zm->base + ZX_MDIO_CTRL);
	return ret;
}

static int zx_mdio_read(struct mii_bus *bus, int phy, int reg)
{
	struct zx_mdio *zm = bus->priv;
	int ret;

	zx_mdio_setup(zm, phy, reg, ZX_CTRL_OP_READ);
	ret = zx_mdio_go(zm);
	if (ret)
		return ret;

	return readl(zm->base + ZX_MDIO_RDATA) & 0xffff;
}

static int zx_mdio_write(struct mii_bus *bus, int phy, int reg, u16 val)
{
	struct zx_mdio *zm = bus->priv;

	zx_mdio_setup(zm, phy, reg, ZX_CTRL_OP_WRITE);
	writel(val, zm->base + ZX_MDIO_WDATA);
	return zx_mdio_go(zm);
}

static int zx_mdio_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct zx_mdio *zm;
	struct mii_bus *bus;
	struct clk *clk;
	int ret;

	bus = devm_mdiobus_alloc_size(dev, sizeof(*zm));
	if (!bus)
		return -ENOMEM;

	zm = bus->priv;
	zm->base = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(zm->base))
		return PTR_ERR(zm->base);

	/* LSP1CRPM+0x04 register and MDC clocks. The provider keeps both on
	 * (they are critical), so taking them changes no register; it only
	 * records the dependency. Optional: a device tree without clocks
	 * behaves as before.
	 */
	clk = devm_clk_get_optional_enabled(dev, "pclk");
	if (IS_ERR(clk))
		return dev_err_probe(dev, PTR_ERR(clk), "cannot enable peripheral clock\n");
	clk = devm_clk_get_optional_enabled(dev, "wclk");
	if (IS_ERR(clk))
		return dev_err_probe(dev, PTR_ERR(clk), "cannot enable working clock\n");

	bus->name = "zx279128-mdio";
	bus->read = zx_mdio_read;
	bus->write = zx_mdio_write;
	bus->parent = dev;
	snprintf(bus->id, MII_BUS_ID_SIZE, "%s", dev_name(dev));

	ret = of_mdiobus_register(bus, dev->of_node);
	if (ret)
		return dev_err_probe(dev, ret, "failed to register MDIO bus\n");

	platform_set_drvdata(pdev, bus);
	dev_info(dev, "ZX279128S MDIO bus registered\n");

	/* Probe-time scan: log every address that answers, so a silent bus can
	 * be told apart from PHYs sitting at unexpected addresses.
	 */
	{
		int a, id2, id3;

		for (a = 0; a < 32; a++) {
			id2 = zx_mdio_read(bus, a, 2);
			id3 = zx_mdio_read(bus, a, 3);
			if (id2 < 0 || id3 < 0) {
				dev_info(dev, "scan phy%d: read error %d/%d\n",
					 a, id2, id3);
				continue;
			}
			if (id2 == 0xffff && id3 == 0xffff)
				continue;
			if (!id2 && !id3)
				continue;
			dev_info(dev, "scan phy%d: id=%04x:%04x\n",
				 a, id2, id3);
		}
	}
	/* Bring-up aid: dump the per-port MAC registers that the vendor U-Boot
	 * smac_init() programs, so the reverse-engineered map can be checked
	 * against live hardware. Base 0x92200000, per-port stride 0x40000.
	 */
	{
		void __iomem *mac = ioremap(0x92200000, 0x1000);
		void __iomem *bm  = ioremap(0x92348000, 0x100);
		void __iomem *tm  = ioremap(0x92350000, 0x200);
		void __iomem *lnk = ioremap(0x921d9000, 0x100);

		if (mac) {
			dev_info(dev,
				 "mac0 +070=%08x +0b4=%08x +0e0=%08x +b00=%08x\n",
				 readl(mac + 0x070), readl(mac + 0x0b4),
				 readl(mac + 0x0e0), readl(mac + 0xb00));
			iounmap(mac);
		}
		if (bm) {
			dev_info(dev, "bm  +000=%08x +00c=%08x +014=%08x\n",
				 readl(bm + 0x00), readl(bm + 0x0c),
				 readl(bm + 0x14));
			iounmap(bm);
		}
		if (tm) {
			dev_info(dev, "tm  +068=%08x +11c=%08x\n",
				 readl(tm + 0x68), readl(tm + 0x11c));
			iounmap(tm);
		}
		{
			/* TM block proper is at 0x92340000; +0xf0 holds the
			 * descriptor ring base (expect 0x41a00000). */
			void __iomem *tmb = ioremap(0x92340000, 0x100);

			if (tmb) {
				dev_info(dev, "tmbase +004=%08x +0f0=%08x\n",
					 readl(tmb + 0x04), readl(tmb + 0xf0));
				iounmap(tmb);
			}
		}
		if (lnk) {
			dev_info(dev, "link +068=%08x\n", readl(lnk + 0x68));
			iounmap(lnk);
		}
	}
	return 0;
}

static void zx_mdio_remove(struct platform_device *pdev)
{
	mdiobus_unregister(platform_get_drvdata(pdev));
}

static const struct of_device_id zx_mdio_of_match[] = {
	{ .compatible = "zte,zx279128s-mdio" },
	{ }
};
MODULE_DEVICE_TABLE(of, zx_mdio_of_match);

static struct platform_driver zx_mdio_driver = {
	.probe = zx_mdio_probe,
	.remove_new = zx_mdio_remove,
	.driver = {
		.name = "mdio-zx279128",
		.of_match_table = zx_mdio_of_match,
	},
};
module_platform_driver(zx_mdio_driver);

MODULE_DESCRIPTION("ZTE ZX279128S MDIO bus driver");
MODULE_LICENSE("GPL");
