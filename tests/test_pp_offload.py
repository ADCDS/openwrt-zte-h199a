"""Execute the ZX279128S hardware flow-offload glue against a C model.

zx279128-pp-offload.c is compiled whole (only its #include lines removed),
together with the REAL shared builders (zx279128-pp-hash.c), against a model
that supplies the kernel's flow-offload, netdevice, neighbour, list, llist and
workqueue surfaces as boundary stubs. A recorder captures every
zx_pp_{cla,pm,aging}_{read,write} so the tests can assert the exact table
traffic, the refusals, the (cookie,direction) bookkeeping, teardown and the
neighbour-invalidation path.

These tests prove software behaviour and policy, not silicon behaviour: there
is no hardware and no build here.

The source-policy tests additionally pin the two properties the task cares
about most: that the offload file uses the SHARED builders rather than its own
copies of the table bit positions (the duplication this codebase has been
bitten by twice), and that the Kconfig symbol really does depend on
NF_FLOW_TABLE (a missing dependency is a link failure at the end of a 1.5 h
build, not a compile error seen early).
"""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_tx_origin_r204 import function, tokens

ROOT = Path(__file__).resolve().parents[1]
ZTE = ROOT / 'files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte'
OFFLOAD_SOURCE = ZTE / 'zx279128-pp-offload.c'
HASH_SOURCE = ZTE / 'zx279128-pp-hash.c'
PP_SOURCE = ZTE / 'zx279128-pp.c'
PP_HEADER = ZTE / 'zx279128-pp.h'
ETH_SOURCE = ZTE / 'zx279128-eth.c'
KCONFIG = ZTE / 'Kconfig'
MAKEFILE = ZTE / 'Makefile'
CONFIG = ROOT / 'files/target/linux/armsr/config-6.6'
CHECK = ROOT / 'ci/check.sh'
HOOKUP_PATCH = ROOT / 'docs/offload/eth-hookup.patch'
SYMBOL = 'CONFIG_ZX279128_PP_OFFLOAD'

