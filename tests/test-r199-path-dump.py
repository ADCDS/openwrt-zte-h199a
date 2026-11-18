#!/usr/bin/env python3
"""Offline execution of the actual bounded dump C functions with mocked MMIO."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c'
text = source.read_text()
functions = text[text.index('static void zx_path_dump('):text.index('static const struct proc_ops zx_regs_pops')]
preamble = r'''
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
#define __iomem
#define SZ_4K 4096u
#define SZ_128K (128u * 1024)
#define READ_ONCE(x) (x)
struct inode { int unused; };
struct seq_file { void *private; };
struct file { int (*show)(struct seq_file *, void *); void *private; };
static bool zx_regs_path_only;
static int zx_regs_pp2_page = -1;
static u32 addresses[4096];
static unsigned nread, nmap, nunmap;
static u32 map_fail, value;
static int alloc_fail;
static size_t output_len, allocation;
static char output[SZ_128K];
static void seq_printf(struct seq_file *m, const char *fmt, ...) {
    (void)m;
    va_list ap; va_start(ap, fmt);
    int n = vsnprintf(output + output_len, sizeof(output) - output_len, fmt, ap);
    va_end(ap); assert(n >= 0 && (size_t)n < sizeof(output) - output_len);
    output_len += n;
}
static void seq_puts(struct seq_file *m, const char *s) { seq_printf(m, "%s", s); }
static void *ioremap(u32 base, unsigned size) {
    assert(size == SZ_4K && !(base & (SZ_4K - 1))); nmap++;
    return base == map_fail ? NULL : (void *)(uintptr_t)base;
}
static void iounmap(void *p) { assert(p); nunmap++; }
static u32 readl(void *p) {
    assert(nread < 4096); addresses[nread++] = (uintptr_t)p; return value;
}
static int zx_regs_show(struct seq_file *m, void *v) { (void)m; (void)v; return 777; }
static int single_open_size(struct file *f, int (*show)(struct seq_file *, void *), void *data, size_t size) {
    if (alloc_fail) return -ENOMEM;
    f->show = show; f->private = data; allocation = size; return 0;
}
static int single_open(struct file *f, int (*show)(struct seq_file *, void *), void *data) {
    return single_open_size(f, show, data, SZ_4K);
}
'''
tests = r'''
static void reset(void) {
    nread = nmap = nunmap = output_len = allocation = 0;
    output[0] = 0; value = map_fail = alloc_fail = 0;
    zx_regs_path_only = true; zx_regs_pp2_page = -1;
}
static void run(struct file *f) {
    struct seq_file m = { .private = f->private };
    assert(f->show(&m, NULL) == 0);
}
static void check_base(void) {
    for (unsigned k = 0; k < 512; k++) {
        assert(addresses[k] == 0x92310000 + 4*k);
        assert(addresses[512+k] == 0x92388000 + 4*k);
    }
    assert(addresses[1024] == 0x921d9068);
    assert(addresses[1025] == 0x92000008);
}
int main(void) {
    struct file f;
    reset(); assert(zx_regs_open(NULL, &f) == 0); assert(allocation == SZ_128K);
    /* Changes after open must not change that open's selected mode/page. */
    zx_regs_pp2_page = 63; zx_regs_path_only = false;
    run(&f); assert(nread == 1026 && nmap == 4 && nunmap == 4); check_base();
    assert(strstr(output, "PATHREG 92310304 00000000\n"));
    assert(strstr(output, "PATHREG 92310344 00000000\n"));
    assert(strstr(output, "PATHREG 92388304 00000000\n"));
    assert(strstr(output, "PATHREG 92388344 00000000\n"));
    assert(strstr(output, "PATHDUMP END\n"));
    for (int page = 0; page < 64; page++) {
        reset(); zx_regs_pp2_page = page;
        assert(zx_regs_open(NULL, &f) == 0); run(&f); check_base();
        assert(nmap == 5 && nunmap == 5);
        assert(nread == 2050u - (page == 36 ? 2u : 0u));
        unsigned i = 1026;
        for (u32 off = 0; off < SZ_4K; off += 4) {
            u32 phys = 0x92140000 + page*SZ_4K + off;
            if (phys == 0x92164058 || phys == 0x92164068) continue;
            assert(addresses[i++] == phys);
        }
        assert(i == nread && output_len < 65536);
        if (page == 36) {
            assert(strstr(output, "PATHREG 92164058 SKIP"));
            assert(strstr(output, "PATHREG 92164068 SKIP"));
        }
    }
    for (int page = -2; page <= 64; page += 66) {
        reset(); zx_regs_pp2_page = page;
        assert(zx_regs_open(NULL, &f) == -EINVAL); assert(nmap == 0 && nread == 0);
    }
    reset(); map_fail = 0x92310000;
    assert(zx_regs_open(NULL, &f) == 0); run(&f);
    assert(strstr(output, "PATH ERROR SW-SBRG map failed"));
    assert(!strstr(output, "PATHREG 92310000")); assert(nread == 514 && nunmap == 3);
    reset(); value = 0x3ff;
    assert(zx_regs_open(NULL, &f) == 0); run(&f);
    assert(strstr(output, "PATHATTACH enable=1f status=1f"));
    reset(); alloc_fail = 1;
    assert(zx_regs_open(NULL, &f) == -ENOMEM); assert(nmap == 0 && nread == 0);
    reset(); zx_regs_path_only = false;
    assert(zx_regs_open(NULL, &f) == 0); assert(f.show == zx_regs_show && allocation == SZ_4K);
    reset(); struct seq_file m = {0}; zx_path_dump(&m, "bad", 0, SZ_4K, 4);
    assert(nmap == 0 && strstr(output, "invalid window"));
    puts("PASS: actual C dump functions; all 64 pages, bounds, skips, zero/error output, open-time selection, <64 KiB output");
    return 0;
}
'''
with tempfile.TemporaryDirectory(prefix='r199-dump-test-') as tmp:
    c = Path(tmp) / 'test.c'
    exe = Path(tmp) / 'test'
    c.write_text(preamble + functions + tests)
    subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', str(c), '-o', str(exe)], check=True)
    subprocess.run([str(exe)], check=True)
