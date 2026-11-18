#!/usr/bin/env python3
"""Capture a gzip file from the bench UART, validating its embedded CRC.

The sender needs only cat. Quiet kernel console output before use. The normal
TTY ONLCR mapping is inverted before decoding; gzip CRC/length validation must
succeed before an output file is created. No binary data is printed to stdout.
"""

import argparse
import hashlib
import os
from pathlib import Path
import re
import time
import zlib


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("output", type=Path)
    parser.add_argument("--port", default="/dev/h199a-uart")
    parser.add_argument("--log", type=Path,
                        default=Path(__file__).resolve().parents[2] / "logs/uart.log")
    parser.add_argument("--timeout", type=int, default=300)
    args = parser.parse_args()
    if not re.fullmatch(r"/tmp/[A-Za-z0-9_.-]+", args.source):
        parser.error("source must be a simple filename under /tmp")
    if args.output.exists():
        parser.error("output already exists")
    mark = args.log.stat().st_size
    fd = os.open(args.port, os.O_WRONLY | os.O_NOCTTY)
    try:
        command = f"cat {args.source}\r".encode("ascii")
        while command:
            command = command[os.write(fd, command):]
    finally:
        os.close(fd)
    start = time.monotonic()
    report = start
    while time.monotonic() - start < args.timeout:
        time.sleep(1)
        with args.log.open("rb") as stream:
            stream.seek(mark)
            data = stream.read().replace(b"\r\n", b"\n")
        begin = data.find(b"\x1f\x8b\x08")
        if begin >= 0:
            decoder = zlib.decompressobj(31)
            unpacked = decoder.decompress(data[begin:])
            if decoder.eof:
                size = len(data) - begin - len(decoder.unused_data)
                packed = data[begin:begin + size]
                with args.output.open("xb") as stream:
                    stream.write(packed)
                print(f"VERIFIED gzip CRC: compressed={size} expanded={len(unpacked)}")
                print(f"sha256={hashlib.sha256(packed).hexdigest()} output={args.output}")
                return
        if time.monotonic() - report >= 15:
            print(f"receiving: {len(data)} normalized bytes", flush=True)
            report = time.monotonic()
    raise TimeoutError(f"no complete gzip stream; raw capture starts at log offset {mark}")


if __name__ == "__main__":
    main()
