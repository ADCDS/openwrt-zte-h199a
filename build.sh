#!/usr/bin/env bash
# Build mainline OpenWrt for the ZTE ZXHN H199A (ZTE/Sanechips ZX279128S,
# dual Cortex-A9, four Ethernet ports). Follows the openwrt-dlink-dir842-r1 recipe
# pattern: pinned upstream tree + files/ overlay + seed config.
#
# The pinned upstream tree lacks this board support. This overlay supplies
# its platform, clocks, pin control and peripheral drivers on armsr/armv7.
# Production NAND, web installation and native upgrades have been qualified
# on one unit; see docs/PORT-STATUS.md for the limits.
#
#   H199A_MT7603_EEPROM=/private/MT7603E_EEPROM.bin ./build.sh # normal build
#   BRINGUP=1 ./build.sh  # bring-up build: adds the /proc debug interfaces
#   SEED=other.config ./build.sh
#   JOBS=2 ./build.sh    # bounded local build parallelism
#   BOOT_PROFILE=diagnostic BRINGUP=1 ./build.sh # readonly shell, radios disabled
#   PREPARE_ONLY=1 ./build.sh # prepare pinned sources/config without compiling
#   ETH_FORCE_INIT=1 DIAGNOSTIC_RADIOS=1 BOOT_PROFILE=diagnostic BRINGUP=1 ./build.sh
#
# All four Ethernet ports are described at runtime; ETH_PORT is retired.
#
# BRINGUP turns on CONFIG_ZX279128_ETH_DEBUG, which is what creates
# /proc/zx_eth_{regs,poke,reinit}. These are diagnostic instruments:
# register access, arbitrary physical read/modify/write, and a manual reset
# endpoint. They are not present in production images.
# They
# must never ship - see the driver Kconfig.
#
# Reinitialization is destructive and remains experimental. Bulk re-prime
# was removed because it returned buffer indices without ownership proof.
#
# NOT what BRINGUP does, and why: an earlier version of this built the Ethernet
# driver as a module (=m) on the theory that insmod/rmmod would beat a
# build-flash-boot cycle. It would not, for two reasons.
#   1. Module parameters are already writable at runtime on the BUILT-IN driver
#      via /sys/module/zx279128_eth/parameters/* - every one of them is 0644.
#      Round 251 swept rx_release exactly that way. =m adds nothing here.
#   2. An =m symbol with no KernelPackage definition builds a .ko into build_dir
#      that never reaches the image, and there would be no network to fetch it
#      over anyway - this driver IS the network.
# Code changes still need a rebuild, but a TFTP RAM boot (./boot-h199a.sh)
# already avoids reflashing for those.
#
# Artifacts for on-device boot (TFTP from serverip=192.168.1.100):
#   openwrt/build_dir/target-arm_cortex-a9+vfpv3-d16_musl_eabi/linux-armsr_armv7/zImage
#   .../arch/arm/boot/dts/zte/zx279128s-zte-h199a.dtb
#   openwrt/bin/targets/armsr/armv7/*initramfs-kernel.bin
set -e
cd "$(dirname "$0")"
SELF_DIR="$(pwd)"
BOOT_PROFILE="${BOOT_PROFILE:-normal}"
RAM_ROOT_TEST="${RAM_ROOT_TEST:-0}"
case "$RAM_ROOT_TEST" in
	0|1) ;;
	*) echo "ERROR: RAM_ROOT_TEST must be 0 or 1" >&2; exit 1 ;;
esac
case "$BOOT_PROFILE" in
	normal|diagnostic|production) ;;
	*) echo "ERROR: BOOT_PROFILE must be normal, diagnostic or production" >&2; exit 1 ;;
esac
PRODUCTION_QUALIFY="${PRODUCTION_QUALIFY:-0}"
case "$PRODUCTION_QUALIFY" in
	0|1) ;;
	*) echo "ERROR: PRODUCTION_QUALIFY must be 0 or 1" >&2; exit 1 ;;
esac
if [ "$PRODUCTION_QUALIFY" = 1 ] && [ "$BOOT_PROFILE" != production ]; then
	echo "ERROR: PRODUCTION_QUALIFY requires BOOT_PROFILE=production" >&2
	exit 1
fi
if [ "$BOOT_PROFILE" = production ] &&
   { [ "${BRINGUP:-0}" = 1 ] || [ "${NAND_UBI_TEST:-0}" = 1 ] ||
     [ "${ETH_FORCE_INIT:-0}" = 1 ] || [ "${DIAGNOSTIC_RADIOS:-0}" = 1 ] ||
     [ "${NAND_ONDIE_PROBE:-0}" = 1 ]; }; then
	echo "ERROR: BOOT_PROFILE=production is a release profile; no diagnostic overrides" >&2
	exit 1
