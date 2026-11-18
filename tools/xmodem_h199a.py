"""Pure, conservative sender for the *own H199A* vendor ``xmodem`` receiver.

No serial/network/file opening, terminal configuration, boot command, flashing,
thread, or ownership integration is provided, including on import. See
artifacts/r203/COLD-RAM-TRANSPORT-REVIEW.md for the actual receiver evidence.

Usage (the caller, not this module, owns the already configured transport)::

    plan = TransferPlan(image_bytes)     # validate BEFORE entering xmodem
    # Parent-only integration enters a fresh receiver and consumes its exact
    # command banner, without consuming the following binary 'C'.
    result = send(plan, exclusive_binary_transport)
    # result is protocol evidence ONLY: independently verify target RAM/image.

Default: 1K blocks, CRC16/XMODEM only. ``TransferPlan(data, block_size=128)``
explicitly selects 128-byte blocks; never change sizes during a transfer. A
startup NAK is rejected, not permission to downgrade to 8-bit checksums.

The adapter must be exclusive, ordered, non-echoing and binary-safe, with no
stale bytes from another reader/session. A stale 'C' cannot authenticate a
fresh receiver. read(size, timeout) returns bytes (at most size); b'' means
that wait expired, NOT EOF. EOF/disconnection must raise. timeout=0 is a
nonblocking pending-byte check. write(data, timeout) returns the KNOWN accepted
prefix length; a short write continues only the unsent suffix. Methods must
honor their deadlines: Python cannot preempt an arbitrary injected callback.
The injected clock must be finite and monotonic; clock and cancellation
callbacks must return promptly, without blocking. Their elapsed time is charged
to the deadline but they cannot be preempted either. Cancellation is cooperative
between bounded I/O calls. A local failure can take total_timeout PLUS at most
cancel_timeout under those callback contracts (not a hard real-time guarantee).

Safety policy:
* Reject empty inputs and padded lengths exceeding the fixed 5 MiB copy cap.
* Only explicit NAKs permit same-frame retries. An ACK timeout or unexpected
  response is terminal: unnumbered late ACKs make speculative retries unsafe.
* Never retry sequence 255, even on NAK (the vendor's duplicate-wrap bug).
  Normal ...254,255,0,1... progression IS supported.
* Reject already-buffered out-of-phase controls before a write; this is not a
  proof against arbitrarily delayed/duplicated controls or bit-flipped ACKs.
* Attempt EOT once. The vendor exits to its console after EOT/ACK, so after an
  EOT write attempt there are NO further writes, even on exception/cancel.
* Local pre-EOT failures after CRC negotiation attempt exactly CAN CAN once,
  with bounded best-effort suffix completion. Do not cancel after remote CAN
  or a transport-contract violation. Cancellation does NOT restore/prove a
  prompt: the target may still be filling a packet for a long time.

The command discards receiver errors/counts. ACKed completion is neither full
RAM verification nor proof of a restored prompt. No automatic recovery/boot
is safe on the strength of this module's result alone.
"""
from __future__ import annotations

from binascii import crc_hqx
from dataclasses import dataclass
import math
import time
from typing import Callable, Protocol

SOH, STX, EOT, ACK, NAK, CAN, CRC_REQUEST = 1, 2, 4, 6, 0x15, 0x18, 0x43
MAX_BYTES = 5 * 1024 * 1024
PAD = 0x1A


class ByteTransport(Protocol):
    def read(self, size: int, timeout: float) -> bytes: ...
    def write(self, data: bytes, timeout: float) -> int: ...


def crc16_xmodem(data: bytes) -> int:
    """Polynomial 0x1021, initial zero, no final XOR."""
    return crc_hqx(data, 0)


