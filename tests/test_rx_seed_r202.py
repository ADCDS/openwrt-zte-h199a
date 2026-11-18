"""Offline R202 tests of extracted, unmodified driver C (never a seed model).

Run: python3 tests/test_rx_seed_r202.py
Only a host cc, Python, and temporary files are used. No kernel build, device,
serial, network, or Ghidra access. RTNL/NAPI/MMIO are host boundary stubs: these
checks establish sequential locking/order contracts, not real SMP correctness.
The later-open-error case explicitly simulates a caller unwind after actual
zx_dp_start: existing PHY attach failures warn rather than return an error.
"""
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
R201_SHA256 = 'ff48452a9126a4a5a8a15f5d585a866e7883a0e5907556282909a84c95f003fe'
R201_BLOCK_SHA256 = '5fac7931ae0f834f76c3bcdb53c4c871212a054a8df9af945948f5ad202e12d7'
# Frozen against the canonical 4283-line R201 file before any R202 edits.
# Includes R201 trace calls; never update hashes to hide datapath changes.
FUNCTION_SHA256 = {
    'zx_eth_xmit': 'b49781516cdfce0188fe2e1dc892339f2cf522d384f435ccb5ff658b3c69e140',
    'zx_eth_poll': '645d2d842f427cfef8b7b442658041508f612be12f48d76d4a60b72d18dfe0b2',
    'zx_eth_open': '4ad7822f3cc19e3cdd5a45b9ab4217b54ea7c2bc1e8868c1d8f4b492c591e572',
    'zx_port_open': 'c859641319f6ad635b76d996e7f883cba7ffd94064aa40d36b9b72c77d37f006',
    'zx_dp_stop': '47e8e2bd76b7fc7fe2c93c524955f4480aa00723e151367a0458efc9975238bb',
    'zx_eth_close_ports': 'dc261aec4c6718f0ce28f6909b3879a54169563e15165a7e95c63659d29d3024',
}
C_LEX = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_]\w*|0[xX][0-9a-fA-F]+[uUlL]*|\d+[uUlL]*|>>=|<<=|->|\+\+|--|&&|\|\||==|!=|<=|>=|<<|>>|\+=|-=|\*=|/=|&=|\|=|\^=|\S', re.S)


def lex(text):
    return [m for m in C_LEX.finditer(text) if not m.group().startswith(('/*', '//'))]


def tokens(text):
    return [m.group() for m in lex(text)]


def marked(text, stem):
    begin, end = f'/* {stem}_BEGIN */', f'/* {stem}_END */'
    if text.count(begin) != 1 or text.count(end) != 1:
        raise AssertionError(f'Expected one complete {stem} marker pair')
    start, stop = text.index(begin) + len(begin), text.index(end)
    if start >= stop:
        raise AssertionError(f'Out-of-order {stem} markers')
    return text[start:stop]


def function(text, name):
    """Return exact source bytes, retaining comments, rather than regenerate C."""
    ms = lex(text)
    ts = [m.group() for m in ms]
    for i, token in enumerate(ts[:-1]):
        if token != name or ts[i + 1] != '(':
            continue
        depth, j = 1, i + 2
        while depth and j < len(ts):
            depth += (ts[j] == '(') - (ts[j] == ')')
            j += 1
        if j == len(ts) or ts[j] != '{':
            continue
        depth, k = 1, j + 1
        while depth and k < len(ts):
            depth += (ts[k] == '{') - (ts[k] == '}')
            k += 1
        if depth:
            raise AssertionError(f'Unterminated {name}')
        # All functions under test have one-line signatures starting with static.
        start = text.rfind('\n', 0, ms[i].start()) + 1
        return text[start:ms[k - 1].end()]
    raise AssertionError(f'Missing function {name}')


def function_digest(text, name):
    ts = tokens(function(text, name))
    ts = ts[ts.index(name):]  # R201 token-digest convention excludes return type.
    return hashlib.sha256(' '.join(ts).encode()).hexdigest()


def index_once(body, snippet):
    needle = tokens(snippet)
    found = [i for i in range(len(body) - len(needle) + 1)
             if body[i:i + len(needle)] == needle]
    if len(found) != 1:
        raise AssertionError(f'Expected one {snippet!r}, got {len(found)}')
    return found[0]


