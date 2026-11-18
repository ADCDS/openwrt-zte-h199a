"""Pure gates + exclusive-FD Linux/TCP helpers for parent-only R206 validation.
No hardware/network access on import. The unchanged R205 lease rules still apply.
"""
from dataclasses import dataclass
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import re
import secrets
import socket
import struct
import threading
import time
import zlib
from h199a_uart_fd import Console, PROMPT, UARTError

R204_SHA='b2a7724bed20853ad04fb5e91ebacc6c86cac3b5573ace0e30bf6500590ad105'
SOURCE_SHA='477ba61a1f992edc9ae94cacecd51c8977ae51133946468dff5b7882cd4e0520'
PARAM='/sys/module/zx279128_eth/parameters/'
SHELL=re.compile(rb'(?:^|\r?\n)~ # ')
KERNEL_HEALTH = re.compile(r'\[\s*\d+\.\d+\] zx-spifc HEALTH: [^\r\n]*\r?\n')


def normalize_trace_text(text):
    """Remove only the known async health printk, preserving split trace bytes."""
    if not isinstance(text,str):
        raise TypeError('text required')
    return KERNEL_HEALTH.sub('',text)


def classify_uart_bytes(data):
    """Classify evidence without treating floating-line bytes as boot output."""
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError('bytes required')
    n=len(data)
    printable=sum(1 for b in data if b in (9,10,13) or 32 <= b < 127)
    return dict(bytes=n, nul=data.count(0), ff=data.count(0xff),
                printable=printable, nonprintable=n-printable,
                likely_floating=(n > 0 and printable == 0 and
                                 (data.count(0)+data.count(0xff))*2 >= n))


def ascii_console_text(data):
    """Lossy ASCII view of console bytes for regex field parsing.

    Byte noise in one line (a corrupted echo, an interleaved record) must not
    abort parsing of the fields that ARE intact. Every field gate still fails
    closed on missing/ambiguous values, so 'replace' cannot manufacture credit.
    """
    if not isinstance(data, (bytes, bytearray)):
        raise TypeError('bytes required')
    return bytes(data).decode('ascii', 'replace')


FORCE_CMDLINE_MARKER='zx279128_eth.force_dp_init=1'


def require_cmdline(cmdline, *, expect_force):
    """Enforce that the booted kernel command line matches the intended mode."""
    if not isinstance(cmdline,str):
        raise TypeError('text required')
    if 'ro init=/bin/sh' not in cmdline:
        raise UARTError('unexpected cmdline (readonly init=/bin/sh required)')
    if expect_force:
        if FORCE_CMDLINE_MARKER not in cmdline:
            raise UARTError('forced cmdline marker missing')
    elif 'force_dp_init' in cmdline:
        # Without this, a forced image whose payload happens to match could be
        # credited as the default/force0 path by a plain substring test.
        raise UARTError('cmdline still forces datapath init; not a force0 run')


def expected_parameters(expect_force):
    """Module parameters implied by the selected image mode."""
    return {'force_dp_init':'Y' if expect_force else 'N','skip_dp_init':'N','init_mask':'959',
            'tx_slot_mode':'0','rx_q0_seed':'-1','tx_w0':'128','tx_w1':'65536',
            'tx_w2':'16777216','tx_w3':'2','tx_dest':'0'}


def datapath_branch(output):
    """Which probe branch a boot log shows; exactly one must be present.

    A U-Boot-warm datapath is attached with init skipped and reports
    ``initialized=0`` (so the TX-origin gate already fails closed). Recording
    the branch explicitly stops a nonnetwork cold boot from being described as a
    warm-path trial.
    """
    if not isinstance(output,(bytes,bytearray)):
        raise TypeError('bytes required')
    output=bytes(output)
    warm=b'datapath warm' in output
    cold=b'datapath init at probe (cold)' in output
    if warm==cold:
        raise UARTError('ambiguous datapath init branch in boot log')
    return 'warm-attach' if warm else 'cold-full-init'


@dataclass(frozen=True)
class Image:
    data: bytes
    payload_bytes: int
    header_crc: int
    data_crc: int
    name: str


