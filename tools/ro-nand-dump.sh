#!/bin/bash
# usage: ro-nand-dump.sh <label> [--no-ramboot]
#
# Full corrected NAND dump of the H199A, from a RAM-booted read-only dumper.
#
# What it does:
#   1. RAM-boots `perst-w` (native read-only storage backend) over U-Boot TFTP,
#      which needs a TFTP server on 192.168.1.100 in netns h199a-wan;
#   2. brings up the diagnostic SSH service on 192.0.2.1 (netns h199a-lan);
#   3. dumps /dev/mtd0 twice -- once to the host, once hashed on the device --
#      and checks the two agree;
#   4. powers the unit off.
#
# Fixes over the version that was committed (which aborted on every run):
#   * `systemctl stop h199a-tftp` failed with "Unit h199a-tftp not loaded" and
#     `set -e` killed the script before it did anything. The TFTP server is a
#     *transient* systemd-run unit, so it usually does not exist; stopping it is
#     now best-effort.
#   * the SSH calls did not pass `--namespace`, so they ran in router-ssh.py's
#     default of h199a-wan while dropbear binds 192.0.2.1, which is in
#     h199a-lan. They now pass `--namespace h199a-lan`.
#   * `tomada` was called as a bare name; it is ~/.local/bin/tomada.
#   * a missing dumper blob or perst-w kernel now fails with a clear message
#     before anything is powered on.
#
# `--no-ramboot` skips step 1 and talks to an already-booted dumper, which is
# what you want when the unit is already up in perst-w.
set -euo pipefail

BENCH=$BENCH
REPO=$BENCH/openwrt-zte-h199a
TOMATO=$HOME/.local/bin/tomada
UART_DEV=/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0
DUMPER=$BENCH/logs/build-20261110/nand-dump-ecc-locations
DUMPER_SHA=1ef6130dffd432e68362f648963b82f8fcdbcf933c7501cecfe11b7db139fa90
PERSTW=$BENCH/h199a-firmware/perst-w.kernel

RUMBOOT=1
L=""
for arg in "$@"; do
	case "$arg" in
	--no-ramboot) RUMBOOT=0 ;;
	-*) echo "ro-nand-dump: unknown option $arg" >&2; exit 2 ;;
	*) L=$arg ;;
	esac
done
[ -n "$L" ] || { echo "usage: ro-nand-dump.sh <label> [--no-ramboot]" >&2; exit 2; }

cd "$BENCH"

# --- preflight: fail before touching power ------------------------------------
[ -x "$TOMATO" ] || { echo "ro-nand-dump: $TOMATO not found" >&2; exit 1; }
[ -f "$DUMPER" ] || { echo "ro-nand-dump: dumper blob missing: $DUMPER" >&2; exit 1; }
got=$(sha256sum "$DUMPER" | cut -d' ' -f1)
[ "$got" = "$DUMPER_SHA" ] || {
	echo "ro-nand-dump: dumper blob hash mismatch ($got != $DUMPER_SHA)" >&2; exit 1; }
if [ "$RUMBOOT" = 1 ]; then
	[ -f "$PERSTW" ] || { echo "ro-nand-dump: perst-w kernel missing: $PERSTW" >&2; exit 1; }
	[ -e "$UART_DEV" ] || { echo "ro-nand-dump: UART adapter not present: $UART_DEV" >&2; exit 1; }
fi

D="$BENCH/logs/$L-nand"
if [ -e "$D" ]; then
	echo "ro-nand-dump: $D already exists; refusing to overwrite a dump" >&2
	exit 1
fi

# --- 1. RAM-boot the read-only dumper -----------------------------------------
if [ "$RUMBOOT" = 1 ]; then
	T="$BENCH/logs/tftp-$L-perstw-$(date +%Y%m%d-%H%M%S)"
	mkdir -p "$T"
	ln -sf "$PERSTW" "$T/kernel"
	# Transient unit: it usually does not exist, so this is best-effort.
	sudo -n systemctl stop h199a-tftp 2>/dev/null || true
	sudo -n systemctl reset-failed h199a-tftp 2>/dev/null || true
	sleep 1
	sudo -n systemd-run --unit=h199a-tftp --property=Restart=no \
		/usr/sbin/ip netns exec h199a-wan \
		/usr/bin/python3 -u "$REPO/tools/tftp-readonly.py" --root "$T" --bind 192.168.1.100 \
		>/dev/null 2>&1 || { echo "ro-nand-dump: could not start the TFTP server" >&2; exit 1; }
	sleep 2
	timeout 300 python3 "$REPO/tools/ramboot-h199a-tftp.py" --execute --storage-backend native-ro \
		--device "$UART_DEV" \
		--raw-log "$BENCH/logs/uart.raw" --image "$PERSTW" --image-name h199a-perst-w \
		--tftp-name kernel --output "$BENCH/logs/ram-perst-w-$L-$(date +%Y%m%d-%H%M%S)" \
		--relay "$TOMATO" | tail -1
	timeout 400 python3 tools/bootstrap-phone-test.py "$L" --wired-only | tail -1
fi

# --- 2. dump twice, host and device must agree --------------------------------
mkdir -m 700 "$D"

# shellcheck disable=SC2016 # $s are remote
python3 tools/router-ssh.py --namespace h199a-lan \
	'cat >/tmp/nand-dump-ecc-locations && chmod 700 /tmp/nand-dump-ecc-locations && echo "'"$DUMPER_SHA"'  /tmp/nand-dump-ecc-locations" | sha256sum -c && mknod /dev/mtd0 c 90 0 && cat /sys/class/mtd/mtd0/flags' \
	--input "$DUMPER" --output "$D/upload.txt" --timeout 30

python3 tools/router-ssh.py --namespace h199a-lan \
	'/tmp/nand-dump-ecc-locations --corrected /dev/mtd0 2>/tmp/ecc-1.log' \
	--output "$D/corrected-oob-1.partial" --quiet --timeout 560

python3 tools/router-ssh.py --namespace h199a-lan \
	'cat /tmp/ecc-1.log' --output "$D/ecc-1.log" --quiet --timeout 20

python3 tools/router-ssh.py --namespace h199a-lan \
	'/tmp/nand-dump-ecc-locations --corrected /dev/mtd0 2>/tmp/ecc-2.log | sha256sum; tail -1 /tmp/ecc-2.log' \
	--output "$D/dump-2-ondevice-hash.txt" --timeout 300

# --- 3. power off -------------------------------------------------------------
"$TOMATO" off >/dev/null 2>&1 || true
sleep 3

# --- 4. report, and fail if the two dumps disagree ----------------------------
host_sum=$(sha256sum < "$D/corrected-oob-1.partial")
dev_sum=$(head -1 "$D/dump-2-ondevice-hash.txt")
echo "host  $host_sum"
echo "devic $dev_sum"
tail -1 "$D/ecc-1.log"
echo "D=$D"

if [ "${host_sum%% *}" != "${dev_sum%% *}" ]; then
	echo "ro-nand-dump: HOST AND DEVICE HASHES DISAGREE -- dump is not trustworthy" >&2
	exit 1
fi
echo "ro-nand-dump: OK, two dumps agree"