# A model of just enough of the kernel to compile and drive the offload glue.
PRELUDE = r'''
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#include <assert.h>
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
typedef uint64_t u64;
typedef uint16_t __be16;
typedef uint32_t __be32;
#define __iomem
#define ETH_ALEN 6
#define IPPROTO_TCP 6
#define IPPROTO_UDP 17
#define GFP_KERNEL 0x10u
#define GFP_ATOMIC 0x20u
#define EINVAL 22
#define ENODEV 19
#define EIO 5
#define ENOSPC 28
#define ENOMEM 12
#define EOPNOTSUPP 95
#define EEXIST 17
#define ENOENT 2
#define E2BIG 7
#define BIT(n) (1u << (n))
#define htons(x) ((u16)__builtin_bswap16((u16)(x)))
#define ntohs(x) ((u16)__builtin_bswap16((u16)(x)))
#define READ_ONCE(x) (x)
#define WARN_ON(x) ((void)(x))
#define max_t(t, a, b) ((t)(a) > (t)(b) ? (t)(a) : (t)(b))
#define container_of(ptr, type, member) \
	((type *)((char *)(ptr) - offsetof(type, member)))
static unsigned long jiffies = 1000;

/* ---- doubly linked list (kernel-shaped) ---- */
struct list_head { struct list_head *next, *prev; };
#define LIST_HEAD_INIT(n) { &(n), &(n) }
#define LIST_HEAD(n) struct list_head n = LIST_HEAD_INIT(n)
static void INIT_LIST_HEAD(struct list_head *l) { l->next = l->prev = l; }
static void __list_add(struct list_head *n, struct list_head *p, struct list_head *x)
{ x->prev = n; n->next = x; n->prev = p; p->next = n; }
static void list_add_tail(struct list_head *n, struct list_head *h) { __list_add(n, h->prev, h); }
static void list_del(struct list_head *e)
{ e->next->prev = e->prev; e->prev->next = e->next; e->next = e->prev = e; }
#define list_entry(ptr, type, member) container_of(ptr, type, member)
#define list_for_each_entry(pos, head, member) \
	for (pos = list_entry((head)->next, typeof(*pos), member); \
	     &pos->member != (head); \
	     pos = list_entry(pos->member.next, typeof(*pos), member))
#define list_for_each_entry_safe(pos, n, head, member) \
	for (pos = list_entry((head)->next, typeof(*pos), member), \
	     n = list_entry(pos->member.next, typeof(*pos), member); \
	     &pos->member != (head); \
	     pos = n, n = list_entry(n->member.next, typeof(*n), member))

/* ---- lock-free list (singly linked) ---- */
struct llist_node { struct llist_node *next; };
struct llist_head { struct llist_node *first; };
static void init_llist_head(struct llist_head *h) { h->first = NULL; }
static void llist_add(struct llist_node *n, struct llist_head *h) { n->next = h->first; h->first = n; }
static struct llist_node *llist_del_all(struct llist_head *h)
{ struct llist_node *f = h->first; h->first = NULL; return f; }
#define llist_entry(ptr, type, member) container_of(ptr, type, member)
#define llist_for_each_entry_safe(pos, n, node, member) \
	for (pos = (node) ? llist_entry(node, typeof(*pos), member) : NULL; \
	     pos && ((n = pos->member.next ? llist_entry(pos->member.next, typeof(*pos), member) : NULL), 1); \
	     pos = n)

/* ---- workqueue: run synchronously ---- */
struct work_struct { void (*func)(struct work_struct *); };
#define INIT_WORK(w, f) ((w)->func = (f))
static void schedule_work(struct work_struct *w) { w->func(w); }
static void cancel_work_sync(struct work_struct *w) { (void)w; }

/* ---- mutex ---- */
struct mutex { int init; int held; };
static void mutex_init(struct mutex *m) { m->init = 1; m->held = 0; }
static void mutex_lock(struct mutex *m) { assert(m->init && !m->held); m->held = 1; }
static void mutex_unlock(struct mutex *m) { assert(m->init && m->held); m->held = 0; }

/* ---- memory ---- */
struct device { int unused; };
static void *devm_kzalloc(struct device *d, size_t n, unsigned gfp) { (void)d; (void)gfp; return calloc(1, n); }
static void *kzalloc(size_t n, unsigned gfp) { (void)gfp; return calloc(1, n); }
static void *kmalloc(size_t n, unsigned gfp) { (void)gfp; return malloc(n); }
static void kfree(void *p) { free(p); }

/* ---- logging ---- */
static unsigned n_info, n_warn, n_err;
static char last_err[256];
static void dev_info(struct device *d, const char *fmt, ...) { (void)d; (void)fmt; n_info++; }
static void dev_warn(struct device *d, const char *fmt, ...) { (void)d; (void)fmt; n_warn++; }
static void dev_dbg(struct device *d, const char *fmt, ...) { (void)d; (void)fmt; }
static void dev_err(struct device *d, const char *fmt, ...)
{ va_list ap; (void)d; va_start(ap, fmt); vsnprintf(last_err, sizeof(last_err), fmt, ap); va_end(ap); n_err++; }

/* ---- ethernet address helpers ---- */
static void ether_addr_copy(u8 *d, const u8 *s) { memcpy(d, s, 6); }
static bool ether_addr_equal(const u8 *a, const u8 *b) { return !memcmp(a, b, 6); }
static bool is_valid_ether_addr(const u8 *a)
{ return !((a[0] & 1) || !(a[0] | a[1] | a[2] | a[3] | a[4] | a[5])); }

/* ---- net_device + ops ---- */
struct net_device_ops { int unused; };
struct net_device {
	unsigned int mtu;
	unsigned int features;
	const struct net_device_ops *netdev_ops;
	int test_port;		/* model: the port index port_index() returns */
};
#define NETIF_F_HW_TC 1u
static bool tc_can_offload(const struct net_device *dev) { return dev->features & NETIF_F_HW_TC; }

/* ---- tc setup types ---- */
enum tc_setup_type { TC_SETUP_CLSFLOWER, TC_SETUP_BLOCK, TC_SETUP_FT, TC_SETUP_OTHER };

/* ---- neighbour / netevent ---- */
#define NUD_VALID 0x3e
#define NETEVENT_NEIGH_UPDATE 1
struct neigh_table { int id; };
static struct neigh_table arp_tbl;
struct net_device_nb;
struct notifier_block { int (*notifier_call)(struct notifier_block *, unsigned long, void *); };
struct neighbour { struct neigh_table *tbl; u8 nud_state; struct net_device *dev; u8 ha[6]; };
static void neigh_ha_snapshot(char *dst, const struct neighbour *n, const struct net_device *dev)
{ (void)dev; memcpy(dst, n->ha, 6); }
static struct notifier_block *reg_netevent_nb;
static int register_netevent_notifier(struct notifier_block *nb) { reg_netevent_nb = nb; return 0; }
static int unregister_netevent_notifier(struct notifier_block *nb) { if (reg_netevent_nb == nb) reg_netevent_nb = NULL; return 0; }
#define NOTIFY_DONE 0

/* ---- flow dissector keys ---- */
enum {
	FLOW_DISSECTOR_KEY_CONTROL = 0,
	FLOW_DISSECTOR_KEY_BASIC,
	FLOW_DISSECTOR_KEY_IPV4_ADDRS,
	FLOW_DISSECTOR_KEY_IPV6_ADDRS,
	FLOW_DISSECTOR_KEY_PORTS,
	FLOW_DISSECTOR_KEY_ETH_ADDRS,
	FLOW_DISSECTOR_KEY_VLAN,
	FLOW_DISSECTOR_KEY_CVLAN,
	FLOW_DISSECTOR_KEY_META,
};
#define FLOW_DIS_IS_FRAGMENT BIT(0)
struct flow_dissector_key_control { u16 thoff; u16 addr_type; u32 flags; };
struct flow_dissector_key_basic { __be16 n_proto; u8 ip_proto; u8 padding; };
struct flow_dissector_key_ipv4_addrs { __be32 src; __be32 dst; };
struct flow_dissector_key_ports { __be16 src; __be16 dst; };
struct flow_dissector { unsigned long long used_keys; };
static bool dissector_uses_key(const struct flow_dissector *d, int key)
{ return d->used_keys & (1ULL << key); }

struct ethhdr { u8 h_dest[6]; u8 h_source[6]; __be16 h_proto; };

/* ---- flow actions ---- */
enum {
	FLOW_ACTION_MANGLE = 1, FLOW_ACTION_REDIRECT, FLOW_ACTION_CSUM,
	FLOW_ACTION_VLAN_PUSH, FLOW_ACTION_VLAN_POP, FLOW_ACTION_PPPOE_PUSH,
	FLOW_ACTION_TUNNEL_ENCAP, FLOW_ACTION_TUNNEL_DECAP, FLOW_ACTION_OTHER,
};
enum { FLOW_ACT_MANGLE_UNSPEC = 0, FLOW_ACT_MANGLE_HDR_TYPE_ETH, FLOW_ACT_MANGLE_HDR_TYPE_IP4 };
struct flow_action_entry {
	int id;
	union {
		struct net_device *dev;
		struct { int htype; u32 offset; u32 mask; u32 val; } mangle;
	};
};
struct flow_action { unsigned int num_entries; struct flow_action_entry entries[8]; };
#define flow_action_for_each(__i, __act, __actions) \
	for (__i = 0, __act = &(__actions)->entries[0]; \
	     __i < (int)(__actions)->num_entries; \
	     __act = &(__actions)->entries[++__i])

/* ---- flow rule + match wrappers ---- */
struct flow_rule {
	struct { struct flow_dissector *dissector; } match;
	struct flow_dissector dissector;
	struct flow_dissector_key_control ctrl_k, ctrl_m;
	struct flow_dissector_key_basic basic_k, basic_m;
	struct flow_dissector_key_ipv4_addrs v4_k, v4_m;
	struct flow_dissector_key_ports ports_k, ports_m;
	struct flow_action action;
};
struct flow_match_control { struct flow_dissector_key_control *key, *mask; };
struct flow_match_basic { struct flow_dissector_key_basic *key, *mask; };
struct flow_match_ipv4_addrs { struct flow_dissector_key_ipv4_addrs *key, *mask; };
struct flow_match_ports { struct flow_dissector_key_ports *key, *mask; };
static bool flow_rule_match_key(const struct flow_rule *r, int key)
{ return dissector_uses_key(r->match.dissector, key); }
static void flow_rule_match_control(const struct flow_rule *r, struct flow_match_control *m)
{ m->key = (void *)&r->ctrl_k; m->mask = (void *)&r->ctrl_m; }
static void flow_rule_match_basic(const struct flow_rule *r, struct flow_match_basic *m)
{ m->key = (void *)&r->basic_k; m->mask = (void *)&r->basic_m; }
static void flow_rule_match_ipv4_addrs(const struct flow_rule *r, struct flow_match_ipv4_addrs *m)
{ m->key = (void *)&r->v4_k; m->mask = (void *)&r->v4_m; }
static void flow_rule_match_ports(const struct flow_rule *r, struct flow_match_ports *m)
{ m->key = (void *)&r->ports_k; m->mask = (void *)&r->ports_m; }

/* ---- flow_cls_offload + stats ---- */
enum { FLOW_CLS_REPLACE = 0, FLOW_CLS_DESTROY, FLOW_CLS_STATS, FLOW_CLS_OTHER };
enum flow_action_hw_stats { FLOW_ACTION_HW_STATS_IMMEDIATE = 1, FLOW_ACTION_HW_STATS_ANY = 7 };
struct flow_stats { u64 pkts, bytes, drops, lastused; enum flow_action_hw_stats used_hw_stats; bool used_hw_stats_valid; };
struct flow_cls_offload { int command; unsigned long cookie; struct flow_rule *rule; struct flow_stats stats; };
static struct flow_rule *flow_cls_offload_flow_rule(struct flow_cls_offload *c) { return c->rule; }
static void flow_stats_update(struct flow_stats *s, u64 bytes, u64 pkts, u64 drops,
			      u64 lastused, enum flow_action_hw_stats used)
{ s->pkts += pkts; s->bytes += bytes; s->drops += drops;
  s->lastused = max_t(u64, s->lastused, lastused); s->used_hw_stats |= used; s->used_hw_stats_valid = true; }

/* ---- flow_block plumbing (bind/unbind) ---- */
enum { FLOW_BLOCK_BIND = 0, FLOW_BLOCK_UNBIND };
enum { FLOW_BLOCK_BINDER_TYPE_CLSACT_INGRESS = 1, FLOW_BLOCK_BINDER_TYPE_OTHER = 2 };
typedef int flow_setup_cb_t(enum tc_setup_type, void *, void *);
struct flow_block { int id; };
struct flow_block_offload { int command; int binder_type; struct flow_block *block; struct list_head *driver_block_list; };
struct flow_block_cb { struct list_head driver_list; flow_setup_cb_t *cb; void *cb_ident; void *cb_priv; int refcnt; };
static struct flow_block_cb *cb_alloc_ret;
static struct flow_block_cb *cb_lookup_ret;
static struct flow_block_cb *flow_block_cb_lookup(struct flow_block *b, flow_setup_cb_t *cb, void *ident)
{ (void)b; (void)cb; (void)ident; return cb_lookup_ret; }
static struct flow_block_cb *flow_block_cb_alloc(flow_setup_cb_t *cb, void *ident, void *priv, void *rel)
{ (void)rel; cb_alloc_ret = calloc(1, sizeof(*cb_alloc_ret)); cb_alloc_ret->cb = cb;
  cb_alloc_ret->cb_ident = ident; cb_alloc_ret->cb_priv = priv; return cb_alloc_ret; }
static void flow_block_cb_incref(struct flow_block_cb *c) { c->refcnt++; }
static unsigned int flow_block_cb_decref(struct flow_block_cb *c) { return --c->refcnt; }
static void flow_block_cb_add(struct flow_block_cb *c, struct flow_block_offload *f) { (void)c; (void)f; }
static void flow_block_cb_remove(struct flow_block_cb *c, struct flow_block_offload *f) { (void)c; (void)f; }
#define IS_ERR(p) ((unsigned long)(void *)(p) >= (unsigned long)-4095)
#define PTR_ERR(p) ((long)(p))

/* ---- recorder for the table traffic ---- */
struct op { char eng; char rw; unsigned sel; u32 addr; unsigned words; };
#define NOPS 4096
static struct op ops[NOPS];
static unsigned nops;
static int fail_at;	/* 1-based op index to fail */
static u32 read_val;
static void record(char eng, char rw, unsigned sel, u32 addr, unsigned words)
{ assert(nops < NOPS); ops[nops].eng = eng; ops[nops].rw = rw; ops[nops].sel = sel;
  ops[nops].addr = addr; ops[nops].words = words; nops++; }
static int maybe_fail(void) { return (fail_at && (int)nops + 1 == fail_at) ? -5 /*EIO*/ : 0; }

struct zx_pp;
int zx_pp_cla_write(struct zx_pp *pp, unsigned sel, u32 addr, const u32 *d, unsigned w)
{ (void)pp; (void)d; int e = maybe_fail(); record('C','W',sel,addr,w); return e; }
int zx_pp_cla_read(struct zx_pp *pp, unsigned sel, u32 addr, u32 *d, unsigned w)
{ (void)pp; int e = maybe_fail(); if (!e && d) for (unsigned i=0;i<w;i++) d[i]=read_val; record('C','R',sel,addr,w); return e; }
int zx_pp_pm_write(struct zx_pp *pp, unsigned sel, u32 addr, const u32 *d, unsigned w)
{ (void)pp; (void)d; int e = maybe_fail(); record('P','W',sel,addr,w); return e; }
int zx_pp_pm_read(struct zx_pp *pp, unsigned sel, u32 addr, u32 *d, unsigned w)
{ (void)pp; int e = maybe_fail(); if (!e && d) d[0]=read_val; record('P','R',sel,addr,w); return e; }
int zx_pp_aging_read(struct zx_pp *pp, u32 addr, u32 *v)
{ (void)pp; int e = maybe_fail(); if (!e && v) *v = read_val; record('C','R',8,addr,1); return e; }
int zx_pp_aging_write(struct zx_pp *pp, u32 addr, u32 v)
{ (void)pp; (void)v; int e = maybe_fail(); record('C','W',8,addr,1); return e; }
'''

