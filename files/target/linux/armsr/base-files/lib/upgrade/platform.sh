# H199A sysupgrade: the kernel maps kernel1/rootfs/header to the verified
# running bank. The peer firmware remains read-only for recovery. The native
# SPI transport independently permits only that bank plus the UBI overlay.
#
# Prepare the header in RAM from this unit's active header, with a version
# serial above both valid banks. Write rootfs -> kernel -> header LAST, and
# read back each part before proceeding. A partial upgrade leaves a CRC
# mismatch so the vendor bootloader can fall back to the untouched peer.
# Configuration lives in overlay_ubi, outside both firmware CRC ranges.

. /lib/functions.sh

REQUIRE_IMAGE_METADATA=0
RAMFS_COPY_BIN="${RAMFS_COPY_BIN:-} /usr/sbin/h199a-upgrade-header"

# Active labels are stable across banks; physical offsets are validated below.
# Both names are accepted: the DTS names the board first and the SoC
# second, so an image built before that change still validates, and a
# unit already running this one keeps doing so after the rename.
H199A_SUPPORTED_BOARD="zte,zxhn-h199a zte,zx279128s"
H199A_OVERLAY_MTD="overlay_ubi"
H199A_OVERLAY_VOL="rootfs_data"
H199A_OVERLAY_LEBS=104
H199A_OVERLAY_VIDOFFSET=2048

h199a_part_offset() {
	local index
	index=$(find_mtd_index "$1") || return 1
	[ -n "$index" ] || return 1
	cat "/sys/class/mtd/mtd$index/offset" 2>/dev/null
}

# Active labels come from the validated boot-bank mapping. Confirm their
# physical ranges before sysupgrade is allowed to use them.
h199a_active_bank() {
	local kernel rootfs header
	kernel=$(h199a_part_offset kernel1) || return 1
	rootfs=$(h199a_part_offset rootfs) || return 1
	header=$(h199a_part_offset header) || return 1
	case "$kernel:$rootfs:$header" in
		"$((0x700000)):$((0xa00000)):$((0x1720000))") echo a ;;
		"$((0x2000000)):$((0x2300000)):$((0x3020000))") echo b ;;
		*) echo "h199a: active partition geometry is not a supported bank" >&2; return 1 ;;
	esac
}

h199a_prepare_upgrade_header() {
	local work="$1" kernel="$2" rootfs="$3" header="$4" bank current backup
	bank=$(h199a_active_bank) || return 1
	command -v h199a-upgrade-header >/dev/null 2>&1 || {
		echo "h199a: required header preparer is missing" >&2; return 1;
	}
	current=$(find_mtd_index header) || return 1
	backup=$(find_mtd_index header2) || return 1
	[ -n "$current" ] && [ -n "$backup" ] || return 1
	dd if="/dev/mtd$current" of="$work/current-header" bs=131072 count=1 2>/dev/null || return 1
	dd if="/dev/mtd$backup" of="$work/backup-header" bs=131072 count=1 2>/dev/null || return 1
	h199a-upgrade-header "$bank" "$work/current-header" "$work/backup-header" \
		"$kernel" "$rootfs" "$work/header.next" || return 1
	mv "$work/header.next" "$header"
}

h199a_part_size() {
	# Size in bytes of an mtd partition, by label.
	#
	# /proc/mtd lines look like:  mtd7: 00d20000 00020000 "rootfs"
	# so the NAME is $4, not $5. And busybox awk has no strtonum() (a gawk
	# extension), so the hex conversion is done in the shell.
	local sz
	sz=$(awk -v l="\"$1\"" '$4 == l { print $2; exit }' /proc/mtd 2>/dev/null)
	[ -n "$sz" ] || return 1
	printf '%d' "0x$sz"
}

# First path component of the tar, i.e. the image's board directory.
#
# Deliberately avoids `head`: stage2 copies a fixed list of applets into the
# ramfs (busybox, tar, mtd, awk, sed, cut, grep, wc, tail, ...) and `head` is
# NOT among them, so `head -1` fails after the pivot - silently, since `mtd
# write` treats a zero-byte stream as a no-op and still reports success.
h199a_board_dir() {
	tar tf "$1" 2>/dev/null | sed -n '1{s|/.*||;p;q}'
}

# Extract one tar member to a real file so it can be written AND read back.
h199a_extract() {
	local tar_file="$1" member="$2" dest="$3"
	tar xOf "$tar_file" "$member" > "$dest" 2>/dev/null
	[ -s "$dest" ]
}

