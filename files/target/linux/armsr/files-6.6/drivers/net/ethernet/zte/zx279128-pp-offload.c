// SPDX-License-Identifier: GPL-2.0
/*
 * ZX279128S packet-processor hardware flow offload (nf_flow_table glue).
 *
 * This is the production offload path: it turns netfilter flow-table entries
 * (conntrack flows that nf_flow_table has decided to offload) into CLA
 * exact-match + PM forwarding entries in the packet processor's DRAM tables.
 * It is the real consumer of the table-access layer (zx279128-pp.c) and the
 * shared entry builders (zx279128-pp-hash.c); it owns none of the bit
 * positions itself, by design -- the diagnostic flow path
 * (zx279128-pp-flow.c) and this path share exactly one copy of every table
 * layout, which is the whole point of the builders being factored out.
 *
 * Driven entirely by the standard TC_SETUP_FT / flow_block_cb machinery. A
 * flow is only accepted when BOTH ends are hardware switch ports and the
 * 5-tuple is something the decoded window encoding can express; everything
 * else is refused with -EOPNOTSUPP so it stays in the software datapath.
 *
 * Compiled only when CONFIG_ZX279128_PP_OFFLOAD is set, which depends on
 * CONFIG_ZX279128_PP_TABLES && NF_FLOW_TABLE. The NF_FLOW_TABLE dependency is
 * load-bearing, not cosmetic: zx279128_eth is a bool and nf_flow_table builds
 * as a module in this config, so without "depends on NF_FLOW_TABLE && the
 * config builds it in" the kernel link fails at the very end of the build
 * (docs/upstream/SERIES.md item 6). With the symbol off this file contributes
 * nothing and the Ethernet driver is byte for byte what it was.
 *
 * Boundary with zx279128-eth.c: this file never touches the Ethernet driver's
 * internals. The Ethernet driver reaches it through two small, explicit seams
 * delivered as a patch (docs/offload/eth-hookup.patch):
 *   - a .ndo_setup_tc wrapper that calls zx_pp_offload_setup_tc(); and
 *   - a dev_ops registration whose port_index() maps a net_device to a
 *     hardware switch-port index (or -1 for anything that is not one).
 * Until that patch is applied the offload is unreachable (nothing ever calls
 * setup_tc), but it still links and is inert -- which is the property the
 * glue must have while the hardware match is being brought up separately.
 */
#include <linux/errno.h>
#include <linux/if_ether.h>
#include <linux/ip.h>
#include <linux/jiffies.h>
#include <linux/list.h>
#include <linux/llist.h>
#include <linux/netdevice.h>
#include <linux/notifier.h>
#include <linux/rtnetlink.h>
#include <linux/slab.h>
#include <linux/spinlock.h>
#include <linux/string.h>
#include <linux/types.h>
#include <linux/workqueue.h>

#include <net/arp.h>
#include <net/flow_offload.h>
#include <net/neighbour.h>
#include <net/netevent.h>
#include <net/pkt_cls.h>

#include "zx279128-pp.h"

#ifdef CONFIG_ZX279128_PP_OFFLOAD

/* The scoping field for every IPv4 5-tuple fast flow: (extIdx << 4) | nibble.
 *
 * extIdx is a constant 9 (ZX_PP_EXTIDX_V4FAST), NOT the ingress port: on the
 * IPv4 fast path aclGetExtIdxRuleRamAddrByPort returns 9 for every port
 * (docs/PP-KEY.md section 8.1). The nibble is 0 -- the 5-tuple path, whose
 * ternary rule tm_acl_fast_init installs at extra_rule[0x90]/[0x91]; nibble 4
 * is the 3-tuple path (docs/PP-KEY.md section 8.2). So the field is a constant
 * 0x90 and is an index into the ternary extra_rule table, not a per-port or
 * per-direction discriminator.
 *
 * ORIGINAL and REPLY are therefore NOT separated by the field nibble. They are
 * separated by the tuple: nf_flow_table installs each direction as its own
 * flow_cls_offload with its own cookie and its own 5-tuple, which hashes to a
 * different CLA bucket. This path installs one entry per call and never
 * assumes the second call is a duplicate of the first (docs/PP-KEY.md section
 * 8 supersedes the earlier "per-direction via the nibble" reading).
 */
#define ZX_PP_OFFLOAD_FIELD	((ZX_PP_EXTIDX_V4FAST << 4) | ZX_PP_KEY_TYPE_V4_REPLY)

/* Table selectors (docs/PP-OFFLOAD.md "indirect accessors"), shared with the
 * diagnostic path. These are engine/table ports, not entry bit positions.
 */
#define ZX_PP_OFF_EXTRA_INDEX_SEL	0u
#define ZX_PP_OFF_EXTRA_RULE_SEL	1u
#define ZX_PP_OFF_EXTRA_INDEX_WORDS	5u
#define ZX_PP_OFF_EXTRA_INDEX_EN_WORD	4u
#define ZX_PP_OFF_EXTRA_INDEX_V4_BIT	(1u << 0)	/* tm_acl_fast_init's own enable */
#define ZX_PP_OFF_PM_SEL_FLOW_INFO	0u
#define ZX_PP_OFF_PM_SEL_NEXT_HOP	1u

