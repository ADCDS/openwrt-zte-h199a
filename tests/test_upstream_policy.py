"""Board policy must not be compiled into a shipped kernel by accident.

Upstream will not take this port with bench scaffolding enabled, and more
importantly a shipped image should not carry it: the PCIe probe test replays a
reverse-engineered PHY sequence at late_initcall, the Ethernet debug option
exposes /proc/zx_eth_poke (arbitrary physical read-modify-write), and the PP
table code writes into tables the live datapath walks.

Each of those is individually gated and off in a production profile. This test
is the list, in one place, of what a shipped config may not enable - so that
"it was on because a bring-up build left it on" cannot happen quietly. That is
exactly how CONFIG_ZX279128_PCIE_PROBE_TEST=y sat in the shipped config while
its own Kconfig help said "Say N for a production image".
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / 'files/target/linux/armsr/config-6.6'

# symbol -> why it must never be on in a shipped image
MUST_NOT_SHIP = {
    'CONFIG_ZX279128_ETH_DEBUG':
        '/proc/zx_eth_poke is arbitrary physical read-modify-write',
    'CONFIG_ZX279128_PP_TABLES':
        'not hardware-qualified; writes tables the datapath walks',
    'CONFIG_ZX279128_PP_FLOW_TEST':
        'the single-flow write path',
    'CONFIG_ZX279128_PP_OFFLOAD':
        'the hardware flow-offload path; the hardware match is not qualified',
    'CONFIG_ZX279128_PCIE_PROBE_TEST':
        'bring-up scaffolding; its own Kconfig help says to say N',
}


class ShippedConfigPolicyTests(unittest.TestCase):
    def test_no_bench_symbol_is_enabled(self):
        text = CONFIG.read_text()
        for symbol, why in MUST_NOT_SHIP.items():
            with self.subTest(symbol=symbol):
                self.assertNotRegex(
                    text, rf'^{re.escape(symbol)}=y\s*$',
                    f'{symbol} is enabled in the shipped config: {why}')

    def test_each_is_explicitly_disabled_rather_than_absent(self):
        """An absent symbol is not the same as a disabled one: kconfig would
        pick its default, which for these is 'n' only by luck of the help
        text. State it."""
        text = CONFIG.read_text()
        for symbol in MUST_NOT_SHIP:
            with self.subTest(symbol=symbol):
                self.assertIn(f'# {symbol} is not set', text)

    def test_the_debug_kconfig_help_still_warns(self):
        """If the help text ever stops saying this is unsafe, the policy above
        loses its justification and should be revisited."""
        kconfig = (ROOT / 'files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/Kconfig').read_text()
        self.assertIn('SECURITY: zx_eth_poke gives root arbitrary physical-address', kconfig)


if __name__ == '__main__':
    unittest.main()
