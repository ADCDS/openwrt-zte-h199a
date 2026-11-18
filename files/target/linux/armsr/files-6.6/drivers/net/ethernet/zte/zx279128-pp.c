// SPDX-License-Identifier: GPL-2.0
/*
 * Packet-processor (PP) table access for the ZTE/Sanechips ZX279128S.
 *
 * First, gated step toward hardware flow offload. Nothing here offloads
 * traffic. It provides:
 *  - the CLA (classifier) and PM (packet modify) indirect table ports, as the
 *    vendor tm.ko accessors drive them;
 *  - the PM and ACL DRAM tables, allocated here and programmed into the PonPp
 *    base registers before any indirect operation is allowed;
 *  - a read-only debugfs view of on-chip tables whose geometry the vendor
 *    readers bound.
 *
 * Evidence, what is unproven, and the hardware qualification steps:
 * docs/PP-OFFLOAD.md.
 */
#include <linux/bits.h>
#include <linux/debugfs.h>
#include <linux/delay.h>
#include <linux/device.h>
#include <linux/dma-mapping.h>
#include <linux/fs.h>
#include <linux/io.h>
#include <linux/kernel.h>
#include <linux/minmax.h>
#include <linux/mutex.h>
#include <linux/seq_file.h>
#include <linux/sizes.h>
#include <linux/uaccess.h>

#include "zx279128-pp.h"

/* Register windows. The stock kernel maps 0x92000000 statically and tm.ko
 * addresses register word w at 0x92000000 + 4 * w (claRegTable, ppPmRegTable,
 * PonPpRegTable in tm.ko .data).
 */
#define ZX_PP_CLA_PHYS		0x9238c000
#define ZX_PP_PM_PHYS		0x9239c000
#define ZX_PP_PONPP_PHYS	0x923a0000

/* Indirect port, same offsets in both engines. */
#define ZX_PP_IND_CMD		0x14
#define ZX_PP_IND_STATUS	0x18
#define ZX_PP_IND_READY		BIT(0)
#define ZX_PP_IND_DATA		0x1c	/* word i at +0x1c + 4 * i */
#define ZX_PP_PM_DATA_HI	0x100	/* PM words 4..7 at +0x100 + 4 * (i - 4) */
#define ZX_PP_PM_DATA_LO_WORDS	4

/* CMD = addr | sel << 22 | op << 27 (cla_set_indirect_rw_cmd 0x44c,
 * pp_pm_set_indirect_cmd 0x1c8b8). tmOnuRegWrite preserves the bits outside
 * the table mask: CLA 31:28, PM 31:28 and 21:20.
 */
#define ZX_PP_CMD_SEL_SHIFT	22
#define ZX_PP_CMD_OP_SHIFT	27
#define ZX_PP_OP_WRITE		0
#define ZX_PP_OP_READ		1
#define ZX_PP_CLA_CMD_MASK	0x0fffffff
#define ZX_PP_PM_CMD_MASK	0x0fcfffff
#define ZX_PP_CLA_ADDR_LIMIT	0x400000
#define ZX_PP_PM_ADDR_LIMIT	0x100000
#define ZX_PP_CLA_SEL_MAX	9
#define ZX_PP_PM_SEL_MAX	31

/* CLA selectors this driver names. The rest are only reached through the
 * read-only table list.
 */
#define ZX_PP_CLA_SEL_AGING	8	/* cla_get/set_acl_aging_table 0x7318 */

/* CLA hash polynomial-selector registers (docs/PP-FLOW.md "CLA exact-match
 * hash"). The vendor never writes them, so the reset value is what the engine
 * uses. They are read at init rather than assumed.
 */
#define ZX_PP_CLA_HASH_POLY_REG	0x90	/* 0x9238c090, mask 0x00ff00ff */
#define ZX_PP_CLA_HASH_OUTER_REG 0x94	/* 0x9238c094, mask 0xf */

/* CLA upstream per-action packet counters, decoded from tm_up_statistics_get
 * (tm.ko 0x51f20): fpga word W reads physical 0x92000000 + 4*W, which for the
 * CLA block (base 0x9238c000) is offset 4*(W - 0xe3000). These count what the
 * classification engine DID with each upstream frame, so they are the live
 * instrument for "is the CLA consulted, and does the exact-match hit": a frame
 * the engine classified-but-did-not-match increments trap; a real hit
 * increments fwd. Direct MMIO, read-only, safe after the Ethernet bring-up.
 */
