"""Execute the actual ZX279128S packet-processor table-access C against a model.

zx279128-pp.c is compiled whole (only its #include lines removed) with boundary
stubs for MMIO, coherent DMA, devres, mutexes, delays and debugfs. The register
model implements the indirect-port protocol recovered from tm.ko (see
docs/PP-OFFLOAD.md) and fails the run on any access outside the CLA CMD/STATUS/
DATA, PM CMD/STATUS/DATA[0..3]/DATA[4..7] and PonPp +0x20/+0x24 registers, on
any STATUS write, and on any CMD/DATA access made without that engine's mutex.

Also checked: the Kconfig/Makefile/config gate (nothing is compiled in when the
symbol is off), the Ethernet probe/remove hooks, and, when the pinned kernel
tree and toolchain are present, a compile against the real 6.6 headers.

These tests prove software order and policy, not silicon behaviour.
"""
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest
from test_tx_origin_r204 import exact_enum, exact_struct, function, tokens
import test_eth_probe

ROOT = Path(__file__).resolve().parents[1]
ZTE = ROOT / 'files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte'
PP_SOURCE = ZTE / 'zx279128-pp.c'
PP_FLOW_SOURCE = PP_SOURCE.with_name('zx279128-pp-flow.c')  # PP component (docs/PP-FLOW.md)
PP_OFFLOAD_SOURCE = PP_SOURCE.with_name('zx279128-pp-offload.c')  # PP component (docs/PP-OFFLOAD.md)
PP_HEADER = ZTE / 'zx279128-pp.h'
ETH_SOURCE = ZTE / 'zx279128-eth.c'
KCONFIG = ZTE / 'Kconfig'
MAKEFILE = ZTE / 'Makefile'
CONFIG = ROOT / 'files/target/linux/armsr/config-6.6'
DOC = ROOT / 'docs/PP-OFFLOAD.md'
SYMBOL = 'CONFIG_ZX279128_PP_TABLES'

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
#include <sys/types.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef u32 __le32;
typedef u64 dma_addr_t;		/* CONFIG_ARCH_DMA_ADDR_T_64BIT=y on this target */
typedef unsigned short umode_t;
#define __iomem
#define __user
#define BIT(n) (1U << (n))
#define SZ_4K 0x1000
#define SZ_128K 0x20000
#define SZ_1M 0x100000
#define SZ_4M 0x400000
#define GFP_KERNEL 0x10u
#define THIS_MODULE ((struct module *)0)
#define DMA_BIT_MASK(n) (((n) == 64) ? ~0ULL : ((1ULL << (n)) - 1))
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define IS_ALIGNED(x, a) ((((u64)(x)) & ((u64)(a) - 1)) == 0)
#define upper_32_bits(n) ((u32)((u64)(n) >> 32))
#define lower_32_bits(n) ((u32)(n))
#define min_t(t, a, b) ((t)(a) < (t)(b) ? (t)(a) : (t)(b))
#define cpu_to_le32(x) ((__le32)(x))

struct module;
struct device { int unused; };
struct dentry { int unused; };
struct inode { void *i_private; };
struct file { void *private_data; };
struct seq_file { char buf[8192]; size_t len; void *private; };
/* Deliberately no .write member: a write method would not compile. */
struct file_operations {
	struct module *owner;
	int (*open)(struct inode *, struct file *);
	ssize_t (*read)(struct file *, char __user *, size_t, loff_t *);
	loff_t (*llseek)(struct file *, loff_t, int);
	int (*release)(struct inode *, struct file *);
};
struct mutex { int init; int held; };

/* ---- event log ---- */
struct event { char kind; u32 pa; u32 val; };
#define NEVENTS 400000
static struct event events[NEVENTS];
static unsigned nev;
static void ev(char kind, u32 pa, u32 val)
{
	assert(nev < NEVENTS);
	events[nev++] = (struct event){ kind, pa, val };
}

/* ---- register model ---- */
enum { CLA = 0, PM = 1, PONPP = 2 };
static const u32 page_phys[3] = { 0x9238c000u, 0x9239c000u, 0x923a0000u };
static u8 pages[3][4096] __attribute__((aligned(8)));
#define PA(pg, off) (page_phys[pg] + (u32)(off))
static u32 R32(int pg, u32 off) { u32 v; memcpy(&v, pages[pg] + off, 4); return v; }
static void W32(int pg, u32 off, u32 v) { memcpy(pages[pg] + off, &v, 4); }

struct engine_model {
	bool never_ready;
	unsigned not_ready;	/* next N status reads say busy */
	unsigned post_cmd_busy;	/* reloaded into not_ready by every CMD write */
	bool budget_on;
	unsigned budget;	/* ready status reads left before staying busy */
	bool pending_write;
	unsigned sel;
	u32 addr;
	int last_op;
	unsigned commits;
};
static struct engine_model em[2];
static bool base_ignore[2];		/* PonPp +0x20 / +0x24 drop every write */
static bool base_ignore_zero[2];	/* ... drop writes of 0 only */

struct ram_entry { bool used; int e; unsigned sel; u32 addr; u32 w[17]; };
static struct ram_entry ram[512];
static u32 ram_default(int e, unsigned sel, u32 addr, unsigned i)
{
	return ((u32)e << 31) | (sel << 24) | ((addr & 0xffff) << 8) | i;
}
static unsigned engine_words(int e) { return e == CLA ? 17 : 8; }
static u32 *ram_entry(int e, unsigned sel, u32 addr)
{
	unsigned i, w;

	for (i = 0; i < 512; i++)
		if (ram[i].used && ram[i].e == e && ram[i].sel == sel && ram[i].addr == addr)
			return ram[i].w;
	for (i = 0; i < 512; i++)
		if (!ram[i].used) {
			ram[i] = (struct ram_entry){ true, e, sel, addr, { 0 } };
			for (w = 0; w < 17; w++)
				ram[i].w[w] = ram_default(e, sel, addr, w);
			return ram[i].w;
		}
	assert(!"model RAM full");
	return NULL;
}

static int locate(const void *p, u32 *off)
{
	int pg;

	for (pg = 0; pg < 3; pg++)
		if ((const u8 *)p >= pages[pg] && (const u8 *)p < pages[pg] + 4096) {
			*off = (u32)((const u8 *)p - pages[pg]);
			return pg;
		}
	assert(!"access outside the CLA, PM and PonPp windows");
	return -1;
}
static bool data_index(int pg, u32 off, unsigned *i)
{
	if (pg == CLA && off >= 0x1c && off <= 0x5c) { *i = (off - 0x1c) / 4; return true; }
	if (pg == PM && off >= 0x1c && off <= 0x28) { *i = (off - 0x1c) / 4; return true; }
	if (pg == PM && off >= 0x100 && off <= 0x10c) { *i = 4 + (off - 0x100) / 4; return true; }
	return false;
}
static u32 data_offset(int e, unsigned i)
{
	return (e == PM && i >= 4) ? 0x100 + 4 * (i - 4) : 0x1c + 4 * i;
}
static bool engine_locked(int e);	/* defined after the driver */
static int mutex_engine(const struct mutex *m);
static void model_note_alloc(void *p, size_t n);

static void check_access(int pg, u32 off)
{
	unsigned i;

	assert(!(off & 3));
	if (pg == PONPP) {
		assert(off == 0x20 || off == 0x24);
		return;
	}
	/* The CLA hash polynomial-selector registers are plain reads, not part of
	 * the indirect port, so they do not take the engine mutex. They are the
	 * only non-indirect CLA registers the driver may touch (read-only: see
	 * the write path below).
	 */
	if (pg == CLA && (off == 0x90 || off == 0x94))
		return;
	assert(off == 0x14 || off == 0x18 || data_index(pg, off, &i));
	if (off != 0x18)
		assert(engine_locked(pg));
}
static u32 status_read(int e)
{
	if (em[e].never_ready)
		return 0;
	if (em[e].not_ready) {
		em[e].not_ready--;
		return 0;
	}
	if (em[e].budget_on) {
		if (!em[e].budget)
			return 0;
		em[e].budget--;
	}
	return 1;
}
static u32 readl(const void *p)
{
	u32 off, v;
	int pg = locate(p, &off);

	check_access(pg, off);
	if (pg != PONPP && off == 0x18)
		v = status_read(pg);
	else
		v = R32(pg, off);
	ev('R', PA(pg, off), v);
	return v;
}
static void writel(u32 v, void *p)
{
	u32 off;
	unsigned i, w;
	int pg = locate(p, &off);

	check_access(pg, off);
	ev('W', PA(pg, off), v);
	if (pg == PONPP) {
		unsigned r = off == 0x24;

		if (base_ignore[r] || (base_ignore_zero[r] && !v))
			return;
		W32(pg, off, v);
		return;
	}
	assert(off != 0x18);	/* STATUS is never written */
	/* The hash selectors are read-only to this driver: the vendor never
	 * writes them either, and rewriting them would move every placed entry
	 * to a different bucket. A write here is a bug, not a policy choice.
	 */
	assert(!(pg == CLA && (off == 0x90 || off == 0x94)));
	W32(pg, off, v);
	if (off == 0x14) {
		struct engine_model *m = &em[pg];
		u32 *row;

		m->last_op = (v >> 27) & 1;
		m->sel = (v >> 22) & 0x1f;
		m->addr = v & (pg == CLA ? 0x3fffff : 0xfffff);
		m->not_ready = m->post_cmd_busy;
		if (m->last_op == 1) {
			row = ram_entry(pg, m->sel, m->addr);
			for (w = 0; w < engine_words(pg); w++)
				W32(pg, data_offset(pg, w), row[w]);
			m->pending_write = false;
		} else {
			m->pending_write = true;
		}
		return;
	}
	assert(data_index(pg, off, &i));
	if (i == 0 && em[pg].pending_write) {	/* commit trigger: DATA[0] */
		u32 *row = ram_entry(pg, em[pg].sel, em[pg].addr);

		for (w = 0; w < engine_words(pg); w++)
			row[w] = R32(pg, data_offset(pg, w));
		em[pg].pending_write = false;
		em[pg].commits++;
	}
}

