#!/usr/bin/env python3
"""Linux host-side exact ICMP measurement; no neighbour/sysctl mutations.

Example (requires CAP_NET_RAW; addresses are numeric, never resolved):
  sudo python3 tools/packet-probe-r200.py --iface enx00e04c125990 \
    --source 192.168.1.100 --target 192.168.1.1 \
    --target-mac 06:20:84:2f:87:b5 --count 30 --interval 0.5 --sizes 56 \
    --output-prefix artifacts/r200/arm-a

--sizes is a comma-separated cycle of ICMP DATA lengths, e.g. 56,512,1400.
--size-seed selects reproducible random choices instead; the exact plan is saved.
--identifier 0..65535 fixes the ICMP ID; each run still generates a fresh nonce.
Ordinary mode: at most 30 seconds scheduled send span and 5 seconds grace.
--pause-after K --pause-seconds S adds S to the normal interval before sequence K
and enables extended mode. --extended also allows longer grace without a pause.
Extended mode: at most 120 seconds total capture; pause/grace each at most 60.
Example: --count 16 --interval 0.5 --pause-after 8 --pause-seconds 20 --grace 30
sends at 0..3.5 and 24..27.5 seconds, then captures until 57.5 seconds.
Capture never stops during pause/drain; no extra probe packets are sent.
Capture has independent 100,000-frame/64-MiB budgets. No capture-only mode.

The transmit socket sends complete Ethernet frames. A DIFFERENT AF_PACKET
socket must observe each request with PACKET_OUTGOING. This proves a Linux
host-egress observation, NOT physical wire delivery. Direction and full receive
timestamps live in the JSON packet index; the nanosecond pcap stores Ethernet
frames as delivered by Linux (NIC offloads can change this view). There is no
inference about router internals. Importing this module never opens a socket.
"""

import argparse
from collections import Counter
from dataclasses import dataclass
import fcntl
import hashlib
import ipaddress
import json
import math
from pathlib import Path
import random
import re
import secrets
import select
import socket
import struct
import sys
import time

ETH_P_ALL = 0x0003
ETH_P_IP = 0x0800
PACKET_OUTGOING = 4
SOL_PACKET = 263
PACKET_STATISTICS = 6
SO_TIMESTAMPNS = getattr(socket, "SO_TIMESTAMPNS", 35)
SNAPLEN = 262144
MAX_FRAMES = 100000
MAX_CAPTURE_BYTES = 64 * 1024 * 1024
MAGIC = b"R200PING"
PAYLOAD_HEADER = 28  # magic(8), nonce(16), sequence(2), data length(2)


