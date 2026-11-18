#!/usr/bin/env python3
"""Apply the ZTE ZX UART support edits to a pristine Linux 6.6 amba-pl011.c,
so `git diff` can generate a clean patch (avoids hand-written hunk drift)."""
import re, sys

F = "drivers/tty/serial/amba-pl011.c"
src = open(F).read()
orig = src

# 1) include reset.h (kept: harmless; future reset work)
if "#include <linux/reset.h>" not in src:
    src = src.replace("#include <linux/pinctrl/consumer.h>",
                      "#include <linux/pinctrl/consumer.h>\n#include <linux/reset.h>", 1)

# 2) vendor_zte after vendor_st block — anchor: the comment line after vendor_st's closing brace
anchor = "/* Deals with DMA transactions */"
zte_block = '''static const u16 pl011_zte_offsets[REG_ARRAY_SIZE] = {
	[REG_DR] = ZX_UART011_DR,
	[REG_FR] = ZX_UART011_FR,
	[REG_LCRH_RX] = ZX_UART011_LCRH,
	[REG_LCRH_TX] = ZX_UART011_LCRH,
	[REG_IBRD] = ZX_UART011_IBRD,
	[REG_FBRD] = ZX_UART011_FBRD,
	[REG_CR] = ZX_UART011_CR,
	[REG_IFLS] = ZX_UART011_IFLS,
	[REG_IMSC] = ZX_UART011_IMSC,
	[REG_RIS] = ZX_UART011_RIS,
	[REG_MIS] = ZX_UART011_MIS,
	[REG_ICR] = ZX_UART011_ICR,
	[REG_DMACR] = ZX_UART011_DMACR,
};

static unsigned int get_fifosize_zte(struct amba_device *dev)
{
	return 16;
}

static struct vendor_data vendor_zte = {
	.reg_offset		= pl011_zte_offsets,
	.ifls			= UART011_IFLS_RX4_8 | UART011_IFLS_TX4_8,
	.fr_busy		= ZX_UART01x_FR_BUSY,
	.fr_dsr			= ZX_UART01x_FR_DSR,
	.fr_cts			= ZX_UART01x_FR_CTS,
	.fr_ri			= ZX_UART011_FR_RI,
	.access_32b		= true,
	.get_fifosize		= get_fifosize_zte,
};

'''
assert anchor in src, "anchor 1 missing"
src = src.replace(anchor, zte_block + anchor, 1)

# 3) zte earlycon write funcs — anchor before "#ifdef CONFIG_CONSOLE_POLL"
ec_write = '''static void zte_pl011_early_putc(struct uart_port *port, unsigned char c)
{
	/* The vendor early output path only waits for transmit FIFO space. */
	while (readl(port->membase + ZX_UART011_FR) & UART01x_FR_TXFF)
		cpu_relax();
	writel(c, port->membase + ZX_UART011_DR);
}

static void zte_pl011_early_write(struct console *con, const char *s, unsigned int n)
{
	struct earlycon_device *dev = con->data;

	uart_console_write(&dev->port, s, n, zte_pl011_early_putc);
}

'''
anchor2 = "#ifdef CONFIG_CONSOLE_POLL"
assert anchor2 in src, "anchor 2 missing"
src = src.replace(anchor2, ec_write + anchor2, 1)

# 4) earlycon declares — anchor after OF_EARLYCON_DECLARE(pl011, "arm,pl011", ...)
anchor3 = 'OF_EARLYCON_DECLARE(pl011, "arm,pl011", pl011_early_console_setup);'
ec_decl = anchor3 + '''

static int __init zte_pl011_early_console_setup(struct earlycon_device *device,
						const char *opt)
{
	if (!device->port.membase)
		return -ENODEV;

	device->con->write = zte_pl011_early_write;
	return 0;
}

OF_EARLYCON_DECLARE(zteuart, "zte,zx279128-uart", zte_pl011_early_console_setup);

OF_EARLYCON_DECLARE(zteuart, "zte,zx279133-uart", zte_pl011_early_console_setup);

/*
 * Name without a trailing digit: earlycon derives the console index from
 * trailing numerals, so "ztepl011" would print as "ztepl11" (index 11).
 */
EARLYCON_DECLARE(zteuart, zte_pl011_early_console_setup);'''
assert anchor3 in src, "anchor 3 missing"
src = src.replace(anchor3, ec_decl, 1)

# 5) amba_id entry — after the vendor_st id block
anchor4 = '''		.mask	= 0x00ffffff,
		.data	= &vendor_st,
	},
'''
zte_id = anchor4 + '''	{
		.id	= 0x001feffe,
		.mask	= 0x00ffffff,
		.data	= &vendor_zte,
	},
'''
assert anchor4 in src, "anchor 4 missing"
src = src.replace(anchor4, zte_id, 1)

assert src != orig
open(F, "w").write(src)
print("edits applied OK")
