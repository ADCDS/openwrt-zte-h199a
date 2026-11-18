#!/usr/bin/env python3
"""Prepare a CRC-correct flashable kernel + header for the ZTE ZXHN H199A.

Decoded 2026-08-21. `zteboot` validates a bank (kernel @0x700000, rootfs
@0xa00000, firmware header @0x1720000) by checking `zlib.crc32` of the kernel
data at +0x20 (after the 32-byte "128s" header) against the header's +0x3c.

Outputs two files to flash over U-Boot TFTP + `nand write`:
    <out>.kernel  -> nand write to 0x700000 (3 MiB, block-aligned)
    <out>.header  -> nand write to 0x1720000 (1 block, block-aligned)

Usage: flash-prep.py KERNEL.uImage DUMP.h199a-flash-full.bin OUT
"""
import sys
import zlib
import struct

ZTE_MAGIC = bytes.fromhex("33333333cccccccc88888888dddddddd") + b"\xff" * 16
KERNEL_OFF = 0x700000
KERNEL_LEN = 0x300000          # fixed 3 MiB read by zteboot
CRC_LEN = 0x2ffdcc             # kernel data CRC length (uImage + 0x00 pad)
HEADER_OFF = 0x1720000
HEADER_BLK = 0x20000          # one erase block; stock BootPara lives in its head
HDR_CRC_LEN = 0xa4            # header self-CRC covers hdr[0:0xa4], stored @+0xa4
FS_OFF = 0xa00000             # rootfs partition
FS_LEN = 0xd20000             # fs size (+0x40); FIXED: header offset = FS_OFF+FS_LEN


def build_kernel_container(uimage: bytes) -> bytes:
    """ZTE magic + uImage, zero-padded to the fixed 3 MiB kernel partition."""
    if uimage[:4] != bytes.fromhex("27051956"):
        raise SystemExit("not a uImage")
    if len(uimage) > KERNEL_LEN - 0x20:
        raise SystemExit(f"uImage {len(uimage)} too big for {KERNEL_LEN-0x20}")
    kernel = ZTE_MAGIC + uimage
    return kernel + b"\x00" * (KERNEL_LEN - len(kernel))


def kernel_crc(container: bytes) -> int:
    """csp_crc over the kernel data at +0x20, fixed length CRC_LEN."""
    return zlib.crc32(container[0x20:0x20 + CRC_LEN]) & 0xffffffff


def fs_image(rootfs: bytes) -> bytes:
    """SquashFS zero-padded to the fixed fs_size; never shrink fs_size (+0x40)."""
    if len(rootfs) > FS_LEN:
        raise SystemExit(f"rootfs {len(rootfs)} > {FS_LEN:#x}")
    return rootfs + b"\x00" * (FS_LEN - len(rootfs))


def fs_crc(fs: bytes) -> int:
    return zlib.crc32(fs) & 0xffffffff


def header_template(dump: bytes) -> bytearray:
    """Extract this unit's 128 KiB bank-A header from a full dump or a block.

    `dump` may be either a full 128 MiB NAND image or just the 128 KiB header
    block extracted from one. Only the header block is ever used, and it is
    device-specific (it carries the unit's vendor fields), so requiring a full
    dump of SOMEBODY ELSE'S device was both unnecessary and wrong - see
    docs/INSTALL.md for how to extract this from your own board.
    """
    if len(dump) >= HEADER_OFF + HEADER_BLK:
        return bytearray(dump[HEADER_OFF:HEADER_OFF + HEADER_BLK])
    if len(dump) == HEADER_BLK:
        return bytearray(dump)
    raise SystemExit(
        f"reference must be a full NAND dump (>= {HEADER_OFF + HEADER_BLK} bytes) "
        f"or exactly one {HEADER_BLK}-byte header block; got {len(dump)} bytes")


