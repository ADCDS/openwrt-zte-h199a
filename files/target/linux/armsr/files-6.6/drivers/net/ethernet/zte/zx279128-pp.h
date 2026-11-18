/* SPDX-License-Identifier: GPL-2.0 */
/*
 * ZX279128S packet-processor table access (CLA and PM indirect ports,
 * PM/ACL DRAM tables). Linked into the Ethernet driver only when
 * CONFIG_ZX279128_PP_TABLES is set; see docs/PP-OFFLOAD.md.
 */
#ifndef ZX279128_PP_H
#define ZX279128_PP_H

#ifdef CONFIG_ZX279128_PP_TABLES

#include <linux/types.h>

struct device;
struct zx_pp;

/* Called by the Ethernet probe after the packet-processor bring-up. Returns
 * NULL when table access stays disabled; the datapath does not need it.
 */
struct zx_pp *zx_pp_tables_init(struct device *dev);
/* Removes debugfs, stops indirect access, clears both DRAM table bases and
 * only then frees the tables. NULL is accepted.
 */
void zx_pp_tables_remove(struct zx_pp *pp);

/* One indirect operation on the CLA or PM table port. data[i] is DATA word i.
 * Returns 0, -EINVAL (request outside the vendor bounds), -ENODEV (tables not
 * live), -ETIMEDOUT (ready flag not seen; the engine then refuses further
 * operations with -EIO).
 */
int zx_pp_cla_read(struct zx_pp *pp, unsigned int sel, u32 addr,
		   u32 *data, unsigned int words);
int zx_pp_cla_write(struct zx_pp *pp, unsigned int sel, u32 addr,
		    const u32 *data, unsigned int words);
int zx_pp_pm_read(struct zx_pp *pp, unsigned int sel, u32 addr,
		  u32 *data, unsigned int words);
int zx_pp_pm_write(struct zx_pp *pp, unsigned int sel, u32 addr,
		   const u32 *data, unsigned int words);

/* CLA exact-match aging (hit) table: one word per hash address, holding the
 * hit bit. The index is the same address a CLA hash entry is written at, so
 * "did anything match this entry" is a read of that one address.
 *
 * The vendor reads the bit and then clears it (tm_get_acl_flow_status), so
 * these accessors deliberately do not: a caller that clears loses the hit.
 * Addresses past the depth are -EINVAL, not a silently wrong table.
 *
 * Hash addresses are 0..511 for the four ways plus 512..519 for the cla_hash4
 * overflow bank. The vendor also addresses `hash_addr + 0x400` for an entry in
 * the external table; that form is not exposed, because the outer table is
 * unconfigured at reset (0x9238c094 = 0) and mode 1 is undecoded.
 */
#define ZX_PP_CLA_AGING_DEPTH	520

int zx_pp_aging_read(struct zx_pp *pp, u32 addr, u32 *val);
int zx_pp_aging_write(struct zx_pp *pp, u32 addr, u32 val);

/* CLA upstream per-action packet counters (fwd/trap/drop/copy). Plain MMIO
 * reads, no engine lock; pass NULL for any counter you do not need. These are
 * the live classification instrument: trap tracks classified-but-unmatched
 * ingress frames 1:1, fwd counts exact-match hits (docs/PP-KEY.md §10).
 */
int zx_pp_cla_counters(struct zx_pp *pp, u32 *fwd, u32 *trap, u32 *drop,
		       u32 *copy);

/* CLA DOWNSTREAM per-action packet counters (dn fwd/trap/drop/copy), decoded
 * from tm_dn_statistics_get (tm.ko 0x5298c). A WAN(uplink)->LAN(UNI) routed
 * frame is downstream, so its forward/trap land here, NOT in the up bank above.
 * dn fwd is 0x9238c3cc; it is the pass criterion for the downstream test flow
 * (docs/PP-KEY.md §21). Same MMIO-read, no-lock contract as the up bank.
 */
int zx_pp_cla_counters_dn(struct zx_pp *pp, u32 *fwd, u32 *trap, u32 *drop,
			  u32 *copy);

