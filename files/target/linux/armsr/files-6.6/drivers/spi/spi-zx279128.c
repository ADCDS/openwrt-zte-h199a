// SPDX-License-Identifier: GPL-2.0-only
/*
 * ZX279128S SPI memory controller, initially for read-only qualification.
 * Register transactions are recovered from the own-board vendor firmware.
 * ECC, chip configuration and page/erase sequencing belong to SPI-NAND: the
 * core selects the Micron on-die ECC engine (ECC_EN for every non-raw page
 * request) and reads the per-page ECC status; this transport never offers a
 * host ECC engine (op->data.ecc is rejected) and never alters ECC itself.
 */
#include <linux/clk.h>
#include <linux/delay.h>
#include <linux/io.h>
#include <linux/ktime.h>
#include <linux/module.h>
#include <linux/of.h>
#include <linux/platform_device.h>
#include <linux/spi/spi.h>
#include <linux/spi/spi-mem.h>
#include <linux/soc/zte/zx279128-boot.h>

#define ZX_TRIG		0x04
#define ZX_CTRL		0x08
#define ZX_INIT		0x0c
#define ZX_CFG		0x10
#define ZX_CFG2		0x14
#define ZX_COUNT	0x18
#define ZX_ADDRESS	0x1c
#define ZX_OPCODE	0x20
#define ZX_STATUS	0x2c
#define ZX_INT_CLEAR	0x30
#define ZX_FIFO_STATUS	0x34
#define ZX_FIFO		0x38

#define ZX_DONE		BIT(0)
#define ZX_FORMAT_ERROR	BIT(1)
#define ZX_RX_AVAILABLE	GENMASK(12, 8)
#define ZX_TX_AVAILABLE	GENMASK(20, 16)
#define ZX_FIFO_CLEAR	0x1c440
#define ZX_MAX_TRANSFER	2176
#define ZX_TIMEOUT_NS	(100 * NSEC_PER_MSEC)
#define ZX_TEST_FIRST_ROW 0xc7c0
#define ZX_TEST_PAGES	64
#define ZX_UBI_FIRST_ROW	0xa800
#define ZX_UBI_END_ROW	0xc800

/* Temporary qualification mode: one verified-empty H199A staging block.
 * Default boots remain read-only. No array operation is issued by probe.
 */
static bool write_test;
module_param(write_test, bool, 0444);
MODULE_PARM_DESC(write_test, "allow one program attempt/page and erase only in staging block799");
static bool ubi_test;
module_param(ubi_test, bool, 0444);
MODULE_PARM_DESC(ubi_test, "allow program/erase only in the 84..100MiB UBI qualification window");

#ifdef CONFIG_SPI_ZX279128_PRODUCTION_POLICY
/*
 * H199A production write policy. This is the second, independent protection
 * layer under the device tree's read-only partitions: a fixed physical
 * allowlist compiled into the transport. The device tree cannot widen it.
 *
 * Rows are SPI-NAND pages (2048 bytes, 64 per 128 KiB eraseblock):
 *   bank A  kernel1+rootfs+header  [0x00700000,0x01740000)  rows [0x0e00,0x2e80)
 *   bank B  kernel1+rootfs+header  [0x02000000,0x03040000)  rows [0x4000,0x6080)
 * Exactly one firmware range is enabled, from the validated boot selection.
 * The overlay UBI window [0x05400000,0x06400000), rows [0xa800,0xc800), is
 * also writable. The peer and everything outside these ranges are refused.
 */
#define ZX_ROWS			0x10000	/* 128 MiB; higher row bits alias */
#define ZX_BLOCK_ROWS		64
#define ZX_BANK_A_FIRST_ROW	0x0e00	/* kernel1 0x00700000 */
#define ZX_BANK_A_END_ROW	0x2e80	/* end of header 0x01740000 */
#define ZX_BANK_B_FIRST_ROW	0x4000	/* kernel2 0x02000000 */
#define ZX_BANK_B_END_ROW	0x6080	/* end of header2 0x03040000 */
#define ZX_REG_BLOCK_LOCK	0xa0
#define ZX_REG_CFG		0xb0
/* CFG2/CFG1/LOT_EN/CFG0 select OTP, parameter-page or lock-down modes in
 * which PROGRAM EXECUTE no longer addresses the main array. ECC_EN (bit 4)
 * and the bits the vendor bootloader leaves set (0x18) remain writable.
 */
