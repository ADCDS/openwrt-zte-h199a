/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef SPINAND_DIAGNOSTIC_H
#define SPINAND_DIAGNOSTIC_H

/* Included after the SPI-NAND and module definitions in core.c. */
#ifdef CONFIG_MTD_SPI_NAND_DIAGNOSTIC
static bool diagnostic_write_guard;
module_param(diagnostic_write_guard, bool, 0444);
MODULE_PARM_DESC(diagnostic_write_guard,
	"qualification: forbid bad-block marking and latch the first write/erase failure");

static inline void spinand_diag_init(struct spinand_device *spinand)
{
	spinand->diagnostic_guard = diagnostic_write_guard;
	if (spinand->diagnostic_guard)
		dev_info(&spinand->spimem->spi->dev,
			 "diagnostic mutation guard: no bad-block marking; stop on write/erase failure\n");
}

static inline bool spinand_diag_no_markbad(struct spinand_device *spinand)
{
	return spinand->diagnostic_guard;
}

static inline int spinand_diag_enter(struct spinand_device *spinand)
{
	lockdep_assert_held(&spinand->lock);
	return spinand->diagnostic_guard && spinand->diagnostic_failed ? -EROFS : 0;
}

static inline int spinand_diag_complete(struct spinand_device *spinand,
				       loff_t offset, int ret, const char *operation)
{
	lockdep_assert_held(&spinand->lock);
	if (!ret || !spinand->diagnostic_guard)
		return ret;
	if (!spinand->diagnostic_failed) {
		spinand->diagnostic_failed = true;
		spinand->diagnostic_errno = ret;
		spinand->diagnostic_offset = offset;
		dev_err(&spinand->spimem->spi->dev,
			"diagnostic %s failure at %#llx: %d; later mutations disabled\n",
			operation, (unsigned long long)offset, ret);
	}
	/* Do not authorize UBI's EIO recovery onto another eraseblock. */
	return -EROFS;
}
#elif defined(CONFIG_MTD_SPI_NAND_FAIL_STOP)
/*
 * Production fail-stop, always on. Bank A must never receive a bad-block
 * marker: the vendor bootloader and OpenWrt's mtd writer would then skip
 * different blocks and the CRC-checked image would no longer line up. In the
 * UBI window the first program/erase failure already stops all mutations,
 * so torture-and-mark could only follow a fault this build cannot yet tell
 * apart from a transport problem. Keep the evidence; retire nothing.
 */
static inline void spinand_diag_init(struct spinand_device *spinand)
{
	dev_info(&spinand->spimem->spi->dev,
		 "production fail-stop: no bad-block marking; first program/erase failure stops mutations until reboot\n");
}

static inline bool spinand_diag_no_markbad(struct spinand_device *spinand)
{
	return true;
}

static inline int spinand_diag_enter(struct spinand_device *spinand)
{
	lockdep_assert_held(&spinand->lock);
	return spinand->failstop_latched ? -EROFS : 0;
}

static inline int spinand_diag_complete(struct spinand_device *spinand,
				       loff_t offset, int ret, const char *operation)
{
	lockdep_assert_held(&spinand->lock);
	if (!ret)
		return 0;
	if (!spinand->failstop_latched) {
		spinand->failstop_latched = true;
		spinand->failstop_errno = ret;
		spinand->failstop_offset = offset;
		dev_err(&spinand->spimem->spi->dev,
			"%s failure at %#llx: %d; program/erase refused until reboot\n",
			operation, (unsigned long long)offset, ret);
	}
	/* Do not authorize UBI's EIO recovery onto another eraseblock. */
	return -EROFS;
}
#else
static inline void spinand_diag_init(struct spinand_device *spinand) { }
static inline bool spinand_diag_no_markbad(struct spinand_device *spinand)
{
	return false;
}
static inline int spinand_diag_enter(struct spinand_device *spinand) { return 0; }
static inline int spinand_diag_complete(struct spinand_device *spinand,
				       loff_t offset, int ret, const char *operation)
{
	return ret;
}
#endif

#endif