STUBS = r'''
#define _GNU_SOURCE
#define CONFIG_ZX279128_ETH_DEBUG 1
#define IS_ENABLED(option) (option)
#define ZX_HAVE_DEBUG_IFACES 1
#include <assert.h>
#include <ctype.h>
#include <errno.h>
#include <limits.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
#define PAGE_SIZE 4096
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, v) ((x) = (v))
#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
#define module_param_cb(name, ops, seed_arg, mode) \
    static const struct kernel_param_ops *registered_ops = (ops); \
    static const struct kernel_param registered_param = { .arg = (seed_arg) }; \
    static const unsigned registered_mode = (mode)
#define MODULE_PARM_DESC(name, description)
struct kernel_param { void *arg; };
struct kernel_param_ops {
    int (*set)(const char *, const struct kernel_param *);
    int (*get)(char *, const struct kernel_param *);
};
struct net_device { unsigned cookie; };
struct napi_struct { bool enabled; };
struct delayed_work { bool pending; };
/* The kernel API boundary, not a replacement seed implementation. */
static int kstrtoint(const char *text, unsigned base, int *value) {
    char *end;
    long v;
    assert(base == 0);
    if (!text || !*text || isspace((unsigned char)*text))
        return -EINVAL;
    errno = 0;
    v = strtol(text, &end, base);
    if (errno == ERANGE || v < INT_MIN || v > INT_MAX)
        return -ERANGE;
    if (end == text || (*end && strcmp(end, "\n")))
        return -EINVAL;
    *value = (int)v;
    return 0;
}
static int scnprintf(char *out, size_t size, const char *fmt, ...)
    __attribute__((format(printf, 3, 4)));
static int scnprintf(char *out, size_t size, const char *fmt, ...) {
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(out, size, fmt, ap);
    va_end(ap);
    assert(n >= 0);
    return !size ? 0 : (size_t)n >= size ? (int)size - 1 : n;
}

static bool rtnl_held, irq_held, force_try_busy;
static unsigned locks, unlocks, tries, busy_tries;
static unsigned enables, disables, rearms, irq_syncs, cancels, mmio_reads, mmio_writes;
static unsigned info_logs;
static char last_log[256];
static void (*before_try)(void), (*before_blocking_lock)(void), (*before_unlock)(void);
static bool rtnl_trylock(void) {
    tries++;
    if (before_try) {
        void (*hook)(void) = before_try;
        before_try = NULL;
        hook();
    }
    if (force_try_busy || rtnl_held) {
        busy_tries++;
        return false;
    }
    rtnl_held = true;
    locks++;
    return true;
}
static void rtnl_lock(void) {
    assert(!rtnl_held);
    if (before_blocking_lock) {
        void (*hook)(void) = before_blocking_lock;
        before_blocking_lock = NULL;
        hook();
    }
    rtnl_held = true;
    locks++;
}
static void rtnl_unlock(void) {
    assert(rtnl_held && !irq_held);
    if (before_unlock) {
        void (*hook)(void) = before_unlock;
        before_unlock = NULL;
        hook();
    }
    rtnl_held = false;
    unlocks++;
}
#define ASSERT_RTNL() assert(rtnl_held)
#define lockdep_assert_held(lock) do { (void)(lock); assert(rtnl_held); } while (0)
static void stub_spin_lock(int *lock) {
    assert(lock && rtnl_held && !irq_held);
    irq_held = true;
}
static void stub_spin_unlock(int *lock) {
    assert(lock && rtnl_held && irq_held);
    irq_held = false;
}
#define spin_lock_irqsave(lock, flags) do { (flags) = 0; stub_spin_lock(lock); } while (0)
#define spin_unlock_irqrestore(lock, flags) do { (void)(flags); stub_spin_unlock(lock); } while (0)
static u32 readl(const void *address) {
    assert(address && rtnl_held && irq_held);
    mmio_reads++;
    return 0x12340000;
}
static void writel(u32 value, void *address) {
    assert(address && value == 0x12340007 && rtnl_held && irq_held);
    mmio_writes++;
}
static void synchronize_irq(int irq) {
    assert(irq == 17 && rtnl_held && !irq_held);
    irq_syncs++;
}
static void cancel_delayed_work_sync(struct delayed_work *work) {
    assert(work && rtnl_held && !irq_held);
    work->pending = false;
    cancels++;
}
static void synchronize_net(void) { assert(rtnl_held && !irq_held); }
#define HZ 100
static unsigned wd_arms;
static void schedule_delayed_work(struct delayed_work *work, unsigned long delay) {
    assert(work && delay == HZ && rtnl_held && !irq_held);
    work->pending = true;
    wd_arms++;
}
static void netdev_info(const struct net_device *ndev, const char *fmt, ...)
    __attribute__((format(printf, 2, 3)));
static void netdev_info(const struct net_device *ndev, const char *fmt, ...) {
    assert(ndev && rtnl_held && !irq_held);
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(last_log, sizeof(last_log), fmt, ap);
    va_end(ap);
    assert(n > 0 && (size_t)n < sizeof(last_log));
    info_logs++;
}
'''

STRUCT_PREFIX = r'''
/* Only the kernel-facing envelope is stubbed. Queue and R202 member
 * declarations below come verbatim from the canonical driver. */
struct zx_eth {
    struct net_device *ndev;
    struct napi_struct napi;
    struct zx_rx_queue rxq[ZX_RX_RINGS];
    unsigned int rx_next;
    int rx_inflight;
    bool rx_fault, removing, running;
    unsigned int dp_users;
    int irq_lock, irq;
    struct delayed_work rx_retry;
    /* Datapath recovery watchdog, armed by zx_dp_start(). */
    struct delayed_work wd_work;
    unsigned long n_desc_rls, wd_rls;
    unsigned int wd_stuck;
    void *tmc;
    u32 tx_next, free_credit;
    unsigned char unrelated[127];
'''

BOUNDARIES = r'''
};
static bool check_napi_order;
static int expected_cursor;
static void napi_enable(struct napi_struct *napi) {
    struct zx_eth *ze = (struct zx_eth *)((char *)napi - offsetof(struct zx_eth, napi));
    assert(rtnl_held && !irq_held && !napi->enabled && ze->dp_users == 1);
    assert(!ze->running && !ze->rx_seed_eligible);
    if (check_napi_order)
        assert(ze->rxq[0].cursor == expected_cursor);
    napi->enabled = true;
    enables++;
}
static void napi_disable(struct napi_struct *napi) {
    struct zx_eth *ze = (struct zx_eth *)((char *)napi - offsetof(struct zx_eth, napi));
    assert(rtnl_held && !irq_held && napi->enabled && !ze->dp_users && !ze->running);
    napi->enabled = false;
    disables++;
}
static void zx_rx_rearm(struct zx_eth *ze, bool software_pending) {
    (void)software_pending;
    assert(rtnl_held && irq_held && ze->running && ze->napi.enabled && ze->dp_users == 1);
    assert(!ze->rx_seed_eligible);
    rearms++;
}
'''

