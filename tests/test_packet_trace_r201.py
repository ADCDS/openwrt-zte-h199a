"""Offline R201 tests: compile the exact marked driver C, never a decoder copy.

Run: python3 tests/test_packet_trace_r201.py
Only a host compiler and temporary files are used. No kernel build, hardware,
network, or sanitizer runtime is needed. Read-only, guard-page-backed frames
make advertised-length overreads and writes fail deterministically on Linux.
The fake spinlock's one-shot before-lock callback models a waiter crossing a
parameter reset; these tests do not claim to prove real SMP memory ordering.
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
BEGIN = '/* ZX_PACKET_TRACE_R201_BEGIN */'
END = '/* ZX_PACKET_TRACE_R201_END */'

# Preserve string/character literals while stripping comments and tokenizing C.
C_LEX = re.compile(r'/\*.*?\*/|//[^\n]*|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_]\w*|0[xX][0-9a-fA-F]+[uUlL]*|\d+[uUlL]*|>>=|<<=|->|\+\+|--|&&|\|\||==|!=|<=|>=|<<|>>|\+=|-=|\*=|/=|&=|\|=|\^=|\S', re.S)


def tokens(text):
    return [m.group() for m in C_LEX.finditer(text)
            if not m.group().startswith(('/*', '//'))]


def function_tokens(text, name):
    ts = tokens(text)
    for i, token in enumerate(ts):
        if token != name or i + 1 == len(ts) or ts[i + 1] != '(':
            continue
        level = 0
        j = i + 1
        while j < len(ts):
            level += (ts[j] == '(') - (ts[j] == ')')
            j += 1
            if not level:
                break
        if j == len(ts) or ts[j] != '{':
            continue
        level = 1
        j += 1
        while level:
            if j == len(ts):
                raise AssertionError(f'Unterminated function {name}')
            level += (ts[j] == '{') - (ts[j] == '}')
            j += 1
        return ts[i:j]
    raise AssertionError(f'No function definition for {name}')


TX_HOOK = tokens('zx_packet_trace_add(skb->data, skb->len, true, txport, -1, slot, idx, 0);')
RX_HOOK = tokens('zx_packet_trace_add(skb->data, skb->len, false, zx_rx_port_of(word1), ring, cur, idx, pool);')


def hook_index(body, hook):
    matches = [i for i in range(len(body) - len(hook) + 1)
               if body[i:i + len(hook)] == hook]
    if len(matches) != 1:
        raise AssertionError(f'Expected one exact hook, found {len(matches)}: {" ".join(hook)}')
    return matches[0]


def datapath_digest(text, name, hook):
    body = function_tokens(text, name)
    i = hook_index(body, hook)
    del body[i:i + len(hook)]
    return hashlib.sha256(' '.join(body).encode()).hexdigest()


# R201 integration reference: existing canonical R200 datapath, excluding ONLY
# each exact new RAM trace hook. Token hashes ignore whitespace/comments, but
# reject MMIO additions, descriptor changes, ring/reclaim policy edits, etc.
# Do not refresh these hashes merely to make an unintended datapath edit pass.
DATAPATH_REFERENCE = {
    'zx_eth_xmit': '8157145942c3ec75090d022068480e8ece21527b014e30496a01b5c3733046eb',
    'zx_eth_poll': '21f6e7d67cbdced529d24673e88566f1f7b6f9769a4b048db566be0293e03eef',
}

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
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/types.h>
#include <unistd.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
typedef uint64_t u64;
#define ETH_HLEN 14
#define IPPROTO_ICMP 1
#define SZ_2K 2048
#define GFP_KERNEL 0
#define READ_ONCE(x) (x)
#define WRITE_ONCE(x, value) ((x) = (value))
#define DEFINE_SPINLOCK(name) int name
#define module_param_cb(name, ops, arg, mode)
#define MODULE_PARM_DESC(name, description)

static unsigned lock_calls, unlock_calls, clock_calls;
static bool locked;
static u64 now_ns = UINT64_C(4294967400), last_timestamp, wait_ns = 1000;
static void (*before_lock)(void), (*before_time)(void);
static void stub_lock(int *lock) {
    assert(lock != NULL && !locked);
    if (before_lock) {
        void (*hook)(void) = before_lock;
        before_lock = NULL;
        hook();
    }
    assert(!locked);
    now_ns += wait_ns;
    locked = true;
    lock_calls++;
}
static void stub_unlock(int *lock) {
    assert(lock != NULL && locked);
    locked = false;
    unlock_calls++;
}
#define spin_lock_irqsave(lock, flags) do { (flags) = 0; stub_lock(lock); } while (0)
#define spin_unlock_irqrestore(lock, flags) do { (void)(flags); stub_unlock(lock); } while (0)
static u64 ktime_get_ns(void) {
    assert(!locked);
    clock_calls++;
    last_timestamp = now_ns;
    now_ns += 7;
    if (before_time) {
        void (*hook)(void) = before_time;
        before_time = NULL;
        hook();
    }
    return last_timestamp;
}

struct kernel_param { void *arg; };
struct kernel_param_ops {
    int (*set)(const char *, const struct kernel_param *);
    int (*get)(char *, const struct kernel_param *);
};
/* Kernel-like base-0 integer parsing, including a single final newline. */
static int kstrtoint(const char *text, unsigned base, int *value) {
    char *end;
    long v;
    if (!text || !*text || isspace((unsigned char)*text))
        return -EINVAL;
    errno = 0;
    v = strtol(text, &end, base);
    if (errno == ERANGE || v > INT_MAX || v < INT_MIN)
        return -ERANGE;
    if (end == text || (*end && strcmp(end, "\n")))
        return -EINVAL;
    *value = (int)v;
    return 0;
}
static int param_get_int(char *out, const struct kernel_param *kp) {
    return sprintf(out, "%d", *(int *)kp->arg);
}

#define OUT_CAP 65536
struct inode { int unused; };
struct seq_file { void *private; size_t used; char output[OUT_CAP]; };
struct file { void *private_data; };
struct proc_ops {
    int (*proc_open)(struct inode *, struct file *);
    ssize_t (*proc_read)(struct file *, char *, size_t, long long *);
    long long (*proc_lseek)(struct file *, long long, int);
    int (*proc_release)(struct inode *, struct file *);
};
struct allocation { void *ptr; size_t size; bool live; };
static struct allocation allocations[64];
static unsigned allocation_count, allocation_calls, free_calls;
static unsigned single_open_calls, single_release_calls, seq_calls;
static bool fail_allocation;
static int single_open_error, single_release_error;
static void *last_single_private;
static int (*last_show)(struct seq_file *, void *);
static struct allocation *live_allocation(void *ptr) {
    for (unsigned i = 0; i < allocation_count; i++)
        if (allocations[i].ptr == ptr && allocations[i].live)
            return &allocations[i];
    return NULL;
}
static void *kmalloc(size_t size, int flags) {
    assert(!locked && flags == GFP_KERNEL);
    allocation_calls++;
    if (fail_allocation)
        return NULL;
    assert(allocation_count < sizeof(allocations) / sizeof(allocations[0]));
    void *ptr = malloc(size);
    assert(ptr);
    memset(ptr, 0xa5, size);
    allocations[allocation_count++] = (struct allocation){ptr, size, true};
    return ptr;
}
static void kfree(void *ptr) {
    assert(!locked);
    if (!ptr)
        return;
    struct allocation *a = live_allocation(ptr);
    assert(a && "unknown pointer or snapshot freed more than once");
    a->live = false;
    memset(ptr, 0xdd, a->size);
    free(ptr);
    free_calls++;
}
static int single_open(struct file *file, int (*show)(struct seq_file *, void *), void *data) {
    assert(!locked && file->private_data == NULL && live_allocation(data));
    single_open_calls++;
    last_single_private = data;
    last_show = show;
    if (single_open_error)
        return single_open_error;
    struct seq_file *m = calloc(1, sizeof(*m));
    assert(m);
    m->private = data;
    file->private_data = m;
    return 0;
}
static int single_release(struct inode *inode, struct file *file) {
    (void)inode;
    assert(!locked && file->private_data);
    struct seq_file *m = file->private_data;
    assert(live_allocation(m->private));
    free(m);
    file->private_data = NULL;
    single_release_calls++;
    return single_release_error;
}
static ssize_t seq_read(struct file *file, char *buf, size_t size, long long *off) {
    (void)file; (void)buf; (void)size; (void)off;
    return -ENOSYS;
}
static long long seq_lseek(struct file *file, long long off, int whence) {
    (void)file; (void)whence;
    return off;
}
static void seq_printf(struct seq_file *m, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
static void seq_printf(struct seq_file *m, const char *fmt, ...) {
    assert(!locked && m && m->private);
    seq_calls++;
    va_list ap;
    va_start(ap, fmt);
    int n = vsnprintf(m->output + m->used, OUT_CAP - m->used, fmt, ap);
    va_end(ap);
    assert(n >= 0 && (size_t)n < OUT_CAP - m->used);
    m->used += (size_t)n;
}
static void seq_puts(struct seq_file *m, const char *text) {
    seq_printf(m, "%s", text);
}
'''

CASES = r'''
#define CAPACITY (BUF_SIZE - BUF_HDR)
static struct kernel_param kp = { .arg = &zx_packet_trace_id };
static void set_id(const char *text) {
    assert(zx_packet_trace_ops.set(text, &kp) == 0);
    assert(!locked && lock_calls == unlock_calls);
}
static void put16(u8 *p, unsigned value) {
    p[0] = value >> 8;
    p[1] = value;
}
/* A packet fixture builder, NOT an alternative implementation of the decoder. */
static u32 packet(u8 *p, unsigned words, unsigned payload, unsigned padding,
                  unsigned type, unsigned id, unsigned seq) {
    unsigned ihl = words * 4, total = ihl + 8 + payload;
    unsigned len = ETH_HLEN + total + padding;
    assert(words >= 5 && words <= 15 && len <= CAPACITY);
    memset(p, 0, CAPACITY + 1);
    for (unsigned i = 0; i < 12; i++)
        p[i] = 0x90 + i;
    put16(p + 12, 0x0800);
    u8 *ip = p + ETH_HLEN;
    ip[0] = 0x40 | words;
    ip[1] = 0x5a;
    put16(ip + 2, total);
    put16(ip + 4, 0xb17e);
    ip[8] = 64;
    ip[9] = IPPROTO_ICMP;
    ip[12] = 192; ip[13] = 0; ip[14] = 2; ip[15] = 1;
    ip[16] = 198; ip[17] = 51; ip[18] = 100; ip[19] = 2;
    for (unsigned i = 20; i < ihl; i++)
        ip[i] = 0xa0 + i;
    u8 *icmp = ip + ihl;
    icmp[0] = type;
    put16(icmp + 4, id);
    put16(icmp + 6, seq);
    for (unsigned i = 0; i < payload; i++)
        icmp[8 + i] = (u8)i;
    memset(p + ETH_HLEN + total, 0xde, padding);
    return len;
}
static void decode_fields(const struct zx_packet_record *r, u32 len,
                          unsigned words, unsigned payload, unsigned type,
                          unsigned id, unsigned seq) {
    assert(r->frame == len && r->iplen == words * 4 + 8 + payload);
    assert(r->payloadlen == payload && r->ipid == 0xb17e);
    assert(r->src == 0xc0000201U && r->dst == 0xc6336402U);
    assert(r->type == type && r->id == id && r->seq == seq);
}
static const char *render(struct file *file) {
    struct seq_file *m = file->private_data;
    unsigned locks = lock_calls, clocks = clock_calls, allocs = allocation_calls;
    assert(m && live_allocation(m->private));
    m->used = 0;
    m->output[0] = '\0';
    assert(zx_packets_show(m, NULL) == 0);
    assert(lock_calls == locks && clock_calls == clocks && allocation_calls == allocs);
    return m->output;
}
static void close_snapshot(struct file *file) {
    unsigned frees = free_calls, releases = single_release_calls;
    assert(zx_packets_pops.proc_release(NULL, file) == single_release_error);
    assert(file->private_data == NULL);
    assert(free_calls == frees + 1 && single_release_calls == releases + 1);
}

static void test_default_off(void) {
    assert(zx_packet_trace_id == -1);
    assert(zx_packet_trace.filter_id == -1 && zx_packet_trace.armed_id == -1);
    assert(zx_packet_trace.generation == 0 && zx_packet_trace.count == 0);
    assert(zx_packet_trace.dropped == 0 && ZX_PACKET_TRACE_MAX == 128);
    /* PROT_NONE is deliberately not a valid readable skb: the gate must win. */
    size_t page = (size_t)sysconf(_SC_PAGESIZE);
    void *inaccessible = mmap(NULL, page, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(inaccessible != MAP_FAILED);
    zx_packet_trace_add(inaccessible, UINT32_MAX, true, 3, -1, 127, 0x123, 0);
    zx_packet_trace_add(NULL, 42, false, 0, 1, 2, 3, 4);
    assert(clock_calls == 0 && lock_calls == 0 && allocation_calls == 0);
    assert(munmap(inaccessible, page) == 0);
    assert(zx_packet_trace_ops.set == zx_packet_trace_set);
    assert(zx_packet_trace_ops.get == param_get_int);
    assert(zx_packets_pops.proc_read == seq_read && zx_packets_pops.proc_lseek == seq_lseek);
    char value[32];
    assert(zx_packet_trace_ops.get(value, &kp) == 2 && !strcmp(value, "-1"));
    printf("HOST_ABI sizeof(zx_packet_record)=%zu sizeof(zx_packet_snapshot)=%zu\n",
           sizeof(struct zx_packet_record), sizeof(struct zx_packet_snapshot));
    struct file file = {0};
    assert(zx_packets_pops.proc_open(NULL, &file) == 0);
    assert(!strcmp(render(&file),
        "PKTRACE_HEADER generation=0 enabled=0 filter_id=-1 armed_id=-1 records=0 dropped=0 tx_stage=pre-doorbell rx_stage=pre-eth_type_trans\nPKTRACE_END\n"));
    close_snapshot(&file);
}

static void test_parameters(void) {
    char value[64], got[64];
    /* Every legal integer, not just the boundaries. */
    for (int id = 0; id <= 65535; id++) {
        snprintf(value, sizeof(value), "%d", id);
        u32 generation = zx_packet_trace.generation;
        set_id(value);
        assert(zx_packet_trace_id == id && zx_packet_trace.filter_id == id);
        assert(zx_packet_trace.armed_id == id && zx_packet_trace.generation == generation + 1);
        assert(zx_packet_trace.count == 0 && zx_packet_trace.dropped == 0);
        assert(zx_packet_trace_ops.get(got, &kp) == (int)strlen(value));
        assert(!strcmp(value, got));
    }
    const struct { const char *text; int result; } good[] = {
        {"0xBEEF", 48879}, {"017", 15}, {"+42", 42}, {"65535\n", 65535}, {"-1", -1}
    };
    for (unsigned i = 0; i < sizeof(good) / sizeof(good[0]); i++) {
        u32 generation = zx_packet_trace.generation;
        set_id(good[i].text);
        assert(zx_packet_trace_id == good[i].result);
        assert(zx_packet_trace.filter_id == good[i].result);
        assert(zx_packet_trace.generation == generation + (good[i].result >= 0));
    }
    const struct { const char *text; int error; } bad[] = {
        {"-2", -EINVAL}, {"65536", -EINVAL}, {"0x10000", -EINVAL},
        {"2147483647", -EINVAL}, {"-2147483648", -EINVAL},
        {"2147483648", -ERANGE}, {"-2147483649", -ERANGE},
        {"99999999999999999999999999999999999", -ERANGE},
        {"", -EINVAL}, {"no", -EINVAL}, {"0x", -EINVAL}, {"1x", -EINVAL},
        {"--1", -EINVAL}, {"1 ", -EINVAL}, {" 1", -EINVAL},
        {"1\n\n", -EINVAL}, {"1\njunk", -EINVAL}
    };
    /* An invalid write cannot change even the padding/records or take the lock. */
    set_id("4660");
    u8 frame[CAPACITY + 1];
    u32 len = packet(frame, 5, 3, 0, 8, 4660, 1);
    zx_packet_trace_add(frame, len, false, 2, 1, 7, 101, 0);
    zx_packet_trace.dropped = 9;
    struct zx_packet_snapshot before = zx_packet_trace;
    unsigned locks = lock_calls;
    for (unsigned i = 0; i < sizeof(bad) / sizeof(bad[0]); i++) {
        assert(zx_packet_trace_ops.set(bad[i].text, &kp) == bad[i].error);
        assert(zx_packet_trace_id == 4660 && lock_calls == locks);
        assert(!memcmp(&before, &zx_packet_trace, sizeof(before)));
    }
}

static void test_decoder_payloads(void) {
    const struct { unsigned size; u32 hash; } vectors[] = {
        {0, 0x811c9dc5U}, {1, 0x050c5d1fU}, {3, 0x22ae7a28U},
        {7, 0xe4991188U}, {23, 0x126f8e68U}, {24, 0x849d51edU},
        {25, 0xb8a804afU}, {31, 0x4b84d038U}, {37, 0x2f2b1f2fU}
    };
    u8 frame[CAPACITY + 1], original[CAPACITY + 1];
    struct zx_packet_record r, padded;
    for (unsigned n = 0; n < sizeof(vectors) / sizeof(vectors[0]); n++) {
        unsigned payload = vectors[n].size;
        for (unsigned words = 5; words <= 15; words++) {
            for (unsigned type = 0; type <= 8; type += 8) {
                u32 len = packet(frame, words, payload, 0, type, 65535, 65244);
                memcpy(original, frame, sizeof(frame));
                memset(&r, 0xa5, sizeof(r));
                assert(zx_packet_decode(frame, len, 65535, &r));
                decode_fields(&r, len, words, payload, type, 65535, 65244);
                assert(r.hash == vectors[n].hash);
                assert(r.ns == 0 && !r.tx && r.port == 0 && r.ring == 0 && r.slot == 0);
                assert(r.buf == 0 && r.pool == 0);
                assert(!memcmp(frame, original, sizeof(frame)));
                /* Expected prefix from literal fixture bytes; also verifies zero-fill. */
                u8 expected[24] = {0};
                for (unsigned i = 0; i < payload && i < sizeof(expected); i++)
                    expected[i] = i;
                for (unsigned i = 0; i < 24; i++)
                    assert(((r.head[i / 4] >> (24 - (i % 4) * 8)) & 255) == expected[i]);
                unsigned pad = 19;
                u32 plen = packet(frame, words, payload, pad, type, 65535, 65244);
                assert(zx_packet_decode(frame, plen, 65535, &padded));
                assert(padded.frame == len + pad && padded.iplen == r.iplen);
                assert(padded.hash == r.hash && padded.payloadlen == r.payloadlen);
                assert(!memcmp(padded.head, r.head, sizeof(r.head)));
                memset(frame + len, 0x31, pad);
                assert(zx_packet_decode(frame, plen, 65535, &padded));
                assert(padded.hash == r.hash && !memcmp(padded.head, r.head, sizeof(r.head)));
            }
        }
    }
    u32 len = packet(frame, 5, 25, 0, 8, 0, 0);
    assert(zx_packet_decode(frame, len, 0, &r));
    const u32 first24[] = {0x00010203U, 0x04050607U, 0x08090a0bU,
                           0x0c0d0e0fU, 0x10111213U, 0x14151617U};
    assert(!memcmp(r.head, first24, sizeof(first24)));
    frame[len - 1] ^= 0xff; /* Byte 25 changes hash, not the 24-byte prefix. */
    assert(zx_packet_decode(frame, len, 0, &padded));
    assert(padded.hash != r.hash && !memcmp(padded.head, r.head, sizeof(r.head)));
    assert(lock_calls == 0 && clock_calls == 0 && allocation_calls == 0);
}

static void test_decoder_rejections(void) {
    u8 frame[CAPACITY + 1];
    struct zx_packet_record r;
    u32 len = packet(frame, 5, 37, 9, 8, 4660, 1);
    assert(!zx_packet_decode(NULL, len, 4660, &r));
    assert(!zx_packet_decode(frame, len, 4660, NULL));
    assert(!zx_packet_decode(frame, len, -1, &r));
    assert(!zx_packet_decode(frame, len, 65536, &r));
    assert(!zx_packet_decode(frame, len, 4661, &r));
    unsigned ether[] = {0, 0x0806, 0x86dd, 0x8100, 0x88a8, 0xffff};
    for (unsigned i = 0; i < sizeof(ether) / sizeof(ether[0]); i++) {
        put16(frame + 12, ether[i]);
        assert(!zx_packet_decode(frame, len, 4660, &r));
    }
    put16(frame + 12, 0x0800);
    for (unsigned version = 0; version < 16; version++) {
        frame[14] = (version << 4) | 5;
        assert(zx_packet_decode(frame, len, 4660, &r) == (version == 4));
    }
    for (unsigned ihl = 0; ihl < 5; ihl++) {
        frame[14] = 0x40 | ihl;
        assert(!zx_packet_decode(frame, len, 4660, &r));
    }
    frame[14] = 0x45;
    for (unsigned protocol = 0; protocol <= 255; protocol++) {
        frame[23] = protocol;
        assert(zx_packet_decode(frame, len, 4660, &r) == (protocol == 1));
    }
    frame[23] = 1;
    for (unsigned bit = 0; bit < 16; bit++) {
        put16(frame + 20, 1U << bit);
        assert(zx_packet_decode(frame, len, 4660, &r) == (bit == 14));
    }
    unsigned badfrags[] = {0x3fff, 0x6000, 0x8001, 0xffff};
    for (unsigned i = 0; i < sizeof(badfrags) / sizeof(badfrags[0]); i++) {
        put16(frame + 20, badfrags[i]);
        assert(!zx_packet_decode(frame, len, 4660, &r));
    }
    put16(frame + 20, 0);
    for (unsigned type = 0; type <= 255; type++) {
        frame[34] = type;
        assert(zx_packet_decode(frame, len, 4660, &r) == (type == 0 || type == 8));
    }
    for (unsigned type = 0; type <= 8; type += 8) {
        frame[34] = type;
        for (unsigned code = 0; code <= 255; code++) {
            frame[35] = code;
            assert(zx_packet_decode(frame, len, 4660, &r) == (code == 0));
        }
    }
    frame[35] = 0;
    for (unsigned total = 0; total <= len - ETH_HLEN + 1; total++) {
        put16(frame + 16, total);
        bool valid = total >= 28 && total <= len - ETH_HLEN;
        assert(zx_packet_decode(frame, len, 4660, &r) == valid);
        if (valid)
            assert(r.iplen == total && r.payloadlen == total - 28);
    }
    put16(frame + 16, 65535);
    assert(!zx_packet_decode(frame, len, 4660, &r));
    /* IHL/total bounds are independent of the minimal Ethernet+IPv4 guard. */
    len = packet(frame, 15, 0, 0, 8, 4660, 1);
    assert(zx_packet_decode(frame, len, 4660, &r));
    assert(!zx_packet_decode(frame, ETH_HLEN + 59, 4660, &r));
    put16(frame + 16, 67);
    assert(!zx_packet_decode(frame, len, 4660, &r));
    len = packet(frame, 5, CAPACITY - ETH_HLEN - 28, 0, 8, 4660, 1);
    assert(len == CAPACITY && zx_packet_decode(frame, len, 4660, &r));
    assert(!zx_packet_decode(frame, CAPACITY + 1, 4660, &r));
    assert(!zx_packet_decode(frame, UINT32_MAX, 4660, &r));
}

static void test_guarded_bounds(void) {
    size_t page = (size_t)sysconf(_SC_PAGESIZE);
    assert(page > CAPACITY + 1);
    u8 *map = mmap(NULL, 3 * page, PROT_NONE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    assert(map != MAP_FAILED);
    u8 *middle = map + page, original[CAPACITY + 1];
    struct zx_packet_record r;
    u32 full = packet(original, 5, 31, 0, 8, 4660, 1);
    set_id("4660");
    /* Every advertised length, including empty, truncations, and cap+1.
     * Frame end touches PROT_NONE and all accessible source bytes are RO. */
    for (u32 len = 0; len <= CAPACITY + 1; len++) {
        assert(mprotect(middle, page, PROT_READ | PROT_WRITE) == 0);
        u8 *frame = middle + page - len;
        memcpy(frame, original, len);
        assert(mprotect(middle, page, PROT_READ) == 0);
        bool valid = len >= full && len <= CAPACITY;
        assert(zx_packet_decode(frame, len, 4660, &r) == valid);
        zx_packet_trace_add(frame, len, false, 3, 2, 1, 7, 0);
        assert(!memcmp(frame, original, len));
    }
    /* Exhaust malformed IHL/total combinations on short end-guarded frames. */
    for (u32 len = ETH_HLEN + 20; len <= ETH_HLEN + 76; len++) {
        for (unsigned ihl = 0; ihl < 16; ihl++) {
            unsigned totals[] = {0, 1, 19, 20, ihl * 4 + 7, ihl * 4 + 8,
                                 len - ETH_HLEN, len - ETH_HLEN + 1, 65535};
            for (unsigned t = 0; t < sizeof(totals) / sizeof(totals[0]); t++) {
                assert(mprotect(middle, page, PROT_READ | PROT_WRITE) == 0);
                u8 *frame = middle + page - len;
                memcpy(frame, original, len);
                frame[14] = 0x40 | ihl;
                put16(frame + 16, totals[t]);
                assert(mprotect(middle, page, PROT_READ) == 0);
                (void)zx_packet_decode(frame, len, 4660, &r);
            }
        }
    }
    /* Source starts directly after a left guard; force unaligned byte reads too. */
    for (unsigned shift = 0; shift < 4; shift++) {
        assert(mprotect(middle, page, PROT_READ | PROT_WRITE) == 0);
        memcpy(middle + shift, original, full);
        assert(mprotect(middle, page, PROT_READ) == 0);
        assert(zx_packet_decode(middle + shift, full, 4660, &r));
        zx_packet_trace_add(middle + shift, full, true, 1, -1, 3, 4, 0);
        assert(!memcmp(middle + shift, original, full));
    }
    assert(munmap(map, 3 * page) == 0);
}

static void test_collector_budget(void) {
    u8 frame[CAPACITY + 1];
    set_id("4660");
    for (unsigned i = 0; i < ZX_PACKET_TRACE_MAX; i++) {
        u32 len = packet(frame, 5, 37, 9, (i & 1) ? 0 : 8, 4660, i);
        u64 timestamp = now_ns;
        zx_packet_trace_add(frame, len, !(i & 1), i % 4, (i & 1) ? 2 : -1,
                            i + 11, 0xf0000000U + i, i & 1);
        assert(zx_packet_trace.count == i + 1 && zx_packet_trace.dropped == 0);
        const struct zx_packet_record *r = &zx_packet_trace.records[i];
        decode_fields(r, len, 5, 37, (i & 1) ? 0 : 8, 4660, i);
        assert(r->ns == timestamp && r->ns < now_ns);
        assert(r->tx == !(i & 1) && r->port == (int)(i % 4));
        assert(r->ring == ((i & 1) ? 2 : -1) && r->slot == (int)i + 11);
        assert(r->buf == 0xf0000000U + i && r->pool == (i & 1));
        assert(r->hash == 0x2f2b1f2fU && r->head[5] == 0x14151617U);
    }
    struct zx_packet_snapshot full = zx_packet_trace;
    for (unsigned i = 0; i < 9; i++) {
        u32 len = packet(frame, 5, 0, 0, 8, 4660, 900 + i);
        zx_packet_trace_add(frame, len, true, 3, -1, 17, 1000, 0);
        assert(zx_packet_trace.count == 128 && zx_packet_trace.dropped == i + 1);
        assert(!memcmp(full.records, zx_packet_trace.records, sizeof(full.records)));
    }
    u32 len = packet(frame, 5, 3, 0, 8, 4661, 1);
    zx_packet_trace_add(frame, len, false, 0, 0, 0, 0, 0);
    zx_packet_trace_add(frame, 20, false, 0, 0, 0, 0, 0);
    assert(zx_packet_trace.count == 128 && zx_packet_trace.dropped == 9);
    struct file file = {0};
    assert(zx_packets_open(NULL, &file) == 0);
    const char *output = render(&file), *cursor = output;
    unsigned rows = 0;
    while ((cursor = strstr(cursor, "\nPKTRACE ns="))) {
        rows++;
        cursor++;
    }
    assert(rows == 128 && strstr(output, "records=128 dropped=9 "));
    assert(!strcmp(output + strlen(output) - strlen("PKTRACE_END\n"), "PKTRACE_END\n"));
    close_snapshot(&file);
    u32 generation = zx_packet_trace.generation;
    set_id("-1");
    assert(zx_packet_trace_id == -1 && zx_packet_trace.filter_id == -1);
    assert(zx_packet_trace.armed_id == 4660 && zx_packet_trace.generation == generation);
    assert(zx_packet_trace.count == 128 && zx_packet_trace.dropped == 9);
    assert(!memcmp(full.records, zx_packet_trace.records, sizeof(full.records)));
    unsigned clocks = clock_calls, locks = lock_calls;
    zx_packet_trace_add(NULL, UINT32_MAX, false, 9, 9, 9, 9, 9);
    assert(clock_calls == clocks && lock_calls == locks);
    set_id("-1");
    assert(zx_packet_trace.generation == generation && zx_packet_trace.dropped == 9);
    set_id("4660"); /* Rearm same ID: reset and advance, not an idempotent write. */
    assert(zx_packet_trace.generation == generation + 1 && zx_packet_trace.count == 0);
    assert(zx_packet_trace.armed_id == 4660 && zx_packet_trace.dropped == 0);
    const unsigned char *bytes = (const unsigned char *)zx_packet_trace.records;
    for (size_t i = 0; i < sizeof(zx_packet_trace.records); i++)
        assert(bytes[i] == 0);
    len = packet(frame, 5, 1, 0, 8, 4660, 1);
    zx_packet_trace_add(frame, len, false, 0, 3, 64, UINT32_MAX, 2);
    assert(zx_packet_trace.count == 1);
    set_id("4660"); /* Also rearm while already enabled. */
    assert(zx_packet_trace.generation == generation + 2 && zx_packet_trace.count == 0);
    set_id("7");
    assert(zx_packet_trace.generation == generation + 3 && zx_packet_trace.armed_id == 7);
    zx_packet_trace_add(frame, len, false, 0, 3, 64, UINT32_MAX, 2);
    assert(zx_packet_trace.count == 0 && zx_packet_trace.dropped == 0);
    len = packet(frame, 5, 1, 0, 8, 7, 1);
    zx_packet_trace_add(frame, len, false, 0, 3, 64, UINT32_MAX, 2);
    assert(zx_packet_trace.count == 1 && zx_packet_trace.records[0].buf == UINT32_MAX);
    assert(zx_packet_trace.records[0].pool == 2);
}

static u8 *time_frame;
static u32 waiting_frame_len;
static void later_rx_wins_lock(void) {
    assert(!locked);
    zx_packet_trace_add(time_frame, waiting_frame_len, false, 2, 3, 4, 5, 1);
}
static void repair_at_timestamp(void) {
    assert(clock_calls > 0 && !locked);
    time_frame[34] = 8;
}
static void assert_timestamp_precedes_wait(void) {
    assert(last_timestamp < now_ns && !locked);
    now_ns += 50000;
}
static void rearm_same_while_waiting(void) {
    assert_timestamp_precedes_wait();
    set_id("4660");
}
static void rearm_other_while_waiting(void) {
    assert_timestamp_precedes_wait();
    set_id("7");
}
static void disable_while_waiting(void) {
    assert_timestamp_precedes_wait();
    set_id("-1");
}
static void test_timestamp_and_generation(void) {
    u8 frame[CAPACITY + 1];
    u32 len = packet(frame, 5, 3, 0, 3, 4660, 1);
    set_id("4660");
    time_frame = frame;
    before_time = repair_at_timestamp;
    before_lock = assert_timestamp_precedes_wait;
    u64 timestamp = now_ns;
    zx_packet_trace_add(frame, len, true, 3, -1, 127, 55, 0);
    /* If parsing came before ktime, the initial non-echo would be rejected. */
    assert(zx_packet_trace.count == 1 && zx_packet_trace.records[0].ns == timestamp);
    assert(zx_packet_trace.records[0].ns + 50000 < now_ns);
    set_id("4660");
    timestamp = now_ns;
    waiting_frame_len = len;
    before_lock = later_rx_wins_lock;
    zx_packet_trace_add(frame, len, true, 3, -1, 127, 55, 0);
    assert(zx_packet_trace.count == 2);
    assert(!zx_packet_trace.records[0].tx && zx_packet_trace.records[1].tx);
    assert(zx_packet_trace.records[1].ns == timestamp);
    assert(zx_packet_trace.records[0].ns > zx_packet_trace.records[1].ns);
    /* Lock acquisition/append order is not necessarily timestamp order. */
    u32 generation = zx_packet_trace.generation;
    before_lock = rearm_same_while_waiting;
    zx_packet_trace_add(frame, len, true, 3, -1, 127, 55, 0);
    assert(zx_packet_trace.generation == generation + 1);
    assert(zx_packet_trace.count == 0 && zx_packet_trace.dropped == 0);
    /* Matching the NEW id still cannot import a timestamp from the old arm. */
    len = packet(frame, 5, 3, 0, 8, 7, 2);
    before_lock = rearm_other_while_waiting;
    zx_packet_trace_add(frame, len, false, 2, 3, 4, 5, 1);
    assert(zx_packet_trace.generation == generation + 2 && zx_packet_trace_id == 7);
    assert(zx_packet_trace.count == 0 && zx_packet_trace.dropped == 0);
    zx_packet_trace_add(frame, len, false, 2, 3, 4, 5, 1);
    assert(zx_packet_trace.count == 1);
    struct zx_packet_snapshot saved = zx_packet_trace;
    before_lock = disable_while_waiting;
    zx_packet_trace_add(frame, len, false, 2, 3, 4, 5, 1);
    assert(zx_packet_trace_id == -1 && zx_packet_trace.generation == saved.generation);
    assert(zx_packet_trace.count == saved.count && zx_packet_trace.dropped == saved.dropped);
    assert(!memcmp(zx_packet_trace.records, saved.records, sizeof(saved.records)));
    assert(before_lock == NULL && before_time == NULL && !locked);
}

static void allocation_exists_at_lock(void) {
    assert(allocation_count && allocations[allocation_count - 1].live);
    assert(allocations[allocation_count - 1].size == sizeof(struct zx_packet_snapshot));
    assert(!locked && single_open_calls == 0);
}
static void reset_before_snapshot_lock(void) {
    u8 frame[CAPACITY + 1];
    set_id("7");
    u32 len = packet(frame, 5, 1, 0, 0, 7, 77);
    zx_packet_trace_add(frame, len, false, 1, 2, 3, 4, 0);
}
static void test_proc_failures(void) {
    struct file file = {0};
    unsigned locks = lock_calls;
    fail_allocation = true;
    assert(zx_packets_open(NULL, &file) == -ENOMEM);
    assert(file.private_data == NULL && allocation_calls == 1 && allocation_count == 0);
    assert(lock_calls == locks && free_calls == 0 && single_open_calls == 0);
    fail_allocation = false;
    single_open_error = -EMFILE;
    before_lock = allocation_exists_at_lock;
    assert(zx_packets_open(NULL, &file) == -EMFILE);
    assert(before_lock == NULL && lock_calls == locks + 1);
    assert(allocation_count == 1 && free_calls == 1 && single_open_calls == 1);
    assert(!live_allocation(last_single_private) && file.private_data == NULL);
    assert(single_release_calls == 0 && last_show == zx_packets_show);
    single_open_error = 0;
    before_lock = reset_before_snapshot_lock;
    assert(zx_packets_open(NULL, &file) == 0);
    struct zx_packet_snapshot *snapshot = ((struct seq_file *)file.private_data)->private;
    assert(live_allocation(snapshot) && snapshot->filter_id == 7);
    assert(snapshot->count == 1 && snapshot->records[0].seq == 77);
    assert(!memcmp(snapshot, &zx_packet_trace, sizeof(*snapshot)));
    single_release_error = -EINTR;
    close_snapshot(&file); /* Preserve release's return code; free even on error. */
    assert(free_calls == 2 && single_release_calls == 1);
}

static void test_proc_snapshots(void) {
    u8 frame[CAPACITY + 1];
    struct file a = {0}, b = {0}, c = {0}, d = {0};
    char saved_a[OUT_CAP], saved_b[OUT_CAP], saved_c[OUT_CAP], expected[2048];
    set_id("4660");
    u32 len = packet(frame, 5, 25, 18, 8, 4660, 65244);
    u64 txns = now_ns;
    zx_packet_trace_add(frame, len, true, 3, -1, 127, 305419896U, 0);
    len = packet(frame, 7, 3, 7, 0, 4660, 2);
    u64 rxns = now_ns;
    zx_packet_trace_add(frame, len, false, 2, 3, 64, UINT32_MAX, 2);
    /* Exercise 64-bit output beyond the range of unsigned int. */
    zx_packet_trace.dropped = UINT64_C(4294967301);
    assert(zx_packets_open(NULL, &a) == 0);
    struct zx_packet_snapshot *sa = ((struct seq_file *)a.private_data)->private;
    assert(sa != &zx_packet_trace && !memcmp(sa, &zx_packet_trace, sizeof(*sa)));
    struct zx_packet_snapshot saved_snapshot = *sa;
    snprintf(expected, sizeof(expected),
        "PKTRACE_HEADER generation=1 enabled=1 filter_id=4660 armed_id=4660 records=2 dropped=4294967301 tx_stage=pre-doorbell rx_stage=pre-eth_type_trans\n"
        "PKTRACE ns=%llu dir=tx port=3 ring=-1 slot=127 buf=305419896 pool=0 frame=85 iplen=53 payloadlen=25 ipid=0xb17e src=0xc0000201 dst=0xc6336402 type=8 id=0x1234 seq=65244 hash=0xb8a804af head=000102030405060708090a0b0c0d0e0f1011121314151617\n"
        "PKTRACE ns=%llu dir=rx port=2 ring=3 slot=64 buf=4294967295 pool=2 frame=60 iplen=39 payloadlen=3 ipid=0xb17e src=0xc0000201 dst=0xc6336402 type=0 id=0x1234 seq=2 hash=0x22ae7a28 head=000102000000000000000000000000000000000000000000\n"
        "PKTRACE_END\n", (unsigned long long)txns, (unsigned long long)rxns);
    assert(!strcmp(render(&a), expected));
    strcpy(saved_a, render(&a));
    memset(frame, 0xee, sizeof(frame));
    assert(!strcmp(render(&a), saved_a));
    set_id("4660");
    len = packet(frame, 5, 0, 0, 8, 4660, 99);
    zx_packet_trace_add(frame, len, true, 1, -1, 4, 123, 0);
    assert(!strcmp(render(&a), saved_a));
    assert(zx_packets_open(NULL, &b) == 0);
    struct zx_packet_snapshot *sb = ((struct seq_file *)b.private_data)->private;
    assert(sb != sa && sb->generation == 2 && sb->count == 1 && sb->filter_id == 4660);
    strcpy(saved_b, render(&b));
    assert(strstr(saved_b, "generation=2 enabled=1 filter_id=4660 armed_id=4660 records=1 dropped=0 "));
    set_id("-1");
    assert(zx_packets_open(NULL, &c) == 0);
    struct zx_packet_snapshot *sc = ((struct seq_file *)c.private_data)->private;
    assert(sc != sa && sc != sb && sc->filter_id == -1 && sc->armed_id == 4660);
    assert(sc->count == sb->count && !memcmp(sc->records, sb->records, sizeof(sc->records)));
    strcpy(saved_c, render(&c));
    assert(strstr(saved_c, "generation=2 enabled=0 filter_id=-1 armed_id=4660 records=1 dropped=0 "));
    assert(!strcmp(render(&a), saved_a) && !strcmp(render(&b), saved_b));
    set_id("7");
    len = packet(frame, 5, 1, 0, 0, 7, 100);
    zx_packet_trace_add(frame, len, false, 0, 0, 0, 0, 0);
    assert(zx_packets_open(NULL, &d) == 0);
    assert(strstr(render(&d), "generation=3 enabled=1 filter_id=7 armed_id=7 records=1 dropped=0 "));
    /* Simulate seq replay/seek: repeated shows must use the same per-open copy. */
    for (unsigned i = 0; i < 5; i++) {
        assert(!strcmp(render(&a), saved_a));
        assert(!strcmp(render(&b), saved_b));
        assert(!strcmp(render(&c), saved_c));
        assert(!memcmp(sa, &saved_snapshot, sizeof(*sa)));
    }
    close_snapshot(&b);
    assert(!strcmp(render(&a), saved_a) && !strcmp(render(&c), saved_c));
    close_snapshot(&d);
    close_snapshot(&a);
    close_snapshot(&c);
    assert(allocation_count == 4 && free_calls == 4 && single_release_calls == 4);
}

int main(int argc, char **argv) {
    assert(argc == 2);
    const struct { const char *name; void (*run)(void); } tests[] = {
        {"default_off", test_default_off}, {"parameters", test_parameters},
        {"decoder_payloads", test_decoder_payloads}, {"decoder_rejections", test_decoder_rejections},
        {"guarded_bounds", test_guarded_bounds}, {"collector_budget", test_collector_budget},
        {"timestamp_generation", test_timestamp_and_generation},
        {"proc_failures", test_proc_failures}, {"proc_snapshots", test_proc_snapshots}
    };
    for (unsigned i = 0; i < sizeof(tests) / sizeof(tests[0]); i++) {
        if (!strcmp(argv[1], tests[i].name)) {
            tests[i].run();
            assert(!locked && lock_calls == unlock_calls);
            for (unsigned a = 0; a < allocation_count; a++)
                assert(!allocations[a].live);
            printf("PASS exact driver C: %s\n", tests[i].name);
            return 0;
        }
    }
    fprintf(stderr, "Unknown case: %s\n", argv[1]);
    return 2;
}
'''


@needs_artifacts()
class PacketTraceRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        text = SOURCE.read_text()
        if text.count(BEGIN) != 1 or text.count(END) != 1:
            raise AssertionError('Expected one complete R201 marker-delimited block')
        start, end = text.index(BEGIN) + len(BEGIN), text.index(END)
        if start >= end:
            raise AssertionError('R201 block markers out of order')
        block = text[start:end]  # Deliberately no rewriting of any driver code.
        definitions = []
        for name in ('BUF_SIZE', 'BUF_HDR'):
            match = re.search(r'^#define\s+' + name + r'\s+[^\n]+', text, re.M)
            if not match:
                raise AssertionError(f'Missing actual driver {name}')
            definitions.append(match.group())
        cls.temp = tempfile.TemporaryDirectory(prefix='packet-trace-r201-')
        cls.addClassCleanup(cls.temp.cleanup)
        c = Path(cls.temp.name) / 'packet_trace_test.c'
        cls.exe = Path(cls.temp.name) / 'packet_trace_test'
        c.write_text(STUBS + '\n' + '\n'.join(definitions) + '\n'
                     + '#line 1 "exact-driver-r201-block"\n' + block
                     + '\n#line 1 "r201-test-cases"\n' + CASES)
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
        for line in result.stdout.splitlines():
            if line.startswith('HOST_ABI '):
                print(line, flush=True)

    def test_default_off_cheap_gate(self):
        self.run_case('default_off')

    def test_all_valid_ids_invalid_ids_and_callback_api(self):
        self.run_case('parameters')

    def test_payload_hash_prefix_options_odd_empty_and_padding(self):
        self.run_case('decoder_payloads')

    def test_ethernet_ipv4_icmp_and_length_validation(self):
        self.run_case('decoder_rejections')

    def test_readonly_guarded_frames_no_oob_or_skb_mutation(self):
        self.run_case('guarded_bounds')

    def test_metadata_fixed_budget_overflow_disable_rearm(self):
        self.run_case('collector_budget')

    def test_timestamp_before_parse_wait_and_generation_change(self):
        self.run_case('timestamp_generation')

    def test_proc_allocation_lock_order_failure_and_release(self):
        self.run_case('proc_failures')

    def test_proc_exact_schema_immutable_independent_snapshots(self):
        self.run_case('proc_snapshots')


@needs_artifacts()
class PacketTraceSourcePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = SOURCE.read_text()

    def test_marked_block_no_mmio_console_or_ring_access(self):
        self.assertEqual(self.text.count(BEGIN), 1)
        self.assertEqual(self.text.count(END), 1)
        block = self.text.split(BEGIN, 1)[1].split(END, 1)[0]
        ids = set(t for t in tokens(block) if re.fullmatch(r'[A-Za-z_]\w*', t))
        forbidden = re.compile(
            r'(?:__raw_)?(?:read|write)[bwlq](?:_relaxed)?|'
            r'(?:devm_)?ioremap\w*|iounmap|ioread\w*|iowrite\w*|'
            r'memcpy_(?:to|from)io|memset_io|printk\w*|'
            r'(?:pr|netdev|dev)_(?:info|err|warn|notice|debug|alert|crit|emerg)\w*|'
            r'dma_\w*|TMQ_\w*|TMC_\w*|BM_\w*|zx_rx_release|zx_rx_retire|'
            r'zx_desc_\w*|zx_eth_singleton|__iomem')
        self.assertEqual(sorted(t for t in ids if forbidden.fullmatch(t)), [])
        self.assertIn('const u8 * frame', ' '.join(function_tokens(block, 'zx_packet_decode')))
        self.assertIn('const u8 * frame', ' '.join(function_tokens(block, 'zx_packet_trace_add')))
        self.assertRegex(block, r'module_param_cb\(packet_trace_id,\s*&zx_packet_trace_ops,\s*&zx_packet_trace_id,\s*0644\)')

    def test_tx_hook_exact_metadata_and_immediately_before_doorbell(self):
        body = function_tokens(self.text, 'zx_eth_xmit')
        i = hook_index(body, TX_HOOK)
        next_statement = tokens('writel(1, ze->tmq + TMQ_DOORBELL);')
        self.assertEqual(body[i + len(TX_HOOK):i + len(TX_HOOK) + len(next_statement)], next_statement)
        self.assertEqual(body.count('zx_packet_trace_add'), 1)
        self.assertLess(' '.join(body).index('wmb ( ) ;'), ' '.join(body).index('zx_packet_trace_add'))

    def test_rx_hook_exact_metadata_and_immediately_before_eth_type_trans(self):
        body = function_tokens(self.text, 'zx_eth_poll')
        i = hook_index(body, RX_HOOK)
        next_statement = tokens('skb->protocol = eth_type_trans(skb, rxdev);')
        self.assertEqual(body[i + len(RX_HOOK):i + len(RX_HOOK) + len(next_statement)], next_statement)
        self.assertEqual(body.count('zx_packet_trace_add'), 1)
        # Exactly two datapath calls plus the one definition; no extra hot-path hook.
        self.assertEqual(tokens(self.text).count('zx_packet_trace_add'), 3)

    def test_proc_readonly_registration_and_removal_are_debug_guarded(self):
        operations = (
            ('zx_eth_probe', 'proc_create("zx_eth_packets", 0444, NULL, &zx_packets_pops);'),
            ('zx_eth_remove', 'remove_proc_entry("zx_eth_packets", NULL);'),
        )
        for name, statement in operations:
            with self.subTest(function=name):
                body = function_tokens(self.text, name)
                guard = tokens('if (ZX_HAVE_DEBUG_IFACES) {')
                start = hook_index(body, guard) + len(guard)
                end, depth = start, 1
                while depth and end < len(body):
                    depth += (body[end] == '{') - (body[end] == '}')
                    end += 1
                self.assertEqual(depth, 0)
                hook_index(body[start:end - 1], tokens(statement))
                hook_index(body, tokens(statement))
        self.assertEqual(tokens(self.text).count('"zx_eth_packets"'), 2)

    def test_archived_r201_datapath_mmio_and_ring_policy(self):
        for name, hook in (('zx_eth_xmit', TX_HOOK), ('zx_eth_poll', RX_HOOK)):
            with self.subTest(function=name):
                self.assertEqual(datapath_digest(ARCHIVE.read_text(), name, hook), DATAPATH_REFERENCE[name],
                                 f'{name}: non-trace datapath tokens changed; review MMIO/ring policy, '
                                 'do not blindly update the reference')


if __name__ == '__main__':
    unittest.main(verbosity=2)
