import json
import struct
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from supra_telemetry.dme_check import DME_TARGET_ADDRESS
from supra_telemetry.engine import AcquisitionEngine
from supra_telemetry.storage import TelemetryStore
from supra_telemetry.temperature_monitor import (
    INTERVAL_SECONDS, TemperatureMonitorSource, run_monitor,
)


def capture_file(path):
    vin, mac = "TESTVIN0000000001", "001122334455"
    body = b"DIAGADR10BMWMAC" + mac.encode() + b"BMWVIN" + vin.encode()
    packet = struct.pack(">IH", len(body), 0x11) + body
    record = {"peer": "169.254.10.20", "port": 6811,
              "identification": {"vin": vin, "mac": mac, "diagnostic_address": 0x10},
              "raw_hex": packet.hex()}
    path.write_text(json.dumps({"interface": "169.254.10.30", "hsfz": [record]}), encoding="utf-8")


class TemperatureMonitorTests(unittest.TestCase):
    def test_fixed_requests_repeat_in_order_and_bind_captured_source(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.json"
            capture_file(path)
            calls, configs = [], []

            class Client:
                connected = True
                def __init__(self, *args, **kwargs):
                    configs.append((args, kwargs))
                    kwargs["sock_factory"]((args[0], kwargs["port"]), kwargs["timeout"])
                def request(self, payload):
                    calls.append(payload)
                    return b"\x41" + payload[1:] + bytes((80 if payload[1] == 5 else 100,))
                def close(self): pass

            def connector(address, timeout, *, source_address):
                configs.append(((address, timeout), {"source_address": source_address}))
                return object()

            source = TemperatureMonitorSource(path, client_factory=Client, connector_factory=connector)
            for _ in range(3):
                samples = source.read()
                self.assertEqual([s.value for s in samples], [40, 60])
            self.assertEqual(calls, [b"\x01\x05", b"\x01\x5c"] * 3)
            (address, timeout), connector_kwargs = configs[-1]
            self.assertEqual((address, timeout), (("169.254.10.20", 6801), 2.0))
            self.assertEqual(connector_kwargs["source_address"], ("169.254.10.30", 0))
            client_args, client_kwargs = configs[0]
            self.assertEqual(client_args[:3], ("169.254.10.20", 0xF4, DME_TARGET_ADDRESS))
            self.assertEqual(client_kwargs["port"], 6801)
            self.assertTrue(client_kwargs["fail_on_pending"])

    def test_first_failure_halts_without_retry_or_second_pid(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.json"
            capture_file(path)
            calls, closed = [], []

            class Client:
                connected = True
                def request(self, payload):
                    calls.append(payload)
                    raise TimeoutError("private peer detail")
                def close(self): closed.append(True)

            source = TemperatureMonitorSource(path, client_factory=lambda *_a, **_k: Client())
            samples = source.read()
            self.assertEqual(calls, [b"\x01\x05"])
            self.assertEqual([s.quality for s in samples], ["error", "halted"])
            self.assertEqual([s.error for s in samples], ["timeout", "timeout"])
            source.read()
            self.assertEqual(calls, [b"\x01\x05"])
            self.assertTrue(closed)

    def test_pending_is_failure_and_raw_exchanges_are_never_persisted(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.json"
            capture_file(path)

            class Client:
                connected = True
                def request(self, payload): raise ConnectionError("pending UDS response is not accepted")
                def close(self): pass

            source = TemperatureMonitorSource(path, client_factory=lambda *_a, **_k: Client())
            samples = source.read()
            self.assertEqual(samples[0].error, "uds-rejected")
            dbpath = Path(td) / "samples.sqlite"
            store = TelemetryStore(dbpath)
            session = store.start_session("now", mode="monitor")
            for signal in source.signals: store.register(session, signal)
            for sample in samples: store.add_sample(session, sample)
            raw_count = store.db.execute("SELECT count(*) FROM raw_exchanges").fetchone()[0]
            signal_metadata = store.db.execute("SELECT service, request, target_address FROM signals").fetchall()
            store.close()
            self.assertEqual(raw_count, 0)
            self.assertEqual(signal_metadata, [(None, None, None), (None, None, None)])
            db_text = dbpath.read_bytes()
            for private in (b"TESTVIN0000000001", b"001122334455", b"169.254.10.20", b"169.254.10.30"):
                self.assertNotIn(private, db_text)

    def test_cli_propagates_halted_monitor_failure(self):
        from supra_telemetry import __main__ as cli
        source = object()
        with patch.object(cli, "TemperatureMonitorSource", return_value=source), \
                patch.object(cli, "run_monitor", return_value=1):
            self.assertEqual(cli.main(["monitor-temperatures", "--capture", "private.json"]), 1)

    def test_interval_and_cli_bounds(self):
        self.assertEqual(INTERVAL_SECONDS, 2.0)
        engine = AcquisitionEngine(interval=INTERVAL_SECONDS)
        self.assertEqual(engine.interval, 2.0)
        from supra_telemetry import __main__ as cli
        with self.assertRaises(SystemExit): cli.main(["monitor-temperatures", "--capture", "x", "--duration", "301"])
        with self.assertRaises(SystemExit): cli.main(["monitor-temperatures", "--capture", "x", "--ui-host", "0.0.0.0"])

    def test_two_second_idle_gap_after_completed_cycles(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.json"
            capture_file(path)
            clock = [0.0]
            waits = []

            class Client:
                connected = True
                def request(self, payload):
                    clock[0] += 0.3
                    return b"\x41" + payload[1:] + b"\x50"
                def close(self): pass

            def wait(seconds):
                waits.append(seconds)
                clock[0] += seconds

            source = TemperatureMonitorSource(path, client_factory=lambda *_a, **_k: Client(),
                                              monotonic=lambda: clock[0], wait=wait)
            source.read()
            first_finished = clock[0]
            source.read()
            self.assertEqual(waits, [2.0])
            self.assertGreaterEqual(clock[0] - first_finished, 2.59)

    def test_setup_failure_closes_source_store_and_finalizes_session(self):
        from supra_telemetry.models import SignalDefinition

        class Source:
            signals = [SignalDefinition("x", "X")]
            def __init__(self): self.closed = 0
            def close(self): self.closed += 1

        source = Source()
        with tempfile.TemporaryDirectory() as td:
            dbpath = Path(td) / "setup.sqlite"
            store = TelemetryStore(dbpath)
            with patch("supra_telemetry.web.serve", side_effect=OSError("bind failed")):
                with self.assertRaisesRegex(OSError, "bind failed"):
                    run_monitor(source, store=store, duration=1, port=0)
            self.assertEqual(source.closed, 1)
            with self.assertRaises(Exception): store.db.execute("SELECT 1")
            import sqlite3
            db = sqlite3.connect(dbpath)
            try: self.assertIsNotNone(db.execute("SELECT ended_utc FROM sessions").fetchone()[0])
            finally: db.close()

    def test_early_halt_stops_dashboard_and_returns_failure(self):
        class Source:
            signals = []
            halted = False
            def read(self): self.halted = True; return []
            def close(self): pass

        with patch("builtins.print"):
            result = run_monitor(Source(), duration=30, port=0)
        self.assertEqual(result, 1)

    def test_expiry_during_request_that_returns_stops_before_second_pid(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.json"
            capture_file(path)
            released = threading.Event()
            calls = []

            class Client:
                connected = True
                def request(self, payload):
                    calls.append(payload)
                    released.wait(2)
                    return b"\x41" + payload[1:] + b"\x50"
                def close(self): pass

            source = TemperatureMonitorSource(path, client_factory=lambda *_a, **_k: Client())
            release_timer = threading.Timer(1.1, released.set)
            release_timer.start()
            with patch("builtins.print"):
                result = run_monitor(source, duration=1, port=0)
            release_timer.join()
            self.assertEqual(result, 0)
            self.assertFalse(source.halted)
            self.assertEqual(calls, [b"\x01\x05"])

    def test_expiry_sets_source_stop_before_releasing_first_request(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.json"
            capture_file(path)
            request_started = threading.Event()
            calls = []

            class Client:
                connected = True
                stop_event = None
                def request(self, payload):
                    calls.append(payload)
                    request_started.set()
                    self.stop_event.wait(2)
                    return b"\x41" + payload[1:] + b"\x50"
                def close(self): pass

            client = Client()
            source = TemperatureMonitorSource(path, client_factory=lambda *_a, **_k: client)
            client.stop_event = source._stop

            class Server:
                server_port = 12345
                def __init__(self): self.stopped = threading.Event()
                def serve_forever(self): self.stopped.wait()
                def shutdown(self):
                    self.stopped.set()
                def server_close(self): pass

            server = Server()
            with patch("supra_telemetry.web.serve", return_value=server), patch("builtins.print"):
                result = run_monitor(source, duration=1, port=0)
            self.assertTrue(request_started.is_set())
            self.assertEqual(result, 0)
            self.assertFalse(source.halted)
            self.assertTrue(client.stop_event.is_set())
            self.assertEqual(calls, [b"\x01\x05"])

    def test_stop_intent_wins_second_request_gate(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.json"
            capture_file(path)
            calls, samples = [], []
            second_gate_waiting, admit_second_gate = threading.Event(), threading.Event()

            class Gate:
                def __init__(self): self.lock = threading.Lock(); self.count = 0; self.guard = threading.Lock()
                def __enter__(self):
                    with self.guard:
                        self.count += 1
                        is_second_request_gate = self.count == 2
                    if is_second_request_gate:
                        second_gate_waiting.set()
                        admit_second_gate.wait(1)
                    self.lock.acquire()
                    return self
                def __exit__(self, *_args): self.lock.release()

            class Client:
                connected = True
                def request(self, payload):
                    calls.append(payload)
                    return b"\x41" + payload[1:] + b"\x50"
                def close(self): pass

            source = TemperatureMonitorSource(path, client_factory=lambda *_a, **_k: Client())
            source._request_gate = Gate()
            reader = threading.Thread(target=lambda: samples.extend(source.read()))
            reader.start()
            self.assertTrue(second_gate_waiting.wait(1))
            stopper = threading.Thread(target=source.stop)
            stopper.start()
            self.assertTrue(source._stop.wait(1))
            stopper.join(1)
            self.assertFalse(stopper.is_alive())
            admit_second_gate.set()
            reader.join(1)
            self.assertFalse(reader.is_alive())
            self.assertEqual(calls, [b"\x01\x05"])
            self.assertEqual([sample.quality for sample in samples], ["good", "halted"])
            self.assertFalse(source.halted)

    def test_request_gate_winner_is_pre_stop_when_stop_arrives_in_flight(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.json"
            capture_file(path)
            second_started, release_second = threading.Event(), threading.Event()
            calls, samples = [], []
            source_ref = []

            class Client:
                connected = True
                def request(self, payload):
                    calls.append(payload)
                    if payload == b"\x01\x5c":
                        second_started.set()
                        release_second.wait(2)
                    return b"\x41" + payload[1:] + b"\x50"
                def close(self): pass

            source = TemperatureMonitorSource(path, client_factory=lambda *_a, **_k: Client())
            source_ref.append(source)
            reader = threading.Thread(target=lambda: samples.extend(source.read()))
            reader.start()
            self.assertTrue(second_started.wait(1))
            stopper = threading.Thread(target=source.stop)
            stopper.start()
            self.assertTrue(source._stop.wait(1))
            release_second.set()
            reader.join(1); stopper.join(1)
            self.assertFalse(reader.is_alive() or stopper.is_alive())
            self.assertEqual(calls, [b"\x01\x05", b"\x01\x5c"])
            self.assertEqual([sample.quality for sample in samples], ["good", "good"])
            self.assertFalse(source.halted)

    def test_expiry_during_request_exception_remains_failure(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "capture.json"
            capture_file(path)
            release = threading.Event()
            calls = []

            class Client:
                connected = True
                def request(self, payload):
                    calls.append(payload)
                    release.wait(2)
                    raise ConnectionError("independent transport failure")
                def close(self): pass

            source = TemperatureMonitorSource(path, client_factory=lambda *_a, **_k: Client())
            release_timer = threading.Timer(1.1, release.set)
            release_timer.start()
            with patch("builtins.print"):
                result = run_monitor(source, duration=1, port=0)
            release_timer.join()
            self.assertEqual(result, 1)
            self.assertTrue(source.halted)
            self.assertEqual(calls, [b"\x01\x05"])

    def test_worker_start_failure_still_cleans_source_store_and_server(self):
        from supra_telemetry.models import SignalDefinition

        class Source:
            signals = [SignalDefinition("x", "X")]
            def __init__(self): self.closed = 0
            def close(self): self.closed += 1

        source = Source()
        original_thread = threading.Thread
        created = []

        class FailingWorker:
            def __init__(self, *args, **kwargs): self.joined = False
            def start(self): raise RuntimeError("thread start failed")
            def is_alive(self): return False
            def join(self, **kwargs): self.joined = True

        def thread_factory(*args, **kwargs):
            if not created:
                worker = FailingWorker()
                created.append(worker)
                return worker
            return original_thread(*args, **kwargs)

        store = TelemetryStore(":memory:")
        with patch("builtins.print"):
            with self.assertRaisesRegex(RuntimeError, "thread start failed"):
                run_monitor(source, store=store, duration=10, port=0,
                            thread_factory=thread_factory)
        self.assertEqual(created[0].joined, False)
        self.assertEqual(source.closed, 1)
        with self.assertRaises(Exception): store.db.execute("SELECT 1")

    def test_stuck_worker_keeps_store_open_until_worker_exits(self):
        class Source:
            signals = []
            entered = threading.Event()
            release = threading.Event()
            def read(self):
                self.entered.set()
                self.release.wait()
                return []
            def close(self): pass

        source = Source()
        store = TelemetryStore(":memory:")
        outcome = []

        def run():
            try: run_monitor(source, store=store, duration=1, port=0, worker_join_timeout=0.01)
            except Exception as exc: outcome.append(exc)

        with patch("builtins.print"):
            thread = threading.Thread(target=run)
            thread.start()
            self.assertTrue(source.entered.wait(2))
            thread.join(5)
        self.assertFalse(thread.is_alive())
        self.assertTrue(any("database left open" in str(error) for error in outcome))
        self.assertEqual(store.db.execute("SELECT count(*) FROM sessions").fetchone()[0], 1)
        source.release.set()
        deadline = threading.Event()
        for _ in range(100):
            if store.db.execute("SELECT ended_utc FROM sessions").fetchone()[0] is not None: break
            deadline.wait(0.01)
        store.close()

    def test_duration_expiry_stops_and_closes(self):
        class Source:
            signals = []
            halted = False
            closed = threading.Event()
            def read(self): return []
            def close(self): self.closed.set()

        source = Source()
        with patch("builtins.print"):
            run_monitor(source, duration=1, port=0)
        self.assertTrue(source.closed.is_set())

    def test_duration_timer_starts_before_first_acquisition(self):
        timer_started = threading.Event()

        class TrackingTimer(threading.Timer):
            def start(self):
                super().start()
                timer_started.set()

        class Source:
            signals = []
            def read(self):
                if not timer_started.is_set(): raise AssertionError("request began before duration timer")
                return []
            def close(self): pass

        with patch("builtins.print"), patch("threading.Timer", TrackingTimer):
            run_monitor(Source(), duration=1, port=0)

    def test_generalized_runner_preserves_temperature_defaults(self):
        captured = {}

        class Source:
            signals = []
            halted = False
            def read(self): self.halted = True; return []
            def close(self): pass

        class Server:
            server_port = 12345
            def __init__(self): self.stopped = threading.Event()
            def serve_forever(self): self.stopped.wait(2)
            def shutdown(self): self.stopped.set()
            def server_close(self): pass

        server = Server()

        def serve(engine, host, port, recording, mode):
            captured.update(engine=engine, host=host, mode=mode)
            return server

        with patch("supra_telemetry.web.serve", side_effect=serve), patch("builtins.print") as output:
            result = run_monitor(Source(), duration=5)
        self.assertEqual(result, 1)
        self.assertEqual(captured["engine"].interval, INTERVAL_SECONDS)
        self.assertEqual(captured["mode"], "temperature-monitor")
        self.assertEqual(captured["host"], "127.0.0.1")
        self.assertIn("Temperature monitor dashboard:", output.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
