#!/usr/bin/env python3
"""Correlate saved kernel identities with saved host bytes; never opens sockets.

Clock bounds assume a constant positive relative clock rate over the capture.
They use causal packet ordering, not manually synchronized wall clocks. If the
constraints are inconsistent or unbounded, no cross-clock latency is inferred.
"""
import argparse
from collections import defaultdict
from fractions import Fraction
import importlib.util
import ipaddress
import json
from pathlib import Path
import re
import struct
import sys


def fnv1a(payload):
    value = 2166136261
    for byte in payload:
        value = ((value ^ byte) * 16777619) & 0xffffffff
    return value


def parse_trace(text):
    header = None
    records = []
    ends = 0
    for line in text.splitlines():
        if line.startswith('PKTRACE_HEADER '):
            if header is not None:
                raise ValueError('duplicate trace header')
            header = dict(item.split('=', 1) for item in line.split()[1:])
        elif line.startswith('PKTRACE '):
            row = dict(item.split('=', 1) for item in line.split()[1:])
            for key in row:
                if key not in ('dir', 'head'):
                    row[key] = int(row[key], 0)
            if row['dir'] not in ('rx', 'tx') or len(bytes.fromhex(row['head'])) != 24:
                raise ValueError('invalid trace direction/head')
            records.append(row)
        elif line == 'PKTRACE_END':
            ends += 1
    if header is None or ends != 1 or int(header['records']) != len(records):
        raise ValueError('incomplete trace transcript')
    if int(header['enabled']) or int(header['dropped']):
        raise ValueError('trace must be frozen without overflow for complete correlation')
    if header['tx_stage'] != 'pre-doorbell' or header['rx_stage'] != 'pre-eth_type_trans':
        raise ValueError('unexpected timestamp boundaries')
    return header, records


def affine_bounds(lower, upper):
    """lower=(board_ns, host_request_ns), upper=(board_ns, host_reply_ns).

    Fit inequalities host_request <= a*board + c <= host_reply at their
    respective trace boundaries. Return a conservative enclosing rectangle
    for all feasible (a,c), without presupposing a ppm error limit.
    Coordinates should be centered to reduce bound width.
    """
    if not lower or not upper:
        return {'feasible': False, 'reason': 'missing matched RX requests or TX replies'}
    amin, amax = Fraction(0), None
    for bx, hx in lower:
        for by, hy in upper:
            dx, dy = bx - by, hx - hy
            if dx > 0:
                amin = max(amin, Fraction(dy, dx))
            elif dx < 0:
                bound = Fraction(dy, dx)
                amax = bound if amax is None else min(amax, bound)
            elif dy > 0:
                return {'feasible': False, 'reason': 'inconsistent equal-time constraints'}
    if amax is None or amax <= 0 or amin > amax:
        return {'feasible': False, 'reason': 'inconsistent or unbounded affine rate'}
    if any(b < 0 for b, _ in lower + upper):
        raise ValueError('center board timestamps at or before first trace record')
    cmin = max(Fraction(h) - amax * b for b, h in lower)
    cmax = min(Fraction(h) - amin * b for b, h in upper)
    return {'feasible': True, 'rate_min': amin, 'rate_max': amax,
            'offset_min_ns': cmin, 'offset_max_ns': cmax}


def key(row):
    return tuple(row[k] for k in ('type', 'id', 'seq', 'src', 'dst', 'ipid', 'payloadlen', 'hash', 'head'))


