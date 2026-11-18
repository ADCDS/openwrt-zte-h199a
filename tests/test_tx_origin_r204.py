"""Offline R204 tests: execute actual driver C, never a Python cursor model.

Run: python3 tests/test_tx_origin_r204.py
Requires Python 3 and a HOST cc (HOSTCC, default cc). Uses TemporaryDirectory only;
no kernel build, devices, hardware, network, source rewrites, or sibling imports.
The full actual zx_eth/queue declarations, helper, LOCAL declaration, and probe
control-flow slice from if (zx_skip_dp_init) through ASSIGN are compiled verbatim.
Kernel types/MMIO/logging/maps/warm detection/datapath init are boundary stubs.
These tests prove software selection/order, not hardware semantics or SMP safety.
The archive and restored source must BOTH retain the frozen pre-R204 SHA below.
"""
from collections import Counter
from pathlib import Path
import hashlib
import os
import re
import shlex
import subprocess
import tempfile
import unittest
from bench_artifacts import needs_artifacts

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c'
ARCHIVE = ROOT / 'artifacts/r206/validated-driver.c'
REFERENCE = ROOT / 'artifacts/r204/reference-driver.c'
REFERENCE_SHA256 = '10f66ed8625f9e376043c866725664a060bbc3ed85e26a46770c1c0e5f3fbf75'
OLD_ASSIGN = b'\tze->tx_next = (readl(ze->tmq + TMQ_TXIDX) & 0xffff) % RING_ENTRIES;\n'
KINDS = ('HELPER', 'LOCAL', 'INITIALIZED', 'ASSIGN')
C_LEX = re.compile(
    r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|'
    r'[A-Za-z_]\w*|0[xX][0-9a-fA-F]+[uUlL]*|\d+[uUlL]*|'
    r'>>=|<<=|->|\+\+|--|&&|\|\||==|!=|<=|>=|<<|>>|\+=|-=|\*=|/=|&=|\|=|\^=|\S',
    re.S)
EXPECTED = {
    'HELPER': r'''
static void zx_tx_origin_init(struct zx_eth *ze, bool datapath_initialized)
{
    u32 raw = readl(ze->tmq + TMQ_TXIDX);
    u32 inherited = (raw & 0xffff) % RING_ENTRIES;
    ze->tx_next = datapath_initialized ? 0 : inherited;
    dev_info(ze->dev,
        "TXORIGIN_R204 raw=%08x inherited=%u selected=%u initialized=%u slot_mode=%u\n",
        raw, inherited, ze->tx_next, datapath_initialized ? 1u : 0u, zx_tx_slot_mode);
}
''',
    'LOCAL': 'bool datapath_initialized = false;',
    'INITIALIZED': 'datapath_initialized = true;',
    'ASSIGN': 'zx_tx_origin_init(ze, datapath_initialized);',
}


def require(condition, message):
    # Do not use Python assert: validation must also work under python -O.
    if not condition:
        raise AssertionError(message)


def lex(text):
    return [m for m in C_LEX.finditer(text) if not m.group().startswith(('/*', '//'))]


def tokens(text):
    return [m.group() for m in lex(text)]


def index_once(body, snippet):
    needle = tokens(snippet)
    found = [i for i in range(len(body) - len(needle) + 1)
             if body[i:i + len(needle)] == needle]
    require(len(found) == 1, f'Expected exactly one executable {snippet!r}: {found}')
    return found[0]


def function(text, name):
    """Extract exact function text, ignoring braces in comments and strings."""
    ms = lex(text)
    ts = [m.group() for m in ms]
    found = []
    for i, token in enumerate(ts[:-1]):
        if token != name or ts[i + 1] != '(':
            continue
        depth, j = 1, i + 2
        while depth and j < len(ts):
            depth += (ts[j] == '(') - (ts[j] == ')')
            j += 1
        if depth or j >= len(ts) or ts[j] != '{':
            continue
        depth, k = 1, j + 1
        while depth and k < len(ts):
            depth += (ts[k] == '{') - (ts[k] == '}')
            k += 1
        require(depth == 0, f'Unterminated function {name}')
        start = text.rfind('\n', 0, ms[i].start()) + 1
        found.append(text[start:ms[k - 1].end()])
    require(len(found) == 1, f'Expected unique definition of {name}')
    return found[0]


def marker(kind, edge):
    indent = '' if kind == 'HELPER' else '\t'
    return f'{indent}/* ZX_TX_ORIGIN_R204_{kind}_{edge} */\n'.encode()


def blocks(data):
    """Fail closed: exactly four ordered, non-nested, whole-line marker pairs."""
    allowed = [f'ZX_TX_ORIGIN_R204_{kind}_{edge}'.encode()
               for kind in KINDS for edge in ('BEGIN', 'END')]
    seen = re.findall(rb'ZX_TX_ORIGIN_[A-Za-z0-9_]*', data)
    require(seen == allowed, 'Missing, duplicate, reordered, or unknown TX origin marker')
    require(data.count(b'ZX_TX_ORIGIN') == 8, 'Malformed TX origin marker stem')
    result = {}
    previous_end = -1
    for kind in KINDS:
        begin, end = marker(kind, 'BEGIN'), marker(kind, 'END')
        starts = list(re.finditer(rb'^' + re.escape(begin), data, re.M))
        ends = list(re.finditer(rb'^' + re.escape(end), data, re.M))
        require(len(starts) == len(ends) == 1, f'{kind}: markers must be exact full lines')
        start, body_start = starts[0].span()
        body_end, stop = ends[0].span()
        require(previous_end < start < body_start <= body_end < stop,
                f'{kind}: nested or reversed markers')
        body = data[body_start:body_end]
        require(not re.search(rb'ZX_[A-Z0-9_]+_(?:BEGIN|END)\b', body),
                f'{kind}: foreign/future marker hidden inside removed region')
        require(tokens(body.decode('utf-8')) == tokens(EXPECTED[kind]),
                f'{kind}: executable delta differs from the exact authorized change')
        result[kind] = (start, stop, body)
        previous_end = stop
    return result