#define ZX_CFG_MODE_BITS	(BIT(7) | BIT(6) | BIT(5) | BIT(1))

static bool production;
module_param(production, bool, 0444);
MODULE_PARM_DESC(production, "H199A production policy: program/erase only the selected bank and UBI");
static bool production_qualify;
module_param(production_qualify, bool, 0444);
MODULE_PARM_DESC(production_qualify, "production policy with firmware writes refused, for RAM-only qualification");

enum zx_verdict {
	ZX_ALLOW,		/* not an array mutation, or inside the allowlist */
	ZX_DENY,		/* outside the allowlist, aliased or malformed */
	ZX_REFUSE_BANK_A,	/* qualification only: bank A recognised, refused */
};
#endif

struct zx_spifc {
	void __iomem *base;
	struct device *dev;
	unsigned long rate;
	bool failed;
	bool write_test;
	bool ubi_test;
	u64 attempted_pages;
#ifdef CONFIG_SPI_ZX279128_PRODUCTION_POLICY
	bool production;
	bool production_qualify;
	bool policy_latched;
	int bank;
	u8 latch_opcode;
	u64 latch_addr;
	u32 policy_refusals;
	u32 bank_a_refusals;
#endif
};

struct zx_wire_op {
	u32 cfg;
	u32 cfg2;
	u32 address;
};

/* Use the verified wire recipes rather than inventing meanings for unused
 * register fields. Zero-length cache templates are needed by dirmap creation.
 */
static bool zx_decode_op(const struct spi_mem_op *op, struct zx_wire_op *wire)
{
	if (op->cmd.nbytes != 1 || op->cmd.buswidth != 1 ||
	    op->cmd.dtr || op->addr.dtr || op->dummy.dtr || op->data.dtr ||
	    op->data.ecc || op->data.swap16 ||
	    op->addr.nbytes > 3 || op->dummy.nbytes > 1 ||
	    (op->addr.nbytes && (op->addr.buswidth != 1 ||
	     op->addr.val >= BIT_ULL(8 * op->addr.nbytes))) ||
	    (op->dummy.nbytes && op->dummy.buswidth != 1))
		return false;

	wire->address = op->addr.val;
	wire->cfg = 0;
	wire->cfg2 = 0;

	switch (op->cmd.opcode) {
	case 0xff:
	case 0x06:
	case 0x04:
		if (op->addr.nbytes || op->dummy.nbytes || op->data.nbytes ||
		    op->data.dir != SPI_MEM_NO_DATA)
			return false;
		wire->cfg2 = op->cmd.opcode == 0xff ? 0 : 0x40;
		return true;
	case 0x13:
	case 0x10:
	case 0xd8:
		if (op->addr.nbytes != 3 || op->dummy.nbytes ||
		    op->data.nbytes || op->data.dir != SPI_MEM_NO_DATA)
			return false;
		wire->cfg = 0x10;
		wire->cfg2 = 0x40;
		return true;
	case 0x0f:
	case 0x1f:
		if (op->addr.nbytes != 1 || op->dummy.nbytes ||
		    op->data.nbytes != 1 || op->data.buswidth != 1 ||
		    op->data.dir != (op->cmd.opcode == 0x0f ?
				    SPI_MEM_DATA_IN : SPI_MEM_DATA_OUT))
			return false;
		wire->cfg = op->cmd.opcode == 0x0f ? 0x12 : 0x11;
		return true;
	case 0x9f:
		if (op->data.dir != SPI_MEM_DATA_IN || op->data.buswidth != 1 ||
		    !op->data.nbytes || op->data.nbytes > 8)
			return false;
		if (!op->addr.nbytes && !op->dummy.nbytes) {
			wire->cfg = 0x02;
			wire->cfg2 = 0x40;
		} else if ((op->addr.nbytes == 1 && !op->addr.val &&
			    !op->dummy.nbytes) ||
			   (!op->addr.nbytes && op->dummy.nbytes == 1)) {
			/* For READ ID only, a zero address byte supplies the same
			 * eight single-lane clocks as the chip's dummy byte.
			 */
			wire->cfg = 0x12;
			wire->address = 0;
		} else {
			return false;
		}
		return true;
	case 0x3b:
		if (op->addr.nbytes != 2 || op->dummy.nbytes != 1 ||
		    op->data.dir != SPI_MEM_DATA_IN || op->data.buswidth != 2 ||
		    op->addr.val > ZX_MAX_TRANSFER ||
		    op->data.nbytes > ZX_MAX_TRANSFER - op->addr.val)
			return false;
		wire->cfg = 0x16;
		wire->cfg2 = 0x1024;
		return true;
	case 0x02:
	case 0x84:
		if (op->addr.nbytes != 2 || op->dummy.nbytes ||
		    op->data.dir != SPI_MEM_DATA_OUT || op->data.buswidth != 1 ||
		    op->addr.val > ZX_MAX_TRANSFER ||
		    op->data.nbytes > ZX_MAX_TRANSFER - op->addr.val)
			return false;
		wire->cfg = 0x11;
		wire->cfg2 = 0x20;
		return true;
	default:
		return false;
	}
}