/* The CLA hash polynomial selectors, read from hardware at init. The vendor
 * never writes these registers, so the reset value is what the engine uses;
 * a driver that assumed zeros instead of reading would place entries in the
 * wrong bucket (docs/PP-FLOW.md "CLA exact-match hash").
 */
struct zx_pp_hash_cfg {
	u8 inner[4];	/* per-way polynomial selector, 0..3 */
	u8 outer[4];
	u8 outer_num;	/* outer table ways: 1 << (2 - outer_num) */
	u8 outer_space;
	/* False when the outer table is configured. Mode 1 (the external hash)
	 * is undecoded, so an entry cannot be placed while it is in use.
	 */
	bool usable;
};

int zx_pp_hash_config(struct zx_pp *pp, struct zx_pp_hash_cfg *cfg);

/* Sizes of the things the builders below produce. Declared here, ahead of
 * them, because their prototypes name the counts.
 */
#define ZX_PP_KEY_LEN		45	/* the vendor's fast-hash key length */
#define ZX_PP_HASH_WAYS		4	/* four ways per inner bucket */
#define ZX_PP_HASH_INNER_SLOTS	512	/* 256 + 128 + 64 + 64 */
#define ZX_PP_HASH_OVERFLOW	8	/* slots 512..519, the linear scan */
#define ZX_PP_HASH_SLOTS	(ZX_PP_HASH_INNER_SLOTS + ZX_PP_HASH_OVERFLOW)
#define ZX_PP_WINDOW_LEN	60	/* the CLA exact-match window */
#define ZX_PP_WINDOW_WORDS	20	/* windata0..19 at window bytes 17..56 */
#define ZX_PP_HASH_WORDS	15	/* the window as 15 little-endian u32 */
#define ZX_PP_NH_WORDS		3	/* a PM next_hop entry */
#define ZX_PP_FLOW_INFO_WORDS	3	/* a PM flow_info entry */

/* The extra-index slot every IPv4 5-tuple fast flow uses, and the ternary
 * extra_rule index pair tm_acl_fast_init installs for it.
 */
#define ZX_PP_EXTIDX_V4FAST	9u
#define ZX_PP_EXTIDX_V6FAST	10u
#define ZX_PP_EXTRA_RULE_WORDS	17u	/* a 68-byte TCAM value+mask entry */
#define ZX_PP_EXTRA_RULE_BYTES	68u

/* ---- table-entry builders (zx279128-pp-hash.c) --------------------------
 * The CLA window and the PM entries are byte-packed and written as
 * little-endian u32 words, so every builder works on a byte buffer and then
 * packs. These are shared by the diagnostic flow path and the offload path;
 * keeping one copy of the bit positions is the point.
 */
void zx_pp_set_field(u8 *buf, unsigned int byte, unsigned int shift,
		     unsigned int width, u32 val);
void zx_pp_pack_words(const u8 *buf, u32 *words, unsigned int nwords);

/* next_hop: the egress DMAC and the next-hop IP, in the vendor's 3 words. */
void zx_pp_build_next_hop(const u8 dmac[6], const u8 dip[4],
			  u32 w[ZX_PP_NH_WORDS]);
/* flow_info: a forwarding + L2/checksum descriptor pointing at next_hop. */
void zx_pp_build_flow_info(unsigned int nh_idx, u32 w[ZX_PP_FLOW_INFO_WORDS]);

/* The window's action fields, bytes 0..18. `field` is the extIdx/type scoping
 * value, (extIdx << 4) | type nibble; the same value goes into the hash key.
 */
void zx_pp_fill_action(u8 ingress, u8 egress, u32 flow_id, u8 field, u8 *b);

/* Build the vendor's IPv4 5-tuple ternary default rule (the 68-byte
 * extra_rule TCAM entry tm_acl_fast_init writes at indices 0x90 and 0x91).
 * `pair` selects the second of the pair, which differs only in bit 9 of the
 * halfword at byte 0x16. See docs/PP-KEY.md section 8.
 */
void zx_pp_build_extra_rule_v4(u32 w[ZX_PP_EXTRA_RULE_WORDS], bool pair);

