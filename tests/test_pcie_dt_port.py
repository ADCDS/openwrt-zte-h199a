"""PCIe host: the port index follows from the node's dbi address.

No functional change on the H199A, shown four ways:

1. No board DTB (base, -production, -production-qualify) has zte,pcie-port
   any more; each node's dbi entry is still at the address of the port the
   node's zte,pcie-port named at commit cb239a9 (OLD_PORT below). Nothing else
   in the DTBs changed (test_pcie_dt_resources.py checks the other entries).
2. The driver's actual zx_pcie_port_of(), compiled on the host and fed each
   DTB's reg/reg-names, selects OLD_PORT for every node, without the
   deprecation warning. With the old property put back (a pre-change DTB) it
   selects the same port and reports the property.
3. Over a grid of zte,pcie-port values (absent, empty, 0, 1, 2, ~0) and dbi
   entries (absent, either port, too small, unknown address, any position in
   reg-names), the new selection (zx_pcie_port_of() + the unchanged
   zx_map_named() dbi check) gives exactly the frozen cb239a9 result whenever
   the property is present. Without it, the old code refused the node and the
   new one takes the port from a valid dbi entry, and refuses anything else.
4. The actual zx_pcie_probe() resolves the port before it maps or prepares
   anything, warns once for a node that still has the property, and refuses a
   node whose property contradicts its dbi address before touching anything.

The cross-compile against the pinned 6.6.151 tree is
test_pcie_dt_resources.PcieCrossCompileTests.
"""
from pathlib import Path
import subprocess
import tempfile
import unittest

import dt_fixture as fx
from test_tx_origin_r204 import exact_define, exact_struct, function, tokens

NODES = ('/soc/pcie@f000000', '/soc/pcie@f100000')
OLD_PORT = {'/soc/pcie@f000000': 0, '/soc/pcie@f100000': 1}    # zte,pcie-port at cb239a9
OLD_DBI = {0: 0x0f000000, 1: 0x0f100000}                         # what cb239a9 required

COMMON = r'''
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
typedef uint32_t resource_size_t;
typedef uint32_t phys_addr_t;
#define __iomem
#define SZ_4K 4096
#define SZ_16K 16384
#define ERR_PTR(n) ((void *)(intptr_t)(n))
#define PTR_ERR(p) ((long)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
struct resource { resource_size_t start, end; };
static resource_size_t resource_size(const struct resource *r) { return r->end - r->start + 1; }
/* A pcie node as the of_* helpers see it. legacy_len is the byte length of
 * zte,pcie-port, -1 when the node has none. */
struct device_node {
	const char *names[8]; u32 base[8], size[8]; unsigned nnames, nreg;
	int legacy_len; u32 legacy;
};
/* drivers/of semantics: a missing string or property is negative, a
 * property shorter than a u32 is -EOVERFLOW. */
static int of_property_match_string(const struct device_node *np, const char *prop,
				    const char *s)
{
	assert(!strcmp(prop, "reg-names"));
	if (!np->nnames)
		return -EINVAL;
	for (unsigned i = 0; i < np->nnames; i++)
		if (!strcmp(np->names[i], s))
			return i;
	return -ENODATA;
}
static int of_address_to_resource(struct device_node *np, int index, struct resource *r)
{
	if (index < 0 || (unsigned)index >= np->nreg)
		return -EINVAL;
	r->start = np->base[index];
	r->end = np->base[index] + np->size[index] - 1;
	return 0;
}
static bool of_property_present(const struct device_node *np, const char *prop)
{
	assert(!strcmp(prop, "zte,pcie-port"));
	return np->legacy_len >= 0;
}
static int of_property_read_u32(const struct device_node *np, const char *prop, u32 *v)
{
	assert(!strcmp(prop, "zte,pcie-port"));
	if (np->legacy_len < 0)
		return -EINVAL;
	if (np->legacy_len < 4)
		return -EOVERFLOW;
	*v = np->legacy;
	return 0;
}
static unsigned char window[SZ_16K];
static unsigned iomaps;
static void *of_iomap(struct device_node *np, int index) { (void)np; (void)index; iomaps++; return window; }
@DT@
'''