def read_wire(prefix):
    spec = importlib.util.spec_from_file_location('packet_probe_r201_correlation', Path(__file__).with_name('packet-probe-r200.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    metadata = json.loads(Path(str(prefix) + '.json').read_text())
    if not metadata['measurement_complete']:
        raise ValueError('host capture measurement is incomplete')
    count = int(metadata['measurement']['planned_requests'])
    nonce = bytes.fromhex(metadata['nonce_hex'])
    sizes = tuple(metadata['planned_data_lengths'] if 'planned_data_lengths' in metadata else metadata['data_lengths'])
    if not 1 <= count <= 1000 or len(nonce) != 16 or not sizes:
        raise ValueError('invalid probe count, nonce or size plan')
    if ('planned_data_lengths' in metadata and len(sizes) != count) or any(
            not isinstance(size, int) or not module.PAYLOAD_HEADER <= size <= 1400 for size in sizes):
        raise ValueError('invalid probe size plan')
    source_mac = bytes.fromhex(metadata['source_mac'].replace(':', ''))
    target_mac = bytes.fromhex(metadata['target_mac'].replace(':', ''))
    if any(len(mac) != 6 or mac == bytes(6) or mac[0] & 1 for mac in (source_mac, target_mac)):
        raise ValueError('invalid probe Ethernet addresses')
    arm = module.Arm(str(ipaddress.IPv4Address(metadata['source'])),
                     str(ipaddress.IPv4Address(metadata['target'])), source_mac, target_mac,
                     metadata['icmp_identifier'], nonce, sizes, count)
    raw = Path(str(prefix) + '.pcap').read_bytes()
    if len(raw) < 24:
        raise ValueError('truncated pcap header')
    if raw[:4] == bytes.fromhex('4d3cb2a1'):
        endian, multiplier = '<', 1
    elif raw[:4] == bytes.fromhex('d4c3b2a1'):
        endian, multiplier = '<', 1000
    else:
        raise ValueError('expected little-endian Ethernet pcap')
    if struct.unpack_from(endian + 'I', raw, 20)[0] != 1:
        raise ValueError('pcap is not Ethernet')
    offset, index, rows = 24, 0, []
    while offset < len(raw):
        if offset + 16 > len(raw) or index >= len(metadata['packet_index']):
            raise ValueError('truncated pcap record or missing packet index')
        sec, subsec, size, original = struct.unpack_from(endian + 'IIII', raw, offset)
        offset += 16
        frame = raw[offset:offset+size]
        offset += size
        item = metadata['packet_index'][index]
        ns = sec * 1000000000 + subsec * multiplier
        if (size != original or len(frame) != size or item['timestamp_ns'] != ns
                or item['length'] != size or item['index'] != index or item.get('msg_trunc', False)
                or not 0 <= subsec * multiplier < 1000000000):
            raise ValueError('pcap/index mismatch')
        index += 1
        try:
            echo = module.parse_echo(frame)
        except module.ParseError:
            continue
        if echo.identifier != arm.identifier or not echo.payload.startswith(module.MAGIC + arm.nonce):
            continue
        # ID/nonce alone do not establish an exact probe. Do not trust the
        # saved classification string: independently check the whole plan.
        if echo.code != 0 or not 0 <= echo.sequence < arm.count or echo.payload != arm.payload(echo.sequence):
            continue
        outgoing = item['pkttype'] == module.PACKET_OUTGOING
        expected_ips = (arm.source, arm.target) if outgoing else (arm.target, arm.source)
        expected_macs = (arm.source_mac, arm.target_mac) if outgoing else (arm.target_mac, arm.source_mac)
        if (echo.kind != (8 if outgoing else 0) or (echo.source, echo.target) != expected_ips
                or (echo.source_mac, echo.target_mac) != expected_macs):
            continue
        # A userspace receive timestamp for an outgoing packet can be AFTER
        # board RX. It cannot support the causal host-egress <= board-RX bound.
        if item.get('timestamp_source') != 'kernel_software_realtime':
            raise ValueError('clock anchors require kernel_software_realtime timestamps')
        ipo = 14
        etype = struct.unpack_from('!H', frame, 12)[0]
        while etype in (0x8100, 0x88a8, 0x9100):
            etype = struct.unpack_from('!H', frame, ipo + 2)[0]
            ipo += 4
        rows.append({'ns': ns, 'index': index-1, 'pkttype': item['pkttype'],
                     'type': echo.kind, 'id': echo.identifier, 'seq': echo.sequence,
                     'src': int(ipaddress.IPv4Address(echo.source)),
                     'dst': int(ipaddress.IPv4Address(echo.target)),
                     'ipid': struct.unpack_from('!H', frame, ipo+4)[0],
                     'payloadlen': len(echo.payload), 'hash': fnv1a(echo.payload),
                     'head': echo.payload[:24].ljust(24, b'\0').hex()})
    if index != len(metadata['packet_index']):
        raise ValueError('pcap record count mismatch')
    return metadata, rows


def correlate(metadata, wire, header, records):
    if int(header['armed_id']) != metadata['icmp_identifier']:
        raise ValueError('kernel/host ICMP filters differ')
    expected_head = (b'R200PING' + bytes.fromhex(metadata['nonce_hex'])).hex()
    relevant = sorted((r for r in records if r['id'] == metadata['icmp_identifier'] and r['head'] == expected_head), key=lambda r: r['ns'])
    outgoing = defaultdict(list)
    incoming = defaultdict(list)
    tx = defaultdict(list)
    for row in wire:
        (outgoing if row['pkttype'] == 4 else incoming)[key(row)].append(row)
    for row in relevant:
        if row['dir'] == 'tx':
            tx[key(row)].append(row)
    requests = []
    responses = []
    for row in relevant:
        matches = outgoing.get(key(row), [])
        if row['dir'] == 'rx' and row['type'] == 8 and len(matches) == 1:
            requests.append((row, matches[0]))
    for k, hosts in incoming.items():
        if k[0] == 0 and len(tx[k]) == 1:
            for host in hosts:
                responses.append((tx[k][0], host))
    board_zero = min((r['ns'] for r in relevant), default=0)
    host_zero = min((r['ns'] for r in wire if r['pkttype'] == 4), default=0)
    model = affine_bounds([(b['ns']-board_zero, h['ns']-host_zero) for b,h in requests],
                          [(b['ns']-board_zero, h['ns']-host_zero) for b,h in responses])
    details = []
    rx_by_seq = defaultdict(list)
    for row, _ in requests:
        rx_by_seq[row['seq']].append(row)
    for row in relevant:
        result = dict(row)
        result['board_relative_ms'] = (row['ns'] - board_zero) / 1e6
        if row['dir'] == 'tx' and row['type'] == 0:
            preceding = [r for r in rx_by_seq[row['seq']] if r['ns'] <= row['ns']
                         and r['hash'] == row['hash'] and r['payloadlen'] == row['payloadlen']
                         and r['src'] == row['dst'] and r['dst'] == row['src']]
            result['preceding_matching_rx_count'] = len(preceding)
            result['nearest_preceding_rx_gap_ms'] = (row['ns'] - max(r['ns'] for r in preceding)) / 1e6 if preceding else None
        details.append(result)
    timings = []
    for direction, pairs in [('host-egress_to_driver-rx', requests), ('driver-tx_to_host-ingress', responses)]:
        for board, host in pairs:
            entry = {'boundary': direction, 'sequence': board['seq'], 'ipv4_id': board['ipid'],
                     'board_ns': board['ns'], 'host_ns': host['ns'], 'pcap_index': host['index']}
            if model['feasible']:
                b, h = board['ns']-board_zero, host['ns']-host_zero
                early = model['rate_min'] * b + model['offset_min_ns']
                late = model['rate_max'] * b + model['offset_max_ns']
                low, high = (early-h, late-h) if direction.startswith('host-') else (h-late, h-early)
                entry['conditional_delay_min_ms'] = float(max(0, low) / 1000000)
                entry['conditional_delay_max_ms'] = float(max(0, high) / 1000000)
            timings.append(entry)
    return {'assumptions': ['Constant positive relative clock rate over the capture; no arbitrary clock jump.',
                             'Unique packet identity/fingerprint matches and causal host-egress/RX, TX/host-ingress ordering.',
                             'Host anchors have kernel software timestamps, exact planned payloads, and verified IP/Ethernet endpoints and direction.',
                             'TX timestamp is BEFORE doorbell; RX is copied skb BEFORE eth_type_trans.',
                             'Fingerprint is not a full kernel payload capture; host pcap validates complete bytes.',
                             'Nearest preceding RX is a temporal association, not proof of causation.',
                             'Outgoing host capture is not proof of physical wire transmission.'],
            'trace_header': header, 'host_measurement_complete': metadata['measurement_complete'],
            'trace_records': len(records), 'current_nonce_records': len(relevant),
            'matched_rx_request_records': len(requests), 'matched_host_reply_records': len(responses),
            'board_zero_ns': board_zero, 'host_zero_ns': host_zero,
            'clock_model': {k: float(v) if isinstance(v, Fraction) else v for k,v in model.items()},
            'events': details, 'boundary_timings': timings}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-prefix', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    header, records = parse_trace(args.trace.read_text())
    metadata, wire = read_wire(args.capture_prefix)
    result = correlate(metadata, wire, header, records)
    with args.output.open('x') as output:
        json.dump(result, output, indent=2)
        output.write('\n')
    print(json.dumps({k:v for k,v in result.items() if k not in ('events','boundary_timings','assumptions')}, indent=2))


if __name__ == '__main__':
    main()