static bool zx_supports_op(struct spi_mem *mem, const struct spi_mem_op *op)
{
	struct zx_spifc *sp = spi_controller_get_devdata(mem->spi->controller);
	struct zx_wire_op wire;

	return op->data.nbytes <= ZX_MAX_TRANSFER &&
		(!op->max_freq || op->max_freq >= sp->rate) &&
		spi_mem_default_supports_op(mem, op) && zx_decode_op(op, &wire);
}

static int zx_adjust_op_size(struct spi_mem *mem, struct spi_mem_op *op)
{
	op->data.nbytes = min_t(unsigned int, op->data.nbytes, ZX_MAX_TRANSFER);
	if (op->cmd.opcode == 0x3b || op->cmd.opcode == 0x02 || op->cmd.opcode == 0x84) {
		if (op->addr.val >= ZX_MAX_TRANSFER)
			return -EINVAL;
		op->data.nbytes = min_t(unsigned int, op->data.nbytes,
					ZX_MAX_TRANSFER - op->addr.val);
	}
	return 0;
}

static int zx_wait(struct zx_spifc *sp, u32 reg, u32 mask, u64 deadline,
		   u32 *last)
{
	for (;;) {
		*last = readl(sp->base + reg);
		if (ktime_get_ns() >= deadline)
			return -ETIMEDOUT;
		if (*last & mask)
			return 0;
		cpu_relax();
	}
}

static int zx_wait_done(struct zx_spifc *sp, u64 deadline, u32 *last)
{
	int ret = zx_wait(sp, ZX_STATUS, ZX_DONE, deadline, last);

	return ret ? ret : (*last & ZX_FORMAT_ERROR) ? -EIO : 0;
}

static bool zx_array_write(unsigned int opcode)
{
	return opcode == 0x06 || opcode == 0x02 || opcode == 0x84 ||
		opcode == 0x10 || opcode == 0xd8;
}

#ifdef CONFIG_SPI_ZX279128_PRODUCTION_POLICY
/* Pure: PROGRAM EXECUTE (0x10) or BLOCK ERASE (0xd8) at one row address. */
static enum zx_verdict zx_policy_row(bool qualify, int bank, unsigned int opcode, u64 row)
{
	if (opcode != 0x10 && opcode != 0xd8)
		return ZX_DENY;
	/* The die ignores row bits above 15, so a larger value would alias. */
	if (row >= ZX_ROWS)
		return ZX_DENY;
	if (opcode == 0xd8 && (row & (ZX_BLOCK_ROWS - 1)))
		return ZX_DENY;
	if (row >= ZX_UBI_FIRST_ROW && row < ZX_UBI_END_ROW)
		return ZX_ALLOW;
	if ((bank == 0 && row >= ZX_BANK_A_FIRST_ROW && row < ZX_BANK_A_END_ROW) ||
	    (bank == 1 && row >= ZX_BANK_B_FIRST_ROW && row < ZX_BANK_B_END_ROW))
		return qualify ? ZX_REFUSE_BANK_A : ZX_ALLOW;
	return ZX_DENY;
}

/* Pure: SET FEATURE. SPI-NAND writes only the unlock value and ECC/OTP-off
 * configuration updates; anything else could redirect program/erase.
 */
