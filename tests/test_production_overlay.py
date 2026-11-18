"""Run the production preinit overlay hook with fixture sysfs/proc, no hardware.

The hook (78_h199a_production_overlay) must:
  * do nothing in a non-production image, including the production-qualify one;
  * attach overlay_ubi and, when rootfs_data already exists, hand it to fstools;
  * format once and create rootfs_data only on a genuinely empty UBI window;
  * refuse to format when a foreign volume is present, entering recovery;
  * never attach the real overlay in the production-qualify (deny-matrix) image.
"""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

SOURCE = (Path(__file__).resolve().parents[1]
          / 'files/target/linux/armsr/base-files/lib/preinit/78_h199a_production_overlay')

# Stubs model attach/format/mkvol by mutating the fixture sysfs tree. They honour
# scenario flags set in the environment.
STUBS = r'''
mknod() { : > "$1"; }   # ignore the c major minor args; just create the node path
# ubiattach: create ubi0 bound to mtd 13, with volumes per $SCENARIO.
ubiattach() {
	[ "$ATTACH_OK" = 1 ] || return 1
	mkdir -p "$U/ubi0"; echo 13 > "$U/ubi0/mtd_num"; echo 10:0 > "$U/ubi0/dev"
	case "$SCENARIO" in
		ready) mkdir -p "$U/ubi0_0"; echo rootfs_data > "$U/ubi0_0/name"; echo 250:1 > "$U/ubi0_0/dev";;
		empty) : ;;
		foreign) mkdir -p "$U/ubi0_1"; echo owner_data > "$U/ubi0_1/name"; echo 250:2 > "$U/ubi0_1/dev";;
	esac
	return 0
}
ubiformat() { echo FORMATTED >> "$LOG"; ATTACH_OK=1; return 0; }
ubimkvol() {
	echo "MKVOL $*" >> "$LOG"
	mkdir -p "$U/ubi0_0"; echo rootfs_data > "$U/ubi0_0/name"; echo 250:1 > "$U/ubi0_0/dev"; return 0
}
boot_run_hook() { echo RECOVERY >> "$LOG"; }
sleep() { echo SLEEP >> "$LOG"; exit 77; }
'''


class ProductionOverlayTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'sys/class/mtd/mtd13').mkdir(parents=True)
        (self.root / 'sys/class/mtd/mtd13/name').write_text('overlay_ubi\n')
        (self.root / 'sys/class/mtd/mtd13/dev').write_text('90:26\n')
        # Two 128 KiB eraseblocks keep the blank-window scan fast.
        (self.root / 'sys/class/mtd/mtd13/size').write_text('262144\n')
        (self.root / 'sys/class/mtd/mtd13/erasesize').write_text('131072\n')
        # a couple of other partitions so the label scan is realistic
        for i, n in ((6, 'kernel1'), (7, 'rootfs'), (8, 'header')):
            (self.root / f'sys/class/mtd/mtd{i}').mkdir(parents=True)
            (self.root / f'sys/class/mtd/mtd{i}/name').write_text(n + '\n')
            (self.root / f'sys/class/mtd/mtd{i}/dev').write_text(f'90:{i}\n')
        (self.root / 'sys/class/misc/ubi_ctrl').mkdir(parents=True)
        (self.root / 'sys/class/misc/ubi_ctrl/dev').write_text('10:63\n')
        (self.root / 'sys/class/ubi').mkdir(parents=True)
        (self.root / 'dev').mkdir(exist_ok=True)
        (self.root / 'tmp').mkdir(exist_ok=True)
        self.log = self.root / 'hook.log'
        self.log.write_text('')
        src = SOURCE.read_text()
        src = src.replace('/sys/', str(self.root / 'sys') + '/')
        src = src.replace('/proc/cmdline', str(self.root / 'cmdline'))
        src = src.replace('/dev/', str(self.root / 'dev') + '/')
        src = src.replace('/tmp/failsafe', str(self.root / 'tmp/failsafe'))
        self.script = self.root / 'hook.sh'
        self.script.write_text(src)

    def cmdline(self, text):
        (self.root / 'cmdline').write_text(text + '\n')

    def run_hook(self, scenario='ready', attach_ok='1'):
        env = {'U': str(self.root / 'sys/class/ubi'), 'LOG': str(self.log),
               'SCENARIO': scenario, 'ATTACH_OK': attach_ok, 'PATH': '/usr/bin:/bin'}
        prog = ('boot_hook_add() { :; }\n' + STUBS + '\n. '
                + shlex.quote(str(self.script)) + '\nh199a_prod_overlay; echo DONE=$?')
        return subprocess.run(['bash', '-c', prog], capture_output=True, text=True,
                              env=env, timeout=15)

    def test_inert_without_production_flag(self):
        self.cmdline('console=ttyAMA0 root=/dev/ram0 ro')
        r = self.run_hook()
        self.assertIn('DONE=0', r.stdout)
        self.assertEqual(self.log.read_text(), '')
        self.assertNotIn('READY', r.stdout)

    def test_inert_in_production_qualify_image(self):
        self.cmdline('console=ttyAMA0 spi_zx279128.production_qualify=1 root=/dev/ram0')
        r = self.run_hook()
        self.assertIn('DONE=0', r.stdout)
        self.assertEqual(self.log.read_text(), '', 'qualify image must not attach the real overlay')

    def test_attaches_existing_rootfs_data_and_publishes_node(self):
        self.cmdline('console=ttyAMA0 spi_zx279128.production=1')
        (self.root / 'sys/class/ubi/ubi0').mkdir()
        (self.root / 'sys/class/ubi/ubi0/mtd_num').write_text('13\n')
        (self.root / 'sys/class/ubi/ubi0/dev').write_text('10:0\n')
        (self.root / 'sys/class/ubi/ubi0_0').mkdir()
        (self.root / 'sys/class/ubi/ubi0_0/name').write_text('rootfs_data\n')
        (self.root / 'sys/class/ubi/ubi0_0/dev').write_text('250:1\n')
        r = self.run_hook(scenario='ready')
        self.assertIn('H199A_PROD_OVERLAY_READY', r.stdout, r.stdout + r.stderr)
        self.assertNotIn('MKVOL', self.log.read_text())
        self.assertNotIn('FORMATTED', self.log.read_text())
        self.assertTrue((self.root / 'dev/ubi0_0').exists())

    def test_formats_and_creates_volume_on_empty_window(self):
        self.cmdline('console=ttyAMA0 spi_zx279128.production=1')
        r = self.run_hook(scenario='empty', attach_ok='0')
        self.assertIn('H199A_PROD_OVERLAY_READY', r.stdout, r.stdout + r.stderr)
        log = self.log.read_text()
        self.assertIn('FORMATTED', log)
        self.assertIn('MKVOL', log)
        self.assertIn('rootfs_data', log)

    def window_node(self, data):
        node = self.root / 'dev/h199a-prod-overlay/mtd'
        node.parent.mkdir(parents=True, exist_ok=True)
        node.write_bytes(data)

    def test_failed_attach_over_existing_ubi_never_formats(self):
        # A UBI EC header in the SECOND eraseblock: attach failed for another
        # reason (bit errors, wrong VID offset). Formatting would destroy the
        # owner's configuration, so the hook must enter recovery instead.
        self.cmdline('console=ttyAMA0 spi_zx279128.production=1')
        self.window_node(b'\xff' * 131072 + b'UBI#' + b'\xff' * (131072 - 4))
        r = self.run_hook(scenario='empty', attach_ok='0')
        self.assertEqual(r.returncode, 77, r.stdout + r.stderr)
        log = self.log.read_text()
        self.assertNotIn('FORMATTED', log)
        self.assertNotIn('MKVOL', log)
        self.assertIn('RECOVERY', log)
        self.assertIn('did not attach (refusing to format)', r.stdout)

    def test_blank_window_still_formats_once(self):
        self.cmdline('console=ttyAMA0 spi_zx279128.production=1')
        self.window_node(b'\xff' * 262144)
        r = self.run_hook(scenario='empty', attach_ok='0')
        self.assertIn('H199A_PROD_OVERLAY_READY', r.stdout, r.stdout + r.stderr)
        self.assertEqual(self.log.read_text().count('FORMATTED'), 1)

    def test_unknown_window_geometry_never_formats(self):
        self.cmdline('console=ttyAMA0 spi_zx279128.production=1')
        (self.root / 'sys/class/mtd/mtd13/erasesize').unlink()
        r = self.run_hook(scenario='empty', attach_ok='0')
        self.assertEqual(r.returncode, 77, r.stdout + r.stderr)
        self.assertNotIn('FORMATTED', self.log.read_text())

    def test_refuses_to_format_foreign_volume(self):
        self.cmdline('console=ttyAMA0 spi_zx279128.production=1')
        r = self.run_hook(scenario='foreign')
        self.assertEqual(r.returncode, 77, r.stdout + r.stderr)  # sleep stub exits 77
        self.assertIn('RECOVERY', self.log.read_text())
        self.assertNotIn('FORMATTED', self.log.read_text())
        self.assertNotIn('MKVOL', self.log.read_text())
        self.assertIn('H199A_PROD_OVERLAY_FAILED', r.stdout)


if __name__ == '__main__':
    unittest.main()
