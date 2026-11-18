#!/usr/bin/env bash
# reboot-h199a-r207.sh - power-cycle the H199A through the Ekaza smart plug and
# watch the host UART log for boot progression.
#
# Diagnostics only: no flash writes, no saveenv, no TX to the router. The host
# uart-log.sh remains the sole serial reader; this script only reads the logfile
# and toggles the relay.
#
# Usage: ./tools/reboot-h199a-r207.sh [off-seconds] [watch-seconds]
set -u

RIG=~/dev/routers/h199a
LOG="${LOG:-$RIG/logs/uart.log}"
OFF_S="${1:-8}"
WATCH_S="${2:-180}"
STAMP=$(date +%H%M%S)
OUT="${OUT:-$RIG/logs/reboot-$STAMP}"

say() { printf '[%s] %s\n' "$(date +%T)" "$*"; }

relay() { timeout 45 tomada status 2>&1 | tr '\n' ' '; }

[ -r "$LOG" ] || { echo "ERROR: no UART log at $LOG" >&2; exit 1; }

MARK=$(stat -c%s "$LOG")
say "log=$LOG start_offset=$MARK"
say "relay before: $(relay)"
say "POWER OFF"
timeout 45 tomada off 2>&1
sleep "$OFF_S"
say "relay off: $(relay)"
say "POWER ON"
timeout 45 tomada on 2>&1

deadline=$(( $(date +%s) + WATCH_S ))
declare -A seen=()
while [ "$(date +%s)" -lt "$deadline" ]; do
	sleep 3
	# slice the log from the pre-cycle offset; NUL-strip then keep text runs
	tail -c +$((MARK + 1)) "$LOG" 2>/dev/null | tr -d '\0' > "$OUT.rx.bin"
	for pat in \
		'Press 1 means entering boot mode' \
		'Hit any key to stop autoboot' \
		'U-Boot 2013.04' \
		'Starting kernel' \
		'Booting Linux' \
		'Please press Enter' \
		'login:' ; do
		if grep -qaF -- "$pat" "$OUT.rx.bin" 2>/dev/null; then
			if [ -z "${seen[$pat]:-}" ]; then
				seen[$pat]=1
				say "MARKER: $pat"
			fi
		fi
	done
	last=$(strings -n 8 "$OUT.rx.bin" 2>/dev/null | tail -1)
	say "tail: ${last:-(no text yet)}"
	if [ -n "${seen['Please press Enter']:-}" ] || [ -n "${seen['login:']:-}" ]; then
		say "userspace console reached; stopping watch"
		break
	fi
done

say "markers seen: ${!seen[*]:-none}"
say "relay after: $(relay)"
say "rx slice saved to $OUT.rx.bin ($(stat -c%s "$OUT.rx.bin" 2>/dev/null) bytes)"
