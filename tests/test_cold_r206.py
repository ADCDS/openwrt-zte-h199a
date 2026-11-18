"""Offline R206 gates and loopback TCP only; never opens bench UART/relay."""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import re
import socket
import struct
import sys
import time
import unittest
import urllib.request
from unittest.mock import patch
import zlib
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
import h199a_cold_r206 as m
from h199a_uart_fd import UARTError
from bench_artifacts import needs_artifacts
ROOT=Path(__file__).resolve().parents[1]


def synthetic(**changes):
    body=changes.pop('body',b'test-kernel')
    values=dict(magic=0x27051956,hcrc=0,stamp=1,n=len(body),load=0x40008000,entry=0x40008000,
                dcrc=zlib.crc32(body),os_=5,arch=2,kind=2,compression=0,name=b'h199a-r204-diag')
    values.update(changes)
    h=struct.pack('>7I4B32s',*values.values());values['hcrc']=zlib.crc32(h)
    return bytes(32)+struct.pack('>7I4B32s',*values.values())+body+bytes(30)


def crc_text(image):
    return (f'## Booting kernel from Legacy Image at 42000020 ...\r\n'
            f'   Image Name:   {image.name}\r\n'
            '   Image Type:   ARM Linux Kernel Image (uncompressed)\r\n'
            f'   Data Size:    {image.payload_bytes} Bytes = 2.5 MiB\r\n'
            '   Load Address: 40008000\r\n   Entry Point:  40008000\r\n'
            '   Verifying Checksum ... OK\r\n=> ').encode()


class FakeIO:
    def __init__(self,responses):self.responses=responses;self.pending=bytearray();self.writes=[];self.writes_allowed=True
    def read(self,n,t):
        if self.pending:
            b=bytes(self.pending[:n]);del self.pending[:n];return b
        if t:time.sleep(min(t,.005))
        return b''
    def pushback(self,b):self.pending[:0]=b
    def write(self,b,t):
        if not self.writes_allowed:raise UARTError('blocked')
        self.writes.append(b);self.pending.extend(self.responses(b));return len(b)


@needs_artifacts()
class ImageTests(unittest.TestCase):
    def test_valid_metadata_and_crcs(self):
        i=m.parse_image(synthetic());self.assertEqual(i.payload_bytes,11)
    def test_geometry_type_and_name_rejected(self):
        for change in [dict(magic=0),dict(load=0x42000000),dict(entry=0),dict(n=9999),dict(n=0),dict(arch=3),dict(compression=1),dict(name=b'other')]:
            with self.assertRaises(ValueError):m.parse_image(synthetic(**change))
    def test_corrupt_header_payload_padding(self):
        good=synthetic()
        for pos in (40,96,len(good)-1):
            b=bytearray(good);b[pos]^=1
            with self.assertRaises(ValueError):m.parse_image(bytes(b))
    def test_only_exact_r204_approved(self):
        with self.assertRaises(ValueError):m.require_r204(synthetic())
        i=m.require_r204((ROOT/'artifacts/r204/r204.kernel').read_bytes())
        self.assertEqual((i.payload_bytes,i.header_crc,i.data_crc),(2667489,0x4ff34051,0x9451d858))
    def test_verify_setting_semantics(self):
        for value in (b'yes',b'Yes',b'True',b't',b'1'):
            self.assertEqual(m.verify_enabled(b'printenv verify\r\nverify='+value+b'\r\n=> '),'enabled')
        self.assertIn('absent',m.verify_enabled(b'printenv verify\r\n## Error: "verify" not defined\r\n=> '))
        for text in (b'verify=no\n',b'verify=0\n',b'verify=\n',b'blah',b'verify=y\nverify=y\n'):
            with self.assertRaises(UARTError):m.verify_enabled(text)
    def test_crc_stage_requires_explicit_success_and_no_execution(self):
        i=m.parse_image(synthetic());good=crc_text(i);m.validate_crc_output(good,i)
        for bad in (good.replace(b'Checksum ... OK',b'Checksum ... BAD'),good.replace(b'Verifying',b'Skipping'),good+b'Starting kernel',good+b'Loading Kernel Image ... OK',good.replace(b'40008000',b'42000000'),good+good):
            with self.assertRaises(UARTError):m.validate_crc_output(bad,i)


