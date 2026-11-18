"""Ethernet: the datapath's DDR window from memory-region.

No functional change on the H199A, and no change to the kernel memory map,
shown five ways:

1. Every board DTB (base, -production, -production-qualify) carries the
   reserved-memory node the DTS has had since bring-up, unchanged:
   /reserved-memory/eth-datapath@41000000, 0x41000000 + 16 MiB, no-map, now the
   ethernet node's memory-region. It is the only carve-out of the 128 MiB
   memory node: no other reserved-memory child, no /memreserve/ entry, and the
   forced CONFIG_CMDLINE has no mem=. The kernel accepts the node's format.
2. The driver's actual zx_eth_resolve_ddr(), compiled on the host with the
   pinned kernel's own of_reserved_mem_lookup() over a reserved_mem[] table
   filled the way fdt_scan_reserved_mem() fills it from each DTB, resolves
   0x41000000 silently. Without memory-region it uses 0x41000000 and says so
   once. It refuses a region that is too small, not no-map, not reserved,
   misaligned or above 4 GiB, and it follows a moved region.
3. The actual zx_eth_datapath_init(), run against an MMIO recorder with the
   resolved base, maps the free lists and programs the TM's DDR pointers
   exactly as OLD (frozen from commit cb239a9). Its whole register trace is
   identical to the fallback run, and a moved window moves only the DDR
   addresses.
4. The actual zx_eth_probe() (test_eth_probe.py's model), with the resolved
   base, maps the pools, free lists and rings exactly as OLD.
5. The actual zx_datapath_warm() accepts exactly the ring bases the frozen
   cb239a9 version accepted.

The cross-compile of the driver against the pinned 6.6.151 tree (tree and
shipping configs) is test_eth_dt_resources.EthCrossCompileTests.
"""
from pathlib import Path
import re
import struct
import subprocess
import tempfile
import unittest

import dt_fixture as fx
import test_eth_probe as probe_model
from test_tx_origin_r204 import exact_define, exact_enum, exact_struct, function, tokens

NODE = '/soc/ethernet@92200000'
RESERVED = '/reserved-memory'
REGION = 'eth-datapath@41000000'
OLD_REGION = (0x41000000, 0x01000000)        # reg of the node, unchanged
OLD_MEMORY = (0x40000000, 0x08000000)        # /memory@40000000

# zx279128-eth.c at cb239a9 (before this change): every DDR address it used.
# probe(): (address, bytes) of each devm_ioremap_wc(), in order.
OLD_PROBE_MAPS = [(0x41000000, 0x400000), (0x41800000, 0x8400),
                  (0x41a00000, 0x40000), (0x41c00000, 0x4000), (0x41400000, 0x100000)]
# datapath_init(): the two temporary free-list mappings, and the TM pointers.
OLD_INIT_MAPS = [(0x41800000, 0x2000), (0x41808000, 0x1000)]
TMC, TMQ = 0x92340000, 0x92350000
OLD_INIT_POINTERS = [(TMC + 0xe8, 0x41800000), (TMC + 0xec, 0x41808000),
                     (TMC + 0xf0, 0x41a00000), (TMC + 0xf4, 0x41000000),
                     (TMC + 0xf8, 0x41400000), (TMQ + 0x50, 0x41b00000),
                     (TMQ + 0x60, 0x41c00000)]
OLD_FREELISTS = [(0x41800000, 2048), (0x41808000, 512)]    # (base, be16 entries)
OLD_DATAPATH_WARM = r'''
static bool old_datapath_warm(struct zx_eth *ze)
{
	u32 rx = readl(ze->tmc + TMC_RING_BASE);
	u32 tx = readl(ze->tmq + TMQ_TXRING);
	int port;

	if (rx < 0x41000000 || rx >= 0x42000000 ||
	    tx < 0x41000000 || tx >= 0x42000000)
		return false;

	for (port = 0; port < ZX_NPORTS; port++)
		if (ze->macs[port] &&
		    (readl(ze->macs[port] + MAC_CTRL) & 0xffff0000))
			return true;
	return false;
}
'''
DDR_DEFINES = ('ZX_DDR_BASE', 'ZX_DDR_SIZE', 'ZX_DDR_ALIGN', 'ZX_DDR_POOL', 'ZX_DDR_POOL2',
               'ZX_DDR_FREELIST', 'ZX_DDR_FREELIST2', 'ZX_DDR_RX_RING', 'ZX_DDR_TMQ',
               'ZX_DDR_TX_RING')


def define_block(text, name):
    """exact_define(), also following backslash continuations."""
    block = exact_define(text, name)
    start = text.index(block)
    end = start + len(block)
    while block.rstrip('\n').endswith('\\'):
        end = text.index('\n', end) + 1
        block = text[start:end]
    return block


def driver_value(text, name):
    value = exact_define(text, name).split(None, 2)[2].split('/*')[0].strip()
    return {'SZ_16M': 0x01000000, 'SZ_1M': 0x100000}.get(value) or int(value, 0)


def kernel_source(path):
    return (fx.kernel_tree() / path).read_text()


def properties(dtb, node):
    run = subprocess.run(['fdtget', '-p', str(dtb), node], capture_output=True, text=True)
    return run.stdout.split() if not run.returncode else None


