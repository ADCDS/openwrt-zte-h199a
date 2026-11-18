#!/usr/bin/env python3
"""Parent-only normal-logger power-on watch for the requested physical LED check.
No binary lease; existing logger MUST remain the sole reader. No networking,
flash, env or OS boot commands. Catch a clean boot-mode banner once; abort and
power OFF on unexpected OS start, unrecognized boot progression or300s timeout.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import time

PORT='/dev/h199a-uart'
LOG=Path('~/dev/routers/h199a/logs/uart.log')

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-prefix',type=Path,required=True)
    args=parser.parse_args();out=args.output_prefix
    if Path(str(out)+'.json').exists():parser.error('fresh prefix required')
    result=dict(stage='before-on',writes=[],success=False);mark=LOG.stat().st_size;raw=b''
    def power(cmd):
        r=subprocess.run(['tomada',cmd],check=True,capture_output=True,timeout=90)
        result.setdefault('relay_output',[]).append(r.stdout.decode(errors='replace'))
        print(r.stdout.decode(errors='replace'),flush=True)
    def send(data):
        fd=os.open(PORT,os.O_WRONLY|os.O_NOCTTY|os.O_CLOEXEC)
        try:
            if os.write(fd,data)!=len(data):raise RuntimeError('short text write')
        finally:os.close(fd)
        result['writes'].append(data.hex())
    try:
        power('on');result['stage']='watching-power-on';start=time.monotonic();end=start+300
        print('POWER ON WATCH: normal logger retained; checking for boot, maximum300s',flush=True)
        deadline=None;stage='banner';version_mark=None
        while time.monotonic()<end:
            with LOG.open('rb') as f:f.seek(mark);raw=f.read(131072)
            if len(raw)==131072:raise RuntimeError('log capture bound reached')
            if any(x in raw for x in (b'Starting kernel',b'Booting Linux',b'Kernel command line:')):
                raise RuntimeError('unexpected OS start')
            if stage=='banner' and b'Press 1 means entering boot mode' in raw:
                send(b'1');stage='password';deadline=time.monotonic()+12
            elif stage=='password' and b'input bootmode password' in raw:
                send(b'Boot4128s!\r');stage='autoboot';deadline=time.monotonic()+12
            elif stage=='autoboot' and b'Hit any key to stop autoboot' in raw:
                send(b'\r');time.sleep(.3);version_mark=LOG.stat().st_size;send(b'version\r')
                stage='version';deadline=time.monotonic()+5
            elif stage=='version':
                with LOG.open('rb') as f:f.seek(version_mark);reply=f.read(32768)
                if b'U-Boot 2013.04 (Jul 06 2021 - 14:44:21)' in reply:
                    result.update(stage='verified-uboot-powered-on',success=True);break
            if deadline is not None and time.monotonic()>deadline:raise TimeoutError('boot stage '+stage)
            if stage=='banner' and any(x in raw for x in (b'Hit any key to stop autoboot',b'Booting kernel')):
                raise RuntimeError('boot mode not caught')
            time.sleep(.1)
        else:raise TimeoutError('no usable boot progression within300s')
    except BaseException as error:
        result['error']=repr(error);power('off');result['left_powered_off']=True
    finally:
        with LOG.open('rb') as f:f.seek(mark);raw=f.read(131072)
        Path(str(out)+'.rx.bin').write_bytes(raw)
        Path(str(out)+'.json').write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps(result,indent=2),flush=True)
    if not result['success']:raise SystemExit(1)

if __name__=='__main__':main()