def checksum(data):
    """Internet checksum, including odd-length payloads."""
    if len(data) & 1:
        data += b"\0"
    total = sum(struct.unpack("!%dH" % (len(data) // 2), data))
    while total >> 16:
        total = (total & 0xffff) + (total >> 16)
    return (~total) & 0xffff


def numeric_ipv4(text):
    try:
        address = ipaddress.IPv4Address(text)
    except ipaddress.AddressValueError as exc:
        raise argparse.ArgumentTypeError("IPv4 must be numeric dotted decimal") from exc
    if (address.is_unspecified or address.is_multicast or address.is_loopback
            or address.is_reserved or int(address) == 0xffffffff):
        raise argparse.ArgumentTypeError("IPv4 must be a non-loopback unicast address")
    return str(address)


def unicast_mac(text):
    if not re.fullmatch(r"(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}", text):
        raise argparse.ArgumentTypeError("MAC must contain six colon-separated octets")
    value = bytes.fromhex(text.replace(":", ""))
    if value == bytes(6) or value[0] & 1:
        raise argparse.ArgumentTypeError("MAC must be nonzero and unicast")
    return value


def interface_name(text):
    if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,15}", text):
        raise argparse.ArgumentTypeError("iface must be 1..15 ASCII interface-name characters")
    return text


def data_sizes(text):
    try:
        parts = text.split(",")
        if not 1 <= len(parts) <= 64 or any(not p.isdecimal() for p in parts):
            raise ValueError
        values = tuple(int(p) for p in parts)
        if any(not PAYLOAD_HEADER <= size <= 1400 for size in values):
            raise ValueError
        return values
    except ValueError as exc:
        raise argparse.ArgumentTypeError("sizes: 1..64 comma-separated data lengths, each 28..1400") from exc


def plan_sizes(sizes, count, seed=None):
    if seed is None:
        return tuple(sizes[seq % len(sizes)] for seq in range(count))
    rng = random.Random(seed)  # independent of secrets: never seeds the nonce
    return tuple(rng.choice(sizes) for _ in range(count))


def plan_send_offsets(count, interval, pause_after=None, pause_seconds=0):
    return tuple(seq * interval + (pause_seconds if pause_after is not None and seq >= pause_after else 0)
                 for seq in range(count))


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--iface", required=True, type=interface_name)
    parser.add_argument("--source", required=True, type=numeric_ipv4)
    parser.add_argument("--target", required=True, type=numeric_ipv4)
    parser.add_argument("--target-mac", required=True, type=unicast_mac)
    parser.add_argument("--count", type=int, default=30)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--sizes", type=data_sizes, default=(56,))
    parser.add_argument("--size-seed", type=int, help="unsigned 64-bit seed for per-packet random size choice")
    parser.add_argument("--identifier", type=int, help="fixed ICMP ID, 0..65535 (nonce remains random)")
    parser.add_argument("--pause-after", type=int, help="pause after K requests, before zero-based sequence K")
    parser.add_argument("--pause-seconds", type=float, help="extra quiet interval, >0..60 seconds")
    parser.add_argument("--extended", action="store_true", help="opt into <=120s capture and <=60s grace")
    parser.add_argument("--grace", type=float, default=2.0)
    parser.add_argument("--output-prefix", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.source == args.target:
        parser.error("source and target must differ")
    if not 1 <= args.count <= 1000:
        parser.error("count must be 1..1000")
    if not math.isfinite(args.interval) or not 0.005 <= args.interval <= 30:
        parser.error("interval must be finite and 0.005..30 seconds")
    if args.identifier is not None and not 0 <= args.identifier <= 65535:
        parser.error("identifier must be 0..65535")
    if args.size_seed is not None and not 0 <= args.size_seed < 2**64:
        parser.error("size-seed must be an unsigned 64-bit integer")
    if (args.pause_after is None) != (args.pause_seconds is None):
        parser.error("pause-after and pause-seconds must be supplied together")
    if args.pause_after is not None:
        if not 1 <= args.pause_after < args.count:
            parser.error("pause-after must be 1..count-1")
        if not math.isfinite(args.pause_seconds) or not 0 < args.pause_seconds <= 60:
            parser.error("pause-seconds must be finite and >0..60")
        args.extended = True
    else:
        args.pause_seconds = 0.0
    max_grace = 60 if args.extended else 5
    if not math.isfinite(args.grace) or not 0.1 <= args.grace <= max_grace:
        parser.error("grace must be finite and 0.1..%d seconds" % max_grace)
    args.send_offsets = plan_send_offsets(args.count, args.interval, args.pause_after, args.pause_seconds)
    if not args.extended and args.send_offsets[-1] > 30:
        parser.error("scheduled send span (count - 1) * interval must not exceed 30 seconds")
    if args.extended and args.send_offsets[-1] + args.grace > 120:
        parser.error("extended send span + pause + grace must not exceed 120 seconds total")
    args.planned_sizes = plan_sizes(args.sizes, args.count, args.size_seed)
    if not args.output_prefix.name or not args.output_prefix.parent.is_dir():
        parser.error("output-prefix must name a file prefix in an existing directory")
    for suffix in (".pcap", ".json"):
        if Path(str(args.output_prefix) + suffix).exists():
            parser.error("output already exists: " + str(args.output_prefix) + suffix)
    return args


@dataclass(frozen=True)
class Arm:
    source: str
    target: str
    source_mac: bytes
    target_mac: bytes
    identifier: int
    nonce: bytes
    sizes: tuple
    count: int

    def payload(self, sequence):
        size = self.sizes[sequence % len(self.sizes)]
        header = MAGIC + self.nonce + struct.pack("!HH", sequence, size)
        return header + bytes((i + sequence) & 255 for i in range(size - len(header)))

    def frame(self, sequence):
        data = self.payload(sequence)
        icmp = struct.pack("!BBHHH", 8, 0, 0, self.identifier, sequence) + data
        icmp = icmp[:2] + struct.pack("!H", checksum(icmp)) + icmp[4:]
        ip = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(icmp),
                         sequence, 0x4000, 64, 1, 0,
                         ipaddress.IPv4Address(self.source).packed,
                         ipaddress.IPv4Address(self.target).packed)
        ip = ip[:10] + struct.pack("!H", checksum(ip)) + ip[12:]
        return self.target_mac + self.source_mac + struct.pack("!H", ETH_P_IP) + ip + icmp


class ParseError(ValueError):
    pass


@dataclass(frozen=True)
class Echo:
    source_mac: bytes
    target_mac: bytes
    source: str
    target: str
    kind: int
    code: int
    identifier: int
    sequence: int
    payload: bytes


def parse_echo(frame):
    """Parse full Ethernet/VLAN/IPv4, including IP options; never trust padding."""
    frame = bytes(frame)
    if len(frame) < 14:
        raise ParseError("truncated_frames")
    etype = struct.unpack_from("!H", frame, 12)[0]
    offset = 14
    tags = 0
    while etype in (0x8100, 0x88a8, 0x9100):
        tags += 1
        if tags > 2:
            raise ParseError("malformed_frames")
        if len(frame) < offset + 4:
            raise ParseError("truncated_frames")
        etype = struct.unpack_from("!H", frame, offset + 2)[0]
        offset += 4
    if etype != ETH_P_IP:
        raise ParseError("non_ipv4_frames")
    if len(frame) < offset + 20:
        raise ParseError("truncated_frames")
    ip = frame[offset:]
    ihl = (ip[0] & 15) * 4
    total = struct.unpack_from("!H", ip, 2)[0]
    if ip[0] >> 4 != 4 or ihl < 20 or total < ihl:
        raise ParseError("malformed_frames")
    if len(ip) < ihl or len(ip) < total:
        raise ParseError("truncated_frames")
    if checksum(ip[:ihl]):
        raise ParseError("bad_ip_checksum_frames")
    # Validate option lengths, including EOL and NOP, without assuming IHL=5.
    position = 20
    while position < ihl:
        option = ip[position]
        if option == 0:
            break
        if option == 1:
            position += 1
            continue
        if position + 1 >= ihl or ip[position + 1] < 2 or position + ip[position + 1] > ihl:
            raise ParseError("malformed_frames")
        position += ip[position + 1]
    flags_offset = struct.unpack_from("!H", ip, 6)[0]
    if flags_offset & 0x8000:
        raise ParseError("malformed_frames")
    if flags_offset & 0x3fff:
        raise ParseError("fragmented_frames")
    if ip[9] != 1:
        raise ParseError("non_icmp_frames")
    icmp = ip[ihl:total]
    if len(icmp) < 8:
        raise ParseError("truncated_frames")
    if checksum(icmp):
        raise ParseError("bad_icmp_checksum_frames")
    kind, code, _, identifier, sequence = struct.unpack_from("!BBHHH", icmp)
    if kind not in (0, 8):
        raise ParseError("foreign_icmp_frames")
    return Echo(frame[6:12], frame[:6], str(ipaddress.IPv4Address(ip[12:16])),
                str(ipaddress.IPv4Address(ip[16:20])), kind, code,
                identifier, sequence, icmp[8:])


class Measurement:
    def __init__(self, arm):
        self.arm = arm
        self.counters = Counter()
        self.attempted = {}
        self.outgoing = {}
        self.replies = {}
        self.returned = {}
        self.planned = {}

    def note_send(self, sequence, timestamp_ns, success, error=None, monotonic_ns=None):
        self.attempted[sequence] = {"syscall_timestamp_ns": timestamp_ns,
                                    "syscall_monotonic_ns": monotonic_ns,
                                    "data_length": len(self.arm.payload(sequence)),
                                    "success": success, "error": error}

    def observe(self, frame, pkttype, timestamp_ns, truncated=False):
        self.counters["captured_frames"] += 1
        try:
            if truncated:
                raise ParseError("truncated_frames")
            echo = parse_echo(frame)
        except ParseError as exc:
            label = str(exc)
            self.counters[label] += 1
            return label, None
        seq = echo.sequence
        arm = self.arm
        if echo.identifier != arm.identifier:
            label = "foreign_identifier_frames"
        elif not echo.payload.startswith(MAGIC + arm.nonce):
            label = "foreign_nonce_frames"
        elif seq >= arm.count:
            label = "wrong_sequence_frames"
        elif len(echo.payload) != len(arm.payload(seq)):
            label = "wrong_payload_size_frames"
        elif echo.payload != arm.payload(seq) or echo.code != 0:
            label = "wrong_payload_frames"
        elif seq not in self.attempted:
            label = "unsent_echo_frames"
        elif echo.kind == 8:
            if (echo.source, echo.target) != (arm.source, arm.target):
                label = "wrong_endpoint_frames"
            elif pkttype != PACKET_OUTGOING:
                # Returning an exact own request is NOT an echo reply. L2 may
                # have been rewritten by a forwarding device; retain raw frame.
                label = "returned_own_requests" if seq not in self.returned else "duplicate_returned_own_requests"
                self.returned.setdefault(seq, timestamp_ns)
            elif (echo.source_mac, echo.target_mac) != (arm.source_mac, arm.target_mac):
                label = "wrong_l2_frames"
            else:
                label = "observed_outgoing_requests" if seq not in self.outgoing else "duplicate_outgoing_requests"
                self.outgoing.setdefault(seq, timestamp_ns)
        elif pkttype == PACKET_OUTGOING:
            label = "unexpected_outgoing_frames"
        elif (echo.source, echo.target) != (arm.target, arm.source):
            label = "wrong_endpoint_frames"
        elif (echo.source_mac, echo.target_mac) != (arm.target_mac, arm.source_mac):
            label = "wrong_l2_frames"
        else:
            label = "unique_exact_replies" if seq not in self.replies else "duplicate_replies"
            self.replies.setdefault(seq, timestamp_ns)
        self.counters[label] += 1
        return label, seq

    def report(self):
        sent = {seq for seq, info in self.attempted.items() if info["success"]}
        outgoing, replies = set(self.outgoing), set(self.replies)
        missing = outgoing - replies
        per_sequence = []
        for seq in range(self.arm.count):
            tx, rx = self.outgoing.get(seq), self.replies.get(seq)
            per_sequence.append({"sequence": seq, "data_length": len(self.arm.payload(seq)),
                                 "planned": self.planned.get(seq),
                                 "send": self.attempted.get(seq), "observed_egress_ns": tx,
                                 "first_exact_reply_ns": rx,
                                 "first_returned_request_ns": self.returned.get(seq),
                                 "capture_rtt_ms": (rx - tx) / 1e6 if tx is not None and rx is not None and rx >= tx else None})
        return {"counters": dict(self.counters), "planned_requests": self.arm.count,
                "send_syscall_successes": len(sent),
                "unique_observed_host_egress": len(outgoing),
                "unique_exact_replies": len(replies),
                "missing_replies_among_observed_egress": sorted(missing),
                "observed_egress_without_reply_percent": 100 * len(missing) / len(outgoing) if outgoing else None,
                "successful_sends_not_observed": sorted(sent - outgoing),
                "replies_without_observed_egress": sorted(replies - outgoing),
                "unattempted_sequences": sorted(set(range(self.arm.count)) - self.attempted.keys()),
                "timestamp_order_anomalies": sorted(seq for seq in outgoing & replies if self.replies[seq] < self.outgoing[seq]),
                "per_sequence": per_sequence}


class PcapWriter:
    def __init__(self, stream):
        self.stream = stream
        # Nanosecond-resolution little-endian classic pcap, DLT_EN10MB.
        stream.write(struct.pack("<IHHIIII", 0xa1b23c4d, 2, 4, 0, 0, SNAPLEN, 1))

    def packet(self, frame, timestamp_ns):
        sec, ns = divmod(timestamp_ns, 1000000000)
        self.stream.write(struct.pack("<IIII", sec, ns, len(frame), len(frame)))
        self.stream.write(frame)


def receive_timestamp(ancillary, fallback_ns):
    for level, kind, data in ancillary:
        if level == socket.SOL_SOCKET and kind == SO_TIMESTAMPNS and len(data) >= struct.calcsize("@ll"):
            sec, ns = struct.unpack_from("@ll", data)
            if sec >= 0 and 0 <= ns < 1000000000:
                return sec * 1000000000 + ns, "kernel_software_realtime"
    return fallback_ns, "userspace_receive_realtime"


def bind_packet_socket(sock, iface):
    # AF_PACKET uses sockaddr_ll binding, not AF_INET's SO_BINDTODEVICE.
    # No route lookup or fallback to another interface is possible here.
    sock.bind((iface, 0))
    sock.setblocking(False)


def validate_interface(sock, args):
    """Read-only Linux ioctls; require the interface's primary IPv4 address."""
    request = struct.pack("256s", args.iface.encode("ascii"))
    address = fcntl.ioctl(sock.fileno(), 0x8915, request)  # SIOCGIFADDR
    mask = fcntl.ioctl(sock.fileno(), 0x891b, request)  # SIOCGIFNETMASK
    mtu_data = fcntl.ioctl(sock.fileno(), 0x8921, request)  # SIOCGIFMTU
    source = str(ipaddress.IPv4Address(address[20:24]))
    netmask = str(ipaddress.IPv4Address(mask[20:24]))
    network = ipaddress.IPv4Network(source + "/" + netmask, strict=False)
    if source != args.source:
        raise ValueError("source must equal interface primary IPv4 address " + source)
    for value in (args.source, args.target):
        if ipaddress.IPv4Address(value) in (network.network_address, network.broadcast_address):
            raise ValueError("source/target cannot be interface subnet network or broadcast address")
    mtu = struct.unpack_from("@i", mtu_data, 16)[0]
    if max(args.sizes) + 28 > mtu:
        raise ValueError("requested packet exceeds interface MTU %d" % mtu)
    return mtu


def run_measurement(args, pcap):
    """Only function that opens sockets. Tests must never call this unmocked."""
    capture = transmitter = None
    measurement = None
    packet_index = []
    failures = []
    timestamp_sources = Counter()
    packet_stats = None
    started = time.time_ns()
    elapsed_start = time.monotonic()
    report = {"schema": "packet-probe-r200-v2", "started_realtime_ns": started,
              "iface": args.iface, "source": args.source, "target": args.target,
              "target_mac": args.target_mac.hex(":"), "count": args.count,
              "interval_seconds": args.interval, "grace_seconds": args.grace,
              "identifier_provided": args.identifier is not None,
              "requested_identifier": args.identifier, "size_seed": args.size_seed,
              "size_selection": "cyclic" if args.size_seed is None else "seeded_choice",
              "planned_data_lengths": list(args.planned_sizes),
              "extended": args.extended, "pause_after": args.pause_after,
              "pause_seconds": args.pause_seconds,
              "pause_semantics": "extra interval before zero-based sequence pause_after",
              "scheduled_send_span_seconds": args.send_offsets[-1],
              "scheduled_capture_seconds": args.send_offsets[-1] + args.grace,
              "data_lengths": list(args.sizes),
              "max_scheduled_send_seconds": 120 - args.grace if args.extended else 30,
              "capture_limits": {"frames": MAX_FRAMES, "bytes": MAX_CAPTURE_BYTES},
              "notes": ["PACKET_OUTGOING is Linux host egress, not proof of physical wire delivery.",
                        "JSON packet_index preserves direction; pcap contains Linux-provided Ethernet frames.",
                        "Checksum/truncation counters cover all captured frames, including background traffic.",
                        "Packet timestamps use CLOCK_REALTIME; duration scheduling uses CLOCK_MONOTONIC.",
                        "Planned realtime timestamps are projections from the initial clock pair; scheduling is not realtime guaranteed.",
                        "Pause/drain suppress only this probe's sends, not unrelated host traffic.",
                        "No neighbour, route, interface configuration, or sysctl writes are performed."]}
    try:
        socket.if_nametoindex(args.iface)  # local interface validation, no DNS
        capture = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_ALL))
        bind_packet_socket(capture, args.iface)
        report["interface_mtu"] = validate_interface(capture, args)
        capture.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4 * 1024 * 1024)
        try:
            capture.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPNS, 1)
        except OSError as exc:
            report["kernel_timestamp_setup_error"] = str(exc)
        local_mac = capture.getsockname()[4]
        if len(local_mac) != 6 or local_mac == bytes(6) or local_mac[0] & 1:
            raise ValueError("interface does not provide a usable six-byte Ethernet MAC")
        if local_mac == args.target_mac:
            raise ValueError("target MAC equals local interface MAC")
        identifier = args.identifier if args.identifier is not None else secrets.randbelow(65536)
        arm = Arm(args.source, args.target, local_mac, args.target_mac,
                  identifier, secrets.token_bytes(16), args.planned_sizes, args.count)
        measurement = Measurement(arm)
        report.update({"source_mac": local_mac.hex(":"), "icmp_identifier": arm.identifier,
                       "nonce_hex": arm.nonce.hex(), "nonce_sha256": hashlib.sha256(arm.nonce).hexdigest(),
                       "sequence_start": 0})
        transmitter = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, socket.htons(ETH_P_IP))
        bind_packet_socket(transmitter, args.iface)
        first_send_ns = time.monotonic_ns()
        first_send = first_send_ns / 1e9
        first_send_realtime_ns = time.time_ns()
        for seq, offset in enumerate(args.send_offsets):
            measurement.planned[seq] = {"offset_seconds": offset,
                                        "monotonic_ns": first_send_ns + round(offset * 1e9),
                                        "realtime_ns": first_send_realtime_ns + round(offset * 1e9),
                                        "data_length": args.planned_sizes[seq]}
        deadline = first_send + args.send_offsets[-1] + args.grace
        next_sequence = 0
        captured_bytes = 0
        while time.monotonic() < deadline:
            now = time.monotonic()
            if next_sequence < args.count and now >= first_send + args.send_offsets[next_sequence]:
                frame = arm.frame(next_sequence)
                send_ns = time.time_ns()
                send_monotonic_ns = time.monotonic_ns()
                try:
                    written = transmitter.send(frame)
                    if written != len(frame):
                        raise OSError("short raw Ethernet send: %d/%d" % (written, len(frame)))
                    measurement.note_send(next_sequence, send_ns, True, monotonic_ns=send_monotonic_ns)
                except OSError as exc:
                    measurement.note_send(next_sequence, send_ns, False, str(exc), send_monotonic_ns)
                    failures.append("send sequence %d: %s" % (next_sequence, exc))
                next_sequence += 1
            next_due = first_send + args.send_offsets[next_sequence] if next_sequence < args.count else deadline
            ready, _, _ = select.select([capture], [], [], max(0, min(next_due, deadline) - time.monotonic()))
            if not ready:
                continue
            for _ in range(256):  # bounded drain: traffic cannot starve scheduling
                if time.monotonic() >= deadline:
                    break
                try:
                    frame, ancillary, flags, address = capture.recvmsg(SNAPLEN, socket.CMSG_SPACE(struct.calcsize("@ll")))
                except BlockingIOError:
                    break
                timestamp_ns, timestamp_source = receive_timestamp(ancillary, time.time_ns())
                timestamp_sources[timestamp_source] += 1
                pkttype = address[2]
                truncated = bool(flags & socket.MSG_TRUNC)
                if len(packet_index) >= MAX_FRAMES or captured_bytes + len(frame) > MAX_CAPTURE_BYTES:
                    raise RuntimeError("capture budget exceeded; measurement is incomplete")
                pcap.packet(frame, timestamp_ns)
                label, sequence = measurement.observe(frame, pkttype, timestamp_ns, truncated)
                packet_index.append({"index": len(packet_index), "timestamp_ns": timestamp_ns,
                                     "timestamp_source": timestamp_source, "pkttype": pkttype,
                                     "direction": "outgoing" if pkttype == PACKET_OUTGOING else "incoming",
                                     "length": len(frame), "msg_trunc": truncated,
                                     "classification": label, "sequence": sequence})
                captured_bytes += len(frame)
        report["scheduled_capture_elapsed_seconds"] = time.monotonic() - first_send
    except KeyboardInterrupt:
        failures.append("interrupted by user; measurement is incomplete")
    except (OSError, ValueError, RuntimeError) as exc:
        failures.append("%s: %s" % (type(exc).__name__, exc))
    finally:
        if capture is not None:
            try:
                raw_stats = capture.getsockopt(SOL_PACKET, PACKET_STATISTICS, 12)
                packets, drops = struct.unpack_from("=II", raw_stats)
                unread = bool(select.select([capture], [], [], 0)[0])
                packet_stats = {"kernel_packets": packets, "kernel_drops": drops,
                                "unread_at_stop": unread}
                if unread:
                    failures.append("capture queue unread at stop; measurement may be incomplete")
            except (OSError, struct.error) as exc:
                failures.append("capture drop statistics unavailable: " + str(exc))
            capture.close()
        if transmitter is not None:
            transmitter.close()
    report.update({"elapsed_seconds": time.monotonic() - elapsed_start,
                   "finished_realtime_ns": time.time_ns(), "failures": failures,
                   "capture_socket_statistics": packet_stats,
                   "timestamp_sources": dict(timestamp_sources), "packet_index": packet_index})
    if measurement is not None:
        result = measurement.report()
        report["measurement"] = result
        report["measurement_complete"] = bool(
            not failures and packet_stats is not None and packet_stats["kernel_drops"] == 0
            and not result["successful_sends_not_observed"] and not result["unattempted_sequences"]
            and not result["replies_without_observed_egress"]
            and not result["timestamp_order_anomalies"]
            and result["send_syscall_successes"] == args.count
            and not any(item["msg_trunc"] for item in packet_index))
    else:
        report["measurement_complete"] = False
    return report


def main(argv=None):
    args = parse_args(argv)  # all CLI/path validation precedes sockets
    prefix = str(args.output_prefix)
    try:
        # Exclusive creation: never overwrite a previous arm or capture.
        with open(prefix + ".pcap", "xb") as raw, open(prefix + ".json", "x", encoding="utf-8") as metadata:
            pcap = PcapWriter(raw)
            report = run_measurement(args, pcap)
            json.dump(report, metadata, indent=2, sort_keys=True)
            metadata.write("\n")
    except OSError as exc:
        print("packet-probe-r200: " + str(exc), file=sys.stderr)
        return 1
    print(json.dumps({"report": prefix + ".json", "pcap": prefix + ".pcap",
                      "measurement_complete": report["measurement_complete"],
                      "failures": report["failures"],
                      "measurement": {key: value for key, value in report.get("measurement", {}).items()
                                      if key not in ("per_sequence", "counters")}}, sort_keys=True))
    return 0 if report["measurement_complete"] else 1


if __name__ == "__main__":
    sys.exit(main())
