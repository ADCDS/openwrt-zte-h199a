"""build.sh profile guards for the production profile; no build or hardware I/O.

Each case exits before any clone/feeds/compile step, so the suite stays offline
and fast. They lock in that the production profile is a release profile, that the
RAM deny-matrix uses PRODUCTION_QUALIFY, and that the normal/RAM profile is
unaffected.
"""
import os
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ProductionBuildGuardTests(unittest.TestCase):
    def run_build(self, **env_overrides):
        env = {'PATH': os.environ.get('PATH', '/usr/bin:/bin'), 'JOBS': '1',
               'H199A_MT7603_EEPROM': ''}
        env.update(env_overrides)
        return subprocess.run(['bash', 'build.sh'], cwd=ROOT, env=env,
                              capture_output=True, text=True, timeout=30)

    def test_production_requires_calibration(self):
        r = self.run_build(BOOT_PROFILE='production')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('production builds require H199A_MT7603_EEPROM', r.stderr)

    def test_production_qualify_requires_production_profile(self):
        r = self.run_build(BOOT_PROFILE='normal', PRODUCTION_QUALIFY='1')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('PRODUCTION_QUALIFY requires BOOT_PROFILE=production', r.stderr)

    def test_production_rejects_diagnostic_overrides(self):
        for override in ('BRINGUP', 'NAND_UBI_TEST', 'ETH_FORCE_INIT',
                         'DIAGNOSTIC_RADIOS', 'NAND_ONDIE_PROBE'):
            with self.subTest(override=override):
                r = self.run_build(BOOT_PROFILE='production', **{override: '1'})
                self.assertNotEqual(r.returncode, 0)
                self.assertIn('release profile', r.stderr)

    def test_production_rejects_ram_root_test_flag(self):
        r = self.run_build(BOOT_PROFILE='production', RAM_ROOT_TEST='1')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('PRODUCTION_QUALIFY=1, not RAM_ROOT_TEST=1', r.stderr)

    def test_invalid_production_qualify_value_rejected(self):
        r = self.run_build(BOOT_PROFILE='production', PRODUCTION_QUALIFY='yes')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('PRODUCTION_QUALIFY must be 0 or 1', r.stderr)

    def test_pp_tables_only_for_diagnostic(self):
        for profile in ('production', 'normal'):
            with self.subTest(profile=profile):
                r = self.run_build(BOOT_PROFILE=profile, PP_TABLES='1')
                self.assertNotEqual(r.returncode, 0)
                self.assertIn('PP_TABLES=1 is for diagnostic', r.stderr)
        r = self.run_build(BOOT_PROFILE='diagnostic', PP_TABLES='2')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('PP_TABLES must be 0 or 1', r.stderr)

    def test_unknown_profile_rejected(self):
        r = self.run_build(BOOT_PROFILE='prod')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('BOOT_PROFILE must be', r.stderr)


if __name__ == '__main__':
    unittest.main()
