"""Bounded loopback dashboard for a simulated demo or capture-bound live reads."""
import math
import mimetypes
import re
import socket
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .common_dme_values import parse_value_response
from .dme_check import DME_TARGET_ADDRESS
from .emissions_dtcs import (FAILURE_REASONS as DTC_FAILURE_REASONS,
                             REJECTION_SUBTYPES, EmissionsDtcError,
                             read_emissions_dtcs)
from .gateway_check import TESTER_ADDRESS, load_gateway_capture
from .hsfz import HsfzClient
from .models import Sample, SignalDefinition, utc_now
from .temperature_values import parse_temperature_response

TICK_SECONDS = 0.1
# Two-second, 20-slot cycle split into identical one-second occupancy windows:
# five requests per second, with RPM every 0.5s, throttle every 1s, and each
# remaining signal every 2s. Empty slots keep requests serialized.
SCHEDULE = (0x0C, None, 0x11, 0x0D, None, 0x0C, None, 0x0F, None, None,
            0x0C, None, 0x11, 0x05, None, 0x0C, None, 0x5C, None, None)
SIGNALS = (
    SignalDefinition("engine_rpm", "Engine RPM", "rpm", provenance="SAE Mode 01 PID 0C", confidence="one-shot-verified", verification="one-shot-verified", enabled=True),
    SignalDefinition("vehicle_speed", "Vehicle speed", "km/h", provenance="SAE Mode 01 PID 0D", confidence="one-shot-verified", verification="one-shot-verified", enabled=True),
    SignalDefinition("intake_air_temperature", "Intake air temperature", "°C", provenance="SAE Mode 01 PID 0F", confidence="one-shot-verified", verification="one-shot-verified", enabled=True),
    SignalDefinition("throttle_position", "Throttle position", "%", provenance="SAE Mode 01 PID 11", confidence="one-shot-verified", verification="one-shot-verified", enabled=True),
    SignalDefinition("coolant_temp", "Coolant temperature", "°C", provenance="SAE Mode 01 PID 05", confidence="verified", verification="verified", enabled=True),
    SignalDefinition("engine_oil_temp", "Engine oil temperature", "°C", provenance="SAE Mode 01 PID 5C", confidence="verified", verification="verified", enabled=True),
)
BY_PID = {0x0C: SIGNALS[0], 0x0D: SIGNALS[1], 0x0F: SIGNALS[2], 0x11: SIGNALS[3], 0x05: SIGNALS[4], 0x5C: SIGNALS[5]}
BOUNDS = {0x0C: (300, 2500), 0x0D: (0, 0), 0x0F: (-40, 120), 0x11: (0, 100), 0x05: (-40, 120), 0x5C: (-40, 210)}
LIVE_FAILURES = frozenset({"timeout", "stationary-gate", "uds-rejected", "response-invalid", "connection-or-transport", "recording-error"})


