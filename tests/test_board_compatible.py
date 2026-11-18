"""The board compatible and every consumer of /tmp/sysinfo/board_name.

Adding a board-level compatible is an ABI change on this port: OpenWrt derives
board_name from the *first* root compatible, and five separate files key off
it. If any of them still compares against the SoC string alone, the unit comes
up with no network configuration or no LEDs - a soft brick that is only
recoverable through the stock fallback.

So the rule this file enforces is: the board string and the SoC string are both
accepted, everywhere, and the DTS names the board first. Either order then
works, and an image built before the change installs over one built after it.
"""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
FILES = ROOT / 'files/target/linux/armsr'
DTS = FILES / 'files-6.6/arch/arm/boot/dts/zte/zx279128s-zte-h199a.dts'
BASEFILES = FILES / 'base-files'
IMAGE_MAKEFILE = FILES / 'image/Makefile'
MACH = FILES / 'files-6.6/arch/arm/mach-zx279128/platform.c'

BOARD = 'zte,zxhn-h199a'
SOC = 'zte,zx279128s'

# Every file that branches on board_name, and how.
CONSUMERS = {
    'etc/board.d/01_leds': 'case',
    'etc/board.d/02_network': 'case',
    'etc/hotplug.d/button/50-h199a-wps-led': 'case',
    'etc/hotplug.d/ieee80211/10-zx-wifi-leds': 'case',
    'lib/upgrade/platform.sh': 'list',
}


class BoardCompatibleTests(unittest.TestCase):
    def test_the_dts_names_the_board_before_the_soc(self):
        root = DTS.read_text()
        m = re.search(r'^\tcompatible = "([^"]+)", "([^"]+)", "([^"]+)";', root, re.M)
        self.assertIsNotNone(m, 'root compatible not found')
        self.assertEqual(m.groups(), (BOARD, SOC, 'zte,zx279128'))

    def test_every_board_name_consumer_accepts_both_names(self):
        for rel, kind in CONSUMERS.items():
            with self.subTest(consumer=rel):
                text = (BASEFILES / rel).read_text()
                self.assertIn('board_name', text)
                if kind == 'case':
                    # a case pattern, or a case used as the equality check
                    self.assertIn(f'{SOC}|{BOARD}', text,
                                  f'{rel} does not accept both board names')
                else:
                    self.assertRegex(text, r'H199A_SUPPORTED_BOARD="[^"]*' + re.escape(BOARD) +
                                     r'[^"]*"')
                    self.assertRegex(text, r'H199A_SUPPORTED_BOARD="[^"]*' + re.escape(SOC) +
                                     r'[^"]*"')

    def test_the_upgrade_gate_takes_a_list_not_one_string(self):
        """platform.sh matches ` $board ` against ` $SUPPORTED `, so it must be a
        list; a single string would silently reject the other name."""
        text = (BASEFILES / 'lib/upgrade/platform.sh').read_text()
        value = re.search(r'^H199A_SUPPORTED_BOARD="([^"]*)"', text, re.M).group(1)
        self.assertEqual(sorted(value.split()), sorted([BOARD, SOC]))
        self.assertIn('case " $H199A_SUPPORTED_BOARD " in', text)

    def test_image_metadata_lists_both_devices(self):
        text = IMAGE_MAKEFILE.read_text()
        value = re.search(r'^SUPPORTED_DEVICES := (.+)$', text, re.M).group(1)
        self.assertEqual(sorted(value.split()), sorted([BOARD, SOC]))

    def test_the_machine_still_matches_the_soc(self):
        """DT_MACHINE_START matches if ANY root compatible is listed, so the
        machine keeps matching on the SoC and does not need the board string.
        Adding it there would make the machine refuse a DT that names only the
        SoC."""
        text = MACH.read_text()
        self.assertIn(f'"{SOC}"', text)
        self.assertNotIn(f'"{BOARD}"', text)

    def test_no_consumer_compares_against_the_soc_alone(self):
        """The regression this file exists for: an exact equality check on one
        name breaks the moment the DTS order changes."""
        for rel in CONSUMERS:
            with self.subTest(consumer=rel):
                text = (BASEFILES / rel).read_text()
                self.assertNotIn(f'[ "$(board_name)" = "{SOC}" ]', text)
                self.assertNotRegex(text, r'case "\$\(board_name\)" in\s*\n\s*' +
                                    re.escape(SOC) + r'\)\s*\n')


if __name__ == '__main__':
    unittest.main()
