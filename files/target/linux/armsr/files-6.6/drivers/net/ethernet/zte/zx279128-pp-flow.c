// SPDX-License-Identifier: GPL-2.0
/*
 * ZX279128S packet-processor flow-install test path (strictly gated).
 *
 * Builds on the hardware-qualified PP table-access layer (zx279128-pp.c) to
 * install EXACTLY ONE explicitly-specified IPv4 forwarding flow into the CLA
 * (classifier) and PM (packet-modify) DRAM tables, and to read its CLA hit
 * bit. It is a bring-up probe for the write path, not flow offload: there is
 * no conntrack integration, no automatic placement, and at most one flow.
 *
 * Everything here is compiled only when CONFIG_ZX279128_PP_FLOW_TEST is set,
 * which depends on the diagnostic-only CONFIG_ZX279128_PP_TABLES. With the
 * symbol off this file contributes nothing and the Ethernet driver is byte
 * for byte what it was. See docs/PP-FLOW.md for the decoded vendor evidence
 * (proven / likely / unknown) that every field below rests on, and
 * docs/PP-OFFLOAD.md for the bounded hardware qualification steps.
 *
 * Refusals are deliberate. Anything that would rest on a field the spec marks
 * "unknown" (header rewrite through cmd_ram packet offsets, IPv6, DNAT, VLAN,
 * custom source MAC) returns -EOPNOTSUPP rather than writing a guess into a
 * table the live datapath engine walks.
 */
#include <linux/debugfs.h>
#include <linux/device.h>
#include <linux/errno.h>
#include <linux/inet.h>
#include <linux/kernel.h>
#include <linux/moduleparam.h>
#include <linux/mutex.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/uaccess.h>

#include "zx279128-pp.h"

#ifdef CONFIG_ZX279128_PP_FLOW_TEST

/* Must be set to 1 before any install/delete is accepted. Default 0: a stray
 * write to the debugfs control file does nothing on its own.
 */
static int flow_test_enable;
module_param(flow_test_enable, int, 0644);
MODULE_PARM_DESC(flow_test_enable,
		 "ZX279128S PP flow test: set to 1 to arm the write path (default 0)");

#define ZX_PP_FLOW_DIR_DEFAULT	0	/* flow_info direction default; runtime-settable via flow_dir */

/* The PM flow_info direction the next install writes: 0 = up (UNI->uplink),
 * 1 = dn (uplink->UNI). pp_pm_set_flow_info (tm.ko) takes a dir param
 * ("up[0],dwn[1]") and the flow_info RAM address is (dir << 10) | idx, so a
 * downstream frame fetches its flow_info from dir 1. A WAN(eth3)->LAN(eth0)
 * routed frame is downstream (PP-KEY §21: it lands on the dn trap counter
 * 0x9238c3d0, not the up bank), so its flow_info must be installed at dir 1 or
 * the exact-match's action has nowhere to point. Runtime-settable (0644) so one
 * boot can A/B dir 0 vs dir 1 with no other variable changing: write it, then
 * re-install the flow ("addh"/"add") and re-inject. Default 0 preserves the
 * historical install so prior evidence reproduces unchanged.
 */
static int flow_dir = ZX_PP_FLOW_DIR_DEFAULT;
module_param(flow_dir, int, 0644);
MODULE_PARM_DESC(flow_dir,
		 "ZX279128S PP flow_info install direction: 0=up, 1=dn (default 0)");

/* Reserved table entries. Chosen at the top of each table because the vendor
 * allocator fills from the bottom (idx 0 up), so these are the last the stock
 * firmware would ever touch. The CLA entry sits in cla_hash4 (sel 6), the
 * 8-deep top bank, at bank address 7 -> global hash address 519, the final
 * exact-match slot. A real packet reaches a slot only through the CLA hash
 * (docs/PP-FLOW.md "Placement"); nothing hashes here by construction, so an
 * installed flow with a non-routable 5-tuple can never match live traffic.
 */
#define ZX_PP_FLOW_NH_IDX	511u	/* PM next_hop,  idx < 512  */
#define ZX_PP_FLOW_INFO_IDX	1023u	/* PM flow_info, idx < 1024 */

/* The PM flow_info RAM address for the current install direction: dir occupies
 * bit 10, idx is the low 10 bits. flow_dir is clamped to {0,1} here so a stray
 * sysfs write cannot corrupt the address. Used for every flow_info write AND
 * its matching clear, so an install at dir 1 is cleared at dir 1.
 */
static inline u16 zx_pp_flow_info_addr(void)
{
	return (u16)(((flow_dir ? 1u : 0u) << 10) | ZX_PP_FLOW_INFO_IDX);
}

#define ZX_PP_FLOW_HASH_SEL	6u	/* cla_hash4 bank */
#define ZX_PP_FLOW_HASH_ADDR	7u	/* bank address; global hash address 519 */
#define ZX_PP_FLOW_AGING_ADDR	519u	/* CLA aging/hit table index = global hash address */

#define ZX_PP_CLA_SEL_HASH4	6u
/* The aging table is reached through zx_pp_aging_read()/zx_pp_aging_write(),
 * which own its depth bound (ZX_PP_CLA_AGING_DEPTH in zx279128-pp.h).
 */
#define ZX_PP_PM_SEL_FLOW_INFO	0u
#define ZX_PP_PM_SEL_NEXT_HOP	1u

/* ZX_PP_HASH_WORDS, ZX_PP_NH_WORDS and ZX_PP_FLOW_INFO_WORDS come from
 * zx279128-pp.h now, next to the builders that use them.
 */

#define ZX_PP_FLOW_MAX_PORT	15u	/* switch-port id ceiling for this driver */

/* A fully-specified flow. Addresses and ports are big-endian on the wire. */
struct zx_pp_flow_spec {
	u8 ingress;		/* ingress switch port */
	u8 egress;		/* egress switch port */
	u8 proto;		/* IPPROTO_TCP (6) or IPPROTO_UDP (17) */
	__be32 src_ip;
	__be32 dst_ip;
	__be16 src_port;
	__be16 dst_port;
	__be32 new_src_ip;	/* SNAT target; must equal src_ip for now */
	__be16 new_src_port;	/* SNAT target; must equal src_port for now */
	u8 dst_mac[ETH_ALEN];	/* next-hop destination MAC */
	u8 src_mac[ETH_ALEN];	/* intended source MAC (advisory, see below) */
};

struct zx_pp_flow {
	struct zx_pp *pp;
	struct device *dev;
	struct mutex lock;	/* serialises the control file and teardown */
	struct dentry *file;
	bool installed;
	bool hashed;		/* installed at a computed bucket, not slot 519 */
	u32 id;			/* monotonic install id, for del/stat */
	u16 bucket;		/* global hash address this flow sits at */
	u16 info_addr;		/* flow_info RAM address used at install (dir<<10|idx),
				 * so the clear targets the same direction even if
				 * flow_dir was changed meanwhile */
	struct zx_pp_hash_map map;	/* which slots this driver owns */
	struct zx_pp_flow_spec spec;
};

/* One PP block on this SoC; one flow context. */
static struct zx_pp_flow *g_flow;

