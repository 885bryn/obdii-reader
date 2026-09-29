import contextlib
import hashlib
import io
import json
import os
import sqlite3
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from supra_telemetry import capture_harness as harness
from supra_telemetry import __main__ as cli
from supra_telemetry.client_dashboard import SIGNALS
from supra_telemetry.models import SignalDefinition
from supra_telemetry.storage import TelemetryStore


def write_valid_decoded_database(path, *, ended=True):
    store = TelemetryStore(path)
    session = store.start_session("2026-09-29T00:00:00+00:00", mode="drive-session")
    for signal in SIGNALS:
        store.register(session, SignalDefinition(
            signal.id, signal.name, signal.unit,
            provenance="standard decoded signal", confidence=signal.confidence,
            verification=signal.verification, enabled=True))
    if ended:
        store.end_session(session, "2026-09-29T00:30:00+00:00")
    store.close()
    return session


class FakeProcess:
    def __init__(self, mode="complete", env=None):
        self.mode = mode
        self.env = env
        self.returncode = None
        self.argv = None
        self.terminated = False
        self.signals = []
        self.killed = False

    def wait(self, timeout=None):
        if self.env is not None:
            self.env.process_waits.append(timeout)
        if self.returncode is not None:
            return self.returncode
        if self.mode in ("timeout", "stubborn"):
            self.env.clock += timeout or 0
            raise subprocess.TimeoutExpired(self.argv, timeout)
        if self.mode == "interrupt":
            raise KeyboardInterrupt()
        if self.mode == "peer-close":
            self.returncode = 1
        else:
            self.returncode = 0
        return self.returncode

    def poll(self):
        return self.returncode

    def send_signal(self, sig):
        self.signals.append(sig)
        if self.mode != "stubborn":
            self.returncode = 130

    def terminate(self):
        self.terminated = True
        if self.mode != "stubborn":
            self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9