# The hash config stub plus the shared-builder header declarations are spliced
# between PRELUDE and the real builder source.
STUBS = r'''
static int outer_usable = 1;
int zx_pp_hash_config(struct zx_pp *pp, struct zx_pp_hash_cfg *cfg)
{
	unsigned i;
	(void)pp;
	if (!cfg) return -22;
	for (i = 0; i < 4; i++) { cfg->inner[i] = (u8)i; cfg->outer[i] = (u8)i; }
	cfg->outer_num = 0; cfg->outer_space = outer_usable ? 0 : 1;
	cfg->usable = outer_usable != 0;
	return 0;
}
'''

# A test-only accessor to the single offload context, and a couple of thin
# wrappers so the cases can drive the static command path and inspect the pools.
ACCESSOR = r'''
struct zx_pp_offload *offload_ctx_for_test(void) { return g_offload; }
int offload_cmd_for_test(struct net_device *idev, struct flow_cls_offload *cls)
{ return zx_pp_offload_cmd(idev, cls); }
unsigned offload_nh_used(void)
{
	unsigned i, c = 0;
	if (!g_offload) return 0;
	for (i = 0; i < ZX_PP_OFF_NEXT_HOP_SLOTS; i++)
		c += g_offload->nh_used[i];
	return c;
}
unsigned offload_fi_used(void)
{
	unsigned i, c = 0;
	if (!g_offload) return 0;
	for (i = 0; i < ZX_PP_OFF_FLOW_INFO_SLOTS; i++)
		c += g_offload->fi_used[i];
	return c;
}
unsigned offload_map_used(void)
{
	unsigned i, c = 0;
	if (!g_offload) return 0;
	for (i = 0; i < ZX_PP_HASH_SLOTS; i++)
		c += g_offload->map.used[i];
	return c;
}
unsigned offload_entries(void)
{
	struct zx_pp_offload_entry *e;
	unsigned c = 0;
	if (!g_offload) return 0;
	list_for_each_entry(e, &g_offload->entries, list)
		c++;
	return c;
}
void offload_fire_neigh(const u8 *ha, u8 nud)
{ struct neighbour n; memset(&n, 0, sizeof(n)); n.tbl = &arp_tbl; n.nud_state = nud;
  memcpy(n.ha, ha, 6); if (reg_netevent_nb) reg_netevent_nb->notifier_call(reg_netevent_nb, NETEVENT_NEIGH_UPDATE, &n); }
'''