fi
# PP_TABLES=1 compiles the unqualified packet-processor table access
# (docs/PP-OFFLOAD.md) into a DIAGNOSTIC RAM-boot image only.
PP_TABLES="${PP_TABLES:-0}"
case "$PP_TABLES" in
	0|1) ;;
	*) echo "ERROR: PP_TABLES must be 0 or 1" >&2; exit 1 ;;
esac
if [ "$PP_TABLES" = 1 ] && [ "$BOOT_PROFILE" != diagnostic ]; then
	echo "ERROR: PP_TABLES=1 is for diagnostic RAM-boot qualification images only (docs/PP-OFFLOAD.md)" >&2
	exit 1
fi
# PP_FLOW_TEST=1 adds the strictly-gated single-flow install write path
# (docs/PP-FLOW.md) on top of PP_TABLES=1. Diagnostic RAM-boot images only.
PP_FLOW_TEST="${PP_FLOW_TEST:-0}"
case "$PP_FLOW_TEST" in
	0|1) ;;
	*) echo "ERROR: PP_FLOW_TEST must be 0 or 1" >&2; exit 1 ;;
esac
if [ "$PP_FLOW_TEST" = 1 ] && [ "$PP_TABLES" != 1 ]; then
	echo "ERROR: PP_FLOW_TEST=1 requires PP_TABLES=1 (docs/PP-FLOW.md)" >&2
	exit 1
fi
if [ "$RAM_ROOT_TEST" = 1 ] && [ "$BOOT_PROFILE" = production ]; then
	echo "ERROR: production RAM qualification uses PRODUCTION_QUALIFY=1, not RAM_ROOT_TEST=1" >&2
	exit 1
fi
if [ "$RAM_ROOT_TEST" = 1 ] &&
   { [ "$BOOT_PROFILE" != normal ] || [ "${BRINGUP:-0}" = 1 ] ||
     [ "${NAND_UBI_TEST:-0}" = 1 ]; }; then
	echo "ERROR: RAM_ROOT_TEST requires normal startup, release Ethernet and no diagnostic NAND profile" >&2
	exit 1
fi
export H199A_RAM_ROOT_TEST="$RAM_ROOT_TEST"
# The production-policy qualification image is a RAM root like the normal one,
# but compiled with the production write policy instead of the diagnostic guard.
H199A_RAM_ROOT="$RAM_ROOT_TEST"
[ "$PRODUCTION_QUALIFY" = 1 ] && H199A_RAM_ROOT=1
export H199A_BOOT_PROFILE="$BOOT_PROFILE"
export H199A_PRODUCTION_QUALIFY="$PRODUCTION_QUALIFY"
export H199A_RAM_ROOT
if grep -q '^CONFIG_SPI_ZX279128=y' files/target/linux/armsr/config-6.6 &&
   { [ "${NAND_ONDIE_PROBE:-0}" = 1 ] || [ "${NAND_ONDIE_PROBE_ALL:-0}" = 1 ]; }; then
	echo "ERROR: native SPI-NAND uses chip ECC and DT read-only protection; legacy NAND_ONDIE_PROBE flags do not apply" >&2
	exit 1
fi
if [ "${NAND_ONDIE_PROBE:-0}" = 1 ] && [ "$BOOT_PROFILE" != diagnostic ]; then
	echo "ERROR: NAND_ONDIE_PROBE requires BOOT_PROFILE=diagnostic" >&2
	exit 1
fi
if [ "${NAND_ONDIE_PROBE_ALL:-0}" = 1 ] && [ "${NAND_ONDIE_PROBE:-0}" != 1 ]; then
	echo "ERROR: NAND_ONDIE_PROBE_ALL requires the read-only NAND_ONDIE_PROBE=1 mode" >&2
	exit 1
fi
if { [ "${ETH_FORCE_INIT:-0}" = 1 ] || [ "${DIAGNOSTIC_RADIOS:-0}" = 1 ]; } &&
   { [ "$BOOT_PROFILE" != diagnostic ] || [ "${BRINGUP:-0}" != 1 ]; }; then
	echo "ERROR: diagnostic Ethernet/radio overrides require BOOT_PROFILE=diagnostic BRINGUP=1" >&2
	exit 1
fi
if [ "${NAND_UBI_TEST:-0}" = 1 ] &&
   { [ "$BOOT_PROFILE" != diagnostic ] || [ "${BRINGUP:-0}" != 1 ]; }; then
	echo "ERROR: NAND_UBI_TEST requires BOOT_PROFILE=diagnostic BRINGUP=1" >&2
	exit 1