PORT_CASES = r'''
/* cb239a9's selection: zx_pcie_probe() and the zx_pcie_prepare_pair() loop
 * took the port from zte,pcie-port (refusing a read error or > 1), then
 * zx_map_named() required dbi at that port's address. */
static long old_select(struct device_node *np)
{
	void __iomem *p;
	u32 port;

	if (of_property_read_u32(np, "zte,pcie-port", &port) || port > 1)
		return -EINVAL;
	p = zx_map_named(np, "dbi", 0x0f000000 + port * 0x100000, SZ_16K);
	return IS_ERR(p) ? PTR_ERR(p) : (long)port;
}
/* Today's: the same pair of steps in zx_pcie_prepare_pair(). */
static long new_select(struct device_node *np, bool *legacy)
{
	void __iomem *p;
	int port = zx_pcie_port_of(np, legacy);

	if (port < 0)
		return port;
	p = zx_map_named(np, "dbi", ZX_DBI_PHYS(port), SZ_16K);
	return IS_ERR(p) ? PTR_ERR(p) : port;
}
static struct device_node with_dbi(const struct device_node *board, int slot, u32 base, u32 size)
{
	struct device_node np = *board;

	if (slot < 0) {				/* no dbi entry at all */
		np.names[0] = "regs";
		return np;
	}
	np.names[0] = np.names[slot]; np.base[0] = np.base[slot]; np.size[0] = np.size[slot];
	np.names[slot] = "dbi"; np.base[slot] = base; np.size[slot] = size;
	return np;
}
int main(int argc, char **argv)
{
	assert(argc == 2);
	if (!strcmp(argv[1], "dt")) {
		for (unsigned b = 0; b < NBOARDS; b++)
			for (unsigned n = 0; n < 2; n++) {
				struct device_node np = boards[b][n];
				bool legacy = true;
				int port = zx_pcie_port_of(&np, &legacy);
				long selected = new_select(&np, &legacy);

				printf("%u %u port %d legacy %d select %ld\n", b, n, port, legacy,
				       selected);
				/* The same node with the property it had before. */
				np.legacy_len = 4; np.legacy = n;
				port = zx_pcie_port_of(&np, &legacy);
				printf("%u %u old-dtb port %d legacy %d old %ld\n", b, n, port, legacy,
				       old_select(&np));
			}
	} else if (!strcmp(argv[1], "grid")) {
		static const struct { int len; u32 value; } props[] = {
			{ -1, 0 }, { 0, 0 }, { 2, 0 }, { 4, 0 }, { 4, 1 }, { 4, 2 }, { 4, 0xffffffff },
		};
		/* port: whose address it is; usable: also large enough to map. */
		static const struct { u32 base, size; int port; bool usable; } dbis[] = {
			{ 0x0f000000, 0x4000, 0, true }, { 0x0f100000, 0x4000, 1, true },
			{ 0x0f000000, 0x1000, 0, false },	/* smaller than the 16 KiB mapped */
			{ 0x0f100000, 0x10000, 1, true },	/* larger is fine */
			{ 0x0f001000, 0x4000, -1, false }, { 0x0f200000, 0x4000, -1, false },
			{ 0x0e000000, 0x4000, -1, false }, { 0, 0x4000, -1, false },
		};
		unsigned cases = 0, same = 0, taken = 0;

		for (unsigned b = 0; b < NBOARDS; b++)
			for (unsigned n = 0; n < 2; n++)
				for (int slot = -1; slot < (int)boards[b][n].nreg; slot++)
					/* Without a dbi entry its value is moot: one pass. */
					for (unsigned d = 0; d < (slot < 0 ? 1 : sizeof(dbis) / sizeof(dbis[0])); d++)
						for (unsigned p = 0; p < sizeof(props) / sizeof(props[0]); p++) {
							struct device_node np = with_dbi(&boards[b][n], slot,
								dbis[d].base, dbis[d].size);
							bool legacy;
							long old, now;

							np.legacy_len = props[p].len;
							np.legacy = props[p].value;
							/* The helper alone: the address's port, if the
							 * property is absent or names that port. */
							int owner = slot < 0 ? -1 : dbis[d].port;
							bool agrees = props[p].len < 0 ||
								(props[p].len >= 4 && props[p].value == (u32)owner);

							assert(zx_pcie_port_of(&np, &legacy) ==
							       (owner >= 0 && agrees ? owner : -EINVAL));
							assert(legacy == (props[p].len >= 0));
							old = old_select(&np);
							now = new_select(&np, &legacy);
							if (props[p].len >= 0) {
								assert(legacy && now == old);
								same++;
							} else {
								bool usable = slot >= 0 && dbis[d].usable;

								assert(old == -EINVAL && !legacy);
								assert(now == (usable ? owner : -EINVAL));
								taken += now >= 0;
							}
							cases++;
						}
		printf("%u cases %u same as cb239a9 %u taken from dbi\n", cases, same, taken);
	} else {
		return 2;
	}
	return 0;
}
'''