static enum zx_verdict zx_policy_feature(u64 reg, unsigned int value)
{
	if (value > 0xff)
		return ZX_DENY;
	if (reg == ZX_REG_BLOCK_LOCK)
		return value ? ZX_DENY : ZX_ALLOW;
	if (reg == ZX_REG_CFG)
		return value & ZX_CFG_MODE_BITS ? ZX_DENY : ZX_ALLOW;
	return ZX_DENY;
}

/* Pure: the production verdict for one controller operation. */
static enum zx_verdict zx_policy_verdict(bool qualify, int bank, const struct spi_mem_op *op)
{
	switch (op->cmd.opcode) {
	case 0x10:
	case 0xd8:
		if (op->addr.nbytes != 3)
			return ZX_DENY;
		return zx_policy_row(qualify, bank, op->cmd.opcode, op->addr.val);
	case 0x1f:
		if (op->addr.nbytes != 1 || op->data.dir != SPI_MEM_DATA_OUT ||
		    op->data.nbytes != 1 || !op->data.buf.out)
			return ZX_DENY;
		return zx_policy_feature(op->addr.val, *(const u8 *)op->data.buf.out);
	default:
		/* Reads, RESET, WRITE ENABLE/DISABLE and cache loads leave the
		 * array unchanged; only PROGRAM EXECUTE and ERASE commit data.
		 */
		return ZX_ALLOW;
	}
}

/* The first refusal latches: no later WREN, load, program or erase is sent
 * until reboot. Feature writes stay filtered but are not latched, because
 * reads toggle ECC_EN through them.
 */
static int zx_production_gate(struct zx_spifc *sp, const struct spi_mem_op *op)
{
	bool array = zx_array_write(op->cmd.opcode);
	enum zx_verdict verdict;

	/* Only array mutations (PROGRAM EXECUTE, BLOCK ERASE, WREN, cache loads)
	 * and SET FEATURE are gated; reads and RESET pass through untouched.
	 */
	if (!array && op->cmd.opcode != 0x1f)
		return 0;
	/* Once latched, no further mutation setup reaches the chip: WREN and
	 * cache loads are refused too, so a denied program cannot be retried.
	 * Feature writes stay available because reads toggle ECC_EN through them.
	 */
	if (array && sp->policy_latched) {
		sp->policy_refusals++;
		return -EROFS;
	}
	verdict = zx_policy_verdict(sp->production_qualify, sp->bank, op);
	if (verdict == ZX_ALLOW)
		return 0;
	sp->policy_refusals++;
	if (verdict == ZX_REFUSE_BANK_A)
		sp->bank_a_refusals++;
	/* Latch only on an array-op refusal. A filtered feature write is a
	 * benign denial (an unexpected mode change) and must not wedge ECC reads.
	 */
	if (array && !sp->policy_latched) {
		sp->policy_latched = true;
		sp->latch_opcode = op->cmd.opcode;
		sp->latch_addr = op->addr.val;
		dev_err(sp->dev, "write policy %s op=%02x addr=%llx; array mutations refused until reboot\n",
			verdict == ZX_REFUSE_BANK_A ? "refused active bank (qualification)" : "denied",
			op->cmd.opcode, op->addr.val);
	}
	return -EROFS;
}
#endif

static int zx_allow_array_op(struct zx_spifc *sp, const struct spi_mem_op *op)
{
	u64 bit;

#ifdef CONFIG_SPI_ZX279128_PRODUCTION_POLICY
	if (sp->production || sp->production_qualify)
		return zx_production_gate(sp, op);
#endif
	if (!zx_array_write(op->cmd.opcode))
		return 0;
	if (sp->write_test && sp->ubi_test)
		return -EINVAL;
	if (sp->ubi_test) {
		if (op->cmd.opcode != 0x10 && op->cmd.opcode != 0xd8)
			return 0;
		if (op->addr.val < ZX_UBI_FIRST_ROW || op->addr.val >= ZX_UBI_END_ROW)
			return -EROFS;
		if (op->cmd.opcode == 0xd8 && (op->addr.val & (ZX_TEST_PAGES - 1)))
			return -EROFS;
		/* UBI reuses pages only after erase. The separate SPI-NAND core
		 * diagnostic guard stops further mutations after any failed write
		 * or erase and forbids permanent bad-block marking.
		 */
		return 0;
	}
	if (!sp->write_test)
		return -EROFS;
	if (op->cmd.opcode == 0xd8)
		return op->addr.val == ZX_TEST_FIRST_ROW ? 0 : -EROFS;
	if (op->cmd.opcode != 0x10)
		return 0; /* WREN and cache loading do not modify the array. */
	if (op->addr.val < ZX_TEST_FIRST_ROW ||
	    op->addr.val >= ZX_TEST_FIRST_ROW + ZX_TEST_PAGES)
		return -EROFS;
	bit = BIT_ULL(op->addr.val - ZX_TEST_FIRST_ROW);
	if (sp->attempted_pages & bit)
		return -EALREADY;
	/* The SPI core serializes operations. Record the attempt before MMIO,
	 * including uncertain completion or subsequent chip P_FAIL. Erase DONE
	 * is not chip completion, so it must not reset this boot's bitmap.
	 */
	sp->attempted_pages |= bit;
	return 0;
}

