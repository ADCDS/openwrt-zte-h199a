"""Offline tests: fake peers and private PTYs only, never the bench UART."""
import errno
import fcntl
import os
from pathlib import Path
import pty
import socket
import stat
import struct
import sys
import tempfile
import termios
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import h199a_uart_fd as u
from xmodem_h199a import TransferPlan, SenderOptions, SendResult
from bench_artifacts import needs_artifacts


@needs_artifacts()
class PrivatePTY(unittest.TestCase):
    def setUp(self):
        self.master, slave = pty.openpty()
        self.path = os.ttyname(slave)
        self.original = termios.tcgetattr(slave)
        os.close(slave)
        self.temp = tempfile.TemporaryDirectory()
        self.lock = Path(self.temp.name) / 'lock'
        self.lock.touch()
        self.lease = None

    def tearDown(self):
        if self.lease and self.lease.fd is not None:
            self.lease.release(powered_off=True)
        os.close(self.master)
        self.temp.cleanup()

    def audit(self, path):
        target = os.stat(path)
        holders = []
        for fd in os.listdir('/proc/self/fd'):
            try:
                s = os.fstat(int(fd))
                if stat.S_ISCHR(s.st_mode) and s.st_rdev == target.st_rdev:
                    holders.append([os.getpid(), int(fd)])
            except OSError:
                pass
        return dict(device=u.identity(target), holders=holders, errors=[], complete=True)

    def acquire(self, **kwargs):
        self.lease = u.Lease.acquire(self.path, self.lock, powered_off=True,
                                     audit=kwargs.get('audit', self.audit))
        return self.lease.transport

    def test_raw_configuration_and_powered_off_release(self):
        self.acquire()
        self.assertEqual(termios.tcgetattr(self.lease.fd), u.raw_attrs(self.original))
        self.assertEqual(termios.tcgetattr(self.lease.fd)[2] & termios.HUPCL,
                         self.original[2] & termios.HUPCL)
        with self.assertRaises(u.UARTError):self.lease.release(powered_off=False)
        self.lease.release(powered_off=True)
        fd = os.open(self.path, os.O_RDWR | os.O_NOCTTY)
        try:self.assertEqual(termios.tcgetattr(fd), self.original)
        finally:os.close(fd)

    def test_power_off_required_before_open(self):
        with self.assertRaises(u.UARTError):
            u.Lease.acquire(self.path, self.lock, powered_off=False, audit=self.audit)

    def test_existing_lock_is_never_replaced(self):
        ino = self.lock.stat().st_ino
        self.acquire()
        self.assertEqual(self.lock.stat().st_ino, ino)
        fd = os.open(self.lock, os.O_RDONLY)
        try:
            with self.assertRaises(BlockingIOError):fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        finally:os.close(fd)

    def test_busy_logger_lock_prevents_uart_open(self):
        fd = os.open(self.lock, os.O_RDONLY)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):self.acquire()
        finally:os.close(fd)

    def test_symlink_lock_rejected(self):
        real = self.lock.with_name('real');self.lock.rename(real);self.lock.symlink_to(real)
        with self.assertRaises(u.UARTError):self.acquire()

    def test_incomplete_audit_fails_before_open(self):
        def audit(path):
            r = self.audit(path);r.update(complete=False, errors=[['/proc/123/fd', 13]])
            return r
        with self.assertRaises(u.UARTError):self.acquire(audit=audit)

    def test_existing_descriptor_rejected(self):
        fd = os.open(self.path, os.O_RDONLY | os.O_NOCTTY)
        try:
            with self.assertRaises(u.UARTError):self.acquire()
        finally:os.close(fd)

    def test_second_audit_failure_releases_lease(self):
        calls = []
        def audit(path):
            r = self.audit(path);calls.append(1)
            if len(calls)==2:r['holders'].append([999999, 5])
            return r
        with self.assertRaises(u.UARTError):self.acquire(audit=audit)
        self.assertEqual(len(calls),2)
        self.acquire()  # lock and TIOCEXCL from failed acquisition were released

    def test_lock_swap_stops_io(self):
        io = self.acquire();self.lock.rename(self.lock.with_name('old'));self.lock.touch()
        with self.assertRaises(u.UARTError):io.write(b'x', .1)
        self.assertTrue(io.failed)

    def test_alias_swap_stops_io(self):
        alias = self.lock.with_name('uart');alias.symlink_to(self.path)
        self.path = str(alias);io = self.acquire();alias.unlink();alias.symlink_to('/dev/null')
        with self.assertRaises(u.UARTError):io.read(1,0)
        self.assertTrue(io.failed)

    def test_nonblocking_and_cloexec(self):
        self.acquire()
        self.assertTrue(fcntl.fcntl(self.lease.fd,fcntl.F_GETFL)&os.O_NONBLOCK)
        self.assertTrue(fcntl.fcntl(self.lease.fd,fcntl.F_GETFD)&fcntl.FD_CLOEXEC)

    @unittest.skipIf(os.geteuid()==0,'privileged openers can bypass TIOCEXCL')
    def test_tiocexcl_rejects_new_opener(self):
        self.acquire()
        with self.assertRaises(OSError) as error:os.open(self.path,os.O_RDWR|os.O_NOCTTY)
        self.assertEqual(error.exception.errno,errno.EBUSY)

    def test_raw_binary_read_and_write(self):
        io=self.acquire();b=bytes(range(256));os.write(self.master,b)
        got=bytearray()
        while len(got)<len(b):got.extend(io.read(256-len(got),.2))
        self.assertEqual(bytes(got),b)
        self.assertEqual(io.write(b,.2),len(b))
        self.assertEqual(os.read(self.master,512),b)

    def test_empty_zero_and_positive_timeouts(self):
        io=self.acquire();start=time.monotonic();self.assertEqual(io.read(1,0),b'')
        self.assertLess(time.monotonic()-start,.05)
        start=time.monotonic();self.assertEqual(io.read(1,.02),b'')
        self.assertGreaterEqual(time.monotonic()-start,.018)

    def test_eof_is_not_timeout(self):
        a,b=socket.socketpair();a.setblocking(False);fd=a.fileno();b.close()
        try:
            io=u.FDTransport(fd)
            with self.assertRaises(u.UARTError):io.read(1,.1)
            self.assertTrue(io.failed)
        finally:a.close()

    def test_partial_write_reports_only_known_prefix(self):
        io=self.acquire();real=os.write
        with patch.object(u.os,'write',side_effect=lambda fd,data:real(fd,data[:3])):
            self.assertEqual(io.write(b'abcdef',.1),3)
        self.assertEqual(os.read(self.master,64),b'abc')

    def test_eagain_write_deadline_does_not_spin_forever(self):
        io=self.acquire();start=time.monotonic()
        with patch.object(u.os,'write',side_effect=BlockingIOError(errno.EAGAIN,'busy')):
            with self.assertRaises(TimeoutError):io.write(b'x',.01)
        self.assertLess(time.monotonic()-start,.3)
        self.assertEqual(io.tx_accepted,0)

    def test_pending_binary_is_not_double_logged(self):
        io=self.acquire();os.write(self.master,b'bannerC')
        b=io.read(64,.1);self.assertEqual(b,b'bannerC');io.pushback(b[-1:])
        self.assertEqual(io.read(1,0),b'C');self.assertEqual(bytes(io.received),b)

    def test_real_fd_sender_and_complete_pilot_readback(self):
        io=self.acquire();plan=TransferPlan(bytes(range(256))*4)
        errors=[];received=[];os.set_blocking(self.master,False)
        real_write=os.write
        def peer():
            try:
                def take(n):
                    b=bytearray();end=time.monotonic()+3
                    while len(b)<n:
                        if time.monotonic()>=end:raise TimeoutError('private PTY peer')
                        try:b.extend(os.read(self.master,n-len(b)))
                        except BlockingIOError:time.sleep(.0002)
                    return bytes(b)
                def line():
                    b=bytearray()
                    while not b.endswith(b'\r'):b.extend(take(1))
                    return bytes(b)
                self.assertEqual(line(),b'xmodem 42000000\r')
                real_write(self.master,u.BANNER+b'C')
                packet=take(1029);self.assertEqual(packet,plan.packet(0));received.append(packet)
                real_write(self.master,b'\x06')
                self.assertEqual(take(1),b'\x04');real_write(self.master,b'\x06\r\n=> ')
                for offset in range(0,1024,64):
                    self.assertEqual(line(),f'md.l 0x{0x42000000+offset:08x} 0x10\r'.encode())
                    rows=[]
                    for row in range(offset,offset+64,16):
                        words=struct.unpack('<4I',plan.payload[row:row+16])
                        rows.append(f'{0x42000000+row:08x}: '+' '.join(f'{w:08x}' for w in words))
                    real_write(self.master,('\r\n'.join(rows)+'\r\n=> ').encode())
            except BaseException as error:errors.append(error)
        thread=threading.Thread(target=peer,daemon=True);thread.start()
        c=u.Console(io);c.state='console'
        with patch.object(u.os,'write',side_effect=lambda fd,b:real_write(fd,b[:37])):
            result=c.transfer(plan,options=SenderOptions(total_timeout=5))
            actual=b''.join(c.memory(0x42000000+o,16) for o in range(0,1024,64))
        thread.join(1);self.assertFalse(thread.is_alive());self.assertEqual(errors,[])
        self.assertEqual(actual,plan.payload);self.assertEqual(len(received),1)
        self.assertTrue(result.protocol_complete);self.assertFalse(result.ram_verified)
        self.assertEqual(c.state,'console')

    def test_invalid_io_and_rx_budget(self):
        io=self.acquire()
        for timeout in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):io.read(1,timeout)
        with self.assertRaises(ValueError):io.read(0,0)
        io.max_rx=1;os.write(self.master,b'12')
        with self.assertRaises(u.UARTError):io.read(2,.1)
        self.assertTrue(io.failed)