def subnodes(dtb, node):
    run = subprocess.run(['fdtget', '-l', str(dtb), node], capture_output=True, text=True)
    return run.stdout.split() if not run.returncode else None


def memreserve_entries(dtb):
    data = Path(dtb).read_bytes()
    offset = struct.unpack('>I', data[16:20])[0]
    entries = []
    while True:
        base, size = struct.unpack('>QQ', data[offset:offset + 16])
        if not size:
            return entries
        entries.append((base, size))
        offset += 16


def reserved_regions(dtb):
    """The /reserved-memory children as the kernel's scan sees them."""
    regions = []
    for name in subnodes(dtb, RESERVED):
        path = f'{RESERVED}/{name}'
        props = properties(dtb, path)
        status = fx.fdtget(dtb, path, 'status', 's')
        regions.append({
            'name': name,
            'available': status in (None, ['okay'], ['ok']),
            'reg': fx.reg_pairs(dtb, path) if 'reg' in props else None,
            'size': 'size' in props,
            'nomap': 'no-map' in props,
            'phandle': (fx.fdtget(dtb, path, 'phandle', 'u') or [0])[0],
        })
    return regions


# ---- 2. zx_eth_resolve_ddr() over the kernel's reserved_mem table ----------

RESOLVE_MODEL = r'''
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
typedef uint64_t u64;
typedef uint32_t phys_addr_t;	/* CONFIG_ARM_LPAE is not set */
struct device_node { const char *full_name; bool nomap; };
struct device { struct device_node *of_node; };
struct zx_eth { struct device *dev; u32 ddr_phys; };
struct reserved_mem_ops;
@KERNEL@
static struct reserved_mem reserved_mem[MAX_RESERVED_REGIONS];
static int reserved_mem_count;
@LOOKUP@
@DRIVER@

static char message[160];
static unsigned infos, errors, node_gets, node_puts;
static void dev_info(struct device *d, const char *fmt, ...)
{
	va_list ap;

	(void)d; infos++;
	va_start(ap, fmt); vsnprintf(message, sizeof(message), fmt, ap); va_end(ap);
}
static int dev_err_probe(struct device *d, int err, const char *fmt, ...)
{ (void)d; (void)fmt; errors++; return err; }

/* One /reserved-memory child, and a board: its children and the child the
 * ethernet node's memory-region points at (-1: no memory-region, -2: a node
 * outside /reserved-memory). */
struct dtregion { const char *name; bool available, has_reg, has_size, nomap; u32 base, size; };
struct dtboard { struct dtregion r[8]; unsigned n; int target; };
@DT@
static struct device_node nodes[8], outside = { "sram@40000000", true };
static struct device_node eth_node;
static struct device dev = { &eth_node };
static int target;

/* fdt_scan_reserved_mem() + __reserved_mem_reserve_reg(): every available
 * child with reg is saved with its FIRST reg entry, a child with only `size`
 * (dynamic) with base 0 and size 0, until fdt_init_reserved_mem() allocates it.
 */
static void scan(const struct dtboard *b)
{
	memset(reserved_mem, 0, sizeof(reserved_mem));
	reserved_mem_count = 0;
	for (unsigned i = 0; i < b->n; i++) {
		const struct dtregion *r = &b->r[i];

		nodes[i] = (struct device_node){ r->name, r->nomap };
		if (!r->available || (!r->has_reg && !r->has_size))
			continue;
		assert(reserved_mem_count < MAX_RESERVED_REGIONS);
		reserved_mem[reserved_mem_count++] = (struct reserved_mem){
			.name = r->name, .base = r->has_reg ? r->base : 0,
			.size = r->has_reg ? r->size : 0 };
	}
	target = b->target;
}
static struct device_node *of_parse_phandle(const struct device_node *np, const char *name,
					    int index)
{
	assert(np == &eth_node && !strcmp(name, "memory-region") && index == 0);
	if (target == -1)
		return NULL;
	node_gets++;
	return target == -2 ? &outside : &nodes[target];
}
static void of_node_put(struct device_node *np) { assert(np); node_puts++; }
static bool of_property_read_bool(const struct device_node *np, const char *name)
{
	assert(!strcmp(name, "no-map"));
	return np->nomap;
}
'''

RESOLVE_CASES = r'''
static void run(const struct dtboard *b)
{
	struct zx_eth ze = { .dev = &dev, .ddr_phys = 0xdeadbeef };
	int rc;

	infos = errors = node_gets = node_puts = 0; message[0] = 0;
	scan(b);
	rc = zx_eth_resolve_ddr(&ze);
	assert(node_gets == node_puts);
	assert(rc ? (errors == 1 && !infos) : !errors);
	printf("rc %d ddr %#x infos %u errors %u gets %u msg %s\n", rc,
	       rc ? 0 : ze.ddr_phys, infos, errors, node_gets, infos ? message : "-\n");
}
int main(int argc, char **argv)
{
	struct dtboard b;
	struct dtregion *r;

	assert(argc == 3);
	b = boards[atoi(argv[1])];
	assert(b.target >= 0);
	r = &b.r[b.target];
	if (!strcmp(argv[2], "dt")) ;
	else if (!strcmp(argv[2], "absent")) b.target = -1;
	else if (!strcmp(argv[2], "outside")) b.target = -2;
	else if (!strcmp(argv[2], "disabled")) r->available = false;
	else if (!strcmp(argv[2], "dynamic")) { r->has_reg = false; r->has_size = true; }
	else if (!strcmp(argv[2], "mapped")) r->nomap = false;
	else if (!strcmp(argv[2], "small")) r->size = ZX_DDR_SIZE - 0x1000;
	else if (!strcmp(argv[2], "misaligned")) r->base += 0x80000;
	else if (!strcmp(argv[2], "high")) r->base = 0xff800000;
	else if (!strcmp(argv[2], "larger")) r->size = 2 * ZX_DDR_SIZE;
	else if (!strcmp(argv[2], "moved")) r->base = 0x45000000;
	else return 2;
	run(&b);
	return 0;
}
'''


