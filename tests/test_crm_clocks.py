"""The ZX279128S CRM clock/reset provider against a register model.

clk-zx279128-crm.c replaced the single-register zte,zx279128s-spi-clocks
driver. The SPI flash controller it clocks is what the board boots from, so
the replacement must not change a single clock parameter, and it must never
gate a clock that is on at boot (an access to an unclocked block hangs this
SoC with no oops).

The whole driver source is compiled verbatim; only its <linux/...> includes
are replaced by boundary stubs, and the exact set removed is asserted. The
stubs record every clock registration (name, parent, flags, physical
register, bit/shift/width, divider flags) instead of running the clock core.
That record is compared with:
  - frozen constants taken from the replaced driver, and
  - the replaced driver itself, taken from git history and run through the
    same model, so a drift on either side is visible.
The reset controller ops run against a model of CRM1+0x74.

The device tree is compiled with the kernel's own dtc and checked against
what the driver expects.

This proves the software contract, not silicon behaviour. In particular the
clock core is NOT run here: what it does with CLK_IS_CRITICAL (enable at
registration, never disable) is the 6.6 core's documented behaviour.
"""
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest

import dt_fixture as fx

ROOT = fx.ROOT
TARGET = ROOT / 'files/target/linux/armsr'
SOURCE = fx.FILES / 'drivers/clk/clk-zx279128-crm.c'
CLK_HEADER = fx.INCLUDE_DIR / 'dt-bindings/clock/zte,zx279128s-crm.h'
RST_HEADER = fx.INCLUDE_DIR / 'dt-bindings/reset/zte,zx279128s-crm.h'
PATCH = TARGET / 'patches-6.6/995-zx279128-crm.patch'
SPI_PATCH = TARGET / 'patches-6.6/995-zx279128-native-spi.patch'
POLICY_PATCH = TARGET / 'patches-6.6/996-zx279128-spi-production-policy.patch'
CONFIG = TARGET / 'config-6.6'
DTS = fx.DTS_DIR / (fx.BASE_DTS + '.dts')
TARBALL = ROOT / 'openwrt/dl/linux-6.6.151.tar.xz'

# The replaced driver, at the last commit that changed it.
OLD_COMMIT = '954922e'
OLD_SOURCE = 'files/target/linux/armsr/files-6.6/drivers/clk/clk-zx279128-spi.c'
OLD_HEADER = 'files/target/linux/armsr/files-6.6/include/dt-bindings/clock/zte,zx279128s-spi.h'

TOPCRM, CRM1, LSP0, LSP1 = 0x94000000, 0x94100000, 0x94400000, 0x9a100000

# 6.6 include/linux/clk-provider.h
CLK_SET_RATE_GATE = 1 << 0
CLK_GET_RATE_NOCACHE = 1 << 6
CLK_IS_CRITICAL = 1 << 11
CLK_DIVIDER_READ_ONLY = 1 << 5

# Frozen from clk-zx279128-spi.c (commit 954922e). One row per registration:
# (kind, name suffix, parent, flags, physical register, bit or shift, width,
#  gate/divider flags). Parent 'fw0'/'fw1' is clk_parent_data index 0/1.
FROZEN = [
    ('gate', 'wclk-parent', 'fw0', CLK_IS_CRITICAL, TOPCRM + 0x14, 13, 1, 0),
    ('gate', 'pclk-parent', 'fw1', CLK_IS_CRITICAL, TOPCRM + 0x14, 11, 1, 0),
    ('div', 'spi-divider', 'wclk-parent', CLK_GET_RATE_NOCACHE | CLK_SET_RATE_GATE,
     LSP0 + 0x18, 11, 6, 0),
    ('gate', 'spi-wclk', 'spi-divider', 0, LSP0 + 0x18, 1, 1, 0),
    ('gate', 'spi-pclk', 'pclk-parent', 0, LSP0 + 0x18, 0, 1, 0),
]
# The one deliberate difference: the two SPI gates are on at boot, so the
# new driver makes them critical too (a failed or deferred SPI probe must not
# let clk_disable_unused gate the boot flash controller).
# Then the consumers wired after the provider was boot-qualified. Each row is
# an entry of the stock kernel's own clock tables, decoded from the stock
# vmlinux (zx279127_top_clocks_init / _lsp0_ / _lsp1_, see VENDOR below),
# restricted to clocks a node in this device tree takes.
ADDED = [
    ('gate', 'gpio-pclk', 'pclk-parent', CLK_IS_CRITICAL, LSP0 + 0x1c, 0, 1, 0),
    ('gate', 'lsp1-wclk', 'fw0', CLK_IS_CRITICAL, TOPCRM + 0x14, 7, 1, 0),
    ('gate', 'lsp1-pclk', 'fw1', CLK_IS_CRITICAL, TOPCRM + 0x14, 5, 1, 0),
    ('div', 'mdio-divider', 'lsp1-wclk', CLK_GET_RATE_NOCACHE,
     LSP1 + 0x04, 11, 7, CLK_DIVIDER_READ_ONLY),
    ('gate', 'mdio-wclk', 'mdio-divider', CLK_IS_CRITICAL, LSP1 + 0x04, 1, 1, 0),
    ('gate', 'mdio-pclk', 'lsp1-pclk', CLK_IS_CRITICAL, LSP1 + 0x04, 0, 1, 0),
]
EXPECTED = [row if row[1] not in ('spi-wclk', 'spi-pclk')
            else row[:3] + (CLK_IS_CRITICAL,) + row[4:] for row in FROZEN] + ADDED