CASES = r'''
static struct device dev;
static struct zx_pp *dummy_pp = (struct zx_pp *)0x1234;
static struct net_device nd_p2, nd_p4, nd_wifi;

/* The Ethernet-side seam: a model port_index(). nd_p2/nd_p4 are switch ports;
 * nd_wifi is not (returns -1), standing in for a software-only interface.
 */
static int model_port_index(const struct net_device *d)
{ return d ? d->test_port : -1; }
static const struct zx_pp_offload_dev_ops model_ops = { .port_index = model_port_index };

static void reset(void)
{
	nops = 0; fail_at = 0; read_val = 0; n_info = n_warn = n_err = 0; last_err[0] = 0;
	outer_usable = 1; reg_netevent_nb = NULL; cb_alloc_ret = NULL; cb_lookup_ret = NULL;
	g_offload = NULL;
	memset(&nd_p2, 0, sizeof(nd_p2)); nd_p2.test_port = 2; nd_p2.mtu = 1500; nd_p2.features = NETIF_F_HW_TC;
	memset(&nd_p4, 0, sizeof(nd_p4)); nd_p4.test_port = 4; nd_p4.mtu = 1500; nd_p4.features = NETIF_F_HW_TC;
	memset(&nd_wifi, 0, sizeof(nd_wifi)); nd_wifi.test_port = -1; nd_wifi.mtu = 1500; nd_wifi.features = NETIF_F_HW_TC;
}

/* Bring the offload up and hand it the port-index seam, then clear the recorder
 * so a case starts from a clean op count (the rule-init writes are counted
 * separately where it matters).
 */
static void up_wired(void)
{
	reset();
	zx_pp_offload_init(dummy_pp, &dev);
	assert(g_offload != NULL);
	zx_pp_offload_set_dev_ops(dummy_pp, &model_ops);
	nops = 0;
}

/* Build a standard, acceptable ORIGINAL flow: eth2 -> eth4, UDP, next-hop MAC
 * set by an ETH mangle, one redirect to nd_p4. `cookie` distinguishes the two
 * directions.
 */
static void build_flow(struct flow_rule *r, struct flow_cls_offload *cls,
		       unsigned long cookie, struct net_device *odev)
{
	static const u8 dmac[6] = { 0x02, 0x11, 0x22, 0x33, 0x44, 0x55 };
	memset(r, 0, sizeof(*r));
	r->match.dissector = &r->dissector;
	r->dissector.used_keys = (1ULL << FLOW_DISSECTOR_KEY_CONTROL) |
				 (1ULL << FLOW_DISSECTOR_KEY_BASIC) |
				 (1ULL << FLOW_DISSECTOR_KEY_IPV4_ADDRS) |
				 (1ULL << FLOW_DISSECTOR_KEY_PORTS);
	r->ctrl_k.addr_type = FLOW_DISSECTOR_KEY_IPV4_ADDRS;
	r->ctrl_k.flags = 0;
	r->basic_k.ip_proto = IPPROTO_UDP;
	r->v4_k.src = (u32)(192u | 0u<<8 | 2u<<16 | 1u<<24);	/* 192.0.2.1 */
	r->v4_k.dst = (u32)(198u | 51u<<8 | 100u<<16 | 2u<<24);	/* 198.51.100.2 */
	r->ports_k.src = htons(40001);
	r->ports_k.dst = htons(40002);
	/* actions: one ETH mangle that writes the DMAC, one redirect. */
	r->action.num_entries = 2;
	r->action.entries[0].id = FLOW_ACTION_MANGLE;
	r->action.entries[0].mangle.htype = FLOW_ACT_MANGLE_HDR_TYPE_ETH;
	r->action.entries[0].mangle.offset = 0;
	r->action.entries[0].mangle.mask = 0;		/* 4-byte write of h_dest[0..3] */
	memcpy(&r->action.entries[0].mangle.val, dmac, 4);
	r->action.entries[1].id = FLOW_ACTION_REDIRECT;
	r->action.entries[1].dev = odev;
	memset(cls, 0, sizeof(*cls));
	cls->command = FLOW_CLS_REPLACE;
	cls->cookie = cookie;
	cls->rule = r;
	/* The second mangle piece (h_dest[4..5]) would be a second ETH mangle;
	 * fold it into entry0 by writing all 6 via mask=0 above is not possible
	 * (mangle writes 4), so add it explicitly.
	 */
	r->action.entries[2].id = FLOW_ACTION_MANGLE;
	r->action.entries[2].mangle.htype = FLOW_ACT_MANGLE_HDR_TYPE_ETH;
	r->action.entries[2].mangle.offset = 4;
	/* nf_flow_table's second ETH mangle uses mask ~0x0000ffff = 0xffff0000
	 * and a 2-byte value; zx_pp_offload_mangle_eth writes h_dest[4..5].
	 */
	r->action.entries[2].mangle.mask = 0xffff0000u;
	{ u16 tail; memcpy(&tail, dmac + 4, 2); r->action.entries[2].mangle.val = (u32)tail; }
	r->action.num_entries = 3;
}

/* --- the ternary rule-init is what the engine needs before any match --- */
static void t_init_installs_the_rule(void)
{
	reset();
	zx_pp_offload_init(dummy_pp, &dev);
	assert(g_offload != NULL);
	/* rule init writes extra_rule[0x90], [0x91] and read-modify-writes
	 * extra_index[9]: cla writes sel1 at 0x90 and 0x91, a sel0 read and a
	 * sel0 write at 9.
	 */
	unsigned w90 = 0, w91 = 0, rd9 = 0, wr9 = 0;
	for (unsigned i = 0; i < nops; i++) {
		if (ops[i].eng=='C' && ops[i].rw=='W' && ops[i].sel==1 && ops[i].addr==0x90) w90++;
		if (ops[i].eng=='C' && ops[i].rw=='W' && ops[i].sel==1 && ops[i].addr==0x91) w91++;
		if (ops[i].eng=='C' && ops[i].rw=='R' && ops[i].sel==0 && ops[i].addr==9) rd9++;
		if (ops[i].eng=='C' && ops[i].rw=='W' && ops[i].sel==0 && ops[i].addr==9) wr9++;
	}
	assert(w90 == 1 && w91 == 1 && rd9 == 1 && wr9 == 1);
	assert(reg_netevent_nb != NULL);	/* neighbour notifier registered */
}

/* --- a wired, acceptable flow installs one entry --- */
static void t_replace_installs_one_entry(void)
{
	struct flow_rule r; struct flow_cls_offload cls;
	up_wired();
	build_flow(&r, &cls, 0x1001, &nd_p4);
	assert(offload_cmd_for_test(&nd_p2, &cls) == 0);
	assert(offload_entries() == 1);
	assert(offload_nh_used() == 1 && offload_fi_used() == 1 && offload_map_used() == 1);
	/* the four table writes: next_hop (PM1), flow_info (PM0), CLA window, aging. */
	unsigned pm1 = 0, pm0 = 0, claw = 0, aging = 0;
	for (unsigned i = 0; i < nops; i++) {
		if (ops[i].eng=='P' && ops[i].rw=='W' && ops[i].sel==1) pm1++;
		if (ops[i].eng=='P' && ops[i].rw=='W' && ops[i].sel==0) pm0++;
		if (ops[i].eng=='C' && ops[i].rw=='W' && ops[i].sel>=2 && ops[i].sel<=6) claw++;
		if (ops[i].eng=='C' && ops[i].rw=='W' && ops[i].sel==8) aging++;
	}
	assert(pm1 == 1 && pm0 == 1 && claw == 1 && aging == 1);
}

/* --- ORIGINAL and REPLY are two distinct entries, keyed on cookie --- */
static void t_both_directions_install_two_entries(void)
{
	struct flow_rule ro, rr; struct flow_cls_offload co, cr;
	up_wired();
	build_flow(&ro, &co, 0x1001, &nd_p4);		/* ORIGINAL cookie */
	/* REPLY: different cookie, swapped tuple, egress nd_p2. */
	build_flow(&rr, &cr, 0x2002, &nd_p2);
	rr.v4_k.src = (u32)(198u | 51u<<8 | 100u<<16 | 2u<<24);
	rr.v4_k.dst = (u32)(192u | 0u<<8 | 2u<<16 | 1u<<24);
	rr.ports_k.src = htons(40002); rr.ports_k.dst = htons(40001);
	assert(offload_cmd_for_test(&nd_p2, &co) == 0);
	assert(offload_cmd_for_test(&nd_p4, &cr) == 0);
	assert(offload_entries() == 2);
	assert(offload_nh_used() == 2 && offload_fi_used() == 2 && offload_map_used() == 2);
	/* a repeat of the same cookie is refused as EEXIST, not a second entry. */
	assert(offload_cmd_for_test(&nd_p2, &co) == -17);	/* EEXIST */
	assert(offload_entries() == 2);
	/* destroy both; every slot released. */
	co.command = FLOW_CLS_DESTROY;
	cr.command = FLOW_CLS_DESTROY;
	assert(offload_cmd_for_test(&nd_p2, &co) == 0);
	assert(offload_cmd_for_test(&nd_p4, &cr) == 0);
	assert(offload_entries() == 0);
	assert(offload_nh_used() == 0 && offload_fi_used() == 0 && offload_map_used() == 0);
}

/* --- every refusal returns -EOPNOTSUPP and installs nothing --- */
#define EOPNOTSUPP 95
static void expect_refused(struct flow_cls_offload *cls, struct net_device *idev)
{
	unsigned before = offload_entries();
	nops = 0;
	assert(offload_cmd_for_test(idev, cls) == -EOPNOTSUPP);
	assert(offload_entries() == before);
	assert(nops == 0);	/* nothing written */
}
static void t_refusals(void)
{
	struct flow_rule r; struct flow_cls_offload cls;

	/* IPv6 (addr_type not v4). */
	up_wired(); build_flow(&r, &cls, 1, &nd_p4);
	r.ctrl_k.addr_type = FLOW_DISSECTOR_KEY_IPV6_ADDRS;
	expect_refused(&cls, &nd_p2);

	/* fragment. */
	up_wired(); build_flow(&r, &cls, 1, &nd_p4);
	r.ctrl_k.flags = FLOW_DIS_IS_FRAGMENT;
	expect_refused(&cls, &nd_p2);

	/* VLAN match present. */
	up_wired(); build_flow(&r, &cls, 1, &nd_p4);
	r.dissector.used_keys |= (1ULL << FLOW_DISSECTOR_KEY_VLAN);
	expect_refused(&cls, &nd_p2);

	/* non-TCP/UDP protocol. */
	up_wired(); build_flow(&r, &cls, 1, &nd_p4);
	r.basic_k.ip_proto = 1;	/* ICMP */
	expect_refused(&cls, &nd_p2);

	/* NAT: an IP4 header mangle. */
	up_wired(); build_flow(&r, &cls, 1, &nd_p4);
	r.action.entries[1].id = FLOW_ACTION_MANGLE;
	r.action.entries[1].mangle.htype = FLOW_ACT_MANGLE_HDR_TYPE_IP4;
	/* keep a redirect so only the mangle is the cause. */
	r.action.entries[3].id = FLOW_ACTION_REDIRECT;
	r.action.entries[3].dev = &nd_p4;
	r.action.num_entries = 4;
	expect_refused(&cls, &nd_p2);

	/* two redirects. */
	up_wired(); build_flow(&r, &cls, 1, &nd_p4);
	r.action.entries[3].id = FLOW_ACTION_REDIRECT;
	r.action.entries[3].dev = &nd_p2;
	r.action.num_entries = 4;
	expect_refused(&cls, &nd_p2);

	/* PPPoE push. */
	up_wired(); build_flow(&r, &cls, 1, &nd_p4);
	r.action.entries[3].id = FLOW_ACTION_PPPOE_PUSH;
	r.action.num_entries = 4;
	expect_refused(&cls, &nd_p2);

	/* ingress not a switch port (software-only path). */
	up_wired(); build_flow(&r, &cls, 1, &nd_p4);
	expect_refused(&cls, &nd_wifi);

	/* egress not a switch port. */
	up_wired(); build_flow(&r, &cls, 1, &nd_wifi);
	expect_refused(&cls, &nd_p2);

	/* egress MTU too large. */
	up_wired(); build_flow(&r, &cls, 1, &nd_p4);
	nd_p4.mtu = 9000;
	expect_refused(&cls, &nd_p2);
}

/* --- inert without the Ethernet seam: no dev_ops -> refuse, install nothing --- */
static void t_inert_without_hook(void)
{
	struct flow_rule r; struct flow_cls_offload cls;
	reset();
	zx_pp_offload_init(dummy_pp, &dev);	/* no set_dev_ops() */
	assert(g_offload != NULL);
	nops = 0;
	build_flow(&r, &cls, 1, &nd_p4);
	assert(offload_cmd_for_test(&nd_p2, &cls) == -EOPNOTSUPP);
	assert(offload_entries() == 0);
	assert(nops == 0);
	/* setup_tc for an unknown pp is also inert. */
	assert(zx_pp_offload_setup_tc((struct zx_pp *)0xbad, &nd_p2, TC_SETUP_FT, NULL) == -EOPNOTSUPP);
}

/* --- teardown flushes every entry and releases every slot --- */
static void t_teardown_flushes(void)
{
	struct flow_rule ro, rr; struct flow_cls_offload co, cr;
	up_wired();
	build_flow(&ro, &co, 0x1001, &nd_p4);
	build_flow(&rr, &cr, 0x2002, &nd_p2);
	assert(offload_cmd_for_test(&nd_p2, &co) == 0);
	assert(offload_cmd_for_test(&nd_p4, &cr) == 0);
	assert(offload_entries() == 2);
	nops = 0;
	assert(zx_pp_offload_fini(dummy_pp) == 0);
	assert(g_offload == NULL);	/* clean -> handle dropped */
	/* each entry cleared with four writes: CLA window, aging, flow_info, next_hop. */
	unsigned claw=0, aging=0, pm0=0, pm1=0;
	for (unsigned i = 0; i < nops; i++) {
		if (ops[i].eng=='C'&&ops[i].rw=='W'&&ops[i].sel>=2&&ops[i].sel<=6) claw++;
		if (ops[i].eng=='C'&&ops[i].rw=='W'&&ops[i].sel==8) aging++;
		if (ops[i].eng=='P'&&ops[i].rw=='W'&&ops[i].sel==0) pm0++;
		if (ops[i].eng=='P'&&ops[i].rw=='W'&&ops[i].sel==1) pm1++;
	}
	assert(claw==2 && aging==2 && pm0==2 && pm1==2);
}

/* --- teardown that cannot clear keeps the tables (returns non-zero) --- */
static void t_teardown_failed_clear_keeps_tables(void)
{
	struct flow_rule r; struct flow_cls_offload cls;
	up_wired();
	build_flow(&r, &cls, 1, &nd_p4);
	assert(offload_cmd_for_test(&nd_p2, &cls) == 0);
	/* fail the very first clear write during fini (op counter restarts). */
	nops = 0;
	fail_at = 1;
	assert(zx_pp_offload_fini(dummy_pp) != 0);
	assert(g_offload != NULL);		/* handle kept */
	assert(offload_entries() == 1);		/* entry kept on the list */
}

/* --- port down flushes that port's entries; idempotent and safe twice --- */
static void t_port_down_flushes(void)
{
	struct flow_rule r; struct flow_cls_offload cls;
	up_wired();
	build_flow(&r, &cls, 1, &nd_p4);
	assert(offload_cmd_for_test(&nd_p2, &cls) == 0);	/* ingress 2, egress 4 */
	assert(offload_entries() == 1);
	/* a port that never offloaded anything: no change, no crash. */
	{ struct net_device p0; memset(&p0,0,sizeof(p0)); p0.test_port = 0;
	  zx_pp_offload_port_down(dummy_pp, &p0); }
	assert(offload_entries() == 1);
	/* the egress port closes: entry gone. */
	zx_pp_offload_port_down(dummy_pp, &nd_p4);
	assert(offload_entries() == 0);
	/* called again on the same port: safe, still zero. */
	zx_pp_offload_port_down(dummy_pp, &nd_p4);
	assert(offload_entries() == 0);
	/* safe with no context at all. */
	g_offload = NULL;
	zx_pp_offload_port_down(dummy_pp, &nd_p4);
}

/* --- neighbour going invalid deletes the entry with that DMAC --- */
static void t_neigh_invalidation(void)
{
	struct flow_rule r; struct flow_cls_offload cls;
	static const u8 dmac[6] = { 0x02, 0x11, 0x22, 0x33, 0x44, 0x55 };
	static const u8 other[6] = { 0x02, 0x99, 0x99, 0x99, 0x99, 0x99 };
	up_wired();
	build_flow(&r, &cls, 1, &nd_p4);
	assert(offload_cmd_for_test(&nd_p2, &cls) == 0);
	assert(offload_entries() == 1);
	/* a still-valid update does nothing. */
	offload_fire_neigh(dmac, NUD_VALID);
	assert(offload_entries() == 1);
	/* an unrelated MAC going invalid does nothing. */
	offload_fire_neigh(other, 0);
	assert(offload_entries() == 1);
	/* the programmed next-hop MAC going invalid deletes the entry. */
	offload_fire_neigh(dmac, 0);
	assert(offload_entries() == 0);
	assert(offload_nh_used() == 0 && offload_fi_used() == 0);
}

/* --- stats: used from the hit bit, zero packets/bytes by design --- */
static void t_stats_liveness_only(void)
{
	struct flow_rule r; struct flow_cls_offload cls;
	up_wired();
	build_flow(&r, &cls, 1, &nd_p4);
	assert(offload_cmd_for_test(&nd_p2, &cls) == 0);
	/* a STATS command with the hit bit set. */
	read_val = 1;			/* aging read returns a hit */
	cls.command = FLOW_CLS_STATS;
	cls.stats.pkts = 0; cls.stats.bytes = 0; cls.stats.lastused = 0;
	jiffies = 5000;
	assert(offload_cmd_for_test(&nd_p2, &cls) == 0);
	assert(cls.stats.pkts == 0 && cls.stats.bytes == 0);	/* never fabricated */
	assert(cls.stats.lastused == 5000);			/* used from the hit bit */
}

/* --- flow_block bind/unbind: the standard pattern, ingress only --- */
static void t_block_bind_unbind(void)
{
	struct flow_block_offload f; struct flow_block blk;
	up_wired();
	memset(&f, 0, sizeof(f)); f.block = &blk;
	f.binder_type = FLOW_BLOCK_BINDER_TYPE_CLSACT_INGRESS;
	f.command = FLOW_BLOCK_BIND;
	cb_lookup_ret = NULL;	/* nothing bound yet */
	assert(zx_pp_offload_setup_tc(dummy_pp, &nd_p2, TC_SETUP_FT, &f) == 0);
	assert(cb_alloc_ret != NULL && cb_alloc_ret->cb_priv == &nd_p2);
	/* an egress binder is refused. */
	f.binder_type = FLOW_BLOCK_BINDER_TYPE_OTHER;
	assert(zx_pp_offload_setup_tc(dummy_pp, &nd_p2, TC_SETUP_FT, &f) == -EOPNOTSUPP);
	/* unbind drops the ref. */
	f.binder_type = FLOW_BLOCK_BINDER_TYPE_CLSACT_INGRESS;
	f.command = FLOW_BLOCK_UNBIND;
	cb_lookup_ret = cb_alloc_ret;
	assert(zx_pp_offload_setup_tc(dummy_pp, &nd_p2, TC_SETUP_FT, &f) == 0);
}

int main(int argc, char **argv)
{
	static const struct { const char *name; void (*fn)(void); } cases[] = {
		{ "init_rule", t_init_installs_the_rule },
		{ "replace_one", t_replace_installs_one_entry },
		{ "both_dirs", t_both_directions_install_two_entries },
		{ "refusals", t_refusals },
		{ "inert", t_inert_without_hook },
		{ "teardown", t_teardown_flushes },
		{ "teardown_fail", t_teardown_failed_clear_keeps_tables },
		{ "port_down", t_port_down_flushes },
		{ "neigh", t_neigh_invalidation },
		{ "stats", t_stats_liveness_only },
		{ "block", t_block_bind_unbind },
	};
	assert(argc == 2);
	for (unsigned i = 0; i < ARRAY_SIZE(cases); i++)
		if (!strcmp(argv[1], cases[i].name)) {
			cases[i].fn();
			printf("PASS %s\n", cases[i].name);
			return 0;
		}
	fprintf(stderr, "no case %s\n", argv[1]);
	return 2;
}
'''


