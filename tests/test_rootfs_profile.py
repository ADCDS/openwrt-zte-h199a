"""Reject the previously observed stale/missing normal-userspace components."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'tools/verify-rootfs-profile.py'
spec = importlib.util.spec_from_file_location('rootfs_profile', SOURCE)
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


class RootfsProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for name in profile.REQUIRED:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'fixture')
        (self.root/'usr/sbin/hostapd').write_bytes(b'\x7fELF'+b''.join(profile.WPS_MARKERS))
        (self.root/'usr/bin/util-linux-flock').write_bytes(b'\x7fELFfixture')
        (self.root/'usr/bin/util-linux-flock').chmod(0o755)
        (self.root/'usr/libexec/timeout-coreutils').write_bytes(b'\x7fELFfixture')
        (self.root/'usr/libexec/timeout-coreutils').chmod(0o755)
        for name in profile.WPS_FILES:
            (self.root/name).write_bytes((profile.BOARD_FILES/name).read_bytes())
        folder = self.root / 'etc/modules.d'
        folder.mkdir()
        (folder / 'mt7603').write_text('mt7603e\n')
        (folder / 'mt7615e').write_text('mt7615e\n')

    def test_complete_tree_and_image_absolute_symlinks(self):
        self.assertEqual(profile.verify(self.root)['autoload']['mt7603'], 'mt7603e')
        init = self.root / 'sbin/init'
        init.unlink()
        init.symlink_to('/sbin/procd')
        hostapd = self.root/'usr/sbin/hostapd'
        hostapd.rename(self.root/'usr/sbin/wpad')
        hostapd.symlink_to('/usr/sbin/wpad')
        profile.verify(self.root)

    def test_button_script_alone_cannot_substitute_for_wps_daemon_support(self):
        hostapd = self.root/'usr/sbin/hostapd'
        complete = hostapd.read_bytes()
        for marker in profile.WPS_MARKERS:
            with self.subTest(marker=marker):
                hostapd.write_bytes(complete.replace(marker, b''))
                with self.assertRaisesRegex(ValueError, 'compiled WPS'):
                    profile.verify(self.root)
        hostapd.write_bytes(b'#!/bin/sh\n'+b''.join(profile.WPS_MARKERS))
        with self.assertRaisesRegex(ValueError, 'compiled WPS'):
            profile.verify(self.root)

    def test_missing_fstools_and_empty_autoload_are_rejected(self):
        (self.root / 'sbin/mount_root').unlink()
        with self.assertRaises(ValueError):
            profile.verify(self.root)
        (self.root / 'sbin/mount_root').write_bytes(b'fixture')
        (self.root / 'etc/modules.d/mt7603').write_text('')
        with self.assertRaises(ValueError):
            profile.verify(self.root)

    def test_retired_service_and_dangling_override_are_rejected(self):
        path = self.root / 'etc/init.d/zx-wifi-late'
        path.write_bytes(b'old experiment')
        with self.assertRaises(ValueError):
            profile.verify(self.root)
        path.unlink()
        path.symlink_to('/missing-old-service')
        with self.assertRaises(ValueError):
            profile.verify(self.root)

    def test_symlink_escape_and_cycle_are_rejected(self):
        path = self.root / 'sbin/init'
        path.unlink()
        for target in ('../../outside', '/sbin/init'):
            with self.subTest(target=target):
                path.symlink_to(target)
                with self.assertRaises(ValueError):
                    profile.verify(self.root)
                path.unlink()

    def test_qualification_requires_marker_and_current_hook(self):
        with self.assertRaises(ValueError):
            profile.verify(self.root, qualification=True)
        marker = self.root / profile.QUALIFICATION_MARKER
        marker.write_text('guarded-ubi-overlay-v1\n')
        hook = self.root / profile.QUALIFICATION_HOOK
        hook.write_text('old hook')
        with self.assertRaises(ValueError):
            profile.verify(self.root, qualification=True)
        with self.assertRaises(ValueError):
            profile.verify(self.root)  # A present marker always enables hook checking.
        hook.write_bytes(profile.HOOK_SOURCE.read_bytes())
        self.assertTrue(profile.verify(self.root, qualification=True)['qualification'])