class DashboardLiveSource:
    """Paced request cadence, source-bound route, finite budget, halt on error."""
    max_duration = 300
    bounds = BOUNDS
    bounds_error_reason = "stationary-gate"

    def __init__(self, capture, *, timeout=2.0, duration=300, client_factory=HsfzClient,
                 connector_factory=socket.create_connection, monotonic=time.monotonic, wait=None):
        if not 0.1 <= float(timeout) <= 5.0:
            raise ValueError("timeout must be between 0.1 and 5 seconds")
        if not isinstance(duration, int) or isinstance(duration, bool) or not 1 <= duration <= self.max_duration:
            raise ValueError(f"duration must be between 1 and {self.max_duration} seconds")
        peer, interface, _target, _vin = load_gateway_capture(capture)
        def bound_connector(address, connect_timeout):
            return connector_factory(address, connect_timeout, source_address=(interface, 0))
        self.client = client_factory(peer, TESTER_ADDRESS, DME_TARGET_ADDRESS, port=6801,
                                     timeout=float(timeout), fail_on_pending=True,
                                     sock_factory=bound_connector)
        self.signals = list(SIGNALS)
        self.timeout, self.duration = float(timeout), duration
        self._max_attempts = 5 * duration
        self._monotonic, self._wait = monotonic, wait or time.sleep
        self._custom_wait = wait is not None
        self._stop = threading.Event()
        self._deadline = monotonic() + duration
        self._started = 0
        self._tick = 0
        self._next_slot_at = self._deadline - duration
        self._last_started = None
        self._request_starts = deque()
        self._gate = threading.Lock()
        self._close_gate = threading.Lock()
        self._closed = False
        self.halted = False
        self.halt_reason = None
        self.connected = False

    def close(self):
        self._stop.set()
        # HsfzClient.close is designed to interrupt an in-flight receive and
        # must not wait on the request serialization gate held by read().
        with self._close_gate:
            if not self._closed:
                self.client.close()
                self._closed = True
        self.connected = False

    def stop(self):
        self.close()

    def read(self):
        if self.halted:
            return []
        if self._started >= self._max_attempts or self._monotonic() >= self._deadline:
            return []
        while True:
            now = self._monotonic()
            if now >= self._deadline or self._stop.is_set():
                return []
            # Drop scheduler slots missed while the prior ECU request was in
            # flight; never replay overdue requests in a catch-up burst.
            while self._next_slot_at < now - 1e-9:
                self._tick += 1
                self._next_slot_at += TICK_SECONDS
            slot_at = max(self._next_slot_at,
                          self._last_started + TICK_SECONDS if self._last_started is not None
                          else self._next_slot_at)
            delay = slot_at - now
            if delay > 0:
                self._wait(delay)
                if self._stop.is_set():
                    return []
            pid = SCHEDULE[self._tick % len(SCHEDULE)]
            self._tick += 1
            self._next_slot_at += TICK_SECONDS
            if pid is not None:
                break
        try:
            with self._gate:
                while True:
                    if self._stop.is_set() or self._started >= self._max_attempts:
                        return []
                    now = self._monotonic()
                    if now >= self._deadline:
                        return []
                    while self._request_starts and now - self._request_starts[0] >= 1.0:
                        self._request_starts.popleft()
                    if len(self._request_starts) < 5:
                        break
                    wait_for = min(self._request_starts[0] + 1.0 - now,
                                   self._deadline - now)
                    if wait_for <= 0:
                        return []
                    if self._custom_wait:
                        self._wait(wait_for)
                    elif self._stop.wait(wait_for):
                        return []
                if self._stop.is_set() or self._started >= self._max_attempts:
                    return []
                self._last_started = self._monotonic()
                if self._last_started >= self._deadline:
                    return []
                self._request_starts.append(self._last_started)
                self._started += 1
                response = self.client.request(bytes((0x01, pid)))
            if isinstance(response, bytes) and response[:1] == b"\x7f":
                raise ConnectionError("negative response")
            value = (parse_temperature_response(response, pid) if pid in (0x05, 0x5C)
                     else parse_value_response(response, pid)[0])
            low, high = self.bounds[pid]
            if not low <= value <= high:
                raise ValueError(self.bounds_error_reason)
            self.connected = bool(getattr(self.client, "connected", False))
            signal = BY_PID[pid]
            return [Sample(signal.id, value, signal.unit, "hsfz", "measured", "good",
                           utc_now(), time.monotonic_ns())]
        except Exception as exc:
            if self._stop.is_set():
                # A normal bounded-session shutdown closes the client to
                # interrupt an in-flight receive. Treat that cancellation as
                # end-of-stream; errors observed before shutdown still halt.
                self.connected = False
                return []
            self.halted = True
            message = str(exc)
            self.halt_reason = ("stationary-gate" if message == "stationary-gate" else
                                "timeout" if isinstance(exc, TimeoutError) else
                                "uds-rejected" if isinstance(exc, ConnectionError) else
                                "response-invalid" if isinstance(exc, ValueError) else
                                "connection-or-transport")
            try:
                self.close()
            except Exception:
                pass
            self.connected = False
            signal = BY_PID[pid]
            return [Sample(signal.id, None, signal.unit, "hsfz", "measured", "error",
                           utc_now(), time.monotonic_ns(), self.halt_reason)]