fi
case "${JOBS:-2}" in
	''|*[!0-9]*|0) echo "ERROR: JOBS must be a positive integer" >&2; exit 1 ;;
esac
command -v readelf >/dev/null || {
	echo "ERROR: readelf is required for build-profile verification; install host binutils" >&2
	exit 1
}

# Calibration belongs to the owner. Validate before cloning/updating anything,
# and keep its generated include and binary inside the ignored build tree.
if [ -n "${H199A_MT7603_EEPROM:-}" ]; then
	command -v fdtget >/dev/null || {
		echo "ERROR: fdtget is required; install the host device-tree-compiler package" >&2
		exit 1
	}
	H199A_MT7603_EEPROM=$(realpath -- "$H199A_MT7603_EEPROM")
	python3 "$SELF_DIR/tools/h199a-calibration.py" check "$H199A_MT7603_EEPROM"
elif [ "$BOOT_PROFILE" = normal ] || [ "$BOOT_PROFILE" = production ]; then
	echo "ERROR: $BOOT_PROFILE builds require H199A_MT7603_EEPROM from tools/extract-stock-calibration.py; see docs/WIFI.md" >&2
	exit 1
fi

PIN=a1ea57bd050c172fdc2b851824ebd9782aafb055   # openwrt-24.10 head (2026-08-20)

# ---- base tree ----------------------------------------------------------
# A dangling symlink here is not a directory, so the clone branch is taken and
# `git clone` then fails with "File exists" - which is what a fresh cloner used
# to hit as the very first step. Clear it explicitly.
if [ -L openwrt ] && [ ! -e openwrt ]; then
	echo "note: removing dangling ./openwrt symlink" >&2
	rm -f openwrt
fi

if [ ! -d openwrt ]; then
	git clone https://github.com/openwrt/openwrt
	( cd openwrt && git checkout "$PIN" )
else
	cur=$(cd openwrt && git rev-parse HEAD)
	if [ "$cur" != "$PIN" ] && [ "${FORCE_TREE:-0}" != 1 ]; then
		echo "ERROR: ./openwrt is at $cur, expected $PIN. Remove it or FORCE_TREE=1." >&2
		exit 1
	fi
fi
cd openwrt

# ---- overlay device support (path-preserving) ----------------------------
# cp -a merges but never deletes, so a file removed from files/ survives in an
# existing checkout and keeps being compiled. That is not hypothetical: it kept
# a deleted driver in the build and made the kernel fail kconfig on a symbol
# nothing set any more. Prune from a manifest of what the previous run
# installed - any listed path that no longer exists in files/ is removed -
# then regenerate it. This replaces hand-maintained retired-file lists, which
# have to be updated by hand at exactly the moment it is easiest to forget.
OVERLAY_MANIFEST=.h199a-overlay-manifest
if [ -f "$OVERLAY_MANIFEST" ]; then
	while IFS= read -r rel; do
		[ -n "$rel" ] || continue
		if [ ! -e "$SELF_DIR/files/$rel" ] && [ ! -L "$SELF_DIR/files/$rel" ]; then
			rm -f -- "$rel"
			echo "overlay: retired $rel"
		fi
	done < "$OVERLAY_MANIFEST"
fi
( cd "$SELF_DIR/files" && find . \( -type f -o -type l \) ) |
	sed 's|^\./||' | LC_ALL=C sort > "$OVERLAY_MANIFEST"
cp -a "$SELF_DIR/files/." .
# Historical retired paths, from before the manifest existed. Kept as a safety
# net: these experiments must not suppress package autoload or bypass netifd.
retired_wifi_files=(
	etc/modules.d/mt7603 etc/modules.d/mt7603e etc/modules.d/mt7615e
	etc/init.d/zx-wifi-late etc/rc.d/S99zx-wifi-late
	etc/zx-wifi-delay etc/zx-wifi-mods etc/uci-defaults/90-zx-defer-wifi
)
for overlay_dir in files target/linux/armsr/base-files; do
	for retired_path in "${retired_wifi_files[@]}"; do
		rm -f -- "$overlay_dir/$retired_path"
	done
