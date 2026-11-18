// SPDX-License-Identifier: GPL-2.0-only
/* ZX279128S TOPCRM system reset. */
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/reboot.h>

static int zx279128_restart(struct sys_off_data *data)
{
	void __iomem *reset = data->cb_data;

	/* The stock restart path writes 1 unconditionally to TOPCRM+0x44.
	 * Do not read/RMW the trigger or depend on a different CPU here:
	 * ARM has already stopped the peer CPUs before invoking this handler.
	 */
	writel(1, reset);
	mdelay(1000);
	return NOTIFY_DONE;
}

static int zx279128_reboot_probe(struct platform_device *pdev)
{
	void __iomem *reset;

	reset = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(reset))
		return PTR_ERR(reset);

	return devm_register_sys_off_handler(&pdev->dev, SYS_OFF_MODE_RESTART,
					    128, zx279128_restart, reset);
}

static const struct of_device_id zx279128_reboot_match[] = {
	{ .compatible = "zte,zx279128s-reboot" },
	{ }
};
MODULE_DEVICE_TABLE(of, zx279128_reboot_match);

static struct platform_driver zx279128_reboot_driver = {
	.probe = zx279128_reboot_probe,
	.driver = {
		.name = "zx279128-reboot",
		.of_match_table = zx279128_reboot_match,
	},
};
module_platform_driver(zx279128_reboot_driver);

MODULE_DESCRIPTION("ZTE ZX279128S system reset");
MODULE_LICENSE("GPL");
