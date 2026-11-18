// SPDX-License-Identifier: GPL-2.0
/*
 * ZX279128S CLA exact-match hash: the CRC, the bucket arithmetic and the
 * slot bookkeeping.
 *
 * A packet only reaches an exact-match entry through the bucket the CLA
 * engine computes for it, so placing an entry needs the same computation the
 * engine does. The algorithm is decoded from the vendor module and recorded in
 * docs/PP-FLOW.md ("CLA exact-match hash") with its evidence in
 * logs/analysis-20261115/pp-cla-hash.md:
 *
 *   - a table-driven, MSB-first CRC-32, init 0, no final XOR, refin/refout
 *     false, of which only the low 16 bits are kept;
 *   - the 45 key bytes are fed in REVERSE order, key[44] first;
 *   - the polynomial is one of four constants, selected per way by a two-bit
 *     field of 0x9238c090 (so one key yields four different hashes);
 *   - way 0 uses h & 0xff, way 1 (h & 0x7f) + 256, way 2 (h & 0x3f) + 384,
 *     way 3 (h & 0x3f) + 448; the first free way wins, then the 512..519
 *     scan.
 *
 * The CRC is computed bitwise rather than through four 256-word tables. The
 * two forms are the same function; the bitwise one costs ~360 shifts per key
 * (nothing at flow-install rate) and keeps four kilobytes of magic constants
 * out of the tree. tests/test_pp_hash.py pins it against the vendor tables'
 * recorded check values and the worked examples in pp-cla-hash.md.
 *
 * What this file does NOT do is decode the vendor's match-info struct. It does
 * build the 45-byte key from the 60-byte window, because that is what the
 * driver has: the window is the thing it writes, and docs/PP-KEY.md shows the
 * key is a one-bit-shifted repack of that window's bytes 17..56 plus the
 * port/type field. The window's own tuple encoding stays a caller concern.
 *
 * The free-slot test is a SOFTWARE occupancy byte, not the aging table: the
 * vendor keeps its own map and the hardware exposes no occupancy
 * (pp-cla-hash.md "Reduction to a table address"). So this driver keeps one
 * too, and a slot is free only when the driver put nothing there.
 */
#include <linux/errno.h>
#include <linux/string.h>
#include <linux/types.h>

#include "zx279128-pp.h"

/* The four polynomials, in selector order. Each is the vendor's own constant,
 * byte-verified against a freshly generated MSB-first table (pp-cla-hash.md,
 * "Polynomial = one of 4 constant tables").
 */
static const u32 zx_pp_hash_poly[ZX_PP_HASH_WAYS] = {
	0x04c11db7,	/* sel 0: CRC-32/IEEE    (the vendor's 0x04C11DB7 table) */
	0x1edc6f41,	/* sel 1: CRC-32C        (the vendor's 0x1EDC6F41 table) */
	0xf4acfb13,	/* sel 2: CRC-32/AUTOSAR (the vendor's 0xF4ACFB13 table) */
	0x32583499,	/* sel 3: CRC-32Q        (the vendor's 0x32583499 table) */
};

u32 zx_pp_crc32(unsigned int sel, const u8 *buf, size_t len)
{
	u32 crc = 0;
	size_t i;
	unsigned int b;
	u32 poly;

	if (sel >= ZX_PP_HASH_WAYS)
		return 0;
	poly = zx_pp_hash_poly[sel];
	for (i = 0; i < len; i++) {
		/* MSB-first: the byte goes into the top 8 bits, then eight
		 * conditional shifts. This is the vendor's CRC_32 loop with the
		 * 256-word table inlined, which is the same function.
		 */
		crc ^= (u32)buf[i] << 24;
		for (b = 0; b < 8; b++)
			crc = (crc & 0x80000000u) ? (crc << 1) ^ poly : crc << 1;
	}
	return crc;
}

