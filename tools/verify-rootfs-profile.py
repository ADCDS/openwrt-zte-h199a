#!/usr/bin/env python3
"""Validate the normal userspace tree before packaging or RAM qualification."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile

RETIRED = (
    'etc/modules.d/mt7603e', 'etc/init.d/zx-wifi-late',
    'etc/rc.d/S99zx-wifi-late', 'etc/zx-wifi-delay', 'etc/zx-wifi-mods',
    'etc/uci-defaults/90-zx-defer-wifi',
)
REQUIRED = (
    'sbin/init', 'sbin/procd', 'sbin/mount_root', 'lib/libfstools.so',
    'usr/sbin/ubiattach', 'usr/sbin/ubidetach', 'usr/sbin/ubinfo',
    'etc/preinit', 'lib/functions/preinit.sh', 'lib/preinit/80_mount_root',
    'etc/init.d/done',
    'usr/sbin/hostapd', 'etc/rc.button/wps',
    'usr/bin/util-linux-flock', 'usr/libexec/h199a-wps-led',
    'usr/libexec/timeout-coreutils',
    'etc/hotplug.d/button/50-h199a-wps-led',
)
WPS_MARKERS = (b'wps_start\0', b'wps_status\0', b'wps_cancel\0',
               b'pbc_status\0', b'last_wps_result\0')
QUALIFICATION_HOOK = 'lib/preinit/79_h199a_overlay'
QUALIFICATION_MARKER = 'etc/h199a-overlay-qualification'
HOOK_SOURCE = Path(__file__).resolve().parents[1] / 'files/target/linux/armsr/base-files' / QUALIFICATION_HOOK
WPS_FILES = ('usr/libexec/h199a-wps-led', 'etc/hotplug.d/button/50-h199a-wps-led')
BOARD_FILES = Path(__file__).resolve().parents[1] / 'files/target/linux/armsr/base-files'


def resolve_in_root(root, relative):
    """Resolve image symlinks against the image root, never the host root."""
    remaining = list(Path(relative).parts)
    resolved = []
    links = 0
    while remaining:
        part = remaining.pop(0)
        if part in ('', '.'):
            continue
        if part == '..':
            if not resolved:
                raise ValueError('symlink escapes image root')
            resolved.pop()
            continue
        path = root.joinpath(*resolved, part)
        if path.is_symlink():
            links += 1
            if links > 40:
                raise ValueError('symlink cycle in image')
            target = os.readlink(path)
            if target.startswith('/'):
                resolved = []
            remaining = [p for p in target.split('/') if p] + remaining
        else:
            resolved.append(part)
    return root.joinpath(*resolved)


def verify(root, qualification=False):
    root = Path(root)
    if not root.is_dir():
        raise ValueError('rootfs directory missing')
    for name in RETIRED:
        path = root / name
        if path.exists() or path.is_symlink():
            raise ValueError('retired diagnostic override remains: ' + name)
    for name in REQUIRED:
        path = resolve_in_root(root, name)
        if not path.is_file() or not path.stat().st_size:
            raise ValueError('required userspace file missing or empty: ' + name)
    marker = resolve_in_root(root, QUALIFICATION_MARKER)
    if qualification or marker.exists():
        if not marker.is_file() or marker.read_text() != 'guarded-ubi-overlay-v1\n':
            raise ValueError('RAM-root qualification marker missing or invalid')
        hook = resolve_in_root(root, QUALIFICATION_HOOK)
        if not hook.is_file() or hook.read_bytes() != HOOK_SOURCE.read_bytes():
            raise ValueError('RAM-root qualification hook missing or stale')
    modules = {}
    for name, module in (('mt7603', 'mt7603e'), ('mt7615e', 'mt7615e')):
        path = resolve_in_root(root, 'etc/modules.d/' + name)
        if not path.is_file():
            raise ValueError('radio autoload entry missing: ' + name)
        words = [line.split('#', 1)[0].split() for line in path.read_text().splitlines()]
        entries = [tokens[0] for tokens in words if tokens]
        if entries != [module]:
            raise ValueError('radio autoload entry differs from its package: ' + name)
        modules[name] = module
    # The basic package ships the common button script without the daemon's
    # WPS methods. Check the resolved final ELF, not just a package selection
    # or a shell script that also exists in the unsupported variant.
    hostapd = resolve_in_root(root, 'usr/sbin/hostapd').read_bytes()
    if not hostapd.startswith(b'\x7fELF') or not all(marker in hostapd for marker in WPS_MARKERS):
        raise ValueError('hostapd lacks the compiled WPS ubus methods/status fields')
    flock = resolve_in_root(root, 'usr/bin/util-linux-flock')
    if not flock.read_bytes().startswith(b'\x7fELF') or not flock.stat().st_mode & 0o111:
        raise ValueError('WPS observer requires the executable util-linux flock, including -w')
    timeout = resolve_in_root(root, 'usr/libexec/timeout-coreutils')
    if not timeout.read_bytes().startswith(b'\x7fELF') or not timeout.stat().st_mode & 0o111:
        raise ValueError('WPS observer requires the executable coreutils timeout')
    for name in WPS_FILES:
        if resolve_in_root(root, name).read_bytes() != (BOARD_FILES/name).read_bytes():
            raise ValueError('WPS indicator helper missing or stale: '+name)
    return {'required_files': len(REQUIRED), 'retired_overrides': False,
            'autoload': modules, 'wps_daemon': True,
            'qualification': qualification or marker.exists(), 'root': str(root)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument('--root', type=Path, help='already extracted image tree')
    inputs.add_argument('--image', type=Path, help='raw SquashFS image')
    inputs.add_argument('--sysupgrade', type=Path, help='H199A sysupgrade tar')
    parser.add_argument('--unsquashfs', default=shutil.which('unsquashfs'))
    parser.add_argument('--qualification', action='store_true', help='require the exact RAM-root qualification hook/marker')
    args = parser.parse_args()
    try:
        if args.root:
            result = verify(args.root, args.qualification)
        else:
            if not args.unsquashfs:
                raise ValueError('unsquashfs is required to validate the finished image')
            source = args.image or args.sysupgrade
            with tempfile.TemporaryDirectory(prefix='h199a-rootfs-check-') as directory:
                work = Path(directory)
                image = args.image
                if args.sysupgrade:
                    with tarfile.open(args.sysupgrade, 'r:') as archive:
                        entries = [m for m in archive.getmembers() if m.name == 'h199a/rootfs']
                        if len(entries) != 1 or not entries[0].isfile() or not 0 < entries[0].size <= 16*1024*1024:
                            raise ValueError('expected one bounded h199a/rootfs tar member')
                        image = work / 'rootfs.squashfs'
                        image.write_bytes(archive.extractfile(entries[0]).read())
                if not 0 < image.stat().st_size <= 16*1024*1024:
                    raise ValueError('SquashFS image exceeds qualification size bound')
                result = subprocess.run([args.unsquashfs, '-processors', '1', '-no-progress',
                                         '-no-xattrs', '-d', str(work/'root'), str(image),
                                         'etc', 'sbin', 'lib', 'usr/sbin', 'usr/bin', 'usr/libexec'],
                                        capture_output=True, text=True)
                if result.returncode:
                    raise ValueError('SquashFS extraction failed: ' + result.stderr[-1000:])
                result = verify(work/'root', args.qualification)
                result.pop('root')
                result['image'] = str(source)
                result['image_sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
    except (OSError, ValueError, tarfile.TarError) as error:
        parser.exit(1, str(error) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