static void zx_tx_word(struct zx_spifc *sp, const struct spi_mem_op *op, u32 *pos)
{
	const u8 *buf = op->data.buf.out;
	unsigned int n = min_t(unsigned int, 4, op->data.nbytes - *pos);
	__le32 word = cpu_to_le32(U32_MAX);

	memcpy(&word, buf + *pos, n);
	writel(le32_to_cpu(word), sp->base + ZX_FIFO);
	*pos += n;
}

static int zx_exec_op(struct spi_mem *mem, const struct spi_mem_op *op)
{
	struct zx_spifc *sp = spi_controller_get_devdata(mem->spi->controller);
	struct zx_wire_op wire;
	const char *phase = "setup";
	bool short_read = op->cmd.opcode == 0x0f || op->cmd.opcode == 0x9f;
	bool bulk_write = op->cmd.opcode == 0x02 || op->cmd.opcode == 0x84;
	u64 deadline;
	u32 last = 0, pos = 0, value;
	int ret;

	if (spi_get_chipselect(mem->spi, 0) || !zx_decode_op(op, &wire) ||
	    op->data.nbytes > ZX_MAX_TRANSFER ||
	    (op->max_freq && op->max_freq < sp->rate))
		return -EINVAL;
	/* EROFS must not fall back to generic SPI transfers. */
	ret = zx_allow_array_op(sp, op);
	if (ret)
		return ret;
	if (sp->failed)
		return -EIO;
	if (op->data.dir != SPI_MEM_NO_DATA &&
	    (!op->data.nbytes || !op->data.buf.in))
		return -EINVAL;

	deadline = ktime_get_ns() + ZX_TIMEOUT_NS;
	value = readl(sp->base + ZX_CTRL);
	/* The vendor only asserts enable while CTRL bit 1 is clear. */
	if (!(value & BIT(1)))
		writel(value | BIT(0), sp->base + ZX_CTRL);
	writel(wire.cfg2, sp->base + ZX_CFG2);
	writel(op->data.nbytes ? op->data.nbytes - 1 : 0, sp->base + ZX_COUNT);
	writel(wire.address, sp->base + ZX_ADDRESS);
	writel(op->cmd.opcode, sp->base + ZX_OPCODE);
	writel(wire.cfg, sp->base + ZX_CFG);
	writel(readl(sp->base + ZX_INIT) | ZX_FIFO_CLEAR, sp->base + ZX_INIT);
	writel(0x3f, sp->base + ZX_INT_CLEAR);
	if (bulk_write) {
		phase = "tx-prefill";
		/* Preload only immediately available space, at most 64 bytes.
		 * Do not wait for a full FIFO to drain before issuing TRIG.
		 */
		while (pos < op->data.nbytes && pos < 64) {
			last = readl(sp->base + ZX_FIFO_STATUS);
			if (ktime_get_ns() >= deadline) {
				ret = -ETIMEDOUT;
				goto fail;
			}
			if (!(last & ZX_TX_AVAILABLE))
				break;
			zx_tx_word(sp, op, &pos);
		}
	}
	writel(readl(sp->base + ZX_TRIG) | BIT(0), sp->base + ZX_TRIG);
	if (short_read) {
		/* Vendor short responses fit entirely in the FIFO. */
		phase = "done";
		ret = zx_wait_done(sp, deadline, &last);
		if (ret)
			goto fail;
	}

	if (op->data.dir == SPI_MEM_DATA_IN) {
		u8 *buf = op->data.buf.in;

		phase = "rx-fifo";
		/* Drain the finite FIFO before waiting for transfer completion. */
		while (pos < op->data.nbytes) {
			unsigned int n = min_t(unsigned int, 4, op->data.nbytes - pos);
			__le32 word;

			ret = zx_wait(sp, ZX_FIFO_STATUS, ZX_RX_AVAILABLE, deadline, &last);
			if (ret)
				goto fail;
			word = cpu_to_le32(readl(sp->base + ZX_FIFO));
			memcpy(buf + pos, &word, n);
			pos += n;
		}
	} else if (op->data.dir == SPI_MEM_DATA_OUT) {
		phase = "tx-fifo";
		while (pos < op->data.nbytes) {
			ret = zx_wait(sp, ZX_FIFO_STATUS, ZX_TX_AVAILABLE, deadline, &last);
			if (ret)
				goto fail;
			if (bulk_write) {
				zx_tx_word(sp, op, &pos);
			} else {
				/* Preserve the verified one-byte SET FEATURE write. */
				writel(*(const u8 *)op->data.buf.out, sp->base + ZX_FIFO);
				pos = 1;
			}
		}
	}

	if (!short_read) {
		phase = "done";
		ret = zx_wait_done(sp, deadline, &last);
		if (ret)
			goto fail;
	}
	if (ktime_get_ns() >= deadline) {
		phase = "deadline";
		ret = -ETIMEDOUT;
		goto fail;
	}
	return 0;

fail:
	/* A hidden RESET would invalidate SPI-NAND's cached B0 configuration.
	 * Stop this controller instead of replaying or concealing an operation.
	 */
	sp->failed = true;
	dev_err(sp->dev, "op=%02x addr=%llx phase=%s bytes=%u/%u last=%08x error=%d; controller stopped\n",
		op->cmd.opcode, op->addr.val, phase, pos, op->data.nbytes, last, ret);
	return ret;
}