# Write a file to a partition by label, then read the partition back and
# compare. `mtd verify` md5s the image file against exactly that many bytes read
# from the mtd char device, so a bit that did not land fails here, before the
# next (more dangerous) part is written. Returns non-zero on any mismatch.
h199a_write_verified() {
	local file="$1" part="$2"
	echo "h199a: writing $part"
	mtd write "$file" "$part" || { echo "h199a: write $part failed"; return 1; }
	echo "h199a: verifying $part"
	mtd verify "$file" "$part" || { echo "h199a: verify $part MISMATCH - aborting"; return 1; }
	return 0
}

platform_check_image() {
	local tar_file="$1"
	local board_dir kern rootfs ksize rsize board bank work result

	# Board-name check BEFORE anything erases. A foreign image is rejected
	# here, not after a partition has already been wiped.
	board=$(cat /tmp/sysinfo/board_name 2>/dev/null)
	case " $H199A_SUPPORTED_BOARD " in
		*" $board "*) ;;
		*)
			echo "Invalid image: board '$board' is not $H199A_SUPPORTED_BOARD"
			return 1 ;;
	esac

	board_dir=$(h199a_board_dir "$tar_file")
	[ -n "$board_dir" ] || {
		echo "Invalid image: not a tar archive"
		return 1
	}
	[ "$board_dir" = "h199a" ] || {
		echo "Invalid image: unexpected board directory '$board_dir'"
		return 1
	}

	for f in kernel rootfs header; do
		tar tf "$tar_file" 2>/dev/null | grep -q "^$board_dir/$f\$" || {
			echo "Invalid image: missing '$f' member"
			return 1
		}
	done

	# Refuse an image whose parts cannot fit, rather than truncating into the
	# next partition.
	kern=$(tar xOf "$tar_file" "$board_dir/kernel" 2>/dev/null | wc -c)
	rootfs=$(tar xOf "$tar_file" "$board_dir/rootfs" 2>/dev/null | wc -c)
	[ "$kern" -gt 0 ] && [ "$rootfs" -gt 0 ] || {
		echo "Invalid image: empty kernel or rootfs"
		return 1
	}
	ksize=$(h199a_part_size kernel1) || {
		echo "Invalid image: cannot read kernel1 partition size"
		return 1
	}
	rsize=$(h199a_part_size rootfs) || {
		echo "Invalid image: cannot read rootfs partition size"
		return 1
	}
	[ "$kern" -le "$ksize" ] || {
		echo "Invalid image: kernel too large ($kern bytes)"
		return 1
	}
	[ "$rootfs" -le "$rsize" ] || {
		echo "Invalid image: rootfs too large ($rootfs bytes)"
		return 1
	}

	bank=$(h199a_active_bank) || return 1
	command -v h199a-upgrade-header >/dev/null 2>&1 || {
		echo "Invalid image: required header preparer is missing"; return 1;
	}
	work=$(mktemp -d 2>/dev/null) || return 1
	result=1
	if h199a_extract "$tar_file" "$board_dir/kernel" "$work/kernel"; then
		h199a-upgrade-header --check-kernel "$bank" "$work/kernel"
		result=$?
	fi
	rm -rf "$work"
	return "$result"
}

# Attach the overlay UBI without ever formatting it. Returns the ubi device
# name (e.g. ubi0) on stdout, or non-zero if it is absent - config handling then
# refuses rather than reformatting an unexpected volume.
h199a_overlay_ubidev() {
	local mtdnum ubidev
	mtdnum=$(find_mtd_index "$H199A_OVERLAY_MTD") || return 1
	[ -n "$mtdnum" ] || return 1
	ubidev=$(nand_find_ubi "$H199A_OVERLAY_MTD")
	if [ -z "$ubidev" ]; then
		ubiattach -m "$mtdnum" -O "$H199A_OVERLAY_VIDOFFSET" >/dev/null 2>&1
		ubidev=$(nand_find_ubi "$H199A_OVERLAY_MTD")
	fi
	[ -n "$ubidev" ] || return 1
	echo "$ubidev"
}

