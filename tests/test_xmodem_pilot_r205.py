"""Pilot orchestration tests with ALL power/service/UART operations mocked."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
spec=importlib.util.spec_from_file_location('pilot_r205',Path(__file__).resolve().parents[1]/'tools/pilot-h199a-xmodem-r205.py')
p=importlib.util.module_from_spec(spec);spec.loader.exec_module(p)
from xmodem_h199a import SendResult


class PilotTests(unittest.TestCase):
    def run_pilot(self, failure=None):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);(root/'h199a-firmware').mkdir()
            backup=bytes(1048576);(root/'h199a-firmware/mtd0-bootloader.bin').write_bytes(backup)
            payload=bytes(range(256))*4;(root/'payload').write_bytes(payload)
            events=[];relay=False
            active=dict(ActiveState='active',SubState='running',MainPID='123',ControlGroup='/__r205_test_absent',
                        KillMode='control-group',Restart='always',DropInPaths='',
                        FragmentPath=str(Path.home()/'.config/systemd/user'/p.UNIT))
            stopped=dict(active,ActiveState='inactive',SubState='dead',MainPID='0')
            io=types.SimpleNamespace(received=bytearray(),tx_accepted=0,read=lambda *a:b'')
            class FakeLease:
                fd=555;expected={};lock_identity={};transport=io
                def release(self,**kw):
                    events.append('release');assert relay is False and kw['powered_off'] is True;self.fd=None
                def recheck(self):events.append('recheck')
            lease=FakeLease()
            def acquire(*a,**kw):
                events.append('acquire');assert relay is False and kw['powered_off'] is True
                return lease
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
                def __init__(self,*a):pass
                def boot_token(self,b):events.append('boot-token:'+repr(b))
                def until(self,*a,**kw):
                    if failure=='entry':raise RuntimeError('unexpected OS boot')
                def confirm_uboot(self):events.append('version')
                def command(self,text):return b''
                def memory(self,addr,count):
                    if 0x42000000<=addr<0x42000400:
                        off=addr-0x42000000
                        return (b'bad' if failure=='readback' else payload[off:off+4*count])
                    return bytes(4*count)
                def transfer(self,*a,**kw):
                    events.append('transfer')
                    if failure=='eot':raise RuntimeError('EOT ACK uncertain')
                    return SendResult(1024,1024,1,1,0,1030,.1)
            argv=['pilot','--execute-1024-byte-pilot','--payload',str(root/'payload'),'--output-prefix',str(root/'result')]
            info=dict(reloc_off=0x95000,relocaddr=0x47f95000,ram_start=0x40000000,ram_size=0x8000000)
            with patch.object(sys,'argv',argv),patch.object(p,'RIG',root),patch.object(p,'BACKUP_SHA',hashlib.sha256(backup).hexdigest()),patch.object(p,'command_run',run),patch.object(p,'service_properties',side_effect=[active,stopped,active]),patch.object(p.Lease,'acquire',acquire),patch.object(p,'Console',FakeConsole),patch.object(p,'validate_info',return_value=info),patch.object(p.time,'sleep',lambda n:None):
                if failure:
                    with self.assertRaises(SystemExit):p.main()
                else:p.main()
            result=json.loads((root/'result.json').read_text())
            return events,result

    def test_success_power_ownership_and_full_readback(self):
        events,result=self.run_pilot()
        self.assertTrue(result['success']);self.assertTrue(result['full_readback_equal'])
        self.assertTrue(result['left_powered_off'])
        self.assertLess(events.index('off'),events.index('stop'))
        self.assertLess(events.index('stop'),events.index('acquire'))
        on=events.index('on')
        self.assertEqual(events[on+1],"boot-token:b'1'")
        self.assertEqual(events[on+2],'verify-relay')
        self.assertLess(events.index('recheck'),events.index('transfer'))
        self.assertEqual(events[-5:],['off','verify-relay','release','audit','start'])

    def test_uncertain_eot_uses_only_poweroff_before_release(self):
        events,result=self.run_pilot('eot')
        self.assertFalse(result['success']);self.assertTrue(result['left_powered_off'])
        self.assertEqual(events[events.index('transfer')+1:],['off','verify-relay','release','audit','start'])

    def test_bad_readback_not_reported_success(self):
        _,result=self.run_pilot('readback')
        self.assertFalse(result['success']);self.assertNotIn('full_readback_equal',result)

    def test_failed_entry_never_enters_receiver(self):
        events,result=self.run_pilot('entry')
        self.assertNotIn('transfer',events);self.assertTrue(result['left_powered_off'])

    def test_bdinfo_bounds_and_duplicates(self):
        good='-> start = 0x40000000\n-> size = 0x08000000\nrelocaddr = 0x47f95000\nreloc off = 0x95000\n'
        self.assertEqual(p.validate_info(good)['reloc_off'],0x95000)
        for bad in [good.replace('08000000','10000000'),good.replace('47f95000','47f85000'),good+'reloc off = 0x95000\n']:
            with self.assertRaises(p.UARTError):p.validate_info(bad)

if __name__=='__main__':unittest.main()
