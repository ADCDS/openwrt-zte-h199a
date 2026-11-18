#!/usr/bin/env python3
"""Prepare a RAM-only stock kernel whose default init is /bin/sh.

Preserve the zImage's linked offsets by padding the replacement gzip header to
the original stream length. This never edits a flash dump in place or writes
to the router. Boot selection/root mounting must be established separately.
"""

import argparse
import hashlib
import struct
import zlib
from pathlib import Path

INIT_PATHS = (b"/sbin/init\0", b"/etc/init\0", b"/bin/init\0")


def prepare(source: bytes) -> bytes:
    header_start = 32
    data_start = header_start + 64
    header = bytearray(source[header_start:data_start])
    if len(header) != 64:
        raise ValueError("short uImage header")
    magic, hcrc, _, size, load, entry, dcrc = struct.unpack_from(">7I", header)
    if magic != 0x27051956 or load != 0x40008000 or entry != 0x40008000:
        raise ValueError("unexpected stock uImage header")
    if header[28:32] != bytes((5, 2, 2, 0)):
        raise ValueError("expected Linux ARM kernel with an uncompressed uImage wrapper")
    struct.pack_into(">I", header, 4, 0)
    if zlib.crc32(header) != hcrc:
        raise ValueError("input uImage header checksum mismatch")
    payload = source[data_start:data_start + size]
    if len(payload) != size or zlib.crc32(payload) != dcrc:
        raise ValueError("input uImage data checksum mismatch")

    candidates = []
    pos = 0
    while True:
        pos = payload.find(b"\x1f\x8b\x08", pos)
        if pos < 0:
            break
        try:
            decoder = zlib.decompressobj(31)
            image = decoder.decompress(payload[pos:]) + decoder.flush()
            if decoder.eof and all(image.count(path) == 1 for path in INIT_PATHS):
                length = len(payload) - pos - len(decoder.unused_data)
                candidates.append((pos, length, image))
        except zlib.error:
            pass
        pos += 3
    if len(candidates) != 1:
        raise ValueError("expected one gzip kernel with one default init path")
    pos, length, image = candidates[0]
    patched = image
    for old in INIT_PATHS:
        patched = patched.replace(old, b"/bin/sh\0".ljust(len(old), b"\0"))
    compressor = zlib.compressobj(9, zlib.DEFLATED, 31)
    packed = compressor.compress(patched) + compressor.flush()
    padding = length - len(packed)
    if padding < 0:
        raise ValueError("patched gzip exceeds the original slot")
    if padding:
        if packed[3] != 0:
            raise ValueError("unexpected gzip header flags")
        # The kernel's small gzip decoder supports FNAME, not FCOMMENT.
        packed = packed[:3] + b"\x08" + packed[4:10] + b"R" * (padding - 1) + b"\0" + packed[10:]
    if len(packed) != length or zlib.decompress(packed, 31) != patched:
        raise ValueError("replacement gzip verification failed")

    output = bytearray(source)
    output[data_start + pos:data_start + pos + length] = packed
    struct.pack_into(">I", header, 24, zlib.crc32(output[data_start:data_start + size]))
    header[32:64] = b"H199A stock shell RAM ONLY".ljust(32, b"\0")
    struct.pack_into(">I", header, 4, zlib.crc32(header))
    output[header_start:data_start] = header
    print(f"init offsets={[hex(image.index(path)) for path in INIT_PATHS]} gzip offset=0x{data_start + pos:x} size={length}")
    print(f"original image sha256={hashlib.sha256(image).hexdigest()}")
    print(f"patched image sha256={hashlib.sha256(patched).hexdigest()}")
    return bytes(output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("refusing to overwrite the source dump")
    result = prepare(args.source.read_bytes())
    with args.output.open("xb") as stream:
        stream.write(result)
    print(f"wrote {len(result)} bytes to {args.output}; RAM boot only, do not flash")


if __name__ == "__main__":
    main()
