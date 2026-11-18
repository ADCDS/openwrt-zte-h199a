#!/usr/bin/env python3
"""Build a flashable kernel image for the ZTE ZXHN H199A.

The A/B kernel partitions (kernel1 @0x700000, kernel2 @0x2000000) hold a
32-byte ZTE "128s" header followed by a standard U-Boot uImage (load/entry
0x40008000). The header is identical across both banks (verified from the
July dump), so a flashable image is just:

    [ "33333333 cccccccc 88888888 dddddddd" (16 B) ][ 16 x 0xff ][ uImage ]

The CRC the bootloader checks is the uImage's own header/data CRC (mkimage
computes it), so no separate ZTE CRC field is needed.

Usage:
    make-flash-image.py INPUT.uImage OUTPUT.bin

INPUT is a uImage as produced by:
    mkimage -A arm -O linux -T kernel -C none -a 0x40008000 -e 0x40008000 \
            -n "h199a-openwrt" -d zImage[+dtb] OUT.uImage
"""
import sys

ZTE_MAGIC = bytes.fromhex("33333333cccccccc88888888dddddddd")
ZTE_PAD = b"\xff" * 16
UIMAGE_MAGIC = bytes.fromhex("27051956")


def build(uimage: bytes) -> bytes:
    if uimage[:4] != UIMAGE_MAGIC:
        raise SystemExit("input is not a uImage (missing 0x27051956 magic)")
    return ZTE_MAGIC + ZTE_PAD + uimage


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    with open(sys.argv[1], "rb") as f:
        uimage = f.read()
    out = build(uimage)
    with open(sys.argv[2], "wb") as f:
        f.write(out)
    print(f"{sys.argv[1]} -> {sys.argv[2]} ({len(out)} bytes) "
          f"[ZTE header 32 B + uImage {len(uimage)} B]")


if __name__ == "__main__":
    main()