#define ZX_PP_CLA_CNT_FWD	0x3c0	/* 0x9238c3c0, fpga word 0xe30f0 */
#define ZX_PP_CLA_CNT_TRAP	0x3c4	/* 0x9238c3c4, fpga word 0xe30f1 */
#define ZX_PP_CLA_CNT_DROP	0x3c8	/* 0x9238c3c8, fpga word 0xe30f2 */
#define ZX_PP_CLA_CNT_COPY	0x3d8	/* 0x9238c3d8, fpga word 0xe30f6 */

/* CLA DOWNSTREAM per-action packet counters, decoded from tm_dn_statistics_get
 * (tm.ko 0x5298c): it reads fpga words 0xe30f3/4/5/7 through the same four
 * formats as tm_up_statistics_get. Phys = 0x92000000 + 4*word; CLA block base
 * 0x9238c000 so the window offset is 4*(word - 0xe3000).
 *
 * This is the correction PP-KEY §21 turned on: a WAN(eth3)->LAN(eth0) routed
 * frame is uplink->UNI = DOWNSTREAM, so its forward lands here, NOT in the up
 * bank the 0x3c0/4/8/d8 quartet reads. Every §10-§20 "cla fwd=0" was the up
 * bank and was blind to this one. 0x9238c3cc (dn fwd) is the pass criterion
 * for the downstream test flow.
 */
#define ZX_PP_CLA_CNT_DN_FWD	0x3cc	/* 0x9238c3cc, fpga word 0xe30f3 */
#define ZX_PP_CLA_CNT_DN_TRAP	0x3d0	/* 0x9238c3d0, fpga word 0xe30f4 */
#define ZX_PP_CLA_CNT_DN_DROP	0x3d4	/* 0x9238c3d4, fpga word 0xe30f5 */
#define ZX_PP_CLA_CNT_DN_COPY	0x3dc	/* 0x9238c3dc, fpga word 0xe30f7 */
#define ZX_PP_CLA_WORDS		17	/* cla_set_indirect_rw_data: i <= 16 */
#define ZX_PP_PM_WORDS		8	/* pp_pm_ind_acc_data_set: i <= 7 */
#define ZX_PP_MAX_WORDS		ZX_PP_CLA_WORDS
#define ZX_PP_DATA_MASK		0xffffffff

/* The vendor polls the ready flag at most 20 times with no delay and takes
 * success only on reads 1..19. This driver accepts all 20 reads and waits
 * 1 us between them: the same bound, never less patient.
 */
#define ZX_PP_POLL_READS	20
#define ZX_PP_POLL_DELAY_US	1

/* PonPpRegTable id14 / id15: full 32-bit read-write base addresses, written
 * by pon_pp_set_pm_base_addr (0x19718) / pon_pp_set_acl_base_addr (0x19894).
 */
#define ZX_PP_PM_BASE_REG	0x20
#define ZX_PP_ACL_BASE_REG	0x24
#define ZX_PP_BASE_MASK		0xffffffff

/* Sizes are the vendor's layout of its reserved block R (R = top
 * ZX_RESERVE_MEM_SIZE MiB of DRAM): ACL at R + 0x20000 (tm_pon_pp_reg_initial),
 * PM at R + 0x420000, and the next allocation, the normal packet buffers, at
 * R + 0x520000 (pon_tm_bmu_init). The kernel maps exactly R..R + 0x520000 for
 * the CPU side (zx_map_io). Vendor bases are 128 KiB aligned; a coherent
 * allocation of these sizes is aligned to its size.
 */
#define ZX_PP_PM_TABLE_SIZE	SZ_1M
#define ZX_PP_ACL_TABLE_SIZE	SZ_4M
#define ZX_PP_TABLE_ALIGN	SZ_128K

#define ZX_PP_DEBUGFS_MAX_ENTRIES	64	/* per read() call */

struct zx_pp_engine {
	const char *name;
	void __iomem *base;
	struct mutex lock;	/* one indirect operation at a time */
	u32 cmd_mask;
	u32 addr_limit;
	unsigned int sel_max;
	unsigned int max_words;
	bool split_data;	/* PM: words 4..7 live at +0x100 */
	bool enabled;		/* tables live; set only after the bases verify */
	bool faulted;		/* a ready poll timed out; stays set */
	unsigned long reads, writes, timeouts;
};

struct zx_pp_dma_table {
	const char *name;
	size_t size;
	unsigned int reg;
	void *cpu;
	dma_addr_t dma;
	u32 prior;		/* register value found before programming */
	u32 readback;		/* register value after programming */
};

