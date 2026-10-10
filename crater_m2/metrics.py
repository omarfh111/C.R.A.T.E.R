"""Streaming nonnegative metrics with constant sample-storage cost."""

import math


class RunningStats:
    def __init__(self):
        self.count = 0
        self._mean = 0.
        self.maximum = None

    @property
    def mean(self):
        return self._mean if self.count else None

    def add(self, value):
        try:
            valid = type(value) in (int, float) and math.isfinite(value) and value >= 0
        except OverflowError:
            valid = False
        if not valid:
            raise ValueError("measurement must be finite and nonnegative")
        self.count += 1
        self._mean += (value - self._mean) / self.count
        self.maximum = value if self.maximum is None else max(self.maximum, value)
