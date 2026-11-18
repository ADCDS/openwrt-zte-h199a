#!/usr/bin/env python3
"""Prepare bank-B BootPara for RAM use from verified U-Boot md.l captures."""

import argparse
from pathlib import Path
import re
import struct

SIZE = 0x554
MAGIC = (0xCCCCCCCC, 0x55555555, 0xAAAAAAAA, 0x11111111)


def parse_dump(text: str) -> bytes:
    result = bytearray()
    base = None
    for line in text.splitlines():
        match = re.match(r"^([0-9a-fA-F]{8}):\s+(.*)", line)
        if not match:
            continue
        address = int(match[1], 16)
        if base is None:
            base = address
        if address != base + len(result) or len(result) >= SIZE:
            raise ValueError("non-contiguous or oversized dump")
        count = min(4, (SIZE - len(result)) // 4)
        words = match[2].split()[:count]
        if len(words) != count or any(not re.fullmatch(r"[0-9a-fA-F]{8}", w) for w in words):
            raise ValueError("invalid md.l data words")
        for word in words:
            result.extend(struct.pack("<I", int(word, 16)))
    if len(result) != SIZE:
        raise ValueError("incomplete BootPara dump")
    return bytes(result)


def select_bank_b(physical: bytes, runtime: bytes) -> bytes:
    if len(physical) != SIZE or len(runtime) != SIZE:
        raise ValueError("wrong BootPara size")
    if struct.unpack_from("<4I", physical) != MAGIC:
        raise ValueError("wrong BootPara magic")
    expected = struct.unpack_from("<I", physical, 0xA0)[0]
    check = bytearray(physical)
    check[0xA0:0xA4] = bytes(4)
    if sum(check) != expected:
        raise ValueError("physical BootPara checksum mismatch")
    # The vendor fills its eight-byte version string after saving the sum.
    if physical[:0x10] != runtime[:0x10] or physical[0x18:] != runtime[0x18:]:
        raise ValueError("runtime BootPara differs outside the known version field")
    _, valid, total, selected = struct.unpack_from("<4I", runtime, 0x30)
    if valid != 2 or total != 2 or selected not in (0, 1):
        raise ValueError("expected two valid image records")
    output = bytearray(runtime)
    struct.pack_into("<I", output, 0x3C, 1)
    struct.pack_into("<I", output, 0xA0, 0)
    struct.pack_into("<I", output, 0xA0, sum(output))
    return bytes(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("physical", type=Path)
    parser.add_argument("runtime", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    output = select_bank_b(
        parse_dump(args.physical.read_text(encoding="ascii")),
        parse_dump(args.runtime.read_text(encoding="ascii")),
    )
    with args.output.open("xb") as stream:
        stream.write(output)
    print(f"RAM-only BootPara: bank=1 size={len(output)} checksum=0x{struct.unpack_from('<I', output, 0xa0)[0]:x}")


if __name__ == "__main__":
    main()