PROBE_MODEL = r'''
struct device { struct device_node *of_node; };
struct platform_device { struct device dev; };
struct dw_pcie_ops { int unused; };
struct dw_pcie_host_ops { int unused; };
struct dw_pcie_rp { const struct dw_pcie_host_ops *ops; };
struct dw_pcie { struct device *dev; void *dbi_base; const struct dw_pcie_ops *ops; struct dw_pcie_rp pp; };
struct gpio_desc { int unused; };
@STRUCT@
static const struct dw_pcie_ops zx_dw_pcie_ops;
static const struct dw_pcie_host_ops zx_pcie_host_ops;
#define GFP_KERNEL 0
#define IORESOURCE_MEM 0x200
static unsigned allocs, lookups, maps, crms, prepares, inits, warns, errors, drvdata;
static int prepared_port = -1;
static char warning[160];
static void *devm_kzalloc(struct device *d, size_t n, int flags)
{ (void)d; (void)flags; allocs++; return calloc(1, n); }
static void platform_set_drvdata(struct platform_device *p, void *data) { (void)p; (void)data; drvdata++; }
static struct resource app = { 0x09500000, 0x09500fff };
static struct resource *platform_get_resource_byname(struct platform_device *p, unsigned type,
						     const char *name)
{ (void)p; assert(type == IORESOURCE_MEM && !strcmp(name, "app")); lookups++; return &app; }
static void *devm_ioremap_resource(struct device *d, struct resource *r)
{ (void)d; (void)r; maps++; return window; }
static int zx_pcie_map_crm(struct platform_device *p, struct zx_pcie *zx)
{ (void)p; (void)zx; crms++; return 0; }
static int zx_pcie_prepare_pair(struct zx_pcie *zx) { prepares++; prepared_port = zx->port; return 0; }
static int dw_pcie_host_init(struct dw_pcie_rp *pp) { (void)pp; inits++; return 0; }
static int zx_pcie_group;
static int devm_device_add_group(struct device *dev,const void *group) {
 (void)dev;assert(group==&zx_pcie_group);return 0;
}
static void dev_warn(struct device *d, const char *fmt, ...)
{
	va_list ap;

	(void)d; warns++;
	va_start(ap, fmt); vsnprintf(warning, sizeof(warning), fmt, ap); va_end(ap);
}
static int dev_err_probe(struct device *d, int err, const char *fmt, ...)
{ (void)d; (void)fmt; errors++; return err; }
'''

PROBE_CASES = r'''
static void probe(struct device_node *np)
{
	struct platform_device pdev = { { np } };
	int rc;

	allocs = lookups = maps = crms = prepares = inits = warns = errors = drvdata = 0;
	prepared_port = -1; warning[0] = 0;
	rc = zx_pcie_probe(&pdev);
	printf("rc %d port %d warns %u errors %u allocs %u drvdata %u lookups %u maps %u crms %u "
	       "prepares %u inits %u %s", rc, prepared_port, warns, errors, allocs, drvdata,
	       lookups, maps, crms, prepares, inits, warns ? warning : "-\n");
}
int main(int argc, char **argv)
{
	assert(argc == 3);
	struct device_node np = boards[atoi(argv[1])][atoi(argv[2]) & 1];
	unsigned port = atoi(argv[2]) & 1;

	probe(&np);				/* the board DT */
	np.legacy_len = 4; np.legacy = port;	/* a pre-change DT */
	probe(&np);
	np.legacy = !port;			/* contradicts dbi */
	probe(&np);
	return 0;
}
'''


def dt_c(dtbs):
    rows = []
    for dtb in dtbs:
        nodes = []
        for node in NODES:
            names = fx.fdtget(dtb, node, 'reg-names', 's')
            regs = fx.reg_pairs(dtb, node)
            legacy = fx.fdtget(dtb, node, 'zte,pcie-port', 'u')
            nodes.append('{ { %s }, { %s }, { %s }, %d, %d, %d, %d }' % (
                ', '.join(f'"{n}"' for n in names), ', '.join(f'{b:#x}' for b, _ in regs),
                ', '.join(f'{s:#x}' for _, s in regs), len(names), len(regs),
                -1 if legacy is None else 4 * len(legacy), legacy[0] if legacy else 0))
        rows.append('\t{ ' + ', '.join(nodes) + ' }')
    return '\n'.join([f'#define NBOARDS {len(dtbs)}',
                      'static const struct device_node boards[NBOARDS][2] = {',
                      ',\n'.join(rows), '};'])


def cc(source, exe):
    built = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                            '-Wno-unused-function', str(source), '-o', str(exe)],
                           capture_output=True, text=True, timeout=60)
    if built.returncode:
        raise AssertionError(built.stderr)


