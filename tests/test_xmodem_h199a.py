"""Offline fixtures only: no serial, sockets, subprocesses, or board operations."""
from collections import Counter, deque
import dataclasses
import importlib.util
from pathlib import Path
import socket
import subprocess
import sys
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'tools/xmodem_h199a.py'
SPEC = importlib.util.spec_from_file_location('xmodem_h199a_tested', PATH)
M = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = M
SPEC.loader.exec_module(M)


def independent_crc(data):
    value = 0
    for byte in data:
        value ^= byte << 8
        for _ in range(8):
            value = ((value << 1) ^ (0x1021 if value & 0x8000 else 0)) & 0xFFFF
    return value


class Clock:
    def __init__(self): self.value = 0.0
    def __call__(self): return self.value
    def advance(self, seconds): self.value += seconds


class Receiver:
    """Model the reviewed H protocol, not just an unconditional ACK queue.

    expected-1 intentionally is NOT byte-masked: duplicate255 at expected0 is
    rejected. Full blocks (including padding) are copied up to the H cap; valid
    oversize blocks are still ACKed. First EOT enters console immediately.
    Faults are selected by (wire_sequence, attempt_number_for_that_sequence).
    """
    def __init__(self, *, initial=b'C', faults=None, eot='ack', max_chunk=None,
                 write_delay=0.0):
        self.clock = Clock()
        self.queue = deque()
        self.writes, self.reads, self.packets, self.controls = [], [], [], []
        self.buffer = bytearray()
        self.received = bytearray()
        self.expected = 1
        self.console = False
        self.after_console = []
        self.attempts = Counter()
        self.faults = faults or {}
        self.eot_action = eot
        self.max_chunk, self.write_delay = max_chunk, write_delay
        self.cancel_requested = False
        self.raise_on_cancel = False
        self.cancel_chunk = None
        self.schedule(initial)

    def schedule(self, data, delay=0.0):
        when = self.clock() + delay
        if self.queue:
            when = max(when, self.queue[-1][0])  # ordered delivery, no overtaking
        for byte in data:
            self.queue.append((when, byte))

    def read(self, size, timeout):
        assert size == 1 and timeout >= 0
        self.reads.append(timeout)
        if self.queue and self.queue[0][0] <= self.clock() + timeout:
            when, byte = self.queue.popleft()
            self.clock.advance(max(0, when - self.clock()))
            return bytes((byte,))
        self.clock.advance(timeout)
        return b''

    def write(self, data, timeout):
        assert isinstance(data, bytes) and timeout > 0
        self.writes.append(data)
        if self.console:
            self.after_console.append(data)
            return len(data)
        if data.startswith(bytes((M.CAN,))) and self.raise_on_cancel:
            raise OSError('cleanup broke')
        if self.write_delay > timeout:
            self.clock.advance(timeout)
            raise TimeoutError('write deadline')
        self.clock.advance(self.write_delay)
        limit = self.cancel_chunk if data.startswith(bytes((M.CAN,))) else self.max_chunk
        count = min(len(data), limit) if limit else len(data)
        self.buffer.extend(data[:count])
        self.consume()
        return count

    def consume(self):
        while self.buffer:
            first = self.buffer[0]
            if first == M.CAN:
                if len(self.buffer) < 2:
                    return
                if self.buffer[:2] != bytes((M.CAN, M.CAN)):
                    raise AssertionError('bad cancel fixture')
                del self.buffer[:2]
                self.controls.append('cancel')
                self.schedule(bytes((M.ACK,)))
                self.console = True
                return
            if first == M.EOT:
                del self.buffer[0]
                self.controls.append('eot')
                self.console = True  # real H exits even if its ACK is lost
                if self.eot_action == 'ack': self.schedule(bytes((M.ACK,)))
                elif self.eot_action == 'nak': self.schedule(bytes((M.NAK,)))
                elif self.eot_action == 'can': self.schedule(bytes((M.CAN, M.CAN)))
                elif self.eot_action == 'unexpected': self.schedule(b'C')
                elif self.eot_action == 'late': self.schedule(bytes((M.ACK,)), delay=5)
                elif self.eot_action == 'raise': raise OSError('EOT delivered, write failed')
                elif self.eot_action == 'interrupt': raise KeyboardInterrupt
                elif self.eot_action == 'cancel': self.cancel_requested = True
                elif self.eot_action != 'drop': raise AssertionError(self.eot_action)
                return
            assert first in (M.SOH, M.STX), 'sender emitted nonprotocol data'
            size = 128 if first == M.SOH else 1024
            if len(self.buffer) < size + 5:
                return
            packet = bytes(self.buffer[:size + 5])
            del self.buffer[:size + 5]
            self.packets.append(packet)
            seq = packet[1]
            self.attempts[seq] += 1
            action = self.faults.get((seq, self.attempts[seq]), 'ack')
            if action == 'nak':
                self.schedule(bytes((M.NAK,)))
                continue
            if action == 'can':
                self.console = True
                self.schedule(bytes((M.CAN, M.CAN, M.CAN)))
                continue
            if action == 'single_can':
                self.console = True
                self.schedule(bytes((M.CAN,)))
                continue
            if action == 'unexpected':
                self.schedule(b'C')
                continue
            checked = bytearray(packet)
            if action == 'corrupt': checked[3] ^= 0x80
            valid = (checked[1] == 255 - checked[2]
                     and independent_crc(checked[3:-2]) == int.from_bytes(checked[-2:], 'big'))
            if not valid or seq not in (self.expected, self.expected - 1):
                self.schedule(bytes((M.NAK,)))
                continue
            if seq == self.expected:
                room = M.MAX_BYTES - len(self.received)
                self.received.extend(packet[3:-2][:max(0, room)])
                self.expected = (self.expected + 1) & 255
            if action == 'drop_ack': pass
            elif action == 'late_ack': self.schedule(bytes((M.ACK,)), delay=5)
            elif action == 'accept_nak': self.schedule(bytes((M.NAK,)))
            elif action == 'nak_then_ack': self.schedule(bytes((M.NAK, M.ACK)))
            elif action == 'duplicate_ack': self.schedule(bytes((M.ACK, M.ACK)))
            elif action == 'raise': raise OSError('data delivered, write failed')
            else: self.schedule(bytes((M.ACK,)))


