"""Conservative source for the four capture-verified common DME values."""
import socket
import threading
import time

from .common_dme_values import parse_value_response
from .dme_check import DME_TARGET_ADDRESS
from .gateway_check import TESTER_ADDRESS, load_gateway_capture
from .hsfz import HsfzClient
from .models import Sample, SignalDefinition, utc_now

SIGNALS = (
    SignalDefinition("engine_rpm", "Engine RPM", "rpm", provenance="SAE Mode 01 PID 0C",
                     confidence="one-shot-verified", verification="one-shot-verified", enabled=True),
    SignalDefinition("vehicle_speed", "Vehicle speed", "km/h", provenance="SAE Mode 01 PID 0D",
                     confidence="one-shot-verified", verification="one-shot-verified", enabled=True),
    SignalDefinition("intake_air_temperature", "Intake air temperature", "°C",
                     provenance="SAE Mode 01 PID 0F", confidence="one-shot-verified",
                     verification="one-shot-verified", enabled=True),
    SignalDefinition("throttle_position", "Throttle position", "%", provenance="SAE Mode 01 PID 11",
                     confidence="one-shot-verified", verification="one-shot-verified", enabled=True),
)
PIDS = (0x0C, 0x0D, 0x0F, 0x11)
MIN_REQUEST_INTERVAL_SECONDS = 1.0
STATIONARY_BOUNDS = ((300.0, 2500.0), (0.0, 0.0), (-40.0, 120.0), (0.0, 100.0))


class _MonitorStopRequested(Exception):
    """Shutdown acquired the gate before the next request could start."""


class _UdsRejected(ConnectionError):
    """A negative diagnostic response was returned for a requested signal."""


class _StationaryGateViolation(Exception):
    """A decoded value is outside the stationary idle acceptance bounds."""


class CommonDmeMonitorSource:
    """Read a fixed four-PID cycle, with a one-second floor between requests."""

    def __init__(self, capture, *, timeout=2.0, client_factory=HsfzClient,
                 connector_factory=socket.create_connection, monotonic=time.monotonic,
                 wait=None, duration=300):
        if not 0.1 <= float(timeout) <= 5.0:
            raise ValueError("invalid monitor timeout")
        if not isinstance(duration, int) or isinstance(duration, bool) or not 1 <= duration <= 300:
            raise ValueError("invalid monitor duration")
        peer, interface, _gateway_target, _vin = load_gateway_capture(capture)

        def source_bound_connector(address, connect_timeout):
            return connector_factory(address, connect_timeout, source_address=(interface, 0))

        self.client = client_factory(peer, TESTER_ADDRESS, DME_TARGET_ADDRESS, port=6801,
                                     timeout=timeout, fail_on_pending=True,
                                     sock_factory=source_bound_connector)
        self.timeout = float(timeout)
        self.signals = list(SIGNALS)
        self._stop = threading.Event()
        self._request_gate = threading.Lock()
        self._read_gate = threading.Lock()
        self._monotonic = monotonic
        self._wait = wait or self._stop.wait
        self._last_request_started = None
        self._deadline = self._monotonic() + duration
        self._request_budget = duration
        self._requests_started = 0
        self.connected = False
        self.halted = False
        self.halt_reason = None
        self._closed = False

    def close(self):
        self._stop.set()
        with self._request_gate:
            if not self._closed:
                self.client.close()
                self._closed = True
        self.connected = False

    def stop(self):
        """Prevent new requests and wait for any request already authorized."""
        self._stop.set()
        with self._request_gate:
            pass

    @staticmethod
    def _failure_category(exc):
        if isinstance(exc, TimeoutError):
            return "timeout"
        if isinstance(exc, ValueError):
            return "response-invalid"
        if isinstance(exc, _UdsRejected) or (isinstance(exc, ConnectionError) and (
                "pending UDS response" in str(exc) or "HSFZ error control" in str(exc))):
            return "uds-rejected"
        return "connection-or-transport"

    def _sample(self, signal, value=None, quality="good", error=None):
        return Sample(signal.id, value, signal.unit, "hsfz", "measured", quality,
                      utc_now(), time.monotonic_ns(), error)

    def _pace_next_request(self):
        while self._last_request_started is not None:
            remaining = (MIN_REQUEST_INTERVAL_SECONDS -
                         (self._monotonic() - self._last_request_started))
            if remaining <= 0:
                return
            self._wait(remaining)
            if self._stop.is_set():
                raise _MonitorStopRequested

    def _request(self, pid):
        self._pace_next_request()
        with self._request_gate:
            if self._stop.is_set():
                raise _MonitorStopRequested
            if self._requests_started >= self._request_budget or self._monotonic() >= self._deadline:
                self._stop.set()
                raise _MonitorStopRequested
            # Record immediately before entering transport; this also covers fast
            # fake clients and enforces the floor across cycle boundaries.
            self._last_request_started = self._monotonic()
            self._requests_started += 1
            return self.client.request(bytes((0x01, pid)))

    def read(self):
        with self._read_gate:
            if self.halted:
                return [self._sample(signal, quality="halted", error=self.halt_reason)
                        for signal in self.signals]

            output = []
            for index, (signal, pid) in enumerate(zip(self.signals, PIDS)):
                try:
                    response = self._request(pid)
                    if isinstance(response, bytes) and response[:1] == b"\x7f":
                        raise _UdsRejected
                    value, unit = parse_value_response(response, pid)
                    if unit != signal.unit:
                        raise ValueError("decoded unit does not match signal definition")
                    low, high = STATIONARY_BOUNDS[index]
                    if not low <= value <= high:
                        raise _StationaryGateViolation
                    output.append(self._sample(signal, value))
                except _MonitorStopRequested:
                    output.extend(self._sample(rest, quality="halted", error="stopped")
                                  for rest in self.signals[index:])
                    break
                except Exception as exc:
                    self.halted = True
                    self.halt_reason = ("stationary-gate" if isinstance(exc, _StationaryGateViolation)
                                        else self._failure_category(exc))
                    output.append(self._sample(signal, quality="error", error=self.halt_reason))
                    output.extend(self._sample(rest, quality="halted", error=self.halt_reason)
                                  for rest in self.signals[index + 1:])
                    self.close()
                    break

            self.connected = (not self.halted and not self._stop.is_set() and
                              getattr(self.client, "connected", False))
            return output
