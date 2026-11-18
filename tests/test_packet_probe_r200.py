"""Synthetic, host-only tests. Real socket construction is forbidden throughout."""
import contextlib
import importlib.util
import io
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock

PATH = Path(__file__).resolve().parents[1] / "tools" / "packet-probe-r200.py"
SPEC = importlib.util.spec_from_file_location("packet_probe_r200", PATH)
probe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


def fix_ip(frame):
    result = bytearray(frame)
    ihl = (result[14] & 15) * 4
    result[24:26] = b"\0\0"
    result[24:26] = struct.pack("!H", probe.checksum(bytes(result[14:14 + ihl])))
    return bytes(result)


def fix_icmp(frame):
    result = bytearray(frame)
    start = 14 + (result[14] & 15) * 4
    total = struct.unpack_from("!H", result, 16)[0]
    result[start + 2:start + 4] = b"\0\0"
    result[start + 2:start + 4] = struct.pack("!H", probe.checksum(bytes(result[start:14 + total])))
    return bytes(result)


def reply(frame):
    result = bytearray(frame)
    result[:6], result[6:12] = frame[6:12], frame[:6]
    result[26:30], result[30:34] = frame[30:34], frame[26:30]
    result[34] = 0
    return fix_ip(fix_icmp(result))


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.socket_guard = mock.patch.object(probe.socket, "socket", side_effect=AssertionError("REAL SOCKET FORBIDDEN"))
        self.socket_guard.start()
        self.addCleanup(self.socket_guard.stop)
        self.arm = probe.Arm("192.168.1.100", "192.168.1.1", bytes.fromhex("020000000001"),
                             bytes.fromhex("0620842f87b5"), 0x1234, bytes(range(16)), (56, 57, 512), 6)
        self.measurement = probe.Measurement(self.arm)
        for seq in range(self.arm.count):
            self.measurement.note_send(seq, 100, True)

    def observe(self, frame, direction=0, timestamp=200):
        return self.measurement.observe(frame, direction, timestamp)[0]

    def test_frame_roundtrip_and_odd_checksum(self):
        for seq in range(self.arm.count):
            echo = probe.parse_echo(self.arm.frame(seq))
            self.assertEqual(echo.payload, self.arm.payload(seq))
            self.assertEqual((echo.identifier, echo.sequence, echo.kind), (0x1234, seq, 8))
        self.assertEqual(probe.checksum(b"\x00\x01\xf2\x03\xf4\xf5\xf6\xf7"), 0x220d)

    def test_exact_reply_duplicates_and_send_observation(self):
        frame = self.arm.frame(0)
        self.assertEqual(self.observe(frame, 4, 100), "observed_outgoing_requests")
        self.assertEqual(self.observe(frame, 4, 101), "duplicate_outgoing_requests")
        self.assertEqual(self.observe(reply(frame), 0, 200), "unique_exact_replies")
        self.assertEqual(self.observe(reply(frame), 0, 201), "duplicate_replies")
        result = self.measurement.report()
        self.assertEqual(result["unique_exact_replies"], 1)
        self.assertEqual(result["unique_observed_host_egress"], 1)
        self.assertEqual(result["observed_egress_without_reply_percent"], 0)
        self.assertEqual(result["successful_sends_not_observed"], [1, 2, 3, 4, 5])
        self.assertEqual(result["per_sequence"][0]["capture_rtt_ms"], 0.0001)

    def test_syscall_success_is_not_wire_observation(self):
        result = self.measurement.report()
        self.assertEqual(result["send_syscall_successes"], 6)
        self.assertEqual(result["unique_observed_host_egress"], 0)
        self.assertIsNone(result["observed_egress_without_reply_percent"])
        self.observe(reply(self.arm.frame(2)))
        self.assertEqual(self.measurement.report()["replies_without_observed_egress"], [2])

    def test_returned_own_request_never_counts_as_reply(self):
        frame = self.arm.frame(0)
        self.assertEqual(self.observe(frame), "returned_own_requests")
        self.assertEqual(self.observe(frame), "duplicate_returned_own_requests")
        self.assertEqual(self.measurement.report()["unique_exact_replies"], 0)
        self.assertEqual(self.observe(reply(frame), 4), "unexpected_outgoing_frames")

    def test_foreign_identifier(self):
        frame = bytearray(reply(self.arm.frame(0)))
        frame[38] ^= 1
        self.assertEqual(self.observe(fix_icmp(frame)), "foreign_identifier_frames")

    def test_foreign_nonce(self):
        frame = bytearray(reply(self.arm.frame(0)))
        frame[50] ^= 1
        self.assertEqual(self.observe(fix_icmp(frame)), "foreign_nonce_frames")

    def test_wrong_sequence(self):
        frame = bytearray(reply(self.arm.frame(0)))
        frame[40:42] = struct.pack("!H", 999)
        self.assertEqual(self.observe(fix_icmp(frame)), "wrong_sequence_frames")

    def test_wrong_size_even_with_valid_checksums(self):
        frame = bytearray(reply(self.arm.frame(0)))
        frame.extend(b"X")
        struct.pack_into("!H", frame, 16, len(frame) - 14)
        self.assertEqual(self.observe(fix_ip(fix_icmp(frame))), "wrong_payload_size_frames")

    def test_payload_full_pattern_not_only_nonce(self):
        frame = bytearray(reply(self.arm.frame(0)))
        frame[-1] ^= 1
        self.assertEqual(self.observe(fix_icmp(frame)), "wrong_payload_frames")

    def test_bad_icmp_checksum(self):
        frame = bytearray(reply(self.arm.frame(0)))
        frame[-1] ^= 1
        self.assertEqual(self.observe(frame), "bad_icmp_checksum_frames")

    def test_bad_ip_checksum(self):
        frame = bytearray(reply(self.arm.frame(0)))
        frame[22] ^= 1
        self.assertEqual(self.observe(frame), "bad_ip_checksum_frames")

    def test_truncated_and_malformed(self):
        frame = self.arm.frame(0)
        for size in (0, 12, 14, 25, 33, len(frame) - 1):
            self.assertEqual(self.observe(frame[:size]), "truncated_frames")
        malformed = bytearray(frame)
        malformed[14] = 0x44
        self.assertEqual(self.observe(malformed), "malformed_frames")
        self.assertEqual(self.measurement.observe(frame, 0, 200, True)[0], "truncated_frames")

    def test_ip_options_and_ethernet_padding(self):
        raw = reply(self.arm.frame(1))
        frame = bytearray(raw[:34] + b"\x01\x01\x00\x00" + raw[34:])
        frame[14] = 0x46
        struct.pack_into("!H", frame, 16, len(frame) - 14)
        self.assertEqual(self.observe(fix_ip(frame) + b"ethernet padding"), "unique_exact_replies")

    def test_malformed_ip_options(self):
        raw = reply(self.arm.frame(1))
        frame = bytearray(raw[:34] + b"\x44\xff\x00\x00" + raw[34:])
        frame[14] = 0x46
        struct.pack_into("!H", frame, 16, len(frame) - 14)
        self.assertEqual(self.observe(fix_ip(frame)), "malformed_frames")

    def test_vlan_reply_and_non_ipv4(self):
        raw = reply(self.arm.frame(0))
        vlan = raw[:12] + b"\x81\x00\x00\x07" + raw[12:]
        self.assertEqual(self.observe(vlan), "unique_exact_replies")
        self.assertEqual(self.observe(raw[:12] + b"\x08\x06" + raw[14:]), "non_ipv4_frames")

    def test_fragments_are_not_reassembled_or_counted(self):
        frame = bytearray(self.arm.frame(0))
        frame[20:22] = b"\x20\x00"
        self.assertEqual(self.observe(fix_ip(frame)), "fragmented_frames")

    def test_wrong_l2_and_ip_endpoints(self):
        frame = bytearray(reply(self.arm.frame(0)))
        frame[6] ^= 2
        self.assertEqual(self.observe(frame), "wrong_l2_frames")
        frame = bytearray(reply(self.arm.frame(0)))
        frame[29] ^= 2
        self.assertEqual(self.observe(fix_ip(frame)), "wrong_endpoint_frames")

    def test_unsent_sequence_and_negative_rtt(self):
        fresh = probe.Measurement(self.arm)
        self.assertEqual(fresh.observe(reply(self.arm.frame(0)), 0, 1)[0], "unsent_echo_frames")
        self.observe(self.arm.frame(0), 4, 300)
        self.observe(reply(self.arm.frame(0)), 0, 200)
        result = self.measurement.report()
        self.assertEqual(result["timestamp_order_anomalies"], [0])
        self.assertIsNone(result["per_sequence"][0]["capture_rtt_ms"])

    def test_pcap_preserves_full_ethernet_and_nanoseconds(self):
        stream = io.BytesIO()
        writer = probe.PcapWriter(stream)
        frame = self.arm.frame(0)
        writer.packet(frame, 1234567890123)
        raw = stream.getvalue()
        self.assertEqual(raw[:4], b"\x4d\x3c\xb2\xa1")
        self.assertEqual(struct.unpack_from("<IIII", raw, 24), (1234, 567890123, len(frame), len(frame)))
        self.assertEqual(raw[40:], frame)

    def test_kernel_timestamp_and_explicit_fallback(self):
        ancillary = [(probe.socket.SOL_SOCKET, probe.SO_TIMESTAMPNS, struct.pack("@ll", 3, 45))]
        self.assertEqual(probe.receive_timestamp(ancillary, 99), (3000000045, "kernel_software_realtime"))
        self.assertEqual(probe.receive_timestamp([], 99), (99, "userspace_receive_realtime"))

    def test_packet_binding_not_routing(self):
        fake = mock.Mock()
        probe.bind_packet_socket(fake, "eth-test")
        fake.bind.assert_called_once_with(("eth-test", 0))
        fake.setblocking.assert_called_once_with(False)

    def cli(self, directory, *extra):
        return ["--iface", "enx00e04c125990", "--source", "192.168.1.100", "--target", "192.168.1.1",
                "--target-mac", "06:20:84:2f:87:b5", "--output-prefix", str(Path(directory) / "arm")] + list(extra)

    def test_valid_cli_and_50pps(self):
        with tempfile.TemporaryDirectory() as directory:
            args = probe.parse_args(self.cli(directory, "--sizes", "56,57,512,1400"))
            self.assertEqual(args.sizes, (56, 57, 512, 1400))
            args = probe.parse_args(self.cli(directory, "--count", "1000", "--interval", "0.02"))
            self.assertEqual(args.count, 1000)

    def test_invalid_arguments_fail_before_sockets(self):
        with tempfile.TemporaryDirectory() as directory:
            for options in (("--source", "router.local"), ("--target", "224.0.0.1"),
                            ("--target", "0.0.0.0"), ("--target", "192.168.1.100"),
                            ("--target-mac", "ff:ff:ff:ff:ff:ff"), ("--target-mac", "06:20:84"),
                            ("--iface", "bad/iface"), ("--interval", "nan"), ("--interval", "inf"),
                            ("--count", "0"), ("--count", "1001"), ("--count", "1000"),
                            ("--grace", "6"), ("--sizes", "27"), ("--sizes", "1401"),
                            ("--sizes", "56,")):
                with self.subTest(options=options), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                    probe.main(self.cli(directory, *options))
                self.assertEqual(caught.exception.code, 2)

    def test_existing_output_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "arm.pcap"
            path.write_bytes(b"preserve")
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                probe.parse_args(self.cli(directory))
            self.assertEqual(path.read_bytes(), b"preserve")

    def test_read_only_interface_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            args = probe.parse_args(self.cli(directory))
            address = bytes(20) + bytes((192, 168, 1, 100)) + bytes(232)
            mask = bytes(20) + bytes((255, 255, 255, 0)) + bytes(232)
            mtu = bytes(16) + struct.pack("@i", 1500) + bytes(236)
            with mock.patch.object(probe.fcntl, "ioctl", side_effect=[address, mask, mtu]):
                self.assertEqual(probe.validate_interface(mock.Mock(), args), 1500)
            args.source = "192.168.1.101"
            with mock.patch.object(probe.fcntl, "ioctl", side_effect=[address, mask, mtu]), self.assertRaises(ValueError):
                probe.validate_interface(mock.Mock(), args)

    def test_identifier_and_extended_bounds(self):
        with tempfile.TemporaryDirectory() as directory:
            for identifier in (0, 65535):
                args = probe.parse_args(self.cli(directory, "--identifier", str(identifier)))
                self.assertEqual(args.identifier, identifier)
            args = probe.parse_args(self.cli(directory, "--extended", "--count", "3", "--interval", "30", "--grace", "60"))
            self.assertEqual(args.send_offsets[-1] + args.grace, 120)
            for options in (("--identifier", "-1"), ("--identifier", "65536"),
                            ("--size-seed", "-1"), ("--size-seed", str(2**64)),
                            ("--pause-after", "8"), ("--pause-seconds", "20"),
                            ("--pause-after", "0", "--pause-seconds", "20"),
                            ("--pause-after", "30", "--pause-seconds", "20"),
                            ("--pause-after", "8", "--pause-seconds", "0"),
                            ("--pause-after", "8", "--pause-seconds", "61"),
                            ("--pause-after", "8", "--pause-seconds", "nan"),
                            ("--pause-after", "8", "--pause-seconds", "inf"),
                            ("--extended", "--grace", "61"),
                            ("--extended", "--count", "4", "--interval", "30", "--grace", "31"),
                            ("--pause-after", "8", "--pause-seconds", "60", "--grace", "60")):
                with self.subTest(options=options), contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    probe.parse_args(self.cli(directory, *options))

    def test_pause_plan_and_legacy_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            args = probe.parse_args(self.cli(directory))
            self.assertFalse(args.extended)
            self.assertIsNone(args.identifier)
            self.assertIsNone(args.size_seed)
            self.assertEqual(args.pause_seconds, 0)
            self.assertEqual(args.send_offsets, tuple(i * 0.5 for i in range(30)))
            args = probe.parse_args(self.cli(directory, "--count", "16", "--pause-after", "8", "--pause-seconds", "20", "--grace", "30"))
            self.assertTrue(args.extended)
            self.assertEqual(args.send_offsets, tuple(i * 0.5 for i in range(8)) + tuple(24 + i * 0.5 for i in range(8)))
            self.assertEqual(args.send_offsets[-1] + args.grace, 57.5)

    def test_seeded_plan_is_deterministic_and_payload_uses_exact_plan(self):
        sizes = (56, 57, 512, 1400)
        plan = probe.plan_sizes(sizes, 32, 201)
        self.assertEqual(plan, probe.plan_sizes(sizes, 32, 201))
        self.assertNotEqual(plan, probe.plan_sizes(sizes, 32, 202))
        self.assertNotEqual(plan, probe.plan_sizes(sizes, 32))
        self.assertEqual(set(plan), set(sizes))
        arm = probe.Arm(self.arm.source, self.arm.target, self.arm.source_mac, self.arm.target_mac,
                        self.arm.identifier, self.arm.nonce, plan, 32)
        for seq, size in enumerate(plan):
            parsed = probe.parse_echo(arm.frame(seq))
            self.assertEqual(len(parsed.payload), size)
            self.assertEqual(struct.unpack("!HH", parsed.payload[24:28]), (seq, size))

    def fake_run(self, args, respond=True, drops=0, nonce=bytes(range(16))):
        """Exercise the actual loop using fake sockets and a virtual clock only."""
        clock = [0.0]
        epoch_ns = 1700000000000000000
        events, sent = [], []
        received = [0]
        cap, tx = mock.Mock(), mock.Mock()
        cap.getsockname.return_value = (args.iface, 3, 0, 1, self.arm.source_mac)
        cap.getsockopt.side_effect = lambda *unused: struct.pack("=II", received[0], drops)

        def time_ns():
            return epoch_ns + round(clock[0] * 1e9)

        def send(frame):
            echo = probe.parse_echo(frame)
            sent.append((clock[0], frame))
            events.append((clock[0], frame, 4))
            if respond:
                delay = 10.0 if echo.sequence == 0 else 50.0 if echo.sequence == args.count - 1 else clock[0] + 0.0001
                events.append((delay, reply(frame), 0))
                if echo.sequence == 0:
                    foreign = bytearray(reply(frame))
                    foreign[38:40] = struct.pack("!H", (echo.identifier + 1) & 65535)
                    events.append((11.0, fix_icmp(foreign), 0))
            events.sort(key=lambda item: item[0])
            return len(frame)

        def choose(readers, writers, exceptions, timeout):
            until = clock[0] + timeout
            if events and events[0][0] <= until:
                clock[0] = max(clock[0], events[0][0])
                return [cap], [], []
            clock[0] = until
            return [], [], []

        def receive(*unused):
            if not events or events[0][0] > clock[0]:
                raise BlockingIOError
            at, frame, direction = events.pop(0)
            received[0] += 1
            seconds, nanoseconds = divmod(epoch_ns + round(at * 1e9), 10**9)
            ancillary = [(probe.socket.SOL_SOCKET, probe.SO_TIMESTAMPNS, struct.pack("@ll", seconds, nanoseconds))]
            return frame, ancillary, 0, (args.iface, 3, direction, 1, self.arm.source_mac)

        tx.send.side_effect = send
        cap.recvmsg.side_effect = receive
        stream = io.BytesIO()
        with mock.patch.object(probe.socket, "socket", side_effect=[cap, tx]) as construction, \
                mock.patch.object(probe.socket, "if_nametoindex", return_value=1), \
                mock.patch.object(probe, "validate_interface", return_value=1500), \
                mock.patch.object(probe.time, "monotonic", side_effect=lambda: clock[0]), \
                mock.patch.object(probe.time, "monotonic_ns", side_effect=lambda: round(clock[0] * 1e9)), \
                mock.patch.object(probe.time, "time_ns", side_effect=time_ns), \
                mock.patch.object(probe.select, "select", side_effect=choose), \
                mock.patch.object(probe.secrets, "token_bytes", return_value=nonce) as entropy, \
                mock.patch.object(probe.secrets, "randbelow", return_value=333) as random_id:
            result = probe.run_measurement(args, probe.PcapWriter(stream))
            self.assertEqual(construction.call_count, 2)
            entropy.assert_called_once_with(16)
            self.assertEqual(random_id.call_count, 0 if args.identifier is not None else 1)
        cap.close.assert_called_once()
        tx.close.assert_called_once()
        return result, sent, stream.getvalue()

    def test_continuous_capture_pause_resume_drain_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            args = probe.parse_args(self.cli(directory, "--identifier", "0", "--count", "16", "--sizes", "56,57,512,1400", "--size-seed", "201", "--pause-after", "8", "--pause-seconds", "20", "--grace", "30"))
            result, sent, pcap = self.fake_run(args)
        self.assertTrue(result["measurement_complete"])
        self.assertEqual(result["icmp_identifier"], 0)
        self.assertTrue(result["identifier_provided"])
        self.assertEqual(result["nonce_sha256"], probe.hashlib.sha256(bytes(range(16))).hexdigest())
        self.assertEqual(result["size_seed"], 201)
        self.assertEqual(result["planned_data_lengths"], list(args.planned_sizes))
        self.assertEqual([at for at, frame in sent], list(args.send_offsets))
        self.assertEqual(result["scheduled_capture_elapsed_seconds"], 57.5)
        self.assertEqual(result["measurement"]["unique_observed_host_egress"], 16)
        self.assertEqual(result["measurement"]["unique_exact_replies"], 16)
        self.assertEqual(result["measurement"]["counters"]["foreign_identifier_frames"], 1)
        incoming = [item for item in result["packet_index"] if item["classification"] == "unique_exact_replies"]
        self.assertEqual(next(item for item in incoming if item["sequence"] == 0)["timestamp_ns"], 1700000010000000000)
        self.assertEqual(next(item for item in incoming if item["sequence"] == 15)["timestamp_ns"], 1700000050000000000)
        for seq, ((at, frame), row) in enumerate(zip(sent, result["measurement"]["per_sequence"])):
            self.assertEqual(probe.parse_echo(frame).sequence, seq)
            self.assertEqual(len(probe.parse_echo(frame).payload), args.planned_sizes[seq])
            self.assertEqual(row["planned"]["data_length"], row["send"]["data_length"])
            self.assertEqual(row["planned"]["monotonic_ns"], row["send"]["syscall_monotonic_ns"])
            self.assertEqual(row["planned"]["realtime_ns"], row["send"]["syscall_timestamp_ns"])
        position, packets = 24, 0
        while position < len(pcap):
            length = struct.unpack_from("<IIII", pcap, position)[2]
            position += 16 + length
            packets += 1
        self.assertEqual(position, len(pcap))
        self.assertEqual(packets, 33)  # 16 sends, 16 exact replies, one foreign

    def test_nonce_not_seeded_and_misses_do_not_invalidate_measurement(self):
        with tempfile.TemporaryDirectory() as directory:
            args = probe.parse_args(self.cli(directory, "--identifier", "65535", "--size-seed", "0"))
            first, sent, _ = self.fake_run(args, respond=False)
            second, _, _ = self.fake_run(args, respond=False, nonce=bytes(reversed(range(16))))
            dropped, _, _ = self.fake_run(args, respond=False, drops=1)
        self.assertTrue(first["measurement_complete"])
        self.assertEqual(first["measurement"]["unique_exact_replies"], 0)
        self.assertEqual(first["measurement"]["observed_egress_without_reply_percent"], 100)
        self.assertEqual(len(sent), args.count)
        self.assertEqual(first["planned_data_lengths"], second["planned_data_lengths"])
        self.assertNotEqual(first["nonce_hex"], second["nonce_hex"])
        self.assertNotEqual(first["nonce_sha256"], second["nonce_sha256"])
        self.assertFalse(dropped["measurement_complete"])


if __name__ == "__main__":
    unittest.main()