/* Entry-pool ceilings, from the PM table geometry (docs/PP-OFFLOAD.md): PM
 * next_hop has 512 entries, PM flow_info 2048 (addr = dir << 10 | idx, so 1024
 * per direction). We place every flow's flow_info in direction 0 and let the
 * CLA bucket (which is per-tuple, already direction-distinct) carry the
 * separation. next_hop is the binding resource, so 512 concurrent offloaded
 * flows is the practical cap; the CLA hash has 520 slots, close enough that
 * exhausting either simply returns the flow to software.
 */
#define ZX_PP_OFF_NEXT_HOP_SLOTS	512u
#define ZX_PP_OFF_FLOW_INFO_SLOTS	1024u
#define ZX_PP_OFF_FLOW_INFO_DIR		0u

/* The hardware forwarding path is only qualified for standard frames. The CLA
 * oversize limit register read 0x47d0 (18384) on hardware (docs/PP-OFFLOAD.md
 * section 7), so the silicon can carry more, but jumbo forwarding through the
 * PM rewrite is not qualified. Refuse a flow whose egress MTU exceeds this
 * conservative ceiling rather than silently mis-forward an oversize frame.
 */
#define ZX_PP_OFFLOAD_MAX_MTU		1500u

/* One installed hardware flow. Keyed by the flow_cls_offload cookie, which is
 * the per-direction conntrack tuple pointer, so ORIGINAL and REPLY are two
 * distinct entries with two distinct cookies.
 */
struct zx_pp_offload_entry {
	struct list_head list;
	unsigned long cookie;	/* flow_cls_offload.cookie, the bookkeeping key */
	u16 bucket;		/* CLA hash address this entry sits at */
	u16 nh_idx;		/* PM next_hop slot */
	u16 fi_idx;		/* PM flow_info slot (direction 0) */
	u8 ingress;		/* hardware switch ingress port */
	u8 egress;		/* hardware switch egress port */
	u8 proto;
	u8 dmac[ETH_ALEN];	/* programmed next-hop DMAC; the neighbour key */
	unsigned long lastused;	/* jiffies of the last observed CLA hit */
};

/* A neighbour-invalidation note, queued lock-free from the (atomic) netevent
 * notifier and drained by the garbage-collect work.
 */
struct zx_pp_offload_neigh_note {
	struct llist_node node;
	u8 ha[ETH_ALEN];
};

struct zx_pp_offload {
	struct zx_pp *pp;
	struct device *dev;
	const struct zx_pp_offload_dev_ops *dev_ops;	/* set by the Ethernet driver */
	struct mutex lock;		/* serialises table ops, the list and the pools */
	struct list_head entries;
	struct zx_pp_hash_map map;	/* CLA slot occupancy for this PP block */
	bool nh_used[ZX_PP_OFF_NEXT_HOP_SLOTS];
	bool fi_used[ZX_PP_OFF_FLOW_INFO_SLOTS];
	bool rule_ready;		/* the ternary default rule is installed */

	/* Neighbour tracking: invalidate a stale DMAC before it is used. */
	struct notifier_block netevent_nb;
	struct llist_head neigh_notes;	/* lock-free queue from the notifier */
	struct work_struct gc_work;
};

/* One PP block on this SoC; one offload context, like the diagnostic path's
 * g_flow. zx279128-pp.c holds no field for it, so it lives here.
 */
static struct zx_pp_offload *g_offload;

/* The driver-wide flow_block_cb list, as the standard pattern requires. */
static LIST_HEAD(zx_pp_offload_block_cb_list);

/* ---- entry-pool allocators (plain free lists, not table layout) --------- */

static int zx_pp_off_alloc(bool *pool, unsigned int n)
{
	unsigned int i;

	for (i = 0; i < n; i++) {
		if (!pool[i]) {
			pool[i] = true;
			return (int)i;
		}
	}
	return -ENOSPC;
}

static void zx_pp_off_free(bool *pool, unsigned int n, u16 idx)
{
	if (idx < n)
		pool[idx] = false;
}

/* ---- the one-time ternary default rule --------------------------------- */

/* Install the vendor's IPv4 5-tuple ternary rule pair at extra_rule[0x90]/
 * [0x91] and set bit 0 of extra_index[9] word 4, exactly as tm_acl_fast_init
 * does. The exact-match hash is not a standalone lookup: the window's field is
 * an index into this ternary rule, and without the rule an entry refers to a
 * program that extracts nothing, so nothing matches (docs/PP-KEY.md section 8).
 * This runs once at init, not per flow. Uses the shared builder for the rule
 * bytes; this file supplies only the table selectors.
 */