@needs_artifacts()
class ConsoleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.image=m.require_r204((ROOT/'artifacts/r204/r204.kernel').read_bytes())
        cls.bootlog=(ROOT/'artifacts/r204/ramboot.log').read_bytes()
    def console(self,header_ok=True,verify=b'## Error: "verify" not defined\r\n=> ',crc=None):
        def response(b):
            if b==b'printenv verify\r':return verify
            if b==b'bootm start 0x42000020\r':return crc if crc is not None else crc_text(self.image)
            if b==b'bootm 0x42000020\r':return self.bootlog
            raise AssertionError(b)
        io=FakeIO(response);c=m.ColdConsole(io);c.state='console'
        c.memory=lambda a,n:self.image.data[a-0x42000000:a-0x42000000+4*n] if header_ok else bytes(4*n)
        return c,io
    def test_crc_gate_then_boot_once(self):
        c,io=self.console();gate,_=c.crc_gate(self.image);self.assertTrue(gate['prefix_header_equal'])
        boot,origin=c.boot();self.assertEqual(c.state,'linux');self.assertEqual(origin['selected'],'0')
        self.assertEqual(origin['datapath_branch'],'cold-full-init')
        self.assertEqual(io.writes,[b'printenv verify\r',b'bootm start 0x42000020\r',b'bootm 0x42000020\r'])
        with self.assertRaises(UARTError):c.boot()
    def test_no_boot_without_gate(self):
        c,io=self.console()
        with self.assertRaises(UARTError):c.boot()
        self.assertEqual(io.writes,[])
    def test_header_mismatch_forbids_boot_or_crc_command(self):
        c,io=self.console(header_ok=False)
        with self.assertRaises(UARTError):c.crc_gate(self.image)
        self.assertEqual(io.writes,[]);self.assertFalse(io.writes_allowed)
    def test_disabled_verify_stops_before_bootm(self):
        c,io=self.console(verify=b'verify=no\r\n=> ')
        with self.assertRaises(UARTError):c.crc_gate(self.image)
        self.assertEqual(io.writes,[b'printenv verify\r'])
    def test_unexpected_os_in_crc_stage_fails_closed(self):
        c,io=self.console(crc=b'Starting kernel ...\r\n')
        with self.assertRaises(UARTError):c.crc_gate(self.image)
        self.assertFalse(io.writes_allowed)
    def test_metadata_tamper_is_rejected(self):
        c,io=self.console()
        with self.assertRaises(UARTError):c.crc_gate(replace(self.image,payload_bytes=1))
        self.assertEqual(io.writes,[])
    def test_linux_split_marker_and_async_text(self):
        def response(b):
            token=re.search(rb"'([a-f0-9]{16})'",b)[1]
            return b+b'\r\nbackground health\r\noutput\r\n__H199A_R206_'+token+b':0\r\n~ # '
        io=FakeIO(response);c=m.ColdConsole(io);c.state='linux'
        output=c.linux('ifconfig lo');self.assertIn('output',output)
        self.assertNotRegex(io.writes[0],rb'__H199A_R206_[a-f0-9]{16}')
    def test_linux_recovers_when_first_footer_is_interleaved(self):
        def response(b):
            token=re.findall(rb"'([a-f0-9]{16})'",b)[0]
            return (b'\r\n__H199A_R206_'+token[:5]+b'[  1.0] printk\r\n'+token[5:]+b':0\r\n'
                    b'__H199A_R206_'+token+b':0\r\n~ # ')
        io=FakeIO(response);c=m.ColdConsole(io);c.state='linux'
        self.assertIn('printk',c.linux('ifconfig lo'))

    def test_linux_nonzero_rc_blocks_further_commands(self):
        def response(b):
            token=re.search(rb"'([a-f0-9]{16})'",b)[1]
            return b'\r\n__H199A_R206_'+token+b':1\r\n~ # '
        io=FakeIO(response);c=m.ColdConsole(io);c.state='linux'
        with self.assertRaises(UARTError):c.linux('ifconfig lo')
        self.assertFalse(io.writes_allowed)
    def test_no_shell_from_unverified_state_and_no_flash_commands(self):
        c,io=self.console()
        with self.assertRaises(UARTError):c.linux('ifconfig lo')
        for command in ('nand erase','reboot','mount -o remount,rw /','echo 0 > /proc/zx_eth_regs','cat /dev/mtd0','nc 192.168.1.100 65536 < /tmp/r206.bin','wget -O /tmp/r206.bin http://192.168.1.100:65536/payload-0123456789abcdef'):
            with self.assertRaises(UARTError):m.validate_linux_command(command)


