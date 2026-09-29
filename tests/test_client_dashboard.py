import contextlib
import io
import json
import re
import tempfile
import threading
import time
import unittest
from collections import deque
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import urlopen
from unittest.mock import patch

from supra_telemetry.client_dashboard import (
    BOUNDS, HTML, SCHEDULE, SIGNALS, DashboardLiveSource, DashboardSimSource,
    dashboard_state, make_dashboard_handler, run_live_dtc_snapshot, safe_dtc_snapshot,
    reserve_dashboard_server, serve_client_dashboard, wait_after_dtc_snapshot,
    STATIC_ROOT,
)
from supra_telemetry.engine import AcquisitionEngine
from supra_telemetry.models import Sample


def capture(directory):
    vin, mac = "TESTVIN0000000001", "001122334455"
    body = b"DIAGADR10BMWMAC" + mac.encode() + b"BMWVIN" + vin.encode()
    packet = len(body).to_bytes(4, "big") + b"\x00\x11" + body
    path = Path(directory) / "capture.json"
    path.write_text(json.dumps({"interface": "169.254.10.30", "hsfz": [{
        "peer": "169.254.10.20", "port": 6811,
        "identification": {"vin": vin, "mac": mac, "diagnostic_address": 16},
        "raw_hex": packet.hex()}]}), encoding="utf-8")
    return path


def dashboard_bundle():
    script = re.search(r'<script[^>]+src="\./(assets/[^\"]+\.js)"', HTML)
    if script is None:
        raise AssertionError("compiled dashboard entrypoint is missing")
    return STATIC_ROOT.joinpath(*script.group(1).split("/")).read_text(encoding="utf-8")