CASES = r'''
static struct net_device ndev = { .cookie = 0xabcdef01 };
static unsigned char fake_tmc[4096];
static int param_set(const char *text) {
    return registered_ops->set(text, &registered_param);
}
static void expect_get(int request) {
    char actual[PAGE_SIZE], expected[32];
    memset(actual, 0xa5, sizeof(actual));
    snprintf(expected, sizeof(expected), "%d", request);
    int n = registered_ops->get(actual, &registered_param);
    assert(n == (int)strlen(actual));
    /* sysfs accepts either conventional decimal representation here. */
    if (n > 0 && actual[n - 1] == '\n')
        actual[--n] = '\0';
    assert(!strcmp(actual, expected));
}
static void check_balanced(void) {
    assert(!rtnl_held && !irq_held && locks == unlocks);
}
static int start(struct zx_eth *ze) {
    rtnl_lock();
    int result = zx_dp_start(ze);
    rtnl_unlock();
    return result;
}
static void stop(struct zx_eth *ze) {
    rtnl_lock();
    zx_dp_stop(ze);
    rtnl_unlock();
}
static bool idle(const struct zx_eth *ze) {
    rtnl_lock();
    bool result = zx_rx_seed_idle(ze);
    rtnl_unlock();
    return result;
}
static int seed_start(struct zx_eth *ze) {
    rtnl_lock();
    int result = zx_rx_seed_start(ze);
    rtnl_unlock();
    return result;
}
static void fixture(struct zx_eth *ze, bool warm) {
    memset(ze, 0, sizeof(*ze));
    ze->ndev = &ndev;
    ze->rx_inflight = -1;
    ze->irq = 17;
    ze->tmc = fake_tmc;
    ze->tx_next = 333;
    ze->free_credit = 444;
    memset(ze->unrelated, 0xa5, sizeof(ze->unrelated));
    for (unsigned i = 0; i < ZX_RX_RINGS; i++) {
        ze->rxq[i].buffer = 100 + i;
        ze->rxq[i].pool = i % 3;
        ze->rxq[i].class = i % 8;
    }
    probe_seed_init(ze); /* exact marked probe initialization */
    assert(ze->rx_q0_seed == -1 && !ze->rx_seed_eligible);
    if (warm)
        verified_warm_seed_init(ze); /* exact positive-branch assignment */
    assert(ze->rx_seed_eligible == warm);
}
static void test_before_probe_and_parse(void) {
    assert(!zx_dbg_ze && registered_param.arg == NULL && registered_mode == 0644);
    assert(registered_ops->set == zx_rx_q0_seed_set);
    assert(registered_ops->get == zx_rx_q0_seed_get);
    expect_get(-1);
    const char *valid[] = {"-1", "0", "1023", "0x3ff"};
    for (unsigned i = 0; i < ARRAY_SIZE(valid); i++) {
        assert(param_set(valid[i]) == -ENODEV);
        assert(!zx_dbg_ze);
    }
    assert(param_set("1024") == -EINVAL);
    assert(param_set("garbage") == -EINVAL);
    assert(!enables && !info_logs && !mmio_reads && !mmio_writes);
    check_balanced();
}
static void test_all_ranges_and_readback(void) {
    struct zx_eth ze, before;
    char value[32];
    fixture(&ze, true);
    zx_rx_seed_publish(&ze);
    for (int seed = -1; seed < RING_ENTRIES; seed++) {
        memcpy(&before, &ze, sizeof(ze));
        snprintf(value, sizeof(value), "%d", seed);
        assert(param_set(value) == 0);
        before.rx_q0_seed = seed;
        assert(!memcmp(&before, &ze, sizeof(ze)));
        expect_get(seed);
        assert(!memcmp(&before, &ze, sizeof(ze)));
    }
    const struct { const char *text; int value; } valid[] = {
        {"0x3fF", 1023}, {"01777", 1023}, {"+42", 42}, {"0\n", 0},
        {"-1\n", -1}, {"-0x1", -1}, {"+0x2a", 42}, {"00", 0}
    };
    for (unsigned i = 0; i < ARRAY_SIZE(valid); i++) {
        assert(param_set(valid[i].text) == 0);
        assert(ze.rx_q0_seed == valid[i].value && !ze.rxq[0].cursor);
        expect_get(valid[i].value);
    }
    assert(!enables && !info_logs && !mmio_reads && !mmio_writes);
    zx_rx_seed_unpublish(&ze);
}
static void test_invalid_input_no_mutation(void) {
    struct zx_eth ze, before;
    fixture(&ze, true);
    zx_rx_seed_publish(&ze);
    assert(param_set("731") == 0);
    memcpy(&before, &ze, sizeof(ze));
    const struct { const char *text; int error; } bad[] = {
        {"-2", -EINVAL}, {"1024", -EINVAL}, {"0x400", -EINVAL},
        {"02000", -EINVAL}, {"2147483647", -EINVAL}, {"-2147483648", -EINVAL},
        {"2147483648", -ERANGE}, {"-2147483649", -ERANGE},
        {"99999999999999999999999999999999999999", -ERANGE},
        {"", -EINVAL}, {"no", -EINVAL}, {"0x", -EINVAL}, {"1x", -EINVAL},
        {"--1", -EINVAL}, {"+-1", -EINVAL}, {" 1", -EINVAL}, {"\t1", -EINVAL},
        {"1 ", -EINVAL}, {"1\n\n", -EINVAL}, {"1\njunk", -EINVAL},
        {"08", -EINVAL}, {"1.0", -EINVAL}, {"1\r\n", -EINVAL}
    };
    unsigned prior_tries = tries;
    for (unsigned i = 0; i < ARRAY_SIZE(bad); i++) {
        assert(param_set(bad[i].text) == bad[i].error);
        assert(!memcmp(&before, &ze, sizeof(ze)));
        assert(tries == prior_tries);
    }
    expect_get(731);
    assert(!info_logs && !mmio_reads && !mmio_writes);
    zx_rx_seed_unpublish(&ze);
}
static void test_trylock_busy(void) {
    struct zx_eth ze, before;
    char out[PAGE_SIZE], untouched[PAGE_SIZE];
    fixture(&ze, true);
    zx_rx_seed_publish(&ze);
    assert(param_set("512") == 0);
    memcpy(&before, &ze, sizeof(ze));
    memset(out, 0x6d, sizeof(out));
    memcpy(untouched, out, sizeof(out));
    force_try_busy = true;
    unsigned prior_locks = locks, prior_unlocks = unlocks;
    assert(param_set("17") == -EBUSY);
    assert(param_set("-1") == -EBUSY);
    assert(registered_ops->get(out, &registered_param) == -EBUSY);
    assert(!memcmp(out, untouched, sizeof(out)));
    assert(!memcmp(&before, &ze, sizeof(ze)));
    assert(locks == prior_locks && unlocks == prior_unlocks);
    force_try_busy = false;
    rtnl_lock(); /* Models a callback racing with an RTNL-held open/close. */
    assert(param_set("0") == -EBUSY);
    assert(registered_ops->get(out, &registered_param) == -EBUSY);
    assert(rtnl_held && !memcmp(&before, &ze, sizeof(ze)));
    rtnl_unlock();
    zx_rx_seed_unpublish(&ze);
    force_try_busy = true;
    assert(param_set("-1") == -EBUSY);
    assert(registered_ops->get(out, &registered_param) == -EBUSY);
    force_try_busy = false;
    assert(!enables && !info_logs && !mmio_reads && !mmio_writes);
}
static void expect_start_failure(struct zx_eth *ze, int error);
static void expect_idle_rejection(struct zx_eth *ze) {
    struct zx_eth before;
    memcpy(&before, ze, sizeof(before));
    assert(!idle(ze));
    assert(param_set("1") == -EBUSY);
    assert(param_set("-1") == -EBUSY);
    assert(!memcmp(&before, ze, sizeof(before)));
    if (ze->rx_seed_eligible) {
        assert(seed_start(ze) == -EBUSY);
        assert(!memcmp(&before, ze, sizeof(before)));
        /* Every guard also goes through the actual complete start function,
         * including its older removing/fault error precedence. */
        expect_start_failure(ze, ze->removing ? -ENODEV : ze->rx_fault ? -EIO : -EBUSY);
    }
}
static void test_every_idle_guard(void) {
    struct zx_eth ze;
    fixture(&ze, true);
    zx_rx_seed_publish(&ze);
    assert(param_set("777") == 0);
    assert(idle(&ze));
#define CHECK_GUARD(field, bad, restored) do { \
    ze.field = (bad); expect_idle_rejection(&ze); ze.field = (restored); \
    assert(idle(&ze)); \
} while (0)
    CHECK_GUARD(rx_seed_eligible, false, true);
    CHECK_GUARD(removing, true, false);
    CHECK_GUARD(running, true, false);
    CHECK_GUARD(dp_users, 1, 0);
    CHECK_GUARD(dp_users, UINT_MAX, 0);
    CHECK_GUARD(rx_fault, true, false);
    CHECK_GUARD(rx_inflight, 0, -1);
    CHECK_GUARD(rx_inflight, ZX_RX_RINGS - 1, -1);
    CHECK_GUARD(rx_inflight, -2, -1);
    CHECK_GUARD(rx_next, 1, 0);
    CHECK_GUARD(rx_next, UINT_MAX, 0);
    for (unsigned i = 0; i < ZX_RX_RINGS; i++) {
        CHECK_GUARD(rxq[i].cursor, 1, 0);
        CHECK_GUARD(rxq[i].cursor, RING_ENTRIES - 1, 0);
        CHECK_GUARD(rxq[i].remaining, 1, 0);
        CHECK_GUARD(rxq[i].remaining, UINT16_MAX, 0);
        CHECK_GUARD(rxq[i].debt, true, false);
        CHECK_GUARD(rxq[i].buffer_pending, true, false);
        CHECK_GUARD(rxq[i].return_sent, true, false);
    }
#undef CHECK_GUARD
    assert(!enables && !info_logs && !mmio_reads && !mmio_writes);
    zx_rx_seed_unpublish(&ze);
}
static void test_cancel_and_default_baseline(void) {
    struct zx_eth ze, before;
    fixture(&ze, true);
    zx_rx_seed_publish(&ze);
    assert(param_set("901") == 0 && !ze.rxq[0].cursor);
    assert(param_set("-1") == 0 && !ze.rxq[0].cursor);
    expect_get(-1);
    /* Default -1 must bypass ALL idle restrictions, preserving baseline state.
     * Direct helper calls isolate the new code from existing dp_start guards. */
    ze.removing = ze.running = ze.rx_fault = true;
    ze.dp_users = 8;
    ze.rx_inflight = 4;
    ze.rx_next = 6;
    for (unsigned i = 0; i < ZX_RX_RINGS; i++) {
        ze.rxq[i].cursor = i + 20;
        ze.rxq[i].remaining = i + 1;
        ze.rxq[i].debt = ze.rxq[i].buffer_pending = ze.rxq[i].return_sent = true;
    }
    memcpy(&before, &ze, sizeof(ze));
    before.rx_seed_eligible = false;
    assert(seed_start(&ze) == 0);
    assert(!memcmp(&before, &ze, sizeof(ze)));
    assert(param_set("-1") == -EBUSY);
    assert(!enables && !info_logs && !mmio_reads && !mmio_writes);
    zx_rx_seed_unpublish(&ze);
    fixture(&ze, true);
    ze.rxq[9].debt = true;
    ze.rxq[9].remaining = 3;
    ze.rxq[0].cursor = 42;
    check_napi_order = true;
    expected_cursor = 42;
    assert(start(&ze) == 0); /* actual default first-open, non-idle baseline */
    assert(!ze.rx_seed_eligible && ze.rxq[0].cursor == 42 && ze.rxq[9].debt);
    assert(ze.rxq[9].remaining == 3 && ze.dp_users == 1 && ze.napi.enabled);
    assert(!info_logs && !mmio_reads && !mmio_writes);
    stop(&ze);
}
static void test_armed_only_q0_and_once(void) {
    struct zx_eth ze, before;
    char value[32];
    for (int seed = 0; seed < RING_ENTRIES; seed++) {
        fixture(&ze, true);
        zx_rx_seed_publish(&ze);
        snprintf(value, sizeof(value), "%d", seed);
        assert(param_set(value) == 0);
        memcpy(&before, &ze, sizeof(ze));
        before.rxq[0].cursor = seed;
        before.rx_seed_eligible = false;
        unsigned logs = info_logs;
        assert(seed_start(&ze) == 0);
        assert(!memcmp(&before, &ze, sizeof(ze)));
        char expected_log[256];
        snprintf(expected_log, sizeof(expected_log),
                 "RXSEED_R202 requested=%d applied=%u ring=0 stage=pre-first-open\n",
                 seed, (unsigned)seed);
        assert(info_logs == logs + 1 && !strcmp(last_log, expected_log));
        expect_get(seed);
        assert(param_set("-1") == -EBUSY);
        assert(seed_start(&ze) == 0 && info_logs == logs + 1);
        assert(!memcmp(&before, &ze, sizeof(ze)));
        zx_rx_seed_unpublish(&ze);
    }
    assert(!enables && !mmio_reads && !mmio_writes);
}
static void expect_start_failure(struct zx_eth *ze, int error) {
    struct zx_eth before;
    memcpy(&before, ze, sizeof(before));
    unsigned saved_enables = enables, saved_logs = info_logs;
    unsigned reads = mmio_reads, writes = mmio_writes, saved_rearms = rearms;
    assert(start(ze) == error);
    assert(!memcmp(&before, ze, sizeof(before)));
    assert(enables == saved_enables && info_logs == saved_logs && rearms == saved_rearms);
    assert(mmio_reads == reads && mmio_writes == writes);
    check_balanced();
}
static void test_first_open_order_and_atomic_failures(void) {
    struct zx_eth ze;
    fixture(&ze, true);
    zx_rx_seed_publish(&ze);
    assert(param_set("1023") == 0);
    ze.rxq[15].return_sent = true;
    expect_start_failure(&ze, -EBUSY);
    ze.rxq[15].return_sent = false;
    ze.rx_inflight = 0;
    expect_start_failure(&ze, -EBUSY);
    ze.rx_inflight = -1;
    const int bad[] = {-2, INT_MIN, RING_ENTRIES, INT_MAX};
    for (unsigned i = 0; i < ARRAY_SIZE(bad); i++) {
        ze.rx_q0_seed = bad[i]; /* corrupted internal request, bypass setter */
        expect_start_failure(&ze, -EINVAL);
    }
    ze.rx_q0_seed = 1023;
    ze.removing = true;
    expect_start_failure(&ze, -ENODEV);
    ze.removing = false;
    ze.rx_fault = true;
    expect_start_failure(&ze, -EIO);
    ze.rx_fault = false;
    check_napi_order = true;
    expected_cursor = 1023;
    assert(start(&ze) == 0);
    assert(ze.rxq[0].cursor == 1023 && !ze.rx_seed_eligible && ze.running);
    assert(ze.dp_users == 1 && ze.napi.enabled && enables == 1 && rearms == 1);
    assert(info_logs == 1 && !mmio_reads && !mmio_writes);
    expect_get(1023);
    stop(&ze);
    assert(!ze.dp_users && !ze.running && !ze.napi.enabled);
    /* Two cancels on the last stop: the RX retry work and the RX watchdog
     * that the first open armed. */
    assert(disables == 1 && irq_syncs == 1 && cancels == 2 && wd_arms == 1);
    assert(!ze.rx_retry.pending && !ze.wd_work.pending);
    zx_rx_seed_unpublish(&ze);
}
static void reject_all_poststart_writes(struct zx_eth *ze) {
    struct zx_eth before;
    char value[32];
    memcpy(&before, ze, sizeof(before));
    for (int seed = -1; seed < RING_ENTRIES; seed++) {
        snprintf(value, sizeof(value), "%d", seed);
        assert(param_set(value) == -EBUSY);
        assert(!memcmp(&before, ze, sizeof(before)));
    }
}
static void test_reopen_secondary_and_poststart_writes(void) {
    for (int requested = -1; requested <= 511; requested += 512) {
        struct zx_eth ze;
        fixture(&ze, true);
        zx_rx_seed_publish(&ze);
        assert(param_set(requested < 0 ? "-1" : "511") == 0);
        check_napi_order = true;
        expected_cursor = requested < 0 ? 0 : requested;
        assert(start(&ze) == 0);
        reject_all_poststart_writes(&ze);
        ze.rxq[0].cursor = 702; /* ordinary RX progress */
        ze.rxq[3].remaining = 5;
        ze.rxq[3].debt = true;
        unsigned saved_enables = enables, saved_logs = info_logs;
        assert(start(&ze) == 0); /* another port shares the already-started DP */
        assert(ze.dp_users == 2 && enables == saved_enables && info_logs == saved_logs);
        assert(ze.rxq[0].cursor == 702 && ze.rxq[3].debt);
        reject_all_poststart_writes(&ze);
        stop(&ze);
        assert(ze.dp_users == 1 && ze.napi.enabled);
        stop(&ze);
        assert(!ze.dp_users && !ze.napi.enabled && !ze.rx_seed_eligible);
        reject_all_poststart_writes(&ze);
        expected_cursor = 702;
        assert(start(&ze) == 0);
        assert(ze.rxq[0].cursor == 702 && ze.rxq[3].remaining == 5 && ze.rxq[3].debt);
        assert(info_logs == saved_logs && enables == saved_enables + 1);
        stop(&ze);
        /* A synthetic later PHY/open failure uses the real stop/unwind code;
         * it must not restore eligibility even if caller resets RX state. */
        memset(ze.rxq, 0, sizeof(ze.rxq));
        ze.rx_next = 0;
        ze.rx_inflight = -1;
        reject_all_poststart_writes(&ze);
        expected_cursor = 0;
        assert(start(&ze) == 0 && !ze.rxq[0].cursor && info_logs == saved_logs);
        stop(&ze);
        zx_rx_seed_unpublish(&ze);
    }
}
static void test_ineligible_cold_and_skip_no_apply(void) {
    struct zx_eth ze, before;
    fixture(&ze, false);
    zx_rx_seed_publish(&ze);
    expect_get(-1);
    assert(param_set("0") == -EBUSY && param_set("-1") == -EBUSY);
    const int values[] = {-1, 123, -2, INT_MAX};
    for (unsigned i = 0; i < ARRAY_SIZE(values); i++) {
        ze.rx_q0_seed = values[i];
        memcpy(&before, &ze, sizeof(ze));
        assert(seed_start(&ze) == 0); /* no apply or validation on reopen */
        assert(!memcmp(&before, &ze, sizeof(ze)));
    }
    ze.rx_q0_seed = -1;
    check_napi_order = true;
    expected_cursor = 0;
    assert(start(&ze) == 0 && !ze.rxq[0].cursor && !info_logs);
    stop(&ze);
    zx_rx_seed_unpublish(&ze);
}

static struct zx_eth *lock_expected_before, *lock_expected_after;
static void observe_before_lock(void) {
    assert(!rtnl_held && zx_dbg_ze == lock_expected_before);
}
static void observe_before_unlock(void) {
    assert(rtnl_held && zx_dbg_ze == lock_expected_after);
}
static void expect_publication(void (*operation)(struct zx_eth *), struct zx_eth *arg,
                               struct zx_eth *before, struct zx_eth *after) {
    lock_expected_before = before;
    lock_expected_after = after;
    before_blocking_lock = observe_before_lock;
    before_unlock = observe_before_unlock;
    unsigned old_locks = locks, old_unlocks = unlocks;
    operation(arg);
    assert(!before_blocking_lock && !before_unlock && zx_dbg_ze == after);
    assert(locks == old_locks + 1 && unlocks == old_unlocks + 1);
    check_balanced();
}
static struct zx_eth *replace_old, *replace_new;
static void replace_at_trylock(void) {
    assert(!rtnl_held);
    zx_rx_seed_unpublish(replace_old);
    zx_rx_seed_publish(replace_new);
}
static void test_publication_rebind_lifetime(void) {
    struct zx_eth newer;
    size_t page = (size_t)sysconf(_SC_PAGESIZE);
    size_t length = (sizeof(struct zx_eth) + page - 1) / page * page;
    struct zx_eth *old = mmap(NULL, length, PROT_READ | PROT_WRITE,
                             MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(old != MAP_FAILED);
    fixture(old, true);
    fixture(&newer, true);
    expect_publication(zx_rx_seed_publish, old, NULL, old);
    assert(param_set("987") == 0);
    old->removing = true;
    expect_get(-1);
    assert(param_set("-1") == -EBUSY);
    expect_publication(zx_rx_seed_unpublish, old, old, NULL);
    assert(mprotect(old, length, PROT_NONE) == 0); /* stale access now faults */
    expect_get(-1);
    assert(param_set("0") == -ENODEV && param_set("-1") == -ENODEV);
    expect_publication(zx_rx_seed_publish, &newer, NULL, &newer);
    expect_get(-1); /* no stale module-global seed carried into new device */
    assert(newer.rx_q0_seed == -1 && !newer.rxq[0].cursor);
    assert(param_set("5") == 0 && newer.rx_q0_seed == 5);
    expect_publication(zx_rx_seed_unpublish, old, &newer, &newer);
    expect_get(5); /* stale teardown cannot unpublish current device */
    expect_publication(zx_rx_seed_unpublish, &newer, &newer, NULL);
    assert(munmap(old, length) == 0);
    assert(!mmio_reads && !mmio_writes && !info_logs);
}
static void test_target_sampled_only_after_rtnl(void) {
    struct zx_eth old, newer;
    fixture(&old, true);
    fixture(&newer, true);
    zx_rx_seed_publish(&old);
    assert(param_set("888") == 0);
    replace_old = &old;
    replace_new = &newer;
    before_try = replace_at_trylock;
    assert(param_set("42") == 0);
    assert(!before_try && zx_dbg_ze == &newer);
    assert(old.rx_q0_seed == 888 && newer.rx_q0_seed == 42);
    zx_rx_seed_unpublish(&newer);
    zx_rx_seed_publish(&old);
    before_try = replace_at_trylock;
    expect_get(42);
    assert(!before_try && zx_dbg_ze == &newer);
    zx_rx_seed_unpublish(&newer);
}

int main(int argc, char **argv) {
    assert(argc == 2 && RING_ENTRIES == 1024 && ZX_RX_RINGS == 16);
    const struct { const char *name; void (*run)(void); } cases[] = {
        {"before_probe", test_before_probe_and_parse},
        {"ranges", test_all_ranges_and_readback},
        {"invalid", test_invalid_input_no_mutation},
        {"busy", test_trylock_busy},
        {"idle_guards", test_every_idle_guard},
        {"default_cancel", test_cancel_and_default_baseline},
        {"armed_q0", test_armed_only_q0_and_once},
        {"first_open", test_first_open_order_and_atomic_failures},
        {"reopen", test_reopen_secondary_and_poststart_writes},
        {"ineligible", test_ineligible_cold_and_skip_no_apply},
        {"lifetime", test_publication_rebind_lifetime},
        {"target_after_lock", test_target_sampled_only_after_rtnl}
    };
    for (unsigned i = 0; i < ARRAY_SIZE(cases); i++) {
        if (!strcmp(argv[1], cases[i].name)) {
            cases[i].run();
            check_balanced();
            assert(!zx_dbg_ze);
            assert(!before_try && !before_blocking_lock && !before_unlock);
            printf("PASS exact driver C: %s\n", cases[i].name);
            return 0;
        }
    }
    fprintf(stderr, "Unknown case: %s\n", argv[1]);
    return 2;
}
'''


