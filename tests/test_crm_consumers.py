"""MDIO and GPIO take their clocks from the CRM provider without changing behaviour.

The real probe functions of mdio-zx279128.c and gpio-zx279128.c are compiled
verbatim against boundary stubs:

  - the clocks are requested by the names the DTS gives (MDIO "pclk" and
    "wclk", GPIO unnamed), optional and enabled;
  - a provider that has not probed yet makes probe defer before the bus or
    chip is registered, with no register access;
  - a device tree without clocks (the clock API's optional NULL) behaves
    exactly as before: same registrations, same register access;
  - the only thing a successful probe adds is the two (one) enabled clocks.

What the clock framework does with an enable on a CLK_IS_CRITICAL gate - a
read-modify-write that sets a bit already set - is covered in
test_crm_clocks.py; here no clock register is reachable at all.
"""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_tx_origin_r204 import exact_struct, function

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / 'files/target/linux/armsr/files-6.6'
MDIO = FILES / 'drivers/net/mdio/mdio-zx279128.c'
GPIO = FILES / 'drivers/gpio/gpio-zx279128.c'

COMMON = r'''
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
typedef uint32_t u32;
typedef uint16_t u16;
#define __iomem
#define BIT(n) (1U << (n))
#define GFP_KERNEL 0
#define EPROBE_DEFER 517
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define THIS_MODULE ((struct module *)0)
#define PRINTF(f, a) __attribute__((format(printf, f, a)))
struct module;
struct device_node { int unused; };
struct device { struct device_node *of_node; const char *name; };
struct platform_device { struct device dev; };
struct clk { const char *id; };
static const char *dev_name(const struct device *d) { return d->name; }
static struct platform_device pdev = { { NULL, "dev" } };
static u32 window[0x100];
static unsigned maps, clk_gets, registered, errors, defer_at, nclk;
static bool no_clocks;
static struct clk clocks[4];
static const char *got[4];
static void *devm_platform_ioremap_resource(struct platform_device *p, unsigned i) {
 assert(p == &pdev && i == 0 && !registered); maps++; return window;
}
/* optional + enabled: NULL when the node has no clocks, the clock otherwise,
 * -EPROBE_DEFER when the provider has not registered yet. */
static struct clk *devm_clk_get_optional_enabled(struct device *d, const char *id) {
 assert(d == &pdev.dev && maps == 1 && !registered);
 clk_gets++;
 if (clk_gets == defer_at) return ERR_PTR(-EPROBE_DEFER);
 if (no_clocks) return NULL;
 got[nclk] = id; clocks[nclk].id = id;
 return &clocks[nclk++];
}
static PRINTF(3, 4) int dev_err_probe(const struct device *d, int err, const char *fmt, ...) { errors++; return err; }
static PRINTF(2, 3) void dev_info(const struct device *d, const char *fmt, ...) { }
static void reset_bench(void) {
 maps = clk_gets = registered = errors = defer_at = nclk = 0; no_clocks = false;
 memset(got, 0, sizeof(got));
}
'''

MDIO_MODEL = r'''
#define MII_BUS_ID_SIZE 61
struct mii_bus { const char *name; char id[MII_BUS_ID_SIZE];
 int (*read)(struct mii_bus *, int, int); int (*write)(struct mii_bus *, int, int, u16);
 struct device *parent; void *priv; };
static struct mii_bus the_bus; static char priv[256];
static struct mii_bus *devm_mdiobus_alloc_size(struct device *d, int size) {
 assert(d == &pdev.dev && size <= (int)sizeof(priv));
 memset(&the_bus, 0, sizeof(the_bus)); the_bus.priv = priv; return &the_bus;
}
static int of_mdiobus_register(struct mii_bus *b, struct device_node *np) {
 assert(b == &the_bus && b->read && b->write && b->parent == &pdev.dev); registered++; return 0;
}
static void platform_set_drvdata(struct platform_device *p, void *d) { }
static int zx_mdio_read(struct mii_bus *b, int phy, int reg) { return 0; }
static int zx_mdio_write(struct mii_bus *b, int phy, int reg, u16 v) { return 0; }
static void zx_mdio_scan_after_probe(void) { }
'''

