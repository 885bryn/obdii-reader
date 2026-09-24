"""Deterministic-ish simulated source; never opens a vehicle connection."""
import math, time
from .models import Sample, utc_now


class MockSource:
    def __init__(self): self.started = time.monotonic()
    def read(self):
        t = time.monotonic() - self.started
        now = time.monotonic_ns()
        return [Sample("engine_rpm", 850 + int(400 * (1 + math.sin(t * .8))), "rpm", "mock", "measured", "simulated", utc_now(), now),
                Sample("vehicle_speed", round(35 + 20 * math.sin(t * .3), 1), "km/h", "mock", "measured", "simulated", utc_now(), now),
                Sample("coolant_temp", 88.0, "°C", "mock", "measured", "simulated", utc_now(), now),
                Sample("boost", round(0.2 + .1 * math.sin(t), 2), "bar", "mock", "derived", "simulated", utc_now(), now),
                Sample("gear", None, "", "mock", "unavailable", "unavailable", utc_now(), now, "No verified gear source configured")]
