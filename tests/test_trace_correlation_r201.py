"""Offline tests for trace parsing, causal clock bounds, and identity matching."""
import importlib.util
from fractions import Fraction
import io
import json
from pathlib import Path
import socket
import struct
import sys
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('correlation_r201', Path(__file__).resolve().parents[1] / 'tools/correlate-packet-trace-r201.py')
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)
PROBE_SPEC = importlib.util.spec_from_file_location('probe_for_correlation_tests', Path(__file__).resolve().parents[1] / 'tools/packet-probe-r200.py')
P = importlib.util.module_from_spec(PROBE_SPEC)
sys.modules[PROBE_SPEC.name] = P
PROBE_SPEC.loader.exec_module(P)


def checksummed(frame):
    frame = bytearray(frame)
    struct.pack_into('!H', frame, 16, len(frame) - 14)
    frame[24:26] = b'\0\0'
    frame[24:26] = struct.pack('!H', P.checksum(bytes(frame[14:34])))
    frame[36:38] = b'\0\0'
    frame[36:38] = struct.pack('!H', P.checksum(bytes(frame[34:])))
    return bytes(frame)


def reply(frame):
    result = bytearray(frame)
    result[:6], result[6:12] = frame[6:12], frame[:6]
    result[26:30], result[30:34] = frame[30:34], frame[26:30]
    result[34] = 0
    return checksummed(result)