def parse_image(data, *, expected_name='h199a-r204-diag'):
    if not isinstance(data,bytes) or not 96<len(data)<=5*1024*1024:
        raise ValueError('image extent outside bounded RAM load')
    header=data[32:96]
    magic,hcrc,stamp,n,load,entry,dcrc,os_,arch,kind,compression,name=struct.unpack('>7I4B32s',header)
    if magic!=0x27051956 or (os_,arch,kind,compression)!=(5,2,2,0):
        raise ValueError('not uncompressed ARM Linux kernel uImage')
    if load!=0x40008000 or entry!=load or not 0<n<=len(data)-96:
        raise ValueError('invalid load/entry/payload range')
    if zlib.crc32(header[:4]+bytes(4)+header[8:])!=hcrc:
        raise ValueError('host header CRC mismatch')
    if zlib.crc32(data[96:96+n])!=dcrc:
        raise ValueError('host data CRC mismatch')
    if any(data[96+n:]):raise ValueError('nonzero trailing padding')
    decoded=name.rstrip(b'\0').decode('ascii','strict')
    if decoded!=expected_name:raise ValueError('wrong image label')
    return Image(data,n,hcrc,dcrc,decoded)


def require_r204(data):
    if hashlib.sha256(data).hexdigest()!=R204_SHA or len(data)!=3*1024*1024:
        raise ValueError('only frozen R2043MiB image is approved')
    return parse_image(data)


def verify_enabled(text):
    values=re.findall(rb'^verify=(.*)\r?$',text,re.M)
    missing=re.findall(rb'^## Error: "verify" not defined\r?$',text,re.M)
    if len(values)==1 and not missing:
        v=values[0].strip()
        if v[:1] in (b'1',b'T',b't',b'Y',b'y'):return 'enabled'
        raise UARTError('U-Boot verify is disabled; no environment change allowed')
    if len(missing)==1 and not values:return 'absent/enabled-by-own-H-code'
    raise UARTError('ambiguous/unrecognized verify response')


def validate_crc_output(text,image, *, address=0x42000020, load=0x40008000):
    if (address, load) not in ((0x42000020, 0x40008000), (0x43ffffc0, 0x44000000)):
        raise ValueError('checksum stage outside the two bounded payload windows')
    needed=[f'## Booting kernel from Legacy Image at {address:08x}'.encode(),
            b'Image Name:   '+image.name.encode(),
            b'Image Type:   ARM Linux Kernel Image (uncompressed)',
            f'Data Size:    {image.payload_bytes} Bytes'.encode(),
            f'Load Address: {load:08x}'.encode(),f'Entry Point:  {load:08x}'.encode()]
    if not all(x in text for x in needed):raise UARTError('CRC-stage image metadata mismatch')
    fields = (
        (rb'^## Booting kernel from Legacy Image at ([0-9a-fA-F]{8})', f'{address:08x}'.encode()),
        (rb'^[ \t]*Image Name:[ \t]*([^\r\n]*)', image.name.encode()),
        (rb'^[ \t]*Image Type:[ \t]*([^\r\n]*)', b'ARM Linux Kernel Image (uncompressed)'),
        (rb'^[ \t]*Data Size:[ \t]*(\d+) Bytes', str(image.payload_bytes).encode()),
        (rb'^[ \t]*Load Address:[ \t]*([0-9a-fA-F]{8})', f'{load:08x}'.encode()),
        (rb'^[ \t]*Entry Point:[ \t]*([0-9a-fA-F]{8})', f'{load:08x}'.encode()),
    )
    for pattern, expected in fields:
        if re.findall(pattern, text, re.M) != [expected]:
            raise UARTError('CRC-stage metadata missing or ambiguous')
    if len(re.findall(rb'Verifying Checksum\s*\.\.\.\s*OK',text))!=1:
        raise UARTError('explicit payload checksum success missing/ambiguous')
    if re.search(rb'(?i)bad|error|fail|Starting kernel|Booting Linux|Loading Kernel Image',text):
        raise UARTError('CRC-stage failure or unexpected loading/execution')


