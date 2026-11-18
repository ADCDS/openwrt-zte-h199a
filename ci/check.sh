#!/usr/bin/env bash
# ci/check.sh — build-side checks that need no bench hardware.
#
# SCOPE, stated honestly: none of this would have caught any of the retractions
# in this project's history. Those came from single-trial inference and from
# register semantics recovered without a datasheet, and the thing that catches
# those is `boot-trial.sh` and the replication discipline in the docs, not a
# linter. What this DOES catch is the other failure mode - a tree that no longer
# builds, a DTS that no longer compiles, a patch that no longer applies - which
# is cheap to check and embarrassing to discover on the bench with a UART
# cable in hand.
#
# Usage:
#   ./ci/check.sh            # everything that does not need a built tree
#   ./ci/check.sh --full     # also compile the kernel (needs ./openwrt built)
set -u
cd "$(dirname "$0")/.." || exit 2
FAIL=0
say() { printf '%s\n' "$*"; }
ok()  { say "  OK    $1"; }
bad() { say "  FAIL  $1"; FAIL=$((FAIL + 1)); }

say "ci/check $(date '+%F %T')"

# Locate the unpacked kernel tree, if the recipe has been built at least once.
KTREE=$(ls -d openwrt/build_dir/target-*/linux-*/linux-6.6.* 2>/dev/null | head -1)
[ -n "$KTREE" ] && say "  .. kernel tree: $KTREE" || say "  .. kernel tree not unpacked; skipping patch-target checks"