/* ---- CLA hash window (sel 2..6, 60 bytes / 15 words) --------------------
 * Action-field bit positions are the inverse of the cla_set_hash_table
 * (tm.ko 0x5a14) debug decoder (docs/PP-FLOW.md "CLA window"):
 *   valid_en   b16.6 (proven)   rule_mode b16.4 (proven)
 *   cmd_flow_id b3[7:1]+b4[2:0] (proven)   modify_en b5.6 (proven)
 *   inport  b12[7:5]+b13[1:0] (likely)     outport b14[5:0] (likely)
 *
 * The match words at bytes 17..56 are the vendor encoding now decoded in
 * docs/PP-KEY.md section 4. Two paths build them:
 *
 *   - `add` writes a DRIVER-DEFINED tuple at bytes 20..33. That entry can
 *     never match a packet; it exists as the never-matching control the first
 *     hardware write test needed.
 *   - `addh` writes the real encoding via zx_pp_build_window_v4(), computes
 *     the key and the bucket, and installs at the bucket a live packet will
 *     hash to.
 */
#define ZX_PP_WIN_KEY_OFF	20u	/* driver-defined region, `add` only */

/* The never-matching control: driver-defined tuple, for readback only. */
static void zx_pp_build_window(const struct zx_pp_flow_spec *s, u32 flow_id, u32 *w)
{
	u8 b[ZX_PP_HASH_WORDS * 4] = { 0 };
	const u8 *sip = (const u8 *)&s->src_ip;
	const u8 *dip = (const u8 *)&s->dst_ip;
	const u8 *sp = (const u8 *)&s->src_port;
	const u8 *dp = (const u8 *)&s->dst_port;

	zx_pp_fill_action(s->ingress, s->egress, flow_id,
			  (u8)((s->ingress << 4) | ZX_PP_KEY_TYPE_V4_ORIG), b);

	/* Match key (driver-defined region, for readback only). */
	b[ZX_PP_WIN_KEY_OFF + 0] = s->proto;
	b[ZX_PP_WIN_KEY_OFF + 1] = s->ingress;
	b[ZX_PP_WIN_KEY_OFF + 2] = sip[0]; b[ZX_PP_WIN_KEY_OFF + 3] = sip[1];
	b[ZX_PP_WIN_KEY_OFF + 4] = sip[2]; b[ZX_PP_WIN_KEY_OFF + 5] = sip[3];
	b[ZX_PP_WIN_KEY_OFF + 6] = dip[0]; b[ZX_PP_WIN_KEY_OFF + 7] = dip[1];
	b[ZX_PP_WIN_KEY_OFF + 8] = dip[2]; b[ZX_PP_WIN_KEY_OFF + 9] = dip[3];
	b[ZX_PP_WIN_KEY_OFF + 10] = sp[0]; b[ZX_PP_WIN_KEY_OFF + 11] = sp[1];
	b[ZX_PP_WIN_KEY_OFF + 12] = dp[0]; b[ZX_PP_WIN_KEY_OFF + 13] = dp[1];

	zx_pp_pack_words(b, w, ZX_PP_HASH_WORDS);
}

/* The scoping field: (extIdx << 4) | type nibble.
 *
 * extIdx is NOT the ingress port. aclGetExtIdxRuleRamAddrByPort (Ghidra
 * 0x5841c) returns a constant 9 for every port while g_ipv4FastEn is set, and
 * tm_acl_fast_add_v4v6 sets that flag right before calling it for rule type 3
 * (TCP/UDP). The nibble for the 5-tuple IPv4 path is 0, not 4: the vendor
 * takes the `(uStack_b8 & 0xf) << 4` branch there, and nibble 4 belongs to
 * the 3-tuple path (it is the one guarded by g_v4OutUsed_3t).
 *
 * So the field is 0x90, which is exactly the extra_rule index
 * tm_acl_fast_init writes its IPv4 5-tuple ternary rule at.
 *
 * `ext_idx` and `nibble` stay overridable from debugfs so the hardware can
 * decide rather than this comment: the `field` verb sets them.
 */
static u8 zx_pp_ext_idx = ZX_PP_EXTIDX_V4FAST;
static u8 zx_pp_type_nibble = ZX_PP_KEY_TYPE_V4_REPLY;	/* 0: the 5-tuple path */

static u8 zx_pp_field(void)
{
	return (u8)((zx_pp_ext_idx << 4) | (zx_pp_type_nibble & 0xf));
}

/* The real encoding: action fields plus the decoded IPv4 match words. */
static int zx_pp_window_v4(const struct zx_pp_flow_spec *s, u32 flow_id, u32 *w)
{
	return zx_pp_build_window_ipv4(w, s->ingress, s->egress,
				       flow_id, zx_pp_field(), s->proto,
				       (const u8 *)&s->src_ip,
				       ntohs(s->src_port),
				       (const u8 *)&s->dst_ip,
				       ntohs(s->dst_port));
}

/* ---- install / delete / stat -------------------------------------------- */


/* Caller holds f->lock. Writes the proven tables in a fixed order:
 *   next_hop -> flow_info -> CLA window -> aging clear.
 * Any failure unwinds by deleting whatever was written.
 */

/* ---- the per-port enable ------------------------------------------------
 * Installing a hash entry is not enough: the engine only consults the
 * exact-match table for a port that the extra-index table says is enabled.
 * The vendor does this in EN_V4FAST_EXTIDXTBL (tm.ko Ghidra 0x57738), called
 * from tm_acl_fast_add_v4v6 right after a successful placement, and it
 * read-modify-writes one 16-bit word of the port's 20-byte extra-index entry:
 *
 *   direction 0: bits 5:4   mask 0xffcf, value 0x30 to enable
 *   direction 1: bits 1:0   mask 0xfffc, value 0x03 to enable
 *
 * The word is the entry's word 4, the one cla_set_extra_index_table's own
 * debug decoder reads back as *(u16 *)(entry + 0x10).
 *
 * Without this the entry sits in the table and nothing ever looks at it,
 * which is exactly what the first hardware attempt showed: the packet arrived
 * (rx_packets 20 -> 40) and the hit bit stayed 0.
 */
#define ZX_PP_EXTRA_INDEX_SEL	0u
#define ZX_PP_EXTRA_INDEX_WORDS	5u
#define ZX_PP_EXTRA_INDEX_ENABLE_WORD	4u
#define ZX_PP_EXTRA_V4_DIR0_SHIFT	4u	/* bits 5:4 */
#define ZX_PP_EXTRA_V4_DIR0_MASK	(0x3u << ZX_PP_EXTRA_V4_DIR0_SHIFT)
#define ZX_PP_EXTRA_V4_DIR1_SHIFT	0u	/* bits 1:0 */
#define ZX_PP_EXTRA_V4_DIR1_MASK	(0x3u << ZX_PP_EXTRA_V4_DIR1_SHIFT)

/* The ternary extra_rule defaults (sel 1), the context the exact-match hash
 * sits above. tm_acl_fast_init (Ghidra 0x5e8e0) writes the IPv4 5-tuple pair
 * at 0x90/0x91 = ZX_PP_EXTIDX_V4FAST * 16 + {0,1} and then sets bit 0 of
 * extra_index[9] word 4.
 *
 * This is the piece that was missing. The window's `field` is the index of
 * one of these rules; with the rule absent the exact-match entry refers to a
 * rule that describes nothing, which is consistent with every hardware result
 * so far: install, enable and spray all succeed, and nothing matches.
 */
#define ZX_PP_EXTRA_RULE_SEL	1u
#define ZX_PP_EXTRA_RULE_DEPTH	160u
/* tm_acl_fast_init's own enable: extra_index[9] word 4 bit 0 (IPv4) and
 * extra_index[10] word 4 bit 2 (IPv6). Different bits from EN_V4FAST's 5:4.
 */