@dataclass(frozen=True)
class TransferPlan:
    payload: bytes
    block_size: int = 1024

    def __post_init__(self):
        if type(self.block_size) is not int or self.block_size not in (128, 1024):
            raise ValueError('block_size must be explicitly 128 or 1024')
        if not isinstance(self.payload, (bytes, bytearray, memoryview)):
            raise TypeError('payload must be a bytes-like object, not a filename')
        size = self.payload.nbytes if isinstance(self.payload, memoryview) else len(self.payload)
        padded = ((size + self.block_size - 1) // self.block_size) * self.block_size
        if not size or padded > MAX_BYTES:
            raise ValueError('nonempty payload INCLUDING block padding must fit 5 MiB')
        object.__setattr__(self, 'payload', bytes(self.payload))

    @property
    def blocks(self) -> int:
        return (len(self.payload) + self.block_size - 1) // self.block_size

    @property
    def padded_bytes(self) -> int:
        return self.blocks * self.block_size

    def packet(self, index: int) -> bytes:
        """Zero-based absolute block index; wire sequence starts at one."""
        if type(index) is not int or not 0 <= index < self.blocks:
            raise IndexError('block outside transfer plan')
        sequence = (index + 1) & 0xFF
        body = self.payload[index * self.block_size:(index + 1) * self.block_size]
        body = body.ljust(self.block_size, bytes((PAD,)))
        return (bytes((STX if self.block_size == 1024 else SOH, sequence, 255 - sequence))
                + body + crc16_xmodem(body).to_bytes(2, 'big'))


@dataclass(frozen=True)
class SenderOptions:
    handshake_timeout: float = 30.0
    response_timeout: float = 3.0
    write_timeout: float = 3.0
    total_timeout: float = 900.0
    cancel_timeout: float = 1.0
    poll_interval: float = 0.25
    max_retries: int = 5

    def __post_init__(self):
        for name in ('handshake_timeout', 'response_timeout', 'write_timeout',
                     'total_timeout', 'cancel_timeout', 'poll_interval'):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or not 0 < value <= 3600):
                raise ValueError(f'{name} must be finite and in (0, 3600] seconds')
        if self.poll_interval < 0.001:
            raise ValueError('poll_interval must be at least 0.001 seconds')
        if type(self.max_retries) is not int or not 0 <= self.max_retries <= 10:
            raise ValueError('max_retries must be an integer in 0..10')


@dataclass(frozen=True)
class SendResult:
    payload_bytes: int
    padded_bytes: int
    acknowledged_blocks: int
    packet_attempts: int
    nak_retries: int
    bytes_written: int
    elapsed_seconds: float
    protocol_complete: bool = True
    ram_verified: bool = False
    prompt_verified: bool = False


class TransferError(RuntimeError):
    """Terminal outcome; never resume by guessing the next block/console state."""
    def __init__(self, message, *, phase, block, acknowledged_blocks):
        super().__init__(message)
        self.phase = phase
        self.block = block       # one-based absolute block, not modulo-256
        self.sequence = None if block is None else block & 255
        self.acknowledged_blocks = acknowledged_blocks
        self.cancel_bytes_sent = 0
        self.cleanup_error = None
        self.receiver_state_unknown = True
        self.prompt_verified = False


class ProtocolError(TransferError): pass
class ResponseTimeout(TransferError): pass
class DeadlineExceeded(TransferError): pass
class RetryLimitError(TransferError): pass
class WrapBoundaryError(TransferError): pass
class PeerCancelled(TransferError): pass
class LocalCancelled(TransferError): pass
class TransportError(TransferError): pass
class TransportContractError(TransportError): pass
class CompletionUncertain(TransferError): pass


class _WaitExpired(Exception): pass


