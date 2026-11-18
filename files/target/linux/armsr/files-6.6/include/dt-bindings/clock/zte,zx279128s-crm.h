/* SPDX-License-Identifier: (GPL-2.0-only OR BSD-2-Clause) */
#ifndef _DT_BINDINGS_CLOCK_ZX279128S_CRM_H
#define _DT_BINDINGS_CLOCK_ZX279128S_CRM_H

/* SPI flash controller clocks, LSP0CRPM+0x18 */
#define ZX_CRM_SPI_WCLK		0	/* working clock, bit 1, after the divider */
#define ZX_CRM_SPI_PCLK		1	/* peripheral clock, bit 0 */

/* Shared LSP0 parent gates, TOPCRM+0x14 (always on) */
#define ZX_CRM_LSP0_WCLK	2	/* bit 13 */
#define ZX_CRM_LSP0_PCLK	3	/* bit 11 */

/* Shared LSP1 parent gates, TOPCRM+0x14 (always on) */
#define ZX_CRM_LSP1_WCLK	4	/* bit 7, 100 MHz */
#define ZX_CRM_LSP1_PCLK	5	/* bit 5, APB */

/* MDIO controller clocks, LSP1CRPM+0x04 */
#define ZX_CRM_MDIO_WCLK	6	/* working clock, bit 1, after the divider */
#define ZX_CRM_MDIO_PCLK	7	/* peripheral clock, bit 0 */

/* GPIO controller peripheral clock, LSP0CRPM+0x1c bit 0 */
#define ZX_CRM_GPIO_PCLK	8

#endif
