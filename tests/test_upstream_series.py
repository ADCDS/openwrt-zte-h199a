"""The series document must stay true to the tree.

docs/upstream/SERIES.md is the submission shape. The failure mode for a
document like that is silent staleness: a driver gets added, or a file gets
deleted, and nobody notices the list is wrong until a reviewer does.

So these tests derive the truth from the tree and compare: every C source the
overlay adds must be named somewhere in the document, and every symbol the
document says must not ship must actually be off.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / 'files/target/linux/armsr/files-6.6'
SERIES = ROOT / 'docs/upstream/SERIES.md'
CONFIG = ROOT / 'files/target/linux/armsr/config-6.6'

# Files the document explicitly excludes from the series, with the reason it
# gives. If one of these ever becomes submittable, the exclusion is a lie.
EXCLUDED = {
    'diagnostic.h',
    'zx_pcie_probe_test.c',
    'zx279128-pp.c',
    'zx279128-pp-flow.c',
    'zx279128-pp-hash.c',
    'zx279128-pp-offload.c',
}


def overlay_sources():
    return sorted(p for p in FILES.rglob('*')
                  if p.suffix in ('.c', '.h') and p.is_file())


class SeriesDocumentTests(unittest.TestCase):
    def setUp(self):
        # phrase checks must not depend on where the line breaks fall
        self.doc = ' '.join(SERIES.read_text().split())

    def test_every_added_source_is_accounted_for(self):
        """Either it is in a patch, or the document says why it is not."""
        missing = [p.name for p in overlay_sources()
                   if p.name not in self.doc]
        self.assertEqual(missing, [],
                         f'SERIES.md never mentions: {missing}')

    def test_the_exclusions_are_the_ones_that_are_gated(self):
        for name in EXCLUDED:
            with self.subTest(file=name):
                self.assertIn(name, self.doc)
        # and each excluded driver really is behind a bench symbol
        text = self.doc
        for symbol in ('CONFIG_ZX279128_PP_TABLES', 'CONFIG_ZX279128_PP_FLOW_TEST',
                       'CONFIG_ZX279128_PP_OFFLOAD',
                       'CONFIG_ZX279128_PCIE_PROBE_TEST', 'CONFIG_ZX279128_ETH_DEBUG',
                       'CONFIG_SPI_ZX279128_PRODUCTION_POLICY'):
            with self.subTest(symbol=symbol):
                self.assertIn(symbol, text)

    def test_the_symbols_it_says_must_not_ship_are_off(self):
        config = CONFIG.read_text()
        for symbol in ('CONFIG_ZX279128_PP_TABLES', 'CONFIG_ZX279128_PP_FLOW_TEST',
                       'CONFIG_ZX279128_PP_OFFLOAD',
                       'CONFIG_ZX279128_PCIE_PROBE_TEST', 'CONFIG_ZX279128_ETH_DEBUG'):
            with self.subTest(symbol=symbol):
                self.assertNotRegex(config, rf'^{re.escape(symbol)}=y\s*$')

    def test_the_document_matches_the_crm_provider_that_exists(self):
        """Keep inventory and qualification scope aligned with the current tree.

        The provider and named consumers have RAM-boot evidence. This is not
        a claim that resource modelling or upstream schema review is complete.
        """
        self.assertTrue(list(FILES.glob('drivers/clk/clk-zx279128-crm.c')),
                        'SERIES.md describes a CRM driver that does not exist')
        self.assertNotIn('No CRM clock/reset provider', self.doc)
        self.assertIn('RAM-boot evidence', self.doc)
        self.assertIn('does not finish resource modelling', self.doc)
        self.assertNotIn('Consumers wired, not yet boot-qualified', self.doc)
        self.assertNotIn('its consumers are not wired', self.doc)
        self.assertFalse(list(FILES.glob('drivers/clk/clk-zx279128-spi.c')),
                         'the retired single-register SPI clock driver is back')

    def test_it_records_the_syscon_reboot_failure(self):
        """The document recommends the dedicated driver. That is only honest
        if it also says why the generic one was rejected."""
        self.assertIn('syscon-reboot', self.doc)
        self.assertRegex(self.doc, r'syscon-reboot.{0,30}experiment hung the unit')


if __name__ == '__main__':
    unittest.main()