#define ZX_PP_EXTRA_FASTINIT_V4_BIT	(1u << 0)
#define ZX_PP_EXTRA_FASTINIT_V6_BIT	(1u << 2)

/* Install the vendor's IPv4 ternary default rule pair at `ext_idx`/`nibble`
 * and OR `en_mask` into that extra-index entry's word 4, exactly as
 * tm_acl_fast_init does for (9, 0, bit 0).
 *
 * The parameters are not hardcoded because which (ext_idx, nibble) pair the
 * engine actually consults is the open question this is meant to settle, and
 * a boot costs minutes: one image can try several. The vendor's own pairs are
 * (9, 0) for the IPv4 5-tuple path -- tm_acl_fast_init's 0x90/0x91 -- and
 * (k, 4) for the IPv4 3-tuple path at every k, from tm_acl_3tuple_fast_init's
 * 0x14 + 0x10*k with its extra_index[k] bit 4.
 */
static int zx_pp_rule_init_v4(struct zx_pp_flow *f, u8 ext_idx, u8 nibble,
			      u32 en_mask)
{
	u32 rule[ZX_PP_EXTRA_RULE_WORDS];
	u32 entry[ZX_PP_EXTRA_INDEX_WORDS] = { 0 };
	u32 idx = (u32)ext_idx * 16u + nibble;
	u32 before;
	int ret;

	if (ext_idx > 15 || nibble > 14 || idx + 1 >= ZX_PP_EXTRA_RULE_DEPTH)
		return -EINVAL;

	zx_pp_build_extra_rule_v4(rule, false);
	ret = zx_pp_cla_write(f->pp, ZX_PP_EXTRA_RULE_SEL, idx, rule,
			      ZX_PP_EXTRA_RULE_WORDS);
	if (ret)
		return ret;
	zx_pp_build_extra_rule_v4(rule, true);
	ret = zx_pp_cla_write(f->pp, ZX_PP_EXTRA_RULE_SEL, idx + 1u, rule,
			      ZX_PP_EXTRA_RULE_WORDS);
	if (ret)
		return ret;

	ret = zx_pp_cla_read(f->pp, ZX_PP_EXTRA_INDEX_SEL, ext_idx,
			     entry, ZX_PP_EXTRA_INDEX_WORDS);
	if (ret)
		return ret;
	before = entry[ZX_PP_EXTRA_INDEX_ENABLE_WORD];
	entry[ZX_PP_EXTRA_INDEX_ENABLE_WORD] |= en_mask;
	ret = zx_pp_cla_write(f->pp, ZX_PP_EXTRA_INDEX_SEL, ext_idx,
			      entry, ZX_PP_EXTRA_INDEX_WORDS);
	if (ret)
		return ret;
	dev_info(f->dev,
		 "pp-flow: extra_rule[%u,%u] installed; extra_index[%u] word4 %#010x -> %#010x (mask %#x)\n",
		 idx, idx + 1u, ext_idx, before,
		 entry[ZX_PP_EXTRA_INDEX_ENABLE_WORD], en_mask);
	return 0;
}

/* Poke one 32-bit word of an extra_rule entry (sel 1) in place: read the whole
 * 17-word entry, replace word `word`, write it back. This is the runtime lever
 * for the key-encoding bisection (docs/PP-KEY.md §10): the decisive test is a
 * rule whose winmask words are all zero (everything masked out), which any
 * packet should match -- if `cla fwd` then moves, the engine path, placement
 * and enable are confirmed and only the value/mask encoding is left. Gated by
 * flow_test_enable; writes any CLA table, so it stays behind the test config.
 */
static int zx_pp_rule_poke(struct zx_pp_flow *f, u32 idx, u32 word, u32 value)
{
	u32 buf[ZX_PP_EXTRA_RULE_WORDS] = { 0 };
	int ret;

	if (idx >= ZX_PP_EXTRA_RULE_DEPTH || word >= ZX_PP_EXTRA_RULE_WORDS)
		return -EINVAL;
	ret = zx_pp_cla_read(f->pp, ZX_PP_EXTRA_RULE_SEL, idx, buf,
			     ZX_PP_EXTRA_RULE_WORDS);
	if (ret)
		return ret;
	dev_info(f->dev, "pp-flow: rule poke sel1[%u] w%u: %08x -> %08x\n",
		 idx, word, buf[word], value);
	buf[word] = value;
	return zx_pp_cla_write(f->pp, ZX_PP_EXTRA_RULE_SEL, idx, buf,
			       ZX_PP_EXTRA_RULE_WORDS);
}

/* Poke one 32-bit word of a stored hash window (sel 2..6) in place, the window
 * analogue of zx_pp_rule_poke. Lets the stored key be varied one word at a time
 * with `pipe` as the readout, to localise which stored byte the comparison
 * actually consumes. Gated by flow_test_enable.
 */
static int zx_pp_win_poke(struct zx_pp_flow *f, unsigned int sel, u16 addr,
			  u32 word, u32 value)
{
	u32 w[ZX_PP_HASH_WORDS] = { 0 };
	int ret;

	if (sel < 2 || sel > 6 || word >= ZX_PP_HASH_WORDS)
		return -EINVAL;
	ret = zx_pp_cla_read(f->pp, sel, addr, w, ZX_PP_HASH_WORDS);
	if (ret)
		return ret;
	dev_info(f->dev, "pp-flow: win poke sel%u[%u] w%u: %08x -> %08x\n",
		 sel, addr, word, w[word], value);
	w[word] = value;
	return zx_pp_cla_write(f->pp, sel, addr, w, ZX_PP_HASH_WORDS);
}

/* Dump one extra_rule or extra_index entry, so a stock-firmware comparison
 * does not need a second tool.
 */
static int zx_pp_rule_show(struct zx_pp_flow *f, unsigned int sel, u32 idx)
{
	u32 buf[ZX_PP_EXTRA_RULE_WORDS] = { 0 };
	unsigned int words = (sel == ZX_PP_EXTRA_RULE_SEL)
			   ? ZX_PP_EXTRA_RULE_WORDS : ZX_PP_EXTRA_INDEX_WORDS;
	unsigned int i;
	int ret;

	if (sel != ZX_PP_EXTRA_RULE_SEL && sel != ZX_PP_EXTRA_INDEX_SEL)
		return -EINVAL;
	if (idx >= (sel == ZX_PP_EXTRA_RULE_SEL ? ZX_PP_EXTRA_RULE_DEPTH : 16u))
		return -EINVAL;
	ret = zx_pp_cla_read(f->pp, sel, idx, buf, words);
	if (ret)
		return ret;
	for (i = 0; i < words; i += 4)
		dev_info(f->dev, "pp-flow: sel%u[%u] w%u: %08x %08x %08x %08x\n",
			 sel, idx, i, buf[i],
			 i + 1 < words ? buf[i + 1] : 0,
			 i + 2 < words ? buf[i + 2] : 0,
			 i + 3 < words ? buf[i + 3] : 0);
	return 0;
}

/* The positive control the whole investigation has been missing.
 *
 * Every negative result so far reads "the aging bit is 0". That is only
 * evidence of a non-match if a 1 can be observed in that table at all, and
 * nothing has ever put one there: the vendor's path is read-to-clear, this
 * driver only ever writes 0, and the engine has never set one. So "hit=0"
 * could equally mean the aging table is write-only-zero, is at a different
 * address than believed, or is not the hit table.
 *
 * `aging poke <addr>` writes 1 and reads it back. A readback of 1 makes every
 * subsequent hit=0 meaningful. A readback of 0 invalidates the entire
 * measurement method and is itself the finding.
 */
