"""Drive the real production platform.sh with stubbed mtd/ubi/tar and fixtures.

No hardware: /proc/mtd, /tmp/sysinfo/board_name, the sysupgrade tar and every
flash/ubi command are faked, and the script's actions are recorded to a log so
the ordering and refusal properties can be asserted:

  * board-name check happens before anything is written;
  * write order is rootfs -> kernel1 -> header, header LAST;
  * each part is read back and verified before the next is written;
  * a verify mismatch aborts before the next (more dangerous) write;
  * bank B (kernel2/rootfs2) and the bootloader are never touched;
  * config preservation writes into the UBI rootfs_data volume;
  * -n resets by recreating the UBI volume, never writing a deadc0de marker.
"""
import os
from pathlib import Path
import shlex
import subprocess
import tarfile
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'files/target/linux/armsr/base-files/lib/upgrade/platform.sh'

# Stubs that record every mutation to $ACTIONLOG and succeed, except that the
# verify of a partition named in $FAIL_VERIFY reports a mismatch.
HARNESS = r'''
log() { echo "$*" >> "$ACTIONLOG"; }

# functions.sh stand-ins used by platform.sh / nand helpers.
find_mtd_index() {
	case "$1" in
		overlay_ubi) echo 13;;
		*) awk -v l="\"$1\"" '$4==l{gsub(":","",$1);sub("mtd","",$1);print $1;exit}' "$PROCMTD";;
	esac
}
nand_find_ubi() { [ -f "$UBI_ATTACHED" ] && echo ubi0; }
nand_find_volume() { [ -f "$RD_PRESENT" ] && echo ubi0_0; }
nand_remove_ubiblock() { log "ubiblock-remove $1"; }

# tools
mtd() {
	case "$1" in
		write) log "WRITE $3 <- $2"; return 0;;
		verify)
			log "VERIFY $3 <- $2"
			case " $FAIL_VERIFY " in *" $3 "*) echo MISMATCH; return 1;; esac
			return 0;;
	esac
}
ubiattach() { log "ubiattach $*"; : > "$UBI_ATTACHED"; }
ubiformat() { log "UBIFORMAT $*"; }
ubirmvol() { log "ubirmvol $*"; rm -f "$RD_PRESENT"; }
ubimkvol() { log "ubimkvol $*"; : > "$RD_PRESENT"; }
mount() { log "mount $*"; return 0; }
umount() { log "umount $*"; return 0; }
dd() {
	log "dd $*"
	for arg in "$@"; do case "$arg" in of=*) : > "${arg#of=}";; esac; done
	return 0
}
h199a-upgrade-header() {
	if [ "$1" = --check-kernel ]; then
		log "CHECK $2"
		[ "$FAIL_CHECK" != 1 ]
		return $?
	fi
	log "PREPARE $1"
	[ "$FAIL_PREPARE" != 1 ] || return 1
	cp "$WORK/upwork/header" "$6"
}
sync() { :; }
mktemp() { echo "$WORK/upwork"; mkdir -p "$WORK/upwork"; }
'''


class PlatformUpgradeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        # A fake /proc/mtd with bank A writable, bank B present, overlay last.
        self.procmtd = self.root / 'proc_mtd'
        self.procmtd.write_text(
            'dev:    size   erasesize  name\n'
            'mtd0: 08000000 00020000 "master"\n'
            'mtd1: 00100000 00020000 "bootloader"\n'
            'mtd6: 00300000 00020000 "kernel1"\n'
            'mtd7: 00d20000 00020000 "rootfs"\n'
            'mtd8: 00020000 00020000 "header"\n'
            'mtd9: 00300000 00020000 "kernel2"\n'
            'mtd10: 00d20000 00020000 "rootfs2"\n'
            'mtd13: 01000000 00020000 "overlay_ubi"\n'
            'mtd14: 00020000 00020000 "header2"\n')
        self.sysmtd = self.root / 'sys_mtd'
        for index, offset in ((6, 0x700000), (7, 0xa00000), (8, 0x1720000),
                              (9, 0x2000000), (10, 0x2300000), (14, 0x3020000)):
            node = self.sysmtd / ('mtd' + str(index))
            node.mkdir(parents=True)
            (node / 'offset').write_text(str(offset) + '\n')
        self.board = self.root / 'board_name'
        self.board.write_text('zte,zx279128s\n')
        self.actionlog = self.root / 'actions.log'
        self.actionlog.write_text('')

    def make_tar(self, members=('kernel', 'rootfs', 'header'), prefix='h199a'):
        path = self.root / 'image.tar'
        with tarfile.open(path, 'w') as tf:
            for name in members:
                data = (name + '-bytes').encode()
                ti = tarfile.TarInfo(f'{prefix}/{name}')
                ti.size = len(data)
                tf.addfile(ti, __import__('io').BytesIO(data))
        return path

    def run_platform(self, call, *, save_config='1', fail_verify='',
                     ubi_attached=False, rd_present=True, backup_file='sysupgrade.tgz',
                     make_sysupgrade_tgz=False, fail_prepare=False, fail_check=False):
        src = SOURCE.read_text()
        src = src.replace('. /lib/functions.sh', '# functions supplied by harness')
        # Redirect the handful of absolute paths the script reads.
        src = src.replace('/proc/mtd', str(self.procmtd))
        src = src.replace('/tmp/sysinfo/board_name', str(self.board))
        src = src.replace('/sys/class/mtd', str(self.sysmtd))
        ubi_attached_flag = self.root / 'ubi_attached'
        rd_flag = self.root / 'rd_present'
        if ubi_attached:
            ubi_attached_flag.write_text('')
        if rd_present:
            rd_flag.write_text('')
        tgz = self.root / 'sysupgrade.tgz'
        if make_sysupgrade_tgz:
            tgz.write_text('config')
        script = self.root / 'platform.sh'
        # Replace /tmp/sysupgrade.tgz and the ubifs restore mount dir with temp paths.
        src = src.replace('/tmp/sysupgrade.tgz', str(tgz))
        src = src.replace('/tmp/overlay-restore', str(self.root / 'overlay-restore'))
        script.write_text(src)
        env = os.environ.copy()
        env.update(ACTIONLOG=str(self.actionlog), FAIL_VERIFY=fail_verify,
                   UBI_ATTACHED=str(ubi_attached_flag), RD_PRESENT=str(rd_flag),
                   WORK=str(self.root), SAVE_CONFIG=save_config, BACKUP_FILE=backup_file,
                   FAIL_PREPARE='1' if fail_prepare else '0',
                   FAIL_CHECK='1' if fail_check else '0')
        env['PROCMTD'] = str(self.procmtd)
        prog = ('BACKUP_FILE="$BACKUP_FILE"\n' + HARNESS + '\n. ' + shlex.quote(str(script))
                + '\n' + call)
        return subprocess.run(['bash', '-c', prog], capture_output=True, text=True,
                              env=env, timeout=15)

    def actions(self):
        return [l for l in self.actionlog.read_text().splitlines() if l]

    # ---- platform_check_image ------------------------------------------------
    def test_check_accepts_valid_image(self):
        tar = self.make_tar()
        r = self.run_platform(f'platform_check_image {shlex.quote(str(tar))}; echo rc=$?')
        self.assertIn('rc=0', r.stdout, r.stdout + r.stderr)

    def test_check_rejects_foreign_board_before_any_write(self):
        self.board.write_text('some,other-board\n')
        tar = self.make_tar()
        r = self.run_platform(f'platform_check_image {shlex.quote(str(tar))}; echo rc=$?')
        self.assertIn('rc=1', r.stdout)
        self.assertEqual(self.actions(), [], 'no flash action may run for a foreign board')

    def test_kernel_capability_refusal_happens_in_preflight(self):
        tar = self.make_tar()
        r = self.run_platform(f'platform_check_image {shlex.quote(str(tar))}; echo rc=$?',
                              fail_check=True)
        self.assertIn('rc=1', r.stdout)
        self.assertEqual(self.actions(), ['CHECK a'])

    def test_check_rejects_missing_member_and_wrong_dir(self):
        for tar in (self.make_tar(members=('kernel', 'rootfs')),
                    self.make_tar(prefix='nothere')):
            r = self.run_platform(f'platform_check_image {shlex.quote(str(tar))}; echo rc=$?')
            self.assertIn('rc=1', r.stdout)

    def test_check_rejects_oversize_rootfs(self):
        # rootfs partition is 0xd20000; a bigger member must be refused.
        path = self.root / 'big.tar'
        with tarfile.open(path, 'w') as tf:
            for name, size in (('kernel', 10), ('rootfs', 0xd20000 + 1), ('header', 10)):
                ti = tarfile.TarInfo(f'h199a/{name}')
                ti.size = size
                tf.addfile(ti, __import__('io').BytesIO(b'\0' * size))
        r = self.run_platform(f'platform_check_image {shlex.quote(str(path))}; echo rc=$?')
        self.assertIn('rc=1', r.stdout)
        self.assertRegex(r.stdout + r.stderr, 'rootfs too large')

    # ---- platform_do_upgrade -------------------------------------------------
    def test_write_order_is_rootfs_kernel_header_each_verified(self):
        tar = self.make_tar()
        r = self.run_platform(f'platform_do_upgrade {shlex.quote(str(tar))}; echo rc=$?')
        self.assertIn('rc=0', r.stdout, r.stdout + r.stderr)
        acts = [a for a in self.actions() if a.startswith(('WRITE', 'VERIFY'))]
        self.assertEqual(acts, [
            'WRITE rootfs <- ' + str(self.root / 'upwork/rootfs'),
            'VERIFY rootfs <- ' + str(self.root / 'upwork/rootfs'),
            'WRITE kernel1 <- ' + str(self.root / 'upwork/kernel'),
            'VERIFY kernel1 <- ' + str(self.root / 'upwork/kernel'),
            'WRITE header <- ' + str(self.root / 'upwork/header'),
            'VERIFY header <- ' + str(self.root / 'upwork/header'),
        ])
        self.assertLess(self.actions().index('PREPARE a'),
                        next(i for i, a in enumerate(self.actions()) if a.startswith('WRITE')))

    def test_bank_b_uses_active_labels_and_prepares_b_header(self):
        text = self.procmtd.read_text()
        for left, right in (('kernel1', 'kernel2'), ('rootfs', 'rootfs2'), ('header', 'header2')):
            text = text.replace('"' + left + '"', '"TEMP"')
            text = text.replace('"' + right + '"', '"' + left + '"')
            text = text.replace('"TEMP"', '"' + right + '"')
        self.procmtd.write_text(text)
        tar = self.make_tar()
        r = self.run_platform(f'platform_do_upgrade {shlex.quote(str(tar))}; echo rc=$?')
        self.assertIn('rc=0', r.stdout, r.stdout + r.stderr)
        self.assertIn('PREPARE b', self.actions())
        self.assertIn('if=/dev/mtd14', '\n'.join(self.actions()))
        self.assertEqual(len([a for a in self.actions() if a.startswith('WRITE')]), 3)

    def test_mixed_physical_geometry_refuses_all_flash_actions(self):
        (self.sysmtd / 'mtd8/offset').write_text(str(0x3020000) + '\n')
        tar = self.make_tar()
        r = self.run_platform(f'platform_do_upgrade {shlex.quote(str(tar))}; echo rc=$?')
        self.assertIn('rc=1', r.stdout)
        self.assertEqual(self.actions(), [])

    def test_header_preparation_failure_happens_before_erasing(self):
        tar = self.make_tar()
        r = self.run_platform(f'platform_do_upgrade {shlex.quote(str(tar))}; echo rc=$?',
                              fail_prepare=True)
        self.assertIn('rc=1', r.stdout)
        self.assertFalse(any(a.startswith(('WRITE', 'VERIFY')) for a in self.actions()))

    def test_never_touches_bank_b_or_bootloader(self):
        tar = self.make_tar()
        self.run_platform(f'platform_do_upgrade {shlex.quote(str(tar))}')
        joined = '\n'.join(self.actions())
        for forbidden in ('kernel2', 'rootfs2', 'bootloader', 'tag', 'wifi'):
            self.assertNotIn(forbidden, joined)

    def test_rootfs_verify_mismatch_aborts_before_kernel_write(self):
        tar = self.make_tar()
        r = self.run_platform(f'platform_do_upgrade {shlex.quote(str(tar))}; echo rc=$?',
                              fail_verify='rootfs')
        self.assertIn('rc=1', r.stdout)
        acts = [a for a in self.actions() if a.startswith(('WRITE', 'VERIFY'))]
        self.assertEqual(acts, ['WRITE rootfs <- ' + str(self.root / 'upwork/rootfs'),
                                'VERIFY rootfs <- ' + str(self.root / 'upwork/rootfs')])
        self.assertNotIn('kernel1', '\n'.join(self.actions()))

    def test_kernel_verify_mismatch_aborts_before_header_write(self):
        tar = self.make_tar()
        r = self.run_platform(f'platform_do_upgrade {shlex.quote(str(tar))}; echo rc=$?',
                              fail_verify='kernel1')
        self.assertIn('rc=1', r.stdout)
        self.assertNotIn('WRITE header', '\n'.join(self.actions()))

    def test_save_config_upgrade_does_not_reset_overlay(self):
        tar = self.make_tar()
        self.run_platform(f'platform_do_upgrade {shlex.quote(str(tar))}',
                          save_config='1', ubi_attached=True, rd_present=True)
        joined = '\n'.join(self.actions())
        self.assertNotIn('ubirmvol', joined)
        self.assertNotIn('ubimkvol', joined)

    def test_minus_n_resets_overlay_via_ubi_not_deadc0de(self):
        tar = self.make_tar()
        r = self.run_platform(f'platform_do_upgrade {shlex.quote(str(tar))}; echo rc=$?',
                              save_config='0', ubi_attached=True, rd_present=True)
        self.assertIn('rc=0', r.stdout, r.stdout + r.stderr)
        joined = '\n'.join(self.actions())
        self.assertIn('ubirmvol', joined)
        self.assertIn('ubimkvol', joined)
        self.assertNotIn('deadc0de', joined.lower())
        # The reset never writes a raw page into the volume.
        self.assertNotRegex(joined, r'of=/dev/(?:mtd|ubi)')

    # ---- platform_copy_config ------------------------------------------------
    def test_copy_config_writes_backup_into_ubi_volume(self):
        r = self.run_platform('platform_copy_config; echo rc=$?',
                              ubi_attached=True, rd_present=True, make_sysupgrade_tgz=True)
        self.assertIn('rc=0', r.stdout, r.stdout + r.stderr)
        joined = '\n'.join(self.actions())
        self.assertIn('mount -t ubifs /dev/ubi0_0', joined)

    def test_copy_config_refuses_when_volume_missing(self):
        r = self.run_platform('platform_copy_config; echo rc=$?',
                              ubi_attached=True, rd_present=False, make_sysupgrade_tgz=True)
        self.assertIn('rc=1', r.stdout)
        self.assertNotIn('mount -t ubifs', '\n'.join(self.actions()))

    def test_copy_config_noop_without_backup(self):
        r = self.run_platform('platform_copy_config; echo rc=$?',
                              ubi_attached=True, rd_present=True, make_sysupgrade_tgz=False)
        self.assertIn('rc=0', r.stdout)
        self.assertEqual(self.actions(), [])


if __name__ == '__main__':
    unittest.main()
