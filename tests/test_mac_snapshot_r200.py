"""Compile the actual R200 MAC snapshot helper against non-writing MMIO stubs."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c'


class MacSnapshotTests(unittest.TestCase):
    def test_exact_persistent_port_reads_only(self):
        text = SOURCE.read_text()
        start = text.index('static void zx_mac_snapshot_log(')
        opening = text.index('{', start)
        depth = 1
        end = opening + 1
        while depth:
            depth += (text[end] == '{') - (text[end] == '}')
            end += 1
        function = text[start:end]
        self.assertNotIn('writel(', function)
        self.assertNotIn('ioremap(', function)
        stubs = r'''
#include <assert.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
#define __iomem
#define ZX_NPORTS 4
#define MAC_CTRL 0
#define READ_ONCE(x) (x)
struct zx_eth { void *macs[ZX_NPORTS]; };
struct net_device { int port; struct zx_eth *ze; };
static bool zx_mac_snapshot;
static unsigned n;
static uintptr_t seen[8];
static char message[512];
static struct zx_eth *zx_ze_of(struct net_device *dev) { return dev->ze; }
static int zx_port_index_of(struct net_device *dev) { return dev->port; }
static u32 readl(void *addr) { assert(n < 8); seen[n++] = (uintptr_t)addr; return (uintptr_t)addr; }
static void netdev_info(struct net_device *dev, const char *fmt, ...) {
    (void)dev; va_list ap; va_start(ap, fmt); vsnprintf(message, sizeof(message), fmt, ap); va_end(ap);
}
'''
        cases = r'''
int main(void) {
    struct zx_eth ze = { .macs = {(void *)0x92200000, (void *)0x92240000, (void *)0x92280000, (void *)0x922c0000} };
    struct net_device dev = { .port = 2, .ze = &ze };
    zx_mac_snapshot_log(&dev, "disabled"); assert(n == 0 && !message[0]);
    zx_mac_snapshot = true;
    for (int p = -1; p <= 4; p += 5) { dev.port = p; zx_mac_snapshot_log(&dev, "invalid"); assert(n == 0); }
    dev.port = 2; ze.macs[2] = NULL; zx_mac_snapshot_log(&dev, "missing"); assert(n == 0);
    ze.macs[2] = (void *)0x92280000;
    for (int p = 0; p < ZX_NPORTS; p++) {
        n = 0; dev.port = p;
        zx_mac_snapshot_log(&dev, "test");
        assert(n == 5);
        unsigned offsets[] = {0, 4, 0xb00, 0xd00, 0xd30};
        for (unsigned i = 0; i < 5; i++) assert(seen[i] == 0x92200000u + p * 0x40000u + offsets[i]);
        assert(strstr(message, "MACSNAP") && strstr(message, "test"));
    }
    puts("PASS: MAC snapshot disabled by default, guards ports/maps, reads exactly five ordered words from persistent port mapping");
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='mac-snapshot-r200-') as tmp:
            c = Path(tmp) / 'test.c'
            exe = Path(tmp) / 'test'
            c.write_text(stubs + function + cases)
            result = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror', str(c), '-o', str(exe)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            subprocess.run([str(exe)], check=True)


if __name__ == '__main__':
    unittest.main()
