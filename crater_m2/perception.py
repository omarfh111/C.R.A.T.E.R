"""Bounded handoff from M1's synchronous callback to the station event loop."""

import asyncio
from copy import deepcopy
import queue
import threading


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

    @property
    def buffered(self):
        return self.queue.qsize()

    @property
    def done(self):
        return not self.thread.is_alive() and self.queue.empty()

    def _offer(self, observation):
        snapshot = deepcopy(observation)
        while not self.stop.is_set():
            try:
                self.queue.put(snapshot, timeout=.05)
                self.produced += 1
                return
            except queue.Full:
                continue
        raise _Stopped()

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

        detector = (SyntheticContrastDetector() if args.perception_backend == "synthetic-contrast"
                    else GroundingDino(device=args.device, cache_dir=args.cache_dir))
        return run(args.perception_video, args.perception_output, detector,
                   calibration=args.calibration, stride=args.stride,
                   max_frames=args.max_frames, preview=not args.no_preview,
                   on_observation=callback)

    return produce