u16 zx_pp_hash16(unsigned int sel, const u8 *key)
{
	u8 reversed[ZX_PP_KEY_LEN];
	unsigned int i;

	if (sel >= ZX_PP_HASH_WAYS || !key)
		return 0;
	/* The vendor copies key[0..44] into a scratch buffer backwards and then
	 * runs the CRC forward over it, so key[44] is the first byte fed in and
	 * key[0] the last (pp-cla-hash.md, "Key bytes hashed: all 45, in
	 * reverse order"). Only the low 16 bits survive (`uxth`).
	 */
	for (i = 0; i < ZX_PP_KEY_LEN; i++)
		reversed[i] = key[ZX_PP_KEY_LEN - 1 - i];
	return (u16)zx_pp_crc32(sel, reversed, ZX_PP_KEY_LEN);
}

/* aclGetAvailableHashAddr mode 0: one address per way, from that way's own
 * hash. The masks are the vendor's (`ldrb`/`and`/`add` before each probe).
 */
static u16 zx_pp_hash_way_addr(unsigned int way, u16 h)
{
	switch (way) {
	case 0:
		return h & 0xff;		/* 0..255   */
	case 1:
		return (h & 0x7f) + 256;	/* 256..383 */
	case 2:
		return (h & 0x3f) + 384;	/* 384..447 */
	default:
		return (h & 0x3f) + 448;	/* 448..511 */
	}
}

/* Build the 45-byte hash key from the 60-byte CLA window (docs/PP-KEY.md).
 *
 * key[0..1] are zero and key[2]/key[3] carry `field`, the port/type scoping
 * byte, written rotated: key[3] = field >> 1, key[2] bit 7 = field & 1.
 *
 * From key[4] the window's twenty match words are packed one bit out of phase
 * with the byte grid, little-endian within each word: windata_j occupies key
 * bits 33 + 16j .. 48 + 16j. The one bit before the first word is
 * window[16] bit 5, which tm_acl_get_fastHashRule sets from the ingress port.
 *
 * key[44] bits 7:1 are not defined by the repack; the vendor leaves them at
 * whatever the buffer held, so they are zeroed here.
 */
void zx_pp_build_key(const u8 window[ZX_PP_WINDOW_LEN], u8 field,
		     u8 key[ZX_PP_KEY_LEN])
{
	u8 bits[ZX_PP_KEY_LEN * 8];
	unsigned int j, b;

	memset(key, 0, ZX_PP_KEY_LEN);
	key[2] = (u8)((field & 1) << 7);
	key[3] = (u8)(field >> 1);

	/* Work in bits for clarity: bit `p` of the key is bits[p]. The stream
	 * starts at key bit 32 with the window's port bit, then each match word
	 * follows LSB first.
	 */
	memset(bits, 0, sizeof(bits));
	bits[32] = (window[16] >> 5) & 1;
	for (j = 0; j < ZX_PP_WINDOW_WORDS; j++) {
		u16 word = (u16)(window[17 + 2 * j] | (window[18 + 2 * j] << 8));

		for (b = 0; b < 16; b++)
			bits[33 + 16 * j + b] = (word >> b) & 1;
	}
	for (j = 4; j < ZX_PP_KEY_LEN; j++) {
		u8 v = 0;

		for (b = 0; b < 8; b++)
			v |= (u8)(bits[8 * j + b] << b);
		key[j] = v;
	}
}