def resolve_dt_c(dtbs):
    rows = []
    for dtb in dtbs:
        regions = reserved_regions(dtb)
        handle = fx.fdtget(dtb, NODE, 'memory-region', 'u')
        target = -1 if handle is None else next(
            i for i, r in enumerate(regions) if r['phandle'] == handle[0])
        cells = ', '.join(
            '{ "%s", %d, %d, %d, %d, %#x, %#x }' % (
                r['name'], r['available'], r['reg'] is not None, r['size'], r['nomap'],
                r['reg'][0][0] if r['reg'] else 0, r['reg'][0][1] if r['reg'] else 0)
            for r in regions)
        rows.append(f'\t{{ {{ {cells} }}, {len(regions)}, {target} }}')
    return 'static const struct dtboard boards[] = {\n' + ',\n'.join(rows) + '\n};'


# ---- 3. zx_eth_datapath_init() against an MMIO recorder -------------------

INIT_MODEL = r'''
#include <assert.h>
#include <errno.h>
#include <netinet/in.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t u8;
typedef uint16_t u16;
#define __iomem
#define SZ_8K 8192
#define BIT(n) (1U << (n))
#define GENMASK(h, l) (((~0U) << (l)) & (~0U >> (31 - (h))))
#define FIELD_PREP(m, v) (((u32)(v) << __builtin_ctz(m)) & (m))
#define cpu_to_be16(v) __builtin_bswap16((u16)(v))
#define wmb() ((void)0)
#define cpu_relax() ((void)0)
@PRELUDE@
typedef uint32_t u32;
@DEFINES@
struct zx_eth {
	bool alloc_pending, pp_bring_up;
	unsigned int free_credit;
	phys_addr_t phys[ZX_NREGS];
	void __iomem *bm, *tmc, *tmq;
	u32 ddr_phys;
};

/* Mappings get real host buffers; every access is translated back to the
 * physical address and logged. Register contents live in one store keyed by
 * physical address, so aliased mappings agree. TMD+0x18 (queue-table ready)
 * always reads ready. */
struct map { u32 phys; size_t size; unsigned char *host; bool alive; };
static struct map maps[64];
static unsigned nmaps;
struct event { char op; u32 phys, value, size; };
static struct event trace[1 << 17];
static unsigned ntrace;
#define STORE (1U << 16)
static u32 keys[STORE], vals[STORE];
static bool used[STORE];
static void record(char op, u32 phys, u32 value, u32 size)
{
	assert(ntrace < sizeof(trace) / sizeof(trace[0]));
	trace[ntrace++] = (struct event){ op, phys, value, size };
}
static u32 *word(u32 phys)
{
	u32 h = ((phys >> 2) * 2654435761U) & (STORE - 1);

	phys &= ~3U;
	while (used[h] && keys[h] != phys)
		h = (h + 1) & (STORE - 1);
	if (!used[h]) { used[h] = true; keys[h] = phys; vals[h] = 0; }
	return &vals[h];
}
static void *map(u32 phys, size_t size, char op)
{
	assert(nmaps < 64);
	maps[nmaps] = (struct map){ phys, size, calloc(1, size), true };
	assert(maps[nmaps].host);
	record(op, phys, 0, size);
	return maps[nmaps++].host;
}
static void *ioremap(u32 phys, size_t size) { return map(phys, size, 'M'); }
static void *ioremap_wc(u32 phys, size_t size) { return map(phys, size, 'C'); }
static void iounmap(void *p)
{
	for (unsigned i = 0; i < nmaps; i++)
		if (maps[i].host == p && maps[i].alive) {
			maps[i].alive = false;
			record('U', maps[i].phys, 0, maps[i].size);
			return;
		}
	assert(!"unmapping an unknown pointer");
}
static u32 phys_of(const void *p, unsigned width)
{
	for (unsigned i = 0; i < nmaps; i++) {
		const unsigned char *h = maps[i].host;

		if (maps[i].alive && (const unsigned char *)p >= h &&
		    (const unsigned char *)p + width <= h + maps[i].size)
			return maps[i].phys + (u32)((const unsigned char *)p - h);
	}
	assert(!"access outside every live mapping");
	return 0;
}
static u32 readl(const void *p)
{
	u32 phys = phys_of(p, 4), v = *word(phys);

	if (phys == TMD_BASE + 0x18)
		v |= 1;
	record('R', phys, v, 4);
	return v;
}
static void writel(u32 v, void *p) { u32 phys = phys_of(p, 4); *word(phys) = v; record('W', phys, v, 4); }
static u16 readw(const void *p)
{
	u32 phys = phys_of(p, 2);
	u16 v = (u16)(*word(phys) >> ((phys & 2) * 8));

	record('r', phys, v, 2);
	return v;
}
static void writew(u16 v, void *p)
{
	u32 phys = phys_of(p, 2), shift = (phys & 2) * 8, *w = word(phys);

	*w = (*w & ~(0xffffU << shift)) | ((u32)v << shift);
	record('w', phys, v, 2);
}
static void udelay(unsigned n) { record('D', 0, n, 0); }
static void mdelay(unsigned n) { record('D', 1, n, 0); }
static void msleep(unsigned n) { record('D', 2, n, 0); }
static void pr_info(const char *fmt, ...) { (void)fmt; }
/* Boundaries this change does not touch (their own tests cover them). */
static int zx_eth_quiesce_init(struct zx_eth *ze) { (void)ze; record('Q', 0, 0, 0); return 0; }
static int zx_tm_queue_state_init(struct zx_eth *ze) { (void)ze; record('T', 0, 0, 0); return 0; }
static int zx_pp_seed_vlans(void __iomem *brg, unsigned int count)
{ (void)brg; record('V', 0, count, 0); return 0; }
'''