def strip_includes(text):
    return re.sub(r'^#include[^\n]*\n', '', text, flags=re.M)


def exact_struct(header, name):
    return re.search(r'^struct ' + name + r' \{.*?^\};', header, re.M | re.S).group()


class PpOffloadModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        root = Path(cls.directory.name)
        source, cls.executable = root / 'offload.c', root / 'offload'
        header = PP_HEADER.read_text()
        # Supply the header's #defines and the structs the model/driver name,
        # taken from the real header so they cannot drift.
        defines = re.findall(r'^#define\s+(ZX_PP_\w+)\s+.*$', header, re.M)
        supplied = '\n'.join(
            [re.search(r'^#define\s+' + d + r'\s+.*$', header, re.M).group() for d in defines]
            + [exact_struct(header, st) for st in
               ('zx_pp_hash_cfg', 'zx_pp_hash_map', 'zx_pp_offload_dev_ops')])
        body = strip_includes(OFFLOAD_SOURCE.read_text())
        body = body.replace('#endif /* CONFIG_ZX279128_PP_OFFLOAD */',
                            ACCESSOR + '\n#endif /* CONFIG_ZX279128_PP_OFFLOAD */', 1)
        source.write_text(PRELUDE + supplied + '\n' + STUBS + '\n' +
                          f'#define {SYMBOL} 1\n' +
                          strip_includes(HASH_SOURCE.read_text()) + body + CASES)
        built = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                '-Wno-unused-parameter', '-Wno-unused-function',
                                str(source), '-o', str(cls.executable)],
                               capture_output=True, text=True, timeout=120)
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

    def test_init_installs_the_ternary_rule(self):
        self.run_case('init_rule')

    def test_a_wired_flow_installs_one_entry(self):
        self.run_case('replace_one')

    def test_both_directions_install_two_entries_keyed_on_cookie(self):
        self.run_case('both_dirs')

    def test_every_refusal_returns_eopnotsupp_and_installs_nothing(self):
        self.run_case('refusals')

    def test_inert_without_the_ethernet_hook(self):
        self.run_case('inert')

    def test_teardown_flushes_every_entry_and_releases_every_slot(self):
        self.run_case('teardown')

    def test_teardown_that_cannot_clear_keeps_the_tables(self):
        self.run_case('teardown_fail')

    def test_port_down_flushes_and_is_idempotent(self):
        self.run_case('port_down')

    def test_neighbour_invalidation_deletes_the_entry(self):
        self.run_case('neigh')

    def test_stats_report_liveness_only_never_fabricated_counts(self):
        self.run_case('stats')

    def test_flow_block_bind_unbind_ingress_only(self):
        self.run_case('block')