static int zx_setup(struct spi_device *spi)
{
	struct zx_spifc *sp = spi_controller_get_devdata(spi->controller);

	if (spi_get_chipselect(spi, 0) || spi->bits_per_word != 8 ||
	    spi->mode & (SPI_CPOL | SPI_CPHA | SPI_CS_HIGH | SPI_LSB_FIRST | SPI_3WIRE))
		return -EINVAL;
	/* The working-clock/SCK relationship is not fully characterized.
	 * Preserve the verified boot clock profile and reject requests needing
	 * a different profile instead of pretending to set arbitrary rates.
	 */
	if (spi->max_speed_hz != sp->rate)
		return -EINVAL;
	return 0;
}

static const struct spi_controller_mem_ops zx_mem_ops = {
	.supports_op = zx_supports_op,
	.adjust_op_size = zx_adjust_op_size,
	.exec_op = zx_exec_op,
};

#ifdef CONFIG_SPI_ZX279128_PRODUCTION_POLICY
static const char *const zx_verdict_names[] = {
	[ZX_ALLOW] = "allow",
	[ZX_DENY] = "deny",
	[ZX_REFUSE_BANK_A] = "refuse-bank-a",
};

static int zx_policy_range(char *buf, int at, const char *kind, unsigned int first,
			   unsigned int end, enum zx_verdict verdict)
{
	return at + sysfs_emit_at(buf, at, "%s %08x-%08x %s\n", kind, first * 2048,
				  end * 2048 - 1, zx_verdict_names[verdict]);
}

/* Evaluate the compiled pure policy over every row, eraseblock, aliased row
 * and feature value. The text is compared on hardware with the host model
 * (tests/test_production_policy.py); it performs no flash access.
 */