class _Sender:
    def __init__(self, plan, transport, options, clock, cancel_requested):
        self.plan, self.transport, self.options = plan, transport, options
        self.clock, self.cancel_requested = clock, cancel_requested
        self.phase, self.block = 'handshake', None
        self.acknowledged = self.attempts = self.retries = self.bytes_written = 0
        self.negotiated = self.remote_can = self.eot_attempted = False
        self.last_time = None
        self.start = self.now()
        self.end = self.start + options.total_timeout

    def error(self, kind, message):
        return kind(message, phase=self.phase, block=self.block,
                    acknowledged_blocks=self.acknowledged)

    def now(self):
        value = self.clock()
        if (isinstance(value, bool) or not isinstance(value, (int, float))
                or not math.isfinite(value)
                or self.last_time is not None and value < self.last_time):
            raise self.error(TransportContractError, 'clock is not finite/monotonic')
        self.last_time = value
        return value

    def check(self):
        now = self.now()
        if now >= self.end:
            raise self.error(DeadlineExceeded, 'overall transfer deadline expired')
        if self.cancel_requested is not None:
            cancelled = self.cancel_requested()
            # Callback execution itself consumes the same absolute deadline.
            now = self.now()
            if now >= self.end:
                raise self.error(DeadlineExceeded, 'deadline expired during cancellation callback')
            if cancelled:
                raise self.error(LocalCancelled, 'caller requested cancellation')
        return now

    def read(self, timeout):
        try:
            data = self.transport.read(1, timeout)
        except TimeoutError:
            data = b''
        except Exception as exc:
            raise self.error(TransportError, f'read failed: {exc}') from exc
        if not isinstance(data, bytes) or len(data) > 1:
            raise self.error(TransportContractError, 'read must return at most one byte')
        if data == bytes((CAN,)):
            self.remote_can = True  # suppress cleanup even if second CAN is lost
        return data

    def control(self, deadline):
        """Poll cancellation within ONE absolute response deadline; never resend."""
        deadline = min(deadline, self.end)
        budget = math.ceil(max(0, deadline - self.now()) / self.options.poll_interval) + 2
        for _ in range(budget):
            now = self.check()
            if now >= deadline:
                raise _WaitExpired
            data = self.read(min(self.options.poll_interval, deadline - now))
            after = self.check()
            if after >= deadline:  # an ACK at/after the boundary is ambiguous
                raise _WaitExpired
            if data:
                return data[0]
            if after <= now:
                raise self.error(TransportContractError, 'empty read did not advance time')
        raise self.error(TransportContractError, 'read returned early too often')

    def no_pending(self):
        self.check()
        data = self.read(0.0)
        self.check()
        if data:
            if data[0] == CAN:
                raise self.error(PeerCancelled, 'remote CAN before next write')
            raise self.error(ProtocolError, f'out-of-phase buffered byte 0x{data[0]:02x}')

    def write_all(self, data):
        deadline = min(self.check() + self.options.write_timeout, self.end)
        offset = 0
        while offset < len(data):
            now = self.check()
            if now >= deadline:
                raise self.error(TransportError, 'write deadline expired; delivery uncertain')
            try:
                count = self.transport.write(data[offset:], deadline - now)
            except Exception as exc:
                raise self.error(TransportError, f'write failed; delivery uncertain: {exc}') from exc
            if type(count) is not int or not 0 < count <= len(data) - offset:
                raise self.error(TransportContractError, 'invalid/zero write progress')
            offset += count
            self.bytes_written += count
            if self.check() >= deadline:
                raise self.error(TransportError, 'write exceeded its absolute deadline')

    def peer_cancel(self, deadline):
        try:
            second = self.control(deadline)
        except _WaitExpired:
            raise self.error(PeerCancelled, 'single CAN; cancellation/state uncertain')
        detail = 'remote CAN CAN' if second == CAN else 'single CAN followed by unexpected byte'
        raise self.error(PeerCancelled, detail)

    def run(self):
        deadline = min(self.start + self.options.handshake_timeout, self.end)
        try:
            first = self.control(deadline)
        except _WaitExpired:
            raise self.error(ResponseTimeout, 'CRC handshake timeout')
        if first == CAN:
            self.peer_cancel(deadline)
        if first != CRC_REQUEST:
            raise self.error(ProtocolError, 'fresh CRC C required; no checksum/banner guessing')
        self.negotiated = True
        self.phase = 'data'
        for index in range(self.plan.blocks):
            self.block = index + 1
            sequence = self.block & 255
            packet = self.plan.packet(index)
            for retry in range(self.options.max_retries + 1):
                self.no_pending()
                self.attempts += 1
                self.write_all(packet)
                deadline = min(self.now() + self.options.response_timeout, self.end)
                try:
                    response = self.control(deadline)
                except _WaitExpired:
                    kind = WrapBoundaryError if sequence == 255 else ResponseTimeout
                    raise self.error(kind, 'ACK timeout; never retransmit an ambiguously accepted block')
                if response == ACK:
                    self.acknowledged += 1
                    break
                if response == CAN:
                    self.peer_cancel(deadline)
                if sequence == 255:
                    raise self.error(WrapBoundaryError, 'sequence255 retry forbidden by vendor wrap quirk')
                if response != NAK:
                    raise self.error(ProtocolError, f'unexpected block response 0x{response:02x}')
                if retry == self.options.max_retries:
                    raise self.error(RetryLimitError, 'explicit NAK retry budget exhausted')
                self.retries += 1
        self.no_pending()
        self.phase = 'eot'
        self.eot_attempted = True  # BEFORE calling write: delivery may precede an exception
        try:
            self.write_all(bytes((EOT,)))
            response = self.control(min(self.now() + self.options.response_timeout, self.end))
            if response != ACK:
                raise self.error(CompletionUncertain, 'EOT was not unambiguously ACKed')
        except CompletionUncertain:
            raise
        except (TransferError, _WaitExpired) as exc:
            raise self.error(CompletionUncertain, 'EOT outcome uncertain; no further writes allowed') from exc
        return SendResult(len(self.plan.payload), self.plan.padded_bytes, self.acknowledged,
                          self.attempts, self.retries, self.bytes_written, self.now() - self.start)

    def cleanup(self, failure):
        if (not self.negotiated or self.remote_can or self.eot_attempted
                or isinstance(failure, TransportContractError)):
            return
        # Separate bounded cleanup allowance. Never repeat bytes of unknown delivery.
        try:
            deadline = self.now() + self.options.cancel_timeout
            data = bytes((CAN, CAN))
            while failure.cancel_bytes_sent < 2:
                left = deadline - self.now()
                if left <= 0:
                    raise TimeoutError('cancellation deadline expired')
                suffix = data[failure.cancel_bytes_sent:]
                count = self.transport.write(suffix, left)
                if type(count) is not int or not 0 < count <= len(suffix):
                    raise ValueError('invalid cancellation write progress')
                failure.cancel_bytes_sent += count
                if self.now() >= deadline:
                    raise TimeoutError('cancellation write exceeded deadline')
        except BaseException as exc:
            failure.cleanup_error = f'{type(exc).__name__}: {exc}'