static int zx_pp_aging_poke(struct zx_pp_flow *f, u16 addr)
{
	u32 v = 0;
	int ret;

	ret = zx_pp_aging_write(f->pp, addr, 1);
	if (ret) {
		dev_info(f->dev, "pp-flow: aging poke %u: write failed (%d)\n",
			 addr, ret);
		return ret;
	}
	ret = zx_pp_aging_read(f->pp, addr, &v);
	if (ret) {
		dev_info(f->dev, "pp-flow: aging poke %u: read failed (%d)\n",
			 addr, ret);
		return ret;
	}
	dev_info(f->dev,
		 "pp-flow: aging poke %u: wrote 1, read %#x -> the table %s hold a 1\n",
		 addr, v, (v & 1u) ? "CAN" : "CANNOT");
	/* leave it clear so a later scan is unambiguous */
	return zx_pp_aging_write(f->pp, addr, 0);
}

/* Dump a CLA hash window straight back out of the engine, so the stored entry
 * can be compared with what the driver believes it wrote without going
 * through the read-path debugfs files (which bound the index differently).
 */
static int zx_pp_win_show(struct zx_pp_flow *f, unsigned int sel, u16 addr)
{
	u32 w[ZX_PP_HASH_WORDS] = { 0 };
	int ret;

	if (sel < 2 || sel > 6)
		return -EINVAL;
	ret = zx_pp_cla_read(f->pp, sel, addr, w, ZX_PP_HASH_WORDS);
	if (ret)
		return ret;
	dev_info(f->dev, "pp-flow: win sel%u[%u]: %08x %08x %08x %08x %08x\n",
		 sel, addr, w[0], w[1], w[2], w[3], w[4]);
	dev_info(f->dev, "pp-flow: win sel%u[%u]+5: %08x %08x %08x %08x %08x\n",
		 sel, addr, w[5], w[6], w[7], w[8], w[9]);
	return 0;
}

static int zx_pp_extra_index_set(struct zx_pp_flow *f, u8 port, u8 dir, bool on)
{
	u32 entry[ZX_PP_EXTRA_INDEX_WORDS] = { 0 };
	u32 mask, val, before;
	int ret;

	if (port >= 16 || dir > 1)
		return -EINVAL;
	mask = dir ? ZX_PP_EXTRA_V4_DIR1_MASK : ZX_PP_EXTRA_V4_DIR0_MASK;
	val = dir ? (ZX_PP_EXTRA_V4_DIR1_MASK) : (ZX_PP_EXTRA_V4_DIR0_MASK);

	ret = zx_pp_cla_read(f->pp, ZX_PP_EXTRA_INDEX_SEL, port, entry,
			     ZX_PP_EXTRA_INDEX_WORDS);
	if (ret)
		return ret;
	before = entry[ZX_PP_EXTRA_INDEX_ENABLE_WORD];
	if (on)
		entry[ZX_PP_EXTRA_INDEX_ENABLE_WORD] |= val;
	else
		entry[ZX_PP_EXTRA_INDEX_ENABLE_WORD] &= ~mask;

	dev_info(f->dev,
		 "pp-flow: extra_index[%u] word%u %#010x -> %#010x (dir %u %s, mask %#x)\n",
		 port, ZX_PP_EXTRA_INDEX_ENABLE_WORD, before,
		 entry[ZX_PP_EXTRA_INDEX_ENABLE_WORD], dir, on ? "on" : "off",
		 mask);

	if (before == entry[ZX_PP_EXTRA_INDEX_ENABLE_WORD])
		return 0;	/* already in that state; do not rewrite */
	return zx_pp_cla_write(f->pp, ZX_PP_EXTRA_INDEX_SEL, port, entry,
			       ZX_PP_EXTRA_INDEX_WORDS);
}

/* Spray the installed window into every slot of one inner bank, so a packet
 * matches wherever the engine looks. This separates "the key or the bucket is
 * wrong" from "the engine never consulted the table": if a spray does not
 * match, no placement can.
 */
static int zx_pp_flow_spray(struct zx_pp_flow *f, unsigned int bank)
{
	static const struct { u8 sel; u16 depth; u16 base; } banks[] = {
		{ 2, 256, 0 }, { 3, 128, 256 }, { 4, 64, 384 }, { 5, 64, 448 },
	};
	u32 win[ZX_PP_HASH_WORDS];
	unsigned int i;
	int ret;

	if (bank >= (unsigned int)ARRAY_SIZE(banks))
		return -EINVAL;
	ret = zx_pp_window_v4(&f->spec, ZX_PP_FLOW_INFO_IDX, win);
	if (ret)
		return ret;
	for (i = 0; i < banks[bank].depth; i++) {
		ret = zx_pp_cla_write(f->pp, banks[bank].sel, (u16)i, win,
				      ZX_PP_HASH_WORDS);
		if (ret)
			return ret;
	}
	/* clear the whole bank's aging so a later stat is unambiguous */
	for (i = 0; i < banks[bank].depth; i++) {
		ret = zx_pp_aging_write(f->pp, banks[bank].base + (u16)i, 0);
		if (ret)
			return ret;
	}
	dev_info(f->dev, "pp-flow: sprayed %u slots into sel %u (aging %u..%u)\n",
		 banks[bank].depth, banks[bank].sel, banks[bank].base,
		 banks[bank].base + banks[bank].depth - 1);
	return 0;
}

/* Report every set aging bit in a bank and clear it. */
static int zx_pp_flow_hits(struct zx_pp_flow *f, unsigned int bank)
{
	static const struct { u16 depth; u16 base; } banks[] = {
		{ 256, 0 }, { 128, 256 }, { 64, 384 }, { 64, 448 }, { 8, 512 },
	};
	unsigned int i, found = 0;
	u32 v;
	int ret;

	if (bank >= (unsigned int)ARRAY_SIZE(banks))
		return -EINVAL;
	for (i = 0; i < banks[bank].depth; i++) {
		u16 slot = banks[bank].base + (u16)i;

		ret = zx_pp_aging_read(f->pp, slot, &v);
		if (ret)
			return ret;
		if (v & 1u) {
			dev_info(f->dev, "pp-flow: HIT slot %u\n", slot);
			found++;
		}
		if (v)
			zx_pp_aging_write(f->pp, slot, 0);
	}
	dev_info(f->dev, "pp-flow: bank %u scan: %u hit(s)\n", bank, found);
	return 0;
}

static int zx_pp_flow_clear_hashed(struct zx_pp_flow *f);

/* Caller holds f->lock. The hashed install: build the real IPv4 window,
 * derive the key, place it at the bucket a live packet will hash to, then
 * write it.
 *
 * The scoping field is (ingress << 4) | type nibble, with the v4 ORIGINAL
 * nibble. That assumes extIdx is the ingress port number, which docs/PP-KEY.md
 * section 5 lists as the first thing the hit bit has to confirm: if it is
 * wrong, the entry lands in the right *slot arithmetic* but the engine hashes
 * a different key and nothing matches. A different port staying at hit 0 is
 * the control.
 */
