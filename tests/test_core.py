import csv
import copy
import json
import os
import socket
import struct
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from pathlib import Path

from supra_telemetry.safety import SafetyPolicy, UnsafeRequest
from supra_telemetry.uds import parse_response, mode01_value
from supra_telemetry.hsfz import encode_frame, recv_frame, parse_frame, parse_discovery_response, HsfzClient, discover as hsfz_discover
from supra_telemetry.doip import encode_message, parse_message, VEHICLE_ANNOUNCEMENT, parse_announcement
from supra_telemetry import doip
from supra_telemetry.models import SignalDefinition, decode_integer, utc_now
from supra_telemetry.profiles import load_profile
from supra_telemetry.storage import TelemetryStore, export_csv
from supra_telemetry.engine import AcquisitionEngine
from supra_telemetry.live import HsfzSignalSource
from supra_telemetry.web import serve


class CoreTests(unittest.TestCase):
    def test_policy_allow_reject_and_correlation(self):
        p = SafetyPolicy()
        for msg in (b"\x01\x0c", b"\x09\x02", b"\x22\xf1\x90"):
            self.assertEqual(p.authorize(msg).payload, msg)
        for msg in (b"\x10\x03", b"\x11\x01", b"\x27\x01", b"\x31\x01", b"\x14", b"\x34"):
            with self.assertRaises(UnsafeRequest): p.authorize(msg)
        with self.assertRaises(UnsafeRequest): p.authorize(b"\x3e\x00")
        self.assertIsInstance(SafetyPolicy.ALLOWED, frozenset)
        self.assertTrue(p.correlate(b"\x22\xf1\x90", b"\x62\xf1\x90\x01"))
        self.assertFalse(p.correlate(b"\x22\xf1\x90", b"\x62\xf1\x91\x01"))

    def test_uds_and_standard_decode(self):
        self.assertEqual(parse_response(b"\x41\x0c\x1a\x2c", 1).data, b"\x0c\x1a\x2c")
        self.assertTrue(parse_response(b"\x7f\x22\x78", 0x22).pending)
        self.assertEqual(mode01_value(0x0c, b"\x1a\x2c"), (1675.0, "rpm"))
        self.assertEqual(mode01_value(0x05, b"\x64"), (60.0, "°C"))

    def test_transport_frames(self):
        packet = encode_frame(0x0001, 0xF4, 0x10, b"\x01\x0c")
        self.assertEqual(packet.hex(), "000000040001f410010c")
        left, right = socket.socketpair()
        try:
            left.sendall(packet)
            frame = recv_frame(right)
            self.assertEqual((frame.control, frame.source, frame.target, frame.payload), (1, 0xF4, 0x10, b"\x01\x0c"))
        finally: left.close(); right.close()
        self.assertEqual(parse_frame(bytes.fromhex("000000020012"), b"\xf4\x10").control, 0x12)
        self.assertEqual(parse_frame(bytes.fromhex("000000030012"), b"\xf4\x10x").payload, b"\xf4\x10x")
        alive = parse_frame(bytes.fromhex("000000080012"), b"ident123")
        self.assertEqual(alive.extra, b"ident123")
        msg = parse_message(encode_message(0x0001, b"x"))
        self.assertEqual(msg.payload_type, 1)
        self.assertEqual(parse_message(encode_message(1, b"x", version=3)).version, 3)
        announcement = b"A" * 17 + b"\x12\x34" + bytes(range(12)) + b"\x05"
        parsed = parse_announcement(encode_message(VEHICLE_ANNOUNCEMENT, announcement))
        self.assertEqual(parsed["logical_address"], "1234")
        self.assertEqual(parsed["further_action"], 5)
        with self.assertRaises(ValueError): parse_message(b"short")
        with self.assertRaises(ValueError): parse_message(bytes.fromhex("02fc000400000000"))
        with self.assertRaises(ValueError): parse_announcement(encode_message(VEHICLE_ANNOUNCEMENT, b"short"))

    def test_profile_and_codec(self):
        root = Path(__file__).resolve().parents[1]
        _, sigs = load_profile(root / "config/supra-2023.template.json")
        self.assertFalse(any(s.enabled for s in sigs))
        with self.assertRaises(ValueError): load_profile(root / "config/supra-2023.template.json", live=True)
        s = SignalDefinition("x", "x", response_offset=1, width=2, scale=.25)
        self.assertEqual(decode_integer(b"\x00\x01\x90", s), 100.0)
        with self.assertRaises(ValueError): decode_integer(b"\x00", s)
        valid = {"validation_status": "verified", "transport":"HSFZ", "tester_address": 244, "signals": [{"id":"rpm","name":"RPM","kind":"measured","verification":"verified","enabled":True,"service":"01","request":"0C","target_address":16,"response_offset":2,"width":2}]}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "profile.json"; path.write_text(json.dumps(valid), encoding="utf-8")
            self.assertTrue(load_profile(path, live=True)[1][0].enabled)
            loaded = load_profile(path, live=True)[1][0]
            self.assertEqual((loaded.unit, loaded.scale, loaded.width, loaded.response_offset), ("rpm", .25, 2, 2))
            del valid["tester_address"]; path.write_text(json.dumps(valid), encoding="utf-8")
            with self.assertRaises(ValueError): load_profile(path, live=True)
            valid["tester_address"] = 244; del valid["signals"][0]["target_address"]
            path.write_text(json.dumps(valid), encoding="utf-8")
            with self.assertRaises(ValueError): load_profile(path, live=True)

    def test_mode01_profile_rejects_false_metadata_before_io(self):
        base = {"validation_status":"verified", "transport":"HSFZ", "tester_address":244,
                "signals":[{"id":"speed", "name":"Speed", "kind":"measured",
                            "verification":"verified", "enabled":True, "service":"01",
                            "request":"0D", "target_address":16}]}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "profile.json"
            canonical = json.loads(json.dumps(base))
            path.write_text(json.dumps(canonical), encoding="utf-8")
            signal = load_profile(path, live=True)[1][0]
            self.assertEqual((signal.unit, signal.scale, signal.response_offset), ("km/h", 1.0, 2))
            for field, value in (("unit", "mph"), ("scale", 0.621371), ("offset", 1)):
                bad = json.loads(json.dumps(base)); bad["signals"][0][field] = value
                path.write_text(json.dumps(bad), encoding="utf-8")
                with self.assertRaises(ValueError): load_profile(path, live=True)
            unsupported = json.loads(json.dumps(base)); unsupported["signals"][0]["request"] = "10"
            path.write_text(json.dumps(unsupported), encoding="utf-8")
            with self.assertRaises(ValueError): load_profile(path, live=True)

    def test_profile_strict_preflight(self):
        base = {"validation_status":"verified", "transport":"HSFZ", "tester_address":244,
                "signals":[{"id":"rpm","name":"RPM","kind":"measured","verification":"verified","enabled":True,"signed":False,"service":"01","request":"0C","target_address":16,"response_offset":2,"width":2,"byteorder":"big","scale":0.25,"offset":0.0,"expected_hz":2.0}]}
        mutations = [
            lambda d: d.update(tester_address=True),
            lambda d: d["signals"][0].update(target_address=True),
            lambda d: d["signals"][0].update(response_offset=True),
            lambda d: d["signals"][0].update(width=True),
            lambda d: d["signals"][0].update(enabled=1),
            lambda d: d["signals"][0].update(signed=1),
            lambda d: d["signals"][0].update(width=5),
            lambda d: d["signals"][0].update(byteorder="native"),
            lambda d: d["signals"][0].update(scale=float("inf")),
            lambda d: d["signals"][0].update(offset=float("nan")),
            lambda d: d["signals"][0].update(expected_hz=0),
            lambda d: d["signals"][0].update(kind="mystery"),
            lambda d: d["signals"][0].update(kind="derived"),
            lambda d: d["signals"][0].update(kind="unavailable"),
            lambda d: d["signals"][0].update(id=""),
            lambda d: d["signals"][0].update(service="10", request="03"),
            lambda d: d["signals"][0].update(response_offset=8191),
            lambda d: d["signals"][0].update(response_offset=-1),
            lambda d: d["signals"].append(dict(d["signals"][0])),
        ]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "profile.json"
            for mutate in mutations:
                invalid = copy.deepcopy(base); mutate(invalid); path.write_text(json.dumps(invalid), encoding="utf-8")
                with self.subTest(profile=invalid), self.assertRaises(ValueError): load_profile(path, live=True)

    def test_storage_csv_and_engine(self):
        with tempfile.TemporaryDirectory() as td:
            dbpath = Path(td) / "x.sqlite"; csvpath = Path(td) / "x.csv"
            store = TelemetryStore(dbpath)
            session = store.start_session(utc_now())
            for name, kind in (("engine_rpm", "measured"), ("vehicle_speed", "measured"), ("coolant_temp", "measured"), ("boost", "derived"), ("gear", "unavailable")):
                metadata = {"service":"01", "request":"0C", "target_address":16, "response_offset":2, "width":2, "byteorder":"big", "signed":False, "scale":.25, "offset":0.0} if name == "engine_rpm" else {}
                store.register(session, SignalDefinition(name, name, kind=kind, **metadata))
            engine = AcquisitionEngine(store=store, session_id=session)
            samples = engine.step()
            self.assertEqual(len(samples), 5)
            time.sleep(.03); samples = engine.step()
            self.assertTrue(all(s.observed_hz and s.observed_hz > 0 for s in samples))
            store.end_session(session, utc_now())
            session2 = store.start_session(utc_now())
            store.register(session2, SignalDefinition("engine_rpm", "Different session definition", service="01", request="0D", target_address=17, response_offset=2, width=1, scale=1.0))
            names_scoped = store.db.execute("SELECT session_id, name, request, target_address, width, scale FROM signals WHERE id='engine_rpm' ORDER BY session_id").fetchall()
            self.assertEqual(names_scoped, [(session, "engine_rpm", "0C", 16, 2, .25), (session2, "Different session definition", "0D", 17, 1, 1.0)])
            store.end_session(session2, utc_now())
            export_csv(dbpath, csvpath); store.close()
            with csvpath.open(encoding="utf-8") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 10)
            self.assertTrue(all(row["timestamp_utc"] and row["quality"] for row in rows))
            self.assertTrue(all(row["session_id"] == str(session) for row in rows))
            self.assertTrue(any(row["observed_hz"] for row in rows))

    def test_store_from_worker_thread(self):
        with tempfile.TemporaryDirectory() as td:
            store = TelemetryStore(Path(td) / "thread.sqlite")
            session = store.start_session(utc_now())
            names = ["engine_rpm", "vehicle_speed", "coolant_temp", "boost", "gear"]
            for name in names: store.register(session, SignalDefinition(name, name, kind="measured" if name != "boost" else "derived"))
            engine = AcquisitionEngine(store=store, session_id=session, interval=.1)
            stopper = threading.Event(); worker = threading.Thread(target=engine.run, args=(stopper,)); worker.start()
            time.sleep(.23); stopper.set(); worker.join(2)
            with store._lock:
                count = store.db.execute("SELECT COUNT(*) FROM samples").fetchone()[0]
            store.close()
            self.assertGreaterEqual(count, 5)

    def test_hsfz_gateway_ack_positive_pending_mismatch_and_policy(self):
        def exchange(responses, request=b"\x01\x0c"):
            client_side, server_side = socket.socketpair(); seen = []
            def gateway():
                received = recv_frame(server_side); seen.append(received)
                for response in responses: server_side.sendall(response)
                server_side.close()
            thread = threading.Thread(target=gateway); thread.start()
            audit = []
            cli = HsfzClient("fixture", 0xF4, 0x10, timeout=1, audit=audit.append, sock_factory=lambda *_: client_side)
            try: result = cli.request(request)
            finally: cli.close(); thread.join(1)
            return result, seen, audit
        ack = encode_frame(2, 0x10, 0xF4)
        positive = encode_frame(1, 0x10, 0xF4, b"\x41\x0c\x1a\x2c")
        alive = bytes.fromhex("000000080012") + b"ident123"
        result, seen, audits = exchange([ack, alive, positive])
        self.assertEqual(result, b"\x41\x0c\x1a\x2c")
        self.assertEqual(seen[0].payload, b"\x01\x0c")
        self.assertEqual(audits[0].outcome, "ok")
        self.assertIn(b"ident123", audits[0].response)
        _, _, pending_audit = exchange([encode_frame(1, 0x10, 0xF4, b"\x7f\x01\x78"), positive])
        self.assertEqual(pending_audit[0].outcome, "ok")
        bad_result = encode_frame(1, 0x10, 0xF5, b"\x41\x0c\x1a\x2c")
        s1, s2 = socket.socketpair()
        def wrong_gateway():
            recv_frame(s2); s2.sendall(bad_result)
        t = threading.Thread(target=wrong_gateway); t.start()
        cli = HsfzClient("fixture", 0xF4, 0x10, timeout=.5, sock_factory=lambda *_: s1)
        with self.assertRaises(ConnectionError): cli.request(b"\x01\x0c")
        cli.close(); t.join(1); s2.close()
        s1, s2 = socket.socketpair()
        def error_gateway():
            recv_frame(s2); s2.sendall(bytes.fromhex("000000000040"))
        t = threading.Thread(target=error_gateway); t.start()
        cli = HsfzClient("fixture", 0xF4, 0x10, timeout=.5, sock_factory=lambda *_: s1)
        with self.assertRaises(ConnectionError): cli.request(b"\x01\x0c")
        cli.close(); t.join(1); s2.close()
        class NoConnect:
            def __call__(self, *_): raise AssertionError("policy must reject before socket creation")
        with self.assertRaises(UnsafeRequest): HsfzClient("fixture", 0xF4, 0x10, sock_factory=NoConnect()).request(b"\x2e\xf1\x90\x00")

    def test_discovery_parse_and_live_source(self):
        body = b"DIAGADR10BMWMACAABBCCDDEEFFBMWVINWBA12345678901234"
        packet = struct.pack(">IH", len(body), 0x11) + body
        parsed = parse_discovery_response(packet)
        self.assertEqual(parsed["vin"], "WBA12345678901234")
        self.assertEqual(parsed["mac"], "AABBCCDDEEFF")
        with self.assertRaises(ValueError): parse_discovery_response(packet[:-1])
        profile = {"validation_status": "verified", "tester_address": 0xF4}
        sig = SignalDefinition("rpm", "RPM", "rpm", verification="verified", enabled=True, service="01", request="0C", target_address=0x10, response_offset=2, width=2)
        class FakeClient:
            def __init__(self, *a, **k): self.audit = k.get("audit")
            def request(self, req): return b"\x41\x0c\x1a\x2c"
            def close(self): pass
        src = HsfzSignalSource("127.0.0.1", profile, [sig], client_factory=FakeClient)
        sample = src.read()[0]
        self.assertEqual((sample.value, sample.quality), (1675.0, "good"))
        class Broken(FakeClient):
            def request(self, req): raise TimeoutError("fixture timeout")
        bad = HsfzSignalSource("127.0.0.1", profile, [sig], client_factory=Broken).read()[0]
        self.assertEqual((bad.value, bad.quality), (None, "error"))

    def test_doip_discovery_absolute_deadline(self):
        payload = b"V" * 17 + b"\x12\x34" + b"E" * 6 + b"G" * 6 + b"\x00"
        response = encode_message(VEHICLE_ANNOUNCEMENT, payload, version=3)
        class FakeSocket:
            def __init__(self): self.timeouts=[]; self.calls=0
            def setsockopt(self, *a): pass
            def bind(self, *a): pass
            def sendto(self, *a): pass
            def settimeout(self, value): self.timeouts.append(value)
            def recvfrom(self, size): self.calls+=1; return response, ("169.254.1.5", 13400)
            def close(self): pass
        fake = FakeSocket()
        with patch.object(doip.socket, "socket", return_value=fake), patch.object(doip.time, "monotonic", side_effect=[0.0, 0.0, 0.4, 0.5]):
            found = doip.discover("169.254.1.2", timeout=.5)
        self.assertEqual(len(found), 2)
        self.assertEqual(len(fake.timeouts), 2)
        self.assertAlmostEqual(fake.timeouts[0], .5)
        self.assertAlmostEqual(fake.timeouts[1], .1)

    def test_live_source_halts_and_emits_unavailable(self):
        profile = {"validation_status":"verified", "transport":"HSFZ", "tester_address":244}
        first = SignalDefinition("first", "First", verification="verified", enabled=True, service="01", request="0C", target_address=16, response_offset=2, width=2)
        second = SignalDefinition("second", "Second", verification="verified", enabled=True, service="01", request="0D", target_address=16, response_offset=2, width=1)
        unavailable = SignalDefinition("oil_temp", "Oil temperature", kind="unavailable", enabled=False)
        calls = []
        class FailedOnce:
            connected = True
            def __init__(self, *a, **k): pass
            def request(self, req): calls.append(req); raise TimeoutError("no response")
            def close(self): self.connected = False
        src = HsfzSignalSource("fixture", profile, [first, second, unavailable], client_factory=FailedOnce)
        samples = src.read()
        self.assertTrue(src.halted)
        self.assertEqual(src.halt_reason, "no response")
        self.assertEqual([s.quality for s in samples], ["error", "halted", "unavailable"])
        self.assertEqual([s.signal_id for s in samples], ["first", "second", "oil_temp"])
        count = len(calls); again = src.read()
        self.assertEqual(len(calls), count)
        self.assertEqual(again[0].quality, "halted")

    def test_acquisition_halts_on_storage_error(self):
        class Source:
            closed = False
            def read(self): return [__import__("supra_telemetry.models", fromlist=["Sample"]).Sample("x", 1, "", "test", "measured", "good", utc_now(), time.monotonic_ns())]
            def close(self): self.closed = True
        class BrokenStore:
            def add_sample(self, *_): raise OSError("disk unavailable")
        source = Source(); engine = AcquisitionEngine(source, BrokenStore(), 1, interval=.1)
        worker = threading.Thread(target=engine.run, args=(threading.Event(),)); worker.start(); worker.join(1)
        self.assertFalse(worker.is_alive())
        self.assertTrue(engine.halted and source.closed)
        self.assertEqual(engine.recording_error, "disk unavailable")
        server = serve(engine, port=0, recording=True, mode="live")
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            import urllib.request
            with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/state") as response:
                status = json.loads(response.read())
            self.assertEqual(status["recording"], "error")
            self.assertEqual(status["recording_error"], "disk unavailable")
            self.assertTrue(status["halted"])
        finally:
            server.shutdown(); thread.join(); server.server_close()

    def test_web_api(self):
        engine = AcquisitionEngine(); engine.step()
        server = serve(engine, port=0, recording=True)
        thread = threading.Thread(target=server.serve_forever); thread.start()
        try:
            import urllib.request
            with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/state") as response:
                data = json.loads(response.read())
            self.assertEqual(data["connection"], "demo")
            self.assertEqual(len(data["samples"]), 5)
            self.assertNotIn("innerHTML", __import__("supra_telemetry.web", fromlist=["HTML"]).HTML)
            engine.recording_error = "disk unavailable"; engine.halted = True
            with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/state") as response:
                failure = json.loads(response.read())
            self.assertEqual(failure["recording"], "error")
            self.assertEqual(failure["recording_error"], "disk unavailable")
        finally:
            server.shutdown(); thread.join(); server.server_close()

    def test_demo_dashboard_sqlite_api_csv_smoke(self):
        with tempfile.TemporaryDirectory() as td:
            dbpath, csvpath = Path(td) / "demo.sqlite", Path(td) / "demo.csv"
            store = TelemetryStore(dbpath); session = store.start_session(utc_now(), "demo")
            definitions = [SignalDefinition("engine_rpm", "RPM"), SignalDefinition("vehicle_speed", "Speed"),
                          SignalDefinition("coolant_temp", "Coolant"), SignalDefinition("boost", "Boost", kind="derived"),
                          SignalDefinition("gear", "Gear", kind="unavailable")]
            for definition in definitions: store.register(session, definition)
            engine = AcquisitionEngine(store=store, session_id=session, interval=.1)
            stopper = threading.Event(); worker = threading.Thread(target=engine.run, args=(stopper,)); worker.start()
            server = serve(engine, port=0, recording=True, mode="demo")
            http = threading.Thread(target=server.serve_forever); http.start()
            try:
                import urllib.request
                deadline = time.monotonic() + 1
                state = {}
                while time.monotonic() < deadline:
                    with urllib.request.urlopen(f"http://127.0.0.1:{server.server_port}/api/state") as response:
                        state = json.loads(response.read())
                    if len(state["samples"]) == 5: break
                    time.sleep(.01)
                self.assertEqual(state["mode"], "demo")
                self.assertEqual(len(state["samples"]), 5)
            finally:
                stopper.set(); worker.join(); server.shutdown(); http.join(); server.server_close()
            export_csv(dbpath, csvpath)
            with csvpath.open(encoding="utf-8") as f: rows = list(csv.DictReader(f))
            self.assertTrue(rows)
            self.assertTrue(all(row["session_id"] == str(session) for row in rows))
            with store._lock:
                ended = store.db.execute("SELECT ended_utc FROM sessions WHERE id=?", (session,)).fetchone()[0]
            store.close()
            self.assertTrue(ended)


if __name__ == "__main__": unittest.main()
