#!/usr/bin/env python3
"""PARENT ONLY: exclusive-UART 1024-byte RAM pilot, then leave router powered OFF.

Never flashes, boots an OS, runs U-Boot networking, changes baud/env, or assumes
ACKs prove RAM. Power off and verify relay state before closing/opening UART;
restore the logger only after power-off plus a complete zero-holder audit.
There is NO automatic console recovery after unknown XMODEM outcomes.
Run as the bench user (not root); sudo is used only for metadata-only FD audits.
"""
import argparse
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import time

from h199a_uart_fd import Lease, Console, UARTError
from xmodem_h199a import TransferPlan, SenderOptions

ROOT=Path(__file__).resolve().parents[1]
RIG=ROOT.parent
PORT='/dev/h199a-uart'
LOCK='/tmp/h199a-uart-log.lock'
UNIT='h199a-uart-log.service'
BACKUP_SHA='559864fe931dcd66ec891823bd945f4469bdcf72e8490e6257b064d7197440c4'
LINK_BASE=0x47edf800


def command_run(argv, timeout=90):
    # Kill the entire helper process group on timeout, not just its shell parent.
    with subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                          start_new_session=True,close_fds=True) as proc:
        try:out,err=proc.communicate(timeout=timeout)
        except BaseException:
            os.killpg(proc.pid,signal.SIGKILL);proc.communicate();raise
        if proc.returncode:
            raise UARTError(f'{argv[0]} exit{proc.returncode}: {err.decode(errors="replace")}')
        return out


def service_properties():
    text=command_run(['systemctl','--user','show',UNIT,'-p','ActiveState','-p','SubState',
                     '-p','MainPID','-p','ControlGroup','-p','Restart','-p','KillMode',
                     '-p','FragmentPath','-p','DropInPaths']).decode()
    return dict(line.split('=',1) for line in text.splitlines())