def validate_and_restore(data, reference):
    """Check new code AND placement, then restore without normalizing any bytes."""
    require(hashlib.sha256(reference).hexdigest() == REFERENCE_SHA256,
            'Archived reference differs from frozen 10f SHA; do not relax the digest')
    parsed = blocks(data)
    helper_start, helper_end, _ = parsed['HELPER']
    require(data[max(0, helper_start - 2):helper_start] == b'\n\n',
            'Helper must retain the existing preceding blank line')
    require(data[helper_end:].startswith(b'\nstatic int zx_eth_probe('),
            'Helper must immediately precede probe with exactly one following blank line')
    text = data.decode('utf-8')
    probe_text = function(text, 'zx_eth_probe')
    probe_start = text.index(probe_text)
    # ASCII before this point is NOT assumed: source includes UTF-8 comments.
    probe_byte_start = len(text[:probe_start].encode('utf-8'))
    probe_byte_end = probe_byte_start + len(probe_text.encode('utf-8'))
    for kind in ('LOCAL', 'INITIALIZED', 'ASSIGN'):
        start, stop, _ = parsed[kind]
        require(probe_byte_start < start < stop < probe_byte_end,
                f'{kind}: not wholly inside probe')
    local_start, local_end, _ = parsed['LOCAL']
    require(data[:local_start].endswith(b'\tu32 rxb, txb;\n') and
            data[local_end:].startswith(b'\tint i;\n\tint ret;\n'),
            'Local flag must be in the exact probe declaration slot')
    init_start, init_end, _ = parsed['INITIALIZED']
    guard_tail = (b'\tif (readl(ze->tmd + TMD_GO) & 1)\n'
                  b'\t\treturn dev_err_probe(dev, -EBUSY, '
                  b'"descriptor return busy after initialization\\n");\n')
    require(data[:init_start].endswith(guard_tail) and
            data[init_end:].startswith(b'warm:\n'),
            'Initialized flag must follow the complete busy guard and precede warm label')
    restored = data
    for kind in reversed(KINDS):
        start, stop, _ = parsed[kind]
        replacement = OLD_ASSIGN if kind == 'ASSIGN' else b''
        if kind == 'HELPER':
            stop += 1  # Remove the added following blank line, not the prior one.
        restored = restored[:start] + replacement + restored[stop:]
    require(hashlib.sha256(restored).hexdigest() == REFERENCE_SHA256,
            'Restored source differs from frozen 10f SHA; non-R204 change or wrong placement')
    require(restored == reference, 'Restored bytes differ from archived reference')
    return restored


def exact_struct(text, name):
    found = list(re.finditer(r'^struct ' + re.escape(name) + r' \{.*?^\};', text, re.M | re.S))
    require(len(found) == 1, f'Missing unique actual struct {name}')
    return found[0].group()


def exact_enum(text, name):
    found = list(re.finditer(r'^enum ' + re.escape(name) + r' \{.*?^\};', text, re.M | re.S))
    require(len(found) == 1, f'Missing unique actual enum {name}')
    return found[0].group()


def exact_define(text, name):
    starts = list(re.finditer(r'^#define[ \t]+' + re.escape(name) + r'[ \t]+', text, re.M))
    require(len(starts) == 1, f'Missing unique driver constant {name}')
    start = starts[0].start()
    end = text.index('\n', start) + 1
    # TMQ_TXIDX/TMQ_TXRING have multi-line comments; retain them verbatim.
    while text[start:end].count('/*') > text[start:end].count('*/'):
        end = text.index('\n', end) + 1
    return text[start:end]


def probe_slice(data):
    parsed = blocks(data)
    text = data.decode('utf-8')
    probe = function(text, 'zx_eth_probe')
    starts = [text for text in ('\tif (zx_skip_dp_init) {',
              '\tif (IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG) && zx_skip_dp_init) {') if text in probe]
    require(len(starts) == 1, 'Missing unique skip branch')
    start_text = starts[0]
    start = data.index(start_text.encode(), parsed['LOCAL'][1])
    return data[start:parsed['ASSIGN'][1]].decode('utf-8')


HEADERS = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
typedef unsigned long spinlock_t;
typedef uint32_t phys_addr_t;
typedef int phy_interface_t;
#define __iomem
#define ETH_ALEN 6
#define SZ_2K 2048
#define CONFIG_ZX279128_ETH_DEBUG 1
#define IS_ENABLED(option) (option)
struct device { u32 cookie; };
struct napi_struct { unsigned char sentinel[32]; };
struct delayed_work { unsigned char sentinel[48]; };
struct timer_list { unsigned char sentinel[32]; };
'''

BOUNDARIES = r'''
/* Fake kernel types do not reproduce the target ABI. The actual complete driver
 * structs are used above, so every driver member and host padding is guarded. */
struct envelope {
    unsigned char before[64];
    struct zx_eth ze;
    unsigned char after[64];
};
static struct envelope box, origin_before;
static struct device device;
static unsigned char tmq[1024], tmc[1024], tmd[1024];
static unsigned char mapping[4][64];
static unsigned int zx_tx_slot_mode;
static bool zx_skip_dp_init, zx_force_dp_init;
static bool probe_running, detected_warm;
static int init_result, failed_mapping;
static u32 live_raw, after_init_raw, live_rxb, live_txb, after_init_rxb, after_init_txb;
static u32 pending[ZX_RX_QUEUES], busy;
static unsigned tx_reads, origin_logs, all_reads, all_logs, error_logs;
static unsigned init_calls, warm_calls, maps, pending_reads[ZX_RX_QUEUES];
static unsigned busy_reads, rxbase_reads, txbase_reads;
static unsigned skip_logs, warm_logs, cold_logs, ring_logs;
static u32 logged_raw, logged_inherited, logged_selected, logged_initialized, logged_mode;
static int error_code;
static char origin_text[256], error_text[128];
static const char origin_format[] =
    "TXORIGIN_R204 raw=%08x inherited=%u selected=%u initialized=%u slot_mode=%u\n";
static unsigned long helper_cases, probe_cases;
#define INITIAL_CURSOR 0xdeadbeefu

static unsigned pending_total(void)
{
    unsigned n = 0;
    for (unsigned i = 0; i < ZX_RX_QUEUES; i++) n += pending_reads[i];
    return n;
}

static void check_backings(void)
{
    const unsigned char *regions[] = {tmq, tmc, tmd, &mapping[0][0]};
    const size_t sizes[] = {sizeof(tmq), sizeof(tmc), sizeof(tmd), sizeof(mapping)};
    for (unsigned r = 0; r < 4; r++)
        for (size_t j = 0; j < sizes[r]; j++) assert(regions[r][j] == 0xa7);
    assert(device.cookie == 0x204cafeu);
}

static void check_only_cursor(const struct envelope *before, u32 selected)
{
    struct envelope expected;
    memcpy(&expected, before, sizeof(expected));
    expected.ze.tx_next = selected;
    assert(memcmp(&box, &expected, sizeof(box)) == 0);
}

static u32 readl(const void *address)
{
    all_reads++;
    if (address == tmq + TMQ_TXIDX) {
        assert(box.ze.tmq == tmq);
        assert(++tx_reads == 1 && origin_logs == 0);
        assert(box.ze.tx_next == INITIAL_CURSOR);
        if (probe_running) {
            assert(maps == 3 && failed_mapping == 0);
            assert(box.ze.bufs && box.ze.bufs2 && box.ze.ring && box.ze.txring);
            assert(live_rxb == 0x41a00000 && live_txb == 0x41c00000);
            if (init_calls) {
                assert(init_calls == 1 && init_result == 0);
                assert(pending_total() == ZX_RX_QUEUES && busy_reads == 1);
                assert(!(busy & 1));
            }
        }
        memcpy(&origin_before, &box, sizeof(box));
        return live_raw;
    }
    assert(probe_running);  /* Helper must read exactly TMQ + 0x6c, nowhere else. */
    for (unsigned i = 0; i < ZX_RX_QUEUES; i++) {
        if (address == tmq + TMQ_PENDING + i * 4) {
            assert(init_calls == 1 && init_result == 0 && busy_reads == 0);
            assert(pending_total() == i && ++pending_reads[i] == 1);
            return pending[i];
        }
    }
    if (address == tmd + TMD_GO) {
        assert(init_calls == 1 && init_result == 0);
        assert(pending_total() == ZX_RX_QUEUES && ++busy_reads == 1);
        return busy;
    }
    if (address == tmc + TMC_RING_BASE) { rxbase_reads++; return live_rxb; }
    if (address == tmq + TMQ_TXRING) { txbase_reads++; return live_txb; }
    fprintf(stderr, "Unexpected MMIO address %p\n", address);
    abort();
}