/* On-chip tables exposed read-only. Entry index == CMD address for every one
 * of them. Words and depth come from the vendor reader named in the comment;
 * a table is listed only when that reader bounds both.
 */
struct zx_pp_table {
	const char *name;
	bool pm;
	u8 sel;
	u8 words;
	u16 depth;
};

static const struct zx_pp_table zx_pp_tables[] = {
	{ "cla_extra_index",  false,  0,  5,   16 },	/* cla_get_extra_index_table 0x4420 */
	{ "cla_extra_rule",   false,  1, 17,  160 },	/* cla_get_extra_rule_table 0x5038 */
	{ "cla_hash0",        false,  2, 15,  256 },	/* cla_get_hash_table 0x5f20, idx 0-255 */
	{ "cla_hash1",        false,  3, 15,  128 },	/* idx 256-383 */
	{ "cla_hash2",        false,  4, 15,   64 },	/* idx 384-447 */
	{ "cla_hash3",        false,  5, 15,   64 },	/* idx 448-511 */
	{ "cla_hash4",        false,  6, 15,    8 },	/* idx 512-519 */
	{ "cla_cpu_queue_id", false,  7,  1, 1024 },	/* cla_get_cpu_queue_id 0x6abc */
	{ "cla_aging",        false,  8,  1,  520 },	/* cla_get_acl_aging_table 0x7318, index = hash addr */
	{ "pm_flow_info",     true,   0,  3, 2048 },	/* pp_pm_get_flow_info 0x1d114, (dir << 10) | idx */
	{ "pm_next_hop",      true,   1,  3,  512 },	/* pp_pm_get_next_hop_ram_info 0x1d890 */
	{ "pm_vlan_modify",   true,   2,  1, 1024 },	/* pp_pm_get_vlan_modify_ram_info 0x1dc74 */
	{ "pm_cmd_ram",       true,   3,  1, 8192 },	/* pp_pm_get_cmd_ram_info 0x1de50 */
	{ "pm_sub",           true,   6,  2, 1024 },	/* pp_pm_get_sub_ram_info 0x1e914 */
	{ "pm_diag",          true,  13,  8,    4 },	/* pp_pm_get_diag_ram_info 0x1fe08 */
};

struct zx_pp_dbg_file {
	struct zx_pp *pp;
	const struct zx_pp_table *table;
};

struct zx_pp {
	struct device *dev;
	void __iomem *ponpp;
	struct zx_pp_engine cla;
	struct zx_pp_engine pm;
	struct zx_pp_dma_table pm_tbl;
	struct zx_pp_dma_table acl_tbl;
	bool programmed;	/* base registers may hold our DMA addresses */
	/* A flow install could not be cleared during teardown, so an entry may
	 * still be live in the ACL table. Nothing may be freed.
	 */
	bool live_flow;
	/* CLA hash polynomial selectors, read from hardware at init. */
	struct zx_pp_hash_cfg hash;
	struct dentry *debugfs;
	struct zx_pp_dbg_file files[ARRAY_SIZE(zx_pp_tables)];
};

/* tmOnuRegWrite (0x35844): read, replace the masked field, write. Every CMD
 * and DATA write in tm.ko goes through it, so every write is preceded by a
 * read of the same register. Returns the old value.
 */
static u32 zx_pp_rmw(void __iomem *reg, u32 mask, u32 val)
{
	u32 old = readl(reg);

	writel((old & ~mask) | (val & mask), reg);
	return old;
}

static int zx_pp_wait_ready(struct zx_pp_engine *e)
{
	unsigned int i;

	for (i = 0; i < ZX_PP_POLL_READS; i++) {
		if (i)
			udelay(ZX_PP_POLL_DELAY_US);
		if (readl(e->base + ZX_PP_IND_STATUS) & ZX_PP_IND_READY)
			return 0;
	}
	e->timeouts++;
	e->faulted = true;
	return -ETIMEDOUT;
}

static unsigned int zx_pp_data_reg(const struct zx_pp_engine *e, unsigned int i)
{
	if (e->split_data && i >= ZX_PP_PM_DATA_LO_WORDS)
		return ZX_PP_PM_DATA_HI + 4 * (i - ZX_PP_PM_DATA_LO_WORDS);
	return ZX_PP_IND_DATA + 4 * i;
}

static u32 zx_pp_cmd(unsigned int op, unsigned int sel, u32 addr)
{
	return addr | (sel << ZX_PP_CMD_SEL_SHIFT) | (op << ZX_PP_CMD_OP_SHIFT);
}