def validate_info(text):
    def field(name):
        found=re.findall(r'^'+re.escape(name)+r'\s*=\s*0x([0-9a-fA-F]+)',text,re.M)
        if len(found)!=1:raise UARTError('missing/ambiguous bdinfo field '+name)
        return int(found[0],16)
    start,size,reloc,offset=(field(n) for n in ('-> start','-> size','relocaddr','reloc off'))
    if start!=0x40000000 or size!=0x08000000 or reloc!=0x47f00000+offset or not 0<=offset<0x100000:
        raise UARTError('unexpected RAM/relocation')
    return dict(ram_start=start,ram_size=size,relocaddr=reloc,reloc_off=offset)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute-1024-byte-pilot',action='store_true',required=True)
    parser.add_argument('--payload',type=Path,required=True)
    parser.add_argument('--output-prefix',type=Path,required=True)
    args=parser.parse_args()
    payload=args.payload.read_bytes()
    if len(payload)!=1024:parser.error('pilot payload must be EXACTLY1024 bytes')
    plan=TransferPlan(payload)
    backup=(RIG/'h199a-firmware/mtd0-bootloader.bin').read_bytes()
    if hashlib.sha256(backup).hexdigest()!=BACKUP_SHA:parser.error('unverified own-H backup')
    if os.geteuid()==0:parser.error('run as the bench user, not root')
    suffixes=('.json','.rx.bin','.rx.txt','.readback.bin')
    paths={s:Path(str(args.output_prefix)+s) for s in suffixes}
    if any(p.exists() for p in paths.values()):parser.error('fresh output prefix required')
    result=dict(phase='preflight',success=False,payload_sha256=hashlib.sha256(payload).hexdigest(),
                payload_bytes=1024,backup_sha256=BACKUP_SHA,events=[],audits=[],
                flash_writes=False,uboot_network_commands=False,os_boot_requested=False)
    lease=None;stopped=False;touched_power=False;off_confirmed=False;readback=b''
    def audit(path):
        data=json.loads(command_run(['sudo','-n','python3',str(ROOT/'tools/h199a_uart_fd.py'),
                                     '--audit-device',str(path)],15))
        result['audits'].append(data)
        return data
    def relay_state(expected):
        data=json.loads(command_run(['tomada','json']))
        if data.get('1') is not expected:raise UARTError('relay state missing/not confirmed')
        result['events'].append(dict(relay_confirmed=expected,monotonic=time.monotonic()))
    def power_off():
        nonlocal off_confirmed,touched_power
        touched_power=True;off_confirmed=False
        command_run(['tomada','off']);relay_state(False);off_confirmed=True
    try:
        before=service_properties();result['service_before']=before
        if (before.get('ActiveState')!='active' or before.get('SubState')!='running' or
            before.get('KillMode')!='control-group' or before.get('Restart')!='always' or
            before.get('DropInPaths')!='' or not before.get('ControlGroup') or
            before.get('FragmentPath')!=str(Path.home()/'.config/systemd/user'/UNIT)):
            raise UARTError('unexpected effective logger supervision')
        initial=audit(PORT)
        if initial.get('complete') is not True or initial.get('errors')!=[]:
            raise UARTError('incomplete initial FD audit')
        result['phase']='power-off-before-ownership'
        power_off();time.sleep(4)
        command_run(['systemctl','--user','stop',UNIT]);stopped=True
        after=service_properties();result['service_stopped']=after
        if after.get('ActiveState')!='inactive' or after.get('SubState')!='dead' or after.get('MainPID')!='0':
            raise UARTError('logger supervisor did not stop')
        events=Path('/sys/fs/cgroup'+before['ControlGroup'])/'cgroup.events'
        if events.exists() and not re.search(r'^populated 0$',events.read_text(),re.M):
            raise UARTError('logger cgroup still populated')
        lease=Lease.acquire(PORT,LOCK,powered_off=off_confirmed,audit=audit)
        result['lease']=dict(device=lease.expected,lock=lease.lock_identity,fd=lease.fd,pid=os.getpid())
        # Explicitly record/drain pre-power-on input; NEVER flush in protocol mode.
        end=time.monotonic()+2
        while lease.transport.read(4096,.1):
            if time.monotonic()>=end:raise UARTError('UART not quiet while powered off')
        result['pre_power_rx_bytes']=len(lease.transport.received)
        c=Console(lease.transport)
        result['phase']='fresh-nonnetwork-boot-entry';off_confirmed=False
        command_run(['tomada','on'])
        # Preserve the empirically proven enter-uboot.sh timing relative to helper return.
        time.sleep(.7);c.boot_token(b'1')
        relay_state(True)
        c.until(b'input bootmode password',timeout=12)
        c.boot_token(b'Boot4128s!\r')
        c.until(b'Hit any key to stop autoboot',timeout=12)
        c.boot_token(b'\r')
        c.confirm_uboot()
        info=validate_info(c.command('bdinfo').decode('ascii','strict'));result['bdinfo']=info
        offset=info['reloc_off'];result['code_checks']=[]
        for name,linked in [('xmodem_handler',0x47f2d814),('xmodem_receiver',0x47f2d5b8)]:
            actual=c.memory(linked+offset,8);pos=linked-LINK_BASE
            result['code_checks'].append(dict(name=name,address=hex(linked+offset),actual_hex=actual.hex(),
                                              expected_hex=backup[pos:pos+32].hex()))
            if actual!=backup[pos:pos+32]:raise UARTError('live XMODEM code differs from own-H backup')
        # Software state only. Do not require warm table geometry on a cold boot.
        result['cold_rx_table_hex']=c.memory(0x47f5a648+offset,16).hex()
        result['cold_tx_cursor_base_hex']=c.memory(0x47f5a694+offset,2).hex()
        lease.recheck()
        result['phase']='pilot-transfer'
        sent=c.transfer(plan,options=SenderOptions(total_timeout=30))
        result['protocol']=asdict(sent);result['prompt_verified']=c.state=='console'
        result['phase']='complete-pilot-readback'
        readback=b''.join(c.memory(0x42000000+i,16) for i in range(0,1024,64))
        result['readback_sha256']=hashlib.sha256(readback).hexdigest()
        if readback!=payload:raise UARTError('pilot RAM byte comparison failed')
        result['full_readback_equal']=True;result['success']=True
        result['phase']='verified-pilot'
    except BaseException as error:
        result['error']=repr(error)
        print('PILOT STOP:',result['phase'],repr(error),flush=True)
    finally:
        # Unknown receiver state is recovered ONLY by external power-off. No UART
        # writes, CR/CAN retry, termios restoration or logger restart beforehand.
        if touched_power:
            while True:
                try:
                    power_off();time.sleep(4)
                    if lease is not None and lease.fd is not None:
                        result['transport_rx_bytes']=len(lease.transport.received)
                        result['transport_tx_accepted']=lease.transport.tx_accepted
                        lease.release(powered_off=off_confirmed)
                    if stopped:
                        clean=audit(PORT)
                        if clean.get('complete') is not True or clean.get('errors')!=[] or clean.get('holders')!=[]:
                            raise UARTError('cannot restore logger: leftover/unknown UART holder')
                        command_run(['systemctl','--user','start',UNIT])
                        restored=service_properties();result['service_restored']=restored
                        if restored.get('ActiveState')!='active' or restored.get('SubState')!='running':
                            raise UARTError('logger restoration not running')
                    result['left_powered_off']=True
                    break
                except Exception as error:
                    result['recovery_error']=repr(error);result['success']=False
                    paths['.json'].write_text(json.dumps(result,indent=2)+'\n')
                    if lease is None or lease.fd is None:
                        print('RECOVERY STOP; do not use UART helpers:',repr(error),flush=True)
                        break
                    # Retain the actual FD/lock rather than implicitly close an
                    # uncertain live receiver. Only retry EXTERNAL power-off;
                    # no UART I/O or logger restart. Parent must inspect this
                    # managed job; do not kill it as a substitute for power-off.
                    print('QUARANTINE: holding UART; external power-off retry in30s:',repr(error),flush=True)
                    time.sleep(30)
        if lease is not None:
            raw=bytes(lease.transport.received)
            paths['.rx.bin'].write_bytes(raw)
            paths['.rx.txt'].write_text(raw.decode('utf-8','replace'))
        paths['.readback.bin'].write_bytes(readback)
        paths['.json'].write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2),flush=True)
    if not result['success']:raise SystemExit(1)


if __name__=='__main__':main()