done
# A tiny on-device tool: regenerate the bank-A header CRCs from the board's own
# header, so one image can install on any unit instead of carrying a template
# extracted from one. It is installed but NOT yet called by platform.sh - the
# boot path only changes once it has been checked against a real header on the
# bench. tests/test_header_regen.py proves it agrees with tools/flash-prep.py
# byte for byte on the host.
regen_cc=$(ls -d "$SELF_DIR"/openwrt/staging_dir/toolchain-arm_*/bin/*-gcc 2>/dev/null | head -1)
if [ -n "$regen_cc" ] && [ -f "$SELF_DIR/tools/h199a-header-regen.c" ]; then
	install -d files/usr/sbin
	regen_staging=$(ls -d "$SELF_DIR"/openwrt/staging_dir/toolchain-arm_* 2>/dev/null | head -1)
	if STAGING_DIR="$regen_staging" "$regen_cc" -O2 -static -Wall -Wextra \
			-o files/usr/sbin/h199a-header-regen \
			"$SELF_DIR/tools/h199a-header-regen.c" 2>/tmp/h199a-header-regen.log; then
		echo "==> installed /usr/sbin/h199a-header-regen"
	else
		echo "WARNING: could not build h199a-header-regen; see /tmp/h199a-header-regen.log" >&2
		rm -f files/usr/sbin/h199a-header-regen
	fi
else
	echo "==> no ARM toolchain yet; skipping h199a-header-regen"
fi
rm -f -- files/README.txt
rm -f -- files/etc/h199a-overlay-qualification
# Optional image identity stamp (/etc/h199a-image-id): lets an upgrade be
# proven to have landed, e.g. in the sysupgrade qualification.
rm -f -- files/etc/h199a-image-id
if [ -n "${H199A_IMAGE_ID:-}" ]; then
	case "$H199A_IMAGE_ID" in
		*[!A-Za-z0-9._-]*)
			echo "ERROR: H199A_IMAGE_ID may contain only A-Z a-z 0-9 . _ -" >&2
			exit 1 ;;
	esac
	mkdir -p files/etc
	printf '%s\n' "$H199A_IMAGE_ID" > files/etc/h199a-image-id
fi
if [ "$RAM_ROOT_TEST" = 1 ]; then
	mkdir -p files/etc
	printf '%s\n' 'guarded-ubi-overlay-v1' > files/etc/h199a-overlay-qualification
fi
# Target metadata scans the parent Makefile, not included subtarget files.
# Refresh it after overlaying target.mk so new features reach defconfig.
touch target/linux/armsr/Makefile
OWNER_DTS=target/linux/armsr/files-6.6/arch/arm/boot/dts/zte/zx279128s-zte-h199a.dts
python3 "$SELF_DIR/tools/h199a-calibration.py" clear "$OWNER_DTS"
if [ -n "${H199A_MT7603_EEPROM:-}" ]; then
	python3 "$SELF_DIR/tools/h199a-calibration.py" install "$OWNER_DTS" "$H199A_MT7603_EEPROM"
fi

# ---- target config additions (idempotent append) ------------------------
# ARM_GLOBAL_TIMER defaults y on multiplatform; pin it explicitly because
# the whole port depends on it (the ZX279128S has no other clocksource yet).
TGT=target/linux/armsr/config-6.6
grep -q '^CONFIG_ARM_GLOBAL_TIMER=y$' "$TGT" || \
	echo 'CONFIG_ARM_GLOBAL_TIMER=y' >> "$TGT"

# ---- bring-up variant ----------------------------------------------------
# Anchored substitutions: sed exits 0 when it matches nothing, so an unanchored
# edit whose anchor has drifted silently produces a build that is missing what
# the edit was supposed to add.
anchor() {  # anchor <expected-count> <pattern> <file>
	local n; n=$(grep -c -- "$2" "$3" || true)
	[ "$n" = "$1" ] || { echo "ERROR: anchor '$2' matched $n times (want $1) in $3" >&2; exit 1; }
}

if [ "$PP_TABLES" = 1 ]; then
	echo "==> PP_TABLES build: CONFIG_ZX279128_PP_TABLES=y (unqualified; diagnostic only)"
	anchor 1 '^# CONFIG_ZX279128_PP_TABLES is not set$' "$TGT"
	sed -i 's/^# CONFIG_ZX279128_PP_TABLES is not set$/CONFIG_ZX279128_PP_TABLES=y/' "$TGT"
	anchor 1 '^CONFIG_ZX279128_PP_TABLES=y$' "$TGT"
fi
if [ "$PP_FLOW_TEST" = 1 ]; then
	echo "==> PP_FLOW_TEST build: CONFIG_ZX279128_PP_FLOW_TEST=y (unqualified write path; diagnostic only)"
	anchor 1 '^# CONFIG_ZX279128_PP_FLOW_TEST is not set$' "$TGT"
	sed -i 's/^# CONFIG_ZX279128_PP_FLOW_TEST is not set$/CONFIG_ZX279128_PP_FLOW_TEST=y/' "$TGT"
	anchor 1 '^CONFIG_ZX279128_PP_FLOW_TEST=y$' "$TGT"
fi
if [ "${BRINGUP:-0}" = 1 ]; then
	echo "==> BRINGUP build: /proc/zx_eth_{regs,poke,reinit} enabled"
	anchor 1 '^# CONFIG_ZX279128_ETH_DEBUG is not set$' "$TGT"
	sed -i 's/^# CONFIG_ZX279128_ETH_DEBUG is not set$/CONFIG_ZX279128_ETH_DEBUG=y/' "$TGT"
	anchor 1 '^CONFIG_ZX279128_ETH_DEBUG=y$' "$TGT"
fi

# Diagnostic entry is explicit; normal images run OpenWrt's init and radio
# loading policy. Keep the required board-specific early console in both.
if [ "$BOOT_PROFILE" = diagnostic ]; then
	anchor 1 '^CONFIG_CMDLINE=".*"$' "$TGT"
	sed -i '/^CONFIG_CMDLINE=/s/"$/ ro init=\/bin\/sh panic=0"/' "$TGT"
	if [ "${DIAGNOSTIC_RADIOS:-0}" != 1 ]; then
		sed -i '/^CONFIG_CMDLINE=/s/"$/ module_blacklist=mt7615e,mt7603e"/' "$TGT"
	fi
fi
if [ "${NAND_ONDIE_PROBE:-0}" = 1 ]; then
	sed -i '/^CONFIG_CMDLINE=/s/"$/ zx_spifc_nand.ondie_probe=1"/' "$TGT"
fi
if [ "${NAND_ONDIE_PROBE_ALL:-0}" = 1 ]; then
	sed -i '/^CONFIG_CMDLINE=/s/"$/ zx_spifc_nand.ondie_probe_all=1"/' "$TGT"
fi
if [ "${ETH_FORCE_INIT:-0}" = 1 ]; then
	sed -i '/^CONFIG_CMDLINE=/s/"$/ zx279128_eth.force_dp_init=1"/' "$TGT"
fi
if [ "${NAND_UBI_TEST:-0}" = 1 ] || [ "$RAM_ROOT_TEST" = 1 ]; then
	anchor 1 '^# CONFIG_MTD_SPI_NAND_DIAGNOSTIC is not set$' "$TGT"
	sed -i 's/^# CONFIG_MTD_SPI_NAND_DIAGNOSTIC is not set$/CONFIG_MTD_SPI_NAND_DIAGNOSTIC=y/' "$TGT"
	sed -i '/^CONFIG_CMDLINE=/s/"$/ spi_zx279128.ubi_test=1 spinand.diagnostic_write_guard=1"/' "$TGT"
fi

# ---- production write policy ---------------------------------------------
# Two always-on protection layers compiled into the release kernel:
#   CONFIG_SPI_ZX279128_PRODUCTION_POLICY - transport physical allowlist
#   CONFIG_MTD_SPI_NAND_FAIL_STOP         - no bad-block marking, fail-stop,
#                                           partitioned-master-read-only
# Neither affects normal or diagnostic builds, which never set the symbols.
if [ "$BOOT_PROFILE" = production ]; then
	# config-6.6 declares both symbols "is not set" so that non-production
	# profiles never stop at a Kconfig prompt; production REPLACES that line
	# (an appended =y could be overridden by a later "is not set").
	anchor 1 '^CONFIG_SPI_ZX279128=y$' "$TGT"
	anchor 1 '^# CONFIG_SPI_ZX279128_PRODUCTION_POLICY is not set$' "$TGT"
	sed -i 's/^# CONFIG_SPI_ZX279128_PRODUCTION_POLICY is not set$/CONFIG_SPI_ZX279128_PRODUCTION_POLICY=y/' "$TGT"
	anchor 1 '^CONFIG_SPI_ZX279128_PRODUCTION_POLICY=y$' "$TGT"
	anchor 0 'CONFIG_SPI_ZX279128_PRODUCTION_POLICY is not set' "$TGT"
	anchor 1 '^# CONFIG_MTD_SPI_NAND_DIAGNOSTIC is not set$' "$TGT"
	anchor 1 '^# CONFIG_MTD_SPI_NAND_FAIL_STOP is not set$' "$TGT"
	sed -i 's/^# CONFIG_MTD_SPI_NAND_FAIL_STOP is not set$/CONFIG_MTD_SPI_NAND_FAIL_STOP=y/' "$TGT"
	anchor 1 '^CONFIG_MTD_SPI_NAND_FAIL_STOP=y$' "$TGT"
	anchor 0 'CONFIG_MTD_SPI_NAND_FAIL_STOP is not set' "$TGT"
	if [ "$PRODUCTION_QUALIFY" = 1 ]; then
		# RAM-boot the deny matrix: bank A writable at the MTD layer but the
		# transport refuses every bank-A program/erase.
		sed -i '/^CONFIG_CMDLINE=/s/"$/ spi_zx279128.production_qualify=1"/' "$TGT"
	else
		# Boot the NAND SquashFS in bank A; the transport allows bank A + the
		# UBI window and refuses everything else.
		sed -i '/^CONFIG_CMDLINE=/s/"$/ spi_zx279128.production=1"/' "$TGT"
	fi
fi

if [ "$H199A_RAM_ROOT" = 1 ]; then
	cat >> "$TGT" <<-'EOF'
	CONFIG_BLK_DEV_INITRD=y
	CONFIG_BLK_DEV_RAM=y
	CONFIG_BLK_DEV_RAM_COUNT=1
	CONFIG_BLK_DEV_RAM_SIZE=16384
	CONFIG_INITRAMFS_SOURCE=""
	EOF
	sed -i '/^CONFIG_CMDLINE=/s/"$/ root=\/dev\/ram0 rootfstype=squashfs ro panic=0"/' "$TGT"
fi

# ---- Ethernet port selection: RETIRED -------------------------------------
# ETH_PORT= used to rewrite the DTS so the driver bound a different MAC window,
# because the driver attached exactly one PHY and the datapath only worked if
# the cable happened to be on that port. It is no longer needed: the device tree
# describes all four ports under `ethernet-ports`, the driver registers a netdev
# per port (eth0..eth3 == mac0..mac3) and each drives its own PHY, so which port
# is cabled is not a build-time decision any more.
#
# Fail loudly rather than silently ignoring a stale invocation.
if [ -n "${ETH_PORT:-}" ]; then
	echo "ERROR: ETH_PORT is retired - all four ports are built in now." >&2
	echo "       Each port has its own netdev (eth0..eth3) and its own PHY." >&2
	exit 1
fi

# ---- package feeds --------------------------------------------------------
# Without this there are no feeds at all beyond `base`, so every
# CONFIG_PACKAGE_luci* in the seed is silently dropped by `make defconfig` and
# the image builds fine WITHOUT the web UI. That is exactly the failure mode
# this recipe exists to prevent, so the seed is asserted against after defconfig.
#
# Feeds are pinned the same way the base tree is. feeds.conf.default tracks
# branches, which would make two builds of the same commit differ; FEEDS_PIN
# records the revision actually used, is committed, and is what makes the image
# reproducible.
FEEDS_PIN="$SELF_DIR/feeds.pin"
if [ -f "$FEEDS_PIN" ]; then
	cp "$FEEDS_PIN" feeds.conf
else
	cp feeds.conf.default feeds.conf
fi

./scripts/feeds update -a
./scripts/feeds install -a

if [ ! -f "$FEEDS_PIN" ]; then
	# Record what we just resolved, so the next build gets the same trees.
	: > "$FEEDS_PIN"
	while read -r kind name url; do
		[ "$kind" = "src-git" ] || continue
		rev=$(cd "feeds/$name" 2>/dev/null && git rev-parse HEAD) || continue
		printf 'src-git %s %s^%s\n' "$name" "${url%%;*}" "$rev" >> "$FEEDS_PIN"
	done < feeds.conf.default
	echo "==> recorded feed pins in $FEEDS_PIN - commit it"
fi

# ---- seed + expand -------------------------------------------------------
SEED="${SEED:-seed.config}"
[ -f "$SELF_DIR/$SEED" ] || { echo "ERROR: no such seed: $SELF_DIR/$SEED" >&2; exit 1; }
cp "$SELF_DIR/$SEED" .config
make defconfig

# The kernel config is the authority here, not the seed - assert defconfig did
# not quietly drop the symbol (an unmet dependency would).
if [ "${BRINGUP:-0}" = 1 ]; then
	grep -q '^CONFIG_ZX279128_ETH_DEBUG=y$' "$TGT" || {
		echo "ERROR: BRINGUP requested but ZX279128_ETH_DEBUG is off after defconfig" >&2
		exit 1; }
fi

# Same assertion for every package the seed asks for. `make defconfig` drops a
# symbol whose dependencies are unmet WITHOUT failing, so "it built" is not
# evidence that what you selected is in the image.
miss=
while IFS= read -r sym; do
	grep -q "^$sym\$" .config || miss="$miss ${sym%%=*}"
done <<-EOSEED
	$(grep '^CONFIG_PACKAGE_.*=y$' "$SELF_DIR/$SEED")
EOSEED
if [ -n "$miss" ]; then
	echo "ERROR: seed packages dropped by defconfig (unmet dependencies?):$miss" >&2
	exit 1
fi

printf '%s\n' "$BOOT_PROFILE" > .h199a-boot-profile
printf '%s\n' "$RAM_ROOT_TEST" > .h199a-ram-root-test
printf '%s\n' "$PRODUCTION_QUALIFY" > .h199a-production-qualify

# The device-tree variant the image recipe will compile and append, so the
# calibration verification below reads the right image-*.dtb.
DTB_NAME=zx279128s-zte-h199a
if [ "$BOOT_PROFILE" = production ]; then
	if [ "$PRODUCTION_QUALIFY" = 1 ]; then
		DTB_NAME=zx279128s-zte-h199a-production-qualify
	else
		DTB_NAME=zx279128s-zte-h199a-production
	fi
fi

if [ "${PREPARE_ONLY:-0}" = 1 ]; then
	echo "Prepared pinned OpenWrt sources and $BOOT_PROFILE configuration."
	exit 0
fi

# ---- build ---------------------------------------------------------------
# First build compiles the toolchain (~30-60 min on 16 cores); subsequent
# kernel-only iterations: make target/linux/{clean,compile} -j$(nproc)
# JOBS overrides the parallelism. Worth having as a knob rather than a fixed
# $(nproc): OpenWrt's link and image steps are memory-hungry, and on a machine
# where something else already holds most of RAM, -j$(nproc) is OOM-killed with
# no diagnostic beyond "make: *** wait: No child processes. Stop." - which reads
# like a build bug and is not one. JOBS=3 completes on a 32 GB host with ~4 GB
# free.
if [ "$H199A_RAM_ROOT" = 1 ]; then
	artifact=bin/targets/armsr/armv7/openwrt-armsr-armv7-zte_h199a-squashfs-ram-rootfs.squashfs
else
	artifact=bin/targets/armsr/armv7/openwrt-armsr-armv7-zte_h199a-squashfs-sysupgrade.tar
fi
artifact_stem="${artifact%.*}"
rm -f "$artifact_stem-calibration.json" "$artifact_stem-debug.json" \
	"$artifact_stem-rootfs.json" "$artifact_stem-production.json"
make -j"${JOBS:-2}"

echo
echo "Build complete. Checking artifact:"
[ -s "$artifact" ] || { echo "ERROR: missing $artifact" >&2; exit 1; }
kernel_configs=(build_dir/target-*/linux-armsr_armv7/linux-6.6.*/.config)
if [ "${#kernel_configs[@]}" != 1 ] || [ ! -s "${kernel_configs[0]}" ]; then
	echo "ERROR: expected exactly one merged kernel configuration" >&2
	exit 1