class CorrelationTests(unittest.TestCase):
    def setUp(self):
        guard = mock.patch.object(socket, 'socket', side_effect=AssertionError('REAL SOCKET FORBIDDEN'))
        guard.start()
        self.addCleanup(guard.stop)
        self.arm = P.Arm('192.168.1.100', '192.168.1.1', bytes.fromhex('00e04c125990'),
                         bytes.fromhex('0620842f87b5'), 20101, bytes(range(16)), (56, 57, 512), 3)

    def read_fixture(self, packets, timestamp_source='kernel_software_realtime', planned=None,
                     metadata_change=None, pcap_change=None):
        metadata = {'measurement_complete': True, 'measurement': {'planned_requests': self.arm.count},
                    'icmp_identifier': self.arm.identifier, 'nonce_hex': self.arm.nonce.hex(),
                    'source': self.arm.source, 'target': self.arm.target,
                    'source_mac': self.arm.source_mac.hex(':'), 'target_mac': self.arm.target_mac.hex(':'),
                    'data_lengths': list(self.arm.sizes), 'packet_index': []}
        if planned is not None:
            metadata['planned_data_lengths'] = planned
        stream = io.BytesIO()
        writer = P.PcapWriter(stream)
        for index, (frame, direction) in enumerate(packets):
            ns = 1000000000 + index * 1000
            writer.packet(frame, ns)
            metadata['packet_index'].append({'index': index, 'timestamp_ns': ns, 'length': len(frame),
                                             'pkttype': direction, 'timestamp_source': timestamp_source,
                                             'classification': 'unique_exact_replies'})  # deliberately not trusted
        if metadata_change:
            metadata_change(metadata)
        raw = stream.getvalue()
        if pcap_change:
            raw = pcap_change(raw)
        with tempfile.TemporaryDirectory() as directory:
            prefix = Path(directory) / 'capture'
            prefix.with_suffix('.json').write_text(json.dumps(metadata))
            prefix.with_suffix('.pcap').write_bytes(raw)
            return M.read_wire(prefix)

    def test_fnv_known_vectors(self):
        self.assertEqual(M.fnv1a(b''), 0x811c9dc5)
        self.assertEqual(M.fnv1a(b'hello'), 0x4f9f2cab)

    def test_disabled_complete_trace_only(self):
        line = ('PKTRACE_HEADER generation=1 enabled=0 filter_id=-1 armed_id=45569 records=1 dropped=0 '
                'tx_stage=pre-doorbell rx_stage=pre-eth_type_trans\n'
                'PKTRACE ns=200 dir=rx port=2 ring=0 slot=1 buf=0 pool=0 frame=98 iplen=84 payloadlen=56 '
                'ipid=0x0000 src=0xc0a80164 dst=0xc0a80101 type=8 id=0xb201 seq=0 hash=0x12345678 head=' + '00' * 24 + '\nPKTRACE_END\n')
        h, rows = M.parse_trace(line)
        self.assertEqual(rows[0]['id'], 45569)
        self.assertEqual(rows[0]['src'], 0xc0a80164)
        for old, new in [('enabled=0', 'enabled=1'), ('records=1', 'records=2'), ('dropped=0', 'dropped=1'), ('PKTRACE_END\n', '')]:
            with self.assertRaises(ValueError):
                M.parse_trace(line.replace(old, new))

    def test_clock_drift_and_large_delay_bounds(self):
        rate = Fraction(99999, 100000)
        origin = Fraction(1234567)
        points = [(1000000000, 100000, 200000), (4000000000, 2000000000, 100000), (30000000000, 150000, 180000)]
        lower, upper = [], []
        for b, rx_delay, tx_delay in points:
            lower.append((b, rate * b + origin - rx_delay))
            upper.append((b+100000, rate * (b+100000) + origin + tx_delay))
        fit = M.affine_bounds(lower, upper)
        self.assertTrue(fit['feasible'])
        self.assertLessEqual(fit['rate_min'], rate)
        self.assertGreaterEqual(fit['rate_max'], rate)
        self.assertLessEqual(fit['offset_min_ns'], origin)
        self.assertGreaterEqual(fit['offset_max_ns'], origin)
        b, h = lower[1]
        lo = fit['rate_min']*b + fit['offset_min_ns'] - h
        hi = fit['rate_max']*b + fit['offset_max_ns'] - h
        self.assertLessEqual(lo, 2000000000)
        self.assertGreaterEqual(hi, 2000000000)
        self.assertGreater(lo, 1990000000)

    def test_inconsistent_clocks_not_forced(self):
        self.assertFalse(M.affine_bounds([(0, 100)], [(0, 99)])['feasible'])
        self.assertFalse(M.affine_bounds([], [(0, 1)])['feasible'])

    def test_distinct_ipids_match_distinct_tx_records(self):
        nonce = '01' * 16
        head = (b'R200PING' + bytes.fromhex(nonce)).hex()
        base = dict(port=2, ring=0, slot=0, buf=0, pool=0, frame=98, iplen=84,
                    payloadlen=56, id=45569, seq=0, hash=1234, head=head)
        rx = dict(base, ns=1000000, dir='rx', type=8, ipid=0, src=0xc0a80164, dst=0xc0a80101)
        tx1 = dict(base, ns=1100000, dir='tx', type=0, ipid=100, src=0xc0a80101, dst=0xc0a80164)
        tx2 = dict(tx1, ns=2100000, ipid=101)
        wire = [dict(rx, ns=1000000000, pkttype=4, index=0),
                dict(tx2, ns=1002200000, pkttype=0, index=1)]
        meta = {'icmp_identifier': 45569, 'nonce_hex': nonce, 'measurement_complete': True}
        header = {'armed_id': '45569'}
        result = M.correlate(meta, wire, header, [rx, tx1, tx2])
        self.assertEqual(result['matched_rx_request_records'], 1)
        self.assertEqual(result['matched_host_reply_records'], 1)
        response = [e for e in result['boundary_timings'] if e['boundary'].startswith('driver-')][0]
        self.assertEqual(response['ipv4_id'], 101)
        self.assertEqual(response['board_ns'], tx2['ns'])
        self.assertEqual(result['events'][2]['nearest_preceding_rx_gap_ms'], 1.1)

    def test_read_wire_accepts_only_valid_directed_request_reply(self):
        frame = self.arm.frame(1)
        _, rows = self.read_fixture([(frame, 4), (reply(frame), 0)])
        self.assertEqual([(r['type'], r['seq'], r['payloadlen']) for r in rows], [(8, 1, 57), (0, 1, 57)])
        self.assertEqual(rows[0]['hash'], M.fnv1a(self.arm.payload(1)))

    def test_read_wire_rejects_userspace_or_missing_anchor_timestamps(self):
        for direction, frame in ((4, self.arm.frame(0)), (0, reply(self.arm.frame(0)))):
            for source in ('userspace_receive_realtime', None):
                with self.subTest(direction=direction, source=source), self.assertRaisesRegex(ValueError, 'kernel_software_realtime'):
                    self.read_fixture([(frame, direction)], timestamp_source=source)
        with self.assertRaisesRegex(ValueError, 'kernel_software_realtime'):
            self.read_fixture([(self.arm.frame(0), 4)], metadata_change=lambda m: m['packet_index'][0].pop('timestamp_source'))

    def test_read_wire_excludes_wrong_full_payload_despite_matching_nonce(self):
        frame = bytearray(reply(self.arm.frame(0)))
        frame[-1] ^= 1
        _, rows = self.read_fixture([(checksummed(frame), 0)])
        self.assertEqual(rows, [])
        # Non-anchor packets do not need a usable cross-clock timestamp.
        _, rows = self.read_fixture([(checksummed(frame), 0)], timestamp_source='userspace_receive_realtime')
        self.assertEqual(rows, [])

    def test_read_wire_excludes_wrong_size_code_and_sequence(self):
        base = reply(self.arm.frame(0))
        size = base + b'X'
        code = bytearray(base); code[35] = 1
        sequence = bytearray(base); sequence[40:42] = struct.pack('!H', self.arm.count)
        for frame in (size, code, sequence):
            with self.subTest(frame=bytes(frame).hex()):
                _, rows = self.read_fixture([(checksummed(frame), 0)])
                self.assertEqual(rows, [])

    def test_read_wire_excludes_wrong_l2_endpoints_and_roles(self):
        base = reply(self.arm.frame(0))
        for offset in (0, 6, 29, 33):
            frame = bytearray(base); frame[offset] ^= 2
            _, rows = self.read_fixture([(checksummed(frame), 0)])
            self.assertEqual(rows, [])
        _, rows = self.read_fixture([(base, 4), (self.arm.frame(0), 0)])
        self.assertEqual(rows, [])

    def test_read_wire_uses_seeded_plan_and_legacy_cycle(self):
        plan = [512, 56, 57]
        planned_arm = P.Arm(self.arm.source, self.arm.target, self.arm.source_mac, self.arm.target_mac,
                            self.arm.identifier, self.arm.nonce, tuple(plan), self.arm.count)
        _, rows = self.read_fixture([(planned_arm.frame(1), 4)], planned=plan)
        self.assertEqual(rows[0]['payloadlen'], 56)
        _, rows = self.read_fixture([(self.arm.frame(1), 4)], planned=plan)
        self.assertEqual(rows, [])
        _, rows = self.read_fixture([(self.arm.frame(1), 4)])
        self.assertEqual(rows[0]['payloadlen'], 57)
        with self.assertRaisesRegex(ValueError, 'size plan'):
            self.read_fixture([(self.arm.frame(1), 4)], planned=[56])

    def test_read_wire_preserves_pcap_index_integrity_checks(self):
        packet = [(self.arm.frame(0), 4)]
        for change in (lambda m: m['packet_index'][0].update(timestamp_ns=1),
                       lambda m: m['packet_index'][0].update(length=1),
                       lambda m: m['packet_index'][0].update(index=1),
                       lambda m: m['packet_index'][0].update(msg_trunc=True),
                       lambda m: m['packet_index'].clear()):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.read_fixture(packet, metadata_change=change)
        for change in (lambda b: b[:10], lambda b: b[:-1], lambda b: b + b'X'):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.read_fixture(packet, pcap_change=change)

    def test_repeated_tx_identity_is_ambiguous_not_forced(self):
        head = (b'R200PING' + self.arm.nonce).hex()
        base = dict(type=8, id=self.arm.identifier, seq=0, src=0xc0a80164, dst=0xc0a80101,
                    ipid=0, payloadlen=56, hash=123, head=head, port=2, ring=0, slot=0, buf=0, pool=0)
        rx = dict(base, ns=10, dir='rx')
        tx = dict(base, ns=20, dir='tx', type=0, ipid=5, src=base['dst'], dst=base['src'])
        wire = [dict(rx, ns=100, index=0, pkttype=4), dict(tx, ns=200, index=1, pkttype=0)]
        metadata = dict(icmp_identifier=self.arm.identifier, nonce_hex=self.arm.nonce.hex(), measurement_complete=True)
        result = M.correlate(metadata, wire, {'armed_id': str(self.arm.identifier)}, [rx, tx, dict(tx, ns=30)])
        self.assertEqual(result['matched_host_reply_records'], 0)
        self.assertFalse(result['clock_model']['feasible'])
        wrong_endpoint = dict(tx, dst=0xc0a80165)
        result = M.correlate(metadata, wire, {'armed_id': str(self.arm.identifier)}, [rx, wrong_endpoint])
        self.assertIsNone(result['events'][1]['nearest_preceding_rx_gap_ms'])
        self.assertEqual(result['events'][1]['preceding_matching_rx_count'], 0)


if __name__ == '__main__':
    unittest.main()
