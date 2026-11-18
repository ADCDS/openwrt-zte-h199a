"""CLA exact-match hash: CRC, buckets, bank mapping, slot placement.

The hash decides which of the 512 exact-match slots the CLA engine looks in for
a given packet, so a driver that computes it wrongly installs entries that can
never match. Until now no C implementation existed at all: the only executable
reference was a Python script that reads the four polynomial tables out of the
vendor module.

These tests pin the C implementation against evidence that does not come from
it:

* the check value of each polynomial table. The vendor tables are constants in
  tm.ko; `CRC_32` over "123456789" with init 0 and no final XOR gives
  0x89a1897f / 0xc052a8c8 / 0x6c9f84a8 / 0x9601dda9 for selectors 0..3
  (logs/analysis-20261115/pp-cla-hash.md, "The CRC core").
* the three worked examples recorded from the decoded algorithm before this
  code existed (pp-cla-hash.md section 7): the all-zero key, key[0] = 1 and
  key[44] = 1, with both the per-way selectors and an all-selector-0 variant.
* the bank split of the 512 inner slots plus the 8-slot overflow scan
  (zx279128-pp.c zx_pp_tables[], cla_get_hash_table 0x5f20).

A test that only compared the C against the Python would prove nothing: both
could be wrong the same way. Every expected value below is transcribed from the
recorded evidence.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
ZTE = ROOT / 'files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte'
HASH_SOURCE = ZTE / 'zx279128-pp-hash.c'
PP_HEADER = ZTE / 'zx279128-pp.h'


def header_declarations():
    """The header's hash constants and structs, taken from the real header.

    The model strips #include, so these have to be supplied. Taking them from
    the header rather than restating them here is what stops the two drifting.
    """
    header = PP_HEADER.read_text()
    # every constant the shared layer and the flow path use, taken as a whole
    # rather than as a hand-picked subset that drifts every time one is added
    names = re.findall(r'^#define\s+(ZX_PP_\w+)\s+.*$', header, re.M)
    if len(names) < 10:
        raise AssertionError(f'too few ZX_PP constants in the header: {names}')
    lines = [re.search(r'^#define\s+' + name + r'\s+.*$', header, re.M).group()
             for name in names]
    structs = []
    for name in ('zx_pp_hash_cfg', 'zx_pp_hash_map'):
        found = re.search(r'^struct ' + name + r' \{.*?^\};', header, re.M | re.S)
        if not found:
            raise AssertionError(f'struct {name} not found in the header')
        structs.append(found.group())
    return '\n'.join(lines) + '\n' + '\n'.join(structs) + '\n'


PRELUDE = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
'''


def strip_includes(text):
    return re.sub(r'^#include[^\n]*\n', '', text, flags=re.M)


CASES = r'''
/* The check value of each polynomial over "123456789": init 0, no final XOR,
 * refin/refout false. These are the recorded values from pp-cla-hash.md
 * section 1, and they are what pins the four polynomial constants.
 */
static void t_check_values(void)
{
	const u8 s[9] = { '1','2','3','4','5','6','7','8','9' };

	assert(zx_pp_crc32(0, s, 9) == 0x89a1897fu);
	assert(zx_pp_crc32(1, s, 9) == 0xc052a8c8u);
	assert(zx_pp_crc32(2, s, 9) == 0x6c9f84a8u);
	assert(zx_pp_crc32(3, s, 9) == 0x9601dda9u);
	/* hash16 keeps the low 16 bits of exactly that CRC */
	assert((u16)zx_pp_crc32(0, s, 9) == 0x897f);
	assert((u16)zx_pp_crc32(1, s, 9) == 0xa8c8);
	assert((u16)zx_pp_crc32(2, s, 9) == 0x84a8);
	assert((u16)zx_pp_crc32(3, s, 9) == 0xdda9);
	/* the table's own first non-zero entry is the polynomial, so a single
	 * 0x01 byte yields it in full
	 */
	{
		const u8 one[1] = { 1 };

		assert(zx_pp_crc32(0, one, 1) == 0x04c11db7u);
		assert(zx_pp_crc32(1, one, 1) == 0x1edc6f41u);
		assert(zx_pp_crc32(2, one, 1) == 0xf4acfb13u);
		assert(zx_pp_crc32(3, one, 1) == 0x32583499u);
	}
	assert(zx_pp_crc32(4, s, 9) == 0);	/* out of range, total */
}

/* pp-cla-hash.md section 7, the three worked examples. Each is recorded with
 * the hash per selector and the resulting inner addresses.
 */
static void t_worked_examples(void)
{
	u16 bucket[4];
	struct zx_pp_hash_cfg cfg = { .usable = true };
	u8 zeros[45] = { 0 };
	u8 key0[45] = { 0 }, key44[45] = { 0 };
	unsigned i;

	/* key[0] = 1 (fed last) and key[44] = 1 (fed first) */
	key0[0] = 1;
	key44[44] = 1;

	/* All-zero key: h = 0 for every polynomial, because T[0] = 0. The four
	 * ways therefore land on 0, 256, 384 and 448 whatever the selectors.
	 */
	for (i = 0; i < 4; i++)
		assert(zx_pp_hash16(i, zeros) == 0);
	for (i = 0; i < 4; i++)
		cfg.inner[i] = i;
	assert(zx_pp_hash_buckets(&cfg, zeros, bucket) == 0);
	assert(bucket[0] == 0 && bucket[1] == 256 && bucket[2] == 384 && bucket[3] == 448);

	/* key[0] = 1: h = 0x1db7 / 0x6f41 / 0xfb13 / 0x3499. Per-way selectors
	 * give 183 / 321 / 403 / 473; all-selector-0 gives 183 / 311 / 439 / 503.
	 */
	assert(zx_pp_hash16(0, key0) == 0x1db7);
	assert(zx_pp_hash16(1, key0) == 0x6f41);
	assert(zx_pp_hash16(2, key0) == 0xfb13);
	assert(zx_pp_hash16(3, key0) == 0x3499);
	assert(zx_pp_hash_buckets(&cfg, key0, bucket) == 0);
	assert(bucket[0] == 183 && bucket[1] == 321 && bucket[2] == 403 && bucket[3] == 473);
	for (i = 0; i < 4; i++)
		cfg.inner[i] = 0;
	assert(zx_pp_hash_buckets(&cfg, key0, bucket) == 0);
	assert(bucket[0] == 183 && bucket[1] == 311 && bucket[2] == 439 && bucket[3] == 503);

	/* key[44] = 1: h = 0x28a8 / 0x7b4d / 0x0016 / 0x0151. All-selector-0
	 * gives 168 / 296 / 424 / 488 (the values the note records).
	 */
	assert(zx_pp_hash16(0, key44) == 0x28a8);
	assert(zx_pp_hash16(1, key44) == 0x7b4d);
	assert(zx_pp_hash16(2, key44) == 0x0016);
	assert(zx_pp_hash16(3, key44) == 0x0151);
	assert(zx_pp_hash_buckets(&cfg, key44, bucket) == 0);
	assert(bucket[0] == 168 && bucket[1] == 296 && bucket[2] == 424 && bucket[3] == 488);
}

/* Reverse feed matters: key[44] is fed first. Swapping the two ends must
 * change the hash, otherwise the direction is untested.
 */
static void t_reverse_feed(void)
{
	u8 key[45] = { 0 };
	u8 swapped[45] = { 0 };
	unsigned i;

	key[0] = 0x11;
	key[44] = 0x22;
	swapped[0] = 0x22;
	swapped[44] = 0x11;
	for (i = 0; i < 4; i++)
		assert(zx_pp_hash16(i, key) != zx_pp_hash16(i, swapped));
	/* key[44] is fed first and key[0] last, so moving a byte between the
	 * two ends is the same test stated per position: a single 0x01 at
	 * key[0] is one CRC step short of the polynomial, and at key[44] it is
	 * 44 bytes' worth of steps away.
	 */
	{
		u8 last[45] = { 0 }, first[45] = { 0 };

		last[0] = 1;
		first[44] = 1;
		for (i = 0; i < 4; i++)
			assert(zx_pp_hash16(i, last) != zx_pp_hash16(i, first));
	}
}

/* CRC is linear over GF(2) with init 0 and no final XOR: h(a ^ b) == h(a) ^
 * h(b). This is what makes a single-bit probe of the hardware identify where a
 * key field sits, so it is worth asserting rather than assuming.
 */
static void t_linear(void)
{
	u8 a[45], b[45], x[45];
	unsigned i, sel;

	for (i = 0; i < 45; i++) {
		a[i] = (u8)(i * 7 + 1);
		b[i] = (u8)(255 - i * 3);
		x[i] = (u8)(a[i] ^ b[i]);
	}
	for (sel = 0; sel < 4; sel++)
		assert(zx_pp_hash16(sel, x) == (u16)(zx_pp_hash16(sel, a) ^ zx_pp_hash16(sel, b)));
}

/* The bank split: 0..255 sel 2, 256..383 sel 3, 384..447 sel 4, 448..511
 * sel 5, 512..519 sel 6, in-bank address = global minus the bank base.
 */
static void t_bank_map(void)
{
	static const struct { u16 addr, sel, bank; } edge[] = {
		{ 0,   2, 0   }, { 255, 2, 255 },
		{ 256, 3, 0   }, { 383, 3, 127 },
		{ 384, 4, 0   }, { 447, 4, 63  },
		{ 448, 5, 0   }, { 511, 5, 63  },
		{ 512, 6, 0   }, { 519, 6, 7   },
	};
	unsigned int sel;
	u16 bank;
	unsigned i;

	for (i = 0; i < sizeof(edge) / sizeof(edge[0]); i++) {
		assert(zx_pp_hash_bank(edge[i].addr, &sel, &bank) == 0);
		assert(sel == edge[i].sel);
		assert(bank == edge[i].bank);
	}
	/* every address round-trips to a distinct (sel, bank) pair */
	{
		u8 seen[5][256];

		memset(seen, 0, sizeof(seen));
		for (i = 0; i < ZX_PP_HASH_SLOTS; i++) {
			assert(zx_pp_hash_bank((u16)i, &sel, &bank) == 0);
			assert(sel >= 2 && sel <= 6);
			assert(!seen[sel - 2][bank]);
			seen[sel - 2][bank] = 1;
		}
	}
	assert(zx_pp_hash_bank(ZX_PP_HASH_SLOTS, &sel, &bank) == -EINVAL);
	assert(zx_pp_hash_bank(0, NULL, &bank) == -EINVAL);
	assert(zx_pp_hash_bank(0, &sel, NULL) == -EINVAL);
}

/* Placement: the first free way wins, then the 512..519 scan.
 *
 * One key can occupy at most its four buckets plus the eight overflow slots:
 * the same key hashes to the same four addresses every time, so after those
 * are taken the only way left is the linear scan, and after 512..519 are taken
 * as well there is nowhere to put it.
 */
static void t_place(void)
{
	struct zx_pp_hash_cfg cfg = { .usable = true };
	struct zx_pp_hash_map *map;
	u8 key[45] = { 0 };
	u16 bucket[4], addr;
	unsigned i;

	map = calloc(1, sizeof(*map));
	assert(map);
	for (i = 0; i < 4; i++)
		cfg.inner[i] = i;
	assert(zx_pp_hash_buckets(&cfg, key, bucket) == 0);
	assert(bucket[0] == 0 && bucket[1] == 256 && bucket[2] == 384 && bucket[3] == 448);

	/* the four ways, in way order */
	for (i = 0; i < 4; i++) {
		assert(zx_pp_hash_place(&cfg, map, key, &addr) == 0);
		assert(addr == bucket[i]);
		assert(map->used[addr]);
	}
	/* all four ways taken: the overflow scan runs 512..519 in order */
	for (i = 0; i < ZX_PP_HASH_OVERFLOW; i++) {
		assert(zx_pp_hash_place(&cfg, map, key, &addr) == 0);
		assert(addr == ZX_PP_HASH_INNER_SLOTS + i);
	}
	/* 4 ways + 8 overflow slots is all one key can ever use */
	assert(zx_pp_hash_place(&cfg, map, key, &addr) == -ENOSPC);

	/* releasing a way reuses it ahead of the overflow slots */
	zx_pp_hash_release(map, bucket[1]);
	assert(zx_pp_hash_place(&cfg, map, key, &addr) == 0);
	assert(addr == bucket[1]);
	assert(zx_pp_hash_place(&cfg, map, key, &addr) == -ENOSPC);

	/* release everything: a fully used map is -ENOSPC, and releasing past the
	 * end is a no-op rather than a wild write.
	 */
	memset(map->used, 1, sizeof(map->used));
	assert(zx_pp_hash_place(&cfg, map, key, &addr) == -ENOSPC);
	zx_pp_hash_release(map, ZX_PP_HASH_SLOTS);
	zx_pp_hash_release(NULL, 0);
	free(map);
}

/* A configured outer table means mode 1, which is undecoded: placement must be
 * refused rather than computed from a formula that cannot be right.
 */
static void t_outer_refused(void)
{
	struct zx_pp_hash_cfg cfg = { .usable = false };
	struct zx_pp_hash_map *map = calloc(1, sizeof(*map));
	u8 key[45] = { 0 };
	u16 bucket[4], addr;
	unsigned i;

	assert(map);
	for (i = 0; i < 4; i++)
		cfg.inner[i] = i;
	assert(zx_pp_hash_buckets(&cfg, key, bucket) == -EOPNOTSUPP);
	assert(zx_pp_hash_place(&cfg, map, key, &addr) == -EOPNOTSUPP);
	assert(!map->used[0]);
	free(map);
}

/* A selector out of range cannot occur (they are two-bit fields), but the
 * function is total: it returns 0 rather than reading past its table.
 */
static void t_selector_bounds(void)
{
	u8 key[45] = { 0 };

	assert(zx_pp_hash16(4, key) == 0);
	assert(zx_pp_hash16(255, key) == 0);
}

/* The key builder, pinned against the bit-position table in docs/PP-KEY.md.
 *
 * Every assertion below names a position from that table. A transcription
 * error in the builder, or a drift in the documented layout, fails here rather
 * than producing an entry that silently never matches a packet.
 */
static void t_build_key(void)
{
	u8 window[ZX_PP_WINDOW_LEN];
	u8 key[ZX_PP_KEY_LEN];
	unsigned int j, b;

	/* ---- the scoping field is written rotated ------------------------ */
	memset(window, 0, sizeof(window));
	zx_pp_build_key(window, 0x4a, key);
	assert(key[0] == 0 && key[1] == 0);
	/* field = ((key[2] >> 7) & 1) | ((key[3] & 0x7f) << 1) */
	assert(key[3] == (0x4a >> 1));
	assert(((key[2] >> 7) & 1) == (0x4a & 1));
	assert((((key[2] >> 7) & 1) | ((key[3] & 0x7f) << 1)) == 0x4a);

	/* the four documented type nibbles */
	{
		static const struct { u8 nibble, type; } types[] = {
			{ 4, ZX_PP_KEY_TYPE_V4_ORIG }, { 0, ZX_PP_KEY_TYPE_V4_REPLY },
			{ 6, ZX_PP_KEY_TYPE_V6_ORIG }, { 2, ZX_PP_KEY_TYPE_V6_REPLY },
		};

		assert(ZX_PP_KEY_TYPE_V4_ORIG == 4 && ZX_PP_KEY_TYPE_V4_REPLY == 0);
		assert(ZX_PP_KEY_TYPE_V6_ORIG == 6 && ZX_PP_KEY_TYPE_V6_REPLY == 2);
		for (j = 0; j < 4; j++) {
			u8 field = (u8)((3 << 4) | types[j].type);

			zx_pp_build_key(window, field, key);
			assert((((key[2] >> 7) & 1) | ((key[3] & 0x7f) << 1)) == field);
			assert(key[3] == (field >> 1));
		}
	}

	/* ---- window[16] bit 5 lands at key[4] bit 0 ---------------------- */
	memset(window, 0, sizeof(window));
	window[16] = 0x20;		/* bit 5 */
	zx_pp_build_key(window, 0, key);
	assert((key[4] & 1) == 1);
	assert(key[4] == 0x01);

	/* ---- windata_j occupies key bits 33 + 16j .. 48 + 16j ------------- */
	/* Walk each word's sixteen bits and check the documented position. */
	for (j = 0; j < ZX_PP_WINDOW_WORDS; j++) {
		for (b = 0; b < 16; b++) {
			unsigned int p = 33 + 16 * j + b;
			unsigned int byte = p / 8, bit = p % 8;

			memset(window, 0, sizeof(window));
			memset(key, 0xa5, sizeof(key));	/* poison, then overwrite */
			if (b < 8)
				window[17 + 2 * j] = (u8)(1u << b);
			else
				window[18 + 2 * j] = (u8)(1u << (b - 8));
			zx_pp_build_key(window, 0, key);
			assert(((key[byte] >> bit) & 1) == 1);
			/* and no other bit of the packed region moved */
			{
				unsigned int q, set = 0;

				for (q = 32; q < ZX_PP_KEY_LEN * 8; q++)
					if ((key[q / 8] >> (q % 8)) & 1)
						set++;
				assert(set == 1);
			}
		}
	}

	/* ---- the closed form: word j starts at key bit 33 + 16j ---------- */
	/* A word of all ones must set exactly its sixteen bits. */
	for (j = 0; j < ZX_PP_WINDOW_WORDS; j++) {
		unsigned int p;

		memset(window, 0, sizeof(window));
		window[17 + 2 * j] = 0xff;
		window[18 + 2 * j] = 0xff;
		zx_pp_build_key(window, 0, key);
		for (p = 32; p < ZX_PP_KEY_LEN * 8; p++) {
			unsigned int want = (p >= 33 + 16 * j && p < 49 + 16 * j);

			assert((unsigned)((key[p / 8] >> (p % 8)) & 1) == want);
		}
	}

	/* ---- key[44] bits 7:1 are undefined by the repack: zeroed -------- */
	memset(window, 0, sizeof(window));
	memset(key, 0xff, sizeof(key));
	zx_pp_build_key(window, 0, key);
	assert(key[44] == 0);

	/* ---- the last word's top bit is key[44] bit 0 -------------------- */
	memset(window, 0, sizeof(window));
	window[18 + 2 * (ZX_PP_WINDOW_WORDS - 1)] = 0x80;	/* bit 15 of word 19 */
	zx_pp_build_key(window, 0, key);
	assert((key[44] & 1) == 1);
	assert(key[44] == 0x01);
}

/* The key builder and the CRC together: a window the driver constructs must
 * produce a bucket, and the same window with a different scoping field must
 * land somewhere else (that is what makes ORIGINAL and REPLY separate).
 */
static void t_key_then_bucket(void)
{
	struct zx_pp_hash_cfg cfg = { .usable = true };
	u8 window[ZX_PP_WINDOW_LEN];
	u8 key[ZX_PP_KEY_LEN];
	u16 orig[4], reply[4];
	unsigned i;

	for (i = 0; i < 4; i++)
		cfg.inner[i] = i;
	/* a plausible window: some tuple bytes in the match words */
	memset(window, 0, sizeof(window));
	for (i = 0; i < ZX_PP_WINDOW_LEN; i++)
		window[i] = (u8)(i * 5 + 1);

	zx_pp_build_key(window, (u8)((2 << 4) | ZX_PP_KEY_TYPE_V4_ORIG), key);
	assert(zx_pp_hash_buckets(&cfg, key, orig) == 0);
	zx_pp_build_key(window, (u8)((2 << 4) | ZX_PP_KEY_TYPE_V4_REPLY), key);
	assert(zx_pp_hash_buckets(&cfg, key, reply) == 0);

	/* same window, different direction: the buckets must differ, because
	 * the scoping field is inside the hashed key.
	 */
	assert(memcmp(orig, reply, sizeof(orig)) != 0);

	/* and the same inputs twice give the same answer */
	zx_pp_build_key(window, (u8)((2 << 4) | ZX_PP_KEY_TYPE_V4_ORIG), key);
	{
		u16 again[4];

		assert(zx_pp_hash_buckets(&cfg, key, again) == 0);
		assert(memcmp(orig, again, sizeof(orig)) == 0);
	}
}

int main(int argc, char **argv)
{
	static const struct { const char *name; void (*fn)(void); } cases[] = {
		{ "check_values", t_check_values },
		{ "worked_examples", t_worked_examples },
		{ "reverse_feed", t_reverse_feed },
		{ "linear", t_linear },
		{ "bank_map", t_bank_map },
		{ "place", t_place },
		{ "outer_refused", t_outer_refused },
		{ "selector_bounds", t_selector_bounds },
		{ "build_key", t_build_key },
		{ "key_then_bucket", t_key_then_bucket },
	};
	unsigned i;

	assert(argc == 2);
	for (i = 0; i < sizeof(cases) / sizeof(cases[0]); i++)
		if (!strcmp(argv[1], cases[i].name)) {
			cases[i].fn();
			printf("PASS %s\n", cases[i].name);
			return 0;
		}
	return 2;
}
'''


class PpHashModelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        root = Path(cls.directory.name)
        source, cls.executable = root / 'hash.c', root / 'hash'
        source.write_text(PRELUDE + header_declarations() +
                          strip_includes(HASH_SOURCE.read_text()) + CASES)
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
        run = subprocess.run([str(self.executable), name], capture_output=True,
                             text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertIn(f'PASS {name}', run.stdout)

    def test_polynomial_check_values_match_the_vendor_tables(self):
        self.run_case('check_values')

    def test_the_recorded_worked_examples_reproduce(self):
        self.run_case('worked_examples')

    def test_key_bytes_are_fed_in_reverse(self):
        self.run_case('reverse_feed')

    def test_the_crc_is_linear_over_gf2(self):
        self.run_case('linear')

    def test_global_hash_addresses_map_to_the_five_banks(self):
        self.run_case('bank_map')

    def test_placement_takes_the_first_free_way_then_the_overflow_scan(self):
        self.run_case('place')

    def test_a_configured_outer_table_refuses_placement(self):
        self.run_case('outer_refused')

    def test_an_out_of_range_selector_is_total(self):
        self.run_case('selector_bounds')

    def test_the_key_layout_matches_the_documented_bit_table(self):
        self.run_case('build_key')

    def test_original_and_reply_hash_to_different_buckets(self):
        self.run_case('key_then_bucket')


class PpHashSourcePolicyTests(unittest.TestCase):
    def test_no_polynomial_table_is_copied_into_the_tree(self):
        """The CRC is bitwise on purpose: four 1 KiB tables are not added."""
        text = HASH_SOURCE.read_text()
        # no 256-entry constant array anywhere in the file
        self.assertNotRegex(text, r'\[\s*256\s*\]')
        self.assertEqual(len(re.findall(r'^static const u32 zx_pp_hash_poly\[', text, re.M)), 1)
        for poly in ('0x04c11db7', '0x1edc6f41', '0xf4acfb13', '0x32583499'):
            self.assertIn(poly, text)

    def test_the_key_is_a_caller_buffer_not_built_here(self):
        """The 45-byte layout is still unknown; this file must not guess it."""
        text = HASH_SOURCE.read_text()
        for name in ('zx_pp_hash16', 'zx_pp_hash_buckets', 'zx_pp_hash_place'):
            self.assertIn(f'{name}(', text)
        # no ethernet/IP header type is referenced, so nothing here reads a packet
        for forbidden in ('sk_buff', 'iphdr', 'ethhdr', 'tcphdr', 'udphdr', 'be32', 'ntohs'):
            self.assertNotIn(forbidden, text)

    def test_occupancy_is_the_drivers_own_map(self):
        """The hardware exposes no occupancy byte, so a map has to be kept."""
        header = PP_HEADER.read_text()
        self.assertIn('struct zx_pp_hash_map', header)
        self.assertIn('u8 used[ZX_PP_HASH_SLOTS];', header)
        text = HASH_SOURCE.read_text()
        self.assertIn('map->used[', text)


if __name__ == '__main__':
    unittest.main()