static void dev_info(struct device *dev, const char *fmt, ...)
    __attribute__((format(printf, 2, 3)));
static void dev_info(struct device *dev, const char *fmt, ...)
{
    va_list ap, copy;
    assert(dev == &device);
    all_logs++;
    va_start(ap, fmt);
    if (strcmp(fmt, origin_format) == 0) {
        assert(++origin_logs == 1 && tx_reads == 1);
        va_copy(copy, ap);
        logged_raw = va_arg(copy, unsigned int);
        logged_inherited = va_arg(copy, unsigned int);
        logged_selected = va_arg(copy, unsigned int);
        logged_initialized = va_arg(copy, unsigned int);
        logged_mode = va_arg(copy, unsigned int);
        va_end(copy);
        int n = vsnprintf(origin_text, sizeof(origin_text), fmt, ap);
        assert(n > 0 && (size_t)n < sizeof(origin_text));
        check_only_cursor(&origin_before, logged_selected);
    } else if (strcmp(fmt, "datapath init SKIPPED (skip_dp_init=1) - attaching\n") == 0) {
        assert(probe_running && zx_skip_dp_init && ++skip_logs == 1);
    } else if (strcmp(fmt, "datapath warm (rx ring %08x tx ring %08x) - init skipped\n") == 0) {
        assert(probe_running && !zx_skip_dp_init && !zx_force_dp_init && detected_warm);
        assert(++warm_logs == 1);
        assert(va_arg(ap, unsigned int) == live_rxb);
        assert(va_arg(ap, unsigned int) == live_txb);
    } else if (strcmp(fmt, "datapath init at probe (cold)\n") == 0) {
        assert(probe_running && !zx_skip_dp_init && ++cold_logs == 1);
    } else if (strcmp(fmt, "rx ring=%08x tx ring=%08x\n") == 0) {
        assert(probe_running && maps == 3 && ++ring_logs == 1 && tx_reads == 0);
        assert(va_arg(ap, unsigned int) == live_rxb);
        assert(va_arg(ap, unsigned int) == live_txb);
    } else {
        fprintf(stderr, "Unexpected dev_info format: %s\n", fmt);
        abort();
    }
    va_end(ap);
}

static int dev_err_probe(struct device *dev, int error, const char *fmt, ...)
    __attribute__((format(printf, 3, 4)));
static int dev_err_probe(struct device *dev, int error, const char *fmt, ...)
{
    va_list ap;
    assert(probe_running && dev == &device && error != 0);
    assert(++error_logs == 1 && tx_reads == 0 && origin_logs == 0);
    error_code = error;
    va_start(ap, fmt);
    int n = vsnprintf(error_text, sizeof(error_text), fmt, ap);
    va_end(ap);
    assert(n > 0 && (size_t)n < sizeof(error_text));
    return error;
}

static bool zx_datapath_warm(struct zx_eth *ze)
{
    assert(probe_running && ze == &box.ze && !zx_skip_dp_init && !zx_force_dp_init);
    assert(++warm_calls == 1 && init_calls == 0);
    return detected_warm;
}

static int zx_eth_datapath_init(struct zx_eth *ze)
{
    assert(probe_running && ze == &box.ze && !zx_skip_dp_init);
    assert(zx_force_dp_init || !detected_warm);
    assert(++init_calls == 1 && tx_reads == 0 && cold_logs == 1);
    if (init_result == 0) {
        /* Simulate reset changing the registers: constructor must sample AFTER. */
        live_raw = after_init_raw;
        live_rxb = after_init_rxb;
        live_txb = after_init_txb;
    }
    return init_result;
}

static void *devm_ioremap_wc(struct device *dev, u32 physical, size_t size)
{
    assert(probe_running && dev == &device && tx_reads == 0);
    assert(rxbase_reads && txbase_reads);
    assert(live_rxb == 0x41a00000 && live_txb == 0x41c00000);
    unsigned which = ++maps;
    assert(which >= 1 && which <= 3);
    switch (which) {
    case 1: assert(physical == live_rxb && size == ZX_RX_MAP_SIZE); break;
    case 2: assert(physical == live_txb && size == RING_ENTRIES * DESC_SIZE); break;
    case 3: assert(physical == 0x41400000 && size == BUF2_COUNT * BUF_SIZE); break;
    default: abort();
    }
    return (int)which == failed_mapping ? NULL : mapping[which - 1];
}
'''

CASES = r'''
static void prepare(unsigned mode)
{
    memset(&box, 0x6d, sizeof(box));
    memset(tmq, 0xa7, sizeof(tmq));
    memset(tmc, 0xa7, sizeof(tmc));
    memset(tmd, 0xa7, sizeof(tmd));
    memset(mapping, 0xa7, sizeof(mapping));
    device.cookie = 0x204cafeu;
    box.ze.dev = &device;
    box.ze.tmq = tmq;
    box.ze.tmc = tmc;
    box.ze.tmd = tmd;
    box.ze.bufs = mapping[3];
    box.ze.ddr_phys = 0x41000000;  /* the board DT's memory-region (test_eth_memory_region.py) */
    box.ze.bufs2 = box.ze.ring = box.ze.txring = NULL;
    box.ze.dp_inited = false;
    box.ze.rx_seed_eligible = false;
    box.ze.tx_next = INITIAL_CURSOR;
    zx_tx_slot_mode = mode;
    zx_skip_dp_init = zx_force_dp_init = detected_warm = probe_running = false;
    init_result = failed_mapping = error_code = 0;
    live_raw = 0x9123f7abu;
    after_init_raw = 0xa5b6f345u;
    live_rxb = after_init_rxb = 0x41a00000;
    live_txb = after_init_txb = 0x41c00000;
    memset(pending, 0, sizeof(pending));
    memset(pending_reads, 0, sizeof(pending_reads));
    busy = 0;
    tx_reads = origin_logs = all_reads = all_logs = error_logs = 0;
    init_calls = warm_calls = maps = busy_reads = rxbase_reads = txbase_reads = 0;
    skip_logs = warm_logs = cold_logs = ring_logs = 0;
    logged_raw = logged_inherited = logged_selected = logged_initialized = logged_mode = ~0u;
    memset(origin_text, 0, sizeof(origin_text));
    memset(error_text, 0, sizeof(error_text));
}

