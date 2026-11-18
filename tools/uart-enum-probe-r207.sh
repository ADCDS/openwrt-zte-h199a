#!/usr/bin/env bash
# uart-enum-probe-r207.sh - does the CP210x re-enumerate when the router is
# power-cycled, and does the normal logger keep receiving through it?
#
# Read-only w.r.t. the router: only toggles the smart plug and reads sysfs/log.
# Writes its evidence inside the workspace (the only writable path in-sandbox).
set -u

RIG=~/dev/routers/h199a
L="${LOG:-$RIG/logs/uart.log}"
OUT="${1:?usage: uart-enum-probe-r207.sh <out-prefix-inside-workspace>}"
DEVP=/sys/bus/usb/devices/3-5

say() { printf '[%s] %s\n' "$(date +%T)" "$*" | tee -a "$OUT.log"; }

snap() {
	printf 'devnum=%s dir_mtime=%s tty=%s ttydir_mtime=%s' \
		"$(cat "$DEVP/devnum" 2>/dev/null)" \
		"$(stat -c %y "$DEVP" 2>/dev/null)" \
		"$(cat /sys/class/tty/ttyUSB0/dev 2>/dev/null)" \
		"$(stat -c %y /sys/class/tty/ttyUSB0 2>/dev/null)"
}

: > "$OUT.log"
MARK=$(stat -c%s "$L")
say "start log=$L offset=$MARK"
say "BEFORE  $(snap)"
say "POWER OFF"
timeout 45 tomada off >/dev/null 2>&1
sleep 8
say "OFF     $(snap)"
say "POWER ON"
timeout 45 tomada on >/dev/null 2>&1
i=0
while [ "$i" -lt 30 ]; do
	i=$((i + 1))
	sleep 3
	say "t+$((i * 3))s $(snap) logsize=$(stat -c%s "$L")"
	if tail -c +$((MARK + 1)) "$L" 2>/dev/null | strings -n 8 | grep -qa 'Please press Enter'; then
		say "userspace console reached"
		break
	fi
done
say "AFTER   $(snap)"
say "log rx bytes added: $(( $(stat -c%s "$L") - MARK ))"
tail -c +$((MARK + 1)) "$L" > "$OUT.rx.bin" 2>/dev/null
strings -n 5 "$OUT.rx.bin" > "$OUT.rx.txt" 2>/dev/null
say "boot-entry banner in slice: $(grep -acF 'Press 1 means entering boot mode' "$OUT.rx.txt" 2>/dev/null)"
say "cspboot line in slice:      $(grep -acF 'cspboot' "$OUT.rx.txt" 2>/dev/null)"
say "kernel lines in slice:      $(grep -acE '^\[ +[0-9]+\.[0-9]+\]' "$OUT.rx.txt" 2>/dev/null)"
say "saved $OUT.rx.txt"
