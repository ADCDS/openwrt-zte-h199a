# Firmware banks and upgrade safety

The production kernel supports either bootloader-selected firmware bank.
The physical vendor layout stays fixed; logical active partition labels move
before flash probing.

| Physical bank | Kernel, 3 MiB | Rootfs, `0xd20000` bytes | Header, 128 KiB |
|---|---:|---:|---:|
| A | `0x00700000` | `0x00a00000` | `0x01720000` |
| B | `0x02000000` | `0x02300000` | `0x03020000` |

Stock web updates write the inactive bank. Native OpenWrt `sysupgrade` replaces
the running bank and preserves its peer. Neither procedure relocates firmware
or changes the vendor upload-window geometry.

## Validated bank selection

The vendor bootloader passes its selected firmware in a checksummed BootPara
at physical `0x40007000`. Decompressor page tables would overwrite it. Before
enabling caches, the early decompressor validates its magic, checksum, index
and canonical kernel/rootfs offsets, then copies the selection into the
existing four-byte `/chosen/zte,boot-bank` property.

Before MTD probing, board code checks the board, marker length and exact
partition geometry. Active labels are always `kernel1`, `rootfs`, `header`;
the peer gets `kernel2`, `rootfs2`, `header2` and stays read-only. Physical
addresses and partition order do not move. Use labels and verified offsets;
`rootfs` is not always mtd7.

| Running bank | Writable MTD devices | Active kernel/rootfs/header |
|---|---|---|
| A | mtd6, mtd7, mtd8, mtd13 | mtd6 / mtd7 / mtd8 |
| B | mtd9, mtd10, mtd13, mtd14 | mtd9 / mtd10 / mtd14 |

`overlay_ubi` remains mtd13; physical B's header is mtd14. Unknown production
selection fails closed. RAM qualification has no authenticated NAND selection
and cannot write either firmware bank.

## Independent write barriers

MTD flags expose only the selected kernel, rootfs, header and `overlay_ubi`
as writable. The whole-flash master, peer firmware, bootloader, factory
calibration, vendor configuration, old overlay and staging partition are
read-only. The rootfs block device is read-only, while its character device
remains writable for validated upgrades.

The SPI transport independently selects one compiled firmware range, plus UBI:

| Selection | Program/erase byte range | Page rows |
|---|---|---|
| A | `[0x00700000,0x01740000)` | `[0x0e00,0x2e80)` |
| B | `[0x02000000,0x03040000)` | `[0x4000,0x6080)` |
| UBI, either bank | `[0x05400000,0x06400000)` | `[0xa800,0xc800)` |

It never enables both firmware ranges. Aliased rows, unaligned erases and
array-mode changes are refused; the first policy refusal latches until reboot.
Device-tree changes cannot widen this compiled allowlist. The controller's
read-only `write_policy_map` and `write_policy_state` sysfs attributes expose
the actual map and latch/refusal counters for comparison with MTD flags.

## Native upgrade contract

`platform_check_image` checks the board, archive members, part-size bounds,
active physical offsets and kernel capability before shutdown. Bank B refuses
an old A-only kernel. `sysupgrade -F` bypasses the early test, but the packaged
header preparer repeats its capability check before the first erase.

`h199a-upgrade-header` reads this unit's current and peer headers. It validates
the current identity, geometry and CRCs, checks the new kernel container,
uImage, zImage bounds and appended FDT, and CRCs the exact payload sizes.
It prepares a new header in RAM; the helper itself never writes flash.

The serial exceeds both selectable headers. A peer with valid inner-header
CRC imposes a serial ceiling even if its extended CRC is stale, matching
bootloader selection. Incrementing at or above `0x7fffffff` is refused to
avoid signed/unsigned counter overflow. Bank/version metadata and both header
CRCs are prepared before any erase.

The upgrade writes **rootfs → kernel → header last**, requiring readback
verification of each before proceeding. Normal upgrades preserve the separate
UBI overlay. `-n` recreates only its `rootfs_data` volume; it does not seed
raw-MTD markers or erase the whole UBI partition.

Power loss can leave an invalid active payload, causing bootloader CRC checks
to select a valid peer. This depends on that peer being bootable; byte
preservation alone is insufficient. No new power-cut qualification of the
bank-aware image is claimed. Stock fallback adds a hazard: after a default
300 seconds, `syn_version` can clone stock over the peer. Inspect fresh boots
and avoid concurrent synchronization/upload.

## Qualification and recovery scope

On one H199A, the **same image03 web container** passed stock A → OpenWrt B
and stock B → OpenWrt A with no source-bank override and zero UART writes
during upload. Changed-payload native image03 → image04 upgrades passed on
both banks, retained their bank and all 13 configuration/SSH-key hashes,
and preserved the peer and protected boot/calibration. A legacy A-only image
was rejected on B before erase/reboot. The recreated v1.0.0 assets repeated
both web directions with the same container, a changed-payload A native
upgrade and an exact-release same-payload B reinstall. All preservation and
write-policy checks passed again. See [VALIDATION.md](../VALIDATION.md).

The public guarded UART installer in [INSTALL.md](INSTALL.md) is explicitly
for physical **bank A**. Do not apply its offsets or header-erasure drill to
an OpenWrt-B installation. The UBI overlay is shared by both banks and must
not be erased as a firmware recovery shortcut.
