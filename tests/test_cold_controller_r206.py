"""Fully mocked power/service/UART/network orchestration; bench never touched."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
spec=importlib.util.spec_from_file_location('cold_controller_r206',ROOT/'tools/cold-h199a-r206.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
from xmodem_h199a import SendResult
from bench_artifacts import needs_artifacts


@needs_artifacts()
class ControllerTests(unittest.TestCase):
    def execute(self,failure=None):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);payload=root/'tcp';payload.write_bytes(bytes(4*1024*1024))
            backup=bytes(range(256))*4096
            (root/'h199a-firmware').mkdir()
            (root/'h199a-firmware/mtd0-bootloader.bin').write_bytes(backup)
            source=b'/* synthetic matching source copies for preflight */\n'
            for name in (
                'files/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c',
                'openwrt/target/linux/armsr/files-6.6/drivers/net/ethernet/zte/zx279128-eth.c',
                'openwrt/build_dir/target-arm_cortex-a9_musl_eabi/linux-armsr_armv7/linux-6.6.151/drivers/net/ethernet/zte/zx279128-eth.c',
            ):
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(source)
            if failure=='backup-preflight':
                (root/'h199a-firmware/mtd0-bootloader.bin').write_bytes(b'corrupt backup')
            if failure=='source-preflight':
                path.write_bytes(b'different generated source')
            events=[];relay=False
            active=dict(ActiveState='active',SubState='running',MainPID='123',ControlGroup='/__r206_test_absent',
                        KillMode='control-group',Restart='always',DropInPaths='',
                        FragmentPath=str(Path.home()/'.config/systemd/user'/p.base.UNIT))
            stopped=dict(active,ActiveState='inactive',SubState='dead',MainPID='0')
            io=types.SimpleNamespace(received=bytearray(),tx_accepted=0,read=lambda *a:b'')
            class FakeLease:
                fd=555;expected={};lock_identity={};transport=io
                def release(self,**kw):
                    events.append('release');assert relay is False and kw['powered_off'] is True;self.fd=None
                def recheck(self):events.append('recheck')
            lease=FakeLease()
            def acquire(*a,**kw):
                events.append('acquire');assert relay is False and kw['powered_off'] is True;return lease
            def run(argv,*args):
                nonlocal relay
                if argv[0]=='tomada':
                    if argv[1]=='json':events.append('verify-relay');return json.dumps({'1':relay}).encode()
                    relay=argv[1]=='on';events.append('on' if relay else 'off');return b''
                if argv[:2]==['systemctl','--user']:
                    events.append(argv[2]);assert relay is False;return b''
                if argv[:2]==['sudo','-n']:
                    events.append('audit');return b'{"complete":true,"errors":[],"holders":[]}'
                raise AssertionError('unexpected command '+str(argv))
            class FakeConsole:
                state='console'
                def __init__(self,*a):self.command_log=[];self.uboot_log=[]
                def boot_token(self,b):events.append('token:'+repr(b))
                def until(self,*a,**kw):
                    if failure=='entry':raise RuntimeError('failed entry')
                def confirm_uboot(self):events.append('version')
                def command(self,text):return b''
                def fixed_uboot(self,text):events.append('verify-setting');return b'verify=yes\n'
                def memory(self,addr,count):
                    if addr in (0x47fef648,0x47fef694):return bytes(count*4)
                    pos=addr-0x95000-p.base.LINK_BASE;return backup[pos:pos+count*4]
                def transfer(self,plan,**kw):
                    events.append('transfer')
                    if failure=='eot':raise RuntimeError('EOT outcome uncertain')
                    return SendResult(len(plan.payload),plan.padded_bytes,plan.blocks,plan.blocks,0,3161089,280)
                def crc_gate(self,image):
                    events.append('crc')
                    if failure=='crc':raise RuntimeError('bad checksum')
                    return dict(valid=True),b'CRC verified'
                def boot(self):events.append('boot');return b'fake boot',dict(selected='0')
            def network(*a):
                events.append('network')
                if failure=='network':raise RuntimeError('bad packet identities')
            argv=['cold','--execute-cold-r204','--image',str(ROOT/'artifacts/r204/r204.kernel'),
                  '--tcp-payload',str(payload),'--output-dir',str(root/'run')]
            info=dict(reloc_off=0x95000,relocaddr=0x47f95000,ram_start=0x40000000,ram_size=0x8000000)
            with patch.object(sys,'argv',argv),patch.object(p.base,'RIG',root),patch.object(p.base,'BACKUP_SHA',hashlib.sha256(backup).hexdigest()),patch.object(p,'ROOT',root),patch.object(p,'SOURCE_SHA',hashlib.sha256(source).hexdigest()),patch.object(p.base,'command_run',run),patch.object(p.base,'service_properties',side_effect=[active,stopped,active]),patch.object(p.Lease,'acquire',acquire),patch.object(p,'ColdConsole',FakeConsole),patch.object(p.base,'validate_info',return_value=info),patch.object(p,'network_suite',network),patch.object(p.time,'sleep',lambda n:None):
                if failure:
                    with self.assertRaises(SystemExit):p.main()
                else:p.main()
            if failure in ('backup-preflight','source-preflight'):
                self.assertEqual(events,[])
                self.assertFalse((root/'run').exists())
                return events,None
            return events,json.loads((root/'run/result.json').read_text())
    def test_bad_backup_rejected_before_any_bench_action(self):
        self.execute('backup-preflight')
    def test_source_drift_rejected_before_any_bench_action(self):
        self.execute('source-preflight')
    def test_success_power_and_crc_before_boot_network(self):
        events,r=self.execute();self.assertTrue(r['success']);self.assertTrue(r['left_powered_off'])
        self.assertLess(events.index('off'),events.index('stop'));self.assertLess(events.index('stop'),events.index('acquire'))
        self.assertEqual(events[events.index('on')+1],"token:b'1'")
        self.assertLess(events.index('transfer'),events.index('crc'));self.assertLess(events.index('crc'),events.index('boot'))
        self.assertLess(events.index('boot'),events.index('network'))
        self.assertEqual(events[-5:],['off','verify-relay','release','audit','start'])
    def test_failed_entry_never_transfers(self):
        events,r=self.execute('entry');self.assertNotIn('transfer',events);self.assertFalse(r['success'])
        # Entry diagnostics must say WHICH stage died and how many bytes it saw.
        self.assertEqual(r['entry']['failed_stage'],'password-prompt')
        self.assertEqual([s['name'] for s in r['entry']['stages']],['press-1'])
        self.assertIn('failed_stage_rx_bytes',r['entry'])
        self.assertIn('uboot_commands',r)
    def test_uncertain_eot_never_crc_or_boot(self):
        events,r=self.execute('eot');self.assertNotIn('crc',events);self.assertNotIn('boot',events)
        self.assertEqual(events[events.index('transfer')+1:],['off','verify-relay','release','audit','start'])
    def test_failed_crc_never_boots(self):
        events,r=self.execute('crc');self.assertNotIn('boot',events);self.assertTrue(r['left_powered_off'])
    def test_failed_ethernet_not_success(self):
        events,r=self.execute('network');self.assertFalse(r['success']);self.assertTrue(r['left_powered_off'])

if __name__=='__main__':unittest.main()
