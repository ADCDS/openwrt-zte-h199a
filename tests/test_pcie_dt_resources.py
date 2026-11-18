"""PCIe host: CRM blocks from named reg entries, PERST# from reset-gpios.

No functional change on the H199A, shown three ways:

1. The compiled board DTBs carry exactly the CRM windows and PERST# pins the
   driver used to hard-code (OLD below, frozen from commit acea19c).
2. The driver's actual resolution code (zx_pcie_map_crm, zx_pcie_get_perst),
   compiled on the host and fed the DTB's properties, maps those same
   addresses and selects those same pins; without the properties it falls
   back to them and says so once.
3. Driving PERST# through gpiod (with the real gpio-zx279128.c callbacks
   underneath and the DT's GPIO_ACTIVE_LOW) produces a register-access trace
   identical to the pre-change zx_gpio_out(), and so does the fallback path.

Plus a cross-compile of the driver against the pinned linux-6.6.151 tree.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

import dt_fixture as fx
from test_tx_origin_r204 import exact_define, exact_struct, function, tokens

# The addresses and pins pcie-zx279128.c hard-coded before this change.
OLD = {'crm0': 0x94000000, 'crm1': 0x94100000, 'crm2': 0x94200000,
       'gpio': 0x94407000, 'perst': {0: 53, 1: 55}}
NODES = {0: '/soc/pcie@f000000', 1: '/soc/pcie@f100000'}
GPIO_NODE = '/soc/gpio@94407000'
GPIO_ACTIVE_LOW = 1

# zx_gpio_out() exactly as it was at acea19c, the reference for the traces.
OLD_GPIO_OUT = r'''
static int zx_gpio_out(struct zx_pcie *zx, unsigned int g, int val)
{
	void __iomem *bank = zx->gpio + ZX_GPIO_BANK(g);
	u32 bit = BIT(g & 15);
	u32 off = val ? ZX_GPIO_SET : ZX_GPIO_CLR;
	u32 state;

	writel(readl(bank + off) | bit, bank + off);
	/* SET/CLR read zero. Observe the pin, allowing its synchronizer to
	 * settle, before starting the reset interval. Never replay a pulse.
	 */
	return readl_poll_timeout_atomic(bank + ZX_GPIO_IN, state,
					!!(state & bit) == !!val, 1, 1000);
}
/* The held-PERST gate read at acea19c, as a function. */
static int old_held_gate(struct zx_pcie *zx, unsigned int g)
{
	u32 value = readl(zx->gpio + ZX_GPIO_BANK(g) + ZX_GPIO_IN);

	return (value & BIT(g & 15)) ? -EIO : 0;
}
'''

# read_poll_timeout_atomic() and its readl wrapper from linux-6.6.151
# include/linux/iopoll.h (checked against the pinned tree when present).
IOPOLL = r'''
#define read_poll_timeout_atomic(op, val, cond, delay_us, timeout_us, \
					delay_before_read, args...) \
({ \
	u64 __timeout_us = (timeout_us); \
	s64 __left_ns = __timeout_us * NSEC_PER_USEC; \
	unsigned long __delay_us = (delay_us); \
	u64 __delay_ns = __delay_us * NSEC_PER_USEC; \
	if (delay_before_read && __delay_us) { \
		udelay(__delay_us); \
		if (__timeout_us) \
			__left_ns -= __delay_ns; \
	} \
	for (;;) { \
		(val) = op(args); \
		if (cond) \
			break; \
		if (__timeout_us && __left_ns < 0) { \
			(val) = op(args); \
			break; \
		} \
		if (__delay_us) { \
			udelay(__delay_us); \
			if (__timeout_us) \
				__left_ns -= __delay_ns; \
		} \
		cpu_relax(); \
		if (__timeout_us) \
			__left_ns--; \
	} \
	(cond) ? 0 : -ETIMEDOUT; \
})
#define readx_poll_timeout_atomic(op, addr, val, cond, delay_us, timeout_us) \
	read_poll_timeout_atomic(op, val, cond, delay_us, timeout_us, false, addr)
#define readl_poll_timeout_atomic(addr, val, cond, delay_us, timeout_us) \
	readx_poll_timeout_atomic(readl, addr, val, cond, delay_us, timeout_us)
'''

HEADER = r'''
#include <assert.h>
#include <errno.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint32_t u32;
typedef uint64_t u64;
typedef int64_t s64;
typedef uint32_t phys_addr_t;
typedef uint32_t resource_size_t;
typedef int spinlock_t;
#define __iomem
#define BIT(n) (1U << (n))
#define SZ_4K 4096
#define NSEC_PER_USEC 1000L
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define EPROBE_DEFER 517
#define IORESOURCE_MEM 0x200
#define GPIOD_ASIS 0
#define ERR_PTR(n) ((void *)(intptr_t)(n))
#define PTR_ERR(p) ((long)(intptr_t)(p))
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define cpu_relax() ((void)0)
#define spin_lock_irqsave(l, f) ((void)(l), (f) = 0)
#define spin_unlock_irqrestore(l, f) ((void)(l), (void)(f))
#define of_fwnode_handle(np) (np)
struct device { int unused; };
struct device_node { int node; };
struct platform_device { struct device dev; int node; };
struct resource { resource_size_t start, end; };
struct dw_pcie { struct device *dev; void *dbi_base; };
struct gpio_chip { int unused; };
struct gpio_desc { unsigned offset; bool active_low; };
static unsigned infos, errors;
static void dev_info(struct device *d, const char *fmt, ...) { (void)d; (void)fmt; infos++; }
static void dev_err(struct device *d, const char *fmt, ...) { (void)d; (void)fmt; errors++; }
static int dev_err_probe(struct device *d, int err, const char *fmt, ...)
{ (void)d; (void)fmt; errors++; return err; }

/* ---- the GPIO block: six 0x40-byte banks; the pin follows SET/CLR after
 * `lag` reads of IN (its synchronizer), or never when `stuck`. ---- */
static unsigned char block[SZ_4K];
static u32 level[6], target[6];
static unsigned countdown[6], lag;
static bool stuck;
struct access { char op; u32 off, val; };
static struct access trace[8192];
static unsigned ntrace;
static void record(char op, u32 off, u32 val)
{ assert(ntrace < 8192); trace[ntrace++] = (struct access){ op, off, val }; }
static u32 readl(const void *p)
{
	uintptr_t off = (const unsigned char *)p - block;
	unsigned bank = off / 0x40, reg = off % 0x40;
	u32 v = 0;

	assert(off < 0x180);
	if (reg == 0x14) {
		if (countdown[bank] && !stuck && !--countdown[bank])
			level[bank] = target[bank];
		v = level[bank];
	} else {
		assert(reg == 0x00 || reg == 0x18 || reg == 0x1c);	/* SET/CLR read 0 */
	}
	record('R', off, v);
	return v;
}
static void writel(u32 v, void *p)
{
	uintptr_t off = (unsigned char *)p - block;
	unsigned bank = off / 0x40, reg = off % 0x40;

	assert(off < 0x180 && (reg == 0x18 || reg == 0x1c));
	target[bank] = reg == 0x18 ? (level[bank] | v) : (level[bank] & ~v);
	if (stuck)
		;	/* the pin never follows */
	else if (lag)
		countdown[bank] = lag;
	else
		level[bank] = target[bank];
	record('W', off, v);
}
static void udelay(unsigned long us) { record('D', 0, us); }
static void reset_block(void)
{
	memset(level, 0xff, sizeof(level));	/* both PERST# released (high) */
	memset(target, 0xff, sizeof(target));
	memset(countdown, 0, sizeof(countdown));
	ntrace = 0;
}

/* ---- device tree, generated from the compiled DTB ---- */
struct dtres { const char *name; u32 start, size; };
@DT@
static struct resource found;
static struct resource *platform_get_resource_byname(struct platform_device *p,
						     unsigned type, const char *name)
{
	assert(type == IORESOURCE_MEM);
	for (unsigned i = 0; i < nres[p->node]; i++)
		if (res[p->node][i].name && !strcmp(res[p->node][i].name, name)) {
			found.start = res[p->node][i].start;
			found.end = res[p->node][i].start + res[p->node][i].size - 1;
			return &found;
		}
	return NULL;
}
static resource_size_t resource_size(const struct resource *r) { return r->end - r->start + 1; }

static u32 mapped[8][2];
static unsigned nmapped, fail_map;
static void *devm_ioremap(struct device *d, phys_addr_t base, resource_size_t size)
{
	(void)d;
	if (++nmapped == fail_map)
		return NULL;
	mapped[nmapped - 1][0] = base; mapped[nmapped - 1][1] = size;
	return block;
}
static void *ioremap(phys_addr_t base, resource_size_t size)
{
	return devm_ioremap(NULL, base, size);
}

/* ---- gpiolib, as far as the consumer API is used ---- */
static struct gpio_desc descs[2];
static int lookup_error;
static struct gpio_desc *fwnode_gpiod_get_index(struct device_node *fw, const char *con,
						int index, int flags, const char *label)
{
	assert(!strcmp(con, "reset") && !index && flags == GPIOD_ASIS && !strcmp(label, "PERST#"));
	if (lookup_error)
		return ERR_PTR(lookup_error);
	if (!has_perst[fw->node])
		return ERR_PTR(-ENOENT);
	descs[fw->node] = (struct gpio_desc){ perst_pin[fw->node], perst_flags[fw->node] & 1 };
	return &descs[fw->node];
}
'''

GPIOLIB = r'''
static struct zx_gpio chip = { .base = block };
/* gpiod_[gs]et_value(): logical value, inverted for GPIO_ACTIVE_LOW, through
 * the chip's own callbacks (gpiolib.c gpiod_get_value/gpiod_set_value_nocheck). */
static int gpiod_get_value(const struct gpio_desc *d)
{
	int v = zx_gpio_get(&chip.gc, d->offset);

	return d->active_low ? !v : v;
}
static void gpiod_set_value(struct gpio_desc *d, int value)
{
	zx_gpio_set(&chip.gc, d->offset, d->active_low ? !value : !!value);
}
'''

CASES = r'''
static struct device dev;
static void check_map_crm(int node, bool expect_fallback)
{
	struct platform_device p = { .node = node };
	struct zx_pcie zx = { .pci = { .dev = &p.dev } };

	nmapped = fail_map = infos = errors = 0;
	assert(zx_pcie_map_crm(&p, &zx) == 0);
	assert(zx.crm0 && zx.crm1 && zx.crm2 && nmapped == 3 && !errors);
	assert(infos == (expect_fallback ? 1U : 0U));
	for (unsigned i = 0; i < 3; i++)
		printf("crm%u %#x %#x\n", i, mapped[i][0], mapped[i][1]);
}
static void check_get_perst(int node, int port)
{
	struct device_node np = { node };
	struct zx_pcie zx = { .pci = { .dev = &dev }, .port = port };

	nmapped = infos = errors = 0; lookup_error = 0;
	assert(zx_pcie_get_perst(&zx, &np) == 0);
	if (zx.perst) {
		assert(!zx.gpio && !nmapped && !infos);
		printf("perst %d desc %u %u\n", port, zx.perst->offset, zx.perst->active_low);
	} else {
		assert(zx.gpio == block && nmapped == 1 && infos == 1);
		printf("perst %d pin %u block %#x %#x\n", port, zx.perst_pin, mapped[0][0], mapped[0][1]);
	}
}
/* One pulse (assert, release) and the held-PERST gate read, through `zx`
 * (new code) or through the acea19c reference with pin `pin`. */
static unsigned run(struct zx_pcie *zx, bool reference, unsigned pin, int rc[3])
{
	reset_block();
	if (reference) {
		rc[0] = zx_gpio_out(zx, pin, 0);
		rc[1] = old_held_gate(zx, pin);
		rc[2] = zx_gpio_out(zx, pin, 1);
	} else {
		rc[0] = zx_perst_set(zx, true);
		rc[1] = zx_perst_get(zx) != 1 ? -EIO : 0;
		rc[2] = zx_perst_set(zx, false);
	}
	return ntrace;
}
static void check_traces(unsigned pin, bool active_low)
{
	static struct access ref[8192];
	struct gpio_desc desc = { pin, active_low };
	struct zx_pcie old = { .gpio = block }, legacy = { .gpio = block, .perst_pin = pin };
	struct zx_pcie gpiod = { .perst = &desc };
	unsigned lags[] = { 0, 1, 3 }, cases = 0;

	for (unsigned l = 0; l < 3; l++)
		for (int s = 0; s < 2; s++) {
			int want[3], got[3];
			unsigned n;

			lag = lags[l]; stuck = s;
			n = run(&old, true, pin, want);
			memcpy(ref, trace, n * sizeof(*ref));
			assert(want[0] == (s ? -ETIMEDOUT : 0));
			struct zx_pcie *paths[] = { &legacy, &gpiod };
			for (unsigned k = 0; k < 2; k++) {
				assert(run(paths[k], false, pin, got) == n);
				assert(!memcmp(trace, ref, n * sizeof(*ref)));
				assert(!memcmp(got, want, sizeof(want)));
			}
			cases++;
		}
	printf("traces pin %u identical in %u cases\n", pin, cases);
}
int main(int argc, char **argv)
{
	assert(argc == 2);
	if (!strcmp(argv[1], "dt")) {
		check_map_crm(0, false); check_map_crm(1, false);
		check_get_perst(0, 0); check_get_perst(1, 1);
	} else if (!strcmp(argv[1], "fallback")) {
		check_map_crm(2, true);			/* a pcie node without crm0..2 */
		check_get_perst(2, 0); check_get_perst(2, 1);
	} else if (!strcmp(argv[1], "errors")) {
		struct platform_device p = { .node = 3 };	/* crm1 too small */
		struct zx_pcie zx = { 0 };
		struct device_node np = { 0 };
		struct zx_pcie port = { .pci = { .dev = &dev } };

		nmapped = fail_map = 0;
		assert(zx_pcie_map_crm(&p, &zx) == -EINVAL && nmapped == 1);
		p.node = 0; nmapped = 0; fail_map = 2;
		assert(zx_pcie_map_crm(&p, &zx) == -ENOMEM && nmapped == 2);
		lookup_error = -EPROBE_DEFER; nmapped = 0; fail_map = 0;
		assert(zx_pcie_get_perst(&port, &np) == -EPROBE_DEFER);
		assert(!port.perst && !port.gpio && !nmapped);
		lookup_error = 0; np.node = 2; fail_map = 1;
		assert(zx_pcie_get_perst(&port, &np) == -ENOMEM && !port.gpio);
		printf("errors ok\n");
	} else if (!strcmp(argv[1], "traces")) {
		for (int node = 0; node < 2; node++)
			check_traces(perst_pin[node], perst_flags[node] & 1);
	} else {
		return 2;
	}
	return 0;
}
'''


def dt_tables(dtb):
    """C tables for platform_get_resource_byname and the PERST# lookup.

    Nodes 0/1 are the board's two pcie nodes, 2 is a pcie node as the old DTS
    had it (no crm entries, no reset-gpios), 3 is node 0 with crm1 shrunk.
    """
    nodes, pins, flags, present = [], [], [], []
    gpio_phandle = fx.fdtget(dtb, GPIO_NODE, 'phandle', 'u')[0]
    for port in (0, 1):
        node = NODES[port]
        names = fx.fdtget(dtb, node, 'reg-names', 's')
        regs = fx.reg_pairs(dtb, node)
        assert len(names) == len(regs), node
        nodes.append(list(zip(names, regs)))
        cells = fx.fdtget(dtb, node, 'reset-gpios', 'u')
        assert cells[0] == gpio_phandle, (node, cells)
        pins.append(cells[1]); flags.append(cells[2]); present.append(1)
    nodes.append([(n, r) for n, r in nodes[0] if not n.startswith('crm')])
    pins.append(0); flags.append(0); present.append(0)
    nodes.append([(n, (r[0], 0x10) if n == 'crm1' else r) for n, r in nodes[0]])
    pins.append(0); flags.append(0); present.append(0)
    rows = ',\n'.join('\t{ ' + ', '.join(f'{{ "{n}", {b:#x}, {s:#x} }}' for n, (b, s) in node) + ' }'
                      for node in nodes)
    return '\n'.join([
        f'static const struct dtres res[4][8] = {{\n{rows}\n}};',
        'static const unsigned nres[4] = { ' + ', '.join(str(len(n)) for n in nodes) + ' };',
        'static const bool has_perst[4] = { ' + ', '.join(map(str, present)) + ' };',
        'static const unsigned perst_pin[4] = { ' + ', '.join(map(str, pins)) + ' };',
        'static const unsigned perst_flags[4] = { ' + ', '.join(map(str, flags)) + ' };',
    ])


def driver_constant(text, name):
    value = exact_define(text, name).split(None, 2)[2].split('/*')[0].strip()
    return int(value, 0)


@unittest.skipUnless(fx.dts_tools_available(), 'requires the unpacked kernel tree, dtc and fdtget')
class PcieDtResourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='pcie-dt-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.out = Path(cls.tmp.name)
        cls.dtb, cls.warnings = {}, {}
        for name in fx.DTS_NAMES:
            cls.dtb[name], cls.warnings[name] = fx.compile_dts(name, cls.out)
        cls.text = fx.PCIE_SOURCE.read_text()
        gpio = fx.GPIO_SOURCE.read_text()
        defines = '\n'.join(exact_define(cls.text, n) for n in (
            'ZX_CRM0_PHYS', 'ZX_CRM1_PHYS', 'ZX_CRM2_PHYS', 'ZX_GPIO_PHYS',
            'ZX_PERST_GPIO0', 'ZX_PERST_GPIO1', 'ZX_GPIO_IN', 'ZX_GPIO_SET', 'ZX_GPIO_CLR'))
        bank = re.search(r'^#define ZX_GPIO_BANK\(g\)[^\n]*', cls.text, re.M).group()
        gpio_defines = '\n'.join(exact_define(gpio, n) for n in ('ZX_GPIO_BANK_STRIDE',))
        code = '\n'.join([
            HEADER.replace('@DT@', dt_tables(cls.dtb[fx.BASE_DTS])), IOPOLL, defines, bank,
            gpio_defines, exact_struct(gpio, 'zx_gpio'),
            '#define gpiochip_get_data(gc) ((struct zx_gpio *)(gc))',
            *(function(gpio, n) for n in ('zx_gpio_reg', 'zx_gpio_get', 'zx_gpio_set')),
            GPIOLIB, exact_struct(cls.text, 'zx_pcie'),
            *(function(cls.text, n) for n in ('zx_perst_get', 'zx_perst_set', 'zx_map',
                                               'zx_pcie_map_crm', 'zx_pcie_get_perst')),
            OLD_GPIO_OUT, CASES])
        src, cls.exe = cls.out / 'pcie_dt.c', cls.out / 'pcie_dt'
        src.write_text(code)
        built = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                '-Wno-sign-compare', '-Wno-unused-function', str(src),
                                '-o', str(cls.exe)], capture_output=True, text=True)
        if built.returncode:
            raise AssertionError(built.stderr)

    def run_case(self, case):
        run = subprocess.run([str(self.exe), case], capture_output=True, text=True, timeout=30)
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return run.stdout

    def test_driver_fallbacks_are_the_old_constants(self):
        for key in ('crm0', 'crm1', 'crm2'):
            self.assertEqual(driver_constant(self.text, f'ZX_{key.upper()}_PHYS'), OLD[key])
        self.assertEqual(driver_constant(self.text, 'ZX_GPIO_PHYS'), OLD['gpio'])
        self.assertEqual(driver_constant(self.text, 'ZX_PERST_GPIO0'), OLD['perst'][0])
        self.assertEqual(driver_constant(self.text, 'ZX_PERST_GPIO1'), OLD['perst'][1])

    def test_every_board_dtb_describes_the_old_resources(self):
        for name, dtb in self.dtb.items():
            self.assertNotRegex(self.warnings[name], r'pcie@|gpio@', name)
            phandle = fx.fdtget(dtb, GPIO_NODE, 'phandle', 'u')[0]
            for port, node in NODES.items():
                with self.subTest(dtb=name, port=port):
                    names = fx.fdtget(dtb, node, 'reg-names', 's')
                    regs = dict(zip(names, fx.reg_pairs(dtb, node)))
                    self.assertEqual(names, ['dbi', 'config', 'app', 'crm0', 'crm1', 'crm2'])
                    for key in ('crm0', 'crm1', 'crm2'):
                        self.assertEqual(regs[key], (OLD[key], 0x1000))
                    # Unchanged entries, still matching the driver's port check.
                    # The port index now follows from dbi (test_pcie_dt_port.py).
                    self.assertEqual(regs['dbi'], (0x0f000000 + port * 0x100000, 0x4000))
                    self.assertEqual(regs['app'][0], 0x09500000 + port * 0x100000)
                    self.assertIsNone(fx.fdtget(dtb, node, 'zte,pcie-port', 'u'))
                    self.assertEqual(fx.fdtget(dtb, node, 'reset-gpios', 'u'),
                                     [phandle, OLD['perst'][port], GPIO_ACTIVE_LOW])

    def test_actual_resolution_of_the_board_dt_selects_the_old_resources(self):
        out = self.run_case('dt').splitlines()
        crm = [f'crm{i} {OLD[f"crm{i}"]:#x} 0x1000' for i in range(3)]
        self.assertEqual(out, crm + crm + ['perst 0 desc 53 1', 'perst 1 desc 55 1'])

    def test_actual_fallback_without_the_properties_is_the_old_behaviour(self):
        out = self.run_case('fallback').splitlines()
        self.assertEqual(out, [f'crm{i} {OLD[f"crm{i}"]:#x} 0x1000' for i in range(3)] +
                         [f'perst 0 pin 53 block {OLD["gpio"]:#x} 0x1000',
                          f'perst 1 pin 55 block {OLD["gpio"]:#x} 0x1000'])

    def test_actual_error_paths(self):
        self.assertEqual(self.run_case('errors').strip(), 'errors ok')

    def test_perst_register_traffic_is_identical_to_the_old_helper(self):
        out = self.run_case('traces').splitlines()
        self.assertEqual(out, ['traces pin 53 identical in 6 cases',
                               'traces pin 55 identical in 6 cases'])

    def test_iopoll_model_matches_the_pinned_kernel(self):
        tree = fx.kernel_tree()
        header = (tree / 'include/linux/iopoll.h').read_text()
        start = header.index('#define read_poll_timeout_atomic(')
        end = header.index('})', start) + 2
        model = IOPOLL[IOPOLL.index('#define read_poll_timeout_atomic('):]
        self.assertEqual(tokens(header[start:end]), tokens(model[:model.index('})') + 2]))

    def test_no_hard_coded_resource_outside_the_fallbacks(self):
        probe = function(self.text, 'zx_pcie_probe')
        prepare = function(self.text, 'zx_pcie_prepare_pair')
        for name in ('ZX_CRM0_PHYS', 'ZX_CRM1_PHYS', 'ZX_CRM2_PHYS', 'ZX_GPIO_PHYS',
                     'ZX_PERST_GPIO0', 'ZX_PERST_GPIO1'):
            self.assertNotIn(name, tokens(probe) + tokens(prepare))
        self.assertEqual(tokens(self.text).count('ZX_GPIO_PHYS'), 2)   # define + fallback
        self.assertIn('ZX_GPIO_PHYS', tokens(function(self.text, 'zx_pcie_get_perst')))


@unittest.skipUnless(fx.cross_tools(), 'requires the pinned kernel tree and toolchain')
class PcieCrossCompileTests(unittest.TestCase):
    def test_driver_builds_against_the_pinned_6_6_151_headers(self):
        tree, _ = fx.cross_tools()
        record = 'drivers/pci/controller/dwc/.pcie-zx279128.o.cmd'
        if not (tree / record).exists():
            self.skipTest('kernel tree has no recorded PCIe compile')
        with tempfile.TemporaryDirectory() as out:
            run = fx.cross_compile(fx.PCIE_SOURCE, record, out,
                                   ['-I', str(tree / 'drivers/pci/controller/dwc')])
            self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