def patch_header(template: bytes, crc: int, fscrc: int | None = None) -> bytes:
    """Return the device header with only +0x3c, +0x48 and +0xa4 rewritten.

    This is the whole CRC contract the bootloader checks: the kernel CRC at
    +0x3c, the fs CRC at +0x48 and the header self-CRC at +0xa4 over hdr[0:0xa4].
    Every other byte - version string, upgrade keys, bank start, version serial
    (+0x1f4) and the stale +0x1fc CRC - is preserved from the unit's template.
    Feeding the stock bank-A CRCs reproduces the unit's own header byte-exactly.
    """
    hdr = bytearray(template)
    struct.pack_into("<I", hdr, 0x3c, crc & 0xffffffff)
    if fscrc is not None:
        struct.pack_into("<I", hdr, 0x48, fscrc & 0xffffffff)
    # Self-CRC over hdr[0:0xa4] MUST be recomputed last: the kernel/fs CRC
    # fields live inside that range.
    hdr_crc = zlib.crc32(bytes(hdr[0:HDR_CRC_LEN])) & 0xffffffff
    struct.pack_into("<I", hdr, HDR_CRC_LEN, hdr_crc)
    return bytes(hdr)


def build(uimage: bytes, dump: bytes, out: str, rootfs: bytes | None = None) -> None:
    kernel = build_kernel_container(uimage)
    crc = kernel_crc(kernel)

    template = header_template(dump)

    fs = fs_crc_value = None
    if rootfs is not None:
        # NOTE: fs_size (+0x40) must stay 0xd20000 because zteboot derives
        # HeaderOffset = fs_start + fs_size; changing it moves the header.
        fs = fs_image(rootfs)
        fs_crc_value = fs_crc(fs)
        open(out + ".rootfs", "wb").write(fs)

    hdr = bytearray(patch_header(template, crc, fs_crc_value))
    hdr_crc = struct.unpack_from("<I", hdr, HDR_CRC_LEN)[0]

    # rootfs_data seed: OpenWrt's fstools only treats a raw-MTD overlay volume as
    # usable if its first bytes are the JFFS2 magic (0x1985) or the `deadc0de`
    # marker -- an erased partition (0xffffffff) is FS_NONE for raw MTD and only
    # counts as JFFS2 on UBI volumes (libfstools/mtd.c). Without the marker
    # mount_root falls back to a tmpfs overlay, `mount_root done` writes
    # /overlay/.fs_state into RAM, the state never reaches READY, and fstools
    # deletes the overlay on every boot (libfstools/overlay.c FS_STATE_PENDING).
    # One page is enough: marker first, erased pattern after.
    seed = struct.pack(">I", 0xdeadc0de) + b"\xff" * (2048 - 4)
    open(out + ".rootfs_data", "wb").write(seed)

    open(out + ".kernel", "wb").write(kernel)
    open(out + ".header", "wb").write(hdr)

    # sysupgrade image: a tar whose single top-level directory holds the three
    # parts, matching what base-files/lib/upgrade/platform.sh expects. Written
    # only when a rootfs was supplied, since all three parts must agree.
    if rootfs is not None:
        import tarfile, io, time
        with tarfile.open(out + "-sysupgrade.tar", "w") as tf:
            def add(name, data):
                ti = tarfile.TarInfo("h199a/" + name)
                ti.size = len(data)
                ti.mtime = int(time.time())
                ti.mode = 0o644
                tf.addfile(ti, io.BytesIO(data))
            add("kernel", bytes(kernel))
            add("rootfs", bytes(fs))
            add("header", bytes(hdr))

    print(f"uImage  : {len(uimage)} bytes")
    print(f"kernel  : {out}.kernel  ({len(kernel)} bytes) -> nand write "
          f"{KERNEL_OFF:#x} {len(kernel):#x}")
    print(f"CRC     : 0x{crc:08x}  (header +0x3c)")
    if fs_crc_value is not None:
        print(f"rootfs  : {out}.rootfs  ({FS_LEN} bytes) -> nand write "
              f"{FS_OFF:#x} {FS_LEN:#x}")
        print(f"fs CRC  : 0x{fs_crc_value:08x}  (header +0x48)")
    print(f"hdr CRC : 0x{hdr_crc:08x}  (header +0x{HDR_CRC_LEN:x})")
    print(f"header  : {out}.header  ({len(hdr)} bytes) -> nand write "
          f"{HEADER_OFF:#x} {len(hdr):#x}")


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        raise SystemExit(__doc__)
    uimg = open(sys.argv[1], "rb").read()
    dump = open(sys.argv[2], "rb").read()
    rfs = open(sys.argv[4], "rb").read() if len(sys.argv) == 5 else None
    build(uimg, dump, sys.argv[3], rfs)
