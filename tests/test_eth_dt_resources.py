"""Ethernet: register blocks from named reg entries, phy-mode honoured.

No functional change on the H199A:

1. The compiled board DTBs name every block the driver used to map by fixed
   physical address, at that address and at the size it maps (OLD below,
   frozen from commit acea19c), with reg[0] still MAC 0.
2. The driver's fallback table is OLD, and its actual zx_eth_resolve_regs(),
   compiled on the host and fed the DTB's reg/reg-names, resolves every block
   to OLD. Without names it falls back to OLD and says so in one line.
3. The actual zx_eth_phy_mode() accepts the board's "rgmii" everywhere (so
   of_phy_connect() still gets PHY_INTERFACE_MODE_RGMII) and refuses any
   other mode with -EINVAL.

Plus a cross-compile of the driver against the pinned linux-6.6.151 tree in
the shared tree's configuration and in the shipping one (debug/PP off).
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import dt_fixture as fx
from test_tx_origin_r204 import exact_define, function, tokens

# name: (physical base, bytes mapped) as zx279128-eth.c hard-coded them at
# acea19c. spa and attach were separate fixed mappings inside the NPP window.
OLD = {
    'mac0': (0x92200000, 0x1000), 'mac1': (0x92240000, 0x1000),
    'mac2': (0x92280000, 0x1000), 'mac3': (0x922c0000, 0x1000),
    'fabric': (0x92000000, 0x1000), 'glb': (0x92040000, 0x1000),
    'npp': (0x921c0000, 0x20000), 'tmc': (0x92340000, 0x1000),
    'tmd': (0x92344000, 0x1000), 'bm': (0x92348000, 0x1000),
    'qmg': (0x9234c000, 0x1000), 'tmq': (0x92350000, 0x1000),
    'pp': (0x92380000, 0x1000), 'sbrg': (0x92388000, 0x1000),
    'cla': (0x9238c000, 0x1000), 'ponpp': (0x923a0000, 0x1000),
}
OLD_SPA, OLD_ATTACH = 0x921d4000, 0x921d9000
NODE = '/soc/ethernet@92200000'

MODEL = r'''
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <strings.h>
typedef uint32_t u32;
@PRELUDE@
#define IORESOURCE_MEM 0x200
#define ZX_NPORTS 4
struct device_node { const char *phy_mode, *conn_type; };
struct device { struct device_node *of_node; };
struct platform_device { struct device dev; };
struct resource { resource_size_t start, end; };
/* of_get_phy_mode() semantics from net/core/of_net.c, over the kernel's
 * phy_interface_t order (first entries). */
typedef enum {
	PHY_INTERFACE_MODE_NA, PHY_INTERFACE_MODE_INTERNAL, PHY_INTERFACE_MODE_MII,
	PHY_INTERFACE_MODE_GMII, PHY_INTERFACE_MODE_SGMII, PHY_INTERFACE_MODE_TBI,
	PHY_INTERFACE_MODE_REVMII, PHY_INTERFACE_MODE_RMII, PHY_INTERFACE_MODE_REVRMII,
	PHY_INTERFACE_MODE_RGMII, PHY_INTERFACE_MODE_RGMII_ID,
	PHY_INTERFACE_MODE_RGMII_RXID, PHY_INTERFACE_MODE_RGMII_TXID,
	PHY_INTERFACE_MODE_MAX
} phy_interface_t;
static const char *const modes[] = { "", "internal", "mii", "gmii", "sgmii", "tbi",
	"rev-mii", "rmii", "rev-rmii", "rgmii", "rgmii-id", "rgmii-rxid", "rgmii-txid" };
struct zx_eth {
	struct device *dev;
	phys_addr_t phys[ZX_NREGS];
	int bound_port;
	phy_interface_t phy_modes[ZX_NPORTS];
	phy_interface_t phy_mode;
};
static char message[256];
static unsigned infos, errors;
static void dev_info(struct device *d, const char *fmt, ...)
{
	va_list ap;

	(void)d; infos++;
	va_start(ap, fmt); vsnprintf(message, sizeof(message), fmt, ap); va_end(ap);
}
static int dev_err_probe(struct device *d, int err, const char *fmt, ...)
{ (void)d; (void)fmt; errors++; return err; }
static int scnprintf(char *buf, size_t size, const char *fmt, ...)
{
	va_list ap;
	int n;

	va_start(ap, fmt); n = vsnprintf(buf, size, fmt, ap); va_end(ap);
	return n < (int)size ? n : (size ? (int)size - 1 : 0);
}

/* reg/reg-names as of_device_alloc() turns them into named resources. */
struct dtres { const char *name; u32 start, size; };
@DT@
static const struct dtres *table;
static unsigned ntable;
static struct resource found;
static struct resource *platform_get_resource_byname(struct platform_device *p,
						     unsigned type, const char *name)
{
	(void)p; assert(type == IORESOURCE_MEM);
	for (unsigned i = 0; i < ntable; i++)
		if (table[i].name && !strcmp(table[i].name, name)) {
			found.start = table[i].start;
			found.end = table[i].start + table[i].size - 1;
			return &found;
		}
	return NULL;
}
static resource_size_t resource_size(const struct resource *r) { return r->end - r->start + 1; }

static bool of_property_present(const struct device_node *np, const char *name)
{
	if (!strcmp(name, "phy-mode"))
		return np->phy_mode;
	assert(!strcmp(name, "phy-connection-type"));
	return np->conn_type;
}
/* ethernet-ports/port@N lookup, over the DT's port nodes. */
static struct device_node ports[ZX_NPORTS];
static bool no_ports;
static unsigned port_puts, port_gets;
static struct device_node *zx_port_node(struct device *d, int port)
{
	(void)d;
	if (port < 0 || no_ports)
		return NULL;
	port_gets++;
	return &ports[port];
}
static void of_node_put(struct device_node *np) { if (np) port_puts++; }
static int of_get_phy_mode(struct device_node *np, phy_interface_t *mode)
{
	const char *pm = np->phy_mode ? np->phy_mode : np->conn_type;

	*mode = PHY_INTERFACE_MODE_NA;
	if (!pm)
		return -EINVAL;
	for (int i = 0; i < PHY_INTERFACE_MODE_MAX; i++)
		if (!strcasecmp(pm, modes[i])) {
			*mode = i;
			return 0;
		}
	return -ENODEV;
}
'''

CASES = r'''
static struct device dev;
static struct platform_device pdev;
static void resolve(const struct dtres *t, unsigned n, int expect)
{
	struct zx_eth ze = { .dev = &dev };

	table = t; ntable = n; infos = errors = 0; message[0] = 0;
	assert(zx_eth_resolve_regs(&ze, &pdev) == expect);
	if (expect)
		return;
	for (int i = 0; i < ZX_NREGS; i++)
		printf("%s %#x\n", zx_eth_reg_desc[i].name, ze.phys[i]);
	printf("infos %u: %s", infos, message);
	if (!infos)
		printf("\n");
}
static int mode(const char *port, const char *port_conn, const char *top, phy_interface_t *m)
{
	struct device_node top_np = { top, NULL }, port_np = { port, port_conn };
	struct device d = { &top_np };

	*m = PHY_INTERFACE_MODE_MAX;
	return zx_eth_phy_mode(&d, port || port_conn ? &port_np : NULL, m);
}
int main(int argc, char **argv)
{
	assert(argc == 2);
	if (!strcmp(argv[1], "dt")) {
		resolve(board, nboard, 0);
	} else if (!strcmp(argv[1], "unnamed")) {
		resolve(unnamed, 1, 0);
	} else if (!strcmp(argv[1], "partial")) {
		resolve(partial, npartial, 0);
	} else if (!strcmp(argv[1], "moved")) {
		resolve(moved, nboard, 0);
	} else if (!strcmp(argv[1], "small")) {
		resolve(small, nboard, -EINVAL);
		assert(errors == 1);
		printf("small ok\n");
	} else if (!strcmp(argv[1], "portmodes")) {
		struct device_node top = { top_mode, NULL };
		struct device d = { &top };

		for (int bound = -1; bound < ZX_NPORTS; bound++) {
			struct zx_eth ze = { .dev = &d, .bound_port = bound };

			for (unsigned i = 0; i < ZX_NPORTS; i++)
				ports[i] = (struct device_node){ port_modes[i], NULL };
			port_gets = port_puts = 0;
			assert(!zx_eth_phy_modes(&ze) && port_gets == 4 && port_puts == 4);
			for (unsigned i = 0; i < ZX_NPORTS; i++)
				assert(ze.phy_modes[i] == PHY_INTERFACE_MODE_RGMII);
			assert(ze.phy_mode == PHY_INTERFACE_MODE_RGMII);
		}
		/* Any one bad port fails the whole probe, before it maps anything. */
		for (unsigned bad = 0; bad < ZX_NPORTS; bad++) {
			struct zx_eth ze = { .dev = &d, .bound_port = 0 };

			for (unsigned i = 0; i < ZX_NPORTS; i++)
				ports[i] = (struct device_node){ i == bad ? "rgmii-id" : port_modes[i], NULL };
			port_gets = port_puts = 0;
			assert(zx_eth_phy_modes(&ze) == -EINVAL && port_gets == port_puts);
		}
		/* No port nodes: the legacy node-level value, for every port. */
		struct zx_eth ze = { .dev = &d, .bound_port = -1 };
		no_ports = true;
		assert(!zx_eth_phy_modes(&ze) && ze.phy_mode == PHY_INTERFACE_MODE_RGMII);
		top.phy_mode = "gmii";
		assert(zx_eth_phy_modes(&ze) == -EINVAL);
		no_ports = false;
		printf("portmodes ok\n");
	} else if (!strcmp(argv[1], "modes")) {
		phy_interface_t m;

		/* The board: every port and the node itself say "rgmii". */
		for (unsigned i = 0; i < 4; i++) {
			assert(!mode(port_modes[i], NULL, top_mode, &m) && m == PHY_INTERFACE_MODE_RGMII);
		}
		assert(!mode(NULL, NULL, top_mode, &m) && m == PHY_INTERFACE_MODE_RGMII);
		/* Absent everywhere: RGMII, as before. */
		assert(!mode(NULL, NULL, NULL, &m) && m == PHY_INTERFACE_MODE_RGMII);
		/* The port's own value wins over the legacy node-level one. */
		assert(!mode("rgmii", NULL, "gmii", &m) && m == PHY_INTERFACE_MODE_RGMII);
		assert(!mode(NULL, "rgmii", NULL, &m) && m == PHY_INTERFACE_MODE_RGMII);
		assert(!mode("RGMII", NULL, NULL, &m) && m == PHY_INTERFACE_MODE_RGMII);
		/* Anything else is refused. */
		const char *bad[] = { "rgmii-id", "rgmii-rxid", "rgmii-txid", "gmii", "mii",
				      "internal", "sgmii", "bogus", "" };
		for (unsigned i = 0; i < sizeof(bad) / sizeof(bad[0]); i++) {
			errors = 0;
			assert(mode(bad[i], NULL, "rgmii", &m) == -EINVAL && errors == 1);
			assert(mode(NULL, bad[i], NULL, &m) == -EINVAL);
			assert(mode(NULL, NULL, bad[i], &m) == -EINVAL);
		}
		printf("modes ok\n");
	} else {
		return 2;
	}
	return 0;
}
'''


def c_table(name, rows):
    body = ', '.join(f'{{ "{n}", {b:#x}, {s:#x} }}' if n else f'{{ NULL, {b:#x}, {s:#x} }}'
                     for n, (b, s) in rows)
    return f'static const struct dtres {name}[] = {{ {body} }};'


def dt_c(dtb):
    names = fx.fdtget(dtb, NODE, 'reg-names', 's')
    regs = fx.reg_pairs(dtb, NODE)
    assert len(names) == len(regs)
    board = list(zip(names, regs))
    partial = [(n, r) for n, r in board if n not in ('glb', 'pp')]
    moved = [(n, (b + 0x01000000, s)) for n, (b, s) in board]
    small = [(n, (b, 0x1000) if n == 'npp' else (b, s)) for n, (b, s) in board]
    ports = [fx.fdtget(dtb, f'{NODE}/ethernet-ports/port@{i}', 'phy-mode', 's')[0]
             for i in range(4)]
    top = fx.fdtget(dtb, NODE, 'phy-mode', 's')[0]
    return '\n'.join([
        c_table('board', board), f'static const unsigned nboard = {len(board)};',
        c_table('unnamed', [(None, regs[0])]),
        c_table('partial', partial), f'static const unsigned npartial = {len(partial)};',
        c_table('moved', moved), c_table('small', small),
        'static const char *const port_modes[4] = { ' + ', '.join(f'"{m}"' for m in ports) + ' };',
        f'static const char *const top_mode = "{top}";',
    ])


def driver_offset(text, name):
    return int(exact_define(text, name).split()[2], 0)


@unittest.skipUnless(fx.dts_tools_available(), 'requires the unpacked kernel tree, dtc and fdtget')
class EthDtResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='eth-dt-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.out = Path(cls.tmp.name)
        cls.dtb, cls.warnings = {}, {}
        for name in fx.DTS_NAMES:
            cls.dtb[name], cls.warnings[name] = fx.compile_dts(name, cls.out)
        cls.text = fx.ETH_SOURCE.read_text()
        code = (MODEL.replace('@PRELUDE@', fx.eth_reg_prelude(cls.text))
                     .replace('@DT@', dt_c(cls.dtb[fx.BASE_DTS])) +
                '\n'.join(function(cls.text, n) for n in (
                    'zx_has_phy_mode', 'zx_eth_phy_mode', 'zx_eth_phy_modes',
                    'zx_eth_resolve_regs')) + CASES)
        src, cls.exe = cls.out / 'eth_dt.c', cls.out / 'eth_dt'
        src.write_text(code)
        built = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                '-Wno-unused-function', '-Wno-sign-compare', str(src),
                                '-o', str(cls.exe)], capture_output=True, text=True)
        if built.returncode:
            raise AssertionError(built.stderr)

    def run_case(self, case):
        run = subprocess.run([str(self.exe), case], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return run.stdout.splitlines()

    def resolved(self, case):
        lines = self.run_case(case)
        phys = dict(line.split() for line in lines[:-1])
        return {k: int(v, 16) for k, v in phys.items()}, lines[-1]

    def test_every_board_dtb_names_the_old_blocks(self):
        for name, dtb in self.dtb.items():
            with self.subTest(dtb=name):
                self.assertNotRegex(self.warnings[name], r'ethernet@', name)
                names = fx.fdtget(dtb, NODE, 'reg-names', 's')
                regs = fx.reg_pairs(dtb, NODE)
                self.assertEqual(names[0], 'mac0')
                self.assertEqual(regs[0], OLD['mac0'])     # reg[0] unchanged
                self.assertEqual(dict(zip(names, regs)), OLD)
                self.assertEqual(len(names), len(set(names)))

    def test_driver_fallback_table_and_offsets_are_the_old_constants(self):
        phys, _ = self.resolved('unnamed')
        self.assertEqual(phys, {k: v[0] for k, v in OLD.items()})
        spa, attach = driver_offset(self.text, 'ZX_NPP_SPA'), driver_offset(self.text, 'ZX_NPP_ATTACH')
        self.assertEqual(OLD['npp'][0] + spa, OLD_SPA)
        self.assertEqual(OLD['npp'][0] + attach, OLD_ATTACH)
        self.assertLessEqual(attach + 0x1000, OLD['npp'][1])   # both inside the NPP map
        # The minimum sizes the driver demands are the sizes it maps.
        sizes = re.findall(r'\[ZX_REG_\w+\]\s*=\s*\{\s*"(\w+)",[^,]+,\s*(SZ_\w+)',
                           fx.exact_table(self.text, 'zx_eth_reg_desc'))
        self.assertEqual({n: {'SZ_4K': 0x1000, 'SZ_128K': 0x20000}[s] for n, s in sizes},
                         {k: v[1] for k, v in OLD.items()})

    def test_actual_resolution_of_the_board_dt_is_the_old_map(self):
        phys, info = self.resolved('dt')
        self.assertEqual(phys, {k: v[0] for k, v in OLD.items()})
        self.assertEqual(info, 'infos 0: ')

    def test_actual_fallback_reports_once_and_only_what_is_missing(self):
        _, info = self.resolved('unnamed')
        self.assertEqual(info, 'infos 1: no reg-names entry for ' + ' '.join(OLD) +
                         '; using built-in addresses')
        phys, info = self.resolved('partial')
        self.assertEqual(phys, {k: v[0] for k, v in OLD.items()})
        self.assertEqual(info, 'infos 1: no reg-names entry for glb pp; using built-in addresses')

    def test_actual_resolution_follows_the_dt_not_the_constants(self):
        phys, info = self.resolved('moved')
        self.assertEqual(phys, {k: v[0] + 0x01000000 for k, v in OLD.items()})
        self.assertEqual(self.run_case('small'), ['small ok'])

    def test_actual_phy_mode_parsing(self):
        for name, dtb in self.dtb.items():
            self.assertEqual(fx.fdtget(dtb, NODE, 'phy-mode', 's'), ['rgmii'], name)
            for i in range(4):
                self.assertEqual(fx.fdtget(dtb, f'{NODE}/ethernet-ports/port@{i}', 'phy-mode', 's'),
                                 ['rgmii'], name)
        self.assertEqual(self.run_case('modes'), ['modes ok'])
        self.assertEqual(self.run_case('portmodes'), ['portmodes ok'])

    def test_no_fixed_address_left_on_the_datapath(self):
        for name in ('zx_eth_probe', 'zx_eth_datapath_init', 'zx_eth_software_ports',
                     'zx_eth_cpu_protocols', 'zx_eth_set_hw_mac'):
            with self.subTest(function=name):
                body = function(self.text, name)
                # Register space only: the DDR rings and pools (0x41xxxxxx)
                # come from memory-region (test_eth_memory_region.py).
                literal = re.search(r'ioremap\w*\(\s*0x9\w*', body)
                self.assertIsNone(literal, literal and literal.group())
                ids = set(tokens(body))
                self.assertFalse(ids & {'BM_BASE', 'TMC_BASE', 'TMD_BASE', 'TMQ_BASE',
                                        'ZX_MAC_BASE', 'ZX_MAC_STRIDE', 'SPA_BASE'})
        # The connect calls take the parsed mode; RGMII is named only inside
        # zx_eth_phy_mode(), as the default and the one accepted value.
        rgmii = re.compile(r'\bPHY_INTERFACE_MODE_RGMII\b')
        self.assertEqual(len(rgmii.findall(self.text)),
                         len(rgmii.findall(function(self.text, 'zx_eth_phy_mode'))))
        self.assertIn('ze->phy_mode);', function(self.text, 'zx_eth_open'))
        self.assertIn('ze->phy_modes[pp->port]);', function(self.text, 'zx_port_open'))
        # Parsed right after the register blocks, before any mapping beyond
        # reg[0] and long before the datapath is reset.
        probe = function(self.text, 'zx_eth_probe')
        self.assertLess(probe.index('zx_eth_resolve_regs(ze, pdev)'),
                        probe.index('zx_eth_phy_modes(ze)'))
        self.assertLess(probe.index('zx_eth_phy_modes(ze)'), probe.index('devm_ioremap('))
        self.assertLess(probe.index('zx_eth_phy_modes(ze)'), probe.index('zx_eth_datapath_init'))


@unittest.skipUnless(fx.cross_tools(), 'requires the pinned kernel tree and toolchain')
class EthCrossCompileTests(unittest.TestCase):
    def test_driver_builds_against_the_pinned_6_6_151_headers(self):
        tree, _ = fx.cross_tools()
        record = 'drivers/net/ethernet/zte/.zx279128-eth.o.cmd'
        if not (tree / record).exists():
            self.skipTest('kernel tree has no recorded Ethernet compile')
        with tempfile.TemporaryDirectory() as out:
            for label, include in (('tree config', None),
                                   ('shipping config', fx.release_autoconf(tree, out))):
                with self.subTest(config=label):
                    run = fx.cross_compile(fx.ETH_SOURCE, record, out, (), include)
                    self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
