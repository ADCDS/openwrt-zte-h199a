#!/usr/bin/env python3
"""PARENT-ONLY bounded TCP integrity test over the existing H199A RAM shell.

Serve the specified existing payload to board tmpfs, verify its board SHA256,
then receive it back over another TCP connection. No flash/configuration writes.
Host services and UART commands run in one job to avoid agent/tool latency races.
The minimal shell must already have writable /tmp, device nodes, and loopback UP:
libubox/musl AI_ADDRCONFIG otherwise rejects even numeric IPv4 destinations.
"""
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from pathlib import Path
import re
import socket
import subprocess
import threading
import time

RIG = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--payload', type=Path, required=True)
    parser.add_argument('--output-prefix', type=Path, required=True)
    args = parser.parse_args()
    data = args.payload.read_bytes()
    if not 1 <= len(data) <= 4 * 1024 * 1024:
        parser.error('payload must be 1 byte..4 MiB')
    expected = hashlib.sha256(data).hexdigest()
    log = Path(str(args.output_prefix) + '.log')
    output = Path(str(args.output_prefix) + '.json')
    if log.exists() or output.exists():
        parser.error('output already exists')
    result = {'bytes': len(data), 'expected_sha256': expected, 'complete': False}
    with log.open('x') as transcript:
        def board(command, timeout):
            r = subprocess.run([str(RIG/'sh.sh'), command, str(timeout)],
                               capture_output=True, text=True, check=True)
            transcript.write(r.stdout)
            transcript.flush()
            return r.stdout
        loopback = board('ifconfig lo', 2)
        assert 'inet addr:127.0.0.1' in loopback and re.search(r'\bUP\b', loopback), 'loopback must be configured and UP before this test'
        http_result = {}
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_GET(self):
                if self.client_address[0] != '192.168.1.1' or self.path != '/payload':
                    self.send_error(403)
                    return
                try:
                    self.connection.settimeout(20)
                    self.send_response(200)
                    self.send_header('Content-Length', str(len(data)))
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    started = time.monotonic()
                    self.wfile.write(data)
                    self.wfile.flush()
                    http_result.update(sent=True, send_seconds=time.monotonic()-started)
                except Exception as error:
                    http_result['error'] = repr(error)
        with HTTPServer(('192.168.1.100', 0), Handler) as server:
            server.timeout = 35
            thread = threading.Thread(target=server.handle_request, daemon=True)
            thread.start()
            url = f'http://192.168.1.100:{server.server_port}/payload'
            result['download_url'] = url
            print('Serving', url, flush=True)
            board(f'wget -O /tmp/r202.bin {url}', 20)
            digest = board('wc -c /tmp/r202.bin; sha256sum /tmp/r202.bin', 3)
            thread.join(timeout=2)
            assert http_result.get('sent'), f'HTTP transfer not served: {http_result}'
            match = re.search(r'\b([0-9a-f]{64})\s+/tmp/r202\.bin', digest)
            assert match and match[1] == expected, 'board SHA256 mismatch or absent'
            assert re.search(r'\b' + str(len(data)) + r'\s+/tmp/r202\.bin', digest), 'board byte count mismatch'
            result.update(download_sha256=match[1], http=http_result)
        received = {}
        with socket.socket() as listener:
            listener.bind(('192.168.1.100', 0))
            listener.listen(1)
            listener.settimeout(25)
            port = listener.getsockname()[1]
            def accept_upload():
                try:
                    conn, peer = listener.accept()
                    with conn:
                        assert peer[0] == '192.168.1.1', 'unexpected peer'
                        conn.settimeout(20)
                        start = time.monotonic()
                        chunks = bytearray()
                        while len(chunks) < len(data):
                            part = conn.recv(min(65536, len(data)-len(chunks)))
                            if not part:
                                break
                            chunks.extend(part)
                        received.update(bytes=len(chunks), sha256=hashlib.sha256(chunks).hexdigest(),
                                        exact_bytes=(chunks == data), receive_seconds=time.monotonic()-start)
                except Exception as error:
                    received['error'] = repr(error)
            thread = threading.Thread(target=accept_upload, daemon=True)
            thread.start()
            # This board has BusyBox's minimal nc: no -w/-q options.
            # The host-side socket deadlines bound the transfer instead.
            board(f'nc 192.168.1.100 {port} < /tmp/r202.bin; echo upload_rc=$?', 20)
            thread.join(timeout=3)
            assert received.get('exact_bytes'), f'upload incomplete or corrupted: {received}'
            result.update(upload_port=port, upload=received, complete=True)
    with output.open('x') as target:
        json.dump(result, target, indent=2)
        target.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