# 1. Every patch in patches-6.6 must be well-formed and reference real files.
for p in files/target/linux/armsr/patches-6.6/*.patch; do
	[ -e "$p" ] || continue
	if ! grep -q '^--- a/' "$p"; then
		bad "$(basename "$p"): no '--- a/' header"
		continue
	fi
	# These patch the KERNEL tree, which lives under build_dir once the
	# recipe has unpacked it - not under ./openwrt itself. Only verify
	# targets when that tree actually exists, so a fresh clone still passes.
	missing=""
	if [ -n "${KTREE:-}" ]; then
		while read -r f; do
			[ -e "$KTREE/$f" ] || missing="$missing $f"
		done < <(sed -n 's|^--- a/||p' "$p")
	fi
	if [ -n "$missing" ]; then
		bad "$(basename "$p"): target(s) absent from kernel tree:$missing"
	else
		ok "$(basename "$p") well-formed"
	fi
done

# 2. Kernel sources the overlay adds must at least be syntactically plausible C
#    and must not have picked up conflict markers or tabs/space damage.
for f in $(find files/target/linux/armsr/files-6.6 -name '*.c' -o -name '*.h'); do
	if grep -qE '^(<<<<<<<|>>>>>>>|=======)$' "$f"; then
		bad "$f: conflict marker"
	fi
done
ok "no conflict markers in added kernel sources"

# 3. The DTS must reference only nodes it defines. Cheapest useful check without
#    a compiler: every &label used must exist as `label:` somewhere.
DTS=files/target/linux/armsr/files-6.6/arch/arm/boot/dts/zte/zx279128s-zte-h199a.dts
if [ -f "$DTS" ]; then
	badref=0
	for lbl in $(grep -o '&[a-zA-Z_][a-zA-Z0-9_]*' "$DTS" | sort -u | tr -d '&'); do
		grep -q "^[[:space:]]*$lbl:" "$DTS" || badref=1
	done
	[ "$badref" = 0 ] && ok "DTS label references resolve" \
			  || bad "DTS references an undefined label"
else
	bad "DTS not found at $DTS"
fi

# 4. seed.config must not contain duplicate symbols - a duplicate silently wins
#    in whichever order defconfig happens to read it.
# Include '-' in the symbol class: package symbols look like
# CONFIG_PACKAGE_kmod-mt7603, and stopping at the hyphen makes every kmod
# package collide into one false duplicate.
dups=$(grep -oE '^CONFIG_[A-Za-z0-9_-]+' seed.config 2>/dev/null | sort | uniq -d)
[ -z "$dups" ] && ok "seed.config has no duplicate symbols" \
	       || bad "seed.config duplicates: $dups"

# 5. Anything that must never ship enabled.
if grep -q '^CONFIG_ZX279128_ETH_DEBUG=y' files/target/linux/armsr/config-6.6 2>/dev/null; then
	bad "config-6.6 enables ZX279128_ETH_DEBUG - /proc/zx_eth_poke must not ship"
else
	ok "ZX279128_ETH_DEBUG not enabled in the shipped config"
fi
# Packet-processor table access is not hardware-qualified (docs/PP-OFFLOAD.md).
if grep -q '^CONFIG_ZX279128_PP_TABLES=y' files/target/linux/armsr/config-6.6 2>/dev/null; then
	bad "config-6.6 enables ZX279128_PP_TABLES before its hardware qualification"
else
	ok "ZX279128_PP_TABLES not enabled in the shipped config"
fi
# The single-flow install test writes into tables the datapath walks
# (docs/PP-FLOW.md); it must never ship enabled.
if grep -q '^CONFIG_ZX279128_PP_FLOW_TEST=y' files/target/linux/armsr/config-6.6 2>/dev/null; then
	bad "config-6.6 enables ZX279128_PP_FLOW_TEST - the flow write path must not ship"
else
	ok "ZX279128_PP_FLOW_TEST not enabled in the shipped config"
fi
# The hardware flow-offload path writes CLA/PM tables the datapath walks and
# the hardware match is not qualified (docs/PP-KEY.md); it must never ship.
if grep -q '^CONFIG_ZX279128_PP_OFFLOAD=y' files/target/linux/armsr/config-6.6 2>/dev/null; then
	bad "config-6.6 enables ZX279128_PP_OFFLOAD - the hardware offload path must not ship"
else
	ok "ZX279128_PP_OFFLOAD not enabled in the shipped config"
fi

# 6. Shipped shell must parse. These run on a device that is reached only over a
#    UART cable, so a syntax error costs a power cycle and a log dig to find.
shbad=""
for f in $(find files -path '*/base-files/*' -type f 2>/dev/null); do
	head -1 "$f" | grep -q '^#!/bin/sh' || continue
	bash -n "$f" 2>/dev/null || shbad="$shbad $f"
done
[ -z "$shbad" ] && ok "shipped shell scripts parse" \
		|| bad "shell syntax error in:$shbad"

pybad=""
for f in tools/*.py; do
	[ -e "$f" ] || continue
	python3 -m py_compile "$f" 2>/dev/null || pybad="$pybad $f"
done
rm -rf tools/__pycache__
[ -z "$pybad" ] && ok "tools/*.py compile" || bad "python syntax error in:$pybad"

# 7. The image recipe must refuse to run flash-prep.py without a header
#    template.
#
# This is here because of a specific failure: H199A_REFERENCE resolved empty,
# make expanded the empty variable away, flash-prep.py received its arguments
# shifted by one position, and the build died with a FileNotFoundError naming
# its own OUTPUT path. Half an hour went into looking for a missing output. A
# missing input has to fail at the input.
IMK=files/target/linux/armsr/image/Makefile
if [ -f "$IMK" ]; then
	if grep -q 'H199A_REFERENCE' "$IMK" && \
	   grep -q '\-s "\$(H199A_REFERENCE)"' "$IMK"; then
		ok "image recipe guards the header template"
	else
		bad "image recipe runs flash-prep.py without checking H199A_REFERENCE"
	fi
fi

# Normal builds must retain the kmod packages' autoload entries.
for name in mt7603 mt7615e; do
	f="files/files/etc/modules.d/$name"
	if [ ! -e "$f" ] && [ ! -L "$f" ]; then
		ok "$name autoload is not overridden by the rootfs overlay"
	else
		bad "$name autoload is overridden by the rootfs overlay"
	fi
done
if [ -e files/target/linux/armsr/base-files/etc/init.d/zx-wifi-late ]; then
	bad "retired delayed WiFi service remains in the rootfs overlay"
else
	ok "WiFi uses normal module loading and netifd"
fi

if PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests; then
	ok "binary image regression tests"
else
	bad "binary image regression tests"
fi

# Optional: real compile. Only meaningful once ./openwrt has been built once.
if [ "${1:-}" = "--full" ]; then
	if [ -d openwrt ]; then
		say "  .. compiling target/linux (this is slow)"
		if (cd openwrt && make target/linux/compile -j"${JOBS:-2}" >/tmp/ci-compile.log 2>&1); then
			ok "kernel compiles"
		else
			bad "kernel compile failed - see /tmp/ci-compile.log"
		fi
	else
		bad "--full requested but ./openwrt does not exist"
	fi
fi

say ""
[ "$FAIL" = 0 ] && { say "VERDICT: ci OK"; exit 0; }
say "VERDICT: $FAIL check(s) FAILED"
exit 1