class MovingDashboardLiveSource(DashboardLiveSource):
    """Finite drive-session source with standardized decoded moving ranges."""
    max_duration = 1800
    bounds = {**BOUNDS, 0x0C: (0, 16383.75), 0x0D: (0, 255)}
    bounds_error_reason = "response-invalid"


class DashboardSimSource:
    """Predictable client-demo values with no connection or storage side effects."""
    def __init__(self, *, monotonic=time.monotonic):
        self._clock, self._start = monotonic, monotonic()
        self.signals = list(SIGNALS)
        self.halted = False
        self._tick = 0

    def read(self):
        t = self._clock() - self._start
        values = {
            "engine_rpm": 850 + int(140 * (1 + math.sin(t * 0.65))),
            "vehicle_speed": 0,
            "intake_air_temperature": round(27 + 2 * math.sin(t * 0.15), 1),
            "throttle_position": round(13 + 1.2 * math.sin(t * 0.4), 1),
            "coolant_temp": 91,
            "engine_oil_temp": 96,
        }
        now = time.monotonic_ns()
        selected = self.signals if self._tick == 0 else [self.signals[0]] if self._tick % 5 else self.signals[1:]
        self._tick += 1
        return [Sample(s.id, values[s.id], s.unit, "simulated", "measured", "simulated",
                       utc_now(), now) for s in selected]


SIMULATED_DTCS = {"stored": ["P0420"], "pending": [], "permanent": ["P0420"]}


def safe_dtc_snapshot(result=None, error=None):
    """Normalize only decoder-vetted DTC values and allowlisted failure labels."""
    if error is not None:
        completed = getattr(error, "completed_reads", {}) or {}
        reason = getattr(error, "reason", "unexpected-error")
        if reason not in DTC_FAILURE_REASONS:
            reason = "unexpected-error"
        subtype = getattr(error, "rejection_subtype", None)
        if subtype not in REJECTION_SUBTYPES:
            subtype = None
        return {"stored": completed.get("stored"), "pending": completed.get("pending"),
                "permanent": completed.get("permanent"),
                "permanent_reason": (subtype or reason)
                if getattr(error, "failed_read", None) == "permanent" else None,
                "status": "partial" if completed else "unavailable"}
    return {"stored": result["stored_dtcs"], "pending": result["pending_dtcs"],
            "permanent": result["permanent_dtcs"], "permanent_reason": None, "status": "complete"}


STATIC_ROOT = Path(__file__).with_name("dashboard_static")
HTML = (STATIC_ROOT / "index.html").read_text(encoding="utf-8")


def make_dashboard_handler(engine, source, mode, dtcs):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            request_path = urlsplit(self.path).path
            if request_path == "/":
                data, content = HTML.encode(), "text/html; charset=utf-8"
                cache = "no-cache"
            elif request_path == "/api/state":
                data = json.dumps(dashboard_state(engine, source, mode, dtcs)).encode()
                content, cache = "application/json", "no-store"
            elif request_path.startswith("/assets/"):
                filename = unquote(request_path.removeprefix("/assets/"))
                if (not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", filename)
                        or filename in {".", ".."}):
                    self.send_error(404); return
                assets_root = (STATIC_ROOT / "assets").resolve()
                try:
                    asset = (assets_root / filename).resolve(strict=True)
                    asset.relative_to(assets_root)
                    if not asset.is_file():
                        raise FileNotFoundError
                    data = asset.read_bytes()
                except (OSError, ValueError):
                    self.send_error(404); return
                content = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
                if content == "text/javascript":
                    content = "text/javascript; charset=utf-8"
                elif content.startswith("text/"):
                    content += "; charset=utf-8"
                cache = "public, max-age=31536000, immutable"
            else:
                self.send_error(404); return
            self.send_response(200); self.send_header("Content-Type", content); self.send_header("Cache-Control", cache); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        def log_message(self, *_): pass
    return Handler