INIT_CASES = r'''
int main(int argc, char **argv)
{
	struct zx_eth ze = { .alloc_pending = true, .free_credit = 9 };
	unsigned premapped;
	int rc;

	assert(argc == 2);
	zx_test_fallback_phys(ze.phys);	/* the DT's blocks: test_eth_dt_resources.py */
	ze.ddr_phys = strcmp(argv[1], "fallback") ? (u32)strtoul(argv[1], NULL, 0) : ZX_DDR_BASE;
	ze.bm = map(ze.phys[ZX_REG_BM], SZ_4K, 'P');
	ze.tmc = map(ze.phys[ZX_REG_TMC], SZ_4K, 'P');
	ze.tmq = map(ze.phys[ZX_REG_TMQ], SZ_4K, 'P');
	premapped = nmaps;
	ntrace = 0;
	rc = zx_eth_datapath_init(&ze);
	for (unsigned i = premapped; i < nmaps; i++)
		assert(!maps[i].alive);		/* every temporary mapping released */
	printf("rc %d\n", rc);
	for (unsigned i = 0; i < ntrace; i++)
		printf("%c %#x %#x %#x\n", trace[i].op, trace[i].phys, trace[i].value, trace[i].size);
	return 0;
}
'''

INIT_DEFINES = ('BM_BASE', 'TMC_BASE', 'TMD_BASE', 'TMQ_BASE', 'BM_ENABLE', 'TMC_CFG',
                'TMQ_TXRING', 'BUF_COUNT', 'BUF2_COUNT', 'ZX_NPP_SPA', 'ZX_NPP_ATTACH',
                'SPA_TRAP_PROTOCOLS', 'SPA_TRAP_PROTOCOL0', 'SPA_TRAP_PROTOCOL1',
                'SPA_CPU_PROTOCOLS', 'ZXI_RESET', 'ZXI_GLOBAL', 'ZXI_NPP', 'ZXI_QCFG',
                'ZXI_FREELIST', 'ZXI_BMREGS', 'ZXI_BMFILL', 'ZXI_RINGS', 'ZXI_QTABLE',
                'ZXI_MACREGS') + DDR_DEFINES


# ---- 5. zx_datapath_warm() against the cb239a9 version -------------------