fi
# The merged kernel configuration must carry exactly the write-protection
# profile that was asked for: both production layers on in production, both
# off everywhere else (a dropped or overridden symbol would build silently).
for sym in CONFIG_SPI_ZX279128_PRODUCTION_POLICY CONFIG_MTD_SPI_NAND_FAIL_STOP; do
	if [ "$BOOT_PROFILE" = production ]; then
		grep -qx "$sym=y" "${kernel_configs[0]}" || {
			echo "ERROR: production build but $sym is not =y in the merged kernel config" >&2; exit 1; }
	elif grep -qx "$sym=y" "${kernel_configs[0]}"; then
		echo "ERROR: $sym=y in a non-production ($BOOT_PROFILE) kernel" >&2; exit 1
	fi
done
if [ "$PP_TABLES" = 1 ]; then
	grep -qx 'CONFIG_ZX279128_PP_TABLES=y' "${kernel_configs[0]}" || {
		echo "ERROR: PP_TABLES=1 but CONFIG_ZX279128_PP_TABLES is not =y in the merged kernel config" >&2; exit 1; }
elif grep -qx 'CONFIG_ZX279128_PP_TABLES=y' "${kernel_configs[0]}"; then
	echo "ERROR: CONFIG_ZX279128_PP_TABLES=y without PP_TABLES=1" >&2; exit 1