static int zx_pp_offload_rule_init(struct zx_pp_offload *off)
{
	u32 rule[ZX_PP_EXTRA_RULE_WORDS];
	u32 entry[ZX_PP_OFF_EXTRA_INDEX_WORDS] = { 0 };
	const u32 idx = ZX_PP_EXTIDX_V4FAST * 16u + ZX_PP_KEY_TYPE_V4_REPLY;	/* 0x90 */
	int ret;

	zx_pp_build_extra_rule_v4(rule, false);
	ret = zx_pp_cla_write(off->pp, ZX_PP_OFF_EXTRA_RULE_SEL, idx, rule,
			      ZX_PP_EXTRA_RULE_WORDS);
	if (ret)
		return ret;
	zx_pp_build_extra_rule_v4(rule, true);
	ret = zx_pp_cla_write(off->pp, ZX_PP_OFF_EXTRA_RULE_SEL, idx + 1u, rule,
			      ZX_PP_EXTRA_RULE_WORDS);
	if (ret)
		return ret;

	ret = zx_pp_cla_read(off->pp, ZX_PP_OFF_EXTRA_INDEX_SEL, ZX_PP_EXTIDX_V4FAST,
			     entry, ZX_PP_OFF_EXTRA_INDEX_WORDS);
	if (ret)
		return ret;
	entry[ZX_PP_OFF_EXTRA_INDEX_EN_WORD] |= ZX_PP_OFF_EXTRA_INDEX_V4_BIT;
	ret = zx_pp_cla_write(off->pp, ZX_PP_OFF_EXTRA_INDEX_SEL, ZX_PP_EXTIDX_V4FAST,
			      entry, ZX_PP_OFF_EXTRA_INDEX_WORDS);
	if (ret)
		return ret;

	off->rule_ready = true;
	return 0;
}

/* ---- table write / clear for one entry --------------------------------- */

/* Caller holds off->lock. Zeroes the CLA window first (valid_en in the zeroed
 * window is 0, so the engine stops considering the entry) and only then the PM
 * entries it pointed at, mirroring the diagnostic path's clear order. Returns
 * the first failing error; on success the caller releases the pools/slot.
 */
static int zx_pp_offload_clear_entry(struct zx_pp_offload *off,
				     const struct zx_pp_offload_entry *e)
{
	u32 win[ZX_PP_HASH_WORDS] = { 0 };
	u32 nh[ZX_PP_NH_WORDS] = { 0 };
	u32 fi[ZX_PP_FLOW_INFO_WORDS] = { 0 };
	unsigned int sel;
	u16 bank_addr;
	int ret, first = 0;

	if (zx_pp_hash_bank(e->bucket, &sel, &bank_addr))
		return -EINVAL;

	ret = zx_pp_cla_write(off->pp, sel, bank_addr, win, ZX_PP_HASH_WORDS);
	first = first ? first : ret;
	ret = zx_pp_aging_write(off->pp, e->bucket, 0);
	first = first ? first : ret;
	ret = zx_pp_pm_write(off->pp, ZX_PP_OFF_PM_SEL_FLOW_INFO,
			     (ZX_PP_OFF_FLOW_INFO_DIR << 10) | e->fi_idx,
			     fi, ZX_PP_FLOW_INFO_WORDS);
	first = first ? first : ret;
	ret = zx_pp_pm_write(off->pp, ZX_PP_OFF_PM_SEL_NEXT_HOP, e->nh_idx,
			     nh, ZX_PP_NH_WORDS);
	first = first ? first : ret;
	return first;
}

/* Caller holds off->lock. Builds and writes one flow's tables in the proven
 * order: next_hop -> flow_info -> CLA window -> aging clear. Everything table-
 * shaped comes from the shared builders. On any write failure it clears
 * whatever was written and returns the error; the pools are the caller's to
 * release.
 */
static int zx_pp_offload_write_entry(struct zx_pp_offload *off,
				     struct zx_pp_offload_entry *e,
				     __be32 sip, __be16 sport,
				     __be32 dip, __be16 dport)
{
	u32 nh[ZX_PP_NH_WORDS], fi[ZX_PP_FLOW_INFO_WORDS], win[ZX_PP_HASH_WORDS];
	unsigned int sel;
	u16 bank_addr;
	int ret;

	ret = zx_pp_build_window_ipv4(win, e->ingress, e->egress, e->fi_idx,
				      ZX_PP_OFFLOAD_FIELD, e->proto,
				      (const u8 *)&sip, ntohs(sport),
				      (const u8 *)&dip, ntohs(dport));
	if (ret)
		return ret;
	if (zx_pp_hash_bank(e->bucket, &sel, &bank_addr))
		return -EINVAL;

	zx_pp_build_next_hop(e->dmac, (const u8 *)&dip, nh);
	zx_pp_build_flow_info(e->nh_idx, fi);

	ret = zx_pp_pm_write(off->pp, ZX_PP_OFF_PM_SEL_NEXT_HOP, e->nh_idx,
			     nh, ZX_PP_NH_WORDS);
	if (ret)
		goto clear;
	ret = zx_pp_pm_write(off->pp, ZX_PP_OFF_PM_SEL_FLOW_INFO,
			     (ZX_PP_OFF_FLOW_INFO_DIR << 10) | e->fi_idx,
			     fi, ZX_PP_FLOW_INFO_WORDS);
	if (ret)
		goto clear;
	ret = zx_pp_cla_write(off->pp, sel, bank_addr, win, ZX_PP_HASH_WORDS);
	if (ret)
		goto clear;
	ret = zx_pp_aging_write(off->pp, e->bucket, 0);
	if (ret)
		goto clear;
	return 0;

clear:
	zx_pp_offload_clear_entry(off, e);
	return ret;
}

