from copy import deepcopy

import pytest

from crater_m2.codec import encode_frame
from crater_m2.radio import LinkConfig, RadioLink, ReliableTransport


def advance_until_done(transport, limit=60):
    for step in range(1, int(limit * 100) + 1):
        transport.advance(step / 100)
        if not transport.pending:
            return
    pytest.fail("transport did not drain")


def test_byte_bandwidth_and_shared_ack_budget():
    link = RadioLink(LinkConfig(bytes_per_second=100, latency_s=.2))
    a = link.send(b"x" * 100, 0, "data")
    b = link.send(b"x" * 50, 0, "ack")
    assert a.arrives_at == pytest.approx(1.2)
    assert b.arrives_at == pytest.approx(1.7)
    assert link.bytes_sent == 150


def test_blackout_intersecting_transmission_is_loss():
    link = RadioLink(LinkConfig(bytes_per_second=100, blackouts=((.5, 2.),)))
    assert link.send(b"x" * 100, 0, "data").lost
    assert link.status(1) == "disconnected"
    assert link.status(3) == "connected"


def test_normal_delivery_order_and_ack(frame):
    transport = ReliableTransport(RadioLink(LinkConfig(bytes_per_second=1000)))
    for seq in range(5):
        frame["sequence"] = seq
        assert transport.enqueue(frame)
    advance_until_done(transport)
    deliveries = transport.take_deliveries()
    assert [d.frame["sequence"] for d in deliveries] == list(range(5))
    assert transport.delivered == 5
    assert transport.acknowledged == 5
    assert transport.link.ack_sent == 5


def test_seeded_loss_recovers_without_station_duplicates(frame):
    transport = ReliableTransport(RadioLink(LinkConfig(
        bytes_per_second=1000, loss_probability=.45, seed=7)), max_attempts=100)
    for seq in range(10):
        frame["sequence"] = seq
        transport.enqueue(frame)
    advance_until_done(transport)
    assert [d.frame["sequence"] for d in transport.take_deliveries()] == list(range(10))
    assert transport.link.packets_lost > 0
    assert transport.retransmissions > 0
    assert transport.duplicates > 0  # lost ACK forces duplicate radio delivery


def test_blackout_buffers_and_recovers(frame):
    transport = ReliableTransport(RadioLink(LinkConfig(blackouts=((0., 5.),))))
    transport.enqueue(frame)
    transport.advance(4.99)
    assert transport.pending == 1
    assert transport.delivered == 0
    assert transport.link.packets_sent == 0
    transport.advance(8)
    assert transport.pending == 0
    assert transport.delivered == 1


def test_buffer_limit_and_exhausted_retries(frame):
    transport = ReliableTransport(RadioLink(LinkConfig(loss_probability=1)),
                                  max_queue=1, max_attempts=3)
    assert transport.enqueue(frame)
    second = deepcopy(frame)
    second["sequence"] += 1
    assert not transport.enqueue(second)
    advance_until_done(transport)
    assert transport.queue_dropped == 1
    assert transport.abandoned == 1
    assert transport.link.data_sent == 3
    assert transport.delivered == 0


def test_adaptive_timeout_does_not_retry_during_slow_transmission(frame):
    transport = ReliableTransport(RadioLink(LinkConfig(bytes_per_second=10, latency_s=1)),
                                  retry_timeout_s=.1)
    transport.enqueue(frame)
    advance_until_done(transport)
    assert transport.link.data_sent == 1
    assert transport.retransmissions == 0
    assert transport.delivered == 1


def test_capture_timestamp_and_counters_not_rewritten(frame):
    transport = ReliableTransport(RadioLink(LinkConfig(blackouts=((0., 2.),))))
    transport.enqueue(frame)
    frame["capturedAt"] = "2026-10-10T15:00:00Z"
    transport.advance(5)
    received = transport.take_deliveries()[0].frame
    assert received["capturedAt"] == "2026-10-10T12:00:00.000Z"
    assert received["link"]["packetsSent"] == 42


def test_sequence_stream_and_monotonic_clock(frame):
    transport = ReliableTransport(RadioLink(LinkConfig()))
    transport.enqueue(frame)
    with pytest.raises(ValueError):
        transport.enqueue(frame)
    transport.advance(1)
    with pytest.raises(ValueError):
        transport.advance(.5)


@pytest.mark.parametrize("kwargs", [dict(bytes_per_second=0), dict(loss_probability=1.1),
                                   dict(latency_s=-1), dict(jitter_s=float("nan")),
                                   dict(blackouts=((3, 1),))])
def test_invalid_link_configuration(kwargs):
    with pytest.raises(ValueError):
        LinkConfig(**kwargs)