WARM_MODEL = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef uint32_t u32;
#define __iomem
#define SZ_16M 0x01000000
#define SZ_1M 0x00100000
@DEFINES@
struct zx_eth { void __iomem *tmc, *tmq, *macs[ZX_NPORTS]; u32 ddr_phys; };
static u32 tmc[64], tmq[64], mac[ZX_NPORTS];
static u32 readl(const void *p) { return *(const u32 *)p; }
'''

WARM_CASES = r'''
int main(int argc, char **argv)
{
	static const u32 bases[] = { 0, 0x40ffffff, 0x41000000, 0x41000001, 0x41a00000,
		0x41c00000, 0x41ffffff, 0x42000000, 0x42000001, 0x7fffffff, 0x80000000,
		0xc1000000, 0xffffffff };
	static const u32 ctrl[] = { 0, 0x0000ffff, 0x00010000, 0x00bb6003, 0xffff0000 };
	struct zx_eth ze = { tmc, tmq, { &mac[0], &mac[1], &mac[2], &mac[3] }, 0 };
	unsigned n = sizeof(bases) / sizeof(bases[0]), cases = 0, warm = 0;

	assert(argc == 2);
	ze.ddr_phys = (u32)strtoul(argv[1], NULL, 0);
	for (unsigned a = 0; a < n; a++)
		for (unsigned b = 0; b < n; b++)
			for (unsigned c = 0; c < sizeof(ctrl) / sizeof(ctrl[0]); c++)
				for (int port = -1; port < ZX_NPORTS; port++)
					for (int gone = 0; gone < 2; gone++) {
						tmc[TMC_RING_BASE / 4] = bases[a];
						tmq[TMQ_TXRING / 4] = bases[b];
						for (int i = 0; i < ZX_NPORTS; i++) {
							mac[i] = i == port ? ctrl[c] : 0;
							ze.macs[i] = gone && i == port ? NULL : &mac[i];
						}
						bool got = zx_datapath_warm(&ze);
						assert(got == old_datapath_warm(&ze));
						warm += got; cases++;
					}
	printf("%u cases %u warm\n", cases, warm);
	return 0;
}
'''


def cc(source, exe, extra=()):
    built = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                            '-Wno-unused-function', '-Wno-sign-compare', *extra,
                            str(source), '-o', str(exe)], capture_output=True, text=True,
                           timeout=60)
    if built.returncode:
        raise AssertionError(built.stderr)


@unittest.skipUnless(fx.dts_tools_available(), 'requires the unpacked kernel tree, dtc and fdtget')
class EthMemoryRegionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='eth-ddr-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.out = Path(cls.tmp.name)
        cls.dtb, cls.warnings = {}, {}
        for name in fx.DTS_NAMES:
            cls.dtb[name], cls.warnings[name] = fx.compile_dts(name, cls.out)
        cls.text = fx.ETH_SOURCE.read_text()
        driver = '\n'.join(exact_define(cls.text, n) for n in DDR_DEFINES)

        # 2. resolution, with the kernel's own lookup and helpers
        reserved_c = kernel_source('drivers/of/of_reserved_mem.c')
        kernel = '\n'.join([
            exact_define(kernel_source('include/linux/sizes.h'), 'SZ_1M'),
            exact_define(kernel_source('include/linux/sizes.h'), 'SZ_16M'),
            exact_define(kernel_source('include/linux/align.h'), 'IS_ALIGNED(x, a)'),
            exact_define(kernel_source('include/linux/wordpart.h'), 'upper_32_bits(n)'),
            exact_define(reserved_c, 'MAX_RESERVED_REGIONS'),
            exact_struct(kernel_source('include/linux/of_reserved_mem.h'), 'reserved_mem'),
            function(kernel_source('include/linux/string.h'), 'kbasename'),
        ])
        code = (RESOLVE_MODEL.replace('@KERNEL@', kernel)
                .replace('@LOOKUP@', function(reserved_c, 'of_reserved_mem_lookup'))
                .replace('@DRIVER@', driver)
                .replace('@DT@', resolve_dt_c([cls.dtb[n] for n in fx.DTS_NAMES])) +
                function(cls.text, 'zx_eth_resolve_ddr') + RESOLVE_CASES)
        cls.resolve_exe = cls.out / 'resolve'
        (cls.out / 'resolve.c').write_text(code)
        cc(cls.out / 'resolve.c', cls.resolve_exe)
        cls.resolved = {}
        for i, name in enumerate(fx.DTS_NAMES):
            fields = cls.resolve(i, 'dt').split()
            cls.resolved[name] = int(fields[3], 16) if fields[1] == '0' else None

        # 3. datapath init
        globals_ = '\n'.join(re.search(pattern, cls.text, re.M).group() for pattern in (
            r'^static unsigned int zx_init_mask = [^;]*;', r'^#define ZXI_MASK\s.*$',
            r'^static bool zx_skip_reset;', r'^static unsigned int zx_npp_port_mask = [^;]*;'))
        code = (INIT_MODEL.replace('@PRELUDE@', fx.eth_reg_prelude(cls.text))
                .replace('@DEFINES@', ''.join(define_block(cls.text, n) for n in INIT_DEFINES
                                              if n not in fx.ETH_TABLE_DEFINES) + globals_) +
                function(cls.text, 'zx_eth_datapath_init') + INIT_CASES)
        cls.init_exe = cls.out / 'init'
        (cls.out / 'init.c').write_text(code)
        cc(cls.out / 'init.c', cls.init_exe)

        # 5. warm detection
        defines = '\n'.join(exact_define(cls.text, n) for n in (
            'TMC_RING_BASE', 'TMQ_TXRING', 'ZX_NPORTS', 'MAC_CTRL', 'ZX_DDR_SIZE'))
        code = (WARM_MODEL.replace('@DEFINES@', defines) + OLD_DATAPATH_WARM +
                function(cls.text, 'zx_datapath_warm') + WARM_CASES)
        cls.warm_exe = cls.out / 'warm'
        (cls.out / 'warm.c').write_text(code)
        cc(cls.out / 'warm.c', cls.warm_exe)

    @classmethod
    def resolve(cls, board, case):
        run = subprocess.run([str(cls.resolve_exe), str(board), case],
                             capture_output=True, text=True, timeout=30)
        if run.returncode:
            raise AssertionError(run.stdout + run.stderr)
        return run.stdout.strip()

    def init_trace(self, base):
        run = subprocess.run([str(self.init_exe), base], capture_output=True, text=True,
                             timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout[-2000:] + run.stderr)
        lines = run.stdout.splitlines()
        self.assertEqual(lines[0], 'rc 0')
        return [(op, int(p, 16), int(v, 16), int(s, 16))
                for op, p, v, s in (line.split() for line in lines[1:])]

    # -- 1 ------------------------------------------------------------------
    def test_every_board_dtb_keeps_the_kernel_memory_map(self):
        for name, dtb in self.dtb.items():
            with self.subTest(dtb=name):
                self.assertNotRegex(self.warnings[name], r'reserved-memory|ethernet@|memory@')
                self.assertEqual([n for n in subnodes(dtb, '/') if n.startswith('memory')],
                                 ['memory@40000000'])
                self.assertEqual(fx.reg_pairs(dtb, '/memory@40000000'), [OLD_MEMORY])
                self.assertEqual(memreserve_entries(dtb), [])
                # The one reserved region, as the kernel parses it: the root
                # check of __reserved_mem_check_root() passes, reg is valid.
                self.assertEqual(fx.fdtget(dtb, RESERVED, '#address-cells', 'u'),
                                 fx.fdtget(dtb, '/', '#address-cells', 'u'))
                self.assertEqual(fx.fdtget(dtb, RESERVED, '#size-cells', 'u'),
                                 fx.fdtget(dtb, '/', '#size-cells', 'u'))
                self.assertIn('ranges', properties(dtb, RESERVED))
                regions = reserved_regions(dtb)
                self.assertEqual([r['name'] for r in regions], [REGION])
                region = regions[0]
                self.assertEqual(region['reg'], [OLD_REGION])
                self.assertTrue(region['available'] and region['nomap'])
                self.assertEqual(sorted(properties(dtb, f'{RESERVED}/{REGION}')),
                                 ['no-map', 'phandle', 'reg'])   # no compatible, no reusable
                self.assertEqual(fx.fdtget(dtb, NODE, 'memory-region', 'u'), [region['phandle']])
                base, size = OLD_REGION
                self.assertTrue(OLD_MEMORY[0] <= base and base + size <= sum(OLD_MEMORY))
                bootargs = ' '.join(fx.fdtget(dtb, '/chosen', 'bootargs', 's') or [])
                self.assertNotIn('mem=', bootargs)

    def test_the_command_line_cannot_carve_memory(self):
        configs = [fx.ROOT / 'files/target/linux/armsr/config-6.6']
        # The merged .config only exists once the kernel has been configured,
        # which is after a build, not after `target/linux/prepare`. A prepared
        # tree has the source but no .config, so check for the file rather than
        # for the tree.
        merged = (fx.kernel_tree() / '.config') if fx.kernel_tree() else None
        if merged and merged.is_file():
            configs.append(merged)
        for config in configs:
            with self.subTest(config=str(config)):
                text = config.read_text()
                self.assertIn('\nCONFIG_CMDLINE_FORCE=y\n', text)
                cmdline = re.search(r'^CONFIG_CMDLINE="([^"]*)"$', text, re.M).group(1)
                self.assertNotRegex(cmdline, r'\bmem(map)?=')
                self.assertIn('# CONFIG_ARM_LPAE is not set', text)
        platform = (fx.FILES / 'arch/arm/mach-zx279128').glob('*.[cS]')
        for source in platform:
            self.assertNotRegex(source.read_text(), r'memblock|\.reserve\b', source.name)

    # -- 2 ------------------------------------------------------------------
    def test_actual_resolution_of_every_board_dt_is_the_old_window(self):
        for i, name in enumerate(fx.DTS_NAMES):
            with self.subTest(dtb=name):
                self.assertEqual(self.resolve(i, 'dt'),
                                 'rc 0 ddr 0x41000000 infos 0 errors 0 gets 1 msg -')
                self.assertEqual(self.resolved[name], OLD_REGION[0])

    def test_actual_fallback_without_memory_region_is_the_old_window(self):
        self.assertEqual(driver_value(self.text, 'ZX_DDR_BASE'), OLD_REGION[0])
        self.assertEqual(driver_value(self.text, 'ZX_DDR_SIZE'), OLD_REGION[1])
        self.assertEqual(self.resolve(0, 'absent'),
                         'rc 0 ddr 0x41000000 infos 1 errors 0 gets 0 msg '
                         'no memory-region; using built-in DDR window 0x41000000+0x1000000')

    def test_actual_resolution_refuses_unusable_regions(self):
        for case in ('outside', 'disabled', 'dynamic', 'mapped', 'small', 'misaligned', 'high'):
            with self.subTest(case=case):
                out = self.resolve(0, case)
                self.assertTrue(out.startswith(f'rc {-22} ddr 0 infos 0 errors 1 gets 1 '), out)

    def test_actual_resolution_follows_the_dt_not_the_constants(self):
        self.assertEqual(self.resolve(0, 'moved'),
                         'rc 0 ddr 0x45000000 infos 0 errors 0 gets 1 msg -')
        self.assertEqual(self.resolve(0, 'larger'),
                         'rc 0 ddr 0x41000000 infos 0 errors 0 gets 1 msg -')

    def test_lookup_and_helpers_are_the_pinned_kernels(self):
        # Extracted verbatim above; guard against a silently different tree.
        lookup = function(kernel_source('drivers/of/of_reserved_mem.c'), 'of_reserved_mem_lookup')
        self.assertIn('kbasename(np->full_name)', lookup)
        # The model's of_parse_phandle()/of_node_put() pairing and
        # of_property_read_bool() semantics.
        header = kernel_source('include/linux/of.h')
        self.assertEqual(tokens(function(header, 'of_property_read_bool')), tokens(
            'static inline bool of_property_read_bool(const struct device_node *np, '
            'const char *propname) { struct property *prop = '
            'of_find_property(np, propname, NULL); return prop ? true : false; }'))
        self.assertRegex(header, r'refcount incremented\.\s+Use\s+\*\s+of_node_put\(\) on it '
                                 r'when done\.\s+\*/\s+static inline struct device_node '
                                 r'\*of_parse_phandle\(')

    # -- 3 ------------------------------------------------------------------
    def test_actual_datapath_init_programs_the_old_ddr_addresses(self):
        traces = {name: self.init_trace(hex(base)) for name, base in self.resolved.items()}
        fallback = self.init_trace('fallback')
        for name, trace in traces.items():
            with self.subTest(dtb=name):
                self.assertEqual(trace, fallback)      # DT and fallback: identical traffic
        trace = fallback
        self.assertEqual([(p, s) for op, p, v, s in trace if op == 'C'], OLD_INIT_MAPS)
        pointers = {p for p, _ in OLD_INIT_POINTERS}
        self.assertEqual([(p, v) for op, p, v, s in trace if op == 'W' and p in pointers],
                         OLD_INIT_POINTERS)
        # No other write carries a DDR window address.
        base, size = OLD_REGION
        self.assertEqual([(p, v) for op, p, v, s in trace
                          if op == 'W' and base <= v < base + size], OLD_INIT_POINTERS)
        # The free-list seeding writes exactly the old tables.
        for first, count in OLD_FREELISTS:
            seeded = [(p, v) for op, p, v, s in trace
                      if op == 'w' and first <= p < first + 2 * count]
            self.assertEqual(seeded, [(first + 2 * i, ((i & 0xff) << 8) | (i >> 8))
                                      for i in range(count)])
        ddr = [e for e in trace if e[0] in 'rwRW' and base <= e[1] < base + size]
        self.assertEqual(len(ddr), sum(c for _, c in OLD_FREELISTS) + 5)  # + 5 readbacks

    def test_actual_datapath_init_moves_only_ddr_addresses_with_the_window(self):
        delta = 0x04000000
        old, moved = self.init_trace('fallback'), self.init_trace(hex(OLD_REGION[0] + delta))
        self.assertEqual(len(old), len(moved))
        base, size = OLD_REGION
        pointers = {p for p, _ in OLD_INIT_POINTERS}
        shifted = 0
        for a, b in zip(old, moved):
            op, phys, value, width = a
            if op in 'CrwRWU' and base <= phys < base + size:
                a = (op, phys + delta, value, width)
            if op == 'W' and phys in pointers:
                a = (op, phys, value + delta, width)
            shifted += a != (op, phys, value, width)
            self.assertEqual(a, b)
        self.assertGreater(shifted, len(OLD_INIT_POINTERS) + 2560)

    # -- 4 ------------------------------------------------------------------
    def test_actual_probe_maps_the_old_ddr_ranges(self):
        source = self.text
        model = probe_model
        boundaries = model.BOUNDARIES
        wc = ('static void *devm_ioremap_wc(struct device *d,unsigned long pa,size_t n) '
              '{ return devm_ioremap(d,pa,n); }\n')
        stub = '    z->ddr_phys=ZX_DDR_BASE;return 0;\n'
        self.assertEqual(boundaries.count(wc), 1)
        self.assertEqual(boundaries.count(stub), 1)
        boundaries = boundaries.replace(wc, (
            'static unsigned long wc_log[8][2]; static unsigned nwc;\n'
            'static void *devm_ioremap_wc(struct device *d,unsigned long pa,size_t n) {\n'
            '    if(nwc<8) { wc_log[nwc][0]=pa;wc_log[nwc][1]=n; } nwc++;\n'
            '    return devm_ioremap(d,pa,n);\n}\n'))
        boundaries = boundaries.replace(stub, '    z->ddr_phys=RESOLVED_DDR;return 0;\n')
        cases = model.CASES[:model.CASES.index('int main(void) {')] + r'''