MARKER_STEMS = ['ZX_RX_SEED_R202'] + [
    f'ZX_RX_SEED_R202_{suffix}'
    for suffix in ('FIELDS', 'DECL', 'START', 'INIT', 'WARM', 'PUBLISH')
]


def strip_approved_r204(text):
    """Accept only the explicit R204 overlay on the frozen R202 control."""
    if 'ZX_TX_ORIGIN_R204' not in text:
        return text
    for suffix in ('HELPER', 'LOCAL', 'INITIALIZED', 'ASSIGN'):
        stem = f'ZX_TX_ORIGIN_R204_{suffix}'
        marked(text, stem)
        indent = '' if suffix == 'HELPER' else '\t'
        pattern = (r'^' + indent + r'/\* ' + stem + r'_BEGIN \*/\n.*?'
                   r'^' + indent + r'/\* ' + stem + r'_END \*/\n')
        if suffix == 'HELPER':
            pattern += r'\n'  # The new helper's own following separator.
        replacement = ('\tze->tx_next = (readl(ze->tmq + TMQ_TXIDX) & 0xffff) '
                       '% RING_ENTRIES;\n') if suffix == 'ASSIGN' else ''
        text, n = re.subn(pattern, lambda _: replacement, text, flags=re.M | re.S)
        if n != 1:
            raise AssertionError(f'Expected exact approved R204 delta for {stem}')
    if 'ZX_TX_ORIGIN_R204' in text:
        raise AssertionError('Unrecognized R204 marker remains')
    expected = '10f66ed8625f9e376043c866725664a060bbc3ed85e26a46770c1c0e5f3fbf75'
    if hashlib.sha256(text.encode()).hexdigest() != expected:
        raise AssertionError('R204 must restore the exact frozen R202 control')
    return text