GPIO_MODEL = r'''
typedef struct { int held; } spinlock_t;
#define spin_lock_init(l) ((l)->held = 0)
struct gpio_chip { const char *label; struct device *parent; struct module *owner; int base;
 unsigned ngpio; bool can_sleep;
 int (*get_direction)(struct gpio_chip *, unsigned);
 int (*direction_input)(struct gpio_chip *, unsigned);
 int (*direction_output)(struct gpio_chip *, unsigned, int);
 int (*get)(struct gpio_chip *, unsigned);
 void (*set)(struct gpio_chip *, unsigned, int); };
static void *devm_kzalloc(struct device *d, size_t n, int f) { return calloc(1, n); }
static int devm_gpiochip_add_data(struct device *d, struct gpio_chip *gc, void *data) {
 assert(d == &pdev.dev && gc->ngpio == 96 && gc->get && gc->set); registered++; return 0;
}
static int zx_gpio_get_direction(struct gpio_chip *c, unsigned o) { return 0; }
static int zx_gpio_direction_input(struct gpio_chip *c, unsigned o) { return 0; }
static int zx_gpio_direction_output(struct gpio_chip *c, unsigned o, int v) { return 0; }
static int zx_gpio_get(struct gpio_chip *c, unsigned o) { return 0; }
static void zx_gpio_set(struct gpio_chip *c, unsigned o, int v) { }
'''

CASES = r'''
int main(void) {
 reset_bench();
 assert(PROBE(&pdev) == 0 && registered == 1 && maps == 1 && clk_gets == NCLK && nclk == NCLK && !errors);
 for (unsigned i = 0; i < NCLK; i++)
  printf("CLK %s\n", got[i] ? got[i] : "(null)");
 /* A device tree without clocks: same probe, no clocks taken. */
 reset_bench(); no_clocks = true;
 assert(PROBE(&pdev) == 0 && registered == 1 && maps == 1 && clk_gets == NCLK && !nclk);
 /* Provider not ready: defer before registering, for each clock. */
 for (unsigned d = 1; d <= NCLK; d++) {
  reset_bench(); defer_at = d;
  assert(PROBE(&pdev) == -EPROBE_DEFER && !registered && errors == 1);
 }
 return 0;
}
'''


def run_c(test, code):
    with tempfile.TemporaryDirectory() as tmp:
        src, exe = Path(tmp) / 'c.c', Path(tmp) / 'c'
        src.write_text(code)
        built = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                                '-Wno-unused-parameter', '-Wno-unused-function', str(src),
                                '-o', str(exe)], capture_output=True, text=True)
        test.assertEqual(built.returncode, 0, built.stderr)
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=20)
        test.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return [l.split(None, 1)[1] for l in run.stdout.splitlines() if l.startswith('CLK ')]


def probe_without_debug_scan(text, name):
    """The MDIO probe ends with a bench-only PHY scan and register dump that
    maps other blocks by address; it runs after registration and is cut at
    the registration log line, which the test requires to be present."""
    body = function(text, name)
    if name != 'zx_mdio_probe':
        return body
    marker = '\tdev_info(dev, "ZX279128S MDIO bus registered\\n");\n'
    assert body.count(marker) == 1, 'MDIO probe registration line changed'
    return body[:body.index(marker) + len(marker)] + '\treturn 0;\n}\n'


class CrmConsumerTests(unittest.TestCase):
    def test_mdio_takes_pclk_and_wclk_before_registering(self):
        text = MDIO.read_text()
        code = (COMMON + MDIO_MODEL + exact_struct(text, 'zx_mdio') +
                probe_without_debug_scan(text, 'zx_mdio_probe') +
                '#define PROBE zx_mdio_probe\n#define NCLK 2\n' + CASES)
        self.assertEqual(run_c(self, code), ['pclk', 'wclk'])

    def test_gpio_takes_one_unnamed_clock_before_registering(self):
        text = GPIO.read_text()
        defines = '\n'.join(l for l in text.splitlines() if re.match(r'#define ZX_GPIO_NGPIO\s', l))
        code = (COMMON + GPIO_MODEL + defines + '\n' + exact_struct(text, 'zx_gpio') +
                function(text, 'zx_gpio_probe') + '\n' +
                '#define PROBE zx_gpio_probe\n#define NCLK 1\n' + CASES)
        self.assertEqual(run_c(self, code), ['(null)'])

    def test_consumers_never_disable_or_set_a_rate(self):
        for path in (MDIO, GPIO, FILES / 'drivers/spi/spi-zx279128.c'):
            code = re.sub(r'/\*.*?\*/', '', path.read_text(), flags=re.S)
            with self.subTest(file=path.name):
                for forbidden in ('clk_disable', 'clk_unprepare', 'clk_set_rate',
                                  'clk_set_parent', 'clk_disable_unprepare'):
                    self.assertNotIn(forbidden, code)


if __name__ == '__main__':
    unittest.main()