static void show(const char *label) {
    printf("%s", label);
    for(unsigned i=0;i<nwc && i<8;i++) printf(" %#lx+%#lx",wc_log[i][0],wc_log[i][1]);
    printf("\n");
}
int main(void) {
    nwc=0; exercise(0); show("cold");
    inherited_warm=true; nwc=0; exercise(0); show("inherited");
    return 0;
}
'''
        structs = '\n'.join([exact_struct(source, 'zx_rx_queue'), exact_struct(source, 'zx_eth'),
                             exact_struct(source, 'zx_port_priv')])
        enum = exact_enum(source, 'zx_eth_reg')
        functions = '\n'.join(function(source, name) for name in (
            'zx_datapath_warm', 'zx_phy_node_put', 'zx_eth_prepare_port_ndev',
            'zx_eth_add_port_ndev', 'zx_tx_done_timer', 'zx_bm_seed_freelists',
            'zx_napi_delete', 'zx_eth_disarm', 'zx_eth_close_ports', 'zx_tx_origin_init',
            'zx_eth_probe', 'zx_eth_remove'))
        gate = next(line for line in source.splitlines()
                    if line.startswith('#define ZX_HAVE_DEBUG_IFACES '))
        force_default = re.search(r'static bool zx_force_dp_init[^;]*;', source).group()
        # The model's own layout constants are the driver's.
        for name in ('ZX_DDR_BASE', 'ZX_DDR_POOL', 'ZX_DDR_POOL2', 'ZX_DDR_FREELIST',
                     'ZX_DDR_RX_RING', 'ZX_DDR_TX_RING'):
            line = re.search(r'^#define ' + name + r' (\S+)$', model.MODEL, re.M)
            self.assertEqual(int(line.group(1), 0), driver_value(source, name), name)
        expected = ' '.join(f'{a:#x}+{s:#x}' for a, s in OLD_PROBE_MAPS)
        cfile, exe = self.out / 'probe.c', self.out / 'probe'
        cfile.write_text(model.MODEL + '\n' + gate + '\n' + enum + '\n' + structs +
                         force_default + boundaries + functions + cases)
        for name, resolved in self.resolved.items():
            for debug in (0, 1):
                with self.subTest(dtb=name, debug=debug):
                    cc(cfile, exe, ('-Wno-unused-parameter', f'-DRESOLVED_DDR={resolved:#x}',
                                    f'-DCONFIG_ZX279128_ETH_DEBUG={debug}'))
                    run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=30)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                    self.assertEqual(run.stdout.splitlines(),
                                     [f'cold {expected}', f'inherited {expected}'])

    # -- 5 ------------------------------------------------------------------
    def test_actual_warm_detection_accepts_what_the_old_one_did(self):
        for name, base in self.resolved.items():
            with self.subTest(dtb=name):
                run = subprocess.run([str(self.warm_exe), hex(base)], capture_output=True,
                                     text=True, timeout=30)
                self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                # Independent count: both bases inside the old window and a
                # mapped port with a configured control word.
                inside = 5 * 5          # of the 13 bases, 5 are in [0x41000000, 0x42000000)
                self.assertEqual(run.stdout.strip(), f'{13 * 13 * 5 * 5 * 2} cases '
                                 f'{inside * 3 * 4} warm')

    # -- static -------------------------------------------------------------
    def test_layout_constants_are_the_old_addresses(self):
        base = driver_value(self.text, 'ZX_DDR_BASE')
        offsets = {name: driver_value(self.text, name) for name in DDR_DEFINES[3:]}
        self.assertEqual(base + offsets['ZX_DDR_POOL'], 0x41000000)
        self.assertEqual(base + offsets['ZX_DDR_POOL2'], 0x41400000)
        self.assertEqual(base + offsets['ZX_DDR_FREELIST'], 0x41800000)
        self.assertEqual(base + offsets['ZX_DDR_FREELIST2'], 0x41808000)
        self.assertEqual(base + offsets['ZX_DDR_RX_RING'], 0x41a00000)
        self.assertEqual(base + offsets['ZX_DDR_TMQ'], 0x41b00000)
        self.assertEqual(base + offsets['ZX_DDR_TX_RING'], 0x41c00000)
        self.assertEqual(driver_value(self.text, 'ZX_DDR_ALIGN'), 0x100000)
        self.assertEqual(base % 0x100000, 0)
        for mapping in OLD_PROBE_MAPS + OLD_INIT_MAPS:
            self.assertLessEqual(mapping[0] + mapping[1], OLD_REGION[0] + OLD_REGION[1])
        # One compile-time check per structure, kept in the driver.
        self.assertEqual(len(re.findall(r'^static_assert\(ZX_DDR_', self.text, re.M)), 8)

    def test_no_ddr_address_outside_the_window_constants(self):
        code = ' '.join(tokens(self.text))
        literals = re.findall(r'\b0x4[0-7][0-9a-fA-F]{6}\b', code)
        self.assertEqual(literals, ['0x41000000'])     # the ZX_DDR_BASE fallback only
        self.assertEqual(tokens(self.text).count('ZX_DDR_BASE'), 3)   # define, fallback, log
        # Every use of the base: the struct field, the two assignments, the
        # warm window, the init addresses and the 5 probe addresses. The cold
        # TOPCRM reset/gate/DPA block (CONFIG_ZX279128_PP_TABLES, docs/PP-KEY.md
        # §15-§16) parks the PM/ACL table bases at ze->ddr_phys after the reset,
        # before any engine can walk their reset-garbage pointers, which is 3
        # more uses (two writes + the log) - still the window base, never a
        # literal, so the invariant this test enforces is unchanged.
        uses = {name: tokens(function(self.text, name)).count('ddr_phys') for name in (
            'zx_eth_resolve_ddr', 'zx_datapath_warm', 'zx_eth_datapath_init', 'zx_eth_probe')}
        self.assertEqual(uses, {'zx_eth_resolve_ddr': 2, 'zx_datapath_warm': 2,
                                'zx_eth_datapath_init': 12, 'zx_eth_probe': 5})
        self.assertEqual(tokens(self.text).count('ddr_phys'), sum(uses.values()) + 1)

    def test_probe_resolves_the_window_before_touching_hardware(self):
        probe = function(self.text, 'zx_eth_probe')
        call = 'ret = zx_eth_resolve_ddr(ze);'
        self.assertEqual(probe.count(call), 1)
        self.assertLess(probe.index('zx_eth_phy_modes(ze)'), probe.index(call))
        self.assertLess(probe.index(call), probe.index('devm_ioremap('))
        self.assertLess(probe.index(call), probe.index('zx_datapath_warm(ze)'))
        self.assertLess(probe.index(call), probe.index('zx_eth_datapath_init(ze)'))


if __name__ == '__main__':
    unittest.main()