# The stock kernel's registrations for the same fields: (kind, register,
# bit or shift, width, gate/divider flags, parent), name -> row. Decoded
# from h199a-firmware/stock-vmlinux-ecc.raw with its kallsyms: the
# clk_register_gate/_divider calls in zx279127_top_clocks_init (TOPCRM),
# zx279127_lsp0_clocks_init and zx279127_lsp1_clocks_init. Stock registers
# every gate CLK_IGNORE_UNUSED (0x8) and every divider with flags 0;
# lb_lsp0_100m_wclk and lb_lsp1_100m_wclk share the parent clk_100m, and
# lb_lsp0_apb_pclk and lb_lsp1_apb_pclk share matrix_pclk.
VENDOR = {
    'wclk-parent': ('gate', TOPCRM + 0x14, 13, 1, 0, 'clk_100m'),       # lb_lsp0_100m_wclk
    'pclk-parent': ('gate', TOPCRM + 0x14, 11, 1, 0, 'matrix_pclk'),    # lb_lsp0_apb_pclk
    'lsp1-wclk': ('gate', TOPCRM + 0x14, 7, 1, 0, 'clk_100m'),          # lb_lsp1_100m_wclk
    'lsp1-pclk': ('gate', TOPCRM + 0x14, 5, 1, 0, 'matrix_pclk'),       # lb_lsp1_apb_pclk
    'spi-divider': ('div', LSP0 + 0x18, 11, 6, 0, 'lb_lsp0_100m_wclk'),  # fb_spi_wclk_div
    'spi-wclk': ('gate', LSP0 + 0x18, 1, 1, 0, 'fb_spi_wclk_div'),       # fb_spi_wclk
    'spi-pclk': ('gate', LSP0 + 0x18, 0, 1, 0, 'lb_lsp0_apb_pclk'),      # fb_spi_pclk
    'gpio-pclk': ('gate', LSP0 + 0x1c, 0, 1, 0, 'lb_lsp0_apb_pclk'),     # fb_gpio_pclk
    'mdio-divider': ('div', LSP1 + 0x04, 11, 7, 0, 'lb_lsp1_100m_wclk'),  # fb_mdio_wclk_div
    'mdio-wclk': ('gate', LSP1 + 0x04, 1, 1, 0, 'fb_mdio_wclk_div'),      # fb_mdio_wclk
    'mdio-pclk': ('gate', LSP1 + 0x04, 0, 1, 0, 'lb_lsp1_apb_pclk'),      # fb_mdio_pclk
}
# Our parent name for each stock parent name.
VENDOR_PARENT = {'clk_100m': 'fw0', 'matrix_pclk': 'fw1',
                 'lb_lsp0_100m_wclk': 'wclk-parent', 'lb_lsp0_apb_pclk': 'pclk-parent',
                 'lb_lsp1_100m_wclk': 'lsp1-wclk', 'lb_lsp1_apb_pclk': 'lsp1-pclk',
                 'fb_spi_wclk_div': 'spi-divider', 'fb_mdio_wclk_div': 'mdio-divider'}

# Boot state. TOPCRM+0x14, LSP0CRPM+0x18 and +0x1c are the values U-Boot
# leaves, measured on the bench (docs/BRINGUP.md, "Boot-inherited
# clock-controller state"): every modelled TOPCRM gate (13, 11, 7, 5), both
# SPI gates with divider field 1, and the GPIO gate are on.
#
# LSP1CRPM+0x04 was NEVER MEASURED. The MDIO bus works on every boot with
# nothing touching that register, so both gates are modelled on; the divider
# field is an arbitrary stand-in (the divider is read-only and never written).
# This is the one input here that is an assumption, not a measurement.
BOOT_TOPCRM_14 = 0xcffffbf7
BOOT_LSP0_18 = 0x0400081b
BOOT_LSP0_1C = 0x00000009
BOOT_LSP1_04 = (0x13 << 11) | 0x3
BOOT_CRM1_74 = 0x3f

LINUX_INCLUDES = {'linux/clk-provider.h', 'linux/io.h', 'linux/module.h', 'linux/of.h',
                  'linux/platform_device.h', 'linux/reset-controller.h', 'linux/sizes.h',
                  'linux/slab.h', 'linux/spinlock.h'}
OLD_INCLUDES = {'linux/clk-provider.h', 'linux/module.h', 'linux/of.h',
                'linux/platform_device.h', 'linux/slab.h'}

PRELUDE = r'''
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
typedef uint64_t u64;
typedef uint32_t resource_size_t;
#define __iomem
#define BIT(n) (1U << (n))
#define SZ_4K 0x1000
#define GFP_KERNEL 0x10
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define IOMEM_ERR_PTR(e) ERR_PTR(e)
#define THIS_MODULE ((struct module *)0)
#define IORESOURCE_MEM 0x200
#define container_of(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define struct_size(p, member, n) (sizeof(*(p)) + (n) * sizeof((p)->member[0]))
#define CLK_SET_RATE_GATE BIT(0)
#define CLK_GET_RATE_NOCACHE BIT(6)
#define CLK_IS_CRITICAL BIT(11)
#define CLK_DIVIDER_READ_ONLY BIT(5)
#define MODULE_DEVICE_TABLE(a, b)
#define MODULE_DESCRIPTION(s)
#define MODULE_LICENSE(s)
#define module_platform_driver(d) static struct platform_driver *registered_driver = &d;
#define builtin_platform_driver(d) static struct platform_driver *registered_driver = &d;
#define PRINTF(f, a) __attribute__((format(printf, f, a)))
struct module;
typedef struct { int held; } spinlock_t;
static unsigned lock_depth;
#define spin_lock_init(l) ((l)->held = 0)
#define spin_lock_irqsave(l, f) do { assert(!(l)->held); (l)->held = 1; lock_depth++; (f) = 0; } while (0)
#define spin_unlock_irqrestore(l, f) do { assert((l)->held); (l)->held = 0; lock_depth--; (void)(f); } while (0)
struct device_node { int unused; };
struct device { struct device_node *of_node; const char *name; };
struct resource { resource_size_t start, end; const char *name; };
struct platform_device { struct device dev; struct resource *res; unsigned nres; };
struct of_device_id { char compatible[128]; };
struct device_driver { const char *name; const struct of_device_id *of_match_table; bool suppress_bind_attrs; };
struct platform_driver { int (*probe)(struct platform_device *); struct device_driver driver; };
struct clk_hw { int id; };
struct clk_hw_onecell_data { unsigned int num; struct clk_hw *hws[]; };
struct clk_parent_data { const struct clk_hw *hw; const char *fw_name; const char *name; int index; };
struct of_phandle_args;
struct reset_controller_dev;
struct reset_control_ops {
 int (*reset)(struct reset_controller_dev *, unsigned long);
 int (*assert)(struct reset_controller_dev *, unsigned long);
 int (*deassert)(struct reset_controller_dev *, unsigned long);
 int (*status)(struct reset_controller_dev *, unsigned long);
};
struct reset_controller_dev {
 const struct reset_control_ops *ops;
 struct module *owner;
 struct device *dev;
 struct device_node *of_node;
 int of_reset_n_cells;
 unsigned int nr_resets;
};
static inline resource_size_t resource_size(const struct resource *r) { return r->end - r->start + 1; }
static const char *dev_name(const struct device *d) { return d->name; }
'''

