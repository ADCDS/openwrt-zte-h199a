#!/usr/bin/env python3
"""Boot flashed R206, bridge physical ports, test syd<->tiny; always power off."""
import importlib.util,json,os,re,secrets,subprocess,time
from pathlib import Path
from h199a_uart_fd import Lease,Console,UARTError
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/r206/flashed-iperf-1';OUT.mkdir(exist_ok=True)
spec=importlib.util.spec_from_file_location('base',ROOT/'tools/pilot-h199a-xmodem-r205.py');base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
def relay(expected):
 d=json.loads(base.command_run(['tomada','json']));
 if d.get('1') is not expected:raise UARTError('relay mismatch')
def audit(path):return json.loads(base.command_run(['sudo','-n','python3',str(ROOT/'tools/h199a_uart_fd.py'),'--audit-device',str(path)],15))
class Linux(Console):
 def cmd(self,text,timeout=15):
  if self.state!='linux':raise UARTError('linux shell required')
  nonce=secrets.token_hex(8);m=('__FLASH_R206_'+nonce).encode();footer="printf '\\n%s%s:%s\\n' '__FLASH_R206_' '"+nonce+"' \"$r\""
  self.write_all((text+'; r=$?; '+footer+'; '+footer).encode()+b'\r');out=self.until(re.compile(re.escape(m)+rb':(\d+)\r?\n'),timeout,131072);self.until(b'~ # ',3,16384)
  if re.search(re.escape(m)+rb':0\r?\n',out) is None:raise UARTError('command failed: '+text)
  return out.decode('utf8','replace')
def run(argv,timeout=30):return subprocess.run(argv,check=True,capture_output=True,text=True,timeout=timeout).stdout

def main():
 result={'success':False,'flash_already_verified':True};(OUT/'result.json').write_text(json.dumps(result,indent=2));lease=None;powered=False
 try:
  base.command_run(['tomada','off']);relay(False);time.sleep(4);base.command_run(['systemctl','--user','stop',base.UNIT]);lease=Lease.acquire(base.PORT,base.LOCK,powered_off=True,audit=audit)
  c=Linux(lease.transport);c.state='linux-boot';base.command_run(['tomada','on']);powered=True
  boot=c.until(re.compile(rb'(?:^|\r?\n)~ # '),75,262144);(OUT/'boot.log').write_bytes(boot)
  if b'Linux version 6.6.151' not in boot or b'ro init=/bin/sh' not in boot or b'datapath init at probe (cold)' not in boot:raise UARTError('flashed R206 markers absent')
  c.state='linux'
  cmds=['mount -t proc proc /proc','mount -t sysfs sysfs /sys','mount -t tmpfs tmpfs /tmp','mount -t tmpfs tmpfs /dev','mknod /dev/null c 1 3','ifconfig lo 127.0.0.1 up','ifconfig eth1 up','ifconfig eth2 up','ifconfig eth3 up','brctl addbr br0','brctl addif br0 eth1','brctl addif br0 eth2','brctl addif br0 eth3','ifconfig br0 up','cat /sys/class/net/eth1/carrier; cat /sys/class/net/eth2/carrier; cat /sys/class/net/eth3/carrier']
  logs=[]
  for x in cmds:logs.append(c.cmd(x,25))
  (OUT/'setup.log').write_text('\n'.join(logs))
  run(['sudo','-n','ip','addr','replace','192.168.9.2/24','dev','enx00e04c125990'])
  result['ping_syd_to_tiny']=run(['ping','-c','20','-i','.2','-W','2','-I','enx00e04c125990','192.168.9.3'],15)
  run(['ssh','-o','BatchMode=yes','tiny','pkill -x iperf3 || true; nohup iperf3 -s >/tmp/iperf-r206.log 2>&1 </dev/null &'],10)
  time.sleep(1)
  tests=[('tcp_syd_tiny',['iperf3','-c','192.168.9.3','-B','192.168.9.2','-t','10','-J']),('tcp_tiny_syd',['iperf3','-c','192.168.9.3','-B','192.168.9.2','-R','-t','10','-J']),('udp_syd_tiny',['iperf3','-c','192.168.9.3','-B','192.168.9.2','-u','-b','10M','-t','10','-J']),('udp_tiny_syd',['iperf3','-c','192.168.9.3','-B','192.168.9.2','-u','-R','-b','10M','-t','10','-J'])]
  for name,argv in tests:
   text=run(argv,30);(OUT/(name+'.json')).write_text(text);result[name]=json.loads(text).get('end',{})
  result['success']=True
 except BaseException as e:result['error']=repr(e);raise
 finally:
  try:run(['sudo','-n','ip','addr','del','192.168.9.2/24','dev','enx00e04c125990'],5)
  except Exception:pass
  try:run(['ssh','-o','BatchMode=yes','tiny','pkill -x iperf3 || true'],10)
  except Exception:pass
  if powered:base.command_run(['tomada','off']);time.sleep(4);relay(False);powered=False
  if lease:lease.release(powered_off=True)
  base.command_run(['systemctl','--user','start',base.UNIT]);result['left_powered_off']=True;result['logger_restored']=base.service_properties().get('ActiveState')=='active';(OUT/'result.json').write_text(json.dumps(result,indent=2))
if __name__=='__main__':main()
