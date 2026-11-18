#!/usr/bin/env python3
"""Transfer a blob to /tmp over the bench UART and verify its SHA256.

Requires uart-log.sh and a live ash prompt. Quiet kernel console output first:
printk.ignore_loglevel=N and console_loglevel=1. Diagnostic console writes can
otherwise overflow UART RX while interrupts are disabled. No received file is
executed by this tool. The receiver uses ash builtins, requiring no base64 applet.
"""

import argparse
import hashlib
import os
from pathlib import Path
import re
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination")
    parser.add_argument("--port", default="/dev/h199a-uart")
    parser.add_argument("--log", type=Path,
                        default=Path(__file__).resolve().parents[2] / "logs/uart.log")
    args = parser.parse_args()
    if not re.fullmatch(r"/tmp/[A-Za-z0-9_.-]+", args.destination):
        parser.error("destination must be a simple filename under /tmp")
    payload = args.source.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    mark = args.log.stat().st_size
    fd = os.open(args.port, os.O_WRONLY | os.O_NOCTTY)

    def send(line):
        data = line.encode("ascii") + b"\r"
        while data:
            written = os.write(fd, data)
            data = data[written:]

    receiving = False
    try:
        for line in ("while read -r -s b", "do", '[ "$b" = END ] && break',
                     'printf "$b"', f"done >{args.destination}"):
            send(line)
            time.sleep(0.5)
        receiving = True
        time.sleep(1)
        for start in range(0, len(payload), 12):
            send("".join(f"\\{byte:03o}" for byte in payload[start:start + 12]))
            time.sleep(0.015)
        send("END")
        receiving = False
        time.sleep(2)
        send(f"sha256sum {args.destination}")
        expected = f"{digest}  {args.destination}"
        for _ in range(30):
            time.sleep(1)
            with args.log.open("rb") as stream:
                stream.seek(mark)
                lines = stream.read().decode("ascii", errors="replace").replace("\r", "").splitlines()
            if expected in lines:
                print(f"VERIFIED {len(payload)} bytes sha256={digest} destination={args.destination}")
                return
        send("END")  # Recover a receiver whose terminator was lost.
        raise RuntimeError("UART checksum not confirmed; do not execute the received file")
    finally:
        if receiving:
            send("")
            send("END")
        os.close(fd)


if __name__ == "__main__":
    main()
