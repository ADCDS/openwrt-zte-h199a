"""Run the real preinit gates with fixture sysfs/proc paths and no hardware IO."""
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'files/target/linux/armsr/base-files/lib/preinit/79_h199a_overlay'


class OverlayPreinitTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.write('sys/module/spi_zx279128/parameters/ubi_test', 'Y')
        self.write('sys/module/spi_zx279128/parameters/write_test', 'N')
        self.write('sys/module/spinand/parameters/diagnostic_write_guard', 'Y')
        for path in ('sys/bus/spi/drivers/spi-nand',
                     'sys/bus/platform/drivers/zx279128-spifc', 'sys/class/ubi', 'tmp', 'dev'):
            (self.root/path).mkdir(parents=True, exist_ok=True)
        names = ['master', 'bootloader', 'tag', 'wifi', 'usercfg', 'defcfg',
                 'kernel1', 'rootfs', 'header', 'kernel2', 'rootfs2', 'legacy_overlay', 'staging', 'overlay_ubi']
        for i, name in enumerate(names):
            self.write(f'sys/class/mtd/mtd{i}/name', name)
            self.write(f'sys/class/mtd/mtd{i}/flags', '0x400' if i in (0, 13) else '0x0')
            (self.root/f'sys/class/mtd/mtd{i}ro').mkdir()
        self.write('sys/class/mtd/mtd0/size', '134217728')
        for name, value in dict(offset=88080384, size=16777216, erasesize=131072,
                                writesize=2048, oobsize=128, type='nand', dev='90:26').items():
            self.write('sys/class/mtd/mtd13/'+name, str(value))
        self.write('sys/class/misc/ubi_ctrl/dev', '10:127')
        self.write('proc/filesystems', 'nodev\tubifs')
        script = SOURCE.read_text().replace('/sys/', str(self.root/'sys')+'/')
        script = script.replace('/proc/', str(self.root/'proc')+'/')
        script = script.replace('/etc/h199a-overlay-qualification', str(self.root/'marker'))
        script = script.replace('/tmp/h199a-', str(self.root/'tmp')+'/h199a-')
        script = script.replace('/dev/h199a-overlay', str(self.root/'dev/h199a-overlay'))
        script = script.replace('/tmp/failsafe', str(self.root/'failsafe'))
        self.script = self.root/'preinit.sh'
        self.script.write_text(script)

    def write(self, name, value):
        path = self.root/name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value+'\n')

    def run_shell(self, command, stubs=''):
        return subprocess.run(['sh', '-c',
            'boot_hook_add() { :; }; '+stubs+'\n. '+shlex.quote(str(self.script))+'\n'+command],
            capture_output=True, text=True, timeout=5)

    def mount_fixture(self):
        self.write('sys/class/ubi/ubi0/mtd_num', '13')
        self.write('sys/class/ubi/ubi0_0/name', 'rootfs_data')
        self.write('proc/mounts',
                   '/dev/ubi0_0 /overlay ubifs rw,noatime 0 0\n'
                   'overlayfs:/overlay / overlay rw,lowerdir=/,upperdir=/overlay/upper,workdir=/overlay/work 0 0\n'
                   '/dev/root /rom squashfs ro,relatime 0 0')
        self.write('proc/self/mountinfo', '20 1 1:0 / /rom ro - squashfs /dev/root ro')

    def test_exact_window_and_original_partition_protections(self):
        result = self.run_shell('h199a_overlay_check')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_wrong_guards_names_geometry_and_write_flags_fail(self):
        cases = {
            'sys/module/spinand/parameters/diagnostic_write_guard': 'N',
            'sys/module/spi_zx279128/parameters/write_test': 'Y',
            'sys/class/mtd/mtd9/flags': '0x400',
            'sys/class/mtd/mtd11/name': 'rootfs_data',
            'sys/class/mtd/mtd13/offset': '83886080',
            'sys/class/mtd/mtd13/oobsize': '64',
        }
        for path, invalid in cases.items():
            with self.subTest(path=path):
                old = (self.root/path).read_text()
                self.write(path, invalid)
                self.assertNotEqual(self.run_shell('h199a_overlay_check').returncode, 0)
                (self.root/path).write_text(old)

    def test_extra_mtd_rebind_and_existing_ubi_fail(self):
        for path in ('sys/class/mtd/mtd14/flags', 'sys/bus/spi/drivers/spi-nand/bind',
                     'sys/bus/platform/drivers/zx279128-spifc/unbind', 'sys/class/ubi/ubi1'):
            with self.subTest(path=path):
                self.write(path, '0')
                self.assertNotEqual(self.run_shell('h199a_overlay_check').returncode, 0)
                (self.root/path).unlink()

    def test_mount_check_accepts_exact_ram_lower_and_ubi_upper(self):
        self.mount_fixture()
        result = self.run_shell('h199a_overlay_mount_check')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_mount_check_rejects_ram_overlay_and_old_nand_lower(self):
        self.mount_fixture()
        mounts = (self.root/'proc/mounts').read_text()
        self.write('proc/mounts', mounts.replace('upperdir=/overlay/upper', 'upperdir=/tmp/root/upper'))
        self.assertNotEqual(self.run_shell('h199a_overlay_mount_check').returncode, 0)
        self.write('proc/mounts', mounts)
        self.write('proc/self/mountinfo', '20 1 31:7 / /rom ro - squashfs /dev/root ro')
        self.assertNotEqual(self.run_shell('h199a_overlay_mount_check').returncode, 0)

    def test_failed_attachment_enters_blocking_recovery_without_format(self):
        (self.root/'marker').write_text('qualification')
        stubs = '''
        mknod() { : >"$1"; }
        ubiattach() { echo ATTACH_FAILED; return 1; }
        ubiformat() { echo UNEXPECTED_FORMAT; exit 99; }
        boot_run_hook() { echo RECOVERY_HOOK; }
        sleep() { exit 77; }
        '''
        result = self.run_shell('h199a_overlay_preinit; echo NORMAL_SERVICES', stubs)
        self.assertEqual(result.returncode, 77, result.stdout+result.stderr)
        self.assertIn('ATTACH_FAILED', result.stdout)
        self.assertIn('RECOVERY_HOOK', result.stdout)
        self.assertNotIn('UNEXPECTED_FORMAT', result.stdout)
        self.assertNotIn('NORMAL_SERVICES', result.stdout)

    def test_failed_mount_does_not_return_to_normal_services(self):
        self.mount_fixture()
        self.write('proc/mounts', '')
        result = self.run_shell('H199A_OVERLAY_QUALIFICATION=1; h199a_overlay_post_mount; echo NORMAL_SERVICES',
                                'boot_run_hook() { echo RECOVERY_HOOK; }; sleep() { exit 77; };')
        self.assertEqual(result.returncode, 77)
        self.assertIn('RECOVERY_HOOK', result.stdout)
        self.assertNotIn('NORMAL_SERVICES', result.stdout)

    def test_unselected_profile_does_not_touch_storage(self):
        result = self.run_shell('h199a_overlay_preinit; echo NORMAL_SERVICES',
                                'ubiattach() { echo UNEXPECTED_ATTACH; exit 99; };')
        self.assertEqual(result.returncode, 0)
        self.assertNotIn('UNEXPECTED_ATTACH', result.stdout)