class ColdConsole(Console):
    def __init__(self,transport):
        super().__init__(transport)
        self.crc_image=None
        self.command_count=0
        self.command_log=[]

    def fixed_uboot(self,text):
        if text not in ('printenv verify','bootm start 0x42000020') or self.state!='console':
            raise UARTError('fixed preboot operation not allowed')
        try:
            if self.io.read(1,0):raise UARTError('unexpected preboot input')
            self.state='boot-entry'  # abort immediately on unexpected OS-start text
            self.write_all(text.encode()+b'\r')
            result=self.until(PROMPT,timeout=15)
            self.state='console'
            return result
        except BaseException:
            self.state='unknown';self.io.writes_allowed=False;raise

    def crc_gate(self,image, *, expected_name='h199a-r204-diag'):
        if self.state!='console' or self.crc_image is not None:
            raise UARTError('CRC gate requires fresh verified console')
        try:
            parsed=(require_r204(image.data) if expected_name=='h199a-r204-diag' else
                    parse_image(image.data,expected_name=expected_name))
            if parsed!=image:raise UARTError('image metadata does not match approved parse')
            header=self.memory(0x42000000,16)+self.memory(0x42000040,8)
            if header!=image.data[:96]:raise UARTError('target prefix/header differs from frozen image')
            enabled=verify_enabled(self.fixed_uboot('printenv verify'))
            output=self.fixed_uboot('bootm start 0x42000020')
            validate_crc_output(output,image)
            self.crc_image=image
            return dict(prefix_header_equal=True,verify=enabled,header_crc=f'{image.header_crc:08x}',
                        data_crc=f'{image.data_crc:08x}',payload_bytes=image.payload_bytes,
                        scope='prefix/header readback plus uImage header/data CRC, NOT full3MiB RAM SHA'),output
        except BaseException:
            self.state='unknown';self.io.writes_allowed=False;raise

    def boot(self, *, expect_force=True):
        if self.state!='console' or self.crc_image is None:
            raise UARTError('no verified image CRC gate')
        image=self.crc_image;self.crc_image=None
        try:
            if self.io.read(1,0):raise UARTError('unexpected input before boot')
            self.state='linux-boot'
            self.write_all(b'bootm 0x42000020\r')
            output=self.until(SHELL,timeout=55,limit=131072)
            required=[b'Verifying Checksum ... OK',b'Starting kernel',b'Linux version 6.6.151',
                      (b'ro init=/bin/sh zx279128_eth.force_dp_init=1' if expect_force else
                       b'ro init=/bin/sh'),
                      b'VFS: Mounted root (squashfs filesystem) readonly',b'Run /bin/sh as init process']
            if not all(x in output for x in required) or b'Kernel panic' in output:
                raise UARTError('unexpected boot/kernel/readonly shell evidence')
            origin=re.findall(rb'TXORIGIN_R204 raw=([0-9a-f]{8}) inherited=(\d+) selected=(\d+) initialized=(\d+) slot_mode=(\d+)',output)
            if len(origin)!=1 or origin[0][2:]!=(b'0',b'1',b'0'):
                raise UARTError('full-init TX origin0/mode0 not established')
            # Record which probe branch actually ran (see datapath_branch()).
            branch=datapath_branch(output)
            self.state='linux'
            return output,dict(zip(('raw','inherited','selected','initialized','slot_mode'),(x.decode() for x in origin[0])),
                               datapath_branch=branch)
        except BaseException:
            self.state='unknown';self.io.writes_allowed=False;raise

    def linux(self,command,timeout=10):
        if self.state!='linux':raise UARTError('verified readonly Linux required')
        validate_linux_command(command)
        self.command_count+=1
        nonce=secrets.token_hex(8)
        marker=('__H199A_R206_'+nonce).encode()
        # Split printf arguments: the command echo cannot contain the full
        # marker. Emit it three times: printk can legally interleave bytes in
        # one footer (as cold-g's eth2-open transcript demonstrated), while a
        # later copy normally remains contiguous. This does not re-run the
        # command or weaken the nonce/return-code check.
        footer="printf '\\n%s%s:%s\\n' '__H199A_R206_' '"+nonce+"' \"$__r\""
        wrapped=command+"; __r=$?; "+footer+"; "+footer+"; "+footer
        self.command_log.append(command)
        try:
            self.write_all(wrapped.encode()+b'\r')
            ending=re.compile(re.escape(marker)+rb':(\d+)\r?\n')
            output=self.until(ending,timeout=timeout,limit=131072)
            rc=ending.search(output)[1]
            # After the nonce footer, asynchronous kernel logs may prefix or
            # interleave the shell prompt. At this point the footer is already
            # verified, so an unanchored prompt token is safe and avoids
            # mistaking a CR/CRLF split or interleaved printk for a lost shell.
            self.until(b'~ # ',timeout=3,limit=16384)
            if rc!=b'0':raise UARTError('Linux command rc='+rc.decode()+': '+command)
            return output.decode('utf-8','replace')
        except BaseException:
            self.state='unknown';self.io.writes_allowed=False;raise


