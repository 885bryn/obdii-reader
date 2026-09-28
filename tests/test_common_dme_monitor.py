import json
import sqlite3
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from supra_telemetry.common_dme_monitor import (
    MIN_REQUEST_INTERVAL_SECONDS, PIDS, SIGNALS, CommonDmeMonitorSource,
)
from supra_telemetry.dme_check import DME_TARGET_ADDRESS
from supra_telemetry.gateway_check import TESTER_ADDRESS
from supra_telemetry.storage import TelemetryStore, export_csv
from supra_telemetry.temperature_monitor import run_monitor


def private_capture(directory):
    vin, mac = "TESTVIN0000000001", "001122334455"
    body = b"DIAGADR10BMWMAC" + mac.encode() + b"BMWVIN" + vin.encode()
    packet = struct.pack(">IH", len(body), 0x11) + body
    record = {"peer": "169.254.10.20", "port": 6811,
              "identification": {"vin": vin, "mac": mac, "diagnostic_address": 0x10},
              "raw_hex": packet.hex()}
    path = Path(directory) / "capture.json"
    path.write_text(json.dumps({"interface": "169.254.10.30", "hsfz": [record]}), encoding="utf-8")
    return path


class CommonDmeMonitorTests(unittest.TestCase):
    def make_source(self, path, client, *, clock=None, wait=None, connector_calls=None,
                    duration=300):
        clock = clock or [0.0]
        connector_calls = connector_calls if connector_calls is not None else []

        def connector(address, timeout, *, source_address):
            connector_calls.append((address, timeout, source_address))
            return object()

        def client_factory(*args, **kwargs):
            self.assertEqual(args[0:3], ("169.254.10.20", TESTER_ADDRESS, DME_TARGET_ADDRESS))
            self.assertEqual(kwargs["port"], 6801)
            self.assertTrue(kwargs["fail_on_pending"])
            kwargs["sock_factory"]((args[0], 6801), kwargs["timeout"])
            return client

        return CommonDmeMonitorSource(path, client_factory=client_factory,
                                     connector_factory=connector,
                                     monotonic=lambda: clock[0], wait=wait,
                                     duration=duration), clock

    @staticmethod
    def response_for(request):
        pid = request[1]
        payload = {0x0C: b"\x0d\x48", 0x0D: b"\x00", 0x0F: b"\x46", 0x11: b"\x80"}[pid]
        return b"\x41" + bytes((pid,)) + payload

    def test_fixed_order_definitions_route_binding_and_spacing_across_cycles(self):
        with tempfile.TemporaryDirectory() as directory:
            path = private_capture(directory)
            clock = [0.0]
            starts, requests, closes, waits, bound = [], [], [], [], []

            class Client:
                connected = True
                def request(self, payload):
                    starts.append(clock[0])
                    requests.append(payload)
                    clock[0] += 0.2
                    return self_outer.response_for(payload)
                def close(self): closes.append(True)

            self_outer = self

            def wait(seconds):
                waits.append(seconds)
                clock[0] += seconds

            source, _ = self.make_source(path, Client(), clock=clock, wait=wait,
                                         connector_calls=bound)
            first, second = source.read(), source.read()

            self.assertEqual(requests, [bytes((0x01, pid)) for _ in range(2) for pid in PIDS])
            self.assertTrue(all(b - a >= MIN_REQUEST_INTERVAL_SECONDS
                                for a, b in zip(starts, starts[1:])))
            self.assertEqual([sample.signal_id for sample in first], [signal.id for signal in SIGNALS])
            self.assertEqual([sample.signal_id for sample in second], [signal.id for signal in SIGNALS])
            self.assertEqual([sample.value for sample in first], [850.0, 0.0, 30.0, 50.19607843137255])
            self.assertTrue(all(sample.quality == "good" for sample in first + second))
            self.assertEqual(bound, [(('169.254.10.20', 6801), 2.0, ('169.254.10.30', 0))])
            self.assertEqual(closes, [])
            self.assertEqual(len(waits), 7)
            self.assertTrue(all(signal.verification == "one-shot-verified"
                                for signal in source.signals))

    def test_stationary_gate_checks_each_decoded_value_and_stops_immediately(self):
        import supra_telemetry.common_dme_monitor as monitor

        invalid_values = ((0, 299.75), (1, 0.25), (2, 120.1), (3, 100.1))
        for invalid_index, invalid_value in invalid_values:
            with self.subTest(signal=SIGNALS[invalid_index].id), tempfile.TemporaryDirectory() as directory:
                calls, clock = [], [0.0]

                class Client:
                    connected = True
                    def request(self, payload):
                        calls.append(payload)
                        return self_outer.response_for(payload)
                    def close(self): pass

                self_outer = self
                source, _ = self.make_source(private_capture(directory), Client(), clock=clock,
                    wait=lambda seconds: clock.__setitem__(0, clock[0] + seconds))
                decoded = [850.0, 0.0, 30.0, 50.0]
                decoded[invalid_index] = invalid_value

                def fake_parse(response, pid):
                    index = PIDS.index(pid)
                    return decoded[index], SIGNALS[index].unit

                with patch.object(monitor, "parse_value_response", side_effect=fake_parse):
                    samples = source.read()
                self.assertEqual(len(calls), invalid_index + 1)
                self.assertEqual(samples[invalid_index].quality, "error")
                self.assertEqual(samples[invalid_index].error, "stationary-gate")
                self.assertTrue(all(sample.quality == "halted" for sample in samples[invalid_index + 1:]))

    def test_one_second_spacing_and_deadline_cap_total_attempts_at_300(self):
        with tempfile.TemporaryDirectory() as directory:
            clock, starts, calls = [0.0], [], []

            class Client:
                connected = True
                def request(self, payload):
                    starts.append(clock[0])
                    calls.append(payload)
                    return self_outer.response_for(payload)
                def close(self): pass

            self_outer = self
            def wait(seconds): clock[0] += seconds

            source, _ = self.make_source(private_capture(directory), Client(), clock=clock,
                                         wait=wait, duration=300)
            for _ in range(75):
                self.assertEqual(len(source.read()), 4)
            self.assertEqual(len(calls), 300)
            self.assertLessEqual(len(calls), 300)
            self.assertTrue(all(b - a >= 1.0 for a, b in zip(starts, starts[1:])))
            stopped = source.read()
            self.assertEqual(len(calls), 300)
            self.assertTrue(all(sample.quality == "halted" for sample in stopped))
            self.assertFalse(source.halted)

    def test_invalid_and_rejected_responses_halt_close_and_never_retry(self):
        for response, expected in ((b"\x41\x0c\x01", "response-invalid"),
                                   (b"\x7f\x01\x31", "uds-rejected")):
            with self.subTest(response=response), tempfile.TemporaryDirectory() as directory:
                path = private_capture(directory)
                calls, closes = [], []

                class Client:
                    connected = True
                    def request(self, payload): calls.append(payload); return response
                    def close(self): closes.append(True)

                source, _ = self.make_source(path, Client())
                samples = source.read()
                again = source.read()
                self.assertEqual(len(calls), 1)
                self.assertEqual(closes, [True])
                self.assertEqual(source.halt_reason, expected)
                self.assertEqual([sample.quality for sample in samples],
                                 ["error", "halted", "halted", "halted"])
                self.assertTrue(all(sample.quality == "halted" for sample in again))
                self.assertTrue(all(sample.value is None for sample in samples[1:] + again))

    def test_timeout_and_transport_failure_stop_at_first_pid(self):
        for error, expected in ((TimeoutError("private timeout text"), "timeout"),
                                (OSError("private socket text"), "connection-or-transport")):
            with self.subTest(expected=expected), tempfile.TemporaryDirectory() as directory:
                calls, closes = [], []

                class Client:
                    connected = True
                    def request(self, payload): calls.append(payload); raise error
                    def close(self): closes.append(True)

                source, _ = self.make_source(private_capture(directory), Client())
                samples = source.read()
                self.assertEqual(calls, [b"\x01\x0c"])
                self.assertEqual(closes, [True])
                self.assertEqual(samples[0].error, expected)
                self.assertTrue(all(sample.quality == "halted" for sample in samples[1:]))
                self.assertNotIn("private", repr(samples))

    def test_stop_arriving_during_request_prevents_next_request(self):
        with tempfile.TemporaryDirectory() as directory:
            entered, release = threading.Event(), threading.Event()
            calls, samples = [], []
            clock = [0.0]

            class Client:
                connected = True
                def request(self, payload):
                    calls.append(payload)
                    entered.set()
                    release.wait(2)
                    clock[0] += 1.0
                    return self_outer.response_for(payload)
                def close(self): pass

            self_outer = self
            source, _ = self.make_source(private_capture(directory), Client(), clock=clock)
            reader = threading.Thread(target=lambda: samples.extend(source.read()))
            reader.start()
            self.assertTrue(entered.wait(1))
            stopper = threading.Thread(target=source.stop)
            stopper.start()
            self.assertTrue(source._stop.wait(1))
            release.set()
            reader.join(1)
            stopper.join(1)
            self.assertFalse(reader.is_alive() or stopper.is_alive())
            self.assertEqual(calls, [b"\x01\x0c"])
            self.assertEqual([sample.quality for sample in samples],
                             ["good", "halted", "halted", "halted"])

    def test_stop_wins_request_initiation_gate_and_prevents_transport(self):
        with tempfile.TemporaryDirectory() as directory:
            path = private_capture(directory)
            calls, samples = [], []
            clock = [0.0]
            second_gate_waiting, allow_second_gate = threading.Event(), threading.Event()

            class Gate:
                def __init__(self):
                    self.lock, self.guard, self.count = threading.Lock(), threading.Lock(), 0
                def __enter__(self):
                    with self.guard:
                        self.count += 1
                        second = self.count == 2
                    if second:
                        second_gate_waiting.set()
                        allow_second_gate.wait(1)
                    self.lock.acquire()
                    return self
                def __exit__(self, *_args): self.lock.release()

            class Client:
                connected = True
                def request(self, payload):
                    calls.append(payload)
                    return self_outer.response_for(payload)
                def close(self): pass

            self_outer = self
            def wait(seconds):
                clock[0] += seconds

            source, _ = self.make_source(path, Client(), clock=clock, wait=wait)
            source._request_gate = Gate()
            reader = threading.Thread(target=lambda: samples.extend(source.read()))
            reader.start()
            self.assertTrue(second_gate_waiting.wait(1))
            stopper = threading.Thread(target=source.stop)
            stopper.start()
            self.assertTrue(source._stop.wait(1))
            stopper.join(1)
            self.assertFalse(stopper.is_alive())
            allow_second_gate.set()
            reader.join(1)
            self.assertFalse(reader.is_alive())
            self.assertEqual(calls, [b"\x01\x0c"])
            self.assertEqual([sample.quality for sample in samples],
                             ["good", "halted", "halted", "halted"])

    def test_no_vehicle_or_network_access_when_fake_factories_are_supplied(self):
        with tempfile.TemporaryDirectory() as directory:
            requested, connected = [], []

            class Client:
                connected = False
                def request(self, payload): requested.append(payload); return self.response_for(payload)
                def close(self): pass
                response_for = staticmethod(lambda payload: b"\x41" + payload[1:] + b"\x00\x00")

            source, _ = self.make_source(private_capture(directory), Client(), connector_calls=connected)
            source.close()
            self.assertEqual(requested, [])
            self.assertEqual(len(connected), 1)  # The injected connector only records the captured binding.
            self.assertEqual(source.signals, list(SIGNALS))

    def test_runner_auto_stops_and_sqlite_csv_contain_samples_without_raw_exchange(self):
        with tempfile.TemporaryDirectory() as directory:
            path = private_capture(directory)
            db_path, csv_path = Path(directory) / "monitor.sqlite", Path(directory) / "monitor.csv"
            calls, closed = [], []

            class Client:
                connected = True
                def request(self, payload):
                    calls.append(payload)
                    return self_outer.response_for(payload)
                def close(self): closed.append(True)

            self_outer = self
            source, _ = self.make_source(path, Client())
            store = TelemetryStore(db_path)
            with patch("builtins.print"):
                result = run_monitor(source, store=store, duration=1, port=0,
                                     interval=1.0, mode="common-dme-monitor",
                                     title="Common DME monitor")
            self.assertEqual(result, 0)
            self.assertEqual(calls, [b"\x01\x0c"])
            self.assertTrue(closed)
            db = sqlite3.connect(db_path)
            try:
                sessions = db.execute("SELECT mode, ended_utc FROM sessions").fetchall()
                raw_count = db.execute("SELECT count(*) FROM raw_exchanges").fetchone()[0]
                sample_rows = db.execute(
                    "SELECT signal_id, value, quality FROM samples ORDER BY id").fetchall()
                self.assertEqual(sessions[0][0], "common-dme-monitor")
                self.assertIsNotNone(sessions[0][1])
                self.assertEqual(raw_count, 0)
                self.assertEqual(sample_rows, [
                    ("engine_rpm", "850.0", "good"),
                    ("vehicle_speed", None, "halted"),
                    ("intake_air_temperature", None, "halted"),
                    ("throttle_position", None, "halted"),
                ])
            finally:
                db.close()
            export_csv(db_path, csv_path)
            csv_text = csv_path.read_text(encoding="utf-8")
            self.assertIn("engine_rpm,hsfz,measured,good,rpm,850.0", csv_text)
            self.assertNotIn("request", csv_text.lower())
            self.assertNotIn("response", csv_text.lower())

    def test_runner_failure_halts_and_persists_only_safe_failure_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            calls, closes = [], []

            class Client:
                connected = True
                def request(self, payload):
                    calls.append(payload)
                    return b"\x41\x0c\x00"  # Invalid width for the requested RPM PID.
                def close(self): closes.append(True)

            source, _ = self.make_source(private_capture(directory), Client())
            db_path = Path(directory) / "failed.sqlite"
            store = TelemetryStore(db_path)
            with patch("builtins.print"):
                result = run_monitor(source, store=store, duration=30, port=0,
                                     interval=1.0, mode="common-dme-monitor",
                                     title="Common DME monitor")
            self.assertEqual(result, 1)
            self.assertTrue(source.halted)
            self.assertEqual(calls, [b"\x01\x0c"])
            self.assertEqual(closes, [True])
            db = sqlite3.connect(db_path)
            try:
                rows = db.execute("SELECT signal_id, quality, error FROM samples ORDER BY id").fetchall()
                self.assertEqual(rows, [
                    ("engine_rpm", "error", "response-invalid"),
                    ("vehicle_speed", "halted", "response-invalid"),
                    ("intake_air_temperature", "halted", "response-invalid"),
                    ("throttle_position", "halted", "response-invalid"),
                ])
                self.assertEqual(db.execute("SELECT count(*) FROM raw_exchanges").fetchone()[0], 0)
                self.assertIsNotNone(db.execute("SELECT ended_utc FROM sessions").fetchone()[0])
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