static void expect_origin(u32 raw, bool initialized, unsigned mode)
{
    /* Independent C test oracle, not substituted driver code. */
    unsigned inherited = (uint16_t)raw % 1024u;
    unsigned selected = initialized ? 0u : inherited;
    char expected[256];
    int n = snprintf(expected, sizeof(expected),
        "TXORIGIN_R204 raw=%08x inherited=%u selected=%u initialized=%u slot_mode=%u\n",
        raw, inherited, selected, initialized ? 1u : 0u, mode);
    assert(n > 0 && (size_t)n < sizeof(expected));
    assert(tx_reads == 1 && origin_logs == 1);
    assert(logged_raw == raw && logged_inherited == inherited);
    assert(logged_selected == selected && box.ze.tx_next == selected);
    assert(logged_initialized == (initialized ? 1u : 0u));
    assert(logged_mode == mode && zx_tx_slot_mode == mode);
    assert(strcmp(origin_text, expected) == 0);
    assert(origin_text[strlen(origin_text) - 1] == '\n');
    check_only_cursor(&origin_before, selected);
}

static void helper_case(u32 raw, bool initialized, unsigned mode)
{
    struct envelope before;
    /* Reuse initialized sentinels for sweep speed, reset all helper observables. */
    assert(!probe_running);
    box.ze.tx_next = INITIAL_CURSOR;
    live_raw = raw;
    zx_tx_slot_mode = mode;
    tx_reads = origin_logs = all_reads = all_logs = 0;
    memcpy(&before, &box, sizeof(box));
    zx_tx_origin_init(&box.ze, initialized);
    expect_origin(raw, initialized, mode);
    check_only_cursor(&before, initialized ? 0 : (uint16_t)raw % 1024u);
    assert(all_reads == 1 && all_logs == 1);
    assert(init_calls == 0 && warm_calls == 0 && maps == 0 && error_logs == 0);
    helper_cases++;
}

static u32 rng = 0x2045eedu;
static u32 random32(void)
{
    rng ^= rng << 13;
    rng ^= rng >> 17;
    rng ^= rng << 5;
    return rng;
}

static void helper_sweep(void)
{
    const u32 high[] = {0x5a5a0000u, 0xffff0000u};
    prepare(0);
    for (unsigned h = 0; h < 2; h++)
        for (u32 low = 0; low < 65536u; low++)
            for (unsigned flag = 0; flag < 2; flag++)
                for (unsigned mode = 0; mode < 3; mode++)
                    helper_case(high[h] | low, flag != 0, mode);
    assert(helper_cases == 786432ul);
    check_backings();
}

static void helper_random(void)
{
    prepare(0);
    rng = 0x2045eedu;
    for (unsigned i = 0; i < 16384; i++) {
        u32 raw = random32();
        for (unsigned flag = 0; flag < 2; flag++)
            for (unsigned mode = 0; mode < 3; mode++)
                helper_case(raw, flag != 0, mode);
    }
    assert(helper_cases == 98304ul);
    check_backings();
}

static void helper_high_bits(void)
{
    const u32 low[] = {0, 1, 1023, 1024, 1025, 32767, 32768, 65535};
    prepare(0);
    /* Every HIGH half too: ensures it is logged raw but cannot select the slot. */
    for (u32 high = 0; high < 65536u; high++)
        for (unsigned l = 0; l < sizeof(low) / sizeof(low[0]); l++)
            for (unsigned flag = 0; flag < 2; flag++)
                helper_case((high << 16) | low[l], flag != 0, high % 3u);
    assert(helper_cases == 1048576ul);
    check_backings();
}

enum branch { COLD, WARM, SKIP };
struct scenario {
    bool skip, force, warm;
    enum branch branch;
    unsigned detectors;
};
/* Explicit expectations for every force/skip/detector combination. */
static const struct scenario scenarios[] = {
    {false, false, false, COLD, 1},
    {false, false, true,  WARM, 1},
    {false, true,  false, COLD, 0},
    {false, true,  true,  COLD, 0},
    {true,  false, false, SKIP, 0},
    {true,  false, true,  SKIP, 0},
    {true,  true,  false, SKIP, 0},
    {true,  true,  true,  SKIP, 0},
};
#define SCENARIOS (sizeof(scenarios) / sizeof(scenarios[0]))

static void setup_scenario(unsigned s, unsigned mode)
{
    const struct scenario *c = &scenarios[s];
    prepare(mode);
    probe_running = true;
    zx_skip_dp_init = c->skip;
    zx_force_dp_init = c->force;
    detected_warm = c->warm;
}

static int run_probe(unsigned s)
{
    const struct scenario *c = &scenarios[s];
    int ret = extracted_probe(&box.ze);
    assert(warm_calls == c->detectors);
    assert(init_calls == (unsigned)(c->branch == COLD));
    assert(skip_logs == (unsigned)(c->branch == SKIP));
    assert(warm_logs == (unsigned)(c->branch == WARM));
    assert(cold_logs == (unsigned)(c->branch == COLD));
    assert(box.ze.rx_seed_eligible == (c->branch == WARM));
    assert(box.ze.dp_inited == (c->branch != COLD || init_result == 0));
    assert(zx_skip_dp_init == c->skip && zx_force_dp_init == c->force);
    assert(detected_warm == c->warm);
    check_backings();
    probe_cases++;
    return ret;
}

static void expect_success(unsigned s, unsigned mode)
{
    const struct scenario *c = &scenarios[s];
    assert(run_probe(s) == 0);
    assert(maps == 3 && error_logs == 0 && ring_logs == 1);
    assert(rxbase_reads == (c->branch == WARM ? 2u : 1u));
    assert(txbase_reads == rxbase_reads);
    assert(pending_total() == (c->branch == COLD ? 8u : 0u));
    assert(busy_reads == (unsigned)(c->branch == COLD));
    assert(all_reads == pending_total() + busy_reads + rxbase_reads + txbase_reads + 1);
    assert(all_logs == 3);  /* branch + ring bases + origin */
    assert(box.ze.rx_ring_phys == 0x41a00000 && box.ze.tx_ring_phys == 0x41c00000);
    assert(box.ze.ring == mapping[0] && box.ze.txring == mapping[1]);
    assert(box.ze.bufs2 == mapping[2] && box.ze.bufs == mapping[3]);
    expect_origin(live_raw, c->branch == COLD, mode);
}

static void expect_failure(unsigned s, unsigned mode, int code, const char *message)
{
    assert(run_probe(s) == code);
    assert(box.ze.tx_next == INITIAL_CURSOR);
    assert(tx_reads == 0 && origin_logs == 0 && origin_text[0] == 0);
    assert(ring_logs == 0 && all_logs == 1);
    assert(all_reads == pending_total() + busy_reads + rxbase_reads + txbase_reads);
    assert(zx_tx_slot_mode == mode);
    if (message) {
        assert(error_logs == 1 && error_code == code);
        assert(strcmp(error_text, message) == 0);
    } else {
        assert(error_logs == 0 && error_text[0] == 0);
    }
}