def reconstruct_r201(text):
    """Reverse approved R204 then R202 deltas; retain the frozen R201 proof."""
    text = strip_approved_r204(text)
    for stem in MARKER_STEMS:
        marked(text, stem)  # Fail on duplicates, missing pairs, or bad order.
        pattern = (r'^[ \t]*/\* ' + re.escape(stem) + r'_BEGIN \*/\n.*?'
                   r'^[ \t]*/\* ' + re.escape(stem) + r'_END \*/\n')
        text, n = re.subn(pattern, '', text, flags=re.M | re.S)
        if n != 1:
            raise AssertionError(f'Expected full-line marker delta for {stem}')
    replacements = {
        '\t/* ZX_RX_SEED_R202_DEFER_PUBLISH */': '\tzx_dbg_ze = ze;',
        '\t/* ZX_RX_SEED_R202_UNPUBLISH */\n\tzx_rx_seed_unpublish(ze);':
            '\tzx_dbg_ze = NULL;',
    }
    for before, after in replacements.items():
        if text.count(before) != 1:
            raise AssertionError(f'Missing unique original-pointer replacement: {before}')
        text = text.replace(before, after)
    return text


def host_translation_unit(text):
    definitions = []
    for name in ('RING_ENTRIES', 'ZX_RX_RINGS', 'TMC_IRQ_MASK'):
        match = re.search(r'^#define\s+' + name + r'\s+[^\n]+', text, re.M)
        if not match:
            raise AssertionError(f'Missing actual driver constant {name}')
        definitions.append(match.group())
    queue = re.search(r'^struct zx_rx_queue \{.*?^\};', text, re.M | re.S)
    pointer = re.search(r'^static struct zx_eth \*zx_dbg_ze;[^\n]*', text, re.M)
    if not queue or not pointer:
        raise AssertionError('Missing original queue declaration or debug pointer')
    # No substitutions or token reconstruction in any compiled driver fragment.
    # The only surrounding generated functions isolate original probe statements
    # from hardware setup; their statements are verbatim marker contents.
    return '\n'.join([
        STUBS, *definitions, queue.group(), STRUCT_PREFIX,
        marked(text, 'ZX_RX_SEED_R202_FIELDS'), BOUNDARIES, pointer.group(),
        '#line 1 "exact-driver-r202-block"', marked(text, 'ZX_RX_SEED_R202'),
        '#line 1 "exact-driver-software-pending"', function(text, 'zx_rx_software_pending'),
        '#line 1 "exact-driver-dp-start"', function(text, 'zx_dp_start'),
        '#line 1 "exact-driver-dp-stop"', function(text, 'zx_dp_stop'),
        '#line 1 "exact-driver-probe-seed-init"',
        'static void probe_seed_init(struct zx_eth *ze) {',
        marked(text, 'ZX_RX_SEED_R202_INIT'), '}',
        '#line 1 "exact-driver-verified-warm-seed-init"',
        'static void verified_warm_seed_init(struct zx_eth *ze) {',
        marked(text, 'ZX_RX_SEED_R202_WARM'), '}',
        '#line 1 "r202-test-cases"', CASES,
    ])