static int zx_pp_flow_write_hashed(struct zx_pp_flow *f, const struct zx_pp_flow_spec *s)
{
	u32 nh[ZX_PP_NH_WORDS], fi[ZX_PP_FLOW_INFO_WORDS], win[ZX_PP_HASH_WORDS];
	u8 key[ZX_PP_KEY_LEN];
	struct zx_pp_hash_cfg cfg;
	u16 bucket;
	unsigned int sel;
	u16 bank_addr;
	int ret;

	ret = zx_pp_hash_config(f->pp, &cfg);
	if (ret)
		return ret;
	if (!cfg.usable) {
		dev_info(f->dev,
			 "pp-flow: refused: the CLA outer table is configured (0x9238c094 != 0) and mode 1 is undecoded\n");
		return -EOPNOTSUPP;
	}

	ret = zx_pp_window_v4(s, ZX_PP_FLOW_INFO_IDX, win);
	if (ret)
		return ret;

	zx_pp_build_key((const u8 *)win, zx_pp_field(), key);

	ret = zx_pp_hash_place(&cfg, &f->map, key, &bucket);
	if (ret) {
		dev_info(f->dev, "pp-flow: refused: no free hash slot (%d)\n", ret);
		return ret;
	}
	ret = zx_pp_hash_bank(bucket, &sel, &bank_addr);
	if (ret) {
		zx_pp_hash_release(&f->map, bucket);
		return ret;
	}

	/* From here the slot is ours, so record it: the unwind below addresses it
	 * through f->bucket, and a failure must not leave a live entry behind.
	 */
	f->bucket = bucket;

	zx_pp_build_next_hop(s->dst_mac, (const u8 *)&s->dst_ip, nh);
	zx_pp_build_flow_info(ZX_PP_FLOW_NH_IDX, fi);
	f->info_addr = zx_pp_flow_info_addr();	/* latch dir for the matching clear */

	ret = zx_pp_pm_write(f->pp, ZX_PP_PM_SEL_NEXT_HOP, ZX_PP_FLOW_NH_IDX,
			     nh, ZX_PP_NH_WORDS);
	if (ret)
		goto unwind;
	ret = zx_pp_pm_write(f->pp, ZX_PP_PM_SEL_FLOW_INFO,
			     f->info_addr,
			     fi, ZX_PP_FLOW_INFO_WORDS);
	if (ret)
		goto unwind;
	ret = zx_pp_cla_write(f->pp, sel, bank_addr, win, ZX_PP_HASH_WORDS);
	if (ret)
		goto unwind;
	ret = zx_pp_aging_write(f->pp, bucket, 0);
	if (ret)
		goto unwind;

	dev_info(f->dev,
		 "pp-flow: hashed id %u: in%u proto%u %pI4:%u -> %pI4:%u egress%u bucket %u (sel %u bank %u) key field %#04x flow_info dir %u addr %#x\n",
		 f->id + 1, s->ingress, s->proto, &s->src_ip, ntohs(s->src_port),
		 &s->dst_ip, ntohs(s->dst_port), s->egress, bucket, sel, bank_addr,
		 zx_pp_field(), (f->info_addr >> 10) & 1u, f->info_addr);
	return 0;

unwind:
	/* Clears whatever got written and releases the slot. Nothing to do when
	 * the failure happened before the first write: this path is only reached
	 * after f->bucket was set.
	 */
	zx_pp_flow_clear_hashed(f);
	f->bucket = 0;
	return ret;
}

/* Caller holds f->lock. Clears the hashed entry at its own bucket. */
static int zx_pp_flow_clear_hashed(struct zx_pp_flow *f)
{
	u32 win[ZX_PP_HASH_WORDS] = { 0 };
	u32 nh[ZX_PP_NH_WORDS] = { 0 };
	u32 fi[ZX_PP_FLOW_INFO_WORDS] = { 0 };
	unsigned int sel;
	u16 bank_addr;
	int ret, first = 0;

	if (zx_pp_hash_bank(f->bucket, &sel, &bank_addr))
		return -EINVAL;

	/* CLA first, so the engine stops considering the entry before the PM
	 * entries behind it disappear.
	 */
	ret = zx_pp_cla_write(f->pp, sel, bank_addr, win, ZX_PP_HASH_WORDS);
	first = first ? first : ret;
	ret = zx_pp_aging_write(f->pp, f->bucket, 0);
	first = first ? first : ret;
	ret = zx_pp_pm_write(f->pp, ZX_PP_PM_SEL_FLOW_INFO,
			     f->info_addr,	/* dir latched at install */
			     fi, ZX_PP_FLOW_INFO_WORDS);
	first = first ? first : ret;
	ret = zx_pp_pm_write(f->pp, ZX_PP_PM_SEL_NEXT_HOP, ZX_PP_FLOW_NH_IDX,
			     nh, ZX_PP_NH_WORDS);
	first = first ? first : ret;
	if (!first)
		zx_pp_hash_release(&f->map, f->bucket);
	return first;
}

static int zx_pp_flow_write(struct zx_pp_flow *f, const struct zx_pp_flow_spec *s)
{
	u32 nh[ZX_PP_NH_WORDS], fi[ZX_PP_FLOW_INFO_WORDS], win[ZX_PP_HASH_WORDS];
	u32 zero = 0;
	int ret;

	zx_pp_build_next_hop(s->dst_mac, (const u8 *)&s->dst_ip, nh);
	zx_pp_build_flow_info(ZX_PP_FLOW_NH_IDX, fi);
	zx_pp_build_window(s, ZX_PP_FLOW_INFO_IDX, win);
	f->info_addr = zx_pp_flow_info_addr();	/* latch dir for the matching clear */

	ret = zx_pp_pm_write(f->pp, ZX_PP_PM_SEL_NEXT_HOP, ZX_PP_FLOW_NH_IDX,
			     nh, ZX_PP_NH_WORDS);
	if (ret)
		return ret;
	ret = zx_pp_pm_write(f->pp, ZX_PP_PM_SEL_FLOW_INFO,
			     f->info_addr,
			     fi, ZX_PP_FLOW_INFO_WORDS);
	if (ret)
		return ret;
	ret = zx_pp_cla_write(f->pp, ZX_PP_CLA_SEL_HASH4, ZX_PP_FLOW_HASH_ADDR,
			      win, ZX_PP_HASH_WORDS);
	if (ret)
		return ret;
	return zx_pp_aging_write(f->pp, ZX_PP_FLOW_AGING_ADDR, zero);
}

/* Caller holds f->lock. Clears the CLA entry first (valid_en in the zeroed
 * window is 0, so the engine stops considering it) and only then releases the
 * PM entries it pointed at.
 */
static int zx_pp_flow_clear(struct zx_pp_flow *f)
{
	u32 win[ZX_PP_HASH_WORDS] = { 0 };
	u32 nh[ZX_PP_NH_WORDS] = { 0 };
	u32 fi[ZX_PP_FLOW_INFO_WORDS] = { 0 };
	u32 zero = 0;
	int ret, first = 0;

	ret = zx_pp_cla_write(f->pp, ZX_PP_CLA_SEL_HASH4, ZX_PP_FLOW_HASH_ADDR,
			      win, ZX_PP_HASH_WORDS);
	first = first ? first : ret;
	ret = zx_pp_aging_write(f->pp, ZX_PP_FLOW_AGING_ADDR, zero);
	first = first ? first : ret;
	ret = zx_pp_pm_write(f->pp, ZX_PP_PM_SEL_FLOW_INFO,
			     f->info_addr,	/* dir latched at install */
			     fi, ZX_PP_FLOW_INFO_WORDS);
	first = first ? first : ret;
	ret = zx_pp_pm_write(f->pp, ZX_PP_PM_SEL_NEXT_HOP, ZX_PP_FLOW_NH_IDX,
			     nh, ZX_PP_NH_WORDS);
	first = first ? first : ret;
	return first;
}

