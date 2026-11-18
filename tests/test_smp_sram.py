"""The SMP trampoline SRAM, as mmio-sram plus a SoC child.

platsmp.c maps this region and writes three words into it - the trampoline, the
physical address of secondary_startup at +0x4 and the pen-release address at
+0x8 - then wakes CPU1. If the address it maps is not exactly 0x200800, the
secondary CPU starts from the wrong place and the board comes up single-core.

So the invariant is an address, not a shape: whatever the device tree says, the
node the driver finds must resolve to the same physical window it mapped before
the conversion. That is what these tests check, against a DTS compiled with the
kernel's own dtc.
"""
from pathlib import Path
import re
import unittest

import dt_fixture as fx

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / 'files/target/linux/armsr/files-6.6'
PLATSMP = FILES / 'arch/arm/mach-zx279128/platsmp.c'
SRAM_YAML = ROOT / 'docs/upstream/bindings/sram/zte,zx279128s-smp-sram.yaml'

# The window the driver mapped before the conversion, and the three offsets it
# writes: trampoline at 0, secondary_startup at +4, pen_release at +8.
WINDOW_BASE, WINDOW_SIZE = 0x200800, 0x1000
SRAM_NODE = '/soc/sram@200800'
CHILD_NODE = SRAM_NODE + '/smp-sram@0'


@unittest.skipUnless(fx.dts_tools_available(), 'needs the kernel tree, dtc and fdtget')
class SmpSramTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = fx.tempfile.TemporaryDirectory() \
            if hasattr(fx, 'tempfile') else None
        import tempfile
        cls.directory = tempfile.TemporaryDirectory()
        cls.dtb, cls.stderr = fx.compile_dts(fx.BASE_DTS, cls.directory.name)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_the_controller_is_mmio_sram(self):
        self.assertEqual(fx.fdtget(self.dtb, SRAM_NODE, 'compatible', 's'), ['mmio-sram'])

    def test_the_child_carries_the_soc_compatible(self):
        self.assertEqual(fx.fdtget(self.dtb, CHILD_NODE, 'compatible', 's'),
                         ['zte,zx279128s-smp-sram'])

    def test_the_child_resolves_to_the_window_the_driver_maps(self):
        """The child's reg goes through the parent's ranges; the result is the
        physical window, and it must not have moved."""
        parent = fx.reg_pairs(self.dtb, SRAM_NODE)[0]
        child = fx.reg_pairs(self.dtb, CHILD_NODE)[0]
        ranges = fx.fdtget(self.dtb, SRAM_NODE, 'ranges')
        self.assertEqual(len(ranges), 3, 'expected one <child parent size> triple')
        child_base, parent_base, window = ranges
        self.assertEqual(parent, (WINDOW_BASE, WINDOW_SIZE))
        self.assertEqual((child_base, parent_base, window), (0, WINDOW_BASE, WINDOW_SIZE))
        resolved = parent_base + child[0] - child_base
        self.assertEqual((resolved, child[1]), (WINDOW_BASE, WINDOW_SIZE))

    def test_the_driver_looks_the_child_up_and_not_a_controller(self):
        text = PLATSMP.read_text()
        self.assertIn('of_find_compatible_node(NULL, NULL, "zte,zx279128s-smp-sram")', text)
        # the three writes the trampoline depends on, at their fixed offsets
        self.assertIn('memcpy_toio(iram, zx_secondary_trampoline, len)', text)
        self.assertIn('writel_relaxed(__pa_symbol(secondary_startup), iram + 4)', text)
        self.assertIn('writel_relaxed(__pa(&zx_pen_release), iram + 8)', text)
        # of_iomap on the child, so the parent's ranges are what translate it
        self.assertIn('iram = of_iomap(np, 0)', text)

    def test_the_binding_documents_the_child_not_a_controller(self):
        text = SRAM_YAML.read_text()
        self.assertIn('compatible:\n    const: zte,zx279128s-smp-sram', text)
        self.assertIn('additionalProperties: false', text)
        # and its example is the shape the DTS actually uses
        self.assertIn('compatible = "mmio-sram"', text)
        self.assertIn('compatible = "zte,zx279128s-smp-sram"', text)

    def test_the_old_generic_compatible_is_gone_from_the_dts(self):
        """'zte,iram' named no SoC and had no binding; it must not come back."""
        dts = (FILES / 'arch/arm/boot/dts/zte/zx279128s-zte-h199a.dts').read_text()
        self.assertNotRegex(dts, r'compatible\s*=\s*"zte,iram"')


if __name__ == '__main__':
    unittest.main()
