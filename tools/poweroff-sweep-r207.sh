#!/usr/bin/env bash
# poweroff-sweep-r207.sh - how long must the relay stay open before the H199A
# actually resets? R206 powered off only ~7s and got 1 byte / no banner 4/4 times.
#
# Read-only w.r.t. the router. Toggles the relay and reads the host UART log.
# Evidence written inside the workspace.
set -u

RIG=~/dev/routers/h199a
L="${LOG:-$RIG/logs/uart.log}"
OUT="${1:?usage: poweroff-sweep-r207.sh <out-prefix-inside-workspace>}"
shift || true
OFFS=("$@")
[ "${#OFFS[@]}" -gt 0 ] || OFFS=(4 7 10 15)

say() { printf '[%s] %s\n' "$(date +%T)" "$*" | tee -a "$OUT.log"; }
: > "$OUT.log"

say "off-time sweep: ${OFFS[*]}"
for OFF in "${OFFS[@]}"; do
	MARK=$(stat -c%s "$L")
	say "=== OFF=${OFF}s (mark=$MARK) ==="
	timeout 45 tomada off >/dev/null 2>&1
	sleep "$OFF"
	timeout 45 tomada on >/dev/null 2>&1

	got=no
	for _ in $(seq 1 15); do
		sleep 3
		if tail -c +$((MARK + 1)) "$L" 2>/dev/null | strings -n 6 |
			grep -qaE 'Press 1 means entering boot mode|cspboot'; then
			got=yes
			break
		fi
	done
	bytes=$(( $(stat -c%s "$L") - MARK ))
	say "OFF=${OFF}s -> fresh_boot=$got rx_bytes=$bytes"
	tail -c +$((MARK + 1)) "$L" > "$OUT.off${OFF}.rx.bin" 2>/dev/null
	strings -n 5 "$OUT.off${OFF}.rx.bin" > "$OUT.off${OFF}.rx.txt" 2>/dev/null
	say "  banner=$(grep -acF 'Press 1 means entering boot mode' "$OUT.off${OFF}.rx.txt" 2>/dev/null)" \
		"cspboot=$(grep -acF 'cspboot' "$OUT.off${OFF}.rx.txt" 2>/dev/null)" \
		"kernel=$(grep -acE '^\[ +[0-9]+\.[0-9]+\]' "$OUT.off${OFF}.rx.txt" 2>/dev/null)"

	if [ "$got" = yes ]; then
		for _ in $(seq 1 25); do
			sleep 3
			if tail -c +$((MARK + 1)) "$L" 2>/dev/null | strings -n 8 |
				grep -qa 'Please press Enter'; then
				break
			fi
		done
		say "  board reached userspace"
	fi
done
say "sweep done"