/* ---- entry lifecycle ---------------------------------------------------- */

/* Caller holds off->lock. */
static struct zx_pp_offload_entry *zx_pp_offload_find(struct zx_pp_offload *off,
						      unsigned long cookie)
{
	struct zx_pp_offload_entry *e;

	list_for_each_entry(e, &off->entries, list)
		if (e->cookie == cookie)
			return e;
	return NULL;
}

/* Caller holds off->lock. Removes an entry from the tables and the list and
 * frees it. On a clear failure the entry is KEPT on the list and the error
 * returned: a half-cleared entry is still live in a table the engine walks, so
 * dropping our only handle would let teardown free a table underneath it
 * (docs/PP-OFFLOAD.md, "never return memory the engine may still reach").
 */
static int zx_pp_offload_destroy_entry(struct zx_pp_offload *off,
				       struct zx_pp_offload_entry *e)
{
	int ret = zx_pp_offload_clear_entry(off, e);

	if (ret) {
		dev_err(off->dev,
			"offload: could not clear flow at bucket %u (%d); kept\n",
			e->bucket, ret);
		return ret;
	}
	zx_pp_hash_release(&off->map, e->bucket);
	zx_pp_off_free(off->nh_used, ZX_PP_OFF_NEXT_HOP_SLOTS, e->nh_idx);
	zx_pp_off_free(off->fi_used, ZX_PP_OFF_FLOW_INFO_SLOTS, e->fi_idx);
	list_del(&e->list);
	kfree(e);
	return 0;
}

/* ---- the flow_rule decode ---------------------------------------------- */

/* Decode a FLOW_ACTION_MANGLE of an Ethernet header into dst/src, the same way
 * mtk_ppe_offload.c does. nf_flow_table's L2-rewrite emits these for the
 * neighbour next-hop MAC; they are the action format, not a zx table layout,
 * so they are decoded here rather than through the shared builders.
 */
static void zx_pp_offload_mangle_eth(const struct flow_action_entry *act,
				     struct ethhdr *eth)
{
	void *dest = (void *)eth + act->mangle.offset;
	const void *src = &act->mangle.val;

	if (act->mangle.offset > 8)
		return;
	if (act->mangle.mask == 0xffff) {
		src += 2;
		dest += 2;
	}
	memcpy(dest, src, act->mangle.mask ? 2 : 4);
}

struct zx_pp_offload_match {
	__be32 sip, dip;
	__be16 sport, dport;
	u8 proto;
	struct ethhdr eth;	/* h_dest = next-hop MAC, filled by the mangles */
	struct net_device *odev;	/* egress, from the redirect */
	unsigned int redirects;
};

/* Pull the IPv4 5-tuple and the egress next-hop out of a flow_cls_offload, and
 * refuse -- explicitly, with a reason -- anything the hardware window cannot
 * express. Returns 0 on an acceptable flow, a negative errno otherwise.
 */
static int zx_pp_offload_parse(struct zx_pp_offload *off,
			       struct flow_cls_offload *cls,
			       struct zx_pp_offload_match *m)
{
	struct flow_rule *rule = flow_cls_offload_flow_rule(cls);
	struct flow_dissector *d = rule->match.dissector;
	struct flow_action_entry *act;
	int i;

	memset(m, 0, sizeof(*m));

	/* CONTROL: addr type + fragment flag. A non-first fragment carries no
	 * L4 ports, so an entry built from a fragment's ports cannot describe
	 * it; refuse fragments outright.
	 */
	if (flow_rule_match_key(rule, FLOW_DISSECTOR_KEY_CONTROL)) {
		struct flow_match_control match;

		flow_rule_match_control(rule, &match);
		if (match.key->addr_type != FLOW_DISSECTOR_KEY_IPV4_ADDRS) {
			/* IPv6 has no decoded window encoding (different ternary
			 * rule, different winoffsets); VLAN/PPPoE/tunnels take
			 * other window branches that are undecoded.
			 */
			return -EOPNOTSUPP;
		}
		if (match.key->flags & FLOW_DIS_IS_FRAGMENT)
			return -EOPNOTSUPP;
	} else {
		return -EOPNOTSUPP;
	}

	/* Reject VLAN / CVLAN / PPPoE matches outright: those are different
	 * window branches (docs/PP-KEY.md section 4) and are not decoded.
	 */
	if (dissector_uses_key(d, FLOW_DISSECTOR_KEY_VLAN) ||
	    dissector_uses_key(d, FLOW_DISSECTOR_KEY_CVLAN))
		return -EOPNOTSUPP;