def send(plan: TransferPlan, transport: ByteTransport, *,
         options: SenderOptions | None = None,
         clock: Callable[[], float] = time.monotonic,
         cancel_requested: Callable[[], bool] | None = None) -> SendResult:
    """Send an immutable, prevalidated plan; terminal errors expose cleanup status.

    Never auto-retry this function on the same receiver after failure. The caller
    owns recovery, UART ownership, target-image verification and any later boot.
    """
    if not isinstance(plan, TransferPlan):
        raise TypeError('construct TransferPlan before entering the receiver')
    # Revalidate public objects before I/O, including deliberately altered instances.
    plan = TransferPlan(plan.payload, plan.block_size)
    if options is None:
        options = SenderOptions()
    if not isinstance(options, SenderOptions):
        raise TypeError('options must be SenderOptions')
    options = SenderOptions(**vars(options))
    if not callable(clock) or cancel_requested is not None and not callable(cancel_requested):
        raise TypeError('clock and cancellation callback must be callable')
    if not callable(getattr(transport, 'read', None)) or not callable(getattr(transport, 'write', None)):
        raise TypeError('transport must provide read and write callbacks')
    sender = _Sender(plan, transport, options, clock, cancel_requested)
    try:
        return sender.run()
    except TransferError as exc:
        sender.cleanup(exc)
        raise
    except KeyboardInterrupt as exc:
        failure = sender.error(CompletionUncertain if sender.eot_attempted else LocalCancelled,
                               'interrupted; receiver state unknown')
        sender.cleanup(failure)
        raise failure from exc
    except Exception as exc:
        failure = sender.error(CompletionUncertain if sender.eot_attempted else TransportError,
                               f'callback failure; receiver state unknown: {exc}')
        sender.cleanup(failure)
        raise failure from exc
