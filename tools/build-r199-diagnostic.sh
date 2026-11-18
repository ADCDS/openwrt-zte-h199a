#!/usr/bin/env bash
# Offline kernel-only build. Creates a RAM-boot container, NEVER flashes/deploys.
set -euo pipefail
ROOT=$(dirname "$(dirname "$(readlink -f "$0")")")
K="$ROOT/openwrt/build_dir/target-arm_cortex-a9_musl_eabi/linux-armsr_armv7/linux-6.6.151"
TC="$ROOT/openwrt/staging_dir/toolchain-arm_cortex-a9_gcc-13.3.0_musl_eabi"
SRC=drivers/net/ethernet/zte/zx279128-eth.c
ROUND=${ROUND:-r199}
case "$ROUND" in r199|r200|r201|r202|r203|r204) ;; *) echo 'unsupported diagnostic round' >&2; exit 2;; esac
OUT="$ROOT/artifacts/$ROUND"
mkdir -p "$OUT"
cmp "$ROOT/files/target/linux/armsr/files-6.6/$SRC" "$ROOT/openwrt/target/linux/armsr/files-6.6/$SRC"
cmp "$ROOT/files/target/linux/armsr/files-6.6/$SRC" "$K/$SRC"
# Fail before building if an experiment leaks into another round's label.
python3 - "$ROOT" "$ROUND" <<'PY'
import hashlib, json, sys
from pathlib import Path
root=Path(sys.argv[1]); label=sys.argv[2]
rel='openwrt/build_dir/target-arm_cortex-a9_musl_eabi/linux-armsr_armv7/linux-6.6.151/.config'
cfg=(root/rel).read_text()
flag='zx279128_eth.force_dp_init=1'
if label == 'r203':
    ref=(root/'artifacts/r203/reference.config').read_bytes()
    manifest=json.loads((root/'artifacts/r202/manifest.json').read_text())
    assert hashlib.sha256(ref).hexdigest() == manifest['sha256'][rel]
    old=next(line for line in ref.decode().splitlines() if line.startswith('CONFIG_CMDLINE='))
    new=old[:-1]+' '+flag+'"'
    assert cfg == ref.decode().replace(old, new, 1), 'R203 must change only the forced command line'
    src='files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c'
    assert hashlib.sha256((root/src).read_bytes()).hexdigest() == manifest['sha256'][src]
elif label == 'r204':
    manifest=json.loads((root/'artifacts/r203/manifest.json').read_text())
    assert hashlib.sha256((root/rel).read_bytes()).hexdigest() == manifest['sha256'][rel], 'R204 config must equal the R203 forced control'
    src='files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c'
    reference=(root/'artifacts/r204/reference-driver.c').read_bytes()
    assert hashlib.sha256(reference).hexdigest() == manifest['sha256'][src], 'R204 source reference drift'
    # The actual-C tests below additionally require exact source restoration.
else:
    assert 'zx279128_eth.force_dp_init' not in cfg.replace('-', '_'), 'forced-init config must not be packaged as the earlier reference'
PY
export PATH="$TC/bin:$ROOT/openwrt/staging_dir/host/bin:$PATH"
export STAGING_DIR="$ROOT/openwrt/staging_dir/target-arm_cortex-a9_musl_eabi"
python3 "$ROOT/tests/test-r199-path-dump.py"
if [[ "$ROUND" != r199 ]]; then
  python3 "$ROOT/tests/test_mac_snapshot_r200.py"
fi
if [[ "$ROUND" == r201 || "$ROUND" == r202 || "$ROUND" == r203 || "$ROUND" == r204 ]]; then
  python3 "$ROOT/tests/test_packet_trace_r201.py"
fi
if [[ "$ROUND" == r202 || "$ROUND" == r203 || "$ROUND" == r204 ]]; then
  python3 "$ROOT/tests/test_rx_seed_r202.py"
  python3 "$ROOT/tests/test_handoff_reader_r202.py"
fi
if [[ "$ROUND" == r203 || "$ROUND" == r204 ]]; then
  python3 "$ROOT/tests/test_build_profile_r203.py"
fi
if [[ "$ROUND" == r204 ]]; then
  python3 "$ROOT/tests/test_tx_origin_r204.py"
  python3 "$ROOT/tests/test_build_profile_r204.py"
  python3 "$ROOT/tests/test_tx_handoff_reader_r204.py"
fi
# Preserve the existing kernel configuration and OpenWrt compiler options.
# Full build.sh would overwrite it from the seed and unnecessarily update feeds.
make -C "$K" -j"${JOBS:-4}" ARCH=arm CROSS_COMPILE=arm-openwrt-linux-muslgnueabi- \
  KCFLAGS="-fmacro-prefix-map=$ROOT/openwrt/build_dir/target-arm_cortex-a9_musl_eabi=target-arm_cortex-a9_musl_eabi -fno-caller-saves" \
  KBUILD_BUILD_USER=agiu KBUILD_BUILD_HOST=syd KBUILD_BUILD_VERSION=0 \
  KBUILD_BUILD_TIMESTAMP='Fri Sep 11 14:10:59 2026' KERNELRELEASE=6.6.151 \
  zImage