def run(receiver, data=b'hello\0\r\n\x03\x11\x13\x18\x1a\xff', *, block_size=1024, **options):
    return M.send(M.TransferPlan(data, block_size), receiver,
                  options=M.SenderOptions(response_timeout=1.0, handshake_timeout=1.0,
                                          total_timeout=20.0, **options),
                  clock=receiver.clock,
                  cancel_requested=lambda: receiver.cancel_requested)


class PlanTests(unittest.TestCase):
    def test_crc_known_vector_and_independent_reference(self):
        self.assertEqual(M.crc16_xmodem(b'123456789'), 0x31C3)
        self.assertEqual(M.crc16_xmodem(bytes(range(256))), independent_crc(bytes(range(256))))

    def test_golden_128_and_1024_frames(self):
        for size, header in ((128, 1), (1024, 2)):
            body = bytes(range(128)) * (size // 128)
            packet = M.TransferPlan(body, size).packet(0)
            self.assertEqual(packet[:3], bytes((header, 1, 254)))
            self.assertEqual(packet[3:-2], body)
            self.assertEqual(packet[-2:], independent_crc(body).to_bytes(2, 'big'))
            self.assertEqual(len(packet), size + 5)

    def test_padding_and_immutable_payload(self):
        source = bytearray(b'abc')
        plan = M.TransferPlan(source)
        source[:] = b'xyz'
        self.assertEqual(plan.payload, b'abc')
        self.assertEqual(plan.packet(0)[3:-2], b'abc' + bytes((0x1A,)) * 1021)
        with self.assertRaises(dataclasses.FrozenInstanceError): plan.block_size = 128

    def test_empty_type_and_block_size_rejected(self):
        for value in (b'', bytearray(), memoryview(b'')):
            with self.assertRaises(ValueError): M.TransferPlan(value)
        for value in ('filename', 10, [1, 2]):
            with self.assertRaises(TypeError): M.TransferPlan(value)
        for value in (0, 256, 1024.0, True):
            with self.assertRaises(ValueError): M.TransferPlan(b'x', value)

    def test_fixed_cap_includes_padding(self):
        for size in (128, 1024):
            self.assertEqual(M.TransferPlan(bytes(M.MAX_BYTES), size).padded_bytes, M.MAX_BYTES)
            self.assertEqual(M.TransferPlan(bytes(M.MAX_BYTES - 1), size).padded_bytes, M.MAX_BYTES)
            with self.assertRaises(ValueError): M.TransferPlan(bytes(M.MAX_BYTES + 1), size)
        # Exercise the padding-specific guard with a deliberately nonaligned fixture cap.
        with patch.object(M, 'MAX_BYTES', 1025):
            with self.assertRaises(ValueError): M.TransferPlan(bytes(1025))

    def test_packet_range_and_clean_wrap_numbers(self):
        p = M.TransferPlan(bytes(257 * 128), 128)
        self.assertEqual([p.packet(i)[1] for i in (253, 254, 255, 256)], [254, 255, 0, 1])
        for i in (-1, 257, True):
            with self.assertRaises(IndexError): p.packet(i)

    def test_options_reject_nonfinite_unbounded_and_invalid_types(self):
        for field in ('handshake_timeout', 'response_timeout', 'write_timeout', 'total_timeout',
                      'cancel_timeout', 'poll_interval'):
            for value in (0, -1, float('nan'), float('inf'), 3601, True, '1'):
                with self.assertRaises(ValueError): M.SenderOptions(**{field: value})
        for retries in (-1, 11, True, 1.0):
            with self.assertRaises(ValueError): M.SenderOptions(max_retries=retries)
        with self.assertRaises(ValueError): M.SenderOptions(poll_interval=1e-300)

    def test_revalidation_precedes_transport_activity(self):
        r = Receiver()
        p = M.TransferPlan(b'x')
        object.__setattr__(p, 'block_size', 256)
        with self.assertRaises(ValueError): M.send(p, r)
        with self.assertRaises(TypeError): M.send(b'not a plan', r)
        self.assertEqual(r.reads + r.writes, [])

    def test_import_does_not_open_serial_socket_or_process(self):
        spec = importlib.util.spec_from_file_location('xmodem_h199a_import_guard', PATH)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {spec.name: module, 'serial': None}), \
             patch.object(socket, 'socket', side_effect=AssertionError('socket opened')), \
             patch.object(subprocess, 'Popen', side_effect=AssertionError('process opened')):
            spec.loader.exec_module(module)