/* Encode an IPv4 5-tuple into the window's match words.
 *
 * CORRECTED 2026-11-16. The previous assignment was derived from what
 * tm_acl_get_fastHashRule STORES, which is not what the engine COMPARES, and
 * it was wrong by one word. The authority is the ternary extra_rule entry the
 * window's `field` selects: cla_set_extra_rule_table's own debug decoder names
 * that entry's fields `winoffset0..19` and `winmask0..19`, i.e. the rule tells
 * the engine WHICH PACKET BYTES to extract into windata0..19 and which bits of
 * each to keep. Decoding tm_acl_fast_init's IPv4 rule through that decoder
 * gives, unambiguously:
 *
 *   winoffset0..6 = 8, 12, 14, 16, 18, 20, 22   (and 7..19 = 0)
 *   winmask0      = 0x00ff
 *   winmask1..6   = 0xffff                      (and 7..19 = 0)
 *
 * Those offsets are byte offsets into the IPv4 header, and each extracts a
 * big-endian halfword:
 *
 *   windata0 = packet[ 8..9]  & 0x00ff  -> IP+8 is TTL, IP+9 is protocol, so
 *                                          the mask keeps the PROTOCOL only
 *   windata1 = packet[12..13]           -> source address, high half
 *   windata2 = packet[14..15]           -> source address, low half
 *   windata3 = packet[16..17]           -> destination address, high half
 *   windata4 = packet[18..19]           -> destination address, low half
 *   windata5 = packet[20..21]           -> source port
 *   windata6 = packet[22..23]           -> destination port
 *   windata7..19 are masked to zero.
 *
 * Two things follow that the old encoding got wrong. The tuple starts at
 * windata1, not windata2, and the protocol lives in windata0, which the old
 * code left zero -- so every stored word was one position out of place.
 * The winmask0 byte is also why a TTL-carrying word is harmless: the engine
 * drops TTL before comparing.
 *
 * The window stores each extracted halfword little-endian within the word
 * (the key packs words little-endian, docs/PP-KEY.md section 3), so a
 * big-endian packet halfword AABB is stored as byte BB then byte AA.
 *
 * Returns -EOPNOTSUPP for anything this encoding does not cover: IPv6, VLAN,
 * PPPoE and tunnels each select a different ternary rule with different
 * offsets, and none of those is decoded.
 */
int zx_pp_build_window_v4(u8 window[ZX_PP_WINDOW_LEN], u8 proto,
			  const u8 sip[4], u16 sport,
			  const u8 dip[4], u16 dport)
{
	if (!window || !sip || !dip)
		return -EINVAL;

	/* windata0: IP+8 = {TTL, proto} big-endian, masked to 0x00ff. The TTL
	 * byte is masked away by the rule, so it is stored as 0.
	 */
	window[17] = proto;	/* low byte of the BE halfword  */
	window[18] = 0;		/* TTL, masked out by winmask0  */

	/* windata1..2: source address, two BE halfwords. */
	window[19] = sip[1];
	window[20] = sip[0];
	window[21] = sip[3];
	window[22] = sip[2];

	/* windata3..4: destination address. */
	window[23] = dip[1];
	window[24] = dip[0];
	window[25] = dip[3];
	window[26] = dip[2];

	/* windata5..6: source and destination port, BE on the wire. */
	window[27] = (u8)(sport & 0xff);
	window[28] = (u8)(sport >> 8);
	window[29] = (u8)(dport & 0xff);
	window[30] = (u8)(dport >> 8);

	/* windata7..19 stay zero: the rule masks them out entirely. */
	return 0;
}

int zx_pp_hash_buckets(const struct zx_pp_hash_cfg *cfg, const u8 *key,
		       u16 bucket[ZX_PP_HASH_WAYS])
{
	unsigned int w;

	if (!cfg || !key || !bucket)
		return -EINVAL;
	/* Mode 1 (the outer/external table) is undecoded, and the engine only
	 * uses it when 0x9238c094 is configured. Refuse rather than compute a
	 * bucket that cannot be right.
	 */
	if (!cfg->usable)
		return -EOPNOTSUPP;
	for (w = 0; w < ZX_PP_HASH_WAYS; w++)
		bucket[w] = zx_pp_hash_way_addr(w, zx_pp_hash16(cfg->inner[w], key));
	return 0;
}

/* A global hash address maps to one of the five CLA banks: 0..255 to
 * cla_hash0 (sel 2), 256..383 to cla_hash1 (sel 3), 384..447 to cla_hash2
 * (sel 4), 448..511 to cla_hash3 (sel 5) and 512..519 to cla_hash4 (sel 6),
 * with the in-bank address being the global one minus the bank's base
 * (zx279128-pp.c zx_pp_tables[], cla_get_hash_table 0x5f20).
 */