static int zx_pp_check(const struct zx_pp_engine *e, unsigned int sel, u32 addr,
		       const void *data, unsigned int words)
{
	if (sel > e->sel_max || addr >= e->addr_limit || !data ||
	    !words || words > e->max_words)
		return -EINVAL;
	return 0;
}

/* Caller holds e->lock. Pre-poll, then the CMD write. */
static int zx_pp_begin(struct zx_pp_engine *e, unsigned int op,
		       unsigned int sel, u32 addr)
{
	int ret;

	if (!e->enabled)
		return -ENODEV;
	if (e->faulted)
		return -EIO;
	ret = zx_pp_wait_ready(e);
	if (ret)
		return ret;
	zx_pp_rmw(e->base + ZX_PP_IND_CMD, e->cmd_mask, zx_pp_cmd(op, sel, addr));
	return 0;
}

/* cla_get_cpu_queue_id (0x6abc), pp_pm_get_diag_ram_info (0x1fe08): pre-poll,
 * read CMD, DATA from the highest word down. The vendor's post-CMD poll is
 * dead code (it tests the stale pre-poll status); this driver polls again,
 * which can only wait longer.
 */
static int zx_pp_ind_read(struct zx_pp_engine *e, unsigned int sel, u32 addr,
			  u32 *data, unsigned int words)
{
	unsigned int i;
	int ret;

	ret = zx_pp_check(e, sel, addr, data, words);
	if (ret)
		return ret;
	mutex_lock(&e->lock);
	ret = zx_pp_begin(e, ZX_PP_OP_READ, sel, addr);
	if (!ret)
		ret = zx_pp_wait_ready(e);
	if (!ret) {
		for (i = words; i-- > 0; )
			data[i] = readl(e->base + zx_pp_data_reg(e, i));
		e->reads++;
	}
	mutex_unlock(&e->lock);
	return ret;
}

/* cla_set_hash_table (0x5a14), pp_pm_set_flow_info (0x1cef8): pre-poll, write
 * CMD, DATA from the highest word down so the last access is DATA[0] at +0x1c.
 * No completion poll: like the vendor, the next operation's pre-poll observes
 * completion.
 */
static int zx_pp_ind_write(struct zx_pp_engine *e, unsigned int sel, u32 addr,
			   const u32 *data, unsigned int words)
{
	unsigned int i;
	int ret;

	ret = zx_pp_check(e, sel, addr, data, words);
	if (ret)
		return ret;
	mutex_lock(&e->lock);
	ret = zx_pp_begin(e, ZX_PP_OP_WRITE, sel, addr);
	if (!ret) {
		for (i = words; i-- > 0; )
			zx_pp_rmw(e->base + zx_pp_data_reg(e, i), ZX_PP_DATA_MASK, data[i]);
		e->writes++;
	}
	mutex_unlock(&e->lock);
	return ret;
}

int zx_pp_cla_read(struct zx_pp *pp, unsigned int sel, u32 addr,
		   u32 *data, unsigned int words)
{
	return pp ? zx_pp_ind_read(&pp->cla, sel, addr, data, words) : -ENODEV;
}

int zx_pp_cla_write(struct zx_pp *pp, unsigned int sel, u32 addr,
		    const u32 *data, unsigned int words)
{
	return pp ? zx_pp_ind_write(&pp->cla, sel, addr, data, words) : -ENODEV;
}

int zx_pp_pm_read(struct zx_pp *pp, unsigned int sel, u32 addr,
		  u32 *data, unsigned int words)
{
	return pp ? zx_pp_ind_read(&pp->pm, sel, addr, data, words) : -ENODEV;
}

int zx_pp_pm_write(struct zx_pp *pp, unsigned int sel, u32 addr,
		   const u32 *data, unsigned int words)
{
	return pp ? zx_pp_ind_write(&pp->pm, sel, addr, data, words) : -ENODEV;
}

/* The aging table is one word per exact-match hash address, so the bound is
 * the table depth rather than the engine's 0x400000 address limit. Checking
 * it here keeps a caller that miscalculates a bucket from reading a different
 * table's word and reporting it as a hit.
 */
int zx_pp_aging_read(struct zx_pp *pp, u32 addr, u32 *val)
{
	if (!pp)
		return -ENODEV;
	if (!val || addr >= ZX_PP_CLA_AGING_DEPTH)
		return -EINVAL;
	return zx_pp_ind_read(&pp->cla, ZX_PP_CLA_SEL_AGING, addr, val, 1);
}