class SenderTests(unittest.TestCase):
    def test_default_1k_crc_and_binary_data(self):
        r = Receiver()
        data = bytes(range(256)) * 5
        result = run(r, data)
        self.assertEqual(bytes(r.received), data + bytes((M.PAD,)) * (2048 - len(data)))
        self.assertEqual((result.payload_bytes, result.padded_bytes, result.acknowledged_blocks),
                         (1280, 2048, 2))
        self.assertEqual((result.packet_attempts, result.nak_retries, result.bytes_written), (2, 0, 2059))
        self.assertTrue(result.protocol_complete)
        self.assertFalse(result.ram_verified or result.prompt_verified)
        self.assertEqual(r.controls, ['eot'])
        self.assertEqual(r.after_console, [])

    def test_explicit_128_only_no_automatic_size_or_checksum_downgrade(self):
        r = Receiver(faults={(1, 1): 'nak'})
        result = run(r, block_size=128)
        self.assertEqual([p[0] for p in r.packets], [M.SOH, M.SOH])
        self.assertEqual(result.nak_retries, 1)
        for first in (bytes((M.NAK,)), bytes((M.ACK,)), b'x', b'\r'):
            r = Receiver(initial=first)
            with self.assertRaises(M.ProtocolError): run(r)
            self.assertEqual(r.writes, [])

    def test_crc_corruption_nak_retries_identical_frame(self):
        r = Receiver(faults={(1, 1): 'corrupt'})
        result = run(r)
        self.assertEqual(r.packets[0], r.packets[1])
        self.assertEqual(result.nak_retries, 1)
        self.assertEqual(len(r.received), 1024)

    def test_receiver_duplicate_acceptance_does_not_copy_twice(self):
        r = Receiver(faults={(1, 1): 'accept_nak'})
        result = run(r)
        self.assertEqual(len(r.packets), 2)
        self.assertEqual(len(r.received), 1024)
        self.assertEqual(result.acknowledged_blocks, 1)

    def test_nak_budget_is_bounded_and_cleanup_once(self):
        r = Receiver(faults={(1, i): 'nak' for i in range(1, 5)})
        with self.assertRaises(M.RetryLimitError) as ctx: run(r, max_retries=2)
        self.assertEqual(len(r.packets), 3)
        self.assertEqual(ctx.exception.cancel_bytes_sent, 2)
        self.assertFalse(ctx.exception.prompt_verified)
        self.assertEqual(r.controls, ['cancel'])

    def test_zero_retry_budget(self):
        r = Receiver(faults={(1, 1): 'nak'})
        with self.assertRaises(M.RetryLimitError): run(r, max_retries=0)
        self.assertEqual(len(r.packets), 1)

    def test_lost_or_late_ack_is_terminal_not_speculative_retry(self):
        for action in ('drop_ack', 'late_ack'):
            r = Receiver(faults={(1, 1): action})
            with self.assertRaises(M.ResponseTimeout): run(r, bytes(2 * 1024))
            self.assertEqual(len(r.packets), 1)  # no duplicate ACK crossing into block2/EOT
            self.assertNotIn('eot', r.controls)
            self.assertLessEqual(r.clock(), 2.0)

    def test_buffered_duplicate_or_stale_ack_rejected_before_eot_or_next_data(self):
        for size in (1024, 2048):
            r = Receiver(faults={(1, 1): 'duplicate_ack'})
            with self.assertRaises(M.ProtocolError): run(r, bytes(size))
            self.assertEqual(len(r.packets), 1)
            self.assertNotIn('eot', r.controls)
        r = Receiver(faults={(1, 1): 'nak_then_ack'})
        with self.assertRaises(M.ProtocolError): run(r)
        self.assertEqual(len(r.packets), 1)

    def test_ack_at_deadline_is_not_accepted(self):
        r = Receiver(faults={(1, 1): 'drop_ack'})
        original = r.consume
        def consume():
            before = len(r.packets)
            original()
            if len(r.packets) > before:
                r.schedule(bytes((M.ACK,)), delay=1.0)
        r.consume = consume
        with self.assertRaises(M.ResponseTimeout): run(r)
        self.assertNotIn('eot', r.controls)

    def test_clean_multiple_wraps(self):
        r = Receiver()
        data = bytes(range(128)) * 513
        result = run(r, data, block_size=128)
        self.assertEqual(bytes(r.received), data)
        self.assertEqual(result.acknowledged_blocks, 513)
        self.assertEqual([r.packets[i][1] for i in (253, 254, 255, 256, 510, 511, 512)],
                         [254, 255, 0, 1, 255, 0, 1])

    def test_every_retry_needed_at_255_fails_closed_at_multiple_wraps(self):
        for occurrence in (1, 2):
            for action in ('nak', 'corrupt', 'drop_ack', 'late_ack', 'unexpected', 'accept_nak'):
                r = Receiver(faults={(255, occurrence): action})
                with self.assertRaises(M.WrapBoundaryError) as ctx:
                    run(r, bytes((256 * occurrence) * 128), block_size=128)
                self.assertEqual(ctx.exception.block, 255 + 256 * (occurrence - 1))
                self.assertEqual(r.attempts[255], occurrence)  # no forbidden retransmission
                self.assertNotIn('eot', r.controls)

    def test_receiver_model_reproduces_255_bug(self):
        r = Receiver(initial=b'')
        r.expected = 255
        packet = M.TransferPlan(bytes(255 * 128), 128).packet(254)
        r.write(packet, 1)
        self.assertEqual(r.expected, 0)
        self.assertEqual(r.read(1, 0), bytes((M.ACK,)))
        r.write(packet, 1)
        self.assertEqual(r.read(1, 0), bytes((M.NAK,)))
        self.assertEqual(len(r.received), 128)

    def test_remote_can_suppresses_all_cleanup_writes(self):
        for action in ('can', 'single_can'):
            r = Receiver(faults={(1, 1): action})
            with self.assertRaises(M.PeerCancelled) as ctx: run(r)
            self.assertEqual(ctx.exception.cancel_bytes_sent, 0)
            self.assertEqual(len(r.writes), 1)
            self.assertEqual(r.after_console, [])
        r = Receiver(initial=bytes((M.CAN, M.CAN)))
        with self.assertRaises(M.PeerCancelled): run(r)
        self.assertEqual(r.writes, [])

    def test_unexpected_post_handshake_control_is_terminal(self):
        for r in (Receiver(initial=b'CC'), Receiver(faults={(1, 1): 'unexpected'})):
            with self.assertRaises(M.ProtocolError): run(r)
            self.assertLessEqual(len(r.packets), 1)

    def test_known_short_writes_continue_only_suffix(self):
        r = Receiver(max_chunk=17)
        result = run(r, block_size=128)
        self.assertEqual(len(r.packets), 1)
        self.assertEqual(r.writes[1], r.writes[0][17:])
        self.assertEqual(result.bytes_written, 134)

    def test_partial_write_timeout_never_restarts_frame(self):
        r = Receiver(max_chunk=1, write_delay=0.02)
        with self.assertRaises(M.TransportError) as ctx: run(r, write_timeout=0.05)
        self.assertEqual(len(r.packets), 0)
        self.assertEqual(r.writes[1], r.writes[0][1:])
        self.assertEqual(ctx.exception.cancel_bytes_sent, 2)
        self.assertTrue(ctx.exception.receiver_state_unknown)
        self.assertLessEqual(r.clock(), 0.1)

    def test_unknown_data_delivery_then_exception_is_terminal(self):
        r = Receiver(faults={(1, 1): 'raise'})
        with self.assertRaises(M.TransportError): run(r)
        self.assertEqual(len(r.packets), 1)
        self.assertNotIn('eot', r.controls)

    def test_invalid_write_counts_and_read_contracts(self):
        for value in (0, -1, 5000, True, None, '1'):
            r = Receiver()
            r.write = lambda data, timeout, v=value: v
            with self.assertRaises(M.TransportContractError) as ctx: run(r)
            self.assertEqual(ctx.exception.cancel_bytes_sent, 0)
        for value in (b'CC', bytearray(b'C'), None):
            r = Receiver()
            r.read = lambda size, timeout, v=value: v
            with self.assertRaises(M.TransportContractError): run(r)
            self.assertEqual(r.writes, [])

    def test_handshake_timeout_has_no_unproven_receiver_cleanup(self):
        r = Receiver(initial=b'')
        with self.assertRaises(M.ResponseTimeout): run(r)
        self.assertEqual(r.writes, [])
        self.assertEqual(r.clock(), 1.0)

    def test_broken_empty_read_cannot_busy_loop_with_frozen_clock(self):
        r = Receiver(initial=b'')
        r.read = lambda size, timeout: b''
        with self.assertRaises(M.TransportContractError): run(r)
        self.assertEqual(r.writes, [])

    def test_overall_deadline_bounds_transfer_plus_cleanup(self):
        r = Receiver(faults={(1, 1): 'drop_ack'})
        with self.assertRaises(M.DeadlineExceeded):
            M.send(M.TransferPlan(b'x'), r, clock=r.clock,
                   options=M.SenderOptions(total_timeout=0.4, cancel_timeout=0.2))
        self.assertLessEqual(r.clock(), 0.6)
        self.assertEqual(len(r.packets), 1)

    def test_local_cancel_before_negotiation_and_after_data(self):
        r = Receiver()
        r.cancel_requested = True
        with self.assertRaises(M.LocalCancelled): run(r)
        self.assertEqual(r.writes, [])
        r = Receiver()
        with self.assertRaises(M.LocalCancelled) as ctx:
            M.send(M.TransferPlan(b'x'), r, clock=r.clock,
                   cancel_requested=lambda: len(r.packets) > 0)
        self.assertEqual(ctx.exception.cancel_bytes_sent, 2)
        self.assertFalse(ctx.exception.prompt_verified)

    def test_cleanup_failure_preserves_primary_error_and_known_progress(self):
        r = Receiver(faults={(1, 1): 'nak'})
        r.raise_on_cancel = True
        with self.assertRaises(M.RetryLimitError) as ctx: run(r, max_retries=0)
        self.assertIn('cleanup broke', ctx.exception.cleanup_error)
        self.assertEqual(ctx.exception.cancel_bytes_sent, 0)
        r = Receiver(faults={(1, 1): 'nak'})
        r.cancel_chunk = 1
        with self.assertRaises(M.RetryLimitError) as ctx: run(r, max_retries=0)
        self.assertEqual(ctx.exception.cancel_bytes_sent, 2)
        self.assertEqual(r.writes[-2:], [bytes((M.CAN, M.CAN)), bytes((M.CAN,))])

    def test_eot_once_no_writes_after_uncertain_or_interrupted_completion(self):
        for action in ('drop', 'late', 'nak', 'can', 'unexpected', 'raise', 'interrupt', 'cancel'):
            r = Receiver(eot=action)
            with self.assertRaises(M.CompletionUncertain) as ctx: run(r)
            self.assertEqual(r.controls, ['eot'])
            self.assertEqual(r.writes[-1], bytes((M.EOT,)))
            self.assertEqual(r.after_console, [])
            self.assertEqual(ctx.exception.cancel_bytes_sent, 0)
            self.assertTrue(ctx.exception.receiver_state_unknown)

    def test_callback_time_counts_against_absolute_write_and_overall_deadlines(self):
        for total, error_type in ((1.0, M.DeadlineExceeded), (10.0, M.TransportError)):
            r = Receiver(initial=b'')
            calls = 0
            def cancellation():
                nonlocal calls
                calls += 1
                if calls == 2:
                    r.clock.advance(2.0)
                return False
            sender = M._Sender(M.TransferPlan(b'x'), r,
                               M.SenderOptions(total_timeout=total, write_timeout=0.5),
                               r.clock, cancellation)
            with self.assertRaises(error_type):
                sender.write_all(sender.plan.packet(0))
            self.assertEqual(r.writes, [])  # stale pre-callback time must NOT permit a write

    def test_cancel_interrupt_or_bad_clock_after_can_never_writes_cleanup(self):
        for fault in ('cancel', 'interrupt', 'clock'):
            r = Receiver(faults={(1, 1): 'can'})
            observed_can = False
            original_read = r.read
            def read(size, timeout):
                nonlocal observed_can
                data = original_read(size, timeout)
                if data == bytes((M.CAN,)):
                    observed_can = True
                    if fault == 'clock': r.clock.value = -1.0
                return data
            def cancellation():
                if observed_can and fault == 'interrupt': raise KeyboardInterrupt
                return observed_can and fault == 'cancel'
            r.read = read
            expected = M.TransportContractError if fault == 'clock' else M.LocalCancelled
            with self.assertRaises(expected) as ctx:
                M.send(M.TransferPlan(b'x'), r, clock=r.clock, cancel_requested=cancellation)
            self.assertEqual(ctx.exception.cancel_bytes_sent, 0)
            self.assertEqual(len(r.writes), 1)
            self.assertEqual(r.after_console, [])

    def test_eot_delivered_then_invalid_write_count_never_writes_again(self):
        for value in (None, 0, 2, True):
            r = Receiver()
            original_write = r.write
            def write(data, timeout):
                count = original_write(data, timeout)
                return value if data == bytes((M.EOT,)) else count
            r.write = write
            with self.assertRaises(M.CompletionUncertain) as ctx: run(r)
            self.assertEqual(r.controls, ['eot'])
            self.assertEqual(r.after_console, [])
            self.assertEqual(ctx.exception.cancel_bytes_sent, 0)

    def test_cleanup_partial_then_unknown_delivery_exception_is_not_replayed(self):
        r = Receiver(faults={(1, 1): 'nak'})
        original_write = r.write
        cleanup_calls = []
        def write(data, timeout):
            if data.startswith(bytes((M.CAN,))):
                cleanup_calls.append(data)
                original_write(data[:1], timeout)
                if len(cleanup_calls) == 2: raise OSError('unknown suffix delivery')
                return 1
            return original_write(data, timeout)
        r.write = write
        with self.assertRaises(M.RetryLimitError) as ctx: run(r, max_retries=0)
        self.assertEqual(cleanup_calls, [bytes((M.CAN, M.CAN)), bytes((M.CAN,))])
        self.assertEqual(ctx.exception.cancel_bytes_sent, 1)  # only KNOWN progress
        self.assertIn('unknown suffix delivery', ctx.exception.cleanup_error)
        self.assertEqual(r.after_console, [])

    def test_cleanup_uses_one_absolute_deadline_for_all_short_writes(self):
        r = Receiver(faults={(1, 1): 'nak'})
        original_write = r.write
        cleanup_calls = []
        def write(data, timeout):
            if data.startswith(bytes((M.CAN,))):
                cleanup_calls.append(data)
                if timeout < 0.6:
                    r.clock.advance(timeout)
                    raise TimeoutError('cleanup timeout')
                r.clock.advance(0.6)
                return original_write(data[:1], timeout)
            return original_write(data, timeout)
        r.write = write
        with self.assertRaises(M.RetryLimitError) as ctx: run(r, max_retries=0)
        self.assertEqual(len(cleanup_calls), 2)
        self.assertEqual(ctx.exception.cancel_bytes_sent, 1)
        self.assertIn('cleanup timeout', ctx.exception.cleanup_error)
        self.assertEqual(r.clock(), 1.0)

    def test_short_read_timeouts_wait_for_same_ack_without_retransmission(self):
        r = Receiver(faults={(1, 1): 'drop_ack'})
        original_consume = r.consume
        def consume():
            before = len(r.packets)
            original_consume()
            if len(r.packets) > before: r.schedule(bytes((M.ACK,)), delay=0.75)
        r.consume = consume
        result = run(r)
        self.assertEqual(result.packet_attempts, 1)
        self.assertEqual(result.nak_retries, 0)
        self.assertEqual(r.clock(), 0.75)

    def test_receiver_silent_cap_does_not_defeat_sender_preflight(self):
        plan = M.TransferPlan(bytes(range(128)) * 2, 128)
        r = Receiver(initial=b'')
        with patch.object(M, 'MAX_BYTES', 128):
            # The model demonstrates the target's ACK-without-copy behavior.
            for i in range(2):
                r.write(plan.packet(i), 1.0)
                self.assertEqual(r.read(1, 0), bytes((M.ACK,)))
            self.assertEqual(len(r.received), 128)
            safe = Receiver()
            with self.assertRaises(ValueError): M.send(plan, safe, clock=safe.clock)
            self.assertEqual(safe.reads + safe.writes, [])

    def test_read_disconnect_is_terminal_and_no_adapter_close_is_called(self):
        r = Receiver()
        original_read = r.read
        r.close = lambda: self.fail('sender must not close caller-owned transport')
        def read(size, timeout):
            if r.packets: raise EOFError('adapter disconnected')
            return original_read(size, timeout)
        r.read = read
        with self.assertRaises(M.TransportError): run(r)
        self.assertEqual(len(r.packets), 1)
        self.assertNotIn('eot', r.controls)

    def test_clock_contract_fails_without_io(self):
        r = Receiver()
        for value in (float('nan'), float('inf'), True):
            with self.assertRaises(M.TransportContractError):
                M.send(M.TransferPlan(b'x'), r, clock=lambda v=value: v)
        self.assertEqual(r.writes + r.reads, [])


if __name__ == '__main__':
    unittest.main()