	/* BASIC: protocol. Only TCP and UDP map onto the 5-tuple fast rule. */
	if (flow_rule_match_key(rule, FLOW_DISSECTOR_KEY_BASIC)) {
		struct flow_match_basic match;

		flow_rule_match_basic(rule, &match);
		m->proto = match.key->ip_proto;
		if (m->proto != IPPROTO_TCP && m->proto != IPPROTO_UDP)
			return -EOPNOTSUPP;
	} else {
		return -EOPNOTSUPP;
	}

	if (flow_rule_match_key(rule, FLOW_DISSECTOR_KEY_IPV4_ADDRS)) {
		struct flow_match_ipv4_addrs match;

		flow_rule_match_ipv4_addrs(rule, &match);
		m->sip = match.key->src;
		m->dip = match.key->dst;
	} else {
		return -EOPNOTSUPP;
	}

	if (flow_rule_match_key(rule, FLOW_DISSECTOR_KEY_PORTS)) {
		struct flow_match_ports match;

		flow_rule_match_ports(rule, &match);
		m->sport = match.key->src;
		m->dport = match.key->dst;
	} else {
		return -EOPNOTSUPP;
	}

	/* Actions: consume the L2-rewrite mangles and the single redirect;
	 * refuse NAT (IP/port mangle -> cmd_ram packet offsets are undecoded),
	 * VLAN/PPPoE push/pop, tunnels, and more than one redirect.
	 */
	flow_action_for_each(i, act, &rule->action) {
		switch (act->id) {
		case FLOW_ACTION_MANGLE:
			if (act->mangle.htype == FLOW_ACT_MANGLE_HDR_TYPE_ETH) {
				zx_pp_offload_mangle_eth(act, &m->eth);
				break;
			}
			/* IP4/IP6/TCP/UDP header rewrite is SNAT/DNAT, which
			 * routes through cmd_ram packet offsets that are not
			 * decoded (docs/PP-FLOW.md). Refuse rather than guess.
			 */
			return -EOPNOTSUPP;
		case FLOW_ACTION_REDIRECT:
			if (m->redirects++)
				return -EOPNOTSUPP;	/* more than one egress */
			m->odev = act->dev;
			break;
		case FLOW_ACTION_CSUM:
			break;			/* hardware recomputes checksums */
		case FLOW_ACTION_VLAN_PUSH:
		case FLOW_ACTION_VLAN_POP:
		case FLOW_ACTION_PPPOE_PUSH:
		case FLOW_ACTION_TUNNEL_ENCAP:
		case FLOW_ACTION_TUNNEL_DECAP:
			return -EOPNOTSUPP;	/* undecoded window branches */
		default:
			return -EOPNOTSUPP;
		}
	}

	if (m->redirects != 1 || !m->odev)
		return -EOPNOTSUPP;		/* need exactly one hw egress */
	if (!is_valid_ether_addr(m->eth.h_dest))
		return -EOPNOTSUPP;		/* no usable next-hop MAC */
	return 0;
}

/* ---- the per-flow commands --------------------------------------------- */

/* Caller holds off->lock. */
static int zx_pp_offload_replace(struct zx_pp_offload *off,
				 struct net_device *idev,
				 struct flow_cls_offload *cls)
{
	struct zx_pp_offload_match m;
	struct zx_pp_offload_entry *e;
	struct zx_pp_hash_cfg cfg;
	u8 key[ZX_PP_KEY_LEN];
	u32 win[ZX_PP_HASH_WORDS];
	u16 bucket;
	int ingress, egress, nh, fi, ret;

	if (!off->dev_ops || !off->dev_ops->port_index)
		return -EOPNOTSUPP;	/* the Ethernet seam is not wired yet */
	if (!off->rule_ready)
		return -EOPNOTSUPP;	/* the ternary default rule is missing */
	if (zx_pp_offload_find(off, cls->cookie))
		return -EEXIST;		/* this (cookie,direction) is already ours */

	ret = zx_pp_offload_parse(off, cls, &m);
	if (ret)
		return ret;

	/* Both ends must be hardware switch ports; that port scoping is what
	 * keeps zones apart. WiFi, tunnels and software-only interfaces have no
	 * port index and are returned to netfilter.
	 */
	ingress = off->dev_ops->port_index(idev);
	egress = off->dev_ops->port_index(m.odev);
	if (ingress < 0 || egress < 0)
		return -EOPNOTSUPP;

	/* Refuse a flow whose egress MTU the hardware forwarding path cannot
	 * honour (jumbo is not qualified; see ZX_PP_OFFLOAD_MAX_MTU).
	 */
	if (m.odev->mtu > ZX_PP_OFFLOAD_MAX_MTU)
		return -EOPNOTSUPP;

	ret = zx_pp_hash_config(off->pp, &cfg);
	if (ret)
		return ret;
	if (!cfg.usable)
		return -EOPNOTSUPP;	/* outer hash table configured, undecoded */