@needs_artifacts()
class RxSeedRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = SOURCE.read_text()
        cls.temp = tempfile.TemporaryDirectory(prefix='rx-seed-r202-')
        cls.addClassCleanup(cls.temp.cleanup)
        c = Path(cls.temp.name) / 'rx_seed_test.c'
        cls.exe = Path(cls.temp.name) / 'rx_seed_test'
        c.write_text(host_translation_unit(text))
        compiler = shlex.split(os.environ.get('CC', 'cc'))
        command = compiler + ['-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                              str(c), '-o', str(cls.exe)]
        built = subprocess.run(command, capture_output=True, text=True, timeout=60)
        if built.returncode:
            raise AssertionError('Host C compilation failed:\n' + built.stdout + built.stderr)

    def run_case(self, name):
        result = subprocess.run([str(self.exe), name], capture_output=True, text=True,
                                timeout=30, cwd=self.temp.name)
        self.assertEqual(result.returncode, 0,
                         f'{name}: exit {result.returncode}\n{result.stdout}{result.stderr}')
        self.assertIn(f'PASS exact driver C: {name}', result.stdout)

    def test_callback_before_probe_runtime_only_and_registration(self):
        self.run_case('before_probe')

    def test_every_legal_seed_stages_only_and_reads_back(self):
        self.run_case('ranges')

    def test_malformed_overflow_out_of_range_never_take_rtnl_or_mutate(self):
        self.run_case('invalid')

    def test_callback_trylock_busy_no_state_or_output_mutation(self):
        self.run_case('busy')

    def test_all_device_and_every_ring_idle_guard(self):
        self.run_case('idle_guards')

    def test_pending_cancel_and_default_nonidle_baseline_freeze(self):
        self.run_case('default_cancel')

    def test_every_armed_seed_changes_only_q0_once_with_readback(self):
        self.run_case('armed_q0')

    def test_first_open_seed_precedes_napi_and_failures_are_atomic(self):
        self.run_case('first_open')

    def test_secondary_open_close_reopen_unwind_and_all_poststart_writes(self):
        self.run_case('reopen')

    def test_cold_blind_skip_and_ineligible_never_apply(self):
        self.run_case('ineligible')

    def test_rtnl_publication_removal_rebind_and_protected_stale_device(self):
        self.run_case('lifetime')

    def test_setter_and_getter_sample_rebound_target_after_lock(self):
        self.run_case('target_after_lock')


@needs_artifacts()
class RxSeedSourcePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SOURCE.read_text()
        cls.block = marked(cls.text, 'ZX_RX_SEED_R202')

    def test_archived_r201_whole_file_reconstruction(self):
        original = reconstruct_r201(ARCHIVE.read_text())
        self.assertEqual(len(original.splitlines()), 4283)
        self.assertEqual(hashlib.sha256(original.encode()).hexdigest(), R201_SHA256,
                         'Non-R202 source delta: do not refresh the frozen R201 hash')

    def test_archived_r201_trace_block_byte_identical(self):
        trace = marked(ARCHIVE.read_text(), 'ZX_PACKET_TRACE_R201')
        self.assertEqual(hashlib.sha256(trace.encode()).hexdigest(), R201_BLOCK_SHA256)

    def test_archived_poll_xmit_open_stop_and_teardown_tokens_frozen(self):
        for name, digest in FUNCTION_SHA256.items():
            with self.subTest(function=name):
                self.assertEqual(function_digest(ARCHIVE.read_text(), name), digest)

    def test_no_mmio_or_hidden_hardware_helper_in_seed_code(self):
        ids = set(t for t in tokens(self.block) if re.fullmatch(r'[A-Za-z_]\w*', t))
        forbidden = re.compile(
            r'(?:__raw_)?(?:read|write)[bwlq](?:_relaxed)?|'
            r'(?:devm_)?ioremap\w*|iounmap|ioread\w*|iowrite\w*|'
            r'memcpy_(?:to|from)io|memset_io|dma_\w*|'
            r'BM_\w*|TM[CDQ]_\w*|zx_desc_\w*|zx_rx_(?:retire|release|rearm)|'
            r'zx_eth_singleton|__iomem|tmc|tmd|tmq|bm|mac|macs|ring|txring|bufs|bufs2')
        # "ring" is also the local loop index; only reject actual member access.
        forbidden_ids = sorted(t for t in ids if forbidden.fullmatch(t) and t != 'ring')
        self.assertEqual(forbidden_ids, [])
        self.assertNotIn('-> ring', ' '.join(tokens(self.block)))
        ts = tokens(self.block)
        calls = {ts[i] for i in range(len(ts) - 1)
                 if re.fullmatch(r'[A-Za-z_]\w*', ts[i]) and ts[i + 1] == '('}
        self.assertLessEqual(calls, {
            'if', 'for', 'IS_ENABLED', 'READ_ONCE', 'ASSERT_RTNL', 'kstrtoint', 'scnprintf',
            'rtnl_trylock', 'rtnl_lock', 'rtnl_unlock', 'netdev_info',
            'module_param_cb', 'MODULE_PARM_DESC', 'zx_rx_seed_idle',
            'zx_rx_q0_seed_set', 'zx_rx_q0_seed_get', 'zx_rx_seed_start',
            'zx_rx_seed_publish', 'zx_rx_seed_unpublish',
        })
        self.assertEqual(ts.count('netdev_info'), 1)
        self.assertIn('RXSEED_R202', function(self.block, 'zx_rx_seed_start'))
        for name in ('zx_rx_seed_idle', 'zx_rx_q0_seed_set', 'zx_rx_q0_seed_get',
                     'zx_rx_seed_publish', 'zx_rx_seed_unpublish'):
            self.assertNotIn('netdev_info', tokens(function(self.block, name)))

    def test_per_device_fields_base_zero_custom_getter_and_no_global_request(self):
        fields = tokens(marked(self.text, 'ZX_RX_SEED_R202_FIELDS'))
        self.assertEqual(fields, tokens('int rx_q0_seed; bool rx_seed_eligible;'))
        self.assertEqual(tokens(marked(self.text, 'ZX_RX_SEED_R202_INIT')),
                         tokens('ze->rx_q0_seed = -1;'))
        index_once(tokens(self.block),
                   'module_param_cb(rx_q0_seed, &zx_rx_q0_seed_ops, NULL, 0644);')
        index_once(tokens(self.block), '.get = zx_rx_q0_seed_get,')
        setter = tokens(function(self.block, 'zx_rx_q0_seed_set'))
        index_once(setter, 'kstrtoint(value, 0, &seed)')
        index_once(setter, 'ze->rx_q0_seed = seed;')
        self.assertNotIn('rxq', setter)
        self.assertNotRegex(self.text, r'\bstatic\s+int\s+(?:zx_)?rx_q0_seed\s*[;=]')
        self.assertNotIn('param_get_int', tokens(self.block))

    def test_callbacks_only_resolve_device_under_rtnl(self):
        for name in ('zx_rx_q0_seed_set', 'zx_rx_q0_seed_get'):
            with self.subTest(function=name):
                body = tokens(function(self.block, name))
                attempt = index_once(body, 'if (!rtnl_trylock()) return -EBUSY;')
                unlock = index_once(body, 'rtnl_unlock();')
                pointer_refs = [i for i, t in enumerate(body) if t == 'zx_dbg_ze']
                self.assertTrue(pointer_refs)
                self.assertTrue(all(attempt < i < unlock for i in pointer_refs))
                self.assertNotIn('rtnl_lock', body)
        getter = tokens(function(self.block, 'zx_rx_q0_seed_get'))
        self.assertLess(index_once(getter, 'rtnl_unlock();'), getter.index('scnprintf'))

    def test_eligibility_only_positive_verified_warm_not_blind_skip(self):
        probe = tokens(function(self.text, 'zx_eth_probe'))
        warm = tokens('if (IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG) && !zx_force_dp_init && zx_datapath_warm(ze)) {')
        warm_start = index_once(probe, ' '.join(warm)) + len(warm)
        depth, warm_end = 1, warm_start
        while depth:
            depth += (probe[warm_end] == '{') - (probe[warm_end] == '}')
            warm_end += 1
        arm = index_once(probe, 'ze->rx_seed_eligible = true;')
        self.assertLess(warm_start, arm)
        self.assertLess(arm, warm_end)
        whole = ' '.join(tokens(self.text))
        self.assertEqual(whole.count('rx_seed_eligible = true'), 1)
        # Cleared once by the first-open seed, and once more by the datapath
        # reset (zx_dp_reset_work), which re-runs cold init: after it there
        # is no warm U-Boot state left to seed from.
        reset = ' '.join(tokens(function(self.text, 'zx_dp_reset_work')))
        self.assertEqual(reset.count('rx_seed_eligible = false'), 1)
        self.assertNotIn('rx_seed_eligible = true', reset)
        self.assertEqual(whole.count('rx_seed_eligible = false'), 2)
        self.assertEqual(tokens(marked(self.text, 'ZX_RX_SEED_R202_WARM')),
                         tokens('ze->rx_seed_eligible = true;'))
        skip = index_once(probe, 'if (IS_ENABLED(CONFIG_ZX279128_ETH_DEBUG) && zx_skip_dp_init) {')
        self.assertLess(skip, warm_start)
        self.assertNotIn('rx_seed_eligible', probe[skip:warm_start - len(warm)])
        # devm_alloc_etherdev zeroes private data: false until the verified branch.
        self.assertLess(index_once(probe, 'ndev = devm_alloc_etherdev(dev, sizeof(*ze));'),
                        index_once(probe, 'ze->rx_q0_seed = -1;'))
        self.assertLess(index_once(probe, 'ze->rx_q0_seed = -1;'), skip)

    def test_start_hook_precedes_user_count_napi_running_and_rearm(self):
        body = tokens(function(self.text, 'zx_dp_start'))
        hook = index_once(body, 'int ret = zx_rx_seed_start(ze); if (ret) return ret;')
        for snippet in ('ze->dp_users++', 'napi_enable(&ze->napi);',
                        'ze->running = true;', 'zx_rx_rearm(ze, software_pending);'):
            self.assertLess(hook, index_once(body, snippet))
        self.assertEqual(body.count('zx_rx_seed_start'), 1)
        seed = tokens(function(self.block, 'zx_rx_seed_start'))
        index_once(seed, 'ze->rxq[0].cursor = seed;')
        index_once(seed, 'ze->rx_seed_eligible = false;')
        self.assertEqual(seed.count('cursor'), 2)  # one assignment + one readback log
        self.assertNotIn('dp_users', seed)
        self.assertNotIn('napi_enable', seed)
        self.assertIn('ASSERT_RTNL', seed)
        self.assertIn('ASSERT_RTNL', tokens(function(self.block, 'zx_rx_seed_idle')))

    def test_both_open_paths_abort_before_mac_and_phy_writes(self):
        for name in ('zx_eth_open', 'zx_port_open'):
            with self.subTest(function=name):
                body = tokens(function(self.text, name))
                hook = index_once(body, 'ret = zx_dp_start(ze); if (ret) return ret;')
                for effect in ('writel', 'zx_mac_enable', 'of_phy_connect', 'phy_start',
                               'netif_start_queue', 'zx_eth_set_hw_mac'):
                    if effect in body:
                        self.assertLess(hook, body.index(effect), effect)
                self.assertEqual(body.count('zx_dp_start'), 1)
        # Both exported ndo_open methods really lead to the checked functions.
        whole = tokens(self.text)
        index_once(whole, '.ndo_open = zx_eth_open,')
        index_once(whole, '.ndo_open = zx_port_open,')

    def test_publication_follows_fatal_gates_and_precedes_proc_exposure(self):
        probe = tokens(function(self.text, 'zx_eth_probe'))
        tail = tokens('return 0; }')
        self.assertEqual(probe[-len(tail):], tail)
        publication = index_once(probe, 'zx_rx_seed_publish(ze);')
        self.assertEqual(probe[publication:].count('return'), 1)
        self.assertLess(publication, probe.index('proc_create'))
        self.assertLess(probe.index('zx_bm_seed_freelists'), probe.index('devm_register_netdev'))
        self.assertNotIn('zx_dbg_ze', probe)
        self.assertGreater(probe.index('zx_rx_seed_publish'), probe.index('devm_register_netdev'))
        self.assertGreater(probe.index('zx_rx_seed_publish'), probe.index('zx_eth_add_port_ndev'))

    def test_publication_and_unpublication_same_rtnl_lock_before_devm_free(self):
        pub = tokens(function(self.block, 'zx_rx_seed_publish'))
        unpub = tokens(function(self.block, 'zx_rx_seed_unpublish'))
        self.assertEqual(pub[pub.index('{'):],
                         tokens('{ rtnl_lock(); zx_dbg_ze = ze; rtnl_unlock(); }'))
        self.assertEqual(unpub[unpub.index('{'):], tokens(
            '{ rtnl_lock(); if (zx_dbg_ze == ze) zx_dbg_ze = NULL; rtnl_unlock(); }'))
        remove = tokens(function(self.text, 'zx_eth_remove'))
        close = index_once(remove, 'zx_eth_close_ports(ze);')
        unpublish = index_once(remove, 'zx_rx_seed_unpublish(ze);')
        self.assertLess(close, unpublish)
        self.assertLess(unpublish, len(remove) - 1)  # devres frees after remove returns
        self.assertNotIn('zx_dbg_ze', remove)
        self.assertNotIn('free_netdev', remove)
        self.assertNotIn('kfree', remove)
        assignments = re.findall(r'\bzx_dbg_ze\s*=\s*(?![=])([^;]+);', self.text)
        self.assertEqual(assignments, ['ze', 'NULL'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
