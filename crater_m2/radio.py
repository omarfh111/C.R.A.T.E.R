"""Deterministic, byte-budgeted half-duplex radio and FIFO ARQ.

Virtual times are seconds from mission start. A lost transmission consumes its
full byte budget. ACKs use the same medium, latency, loss and blackout rules.
"""

from collections import deque
from dataclasses import dataclass
import heapq
import math
import random

from .codec import decode_ack, decode_frame, encode_ack, encode_frame
from .metrics import RunningStats


@dataclass(frozen=True)
class LinkConfig:
    bytes_per_second: float = 256
    latency_s: float = .1
    jitter_s: float = 0
    loss_probability: float = 0
    blackouts: tuple = ()
    seed: int = 7

    def __post_init__(self):
        if not all(math.isfinite(v) for v in (self.bytes_per_second, self.latency_s, self.jitter_s, self.loss_probability)):
            raise ValueError("link settings must be finite")
        if self.bytes_per_second <= 0 or min(self.latency_s, self.jitter_s) < 0 or not 0 <= self.loss_probability <= 1:
            raise ValueError("invalid bandwidth, delay or loss")
        intervals = tuple(sorted(tuple(interval) for interval in self.blackouts))
        for interval in intervals:
            if len(interval) != 2 or not all(math.isfinite(v) for v in interval) or not 0 <= interval[0] < interval[1]:
                raise ValueError("blackouts require finite 0 <= start < end")
        object.__setattr__(self, "blackouts", intervals)


@dataclass(frozen=True)
class Transmission:
    arrives_at: float
    lost: bool


class RadioLink:
    def __init__(self, config: LinkConfig, *, history_capacity=4096):
        if type(history_capacity) is not int or history_capacity < 1:
            raise ValueError("positive link history capacity required")
        self.config = config
        self.random = random.Random(config.seed)
        self.available_at = 0.
        self.data_sent = self.data_lost = self.ack_sent = self.ack_lost = 0
        self.data_bytes = self.ack_bytes = 0
        self.history_capacity = history_capacity
        self._data_attempts = deque()
        self._history_baseline = None
        self._last_send_time = 0.

    @property
    def history_size(self):
        return len(self._data_attempts)

    @property
    def packets_sent(self):
        return self.data_sent + self.ack_sent

    @property
    def packets_lost(self):
        return self.data_lost + self.ack_lost

    @property
    def bytes_sent(self):
        return self.data_bytes + self.ack_bytes

    def resume_at(self, now):
        # Merge overlapping blackout intervals by walking to their last end.
        result = now
        for start, end in self.config.blackouts:
            if start <= result < end:
                result = end
        return result

    def status(self, now):
        if self.resume_at(now) > now:
            return "disconnected"
        return "degraded" if self.config.loss_probability > 0 or self.config.latency_s > .25 else "connected"

    def snapshot(self, captured_at_s):
        """Capture-time DATA attempt counters for delayed local perception.

        Attempts use the simulator's send-call time, as its cumulative counters
        do; loss is the simulated outcome, not a physical loss estimator.
        """
        if not math.isfinite(captured_at_s) or captured_at_s < 0:
            raise ValueError("invalid capture time")
        sent = lost = 0
        if self._history_baseline is not None:
            floor, sent, lost = self._history_baseline
            if captured_at_s < floor:
                raise ValueError("capture predates retained radio history; increase --link-history")
        for when, cumulative_sent, cumulative_lost in self._data_attempts:
            if when > captured_at_s:
                break
            sent, lost = cumulative_sent, cumulative_lost
        return dict(status=self.status(captured_at_s), packetsSent=sent, packetsLost=lost)

    def send(self, payload: bytes, now: float, kind: str) -> Transmission:
        if kind not in ("data", "ack") or not isinstance(payload, bytes) or not payload:
            raise ValueError("expected nonempty bytes and data/ack kind")
        if not math.isfinite(now) or now < 0:
            raise ValueError("invalid transmission time")
        if now < self._last_send_time:
            raise ValueError("transmission time must be monotonic")
        self._last_send_time = now
        start = max(now, self.available_at)
        self.available_at = start + len(payload) / self.config.bytes_per_second
        arrival = self.available_at + self.config.latency_s + self.random.uniform(0, self.config.jitter_s)
        random_loss = self.random.random() < self.config.loss_probability
        blackout = any(a < arrival and b > start for a, b in self.config.blackouts)
        lost = random_loss or blackout
        if kind == "data":
            self.data_sent += 1
            self.data_lost += int(lost)
            self.data_bytes += len(payload)
            if len(self._data_attempts) == self.history_capacity:
                self._history_baseline = self._data_attempts.popleft()
            self._data_attempts.append((now, self.data_sent, self.data_lost))
        else:
            self.ack_sent += 1
            self.ack_lost += int(lost)
            self.ack_bytes += len(payload)
        return Transmission(arrival, lost)


@dataclass
class _Pending:
    packet: bytes
    sequence: int
    enqueued_at: float
    attempts: int = 0


@dataclass(frozen=True)
class Delivery:
    frame: dict
    received_at_s: float
    latency_s: float