/* Build the whole 60-byte IPv4 window: action fields plus the decoded match
 * words, packed to ZX_PP_HASH_WORDS words. -EOPNOTSUPP for anything the
 * encoding does not cover (see zx_pp_build_window_v4).
 *
 * `field` is (extIdx << 4) | type nibble. It is a caller argument rather than
 * (ingress << 4) | 4, because extIdx is the extra-index slot (9 for every
 * IPv4 5-tuple flow), not the ingress port -- see ZX_PP_EXTIDX_V4FAST.
 */
int zx_pp_build_window_ipv4(u32 w[ZX_PP_HASH_WORDS], u8 ingress, u8 egress,
			    u32 flow_id, u8 field, u8 proto,
			    const u8 sip[4], u16 sport,
			    const u8 dip[4], u16 dport);

/* ---- CLA exact-match hash (zx279128-pp-hash.c) -------------------------
 * A packet reaches an exact-match entry only through the bucket the engine
 * computes for it, so placing an entry needs the engine's own computation.
 * The algorithm is decoded and recorded in docs/PP-FLOW.md; what is NOT
 * decoded is the byte layout of the 45-byte key, so every function here takes
 * the key as a caller-supplied buffer rather than building one from a packet.
 */

/* The port/type nibbles of the key's scoping field, (extIdx << 4) | nibble.
 * The key is per-extIdx AND per-direction, so an ORIGINAL and a REPLY entry
 * for the same tuple hash to different buckets (docs/PP-KEY.md section 2).
 *
 * CORRECTION, 2026-11-16: `field` is NOT (ingress_port << 4). It is
 * (extIdx << 4), and extIdx is the EXTRA-INDEX TABLE SLOT, which
 * aclGetExtIdxRuleRamAddrByPort (Ghidra 0x5841c) returns as a constant 9 for
 * every port while g_ipv4FastEn is set -- and tm_acl_fast_add_v4v6 sets that
 * flag immediately before calling it for rule type 3 (TCP/UDP). So every
 * 5-tuple IPv4 fast flow on every port uses extIdx 9.
 *
 * `field` is therefore an INDEX INTO THE TERNARY extra_rule TABLE:
 * rule index = extIdx * 16 + nibble. tm_acl_fast_init installs the IPv4
 * 5-tuple rule pair at 0x90/0x91 = 9*16 + {0,1}. Nibble 0 is the 5-tuple
 * ORIGINAL path; nibble 4 belongs to the 3-tuple path (g_v4OutUsed_3t).
 */
#define ZX_PP_KEY_TYPE_V4_ORIG	4
#define ZX_PP_KEY_TYPE_V4_REPLY	0
#define ZX_PP_KEY_TYPE_V6_ORIG	6
#define ZX_PP_KEY_TYPE_V6_REPLY	2


/* Build the 45-byte hash key from the 60-byte window the driver is about to
 * write, plus the scoping field (extIdx << 4 | type nibble). docs/PP-KEY.md
 * section 3 is the bit-position table this implements.
 */
void zx_pp_build_key(const u8 window[ZX_PP_WINDOW_LEN], u8 field,
		     u8 key[ZX_PP_KEY_LEN]);

/* Encode an IPv4 5-tuple into the window's match words (docs/PP-KEY.md
 * section 4). Writes window bytes 19..32 only; the action fields are the
 * caller's. IPv6, VLAN, PPPoE and tunnels take different branches in the
 * vendor function and are not decoded, so they are not expressible here.
 */
int zx_pp_build_window_v4(u8 window[ZX_PP_WINDOW_LEN], u8 proto,
			  const u8 sip[4], u16 sport,
			  const u8 dip[4], u16 dport);

/* Which slots this driver has put something in. The hardware exposes no
 * occupancy (the vendor keeps its own map), so this must be kept.
 */
struct zx_pp_hash_map {
	u8 used[ZX_PP_HASH_SLOTS];
};

/* The 16-bit hash of `key` under polynomial table `sel` (0..3), as
 * cla_acl_hash_addr_gen computes it: reverse byte feed, init 0, no final XOR,
 * low 16 bits kept. Returns 0 for a selector out of range, which cannot occur
 * because the selectors are two-bit fields.
 */
u16 zx_pp_hash16(unsigned int sel, const u8 *key);

