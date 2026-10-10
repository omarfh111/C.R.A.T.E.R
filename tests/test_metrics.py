import pytest

from crater_m2.metrics import RunningStats
from crater_m2.radio import LinkConfig, RadioLink


def test_statistics_keep_full_counts_without_retaining_samples():
    stats = RunningStats()
    assert stats.count == 0 and stats.mean is None and stats.maximum is None
    for value in range(10000):
        stats.add(value)
    assert stats.count == 10000
    assert stats.mean == pytest.approx(4999.5)
    assert stats.maximum == 9999
    assert all(not isinstance(value, (list, dict, tuple, set)) for value in vars(stats).values())


def test_online_mean_does_not_overflow_when_sum_would():
    stats = RunningStats()
    stats.add(1e308)
    stats.add(1e308)
    assert stats.mean == 1e308
    assert stats.maximum == 1e308


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), True, 10**400])
def test_bad_measurements_rejected(value):
    with pytest.raises(ValueError):
        RunningStats().add(value)


def test_radio_history_is_bounded_and_old_capture_fails_explicitly():
    link = RadioLink(LinkConfig(bytes_per_second=100, blackouts=((6., 7.),)), history_capacity=4)
    for when in range(10):
        link.send(b"x", when, "data")
    assert link.history_size == 4
    assert link.snapshot(5.) == dict(status="connected", packetsSent=6, packetsLost=0)
    assert link.snapshot(6.5) == dict(status="disconnected", packetsSent=7, packetsLost=1)
    assert link.snapshot(9.) == dict(status="connected", packetsSent=10, packetsLost=1)
    with pytest.raises(ValueError, match="history"):
        link.snapshot(4.9)
    before = link.data_sent
    with pytest.raises(ValueError, match="monotonic"):
        link.send(b"x", 8., "data")
    assert link.data_sent == before