class Peer:
    def __init__(self, plan, *, eot_ack=True, prompt=True):
        self.plan=plan;self.pending=bytearray();self.writes=[];self.writes_allowed=True
        self.eot_ack=eot_ack;self.prompt=prompt
    def pushback(self,b):self.pending[:0]=b
    def read(self,n,timeout):
        if self.pending:
            b=bytes(self.pending[:n]);del self.pending[:n];return b
        if timeout:time.sleep(timeout)
        return b''
    def write(self,b,timeout):
        if not self.writes_allowed:raise u.UARTError('forbidden')
        self.writes.append(b)
        if b==b'xmodem 42000000\r':self.pending.extend(b'xmodem 42000000\r\n'+u.BANNER+b'C')
        elif b==self.plan.packet(0):self.pending.extend(b'\x06')
        elif b==b'\x04':
            if self.eot_ack:self.pending.extend(b'\x06')
            if self.prompt:self.pending.extend(b'\r\n=> ')
        else:raise AssertionError(f'unexpected write {b!r}')
        return len(b)


@needs_artifacts()
class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.plan=TransferPlan(bytes(range(256))*4)
        self.peer=Peer(self.plan);self.c=u.Console(self.peer);self.c.state='console'
        self.options=SenderOptions(response_timeout=.02,poll_interval=.005,total_timeout=1)

    def test_adjacent_banner_c_and_eot_prompt(self):
        r=self.c.transfer(self.plan,options=self.options)
        self.assertTrue(r.protocol_complete)
        self.assertFalse(r.ram_verified)
        self.assertEqual(self.c.state,'console')
        self.assertEqual(self.peer.writes,[b'xmodem 42000000\r',self.plan.packet(0),b'\x04'])

    def test_marker_every_chunk_boundary_preserves_c(self):
        for split in range(1,len(u.BANNER)):
            peer=Peer(self.plan);peer.pending.extend(u.BANNER+b'C')
            original=peer.read
            peer.read=lambda n,t,read=original,split=split:read(min(n,split),t)
            c=u.Console(peer)
            self.assertEqual(c.until(u.BANNER,.1),u.BANNER)
            self.assertEqual(peer.read(1,0),b'C')

    def test_unexpected_os_boot_blocks_more_tokens(self):
        self.c.state='boot-entry';self.peer.pending.extend(b'Starting kernel ...\r\n')
        with self.assertRaises(u.UARTError):self.c.until(b'input bootmode password',.01)
        self.assertEqual(self.c.state,'unknown');self.assertFalse(self.peer.writes_allowed)
        with self.assertRaises(u.UARTError):self.c.boot_token(b'1')
        self.assertFalse(self.peer.writes)

    def test_no_generic_c_scanning(self):
        self.peer.pending.extend(b'CPU noise C\nnot the banner C')
        with self.assertRaises(u.UARTError):self.c.until(u.BANNER,.01)
        self.assertFalse(self.peer.writes)

    def test_missing_eot_ack_forbids_every_further_write(self):
        self.peer.eot_ack=False;self.peer.prompt=False
        with self.assertRaises(Exception):self.c.transfer(self.plan,options=self.options)
        self.assertEqual(self.peer.writes[-1],b'\x04')
        self.assertEqual(self.c.state,'unknown');self.assertFalse(self.peer.writes_allowed)
        before=list(self.peer.writes)
        with self.assertRaises(u.UARTError):self.c.command('version')
        self.assertEqual(before,self.peer.writes)

    def test_acked_eot_without_prompt_does_not_restore(self):
        self.peer.prompt=False
        real=self.c.until;self.c.until=lambda marker,timeout=10,limit=65536:real(marker,min(timeout,.02),limit)
        with self.assertRaises(u.UARTError):self.c.transfer(self.plan,options=self.options)
        self.assertEqual(self.peer.writes[-1],b'\x04')
        self.assertFalse(self.peer.writes_allowed)

    def test_invalid_plan_rejected_before_command(self):
        with self.assertRaises(TypeError):self.c.transfer(None)
        self.assertFalse(self.peer.writes)

    def test_invalid_options_rejected_before_command(self):
        opts=SenderOptions();object.__setattr__(opts,'response_timeout',float('inf'))
        with self.assertRaises(ValueError):self.c.transfer(self.plan,options=opts)
        self.assertFalse(self.peer.writes)

    def test_stale_precommand_bytes_fail_closed(self):
        self.peer.pending.extend(b'C')
        with self.assertRaises(u.UARTError):self.c.transfer(self.plan)
        self.assertFalse(self.peer.writes_allowed);self.assertFalse(self.peer.writes)

    def test_dangerous_commands_and_mmio_never_sent(self):
        for command in ['saveenv','setenv verify yes','bootm 42000020','tftp 42000000 x','nand erase','md.l 0x92160000 0x1','md.l 0x47fffffc 0x2','md.l 0x42000000 0x11']:
            with self.assertRaises(u.UARTError):self.c.command(command)
        self.assertFalse(self.peer.writes)

    def test_bounded_memory_response_validation(self):
        def command(text):return b'md.l\r\n42000000: 01020304 05060708\r\n=> '
        self.c.command=command
        self.assertEqual(self.c.memory(0x42000000,2),bytes.fromhex('0403020108070605'))
        with self.assertRaises(u.UARTError):self.c.memory(0x42000000,3)
        self.c.command=lambda text:command(text)+b'\r\n42000000: 00000000\r\n'
        with self.assertRaises(u.UARTError):self.c.memory(0x42000000,2)

    def test_memory_survives_corrupted_echo_but_never_credits_response(self):
        # Measured on this bench (artifacts/r206/cold-default-c): binary bytes
        # replaced part of the 'md.l' ECHO while the response stayed byte-exact.
        # A strict-ASCII decode turned that recoverable noise into a fatal
        # UnicodeDecodeError; byte parsing must not.
        expected=bytes.fromhex('f04e2de941de4de20040a0e30ba08de2')
        noisy=(b'md.l 0x47fc25\xb2\x02\x82\xc2\xe1\r\n'
               b'47fc25b8: e92d4ef0 e24dde41 e3a04000 e28da00b\r\n=> ')
        self.c.command=lambda text:noisy
        self.assertEqual(self.c.memory(0x47fc25b8,4),expected)
        # A hex-shaped corruption inside the response parses but must NOT equal
        # the SHA-bound backup the caller compares against.
        self.c.command=lambda text:noisy.replace(b'e92d4ef0',b'e92d4ef1')
        self.assertNotEqual(self.c.memory(0x47fc25b8,4),expected)
        # A non-hex corruption of the address fails closed as incomplete.
        self.c.command=lambda text:noisy.replace(b'47fc25b8:',b'47fc25\xb2:')
        with self.assertRaises(u.UARTError):self.c.memory(0x47fc25b8,4)
        with self.assertRaises(TypeError):u.parse_memory_response('text',0x47fc25b8,4)
        with self.assertRaises(ValueError):u.parse_memory_response(noisy,0x47fc25b8,17)

    def test_uboot_command_log_records_echo_integrity(self):
        class Echo:
            def __init__(self,payload):self.payload=payload;self.pending=bytearray();self.writes=[]
            def read(self,n,t):
                if self.pending:
                    data=bytes(self.pending[:n]);del self.pending[:n];return data
                return b''
            def write(self,data,t):self.writes.append(data);self.pending.extend(self.payload);return len(data)
            def pushback(self,data):self.pending[:0]=data
        for payload,expected in ((b'version\r\nU-Boot 2013.04\r\n=> ',True),
                                 (b'vers\xb2ion\r\nU-Boot 2013.04\r\n=> ',False)):
            io=Echo(payload);c=u.Console(io);c.state='console'
            c.command('version')
            self.assertEqual(c.uboot_log[0]['command'],'version')
            self.assertEqual(c.uboot_log[0]['echo_intact'],expected)
            self.assertEqual(c.uboot_log[0]['bytes'],len(payload))

    def test_audit_unknown_permissions_or_holders_rejected(self):
        expected=dict(dev=1,inode=2,rdev=3,uid=0,mode=stat.S_IFCHR)
        r=dict(device=expected,holders=[],errors=[],complete=True)
        u.check_audit(r,expected,[])
        for delta in [dict(complete=False),dict(errors=[['x',13]]),dict(holders=[[1,2]]),dict(device={})]:
            with self.assertRaises(u.UARTError):u.check_audit(dict(r,**delta),expected,[])

if __name__=='__main__':unittest.main()