int zx_pp_hash_bank(u16 addr, unsigned int *sel, u16 *bank_addr)
{
	if (!sel || !bank_addr)
		return -EINVAL;
	if (addr < 256) {
		*sel = 2;
		*bank_addr = addr;
	} else if (addr < 384) {
		*sel = 3;
		*bank_addr = addr - 256;
	} else if (addr < 448) {
		*sel = 4;
		*bank_addr = addr - 384;
	} else if (addr < 512) {
		*sel = 5;
		*bank_addr = addr - 448;
	} else if (addr < ZX_PP_HASH_SLOTS) {
		*sel = 6;
		*bank_addr = addr - 512;
	} else {
		return -EINVAL;
	}
	return 0;
}

/* aclGetAvailableHashAddr: the first free way, then the linear 512..519 scan
 * (mode 2, which uses no hash at all).
 */
int zx_pp_hash_place(const struct zx_pp_hash_cfg *cfg, struct zx_pp_hash_map *map,
		     const u8 *key, u16 *addr)
{
	u16 bucket[ZX_PP_HASH_WAYS];
	unsigned int w;
	int ret;

	if (!map || !addr)
		return -EINVAL;
	ret = zx_pp_hash_buckets(cfg, key, bucket);
	if (ret)
		return ret;
	for (w = 0; w < ZX_PP_HASH_WAYS; w++) {
		if (map->used[bucket[w]])
			continue;
		map->used[bucket[w]] = 1;
		*addr = bucket[w];
		return 0;
	}
	for (w = 0; w < ZX_PP_HASH_OVERFLOW; w++) {
		u16 slot = ZX_PP_HASH_INNER_SLOTS + w;	/* 512..519 */

		if (map->used[slot])
			continue;
		map->used[slot] = 1;
		*addr = slot;
		return 0;
	}
	return -ENOSPC;
}

void zx_pp_hash_release(struct zx_pp_hash_map *map, u16 addr)
{
	if (!map || addr >= ZX_PP_HASH_SLOTS)
		return;
	map->used[addr] = 0;
}

/* ---- table-entry builders ----------------------------------------------
 * The CLA window and the PM entries are byte-packed with fields that straddle
 * byte boundaries, then written as little-endian u32 words. One copy of the
 * bit positions lives here so the diagnostic path and the offload path cannot
 * drift apart.
 */
void zx_pp_set_field(u8 *buf, unsigned int byte, unsigned int shift,
		     unsigned int width, u32 val)
{
	u32 mask = (width >= 32) ? ~0u : ((1u << width) - 1);

	val &= mask;
	buf[byte] = (buf[byte] & ~(u8)(mask << shift)) | (u8)(val << shift);
	if (shift + width > 8)
		buf[byte + 1] = (buf[byte + 1] & ~(u8)(mask >> (8 - shift))) |
				(u8)(val >> (8 - shift));
	if (shift + width > 16)
		buf[byte + 2] = (buf[byte + 2] & ~(u8)(mask >> (16 - shift))) |
				(u8)(val >> (16 - shift));
}

void zx_pp_pack_words(const u8 *buf, u32 *words, unsigned int nwords)
{
	unsigned int i;

	for (i = 0; i < nwords; i++)
		words[i] = (u32)buf[4 * i] | ((u32)buf[4 * i + 1] << 8) |
			   ((u32)buf[4 * i + 2] << 16) |
			   ((u32)buf[4 * i + 3] << 24);
}

/* pp_pm_set_next_hop_ram_info (tm.ko 0x1d66c) packs a 10-byte {DMAC[6],
 * next-hop DIP[4]} record into 3 words:
 *   word0 = m2<<24 | m3<<16 | m4<<8 | m5
 *   word1 = ip0<<24 | ip1<<16 | ip2<<8 | ip3
 *   word2 = m1<<8 | m0
 */
void zx_pp_build_next_hop(const u8 dmac[6], const u8 dip[4],
			  u32 w[ZX_PP_NH_WORDS])
{
	w[0] = ((u32)dmac[2] << 24) | ((u32)dmac[3] << 16) |
	       ((u32)dmac[4] << 8) | dmac[5];
	w[1] = ((u32)dip[0] << 24) | ((u32)dip[1] << 16) |
	       ((u32)dip[2] << 8) | dip[3];
	w[2] = ((u32)dmac[1] << 8) | dmac[0];
}

