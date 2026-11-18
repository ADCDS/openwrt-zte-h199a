// SPDX-License-Identifier: GPL-2.0-only
/* Early I/O coherency setup for the ZX279128S.
 *
 * The verified vendor kernel programs this block before PCIe probing and
 * uses coherent identity DMA for its PCI WiFi devices. Keep the complete
 * sequence, without assigning undocumented meanings to individual bits.
 */
#include <linux/init.h>
#include <linux/io.h>
#include <linux/kernel.h>
#include <linux/of.h>
#include <linux/of_address.h>
#include <linux/soc/zte/zx279128-boot.h>

#include <asm/mach/arch.h>

static void __init zx279128_init_machine(void)
{
	static const struct {
		u32 offset;
		u32 value;
	} sequence[] = {
		{ 0x80, 0x40000001 },
		{ 0x84, 0xbfffffff },
		{ 0x88, 0x1f0f1f0f },
		{ 0x78, 0x1f0f1f0f },
		{ 0x00, 0x0d000000 },
	};
	struct device_node *node;
	struct resource resource;
	void __iomem *base;
	unsigned int i;
	bool valid = true;

	zx279128_init_boot_bank();

	node = of_find_compatible_node(NULL, NULL, "zte,zx279128s-iocc");
	if (!node)
		panic("ZX279128: I/O coherency DT resource is required\n");
	if (of_address_to_resource(node, 0, &resource) ||
	    resource_size(&resource) < 0x8c) {
		of_node_put(node);
		panic("ZX279128: invalid I/O coherency resource\n");
	}
	base = of_iomap(node, 0);
	of_node_put(node);
	if (!base)
		panic("ZX279128: cannot map I/O coherency registers\n");

	/* Machine init is before the default OF population and PCIe probes.
	 * Do not permit coherent DMA clients to start if setup cannot be proved.
	 */
	for (i = 0; i < ARRAY_SIZE(sequence); i++)
		writel(sequence[i].value, base + sequence[i].offset);
	for (i = 0; i < ARRAY_SIZE(sequence); i++) {
		u32 observed = readl(base + sequence[i].offset);

		pr_info("zx279128 IOCC +%02x: wrote=%08x read=%08x\n",
			sequence[i].offset, sequence[i].value, observed);
		if (observed != sequence[i].value)
			valid = false;
	}
	iounmap(base);
	if (!valid)
		panic("ZX279128: I/O coherency readback failed; DMA clients blocked\n");
}

static const char *const zx279128_dt_compat[] __initconst = {
	"zte,zx279128s",
	NULL,
};

DT_MACHINE_START(ZX279128_DT, "ZTE ZX279128S")
	/* Stock uses value 0x30400000/mask 0xfeffffff. The shared-override
	 * and prefetch settings are in DT so Linux updates both PL310 AUX
	 * and PREFETCH representations; retain the remaining vendor mask.
	 */
	.l2c_aux_val = 0,
	.l2c_aux_mask = 0xfeffffff,
	.init_machine = zx279128_init_machine,
	.dt_compat = zx279128_dt_compat,
MACHINE_END
