// SPDX-License-Identifier: GPL-2.0-only
/* Give the running image stable MTD labels while retaining physical geometry.
 * The inactive firmware is read-only. The SPI transport independently limits
 * mutations to the captured active bank, never both firmware windows.
 */
#include <linux/init.h>
#include <linux/kernel.h>
#include <linux/of.h>
#include <linux/slab.h>
#include <linux/soc/zte/zx279128-boot.h>

#define ZX_PARTS_PATH "/soc/spi@94406000/flash@0/partitions/"

static int active_bank __ro_after_init = -1;

int zx279128_active_bank(void)
{
	return active_bank;
}

static int __init zx_bank_property(struct device_node *node, const char *name,
				 const void *value, int size)
{
	struct property *property;
	int ret;

	property = kzalloc(sizeof(*property), GFP_KERNEL);
	if (!property)
		return -ENOMEM;
	property->name = kstrdup(name, GFP_KERNEL);
	/* Legacy OF consumers use of_get_property() as a boolean test. Even
	 * a zero-length boolean therefore needs a non-NULL value pointer.
	 */
	property->value = kmemdup(size ? value : "", size ? size : 1, GFP_KERNEL);
	property->length = size;
	if (!property->name || !property->value) {
		ret = -ENOMEM;
		goto fail;
	}
	ret = of_update_property(node, property);
	if (!ret)
		return 0;
fail:
	kfree(property->value);
	kfree(property->name);
	kfree(property);
	return ret;
}

static int __init zx_bank_flag(struct device_node *node, const char *name, bool set)
{
	struct property *property;

	if (set)
		return zx_bank_property(node, name, "", 0);
	property = of_find_property(node, name, NULL);
	return property ? of_remove_property(node, property) : 0;
}

void __init zx279128_init_boot_bank(void)
{
	static const struct {
		const char *path;
		u32 offset;
		u32 size;
		unsigned int bank;
		const char *active_label;
		const char *inactive_label;
		bool rootfs;
	} parts[] = {
		{ ZX_PARTS_PATH "partition@700000", 0x700000, 0x300000, 0, "kernel1", "kernel2", false },
		{ ZX_PARTS_PATH "partition@a00000", 0xa00000, 0xd20000, 0, "rootfs", "rootfs2", true },
		{ ZX_PARTS_PATH "partition@1720000", 0x1720000, 0x20000, 0, "header", "header2", false },
		{ ZX_PARTS_PATH "partition@2000000", 0x2000000, 0x300000, 1, "kernel1", "kernel2", false },
		{ ZX_PARTS_PATH "partition@2300000", 0x2300000, 0xd20000, 1, "rootfs", "rootfs2", true },
		{ ZX_PARTS_PATH "partition@3020000", 0x3020000, 0x20000, 1, "header", "header2", false },
	};
	struct device_node *chosen, *flash, *table, *nodes[ARRAY_SIZE(parts)] = {};
	u32 bank, reg[2];
	unsigned int i;
	int ret = -EINVAL;
	bool valid;

	if (!of_machine_is_compatible("zte,zxhn-h199a"))
		return;
	chosen = of_find_node_by_path("/chosen");
	valid = of_property_count_u32_elems(chosen, "zte,boot-bank") == 1 &&
		!of_property_read_u32(chosen, "zte,boot-bank", &bank) && bank <= 1;
	of_node_put(chosen);
	if (valid)
		pr_info("H199A: vendor boot bank %c (validated before MMU setup)\n", 'A' + bank);
	else
		pr_info("H199A: vendor boot bank unavailable\n");
	flash = of_find_node_by_path("/soc/spi@94406000/flash@0");
	if (!of_property_read_bool(flash, "zte,bank-aware")) {
		of_node_put(flash);
		return;
	}
	if (!valid)
		panic("H199A: refusing NAND boot without a validated active bank\n");
	table = of_get_child_by_name(flash, "partitions");
	of_node_put(flash);
	if (!table)
		panic("H199A: active-bank partition table missing\n");
	/* Validate every physical range before changing any labels or permissions. */
	for (i = 0; i < ARRAY_SIZE(parts); i++) {
		/* of_get_child_by_name compares the name without @unit-address. */
		nodes[i] = of_find_node_by_path(parts[i].path);
		if (!nodes[i] || of_property_count_u32_elems(nodes[i], "reg") != 2 ||
		    of_property_read_u32_array(nodes[i], "reg", reg, 2) ||
		    reg[0] != parts[i].offset || reg[1] != parts[i].size)
			goto out;
	}
	for (i = 0; i < ARRAY_SIZE(parts); i++) {
		bool selected = parts[i].bank == bank;
		const char *label = selected ? parts[i].active_label : parts[i].inactive_label;

		ret = zx_bank_property(nodes[i], "label", label, strlen(label) + 1);
		if (!ret)
			ret = zx_bank_flag(nodes[i], "read-only", !selected);
		if (!ret)
			ret = zx_bank_flag(nodes[i], "linux,rootfs", selected && parts[i].rootfs);
		if (ret)
			goto out;
	}
	active_bank = bank;
	pr_info("H199A: active MTD labels and write window select bank %c; peer protected\n",
		'A' + bank);
out:
	for (i = 0; i < ARRAY_SIZE(parts); i++)
		of_node_put(nodes[i]);
	of_node_put(table);
	if (ret)
		panic("H199A: active-bank partition setup failed (%d); no flash devices probed\n", ret);
}