static int zx_policy_map(char *buf, int at, bool qualify, int bank)
{
	static const unsigned int opcodes[] = { 0x10, 0xd8 };
	unsigned int i, row, step, first, reg, value, allowed, mask, other = 0;
	enum zx_verdict verdict, run = ZX_DENY;

	at += sysfs_emit_at(buf, at, "flavour %s\n", qualify ? "production-qualify" : "production");
	for (i = 0; i < ARRAY_SIZE(opcodes); i++) {
		step = opcodes[i] == 0xd8 ? ZX_BLOCK_ROWS : 1;
		first = 0;
		for (row = 0; row < ZX_ROWS; row += step) {
			verdict = zx_policy_row(qualify, bank, opcodes[i], row);
			if (row && verdict != run) {
				at = zx_policy_range(buf, at, i ? "erase" : "program", first, row, run);
				first = row;
			}
			run = verdict;
		}
		at = zx_policy_range(buf, at, i ? "erase" : "program", first, ZX_ROWS, run);
	}
	allowed = 0;
	for (row = 0; row < ZX_ROWS; row++)
		if (row & (ZX_BLOCK_ROWS - 1))
			allowed += zx_policy_row(qualify, bank, 0xd8, row) != ZX_DENY;
	at += sysfs_emit_at(buf, at, "erase-unaligned non-deny=%u\n", allowed);
	allowed = 0;
	for (row = ZX_ROWS; row < 2 * ZX_ROWS; row++)
		allowed += (zx_policy_row(qualify, bank, 0x10, row) != ZX_DENY) +
			   (zx_policy_row(qualify, bank, 0xd8, row) != ZX_DENY);
	allowed += (zx_policy_row(qualify, bank, 0x10, 0xffffff) != ZX_DENY) +
		   (zx_policy_row(qualify, bank, 0xd8, 0xffffc0) != ZX_DENY);
	at += sysfs_emit_at(buf, at, "row-alias non-deny=%u\n", allowed);
	for (reg = 0; reg <= 0xff; reg++) {
		allowed = mask = 0;
		for (value = 0; value <= 0xff; value++) {
			if (zx_policy_feature(reg, value) == ZX_ALLOW) {
				allowed++;
				mask |= value;
			}
		}
		if (reg == ZX_REG_BLOCK_LOCK || reg == ZX_REG_CFG)
			at += sysfs_emit_at(buf, at, "feature %02x allowed=%u or=%02x\n",
					    reg, allowed, mask);
		else
			other += allowed;
	}
	return at + sysfs_emit_at(buf, at, "feature other allowed=%u\n", other);
}

static struct zx_spifc *zx_dev_spifc(struct device *dev)
{
	return spi_controller_get_devdata(dev_get_drvdata(dev));
}

static const char *zx_policy_mode(const struct zx_spifc *sp)
{
	return sp->production_qualify ? "production-qualify" : "production";
}

static ssize_t write_policy_show(struct device *dev, struct device_attribute *attr,
				 char *buf)
{
	return sysfs_emit(buf, "%s\n", zx_policy_mode(zx_dev_spifc(dev)));
}
static DEVICE_ATTR_RO(write_policy);

static ssize_t write_policy_state_show(struct device *dev, struct device_attribute *attr,
				       char *buf)
{
	struct zx_spifc *sp = zx_dev_spifc(dev);

	return sysfs_emit(buf, "mode=%s latched=%d refusals=%u bank_a_refusals=%u first_opcode=%02x first_addr=%llx\n",
			  zx_policy_mode(sp), sp->policy_latched, sp->policy_refusals,
			  sp->bank_a_refusals, sp->latch_opcode, sp->latch_addr);
}
static DEVICE_ATTR_RO(write_policy_state);

static ssize_t write_policy_map_show(struct device *dev, struct device_attribute *attr,
				     char *buf)
{
	int at = sysfs_emit(buf, "zx279128 write policy v1 active=%s\n",
			    zx_policy_mode(zx_dev_spifc(dev)));
	int bank = zx_dev_spifc(dev)->bank;

	at = zx_policy_map(buf, at, false, bank);
	return zx_policy_map(buf, at, true, bank);
}
static DEVICE_ATTR_RO(write_policy_map);

static struct attribute *zx_policy_attrs[] = {
	&dev_attr_write_policy.attr,
	&dev_attr_write_policy_state.attr,
	&dev_attr_write_policy_map.attr,
	NULL
};

static const struct attribute_group zx_policy_group = {
	.attrs = zx_policy_attrs,
};
#endif

