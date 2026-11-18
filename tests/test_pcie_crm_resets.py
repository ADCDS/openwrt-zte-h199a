"""PCIe resets through the CRM reset provider: same register traffic as before.

pcie-zx279128.c used to clear and set its bit of CRM1+0x74 itself. It now
takes the port's line from `resets` and calls reset_control_assert() /
reset_control_deassert(), which land in the zte,zx279128s-crm provider's
ops. The domain-enable sequence is what makes the PCIe block (and both
radios behind it) reachable at all, so this compiles, verbatim:

  - the previous driver's zx_crm_writel() and zx_pcie_domain_enable(), taken
    from git (BASELINE);
  - the current driver's zx_crm_writel(), zx_pcie_core_reset() and
    zx_pcie_domain_enable(), with the reset line resolved to the current
    CRM driver's reset ops (struct zx_crm, zx_crm_reset_update() and the
    assert/deassert ops, verbatim), through a model of the 6.6 reset core's
    exclusive assert/deassert path;
  - the current driver again with no `resets` (the fallback);

runs both ports against one CRM/glue register model with the measured boot
values, and requires the three traces - every read, every write with its
value, every delay, in order - to be identical.

The blind `writel(0x3f, CRM1+0x74)` tail is deliberately not converted; the
test checks that it is still there, unchanged, and still a raw write.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_tx_origin_r204 import exact_struct, function, tokens

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / 'files/target/linux/armsr/files-6.6'
PCIE = FILES / 'drivers/pci/controller/dwc/pcie-zx279128.c'
CRM = FILES / 'drivers/clk/clk-zx279128-crm.c'
RST_HEADER = FILES / 'include/dt-bindings/reset/zte,zx279128s-crm.h'
BASELINE = 'd5ba63b'   # last commit with the direct CRM1+0x74 bit writes
PCIE_PATH = 'files/target/linux/armsr/files-6.6/drivers/pci/controller/dwc/pcie-zx279128.c'

PRELUDE = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
#define __iomem
#define BIT(n) (1U << (n))
#define GENMASK(h, l) (((~0U) << (l)) & (~0U >> (31 - (h))))
#define container_of(p, t, m) ((t *)((char *)(p) - offsetof(t, m)))
#define PRINTF(f, a) __attribute__((format(printf, f, a)))
typedef struct { int held; } spinlock_t;
static int lock_depth;
#define spin_lock_irqsave(l, f) do { assert(!(l)->held); (l)->held = 1; lock_depth++; (f) = 0; } while (0)
#define spin_unlock_irqrestore(l, f) do { assert((l)->held); (l)->held = 0; lock_depth--; (void)(f); } while (0)
struct device { int unused; };
struct device_node { int unused; };
struct module;
struct gpio_desc;
struct clk_hw_onecell_data;
struct dw_pcie { struct device *dev; void *dbi_base; };

/* Register model: TOPCRM (crm0), CRM1, CRM2, and one glue block per port. */
static u32 regs[5][0x400];
static const char *const region_name[5] = { "crm0", "crm1", "crm2", "glue0", "glue1" };
static int region_of(const volatile void *p, unsigned *off) {
 for (int r = 0; r < 5; r++) {
  const char *b = (const char *)regs[r];
  if ((const char *)p >= b && (const char *)p < b + sizeof(regs[r])) {
   *off = (unsigned)((const char *)p - b);
   assert(*off % 4 == 0);
   return r;
  }
 }
 assert(!"access outside the modelled CRM and glue blocks");
 return -1;
}
static u32 readl(const volatile void *p) {
 unsigned off; int r = region_of(p, &off);
 printf("R %s+0x%03x = %08x\n", region_name[r], off, regs[r][off / 4]);
 return regs[r][off / 4];
}
static void writel(u32 v, volatile void *p) {
 unsigned off; int r = region_of(p, &off);
 printf("W %s+0x%03x = %08x\n", region_name[r], off, v);
 regs[r][off / 4] = v;
}
static void mdelay(unsigned ms) { printf("D %u\n", ms); }
static PRINTF(2, 3) void dev_info(const struct device *d, const char *fmt, ...) { printf("I\n"); }
'''

# 6.6 reset core, exclusive acquired control: assert/deassert call the ops.
RESET_CORE = r'''
struct reset_controller_dev;
struct reset_control_ops {
 int (*reset)(struct reset_controller_dev *, unsigned long);
 int (*assert)(struct reset_controller_dev *, unsigned long);
 int (*deassert)(struct reset_controller_dev *, unsigned long);
 int (*status)(struct reset_controller_dev *, unsigned long);
};
struct reset_controller_dev {
 const struct reset_control_ops *ops;
 struct module *owner;
 struct device *dev;
 struct device_node *of_node;
 int of_reset_n_cells;
 unsigned int nr_resets;
};
struct reset_control { struct reset_controller_dev *rcdev; unsigned int id; bool acquired; };
static int reset_control_assert(struct reset_control *r) {
 if (!r) return 0;
 assert(r->acquired && (r->rcdev->ops->assert));
 return (r->rcdev->ops->assert)(r->rcdev, r->id);
}
static int reset_control_deassert(struct reset_control *r) {
 if (!r) return 0;
 assert(r->acquired);
 if (!r->rcdev->ops->deassert) return 0;
 return r->rcdev->ops->deassert(r->rcdev, r->id);
}
'''

BOOT = r'''
static void boot(void) {
 memset(regs, 0, sizeof(regs));
 /* Measured before the PCIe sequence (docs/WIFI-JOURNAL.md, BRINGUP.md). */
 regs[0][0x08 / 4] = 0x10061fff;
 regs[0][0x24 / 4] = 0x10000000;
 regs[1][0x70 / 4] = 0x00002814;
 regs[1][0x74 / 4] = 0x0000001b;
 regs[2][0x0c / 4] = 0x003dbf85;
}
'''


def pcie_defines(text):
    lines = [l for l in text.splitlines()
             if re.match(r'#define\s+\s?ZX_\w+(\(\w+\))?\s', l) and not l.rstrip().endswith('\\')]
    return '\n'.join(lines) + '\n'


def run_c(test, code):
    with tempfile.TemporaryDirectory() as tmp:
        src, exe = Path(tmp) / 'p.c', Path(tmp) / 'p'
        src.write_text(code)
        built = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                '-Wno-unused-parameter', '-Wno-unused-function',
                                '-Wno-unused-macros', str(src), '-o', str(exe)],
                               capture_output=True, text=True)
        test.assertEqual(built.returncode, 0, built.stderr)
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
        test.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return run.stdout


def git_show(path, rev=BASELINE):
    run = subprocess.run(['git', '-C', str(ROOT), 'show', f'{rev}:{path}'],
                         capture_output=True, text=True)
    return run.stdout if run.returncode == 0 else None


class PcieCrmResetTrafficTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pcie = PCIE.read_text()
        cls.crm = CRM.read_text()

    def baseline_trace(self):
        old = git_show(PCIE_PATH)
        if old is None:
            self.skipTest(f'git history with {BASELINE} not available')
        self.assertNotIn('zx_pcie_core_reset', old, 'BASELINE must be the pre-conversion driver')
        code = (PRELUDE + pcie_defines(old) +
                'struct zx_pcie { struct dw_pcie pci; u32 port; void __iomem *glue, *crm0, *crm1, *crm2;'
                ' struct gpio_desc *perst; void __iomem *gpio; unsigned int perst_pin; };\n' +
                function(old, 'zx_crm_writel') + function(old, 'zx_pcie_domain_enable') + BOOT +
                MAIN.replace('@RST0@', '').replace('@RST1@', ''))
        return run_c(self, code)

    def current_trace(self, with_resets):
        crm_parts = [
            'static const u8 zx_crm_reset_bits[2] = {\n'
            + re.search(r'static const u8 zx_crm_reset_bits\[ZX_CRM_NR_RESETS\] = \{\n(.*?)\n\};',
                        self.crm, re.S).group(1) + '\n};\n',
            exact_struct(self.crm, 'zx_crm'),
            function(self.crm, 'to_zx_crm'),
            function(self.crm, 'zx_crm_reset_update'),
            function(self.crm, 'zx_crm_reset_assert'),
            function(self.crm, 'zx_crm_reset_deassert'),
            function(self.crm, 'zx_crm_reset_status'),
            re.search(r'static const struct reset_control_ops zx_crm_reset_ops = \{.*?\n\};',
                      self.crm, re.S).group(),
        ]
        crm_consts = ''.join(re.search(rf'^#define {n}\s.*$', self.crm, re.M).group() + '\n'
                             for n in ('ZX_CRM1_RST',))
        rst = RST_HEADER.read_text()
        provider = r'''
static struct zx_crm crm_dev;
static struct reset_control lines[2];
static void provider(void) {
 crm_dev.crm1 = regs[1];
 crm_dev.rcdev.ops = &zx_crm_reset_ops;
 crm_dev.rcdev.nr_resets = 2;
 lines[0] = (struct reset_control){ &crm_dev.rcdev, ZX_CRM_RST_PCIE0, true };
 lines[1] = (struct reset_control){ &crm_dev.rcdev, ZX_CRM_RST_PCIE1, true };
}
'''
        # The PCIe driver's own ZX_CRM1_RST is the same name as the CRM
        # driver's; both must say 0x74, so define it once.
        pdefs = pcie_defines(self.pcie)
        self.assertRegex(pdefs, r'#define ZX_CRM1_RST\s+0x74\b')
        self.assertRegex(crm_consts, r'#define ZX_CRM1_RST\s+0x74\b')
        code = (PRELUDE + RESET_CORE + rst + pdefs +
                '#define ZX_CRM_NR_RESETS 2\n'
                'struct clk_hw_onecell_data { int unused; };\n' + ''.join(crm_parts) +
                exact_struct(self.pcie, 'zx_pcie') +
                function(self.pcie, 'zx_crm_writel') + function(self.pcie, 'zx_pcie_core_reset') +
                function(self.pcie, 'zx_pcie_domain_enable') + BOOT + provider +
                MAIN.replace('@RST0@', '.rst = &lines[0],' if with_resets else '')
                    .replace('@RST1@', '.rst = &lines[1],' if with_resets else ''))
        return run_c(self, code)

    def test_resets_path_has_the_baseline_register_traffic(self):
        old = self.baseline_trace()
        new = self.current_trace(True)
        self.assertGreater(old.count('\n'), 40)
        self.assertEqual(new, old)

    def test_fallback_without_resets_has_the_baseline_register_traffic(self):
        self.assertEqual(self.current_trace(False), self.baseline_trace())

    def test_crm1_reset_writes_are_the_port_bits(self):
        trace = self.current_trace(True)
        writes = [l for l in trace.splitlines() if l.startswith('W crm1+0x074')]
        # port 0 assert (bit 0 cleared), port 0 deassert, port 1 assert
        # (bit 3 cleared), port 1 deassert - from the measured 0x1b.
        self.assertEqual(writes, ['W crm1+0x074 = 0000001a', 'W crm1+0x074 = 0000001b',
                                  'W crm1+0x074 = 00000013', 'W crm1+0x074 = 0000001b'])

    def test_the_blind_tail_write_is_left_alone(self):
        prepare = function(self.pcie, 'zx_pcie_prepare_pair')
        held = function(self.pcie, 'zx_pcie_prepare_held_perst')
        for body in (prepare, held):
            self.assertEqual(tokens(body).count('0x3f'), 1)
            self.assertIn('writel(0x3f,', body)
        old = git_show(PCIE_PATH)
        if old:
            self.assertEqual(old.count('writel(0x3f,'), self.pcie.count('writel(0x3f,'))

    def test_reset_line_is_resolved_before_any_mutation(self):
        prepare = function(self.pcie, 'zx_pcie_prepare_pair')
        get = prepare.index('of_reset_control_get_optional_exclusive(np, NULL)')
        self.assertLess(get, prepare.index('zx_prepare_state = ZX_PREPARE_FAILED;'))
        self.assertIn('reset_control_put(pair[i].rst);', prepare)
        # No direct CRM1+0x74 write in the domain sequence: only the
        # diagnostic readback of the register remains there.
        body = function(self.pcie, 'zx_pcie_domain_enable')
        self.assertEqual(re.findall(r'[^\n]*ZX_CRM1_RST[^\n]*', body),
                         ['\t\t\t readl(zx->crm1 + ZX_CRM1_RST),'])
        self.assertEqual(tokens(body).count('zx_pcie_core_reset'), 4)


MAIN = r'''
int main(void) {
 struct zx_pcie port0 = { .port = 0, @RST0@ .glue = regs[3], .crm0 = regs[0], .crm1 = regs[1], .crm2 = regs[2] };
 struct zx_pcie port1 = { .port = 1, @RST1@ .glue = regs[4], .crm0 = regs[0], .crm1 = regs[1], .crm2 = regs[2] };
#ifdef ZX_CRM_RST_PCIE0
 provider();
#endif
 boot();
 printf("port0\n");
 zx_pcie_domain_enable(&port0);
 printf("port1\n");
 zx_pcie_domain_enable(&port1);
 assert(!lock_depth);
 return 0;
}
'''


if __name__ == '__main__':
    unittest.main()