class ClientDashboardTests(unittest.TestCase):
    def test_close_interrupts_blocked_request_without_waiting_for_request_gate(self):
        with tempfile.TemporaryDirectory() as td:
            entered, release = threading.Event(), threading.Event()
            close_calls = []
            class BlockingClient:
                connected = True
                def request(self, _payload):
                    entered.set()
                    release.wait(2)
                    return b"\x41\x0c\x0d\x48"
                def close(self): close_calls.append(True); release.set()
            client = BlockingClient()
            source = DashboardLiveSource.__new__(DashboardLiveSource)
            source.client = client
            source.signals = list(SIGNALS)
            source.timeout, source.duration = 1.0, 4
            source._max_attempts, source._monotonic = 20, time.monotonic
            source._wait, source._custom_wait = time.sleep, False
            source._stop, source._deadline = threading.Event(), time.monotonic() + 4
            source._started, source._tick = 0, 0
            source._next_slot_at, source._last_started = time.monotonic(), None
            source._request_starts, source._gate = deque(), threading.Lock()
            source._close_gate = threading.Lock()
            source._closed, source.halted = False, False
            source.halt_reason, source.connected = None, False
            reader = threading.Thread(target=source.read, daemon=True)
            reader.start()
            self.assertTrue(entered.wait(1), "request did not begin")
            closer = threading.Thread(target=source.close, daemon=True)
            closer.start()
            closer.join(0.2)
            try:
                self.assertFalse(closer.is_alive(), "close waited for the blocked request gate")
                self.assertTrue(release.is_set(), "client.close was not called promptly")
                source.close()
                self.assertEqual(len(close_calls), 1, "source.close must remain idempotent")
            finally:
                release.set()
                closer.join(1)
                reader.join(1)

    def make_source(self, path, clock, calls, *, duration=300, wait=None, response=None):
        class Client:
            connected = True
            def request(self, payload):
                calls.append((clock[0], payload))
                if response:
                    return response(payload)
                pid = payload[1]
                if pid in (0x05, 0x5C):
                    return bytes((0x41, pid, 130))
                data = {0x0C: b"\x0d\x48", 0x0D: b"\x00", 0x0F: b"\x46", 0x11: b"\x20"}[pid]
                return b"\x41" + bytes((pid,)) + data
            def close(self): pass
        def factory(*_args, **kwargs):
            kwargs["sock_factory"](("ignored", 6801), kwargs["timeout"])
            return Client()
        def connector(addr, timeout, *, source_address):
            self.assertEqual(source_address, ("169.254.10.30", 0))
            return object()
        return DashboardLiveSource(path, duration=duration, monotonic=lambda: clock[0],
                                   wait=wait or (lambda delay: clock.__setitem__(0, clock[0]+delay)),
                                   client_factory=factory, connector_factory=connector)

    def test_schedule_uses_idle_slots_and_meets_each_signal_cadence(self):
        with tempfile.TemporaryDirectory() as td:
            clock, calls = [0.0], []
            source = self.make_source(capture(td), clock, calls, duration=4)
            for _ in range(20): source.read()
            pids = [payload[1] for _, payload in calls]
            self.assertEqual(pids, [pid for pid in SCHEDULE if pid is not None] * 2)
            self.assertEqual(sum(pid is not None for pid in SCHEDULE[:10]), 5)
            self.assertEqual(sum(pid is not None for pid in SCHEDULE[10:]), 5)
            self.assertTrue(all(b[0]-a[0] >= 0.1 - 1e-9 for a, b in zip(calls, calls[1:])))
            for pid, expected_count, max_gap in ((0x0C, 8, 0.5), (0x11, 4, 1.0),
                                                 (0x0D, 2, 2.0), (0x0F, 2, 2.0),
                                                 (0x05, 2, 2.0), (0x5C, 2, 2.0)):
                starts = [at for at, payload in calls if payload[1] == pid]
                self.assertEqual(len(starts), expected_count)
                self.assertLessEqual(max(b-a for a, b in zip(starts, starts[1:])), max_gap + 1e-9)
            starts = [at for at, _ in calls]
            self.assertTrue(all(sum(0 <= later-at < 1.0 - 1e-9 for later in starts) <= 5
                                for at in starts))
            self.assertEqual([s.id for s in SIGNALS], ["engine_rpm", "vehicle_speed", "intake_air_temperature", "throttle_position", "coolant_temp", "engine_oil_temp"])

    def test_duration_caps_attempts_and_pacing_wait_can_be_stopped(self):
        with tempfile.TemporaryDirectory() as td:
            clock, calls = [0.0], []
            source = self.make_source(capture(td), clock, calls, duration=2)
            for _ in range(11): source.read()
            self.assertEqual(len(calls), 10)
            self.assertAlmostEqual(clock[0], 1.7)
            self.assertTrue(all(at < 2 for at, _ in calls))

        with tempfile.TemporaryDirectory() as td:
            clock, calls = [0.0], []
            source = self.make_source(capture(td), clock, calls, duration=300)
            for _ in range(1501): source.read()
            self.assertLessEqual(len(calls), 1500)
            self.assertGreater(len(calls), 0)
            self.assertLess(clock[0], 300)

        with tempfile.TemporaryDirectory() as td:
            clock, calls = [0.0], []
            source = self.make_source(capture(td), clock, calls, duration=1)
            for _ in range(6): source.read()
            self.assertEqual(len(calls), 5)
            self.assertTrue(all(at < 1 for at, _ in calls))

        with tempfile.TemporaryDirectory() as td:
            clock, calls = [0.0], []
            def slow_response(payload):
                clock[0] += 0.65
                pid = payload[1]
                if pid in (0x05, 0x5C):
                    return bytes((0x41, pid, 130))
                data = {0x0C: b"\x0d\x48", 0x0D: b"\x00", 0x0F: b"\x46", 0x11: b"\x20"}[pid]
                return b"\x41" + bytes((pid,)) + data
            source = self.make_source(capture(td), clock, calls, duration=4,
                                      response=slow_response)
            for _ in range(3): source.read()
            starts = [at for at, _ in calls]
            pids = [payload[1] for _, payload in calls]
            self.assertEqual(pids, [0x0C, 0x0F, 0x0C])
            self.assertGreater(starts[1] - starts[0], 0.5)
            self.assertTrue(all(b-a >= 0.1 for a, b in zip(starts, starts[1:])))
            self.assertEqual(len(calls), 3)

        with tempfile.TemporaryDirectory() as td:
            clock, calls = [1.05], []
            source = self.make_source(capture(td), clock, calls, duration=4,
                                      wait=lambda delay: clock.__setitem__(0, clock[0]+delay))
            source._request_starts.extend((0.11, 0.21, 0.31, 0.41, 0.51))
            source._started = 5
            source._next_slot_at = 1.05  # jitter put this scheduled slot late
            source._tick = 10
            source.read()
            starts = [0.11, 0.21, 0.31, 0.41, 0.51, calls[0][0]]
            self.assertAlmostEqual(calls[0][0], 1.11)
            self.assertTrue(all(sum(0 <= later-at < 1.0 - 1e-9 for later in starts) <= 5
                                for at in starts))

    def test_rolling_rate_wait_obeys_stop_and_deadline(self):
        with tempfile.TemporaryDirectory() as td:
            clock, calls = [0.0], []
            waiting, release = threading.Event(), threading.Event()
            def wait(_):
                waiting.set(); release.wait(1)
            source = self.make_source(capture(td), clock, calls, duration=3, wait=wait)
            clock[0] = 0.5
            source._request_starts.extend((0.0, 0.1, 0.2, 0.3, 0.4))
            source._started = 5
            source._next_slot_at = 0.5
            source._tick = 5
            reader = threading.Thread(target=source.read)
            reader.start(); self.assertTrue(waiting.wait(1))
            closer = threading.Thread(target=source.close)
            closer.start(); release.set()
            reader.join(1); closer.join(1)
            self.assertFalse(reader.is_alive())
            self.assertFalse(closer.is_alive())
            self.assertEqual(calls, [])

        with tempfile.TemporaryDirectory() as td:
            clock, calls = [0.0], []
            source = self.make_source(capture(td), clock, calls, duration=2,
                                      wait=lambda delay: clock.__setitem__(0, clock[0]+delay))
            clock[0] = 1.5
            source._request_starts.extend((1.2, 1.3, 1.4, 1.45, 1.49))
            source._started = 5
            source._next_slot_at = 1.5
            source._tick = 15
            source.read()
            self.assertEqual(clock[0], 2.0)
            self.assertEqual(calls, [])

        with tempfile.TemporaryDirectory() as td:
            clock, calls = [0.0], []
            waiting, release = threading.Event(), threading.Event()
            def wait(_):
                waiting.set(); release.wait(1)
            source = self.make_source(capture(td), clock, calls, wait=wait)
            source.read()
            reader = threading.Thread(target=source.read)
            reader.start(); self.assertTrue(waiting.wait(1))
            source.close(); release.set(); reader.join(1)
            self.assertFalse(reader.is_alive())
            self.assertEqual(len(calls), 1)

    def test_first_failure_halts_without_retry_and_stationary_bound(self):
        with tempfile.TemporaryDirectory() as td:
            clock, calls = [0.0], []
            source = self.make_source(capture(td), clock, calls,
                                      response=lambda _: b"\x7f\x01\x31")
            sample = source.read()[0]
            self.assertEqual(sample.error, "uds-rejected")
            self.assertEqual(source.read(), [])
            self.assertEqual(len(calls), 1)

        self.assertEqual(BOUNDS[0x0D], (0, 0))
        self.assertEqual(BOUNDS[0x0C], (300, 2500))

    def test_dtc_partial_result_keeps_safe_codes_and_fixed_reason(self):
        class Error(Exception):
            completed_reads = {"stored": ["P0420"], "pending": ["U0123"]}
            failed_read = "permanent"
            reason = "uds-rejected"
            rejection_subtype = "service-not-supported"
        got = safe_dtc_snapshot(error=Error())
        self.assertEqual(got, {"stored": ["P0420"], "pending": ["U0123"],
                               "permanent": None, "permanent_reason": "service-not-supported",
                               "status": "partial"})
        bundle = dashboard_bundle()
        self.assertIn("SIMULATED", bundle)
        self.assertIn("No fault clearing", bundle)
        self.assertIn("permanent_reason", bundle)

    def test_dtc_display_uses_only_allowlisted_descriptions_and_unknown_fallback(self):
        mapping = (Path(__file__).parents[1] / "frontend" / "src" / "lib" / "dtc-descriptions.ts").read_text(encoding="utf-8")
        mapped_codes = re.findall(r"^\s*([PBCU][0-9A-F]{4}):", mapping, re.MULTILINE)
        self.assertEqual(mapped_codes, ["P0420"])
        self.assertIn("SAE J2012", mapping)
        self.assertIn("https://law.resource.org/pub/us/cfr/ibr/005/sae.j2012.2002.pdf", mapping)
        self.assertIn('"Catalyst system efficiency below threshold (Bank 1)"', mapping)
        bundle = dashboard_bundle()
        self.assertIn("Outstanding fault codes", bundle)
        self.assertNotIn("Emissions fault codes", bundle)
        self.assertIn("Description unavailable", bundle)
        self.assertIn("Catalyst system efficiency below threshold (Bank 1)", bundle)
        self.assertIn("code-value", bundle)
        self.assertIn("SAMPLE ERROR", bundle)
        self.assertIn("NO SAMPLE", bundle)
        self.assertIn("VERIFIED SIGNAL", bundle)

    def test_temperature_missing_and_error_samples_are_not_success_states(self):
        frontend = (Path(__file__).parents[1] / "frontend" / "src" / "dashboard.tsx").read_text(encoding="utf-8")
        self.assertIn('const sampleStatus = !sample || sample.quality === "simulated" ? "warning"', frontend)
        self.assertIn('sample.quality === "good" && sample.value !== null ? "success" : "error"', frontend)

        with patch("supra_telemetry.client_dashboard.read_emissions_dtcs",
                   side_effect=RuntimeError("private socket details")):
            unavailable = run_live_dtc_snapshot("capture")
        self.assertEqual(unavailable["permanent_reason"], "unexpected-error")
        self.assertNotIn("private", repr(unavailable))

    def test_http_api_state_contains_only_safe_samples_and_allowlisted_error(self):
        class Source:
            halted = True
            connected = False
            halt_reason = "secret ip 10.0.0.1"
            def read(self): return []
        engine = AcquisitionEngine(source=Source())
        engine.latest = {"engine_rpm": Sample("engine_rpm", 850, "rpm", "hsfz",
            "measured", "good", "now", 1)}
        state = dashboard_state(engine, engine.source, "live", {
            "stored": [], "pending": [], "permanent": None,
            "permanent_reason": "service-not-supported", "status": "partial"})
        encoded = json.dumps(state)
        self.assertEqual(state["acquisition_error"], "unexpected-error")
        self.assertIn('"engine_rpm"', encoded)
        self.assertNotIn("secret ip", encoded)
        self.assertNotIn("raw_hex", encoded)

        simulated = DashboardSimSource(monotonic=lambda: 1.0)
        simulated_engine = AcquisitionEngine(source=simulated)
        simulated_engine.step()
        handler = make_dashboard_handler(simulated_engine, simulated, "simulated", {
            "stored": ["P0420"], "pending": [], "permanent": [],
            "permanent_reason": None, "status": "simulated"})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with urlopen(f"http://127.0.0.1:{server.server_port}/api/state", timeout=2) as response:
                payload = json.loads(response.read())
            self.assertEqual(payload["mode"], "simulated")
            self.assertEqual({s["signal_id"] for s in payload["samples"]}, {s.id for s in SIGNALS})
            self.assertEqual(payload["dtcs"]["stored"], ["P0420"])
        finally:
            server.shutdown(); thread.join(2); server.server_close()

    def test_http_serves_bundled_dashboard_assets_and_rejects_traversal(self):
        source = DashboardSimSource()
        engine = AcquisitionEngine(source=source)
        handler = make_dashboard_handler(engine, source, "simulated", {
            "stored": [], "pending": [], "permanent": [],
            "permanent_reason": None, "status": "simulated"})
        server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urlopen(base + "/", timeout=2) as response:
                html = response.read().decode("utf-8")
                self.assertEqual(response.headers.get_content_type(), "text/html")
                self.assertEqual(response.headers.get("Cache-Control"), "no-cache")
            self.assertIn("GR Supra", html)
            asset = re.search(r'(?:src|href)="\./(assets/[^\"]+\.js)"', html)
            self.assertIsNotNone(asset)
            with urlopen(base + "/" + asset.group(1), timeout=2) as response:
                self.assertEqual(response.headers.get_content_type(), "text/javascript")
                self.assertIn("immutable", response.headers.get("Cache-Control", ""))
                self.assertGreater(len(response.read()), 1000)
            with self.assertRaises(HTTPError) as failure:
                urlopen(base + "/assets/%2e%2e%2fpyproject.toml", timeout=2)
            self.assertEqual(failure.exception.code, 404)
        finally:
            server.shutdown(); thread.join(2); server.server_close()

    def test_primary_temperature_type_scale_dominates_rpm(self):
        styles = (Path(__file__).parents[1] / "frontend" / "src" / "index.css").read_text(encoding="utf-8")
        temperature = re.search(r"\.temp-value\s*\{[^}]*font-size:\s*clamp\(\s*(\d+)px,[^,]+,\s*(\d+)px\)", styles)
        rpm = re.search(r"\.rpm-value\s*\{[^}]*font-size:\s*clamp\(\s*(\d+)px,[^,]+,\s*(\d+)px\)", styles)
        self.assertIsNotNone(temperature)
        self.assertIsNotNone(rpm)
        self.assertGreater(int(temperature.group(2)), int(rpm.group(2)))

    def test_third_party_notice_is_a_persistent_build_and_package_asset(self):
        project_root = Path(__file__).parents[1]
        source_notice = project_root / "frontend" / "public" / "THIRD_PARTY_NOTICES.txt"
        built_notice = STATIC_ROOT / "THIRD_PARTY_NOTICES.txt"
        self.assertEqual(source_notice.read_bytes(), built_notice.read_bytes())
        package_config = (project_root / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn('"dashboard_static/THIRD_PARTY_NOTICES.txt"', package_config)

    def test_simulated_source_has_exact_six_ids_and_no_network_surface(self):
        source = DashboardSimSource(monotonic=lambda: 2.0)
        samples = source.read()
        self.assertEqual({s.signal_id for s in samples}, {s.id for s in SIGNALS})
        self.assertTrue(all(s.quality == "simulated" for s in samples))
        self.assertFalse(hasattr(source, "client"))
        self.assertFalse(hasattr(source, "connector"))
        self.assertEqual([s.signal_id for s in source.read()], ["engine_rpm"])

    def test_cli_validation_and_mode_wiring(self):
        from supra_telemetry import __main__ as cli
        with patch.object(cli, "serve_client_dashboard", return_value=0) as serve:
            self.assertEqual(cli.main(["client-dashboard", "--mode", "simulated"]), 0)
            self.assertEqual(serve.call_args.kwargs["mode"], "simulated")
        with self.assertRaises(SystemExit):
            cli.main(["client-dashboard", "--mode", "live"])
        with self.assertRaises(SystemExit):
            cli.main(["client-dashboard", "--mode", "simulated", "--capture", "private"])
        with patch.object(cli, "run_live_dtc_snapshot", return_value={
                "stored": [], "pending": [], "permanent": None,
                "permanent_reason": "uds-rejected", "status": "partial"}), \
             patch.object(cli, "DashboardLiveSource") as make_source, \
             contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cli.main(["client-dashboard", "--mode", "live", "--capture", "private"]), 1)
            make_source.assert_not_called()

    def test_live_cli_binds_before_vehicle_reads_and_waits_before_monitor(self):
        from supra_telemetry import __main__ as cli
        events = []
        class Server:
            server_port = 12345
            def server_close(self): events.append("closed")
        result = {"stored": [], "pending": [], "permanent": [],
                  "permanent_reason": None, "status": "complete"}
        with patch.object(cli, "reserve_dashboard_server", side_effect=lambda *_: events.append("bind") or Server()), \
             patch.object(cli, "run_live_dtc_snapshot", side_effect=lambda *_: events.append("dtc") or result), \
             patch.object(cli, "wait_after_dtc_snapshot", side_effect=lambda: events.append("gap")), \
             patch.object(cli, "DashboardLiveSource", side_effect=lambda *_a, **_k: events.append("source") or object()), \
             patch.object(cli, "serve_client_dashboard", side_effect=lambda *_a, **_k: events.append("serve") or 0):
            self.assertEqual(cli.main(["client-dashboard", "--mode", "live", "--capture", "private"]), 0)
        self.assertEqual(events, ["bind", "dtc", "gap", "source", "serve"])

    def test_live_cli_occupied_port_prevents_vehicle_calls(self):
        from supra_telemetry import __main__ as cli
        server = ThreadingHTTPServer(("127.0.0.1", 0), lambda *_: None)
        listener = threading.Thread(target=server.serve_forever, daemon=True)
        listener.start()
        try:
            with patch.object(cli, "run_live_dtc_snapshot") as dtc, \
                 patch.object(cli, "DashboardLiveSource") as source, \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(cli.main(["client-dashboard", "--mode", "live", "--capture", "private",
                                           "--port", str(server.server_port)]), 1)
            dtc.assert_not_called(); source.assert_not_called()
            self.assertEqual(json.loads(output.getvalue())["reason"], "dashboard-bind-failed")
        finally:
            server.shutdown(); listener.join(2); server.server_close()

    def test_dtc_requests_are_spaced_with_injected_clock(self):
        from supra_telemetry.emissions_dtcs import read_emissions_dtcs
        with tempfile.TemporaryDirectory() as td:
            path = capture(td); clock, starts, waits = [0.0], [], []
            class Client:
                def request(self, payload):
                    starts.append(clock[0])
                    service = payload[0]
                    return bytes((service + 0x40, 0))
                def close(self): pass
            def wait(delay):
                waits.append(delay); clock[0] += delay
            result = read_emissions_dtcs(path, client_factory=lambda *_a, **_k: Client(),
                                         monotonic=lambda: clock[0], wait=wait,
                                         min_request_interval=1.0)
            self.assertEqual(result["requests_sent"], 3)
            self.assertTrue(all(b-a >= 1 for a, b in zip(starts, starts[1:])))
            self.assertEqual(waits, [1.0, 1.0])

    def test_prebound_server_closes_if_worker_start_fails(self):
        class Source:
            def close(self): self.closed = True
        class BadWorker:
            def __init__(self, **_): pass
            def start(self): raise RuntimeError("private details")
        source = Source()
        server = reserve_dashboard_server("127.0.0.1", 0)
        port = server.server_port
        with self.assertRaises(RuntimeError):
            serve_client_dashboard(source, mode="live", dtcs={}, server=server,
                                   worker_factory=BadWorker)
        self.assertTrue(source.closed)
        reopened = ThreadingHTTPServer(("127.0.0.1", port), lambda *_: None)
        reopened.server_close()

    def test_source_construction_failure_is_redacted_and_closes_reserved_server(self):
        from supra_telemetry import __main__ as cli
        events = []
        class Server:
            def server_close(self): events.append("closed")
        with patch.object(cli, "reserve_dashboard_server", return_value=Server()), \
             patch.object(cli, "run_live_dtc_snapshot", return_value={"status": "complete"}), \
             patch.object(cli, "wait_after_dtc_snapshot"), \
             patch.object(cli, "DashboardLiveSource", side_effect=RuntimeError("secret path 10.2.3.4")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(["client-dashboard", "--mode", "live", "--capture", "private"]), 1)
        self.assertEqual(events, ["closed"])
        self.assertEqual(json.loads(output.getvalue())["reason"], "source-unavailable")
        self.assertNotIn("secret", output.getvalue())

    def test_post_dtc_wait_failure_is_redacted_and_closes_reserved_server(self):
        from supra_telemetry import __main__ as cli
        events = []
        class Server:
            def server_close(self): events.append("closed")
        with patch.object(cli, "reserve_dashboard_server", return_value=Server()), \
             patch.object(cli, "run_live_dtc_snapshot", return_value={"status": "complete"}), \
             patch.object(cli, "wait_after_dtc_snapshot",
                          side_effect=RuntimeError("secret timing detail")), \
             patch.object(cli, "DashboardLiveSource") as source, \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(["client-dashboard", "--mode", "live",
                                       "--capture", "private"]), 1)
        source.assert_not_called()
        self.assertEqual(events, ["closed"])
        self.assertEqual(json.loads(output.getvalue())["reason"], "source-unavailable")
        self.assertNotIn("secret", output.getvalue())

    def test_cli_redacts_dashboard_serving_failure(self):
        from supra_telemetry import __main__ as cli
        result = {"stored": [], "pending": [], "permanent": [],
                  "permanent_reason": None, "status": "complete"}
        with patch.object(cli, "reserve_dashboard_server", return_value=object()), \
             patch.object(cli, "run_live_dtc_snapshot", return_value=result), \
             patch.object(cli, "wait_after_dtc_snapshot"), \
             patch.object(cli, "DashboardLiveSource", return_value=object()), \
             patch.object(cli, "serve_client_dashboard", side_effect=RuntimeError("private bind data")), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(cli.main(["client-dashboard", "--mode", "live", "--capture", "private"]), 1)
        self.assertEqual(json.loads(output.getvalue())["reason"], "dashboard-stopped")
        self.assertNotIn("private bind", output.getvalue())

    def test_concurrent_latest_updates_do_not_break_state_snapshot(self):
        class ChangingLatest(dict):
            def values(self):
                raise RuntimeError("dictionary changed size during iteration")
        class Source:
            halted = connected = False
        engine = AcquisitionEngine(source=Source())
        engine.latest = ChangingLatest()
        state = dashboard_state(engine, engine.source, "live", {})
        self.assertEqual(state["samples"], [])


if __name__ == "__main__":
    unittest.main()
