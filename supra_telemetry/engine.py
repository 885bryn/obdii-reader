"""Serialized acquisition loop with measured rates, health state, and graceful stop."""
import time
from dataclasses import replace
from .mock import MockSource
from .models import utc_now


class AcquisitionEngine:
    def __init__(self, source=None, store=None, session_id=None, interval=0.5):
        self.source, self.store, self.session_id = source or MockSource(), store, session_id
        self.interval = max(0.1, float(interval))
        self.latest = {}
        self.running = False
        self.halted = False
        self.last_error = None
        self.recording_error = None
        self.observed_cycle_hz = None
        self._last_cycle_ns = None
        self._last_signal_ns = {}

    def _halt(self, error):
        self.halted = True
        self.last_error = str(error)
        if hasattr(self.source, "close"):
            try: self.source.close()
            except Exception: pass

    def step(self):
        cycle_start = time.monotonic_ns()
        if self._last_cycle_ns is not None and cycle_start > self._last_cycle_ns:
            self.observed_cycle_hz = 1e9 / (cycle_start - self._last_cycle_ns)
        self._last_cycle_ns = cycle_start
        try:
            samples = self.source.read()
        except Exception as exc:
            self._halt(exc)
            raise
        measured = []
        for sample in samples:
            rate = None
            previous = self._last_signal_ns.get(sample.signal_id)
            if previous is not None and sample.monotonic_ns > previous:
                rate = 1e9 / (sample.monotonic_ns - previous)
            self._last_signal_ns[sample.signal_id] = sample.monotonic_ns
            sample = replace(sample, observed_hz=rate)
            self.latest[sample.signal_id] = sample
            measured.append(sample)
            if self.store:
                try:
                    self.store.add_sample(self.session_id, sample)
                except Exception as exc:
                    self.recording_error = str(exc)
                    self._halt(f"recording error: {exc}")
                    raise
        return measured

    def run(self, stop_event):
        self.running = True
        try:
            while not stop_event.is_set() and not self.halted:
                started = time.monotonic()
                try:
                    self.step()
                except Exception:
                    break
                if getattr(self.source, "halted", False):
                    self.halted = True
                    self.last_error = getattr(self.source, "halt_reason", None) or self.last_error
                    if hasattr(self.source, "close"):
                        try: self.source.close()
                        except Exception: pass
                    break
                stop_event.wait(max(0, self.interval - (time.monotonic() - started)))
        finally:
            self.running = False
            if self.store and self.session_id is not None and hasattr(self.store, "end_session"):
                try:
                    self.store.end_session(self.session_id, utc_now())
                except Exception as exc:
                    self.recording_error = str(exc)
                    self.last_error = f"session finalization error: {exc}"
                    self.halted = True
                    if hasattr(self.source, "close"):
                        try: self.source.close()
                        except Exception: pass
