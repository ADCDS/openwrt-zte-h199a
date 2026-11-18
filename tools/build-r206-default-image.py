#!/usr/bin/env python3
"""Build a padded, RAM-only uImage for the force0 R206 warm-path trial."""
from pathlib import Path
import argparse, hashlib, struct, time, zlib

TOTAL=3*1024*1024
LOAD=ENTRY=0x40008000

def main():
    ap=argparse.ArgumentParser();ap.add_argument('kernel');ap.add_argument('output');a=ap.parse_args()
    payload=Path(a.kernel).read_bytes()
    if not 2_000_000 < len(payload) < TOTAL-96: raise SystemExit('unexpected payload size')
    name=b'h199a-r206-default\0'.ljust(32,b'\0')
    stamp=int(time.time())
    dcrc=zlib.crc32(payload)&0xffffffff
    raw=struct.pack('>7I4B32s',0x27051956,0,stamp,len(payload),LOAD,ENTRY,dcrc,5,2,2,0,name)
    hcrc=zlib.crc32(raw[:4]+b'\0\0\0\0'+raw[8:])&0xffffffff
    header=struct.pack('>7I4B32s',0x27051956,hcrc,stamp,len(payload),LOAD,ENTRY,dcrc,5,2,2,0,name)
    out=b'\0'*32+header+payload
    if len(out)>TOTAL: raise SystemExit('image exceeds 3MiB')
    Path(a.output).write_bytes(out+b'\0'*(TOTAL-len(out)))
    print('payload_sha256',hashlib.sha256(payload).hexdigest())
    print('image_sha256',hashlib.sha256(Path(a.output).read_bytes()).hexdigest())
    print('payload_bytes',len(payload),'header_crc',f'{hcrc:08x}','data_crc',f'{dcrc:08x}')
if __name__=='__main__': main()
