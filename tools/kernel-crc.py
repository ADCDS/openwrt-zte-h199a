#!/usr/bin/env python3
"""Compute the ZTE kernel CRC + firmware-header patch for a bootable image.

Decoded 2026-08-21: `zteboot`'s `csp_crc` checks `zlib.crc32` over the kernel
data starting at flash offset +0x20 (right after the 32-byte "128s" header),
for a length stored in the firmware header at 0x1720000 (+0x34). The CRC goes
at header +0x3c. The stock header carries length 0x2ffdcc, so the uImage is
0xFF-padded to that length before the CRC is taken (the bootloader reads a
fixed 3 MiB from the kernel offset regardless).

Usage:
    kernel-crc.py KERNEL.uImage          # prints CRC + header patch bytes

The kernel uImage must be <= ~0x2fffe0 bytes (fits the 3 MiB kernel partition).
"""
import sys
import zlib

CRC_LEN = 0x2ffdcc          # stock kernel-data length (can be lowered if the
                             # uImage is smaller; keep it for minimal patching)


def kernel_crc(uimage: bytes, crc_len: int = CRC_LEN) -> int:
    # stock pads the region after the uImage with 0x00 up to crc_len
    data = uimage + b"\x00" * max(0, crc_len - len(uimage))
    return zlib.crc32(data[:crc_len]) & 0xffffffff


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    uimage = open(sys.argv[1], "rb").read()
    if uimage[:4] != bytes.fromhex("27051956"):
        raise SystemExit("input is not a uImage (missing 0x27051956 magic)")
    if len(uimage) > 0x2fffe0:
        print(f"WARNING: uImage {len(uimage)} bytes exceeds 3 MiB partition "
              f"(0x2fffe0); it will be truncated by zteboot.", file=sys.stderr)
    crc = kernel_crc(uimage)
    print(f"uImage size : {len(uimage)} bytes (0x{len(uimage):x}) "
          f"(must be <= {CRC_LEN:#x})")
    print(f"kernel CRC  : 0x{crc:08x}")
    print(f"header patch: +0x3c <- {crc.to_bytes(4,'little').hex()}"
          f"  (CRC, LE); +0x34 stays {CRC_LEN.to_bytes(4,'little').hex()}")


if __name__ == "__main__":
    main()