@needs_artifacts()
class UARTClassificationTests(unittest.TestCase):
    def test_floating_line_signature(self):
        r=m.classify_uart_bytes(b'\x00\xff\x00\x80\xc0\xfe')
        self.assertTrue(r['likely_floating']);self.assertEqual(r['printable'],0)
    def test_trace_health_printk_interleave_is_repaired(self):
        text='PKTRACE ns=1 dir=tx ip[   2.0] zx-spifc HEALTH: reads=1\nlen=4 payloadlen=1\n'
        self.assertEqual(m.normalize_trace_text(text),'PKTRACE ns=1 dir=tx iplen=4 payloadlen=1\n')

    def test_clean_console_is_not_floating(self):
        r=m.classify_uart_bytes(b'Boot SPI NAND\r\nU-Boot 2013.04\r\n')
        self.assertFalse(r['likely_floating']);self.assertGreater(r['printable'],0)
    def test_empty_is_not_evidence(self):
        r=m.classify_uart_bytes(b'');self.assertFalse(r['likely_floating'])


@needs_artifacts()
class ModeGateTests(unittest.TestCase):
    FORCED='ro init=/bin/sh zx279128_eth.force_dp_init=1'
    DEFAULT='ro init=/bin/sh'
    def test_force_and_force0_cmdlines_are_not_interchangeable(self):
        m.require_cmdline(self.FORCED,expect_force=True)
        m.require_cmdline(self.DEFAULT,expect_force=False)
        with self.assertRaises(UARTError):m.require_cmdline(self.DEFAULT,expect_force=True)
        # This is the handoff requirement: a force0/default credit must never be
        # granted from a cmdline that still forces datapath init.
        with self.assertRaises(UARTError):m.require_cmdline(self.FORCED,expect_force=False)
        with self.assertRaises(UARTError):m.require_cmdline('ro init=/bin/bash',expect_force=False)
        with self.assertRaises(TypeError):m.require_cmdline(b'ro init=/bin/sh',expect_force=False)

    def test_expected_parameters_follow_the_selected_mode(self):
        forced=m.expected_parameters(True);default=m.expected_parameters(False)
        self.assertEqual(forced['force_dp_init'],'Y')
        self.assertEqual(default['force_dp_init'],'N')
        self.assertEqual(set(forced),set(default))
        self.assertEqual(default['init_mask'],'959')
        self.assertEqual(default['skip_dp_init'],'N')
        self.assertEqual(default['rx_q0_seed'],'-1')
        self.assertEqual(default['tx_slot_mode'],'0')

    def test_ascii_console_text_is_lossy_but_never_fatal(self):
        clean=b'-> start    = 0x40000000\r\nreloc off   = 0x00095000\r\n'
        self.assertEqual(m.ascii_console_text(clean),clean.decode('ascii'))
        noisy=m.ascii_console_text(b'-> start    = 0x4000\xb20000\r\n')
        self.assertIn('\ufffd',noisy)
        # The relocated field no longer matches its strict regex, so the
        # existing bdinfo gate still fails closed rather than guessing.
        self.assertNotRegex(noisy,r'^-> start\s*=\s*0x([0-9a-fA-F]+)\r?$')
        with self.assertRaises(TypeError):m.ascii_console_text('text')

    def test_datapath_branch_is_explicit_and_never_ambiguous(self):
        cold=b'... datapath init at probe (cold) ... TXORIGIN_R204 raw=0'
        warm=b'... datapath warm (rx ring 41a00000 tx ring 41c00000) - init skipped ...'
        self.assertEqual(m.datapath_branch(cold),'cold-full-init')
        self.assertEqual(m.datapath_branch(warm),'warm-attach')
        with self.assertRaises(UARTError):m.datapath_branch(b'neither marker')
        with self.assertRaises(UARTError):m.datapath_branch(cold+warm)
        with self.assertRaises(TypeError):m.datapath_branch('text')