class PpOffloadSharedBuilderTests(unittest.TestCase):
    """The failure mode this codebase has been bitten by twice: a second copy
    of the table bit positions. The offload file must go through the SHARED
    builders in zx279128-pp-hash.c, never its own packing."""

    def setUp(self):
        self.text = OFFLOAD_SOURCE.read_text()

    def test_uses_the_shared_entry_builders(self):
        for builder in ('zx_pp_build_next_hop', 'zx_pp_build_flow_info',
                        'zx_pp_build_window_ipv4', 'zx_pp_build_key',
                        'zx_pp_build_extra_rule_v4', 'zx_pp_hash_place',
                        'zx_pp_hash_bank'):
            with self.subTest(builder=builder):
                self.assertIn(builder, self.text)

    def test_never_packs_table_bits_itself(self):
        # The low-level packers that encode bit positions live only in
        # zx279128-pp-hash.c; the offload file must not call them.
        self.assertNotIn('zx_pp_set_field', self.text)
        self.assertNotIn('zx_pp_pack_words', self.text)
        self.assertNotIn('zx_pp_fill_action', self.text)
        self.assertNotIn('zx_pp_build_window_v4(', self.text)

    def test_no_handpacked_table_byte_offsets(self):
        # A re-encoded entry would show up as byte-literal writes into a buffer
        # (b[0x11] = 0xf0, window[17] = ...). Those belong only to the shared
        # builders. Strip comments first so a refusal comment that merely names
        # "winoffsets" is not mistaken for a second copy of the encoding.
        code = re.sub(r'/\*.*?\*/', '', self.text, flags=re.S)
        code = re.sub(r'//[^\n]*', '', code)
        self.assertFalse(re.search(r'\bwindow\s*\[\s*\d', code),
                         'offload must not index a window byte buffer itself')
        self.assertFalse(re.search(r'\bwinoffset\s*\d|\bwinmask\s*\d', code))
        self.assertFalse(re.search(r'\bb\[0x[0-9a-fA-F]+\]\s*=', code),
                         'offload must not hand-pack entry bytes')

    def test_the_only_bit_literal_is_the_documented_fast_enable(self):
        # The one hardware bit the offload file states for itself is the
        # extra_index fast-path enable (bit 0), which is a table SELECTOR-level
        # control, not an entry layout. It must be commented as such.
        self.assertIn('ZX_PP_OFF_EXTRA_INDEX_V4_BIT', self.text)
        self.assertIn('tm_acl_fast_init', self.text)