static int zx_probe(struct platform_device *pdev)
{
	struct device *dev = &pdev->dev;
	struct spi_controller *ctlr;
	struct zx_spifc *sp;
	struct clk *pclk, *wclk;

	if (write_test && ubi_test)
		return dev_err_probe(dev, -EINVAL, "qualification modes are mutually exclusive\n");
#ifdef CONFIG_SPI_ZX279128_PRODUCTION_POLICY
	if ((production || production_qualify) &&
	    (write_test || ubi_test || (production && production_qualify)))
		return dev_err_probe(dev, -EINVAL, "write policy modes are mutually exclusive\n");
#endif
	ctlr = devm_spi_alloc_host(dev, sizeof(*sp));
	if (!ctlr)
		return -ENOMEM;
	sp = spi_controller_get_devdata(ctlr);
	sp->dev = dev;
	sp->write_test = write_test;
	sp->ubi_test = ubi_test;
#ifdef CONFIG_SPI_ZX279128_PRODUCTION_POLICY
	sp->production = production;
	sp->production_qualify = production_qualify;
	sp->bank = zx279128_active_bank();
	if (sp->production && (sp->bank < 0 || sp->bank > 1))
		return dev_err_probe(dev, -EINVAL, "production policy requires validated active-bank mapping\n");
	/* A RAM qualification boot has no vendor selection; it refuses all
	 * firmware writes while exercising the established bank-A deny matrix.
	 */
	if (sp->production_qualify && sp->bank < 0)
		sp->bank = 0;
#endif
	sp->base = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(sp->base))
		return PTR_ERR(sp->base);
	pclk = devm_clk_get_enabled(dev, "pclk");
	if (IS_ERR(pclk))
		return dev_err_probe(dev, PTR_ERR(pclk), "cannot enable peripheral clock\n");
	wclk = devm_clk_get_enabled(dev, "wclk");
	if (IS_ERR(wclk))
		return dev_err_probe(dev, PTR_ERR(wclk), "cannot enable working clock\n");
	sp->rate = clk_get_rate(wclk);
	if (!sp->rate || sp->rate > U32_MAX)
		return dev_err_probe(dev, -EINVAL, "invalid inherited working clock\n");

	ctlr->dev.of_node = dev->of_node;
	ctlr->bus_num = -1;
	ctlr->num_chipselect = 1;
	ctlr->mode_bits = SPI_RX_DUAL;
	ctlr->bits_per_word_mask = SPI_BPW_MASK(8);
	ctlr->max_speed_hz = sp->rate;
	ctlr->setup = zx_setup;
	ctlr->mem_ops = &zx_mem_ops;
	platform_set_drvdata(pdev, ctlr);
#ifdef CONFIG_SPI_ZX279128_PRODUCTION_POLICY
	if (sp->production || sp->production_qualify) {
		int ret = devm_device_add_group(dev, &zx_policy_group);

		if (ret)
			return dev_err_probe(dev, ret, "cannot publish write policy state\n");
	}
#endif
	if (sp->ubi_test)
		dev_info(dev, "UBI WRITE TEST: bytes [05400000,06400000), rows [a800,c800), aligned erase only\n");
	else if (sp->write_test)
		dev_info(dev, "STAGING WRITE TEST: bytes [063e0000,06400000), rows [c7c0,c800), one program attempt/page\n");
#ifdef CONFIG_SPI_ZX279128_PRODUCTION_POLICY
	else if (sp->production_qualify)
		dev_info(dev, "PRODUCTION POLICY QUALIFICATION: program/erase only UBI [05400000,06400000); bank A [00700000,01740000) refused; first refusal latches\n");
	else if (sp->production)
		dev_info(dev, "production write policy: program/erase only bank %c [%08x,%08x) and UBI [05400000,06400000); first refusal latches\n",
			'A' + sp->bank, sp->bank ? 0x2000000 : 0x700000,
			sp->bank ? 0x3040000 : 0x1740000);
#endif
	else
		dev_info(dev, "inherited working clock %lu Hz; array writes disabled\n", sp->rate);
	return devm_spi_register_controller(dev, ctlr);
}

static const struct of_device_id zx_of_match[] = {
	{ .compatible = "zte,zx279128s-spifc" },
	{ }
};
MODULE_DEVICE_TABLE(of, zx_of_match);

static struct platform_driver zx_driver = {
	.probe = zx_probe,
	.driver = {
		.name = "zx279128-spifc",
		.of_match_table = zx_of_match,
		/* The qualification bitmap must not be reset by sysfs rebind. */
		.suppress_bind_attrs = true,
	},
};
module_platform_driver(zx_driver);

MODULE_DESCRIPTION("ZTE ZX279128S SPI memory controller, read-only prototype");
MODULE_LICENSE("GPL");