static unsigned n_delay;
static void udelay(unsigned long us) { n_delay++; ev('d', 0, (u32)us); }

static void mutex_init(struct mutex *m) { m->init = 1; m->held = 0; }
static void mutex_lock(struct mutex *m)
{
	assert(m->init && !m->held);
	m->held = 1;
	ev('L', 0, (u32)mutex_engine(m));
}
static void mutex_unlock(struct mutex *m)
{
	assert(m->init && m->held);
	m->held = 0;
	ev('U', 0, (u32)mutex_engine(m));
}

/* ---- logging ---- */
static unsigned n_err, n_warn, n_info;
static char last_msg[512];
#define LOGGER(name, counter) \
static void name(struct device *d, const char *fmt, ...) \
{ va_list ap; (void)d; va_start(ap, fmt); vsnprintf(last_msg, sizeof(last_msg), fmt, ap); va_end(ap); counter++; }
LOGGER(dev_err, n_err)
LOGGER(dev_warn, n_warn)
LOGGER(dev_info, n_info)

/* ---- devres ---- */
struct devres_action { void (*fn)(void *); void *arg; };
static struct devres_action actions[16];
static unsigned nactions;
static void *devmem[16];
static unsigned ndevmem;
static bool map_fail, action_fail;
static void *devm_kzalloc(struct device *d, size_t n, unsigned gfp)
{
	void *p;

	(void)d; assert(gfp == GFP_KERNEL);
	p = calloc(1, n);
	assert(p && ndevmem < 16);
	devmem[ndevmem++] = p;
	model_note_alloc(p, n);
	return p;
}
static void *devm_ioremap(struct device *d, u64 pa, u64 size)
{
	int pg;

	(void)d; assert(size == SZ_4K);
	if (map_fail)
		return NULL;
	for (pg = 0; pg < 3; pg++)
		if (pa == page_phys[pg]) {
			ev('M', (u32)pa, (u32)size);
			return pages[pg];
		}
	assert(!"unexpected ioremap");
	return NULL;
}
static int devm_add_action_or_reset(struct device *d, void (*fn)(void *), void *arg)
{
	(void)d;
	if (action_fail) {
		fn(arg);
		return -ENOMEM;
	}
	assert(nactions < 16);
	actions[nactions++] = (struct devres_action){ fn, arg };
	return 0;
}
static void devm_release_action(struct device *d, void (*fn)(void *), void *arg)
{
	unsigned i;

	(void)d;
	for (i = 0; i < nactions; i++)
		if (actions[i].fn == fn && actions[i].arg == arg) {
			memmove(&actions[i], &actions[i + 1], (nactions - i - 1) * sizeof(actions[0]));
			nactions--;
			fn(arg);
			return;
		}
	assert(!"devm_release_action: no such action");
}

/* ---- coherent DMA ---- */
struct dma_block { void *cpu; dma_addr_t dma; size_t size; bool live; };
static struct dma_block blocks[8];
static unsigned nblocks, alloc_calls, fail_alloc_at;
static dma_addr_t addr_for[2];
static bool mask_fail;
static int dma_set_coherent_mask(struct device *d, u64 mask)
{
	(void)d; assert(mask == 0xffffffffULL);
	ev('m', 0, 0);
	return mask_fail ? -EIO : 0;
}
static void *dma_alloc_coherent(struct device *d, size_t size, dma_addr_t *handle, unsigned gfp)
{
	void *p;

	(void)d; assert(gfp == GFP_KERNEL);
	alloc_calls++;
	if (alloc_calls == fail_alloc_at) {
		ev('a', 0, (u32)size);
		return NULL;
	}
	assert(nblocks < 2);
	p = calloc(1, size);
	assert(p);
	*handle = addr_for[nblocks];
	blocks[nblocks++] = (struct dma_block){ p, *handle, size, true };
	ev('A', (u32)*handle, (u32)size);
	return p;
}
static void dma_free_coherent(struct device *d, size_t size, void *cpu, dma_addr_t handle)
{
	unsigned i;

	(void)d;
	for (i = 0; i < nblocks; i++)
		if (blocks[i].cpu == cpu) {
			assert(blocks[i].live && blocks[i].dma == handle && blocks[i].size == size);
			blocks[i].live = false;
			free(cpu);
			ev('F', (u32)handle, (u32)size);
			return;
		}
	assert(!"freeing unknown coherent memory");
}
static unsigned live_blocks(void)
{
	unsigned i, n = 0;

	for (i = 0; i < nblocks; i++)
		n += blocks[i].live;
	return n;
}

/* ---- debugfs / seq_file / uaccess ---- */
struct dfile { const char *name; umode_t mode; struct dentry *parent; void *data;
	       const struct file_operations *fops; long long size; };