static void probe_success(void)
{
    const u32 raw[] = {0, 1, 1023, 1024, 1025, 0xffff, 0xdeadf321, 0xffffffff};
    for (unsigned s = 0; s < SCENARIOS; s++)
        for (unsigned mode = 0; mode < 3; mode++)
            for (unsigned r = 0; r < sizeof(raw) / sizeof(raw[0]); r++) {
                setup_scenario(s, mode);
                live_raw = raw[r];
                after_init_raw = raw[r] ^ 0xa5a55a5au;
                if (scenarios[s].branch == COLD) {
                    /* Only real initialization repairs these deliberately bad bases. */
                    live_rxb = live_txb = 0;
                }
                expect_success(s, mode);
                assert(live_raw == (scenarios[s].branch == COLD ? after_init_raw : raw[r]));
            }
}

static void probe_init_failure(void)
{
    const int errors[] = {-EIO, -ENOMEM, -ETIMEDOUT, -517, 7};
    for (unsigned s = 0; s < SCENARIOS; s++) {
        if (scenarios[s].branch != COLD) continue;
        for (unsigned mode = 0; mode < 3; mode++)
            for (unsigned e = 0; e < sizeof(errors) / sizeof(errors[0]); e++) {
                setup_scenario(s, mode);
                init_result = errors[e];
                expect_failure(s, mode, errors[e], "datapath initialization failed\n");
                assert(maps == 0 && pending_total() == 0 && busy_reads == 0);
                assert(rxbase_reads == 0 && txbase_reads == 0 && all_reads == 0);
            }
    }
}

static void probe_pending(void)
{
    for (unsigned s = 0; s < SCENARIOS; s++) {
        if (scenarios[s].branch != COLD) continue;
        for (unsigned mode = 0; mode < 3; mode++)
            for (unsigned word = 0; word < 8; word++)
                for (unsigned bit = 0; bit < 32; bit++) {
                    setup_scenario(s, mode);
                    pending[word] = UINT32_C(1) << bit;
                    expect_failure(s, mode, -EIO, "RX queues not empty after initialization\n");
                    assert(pending_total() == word + 1 && busy_reads == 0);
                    for (unsigned i = 0; i < 8; i++)
                        assert(pending_reads[i] == (unsigned)(i <= word));
                    assert(maps == 0 && rxbase_reads == 0 && txbase_reads == 0);
                }
    }
}

static void probe_busy(void)
{
    const u32 values[] = {1, 3, 0x80000001u, 0xffffffffu, 0, 2, 0x10000, 0x80000000u, 0xfffffffeu};
    for (unsigned s = 0; s < SCENARIOS; s++) {
        if (scenarios[s].branch != COLD) continue;
        for (unsigned mode = 0; mode < 3; mode++)
            for (unsigned b = 0; b < sizeof(values) / sizeof(values[0]); b++) {
                setup_scenario(s, mode);
                busy = values[b];
                if (busy & 1) {
                    expect_failure(s, mode, -EBUSY, "descriptor return busy after initialization\n");
                    assert(pending_total() == 8 && busy_reads == 1);
                    assert(maps == 0 && rxbase_reads == 0 && txbase_reads == 0);
                } else {
                    expect_success(s, mode);
                }
            }
    }
}

static void probe_bases(void)
{
    const u32 bad[][2] = {
        {0, 0x41c00000}, {0x41a00004, 0x41c00000}, {0x41c00000, 0x41c00000},
        {0xffffffff, 0x41c00000}, {0x41a00000, 0}, {0x41a00000, 0x41c00004},
        {0x41a00000, 0x41a00000}, {0x41a00000, 0xffffffff}, {0, 0},
    };
    for (unsigned s = 0; s < SCENARIOS; s++)
        for (unsigned mode = 0; mode < 3; mode++)
            for (unsigned b = 0; b < sizeof(bad) / sizeof(bad[0]); b++) {
                setup_scenario(s, mode);
                live_rxb = after_init_rxb = bad[b][0];
                live_txb = after_init_txb = bad[b][1];
                expect_failure(s, mode, -EINVAL, "invalid RX/TX ring bases\n");
                assert(maps == 0);
                assert(rxbase_reads == (scenarios[s].branch == WARM ? 2u : 1u));
                assert(txbase_reads == rxbase_reads);
            }
}

static void probe_maps(void)
{
    for (unsigned s = 0; s < SCENARIOS; s++)
        for (unsigned mode = 0; mode < 3; mode++)
            for (unsigned bad = 1; bad <= 4; bad++) {
                setup_scenario(s, mode);
                if (bad <= 3) failed_mapping = (int)bad;
                else box.ze.bufs = NULL;  /* earlier buffer-pool mapping failed */
                expect_failure(s, mode, -ENOMEM, NULL);
                assert(maps == 3);
                assert((box.ze.ring == NULL) == (bad == 1));
                assert((box.ze.txring == NULL) == (bad == 2));
                assert((box.ze.bufs2 == NULL) == (bad == 3));
                assert((box.ze.bufs == NULL) == (bad == 4));
            }
}

static void probe_precedence(void)
{
    for (unsigned s = 0; s < SCENARIOS; s++)
        for (unsigned mode = 0; mode < 3; mode++) {
            setup_scenario(s, mode);
            for (unsigned i = 0; i < 8; i++) pending[i] = 0xffffffffu;
            busy = 0xffffffffu;
            init_result = -ETIMEDOUT;
            if (scenarios[s].branch != COLD) {
                /* Warm and blind skip (even force+skip) bypass init AND guards. */
                expect_success(s, mode);
                assert(init_calls == 0 && pending_total() == 0 && busy_reads == 0);
            } else {
                /* Init failure dominates all pending/busy/bases/map failures. */
                after_init_rxb = 0;
                failed_mapping = 1;
                expect_failure(s, mode, -ETIMEDOUT, "datapath initialization failed\n");
                assert(all_reads == 0 && maps == 0);
                setup_scenario(s, mode);
                for (unsigned i = 0; i < 8; i++) pending[i] = 0xffffffffu;
                busy = 1;
                after_init_rxb = 0;
                failed_mapping = 1;
                expect_failure(s, mode, -EIO, "RX queues not empty after initialization\n");
                assert(pending_total() == 1 && busy_reads == 0 && maps == 0);
                setup_scenario(s, mode);
                busy = 1;
                after_init_rxb = 0;
                failed_mapping = 1;
                expect_failure(s, mode, -EBUSY, "descriptor return busy after initialization\n");
                assert(pending_total() == 8 && busy_reads == 1 && maps == 0);
            }
        }
}