/* pp_pm_set_flow_info (tm.ko 0x1cef8): a pure forwarding + L2-rewrite
 * descriptor. All header-rewrite enables stay 0 because SNAT/DNAT route
 * through cmd_ram packet offsets, which are not decoded.
 */
void zx_pp_build_flow_info(unsigned int nh_idx, u32 w[ZX_PP_FLOW_INFO_WORDS])
{
	u8 b[12] = { 0 };

	zx_pp_set_field(b, 0, 0, 1, 1);			/* dmac_en  = 1 */
	zx_pp_set_field(b, 0, 1, 1, 1);			/* smac_en  = 1 */
	zx_pp_set_field(b, 4, 3, 1, 1);			/* tcp_udp_chk_en = 1 */
	zx_pp_set_field(b, 4, 4, 1, 1);			/* ip_chk_en = 1 */
	zx_pp_set_field(b, 6, 2, 6, nh_idx & 0x3f);	/* next_hop_idx[5:0] */
	zx_pp_set_field(b, 7, 0, 3, (nh_idx >> 6) & 0x7);	/* [8:6] */
	zx_pp_pack_words(b, w, ZX_PP_FLOW_INFO_WORDS);
}

/* The window's action fields, bytes 0..18. See docs/PP-KEY.md section 2 for
 * why rule_mode (window[16] bit 4) is 0 and direct (bit 5) is 0.
 */
void zx_pp_fill_action(u8 ingress, u8 egress, u32 flow_id, u8 field, u8 *b)
{
	zx_pp_set_field(b, 16, 6, 1, 1);		/* valid_en  = 1 */
	zx_pp_set_field(b, 5, 6, 1, 1);			/* modify_en = 1 */
	zx_pp_set_field(b, 3, 1, 7, flow_id & 0x7f);	/* cmd_flow_id[6:0] */
	zx_pp_set_field(b, 4, 0, 3, (flow_id >> 7) & 0x7);	/* [9:7] */

	zx_pp_set_field(b, 12, 5, 3, ingress & 0x7);	/* inport[2:0] */
	zx_pp_set_field(b, 13, 0, 2, (ingress >> 3) & 0x3);	/* inport[4:3] */
	zx_pp_set_field(b, 14, 0, 6, egress & 0x3f);	/* outport[5:0] */

	/* The port/type field in the window's own copy (window[15] bits 7:4,
	 * window[16] bits 3:0), which is what the vendor writes. This value is
	 * the ternary extra_rule index, (extIdx << 4) | nibble.
	 */
	zx_pp_set_field(b, 15, 4, 4, field & 0xf);
	zx_pp_set_field(b, 16, 0, 4, (field >> 4) & 0xf);

	/* window[17..18] is windata0, which the selected ternary rule fills
	 * from the packet (IP+8, masked to the protocol byte). It is a MATCH
	 * word, not an action field, so it is left to zx_pp_build_window_v4().
	 * An earlier revision wrote 0x10 into window[18] here, which put a
	 * constant into the TTL position of the first match word.
	 */
}

int zx_pp_build_window_ipv4(u32 w[ZX_PP_HASH_WORDS], u8 ingress, u8 egress,
			    u32 flow_id, u8 field, u8 proto,
			    const u8 sip[4], u16 sport,
			    const u8 dip[4], u16 dport)
{
	u8 b[ZX_PP_WINDOW_LEN] = { 0 };
	int ret;

	if (!w)
		return -EINVAL;
	zx_pp_fill_action(ingress, egress, flow_id, field, b);
	ret = zx_pp_build_window_v4(b, proto, sip, sport, dip, dport);
	if (ret)
		return ret;
	zx_pp_pack_words(b, w, ZX_PP_HASH_WORDS);
	return 0;
}