MODEL = r'''
/* Three 4 KiB windows. Every MMIO access must land inside one of them. */
static u32 topcrm[0x400], crm1[0x400], lsp0[0x400], lsp1[0x400];
struct window { u32 phys; u32 *mem; } windows[] = {
 { 0x94000000, topcrm }, { 0x94100000, crm1 }, { 0x94400000, lsp0 }, { 0x9a100000, lsp1 },
};
#define NWIN 4
static unsigned reads, writes, maps, regs, providers, resets_registered, errors;
static int fail_alloc_at = -1, allocs;
static u32 phys_of(const volatile void *p) {
 for (unsigned i = 0; i < NWIN; i++) {
  const char *b = (const char *)windows[i].mem;
  if ((const char *)p >= b && (const char *)p < b + 0x1000) {
   assert(((const char *)p - b) % 4 == 0);
   return windows[i].phys + (u32)((const char *)p - b);
  }
 }
 assert(!"MMIO outside the modelled CRM windows");
 return 0;
}
static u32 *cell(const volatile void *p) {
 u32 phys = phys_of(p);
 for (unsigned i = 0; i < NWIN; i++)
  if (phys >= windows[i].phys && phys < windows[i].phys + 0x1000)
   return &windows[i].mem[(phys - windows[i].phys) / 4];
 return NULL;
}
static u32 readl(const volatile void *p) { reads++; return *cell(p); }
static void writel(u32 v, volatile void *p) { assert(lock_depth); writes++; *cell(p) = v; }

static void *devm_kzalloc(struct device *d, size_t n, int gfp) {
 assert(gfp == GFP_KERNEL && d);
 if (allocs++ == fail_alloc_at)
  return NULL;
 return calloc(1, n);
}
static PRINTF(3, 4) char *devm_kasprintf(struct device *d, int gfp, const char *fmt, ...) {
 char *s = devm_kzalloc(d, 128, gfp);
 va_list ap;
 if (!s)
  return NULL;
 va_start(ap, fmt);
 vsnprintf(s, 128, fmt, ap);
 va_end(ap);
 return s;
}
static PRINTF(3, 4) int dev_err_probe(const struct device *d, int err, const char *fmt, ...) { errors++; return err; }

static struct resource *platform_get_resource_byname(struct platform_device *p, unsigned type, const char *name) {
 assert(type == IORESOURCE_MEM);
 for (unsigned i = 0; i < p->nres; i++)
  if (!strcmp(p->res[i].name, name))
   return &p->res[i];
 return NULL;
}
static void *map_phys(u32 phys, u32 size) {
 for (unsigned i = 0; i < NWIN; i++)
  if (phys >= windows[i].phys && phys + size <= windows[i].phys + 0x1000)
   return (char *)windows[i].mem + (phys - windows[i].phys);
 assert(!"map outside the modelled windows");
 return NULL;
}
/* Mapping without claiming: the new driver's only way in. */
static void *devm_ioremap(struct device *d, resource_size_t start, resource_size_t size) {
 maps++;
 return map_phys(start, size);
}
/* Claiming map, used by the replaced driver only. */
static unsigned claims;
static void *devm_platform_ioremap_resource_byname(struct platform_device *p, const char *name) {
 struct resource *r = platform_get_resource_byname(p, IORESOURCE_MEM, name);
 if (!r)
  return ERR_PTR(-EINVAL);
 claims++;
 return map_phys(r->start, resource_size(r));
}

/* Registration record. */
struct rec { char kind[8]; char name[64]; char parent[64]; unsigned long flags; u32 phys; unsigned bit, width, cflags; };
static struct rec rec[24];
static struct clk_hw hw_pool[24];
static const char *names[24];
static spinlock_t *locks[24];
static const char *suffix(const char *n) { const char *dot = strrchr(n, '.'); return dot ? dot + 1 : n; }
static const char *hw_name(const struct clk_hw *hw) {
 assert(hw >= hw_pool && hw < hw_pool + regs);
 return suffix(names[hw - hw_pool]);
}
static struct clk_hw *record(const char *kind, const char *name, const char *parent, unsigned long flags,
                             void *reg, unsigned bit, unsigned width, unsigned cflags, spinlock_t *lock) {
 assert(regs < 24 && name && lock);
 struct rec *r = &rec[regs];
 snprintf(r->kind, sizeof(r->kind), "%s", kind);
 snprintf(r->name, sizeof(r->name), "%s", suffix(name));
 snprintf(r->parent, sizeof(r->parent), "%s", parent);
 r->flags = flags; r->phys = phys_of(reg); r->bit = bit; r->width = width; r->cflags = cflags;
 names[regs] = name; locks[regs] = lock;
 return &hw_pool[regs++];
}
static struct clk_hw *__devm_clk_hw_register_gate(struct device *d, struct device_node *np, const char *name,
  const char *parent_name, const struct clk_hw *parent_hw, const struct clk_parent_data *pd,
  unsigned long flags, void *reg, u8 bit, u8 gflags, spinlock_t *lock) {
 char parent[64];
 assert(!np && !!parent_name + !!parent_hw + !!pd == 1);
 if (pd) {
  assert(!pd->hw && !pd->fw_name && !pd->name);
  snprintf(parent, sizeof(parent), "fw%d", pd->index);
 } else if (parent_hw) {
  snprintf(parent, sizeof(parent), "%s", hw_name(parent_hw));
 } else {
  snprintf(parent, sizeof(parent), "%s", suffix(parent_name));
 }
 return record("gate", name, parent, flags, reg, bit, 1, gflags, lock);
}
#define devm_clk_hw_register_gate(dev, name, parent_name, flags, reg, bit, gflags, lock) \
 __devm_clk_hw_register_gate(dev, NULL, name, parent_name, NULL, NULL, flags, reg, bit, gflags, lock)
#define devm_clk_hw_register_gate_parent_data(dev, name, pd, flags, reg, bit, gflags, lock) \
 __devm_clk_hw_register_gate(dev, NULL, name, NULL, NULL, pd, flags, reg, bit, gflags, lock)
static struct clk_hw *devm_clk_hw_register_divider_parent_hw(struct device *d, const char *name,
  const struct clk_hw *parent, unsigned long flags, void *reg, u8 shift, u8 width, u8 dflags, spinlock_t *lock) {
 return record("div", name, hw_name(parent), flags, reg, shift, width, dflags, lock);
}
static struct clk_hw_onecell_data *provided;
struct of_phandle_args;
static struct clk_hw *of_clk_hw_onecell_get(struct of_phandle_args *spec, void *data) { return NULL; }
typedef struct clk_hw *(*onecell_get_t)(struct of_phandle_args *, void *);
static int provider_error, reset_error;
static int devm_of_clk_add_hw_provider(struct device *d, onecell_get_t get, struct clk_hw_onecell_data *data) {
 assert(get == of_clk_hw_onecell_get);
 providers++;
 provided = data;
 return provider_error;
}
static struct reset_controller_dev *rcdev;
static int devm_reset_controller_register(struct device *d, struct reset_controller_dev *r) {
 resets_registered++;
 rcdev = r;
 return reset_error;
}
'''