int main(int argc, char **argv)
{
    assert(argc == 2);
    assert(RING_ENTRIES == 1024 && TMQ_TXIDX == 0x6c && ZX_RX_QUEUES == 8);
    if (!strcmp(argv[1], "helper_sweep")) helper_sweep();
    else if (!strcmp(argv[1], "helper_random")) helper_random();
    else if (!strcmp(argv[1], "helper_high_bits")) helper_high_bits();
    else if (!strcmp(argv[1], "probe_success")) probe_success();
    else if (!strcmp(argv[1], "probe_init_failure")) probe_init_failure();
    else if (!strcmp(argv[1], "probe_pending")) probe_pending();
    else if (!strcmp(argv[1], "probe_busy")) probe_busy();
    else if (!strcmp(argv[1], "probe_bases")) probe_bases();
    else if (!strcmp(argv[1], "probe_maps")) probe_maps();
    else if (!strcmp(argv[1], "probe_precedence")) probe_precedence();
    else { fprintf(stderr, "Unknown case: %s\n", argv[1]); return 2; }
    printf("PASS exact driver C: %s helper_cases=%lu probe_cases=%lu\n",
           argv[1], helper_cases, probe_cases);
    return 0;
}
'''


def host_translation_unit(data, reference, *, frozen=True):
    if frozen:
        validate_and_restore(data, reference)
    parsed = blocks(data)
    text = data.decode('utf-8')
    constants = ('TMD_GO', 'TMC_RING_BASE', 'TMQ_PENDING', 'TMQ_TXIDX', 'TMQ_TXRING',
                 'ZX_NPORTS', 'BUF_SIZE', 'BUF2_COUNT', 'RING_ENTRIES', 'ZX_DDR_POOL2',
                 'ZX_DDR_RX_RING', 'ZX_DDR_TX_RING',
                 'DESC_SIZE', 'ZX_RX_QUEUES', 'ZX_RX_RINGS', 'ZX_RX_RING_SIZE', 'ZX_RX_MAP_SIZE')
    return '\n'.join([
        HEADERS, *(exact_define(text, name) for name in constants),
        '#line 1 "exact-driver-reg-enum"', exact_enum(text, 'zx_eth_reg'),
        '#line 1 "exact-driver-queue-struct"', exact_struct(text, 'zx_rx_queue'),
        '#line 1 "exact-driver-eth-struct"', exact_struct(text, 'zx_eth'),
        '#line 1 "r204-host-boundary-stubs"', BOUNDARIES,
        '#line 1 "exact-driver-tx-origin-helper"', function(text, 'zx_tx_origin_init'),
        '#line 1 "r204-probe-wrapper"',
        'static int extracted_probe(struct zx_eth *ze) {',
        'struct device *dev = ze->dev; u32 rxb, txb; int i; int ret;',
        '#line 1 "exact-driver-probe-local"', parsed['LOCAL'][2].decode('utf-8'),
        '#line 1 "exact-driver-probe-control-flow"', probe_slice(data),
        '#line 1 "r204-probe-wrapper-end"', 'return 0; }',
        '#line 1 "r204-runtime-tests"', CASES,
    ])


@needs_artifacts()
class TxOriginSourcePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Whole-file provenance belongs to the immutable, hardware-validated
        # snapshot. Ordering checks and runtime C continue using today's code.
        cls.data = ARCHIVE.read_bytes()
        cls.reference = REFERENCE.read_bytes()
        cls.text = SOURCE.read_text()

    def test_archive_and_exact_whole_file_restoration_are_frozen_10f(self):
        self.assertEqual(hashlib.sha256(self.data).hexdigest(),
                         '477ba61a1f992edc9ae94cacecd51c8977ae51133946468dff5b7882cd4e0520')
        restored = validate_and_restore(self.data, self.reference)
        self.assertEqual(restored, self.reference)
        self.assertEqual(hashlib.sha256(restored).hexdigest(), REFERENCE_SHA256)

    def test_all_r201_r202_blocks_and_every_outside_byte_are_unchanged(self):
        restored = validate_and_restore(self.data, self.reference)
        self.assertEqual(restored, self.reference)
        stems = re.findall(rb'/\* (ZX_[A-Z0-9_]*_R20[12](?:_[A-Z0-9_]+)?)_BEGIN \*/',
                           self.reference)
        self.assertGreaterEqual(len(stems), 8)
        for stem in stems:
            with self.subTest(stem=stem):
                pattern = rb'/\* ' + stem + rb'_BEGIN \*/.*?/\* ' + stem + rb'_END \*/'
                old = re.findall(pattern, self.reference, re.S)
                new = re.findall(pattern, self.data, re.S)
                self.assertEqual(len(old), 1)
                self.assertEqual(new, old)

    def test_flag_only_after_actual_success_all_eight_pending_and_busy_guards(self):
        probe = tokens(function(self.text, 'zx_eth_probe'))
        sequence = tokens(r'''
            ret = zx_eth_datapath_init(ze);
            if (ret) return dev_err_probe(dev, ret, "datapath initialization failed\n");
            ze->dp_inited = true;
            for (i = 0; i < ZX_RX_QUEUES; i++)
                if (readl(ze->tmq + TMQ_PENDING + i * 4))
                    return dev_err_probe(dev, -EIO, "RX queues not empty after initialization\n");
            if (readl(ze->tmd + TMD_GO) & 1)
                return dev_err_probe(dev, -EBUSY, "descriptor return busy after initialization\n");
            datapath_initialized = true;
            warm:
        ''')
        index_once(probe, ' '.join(sequence))
        decl = index_once(probe, EXPECTED['LOCAL'])
        skip = index_once(probe, 'if (IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG) && zx_skip_dp_init) {')
        detector = index_once(probe, 'if (IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG) && !zx_force_dp_init && zx_datapath_warm(ze)) {')
        init = index_once(probe, 'ret = zx_eth_datapath_init(ze);')
        flag = index_once(probe, EXPECTED['INITIALIZED'])
        warm_label = index_once(probe, 'warm:')
        ctor = index_once(probe, EXPECTED['ASSIGN'])
        self.assertEqual(sorted((decl, skip, detector, init, flag, warm_label, ctor)),
                         [decl, skip, detector, init, flag, warm_label, ctor])
        self.assertNotIn('datapath_initialized', probe[skip:init])
        self.assertEqual(probe[skip:init].count('goto'), 2)
        self.assertEqual(probe.count('datapath_initialized'), 3)
        validate_and_restore(self.data, self.reference)

    def test_constructor_once_before_all_registration_and_never_on_open_reopen(self):
        whole = tokens(self.text)
        # Definition, the probe's call, and the datapath reset's call: the
        # reset re-runs cold init, so its origin is always "initialized".
        self.assertEqual(whole.count('zx_tx_origin_init'), 3)
        reset = ' '.join(tokens(function(self.text, 'zx_dp_reset_work')))
        self.assertEqual(reset.count('zx_tx_origin_init'), 1)
        self.assertIn('zx_tx_origin_init ( ze , true )', reset)
        probe = tokens(function(self.text, 'zx_eth_probe'))
        ctor = index_once(probe, EXPECTED['ASSIGN'])
        for name in ('devm_register_netdev', 'zx_eth_add_port_ndev'):
            self.assertIn(name, probe)
            self.assertTrue(all(ctor < i for i, t in enumerate(probe) if t == name))
        for name in ('zx_eth_open', 'zx_port_open', 'zx_dp_start', 'zx_dp_stop',
                     'zx_eth_add_port_ndev', 'zx_eth_xmit', 'zx_eth_poll'):
            with self.subTest(function=name):
                body = function(self.text, name)
                self.assertEqual(function(self.data.decode('utf-8'), name),
                                 function(self.reference.decode('utf-8'), name))
                self.assertNotIn('zx_tx_origin_init', tokens(body))
                self.assertNotIn('datapath_initialized', tokens(body))
        for name in ('zx_eth_open', 'zx_port_open', 'zx_dp_start', 'zx_dp_stop'):
            self.assertNotRegex(' '.join(tokens(function(self.text, name))),
                                r'-> tx_next (?:=|\+=|-=|\+\+|--)')

    def test_current_origin_read_and_archived_r204_mmio_delta(self):
        helper = tokens(function(self.text, 'zx_tx_origin_init'))
        self.assertEqual(helper, tokens(EXPECTED['HELPER']))
        index_once(helper, 'readl(ze->tmq + TMQ_TXIDX)')
        self.assertEqual(helper.count('readl'), 1)
        self.assertEqual(helper.count('dev_info'), 1)
        current, old = tokens(self.data.decode('utf-8')), tokens(self.reference.decode('utf-8'))
        mmio = re.compile(r'(?:__raw_)?(?:read|write)[bwlq](?:_relaxed)?|'
                          r'ioread\w*|iowrite\w*|(?:devm_)?ioremap\w*|iounmap|'
                          r'memcpy_(?:to|from)io|memset_io|dma_\w*|module_param\w*')
        self.assertEqual(Counter(t for t in current if mmio.fullmatch(t)),
                         Counter(t for t in old if mmio.fullmatch(t)))
        self.assertEqual(tokens(exact_define(self.text, 'TMQ_TXIDX')),
                         tokens('#define TMQ_TXIDX 0x6c'))
        self.assertEqual(tokens(exact_define(self.text, 'RING_ENTRIES')),
                         tokens('#define RING_ENTRIES 1024'))
        validate_and_restore(self.data, self.reference)

    def test_host_unit_contains_unmodified_c_fragments_not_regenerated_statements(self):
        data = SOURCE.read_bytes()
        unit = host_translation_unit(data, self.reference, frozen=False)
        self.assertIn(function(self.text, 'zx_tx_origin_init'), unit)
        self.assertIn(probe_slice(data), unit)
        self.assertIn(blocks(data)['LOCAL'][2].decode('utf-8'), unit)
        self.assertIn(exact_struct(self.text, 'zx_eth'), unit)
        self.assertIn(exact_struct(self.text, 'zx_rx_queue'), unit)


@needs_artifacts()
class TxOriginTamperRejectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = ARCHIVE.read_bytes()
        cls.reference = REFERENCE.read_bytes()
        validate_and_restore(cls.data, cls.reference)
        cls.parsed = blocks(cls.data)

    def reject(self, data):
        self.assertNotEqual(data, self.data, 'Negative mutation did not change candidate')
        with self.assertRaises(AssertionError):
            validate_and_restore(data, self.reference)

    def test_every_missing_duplicate_reversed_and_non_full_line_marker(self):
        for kind in KINDS:
            begin, end = marker(kind, 'BEGIN'), marker(kind, 'END')
            for edge in (begin, end):
                for replacement in (b'', edge + edge, b' ' + edge,
                                    edge[:-1], edge.replace(b' */', b' */ extra')):
                    with self.subTest(kind=kind, edge=edge, replacement=replacement):
                        self.reject(self.data.replace(edge, replacement, 1))
            start, stop, body = self.parsed[kind]
            with self.subTest(kind=kind, reverse=True):
                self.reject(self.data[:start] + end + body + begin + self.data[stop:])

    def test_unknown_future_truncated_and_nested_marker_rejection(self):
        for extra in (b'/* ZX_TX_ORIGIN_R204_UNKNOWN_BEGIN */\n',
                      b'/* ZX_TX_ORIGIN_R204_HELPER_BEGIN_EXTRA */\n',
                      b'/* ZX_TX_ORIGIN_R205_HELPER_BEGIN */\n',
                      b'/* ZX_TX_ORIGIN_R204_ */\n',
                      b'/* ZX_RX_SEED_R205_BEGIN */\n',
                      marker('LOCAL', 'BEGIN')):
            with self.subTest(extra=extra):
                point = self.data.index(marker('HELPER', 'END'))
                self.reject(self.data[:point] + extra + self.data[point:])
        # Proper names, but cross-pair/nested order must not become a greedy match.
        a, b = marker('LOCAL', 'END'), marker('INITIALIZED', 'BEGIN')
        self.reject(self.data.replace(a, b'@TEMP@', 1).replace(b, a, 1).replace(b'@TEMP@', b, 1))

    def test_exact_block_bodies_cannot_hide_extra_state_mmio_parameters_or_selection(self):
        mutations = (
            (b'u32 raw = readl(ze->tmq + TMQ_TXIDX);', b'u32 raw = readl(ze->tmq + TMQ_TXIDX + 4);'),
            (b'u32 raw = readl(ze->tmq + TMQ_TXIDX);', b'u32 raw = readl(ze->tmq + TMQ_TXIDX); readl(ze->tmq + 0x68);'),
            (b'u32 inherited = (raw & 0xffff) % RING_ENTRIES;', b'u32 inherited = (raw >> 16) % RING_ENTRIES;'),
            (b'? 0 : inherited;', b'? inherited : 0;'),
            (b'? 0 : inherited;', b'? 0 : inherited; ze->tx_pending = 0;'),
            (b'? 0 : inherited;', b'? 0 : inherited; writel(0, ze->tmq + TMQ_TXIDX);'),
            (b'? 0 : inherited;', b'? 0 : inherited; zx_tx_slot_mode = 0;'),
            (b'bool datapath_initialized = false;', b'bool datapath_initialized = true;'),
            (b'bool datapath_initialized = false;', b'static bool datapath_initialized = false;'),
            (b'datapath_initialized = true;', b'datapath_initialized = zx_force_dp_init;'),
            (b'zx_tx_origin_init(ze, datapath_initialized);', b'zx_tx_origin_init(ze, ze->dp_inited);'),
            (b'zx_tx_origin_init(ze, datapath_initialized);', b'zx_tx_origin_init(ze, datapath_initialized); zx_tx_origin_init(ze, false);'),
            (b'slot_mode=%u\\n', b'slot_mode=%u'),
        )
        for old, new in mutations:
            with self.subTest(old=old, new=new):
                self.assertIn(old, self.data)
                self.reject(self.data.replace(old, new, 1))
        for kind in KINDS:
            point = self.data.index(marker(kind, 'END'))
            for extra in (b'\tze->tx_next = 99;\n', b'\tmodule_param(extra, int, 0644);\n',
                          b'#if 0\n', b'\t/* unterminated comment\n'):
                with self.subTest(kind=kind, extra=extra):
                    self.reject(self.data[:point] + extra + self.data[point:])

    def test_removable_blocks_cannot_be_relocated_without_changing_baseline(self):
        # Relocating LOCAL/INITIALIZED/HELPER could otherwise disappear on restore.
        for kind, anchor in (
            ('LOCAL', b'\tif (zx_skip_dp_init) {\n'),
            ('INITIALIZED', b'\tret = zx_eth_datapath_init(ze);\n'),
            ('INITIALIZED', b'warm:\n'),
            ('INITIALIZED', b'\tfor (i = 0; i < ZX_RX_QUEUES; i++)\n'),
        ):
            with self.subTest(kind=kind, anchor=anchor):
                start, stop, _ = self.parsed[kind]
                block = self.data[start:stop]
                removed = self.data[:start] + self.data[stop:]
                where = removed.index(anchor, removed.index(b'static int zx_eth_probe('))
                if anchor == b'warm:\n':
                    where += len(anchor)  # specifically after the jump target
                self.reject(removed[:where] + block + removed[where:])
        start, stop, _ = self.parsed['HELPER']
        block = self.data[start:stop + 1]
        removed = self.data[:start] + self.data[stop + 1:]
        where = removed.index(b'static void zx_eth_close_ports(')
        self.reject(removed[:where] + block + removed[where:])

    def test_whole_blocks_reordered_and_extra_blank_lines_rejected(self):
        a, b, _ = self.parsed['LOCAL']
        c, d, _ = self.parsed['INITIALIZED']
        self.reject(self.data[:a] + self.data[c:d] + self.data[b:c] + self.data[a:b] + self.data[d:])
        for kind in KINDS:
            end = marker(kind, 'END')
            with self.subTest(kind=kind):
                self.reject(self.data.replace(end, end + b'\n', 1))
        self.reject(self.data.replace(marker('HELPER', 'END') + b'\n', marker('HELPER', 'END'), 1))

    def test_outside_delta_guard_open_r201_r202_and_new_module_parameter_rejected(self):
        mutations = (
            (b'i < ZX_RX_QUEUES; i++)\n\t\tif (readl', b'i < ZX_RX_QUEUES - 1; i++)\n\t\tif (readl'),
            (b'if (readl(ze->tmd + TMD_GO) & 1)\n\t\treturn dev_err_probe',
             b'if (false)\n\t\treturn dev_err_probe'),
            (b'if (!zx_force_dp_init && zx_datapath_warm(ze))', b'if (zx_datapath_warm(ze))'),
            (b'if (zx_skip_dp_init) {', b'if (zx_skip_dp_init && !zx_force_dp_init) {'),
            (b'ze->rx_seed_eligible = true;', b'ze->rx_seed_eligible = false;'),
            (b'/* ZX_PACKET_TRACE_R201_BEGIN */', b'/* ZX_PACKET_TRACE_R201_BEGIN */\n/* tampered */'),
            (b'static int zx_eth_open(struct net_device *ndev)\n{',
             b'static int zx_eth_open(struct net_device *ndev)\n{\n\tzx_tx_origin_init(netdev_priv(ndev), true);'),
        )
        for old, new in mutations:
            with self.subTest(old=old):
                self.assertIn(old, self.data)
                self.reject(self.data.replace(old, new, 1))
        self.reject(self.data + b'\nmodule_param(new_origin, int, 0644);\n')
        self.reject(self.data.replace(b'\n', b'\r\n'))

    def test_modified_archive_cannot_authorize_matching_non_r204_change(self):
        old = b'#define RING_ENTRIES\t1024'
        new = b'#define RING_ENTRIES\t2048'
        self.assertIn(old, self.reference)
        with self.assertRaises(AssertionError):
            validate_and_restore(self.data.replace(old, new), self.reference.replace(old, new))

    def test_function_extractor_ignores_comment_and_string_braces_and_rejects_duplicates(self):
        snippet = 'static int example(void)\n{ /* } */ puts("}"); return 0; }'
        self.assertEqual(function(snippet, 'example'), snippet)
        with self.assertRaises(AssertionError):
            function(snippet + '\n' + snippet, 'example')
        with self.assertRaises(AssertionError):
            function('static int example(void) {', 'example')


@needs_artifacts()
class TxOriginRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        data, reference = SOURCE.read_bytes(), REFERENCE.read_bytes()
        cls.temp = tempfile.TemporaryDirectory(prefix='tx-origin-r204-')
        cls.addClassCleanup(cls.temp.cleanup)
        cfile = Path(cls.temp.name) / 'tx_origin_test.c'
        cls.exe = Path(cls.temp.name) / 'tx_origin_test'
        cfile.write_text(host_translation_unit(data, reference, frozen=False), encoding='utf-8')
        # HOSTCC deliberately avoids an OpenWrt cross-compiler in CC.
        compiler = shlex.split(os.environ.get('HOSTCC', 'cc'))
        require(bool(compiler), 'HOSTCC must name a host C compiler')
        command = compiler + ['-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                              '-UNDEBUG', str(cfile), '-o', str(cls.exe)]
        built = subprocess.run(command, capture_output=True, text=True, timeout=60,
                               cwd=cls.temp.name)
        require(built.returncode == 0, 'Host C compilation failed:\n' + built.stdout + built.stderr)

    def run_case(self, name, expected_count=None):
        result = subprocess.run([str(self.exe), name], capture_output=True, text=True,
                                timeout=90, cwd=self.temp.name)
        self.assertEqual(result.returncode, 0,
                         f'{name}: exit {result.returncode}\n{result.stdout}{result.stderr}')
        self.assertIn(f'PASS exact driver C: {name} ', result.stdout)
        if expected_count is not None:
            self.assertIn(f'helper_cases={expected_count} ', result.stdout)

    def test_full_low16_sweep_both_flags_two_nonzero_high_patterns_all_modes(self):
        self.run_case('helper_sweep', 786432)

    def test_seeded_random32_both_flags_all_modes_exact_log_and_state_sentinels(self):
        self.run_case('helper_random', 98304)

    def test_every_high16_and_boundary_low16_preserve_raw_but_ignore_high_for_selection(self):
        self.run_case('helper_high_bits', 1048576)

    def test_actual_probe_all_skip_force_warm_combinations_and_post_init_reads(self):
        self.run_case('probe_success')

    def test_actual_probe_init_failures_never_reach_constructor(self):
        self.run_case('probe_init_failure')

    def test_actual_probe_every_bit_both_halves_of_all_eight_pending_words(self):
        self.run_case('probe_pending')

    def test_actual_probe_busy_bit_rejects_but_other_tmd_bits_do_not(self):
        self.run_case('probe_busy')

    def test_actual_probe_bad_rx_and_tx_bases_all_branches(self):
        self.run_case('probe_bases')

    def test_actual_probe_each_mapping_failure_including_earlier_buffer_pool(self):
        self.run_case('probe_maps')

    def test_actual_probe_force_plus_skip_bypasses_init_and_guards_and_failure_order(self):
        self.run_case('probe_precedence')


if __name__ == '__main__':
    unittest.main(verbosity=2)
