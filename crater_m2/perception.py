"""Bounded handoff from M1's synchronous callback to the station event loop."""

import asyncio
from copy import deepcopy
import json
import math
from pathlib import Path
import queue
import threading
import time


class _Stopped(Exception):
    pass


class PerceptionStream:
    """Producer executes in one worker; radio and WebSocket stay on asyncio.

    A full handoff blocks M1, without dropping captured observations. Shutdown
    is cooperative between inference calls; a running inference must finish.
    """

    def __init__(self, producer, *, capacity=4):
        if type(capacity) is not int or capacity < 1:
            raise ValueError("positive perception buffer capacity required")
        self.producer = producer
        self.queue = queue.Queue(maxsize=capacity)
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, name="crater-m1")
        self.error = None
        self.result = None
        self.interrupted = False
        self.produced = 0
        self.consumed = 0
        self.max_buffered = 0
        self.handoff_wait_s = 0.
        self.max_handoff_wait_s = 0.

    @property
    def buffered(self):
        return self.queue.qsize()

    @property
    def done(self):
        return not self.thread.is_alive() and self.queue.empty()

    def _offer(self, observation):
        snapshot = deepcopy(observation)
        started = time.perf_counter()
        try:
            while not self.stop.is_set():
                try:
                    self.queue.put(snapshot, timeout=.05)
                    self.produced += 1
                    self.max_buffered = max(self.max_buffered, self.queue.qsize())
                    return
                except queue.Full:
                    continue
            raise _Stopped()
        finally:
            waited = time.perf_counter() - started
            self.handoff_wait_s += waited
            self.max_handoff_wait_s = max(self.max_handoff_wait_s, waited)

    def _run(self):
        try:
            self.result = self.producer(self._offer)
        except _Stopped:
            self.interrupted = True
        except Exception as exc:
            self.error = exc

    def poll(self):
        if self.error is not None:
            raise ValueError(f"M1 perception failed: {self.error}") from self.error
        try:
            observation = self.queue.get_nowait()
            self.consumed += 1
            return observation
        except queue.Empty:
            return None

    async def __aenter__(self):
        self.thread.start()
        return self

    async def __aexit__(self, exc_type, *_):
        self.stop.set()
        # Do not leave inference/video writers running after mission exit.
        while self.thread.is_alive():
            await asyncio.sleep(.01)
        self.thread.join()
        if exc_type is None and self.error is not None:
            raise ValueError(f"M1 perception failed: {self.error}") from self.error


def local_producer(args):
    """Construct only local backends, in the worker to avoid blocking radio."""
    def produce(callback):
        from crater_m1.detectors import GroundingDino, SyntheticContrastDetector
        from crater_m1.pipeline import run
        from crater_m1.tracking import Tracker

        poses = json.loads(Path(args.calibration).read_text(encoding="utf-8"))
        if poses.get("frameId") != "LOCAL_ENU_V1":
            raise ValueError("calibration must declare LOCAL_ENU_V1 with the agreed mission origin")
        ground_z = poses.get("ground_z_m", 0)
        if type(ground_z) not in (int, float) or not math.isfinite(ground_z):
            raise ValueError("ground_z_m must be finite meters")

        def calibrated_callback(observation):
            enriched = dict(observation, groundZM=ground_z)
            replay.write(json.dumps(enriched, allow_nan=False) + "\n")
            replay.flush()
            callback(enriched)

        if args.perception_backend == "onnx-grounding-dino":
            from crater_m1.onnx_detector import OnnxGroundingDino
            detector = OnnxGroundingDino(device=args.device, cache_dir=args.cache_dir,
                threshold=args.threshold, text_threshold=args.text_threshold,
                max_area=args.max_rock_area, terrain_policy=args.terrain_filter)
        elif args.perception_backend == "synthetic-contrast":
            detector = SyntheticContrastDetector()
        elif args.perception_backend == "grounding-dino":
            detector = GroundingDino(device=args.device, cache_dir=args.cache_dir,
                threshold=args.threshold, text_threshold=args.text_threshold)
        else:
            raise ValueError("only explicitly selected local perception backends are supported")
        if args.tiles != "off":
            from crater_m1.tiling import TiledDetector
            detector = TiledDetector(detector)
        tracker = Tracker(min_hits=args.track_min_hits, max_missed=args.track_max_missed,
                          confirmed_only=args.confirmed_only)
        Path(args.perception_output).mkdir(parents=True, exist_ok=True)
        with (Path(args.perception_output) / "m2-observations.jsonl").open("x", encoding="utf-8") as replay:
            result = run(args.perception_video, args.perception_output, detector,
                       calibration=args.calibration, stride=args.stride,
                       max_frames=args.max_frames, preview=not args.no_preview,
                       tracker=tracker, on_observation=calibrated_callback)
        result["backend"] = args.perception_backend
        (Path(args.perception_output) / "metrics.json").write_text(
            json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
        return result

    return produce