# Shared Python-side driver of the C model: print the registration record.
DUMP = r'''
static void dump(void) {
 for (unsigned i = 0; i < regs; i++)
  printf("REC %s %s %s %lu %u %u %u %u\n", rec[i].kind, rec[i].name, rec[i].parent,
         rec[i].flags, rec[i].phys, rec[i].bit, rec[i].width, rec[i].cflags);
}
static void boot_state(void) {
 memset(topcrm, 0, sizeof(topcrm)); memset(crm1, 0, sizeof(crm1));
 memset(lsp0, 0, sizeof(lsp0)); memset(lsp1, 0, sizeof(lsp1));
 topcrm[0x14 / 4] = BOOT_TOPCRM_14;
 lsp0[0x18 / 4] = BOOT_LSP0_18;
 lsp0[0x1c / 4] = BOOT_LSP0_1C;
 lsp1[0x04 / 4] = BOOT_LSP1_04;
 crm1[0x74 / 4] = BOOT_CRM1_74;
 reads = writes = maps = regs = providers = resets_registered = errors = claims = 0;
 allocs = 0; fail_alloc_at = -1; provider_error = reset_error = 0;
 provided = NULL; rcdev = NULL;
}
'''

NEW_CASES = r'''
static struct device_node node;
static struct resource good[] = {
 { 0x94000000, 0x94000fff, "topcrm" }, { 0x94100000, 0x941000ff + 0xf00, "crm1" },
 { 0x94400000, 0x94400fff, "lsp0crpm" }, { 0x9a100000, 0x9a100fff, "lsp1crpm" },
};
#define NRES 4
static struct platform_device pdev = { { &node, "94000000.clock-controller" }, good, NRES };
static unsigned rec_index(const char *name) {
 unsigned p;
 for (p = 0; p < regs && strcmp(rec[p].name, name); p++) ;
 assert(p < regs);
 return p;
}
/* Reference rate model: fixed parents, gates pass the rate, a divider with
 * flags 0 divides by field + 1 rounding up (6.6 divider_recalc_rate). */
static u32 rate_of_rec(unsigned i) {
 const u32 fw[2] = { 100000000, 125000000 };
 struct rec *r = &rec[i];
 u32 rate = !strncmp(r->parent, "fw", 2) ? fw[r->parent[2] - '0'] : rate_of_rec(rec_index(r->parent));
 if (!strcmp(r->kind, "div")) {
  u32 field = (*cell(map_phys(r->phys, 4)) >> r->bit) & ((1U << r->width) - 1);
  assert(r->cflags == 0 || r->cflags == CLK_DIVIDER_READ_ONLY);
  rate = (rate + field) / (field + 1);
 }
 return rate;
}
static u32 rate_of(unsigned idx) { return rate_of_rec(provided->hws[idx] - hw_pool); }
int main(void) {
 boot_state();
 assert(registered_driver->probe(&pdev) == 0);
 /* Probe maps three whole windows, claims nothing, and touches no register. */
 assert(maps == NRES && !claims && !reads && !writes && providers == 1 && resets_registered == 1 && !errors);
 assert(topcrm[0x14 / 4] == BOOT_TOPCRM_14 && lsp0[0x18 / 4] == BOOT_LSP0_18 && crm1[0x74 / 4] == BOOT_CRM1_74);
 assert(lsp0[0x1c / 4] == BOOT_LSP0_1C && lsp1[0x04 / 4] == BOOT_LSP1_04);
 /* All registrations share one lock. */
 for (unsigned i = 1; i < regs; i++)
  assert(locks[i] == locks[0]);
 /* Provider table: index -> clock. */
 /* Every slot of the provider table is filled: print it for Python. */
 for (unsigned i = 0; i < provided->num; i++) {
  assert(provided->hws[i]);
  printf("HWS %u %s\n", i, hw_name(provided->hws[i]));
 }
 printf("RATE wclk %u\nRATE pclk %u\n", rate_of(ZX_CRM_SPI_WCLK), rate_of(ZX_CRM_SPI_PCLK));
 printf("RATE mdio-wclk %u\nRATE gpio-pclk %u\n", rate_of(ZX_CRM_MDIO_WCLK), rate_of(ZX_CRM_GPIO_PCLK));
 /* Every gate that the boot state has on is critical. */
 for (unsigned i = 0; i < regs; i++) {
  if (strcmp(rec[i].kind, "gate"))
   continue;
  u32 v = *cell(map_phys(rec[i].phys, 4));
  printf("GATE %s on=%u critical=%u\n", rec[i].name, (v >> rec[i].bit) & 1,
         !!(rec[i].flags & CLK_IS_CRITICAL));
 }
 dump();

 /* Reset controller: one cell, two lines, bits 0 and 3 of CRM1+0x74. */
 assert(rcdev && rcdev->nr_resets == 2 && rcdev->of_node == &node && rcdev->dev == &pdev.dev);
 assert(rcdev->ops->assert && rcdev->ops->deassert && rcdev->ops->status && !rcdev->ops->reset);
 assert(!rcdev->of_reset_n_cells); /* core default: 1 cell, simple xlate */
 const unsigned bits[2] = { 0, 3 };
 for (unsigned id = 0; id < 2; id++) {
  crm1[0x74 / 4] = 0xffffffff;
  writes = 0;
  assert(rcdev->ops->status(rcdev, id) == 0);
  assert((rcdev->ops->assert)(rcdev, id) == 0);
  assert(crm1[0x74 / 4] == ~BIT(bits[id]) && writes == 1 && !lock_depth);
  assert(rcdev->ops->status(rcdev, id) == 1);
  crm1[0x74 / 4] = 0;
  assert(rcdev->ops->deassert(rcdev, id) == 0);
  assert(crm1[0x74 / 4] == BIT(bits[id]) && !lock_depth);
  assert(rcdev->ops->status(rcdev, id) == 0);
  printf("RESET %u bit %u\n", id, bits[id]);
 }
 /* Other CRM words untouched by the reset ops. */
 assert(topcrm[0x14 / 4] == BOOT_TOPCRM_14 && lsp0[0x18 / 4] == BOOT_LSP0_18);
 assert(lsp0[0x1c / 4] == BOOT_LSP0_1C && lsp1[0x04 / 4] == BOOT_LSP1_04);

 /* Failure paths: no register access, no partial provider. */
 for (unsigned m = 0; m < NRES; m++) {
  struct resource r[NRES];
  memcpy(r, good, sizeof(r));
  r[m].name = "absent";
  struct platform_device p = { { &node, "x" }, r, NRES };
  boot_state();
  assert(registered_driver->probe(&p) == -EINVAL && !regs && !providers && !resets_registered);
  assert(!reads && !writes && errors == 1);
 }
 {
  struct resource r[NRES];
  memcpy(r, good, sizeof(r));
  r[1].end = r[1].start + 0x7f; /* a single-register slice is refused */
  struct platform_device p = { { &node, "x" }, r, NRES };
  boot_state();
  assert(registered_driver->probe(&p) == -EINVAL && !regs && !providers && !reads && !writes);
 }
 /* Every allocation (the state, the table and each clock name) can fail. */
 int f;
 for (f = 0; f < 32; f++) {
  boot_state();
  fail_alloc_at = f;
  int ret = registered_driver->probe(&pdev);
  if (!ret)
   break;
  assert(ret == -ENOMEM && !providers && !reads && !writes);
 }
 assert(f == 13); /* 2 + one name for each of the 11 registrations */
 boot_state();
 provider_error = -EBUSY;
 assert(registered_driver->probe(&pdev) == -EBUSY && !resets_registered && !writes);
 boot_state();
 reset_error = -EBUSY;
 assert(registered_driver->probe(&pdev) == -EBUSY && !writes);

 assert(!strcmp(registered_driver->driver.of_match_table[0].compatible, "zte,zx279128s-crm"));
 assert(!registered_driver->driver.of_match_table[1].compatible[0]);
 assert(registered_driver->driver.suppress_bind_attrs);
 return 0;
}
'''