int zx_pp_aging_write(struct zx_pp *pp, u32 addr, u32 val)
{
	if (!pp)
		return -ENODEV;
	if (addr >= ZX_PP_CLA_AGING_DEPTH)
		return -EINVAL;
	return zx_pp_ind_write(&pp->cla, ZX_PP_CLA_SEL_AGING, addr, &val, 1);
}

/* Read, never assume (docs/PP-FLOW.md "CLA exact-match hash"). The registers
 * are plain reads of the already-mapped CLA window: no indirect operation, no
 * write, so this is safe at any point after the Ethernet bring-up.
 */
static void zx_pp_read_hash_config(struct zx_pp *pp)
{
	u32 poly, space;
	unsigned int i;

	poly = readl(pp->cla.base + ZX_PP_CLA_HASH_POLY_REG);
	space = readl(pp->cla.base + ZX_PP_CLA_HASH_OUTER_REG);

	for (i = 0; i < 4; i++) {
		pp->hash.inner[i] = (poly >> (2 * i)) & 0x3;
		pp->hash.outer[i] = (poly >> (16 + 2 * i)) & 0x3;
	}
	pp->hash.outer_num = (space >> 2) & 0x3;
	pp->hash.outer_space = space & 0x3;
	/* outer_space_sel is the only field that says whether an outer table is
	 * in use; the vendor leaves the whole register at 0.
	 */
	pp->hash.usable = (space == 0);
}

int zx_pp_hash_config(struct zx_pp *pp, struct zx_pp_hash_cfg *cfg)
{
	if (!pp)
		return -ENODEV;
	if (!cfg)
		return -EINVAL;
	mutex_lock(&pp->cla.lock);
	*cfg = pp->hash;
	mutex_unlock(&pp->cla.lock);
	return 0;
}

/* Snapshot the CLA upstream per-action packet counters (fwd/trap/drop/copy).
 * These are plain MMIO reads on the already-mapped CLA block, not an indirect
 * operation, so they take no engine lock and cannot stall. fwd > 0 means the
 * exact-match hit; trap tracks classified-but-unmatched frames 1:1 with
 * ingress (measured 2026-11-16, docs/PP-KEY.md §10).
 */
int zx_pp_cla_counters(struct zx_pp *pp, u32 *fwd, u32 *trap, u32 *drop,
		       u32 *copy)
{
	if (!pp)
		return -ENODEV;
	if (fwd)
		*fwd = readl(pp->cla.base + ZX_PP_CLA_CNT_FWD);
	if (trap)
		*trap = readl(pp->cla.base + ZX_PP_CLA_CNT_TRAP);
	if (drop)
		*drop = readl(pp->cla.base + ZX_PP_CLA_CNT_DROP);
	if (copy)
		*copy = readl(pp->cla.base + ZX_PP_CLA_CNT_COPY);
	return 0;
}

/* Snapshot the CLA DOWNSTREAM per-action packet counters. Same MMIO-read
 * contract as zx_pp_cla_counters; this is the bank a WAN->LAN routed frame's
 * action lands in (PP-KEY §21). A forward of the downstream test flow shows as
 * dn fwd (0x9238c3cc) incrementing, so this is the pass criterion read.
 */
int zx_pp_cla_counters_dn(struct zx_pp *pp, u32 *fwd, u32 *trap, u32 *drop,
			  u32 *copy)
{
	if (!pp)
		return -ENODEV;
	if (fwd)
		*fwd = readl(pp->cla.base + ZX_PP_CLA_CNT_DN_FWD);
	if (trap)
		*trap = readl(pp->cla.base + ZX_PP_CLA_CNT_DN_TRAP);
	if (drop)
		*drop = readl(pp->cla.base + ZX_PP_CLA_CNT_DN_DROP);
	if (copy)
		*copy = readl(pp->cla.base + ZX_PP_CLA_CNT_DN_COPY);
	return 0;
}

static ssize_t zx_pp_table_read(struct file *file, char __user *buf,
				size_t count, loff_t *ppos)
{
	const struct zx_pp_dbg_file *f = file->private_data;
	const struct zx_pp_table *t = f->table;
	unsigned int esize = t->words * sizeof(u32);
	unsigned int end = t->depth * esize;
	u32 words[ZX_PP_MAX_WORDS];
	__le32 out[ZX_PP_MAX_WORDS];
	unsigned int index, n, i, w;
	size_t done = 0;
	int ret = 0;

	if (*ppos < 0)
		return -EINVAL;
	if (*ppos >= end)
		return 0;
	if ((unsigned int)*ppos % esize || count < esize)
		return -EINVAL;
	index = (unsigned int)*ppos / esize;
	n = min_t(size_t, count / esize, ZX_PP_DEBUGFS_MAX_ENTRIES);
	n = min_t(unsigned int, n, t->depth - index);

	for (i = 0; i < n; i++) {
		if (t->pm)
			ret = zx_pp_pm_read(f->pp, t->sel, index + i, words, t->words);
		else
			ret = zx_pp_cla_read(f->pp, t->sel, index + i, words, t->words);
		if (ret)
			break;
		for (w = 0; w < t->words; w++)
			out[w] = cpu_to_le32(words[w]);
		if (copy_to_user(buf + done, out, esize)) {
			ret = -EFAULT;
			break;
		}
		done += esize;
	}
	if (!done)
		return ret;
	*ppos += done;
	return done;
}

