// SPDX-License-Identifier: GPL-2.0-only
/* Preserve the vendor-selected NAND bank before the decompressor page table
 * overwrites the BootPara block at 0x40007000. No flash access or ATAG merge.
 */
#include <linux/libfdt_env.h>
#include <libfdt.h>

#define ZX_BOOTPARA_SIZE 0x554
#define ZX_BOOTPARA_CHECKSUM 0xa0
#define ZX_BOOTPARA_SELECT 0x3c
#define ZX_BOOTPARA_RECORD 0x21c
#define ZX_BOOTPARA_KERNEL 0x130
#define ZX_BOOTPARA_FS 0x134

static unsigned int zx_boot_le32(const unsigned char *p)
{
	return (unsigned int)p[0] | (unsigned int)p[1] << 8 |
	       (unsigned int)p[2] << 16 | (unsigned int)p[3] << 24;
}

static int zx_boot_bank(const unsigned char *p, unsigned int length)
{
	unsigned int sum = 0, selected, record, i;

	if (length != ZX_BOOTPARA_SIZE ||
	    zx_boot_le32(p) != 0xcccccccc ||
	    zx_boot_le32(p + 4) != 0x55555555 ||
	    zx_boot_le32(p + 8) != 0xaaaaaaaa ||
	    zx_boot_le32(p + 12) != 0x11111111)
		return -1;
	for (i = 0; i < length; i++)
		if (i < ZX_BOOTPARA_CHECKSUM || i >= ZX_BOOTPARA_CHECKSUM + 4)
			sum += p[i];
	if (sum != zx_boot_le32(p + ZX_BOOTPARA_CHECKSUM) ||
	    !zx_boot_le32(p + 0x38) || zx_boot_le32(p + 0x38) > 2 ||
	    !zx_boot_le32(p + 0x34) || zx_boot_le32(p + 0x34) > 2)
		return -1;
	selected = zx_boot_le32(p + ZX_BOOTPARA_SELECT);
	if (selected > 1)
		return -1;
	record = selected * ZX_BOOTPARA_RECORD;
	if (zx_boot_le32(p + record + ZX_BOOTPARA_KERNEL) !=
	    (selected ? 0x2000000 : 0x700000) ||
	    zx_boot_le32(p + record + ZX_BOOTPARA_FS) !=
	    (selected ? 0x2300000 : 0xa00000))
		return -1;
	return selected;
}

void zx279128_capture_boot_bank(void *fdt)
{
	const unsigned char *bootpara = (const unsigned char *)0x40007000;
	const void *property;
	fdt32_t value;
	int chosen, length, bank;

	if (!fdt || fdt_check_header(fdt) ||
	    fdt_node_check_compatible(fdt, 0, "zte,zxhn-h199a"))
		return;
	chosen = fdt_path_offset(fdt, "/chosen");
	if (chosen < 0)
		return;
	property = fdt_getprop(fdt, chosen, "zte,boot-bank", &length);
	if (!property || length != sizeof(value))
		return;
	bank = zx_boot_bank(bootpara, ZX_BOOTPARA_SIZE);
	value = cpu_to_fdt32(bank < 0 ? 0xffffffff : bank);
	/* Replace an existing cell: never grow into the appended DTB's stack. */
	fdt_setprop_inplace(fdt, chosen, "zte,boot-bank", &value, sizeof(value));
}