def serve_client_dashboard(source, *, mode, dtcs, host="127.0.0.1", port=8765,
                           duration=300, worker_factory=threading.Thread, server=None,
                           stop_on_halt=False, max_duration=300):
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("dashboard must bind to loopback")
    if mode not in ("simulated", "live"):
        raise ValueError("mode must be simulated or live")
    if not 1 <= duration <= max_duration:
        raise ValueError(f"duration must be between 1 and {max_duration} seconds")
    from .engine import AcquisitionEngine
    server = server
    timer = worker = None
    engine = None
    stop = threading.Event()
    try:
        engine = AcquisitionEngine(source=source, interval=0.1 if mode == "live" else 0.2)
        Handler = make_dashboard_handler(engine, source, mode, dtcs)
        if server is None:
            server = ThreadingHTTPServer((host, port), Handler)
        else:
            server.RequestHandlerClass = Handler
        def run_engine():
            engine.run(stop)
            if stop_on_halt and engine.halted and server is not None:
                server.shutdown()
        worker = worker_factory(target=run_engine, daemon=True)
        worker.start()
        print(f"{mode.title()} client dashboard: http://{host}:{server.server_port}/", flush=True)
        timer = threading.Timer(duration, server.shutdown); timer.daemon = True; timer.start()
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if timer is not None: timer.cancel()
        stop.set()
        if hasattr(source, "close"):
            try: source.close()
            except Exception: pass
        if worker is not None and getattr(worker, "ident", None) is not None:
            worker.join(timeout=max(2.0, getattr(source, "timeout", 0) + 1))
        if server is not None: server.server_close()
    return 1 if engine is not None and engine.halted else 0


def reserve_dashboard_server(host="127.0.0.1", port=8765):
    """Bind loopback before any live vehicle I/O; expose only a fixed error."""
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("dashboard-bind-failed")
    try:
        class ReservedServer(ThreadingHTTPServer):
            allow_reuse_address = False
        return ReservedServer((host, port), BaseHTTPRequestHandler)
    except Exception:
        raise RuntimeError("dashboard-bind-failed") from None


def wait_after_dtc_snapshot(wait=time.sleep):
    """Keep a conservative quiet interval between the DTC and sensor sources."""
    wait(1.0)


def run_live_dtc_snapshot(capture, timeout=2.0, *, monotonic=time.monotonic, wait=time.sleep,
                          client_factory=None):
    """Exactly one existing three-service DTC snapshot, preserving safe partials."""
    try:
        kwargs = {"monotonic": monotonic, "wait": wait, "min_request_interval": 1.0}
        if client_factory is not None:
            kwargs["client_factory"] = client_factory
        return safe_dtc_snapshot(read_emissions_dtcs(capture, timeout, **kwargs))
    except EmissionsDtcError as exc:
        return safe_dtc_snapshot(error=exc)
    except Exception:
        return {"stored": None, "pending": None, "permanent": None,
                "permanent_reason": "unexpected-error", "status": "unavailable"}


def dashboard_state(engine, source, mode, dtcs):
    """Build the deliberately small, privacy-safe API response shape."""
    now = time.monotonic_ns()
    for _ in range(3):
        try:
            latest = tuple(engine.latest.values())
            break
        except RuntimeError:
            continue
    else:
        latest = ()
    samples = [{**vars(sample), "age_ms": max(0, (now - sample.monotonic_ns) // 1_000_000)}
               for sample in latest]
    reason = "recording-error" if engine.recording_error else getattr(source, "halt_reason", None)
    if reason not in LIVE_FAILURES:
        reason = "unexpected-error" if engine.halted or source.halted else None
    return {"mode": mode,
            "recording": bool(engine.store is not None and not engine.halted),
            "connection": "running" if mode == "simulated" else "connected" if source.connected else "waiting",
            "halted": engine.halted or source.halted,
            "acquisition_error": reason,
            "samples": samples,
            "dtcs": dtcs}