static const struct file_operations zx_pp_table_fops = {
	.owner = THIS_MODULE,
	.open = simple_open,
	.read = zx_pp_table_read,
	.llseek = default_llseek,
};

static void zx_pp_show_table(struct seq_file *s, struct zx_pp *pp,
			     const struct zx_pp_dma_table *t)
{
	seq_printf(s, "%s_base dma=%pad size=%#zx prior=%#010x programmed=%#010x now=%#010x\n",
		   t->name, &t->dma, t->size, t->prior, t->readback,
		   readl(pp->ponpp + t->reg));
}

static void zx_pp_show_engine(struct seq_file *s, struct zx_pp_engine *e)
{
	u32 status;

	mutex_lock(&e->lock);
	status = readl(e->base + ZX_PP_IND_STATUS);
	seq_printf(s, "%s status=%#010x enabled=%d faulted=%d reads=%lu writes=%lu timeouts=%lu\n",
		   e->name, status, e->enabled, e->faulted, e->reads, e->writes,
		   e->timeouts);
	mutex_unlock(&e->lock);
}

static int zx_pp_status_show(struct seq_file *s, void *unused)
{
	struct zx_pp *pp = s->private;

	zx_pp_show_table(s, pp, &pp->pm_tbl);
	zx_pp_show_table(s, pp, &pp->acl_tbl);
	zx_pp_show_engine(s, &pp->cla);
	zx_pp_show_engine(s, &pp->pm);
	seq_printf(s, "cla_hash inner=%u,%u,%u,%u outer=%u,%u,%u,%u num=%u space=%u usable=%d\n",
		   pp->hash.inner[0], pp->hash.inner[1], pp->hash.inner[2],
		   pp->hash.inner[3], pp->hash.outer[0], pp->hash.outer[1],
		   pp->hash.outer[2], pp->hash.outer[3], pp->hash.outer_num,
		   pp->hash.outer_space, pp->hash.usable);
	return 0;
}
DEFINE_SHOW_ATTRIBUTE(zx_pp_status);

/* Root-readable only. No file has a write method. */
static void zx_pp_debugfs_init(struct zx_pp *pp)
{
	unsigned int i;

	pp->debugfs = debugfs_create_dir("zx279128-pp", NULL);
	debugfs_create_file("status", 0400, pp->debugfs, pp, &zx_pp_status_fops);
	for (i = 0; i < ARRAY_SIZE(zx_pp_tables); i++) {
		const struct zx_pp_table *t = &zx_pp_tables[i];

		pp->files[i].pp = pp;
		pp->files[i].table = t;
		debugfs_create_file_size(t->name, 0400, pp->debugfs, &pp->files[i],
					 &zx_pp_table_fops,
					 (loff_t)t->depth * t->words * sizeof(u32));
	}
}

static int zx_pp_alloc_table(struct zx_pp *pp, struct zx_pp_dma_table *t)
{
	t->cpu = dma_alloc_coherent(pp->dev, t->size, &t->dma, GFP_KERNEL);
	if (!t->cpu) {
		dev_err(pp->dev, "pp: cannot allocate the %#zx-byte %s table\n",
			t->size, t->name);
		return -ENOMEM;
	}
	if (!IS_ALIGNED(t->dma, ZX_PP_TABLE_ALIGN) ||
	    upper_32_bits(t->dma + t->size - 1)) {
		dev_err(pp->dev, "pp: %s table at %pad is not a usable base\n",
			t->name, &t->dma);
		return -ERANGE;
	}
	return 0;
}

/* Never return memory the engine may still reach: if the base register
 * still points into the table, keep (leak) it. The same applies when a flow
 * install could not be cleared at teardown: the CLA entry may still be live,
 * and it references PM entries inside these tables.
 */
