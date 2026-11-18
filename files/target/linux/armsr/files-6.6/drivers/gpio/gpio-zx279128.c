// SPDX-License-Identifier: GPL-2.0-only
/*
 * GPIO controller for the ZTE/Sanechips ZX279128S.
 *
 * There is no datasheet and no vendor GPL source for this SoC. The register
 * layout below was recovered from two unencrypted vendor binaries - the
 * bootloader's zte_gpio_init/gpiotest command and the stock kernel's exported
 * zte_gpio_{get_value,set_value,direction_input,direction_output} - and
 * cross-checked against the one access sequence already known to work on real
 * hardware: pcie-zx279128.c has been driving PCIe PERST# on pins 53 and 55
 * through these same registers since before this driver existed.
 *
 * Layout: six banks of sixteen pins, 0x40 apart.
 *
 *   bank      = pin >> 4
 *   bank_base = 0x94407000 + bank * 0x40
 *   bit       = BIT(pin & 15)
 *
 *   +0x00  direction, 1 = output
 *   +0x14  input level
 *   +0x18  output set   - write the bit to drive high
 *   +0x1c  output clear - write the bit to drive low
 *
 * Independently corroborated by a vendor strap-reading routine that hardcodes
 * [base+0x14] for pins 5/15, [base+0x94] (bank 2 + 0x14) for pins 43..47 and
 * [base+0xd4] (bank 3 + 0x14) for pins 61/62.
 *
 * Both vendor binaries read-modify-write the set and clear registers rather
 * than writing the bare bit, so this driver does the same.
 *
 * Pin muxing lives in a separate block (CRM2, 0x94200000 +0x00..0x14) which the
 * bootloader programs from its own board table before Linux starts. This driver
 * deliberately does not touch it: the bit layout could not be recovered, and a
 * pin that the bootloader left muxed to a peripheral will not behave as GPIO no
 * matter what is written here.
 */

#include <linux/clk.h>
#include <linux/gpio/driver.h>
#include <linux/io.h>
#include <linux/mod_devicetable.h>
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/spinlock.h>

#define ZX_GPIO_NGPIO		96
#define ZX_GPIO_BANK_STRIDE	0x40
#define ZX_GPIO_DIR		0x00
#define ZX_GPIO_IN		0x14
#define ZX_GPIO_SET		0x18
#define ZX_GPIO_CLR		0x1c

struct zx_gpio {
	struct gpio_chip gc;
	void __iomem *base;
	spinlock_t lock;	/* serialises the read-modify-writes below */
};

static void __iomem *zx_gpio_reg(struct zx_gpio *zg, unsigned int off,
				 unsigned int reg, u32 *bit)
{
	*bit = BIT(off & 15);
	return zg->base + (off >> 4) * ZX_GPIO_BANK_STRIDE + reg;
}

static int zx_gpio_get_direction(struct gpio_chip *gc, unsigned int off)
{
	struct zx_gpio *zg = gpiochip_get_data(gc);
	void __iomem *r;
	u32 bit;

	r = zx_gpio_reg(zg, off, ZX_GPIO_DIR, &bit);

	return (readl(r) & bit) ? GPIO_LINE_DIRECTION_OUT
			       : GPIO_LINE_DIRECTION_IN;
}

static int zx_gpio_get(struct gpio_chip *gc, unsigned int off)
{
	struct zx_gpio *zg = gpiochip_get_data(gc);
	void __iomem *r;
	u32 bit;

	r = zx_gpio_reg(zg, off, ZX_GPIO_IN, &bit);

	return !!(readl(r) & bit);
}

static void zx_gpio_set(struct gpio_chip *gc, unsigned int off, int val)
{
	struct zx_gpio *zg = gpiochip_get_data(gc);
	unsigned long flags;
	void __iomem *r;
	u32 bit;

	r = zx_gpio_reg(zg, off, val ? ZX_GPIO_SET : ZX_GPIO_CLR, &bit);

	spin_lock_irqsave(&zg->lock, flags);
	writel(readl(r) | bit, r);
	spin_unlock_irqrestore(&zg->lock, flags);
}

static int zx_gpio_direction_input(struct gpio_chip *gc, unsigned int off)
{
	struct zx_gpio *zg = gpiochip_get_data(gc);
	unsigned long flags;
	void __iomem *r;
	u32 bit;

	r = zx_gpio_reg(zg, off, ZX_GPIO_DIR, &bit);

	spin_lock_irqsave(&zg->lock, flags);
	writel(readl(r) & ~bit, r);
	spin_unlock_irqrestore(&zg->lock, flags);

	return 0;
}

static int zx_gpio_direction_output(struct gpio_chip *gc, unsigned int off,
				    int val)
{
	struct zx_gpio *zg = gpiochip_get_data(gc);
	unsigned long flags;
	void __iomem *r;
	u32 bit;

	/* Drive the level before switching the pin to an output, so enabling a
	 * line cannot glitch it to whatever the set/clear registers last held.
	 */
	zx_gpio_set(gc, off, val);

	r = zx_gpio_reg(zg, off, ZX_GPIO_DIR, &bit);

	spin_lock_irqsave(&zg->lock, flags);
	writel(readl(r) | bit, r);
	spin_unlock_irqrestore(&zg->lock, flags);

	return 0;
}

static int zx_gpio_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct zx_gpio *zg;
	struct clk *clk;

	zg = devm_kzalloc(dev, sizeof(*zg), GFP_KERNEL);
	if (!zg)
		return -ENOMEM;

	zg->base = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(zg->base))
		return PTR_ERR(zg->base);

	/* LSP0CRPM+0x1c register clock. The provider keeps it on (critical),
	 * so taking it changes no register. Optional: a device tree without
	 * clocks behaves as before.
	 */
	clk = devm_clk_get_optional_enabled(dev, NULL);
	if (IS_ERR(clk))
		return dev_err_probe(dev, PTR_ERR(clk), "cannot enable clock\n");

	spin_lock_init(&zg->lock);

	zg->gc.label = dev_name(dev);
	zg->gc.parent = dev;
	zg->gc.owner = THIS_MODULE;
	zg->gc.base = -1;
	zg->gc.ngpio = ZX_GPIO_NGPIO;
	zg->gc.can_sleep = false;
	zg->gc.get_direction = zx_gpio_get_direction;
	zg->gc.direction_input = zx_gpio_direction_input;
	zg->gc.direction_output = zx_gpio_direction_output;
	zg->gc.get = zx_gpio_get;
	zg->gc.set = zx_gpio_set;

	return devm_gpiochip_add_data(dev, &zg->gc, zg);
}

static const struct of_device_id zx_gpio_of_match[] = {
	{ .compatible = "zte,zx279128s-gpio" },
	{ }
};
MODULE_DEVICE_TABLE(of, zx_gpio_of_match);

static struct platform_driver zx_gpio_driver = {
	.driver = {
		.name = "gpio-zx279128",
		.of_match_table = zx_gpio_of_match,
	},
	.probe = zx_gpio_probe,
};
builtin_platform_driver(zx_gpio_driver);