platform_do_upgrade() {
	local tar_file="$1"
	local board_dir work kpart rpart hpart

	board_dir=$(h199a_board_dir "$tar_file")
	work=$(mktemp -d 2>/dev/null) || work=/tmp/h199a-upgrade.$$
	mkdir -p "$work"
	kpart="$work/kernel"; rpart="$work/rootfs"; hpart="$work/header"

	h199a_extract "$tar_file" "$board_dir/kernel" "$kpart" || { echo "h199a: kernel extract failed"; return 1; }
	h199a_extract "$tar_file" "$board_dir/rootfs" "$rpart" || { echo "h199a: rootfs extract failed"; return 1; }
	h199a_extract "$tar_file" "$board_dir/header" "$hpart" || { echo "h199a: header extract failed"; return 1; }

	# Prepare identity and version metadata before the first flash erase.
	h199a_prepare_upgrade_header "$work" "$kpart" "$rpart" "$hpart" || {
		echo "h199a: active-bank header preparation failed; nothing written"
		return 1
	}

	# We are running from RAM here. If a changed rootfs is only partially
	# written, the old header's payload CRC can fail at the next boot and
	# select the untouched, valid peer.
	h199a_write_verified "$rpart" rootfs || return 1

	# Then the kernel. The old header remains until both payloads verify.
	h199a_write_verified "$kpart" kernel1 || return 1

	# Header LAST is the commit point for the new active-bank payload.
	# Recovery from an interrupted update relies on a valid peer image.
	h199a_write_verified "$hpart" header || return 1

	# The inactive firmware and bootloader were never exposed.

	# Configuration lives in the UBI rootfs_data volume, outside the firmware banks, so the
	# writes above already preserved it. `sysupgrade -n` must actively reset it
	# by recreating the UBI volume - never by seeding a raw-MTD deadc0de page
	# into UBI, which is meaningless to a UBI volume and is a raw-MTD artifact.
	if [ "${SAVE_CONFIG:-1}" != "1" ]; then
		h199a_overlay_reset
	fi

	rm -rf "$work"
	return 0
}

# -n reset: erase and recreate ONLY the rootfs_data UBI volume. The UBI device,
# its EC/VID metadata and every other volume are untouched; no deadc0de marker
# is written (that is a raw-MTD concept and UBI would treat it as data).
h199a_overlay_reset() {
	local ubidev vol
	ubidev=$(h199a_overlay_ubidev) || { echo "h199a: cannot attach $H199A_OVERLAY_MTD for -n reset"; return 1; }
	vol=$(nand_find_volume "$ubidev" "$H199A_OVERLAY_VOL")
	if [ -n "$vol" ]; then
		nand_remove_ubiblock "$vol" 2>/dev/null
		umount "/dev/$vol" 2>/dev/null
		ubirmvol "/dev/$ubidev" -N "$H199A_OVERLAY_VOL" || { echo "h199a: ubirmvol failed"; return 1; }
	fi
	ubimkvol "/dev/$ubidev" -N "$H199A_OVERLAY_VOL" -t dynamic -S "$H199A_OVERLAY_LEBS" || {
		echo "h199a: ubimkvol $H199A_OVERLAY_VOL failed"; return 1; }
	echo "h199a: overlay $H199A_OVERLAY_VOL reset (sysupgrade -n)"
	return 0
}

# Config preservation into UBI. sysupgrade saved /tmp/sysupgrade.tgz before the
# pivot when a backup was requested; drop it into the rootfs_data volume so the
# next boot's fstools restores it. Mirrors nand_restore_config but pinned to our
# own overlay partition and VID offset, and it never formats the volume.
platform_copy_config() {
	local ubidev vol
	[ -f /tmp/sysupgrade.tgz ] || return 0
	ubidev=$(h199a_overlay_ubidev) || { echo "h199a: cannot attach $H199A_OVERLAY_MTD for config save"; return 1; }
	vol=$(nand_find_volume "$ubidev" "$H199A_OVERLAY_VOL")
	[ -n "$vol" ] || { echo "h199a: $H199A_OVERLAY_VOL volume missing; config not saved"; return 1; }
	mkdir -p /tmp/overlay-restore
	if mount -t ubifs "/dev/$vol" /tmp/overlay-restore; then
		cp /tmp/sysupgrade.tgz "/tmp/overlay-restore/$BACKUP_FILE" && sync
		umount /tmp/overlay-restore
		echo "h199a: configuration saved to $H199A_OVERLAY_VOL"
	else
		echo "h199a: could not mount $H199A_OVERLAY_VOL; config not saved"
		rmdir /tmp/overlay-restore 2>/dev/null
		return 1
	fi
	rmdir /tmp/overlay-restore 2>/dev/null
	return 0
}