static void zx_pp_free_table(struct zx_pp *pp, struct zx_pp_dma_table *t)
{
	u32 now;

	if (!t->cpu)
		return;
	if (pp->live_flow) {
		dev_err(pp->dev,
			"pp: %s table kept: a flow could not be cleared at teardown\n",
			t->name);
		t->cpu = NULL;
		return;
	}
	now = readl(pp->ponpp + t->reg);
	if (now >= t->dma && now - t->dma < t->size) {
		dev_err(pp->dev, "pp: %s base still %#010x after clear; leaking its table\n",
			t->name, now);
		t->cpu = NULL;
		return;
	}
	dma_free_coherent(pp->dev, t->size, t->cpu, t->dma);
	t->cpu = NULL;
}

/* Clear both bases (reverse of programming order), then free. */
static void zx_pp_free_tables(struct zx_pp *pp)
{
	if (pp->programmed) {
		zx_pp_rmw(pp->ponpp + ZX_PP_ACL_BASE_REG, ZX_PP_BASE_MASK, 0);
		zx_pp_rmw(pp->ponpp + ZX_PP_PM_BASE_REG, ZX_PP_BASE_MASK, 0);
		pp->programmed = false;
	}
	zx_pp_free_table(pp, &pp->acl_tbl);
	zx_pp_free_table(pp, &pp->pm_tbl);
}

static void zx_pp_disable(struct zx_pp_engine *e)
{
	mutex_lock(&e->lock);
	e->enabled = false;
	mutex_unlock(&e->lock);
}

/* devres action. Order: no new debugfs reader, no indirect operation in
 * flight or possible, bases cleared, tables freed.
 */
static void zx_pp_teardown(void *data)
{
	struct zx_pp *pp = data;

	debugfs_remove_recursive(pp->debugfs);
	pp->debugfs = NULL;
#ifdef CONFIG_ZX279128_PP_FLOW_TEST
	/* debugfs is gone (no writer can race); the engines are still enabled,
	 * so the installed flow can be cleared before they are disabled and the
	 * tables freed. A clear that fails leaves an entry the engine may still
	 * walk, so the tables are then kept rather than handed back.
	 */
	if (zx_pp_flow_fini())
		pp->live_flow = true;
#endif
#ifdef CONFIG_ZX279128_PP_OFFLOAD
	/* Same contract as the flow test: debugfs is gone and the engines are
	 * still enabled, so every offloaded entry can be flushed before the
	 * tables are freed. A clear that fails keeps an entry the engine may
	 * still walk, so the tables are then kept rather than handed back.
	 */
	if (zx_pp_offload_fini(pp))
		pp->live_flow = true;
#endif
	zx_pp_disable(&pp->cla);
	zx_pp_disable(&pp->pm);
	zx_pp_free_tables(pp);
}

static void zx_pp_engine_setup(struct zx_pp_engine *e, const char *name,
			       u32 cmd_mask, u32 addr_limit,
			       unsigned int sel_max, unsigned int max_words,
			       bool split_data)
{
	e->name = name;
	mutex_init(&e->lock);
	e->cmd_mask = cmd_mask;
	e->addr_limit = addr_limit;
	e->sel_max = sel_max;
	e->max_words = max_words;
	e->split_data = split_data;
}

struct zx_pp *zx_pp_tables_init(struct device *dev)
{
	struct zx_pp *pp;
	int ret;

	pp = devm_kzalloc(dev, sizeof(*pp), GFP_KERNEL);
	if (!pp)
		return NULL;
	pp->dev = dev;
	pp->cla.base = devm_ioremap(dev, ZX_PP_CLA_PHYS, SZ_4K);
	pp->pm.base = devm_ioremap(dev, ZX_PP_PM_PHYS, SZ_4K);
	pp->ponpp = devm_ioremap(dev, ZX_PP_PONPP_PHYS, SZ_4K);
	if (!pp->cla.base || !pp->pm.base || !pp->ponpp) {
		dev_err(dev, "pp: cannot map the CLA/PM/PonPp windows\n");
		return NULL;
	}
	zx_pp_engine_setup(&pp->cla, "cla", ZX_PP_CLA_CMD_MASK, ZX_PP_CLA_ADDR_LIMIT,
			   ZX_PP_CLA_SEL_MAX, ZX_PP_CLA_WORDS, false);
	zx_pp_engine_setup(&pp->pm, "pm", ZX_PP_PM_CMD_MASK, ZX_PP_PM_ADDR_LIMIT,
			   ZX_PP_PM_SEL_MAX, ZX_PP_PM_WORDS, true);
	pp->pm_tbl.name = "pm";
	pp->pm_tbl.size = ZX_PP_PM_TABLE_SIZE;
	pp->pm_tbl.reg = ZX_PP_PM_BASE_REG;
	pp->acl_tbl.name = "acl";
	pp->acl_tbl.size = ZX_PP_ACL_TABLE_SIZE;
	pp->acl_tbl.reg = ZX_PP_ACL_BASE_REG;