fi
if [ "$PP_FLOW_TEST" = 1 ]; then
	grep -qx 'CONFIG_ZX279128_PP_FLOW_TEST=y' "${kernel_configs[0]}" || {
		echo "ERROR: PP_FLOW_TEST=1 but CONFIG_ZX279128_PP_FLOW_TEST is not =y in the merged kernel config" >&2; exit 1; }
elif grep -qx 'CONFIG_ZX279128_PP_FLOW_TEST=y' "${kernel_configs[0]}"; then
	echo "ERROR: CONFIG_ZX279128_PP_FLOW_TEST=y without PP_FLOW_TEST=1" >&2; exit 1
fi
expect_debug=no
[ "${BRINGUP:-0}" != 1 ] || expect_debug=yes
python3 "$SELF_DIR/tools/verify-eth-debug.py" "${kernel_configs[0]}" \
	"${kernel_configs[0]%/.config}/drivers/net/ethernet/zte/zx279128-eth.o" \
	--expect-debug "$expect_debug" > "$artifact_stem-debug.json"
if [ -n "${H199A_MT7603_EEPROM:-}" ]; then
	kernel_dtbs=(build_dir/target-*/linux-armsr_armv7/image-$DTB_NAME.dtb)
	if [ "${#kernel_dtbs[@]}" != 1 ] || [ ! -s "${kernel_dtbs[0]}" ]; then
		echo "ERROR: expected exactly one compiled H199A DTB ($DTB_NAME) for calibration verification" >&2
		exit 1
	fi
	calibration_manifest="${OWNER_DTS%/*}/h199a-owner-calibration.json"
	calibration_args=()
	# A packaged-kernel CRC check only applies to the sysupgrade tar (non-RAM).
	[ "$H199A_RAM_ROOT" = 1 ] || calibration_args=(--image "$artifact")
	python3 "$SELF_DIR/tools/h199a-calibration.py" verify "${kernel_dtbs[0]}" \
		"$calibration_manifest" "${calibration_args[@]}"
	cp "$calibration_manifest" "$artifact_stem-calibration.json"
