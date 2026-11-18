#!/usr/bin/env python3
"""Minimal read-only TFTP server with blksize/tsize negotiation."""
import argparse, socket, struct, threading, time
from pathlib import Path

RRQ, DATA, ACK, ERROR, OACK = 1, 3, 4, 5, 6

def zparts(data): return data.split(b'\0')

def serve_one(root, peer, request, log):
    parts=zparts(request[2:])
    try:
        name=parts[0].decode('ascii'); mode=parts[1].decode('ascii').lower()
        if mode!='octet' or '/' in name or name not in ('kernel','rootfs','header'): raise ValueError('denied')
        data=(root/name).read_bytes(); opts={}
        for i in range(2,len(parts)-1,2):
            if not parts[i]: break
            opts[parts[i].decode('ascii').lower()]=parts[i+1].decode('ascii')
        blocksize=max(8,min(1468,int(opts.get('blksize','512'))))
    except Exception as e:
        s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.sendto(struct.pack('!HH',ERROR,1)+str(e).encode()+b'\0',peer);s.close();return
    s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.bind(('',0));s.settimeout(2)
    def exchange(packet,want):
        for _ in range(8):
            s.sendto(packet,peer)
            try:
                r,p=s.recvfrom(2048)
                if p==peer and len(r)>=4 and struct.unpack('!HH',r[:4])==(ACK,want): return
            except socket.timeout: pass
        raise TimeoutError(f'ACK {want}')
    try:
        negotiated=[]
        if 'blksize' in opts: negotiated += [b'blksize',str(blocksize).encode()]
        if 'tsize' in opts: negotiated += [b'tsize',str(len(data)).encode()]
        if 'timeout' in opts: negotiated += [b'timeout',opts['timeout'].encode()]
        if negotiated: exchange(struct.pack('!H',OACK)+b'\0'.join(negotiated)+b'\0',0)
        block=1;off=0
        while True:
            chunk=data[off:off+blocksize]
            exchange(struct.pack('!HH',DATA,block)+chunk,block)
            off+=len(chunk)
            if len(chunk)<blocksize: break
            block=(block+1)&0xffff
        log(f'complete {name} bytes={len(data)} peer={peer[0]}:{peer[1]}')
    except Exception as e: log(f'failed {name} {e!r}')
    finally:s.close()

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--bind',default='0.0.0.0');ap.add_argument('--port',type=int,default=69);a=ap.parse_args()
    root=a.root.resolve()
    def log(x): print(time.strftime('%FT%T'),x,flush=True)
    sock=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);sock.bind((a.bind,a.port));log(f'listening {a.bind}:{a.port} root={root}')
    while True:
        req,peer=sock.recvfrom(2048)
        if len(req)>=2 and struct.unpack('!H',req[:2])[0]==RRQ: threading.Thread(target=serve_one,args=(root,peer,req,log),daemon=True).start()
        else:sock.sendto(struct.pack('!HH',ERROR,4)+b'read-only RRQ server\0',peer)
if __name__=='__main__':main()