class ReliableTransport:
    """One rover stream per instance; stop-and-wait preserves capture ordering."""

    def __init__(self, link: RadioLink, *, max_queue=64, max_attempts=20, retry_timeout_s=.25):
        if type(max_queue) is not int or type(max_attempts) is not int or min(max_queue, max_attempts) <= 0:
            raise ValueError("positive integer queue and retry limits required")
        if not math.isfinite(retry_timeout_s) or retry_timeout_s <= 0:
            raise ValueError("positive finite retry timeout required")
        self.link = link
        self.max_queue = max_queue
        self.max_attempts = max_attempts
        self.retry_timeout_s = retry_timeout_s
        self.clock = 0.
        self._queue = deque()
        self._events = []
        self._event_id = 0
        self._attempt_token = 0
        self._waiting = False
        self._rover_id = None
        self._last_generated = -1
        self._last_received = -1
        self._deliveries = []
        self.delivered = self.acknowledged = self.duplicates = 0
        self.queue_dropped = self.abandoned = self.retransmissions = 0
        self.generated = self.accepted = 0
        self.max_pending = 0
        self._latency_stats = RunningStats()

    @property
    def pending(self):
        return len(self._queue)

    def enqueue(self, frame: dict) -> bool:
        packet = encode_frame(frame)
        rover, sequence = frame["roverId"], frame["sequence"]
        if self._rover_id is not None and rover != self._rover_id or sequence <= self._last_generated:
            raise ValueError("one rover stream with increasing generated sequences required")
        self._rover_id = rover
        self._last_generated = sequence
        self.generated += 1
        if len(self._queue) >= self.max_queue:
            self.queue_dropped += 1
            return False
        self._queue.append(_Pending(packet, sequence, self.clock))
        self.accepted += 1
        self.max_pending = max(self.max_pending, len(self._queue))
        self._try_send()
        return True

    def _schedule(self, when, kind, value):
        self._event_id += 1
        heapq.heappush(self._events, (when, self._event_id, kind, value))

    def _try_send(self):
        if self._waiting or not self._queue:
            return
        item = self._queue[0]
        resume = self.link.resume_at(self.clock)
        if resume > self.clock:
            self._waiting = True
            self._schedule(resume, "wake", item.sequence)
            return
        if item.attempts >= self.max_attempts:
            self._queue.popleft()
            self.abandoned += 1
            self._try_send()
            return
        self.retransmissions += int(item.attempts > 0)
        item.attempts += 1
        self._attempt_token += 1
        token = self._attempt_token
        self._waiting = True
        tx = self.link.send(item.packet, self.clock, "data")
        if not tx.lost:
            self._schedule(tx.arrives_at, "data", item)
        # Wait for worst-case ACK airtime/delay in addition to DATA airtime.
        ack_budget = len(encode_ack(item.sequence)) / self.link.config.bytes_per_second
        deadline = tx.arrives_at + ack_budget + self.link.config.latency_s + self.link.config.jitter_s + self.retry_timeout_s
        self._schedule(deadline, "timeout", (item.sequence, token))

    def advance(self, now: float):
        if not math.isfinite(now) or now < self.clock:
            raise ValueError("clock must be finite and monotonic")
        while self._events and self._events[0][0] <= now:
            when, _, kind, value = heapq.heappop(self._events)
            self.clock = when
            if kind == "data":
                frame = decode_frame(value.packet)
                if frame["sequence"] > self._last_received:
                    self._last_received = frame["sequence"]
                    latency = when - value.enqueued_at
                    self._deliveries.append(Delivery(frame, when, latency))
                    self._latency_stats.add(latency)
                    self.delivered += 1
                else:
                    self.duplicates += 1
                ack = encode_ack(frame["sequence"])
                tx = self.link.send(ack, when, "ack")
                if not tx.lost:
                    self._schedule(tx.arrives_at, "ack", ack)
            elif kind == "ack":
                sequence = decode_ack(value)
                if self._queue and self._queue[0].sequence == sequence:
                    self._queue.popleft()
                    self.acknowledged += 1
                    self._waiting = False
                    self._try_send()
            elif kind == "timeout":
                sequence, token = value
                if self._queue and self._queue[0].sequence == sequence and token == self._attempt_token:
                    self._waiting = False
                    self._try_send()
            elif kind == "wake":
                if self._queue and self._queue[0].sequence == value:
                    self._waiting = False
                    self._try_send()
        self.clock = now

    def take_deliveries(self) -> list[Delivery]:
        result, self._deliveries = self._deliveries, []
        return result

    def report(self) -> dict:
        return dict(generated=self.generated, enqueued=self.accepted, delivered=self.delivered,
                    acknowledged=self.acknowledged, pending=self.pending, maxPending=self.max_pending,
                    queueDropped=self.queue_dropped, abandoned=self.abandoned,
                    retransmissions=self.retransmissions, radioDuplicates=self.duplicates,
                    dataPacketsSent=self.link.data_sent, dataPacketsLost=self.link.data_lost,
                    ackPacketsSent=self.link.ack_sent, ackPacketsLost=self.link.ack_lost,
                    dataBytesSent=self.link.data_bytes, ackBytesSent=self.link.ack_bytes,
                    totalBytesSent=self.link.bytes_sent,
                    deliveryRate=self.delivered / self.generated if self.generated else 0,
                    meanDeliveryLatencyS=self._latency_stats.mean,
                    maxDeliveryLatencyS=self._latency_stats.maximum)
