/* SPDX-License-Identifier: GPL-2.0-only */
#ifndef _LINUX_SOC_ZTE_ZX279128_BOOT_H
#define _LINUX_SOC_ZTE_ZX279128_BOOT_H

#include <linux/init.h>

/* Unknown is negative; callers must never turn it into bank A by default. */
int zx279128_active_bank(void);
void __init zx279128_init_boot_bank(void);

#endif