	/* Gate 1, reads only: both engines idle, as measured on this image. */
	if (zx_pp_wait_ready(&pp->cla) || zx_pp_wait_ready(&pp->pm)) {
		dev_warn(dev, "pp: CLA/PM not ready; table access disabled\n");
		return NULL;
	}

	/* Gate 2: both tables, at the vendor's sizes, addressable by the
	 * 32-bit base registers.
	 */
	ret = dma_set_coherent_mask(dev, DMA_BIT_MASK(32));
	if (ret) {
		dev_err(dev, "pp: no 32-bit coherent DMA: %d\n", ret);
		return NULL;
	}
	ret = zx_pp_alloc_table(pp, &pp->pm_tbl);
	if (!ret)
		ret = zx_pp_alloc_table(pp, &pp->acl_tbl);
	if (ret)
		goto fail;

	/* Gate 3: program PM then ACL (tm_pon_pp_reg_initial order), read both
	 * back. Indirect operations are refused until both match.
	 */
	pp->programmed = true;
	pp->pm_tbl.prior = zx_pp_rmw(pp->ponpp + ZX_PP_PM_BASE_REG, ZX_PP_BASE_MASK,
				     lower_32_bits(pp->pm_tbl.dma));
	pp->acl_tbl.prior = zx_pp_rmw(pp->ponpp + ZX_PP_ACL_BASE_REG, ZX_PP_BASE_MASK,
				      lower_32_bits(pp->acl_tbl.dma));
	pp->pm_tbl.readback = readl(pp->ponpp + ZX_PP_PM_BASE_REG);
	pp->acl_tbl.readback = readl(pp->ponpp + ZX_PP_ACL_BASE_REG);
	if (pp->pm_tbl.readback != lower_32_bits(pp->pm_tbl.dma) ||
	    pp->acl_tbl.readback != lower_32_bits(pp->acl_tbl.dma)) {
		dev_err(dev, "pp: table bases did not stick (pm %#010x acl %#010x); disabled\n",
			pp->pm_tbl.readback, pp->acl_tbl.readback);
		goto fail;
	}
	pp->cla.enabled = true;
	pp->pm.enabled = true;

	/* The hash selectors are read once, here, while the CLA window is known
	 * live (Gate 1 above already read its STATUS). Everything that places a
	 * hash entry uses these values instead of assuming the reset ones.
	 */
	zx_pp_read_hash_config(pp);

	ret = devm_add_action_or_reset(dev, zx_pp_teardown, pp);
	if (ret)
		return NULL;
	zx_pp_debugfs_init(pp);
	dev_info(dev, "pp: tables live, pm %pad acl %pad (were %#010x %#010x)\n",
		 &pp->pm_tbl.dma, &pp->acl_tbl.dma, pp->pm_tbl.prior,
		 pp->acl_tbl.prior);
	dev_info(dev, "pp: cla hash poly way0..3=%u,%u,%u,%u outer=%u,%u,%u,%u num=%u space=%u%s\n",
		 pp->hash.inner[0], pp->hash.inner[1], pp->hash.inner[2],
		 pp->hash.inner[3], pp->hash.outer[0], pp->hash.outer[1],
		 pp->hash.outer[2], pp->hash.outer[3], pp->hash.outer_num,
		 pp->hash.outer_space,
		 pp->hash.usable ? "" : " (outer table configured; placement disabled)");
#ifdef CONFIG_ZX279128_PP_FLOW_TEST
	zx_pp_flow_init(pp, dev, pp->debugfs);
#endif
#ifdef CONFIG_ZX279128_PP_OFFLOAD
	/* After debugfs is up and the hash config is read. Installs the one-time
	 * ternary default rule and registers the neighbour notifier; the
	 * proposed Ethernet hookup is retained in docs/offload/eth-hookup.patch;
	 * it is not installed by the current Ethernet driver.
	 */
	zx_pp_offload_init(pp, dev);
#endif
	return pp;

fail:
	zx_pp_free_tables(pp);
	return NULL;
}

void zx_pp_tables_remove(struct zx_pp *pp)
{
	if (pp)
		devm_release_action(pp->dev, zx_pp_teardown, pp);
}