class FakeEnvironment:
    pktmon = "pktmon"
    wevtutil = "wevtutil"
    tracerpt = "tracerpt"

    def __init__(self, *, app="complete", failures=None, providers=None,
                 metadata=None, stats=None, free=harness.MIN_FREE_BYTES,
                 windows=True, admin=True):
        self.app = app
        self.failures = set(failures or ())
        self.providers = providers or list(harness.PROVIDERS)
        self.metadata = metadata if metadata is not None else "\n".join(self.providers)
        self.stats = stats if stats is not None else (
            "trace_start_epoch=100 lost_events=0 internal_errors=0 overwrite=0 "
            "trace_stop_epoch=200")
        self.free = free
        self.windows = windows
        self.admin = admin
        self.calls = []
        self.clock = 100
        self.process = None
        self.filter_added = False
        self.capture_active = False
        self.filter_list_count = 0
        self.unexpected_filter_at = None
        self.health_loss_after = None
        self.low_disk_after = None
        self.health_checks = 0
        self.wait_calls = []
        self.process_waits = []
        self.stop_leaves_active = False
        self.start_output = "Packet Monitor started"

    def is_windows(self): return self.windows
    def is_admin(self): return self.admin
    def free_bytes(self, path):
        if self.low_disk_after is not None and self.health_checks >= self.low_disk_after:
            return 1
        return self.free
    def now(self):
        self.clock += .1
        return self.clock
    def monotonic(self): return self.clock
    def wait(self, event, duration):
        self.wait_calls.append(duration)
        self.clock += duration
        event.wait(0)
        time.sleep(0)
        return event.is_set()
    def create_process_group(self): return 0
    def file_version(self, path): return "fixture-version"

    def run(self, argv, timeout=30):
        self.calls.append(list(argv))
        joined = " ".join(str(v) for v in argv).lower()
        if argv and argv[0] == "pktmon" and not self.valid_pktmon_argv(argv):
            return SimpleNamespace(returncode=2, stdout="", stderr="invalid fixture command")
        if any(marker in joined for marker in self.failures):
            return SimpleNamespace(returncode=1, stdout="", stderr="private details")
        if "start help" in joined:
            return SimpleNamespace(returncode=0,
                stdout="--flags 0x001 0x002 0x004 0x008 0x010 0x020", stderr="")
        if argv[0] == "pktmon" and argv[1:] == ["status"]:
            if self.capture_active:
                self.health_checks += 1
            active = self.capture_active and not (
                self.health_loss_after is not None and self.health_checks >= self.health_loss_after)
            status = "Packet Monitor is running" if active else "Packet Monitor is stopped"
            return SimpleNamespace(returncode=0, stdout=status, stderr="")
        if "filter list" in joined:
            self.filter_list_count += 1
            if self.filter_list_count == self.unexpected_filter_at:
                return SimpleNamespace(returncode=0, stdout=(
                    "Packet Filters:\n"
                    "  supra-capture-harness-owned TCP port 6801\n"
                    "  externally-added UDP port 1234"), stderr="")
            text = ("Packet Filters:\n  supra-capture-harness-owned TCP port 6801"
                    if self.filter_added else "No filters")
            return SimpleNamespace(returncode=0, stdout=text, stderr="")
        if argv[:2] == ["wevtutil", "ep"]:
            return SimpleNamespace(returncode=0, stdout="\n".join(self.providers), stderr="")
        if "filter add" in joined:
            self.filter_added = True
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv[:2] == ["pktmon", "start"]:
            self.capture_active = True
            etl_arg = argv[argv.index("--file-name") + 1]
            Path(etl_arg).write_bytes(b"authoritative-etl")
            return SimpleNamespace(returncode=0, stdout=self.start_output, stderr="")
        if argv[:2] == ["pktmon", "stop"]:
            if not self.stop_leaves_active:
                self.capture_active = False
            return SimpleNamespace(returncode=0, stdout="Packet Monitor stopped", stderr="")
        if "filter remove" in joined:
            self.filter_added = False
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if "etl2txt" in joined:
            if "--out" in argv:
                Path(argv[argv.index("--out") + 1]).write_text(
                    "private packets\n" + "\n".join(self.providers), encoding="utf-8")
                return SimpleNamespace(returncode=0, stdout="", stderr="")
            if "--stats" in argv:
                return SimpleNamespace(returncode=0, stdout=self.stats, stderr="")
        if "etl2pcap" in joined:
            Path(argv[argv.index("--out") + 1]).write_bytes(b"pcap fixture")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv[0] == "tracerpt":
            if "-?" in argv:
                return SimpleNamespace(returncode=1, stdout="TraceRpt Usage: tracerpt [options]", stderr="")
            for flag in ("-o", "-summary", "-report"):
                Path(argv[argv.index(flag) + 1]).write_text("private trace fixture", encoding="utf-8")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if argv[0] == "wevtutil" and "epl" in argv:
            Path(argv[3]).write_bytes(b"private event log")
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        # host evidence commands
        return SimpleNamespace(returncode=0, stdout="private host value\n", stderr="")

    @staticmethod
    def valid_pktmon_argv(argv):
        args = argv[1:]
        if args == ["start", "help"] or args == ["status"] or args == ["filter", "list"]:
            return True
        if args[:2] == ["filter", "add"]:
            return args[2:] == [harness.FILTER_NAME, "-t", "TCP", "-p", "6801"]
        if args == ["filter", "remove"] or args == ["stop"] or args == ["list"]:
            return True
        if args and args[0] == "start":
            required = ["start", "--capture", "--comp", "all", "--type", "all",
                        "--pkt-size", "0", "--flags", "0x03F", "--trace"]
            if args[:len(required)] != required:
                return False
            providers, cursor = [], len(required)
            while cursor < len(args) and args[cursor] == "--provider":
                if args[cursor + 2:cursor + 5] != ["--keywords", "0xFFFFFFFFFFFFFFFF", "--level"]:
                    return False
                if cursor + 5 >= len(args) or args[cursor + 5] != "5":
                    return False
                providers.append(args[cursor + 1])
                cursor += 6
            suffix = ["--file-name", args[cursor + 1] if cursor + 1 < len(args) else "",
                      "--file-size", "4096", "--log-mode", "circular"]
            return providers == list(harness.PROVIDERS) and args[cursor:] == suffix
        if args and args[0] == "etl2txt":
            if len(args) == 3 and args[2:] == ["--stats"]:
                return True
            return (len(args) == 6 and args[2] == "--out" and args[4:] ==
                    ["--verbose", "--metadata"])
        if args and args[0] == "etl2pcap":
            return (len(args) == 4 and args[2] == "--out") or (
                    len(args) == 5 and args[2] == "--out" and args[4] == "--drop-only")
        return False

    def popen(self, argv, **kwargs):
        self.calls.append(list(argv))
        if "--db" in argv:
            write_valid_decoded_database(Path(argv[argv.index("--db") + 1]))
        self.process = FakeProcess(self.app, self)
        self.process.argv = argv
        return self.process

    def send_graceful(self, process):
        process.send_signal("graceful")


class CaptureHarnessTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.private = self.root / "captures" / "private"
        self.private.mkdir(parents=True)
        self.output = self.private / "candidate"
        self.capture = self.root / "discovery.json"
        self.capture.write_text("{}", encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def invoke(self, env=None, *, normalized=False, **kwargs):
        evidence = harness.CoverageEvidence(0, 10**10, 0, 0, False,
                                             frozenset(harness.PROVIDERS))
        with patch.object(harness, "parse_native_coverage",
                          return_value=evidence if normalized else harness.CoverageEvidence()):
            return harness.run_capture(self.capture, self.output,
                confirm_private_raw_capture=True, repo_root=self.root,
                env=env or FakeEnvironment(), **kwargs)

    def test_clean_completion_exact_child_argv_manifest_hashes_and_privacy(self):
        env = FakeEnvironment()
        status, category = self.invoke(env, normalized=True)
        self.assertEqual((status, category), (0, "complete"))
        child = next(call for call in env.calls if call and call[0] == os.sys.executable)
        self.assertEqual(child, harness.child_argv(self.capture.resolve(),
                         self.output.resolve() / "decoded.sqlite"))
        start = next(call for call in env.calls if call[:2] == ["pktmon", "start"]
                     and "--capture" in call)
        self.assertEqual(start[start.index("--flags") + 1], "0x03F")
        self.assertEqual([start[index + 1] for index, value in enumerate(start)
                          if value == "--provider"], list(harness.PROVIDERS))
        self.assertTrue(all(start[index + 3] == "0xFFFFFFFFFFFFFFFF" and start[index + 5] == "5"
                            for index, value in enumerate(start) if value == "--provider"))
        manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertTrue(manifest["filter_removed"])
        self.assertTrue(manifest["coverage"]["coverage_passed"])
        self.assertEqual(manifest["artifacts"]["capture.etl"]["sha256"],
                         hashlib.sha256(b"authoritative-etl").hexdigest())
        self.assertNotIn(str(self.root), json.dumps({"console": category}))

    def test_native_start_configuration_output_relies_on_active_status_proof(self):
        env = FakeEnvironment()
        env.start_output = "Logger Parameters:\nLogging mode: Circular\n"
        self.assertEqual(self.invoke(env, normalized=True), (0, "complete"))
        self.assertIn(["pktmon", "status"], env.calls)

    def test_nonzero_child_exit_still_returns_finalized_valid_evidence_without_retry(self):
        env = FakeEnvironment(app="peer-close")
        status, category = self.invoke(env, normalized=True)
        self.assertEqual((status, category), (1, "captured-application-failure"))
        self.assertEqual(sum(call and call[0] == os.sys.executable for call in env.calls), 1)
        manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["application_exit_code"], 1)
        self.assertTrue(manifest["evidence_bundle_finalized"])

    def test_native_coverage_remains_unverified(self):
        status, category = self.invoke(FakeEnvironment())
        self.assertEqual((status, category), (1, "coverage-unverified"))
        manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(manifest["evidence_bundle_finalized"])

    def test_health_loss_and_low_disk_stop_child_with_fixed_reason(self):
        for field, value, category in (("health_loss_after", 3, "capture-health-lost"),
                                       ("low_disk_after", 3, "capture-disk-low")):
            with self.subTest(category=category):
                env = FakeEnvironment(app="timeout")
                setattr(env, field, value)
                status, reason = self.invoke(env)
                manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual((status, reason), (1, category))
                self.assertEqual(manifest["application_outcome"], category)
                self.assertEqual(manifest["child_shutdown_outcome"], "graceful-stop")
                self.assertTrue(all(value <= harness.HEALTH_POLL_SECONDS for value in
                                    env.process_waits[:-1]))
                self.output = self.private / ("candidate-" + field)

    def test_health_probe_timeout_is_bounded_below_poll_interval(self):
        env = FakeEnvironment()
        env.capture_active = True
        blocker = __import__("threading").Event()
        original = env.run
        def run(argv, timeout=30):
            if argv == ["pktmon", "status"]:
                blocker.wait(1)
            return original(argv, timeout)
        env.run = run
        started = time.monotonic()
        with patch.object(harness, "HEALTH_STATUS_SECONDS", .02):
            self.assertEqual(harness._capture_health(env, self.private),
                             "capture-health-lost")
        self.assertLess(time.monotonic() - started, .25)
        self.assertLess(harness.HEALTH_STATUS_SECONDS + harness.HEALTH_DISK_SECONDS,
                        harness.HEALTH_POLL_SECONDS)

    def test_rehearsal_health_check_stops_loopback_exchange(self):
        env = FakeEnvironment()
        checks = 0
        def health():
            nonlocal checks
            checks += 1
            return "capture-disk-low" if checks == 2 else None
        self.assertEqual(harness._run_rehearsal(.6, env.monotonic() + 2, env,
                                                port=0, health_check=health), "capture-disk-low")

    def test_missing_or_empty_artifact_prevents_finalization(self):
        for target in ("capture-drops.pcapng", "tracerpt-report.xml", "system-events.evtx"):
            with self.subTest(target=target):
                env = FakeEnvironment()
                original = env.run
                def run(argv, timeout=30):
                    result = original(argv, timeout)
                    path = self.output / target
                    if path.exists():
                        path.write_bytes(b"")
                    return result
                env.run = run
                status, category = self.invoke(env, normalized=True)
                manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
                self.assertEqual((status, category), (1, "evidence-invalid"))
                self.assertFalse(manifest["required_artifacts_complete"])
                self.output = self.private / ("candidate-" + target)

    def test_required_artifact_inventory_checks_every_file(self):
        required = ("pktmon-start-help.txt", "pktmon-preflight-status.txt",
                    "pktmon-filter-pre.txt", "pktmon-filter-owned.txt",
                    "pktmon-filter-active.txt", "pktmon-start.txt",
                    "pktmon-running-status.txt", "pktmon-stop.txt",
                    "pktmon-stopped-status.txt", "pktmon-filter-cleanup.txt",
                    "pktmon-filter-restored.txt", "host-pre.txt", "host-post.txt",
                    "capture.etl", "capture.pcapng", "capture-drops.pcapng",
                    "capture.txt", "capture-stats.txt", "tracerpt-summary.txt",
                    "tracerpt-report.xml", "tracerpt-events.xml", "system-events.evtx")
        self.output.mkdir()
        for name in required:
            (self.output / name).write_bytes(b"evidence")
        for name in ("application.stdout", "application.stderr"):
            (self.output / name).write_bytes(b"")
        (self.output / "decoded.sqlite").write_bytes(b"sqlite fixture")
        self.assertTrue(harness._required_artifacts(self.output, rehearsal=False))
        for name in required:
            path = self.output / name
            path.write_bytes(b"")
            self.assertFalse(harness._required_artifacts(self.output, rehearsal=False), name)
            path.write_bytes(b"evidence")
            path.unlink()
            self.assertFalse(harness._required_artifacts(self.output, rehearsal=False), name)
            path.write_bytes(b"evidence")
        for name in ("application.stdout", "application.stderr"):
            path = self.output / name
            path.unlink()
            self.assertFalse(harness._required_artifacts(self.output, rehearsal=False), name)
            path.write_bytes(b"")
        database = self.output / "decoded.sqlite"
        database.write_bytes(b"")
        self.assertFalse(harness._required_artifacts(self.output, rehearsal=False), database.name)
        database.unlink()
        self.assertFalse(harness._required_artifacts(self.output, rehearsal=False), database.name)

    def test_decoded_database_requires_integrity_schema_finalized_session_and_no_raw(self):
        valid = self.private / "valid.sqlite"
        session = write_valid_decoded_database(valid)
        self.assertTrue(harness._validate_decoded_database(valid))

        corrupt = self.private / "corrupt.sqlite"
        corrupt.write_bytes(b"not sqlite")
        self.assertFalse(harness._validate_decoded_database(corrupt))

        wrong = self.private / "wrong.sqlite"
        db = sqlite3.connect(wrong)
        try:
            db.execute("CREATE TABLE unrelated(value TEXT)")
            db.commit()
        finally:
            db.close()
        self.assertFalse(harness._validate_decoded_database(wrong))

        unfinished = self.private / "unfinished.sqlite"
        write_valid_decoded_database(unfinished, ended=False)
        self.assertFalse(harness._validate_decoded_database(unfinished))

        raw = self.private / "raw.sqlite"
        write_valid_decoded_database(raw)
        db = sqlite3.connect(raw)
        try:
            db.execute("INSERT INTO raw_exchanges(session_id,timestamp_utc,transport,outcome) "
                       "VALUES (?,?,?,?)", (session, "now", "fixture", "ok"))
            db.commit()
        finally:
            db.close()
        self.assertFalse(harness._validate_decoded_database(raw))

    def test_post_add_filter_race_leaves_filters_for_manual_recovery(self):
        env = FakeEnvironment()
        env.unexpected_filter_at = 2
        status, category = self.invoke(env)
        manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((status, category), (1, "owned-filter-unconfirmed"))
        self.assertFalse(manifest["filter_removed"])
        self.assertNotIn(["pktmon", "filter", "remove"], env.calls)

    def test_preflight_rejects_non_windows_admin_low_space_tools_and_provider(self):
        for env, category in ((FakeEnvironment(windows=False), "windows-required"),
                              (FakeEnvironment(admin=False), "administrator-required"),
                              (FakeEnvironment(free=1), "insufficient-free-space"),
                              (FakeEnvironment(failures={"pktmon start help"}), "tool-failed"),
                              (FakeEnvironment(providers=harness.PROVIDERS[:-1]), "provider-unavailable")):
            with self.subTest(category=category):
                with self.assertRaisesRegex(harness.HarnessError, category):
                    harness._safe_preflight(env, self.output, self.root, self.capture)

    def test_preflight_rejects_running_pktmon_and_existing_filters(self):
        for environment, category in (("running", "pktmon-running-or-unknown"),
                                      ("filters", "pktmon-filters-present-or-unknown")):
            env = FakeEnvironment()
            original = env.run
            def run(argv, timeout=30, *, _original=original, _kind=environment):
                result = _original(argv, timeout)
                if _kind == "running" and argv == ["pktmon", "status"]:
                    return SimpleNamespace(returncode=0, stdout="Packet Monitor running", stderr="")
                if _kind == "filters" and argv == ["pktmon", "filter", "list"]:
                    return SimpleNamespace(returncode=0, stdout="Filter 1: existing", stderr="")
                return result
            env.run = run
            with self.subTest(category=category), self.assertRaisesRegex(harness.HarnessError, category):
                harness._safe_preflight(env, self.output, self.root, self.capture)

    def test_host_observed_empty_filter_layout_is_accepted_exactly(self):
        self.assertTrue(harness._no_filters_confirmed("Packet Filters:\n    None\n"))
        self.assertFalse(harness._no_filters_confirmed(
            "Packet Filters:\n    None\n    external filter\n"))

    def test_host_observed_owned_filter_layout_requires_exact_single_entry(self):
        observed = ("Packet Filters:\n"
                    "     # Name                        Protocol Port\n"
                    "     - ----                        -------- ----\n"
                    "     1 supra-capture-harness-owned TCP      6801\n")
        self.assertTrue(harness._owned_filter_is_confirmed(observed))
        self.assertFalse(harness._owned_filter_is_confirmed(
            observed + "     2 external                    UDP      1234\n"))

    def test_host_observed_active_status_requires_logger_capture_and_providers(self):
        observed = ("Collected Data:\n    Packet counters, packet capture\n\n"
                    "Capture Type:\n    All packets\n\n"
                    "Logger Parameters:\n    Logger name: PktMon\n\n"
                    "Event Providers:\n" +
                    "\n".join("    " + provider +
                              " 5 0xffffffffffffffff"
                              for provider in harness.PROVIDERS) +
                    "\n    Microsoft-Windows-PktMon 4 0x3f\n")
        self.assertTrue(harness._capture_active_confirmed(observed))
        self.assertTrue(harness._capture_active_confirmed(
            "Packet Monitor is running\n"))
        self.assertFalse(harness._capture_active_confirmed(
            observed + "\nPacket Monitor is not running.\n"))
        self.assertFalse(harness._capture_active_confirmed(
            observed.replace("Event Providers:", "Providers omitted:")))
        self.assertFalse(harness._capture_active_confirmed("Active filters: none\n"))
        self.assertFalse(harness._capture_active_confirmed(
            "Collected Data:\nCapture Type:\nLogger Parameters:\n"
            "Logger name: PktMon\nEvent Providers:\n"))
        self.assertFalse(harness._capture_active_confirmed(
            observed.replace("Microsoft-Windows-NDIS 5", "Microsoft-Windows-NDIS 4")))

    def test_preflight_rejects_outside_existing_and_bad_flag_surface(self):
        env = FakeEnvironment()
        with self.assertRaisesRegex(harness.HarnessError, "output-outside-private-root"):
            harness._safe_preflight(env, self.root / "outside", self.root, self.capture)
        self.output.mkdir()
        with self.assertRaisesRegex(harness.HarnessError, "output-not-fresh"):
            harness._safe_preflight(env, self.output, self.root, self.capture)
        self.output.rmdir()
        original = env.run
        env.run = lambda argv, timeout=30: (SimpleNamespace(returncode=0, stdout="--flags 0x01F", stderr="")
                    if argv == ["pktmon", "start", "help"] else original(argv, timeout))
        with self.assertRaisesRegex(harness.HarnessError, "pktmon-flags-unsupported"):
            harness._safe_preflight(env, self.output, self.root, self.capture)

    def test_app_deadline_interrupt_start_stop_and_conversion_failures_cleanup_filter(self):
        cases = ((FakeEnvironment(app="timeout"), "hard-deadline"),
                 (FakeEnvironment(app="interrupt"), "operator-interrupt"),
                 (FakeEnvironment(failures={"pktmon start --capture"}), "capture-start-unconfirmed"),
                 (FakeEnvironment(failures={"pktmon stop"}), "capture-stop-failed"),
                 (FakeEnvironment(failures={"etl2txt"}), "conversion-failed"))
        for env, expected in cases:
            with self.subTest(expected=expected):
                status, _ = self.invoke(env)
                manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
                if expected == "capture-start-unconfirmed":
                    self.assertEqual(status, 1)
                elif expected in ("hard-deadline", "operator-interrupt"):
                    self.assertEqual(manifest["application_outcome"], expected)
                elif expected == "capture-stop-failed":
                    self.assertIn(expected, manifest["cleanup_errors"])
                else:
                    self.assertIn(expected, manifest["cleanup_errors"])
                self.assertTrue(manifest["filter_removed"])
                self.output = self.private / "candidate"
                self.output = self.private / ("candidate-" + str(len(list(self.private.iterdir()))))

    def test_stubborn_child_and_false_success_stop_fail_within_hard_bound(self):
        env = FakeEnvironment(app="stubborn")
        status, category = self.invoke(env)
        manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual((status, category), (1, "hard-deadline"))
        self.assertLessEqual(manifest["capture_stop_monotonic"],
                             manifest["application_start_monotonic"] + harness.HARNESS_SECONDS)
        self.assertTrue(env.process.killed)

        self.output = self.private / "candidate-stop-unconfirmed"
        env = FakeEnvironment()
        env.stop_leaves_active = True
        status, _ = self.invoke(env, normalized=True)
        manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(status, 1)
        self.assertFalse(manifest["capture_stopped"])
        self.assertFalse(manifest["evidence_bundle_finalized"])
        self.assertIn("capture-stop-unconfirmed", manifest["cleanup_errors"])

    def test_coverage_fails_on_loss_overwrite_missing_provider_or_unverified_fields(self):
        args = dict(app_start=110, app_stop=190, trace_start=100, trace_stop=200)
        good = harness.CoverageEvidence(100, 200, 0, 0, False, frozenset(harness.PROVIDERS))
        self.assertTrue(harness.evaluate_coverage(good, **args)["coverage_passed"])
        from dataclasses import replace
        for evidence in (replace(good, lost_events=1),
                         replace(good, overwritten_application_interval=True),
                         replace(good, active_providers=frozenset(harness.PROVIDERS[1:])),
                         harness.CoverageEvidence()):
            self.assertFalse(harness.evaluate_coverage(evidence, **args)["coverage_passed"])
        fake_native = " ".join(harness.PROVIDERS) + " trace_start_epoch=100 trace_stop_epoch=200 lost_events=0 internal_errors=0 overwrite=0"
        self.assertFalse(harness.evaluate_coverage(
            harness.parse_native_coverage(fake_native, fake_native), **args)["coverage_passed"])

    def test_rehearsal_refuses_capture_and_duration_over_limit(self):
        env = FakeEnvironment()
        with self.assertRaisesRegex(harness.HarnessError, "invalid-rehearsal-request"):
            harness.run_capture(self.capture, self.output, confirm_private_raw_capture=True,
                repo_root=self.root, env=env, rehearsal_duration=5)

    def test_partial_local_hsfz_fixture_and_cli_confirmation_gate(self):
        left, right = __import__("socket").socketpair()
        try:
            right.sendall(b"ab")
            right.close()
            with self.assertRaises(EOFError):
                harness._socket_read_exact(left, 4)
        finally:
            left.close()
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(io.StringIO()), \
                patch.object(cli, "run_capture") as run:
            with self.assertRaises(SystemExit):
                cli.main(["capture-harness", "--capture", str(self.capture),
                          "--output", str(self.output)])
        run.assert_not_called()

    def test_start_failure_removes_only_owned_filter_and_never_launches_app(self):
        env = FakeEnvironment(failures={"pktmon start --capture"})
        status, category = self.invoke(env)
        self.assertEqual(status, 1)
        self.assertEqual(category, "tool-failed")
        self.assertIn(["pktmon", "filter", "remove"], env.calls)
        self.assertFalse(env.filter_added)
        self.assertFalse(any(call and call[0] == os.sys.executable for call in env.calls))

    def test_cleanup_leaves_unexpected_filter_set_untouched_for_manual_recovery(self):
        env = FakeEnvironment()
        env.unexpected_filter_at = 4
        status, _ = self.invoke(env)
        manifest = json.loads((self.output / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(status, 1)
        self.assertIn("unexpected-filters-present-manual-recovery", manifest["cleanup_errors"])
        self.assertFalse(manifest["filter_removed"])
        self.assertTrue(env.filter_added)
        self.assertNotIn(["pktmon", "filter", "remove"], env.calls)

    def test_rehearsal_loopback_happy_path_uses_short_fast_timing_and_valid_ack(self):
        env = FakeEnvironment()
        deadline = env.monotonic() + 2
        self.assertEqual(harness._run_rehearsal(.6, deadline, env, port=0), "completed")
        self.assertGreaterEqual(len(env.wait_calls), 2)
        self.assertTrue(all(wait == .2 for wait in env.wait_calls))

    def test_metadata_uses_host_supported_pktmon_syntax_and_event_window_covers_35_minutes(self):
        env = FakeEnvironment()
        etl = self.private / "source.etl"
        etl.write_bytes(b"fixture")
        harness._metadata(env, etl, self.private)
        commands = [call for call in env.calls if call[:2] == ["pktmon", "etl2txt"]]
        self.assertEqual(commands, [
            ["pktmon", "etl2txt", str(etl), "--out", str(self.private / "capture.txt"),
             "--verbose", "--metadata"],
            ["pktmon", "etl2txt", str(etl), "--stats"],
        ])
        self.assertTrue((self.private / "tracerpt-summary.txt").exists())
        env.clock = 2200
        harness._export_system_window(env, self.private, capture_start_epoch=100)
        event_command = next(call for call in env.calls if call[:2] == ["wevtutil", "epl"])
        window = int(event_command[-1].split("<= ", 1)[1].split("]", 1)[0])
        self.assertGreaterEqual(window, 2160000)


if __name__ == "__main__":
    unittest.main()