LINUX_FIXED={
    'mount -t proc proc /proc','mount -t sysfs sysfs /sys',
    'mount -t tmpfs tmpfs /tmp','mount -t tmpfs tmpfs /dev',
    'mknod /dev/null c 1 3','mknod /dev/urandom c 1 9','mknod /dev/console c 5 1',
    'ifconfig lo 127.0.0.1 up','ifconfig lo','ifconfig eth2',
    'ifconfig eth2 down','ifconfig eth2 192.168.1.1 netmask 255.255.255.0 up',
    'cat /proc/mounts','cat /proc/cmdline','cat /sys/class/net/eth2/carrier',
    'cat /proc/zx_eth_packets','wc -c /tmp/r206.bin; sha256sum /tmp/r206.bin','dmesg',
}


def validate_linux_command(command):
    if command in LINUX_FIXED:return
    if re.fullmatch(r'cat '+re.escape(PARAM)+r'(force_dp_init|skip_dp_init|init_mask|tx_slot_mode|rx_q0_seed|tx_w[0-3]|tx_dest)',command):return
    m=re.fullmatch(r'echo (-?\d+) > '+re.escape(PARAM)+r'(packet_trace_id|tx_dbg_max)',command)
    if m and ((m[2]=='packet_trace_id' and -1<=int(m[1])<=65535) or (m[2]=='tx_dbg_max' and m[1]=='0')):return
    if command=='echo Y > '+PARAM+'regs_path_only':return
    m=re.fullmatch(r'wget -O /tmp/r206.bin http://192\.168\.1\.100:([1-9][0-9]{0,4})/payload-[a-f0-9]{16}',command)
    if m and int(m[1])<=65535:return
    m=re.fullmatch(r'nc 192\.168\.1\.100 ([1-9][0-9]{0,4}) < /tmp/r206.bin',command)
    if m and int(m[1])<=65535:return
    raise UARTError('Linux command outside RAM-test allowlist')


def validate_probe(d,pcap):
    if not d['measurement_complete'] or d['failures']:raise UARTError('probe incomplete/failed')
    s=d['capture_socket_statistics'];m=d['measurement'];n=d['count']
    if s['kernel_drops'] or s['unread_at_stop'] or m['unique_exact_replies']!=n or m['unique_observed_host_egress']!=n:
        raise UARTError('probe identities/capture gate failed')
    formats={bytes.fromhex('4d3cb2a1'):('<',1),bytes.fromhex('d4c3b2a1'):('<',1000)}
    if pcap[:4] not in formats:raise UARTError('unexpected pcap encoding')
    endian,scale=formats[pcap[:4]]
    if len(pcap)<24 or struct.unpack_from(endian+'I',pcap,20)[0]!=1:raise UARTError('not Ethernet pcap')
    at=24;frames=[]
    while at<len(pcap):
        if at+16>len(pcap):raise UARTError('truncated pcap header')
        sec,ns,size,original=struct.unpack_from(endian+'4I',pcap,at);at+=16
        if size!=original or at+size>len(pcap):raise UARTError('truncated pcap frame')
        frames.append((sec*10**9+ns*scale,pcap[at:at+size]));at+=size
    if len(frames)!=len(d['packet_index']):raise UARTError('pcap/index mismatch')
    arp=0
    for i,(meta,(ts,f)) in enumerate(zip(d['packet_index'],frames)):
        if meta['index']!=i or meta['timestamp_ns']!=ts or meta['length']!=len(f) or meta['msg_trunc']:
            raise UARTError('frame metadata mismatch')
        if meta['direction']=='incoming' and meta['classification']!='unique_exact_replies':
            if (meta['classification']!='non_ipv4_frames' or len(f)<42 or
                f[6:12]!=bytes.fromhex('0620842f87b5') or f[12:20]!=bytes.fromhex('0806000108000604') or
                f[20:22] not in (b'\0\1',b'\0\2') or f[22:28]!=bytes.fromhex('0620842f87b5') or
                f[28:32]!=bytes([192,168,1,1]) or f[38:42]!=bytes([192,168,1,100])):
                raise UARTError('unexplained/noncurrent incoming frame')
            arp+=1
    return dict(exact_replies=n,capture_frames=len(frames),capture_drops=0,consistent_incoming_arp=arp)


