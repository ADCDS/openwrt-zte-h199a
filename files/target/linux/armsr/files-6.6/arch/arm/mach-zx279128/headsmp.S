/* SPDX-License-Identifier: GPL-2.0 */
/*
 * SMP trampoline for the ZTE/Sanechips ZX279128S.
 *
 * This is a faithful reimplementation of the vendor stub found at VA
 * 0xc057826c in the stock ZX279128S vmlinux (Linux 4.1.25). Assembling
 * this file reproduces those 0x44 bytes exactly.
 *
 * Copied into on-chip SRAM ("zte,zx279128s-smp-sram", phys 0x200800) by
 * zx_smp_prepare_cpus(), which patches the two data words:
 *
 *   +0x04  physical address of secondary_startup
 *   +0x08  physical address of zx_pen_release
 *
 * IMPORTANT: the vendor stub does NOT use WFE. It is a pure polling
 * spin. Using WFE here loses the wakeup, because the SEV issued by
 * smp_prepare_cpus() races with CPU1 still being inside the BootROM pen:
 * ARM's event register is one-shot, so a WFE entered after the SEV was
 * consumed blocks forever. Do not "optimise" this loop with WFE.
 *
 * Runs from SRAM with the MMU and caches off, so it must be position
 * independent and must not touch anything outside these words.
 */
#include <linux/linkage.h>
#include <linux/init.h>

	.arm
	.align	2

ENTRY(zx_secondary_trampoline)
	b	1f			@ +0x00 skip over the patch words
	.word	0			@ +0x04: secondary entry (physical)
	.word	0			@ +0x08: &pen_release (physical)
	.word	0x34			@ +0x0c: size word (vendor parity)
1:
	mrc	p15, 0, r0, c0, c0, 5	@ MPIDR
	and	r0, r0, #15		@ our CPU id
	adr	r1, zx_secondary_trampoline
2:
	ldr	r7, [r1, #8]		@ &pen_release (physical)
	ldr	r7, [r7]		@ *pen_release
	cmp	r7, r0
	bne	2b			@ spin (no WFE -- see comment above)
	ldr	r1, [r1, #4]		@ secondary entry (physical)
	mov	pc, r1			@ enter secondary_startup, MMU off
3:
	b	3b			@ safety trap
ENTRY(zx_secondary_trampoline_end)