@unittest.skipUnless(fx.dts_tools_available(), 'requires the unpacked kernel tree, dtc and fdtget')
class PcieDtPortTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='pcie-port-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.out = Path(cls.tmp.name)
        cls.dtb, cls.warnings = {}, {}
        for name in fx.DTS_NAMES:
            cls.dtb[name], cls.warnings[name] = fx.compile_dts(name, cls.out)
        cls.text = fx.PCIE_SOURCE.read_text()
        common = (COMMON.replace('@DT@', dt_c([cls.dtb[n] for n in fx.DTS_NAMES])) +
                  exact_define(cls.text, 'ZX_DBI_PHYS(port)') +
                  exact_define(cls.text, 'ZX_APP_PHYS(port)') +
                  function(cls.text, 'zx_map_named') + function(cls.text, 'zx_pcie_port_of'))
        cls.port_exe, cls.probe_exe = cls.out / 'port', cls.out / 'probe'
        (cls.out / 'port.c').write_text(common + PORT_CASES)
        cc(cls.out / 'port.c', cls.port_exe)
        (cls.out / 'probe.c').write_text(
            common + PROBE_MODEL.replace('@STRUCT@', exact_struct(cls.text, 'zx_pcie')) +
            function(cls.text, 'zx_pcie_probe') + PROBE_CASES)
        cc(cls.out / 'probe.c', cls.probe_exe)

    def run_exe(self, *args):
        run = subprocess.run([str(a) for a in args], capture_output=True, text=True, timeout=60)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return run.stdout.splitlines()

    def test_every_board_dtb_drops_the_property_and_keeps_dbi(self):
        for name, dtb in self.dtb.items():
            for node, port in OLD_PORT.items():
                with self.subTest(dtb=name, node=node):
                    self.assertNotRegex(self.warnings[name], r'pcie@')
                    self.assertIsNone(fx.fdtget(dtb, node, 'zte,pcie-port', 'u'))
                    regs = dict(zip(fx.fdtget(dtb, node, 'reg-names', 's'),
                                    fx.reg_pairs(dtb, node)))
                    self.assertEqual(regs['dbi'], (OLD_DBI[port], 0x4000))

    def test_actual_port_selection_of_every_board_dt_is_the_old_index(self):
        expected = []
        for b in range(len(fx.DTS_NAMES)):
            for n, node in enumerate(NODES):
                port = OLD_PORT[node]
                expected += [f'{b} {n} port {port} legacy 0 select {port}',
                             f'{b} {n} old-dtb port {port} legacy 1 old {port}']
        self.assertEqual(self.run_exe(self.port_exe, 'dt'), expected)

    def test_actual_selection_matches_cb239a9_wherever_the_property_exists(self):
        out = self.run_exe(self.port_exe, 'grid')
        # Per node: 6 reg-names slots x 8 dbi values x 7 property states,
        # plus 7 for no dbi entry at all; 2 nodes x 3 DTBs.
        cases = 6 * (6 * 8 * 7 + 7)
        same = 6 * (6 * 8 * 6 + 6)
        taken = 6 * 6 * 3          # three valid dbi entries in each slot
        self.assertEqual(out, [f'{cases} cases {same} same as cb239a9 {taken} taken from dbi'])

    def test_actual_probe_resolves_warns_and_refuses_before_touching_anything(self):
        message = 'zte,pcie-port is deprecated; the port follows from the dbi address'
        for b, name in enumerate(fx.DTS_NAMES):
            for n, node in enumerate(NODES):
                with self.subTest(dtb=name, node=node):
                    port = OLD_PORT[node]
                    ok = (f'rc 0 port {port} warns {{}} errors 0 allocs 1 drvdata 1 lookups 1 '
                          'maps 1 crms 1 prepares 1 inits 1 {}')
                    self.assertEqual(self.run_exe(self.probe_exe, b, n), [
                        ok.format(0, '-'), ok.format(1, message),
                        'rc -22 port -1 warns 0 errors 1 allocs 1 drvdata 0 lookups 0 maps 0 '
                        'crms 0 prepares 0 inits 0 -'])

    def test_port_addresses_are_the_old_expressions(self):
        for port, dbi in OLD_DBI.items():
            self.assertEqual(eval(exact_define(self.text, 'ZX_DBI_PHYS(port)')
                                  .split(None, 2)[2].replace('(port)', str(port))), dbi)
            self.assertEqual(eval(exact_define(self.text, 'ZX_APP_PHYS(port)')
                                  .split(None, 2)[2].replace('(port)', str(port))),
                             0x09500000 + port * 0x100000)

    def test_the_property_is_read_only_by_the_port_helper(self):
        helper = function(self.text, 'zx_pcie_port_of')
        self.assertEqual(self.text.count('"zte,pcie-port"'), helper.count('"zte,pcie-port"'))
        for name in ('zx_pcie_probe', 'zx_pcie_prepare_pair'):
            body = tokens(function(self.text, name))
            self.assertEqual(body.count('zx_pcie_port_of'), 1, name)
            self.assertNotIn('0x0f000000', body)
            self.assertNotIn('0x09500000', body)
        probe = function(self.text, 'zx_pcie_probe')
        self.assertLess(probe.index('zx_pcie_port_of('), probe.index('platform_get_resource_byname('))
        self.assertLess(probe.index('zx_pcie_port_of('), probe.index('zx_pcie_prepare_pair('))


if __name__ == '__main__':
    unittest.main()