def tcp_roundtrip(data,board,*,host='192.168.1.100',peer='192.168.1.1'):
    """Injected command callback is the sole UART owner; no sh.sh or device open."""
    if not isinstance(data,bytes) or not 1<=len(data)<=4*1024*1024:raise ValueError('TCP payload extent')
    expected=hashlib.sha256(data).hexdigest()
    loop=board('ifconfig lo',3)
    if 'inet addr:127.0.0.1' not in loop or not re.search(r'\bUP\b',loop):raise UARTError('loopback not ready')
    path='/payload-'+secrets.token_hex(8);sent={};sent_done=threading.Event()
    class Handler(BaseHTTPRequestHandler):
        timeout=20  # also bounds request-line/header reads, before do_GET
        def log_message(self,*args):pass
        def do_GET(self):
            if self.client_address[0]!=peer or self.path!=path or sent:
                self.send_error(403);return
            try:
                self.connection.settimeout(20)
                self.send_response(200);self.send_header('Content-Length',str(len(data)))
                self.send_header('Connection','close');self.end_headers()
                start=time.monotonic();self.wfile.write(data);self.wfile.flush()
                sent.update(complete=True,send_seconds=time.monotonic()-start)
            except Exception as error:sent['error']=repr(error)
            finally:sent_done.set()
    with HTTPServer((host,0),Handler) as server:
        worker=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=True)
        worker.start()
        try:
            board(f'wget -O /tmp/r206.bin http://{host}:{server.server_port}{path}',25)
            digest=board('wc -c /tmp/r206.bin; sha256sum /tmp/r206.bin',5)
            match=re.search(r'\b([0-9a-f]{64})\s+/tmp/r206\.bin',digest)
            if not sent_done.wait(2) or not sent.get('complete') or not match or match[1]!=expected or not re.search(r'\b'+str(len(data))+r'\s+/tmp/r206\.bin',digest):
                raise UARTError('TCP download/hash/length failed: '+str(sent))
        finally:
            server.shutdown();worker.join(2)
    received={};stop=threading.Event();active=[];guard=threading.Lock()
    with socket.socket() as listener:
        listener.bind((host,0));listener.listen(1);listener.settimeout(.2)
        port=listener.getsockname()[1]
        def accept_upload():
            try:
                end=time.monotonic()+25
                while not stop.is_set():
                    if time.monotonic()>=end:raise TimeoutError('upload accept deadline')
                    try:conn,address=listener.accept();break
                    except socket.timeout:continue
                else:return
                with conn:
                    with guard:
                        if stop.is_set():return
                        active.append(conn)
                    if address[0]!=peer:raise UARTError('unexpected upload peer')
                    conn.settimeout(20);start=time.monotonic();chunks=bytearray()
                    while len(chunks)<len(data):
                        part=conn.recv(min(65536,len(data)-len(chunks)))
                        if not part:break
                        chunks.extend(part)
                    received.update(bytes=len(chunks),sha256=hashlib.sha256(chunks).hexdigest(),
                                    exact_bytes=chunks==data,receive_seconds=time.monotonic()-start)
            except Exception as error:received['error']=repr(error)
        worker=threading.Thread(target=accept_upload,daemon=True);worker.start()
        try:board(f'nc {host} {port} < /tmp/r206.bin',25)
        finally:
            worker.join(.3);stop.set()
            with guard:
                for conn in active:
                    try:conn.shutdown(socket.SHUT_RDWR)
                    except OSError:pass
            worker.join(2)
        if worker.is_alive() or not received.get('exact_bytes'):
            raise UARTError('TCP upload incomplete/corrupt: '+str(received))
    return dict(complete=True,bytes=len(data),expected_sha256=expected,download_sha256=expected,
                http=sent,upload=received)