python3 - "$ROOT" "$ROUND" <<'PY'
import hashlib, json, lzma, struct, sys, time, zlib
from pathlib import Path
root = Path(sys.argv[1]); label = sys.argv[2]; out = root / 'artifacts' / label
k = root / 'openwrt/build_dir/target-arm_cortex-a9_musl_eabi/linux-armsr_armv7/linux-6.6.151'
baseline = Path('/srv/tftp/r75.kernel').read_bytes()
assert hashlib.sha256(baseline).hexdigest() == '3aad74d951449cc32f68a15656ab3be9206da58bfa3c85ebd43e7256a43cf94a'
old_header = bytearray(baseline[32:96]); h = struct.unpack('>7I4B32s', old_header)
assert h[0] == 0x27051956 and h[4:6] == (0x40008000, 0x40008000)
old_header[4:8] = bytes(4)
assert zlib.crc32(old_header) == h[1]
old_payload = baseline[96:96+h[3]]
assert zlib.crc32(old_payload) == h[6]
old_zsize = struct.unpack_from('<I', old_payload, 44)[0]
dtb = old_payload[old_zsize:]
assert dtb[:4] == bytes.fromhex('d00dfeed')
assert struct.unpack_from('>I', dtb, 4)[0] == len(dtb)
zimage = (k / 'arch/arm/boot/zImage').read_bytes()
assert struct.unpack_from('<I', zimage, 44)[0] == len(zimage)
# The first XZ magic in a zImage can be a decompressor string constant.
raw = None
for pos in range(len(zimage)):
    if zimage[pos:pos+8] != bytes.fromhex('fd377a585a000001'):
        continue
    try:
        dec = lzma.LZMADecompressor(); candidate = dec.decompress(zimage[pos:])
        if dec.eof:
            raw = candidate; break
    except lzma.LZMAError:
        pass
assert raw is not None, 'no complete XZ kernel stream'
assert b'PATHDUMP R199' in raw and b'regs_path_only' in raw and b'regs_pp2_page' in raw
if label != 'r199':
    assert b'MACSNAP' in raw and b'mac_snapshot' in raw
if label in ('r201', 'r202', 'r203', 'r204'):
    assert b'packet_trace_id' in raw and b'zx_eth_packets' in raw
if label in ('r202', 'r203', 'r204'):
    assert b'rx_q0_seed' in raw
config = (k / '.config').read_text()
assert 'CONFIG_CMDLINE_FORCE=y' in config
cmdline = next(line for line in config.splitlines() if line.startswith('CONFIG_CMDLINE='))
assert 'ro init=/bin/sh' in cmdline
assert cmdline.split('=', 1)[1][1:-1].encode() + b'\0' in raw, 'compiled command line mismatch'
if label in ('r203', 'r204'):
    assert cmdline.endswith(' zx279128_eth.force_dp_init=1"')
    (out / 'forced.config').write_text(config)
if label == 'r204':
    assert b'TXORIGIN_R204' in raw, 'compiled TX origin instrumentation missing'
payload = zimage + dtb
header = struct.pack('>7I4B32s', h[0], 0, int(time.time()), len(payload), h[4], h[5],
                     zlib.crc32(payload), *h[7:11], f'h199a-{label}-diag'.encode())
header = header[:4] + struct.pack('>I', zlib.crc32(header)) + header[8:]
image = baseline[:32] + header + payload
assert len(image) <= 0x300000
image += bytes(0x300000 - len(image))
(out / f'{label}.kernel').write_bytes(image)
(out / f'{label}.Image').write_bytes(raw)
(out / 'r75.dtb').write_bytes(dtb)
paths = [root / 'files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c',
         root / 'openwrt/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c',
         k / 'drivers/net/ethernet/zte/zx279128-eth.c', k / '.config', k / 'vmlinux',
         k / 'arch/arm/boot/zImage', out / 'r75.dtb', out / f'{label}.kernel']
manifest = {'baseline': '/srv/tftp/r75.kernel', 'baseline_sha256': hashlib.sha256(baseline).hexdigest(),
            'tftp_load_address': '0x42000000', 'uimage_offset': 32, 'bootm_address': '0x42000020',
            'cmdline': cmdline, 'dtb': 'byte-identical to embedded r75 DTB',
            'mode': ('cold/full-init-only TX origin zero with one-time observation; same forced config as R203; RAM-only, no default or flash changes'
                      if label == 'r204' else
                      'existing full datapath init forced via compiled command line; unchanged R202 driver source; RAM-only, no deployment or flash operation'
                      if label == 'r203' else
                      'diagnostics plus default-off observed warm RX cursor seed; no deployment or flash operation'
                      if label == 'r202' else
                      'diagnostics only; no behavioral MAC/init changes; no deployment or flash operation'),
            'sha256': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}}
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
PY