	nh = zx_pp_off_alloc(off->nh_used, ZX_PP_OFF_NEXT_HOP_SLOTS);
	if (nh < 0)
		return nh;
	fi = zx_pp_off_alloc(off->fi_used, ZX_PP_OFF_FLOW_INFO_SLOTS);
	if (fi < 0) {
		zx_pp_off_free(off->nh_used, ZX_PP_OFF_NEXT_HOP_SLOTS, (u16)nh);
		return fi;
	}

	/* Build the window from the allocated flow_info index, derive the key,
	 * and place it at the bucket a live packet will hash to. */
	ret = zx_pp_build_window_ipv4(win, (u8)ingress, (u8)egress, (u32)fi,
				      ZX_PP_OFFLOAD_FIELD, m.proto,
				      (const u8 *)&m.sip, ntohs(m.sport),
				      (const u8 *)&m.dip, ntohs(m.dport));
	if (ret)
		goto free_pools;
	zx_pp_build_key((const u8 *)win, ZX_PP_OFFLOAD_FIELD, key);
	ret = zx_pp_hash_place(&cfg, &off->map, key, &bucket);
	if (ret)
		goto free_pools;

	e = kzalloc(sizeof(*e), GFP_KERNEL);
	if (!e) {
		ret = -ENOMEM;
		goto release_slot;
	}
	e->cookie = cls->cookie;
	e->bucket = bucket;
	e->nh_idx = (u16)nh;
	e->fi_idx = (u16)fi;
	e->ingress = (u8)ingress;
	e->egress = (u8)egress;
	e->proto = m.proto;
	ether_addr_copy(e->dmac, m.eth.h_dest);
	e->lastused = jiffies;

	ret = zx_pp_offload_write_entry(off, e, m.sip, m.sport, m.dip, m.dport);
	if (ret) {
		kfree(e);
		goto release_slot;
	}
	list_add_tail(&e->list, &off->entries);
	dev_dbg(off->dev,
		"offload: in%d out%d proto%u %pI4:%u -> %pI4:%u dmac %pM bucket %u nh %d fi %d\n",
		ingress, egress, m.proto, &m.sip, ntohs(m.sport), &m.dip,
		ntohs(m.dport), e->dmac, bucket, nh, fi);
	return 0;

release_slot:
	zx_pp_hash_release(&off->map, bucket);
free_pools:
	zx_pp_off_free(off->nh_used, ZX_PP_OFF_NEXT_HOP_SLOTS, (u16)nh);
	zx_pp_off_free(off->fi_used, ZX_PP_OFF_FLOW_INFO_SLOTS, (u16)fi);
	return ret;
}

/* Caller holds off->lock. */
static int zx_pp_offload_destroy(struct zx_pp_offload *off,
				 struct flow_cls_offload *cls)
{
	struct zx_pp_offload_entry *e = zx_pp_offload_find(off, cls->cookie);

	if (!e)
		return -ENOENT;
	return zx_pp_offload_destroy_entry(off, e);
}

/* Caller holds off->lock. Per-flow liveness only.
 *
 * The CLA aging hit bit is the one per-flow signal we have: it is set when an
 * exact-match entry matches, and is read-to-clear. We report `used` (lastused)
 * from it so an active flow stays offloaded and an idle one eventually times
 * out. We deliberately report ZERO packets and bytes: ADM's packet counter is
 * indexed per-WAN, not per-flow (docs/PP-OFFLOAD.md, zx279128-pp.h), so a
 * per-flow packet count would be a fabricated number. Zero is the honest value.
 */
static int zx_pp_offload_stats(struct zx_pp_offload *off,
			       struct flow_cls_offload *cls)
{
	struct zx_pp_offload_entry *e = zx_pp_offload_find(off, cls->cookie);
	u32 hit = 0;
	int ret;

	if (!e)
		return -ENOENT;
	ret = zx_pp_aging_read(off->pp, e->bucket, &hit);
	if (ret)
		return ret;
	if (hit & 1u) {
		e->lastused = jiffies;
		/* read-to-clear, like the vendor's tm_get_acl_flow_status, so
		 * the next poll reports a fresh hit rather than a stale one.
		 */
		zx_pp_aging_write(off->pp, e->bucket, 0);
	}
	flow_stats_update(&cls->stats, 0, 0, 0, e->lastused,
			  FLOW_ACTION_HW_STATS_IMMEDIATE);
	return 0;
}

static int zx_pp_offload_cmd(struct net_device *idev,
			     struct flow_cls_offload *cls)
{
	struct zx_pp_offload *off = g_offload;
	int ret;

	if (!off)
		return -EOPNOTSUPP;

	mutex_lock(&off->lock);
	switch (cls->command) {
	case FLOW_CLS_REPLACE:
		ret = zx_pp_offload_replace(off, idev, cls);
		break;
	case FLOW_CLS_DESTROY:
		ret = zx_pp_offload_destroy(off, cls);
		break;
	case FLOW_CLS_STATS:
		ret = zx_pp_offload_stats(off, cls);
		break;
	default:
		ret = -EOPNOTSUPP;
		break;
	}
	mutex_unlock(&off->lock);
	return ret;
}