/* The 32-bit CRC core, forward over `buf`. Exposed because the vendor tables'
 * recorded check value is the full CRC of "123456789", which is what pins the
 * polynomial constants; the driver itself only needs zx_pp_hash16().
 */
u32 zx_pp_crc32(unsigned int sel, const u8 *buf, size_t len);

/* The four inner buckets for `key`, one per way, using cfg's selectors.
 * Returns -EOPNOTSUPP when cfg->usable is false: an entry cannot be placed
 * while the undecoded outer table is in use.
 */
int zx_pp_hash_buckets(const struct zx_pp_hash_cfg *cfg, const u8 *key,
		       u16 bucket[ZX_PP_HASH_WAYS]);

/* The CLA bank selector (2..6) and in-bank address for a global hash address
 * (0..519). -EINVAL outside that range.
 */
int zx_pp_hash_bank(u16 addr, unsigned int *sel, u16 *bank_addr);

/* Place a key: the first free way, then the 512..519 scan. 0 and *addr on
 * success, -ENOSPC when every slot this driver may use is taken.
 */
int zx_pp_hash_place(const struct zx_pp_hash_cfg *cfg, struct zx_pp_hash_map *map,
		     const u8 *key, u16 *addr);
void zx_pp_hash_release(struct zx_pp_hash_map *map, u16 addr);

#ifdef CONFIG_ZX279128_PP_OFFLOAD
struct device;
struct net_device;
enum tc_setup_type;

/* The one seam the Ethernet driver (zx279128-eth.c) supplies: how to turn a
 * net_device into a hardware switch-port index. Returns 0..N-1 for a real
 * switch port and a negative value for anything that is not one (WiFi, a
 * tunnel, a software bridge) -- which is exactly what makes those flows stay
 * in the software datapath. The offload path keeps a pointer to this; it never
 * reaches into the Ethernet driver's structures.
 */
struct zx_pp_offload_dev_ops {
	int (*port_index)(const struct net_device *dev);
};

/* Hardware flow offload (zx279128-pp-offload.c), gated by its own symbol on
 * top of table access. zx_pp_offload_init() installs the one-time ternary
 * rule and registers the neighbour notifier; zx_pp_offload_fini() flushes
 * every entry during teardown (returning non-zero if a table must be kept).
 * zx_pp_offload_setup_tc() is the ndo_setup_tc body the Ethernet driver's
 * per-port ops call; zx_pp_offload_port_down() flushes a closing port's
 * entries. zx_pp_offload_set_dev_ops() hands the port-index seam over once.
 */
void zx_pp_offload_init(struct zx_pp *pp, struct device *dev);
int zx_pp_offload_fini(struct zx_pp *pp);
void zx_pp_offload_set_dev_ops(struct zx_pp *pp,
			       const struct zx_pp_offload_dev_ops *ops);
int zx_pp_offload_setup_tc(struct zx_pp *pp, struct net_device *dev,
			   enum tc_setup_type type, void *type_data);
void zx_pp_offload_port_down(struct zx_pp *pp, const struct net_device *dev);
#endif /* CONFIG_ZX279128_PP_OFFLOAD */

#ifdef CONFIG_ZX279128_PP_FLOW_TEST
struct device;
struct dentry;
/* Flow-install test path (zx279128-pp-flow.c), gated by a separate symbol.
 * zx_pp_flow_init() adds its debugfs control file under the table-access
 * directory; zx_pp_flow_fini() deletes any installed flow during teardown,
 * after debugfs is gone and before the engines are disabled and the tables
 * freed. See docs/PP-FLOW.md.
 *
 * zx_pp_flow_fini() returns 0 when no flow is installed afterwards. A
 * non-zero return means the clear failed and an entry may still be live in a
 * table the engine walks, so the caller must not free that table.
 */
void zx_pp_flow_init(struct zx_pp *pp, struct device *dev, struct dentry *dir);
int zx_pp_flow_fini(void);
#endif /* CONFIG_ZX279128_PP_FLOW_TEST */

#endif /* CONFIG_ZX279128_PP_TABLES */
#endif /* ZX279128_PP_H */