static int zx_pp_flow_validate(struct zx_pp_flow *f, const struct zx_pp_flow_spec *s)
{
	if (s->proto != IPPROTO_TCP && s->proto != IPPROTO_UDP) {
		dev_info(f->dev, "pp-flow: refused: proto %u is not TCP or UDP\n",
			 s->proto);
		return -EOPNOTSUPP;
	}
	if (s->ingress > ZX_PP_FLOW_MAX_PORT || s->egress > ZX_PP_FLOW_MAX_PORT) {
		dev_info(f->dev, "pp-flow: refused: port out of range (in %u out %u)\n",
			 s->ingress, s->egress);
		return -EINVAL;
	}
	/* Header rewrite routes through cmd_ram packet offsets, which are
	 * unknown (docs/PP-FLOW.md). Refuse rather than write a guess.
	 */
	if (s->new_src_ip != s->src_ip) {
		dev_info(f->dev, "pp-flow: refused: source NAT rewrite rests on an unknown (cmd_ram offset)\n");
		return -EOPNOTSUPP;
	}
	if (s->new_src_port != s->src_port) {
		dev_info(f->dev, "pp-flow: refused: source-port rewrite rests on an unknown (cmd_ram offset)\n");
		return -EOPNOTSUPP;
	}
	return 0;
}

static int zx_pp_flow_install(struct zx_pp_flow *f, const struct zx_pp_flow_spec *s,
			      bool hashed)
{
	int ret;

	if (!flow_test_enable) {
		dev_info(f->dev, "pp-flow: refused: flow_test_enable is 0\n");
		return -EPERM;
	}
	mutex_lock(&f->lock);
	if (f->installed) {
		dev_info(f->dev, "pp-flow: refused: a flow is already installed (id %u); del it first\n",
			 f->id);
		ret = -EBUSY;
		goto out;
	}
	ret = zx_pp_flow_validate(f, s);
	if (ret)
		goto out;

	if (hashed) {
		ret = zx_pp_flow_write_hashed(f, s);
	} else {
		ret = zx_pp_flow_write(f, s);
	}
	if (ret) {
		dev_info(f->dev, "pp-flow: install failed (%d)\n", ret);
		/* The hashed writer unwinds itself; the legacy one leaves its
		 * partial writes to the caller, which is the tested behaviour.
		 */
		if (!hashed)
			zx_pp_flow_clear(f);
		goto out;
	}
	f->spec = *s;
	f->installed = true;
	f->hashed = hashed;
	f->id++;
	if (!hashed)
		dev_info(f->dev,
			 "pp-flow: installed id %u: in%u proto%u %pI4:%u -> %pI4:%u egress%u dmac %pM (fixed slot %u, flow_idx %u, nh %u)\n",
			 f->id, s->ingress, s->proto, &s->src_ip, ntohs(s->src_port),
			 &s->dst_ip, ntohs(s->dst_port), s->egress, s->dst_mac,
			 ZX_PP_FLOW_AGING_ADDR, ZX_PP_FLOW_INFO_IDX, ZX_PP_FLOW_NH_IDX);
out:
	mutex_unlock(&f->lock);
	return ret;
}

static int zx_pp_flow_delete(struct zx_pp_flow *f, u32 id)
{
	int ret;

	mutex_lock(&f->lock);
	if (!f->installed || f->id != id) {
		dev_info(f->dev, "pp-flow: refused del: no installed flow with id %u\n", id);
		ret = -ENOENT;
		goto out;
	}
	ret = f->hashed ? zx_pp_flow_clear_hashed(f) : zx_pp_flow_clear(f);
	if (ret) {
		/* The clear failed, so an entry may still be live in a table the
		 * engine walks. Keep `installed` set: it is this driver's only
		 * handle on that entry, and it is what stops teardown from
		 * freeing the tables underneath it. The caller can retry.
		 */
		dev_err(f->dev,
			"pp-flow: delete id %u failed (%d); the flow may still be installed\n",
			id, ret);
		goto out;
	}
	f->installed = false;
	dev_info(f->dev, "pp-flow: deleted id %u (slot %u)\n", id,
		 f->hashed ? f->bucket : ZX_PP_FLOW_AGING_ADDR);
	f->hashed = false;
out:
	mutex_unlock(&f->lock);
	return ret;
}

static int zx_pp_flow_stat(struct zx_pp_flow *f, u32 id)
{
	u32 hit = 0, zero = 0;
	u16 slot;
	int ret, clear_ret;

	mutex_lock(&f->lock);
	if (!f->installed || f->id != id) {
		dev_info(f->dev, "pp-flow: refused stat: no installed flow with id %u\n", id);
		ret = -ENOENT;
		goto out;
	}
	slot = f->hashed ? f->bucket : ZX_PP_FLOW_AGING_ADDR;
	ret = zx_pp_aging_read(f->pp, slot, &hit);
	if (ret) {
		dev_info(f->dev, "pp-flow: stat id %u: aging read failed (%d)\n", id, ret);
		goto out;
	}
	dev_info(f->dev, "pp-flow: stat id %u: hit=%u (aging[%u]=%#x)\n",
		 id, hit & 1u, slot, hit);
	/* The vendor reads the hit bit and clears it (read-to-clear,
	 * tm_get_acl_flow_status). Mirror that so the next poll reports fresh
	 * hits. A clear that fails is reported rather than swallowed: the next
	 * read would otherwise show a stale hit and be read as new traffic.
	 */
	clear_ret = zx_pp_aging_write(f->pp, slot, zero);
	if (clear_ret) {
		dev_err(f->dev, "pp-flow: stat id %u: hit bit did not clear (%d)\n",
			id, clear_ret);
		ret = clear_ret;
	}
out:
	mutex_unlock(&f->lock);
	return ret;
}

/* "pipe": dump the CLA per-action packet counters for BOTH directions.
 *
 * This is the classification instrument that round 4 (docs/PP-KEY.md §10)
 * established: `trap` increments 1:1 with every GE-ingress frame the engine
 * classifies. `fwd` counts forwarding actions, including a default flow, so
 * it alone does not prove an exact-match hit. Read both action banks and the
 * separate match/aging instruments with explicit controls; a moving pipeline
 * counter cannot establish which table entry matched.
 *
 * CORRECTED (PP-KEY §21): the counters are TWO banks, up and dn. The historical
 * `pipe` read only the up bank, which is why every §10-§20 measurement watched
 * `cla fwd`=0 for a frame whose action was actually landing on the DOWNSTREAM
 * trap (0x9238c3d0). A WAN(eth3)->LAN(eth0) routed frame is uplink->UNI = dn,
 * so for the test flow the number that matters is dn fwd (0x9238c3cc). Both
 * banks are printed now so a single `pipe` read can no longer watch the wrong
 * side of the A/B. A dn fwd change with traps flat is forwarding evidence,
 * while exact-match attribution still requires a separate match control.
 */