/* ---- the flow_block plumbing (standard pattern) ------------------------ */

static int zx_pp_offload_block_cb(enum tc_setup_type type, void *type_data,
				  void *cb_priv)
{
	struct net_device *dev = cb_priv;	/* the ingress netdev */

	if (!tc_can_offload(dev))
		return -EOPNOTSUPP;
	if (type != TC_SETUP_CLSFLOWER)
		return -EOPNOTSUPP;
	return zx_pp_offload_cmd(dev, type_data);
}

static int zx_pp_offload_setup_block(struct net_device *dev,
				     struct flow_block_offload *f)
{
	struct flow_block_cb *block_cb;
	flow_setup_cb_t *cb = zx_pp_offload_block_cb;

	/* Ingress hook only. The key is scoped to the ingress port, so an
	 * egress or shared binding would break that scoping.
	 */
	if (f->binder_type != FLOW_BLOCK_BINDER_TYPE_CLSACT_INGRESS)
		return -EOPNOTSUPP;

	f->driver_block_list = &zx_pp_offload_block_cb_list;

	switch (f->command) {
	case FLOW_BLOCK_BIND:
		block_cb = flow_block_cb_lookup(f->block, cb, dev);
		if (block_cb) {
			flow_block_cb_incref(block_cb);
			return 0;
		}
		block_cb = flow_block_cb_alloc(cb, dev, dev, NULL);
		if (IS_ERR(block_cb))
			return PTR_ERR(block_cb);
		flow_block_cb_incref(block_cb);
		flow_block_cb_add(block_cb, f);
		list_add_tail(&block_cb->driver_list, &zx_pp_offload_block_cb_list);
		return 0;
	case FLOW_BLOCK_UNBIND:
		block_cb = flow_block_cb_lookup(f->block, cb, dev);
		if (!block_cb)
			return -ENOENT;
		if (!flow_block_cb_decref(block_cb)) {
			flow_block_cb_remove(block_cb, f);
			list_del(&block_cb->driver_list);
		}
		return 0;
	default:
		return -EOPNOTSUPP;
	}
}

int zx_pp_offload_setup_tc(struct zx_pp *pp, struct net_device *dev,
			   enum tc_setup_type type, void *type_data)
{
	/* Inert until the table layer is live. Returning -EOPNOTSUPP keeps the
	 * flow in the software datapath rather than failing the qdisc setup.
	 */
	if (!pp || !g_offload || g_offload->pp != pp)
		return -EOPNOTSUPP;

	switch (type) {
	case TC_SETUP_BLOCK:
	case TC_SETUP_FT:
		return zx_pp_offload_setup_block(dev, type_data);
	default:
		return -EOPNOTSUPP;
	}
}

/* ---- the neighbour notifier -------------------------------------------- */

/* Caller holds off->lock. Delete every entry whose programmed next-hop DMAC is
 * `ha`. Called from the GC work after a neighbour went invalid, so a stale
 * DMAC is never left in a live entry.
 */
static void zx_pp_offload_drop_dmac(struct zx_pp_offload *off, const u8 *ha)
{
	struct zx_pp_offload_entry *e, *n;

	list_for_each_entry_safe(e, n, &off->entries, list) {
		if (ether_addr_equal(e->dmac, ha))
			zx_pp_offload_destroy_entry(off, e);
	}
}

static void zx_pp_offload_gc_work(struct work_struct *w)
{
	struct zx_pp_offload *off = container_of(w, struct zx_pp_offload, gc_work);
	struct zx_pp_offload_neigh_note *note, *tmp;
	struct llist_node *batch;

	batch = llist_del_all(&off->neigh_notes);
	if (!batch)
		return;
	mutex_lock(&off->lock);
	llist_for_each_entry_safe(note, tmp, batch, node) {
		zx_pp_offload_drop_dmac(off, note->ha);
		kfree(note);
	}
	mutex_unlock(&off->lock);
}

/* The netevent chain is an ATOMIC notifier, so this runs in atomic context and
 * must not sleep -- and clearing a table takes a mutex and busy-waits on the
 * engine. So the notifier only snapshots the stale MAC (lock-free) and defers
 * the table work to zx_pp_offload_gc_work. IPv4/ARP only; still-valid updates
 * are ignored.
 */