@needs_artifacts()
class ProbeTests(unittest.TestCase):
    def test_r204_control_successes_revalidated(self):
        for name in ('mixed','wrap-1','reopen-mixed'):
            p=ROOT/'artifacts/r204'/name
            d=json.loads(p.with_suffix('.json').read_text())
            r=m.validate_probe(d,p.with_suffix('.pcap').read_bytes())
            self.assertEqual(r['exact_replies'],d['count'])
    def test_failed_identities_or_capture_not_accepted(self):
        p=ROOT/'artifacts/r204/mixed';blob=p.with_suffix('.pcap').read_bytes()
        for change in ('drop','reply','incomplete','extra'):
            d=json.loads(p.with_suffix('.json').read_text())
            if change=='drop':d['capture_socket_statistics']['kernel_drops']=1
            if change=='reply':d['measurement']['unique_exact_replies']=0
            if change=='incomplete':d['measurement_complete']=False
            if change=='extra':d['packet_index'][1]['classification']='returned_own_request'
            with self.assertRaises(UARTError):m.validate_probe(d,blob)
    def test_pcap_mutation_rejected(self):
        p=ROOT/'artifacts/r204/reopen-mixed';d=json.loads(p.with_suffix('.json').read_text());b=p.with_suffix('.pcap').read_bytes()
        for bad in (b[:-1],b'xxxx'+b[4:]):
            with self.assertRaises(UARTError):m.validate_probe(d,bad)


@needs_artifacts()
class TCPTests(unittest.TestCase):
    def fake_board(self,data,corrupt=None):
        self.download=None
        def board(command,timeout):
            if command=='ifconfig lo':return 'inet addr:127.0.0.1 UP'
            if command.startswith('wget '):
                with urllib.request.urlopen(command.split()[-1],timeout=2) as f:self.download=f.read()
                return ''
            if command.startswith('wc -c'):
                digest=hashlib.sha256(self.download).hexdigest() if corrupt!='hash' else '0'*64
                return f'{len(self.download)} /tmp/r206.bin\n{digest}  /tmp/r206.bin\n'
            if command.startswith('nc '):
                with socket.create_connection(('127.0.0.1',int(command.split()[2])),timeout=2) as s:
                    s.sendall(data if corrupt!='upload' else b'X'+data[1:])
                return ''
            raise AssertionError(command)
        return board
    def test_both_directions_with_injected_callback(self):
        data=bytes(range(256))*1024
        r=m.tcp_roundtrip(data,self.fake_board(data),host='127.0.0.1',peer='127.0.0.1')
        self.assertEqual(self.download,data);self.assertTrue(r['upload']['exact_bytes']);self.assertTrue(r['complete'])
    def test_corruption_and_missing_loopback_rejected(self):
        data=b'known-nonce'*1024
        for corrupt in ('hash','upload'):
            with self.assertRaises(UARTError):m.tcp_roundtrip(data,self.fake_board(data,corrupt),host='127.0.0.1',peer='127.0.0.1')
        with self.assertRaises(UARTError):m.tcp_roundtrip(data,lambda *a:'no address',host='127.0.0.1',peer='127.0.0.1')
    def test_failure_before_upload_connect_cleans_listener(self):
        data=b'known-nonce'*1024;inner=self.fake_board(data);port=[]
        def board(command,timeout):
            if command.startswith('nc '):port.append(int(command.split()[2]));raise UARTError('board command failed')
            return inner(command,timeout)
        with self.assertRaisesRegex(UARTError,'board command failed'):m.tcp_roundtrip(data,board,host='127.0.0.1',peer='127.0.0.1')
        with self.assertRaises(OSError):socket.create_connection(('127.0.0.1',port[0]),timeout=.2)

    def test_download_waits_for_sender_completion_publication(self):
        import socketserver
        import threading
        data=b'completion-race'*1024;inner=self.fake_board(data)
        blocked=threading.Event();release=threading.Event();timers=[]
        original=socketserver._SocketWriter.flush
        def delayed_flush(writer):
            blocked.set()
            if not release.wait(2):raise TimeoutError('test did not release sender')
            return original(writer)
        def board(command,timeout):
            result=inner(command,timeout)
            if command.startswith('wc -c'):
                self.assertTrue(blocked.wait(1))
                timer=threading.Timer(.05,release.set);timer.start();timers.append(timer)
            return result
        try:
            with patch.object(socketserver._SocketWriter,'flush',delayed_flush):
                result=m.tcp_roundtrip(data,board,host='127.0.0.1',peer='127.0.0.1')
            self.assertTrue(result['complete'])
        finally:
            release.set()
            for timer in timers:timer.join(1)

if __name__=='__main__':unittest.main()