fi
rootfs_args=(--sysupgrade "$artifact")
if [ "$RAM_ROOT_TEST" = 1 ]; then
	rootfs_args=(--image "$artifact" --qualification)
elif [ "$H199A_RAM_ROOT" = 1 ]; then
	# production-policy qualification RAM root: release userspace, no marker.
	rootfs_args=(--image "$artifact")
fi
python3 "$SELF_DIR/tools/verify-rootfs-profile.py" "${rootfs_args[@]}" \
	--unsquashfs "$SELF_DIR/openwrt/staging_dir/host/bin/unsquashfs4" \
	> "$artifact_stem-rootfs.json"

# Production factory image: validate the bank-A parts (sizes + every CRC the
# bootloader checks) and extract the loose kernel/rootfs/header for a first
# U-Boot install, next to the sysupgrade tar.
if [ "$BOOT_PROFILE" = production ] && [ "$H199A_RAM_ROOT" != 1 ]; then
	# Same template the image recipe used (it reads H199A_HEADER from the
	# environment); build.sh previously tested this variable without ever
	# assigning it, so production validation could not run.
	H199A_REFERENCE="${H199A_REFERENCE:-${H199A_HEADER:-}}"
	[ -s "$H199A_REFERENCE" ] || { echo "ERROR: production validation needs the header template (H199A_HEADER)" >&2; exit 1; }
	python3 "$SELF_DIR/tools/verify-production-image.py" "$artifact" \
		--header-template "$H199A_REFERENCE" \
		--extract-dir "$artifact_stem-parts" > "$artifact_stem-production.json"
fi

ls -lh "$artifact"
echo
if [ "$H199A_RAM_ROOT" = 1 ]; then
	echo "RAM-root qualification artifact ready; use the guarded TFTP controller"
	echo "with a matching kernel, checksum envelope and manifest (docs/BRINGUP.md)."
	[ "$BOOT_PROFILE" = production ] && \
		echo "This is the PRODUCTION-POLICY qualification variant (deny matrix); it NEVER writes bank A."
elif [ "$BOOT_PROFILE" = production ]; then
	echo "Production factory/sysupgrade image ready (NOT hardware-qualified)."
	echo "Loose bank-A parts for first install: $artifact_stem-parts/{kernel,rootfs,header}"
	echo "Validation: $artifact_stem-production.json. See docs/INSTALL.md."
else
	echo "Build artifacts are ready. Installation is a separate step (docs/INSTALL.md)."
fi
if [ "${BRINGUP:-0}" = 1 ]; then
	echo
	echo "BRINGUP image: /proc/zx_eth_{regs,poke,reinit} are present."
	echo "  zx_eth_poke is an arbitrary physical RMW primitive - never ship this."
	echo "  Module parameters: /sys/module/zx279128_eth/parameters/*"
fi