static int zx_pp_flow_pipe(struct zx_pp_flow *f)
{
	u32 fwd = 0, trap = 0, drop = 0, copy = 0;
	u32 dfwd = 0, dtrap = 0, ddrop = 0, dcopy = 0;
	int ret;

	ret = zx_pp_cla_counters(f->pp, &fwd, &trap, &drop, &copy);
	if (ret) {
		dev_info(f->dev, "pp-flow: pipe: up counter read failed (%d)\n", ret);
		return ret;
	}
	ret = zx_pp_cla_counters_dn(f->pp, &dfwd, &dtrap, &ddrop, &dcopy);
	if (ret) {
		dev_info(f->dev, "pp-flow: pipe: dn counter read failed (%d)\n", ret);
		return ret;
	}
	dev_info(f->dev,
		 "pp-flow: cla up: fwd=%u trap=%u drop=%u copy=%u\n",
		 fwd, trap, drop, copy);
	dev_info(f->dev,
		 "pp-flow: cla dn: fwd=%u trap=%u drop=%u copy=%u\n",
		 dfwd, dtrap, ddrop, dcopy);
	return 0;
}

/* ---- control-file parsing ----------------------------------------------- */

/* "add <in> <proto> <sip>:<sport> <dip>:<dport> -> <out> <nsip>:<nsport> <dmac> <smac>" */
static int zx_pp_parse_ipport(const char *tok, __be32 *ip, __be16 *port)
{
	const char *end;
	u16 p;

	if (in4_pton(tok, -1, (u8 *)ip, ':', &end) != 1)
		return -EINVAL;
	if (*end != ':')
		return -EINVAL;
	if (kstrtou16(end + 1, 10, &p))
		return -EINVAL;
	*port = htons(p);
	return 0;
}

static int zx_pp_parse_proto(const char *tok, u8 *proto)
{
	if (!strcmp(tok, "tcp"))
		*proto = IPPROTO_TCP;
	else if (!strcmp(tok, "udp"))
		*proto = IPPROTO_UDP;
	else
		return -EINVAL;
	return 0;
}

static int zx_pp_parse_add(char *args, struct zx_pp_flow_spec *s)
{
	char *tok, *proto, *sip, *dip, *arrow, *out, *nsip, *dmac, *smac;
	u16 in, egress;

	memset(s, 0, sizeof(*s));
	tok   = strsep(&args, " ");
	proto = strsep(&args, " ");
	sip   = strsep(&args, " ");
	dip   = strsep(&args, " ");
	arrow = strsep(&args, " ");
	out   = strsep(&args, " ");
	nsip  = strsep(&args, " ");
	dmac  = strsep(&args, " ");
	smac  = strsep(&args, " ");
	if (!tok || !proto || !sip || !dip || !arrow || !out || !nsip || !dmac || !smac)
		return -EINVAL;
	if (strcmp(arrow, "->"))
		return -EINVAL;
	if (kstrtou16(tok, 10, &in) || in > 0xff)
		return -EINVAL;
	if (kstrtou16(out, 10, &egress) || egress > 0xff)
		return -EINVAL;
	s->ingress = in;
	s->egress = egress;
	if (zx_pp_parse_proto(proto, &s->proto))
		return -EINVAL;
	if (zx_pp_parse_ipport(sip, &s->src_ip, &s->src_port))
		return -EINVAL;
	if (zx_pp_parse_ipport(dip, &s->dst_ip, &s->dst_port))
		return -EINVAL;
	if (zx_pp_parse_ipport(nsip, &s->new_src_ip, &s->new_src_port))
		return -EINVAL;
	if (!mac_pton(dmac, s->dst_mac))
		return -EINVAL;
	if (!mac_pton(smac, s->src_mac))
		return -EINVAL;
	return 0;
}

