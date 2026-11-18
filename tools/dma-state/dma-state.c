// SPDX-License-Identifier: GPL-2.0-only
/* Diagnostic only: report cached PCI DMA metadata, without device MMIO. */
#include <linux/dma-map-ops.h>
#include <linux/init.h>
#include <linux/module.h>
#include <linux/pci.h>

static int __init dma_state_init(void)
{
	struct pci_dev *pdev = NULL;

	for_each_pci_dev(pdev) {
		if (pdev->vendor != 0x14c3 ||
		    (pdev->device != 0x7603 && pdev->device != 0x7663))
			continue;
		pr_info("h199a DMA %s id=%04x:%04x coherent=%u mask=%llx coherent_mask=%llx dma_addr_bytes=%zu\n",
			pci_name(pdev), pdev->vendor, pdev->device,
			dev_is_dma_coherent(&pdev->dev),
			(unsigned long long)dma_get_mask(&pdev->dev),
			(unsigned long long)pdev->dev.coherent_dma_mask,
			sizeof(dma_addr_t));
	}
	return 0;
}

static void __exit dma_state_exit(void)
{
}

module_init(dma_state_init);
module_exit(dma_state_exit);
MODULE_LICENSE("GPL");
MODULE_DESCRIPTION("Read-only H199A PCI DMA configuration snapshot");