static struct dfile dfiles[32];
static unsigned ndfiles, ndirs, nremoved;
static struct dentry dir_dentry, file_dentry;
static struct dentry *debugfs_create_dir(const char *name, struct dentry *parent)
{
	assert(!strcmp(name, "zx279128-pp") && !parent);
	ndirs++;
	ev('D', 0, 0);
	return &dir_dentry;
}
static struct dentry *debugfs_create_file(const char *name, umode_t mode, struct dentry *parent,
					  void *data, const struct file_operations *fops)
{
	assert(ndfiles < 32);
	dfiles[ndfiles++] = (struct dfile){ name, mode, parent, data, fops, -1 };
	ev('f', 0, ndfiles);
	return &file_dentry;
}
static void debugfs_create_file_size(const char *name, umode_t mode, struct dentry *parent,
				     void *data, const struct file_operations *fops, loff_t size)
{
	assert(ndfiles < 32);
	dfiles[ndfiles++] = (struct dfile){ name, mode, parent, data, fops, size };
	ev('f', 0, ndfiles);
}
static void debugfs_remove(struct dentry *d)
{
	if (!d)
		return;
	assert(d == &dir_dentry);
	nremoved++;
	ev('X', 0, 0);
}
#define debugfs_remove_recursive debugfs_remove
static int simple_open(struct inode *inode, struct file *file)
{
	file->private_data = inode->i_private;
	return 0;
}
static loff_t default_llseek(struct file *f, loff_t off, int whence) { (void)f; (void)whence; return off; }
static bool copy_fail;
static unsigned long copy_to_user(void __user *to, const void *from, unsigned long n)
{
	if (copy_fail)
		return n;
	memcpy(to, from, n);
	return 0;
}
static struct seq_file seq;
static int (*seq_show)(struct seq_file *, void *);
static int single_open(struct file *f, int (*show)(struct seq_file *, void *), void *data)
{
	memset(&seq, 0, sizeof(seq));
	seq.private = data;
	seq_show = show;
	f->private_data = &seq;
	return 0;
}
static ssize_t seq_read(struct file *f, char __user *buf, size_t n, loff_t *pos)
{
	struct seq_file *s = f->private_data;
	size_t c;

	(void)pos;
	s->len = 0;
	assert(seq_show(s, NULL) == 0);
	c = s->len < n ? s->len : n;
	memcpy(buf, s->buf, c);
	return (ssize_t)c;
}
static loff_t seq_lseek(struct file *f, loff_t off, int whence) { (void)f; (void)whence; return off; }
static int single_release(struct inode *i, struct file *f) { (void)i; (void)f; return 0; }
static void seq_printf(struct seq_file *s, const char *fmt, ...)
{
	va_list ap;

	va_start(ap, fmt);
	s->len += vsnprintf(s->buf + s->len, sizeof(s->buf) - s->len, fmt, ap);
	va_end(ap);
	assert(s->len < sizeof(s->buf));
}
#define DEFINE_SHOW_ATTRIBUTE(__name) \
static int __name ## _open(struct inode *inode, struct file *file) \
{ return single_open(file, __name ## _show, inode->i_private); } \
static const struct file_operations __name ## _fops = { \
	.owner = THIS_MODULE, .open = __name ## _open, .read = seq_read, \
	.llseek = seq_lseek, .release = single_release, }
'''

CASES = r'''
static struct zx_pp *g_pp;
static struct device dev;

static void model_note_alloc(void *p, size_t n)
{
	if (n == sizeof(struct zx_pp))
		g_pp = p;
}
static bool engine_locked(int e)
{
	return g_pp && (e == CLA ? g_pp->cla.lock.held : g_pp->pm.lock.held);
}
static int mutex_engine(const struct mutex *m)
{
	if (g_pp && m == &g_pp->cla.lock)
		return CLA;
	if (g_pp && m == &g_pp->pm.lock)
		return PM;
	assert(!"unknown mutex");
	return -1;
}

static void devres_release_all(void)
{
	while (nactions) {
		struct devres_action a = actions[--nactions];

		a.fn(a.arg);
	}
	while (ndevmem)
		free(devmem[--ndevmem]);
	g_pp = NULL;
}

static void model_reset(void)
{
	unsigned i;

	devres_release_all();
	for (i = 0; i < nblocks; i++)	/* deliberately leaked by the driver */
		if (blocks[i].live)
			free(blocks[i].cpu);
	memset(blocks, 0, sizeof(blocks));
	nblocks = alloc_calls = fail_alloc_at = 0;
	addr_for[0] = 0x45f00000u;	/* 1 MiB aligned */
	addr_for[1] = 0x46400000u;	/* 4 MiB aligned */
	mask_fail = map_fail = action_fail = copy_fail = false;
	memset(em, 0, sizeof(em));
	memset(base_ignore, 0, sizeof(base_ignore));
	memset(base_ignore_zero, 0, sizeof(base_ignore_zero));
	memset(ram, 0, sizeof(ram));
	memset(pages, 0, sizeof(pages));
	for (i = 0x1c; i <= 0x5c; i += 4)
		W32(CLA, i, 0xdeadbeefu);
	for (i = 0; i < 8; i++)
		W32(PM, data_offset(PM, i), 0xdeadbeefu);
	W32(CLA, 0x14, 0xa0000000u | 0x0123456u);	/* reserved 31:28 + garbage */
	W32(PM, 0x14, 0x50300000u | 0x0012345u);	/* reserved 31:28, 21:20 */
	W32(PONPP, 0x20, 0x56409000u);	/* values measured on hardware */
	W32(PONPP, 0x24, 0x5f600000u);
	/* CLA hash selectors, at the values measured on hardware 2026-11-16:
	 * way0..3 use polynomial tables 0..3 and the outer table is
	 * unconfigured (logs/analysis-20261115/pp-cla-hash.md).
	 */
	W32(CLA, 0x90, 0x00e400e4u);
	W32(CLA, 0x94, 0x00000000u);
	memset(dfiles, 0, sizeof(dfiles));
	ndfiles = ndirs = nremoved = 0;
	nev = n_delay = n_err = n_warn = n_info = 0;
}

static struct zx_pp *up(void)
{
	struct zx_pp *pp;

	model_reset();
	pp = zx_pp_tables_init(&dev);
	assert(pp && pp == g_pp);
	return pp;
}

static unsigned count(unsigned from, char kind, u32 pa)
{
	unsigned i, n = 0;

	for (i = from; i < nev; i++)
		n += events[i].kind == kind && events[i].pa == pa;
	return n;
}
static unsigned count_kind(unsigned from, char kind)
{
	unsigned i, n = 0;

	for (i = from; i < nev; i++)
		n += events[i].kind == kind;
	return n;
}
static unsigned mmio(unsigned from) { return count_kind(from, 'R') + count_kind(from, 'W'); }
static u32 last_write(u32 pa)
{
	unsigned i;

	for (i = nev; i-- > 0; )
		if (events[i].kind == 'W' && events[i].pa == pa)
			return events[i].val;
	assert(!"no write to that register");
	return 0;
}
static bool is_data_pa(u32 pa, int *pg, unsigned *idx)
{
	int p;

	for (p = 0; p < 2; p++)
		if (pa >= page_phys[p] && pa < page_phys[p] + 4096 &&
		    data_index(p, pa - page_phys[p], idx)) {
			*pg = p;
			return true;
		}
	return false;
}
/* Every register write is immediately preceded by a read of that register. */
static void check_rmw_pairs(void)
{
	unsigned i;

	for (i = 0; i < nev; i++)
		if (events[i].kind == 'W')
			assert(i && events[i - 1].kind == 'R' && events[i - 1].pa == events[i].pa);
}

struct want { char kind; u32 pa; };
static void expect_sequence(unsigned from, const char *kinds, const struct want *w, unsigned n)
{
	unsigned i, j = 0;

	for (i = from; i < nev; i++) {
		if (!strchr(kinds, events[i].kind))
			continue;
		if (j >= n || events[i].kind != w[j].kind || events[i].pa != w[j].pa) {
			fprintf(stderr, "event %u: got %c %08x, want %c %08x (#%u)\n", i,
				events[i].kind, events[i].pa, j < n ? w[j].kind : '-',
				j < n ? w[j].pa : 0, j);
			assert(!"unexpected event sequence");
		}
		j++;
	}
	assert(j == n);
}

static void t_cmd_encoding(void)
{
	struct zx_pp *pp = up();
	u32 d[17] = { 0 };
	unsigned mark = nev;

	assert(zx_pp_cla_read(NULL, 7, 5, d, 1) == -ENODEV);
	assert(zx_pp_cla_write(NULL, 7, 5, d, 1) == -ENODEV);
	assert(zx_pp_pm_read(NULL, 0, 0, d, 1) == -ENODEV);
	assert(zx_pp_pm_write(NULL, 0, 0, d, 1) == -ENODEV);
	/* Outside the vendor bounds: refused before any register access. */
	assert(zx_pp_cla_read(pp, 10, 0, d, 1) == -EINVAL);
	assert(zx_pp_cla_read(pp, 9, 0x400000, d, 1) == -EINVAL);
	assert(zx_pp_cla_read(pp, 0, 0, d, 0) == -EINVAL);
	assert(zx_pp_cla_read(pp, 0, 0, d, 18) == -EINVAL);
	assert(zx_pp_cla_read(pp, 0, 0, NULL, 1) == -EINVAL);
	assert(zx_pp_cla_write(pp, 0, 0, NULL, 1) == -EINVAL);
	assert(zx_pp_pm_read(pp, 32, 0, d, 1) == -EINVAL);
	assert(zx_pp_pm_write(pp, 31, 0x100000, d, 1) == -EINVAL);
	assert(zx_pp_pm_read(pp, 0, 0, d, 9) == -EINVAL);
	assert(nev == mark);

	/* CLA: addr | sel << 22 | op << 27, bits 31:28 preserved. */
	assert(zx_pp_cla_read(pp, 7, 5, d, 1) == 0);
	assert(last_write(PA(CLA, 0x14)) == (0xa0000000u | 5u | 7u << 22 | 1u << 27));
	assert(em[CLA].last_op == 1 && em[CLA].sel == 7 && em[CLA].addr == 5);
	assert(zx_pp_cla_write(pp, 9, 0x3fffff, d, 17) == 0);
	assert(last_write(PA(CLA, 0x14)) == (0xa0000000u | 0x3fffffu | 9u << 22));
	assert(em[CLA].last_op == 0 && em[CLA].sel == 9 && em[CLA].addr == 0x3fffff);
	/* PM: bits 31:28 and 21:20 preserved. */
	assert(zx_pp_pm_read(pp, 13, 3, d, 8) == 0);
	assert(last_write(PA(PM, 0x14)) == (0x50300000u | 3u | 13u << 22 | 1u << 27));
	assert(zx_pp_pm_write(pp, 31, 0xfffff, d, 8) == 0);
	assert(last_write(PA(PM, 0x14)) == (0x50300000u | 0xfffffu | 31u << 22));
	assert(em[PM].last_op == 0 && em[PM].sel == 31 && em[PM].addr == 0xfffff);
}

static void t_poll_bound(void)
{
	struct zx_pp *pp = up();
	u32 d[17] = { 0 };
	unsigned mark = nev, delays = n_delay, k, n;

	/* Never ready: exactly 20 STATUS reads, no command, then a latch. */
	em[CLA].never_ready = true;
	assert(zx_pp_cla_read(pp, 7, 0, d, 1) == -ETIMEDOUT);
	assert(count(mark, 'R', PA(CLA, 0x18)) == 20 && count_kind(mark, 'R') == 20);
	assert(count_kind(mark, 'W') == 0 && n_delay - delays == 19);
	assert(pp->cla.faulted && pp->cla.timeouts == 1);
	em[CLA].never_ready = false;
	mark = nev;
	assert(zx_pp_cla_read(pp, 7, 0, d, 1) == -EIO);
	assert(zx_pp_cla_write(pp, 7, 0, d, 1) == -EIO);
	assert(mmio(mark) == 0);
	assert(zx_pp_pm_read(pp, 3, 1, d, 1) == 0);	/* PM is independent */

	/* Ready on pre-poll read k: exactly k reads, k - 1 delays. */
	for (k = 1; k <= 20; k++) {
		pp = up();
		mark = nev;
		delays = n_delay;
		em[CLA].not_ready = k - 1;
		assert(zx_pp_cla_read(pp, 7, 0, d, 1) == 0);
		assert(count(mark, 'R', PA(CLA, 0x18)) == k + 1);	/* + post-poll */
		assert(n_delay - delays == k - 1);
	}
	/* Post-command poll, busy for n reads after the CMD write. */
	for (n = 1; n < 20; n += 6) {
		pp = up();
		mark = nev;
		em[PM].post_cmd_busy = n;
		assert(zx_pp_pm_read(pp, 13, 0, d, 8) == 0);
		assert(count(mark, 'R', PA(PM, 0x18)) == 1 + n + 1);
	}
	pp = up();
	mark = nev;
	em[PM].post_cmd_busy = 20;
	assert(zx_pp_pm_read(pp, 13, 0, d, 8) == -ETIMEDOUT);
	assert(count(mark, 'W', PA(PM, 0x14)) == 1 && count(mark, 'R', PA(PM, 0x18)) == 21);
	assert(mmio(mark) == 1 + 2 + 20);	/* pre-poll, CMD read+write, post-poll; no DATA */
	assert(pp->pm.faulted);

	/* Writes end at DATA[0]; completion is left to the next pre-poll. */
	pp = up();
	assert(zx_pp_cla_write(pp, 2, 1, d, 15) == 0);
	assert(events[nev - 2].kind == 'W' && events[nev - 2].pa == PA(CLA, 0x1c));
	assert(events[nev - 1].kind == 'U');

	/* Init gate: an engine that is not ready blocks everything. */
	for (k = 0; k < 2; k++) {
		model_reset();
		em[k].never_ready = true;
		assert(zx_pp_tables_init(&dev) == NULL);
		assert(count_kind(0, 'W') == 0 && count_kind(0, 'A') == 0 && count_kind(0, 'm') == 0);
		assert(count(0, 'R', PA(k, 0x18)) == 20 && ndirs == 0 && nactions == 0);
	}
}

static void t_pm_word_placement(void)
{
	static const u32 pm_off[8] = { 0x1c, 0x20, 0x24, 0x28, 0x100, 0x104, 0x108, 0x10c };
	struct zx_pp *pp = up();
	u32 d[17] = { 0 }, v[17];
	struct want w[17];
	unsigned mark, i;

	for (i = 0; i < 8; i++)
		w[i] = (struct want){ 'R', PA(PM, pm_off[7 - i]) };
	mark = nev;
	assert(zx_pp_pm_read(pp, 13, 2, d, 8) == 0);
	{
		/* Only the DATA reads, highest word first. */
		unsigned j = 0, idx;
		int pg;

		for (i = mark; i < nev; i++)
			if (events[i].kind == 'R' && is_data_pa(events[i].pa, &pg, &idx)) {
				assert(j < 8 && events[i].pa == w[j].pa);
				j++;
			}
		assert(j == 8);
	}
	for (i = 0; i < 8; i++)
		assert(d[i] == ram_default(PM, 13, 2, i));

	for (i = 0; i < 8; i++)
		v[i] = 0x11110000u + i;
	mark = nev;
	assert(zx_pp_pm_write(pp, 0, 0x7ff, v, 8) == 0);
	for (i = 0; i < 8; i++)
		assert(last_write(PA(PM, pm_off[i])) == v[i]);
	{
		unsigned j = 0, idx;
		int pg;

		for (i = mark; i < nev; i++)
			if (events[i].kind == 'W' && is_data_pa(events[i].pa, &pg, &idx)) {
				assert(events[i].pa == PA(PM, pm_off[7 - j]));
				j++;
			}
		assert(j == 8);
	}
	assert(em[PM].commits == 1);
	memset(d, 0, sizeof(d));
	assert(zx_pp_pm_read(pp, 0, 0x7ff, d, 8) == 0);
	for (i = 0; i < 8; i++)
		assert(d[i] == v[i]);
	/* Four words never touch the high bank. */
	mark = nev;
	assert(zx_pp_pm_read(pp, 10, 1, d, 4) == 0);
	for (i = mark; i < nev; i++)
		assert(events[i].pa < PA(PM, 0x100) || events[i].pa > PA(PM, 0x10c));
	/* CLA is contiguous: 17 words, +0x5c down to +0x1c. */
	mark = nev;
	assert(zx_pp_cla_read(pp, 1, 159, d, 17) == 0);
	{
		unsigned j = 0, idx;
		int pg;

		for (i = mark; i < nev; i++)
			if (events[i].kind == 'R' && is_data_pa(events[i].pa, &pg, &idx)) {
				assert(pg == CLA && events[i].pa == PA(CLA, 0x5c - 4 * j));
				j++;
			}
		assert(j == 17);
	}
	for (i = 0; i < 17; i++)
		assert(d[i] == ram_default(CLA, 1, 159, i));
}

static void t_write_ordering(void)
{
	struct zx_pp *pp = up();
	struct want w[64];
	u32 v[17];
	unsigned mark, i, n;

	for (i = 0; i < 17; i++)
		v[i] = 0x5a5a0000u | i;
	n = 0;
	w[n++] = (struct want){ 'L', 0 };
	w[n++] = (struct want){ 'R', PA(CLA, 0x18) };
	w[n++] = (struct want){ 'R', PA(CLA, 0x14) };
	w[n++] = (struct want){ 'W', PA(CLA, 0x14) };
	for (i = 15; i-- > 0; ) {
		w[n++] = (struct want){ 'R', PA(CLA, 0x1c + 4 * i) };
		w[n++] = (struct want){ 'W', PA(CLA, 0x1c + 4 * i) };
	}
	w[n++] = (struct want){ 'U', 0 };
	mark = nev;
	assert(zx_pp_cla_write(pp, 2, 0x10, v, 15) == 0);
	expect_sequence(mark, "LURW", w, n);
	assert(last_write(PA(CLA, 0x14)) == (0xa0000000u | 0x10u | 2u << 22));
	for (i = 0; i < 15; i++)
		assert(last_write(PA(CLA, 0x1c + 4 * i)) == v[i]);
	assert(em[CLA].commits == 1);
	for (i = 0; i < 15; i++)
		assert(ram_entry(CLA, 2, 0x10)[i] == v[i]);

	n = 0;
	w[n++] = (struct want){ 'L', 1 };
	w[n++] = (struct want){ 'R', PA(PM, 0x18) };
	w[n++] = (struct want){ 'R', PA(PM, 0x14) };
	w[n++] = (struct want){ 'W', PA(PM, 0x14) };
	for (i = 3; i-- > 0; ) {
		w[n++] = (struct want){ 'R', PA(PM, 0x1c + 4 * i) };
		w[n++] = (struct want){ 'W', PA(PM, 0x1c + 4 * i) };
	}
	w[n++] = (struct want){ 'U', 1 };
	mark = nev;
	assert(zx_pp_pm_write(pp, 0, (1u << 10) | 5u, v, 3) == 0);
	/* 'L'/'U' events carry the engine in val, not pa. */
	for (i = 0; i < n; i++)
		if (w[i].kind == 'L' || w[i].kind == 'U')
			w[i].pa = 0;
	expect_sequence(mark, "LURW", w, n);
	assert(events[nev - 1].kind == 'U' && events[nev - 1].val == PM);
	assert(events[nev - 2].kind == 'W' && events[nev - 2].pa == PA(PM, 0x1c));
}

static void t_rmw(void)
{
	struct zx_pp *pp = up();
	u32 v[8] = { 1, 2, 3, 4, 5, 6, 7, 8 };
	unsigned i;

	/* Base registers: read (prior value kept), then write the DMA address. */
	assert(pp->pm_tbl.prior == 0x56409000u && pp->acl_tbl.prior == 0x5f600000u);
	assert(last_write(PA(PONPP, 0x20)) == 0x45f00000u);
	assert(last_write(PA(PONPP, 0x24)) == 0x46400000u);
	/* DATA is fully masked: stale register contents do not leak in. */
	for (i = 0; i < 8; i++)
		W32(PM, data_offset(PM, i), 0xffffffffu);
	assert(zx_pp_pm_write(pp, 6, 9, v, 8) == 0);
	for (i = 0; i < 8; i++)
		assert(R32(PM, data_offset(PM, i)) == v[i]);
	/* CMD keeps its reserved bits across operations. */
	assert((R32(CLA, 0x14) & 0xf0000000u) == 0xa0000000u);
	assert((R32(PM, 0x14) & 0xf0300000u) == 0x50300000u);
	zx_pp_tables_remove(pp);
	check_rmw_pairs();
}

static void t_base_before_indirect(void)
{
	static const struct want init_seq[] = {
		{ 'R', 0x9238c018u }, { 'R', 0x9239c018u },
		{ 'A', 0x45f00000u }, { 'A', 0x46400000u },
		{ 'R', 0x923a0020u }, { 'W', 0x923a0020u },
		{ 'R', 0x923a0024u }, { 'W', 0x923a0024u },
		{ 'R', 0x923a0020u }, { 'R', 0x923a0024u },
		/* hash selectors, read once after the bases verify */
		{ 'R', 0x9238c090u }, { 'R', 0x9238c094u },
	};
	struct zx_pp *pp;
	u32 d[17];
	unsigned i, k, mark, first_dir = 0, first_cmd = 0, base_write = 0;
	const u8 *t;

	pp = up();
	expect_sequence(0, "RWAF", init_seq, ARRAY_SIZE(init_seq));
	assert(last_write(PA(PONPP, 0x20)) == 0x45f00000u && last_write(PA(PONPP, 0x24)) == 0x46400000u);
	assert(blocks[0].size == SZ_1M && blocks[1].size == SZ_4M);
	assert(pp->cla.enabled && pp->pm.enabled && pp->programmed);
	t = pp->acl_tbl.cpu;
	for (i = 0; i < SZ_4M; i++)
		assert(!t[i]);
	t = pp->pm_tbl.cpu;
	for (i = 0; i < SZ_1M; i++)
		assert(!t[i]);
	assert(zx_pp_cla_read(pp, 0, 0, d, 5) == 0);
	for (i = 0; i < nev; i++) {
		if (events[i].kind == 'W' && events[i].pa == PA(PONPP, 0x24))
			base_write = i;
		if (events[i].kind == 'D' && !first_dir)
			first_dir = i;
		if (events[i].kind == 'W' && events[i].pa == PA(CLA, 0x14) && !first_cmd)
			first_cmd = i;
	}
	assert(base_write && base_write < first_dir && first_dir < first_cmd);

	/* A base that does not read back keeps the engines disabled. */
	for (k = 0; k < 2; k++) {
		model_reset();
		base_ignore[k] = true;
		assert(zx_pp_tables_init(&dev) == NULL);
		assert(ndirs == 0 && nactions == 0 && live_blocks() == 0 && n_err == 1);
		assert(count(0, 'W', PA(PONPP, 0x20)) == 2 && count(0, 'W', PA(PONPP, 0x24)) == 2);
		assert(R32(PONPP, k ? 0x24 : 0x20) == (k ? 0x5f600000u : 0x56409000u));
		assert(R32(PONPP, k ? 0x20 : 0x24) == 0);
		/* both frees only after both clears */
		mark = 0;
		for (i = 0; i < nev; i++)
			if (events[i].kind == 'W' && !events[i].val)
				mark = i;
		for (i = 0; i < nev; i++)
			if (events[i].kind == 'F')
				assert(i > mark);
		assert(count_kind(0, 'F') == 2);
	}
	/* Allocation and range failures never touch the base registers. */
	model_reset();
	fail_alloc_at = 1;
	assert(zx_pp_tables_init(&dev) == NULL && count_kind(0, 'W') == 0 && count_kind(0, 'F') == 0);
	model_reset();
	fail_alloc_at = 2;
	assert(zx_pp_tables_init(&dev) == NULL && count_kind(0, 'W') == 0);
	assert(count(0, 'F', 0x45f00000u) == 1 && live_blocks() == 0);
	model_reset();
	addr_for[0] = 0x45f01000u;	/* not 128 KiB aligned */
	assert(zx_pp_tables_init(&dev) == NULL && count_kind(0, 'W') == 0 && live_blocks() == 0);
	model_reset();
	addr_for[1] = 0x100000000ull;	/* not reachable by a 32-bit base */
	assert(zx_pp_tables_init(&dev) == NULL && count_kind(0, 'W') == 0 && live_blocks() == 0);
	model_reset();
	addr_for[1] = 0xffe00000ull;	/* ends above 4 GiB */
	assert(zx_pp_tables_init(&dev) == NULL && count_kind(0, 'W') == 0 && live_blocks() == 0);
	model_reset();
	mask_fail = true;
	assert(zx_pp_tables_init(&dev) == NULL && count_kind(0, 'A') == 0 && count_kind(0, 'W') == 0);
	model_reset();
	map_fail = true;
	assert(zx_pp_tables_init(&dev) == NULL && mmio(0) == 0);
}

static void t_teardown_order(void)
{
	static const struct want seq[] = {
		{ 'X', 0 },
		{ 'L', 0 }, { 'U', 0 }, { 'L', 0 }, { 'U', 0 },
		{ 'R', 0x923a0024u }, { 'W', 0x923a0024u },
		{ 'R', 0x923a0020u }, { 'W', 0x923a0020u },
		{ 'R', 0x923a0024u }, { 'F', 0x46400000u },
		{ 'R', 0x923a0020u }, { 'F', 0x45f00000u },
	};
	struct zx_pp *pp = up();
	u32 d[17];
	unsigned mark;

	assert(zx_pp_cla_read(pp, 7, 1, d, 1) == 0);
	mark = nev;
	zx_pp_tables_remove(pp);
	expect_sequence(mark, "XLURWF", seq, ARRAY_SIZE(seq));
	assert(!last_write(PA(PONPP, 0x24)) && !last_write(PA(PONPP, 0x20)));
	assert(!R32(PONPP, 0x20) && !R32(PONPP, 0x24) && live_blocks() == 0);
	assert(nactions == 0 && nremoved == 1 && !pp->cla.enabled && !pp->pm.enabled);
	mark = nev;
	assert(zx_pp_cla_read(pp, 7, 1, d, 1) == -ENODEV);
	assert(zx_pp_pm_write(pp, 0, 1, d, 3) == -ENODEV);
	assert(mmio(mark) == 0);
	devres_release_all();	/* nothing runs twice */
	assert(mmio(mark) == 0 && count_kind(mark, 'F') == 0);
	zx_pp_tables_remove(NULL);

	/* A later probe failure releases the same way through devres. */
	pp = up();
	mark = nev;
	devres_release_all();
	expect_sequence(mark, "XLURWF", seq, ARRAY_SIZE(seq));

	/* devm_add_action_or_reset failure tears down at once. */
	model_reset();
	action_fail = true;
	assert(zx_pp_tables_init(&dev) == NULL);
	assert(ndirs == 0 && live_blocks() == 0 && !R32(PONPP, 0x20) && !R32(PONPP, 0x24));

	/* A clear that does not stick: never free what the engine may reach. */
	pp = up();
	base_ignore_zero[1] = true;
	mark = nev;
	zx_pp_tables_remove(pp);
	assert(count(mark, 'F', 0x46400000u) == 0 && count(mark, 'F', 0x45f00000u) == 1);
	assert(live_blocks() == 1 && n_err == 1 && strstr(last_msg, "leaking"));
}

static const struct dfile *find_file(const char *name)
{
	unsigned i;

	for (i = 0; i < ndfiles; i++)
		if (!strcmp(dfiles[i].name, name))
			return &dfiles[i];
	assert(!"no such debugfs file");
	return NULL;
}
static void open_file(const char *name, struct file *f)
{
	const struct dfile *df = find_file(name);
	struct inode inode = { .i_private = df->data };

	memset(f, 0, sizeof(*f));
	assert(df->fops->open(&inode, f) == 0);
}
static ssize_t do_read(const char *name, char *buf, size_t n, loff_t *pos)
{
	struct file f;

	open_file(name, &f);
	return find_file(name)->fops->read(&f, buf, n, pos);
}

static void t_debugfs_readonly(void)
{
	struct zx_pp *pp = up();
	static char buf[8192];
	unsigned i, j, mark;
	loff_t pos;
	u32 word;

	assert(ndirs == 1 && ndfiles == 1 + ARRAY_SIZE(zx_pp_tables));
	assert(!strcmp(dfiles[0].name, "status") && dfiles[0].data == pp);
	for (i = 0; i < ndfiles; i++) {
		assert(dfiles[i].mode == 0400 && dfiles[i].parent == &dir_dentry);
		assert(dfiles[i].fops->read && dfiles[i].fops->open);
	}
	for (i = 0; i < ARRAY_SIZE(zx_pp_tables); i++) {
		const struct zx_pp_table *t = &zx_pp_tables[i];
		const struct zx_pp_engine *e = t->pm ? &pp->pm : &pp->cla;
		const struct dfile *df = &dfiles[1 + i];

		assert(!strcmp(df->name, t->name) && df->data == &pp->files[i]);
		assert(df->fops == &zx_pp_table_fops && df->size == (long long)t->depth * t->words * 4);
		assert(t->depth && t->sel <= e->sel_max && t->words && t->words <= e->max_words);
		assert(t->depth - 1u < e->addr_limit);
		for (j = 0; j < i; j++)
			assert(strcmp(zx_pp_tables[j].name, t->name));
	}

	/* One entry is one indirect read at that address. */
	pos = 5 * 4;
	mark = nev;
	assert(do_read("cla_cpu_queue_id", buf, 4, &pos) == 4 && pos == 24);
	assert(count(mark, 'W', PA(CLA, 0x14)) == 1);
	assert(last_write(PA(CLA, 0x14)) == (0xa0000000u | 5u | 7u << 22 | 1u << 27));
	memcpy(&word, buf, 4);
	assert(word == ram_default(CLA, 7, 5, 0));
	pos = 3 * 60;
	mark = nev;
	assert(do_read("cla_hash0", buf, 60, &pos) == 60 && count(mark, 'W', PA(CLA, 0x14)) == 1);
	for (i = 0; i < 15; i++) {
		memcpy(&word, buf + 4 * i, 4);
		assert(word == ram_default(CLA, 2, 3, i));
	}
	pos = 2 * 32 + 0;
	assert(do_read("pm_diag", buf, 32, &pos) == 32);
	for (i = 0; i < 8; i++) {
		memcpy(&word, buf + 4 * i, 4);
		assert(word == ram_default(PM, 13, 2, i));
	}

	/* Malformed requests touch no register. */
	mark = nev;
	pos = 2;
	assert(do_read("cla_cpu_queue_id", buf, 4, &pos) == -EINVAL);
	pos = 0;
	assert(do_read("cla_cpu_queue_id", buf, 3, &pos) == -EINVAL);
	pos = -4;
	assert(do_read("cla_cpu_queue_id", buf, 4, &pos) == -EINVAL);
	pos = 1024 * 4;
	assert(do_read("cla_cpu_queue_id", buf, 4, &pos) == 0);
	assert(mmio(mark) == 0);

	/* At most 64 entries per read() call, and never past the end. */
	pos = 0;
	mark = nev;
	assert(do_read("pm_cmd_ram", buf, 4096, &pos) == 256 && pos == 256);
	assert(count(mark, 'W', PA(PM, 0x14)) == 64);
	pos = 2 * 32;
	assert(do_read("pm_diag", buf, 1000, &pos) == 64 && pos == 128);
	assert(do_read("pm_diag", buf, 1000, &pos) == 0);

	copy_fail = true;
	pos = 0;
	assert(do_read("cla_cpu_queue_id", buf, 4, &pos) == -EFAULT && pos == 0);
	copy_fail = false;

	/* A timeout part-way returns what was read, then the engine stays off. */
	em[CLA].budget_on = true;
	em[CLA].budget = 4;	/* two reads: pre-poll and post-poll each */
	pos = 0;
	assert(do_read("cla_extra_index", buf, 5 * 20, &pos) == 40 && pos == 40);
	assert(do_read("cla_extra_index", buf, 20, &pos) == -EIO);

	pos = 0;
	memset(buf, 0, sizeof(buf));
	assert(do_read("status", buf, sizeof(buf) - 1, &pos) > 0);
	assert(strstr(buf, "pm_base dma=") && strstr(buf, "acl_base dma="));
	assert(strstr(buf, "prior=0x56409000 programmed=0x45f00000 now=0x45f00000"));
	assert(strstr(buf, "prior=0x5f600000 programmed=0x46400000 now=0x46400000"));
	/* glibc prints %#x of 0 without "0x"; the kernel's vsnprintf adds it. */
	assert(strstr(buf, "cla status=") && strstr(buf, " enabled=1 faulted=1 reads="));
	assert(strstr(buf, "pm status=0x00000001 enabled=1 faulted=0"));
}

/* The aging accessor is CLA sel 8 with the table's own depth bound, so a
 * caller that miscalculates a bucket is refused instead of reading another
 * table's word and reporting it as a hit.
 */
static void t_aging_accessor(void)
{
	struct zx_pp *pp = up();
	u32 v = 0, mark;

	assert(zx_pp_aging_read(pp, 0, &v) == 0);
	assert(em[CLA].sel == 8 && em[CLA].addr == 0 && em[CLA].last_op == 1);
	assert(zx_pp_aging_read(pp, ZX_PP_CLA_AGING_DEPTH - 1, &v) == 0);
	assert(em[CLA].addr == ZX_PP_CLA_AGING_DEPTH - 1);
	assert(zx_pp_aging_write(pp, 519, 0) == 0);
	assert(em[CLA].sel == 8 && em[CLA].addr == 519 && em[CLA].last_op == 0);

	/* Out of range and NULL are refused before any register access. */
	mark = nev;
	assert(zx_pp_aging_read(pp, ZX_PP_CLA_AGING_DEPTH, &v) == -EINVAL);
	assert(zx_pp_aging_write(pp, ZX_PP_CLA_AGING_DEPTH, 0) == -EINVAL);
	assert(zx_pp_aging_read(pp, 0, NULL) == -EINVAL);
	assert(nev == mark);
	assert(zx_pp_aging_read(NULL, 0, &v) == -ENODEV);
	assert(zx_pp_aging_write(NULL, 0, 0) == -ENODEV);
}

/* The hash selectors come from hardware, not from an assumption of zero. */
static void t_hash_config(void)
{
	struct zx_pp *pp;
	struct zx_pp_hash_cfg cfg;
	unsigned i;

	pp = up();
	assert(zx_pp_hash_config(pp, &cfg) == 0);
	/* measured reset values: 0x9238c090 = 0x00e400e4, 0x9238c094 = 0 */
	for (i = 0; i < 4; i++) {
		assert(cfg.inner[i] == i);
		assert(cfg.outer[i] == i);
	}
	assert(cfg.outer_num == 0 && cfg.outer_space == 0);
	assert(cfg.usable);

	/* A configured outer table means mode 1, which is undecoded: placement
	 * must be refused rather than guessed.
	 */
	model_reset();
	W32(CLA, 0x94, 0x00000001u);
	pp = zx_pp_tables_init(&dev);
	assert(pp);
	assert(zx_pp_hash_config(pp, &cfg) == 0);
	assert(!cfg.usable);

	/* Different selectors are honoured, not normalised away. */
	model_reset();
	W32(CLA, 0x90, 0x00e40000u);	/* inner all 0, outer 0,1,2,3 */
	pp = zx_pp_tables_init(&dev);
	assert(pp);
	assert(zx_pp_hash_config(pp, &cfg) == 0);
	for (i = 0; i < 4; i++) {
		assert(cfg.inner[i] == 0);
		assert(cfg.outer[i] == i);
	}

	assert(zx_pp_hash_config(NULL, &cfg) == -ENODEV);
	assert(zx_pp_hash_config(pp, NULL) == -EINVAL);
}

int main(int argc, char **argv)
{
	static const struct { const char *name; void (*fn)(void); } cases[] = {
		{ "cmd_encoding", t_cmd_encoding },
		{ "poll_bound", t_poll_bound },
		{ "pm_word_placement", t_pm_word_placement },
		{ "write_ordering", t_write_ordering },
		{ "rmw", t_rmw },
		{ "base_before_indirect", t_base_before_indirect },
		{ "teardown_order", t_teardown_order },
		{ "debugfs_readonly", t_debugfs_readonly },
		{ "aging_accessor", t_aging_accessor },
		{ "hash_config", t_hash_config },
	};
	unsigned i;

	assert(argc == 2);
	for (i = 0; i < ARRAY_SIZE(cases); i++)
		if (!strcmp(argv[1], cases[i].name)) {
			cases[i].fn();
			check_rmw_pairs();
			model_reset();
			printf("PASS %s\n", cases[i].name);
			return 0;
		}
	return 2;
}
'''


def strip_includes(text):
    return re.sub(r'^#include[^\n]*\n', '', text, flags=re.M)


def preprocess(text, defines=()):
    run = subprocess.run(['cc', '-E', '-P', '-x', 'c', '-', *defines],
                         input=strip_includes(text), capture_output=True, text=True, check=True)
    return run.stdout


class PpTablesModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        root = Path(cls.directory.name)
        source, cls.executable = root / 'pp.c', root / 'pp'
        # The model strips #include, so the header's own declarations have to
        # be supplied. Take them from the real header rather than restating
        # them here, so neither can drift from the driver's copy.
        header = PP_HEADER.read_text()
        supplied = '\n'.join([
            re.search(r'^#define\s+ZX_PP_CLA_AGING_DEPTH\s+\S+$', header, re.M).group(),
            exact_struct(header, 'zx_pp_hash_cfg'),
        ])
        source.write_text(PRELUDE + supplied + '\n' +
                          strip_includes(PP_SOURCE.read_text()) + CASES)
        built = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                '-Wno-unused-parameter', '-Wno-unused-function',
                                str(source), '-o', str(cls.executable)],
                               capture_output=True, text=True, timeout=60)
        if built.returncode:
            cls.directory.cleanup()
            raise AssertionError(built.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def run_case(self, name):
        run = subprocess.run([str(self.executable), name], capture_output=True, text=True,
                             timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn(f'PASS {name}', run.stdout)

    def test_command_encoding_bounds_and_reserved_bits(self):
        self.run_case('cmd_encoding')

    def test_ready_poll_is_bounded_and_latches_the_engine(self):
        self.run_case('poll_bound')

    def test_pm_words_4_to_7_live_at_0x100_and_cla_is_contiguous(self):
        self.run_case('pm_word_placement')

    def test_write_is_cmd_then_highest_word_down_ending_at_data0(self):
        self.run_case('write_ordering')

    def test_every_register_write_is_a_read_modify_write(self):
        self.run_case('rmw')

    def test_bases_programmed_and_verified_before_any_indirect_operation(self):
        self.run_case('base_before_indirect')

    def test_teardown_clears_bases_before_freeing_and_never_frees_a_live_base(self):
        self.run_case('teardown_order')

    def test_a_flow_that_cannot_be_cleared_keeps_the_tables(self):
        """A live CLA entry references PM entries inside these tables.

        If the flow test path cannot clear its entry, teardown must keep both
        tables rather than hand memory back that the engine may still walk.
        """
        pp = PP_SOURCE.read_text()
        teardown = function(pp, 'zx_pp_teardown')
        self.assertIn('if (zx_pp_flow_fini())', teardown)
        self.assertIn('pp->live_flow = true', teardown)
        free_table = function(pp, 'zx_pp_free_table')
        self.assertIn('pp->live_flow', free_table)
        # the keep branch must be taken before the allocator is called
        self.assertLess(free_table.index('pp->live_flow'),
                        free_table.index('dma_free_coherent'))
        # and the flag exists on the context
        self.assertIn('bool live_flow;', exact_struct(pp, 'zx_pp'))

    def test_debugfs_is_read_only_and_reads_exactly_the_requested_entries(self):
        self.run_case('debugfs_readonly')

    def test_aging_accessor_is_cla_sel_8_bounded_to_the_table(self):
        self.run_case('aging_accessor')

    def test_hash_selectors_are_read_from_hardware_not_assumed(self):
        self.run_case('hash_config')


class PpTablesSourcePolicyTests(unittest.TestCase):
    def test_no_userspace_write_path_and_no_other_interfaces(self):
        code = set(tokens(PP_SOURCE.read_text()))
        forbidden = {'write', 'copy_from_user', 'get_user', 'kstrtouint', 'kstrtou32', 'kstrtoul',
                     'debugfs_create_u32', 'debugfs_create_x32', 'debugfs_create_bool',
                     'debugfs_create_regset32', 'proc_create', 'module_param', 'sysfs_create_group',
                     'DEVICE_ATTR', 'writel_relaxed', 'readl_relaxed', 'ioremap', 'iounmap'}
        self.assertFalse(code & forbidden, code & forbidden)
        modes = re.findall(r'debugfs_create_file(?:_size)?\([^,]+,\s*(0\d+)', PP_SOURCE.read_text())
        self.assertEqual(modes, ['0400', '0400'])

    def test_constants_match_the_recorded_evidence(self):
        text = PP_SOURCE.read_text()
        expected = {
            'ZX_PP_CLA_PHYS': '0x9238c000', 'ZX_PP_PM_PHYS': '0x9239c000',
            'ZX_PP_PONPP_PHYS': '0x923a0000', 'ZX_PP_IND_CMD': '0x14',
            'ZX_PP_IND_STATUS': '0x18', 'ZX_PP_IND_DATA': '0x1c', 'ZX_PP_PM_DATA_HI': '0x100',
            'ZX_PP_PM_DATA_LO_WORDS': '4', 'ZX_PP_CMD_SEL_SHIFT': '22', 'ZX_PP_CMD_OP_SHIFT': '27',
            'ZX_PP_OP_WRITE': '0', 'ZX_PP_OP_READ': '1',
            'ZX_PP_CLA_CMD_MASK': '0x0fffffff', 'ZX_PP_PM_CMD_MASK': '0x0fcfffff',
            'ZX_PP_CLA_ADDR_LIMIT': '0x400000', 'ZX_PP_PM_ADDR_LIMIT': '0x100000',
            'ZX_PP_CLA_SEL_MAX': '9', 'ZX_PP_PM_SEL_MAX': '31', 'ZX_PP_CLA_WORDS': '17',
            'ZX_PP_PM_WORDS': '8', 'ZX_PP_DATA_MASK': '0xffffffff', 'ZX_PP_POLL_READS': '20',
            'ZX_PP_PM_BASE_REG': '0x20', 'ZX_PP_ACL_BASE_REG': '0x24',
            'ZX_PP_BASE_MASK': '0xffffffff', 'ZX_PP_PM_TABLE_SIZE': 'SZ_1M',
            'ZX_PP_ACL_TABLE_SIZE': 'SZ_4M', 'ZX_PP_TABLE_ALIGN': 'SZ_128K',
            # CLA aging (sel 8) and the hash polynomial-selector registers.
            'ZX_PP_CLA_SEL_AGING': '8', 'ZX_PP_CLA_HASH_POLY_REG': '0x90',
            'ZX_PP_CLA_HASH_OUTER_REG': '0x94',
        }
        for name, value in expected.items():
            found = re.findall(r'^#define\s+' + name + r'\s+(\S+)', text, re.M)
            self.assertEqual(found, [value], name)

    def test_the_aging_table_is_exposed_at_its_full_depth(self):
        """sel 8, one word per exact-match hash address, 0..519."""
        text = PP_SOURCE.read_text()
        rows = re.findall(r'\{\s*"cla_aging",\s*(\w+),\s*(\d+),\s*(\d+),\s*(\d+)\s*\}', text)
        self.assertEqual(rows, [('false', '8', '1', '520')])
        # the header owns the public depth constant; pp.c must not restate it
        header = PP_HEADER.read_text()
        self.assertEqual(re.findall(r'^#define\s+ZX_PP_CLA_AGING_DEPTH\s+(\S+)', header, re.M),
                         ['520'])
        self.assertEqual(re.findall(r'^#define\s+ZX_PP_CLA_AGING_DEPTH\s+', text, re.M), [])


class PpTablesBuildGateTests(unittest.TestCase):
    def test_kconfig_symbol_is_bool_default_n_behind_the_ethernet_driver(self):
        text = KCONFIG.read_text()
        block = re.search(r'^config ZX279128_PP_TABLES\n(.*?)(?=^\S)', text, re.M | re.S)
        self.assertIsNotNone(block)
        body = block.group(1)
        self.assertIn('\tbool "', body)
        self.assertIn('\tdepends on ZX279128_ETH\n', body)
        self.assertIn('\tdefault n\n', body)
        self.assertNotIn('select', body)

    def test_no_shipped_config_or_profile_enables_the_symbol(self):
        config = CONFIG.read_text().splitlines()
        self.assertEqual(config.count('# CONFIG_ZX279128_PP_TABLES is not set'), 1)
        self.assertFalse([line for line in config if line.startswith(SYMBOL + '=')])
        check = ROOT / 'ci/check.sh'
        self.assertIn("grep -q '^CONFIG_ZX279128_PP_TABLES=y' files/target/linux/armsr/config-6.6",
                      check.read_text())
        candidates = [ROOT / 'build.sh', ROOT / 'seed.config', check]
        candidates += [p for p in (ROOT / 'files').rglob('*') if p.is_file()]
        candidates += [p for p in (ROOT / 'tools').rglob('*') if p.is_file()]
        # Any assignment counts, quoted or not; only an anchored grep pattern
        # (the CI gate itself) is not one.
        setting = re.compile(rb'(?<!\^)' + SYMBOL.encode() + rb'\s*=')
        build = ROOT / 'build.sh'
        for path in candidates:
            data = path.read_bytes()
            if path == build:
                data = self.build_sh_without_the_diagnostic_knob(data)
            self.assertFalse(setting.search(data), path)
            if path not in (CONFIG, KCONFIG, MAKEFILE, ETH_SOURCE, PP_HEADER, PP_SOURCE,
                            PP_FLOW_SOURCE, PP_OFFLOAD_SOURCE, check):
                self.assertNotIn(b'ZX279128_PP_TABLES', data, path)

    def build_sh_without_the_diagnostic_knob(self, data):
        """build.sh may name the symbol only in its diagnostic-only PP_TABLES knob:
        the refusal for non-diagnostic profiles, the anchored "is not set" -> =y
        replacement of the BUILD COPY, anchors/grep assertions and messages. Strip
        exactly those forms; anything left must not set or name the symbol."""
        text = data.decode()
        self.assertIn('if [ "$PP_TABLES" = 1 ] && [ "$BOOT_PROFILE" != diagnostic ]; then', text)
        self.assertIn('PP_TABLES=1 is for diagnostic RAM-boot qualification images only', text)
        allowed = (
            re.compile(r"^\s*sed -i 's/\^# CONFIG_ZX279128_PP_TABLES is not set\$/CONFIG_ZX279128_PP_TABLES=y/' \"\$TGT\"$"),
            re.compile(r"^\s*anchor [01] '\^#? ?CONFIG_ZX279128_PP_TABLES(=y| is not set)\$' \"\$TGT\"$"),
            re.compile(r"^\s*(elif |if )?grep -qx? '?CONFIG_ZX279128_PP_TABLES=y'? "),
            re.compile(r'^\s*echo "(==> PP_TABLES build|ERROR: [^"]*PP_TABLES)'),
        )
        kept = [line for line in text.splitlines()
                if 'ZX279128_PP_TABLES' not in line or not any(rx.search(line) for rx in allowed)]
        return '\n'.join(kept).encode()

    def test_makefile_links_the_component_only_when_enabled(self):
        make = shutil.which('make')
        if not make:
            raise unittest.SkipTest('requires GNU make')
        with tempfile.TemporaryDirectory() as directory:
            wrapper = Path(directory) / 'probe.mk'
            wrapper.write_text(f'include {MAKEFILE}\n'
                               '$(info OBJY=$(sort $(obj-y)))\n'
                               '$(info OBJM=$(sort $(obj-m)))\n'
                               '$(info MULTI=$(zx279128_eth-y))\n'
                               'all: ;\n')
            results = {}
            for eth in ('y', 'm'):
                for pp in ('', 'y'):
                    args = [make, '-s', '-f', str(wrapper), f'CONFIG_ZX279128_ETH={eth}',
                            'CONFIG_ZX279128_PCIE_PROBE_TEST=y']
                    if pp:
                        args.append(f'{SYMBOL}={pp}')
                    run = subprocess.run(args, capture_output=True, text=True, cwd=directory,
                                         check=True)
                    results[eth, pp] = dict(line.split('=', 1) for line in run.stdout.splitlines())
            self.assertEqual(results['y', ''], {'OBJY': 'zx279128-eth.o zx_pcie_probe_test.o',
                                                'OBJM': '', 'MULTI': ''})
            self.assertEqual(results['m', ''], {'OBJY': 'zx_pcie_probe_test.o',
                                                'OBJM': 'zx279128-eth.o', 'MULTI': ''})
            self.assertEqual(results['y', 'y'], {'OBJY': 'zx279128_eth.o zx_pcie_probe_test.o',
                                                 'OBJM': '',
                                                 # MULTI is unsorted: Makefile order
                                                 'MULTI': 'zx279128-eth.o zx279128-pp.o '
                                                          'zx279128-pp-hash.o'})
            self.assertEqual(results['m', 'y']['OBJM'], 'zx279128_eth.o')

    def test_nothing_reaches_the_ethernet_driver_when_the_symbol_is_off(self):
        eth = ETH_SOURCE.read_text()
        base = ['-DIS_ENABLED(x)=(x)', '-DCONFIG_ZX279128_ETH_DEBUG=0']
        off = preprocess(eth, base)
        on = preprocess(eth, base + [f'-D{SYMBOL}=1'])
        ours = r'\bzx_pp\b|\bzx_pp_(?:tables|cla|pm)_\w+'
        self.assertFalse(re.findall(ours, off))
        self.assertNotIn('pp_bring_up', off)
        on_tokens = re.findall(ours, on)
        self.assertEqual(sorted(on_tokens), ['zx_pp', 'zx_pp_tables_init', 'zx_pp_tables_remove'])
        self.assertEqual(eth.count('#include "zx279128-pp.h"'), 1)
        # The seventh guards zx_dp_reset_work(): no datapath reset under live
        # tables (the cold bring-up re-parks the PM/ACL bases).
        self.assertEqual(len(re.findall(r'^#ifdef ' + SYMBOL + r'$', eth, re.M)), 7)
        reset = function(eth, 'zx_dp_reset_work')
        self.assertIn('#ifdef ' + SYMBOL, reset)
        self.assertIn('if (ze->pp)', reset)
        self.assertFalse(re.search(r'#if\s+IS_ENABLED\(' + SYMBOL, eth))
        header = PP_HEADER.read_text()
        self.assertFalse(re.findall(r'\w+', preprocess(header)))
        self.assertIn('zx_pp_tables_init', preprocess(header, [f'-D{SYMBOL}=1']))

    def test_probe_hook_follows_the_bring_up_and_remove_hook_precedes_devres(self):
        eth = ETH_SOURCE.read_text()
        probe = function(eth, 'zx_eth_probe')
        remove = function(eth, 'zx_eth_remove')
        init = function(eth, 'zx_eth_datapath_init')
        # The flag is raised only by the PP bring-up block, after its last write.
        flag = '\t\tze->pp_bring_up = true;'
        self.assertEqual(eth.count('pp_bring_up = true'), 1)
        self.assertEqual(init.count(flag), 1)
        done = init.index('pr_info("zx-eth: packet processor bring-up done\\n");')
        self.assertLess(init.index('writel(0, ppa + 0x14);'), done)
        self.assertLess(done, init.index(flag))
        self.assertFalse(init[done:init.index(flag)].count(';') - 1)
        hook = '\tif (ze->pp_bring_up)\n\t\tze->pp = zx_pp_tables_init(dev);\n'
        self.assertEqual(probe.count(hook), 1)
        self.assertEqual(eth.count('zx_pp_tables_init(dev)'), 1)
        self.assertLess(probe.index('ret = zx_eth_datapath_init(ze);'), probe.index(hook))
        self.assertLess(probe.index(hook), probe.index('ret = devm_register_netdev(dev, ndev);'))
        self.assertEqual(remove.count('zx_pp_tables_remove(ze->pp);\n\tze->pp = NULL;'), 1)
        self.assertLess(remove.index('zx_eth_close_ports(ze);'), remove.index('zx_pp_tables_remove'))
        struct = exact_struct(eth, 'zx_eth')
        self.assertIn('bool pp_bring_up;', struct)
        self.assertIn('struct zx_pp *pp;', struct)


PROBE_STUBS = r'''
struct zx_pp { bool live; struct device *dev; };
static struct zx_pp pp_object;
static unsigned pp_inits, pp_removes, pp_teardowns;
static bool pp_unavailable, pp_created;
static void pp_teardown(void *arg)
{
    struct zx_pp *p = arg;
    assert(p == &pp_object && p->live);
    p->live = false; pp_teardowns++;
}
static struct zx_pp *zx_pp_tables_init(struct device *d)
{
    /* After this probe's own bring-up, before any netdev is visible. */
    assert(live && d == live->dev && init_calls == 1 && hardware_started && !registrations);
    pp_inits++;
    if (pp_unavailable || failed()) return NULL;
    pp_object.live = true; pp_object.dev = d; pp_created = true;
    add(pp_teardown, &pp_object);
    return &pp_object;
}
static void zx_pp_tables_remove(struct zx_pp *p)
{
    pp_removes++;
    if (!p) return;
    for (unsigned i = nactions; i-- > 0; )
        if (actions[i].fn == pp_teardown && actions[i].arg == p) {
            memmove(&actions[i], &actions[i + 1], (nactions - i - 1) * sizeof(actions[0]));
            nactions--;
            pp_teardown(p);
            return;
        }
    assert(!"remove without a registered teardown");
}
'''

PROBE_CASES = r'''
static unsigned exercise_pp(unsigned failure, bool expect_init) {
    memset(memory,0,sizeof(memory));memset(actions,0,sizeof(actions));
    nmem=nactions=calls=seed_writes=active_ports=registrations=0;
    irq_requests=irq_releases=disarms=proc_entries=init_calls=0;fail_at=failure;
    in_timer=hardware_started=false;live=zx_dbg_ze=zx_eth_singleton=NULL;
    pp_inits=pp_removes=pp_teardowns=0;pp_created=false;pp_object.live=false;
    struct platform_device p={.dev={.of_node=&node}};
    int result=zx_eth_probe(&p);unsigned total=calls;
    struct zx_eth *z=live;
    if(result==0) {
        assert(pp_inits==(expect_init?1u:0u));
        assert(z->pp==(pp_created?&pp_object:NULL));
        zx_eth_remove(&p);
        assert(pp_removes==1 && z->pp==NULL && !pp_object.live);
        assert(pp_teardowns==(pp_created?1u:0u));
    } else {
        assert(failure && pp_removes==0);
    }
    while(nactions) { struct action a=actions[--nactions];a.fn(a.arg); }
    assert(!pp_object.live && pp_teardowns==(pp_created?1u:0u));
    assert(!active_ports && irq_requests==irq_releases);
    for(unsigned i=0;i<nmem;i++) { assert(!memory[i].alive);free(memory[i].ptr); }
    return total;
}
int main(void) {
    unsigned total=exercise_pp(0,true), failure, created_then_failed=0;
    assert(pp_created);
    for(failure=1;failure<=total;failure++) {
        exercise_pp(failure,true);
        created_then_failed+=pp_created && pp_teardowns==1;
    }
    assert(created_then_failed>5);
    pp_unavailable=true; exercise_pp(0,true); assert(!pp_created); pp_unavailable=false;
    if(CONFIG_ZX279128_ETH_DEBUG) {
        inherited_warm=true; zx_force_dp_init=false;
        exercise_pp(0,false);   /* warm attach: this probe ran no bring-up */
        zx_force_dp_init=true; zx_skip_dp_init=true;
        exercise_pp(0,false);
        zx_skip_dp_init=false; inherited_warm=false;
    }
    printf("PASS probe/remove PP hooks: %u failure points\n",total);
    return 0;
}
'''


class PpTablesProbeIntegrationTests(unittest.TestCase):
    def test_actual_probe_and_remove_with_the_symbol_on(self):
        source = ETH_SOURCE.read_text()
        structs = '\n'.join([exact_enum(source, 'zx_eth_reg')] +
                            [exact_struct(source, name) for name in
                             ('zx_rx_queue', 'zx_eth', 'zx_port_priv')])
        functions = '\n'.join(function(source, name) for name in (
            'zx_datapath_warm', 'zx_phy_node_put', 'zx_eth_prepare_port_ndev',
            'zx_eth_add_port_ndev', 'zx_tx_done_timer', 'zx_bm_seed_freelists',
            'zx_napi_delete', 'zx_eth_disarm', 'zx_eth_close_ports', 'zx_tx_origin_init',
            'zx_eth_probe', 'zx_eth_remove'))
        gate = next(line for line in source.splitlines()
                    if line.startswith('#define ZX_HAVE_DEBUG_IFACES '))
        force_default = re.search(r'static bool zx_force_dp_init[^;]*;', source).group()
        with tempfile.TemporaryDirectory() as directory:
            cfile, executable = Path(directory) / 'probe.c', Path(directory) / 'probe'
            # The stubbed datapath init stands for the real one, whose PP
            # bring-up block raises the flag (checked textually above).
            anchor = '    init_calls++;\n'
            boundaries = test_eth_probe.BOUNDARIES
            self.assertEqual(boundaries.count(anchor), 1)
            boundaries = boundaries.replace(anchor, anchor + '    z->pp_bring_up=true;\n')
            cfile.write_text(test_eth_probe.MODEL + '\n' + gate + '\n' + structs + force_default +
                             boundaries + PROBE_STUBS + functions + PROBE_CASES)
            for debug in (0, 1):
                with self.subTest(debug=debug):
                    built = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                            '-Wno-unused-function', f'-D{SYMBOL}=1',
                                            f'-DCONFIG_ZX279128_ETH_DEBUG={debug}',
                                            str(cfile), '-o', str(executable)],
                                           capture_output=True, text=True, timeout=60)
                    self.assertEqual(built.returncode, 0, built.stderr)
                    run = subprocess.run([str(executable)], capture_output=True, text=True,
                                         timeout=30)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


TREES = sorted((ROOT / 'openwrt/build_dir').glob('target-*/linux-armsr_armv7/linux-6.6.151'))
TOOLCHAINS = sorted((ROOT / 'openwrt/staging_dir').glob('toolchain-arm_cortex-a9_gcc-*_musl_eabi'))


class PpTablesRealHeaderTests(unittest.TestCase):
    def test_compiles_against_the_pinned_kernel_with_its_own_flags(self):
        if len(TREES) != 1 or len(TOOLCHAINS) != 1:
            raise unittest.SkipTest('requires the pinned prepared kernel tree and toolchain')
        kernel, toolchain = TREES[0].resolve(), TOOLCHAINS[0].resolve()
        record = kernel / 'drivers/net/ethernet/zte/.zx279128-eth.o.cmd'
        if not record.exists():
            raise unittest.SkipTest('kernel tree has no recorded Ethernet compile')
        line = next(l for l in record.read_text().splitlines()
                    if l.startswith('savedcmd_drivers/net/ethernet/zte/zx279128-eth.o := '))
        command = line.split(' := ', 1)[1].split(' -c -o ', 1)[0]
        command = re.sub(r'-Wp,-MMD,\S+ ', '', command)
        command = re.sub(r'(^|\s)(-I|-include\s+)?\./', lambda m: m.group(1) + (m.group(2) or '')
                         + str(kernel) + '/', command)
        words = shlex.split(command)
        compiler = toolchain / 'bin' / words[0]
        environment = dict(os.environ, STAGING_DIR=str(toolchain.parent))
        with tempfile.TemporaryDirectory() as directory:
            for name in ('zx279128-pp.c', 'zx279128-eth.c'):
                with self.subTest(source=name):
                    run = subprocess.run([str(compiler), *words[1:], f'-D{SYMBOL}=1', '-c',
                                          '-o', str(Path(directory) / 'out.o'), str(ZTE / name)],
                                         capture_output=True, text=True, cwd=directory,
                                         env=environment, timeout=300)
                    self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