static int zx_pp_offload_netevent(struct notifier_block *nb, unsigned long event,
				  void *ptr)
{
	struct zx_pp_offload *off = container_of(nb, struct zx_pp_offload,
						 netevent_nb);
	struct zx_pp_offload_neigh_note *note;
	struct neighbour *n = ptr;

	if (event != NETEVENT_NEIGH_UPDATE)
		return NOTIFY_DONE;
	if (n->tbl != &arp_tbl)
		return NOTIFY_DONE;
	if (READ_ONCE(n->nud_state) & NUD_VALID)
		return NOTIFY_DONE;	/* still usable, nothing to invalidate */

	note = kmalloc(sizeof(*note), GFP_ATOMIC);
	if (!note)
		return NOTIFY_DONE;	/* the flow will also time out via stats */
	neigh_ha_snapshot((char *)note->ha, n, n->dev);
	llist_add(&note->node, &off->neigh_notes);
	schedule_work(&off->gc_work);
	return NOTIFY_DONE;
}

/* ---- init / teardown / port down --------------------------------------- */

void zx_pp_offload_set_dev_ops(struct zx_pp *pp,
			       const struct zx_pp_offload_dev_ops *ops)
{
	if (g_offload && g_offload->pp == pp)
		g_offload->dev_ops = ops;
}

void zx_pp_offload_init(struct zx_pp *pp, struct device *dev)
{
	struct zx_pp_offload *off;
	int ret;

	off = devm_kzalloc(dev, sizeof(*off), GFP_KERNEL);
	if (!off)
		return;
	off->pp = pp;
	off->dev = dev;
	mutex_init(&off->lock);
	INIT_LIST_HEAD(&off->entries);
	init_llist_head(&off->neigh_notes);
	INIT_WORK(&off->gc_work, zx_pp_offload_gc_work);

	/* The ternary default rule is the context every exact-match entry
	 * refers to; install it once, here, not per flow. A failure leaves the
	 * offload inert (replace refuses) rather than installing entries that
	 * can never match.
	 */
	ret = zx_pp_offload_rule_init(off);
	if (ret) {
		dev_warn(dev, "offload: ternary rule init failed (%d); offload disabled\n",
			 ret);
		return;
	}

	off->netevent_nb.notifier_call = zx_pp_offload_netevent;
	if (register_netevent_notifier(&off->netevent_nb)) {
		dev_warn(dev, "offload: netevent notifier registration failed; offload disabled\n");
		return;
	}

	g_offload = off;
	dev_info(dev, "offload: ready (nf_flow_table TC_SETUP_FT)\n");
}

/* Flush every installed entry. Caller holds off->lock. Returns the first clear
 * failure, leaving any entry that could not be cleared on the list so the
 * caller keeps the tables rather than freeing a region the engine still walks.
 */
static int zx_pp_offload_flush_locked(struct zx_pp_offload *off)
{
	struct zx_pp_offload_entry *e, *n;
	int first = 0;

	list_for_each_entry_safe(e, n, &off->entries, list) {
		int ret = zx_pp_offload_destroy_entry(off, e);

		if (ret && !first)
			first = ret;
	}
	return first;
}

/* Called from the PP teardown, after debugfs is gone and before the engines
 * are disabled and the tables freed. Unregisters the notifier (so no new GC
 * work is queued), drains the GC work, then flushes every entry. Returns 0
 * when nothing is installed afterwards; non-zero means a clear failed and the
 * tables must not be freed.
 */
int zx_pp_offload_fini(struct zx_pp *pp)
{
	struct zx_pp_offload *off = g_offload;
	struct zx_pp_offload_neigh_note *note, *tmp;
	struct llist_node *batch;
	int ret;

	if (!off || off->pp != pp)
		return 0;

	unregister_netevent_notifier(&off->netevent_nb);
	cancel_work_sync(&off->gc_work);
	/* Drop any notes the notifier queued after the cancel saw the work
	 * idle; their entries are flushed below regardless.
	 */
	batch = llist_del_all(&off->neigh_notes);
	llist_for_each_entry_safe(note, tmp, batch, node)
		kfree(note);

	mutex_lock(&off->lock);
	ret = zx_pp_offload_flush_locked(off);
	mutex_unlock(&off->lock);

	/* Keep the handle if a clear failed: it is the only record that an
	 * entry may still be live, and the tables are being kept anyway.
	 */
	if (!ret)
		g_offload = NULL;
	return ret;
}

/* Flush entries that ingress or egress on a port that is going down. Idempotent
 * and safe for a port that never offloaded anything (the list is simply walked)
 * and safe when called twice (the second pass finds the entries already gone).
 * Safe with no offload context at all (NULL pp or offload) -- port-stop paths
 * run in awkward orders during shutdown.
 */
void zx_pp_offload_port_down(struct zx_pp *pp, const struct net_device *dev)
{
	struct zx_pp_offload *off = g_offload;
	struct zx_pp_offload_entry *e, *n;
	int port;

	if (!off || off->pp != pp || !off->dev_ops || !off->dev_ops->port_index)
		return;
	port = off->dev_ops->port_index(dev);
	if (port < 0)
		return;

	mutex_lock(&off->lock);
	list_for_each_entry_safe(e, n, &off->entries, list) {
		if (e->ingress == port || e->egress == port)
			zx_pp_offload_destroy_entry(off, e);
	}
	mutex_unlock(&off->lock);
}

#endif /* CONFIG_ZX279128_PP_OFFLOAD */
