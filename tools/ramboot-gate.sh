#!/usr/bin/env bash
# ramboot-gate.sh - N consecutive unattended TFTP RAM boots, pass/fail counted.
#
# WHY THIS EXISTS
#
# Every capability claim in this port has at some point rested on a single boot,
# and this board has repeatedly shown single boots to be misleading. The
# ~22% Wi-Fi firmware-load boot hang in particular looked like "the image is
# broken" three times in a row before it was counted and recognised.
#
# This is the RAM-boot counterpart to ../soak.sh (which cold-boots the FLASHED
# image). It writes nothing to flash, so it is safe to run against a candidate
# kernel before committing to a flash cycle.
#
# Usage:  ./tools/ramboot-gate.sh <uimage-name-in-/srv/tftp> [iterations]
#         N=10 is the gate; anything less than N/N is a fail.
#
# Two guards are load-bearing, both learned the hard way:
#
#  * The logger is restarted through ../rig-reset.sh rather than a `pkill -f`.
#    A kill filter that names its target matches the shell running it - that
#    exact mistake killed this session's shell twice and each time looked like
#    the device had died.
#  * The log is sliced per boot by byte offset taken BEFORE the power cycle.
#    Grepping the whole log scores an earlier boot's success against a later
#    boot's failure.
set -u

IMG="${1:?usage: ramboot-gate.sh <uimage> [iterations]}"
N="${2:-10}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BENCH="$(cd "$ROOT/.." && pwd)"      # workspace root holds the rig scripts
PORT="${PORT:-/dev/h199a-uart}"
LOG="${LOG:-$BENCH/logs/uart.log}"

[ -r "$LOG" ] || { echo "ERROR: no UART log at $LOG" >&2; exit 1; }
[ -r "/srv/tftp/$IMG" ] || { echo "ERROR: /srv/tftp/$IMG not readable" >&2; exit 1; }

pass=0; fail=0
for i in $(seq 1 "$N"); do
	start=$(stat -c%s "$LOG")

	"$BENCH/rig-reset.sh" >/dev/null 2>&1
	setsid "$BENCH/catch-bootmode-v2.sh" >/dev/null 2>&1 </dev/null &
	disown 2>/dev/null || true   # rig-reset kills it later; no job-control noise
	sleep 2
	timeout 20 tomada off >/dev/null 2>&1; sleep 6
	timeout 20 tomada on  >/dev/null 2>&1

	# wait for the U-Boot prompt
	ub=0
	for _ in $(seq 1 20); do
		sleep 5
		tail -c 2000 "$LOG" | tr -d '\0' | grep -q '=> *$' && { ub=1; break; }
	done
	"$BENCH/rig-reset.sh" >/dev/null 2>&1
	if [ "$ub" != 1 ]; then
		echo "boot $i: FAIL (never reached the U-Boot prompt)"
		fail=$((fail+1)); continue
	fi

	printf 'tftp 0x42000000 %s\r' "$IMG" > "$PORT"; sleep 24
	printf 'bootm 0x42000000\r' > "$PORT"

	up=0
	for _ in $(seq 1 32); do
		sleep 5
		tail -c 6000 "$LOG" | tr -d '\0' | grep -q "Please press Enter" && { up=1; break; }
	done

	slice=$(tail -c +$((start+1)) "$LOG" | tr -d '\0')
	# CASE-SENSITIVE on purpose. `grep -i ... 'BUG:'` matches the perfectly
	# healthy line "printk: debug: ignoring loglevel setting", so every good
	# boot scored as a fault and the gate reported 0/3 on a working board.
	# The kernel spells all of these with the capitalisation below.
	bad=$(printf '%s' "$slice" | grep -acE 'Oops|Unable to handle kernel|Kernel panic|Unhandled fault|unaligned access|\bBUG:')

	if [ "$up" = 1 ] && [ "$bad" -eq 0 ]; then
		echo "boot $i: pass"
		pass=$((pass+1))
	else
		echo "boot $i: FAIL (userspace=$up faults=$bad)"
		fail=$((fail+1))
	fi
done

echo "=== GATE RESULT: $pass/$N pass, $fail fail ==="
[ "$fail" -eq 0 ]
