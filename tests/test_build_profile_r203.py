#!/usr/bin/env python3
"""Pure fixture tests of the builder's actual pre-build profile guard; no hardware."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from bench_artifacts import needs_artifacts

ROOT = Path(__file__).resolve().parents[1]
CONFIG = 'openwrt/build_dir/target-arm_cortex-a9_musl_eabi/linux-armsr_armv7/linux-6.6.151/.config'
SOURCE = 'files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c'
FLAG = 'zx279128_eth.force_dp_init=1'
REFERENCE = 'CONFIG_CMDLINE="console=ttyAMA0,115200n8 ro init=/bin/sh"\nCONFIG_CMDLINE_FORCE=y\nCONFIG_INET=y\n'
FORCED = REFERENCE.replace('ro init=/bin/sh"', 'ro init=/bin/sh ' + FLAG + '"')

@needs_artifacts()
class ProfileGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        wrapper = (ROOT / 'tools/build-r199-diagnostic.sh').read_text()
        match = re.search(r'python3 - "\$ROOT" "\$ROUND" <<\'PY\'\n(.*?)\nPY\n', wrapper, re.S)
        assert match, 'actual pre-build guard not found'
        cls.guard = match.group(1)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.put(CONFIG, FORCED)
        self.put(SOURCE, '/* immutable reference driver */\n')
        self.put('artifacts/r203/reference.config', REFERENCE)
        hashes = {CONFIG: hashlib.sha256(REFERENCE.encode()).hexdigest(),
                  SOURCE: hashlib.sha256((self.root / SOURCE).read_bytes()).hexdigest()}
        self.put('artifacts/r202/manifest.json', json.dumps({'sha256': hashes}))

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def run_guard(self, label, accepted):
        result = subprocess.run([sys.executable, '-', str(self.root), label],
                                input=self.guard, text=True, capture_output=True)
        self.assertEqual(result.returncode == 0, accepted, result.stderr)

    def test_force_only_variant_accepted(self):
        self.run_guard('r203', True)

    def test_missing_force_rejected(self):
        self.put(CONFIG, REFERENCE)
        self.run_guard('r203', False)

    def test_unrelated_config_change_rejected(self):
        self.put(CONFIG, FORCED.replace('CONFIG_INET=y', 'CONFIG_INET=n'))
        self.run_guard('r203', False)

    def test_extra_parameter_rejected(self):
        self.put(CONFIG, FORCED.replace(FLAG, FLAG + ' zx279128_eth.rx_q0_seed=-1'))
        self.run_guard('r203', False)

    def test_reference_hash_drift_rejected(self):
        self.put('artifacts/r203/reference.config', REFERENCE + '# changed\n')
        self.run_guard('r203', False)

    def test_driver_drift_rejected(self):
        self.put(SOURCE, '/* another driver */\n')
        self.run_guard('r203', False)

    def test_old_labels_reject_forced_profile(self):
        for label in ('r199', 'r200', 'r201', 'r202'):
            for flag in (FLAG, 'zx279128_eth.force_dp_init=y',
                         'zx279128-eth.force_dp_init=1', 'zx279128_eth.force_dp_init'):
                with self.subTest(label=label, flag=flag):
                    self.put(CONFIG, FORCED.replace(FLAG, flag))
                    self.run_guard(label, False)

    def test_old_labels_accept_unforced_profile(self):
        self.put(CONFIG, REFERENCE)
        for label in ('r199', 'r200', 'r201', 'r202'):
            with self.subTest(label=label):
                self.run_guard(label, True)

if __name__ == '__main__':
    unittest.main()
