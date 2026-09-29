import contextlib
import io
import json
import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from supra_telemetry.client_dashboard import MovingDashboardLiveSource, DashboardLiveSource
from supra_telemetry.drive_session import run_drive_session
from supra_telemetry.models import Sample
from supra_telemetry.engine import AcquisitionEngine
from supra_telemetry.client_dashboard import dashboard_state


def make_capture(directory):
    path = Path(directory) / "capture.json"
    vin, mac = "TESTVIN0000000001", "001122334455"
    body = b"DIAGADR10BMWMAC" + mac.encode() + b"BMWVIN" + vin.encode()
    packet = len(body).to_bytes(4, "big") + b"\x00\x11" + body
    path.write_text(json.dumps({"interface": "169.254.10.30", "hsfz": [{
        "peer": "169.254.10.20", "port": 6811,
        "identification": {"vin": vin, "mac": mac, "diagnostic_address": 16},
        "raw_hex": packet.hex()}]}), encoding="utf-8")
    return path


class DriveSessionTests(unittest.TestCase):
    def test_stationary_speed_gate_and_moving_policy_are_distinct(self):
        self.assertEqual(DashboardLiveSource.bounds[0x0D], (0, 0))
        self.assertEqual(MovingDashboardLiveSource.bounds[0x0D], (0, 255))
        self.assertEqual(MovingDashboardLiveSource.bounds[0x0C], (0, 16383.75))
        with tempfile.TemporaryDirectory() as td:
            clock = [0.0]
            class Client:
                connected = True
                def request(self, payload):
                    pid = payload[1]
                    values = {0x0C: b"\x0d\x48", 0x0D: b"\x2a", 0x0F: b"\x46", 0x11: b"\x20"}
                    return (b"\x41" + bytes((pid,)) + (bytes((130,)) if pid in (5, 0x5c) else values[pid]))
                def close(self): pass
            def factory(*_args, **kwargs):
                kwargs["sock_factory"](("ignored", 6801), kwargs["timeout"])
                return Client()
            source = MovingDashboardLiveSource(make_capture(td), duration=1,
                monotonic=lambda: clock[0], wait=lambda delay: clock.__setitem__(0, clock[0] + delay),
                client_factory=factory, connector_factory=lambda *a, **k: object())
            for _ in range(3):
                samples = source.read()
                if samples and samples[0].signal_id == "vehicle_speed":
                    self.assertEqual(samples[0].value, 42)
                    break
            else:
                self.fail("moving source did not accept decoded nonzero speed")
            source.close()

    def test_moving_duration_cap_and_cli_confirmation(self):
        with self.assertRaises(ValueError):
            MovingDashboardLiveSource("unused", duration=1801)
        from supra_telemetry.__main__ import main
        with self.assertRaises(SystemExit):
            main(["drive-session", "--capture", "c", "--db", "x"])
        with self.assertRaises(SystemExit):
            main(["drive-session", "--capture", "c", "--db", "x",
                  "--confirm-hands-off", "--duration", "1801"])

    def test_preflight_order_decoded_only_persistence_and_privacy_safe_summary(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "session.sqlite"
            events = []
            read_event = threading.Event()
            class Source:
                signals = []
                halted = False
                connected = True
                _started = 1
                def __init__(self, *_a, **_kw): events.append("source")
                def read(self):
                    read_event.set()
                    return [Sample("engine_rpm", 850, "rpm", "hsfz", "measured", "good", "2026-01-01T00:00:00Z", 1)]
                def close(self): pass
            class Server:
                server_port = 8765
                RequestHandlerClass = None
                def serve_forever(self): read_event.wait(1)
                def shutdown(self): pass
                def server_close(self): pass
            def server_factory(*_a): events.append("bind"); return Server()
            def store_factory(path): events.append("store"); from supra_telemetry.storage import TelemetryStore; return TelemetryStore(path)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = run_drive_session("capture", db, duration=1, source_factory=Source,
                                         store_factory=store_factory, server_factory=server_factory)
            self.assertEqual(code, 0)
            self.assertEqual(events, ["bind", "store", "source"])
            summary = json.loads(output.getvalue().splitlines()[-1])
            self.assertEqual(summary["result"], "completed")
            self.assertEqual(summary["signals"]["engine_rpm"]["samples"], 1)
            self.assertNotIn("value", json.dumps(summary))
            dbx = sqlite3.connect(db)
            self.assertEqual(dbx.execute("SELECT COUNT(*) FROM raw_exchanges").fetchone()[0], 0)
            signal_rows = dbx.execute("SELECT * FROM signals").fetchall()
            self.assertEqual(len(signal_rows), 6)
            for row in signal_rows:
                self.assertTrue(all(value is None for value in row[8:14]),
                                "signal metadata must contain no rates, service, request, route or decoder offset")
                self.assertNotIn("PID", str(row).upper())
                for token in ("01 0C", "01 0D", "01 0F", "01 11", "01 05", "01 5C"):
                    self.assertNotIn(token, str(row).upper())
            dbx.close()
            database_bytes = db.read_bytes()
            for identifier in (b"TESTVIN0000000001", b"001122334455", b"169.254.10.30",
                               b"169.254.10.20", b"DIAGADR10", b"BMWMAC", b"BMWVIN"):
                self.assertNotIn(identifier, database_bytes)
            self.assertNotIn(b"PID", database_bytes)
            dbx = sqlite3.connect(db)
            self.assertEqual(dbx.execute("SELECT mode FROM sessions").fetchone()[0], "drive-session")
            dbx.close()

    def test_drive_source_issues_only_the_fixed_mode01_pid_schedule(self):
        from supra_telemetry.client_dashboard import SCHEDULE
        with tempfile.TemporaryDirectory() as td:
            requests = []
            class Client:
                connected = True
                def request(self, payload):
                    requests.append(payload)
                    pid = payload[1]
                    values = {0x0c: b"\x0d\x48", 0x0d: b"\x00", 0x0f: b"\x46", 0x11: b"\x20"}
                    return b"\x41" + bytes((pid,)) + (bytes((130,)) if pid in (5, 0x5c) else values[pid])
                def close(self): pass
            def factory(*_args, **kwargs):
                kwargs["sock_factory"](("ignored", 6801), kwargs["timeout"])
                return Client()
            clock = [0.0]
            source = MovingDashboardLiveSource(make_capture(td), duration=4,
                monotonic=lambda: clock[0], wait=lambda delta: clock.__setitem__(0, clock[0]+delta),
                client_factory=factory, connector_factory=lambda *_a, **_kw: object())
            for _ in SCHEDULE:
                source.read()
            self.assertEqual([tuple(request) for request in requests],
                             [(1, pid) for pid in SCHEDULE if pid is not None] * 2)
            self.assertTrue(all(payload[0] == 1 and payload[1] in {0x0c, 0x0d, 0x0f, 0x11, 0x05, 0x5c}
                                for payload in requests))
            source.close()

    def test_normal_timer_interrupt_does_not_turn_inflight_read_into_failure(self):
        with tempfile.TemporaryDirectory() as td:
            capture_path = make_capture(td)
            db = Path(td) / "normal-stop.sqlite"
            request_started = threading.Event()
            sources = []
            class InterruptibleClient:
                connected = True
                def request(self, _payload):
                    request_started.set()
                    self.closed.wait(3)
                    raise OSError("socket closed by normal session shutdown")
                def close(self): self.closed.set()
                def __init__(self): self.closed = threading.Event()
            clients = []
            def source_factory(path, *, timeout, duration, monotonic):
                client = InterruptibleClient()
                clients.append(client)
                source = MovingDashboardLiveSource(path, timeout=timeout, duration=duration,
                    monotonic=monotonic, client_factory=lambda *_a, **_kw: client,
                    connector_factory=lambda *_a, **_kw: object())
                sources.append(source)
                return source
            from supra_telemetry.client_dashboard import reserve_dashboard_server
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                result = run_drive_session(capture_path, db, duration=1, timeout=1,
                    port=0, source_factory=source_factory,
                    server_factory=lambda host, _port: reserve_dashboard_server(host, 0))
            self.assertTrue(request_started.is_set(), "the session timer must expire during a live request")
            self.assertTrue(clients[0].closed.is_set(), "normal cleanup must promptly close the blocked client")
            self.assertEqual(result, 0)
            self.assertFalse(sources[0].halted)
            self.assertEqual(json.loads(out.getvalue().splitlines()[-1])["result"], "completed")
            connection = sqlite3.connect(db)
            try:
                self.assertEqual(connection.execute("SELECT COUNT(*) FROM samples WHERE quality='error'").fetchone()[0], 0)
                session = connection.execute("SELECT ended_utc FROM sessions").fetchone()
                self.assertIsNotNone(session[0], "normal completion must finalize the session")
            finally:
                connection.close()

    def test_first_source_error_is_closed_and_server_exits_nonzero(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "session.sqlite"
            closed = []
            class Source:
                signals = []
                halted = False
                connected = True
                halt_reason = "response-invalid"
                _started = 1
                def __init__(self, *_a, **_kw): pass
                def read(self): self.halted = True; return [Sample("engine_rpm", None, "rpm", "hsfz", "measured", "error", "2026-01-01T00:00:00Z", 1, "response-invalid")]
                def close(self): closed.append(True)
            class Server:
                server_port = 8765
                RequestHandlerClass = None
                def __init__(self): self.done = threading.Event()
                def serve_forever(self): self.done.wait(2)
                def shutdown(self): self.done.set()
                def server_close(self): pass
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = run_drive_session("capture", db, duration=20, source_factory=Source,
                    server_factory=lambda *_a: Server())
            self.assertEqual(code, 1)
            self.assertTrue(closed)
            self.assertEqual(json.loads(out.getvalue().splitlines()[-1])["reason"], "response-invalid")

    def test_recording_failure_stops_source_and_dashboard(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "session.sqlite"
            closed = []
            class Source:
                signals = []
                halted = False
                connected = True
                _started = 1
                def __init__(self, *_a, **_kw): pass
                def read(self): return [Sample("engine_rpm", 850, "rpm", "hsfz", "measured", "good", "2026-01-01T00:00:00Z", 1)]
                def close(self): closed.append(True)
            from supra_telemetry.storage import TelemetryStore
            class BrokenStore(TelemetryStore):
                def add_sample(self, *_a): raise OSError("private path must not leak")
            class Server:
                server_port = 8765
                RequestHandlerClass = None
                def __init__(self): self.done = threading.Event()
                def serve_forever(self): self.done.wait(2)
                def shutdown(self): self.done.set()
                def server_close(self): pass
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = run_drive_session("capture", db, duration=20, source_factory=Source,
                    store_factory=BrokenStore, server_factory=lambda *_a: Server())
            self.assertEqual(code, 1)
            self.assertTrue(closed)
            summary = json.loads(out.getvalue().splitlines()[-1])
            self.assertEqual(summary["reason"], "recording-error")
            self.assertNotIn("private path", out.getvalue())

    def test_source_setup_failure_removes_only_its_new_database(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "new.sqlite"
            class Server:
                server_port = 8765
                def server_close(self): pass
            def fail_source(*_a, **_kw):
                self.assertTrue(db.exists())
                raise RuntimeError("capture detail must not leak")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(run_drive_session("capture", db, source_factory=fail_source,
                    server_factory=lambda *_a: Server()), 1)
            self.assertFalse(db.exists())
            self.assertNotIn("capture detail", out.getvalue())

            db.write_text("existing user file", encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(run_drive_session("capture", db,
                    server_factory=lambda *_a: self.fail("must not bind for existing DB")), 1)
            self.assertEqual(db.read_text(encoding="utf-8"), "existing user file")

    def test_summary_duration_starts_after_setup(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "timed.sqlite"
            clock = [0.0]
            read_event = threading.Event()
            class Source:
                signals = []
                halted = False
                connected = True
                _started = 0
                def __init__(self, *_a, **_kw): clock[0] += 10
                def read(self): read_event.set(); return []
                def close(self): pass
            class Server:
                server_port = 8765
                RequestHandlerClass = None
                def serve_forever(self):
                    read_event.wait(1)
                    clock[0] += 3
                def shutdown(self): pass
                def server_close(self): pass
            def bind(*_a): clock[0] += 10; return Server()
            def make_store(path):
                clock[0] += 10
                from supra_telemetry.storage import TelemetryStore
                return TelemetryStore(path)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = run_drive_session("capture", db, duration=20, source_factory=Source,
                    store_factory=make_store, server_factory=bind, monotonic=lambda: clock[0])
            self.assertEqual(code, 0)
            summary = json.loads(out.getvalue().splitlines()[-1])
            self.assertEqual(summary["duration_seconds"], 3.0)

    def test_live_worker_after_join_timeout_keeps_store_open_and_unqueried(self):
        with tempfile.TemporaryDirectory() as td:
            db = Path(td) / "busy.sqlite"
            entered, release, worker_finalized = threading.Event(), threading.Event(), threading.Event()
            stores = []
            class Source:
                signals = []
                halted = False
                connected = True
                _started = 0
                def __init__(self, *_a, **_kw): pass
                def read(self): entered.set(); release.wait(10); return []
                def close(self): pass
            from supra_telemetry.storage import TelemetryStore
            class TrackedStore(TelemetryStore):
                def __init__(self, path): super().__init__(path); self.closed_by_runner = False; stores.append(self)
                def end_session(self, *args):
                    super().end_session(*args)
                    worker_finalized.set()
                def close(self): self.closed_by_runner = True; super().close()
            class Server:
                server_port = 8765
                RequestHandlerClass = None
                def serve_forever(self): entered.wait(1)
                def shutdown(self): pass
                def server_close(self): pass
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = run_drive_session("capture", db, timeout=0.1, duration=20,
                    source_factory=Source, store_factory=TrackedStore,
                    server_factory=lambda *_a: Server())
            self.assertEqual(code, 1)
            self.assertEqual(len(stores), 1)
            self.assertFalse(stores[0].closed_by_runner)
            self.assertFalse(worker_finalized.is_set())
            summary = json.loads(out.getvalue().splitlines()[-1])
            self.assertEqual(summary["reason"], "dashboard-error")
            self.assertTrue(all(item["samples"] is None and item["achieved_hz"] is None
                                for item in summary["signals"].values()))
            release.set()
            self.assertTrue(worker_finalized.wait(2))
            stores[0].close()

    def test_dashboard_state_reports_allowlisted_recording_error(self):
        class Source:
            halted = True
            connected = False
            halt_reason = "private details 10.0.0.1"
            def read(self): return []
        engine = AcquisitionEngine(source=Source())
        engine.recording_error = "private database path"
        state = dashboard_state(engine, engine.source, "live", {})
        self.assertEqual(state["acquisition_error"], "recording-error")
        self.assertNotIn("private", json.dumps(state))


if __name__ == "__main__":
    unittest.main()
