#!/usr/bin/env python3
"""Explicitly authorized bank-A R206 flash transaction; never touches bank B/saveenv."""
import hashlib, importlib.util, json, os, re, time
from pathlib import Path
from h199a_uart_fd import Lease, Console, PROMPT, UARTError

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('base',ROOT/'tools/pilot-h199a-xmodem-r205.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
PARTS=[('kernel',0x700000,0x300000,'2c33378b0903bca26eba16624cbb04f74f9e9031ba8539f6f79417df03a5dea6'),('rootfs',0xa00000,0xd20000,'633fe4d4e8c4f12dfd8e40c8769cf8b4faca96b95bd0fcdd092e1b3e1f40db75'),('header',0x1720000,0x20000,'920c1f8575561a83c20b7bad6f2501c5ceb6ee8b7dd32b27100179a23aa897a1')]

def relay_state(expected):
    data=json.loads(base.command_run(['tomada','json']))
    if data.get('1') is not expected: raise UARTError('relay state missing/not confirmed')
    return expected

def audit(path):
    return json.loads(base.command_run(['sudo','-n','python3',str(ROOT/'tools/h199a_uart_fd.py'),'--audit-device',str(path)],15))

class FlashConsole(Console):
    def run(self,text,timeout):
        if self.state!='console': raise UARTError('verified console required')
        if self.io.read(1,0): raise UARTError('unexpected input before command')
        sent=text.encode()+b'\r';self.write_all(sent);out=self.until(PROMPT,timeout=timeout,limit=262144)
        if not out.startswith(sent): raise UARTError('corrupt command echo')
        return out

def main():
    stage=ROOT/'artifacts/r206/flash-stage';out=stage/'flash-result.json';result={'authorized':True,'saveenv':False,'bank_b_touched':False,'parts':[],'success':False};out.write_text(json.dumps(result,indent=2))
    for name,off,n,sha in PARTS:
        p=stage/name;b=p.read_bytes()
        if len(b)!=n or hashlib.sha256(b).hexdigest()!=sha: raise SystemExit('staged part mismatch: '+name)
    before=base.service_properties();lease=None;powered=False
    try:
        relay_state(False)
        base.command_run(['systemctl','--user','stop',base.UNIT]);time.sleep(1)
        lease=Lease.acquire(base.PORT,base.LOCK,powered_off=True,audit=audit);c=FlashConsole(lease.transport)
        base.command_run(['tomada','on']);powered=True;time.sleep(.7)
        c.boot_token(b'1');c.until(b'input bootmode password',12);c.boot_token(b'Boot4128s!\r');c.until(b'Hit any key to stop autoboot',12);c.boot_token(b'\r');c.confirm_uboot()
        c.run('setenv ipaddr 192.168.1.1',5);c.run('setenv serverip 192.168.1.100',5)
        for name,off,n,sha in PARTS:
            rec={'name':name,'offset':hex(off),'bytes':n,'sha256':sha};result['parts'].append(rec);out.write_text(json.dumps(result,indent=2))
            t=c.run(f'tftp 0x42000000 {name}',180)
            if f'Bytes transferred = {n} ({n:x} hex)'.encode() not in t: raise UARTError(name+' TFTP byte count mismatch')
            e=c.run(f'nand erase 0x{off:x} 0x{n:x}',180)
            if b'Skipping bad block' in e or not re.search(rb'OK\s*\r?\n',e): raise UARTError(name+' erase not clean')
            w=c.run(f'nand write 0x42000000 0x{off:x} 0x{n:x}',180)
            if b'written: OK' not in w or b'ERROR' in w: raise UARTError(name+' write failed')
            r=c.run(f'nand read 0x44000000 0x{off:x} 0x{n:x}',180)
            if b'read: OK' not in r or b'ERROR' in r: raise UARTError(name+' readback failed')
            q=c.run(f'cmp.b 0x42000000 0x44000000 0x{n:x}',180)
            if f'Total of {n} byte(s) were the same'.encode() not in q: raise UARTError(name+' readback differs')
            rec['tftp_exact']=rec['erase_clean']=rec['write_ok']=rec['readback_equal']=True;out.write_text(json.dumps(result,indent=2))
        result['success']=True;out.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    except BaseException as e:
        result['error']=repr(e);out.write_text(json.dumps(result,indent=2));raise
    finally:
        if powered:
            while True:
                try: base.command_run(['tomada','off']);time.sleep(4)
                except Exception: time.sleep(30);continue
                try: relay_state(False);powered=False;break
                except Exception: time.sleep(30)
        if lease: lease.release(powered_off=True)
        base.command_run(['systemctl','--user','start',base.UNIT])
        try: relay_state(False);result['left_powered_off']=True
        except Exception: result['left_powered_off']=False
        result['logger_restored']=base.service_properties().get('ActiveState')=='active';out.write_text(json.dumps(result,indent=2))
if __name__=='__main__':main()
