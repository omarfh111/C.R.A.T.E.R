"""Offline measurement-harness regressions; no installed model calls."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


def benchmark_module():
    path = Path(__file__).resolve().parents[1] / "scripts/benchmark_assistant.py"
    spec = importlib.util.spec_from_file_location("assistant_benchmark_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_operation_latency_excludes_sampler_teardown(monkeypatch):
    module = benchmark_module()
    clock = [0.0]
    monkeypatch.setattr(module.time, "perf_counter", lambda: clock[0])

    class DelayedSampler:
        def __init__(self, **kwargs):
            pass

        def start(self):
            pass

        def join(self, timeout):
            clock[0] += 3.0

    monkeypatch.setattr(module.threading, "Thread", DelayedSampler)
    with module.sampled_resources() as measurement:
        clock[0] += 2.0
    assert measurement["elapsedS"] == 2.0
    assert measurement["samplerTeardownS"] == 3.0
    assert module.summarize(measurement["samples"])["peakGpuUsedMiB"] is None


def test_direct_benchmark_api_rejects_redirects(monkeypatch):
    module = benchmark_module()
    with pytest.raises(ValueError, match="redirects"):
        module.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "http://evil.example/")