class PpOffloadBuildGateTests(unittest.TestCase):
    def test_kconfig_symbol_is_bool_default_n_and_depends_on_nf_flow_table(self):
        block = re.search(r'^config ZX279128_PP_OFFLOAD\n(.*?)(?=^\S)',
                          KCONFIG.read_text(), re.M | re.S)
        self.assertIsNotNone(block)
        body = block.group(1)
        self.assertIn('\tbool "', body)
        self.assertIn('\tdefault n\n', body)
        # No `select` statement (the help text may say "unselectable").
        self.assertFalse(re.search(r'^\tselect ', body, re.M))
        # The load-bearing dependency: ZX279128_PP_TABLES && NF_FLOW_TABLE.
        depends = re.search(r'^\tdepends on (.+)$', body, re.M)
        self.assertIsNotNone(depends)
        self.assertIn('ZX279128_PP_TABLES', depends.group(1))
        self.assertIn('NF_FLOW_TABLE', depends.group(1))

    def test_nf_flow_table_dependency_is_not_accidentally_dropped(self):
        # This is the one that stops a 1.5 h build ending in a link failure:
        # zx279128_eth is a bool and nf_flow_table is a module, so the symbol
        # must depend on NF_FLOW_TABLE (and the config must build it in).
        kconfig = KCONFIG.read_text()
        block = re.search(r'^config ZX279128_PP_OFFLOAD\n.*?depends on ([^\n]+)',
                          kconfig, re.M | re.S)
        self.assertIsNotNone(block)
        self.assertRegex(block.group(1), r'NF_FLOW_TABLE\b')

    def test_no_shipped_config_enables_the_symbol(self):
        config = CONFIG.read_text().splitlines()
        self.assertEqual(config.count('# CONFIG_ZX279128_PP_OFFLOAD is not set'), 1)
        self.assertFalse([l for l in config if l.startswith(SYMBOL + '=')])

    def test_ci_policy_test_would_catch_it_being_turned_on(self):
        # The CI guard (ci/check.sh) and the policy unit test both name the
        # symbol, so turning it on in the shipped config fails the gate.
        self.assertIn("grep -q '^CONFIG_ZX279128_PP_OFFLOAD=y'", CHECK.read_text())
        policy = (ROOT / 'tests/test_upstream_policy.py').read_text()
        self.assertIn('CONFIG_ZX279128_PP_OFFLOAD', policy)

    def test_makefile_links_the_object_only_when_enabled(self):
        make = MAKEFILE.read_text()
        self.assertIn('zx279128_eth-$(CONFIG_ZX279128_PP_OFFLOAD) += zx279128-pp-offload.o', make)
        # it is inside the PP_TABLES branch (offload depends on tables)
        branch = make.split('ifdef CONFIG_ZX279128_PP_TABLES', 1)[1].split('else', 1)[0]
        self.assertIn('zx279128-pp-offload.o', branch)

    def test_symbol_off_compiles_to_nothing(self):
        off = subprocess.run(['cc', '-E', '-P', '-x', 'c', '-'],
                             input=strip_includes(OFFLOAD_SOURCE.read_text()),
                             capture_output=True, text=True, check=True).stdout
        self.assertFalse(re.findall(r'zx_pp_offload_\w+', off))

    def test_pp_c_calls_the_offload_hooks_behind_the_symbol(self):
        pp = PP_SOURCE.read_text()
        init = function(pp, 'zx_pp_tables_init')
        teardown = function(pp, 'zx_pp_teardown')
        self.assertIn('zx_pp_offload_init(pp, dev)', init)
        self.assertIn('zx_pp_offload_fini(pp)', teardown)
        # fini runs after debugfs removal and before the engines are disabled.
        self.assertLess(teardown.index('debugfs_remove_recursive'),
                        teardown.index('zx_pp_offload_fini'))
        self.assertLess(teardown.index('zx_pp_offload_fini'),
                        teardown.index('zx_pp_disable(&pp->cla)'))
        self.assertEqual(len(re.findall(r'^#ifdef ' + SYMBOL + r'$', pp, re.M)), 2)

    def test_header_gates_the_offload_api(self):
        header = PP_HEADER.read_text()
        self.assertIn('#ifdef CONFIG_ZX279128_PP_OFFLOAD', header)
        for decl in ('void zx_pp_offload_init(', 'int zx_pp_offload_fini(',
                     'int zx_pp_offload_setup_tc(', 'void zx_pp_offload_port_down(',
                     'struct zx_pp_offload_dev_ops'):
            with self.subTest(decl=decl):
                self.assertIn(decl, header)


