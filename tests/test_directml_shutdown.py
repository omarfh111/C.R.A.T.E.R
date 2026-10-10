"""Bound Windows DirectML CLI shutdown to the fully closed mission path."""

from pathlib import Path
from types import SimpleNamespace

import crater_m2.__main__ as cli


class Stream:
    def __init__(self):
        self.flushed = False

    def flush(self):
        self.flushed = True


def test_windows_directml_flushes_before_native_exit(monkeypatch):
    stdout, stderr = Stream(), Stream()
    exits = []
    monkeypatch.setattr(cli.sys, "stdout", stdout)
    monkeypatch.setattr(cli.sys, "stderr", stderr)
    monkeypatch.setattr(cli, "_terminate_windows_process", exits.append)
    args = SimpleNamespace(perception_video=Path("calibrated.mp4"), device="directml")

    assert cli._finish_process(args, 0, platform="win32") == 0
    assert exits == [0]
    assert stdout.flushed and stderr.flushed


def test_other_paths_do_not_use_native_exit(monkeypatch):
    exits = []
    monkeypatch.setattr(cli, "_terminate_windows_process", exits.append)
    for args, platform in (
        (SimpleNamespace(perception_video=None, device="directml"), "win32"),
        (SimpleNamespace(perception_video=Path("calibrated.mp4"), device="cpu"), "win32"),
        (SimpleNamespace(perception_video=Path("calibrated.mp4"), device="directml"), "linux"),
    ):
        assert cli._finish_process(args, 2, platform=platform) == 2
    assert exits == []