static ssize_t zx_pp_flow_write_cmd(struct file *file, const char __user *ubuf,
				    size_t len, loff_t *ppos)
{
	struct zx_pp_flow *f = file->private_data;
	struct zx_pp_flow_spec spec;
	char buf[192], *line, *verb, *args;
	u16 id;
	int ret;

	if (len == 0 || len >= sizeof(buf))
		return -EINVAL;
	if (copy_from_user(buf, ubuf, len))
		return -EFAULT;
	buf[len] = '\0';
	line = strim(buf);
	args = line;
	verb = strsep(&args, " ");
	if (!verb)
		return -EINVAL;

	if (!strcmp(verb, "add") || !strcmp(verb, "addh")) {
		bool hashed = !strcmp(verb, "addh");

		if (!args)
			return -EINVAL;
		ret = zx_pp_parse_add(args, &spec);
		if (ret) {
			dev_info(f->dev, "pp-flow: %s: malformed command\n", verb);
			return ret;
		}
		ret = zx_pp_flow_install(f, &spec, hashed);
	} else if (!strcmp(verb, "enable") || !strcmp(verb, "disable")) {
		char *port_s, *dir_s, *state_s;
		u16 port, dir;

		port_s = strsep(&args, " ");
		dir_s = strsep(&args, " ");
		state_s = strsep(&args, " ");
		if (!port_s || !dir_s || kstrtou16(port_s, 10, &port) ||
		    kstrtou16(dir_s, 10, &dir) || port > 0xff || dir > 1)
			return -EINVAL;
		ret = zx_pp_extra_index_set(f, (u8)port, (u8)dir,
					    !strcmp(verb, "enable"));
		(void)state_s;
	} else if (!strcmp(verb, "rule")) {
		/* "rule init" installs the vendor's IPv4 ternary default pair;
		 * "rule show <sel> <idx>" dumps an extra_rule/extra_index entry.
		 */
		char *sub = strsep(&args, " ");
		u16 sel, idx;

		if (!sub)
			return -EINVAL;
		if (!flow_test_enable)
			return -EPERM;
		mutex_lock(&f->lock);
		if (!strcmp(sub, "init")) {
			/* "rule init [ext_idx nibble [mask]]", default the
			 * vendor's (9, 0, bit 0).
			 */
			char *e_s = strsep(&args, " ");
			char *n_s = strsep(&args, " ");
			char *m_s = strsep(&args, " ");
			u16 e = ZX_PP_EXTIDX_V4FAST, n = 0;
			u32 m = ZX_PP_EXTRA_FASTINIT_V4_BIT;

			if (e_s && *e_s &&
			    (kstrtou16(e_s, 0, &e) || e > 15))
				ret = -EINVAL;
			else if (n_s && *n_s &&
				 (kstrtou16(n_s, 0, &n) || n > 14))
				ret = -EINVAL;
			else if (m_s && *m_s && kstrtou32(strim(m_s), 0, &m))
				ret = -EINVAL;
			else
				ret = zx_pp_rule_init_v4(f, (u8)e, (u8)n, m);
		} else if (!strcmp(sub, "show")) {
			char *sel_s = strsep(&args, " ");
			char *idx_s = strsep(&args, " ");

			if (!sel_s || !idx_s || kstrtou16(sel_s, 0, &sel) ||
			    kstrtou16(strim(idx_s), 0, &idx))
				ret = -EINVAL;
			else
				ret = zx_pp_rule_show(f, sel, idx);
		} else {
			ret = -EINVAL;
		}
		mutex_unlock(&f->lock);
		if (ret)
			return ret;
		*ppos += len;
		return len;
	} else if (!strcmp(verb, "aging")) {
		/* "aging poke <addr>": the positive control. */
		char *sub = strsep(&args, " ");
		char *a_s = strsep(&args, " ");
		u16 a;

		if (!sub || strcmp(sub, "poke") || !a_s ||
		    kstrtou16(strim(a_s), 0, &a) || a >= ZX_PP_CLA_AGING_DEPTH)
			return -EINVAL;
		if (!flow_test_enable)
			return -EPERM;
		mutex_lock(&f->lock);
		ret = zx_pp_aging_poke(f, a);
		mutex_unlock(&f->lock);
		if (ret)
			return ret;
		*ppos += len;
		return len;
	} else if (!strcmp(verb, "win")) {
		/* "win <sel> <addr>": read a stored hash window back. */
		char *s_s = strsep(&args, " ");
		char *a_s = strsep(&args, " ");
		u16 sl, a;

		if (!s_s || !a_s || kstrtou16(s_s, 0, &sl) ||
		    kstrtou16(strim(a_s), 0, &a))
			return -EINVAL;
		mutex_lock(&f->lock);
		ret = zx_pp_win_show(f, sl, a);
		mutex_unlock(&f->lock);
		if (ret)
			return ret;
		*ppos += len;
		return len;
	} else if (!strcmp(verb, "rulew")) {
		/* "rulew <idx> <word> <value>": overwrite one 32-bit word of an
		 * extra_rule entry in place (the key-encoding bisection lever).
		 */
		char *i_s = strsep(&args, " ");
		char *w_s = strsep(&args, " ");
		char *v_s = strsep(&args, " ");
		u32 idx, word, value;

		if (!i_s || !w_s || !v_s || kstrtou32(i_s, 0, &idx) ||
		    kstrtou32(w_s, 0, &word) || kstrtou32(strim(v_s), 0, &value))
			return -EINVAL;
		if (!flow_test_enable)
			return -EPERM;
		mutex_lock(&f->lock);
		ret = zx_pp_rule_poke(f, idx, word, value);
		mutex_unlock(&f->lock);
		if (ret)
			return ret;
		*ppos += len;
		return len;
	} else if (!strcmp(verb, "winw")) {
		/* "winw <sel> <addr> <word> <value>": overwrite one 32-bit word
		 * of a stored hash window in place.
		 */
		char *s_s = strsep(&args, " ");
		char *a_s = strsep(&args, " ");
		char *w_s = strsep(&args, " ");
		char *v_s = strsep(&args, " ");
		u16 sl, a;
		u32 word, value;

		if (!s_s || !a_s || !w_s || !v_s || kstrtou16(s_s, 0, &sl) ||
		    kstrtou16(a_s, 0, &a) || kstrtou32(w_s, 0, &word) ||
		    kstrtou32(strim(v_s), 0, &value))
			return -EINVAL;
		if (!flow_test_enable)
			return -EPERM;
		mutex_lock(&f->lock);
		ret = zx_pp_win_poke(f, sl, a, word, value);
		mutex_unlock(&f->lock);
		if (ret)
			return ret;
		*ppos += len;
		return len;
	} else if (!strcmp(verb, "field")) {
		/* "field <ext_idx> <nibble>": the scoping field the next install
		 * uses. extIdx is an extra-index slot, not a port (0x5841c).
		 */
		char *ext_s = strsep(&args, " ");
		char *nib_s = strsep(&args, " ");
		u16 ext, nib;

		if (!ext_s || !nib_s || kstrtou16(ext_s, 0, &ext) ||
		    kstrtou16(strim(nib_s), 0, &nib) || ext > 15 || nib > 15)
			return -EINVAL;
		zx_pp_ext_idx = (u8)ext;
		zx_pp_type_nibble = (u8)nib;
		dev_info(f->dev, "pp-flow: field = %#04x (extIdx %u nibble %u, rule %u)\n",
			 zx_pp_field(), ext, nib, ext * 16u + nib);
		*ppos += len;
		return len;
	} else if (!strcmp(verb, "spray") || !strcmp(verb, "hits")) {
		u16 bank;

		if (!args || kstrtou16(strim(args), 10, &bank) || bank > 0xff)
			return -EINVAL;
		mutex_lock(&f->lock);
		ret = !strcmp(verb, "spray") ? zx_pp_flow_spray(f, bank)
					     : zx_pp_flow_hits(f, bank);
		mutex_unlock(&f->lock);
		if (ret)
			return ret;
		*ppos += len;
		return len;
	} else if (!strcmp(verb, "del")) {
		if (!args || kstrtou16(strim(args), 10, &id))
			return -EINVAL;
		ret = zx_pp_flow_delete(f, id);
	} else if (!strcmp(verb, "stat")) {
		if (!args || kstrtou16(strim(args), 10, &id))
			return -EINVAL;
		ret = zx_pp_flow_stat(f, id);
	} else if (!strcmp(verb, "pipe")) {
		/* "pipe": read the CLA fwd/trap/drop/copy counters. No argument,
		 * no state change; safe to call before and after any injection.
		 */
		mutex_lock(&f->lock);
		ret = zx_pp_flow_pipe(f);
		mutex_unlock(&f->lock);
	} else {
		dev_info(f->dev, "pp-flow: unknown command '%s'\n", verb);
		return -EINVAL;
	}

	if (ret)
		return ret;
	*ppos += len;
	return len;
}

static int zx_pp_flow_open(struct inode *inode, struct file *file)
{
	file->private_data = inode->i_private;
	return 0;
}

static const struct file_operations zx_pp_flow_fops = {
	.owner = THIS_MODULE,
	.open = zx_pp_flow_open,
	.write = zx_pp_flow_write_cmd,	/* 0200: write-only, root-only */
	.llseek = noop_llseek,
};

void zx_pp_flow_init(struct zx_pp *pp, struct device *dev, struct dentry *dir)
{
	struct zx_pp_flow *f;

	f = devm_kzalloc(dev, sizeof(*f), GFP_KERNEL);
	if (!f)
		return;
	f->pp = pp;
	f->dev = dev;
	mutex_init(&f->lock);
	f->file = debugfs_create_file("flow", 0200, dir, f, &zx_pp_flow_fops);
	g_flow = f;
	dev_info(dev, "pp-flow: control file ready (write-only, flow_test_enable=%d)\n",
		 flow_test_enable);
}

/* Called from the PP teardown AFTER debugfs is gone (no writer can race) and
 * BEFORE the engines are disabled and the tables freed. Deletes the one flow
 * so the engines never walk a table that is about to be handed back.
 *
 * Returns 0 when nothing is installed afterwards. A non-zero return means the
 * clear failed and an entry may still be live: the caller must then keep the
 * tables (docs/PP-OFFLOAD.md, "never return memory the engine may still
 * reach") rather than free them.
 */
int zx_pp_flow_fini(void)
{
	struct zx_pp_flow *f = g_flow;
	int ret = 0;

	if (!f)
		return 0;
	mutex_lock(&f->lock);
	if (f->installed) {
		ret = f->hashed ? zx_pp_flow_clear_hashed(f) : zx_pp_flow_clear(f);
		if (ret) {
			dev_err(f->dev,
				"pp-flow: teardown could not clear the installed flow (%d); the tables must not be freed\n",
				ret);
		} else {
			f->installed = false;
			dev_info(f->dev, "pp-flow: deleted installed flow at teardown\n");
		}
	}
	mutex_unlock(&f->lock);
	/* Drop the handle only when it is clean. On failure the flow context is
	 * the only record that an entry may be live, and the tables are being
	 * leaked anyway, so keeping it costs nothing.
	 */
	if (!ret)
		g_flow = NULL;
	return ret;
}

#endif /* CONFIG_ZX279128_PP_FLOW_TEST */
