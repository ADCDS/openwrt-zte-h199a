"""Execute the ZX279128S single-flow install write path against a model.

zx279128-pp-flow.c is compiled whole (only its #include lines removed) with
boundary stubs for the exported PP table accessors, debugfs, the module
parameter, mutexes, and the IPv4/MAC string parsers. A recorder captures every
zx_pp_{cla,pm}_{read,write} call so the tests can assert the exact table write
sequence the spec (docs/PP-FLOW.md) defines, the gating, the refusals, and that
teardown deletes the installed flow before the tables are freed.

These tests prove software order and policy, not silicon behaviour.
"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_tx_origin_r204 import function, tokens

ROOT = Path(__file__).resolve().parents[1]
ZTE = ROOT / 'files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte'
FLOW_SOURCE = ZTE / 'zx279128-pp-flow.c'
HASH_SOURCE = ZTE / 'zx279128-pp-hash.c'
PP_SOURCE = ZTE / 'zx279128-pp.c'
PP_HEADER = ZTE / 'zx279128-pp.h'
KCONFIG = ZTE / 'Kconfig'
MAKEFILE = ZTE / 'Makefile'
CONFIG = ROOT / 'files/target/linux/armsr/config-6.6'
CHECK = ROOT / 'ci/check.sh'
BUILD = ROOT / 'build.sh'
SYMBOL = 'CONFIG_ZX279128_PP_FLOW_TEST'

PRELUDE = r'''
#define _DEFAULT_SOURCE
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#include <assert.h>
#include <ctype.h>
#include <errno.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint16_t __be16;
typedef uint32_t __be32;
#include <sys/types.h>		/* loff_t, ssize_t */
typedef unsigned short umode_t;
#define __user
#define __iomem
#define ETH_ALEN 6
#define IPPROTO_TCP 6
#define IPPROTO_UDP 17
#define GFP_KERNEL 0x10u
#define THIS_MODULE ((struct module *)0)
#define htons(x) ((u16)__builtin_bswap16((u16)(x)))
#define ntohs(x) ((u16)__builtin_bswap16((u16)(x)))
#define module_param(name, type, perm)
#define MODULE_PARM_DESC(name, desc)

struct module;
struct device { int unused; };
struct dentry { int unused; };
struct zx_pp;		/* opaque */
struct inode { void *i_private; };
struct file { void *private_data; };
struct file_operations {
	struct module *owner;
	int (*open)(struct inode *, struct file *);
	ssize_t (*write)(struct file *, const char __user *, size_t, loff_t *);
	loff_t (*llseek)(struct file *, loff_t, int);
};
struct mutex { int init; int held; };
static void mutex_init(struct mutex *m) { m->init = 1; m->held = 0; }
static void mutex_lock(struct mutex *m) { assert(m->init && !m->held); m->held = 1; }
static void mutex_unlock(struct mutex *m) { assert(m->init && m->held); m->held = 0; }

/* ---- recorder for the table write/read sequence ---- */
struct op { char eng; char rw; unsigned sel; u32 addr; unsigned words; u32 data[17]; };
#define NOPS 64
static struct op ops[NOPS];
static unsigned nops;
static int fail_at;		/* 1-based op index to fail, 0 = none */
static u32 read_val;		/* value every read returns in data[0] */
static void record(char eng, char rw, unsigned sel, u32 addr, const u32 *data, unsigned words)
{
	assert(nops < NOPS);
	struct op *o = &ops[nops];
	o->eng = eng; o->rw = rw; o->sel = sel; o->addr = addr; o->words = words;
	memset(o->data, 0, sizeof(o->data));
	if (data) for (unsigned i = 0; i < words && i < 17; i++) o->data[i] = data[i];
	nops++;
}
static int maybe_fail(void) { return (fail_at && (int)nops == fail_at) ? -EIO : 0; }

int zx_pp_cla_write(struct zx_pp *pp, unsigned sel, u32 addr, const u32 *data, unsigned words)
{ (void)pp; int e = maybe_fail(); record('C', 'W', sel, addr, data, words); return e; }
int zx_pp_pm_write(struct zx_pp *pp, unsigned sel, u32 addr, const u32 *data, unsigned words)
{ (void)pp; int e = maybe_fail(); record('P', 'W', sel, addr, data, words); return e; }
int zx_pp_cla_read(struct zx_pp *pp, unsigned sel, u32 addr, u32 *data, unsigned words)
{ (void)pp; int e = maybe_fail(); if (!e && data) { data[0] = read_val; } record('C', 'R', sel, addr, data, words); return e; }
int zx_pp_pm_read(struct zx_pp *pp, unsigned sel, u32 addr, u32 *data, unsigned words)
{ (void)pp; int e = maybe_fail(); if (!e && data) data[0] = read_val; record('P', 'R', sel, addr, data, words); return e; }

/* The aging table has its own accessors (they own the depth bound); the model
 * records them as the CLA sel-8 operations they are, so every op assertion in
 * this file still describes the wire traffic.
 */
int zx_pp_aging_read(struct zx_pp *pp, u32 addr, u32 *val)
{ (void)pp; int e = maybe_fail(); if (!e && val) *val = read_val; record('C', 'R', 8, addr, val, 1); return e; }
int zx_pp_aging_write(struct zx_pp *pp, u32 addr, u32 val)
{ (void)pp; int e = maybe_fail(); record('C', 'W', 8, addr, &val, 1); return e; }

/* The CLA per-action counters are plain MMIO reads with no sel/addr; the model
 * just hands back read_val so the "pipe" verb compiles and runs. They take no
 * engine lock, so there is no wire traffic to record.
 */
int zx_pp_cla_counters(struct zx_pp *pp, u32 *fwd, u32 *trap, u32 *drop, u32 *copy)
{
	(void)pp;
	if (fwd)
		*fwd = read_val;
	if (trap)
		*trap = read_val;
	if (drop)
		*drop = read_val;
	if (copy)
		*copy = read_val;
	return 0;
}

int zx_pp_cla_counters_dn(struct zx_pp *pp, u32 *fwd, u32 *trap, u32 *drop, u32 *copy)
{
	(void)pp;
	if (fwd)
		*fwd = read_val;
	if (trap)
		*trap = read_val;
	if (drop)
		*drop = read_val;
	if (copy)
		*copy = read_val;
	return 0;
}


/* ---- debugfs / dev_info ---- */
static const struct file_operations *reg_fops;
static void *reg_priv;
static umode_t reg_mode;
static struct dentry file_dentry;
static struct dentry *debugfs_create_file(const char *name, umode_t mode, struct dentry *parent,
					  void *data, const struct file_operations *fops)
{
	assert(!strcmp(name, "flow"));
	reg_fops = fops; reg_priv = data; reg_mode = mode;
	return &file_dentry;
}
static char last_info[512];
static char last_err[512];
static unsigned n_info, n_err;
static void dev_info(struct device *d, const char *fmt, ...)
{ va_list ap; (void)d; va_start(ap, fmt); vsnprintf(last_info, sizeof(last_info), fmt, ap); va_end(ap); n_info++; }
static void dev_err(struct device *d, const char *fmt, ...)
{ va_list ap; (void)d; va_start(ap, fmt); vsnprintf(last_err, sizeof(last_err), fmt, ap); va_end(ap); n_err++; }

/* ---- devres / memory ---- */
static void *devm_kzalloc(struct device *d, size_t n, unsigned gfp)
{ (void)d; assert(gfp == GFP_KERNEL); return calloc(1, n); }

/* ---- uaccess ---- */
static unsigned long copy_from_user(void *to, const void __user *from, unsigned long n)
{ memcpy(to, from, n); return 0; }

/* ---- string / parse helpers (host versions of the kernel API) ---- */
static loff_t noop_llseek(struct file *f, loff_t o, int w) { (void)f; (void)w; return o; }
static char *strim(char *s)
{
	char *e;
	while (*s && isspace((unsigned char)*s)) s++;
	e = s + strlen(s);
	while (e > s && isspace((unsigned char)e[-1])) *--e = '\0';
	return s;
}
/* base 0 is the kernel's "accept 0x..., 0..., decimal" form, which the rule
 * and field verbs use so a mask can be written in hex.
 */
static int kstrtou32(const char *s, unsigned base, u32 *out)
{
	char *end; unsigned long v;
	assert(base == 10 || base == 0);
	if (!*s) return -EINVAL;
	v = strtoul(s, &end, (int)base);
	if (end == s) return -EINVAL;
	if (*end == '\n') end++;
	if (*end) return -EINVAL;
	if (v > 0xffffffffUL) return -ERANGE;
	*out = (u32)v;
	return 0;
}
static int kstrtou16(const char *s, unsigned base, u16 *out)
{
	u32 v;
	int ret = kstrtou32(s, base, &v);

	if (ret) return ret;
	if (v > 0xffff) return -ERANGE;
	*out = (u16)v;
	return 0;
}
static int in4_pton(const char *src, int srclen, u8 *dst, int delim, const char **end)
{
	int i; const char *p = src;
	(void)srclen;
	for (i = 0; i < 4; i++) {
		char *e; unsigned long o = strtoul(p, &e, 10);
		if (e == p || o > 255) return 0;
		dst[i] = (u8)o;
		p = e;
		if (i < 3) { if (*p != '.') return 0; p++; }
	}
	if (end) *end = p;
	if (*p && *p != (char)delim && *p != '\0' && delim != -1) { /* ok: caller checks */ }
	return 1;
}
static bool mac_pton(const char *s, u8 *mac)
{
	int i;
	for (i = 0; i < 6; i++) {
		char *e; unsigned long b = strtoul(s, &e, 16);
		if (e != s + 2 || b > 255) return false;
		mac[i] = (u8)b;
		s = e;
		if (i < 5) { if (*s != ':') return false; s++; }
	}
	return *s == '\0';
}
'''

STUBS = r'''
/* The PP table layer (zx279128-pp.c) is not part of this model, so its hash
 * config accessor is stubbed. The values are the ones measured on hardware
 * (0x00e400e4 / 0), which is what the driver reads at probe.
 */
static int outer_usable = 1;	/* 0 models 0x9238c094 != 0 */
int zx_pp_hash_config(struct zx_pp *pp, struct zx_pp_hash_cfg *cfg)
{
	unsigned i;
	(void)pp;
	if (!cfg) return -EINVAL;
	for (i = 0; i < 4; i++) { cfg->inner[i] = (u8)i; cfg->outer[i] = (u8)i; }
	cfg->outer_num = 0;
	cfg->outer_space = outer_usable ? 0 : 1;
	cfg->usable = outer_usable != 0;
	return 0;
}
'''

CASES = r'''
static struct device dev;
static struct dentry dir;
extern int flow_test_enable;
extern void zx_pp_flow_init(struct zx_pp *pp, struct device *d, struct dentry *dir);
extern int zx_pp_flow_fini(void);
extern struct zx_pp_flow *flow_ctx_for_test(void);

static struct zx_pp *dummy_pp = (struct zx_pp *)0x1234;

static void up(void)
{
	nops = 0; fail_at = 0; read_val = 0; n_info = 0; last_info[0] = 0;
	n_err = 0; last_err[0] = 0;
	outer_usable = 1;
	reg_fops = NULL; reg_priv = NULL;
	zx_pp_flow_init(dummy_pp, &dev, &dir);
	assert(reg_fops && reg_fops->write && reg_mode == 0200);
	assert(reg_fops->owner == THIS_MODULE && reg_fops->open);
}
static int cmd(const char *s)
{
	struct file f; loff_t pos = 0; struct inode ino;
	ino.i_private = reg_priv;
	assert(reg_fops->open(&ino, &f) == 0);
	ssize_t r = reg_fops->write(&f, s, strlen(s), &pos);
	return (r < 0) ? (int)r : (int)r;
}

static const char *VALID =
	"add 2 tcp 192.0.2.1:1111 198.51.100.2:80 -> 4 192.0.2.1:1111 "
	"aa:bb:cc:dd:ee:ff 11:22:33:44:55:66\n";

static unsigned find_op(unsigned from, char eng, char rw, unsigned sel, u32 addr)
{
	for (unsigned i = from; i < nops; i++)
		if (ops[i].eng == eng && ops[i].rw == rw && ops[i].sel == sel && ops[i].addr == addr)
			return i;
	return NOPS;
}

static void t_sequence(void)
{
	flow_test_enable = 1;
	up();
	int r = cmd(VALID);
	assert(r == (int)strlen(VALID));
	/* Exactly four ops, in the spec's order. */
	assert(nops == 4);
	assert(ops[0].eng == 'P' && ops[0].rw == 'W' && ops[0].sel == 1 && ops[0].addr == 511 && ops[0].words == 3);
	assert(ops[1].eng == 'P' && ops[1].rw == 'W' && ops[1].sel == 0 && ops[1].addr == 1023 && ops[1].words == 3);
	assert(ops[2].eng == 'C' && ops[2].rw == 'W' && ops[2].sel == 6 && ops[2].addr == 7 && ops[2].words == 15);
	assert(ops[3].eng == 'C' && ops[3].rw == 'W' && ops[3].sel == 8 && ops[3].addr == 519 && ops[3].words == 1);
	assert(ops[3].data[0] == 0);	/* aging cleared */

	/* next_hop: dmac aa:bb:cc:dd:ee:ff, next-hop IP 198.51.100.2. */
	assert(ops[0].data[0] == (0xccu << 24 | 0xddu << 16 | 0xeeu << 8 | 0xffu));
	assert(ops[0].data[1] == (198u << 24 | 51u << 16 | 100u << 8 | 2u));
	assert(ops[0].data[2] == (0xbbu << 8 | 0xaau));

	/* flow_info: dmac_en|smac_en (b0=0x03), chk ens (b4=0x18), next_hop_idx=511. */
	assert(ops[1].data[0] == 0x00000003u);
	assert(ops[1].data[1] == 0x07fc0018u);	/* b4=0x18, b6=0xfc, b7=0x07 */
	assert(ops[1].data[2] == 0);

	/* window: valid_en+rule_mode (b16=0x50 -> word4), cmd_flow_id=1023
	 * (b3=0xfe -> word0, b4=0x07 with modify-free), inport 2 / outport 4
	 * (b12=0x40,b14=0x04 -> word3), proto byte at the key region.
	 */
	/* data[4] is window[16..19]: valid_en bit6 = 1, direct bit5 = 0,
	 * rule_mode bit4 = 0 (the vendor's fast path clears it; setting it
	 * describes a ternary rule), bits 3:0 = field >> 4 = 2 for ingress 2
	 * with the v4-ORIGINAL nibble -> 0x42; then window[17]=0,
	 * window[18]=0x10 (windata0 bit 4). window[19] stays 0 because `add` is
	 * the driver-defined-tuple control and writes it at window[20].
	 */
	/* window[16..19]: valid_en bit6 = 1, rule_mode bit4 = 0, bits 3:0 =
	 * field >> 4. `add` is the never-matching control and still derives its
	 * field from the ingress port, so for ingress 2 that is 0x24 -> 0x42.
	 * window[17..18] is windata0, a MATCH word: the action filler no longer
	 * writes 0x10 into it (that put a constant in the TTL position), and
	 * `add` stores its driver-defined tuple at window[20] onward.
	 */
	assert(ops[2].data[4] == 0x00000042u);
	assert((ops[2].data[0] >> 24) == 0xfeu);		/* b3 cmd_flow_id[6:0] */
	assert((ops[2].data[1] & 0xff) == 0x07u);		/* b4 cmd_flow_id[9:7] */
	assert(((ops[2].data[1] >> 8) & 0xff) == 0x40u);	/* b5 modify_en */
	assert((ops[2].data[3] & 0xff) == 0x40u);		/* b12 inport */
	assert(((ops[2].data[3] >> 16) & 0xff) == 0x04u);	/* b14 outport */
	assert((ops[2].data[5] & 0xff) == 6u);			/* b20 proto (key region) */
}

static void t_gating(void)
{
	/* param 0 refuses with -EPERM and writes nothing. */
	flow_test_enable = 0;
	up();
	assert(cmd(VALID) == -EPERM && nops == 0);

	/* second flow refused with -EBUSY, no further writes. */
	flow_test_enable = 1;
	up();
	assert(cmd(VALID) == (int)strlen(VALID) && nops == 4);
	assert(cmd(VALID) == -EBUSY && nops == 4);
}

static void t_refuse(void)
{
	flow_test_enable = 1;
	/* source-IP rewrite: nsip != sip. */
	up();
	assert(cmd("add 2 tcp 192.0.2.1:1111 198.51.100.2:80 -> 4 203.0.113.9:1111 "
		   "aa:bb:cc:dd:ee:ff 11:22:33:44:55:66\n") == -EOPNOTSUPP && nops == 0);
	/* source-port rewrite: nsport != sport. */
	up();
	assert(cmd("add 2 tcp 192.0.2.1:1111 198.51.100.2:80 -> 4 192.0.2.1:2222 "
		   "aa:bb:cc:dd:ee:ff 11:22:33:44:55:66\n") == -EOPNOTSUPP && nops == 0);
	/* proto refusal is reachable through the kernel API (parser rejects
	 * non-tcp/udp earlier). Drive validate() via the installed context.
	 */
	up();
	assert(cmd(VALID) == (int)strlen(VALID));
	{
		struct zx_pp_flow *f = flow_ctx_for_test();
		struct zx_pp_flow_spec s;
		memset(&s, 0, sizeof(s));
		s.ingress = 1; s.egress = 2; s.proto = 1;	/* ICMP */
		/* a second install is -EBUSY first; delete then try the proto. */
		assert(cmd("del 1\n") == (int)strlen("del 1\n"));
		assert(zx_pp_flow_install(f, &s, false) == -EOPNOTSUPP);
	}
	/* malformed lines: -EINVAL, nothing written. */
	up();
	assert(cmd("add 2 tcp 192.0.2.1:1111 198.51.100.2:80 4 192.0.2.1:1111 "
		   "aa:bb:cc:dd:ee:ff 11:22:33:44:55:66\n") == -EINVAL && nops == 0);
	assert(cmd("add 2 sctp 192.0.2.1:1111 198.51.100.2:80 -> 4 192.0.2.1:1111 "
		   "aa:bb:cc:dd:ee:ff 11:22:33:44:55:66\n") == -EINVAL && nops == 0);
	assert(cmd("frob\n") == -EINVAL && nops == 0);
}

static void t_parse(void)
{
	flow_test_enable = 1;
	up();
	assert(cmd(VALID) == (int)strlen(VALID));
	{
		struct zx_pp_flow *f = flow_ctx_for_test();
		assert(f->installed && f->id == 1);
		assert(f->spec.ingress == 2 && f->spec.egress == 4 && f->spec.proto == 6);
		/* 192.0.2.1 big-endian. */
		assert(f->spec.src_ip == (u32)(192u | 0u << 8 | 2u << 16 | 1u << 24));
		assert(f->spec.src_port == htons(1111) && f->spec.dst_port == htons(80));
		assert(f->spec.dst_mac[0] == 0xaa && f->spec.dst_mac[5] == 0xff);
		assert(f->spec.src_mac[0] == 0x11 && f->spec.src_mac[5] == 0x66);
	}
}

static void t_delete_before_free(void)
{
	flow_test_enable = 1;
	up();
	assert(cmd(VALID) == (int)strlen(VALID));
	nops = 0;
	zx_pp_flow_fini();	/* teardown path */
	/* clear order: CLA window 0, aging 0, flow_info 0, next_hop 0. */
	assert(nops == 4);
	assert(ops[0].eng == 'C' && ops[0].sel == 6 && ops[0].addr == 7 && ops[0].words == 15);
	for (unsigned i = 0; i < 15; i++) assert(ops[0].data[i] == 0);
	assert(ops[1].eng == 'C' && ops[1].sel == 8 && ops[1].addr == 519 && ops[1].data[0] == 0);
	assert(ops[2].eng == 'P' && ops[2].sel == 0 && ops[2].addr == 1023 && ops[2].words == 3);
	assert(ops[3].eng == 'P' && ops[3].sel == 1 && ops[3].addr == 511 && ops[3].words == 3);

	/* fini is idempotent / a no-op with nothing installed. */
	nops = 0;
	up();
	zx_pp_flow_fini();
	assert(nops == 0);

	/* del command path clears in the same order. */
	up();
	assert(cmd(VALID) == (int)strlen(VALID));
	nops = 0;
	assert(cmd("del 1\n") == (int)strlen("del 1\n"));
	assert(nops == 4 && ops[0].eng == 'C' && ops[0].sel == 6);
	assert(cmd("del 1\n") == -ENOENT);	/* already gone */
}

static void t_stat(void)
{
	flow_test_enable = 1;
	up();
	assert(cmd(VALID) == (int)strlen(VALID));
	nops = 0; read_val = 1;
	assert(cmd("stat 1\n") == (int)strlen("stat 1\n"));
	/* read aging[519], then clear it (read-to-clear). */
	assert(nops == 2);
	assert(ops[0].eng == 'C' && ops[0].rw == 'R' && ops[0].sel == 8 && ops[0].addr == 519);
	assert(ops[1].eng == 'C' && ops[1].rw == 'W' && ops[1].sel == 8 && ops[1].addr == 519 && ops[1].data[0] == 0);
	assert(strstr(last_info, "hit=1"));
	assert(cmd("stat 2\n") == -ENOENT);
}

static void t_unwind(void)
{
	/* a failure part-way through install unwinds (deletes what was written)
	 * and leaves nothing installed.
	 */
	flow_test_enable = 1;
	up();
	fail_at = 3;	/* fail the CLA window write (3rd op) */
	assert(cmd(VALID) == -EIO);
	{
		struct zx_pp_flow *f = flow_ctx_for_test();
		assert(!f->installed);
	}
	/* the clear path ran after the two successful PM writes + failed CLA. */
	assert(find_op(0, 'C', 'W', 6, 7) != NOPS);	/* clear window attempted */
	assert(find_op(0, 'P', 'W', 1, 511) != NOPS);	/* next_hop touched */
}

/* A clear that fails leaves an entry the engine may still walk. The driver
 * must keep its handle on it: dropping `installed` would make the entry
 * unreachable and let teardown free the table underneath it.
 */
static void t_delete_failure_keeps_the_flow(void)
{
	flow_test_enable = 1;
	up();
	assert(cmd(VALID) == (int)strlen(VALID));	/* op indices 0..3 */
	/* The clear's first write (the CLA window) is op index 4. */
	fail_at = 4;
	assert(cmd("del 1\n") == -EIO);
	assert(strstr(last_err, "may still be installed"));
	assert(flow_ctx_for_test()->installed);
	/* The handle survived, so the same id is still deletable. */
	fail_at = 0;
	assert(cmd("del 1\n") == (int)strlen("del 1\n"));
	assert(!flow_ctx_for_test()->installed);
	assert(cmd("del 1\n") == -ENOENT);
}

static void t_fini_reports_a_failed_clear(void)
{
	flow_test_enable = 1;
	up();
	assert(cmd(VALID) == (int)strlen(VALID));
	fail_at = 4;
	assert(zx_pp_flow_fini() == -EIO);
	assert(strstr(last_err, "must not be freed"));
	/* The context is kept: it is the only record that an entry may be live. */
	assert(flow_ctx_for_test() != NULL);
}

static void t_fini_clean_returns_zero(void)
{
	flow_test_enable = 1;
	up();
	assert(cmd(VALID) == (int)strlen(VALID));
	assert(zx_pp_flow_fini() == 0);
	assert(flow_ctx_for_test() == NULL);
}

/* The hit value is reported before the clear, so a failed clear must still
 * return the reading - and must not be swallowed, or the next stat would show
 * a stale hit and be read as fresh traffic.
 */
static void t_stat_clear_failure_is_reported(void)
{
	flow_test_enable = 1;
	up();
	assert(cmd(VALID) == (int)strlen(VALID));
	nops = 0; read_val = 1;
	fail_at = 1;		/* the aging clear is op index 1 */
	assert(cmd("stat 1\n") == -EIO);
	assert(strstr(last_info, "hit=1"));
	assert(strstr(last_err, "did not clear"));
}


/* ---- the hashed path: place at the bucket a live packet will hash to ---- */

static const char *HASHED =
	"addh 2 tcp 192.0.2.1:1111 198.51.100.2:80 -> 4 192.0.2.1:1111 "
	"aa:bb:cc:dd:ee:ff 11:22:33:44:55:66\n";

/* sel 2..6 map back to the global hash address, so the CLA write and the
 * aging read have to agree on the same slot. That is the invariant the whole
 * placement rests on.
 */
static unsigned global_of(unsigned sel, unsigned addr)
{
	static const unsigned base[] = { 0, 0, 0, 256, 384, 448, 512 };

	assert(sel >= 2 && sel <= 6);
	return base[sel] + addr;
}

static void t_hashed_install(void)
{
	unsigned slot;

	flow_test_enable = 1;
	up();
	assert(cmd(HASHED) == (int)strlen(HASHED));

	/* Four ops, same shape as `add`: next_hop, flow_info, CLA, aging. */
	assert(nops == 4);
	assert(ops[0].eng == 'P' && ops[0].sel == 1 && ops[0].addr == 511);
	assert(ops[1].eng == 'P' && ops[1].sel == 0 && ops[1].addr == 1023);

	/* The CLA write goes to a real bank, and the aging op targets exactly the
	 * slot that bank address encodes.
	 */
	assert(ops[2].eng == 'C' && ops[2].rw == 'W' && ops[2].words == 15);
	assert(ops[2].sel >= 2 && ops[2].sel <= 6);
	assert(ops[3].eng == 'C' && ops[3].rw == 'W' && ops[3].sel == 8);
	assert(ops[3].addr == global_of(ops[2].sel, ops[2].addr));
	assert(ops[3].data[0] == 0);
	assert(ops[3].addr < ZX_PP_CLA_AGING_DEPTH);

	/* The window's match words carry the decoded IPv4 encoding.
	 * data[n] holds window[4n..4n+3] low byte first, so:
	 *   window[19] = proto            -> data[4] byte 3
	 *   window[21] = sip[1]           -> data[5] byte 1
	 *   window[22] = sip[0]           -> data[5] byte 2
	 *   window[23] = sip[3]           -> data[5] byte 3
	 *   window[29] = sport & 0xff     -> data[7] byte 1
	 *   window[30] = sport >> 8       -> data[7] byte 2
	 * For 192.0.2.1:1111 that is sip = 192,0,2,1 and sport = 0x0457.
	 */
	/* The match words, in the positions the ternary rule's winoffset list
	 * dictates: windata0 = protocol (IP+8 masked to 0x00ff), windata1..2 =
	 * source address, windata3..4 = destination, windata5..6 = ports.
	 * window[17] is windata0's low byte, so data[4] byte 1.
	 */
	assert(((ops[2].data[4] >> 8) & 0xff) == 6);			/* proto   */
	assert(((ops[2].data[4] >> 16) & 0xff) == 0);			/* TTL slot */
	assert(((ops[2].data[4] >> 24) & 0xff) == 0);			/* sip[1]  */
	assert(((ops[2].data[5] >> 0) & 0xff) == 192);			/* sip[0]  */
	assert(((ops[2].data[5] >> 8) & 0xff) == 1);			/* sip[3]  */
	assert(((ops[2].data[5] >> 16) & 0xff) == 2);			/* sip[2]  */
	assert(((ops[2].data[6] >> 24) & 0xff) == (1111 & 0xff));	/* sport lo */
	assert(((ops[2].data[7] >> 0) & 0xff) == (1111 >> 8));		/* sport hi */

	/* The window's own copy of the port/type field, and windata0. These are
	 * what the vendor writes and this driver used to omit; an entry without
	 * them described a different rule, which is why spraying one across every
	 * slot still matched nothing.
	 *
	 * CORRECTED 2026-11-16: the field is (extIdx << 4) | nibble, and extIdx
	 * is the extra-index SLOT, not the ingress port. For the IPv4 5-tuple
	 * fast path aclGetExtIdxRuleRamAddrByPort returns a constant 9 and the
	 * nibble is 0, so the field is 0x90 for every port -- which is exactly
	 * the extra_rule index tm_acl_fast_init installs the matching ternary
	 * rule at. Hence:
	 *   window[15] bits 7:4 = 0x90 & 0xf  = 0
	 *   window[16] bits 3:0 = 0x90 >> 4   = 9
	 *   window[16] = valid_en(1) | direct(0) | rule_mode(0) | 9 = 0x49
	 *   window[17] = 0, window[18] = 0x10
	 */
	assert(((ops[2].data[3] >> 24) & 0xff) == 0x00);	/* window[15] */
	assert((ops[2].data[4] & 0xff) == 0x49);		/* window[16] */
	/* window[17..18] is windata0 = {proto, TTL-slot}, no longer a constant */
	assert(((ops[2].data[4] >> 8) & 0xff) == 6);		/* window[17] */
	assert(((ops[2].data[4] >> 16) & 0xff) == 0x00);	/* window[18] */

	/* rule_mode must stay clear: bit 4 set describes a ternary rule, and an
	 * exact-match hash entry with it set never matches. This is the single
	 * assumption that cost the most time on hardware.
	 */
	assert((((ops[2].data[4] & 0xff) >> 4) & 1) == 0);
	assert((((ops[2].data[4] & 0xff) >> 6) & 1) == 1);

	/* The hashed entry must NOT be the fixed never-matching slot. */
	assert(!(ops[2].sel == 6 && ops[2].addr == 7));

	/* stat reads the slot the install used, and del clears it. */
	slot = global_of(ops[2].sel, ops[2].addr);
	nops = 0; read_val = 1;
	assert(cmd("stat 1\n") == (int)strlen("stat 1\n"));
	assert(nops == 2);
	assert(ops[0].eng == 'C' && ops[0].rw == 'R' && ops[0].sel == 8);
	assert(ops[0].addr == slot);
	assert(ops[1].eng == 'C' && ops[1].rw == 'W' && ops[1].addr == slot);
	assert(strstr(last_info, "hit=1"));

	nops = 0;
	assert(cmd("del 1\n") == (int)strlen("del 1\n"));
	assert(nops == 4);
	assert(ops[0].eng == 'C' && ops[0].rw == 'W');
	assert(global_of(ops[0].sel, ops[0].addr) == slot);
	assert(ops[1].eng == 'C' && ops[1].rw == 'W' && ops[1].sel == 8);
	assert(ops[1].addr == slot);
	assert(cmd("del 1\n") == -ENOENT);
}

/* The scoping field is NOT the ingress port.
 *
 * This test used to assert the opposite: that the same tuple on a different
 * ingress port hashed to a different bucket. That was wrong, and it is worth
 * saying why, because it cost several hardware boots.
 * aclGetExtIdxRuleRamAddrByPort (Ghidra 0x5841c) short-circuits to a constant
 * 9 whenever g_ipv4FastEn is set, and tm_acl_fast_add_v4v6 sets that flag
 * immediately before calling it for rule type 3 (TCP/UDP). So every IPv4
 * 5-tuple fast flow, on every port, uses extIdx 9 and field 0x90. The hashed
 * bucket is therefore port-INDEPENDENT, and per-port scoping must come from
 * the ternary rule the field selects, not from the hash.
 */
static void t_hashed_field_is_port_independent(void)
{
	flow_test_enable = 1;
	up();
	assert(cmd(HASHED) == (int)strlen(HASHED));
	{
		unsigned sel_a = ops[2].sel, addr_a = ops[2].addr;

		assert(cmd("del 1\n") == (int)strlen("del 1\n"));
		up();
		/* same tuple, ingress port 3 instead of 2 */
		{
			static const char *other =
				"addh 3 tcp 192.0.2.1:1111 198.51.100.2:80 -> 4 192.0.2.1:1111 "
				"aa:bb:cc:dd:ee:ff 11:22:33:44:55:66\n";

			assert(cmd(other) == (int)strlen(other));
		}
		/* identical bucket: the key carries extIdx 9, not the port */
		assert(ops[2].sel == sel_a && ops[2].addr == addr_a);
		/* and the window's field bytes are 0x90 either way */
		assert(((ops[2].data[3] >> 24) & 0xff) == 0x00);
		assert((ops[2].data[4] & 0xff) == 0x49);
	}
}

/* The ternary rule decoded through the VENDOR's own field decoder.
 *
 * cla_set_extra_rule_table's debug strings name an extra_rule entry's fields
 * `winoffset0..19` and `winmask0..19`: the rule says which packet bytes the
 * engine extracts into windata0..19 and which bits of each it keeps. Running
 * tm_acl_fast_init's IPv4 rule back through that decoder is what pins the
 * match-word layout, and it is independent of anything this driver believes.
 *
 * Expected, and the reason each one matters:
 *   winoffset0..6 = 8,12,14,16,18,20,22 -- IPv4 header byte offsets: the
 *     {TTL,proto} halfword, the two halves of each address, then the ports.
 *   winmask0 = 0x00ff -- keeps the protocol byte and DROPS TTL, which is why
 *     a stored entry can match packets whose TTL differs.
 *   winmask1..6 = 0xffff, and offsets/masks 7..19 = 0.
 */
static void t_rule_decodes_to_the_ipv4_5tuple_offsets(void)
{
	u32 w[ZX_PP_EXTRA_RULE_WORDS];
	u8 p[ZX_PP_EXTRA_RULE_BYTES];
	unsigned i;
	static const u8 want_off[7] = { 8, 12, 14, 16, 18, 20, 22 };
	unsigned off[20];
	unsigned msk[20];

	zx_pp_build_extra_rule_v4(w, false);
	for (i = 0; i < ZX_PP_EXTRA_RULE_WORDS; i++) {
		p[4 * i + 0] = (u8)(w[i] & 0xff);
		p[4 * i + 1] = (u8)((w[i] >> 8) & 0xff);
		p[4 * i + 2] = (u8)((w[i] >> 16) & 0xff);
		p[4 * i + 3] = (u8)((w[i] >> 24) & 0xff);
	}

	/* the vendor decoder's 7-bit winoffset chain (LC190..LC194) */
	off[0] = p[0] & 0x7f;
	off[1] = ((p[1] & 0x3f) << 1) | (p[0] >> 7);
	off[2] = ((p[2] & 0x1f) << 2) | (p[1] >> 6);
	off[3] = ((p[3] & 0x0f) << 3) | (p[2] >> 5);
	off[4] = ((p[4] & 0x07) << 4) | (p[3] >> 4);
	off[5] = ((p[5] & 0x03) << 5) | (p[4] >> 3);
	off[6] = ((p[6] & 0x01) << 6) | (p[5] >> 2);
	off[7] = p[6] >> 1;
	off[8] = p[7] & 0x7f;
	for (i = 0; i < 7; i++)
		assert(off[i] == want_off[i]);
	assert(off[7] == 0 && off[8] == 0);

	/* the 16-bit winmask chain (LC195..LC199), nibble-aligned from 0x11 */
	for (i = 0; i < 20; i++) {
		unsigned lo = 0x11 + 2 * i;

		msk[i] = ((unsigned)p[lo + 1] << 4) | (p[lo] >> 4) |
			 ((unsigned)(p[lo + 2] & 0xf) << 12);
	}
	assert(msk[0] == 0x00ff);	/* protocol kept, TTL dropped */
	for (i = 1; i < 7; i++)
		assert(msk[i] == 0xffff);
	for (i = 7; i < 20; i++)
		assert(msk[i] == 0x0000);
}

/* The ternary default rule pair, which the exact-match field indexes. */
static void t_rule_init_writes_the_pair_and_enables_the_slot(void)
{
	flow_test_enable = 1;
	up();
	assert(cmd("rule init\n") == (int)strlen("rule init\n"));
	/* two extra_rule writes (sel 1) at 0x90/0x91, then a read and a write
	 * of extra_index[9] (sel 0).
	 */
	assert(nops == 4);
	assert(ops[0].eng == 'C' && ops[0].rw == 'W' && ops[0].sel == 1 &&
	       ops[0].addr == 0x90);
	assert(ops[1].eng == 'C' && ops[1].rw == 'W' && ops[1].sel == 1 &&
	       ops[1].addr == 0x91);
	assert(ops[2].eng == 'C' && ops[2].rw == 'R' && ops[2].sel == 0 &&
	       ops[2].addr == 9);
	assert(ops[3].eng == 'C' && ops[3].rw == 'W' && ops[3].sel == 0 &&
	       ops[3].addr == 9);
	/* tm_acl_fast_init's enable is bit 0 of word 4, not EN_V4FAST's 5:4 */
	assert((ops[3].data[4] & 0x1u) == 0x1u);
	/* the pair differs only in bit 9 of the halfword at byte 0x3a */
	assert(ops[0].data[14] == 0x00700000u);
	assert(ops[1].data[14] == 0x02700000u);
	/* and the rule is not all-zero, which is what the table held before */
	assert(ops[0].data[0] == 0x22038608u);

	/* gated like every other write */
	flow_test_enable = 0;
	up();
	assert(cmd("rule init\n") == -EPERM && nops == 0);
	flow_test_enable = 1;
}

/* A configured outer table means mode 1, which is undecoded: the hashed path
 * must refuse rather than install at a guessed bucket.
 */
static void t_hashed_refuses_a_configured_outer_table(void)
{
	flow_test_enable = 1;
	up();
	outer_usable = 0;
	assert(cmd(HASHED) == -EOPNOTSUPP);
	/* Nothing was written: the refusal happens before the first table op,
	 * which is the invariant that matters. (The model keeps only the last
	 * dev_info, and install logs its own failure line over the reason.)
	 */
	assert(nops == 0);
	outer_usable = 1;
}

/* `add` still parks at the fixed slot, so the never-matching control the
 * first hardware write test needed is unchanged.
 */
static void t_add_still_uses_the_fixed_slot(void)
{
	flow_test_enable = 1;
	up();
	assert(cmd(VALID) == (int)strlen(VALID));
	assert(ops[2].sel == 6 && ops[2].addr == 7);
	assert(ops[3].addr == 519);
}

/* The "pipe" verb reads the CLA fwd/trap/drop/copy counters and logs them.
 * It is a plain MMIO read in the model (no indirect op), so it records no
 * table traffic; the contract is only that it is gated and prints the line.
 */
static void t_pipe_reads_the_cla_counters(void)
{
	flow_test_enable = 1;
	up();
	nops = 0; read_val = 0x2a;
	assert(cmd("pipe\n") == (int)strlen("pipe\n"));
	assert(nops == 0);	/* counters are MMIO, not an indirect operation */
	/* pipe now prints BOTH banks (PP-KEY §21); last_info holds the final
	 * line, which is the downstream bank. The dn fwd (0x9238c3cc) is the
	 * pass criterion for the WAN->LAN test flow.
	 */
	assert(strstr(last_info, "cla dn:"));
	assert(strstr(last_info, "fwd=42"));
	assert(strstr(last_info, "trap=42"));
}

/* "rulew <idx> <word> <value>" reads the 17-word extra_rule entry, replaces one
 * word, and writes it back. The decisive key-encoding lever; gated.
 */
static void t_rulew_pokes_one_rule_word(void)
{
	flow_test_enable = 1;
	up();
	nops = 0; read_val = 0;
	assert(cmd("rulew 144 11 0\n") == (int)strlen("rulew 144 11 0\n"));
	/* read the whole entry (sel 1, idx 144), then write it back. */
	assert(nops == 2);
	assert(ops[0].eng == 'C' && ops[0].rw == 'R' && ops[0].sel == 1 &&
	       ops[0].addr == 144 && ops[0].words == 17);
	assert(ops[1].eng == 'C' && ops[1].rw == 'W' && ops[1].sel == 1 &&
	       ops[1].addr == 144 && ops[1].words == 17);
	/* gated like every other write */
	flow_test_enable = 0;
	up();
	assert(cmd("rulew 144 11 0\n") == -EPERM && nops == 0);
	flow_test_enable = 1;
}

/* "winw <sel> <addr> <word> <value>" is the window analogue of rulew. */
static void t_winw_pokes_one_window_word(void)
{
	flow_test_enable = 1;
	up();
	nops = 0; read_val = 0;
	assert(cmd("winw 2 244 0 0x11\n") == (int)strlen("winw 2 244 0 0x11\n"));
	assert(nops == 2);
	assert(ops[0].eng == 'C' && ops[0].rw == 'R' && ops[0].sel == 2 &&
	       ops[0].addr == 244 && ops[0].words == 15);
	assert(ops[1].eng == 'C' && ops[1].rw == 'W' && ops[1].sel == 2 &&
	       ops[1].addr == 244 && ops[1].words == 15);
	flow_test_enable = 0;
	up();
	assert(cmd("winw 2 244 0 0x11\n") == -EPERM && nops == 0);
	flow_test_enable = 1;
}

int main(int argc, char **argv)
{
	static const struct { const char *name; void (*fn)(void); } cases[] = {
		{ "sequence", t_sequence },
		{ "gating", t_gating },
		{ "refuse", t_refuse },
		{ "parse", t_parse },
		{ "delete_before_free", t_delete_before_free },
		{ "stat", t_stat },
		{ "unwind", t_unwind },
		{ "delete_failure", t_delete_failure_keeps_the_flow },
		{ "fini_failure", t_fini_reports_a_failed_clear },
		{ "fini_clean", t_fini_clean_returns_zero },
		{ "stat_clear_failure", t_stat_clear_failure_is_reported },
		{ "hashed_install", t_hashed_install },
		{ "hashed_port_scope", t_hashed_field_is_port_independent },
		{ "rule_init", t_rule_init_writes_the_pair_and_enables_the_slot },
		{ "rule_offsets", t_rule_decodes_to_the_ipv4_5tuple_offsets },
		{ "hashed_outer_refused", t_hashed_refuses_a_configured_outer_table },
		{ "add_fixed_slot", t_add_still_uses_the_fixed_slot },
		{ "pipe", t_pipe_reads_the_cla_counters },
		{ "rulew", t_rulew_pokes_one_rule_word },
		{ "winw", t_winw_pokes_one_window_word },
	};
	assert(argc == 2);
	for (unsigned i = 0; i < sizeof(cases)/sizeof(cases[0]); i++)
		if (!strcmp(argv[1], cases[i].name)) {
			cases[i].fn();
			printf("PASS %s\n", cases[i].name);
			return 0;
		}
	return 2;
}
'''

# A tiny accessor so the test can read the single flow context. Appended to the
# translation unit; it only exists in the test build.
ACCESSOR = r'''
struct zx_pp_flow *flow_ctx_for_test(void) { return g_flow; }
'''


def strip_includes(text):
    return re.sub(r'^#include[^\n]*\n', '', text, flags=re.M)


def preprocess(text, defines=()):
    run = subprocess.run(['cc', '-E', '-P', '-x', 'c', '-', *defines],
                         input=strip_includes(text), capture_output=True, text=True, check=True)
    return run.stdout


class PpFlowModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        root = Path(cls.directory.name)
        source, cls.executable = root / 'flow.c', root / 'flow'
        body = strip_includes(FLOW_SOURCE.read_text())
        # expose the static context through a test-only accessor
        body = body.replace('#endif /* CONFIG_ZX279128_PP_FLOW_TEST */',
                            ACCESSOR + '\n#endif /* CONFIG_ZX279128_PP_FLOW_TEST */', 1)
        # The key builder and the slot allocator are real code, not stubs: the
        # hashed install path is what these tests have to exercise. Only the
        # header's declarations are supplied, taken from the real header.
        header = PP_HEADER.read_text()
        names = re.findall(r'^#define\s+(ZX_PP_\w+)\s+.*$', header, re.M)
        declared = '\n'.join(
            [re.search(r'^#define\s+' + n + r'\s+.*$', header, re.M).group() for n in names]
            + [re.search(r'^struct ' + st + r' \{.*?^\};', header, re.M | re.S).group()
               for st in ('zx_pp_hash_cfg', 'zx_pp_hash_map')])
        # the stub needs struct zx_pp_hash_cfg, so it follows the header text
        stubs = STUBS
        source.write_text(PRELUDE + declared + '\n' + stubs + '\n' +
                          f'#define {SYMBOL} 1\n' +
                          strip_includes(HASH_SOURCE.read_text()) + body + CASES)
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

    def test_install_writes_the_four_tables_in_spec_order(self):
        self.run_case('sequence')

    def test_param_zero_refused_and_second_flow_refused(self):
        self.run_case('gating')

    def test_unknown_dependent_fields_are_refused(self):
        self.run_case('refuse')

    def test_command_line_parses_into_the_spec(self):
        self.run_case('parse')

    def test_teardown_deletes_the_flow_before_the_tables(self):
        self.run_case('delete_before_free')

    def test_stat_reads_and_clears_the_hit_bit(self):
        self.run_case('stat')

    def test_a_failed_install_unwinds(self):
        self.run_case('unwind')

    def test_a_failed_clear_keeps_the_handle(self):
        self.run_case('delete_failure')

    def test_teardown_reports_a_failed_clear(self):
        self.run_case('fini_failure')

    def test_teardown_returns_zero_when_clean(self):
        self.run_case('fini_clean')

    def test_stat_reports_a_failed_clear(self):
        self.run_case('stat_clear_failure')

    def test_hashed_install_places_at_the_packets_bucket(self):
        self.run_case('hashed_install')

    def test_the_hashed_key_is_port_independent(self):
        self.run_case('hashed_port_scope')

    def test_rule_init_installs_the_ternary_default_pair(self):
        self.run_case('rule_init')

    def test_rule_decodes_to_the_ipv4_five_tuple_offsets(self):
        self.run_case('rule_offsets')

    def test_hashed_install_refuses_a_configured_outer_table(self):
        self.run_case('hashed_outer_refused')

    def test_add_still_parks_at_the_fixed_slot(self):
        self.run_case('add_fixed_slot')

    def test_pipe_reads_the_cla_counters(self):
        self.run_case('pipe')

    def test_rulew_pokes_one_rule_word(self):
        self.run_case('rulew')

    def test_winw_pokes_one_window_word(self):
        self.run_case('winw')


class PpFlowSourcePolicyTests(unittest.TestCase):
    def test_control_file_is_root_only_and_write_only(self):
        text = FLOW_SOURCE.read_text()
        # debugfs mode 0200 (write-only, root-only); the fops carry a .write
        # method and no .read.
        modes = re.findall(r'debugfs_create_file\([^,]+,\s*(0\d+)', text)
        self.assertEqual(modes, ['0200'])
        fops = function(text, 'zx_pp_flow_write_cmd')  # exists
        self.assertTrue(fops)
        self.assertIn('.write = zx_pp_flow_write_cmd', text)
        self.assertNotIn('.read =', text)

    def test_module_param_default_is_zero_and_gates_writes(self):
        text = FLOW_SOURCE.read_text()
        self.assertIn('static int flow_test_enable;', text)
        self.assertIn('module_param(flow_test_enable, int, 0644)', text)
        # the install path checks it before anything else
        install = function(text, 'zx_pp_flow_install')
        self.assertIn('if (!flow_test_enable)', install)
        self.assertLess(install.index('flow_test_enable'), install.index('zx_pp_flow_write'))

    def test_one_flow_at_a_time(self):
        install = function(FLOW_SOURCE.read_text(), 'zx_pp_flow_install')
        self.assertIn('if (f->installed)', install)
        self.assertIn('-EBUSY', install)

    def test_refuses_unknown_dependent_rewrites(self):
        validate = function(FLOW_SOURCE.read_text(), 'zx_pp_flow_validate')
        self.assertIn('new_src_ip != s->src_ip', validate)
        self.assertIn('new_src_port != s->src_port', validate)
        self.assertEqual(validate.count('-EOPNOTSUPP'), 3)  # proto + ip + port

    def test_every_accepted_write_is_logged(self):
        text = FLOW_SOURCE.read_text()
        for fn in ('zx_pp_flow_install', 'zx_pp_flow_delete', 'zx_pp_flow_stat'):
            self.assertIn('dev_info', function(text, fn))

    def test_a_failed_clear_never_discards_the_only_handle(self):
        """`installed` is cleared only after the clear succeeds.

        Dropping it on failure would make a possibly-live entry unreachable
        and would let teardown free a table the engine may still walk
        (docs/PP-OFFLOAD.md, "never return memory the engine may still
        reach").
        """
        text = FLOW_SOURCE.read_text()
        delete = function(text, 'zx_pp_flow_delete')
        self.assertIn('if (ret)', delete)
        self.assertLess(delete.index('if (ret)'), delete.index('f->installed = false'))
        self.assertIn('dev_err', delete)

        fini = function(text, 'zx_pp_flow_fini')
        # the handle is dropped only when the clear was clean
        self.assertIn('if (!ret)', fini)
        self.assertLess(fini.index('if (!ret)'), fini.index('g_flow = NULL'))
        self.assertIn('must not be freed', fini)
        # and the "installed" flag is cleared only on the success path
        self.assertLess(fini.index('f->installed = false'), fini.index('if (!ret)'))

    def test_stat_does_not_swallow_a_failed_clear(self):
        stat = function(FLOW_SOURCE.read_text(), 'zx_pp_flow_stat')
        # the hit is logged before the clear is attempted, so a failure still
        # reports the reading; the clear's error is then returned.
        self.assertLess(stat.index('dev_info'), stat.index('clear_ret ='))
        self.assertIn('did not clear', stat)
        self.assertIn('ret = clear_ret', stat)


class PpFlowBuildGateTests(unittest.TestCase):
    def test_kconfig_symbol_is_bool_default_n_behind_pp_tables(self):
        block = re.search(r'^config ZX279128_PP_FLOW_TEST\n(.*?)(?=^\S)',
                          KCONFIG.read_text(), re.M | re.S)
        self.assertIsNotNone(block)
        body = block.group(1)
        self.assertIn('\tbool "', body)
        self.assertIn('\tdepends on ZX279128_PP_TABLES\n', body)
        self.assertIn('\tdefault n\n', body)
        self.assertNotIn('select', body)

    def test_no_shipped_config_enables_the_symbol(self):
        config = CONFIG.read_text().splitlines()
        self.assertEqual(config.count('# CONFIG_ZX279128_PP_FLOW_TEST is not set'), 1)
        self.assertFalse([l for l in config if l.startswith(SYMBOL + '=')])

    def test_ci_guard_blocks_the_symbol(self):
        self.assertIn("grep -q '^CONFIG_ZX279128_PP_FLOW_TEST=y'", CHECK.read_text())

    def test_build_flag_requires_pp_tables(self):
        text = BUILD.read_text()
        self.assertIn('PP_FLOW_TEST', text)
        self.assertIn('PP_FLOW_TEST=1 requires PP_TABLES=1', text)
        # the merged-config assertion exists both directions
        self.assertIn("grep -qx 'CONFIG_ZX279128_PP_FLOW_TEST=y'", text)

    def test_makefile_links_the_object_only_when_enabled(self):
        make = MAKEFILE.read_text()
        self.assertIn('zx279128_eth-$(CONFIG_ZX279128_PP_FLOW_TEST) += zx279128-pp-flow.o', make)
        # it is inside the PP_TABLES branch (flow depends on tables)
        tables_branch = make.split('ifdef CONFIG_ZX279128_PP_TABLES', 1)[1].split('else', 1)[0]
        self.assertIn('zx279128-pp-flow.o', tables_branch)

    def test_symbol_off_compiles_to_nothing(self):
        off = preprocess(FLOW_SOURCE.read_text())
        self.assertFalse(re.findall(r'zx_pp_flow_\w+', off))
        self.assertNotIn('flow_test_enable', off)
        on = preprocess(FLOW_SOURCE.read_text(), [f'-D{SYMBOL}=1'])
        self.assertIn('zx_pp_flow_init', on)

    def test_pp_c_calls_flow_hooks_in_the_right_place(self):
        pp = PP_SOURCE.read_text()
        init = function(pp, 'zx_pp_tables_init')
        teardown = function(pp, 'zx_pp_teardown')
        # init hook: after debugfs is up, guarded by the symbol
        self.assertIn('zx_pp_flow_init(pp, dev, pp->debugfs)', init)
        self.assertLess(init.index('zx_pp_debugfs_init(pp)'), init.index('zx_pp_flow_init'))
        # teardown: delete the flow after debugfs removal, before engines off
        self.assertIn('zx_pp_flow_fini()', teardown)
        self.assertLess(teardown.index('debugfs_remove_recursive'), teardown.index('zx_pp_flow_fini'))
        self.assertLess(teardown.index('zx_pp_flow_fini'), teardown.index('zx_pp_disable(&pp->cla)'))
        # every flow reference in pp.c is behind the symbol
        self.assertEqual(len(re.findall(r'^#ifdef ' + SYMBOL + r'$', pp, re.M)), 2)

    def test_header_gates_the_hooks(self):
        header = PP_HEADER.read_text()
        self.assertIn('#ifdef CONFIG_ZX279128_PP_FLOW_TEST', header)
        self.assertIn('void zx_pp_flow_init(', header)
        self.assertIn('int zx_pp_flow_fini(void)', header)


if __name__ == '__main__':
    unittest.main()
