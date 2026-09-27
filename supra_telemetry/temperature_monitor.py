"""Conservative live monitor for the two candidate SAE temperature PIDs."""
import socket
import threading
import time

from .dme_check import DME_TARGET_ADDRESS
from .gateway_check import TESTER_ADDRESS, load_gateway_capture
from .hsfz import HsfzClient
from .models import Sample, SignalDefinition, utc_now
from .temperature_values import parse_temperature_response

SIGNALS = (
    SignalDefinition("coolant_temp", "Coolant temperature", "°C", provenance="SAE Mode 01 PID 05",
                     confidence="verified", verification="verified", enabled=True),
    SignalDefinition("engine_oil_temp", "Engine oil temperature", "°C", provenance="SAE Mode 01 PID 5C",
                     confidence="verified", verification="verified", enabled=True),
)
INTERVAL_SECONDS = 2.0


class _MonitorStopRequested(Exception):
    """Internal signal that shutdown won the request-initiation gate."""


class TemperatureMonitorSource:
    """One fixed two-request cycle per read; stop permanently on first failure."""
    def __init__(self, capture, *, timeout=2.0, client_factory=HsfzClient,
                 connector_factory=socket.create_connection, monotonic=time.monotonic,
                 wait=None):
        if not 0.1 <= float(timeout) <= 5.0:
            raise ValueError("invalid monitor timeout")
        peer, interface, _gateway_target, _vin = load_gateway_capture(capture)

        def source_bound_connector(address, connect_timeout):
            return connector_factory(address, connect_timeout, source_address=(interface, 0))

        self.client = client_factory(peer, TESTER_ADDRESS, DME_TARGET_ADDRESS, port=6801,
                                     timeout=timeout, fail_on_pending=True,
                                     sock_factory=source_bound_connector)
        self.timeout = float(timeout)
        self._stop = threading.Event()
        self._request_gate = threading.Lock()
        self._monotonic = monotonic
        self._wait = wait or self._stop.wait
        self._last_cycle_completed = None
        self.halted = False
        self.halt_reason = None
        self.connected = False
        self.signals = list(SIGNALS)

    def close(self):
        self._stop.set()
        self.client.close()
        self.connected = False

    def stop(self):
        """Block new request authorization and wait for any authorized request."""
        self._stop.set()
        with self._request_gate:
            pass

    def _request(self, payload):
        with self._request_gate:
            if self._stop.is_set():
                raise _MonitorStopRequested
            return self.client.request(payload)

    @staticmethod
    def _failure_category(exc):
        if isinstance(exc, TimeoutError):
            return "timeout"
        if isinstance(exc, ValueError):
            return "response-invalid"
        if isinstance(exc, ConnectionError):
            return "uds-rejected"
        return "connection-or-transport"

    def _sample(self, signal, value=None, quality="good", error=None):
        return Sample(signal.id, value, signal.unit, "hsfz", "measured", quality,
                      utc_now(), time.monotonic_ns(), error)

    def read(self):
        if self.halted:
            return [self._sample(signal, quality="halted", error=self.halt_reason)
                    for signal in self.signals]
        if self._last_cycle_completed is not None:
            remaining = INTERVAL_SECONDS - (self._monotonic() - self._last_cycle_completed)
            if remaining > 0:
                self._wait(remaining)
            if self._stop.is_set():
                return [self._sample(signal, quality="halted", error="stopped")
                        for signal in self.signals]
        output = []
        for index, (signal, pid) in enumerate(zip(self.signals, (0x05, 0x5C))):
            if self._stop.is_set():
                output.extend(self._sample(remaining, quality="halted", error="stopped")
                              for remaining in self.signals[index:])
                break
            try:
                response = self._request(bytes((0x01, pid)))
                value = parse_temperature_response(response, pid)
                output.append(self._sample(signal, value))
            except _MonitorStopRequested:
                output.extend(self._sample(remaining, quality="halted", error="stopped")
                              for remaining in self.signals[index:])
                break
            except Exception as exc:
                self.halted = True
                self.halt_reason = self._failure_category(exc)
                output.append(self._sample(signal, quality="error", error=self.halt_reason))
                for remaining in self.signals[index + 1:]:
                    output.append(self._sample(remaining, quality="halted", error=self.halt_reason))
                self.close()
                break
        self.connected = not self.halted and getattr(self.client, "connected", False)
        self._last_cycle_completed = self._monotonic()
        return output


def run_monitor(source, *, store=None, duration=300, host="127.0.0.1", port=8765,
                worker_join_timeout=7.0, thread_factory=threading.Thread):
    """Serve a local dashboard for a bounded run and close all resources on expiry."""
    from .engine import AcquisitionEngine
    from .web import serve

    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("dashboard must bind to loopback")
    if not 1 <= duration <= 300:
        raise ValueError("duration must be between 1 and 300 seconds")
    session = None
    server = None
    worker = None
    worker_started = False
    server_worker = None
    timer = None
    stopper = threading.Event()
    expired = threading.Event()
    engine = None
    worker_stuck = False
    source_closed = False

    def finish_session():
        if store and session is not None:
            store.end_session(session, utc_now())

    def stop_source():
        stop = getattr(source, "stop", None)
        if callable(stop):
            stop()
        else:
            close_source()

    def close_source():
        nonlocal source_closed
        if source_closed:
            return
        source.close()
        source_closed = True

    try:
        if store:
            session = store.start_session(utc_now(), mode="temperature-monitor")
            for signal in source.signals:
                store.register(session, signal)
        engine = AcquisitionEngine(source=source, store=store, session_id=session,
                                   interval=INTERVAL_SECONDS)
        server = serve(engine, host, port, bool(store), mode="temperature-monitor")

        def expire():
            try:
                stop_source()
            finally:
                expired.set()
                stopper.set()
                server.shutdown()

        def acquire():
            try:
                engine.run(stopper)
            except Exception:
                engine.halted = True
                engine.last_error = "monitor-stopped"
                source.close()
            finally:
                server.shutdown()

        worker = thread_factory(target=acquire, daemon=True)
        server_worker = thread_factory(target=server.serve_forever, daemon=True)
        timer = threading.Timer(duration, expire)
        timer.daemon = True
        server_worker.start()
        timer.start()  # Bound the request window before the acquisition worker can send.
        worker.start()
        worker_started = True
        print(f"Temperature monitor dashboard: http://{host}:{server.server_port}/", flush=True)
        while worker.is_alive():
            worker.join(timeout=0.1)
            if engine.halted or expired.is_set():
                break
    except KeyboardInterrupt:
        pass
    finally:
        if timer is not None:
            timer.cancel()
        stopper.set()
        stop_source()
        if server is not None and server_worker is not None and server_worker.is_alive():
            server.shutdown()
        if worker is not None and worker_started:
            graceful_timeout = max(worker_join_timeout, float(getattr(source, "timeout", 0)) + 1.0)
            worker.join(timeout=graceful_timeout)
            if worker.is_alive():
                close_source()
                worker.join(timeout=1.0)
            worker_stuck = worker.is_alive()
            if not worker_stuck:
                close_source()
        else:
            close_source()
        if server_worker is not None:
            server_worker.join(timeout=2.0)
        if server is not None:
            server.server_close()
        if store and not worker_stuck:
            # AcquisitionEngine finalizes its session after a started worker.
            if not worker_started:
                try: finish_session()
                finally: store.close()
            else:
                store.close()
    if worker_stuck:
        raise RuntimeError("temperature monitor worker did not stop; database left open")
    return 1 if engine is not None and engine.halted else 0
