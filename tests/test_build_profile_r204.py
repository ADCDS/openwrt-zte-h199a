#!/usr/bin/env python3
"""Pure R204 config/control provenance guard tests; no build or hardware I/O."""
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
FORCED = 'CONFIG_CMDLINE="console=ttyAMA0,115200n8 ro init=/bin/sh zx279128_eth.force_dp_init=1"\nCONFIG_CMDLINE_FORCE=y\nCONFIG_INET=y\n'
REFERENCE = '/* original R203 control */\n'

@needs_artifacts()
class R204ProfileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.wrapper = (ROOT / 'tools/build-r199-diagnostic.sh').read_text()
        match = re.search(r'python3 - "\$ROOT" "\$ROUND" <<\'PY\'\n(.*?)\nPY\n', cls.wrapper, re.S)
        assert match, 'actual pre-build guard not found'
        cls.guard = match.group(1)

    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.put(CONFIG, FORCED)
        self.put('artifacts/r204/reference-driver.c', REFERENCE)
        hashes = {CONFIG: hashlib.sha256(FORCED.encode()).hexdigest(),
                  SOURCE: hashlib.sha256(REFERENCE.encode()).hexdigest()}
        self.put('artifacts/r203/manifest.json', json.dumps({'sha256': hashes}))

    def put(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def check(self, accepted):
        result = subprocess.run([sys.executable, '-', str(self.root), 'r204'],
                                input=self.guard, text=True, capture_output=True)
        self.assertEqual(result.returncode == 0, accepted, result.stderr)

    def test_matching_control_profile_accepted(self):
        self.check(True)

    def test_unforced_config_rejected(self):
        self.put(CONFIG, FORCED.replace(' zx279128_eth.force_dp_init=1', ''))
        self.check(False)

    def test_unrelated_config_drift_rejected(self):
        self.put(CONFIG, FORCED.replace('CONFIG_INET=y', 'CONFIG_INET=n'))
        self.check(False)

    def test_control_source_drift_rejected(self):
        self.put('artifacts/r204/reference-driver.c', REFERENCE + '/* changed */\n')
        self.check(False)

    def test_missing_control_manifest_rejected(self):
        (self.root / 'artifacts/r203/manifest.json').unlink()
        self.check(False)

    def test_actual_c_restoration_tests_precede_build(self):
        self.assertLess(self.wrapper.index('python3 "$ROOT/tests/test_tx_origin_r204.py"'),
                        self.wrapper.index('make -C "$K"'))
        self.assertLess(self.wrapper.index('python3 "$ROOT/tests/test_build_profile_r204.py"'),
                        self.wrapper.index('make -C "$K"'))

if __name__ == '__main__':
    unittest.main()