/* The IPv4 5-tuple ternary default rule, as tm_acl_fast_init (Ghidra 0x5e8e0)
 * builds it in a 68-byte buffer at sp+0x20 and writes with
 * cla_set_extra_rule_table at indices 0x90 and 0x91.
 *
 * Why this exists at all: the exact-match hash is not a standalone lookup.
 * The window's `field` is (extIdx << 4) | nibble, and that value is the INDEX
 * of a ternary extra_rule entry -- rule = extIdx * 16 + nibble. An exact-match
 * entry whose field points at an all-zero rule describes nothing, which is
 * why a flow could be installed, enabled and sprayed across all 512 slots and
 * still never match. The engine consults the ternary rule first.
 *
 * The buffer is transcribed from the function's own stores. The decompiler's
 * stack-slot NAMES are unreliable for this function, so the mapping from name
 * to byte offset was pinned against the disassembly rather than assumed:
 * `add r0,sp,#0x20` before the memset puts the entry base at sp+0x20, and the
 * extra_index call right after uses `add r1,sp,#0xc` with
 * `ldrh r3,[sp,#0x1c]` -- that halfword is the extra_index entry's word 4 at
 * its byte 0x10, so sp+0xc is that buffer's base and the decompiler's
 * uStack_b4 (= sp+0x1c) fixes the relation uStack_N = sp + (0xd0 - N).
 * Applying it, uStack_b0 is sp+0x20, i.e. entry byte 0, and every other slot
 * follows. `strb r10,[sp,#0x20]` with r10 = 8 independently confirms byte 0.
 *
 * Offsets below are byte offsets into the 68-byte entry.
 */
void zx_pp_build_extra_rule_v4(u32 w[ZX_PP_EXTRA_RULE_WORDS], bool pair)
{
	u8 b[ZX_PP_EXTRA_RULE_BYTES] = { 0 };
	u16 h;

	/* bytes 0x00..0x03 = 0x22038608. Byte 0 = 8 is `strb r10,[sp,#0x20]`;
	 * `bfi r2,r11,#7,#7` (r11 = 0xc) and `bfi lr,r0,#0xe,#7` (r0 = 0xe)
	 * build the rest, which is what the decompiler folds into the constant.
	 */
	b[0x00] = 0x08; b[0x01] = 0x86; b[0x02] = 0x03; b[0x03] = 0x22;

	/* bytes 0x04..0x07 = 0x000058a1: (1 & 0xfffe0007) | 0x58a0. */
	b[0x04] = 0xa1; b[0x05] = 0x58;

	/* bytes 0x10..0x13 = 0xf00ff000: low three bytes (0 & 0xfff) | 0xff000,
	 * top byte 0xf0 (the decompiler's CONCAT13(0xf0, ...)).
	 */
	b[0x11] = 0xf0; b[0x12] = 0x0f; b[0x13] = 0xf0;

	/* bytes 0x14..0x1b: the two all-ones words. */
	b[0x14] = b[0x15] = b[0x16] = b[0x17] = 0xff;
	b[0x18] = b[0x19] = b[0x1a] = b[0x1b] = 0xff;

	/* bytes 0x1c..0x1f = 0x0fffffff: (0 & 0xf0000fff) | 0xfffffff. */
	b[0x1c] = 0xff; b[0x1d] = 0xff; b[0x1e] = 0xff; b[0x1f] = 0x0f;

	/* bytes 0x3c..0x3f = 0x00092492: 0x2492, then & 0xffe0ffff | 0x90000. */
	b[0x3c] = 0x92; b[0x3d] = 0x24; b[0x3e] = 0x09;

	/* the halfword at 0x3a: (x & 0xfe0f) | 0x70. The second entry of the
	 * pair differs only in bit 9 (`uStack_76 |= 0x200` between the two
	 * cla_set_extra_rule_table calls).
	 */
	h = 0x0070;
	if (pair)
		h |= 0x0200;
	b[0x3a] = (u8)(h & 0xff);
	b[0x3b] = (u8)(h >> 8);

	zx_pp_pack_words(b, w, ZX_PP_EXTRA_RULE_WORDS);
}