OLD_CASES = r'''
static struct device_node node;
static struct resource good[] = { { 0x94400018, 0x9440001b, "spi" }, { 0x94000014, 0x94000017, "parents" } };
static struct platform_device pdev = { { &node, "94400018.clock-controller" }, good, 2 };
int main(void) {
 boot_state();
 assert(registered_driver->probe(&pdev) == 0 && !reads && !writes && claims == 2);
 dump();
 return 0;
}
'''


def strip_linux_includes(test, text, expected):
    found = set(re.findall(r'^#include <(linux/[^>]+)>$', text, re.M))
    test.assertEqual(found, expected, 'driver includes changed: update the boundary stubs')
    return re.sub(r'^#include <linux/[^>]+>\n', '', text, flags=re.M)


def run_c(test, code, include_dirs):
    with tempfile.TemporaryDirectory() as directory:
        source, executable = Path(directory) / 'crm.c', Path(directory) / 'crm'
        source.write_text(code)
        args = ['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                '-Wno-unused-function', '-Wno-missing-field-initializers']
        for inc in include_dirs:
            args += ['-I', str(inc)]
        run = subprocess.run(args + [str(source), '-o', str(executable)],
                             capture_output=True, text=True)
        test.assertEqual(run.returncode, 0, run.stderr)
        run = subprocess.run([str(executable)], capture_output=True, text=True, timeout=20)
        test.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return run.stdout


def boot_defines():
    return (f'#define BOOT_TOPCRM_14 0x{BOOT_TOPCRM_14:08x}U\n'
            f'#define BOOT_LSP0_18 0x{BOOT_LSP0_18:08x}U\n'
            f'#define BOOT_LSP0_1C 0x{BOOT_LSP0_1C:08x}U\n'
            f'#define BOOT_LSP1_04 0x{BOOT_LSP1_04:08x}U\n'
            f'#define BOOT_CRM1_74 0x{BOOT_CRM1_74:08x}U\n')


def records(output):
    rows = []
    for line in output.splitlines():
        if line.startswith('REC '):
            kind, name, parent, *nums = line.split()[1:]
            flags, phys, bit, width, cflags = map(int, nums)
            rows.append((kind, name, parent, flags, phys, bit, width, cflags))
    return rows


def git_show(path):
    run = subprocess.run(['git', '-C', str(ROOT), 'show', f'{OLD_COMMIT}:{path}'],
                         capture_output=True, text=True)
    return run.stdout if run.returncode == 0 else None


class CrmDriverModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SOURCE.read_text()

    def new_output(self):
        body = strip_linux_includes(self, self.text, LINUX_INCLUDES)
        return run_c(self, PRELUDE + boot_defines() + MODEL + DUMP + body + NEW_CASES,
                     [fx.INCLUDE_DIR])

    def test_registrations_match_the_frozen_constants(self):
        self.assertEqual(records(self.new_output()), EXPECTED)

    def test_every_gate_on_at_boot_is_critical(self):
        """The safety property: nothing that is on today can be gated."""
        gates = [l.split() for l in self.new_output().splitlines() if l.startswith('GATE ')]
        self.assertEqual(len(gates), 9)
        for _, name, on, critical in gates:
            with self.subTest(gate=name):
                self.assertEqual(on, 'on=1', 'boot model has this gate off')
                self.assertEqual(critical, 'critical=1')
        # And no CLK_IGNORE_UNUSED-style half measure or gate-flag inversion.
        for row in records(self.new_output()):
            if row[0] == 'gate':
                self.assertTrue(row[3] & CLK_IS_CRITICAL, row)
                self.assertEqual(row[7], 0, f'{row[1]}: gate flags must stay 0 (set-to-enable)')

    def test_rates_are_unchanged(self):
        out = self.new_output()
        rates = dict(l.split()[1:] for l in out.splitlines() if l.startswith('RATE '))
        # field 1 -> 100 MHz / 2; pclk passes the 125 MHz APB reference.
        # GPIO gets the APB reference; MDIO's divider is read-only and its
        # rate is whatever the inherited field says (the model's stand-in).
        self.assertEqual(rates, {'wclk': '50000000', 'pclk': '125000000',
                                 'mdio-wclk': str(-(-100000000 // (((BOOT_LSP1_04 >> 11) & 0x7f) + 1))),
                                 'gpio-pclk': '125000000'})

    def test_reset_bits_are_crm1_0x74_bits_0_and_3(self):
        out = self.new_output()
        resets = [l.split() for l in out.splitlines() if l.startswith('RESET ')]
        self.assertEqual(resets, [['RESET', '0', 'bit', '0'], ['RESET', '1', 'bit', '3']])
        self.assertRegex(self.text, r'#define ZX_CRM1_RST\s+0x74\b')
        pcie = fx.PCIE_SOURCE.read_text()
        self.assertRegex(pcie, r'#define ZX_CRM1_RST\s+0x74\s+/\* port-0 bit 0, port-1 bit 3')

    def test_header_indices(self):
        clk = CLK_HEADER.read_text()
        rst = RST_HEADER.read_text()
        want = {'ZX_CRM_SPI_WCLK': 0, 'ZX_CRM_SPI_PCLK': 1, 'ZX_CRM_LSP0_WCLK': 2,
                'ZX_CRM_LSP0_PCLK': 3, 'ZX_CRM_LSP1_WCLK': 4, 'ZX_CRM_LSP1_PCLK': 5,
                'ZX_CRM_MDIO_WCLK': 6, 'ZX_CRM_MDIO_PCLK': 7, 'ZX_CRM_GPIO_PCLK': 8}
        for name, value in want.items():
            self.assertRegex(clk, rf'#define {name}\s+{value}\b')
        self.assertEqual(len(re.findall(r'^#define ZX_CRM_\w+\s+\d+', clk, re.M)), len(want))
        # And the provider table maps every index to the clock it names.
        hws = dict(l.split()[1:] for l in self.new_output().splitlines() if l.startswith('HWS '))
        self.assertEqual(hws, {'0': 'spi-wclk', '1': 'spi-pclk', '2': 'wclk-parent',
                               '3': 'pclk-parent', '4': 'lsp1-wclk', '5': 'lsp1-pclk',
                               '6': 'mdio-wclk', '7': 'mdio-pclk', '8': 'gpio-pclk'})
        self.assertRegex(self.text, rf'#define ZX_CRM_NR_CLKS\s+{len(want)}\b')
        for name, value in {'ZX_CRM_RST_PCIE0': 0, 'ZX_CRM_RST_PCIE1': 1}.items():
            self.assertRegex(rst, rf'#define {name}\s+{value}\b')
        # Old header indices are preserved for the SPI clocks.
        old = git_show(OLD_HEADER)
        if old:
            self.assertRegex(old, r'#define ZX_SPI_WCLK 0\b')
            self.assertRegex(old, r'#define ZX_SPI_PCLK 1\b')

    def test_mmio_is_mapped_not_claimed_and_never_relaxed(self):
        code = re.sub(r'/\*.*?\*/', '', self.text, flags=re.S)
        for forbidden in ('devm_platform_ioremap_resource', 'devm_ioremap_resource',
                          'request_mem_region', 'writel_relaxed', 'readl_relaxed',
                          'syscon', 'regmap', 'CLK_IGNORE_UNUSED', 'clk_prepare_enable'):
            self.assertNotIn(forbidden, code)

    def test_every_field_is_the_stock_kernels_own(self):
        """No invented clock tree: each register, bit, shift, width and
        parent is the stock kernel's own registration for that field."""
        rows = records(self.new_output())
        self.assertEqual(sorted(r[1] for r in rows), sorted(VENDOR))
        for kind, name, parent, flags, phys, bit, width, cflags in rows:
            with self.subTest(clock=name):
                vkind, vphys, vbit, vwidth, vflags, vparent = VENDOR[name]
                self.assertEqual((kind, phys, bit, width), (vkind, vphys, vbit, vwidth))
                self.assertEqual(parent, VENDOR_PARENT[vparent])
                if kind == 'div':
                    # Stock divider flags 0 = divisor field + 1. READ_ONLY only
                    # stops writes; it does not change the decoding.
                    self.assertEqual(cflags & ~CLK_DIVIDER_READ_ONLY, vflags)
                else:
                    self.assertEqual(cflags, vflags)

    def test_replaced_driver_produces_the_same_clocks(self):
        """Run the replaced driver through the same model."""
        old = git_show(OLD_SOURCE)
        header = git_show(OLD_HEADER)
        if not old or not header:
            self.skipTest(f'git history with {OLD_COMMIT} not available')
        with tempfile.TemporaryDirectory() as inc:
            target = Path(inc) / 'dt-bindings/clock/zte,zx279128s-spi.h'
            target.parent.mkdir(parents=True)
            target.write_text(header)
            body = strip_linux_includes(self, old, OLD_INCLUDES)
            out = run_c(self, PRELUDE + boot_defines() + MODEL + DUMP + body + OLD_CASES, [inc])
        old_rows = records(out)
        self.assertEqual(old_rows, FROZEN, 'the frozen table no longer describes the old driver')
        new_rows = records(self.new_output())[:len(old_rows)]
        for old_row, new_row in zip(old_rows, new_rows):
            with self.subTest(clock=old_row[1]):
                if old_row[1] in ('spi-wclk', 'spi-pclk'):
                    # Only the flag changes: 0 -> CLK_IS_CRITICAL.
                    self.assertEqual(old_row[3], 0)
                    self.assertEqual(new_row[3], CLK_IS_CRITICAL)
                    self.assertEqual(old_row[:3] + old_row[4:], new_row[:3] + new_row[4:])
                else:
                    self.assertEqual(old_row, new_row)


class CrmKernelContractTests(unittest.TestCase):
    def test_clk_flag_values_match_the_pinned_tree(self):
        tree = fx.kernel_tree()
        if not tree:
            self.skipTest('requires the pinned kernel tree')
        header = (tree / 'include/linux/clk-provider.h').read_text()
        for name, bit in (('CLK_SET_RATE_GATE', 0), ('CLK_GET_RATE_NOCACHE', 6),
                          ('CLK_IS_CRITICAL', 11)):
            self.assertRegex(header, rf'#define {name}\s+BIT\({bit}\)')
        divider = (tree / 'drivers/clk/clk-divider.c').read_text()
        # flags 0, no table: divisor is val + 1
        self.assertIn('\treturn val + 1;\n', divider)
        core = (tree / 'drivers/clk/clk.c').read_text()
        self.assertIn('if (core->flags & CLK_IS_CRITICAL) {', core)

    @unittest.skipUnless(fx.cross_tools(), 'requires the pinned kernel tree and toolchain')
    def test_cross_compiles_against_the_pinned_tree(self):
        tree, _ = fx.cross_tools()
        records_ = sorted((tree / 'drivers/clk').glob('.clk-zx279128-*.o.cmd'))
        if not records_:
            self.skipTest('kernel tree has no recorded ZX279128 clk compile')
        record = str(records_[0].relative_to(tree))
        with tempfile.TemporaryDirectory() as out:
            run = fx.cross_compile(SOURCE, record, out, first_include=fx.INCLUDE_DIR)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_patch_applies_to_pristine_6_6_151(self):
        if not TARBALL.exists() or not shutil.which('patch'):
            self.skipTest('requires openwrt/dl/linux-6.6.151.tar.xz and patch')
        wanted = ['drivers/clk/Kconfig', 'drivers/clk/Makefile',
                  'drivers/spi/Kconfig', 'drivers/spi/Makefile']
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with tarfile.open(TARBALL) as tar:
                for name in wanted:
                    member = tar.getmember('linux-6.6.151/' + name)
                    data = tar.extractfile(member).read()
                    (root / name).parent.mkdir(parents=True, exist_ok=True)
                    (root / name).write_bytes(data)
            for patch in (PATCH, SPI_PATCH, POLICY_PATCH):
                run = subprocess.run(['patch', '-p1', '--batch', '--fuzz=0', '--input', str(patch)],
                                     cwd=root, capture_output=True, text=True)
                self.assertEqual(run.returncode, 0, patch.name + run.stdout + run.stderr)
            kconfig = (root / 'drivers/clk/Kconfig').read_text()
            block = re.search(r'^config COMMON_CLK_ZX279128_CRM\n(.*?)\n\n', kconfig, re.M | re.S)
            self.assertTrue(block)
            self.assertIn('\tbool ', block.group(1))
            self.assertIn('\tdepends on OF && ARCH_ZX279128\n', block.group(1))
            self.assertIn('\tselect RESET_CONTROLLER\n', block.group(1))
            self.assertEqual((root / 'drivers/clk/Makefile').read_text().count(
                'obj-$(CONFIG_COMMON_CLK_ZX279128_CRM) += clk-zx279128-crm.o\n'), 1)
            spi = (root / 'drivers/spi/Kconfig').read_text()
            self.assertIn('\tselect COMMON_CLK_ZX279128_CRM\n', spi)
            for name in wanted:
                self.assertNotIn('ZX279128_SPI\n' if 'clk' in name else 'COMMON_CLK_ZX279128_SPI',
                                 (root / name).read_text())

    def test_no_patch_or_config_names_the_retired_symbol(self):
        for path in sorted((TARGET / 'patches-6.6').glob('*.patch')) + [CONFIG]:
            with self.subTest(file=path.name):
                self.assertNotIn('COMMON_CLK_ZX279128_SPI', path.read_text())
        self.assertFalse((fx.FILES / 'drivers/clk/clk-zx279128-spi.c').exists())
        config = CONFIG.read_text()
        self.assertRegex(config, r'(?m)^CONFIG_COMMON_CLK_ZX279128_CRM=y$')
        self.assertRegex(config, r'(?m)^CONFIG_RESET_CONTROLLER=y$')


def header_names(path):
    """Index -> macro name of a dt-bindings header with one #define per id."""
    pairs = re.findall(r'^#define (ZX_CRM_\w+)\s+(\d+)', path.read_text(), re.M)
    out = {}
    for name, value in pairs:
        assert int(value) not in out, f'{path.name}: {value} defined twice'
        out[int(value)] = name
    assert sorted(out) == list(range(len(out))), f'{path.name}: indices not dense'
    return [out[i] for i in range(len(out))]


def all_nodes(dtb):
    run = subprocess.run(['fdtget', '-l', '-d', str(dtb), '/'], capture_output=True, text=True)
    nodes, stack = ['/'], ['/']
    # fdtget cannot recurse; walk breadth-first with -l.
    seen = 0
    while seen < len(nodes):
        parent = nodes[seen]
        seen += 1
        run = subprocess.run(['fdtget', '-l', str(dtb), parent], capture_output=True, text=True)
        for child in run.stdout.split():
            nodes.append(parent.rstrip('/') + '/' + child)
    return nodes


def specifiers(dtb, words, prop):
    """Split a phandle-with-args list using each target's own cells property."""
    cells_prop = {'clocks': '#clock-cells', 'resets': '#reset-cells'}[prop]
    by_phandle = {}
    for node in all_nodes_cached(dtb):
        ph = fx.fdtget(dtb, node, 'phandle')
        if ph:
            by_phandle[ph[0]] = (fx.fdtget(dtb, node, cells_prop) or [0])[0]
    i, out = 0, []
    while i < len(words):
        phandle = words[i]
        assert phandle in by_phandle, f'{prop}: phandle {phandle} has no node'
        n = by_phandle[phandle]
        out.append((phandle, words[i + 1:i + 1 + n]))
        i += 1 + n
    assert i == len(words), f'{prop}: trailing cells'
    return out


_NODES = {}


def all_nodes_cached(dtb):
    if dtb not in _NODES:
        _NODES[dtb] = all_nodes(dtb)
    return _NODES[dtb]


@unittest.skipUnless(fx.dts_tools_available(), 'requires the unpacked kernel tree, dtc and fdtget')
class CrmDeviceTreeTests(unittest.TestCase):
    NODE = '/soc/clock-controller@94000000'

    def test_compiled_nodes(self):
        text = SOURCE.read_text()
        compatible = re.search(r'\.compatible = "([^"]+)"', text).group(1)
        mapped = re.findall(r'zx_crm_map\(pdev, "([^"]+)"\)', text)
        for name in fx.DTS_NAMES:
            with self.subTest(dts=name), tempfile.TemporaryDirectory() as out:
                dtb, stderr = fx.compile_dts(name, out)
                self.assertNotIn('clock-controller', stderr)
                get = lambda node, prop, kind='x': fx.fdtget(dtb, node, prop, kind)
                self.assertEqual(get(self.NODE, 'compatible', 's'), [compatible])
                self.assertEqual(fx.reg_pairs(dtb, self.NODE),
                                 [(TOPCRM, 0x1000), (CRM1, 0x1000), (LSP0, 0x1000),
                                  (LSP1, 0x1000)])
                self.assertEqual(get(self.NODE, 'reg-names', 's'), mapped)
                self.assertEqual(get(self.NODE, '#clock-cells'), [1])
                self.assertEqual(get(self.NODE, '#reset-cells'), [1])
                self.assertEqual(get(self.NODE, 'clock-names', 's'), ['lsp0-wclk', 'lsp0-pclk'])
                # Parents by index: [0] = 100 MHz LSP0 reference, [1] = 125 MHz APB.
                refs = get(self.NODE, 'clocks')
                self.assertEqual(refs, [get('/clocks/clock-spifc-ref', 'phandle')[0],
                                        get('/clocks/clock-apb', 'phandle')[0]])
                self.assertEqual(get('/clocks/clock-spifc-ref', 'clock-frequency', 'u'), [100000000])
                self.assertEqual(get('/clocks/clock-apb', 'clock-frequency', 'u'), [125000000])
                # The SPI flash controller takes pclk = index 1, wclk = index 0.
                crm = get(self.NODE, 'phandle')[0]
                self.assertEqual(get('/soc/spi@94406000', 'clocks'), [crm, 1, crm, 0])
                self.assertEqual(get('/soc/spi@94406000', 'clock-names', 's'), ['pclk', 'wclk'])
                self.assertEqual(get('/soc/spi@94406000/flash@0', 'spi-max-frequency', 'u'),
                                 [50000000])
                # The reboot node is untouched: its own compatible, one word.
                self.assertEqual(get('/soc/reset-controller@94000044', 'compatible', 's'),
                                 ['zte,zx279128s-reboot'])
                self.assertEqual(fx.reg_pairs(dtb, '/soc/reset-controller@94000044'),
                                 [(TOPCRM + 0x44, 4)])
                # The single-register provider is gone.
                self.assertIsNone(get('/soc/clock-controller@94400018', 'compatible', 's'))
                run = subprocess.run(['fdtget', '-l', str(dtb), '/soc'], capture_output=True,
                                     text=True)
                self.assertNotIn('syscon', run.stdout)

    def test_every_consumer_specifier_is_in_the_providers_range(self):
        """A clock or reset index the provider does not have compiles, and
        then defers forever at runtime. Walk every clocks/resets property in
        the compiled tree; for each phandle that is the CRM node, the cell
        count must be its #clock-cells/#reset-cells and the index must be
        below the driver's ZX_CRM_NR_CLKS/ZX_CRM_NR_RESETS. The expected
        consumer set is pinned, so a new or dropped consumer is noticed."""
        text = SOURCE.read_text()
        nr_clks = int(re.search(r'#define ZX_CRM_NR_CLKS\s+(\d+)', text).group(1))
        nr_rsts = int(re.search(r'#define ZX_CRM_NR_RESETS\s+(\d+)', text).group(1))
        clk_names = header_names(CLK_HEADER)
        rst_names = header_names(RST_HEADER)
        self.assertEqual(len(clk_names), nr_clks)
        self.assertEqual(len(rst_names), nr_rsts)
        expected = {
            ('/soc/spi@94406000', 'clocks'): ['ZX_CRM_SPI_PCLK', 'ZX_CRM_SPI_WCLK'],
            ('/soc/mdio@9a101000', 'clocks'): ['ZX_CRM_MDIO_PCLK', 'ZX_CRM_MDIO_WCLK'],
            ('/soc/gpio@94407000', 'clocks'): ['ZX_CRM_GPIO_PCLK'],
            ('/soc/pcie@f000000', 'resets'): ['ZX_CRM_RST_PCIE0'],
            ('/soc/pcie@f100000', 'resets'): ['ZX_CRM_RST_PCIE1'],
        }
        for name in fx.DTS_NAMES:
            with self.subTest(dts=name), tempfile.TemporaryDirectory() as out:
                dtb, _ = fx.compile_dts(name, out)
                crm = fx.fdtget(dtb, self.NODE, 'phandle')[0]
                cells = {'clocks': fx.fdtget(dtb, self.NODE, '#clock-cells')[0],
                         'resets': fx.fdtget(dtb, self.NODE, '#reset-cells')[0]}
                limit = {'clocks': nr_clks, 'resets': nr_rsts}
                names = {'clocks': clk_names, 'resets': rst_names}
                found = {}
                for node in all_nodes(dtb):
                    for prop in ('clocks', 'resets'):
                        words = fx.fdtget(dtb, node, prop)
                        if not words:
                            continue
                        for phandle, args in specifiers(dtb, words, prop):
                            if phandle != crm:
                                continue
                            self.assertEqual(len(args), cells[prop], f'{node} {prop}')
                            self.assertLess(args[0], limit[prop], f'{node} {prop} index')
                            found.setdefault((node, prop), []).append(names[prop][args[0]])
                self.assertEqual(found, expected)
                # The provider's own clock-names entries are what the driver
                # takes by index, and the names agree with the indices.
                self.assertEqual(fx.fdtget(dtb, '/soc/mdio@9a101000', 'clock-names', 's'),
                                 ['pclk', 'wclk'])
                self.assertIsNone(fx.fdtget(dtb, '/soc/gpio@94407000', 'clock-names', 's'))
                self.assertIsNone(fx.fdtget(dtb, '/soc/pcie@f000000', 'reset-names', 's'))

    def test_source_text(self):
        text = DTS.read_text()
        self.assertNotIn('zte,zx279128s-spi-clocks', text)
        self.assertNotIn('syscon-reboot', text.split('reboot: reset-controller@94000044')[1]
                         .split('};')[0])


if __name__ == '__main__':
    unittest.main()