class PpOffloadEthHookupTests(unittest.TestCase):
    """The Ethernet-side wiring is delivered as a patch, not applied, because
    zx279128-eth.c is owned by the datapath-reset work. These tests pin that:
    the shipped eth.c is untouched (so the offload is inert), and the patch
    applies mechanically."""

    def test_shipped_eth_c_is_untouched_so_offload_is_inert(self):
        eth = ETH_SOURCE.read_text()
        # No setup_tc on the per-port ops, and no reference to the offload glue:
        # without the patch nothing ever calls into the offload, so it registers
        # nothing. This is the "inert but correct" property.
        self.assertNotIn('zx_pp_offload', eth)
        self.assertNotIn('.ndo_setup_tc', eth)

    def test_the_hookup_patch_exists_and_targets_eth_c(self):
        self.assertTrue(HOOKUP_PATCH.is_file())
        patch = HOOKUP_PATCH.read_text()
        self.assertIn('zx279128-eth.c', patch)
        self.assertIn('.ndo_setup_tc = zx_port_setup_tc', patch)
        self.assertIn('zx_pp_offload_setup_tc', patch)
        self.assertIn('zx_pp_offload_set_dev_ops', patch)
        self.assertIn('zx_pp_offload_port_down', patch)

    def test_the_hookup_patch_applies_mechanically(self):
        git = subprocess.run(['git', 'apply', '--check', '-p1', str(HOOKUP_PATCH)],
                             cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(git.returncode, 0,
                         'docs/offload/eth-hookup.patch no longer applies to '
                         'zx279128-eth.c; regenerate it:\n' + git.stderr)


if __name__ == '__main__':
    unittest.main()
