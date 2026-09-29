"""Private, bounded Windows Packet Monitor capture wrapper for drive-session.

All external system interaction is behind CaptureEnvironment so offline tests can
exercise lifecycle and failure paths without starting Packet Monitor or vehicle
traffic.
"""
from __future__ import annotations

import ctypes
from contextlib import closing
import hashlib
import json
import os
import platform
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


MIN_FREE_BYTES = 10 * 1024 ** 3
APPLICATION_SECONDS = 1800
HARNESS_SECONDS = 1860
REHEARSAL_MAX_SECONDS = 2100
HEALTH_POLL_SECONDS = 5
HEALTH_STATUS_SECONDS = 1.5
HEALTH_DISK_SECONDS = 1
CHILD_SHUTDOWN_SECONDS = 17
CAPTURE_STOP_SECONDS = 35
CAPTURE_STATUS_SECONDS = 3
SHUTDOWN_RESERVE_SECONDS = (CHILD_SHUTDOWN_SECONDS + CAPTURE_STOP_SECONDS +
                            CAPTURE_STATUS_SECONDS)
FILTER_NAME = "supra-capture-harness-owned"
PROVIDERS = (
    "Microsoft-Windows-NDIS", "Microsoft-Windows-TCPIP",
    "Microsoft-Windows-DriverFrameworks-UserMode", "Microsoft-Windows-Kernel-PnP",
    "Microsoft-Windows-USB-USBHUB3", "Microsoft-Windows-USB-USBXHCI",
    "Microsoft-Windows-Dhcp-Client", "Microsoft-Windows-NetworkProfile",
    "Microsoft-Windows-Wired-AutoConfig",
)


class HarnessError(RuntimeError):
    """Safe-category harness failure."""


def utc_stamp():
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def artifact_inventory(root: Path):
    result = {}
    for path in sorted(root.rglob("*")):
        if path.is_file():
            result[path.relative_to(root).as_posix()] = {
                "size_bytes": path.stat().st_size, "sha256": sha256_file(path)}
    return result


def child_argv(capture: Path, db: Path):
    return [sys.executable, "-m", "supra_telemetry", "drive-session",
            "--capture", str(capture), "--db", str(db), "--duration", "1800",
            "--timeout", "2.0", "--ui-host", "127.0.0.1", "--port", "8765",
            "--confirm-hands-off"]


@dataclass(frozen=True)
class CoverageEvidence:
    """Verified facts supplied by a host-specific native output parser."""
    trace_start_epoch: float | None = None
    trace_stop_epoch: float | None = None
    lost_events: int | None = None
    internal_errors: int | None = None
    overwritten_application_interval: bool | None = None
    active_providers: frozenset[str] = frozenset()


def parse_native_coverage(metadata_text: str, stats_text: str) -> CoverageEvidence:
    """No native field layout has yet been observed and verified on this host.

    In particular, provider names or synthetic key=value strings are not proof.
    Keep the production gate closed until a native rehearsal establishes fields.
    """
    return CoverageEvidence()


def evaluate_coverage(evidence: CoverageEvidence, *, app_start: float,
                      app_stop: float, trace_start: float, trace_stop: float,
                      expected_providers=PROVIDERS):
    time_covered = (trace_start <= app_start <= app_stop <= trace_stop and
                    evidence.trace_start_epoch is not None and
                    evidence.trace_stop_epoch is not None and
                    evidence.trace_start_epoch <= app_start and
                    evidence.trace_stop_epoch >= app_stop)
    missing = set(expected_providers) - set(evidence.active_providers)
    result = {
        "trace_covers_application": time_covered,
        "lost_events_clear": evidence.lost_events == 0,
        "internal_errors_clear": evidence.internal_errors == 0,
        "application_interval_overwrite_clear": evidence.overwritten_application_interval is False,
        "missing_provider_count": len(missing),
    }
    result["coverage_passed"] = bool(time_covered and not missing and
        result["lost_events_clear"] and result["internal_errors_clear"] and
        result["application_interval_overwrite_clear"])
    return result


class CaptureEnvironment:
    """Thin OS boundary; methods are replaceable with fakes in unit tests."""
    def __init__(self):
        self.pktmon = shutil.which("pktmon")
        self.wevtutil = shutil.which("wevtutil")
        self.tracerpt = shutil.which("tracerpt")

    @staticmethod
    def is_windows():
        return os.name == "nt"

    @staticmethod
    def is_admin():
        try:
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except (AttributeError, OSError):
            return False

    def run(self, argv, *, timeout=30):
        return subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                              check=False, shell=False)

    def free_bytes(self, path):
        return shutil.disk_usage(path).free

    def now(self):
        return time.time()

    def monotonic(self):
        return time.monotonic()

    @staticmethod
    def wait(event, duration):
        return event.wait(duration)

    def popen(self, argv, **kwargs):
        return subprocess.Popen(argv, **kwargs)

    def create_process_group(self):
        return getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    @staticmethod
    def file_version(path):
        if os.name != "nt" or not path:
            return "unknown"
        try:
            version_api = ctypes.WinDLL("version", use_last_error=True)
            version_api.GetFileVersionInfoSizeW.argtypes = [ctypes.c_wchar_p,
                                                            ctypes.POINTER(ctypes.c_uint)]
            version_api.GetFileVersionInfoSizeW.restype = ctypes.c_uint
            version_api.GetFileVersionInfoW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint,
                                                        ctypes.c_uint, ctypes.c_void_p]
            version_api.GetFileVersionInfoW.restype = ctypes.c_int
            version_api.VerQueryValueW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p,
                                                   ctypes.POINTER(ctypes.c_void_p),
                                                   ctypes.POINTER(ctypes.c_uint)]
            version_api.VerQueryValueW.restype = ctypes.c_int
            size = version_api.GetFileVersionInfoSizeW(str(path), None)
            if not size:
                return "unknown"
            block = ctypes.create_string_buffer(size)
            if not version_api.GetFileVersionInfoW(str(path), 0, size, block):
                return "unknown"
            pointer = ctypes.c_void_p()
            length = ctypes.c_uint()
            if not version_api.VerQueryValueW(block, "\\", ctypes.byref(pointer),
                                               ctypes.byref(length)):
                return "unknown"
            data = ctypes.string_at(pointer, length.value)
            if len(data) < 16:
                return "unknown"
            ms = int.from_bytes(data[8:12], "little")
            ls = int.from_bytes(data[12:16], "little")
            return f"{ms >> 16}.{ms & 0xffff}.{ls >> 16}.{ls & 0xffff}"
        except Exception:
            return "unknown"

    def send_graceful(self, process):
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.send_signal(signal.SIGINT)


def _command(env, argv, *, timeout=30):
    try:
        result = env.run(argv, timeout=timeout)
    except Exception as exc:
        raise HarnessError("tool-unavailable") from exc
    if result.returncode != 0:
        raise HarnessError("tool-failed")
    return result.stdout or "", result.stderr or ""


def _write_command_record(path, stdout, stderr=""):
    """Persist command output privately, including an explicit empty-output marker."""
    text = stdout or ""
    if stderr:
        text += ("\n" if text else "") + "[stderr]\n" + stderr
    path.write_text(text if text else "[no output]\n", encoding="utf-8")


def _safe_preflight(env, output: Path, repo_root: Path, capture: Path,
                    *, rehearsal=False):
    if not env.is_windows():
        raise HarnessError("windows-required")
    if not env.is_admin():
        raise HarnessError("administrator-required")
    repo_root = repo_root.resolve(strict=True)
    captures_root = repo_root / "captures"
    if captures_root.is_symlink():
        raise HarnessError("private-root-invalid")
    captures_root.mkdir(parents=True, exist_ok=True)
    private_root = (repo_root / "captures" / "private")
    if private_root.is_symlink():
        raise HarnessError("private-root-invalid")
    private_root.mkdir(parents=True, exist_ok=True)
    private_root = private_root.resolve(strict=True)
    try:
        private_root.relative_to(repo_root)
    except ValueError as exc:
        raise HarnessError("private-root-invalid") from exc
    output = output.absolute()
    if output.exists():
        raise HarnessError("output-not-fresh")
    # Resolve the nearest existing parent so symlink traversal cannot escape.
    parent = output.parent.resolve(strict=True)
    candidate = parent / output.name
    try:
        candidate.relative_to(private_root)
    except ValueError as exc:
        raise HarnessError("output-outside-private-root") from exc
    if candidate.parent != private_root and private_root not in candidate.parents:
        raise HarnessError("output-outside-private-root")
    if env.free_bytes(parent) < MIN_FREE_BYTES:
        raise HarnessError("insufficient-free-space")
    for tool in (env.pktmon, env.wevtutil, env.tracerpt):
        if not tool:
            raise HarnessError("tool-unavailable")
    help_text, help_stderr = _command(env, [env.pktmon, "start", "help"])
    required_flag_labels = ("0x001", "0x002", "0x004", "0x008", "0x010", "0x020")
    folded_help = help_text.casefold()
    if "--flags" not in folded_help or any(flag not in folded_help for flag in required_flag_labels):
        raise HarnessError("pktmon-flags-unsupported")
    env.pktmon_start_help = help_text
    env.pktmon_start_help_stderr = help_stderr
    try:
        tracerpt_help = env.run([env.tracerpt, "-?"], timeout=30)
    except Exception as exc:
        raise HarnessError("tool-unavailable") from exc
    help_output = ((tracerpt_help.stdout or "") + "\n" +
                   (tracerpt_help.stderr or "")).casefold()
    # This Windows build documents usage successfully but exits 1 for `-?`.
    if tracerpt_help.returncode not in (0, 1) or "tracerpt" not in help_output or "usage" not in help_output:
        raise HarnessError("tool-unavailable")
    start_status, start_status_stderr = _command(env, [env.pktmon, "status"])
    env.pktmon_preflight_status = start_status
    env.pktmon_preflight_status_stderr = start_status_stderr
    if not re.search(r"\b(stopped|not running|inactive)\b", start_status, re.I):
        raise HarnessError("pktmon-running-or-unknown")
    filters, filters_stderr = _command(env, [env.pktmon, "filter", "list"])
    env.pktmon_preflight_filters = filters
    env.pktmon_preflight_filters_stderr = filters_stderr
    if not _no_filters_confirmed(filters):
        raise HarnessError("pktmon-filters-present-or-unknown")
    registered, _ = _command(env, [env.wevtutil, "ep"])
    missing = [provider for provider in PROVIDERS if provider.casefold() not in registered.casefold()]
    if missing:
        raise HarnessError("provider-unavailable")
    if not rehearsal:
        if not capture or not capture.is_file():
            raise HarnessError("capture-unavailable")
        capture = capture.resolve(strict=True)
    return candidate, capture


def _no_filters_confirmed(text):
    """Recognize only host-observed or explicit native empty-filter layouts."""
    lines = tuple(" ".join(line.split()).casefold()
                  for line in text.splitlines() if line.strip())
    return lines in {
        ("no filters",),
        ("no active filters",),
        ("filter list is empty",),
        ("packet filters:", "none"),
    }


def _owned_filter_is_confirmed(text):
    """Only a known, single-entry layout proves remove-all is safe.

    Other native layouts fail closed pending a host-specific proof.
    """
    lines = tuple(" ".join(line.split()).casefold()
                  for line in text.splitlines() if line.strip())
    simple = ("packet filters:",
              (FILTER_NAME + " TCP port 6801").casefold())
    host_table = (
        "packet filters:",
        "# name protocol port",
        "- ---- -------- ----",
        ("1 " + FILTER_NAME + " TCP 6801").casefold(),
    )
    return lines in (simple, host_table)


def _capture_active_confirmed(text):
    """Recognize explicit or host-observed active Packet Monitor status."""
    lines = tuple(" ".join(line.split()).casefold()
                  for line in text.splitlines() if line.strip())
    if lines == ("packet monitor is running",):
        return True
    if re.search(r"\b(stopped|not running|inactive)\b", text, re.I):
        return False
    required_lines = (
        "collected data:",
        "packet counters, packet capture",
        "capture type:",
        "all packets",
        "logger parameters:",
        "logger name: pktmon",
        "event providers:",
    )
    if not all(line in lines for line in required_lines):
        return False
    for provider in PROVIDERS:
        pattern = (r"(?m)^\s*" + re.escape(provider) +
                   r"\s+5\s+0xffffffffffffffff\s*$")
        if not re.search(pattern, text, re.I):
            return False
    return bool(re.search(
        r"(?m)^\s*Microsoft-Windows-PktMon\s+4\s+0x(?:0*3f)\s*$",
        text, re.I))


def _capture_health(env, output):
    try:
        status, _ = _bounded_probe(
            lambda: _command(env, [env.pktmon, "status"],
                             timeout=HEALTH_STATUS_SECONDS),
            HEALTH_STATUS_SECONDS)
        if not _capture_active_confirmed(status):
            return "capture-health-lost"
    except Exception:
        return "capture-health-lost"
    try:
        if _bounded_probe(lambda: env.free_bytes(output),
                          HEALTH_DISK_SECONDS) < MIN_FREE_BYTES:
            return "capture-disk-low"
    except Exception:
        return "capture-disk-low"
    return None


def _bounded_probe(operation, timeout):
    """Return a probe result within its budget, even if the OS call stalls."""
    done = threading.Event()
    result = []
    def worker():
        try:
            result.append((True, operation()))
        except BaseException as exc:
            result.append((False, exc))
        finally:
            done.set()
    threading.Thread(target=worker, daemon=True).start()
    if not done.wait(timeout):
        raise TimeoutError("bounded probe timed out")
    ok, value = result[0]
    if not ok:
        raise value
    return value


def _validate_decoded_database(path):
    """Inspect the finalized decoded-only drive-session file without creating it."""
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        from .drive_session import SIGNALS
        with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True,
                                     timeout=2)) as db:
            for check in ("quick_check", "integrity_check"):
                if db.execute("PRAGMA " + check).fetchone() != ("ok",):
                    return False
            if db.execute("PRAGMA foreign_key_check").fetchone() is not None:
                return False
            expected = {signal.id for signal in SIGNALS}
            session = db.execute(
                "SELECT id, started_utc, ended_utc, mode FROM sessions").fetchall()
            if len(session) != 1 or session[0][3] != "drive-session" or not all(session[0][1:3]):
                return False
            session_id = session[0][0]
            signals = db.execute("SELECT session_id, id, service, request, target_address, "
                                 "response_offset FROM signals").fetchall()
            if len(signals) != len(expected) or {row[1] for row in signals} != expected:
                return False
            if any(row[0] != session_id or any(value is not None for value in row[2:])
                   for row in signals):
                return False
            if db.execute("SELECT COUNT(*) FROM raw_exchanges").fetchone()[0]:
                return False
            if db.execute("SELECT COUNT(*) FROM samples WHERE session_id != ? OR "
                          "timestamp_utc IS NULL OR timestamp_utc = '' OR monotonic_ns <= 0",
                          (session_id,)).fetchone()[0]:
                return False
            return True
    except (OSError, sqlite3.Error, ValueError):
        return False


def _required_artifacts(output, *, rehearsal):
    required = ("pktmon-start-help.txt", "pktmon-preflight-status.txt",
                "pktmon-filter-pre.txt", "pktmon-filter-owned.txt",
                "pktmon-filter-active.txt", "pktmon-start.txt",
                "pktmon-running-status.txt", "pktmon-stop.txt",
                "pktmon-stopped-status.txt", "pktmon-filter-cleanup.txt",
                "pktmon-filter-restored.txt", "host-pre.txt", "host-post.txt",
                "capture.etl", "capture.pcapng", "capture-drops.pcapng",
                "capture.txt", "capture-stats.txt", "tracerpt-summary.txt",
                "tracerpt-report.xml", "tracerpt-events.xml", "system-events.evtx")
    for name in required:
        path = output / name
        if not path.is_file() or path.stat().st_size == 0:
            return False
    if not rehearsal and any(not (output / name).is_file() for name in
                             ("application.stdout", "application.stderr")):
        return False
    if not rehearsal:
        database = output / "decoded.sqlite"
        if not database.is_file() or database.stat().st_size == 0:
            return False
    return True


def _normalize_filter_snapshot(text):
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())


def _pktmon_start_argv(env, etl_path):
    argv = [env.pktmon, "start", "--capture", "--comp", "all", "--type", "all",
            "--pkt-size", "0", "--flags", "0x03F", "--trace"]
    for provider in PROVIDERS:
        argv.extend(("--provider", provider, "--keywords", "0xFFFFFFFFFFFFFFFF", "--level", "5"))
    argv.extend(("--file-name", str(etl_path), "--file-size", "4096",
                 "--log-mode", "circular"))
    return argv


def _metadata(env, etl, output):
    text_path = output / "capture.txt"
    stats_path = output / "capture-stats.txt"
    tracerpt_summary = output / "tracerpt-summary.txt"
    tracerpt_report = output / "tracerpt-report.xml"
    tracerpt_dump = output / "tracerpt-events.xml"
    _command(env, [env.pktmon, "etl2txt", str(etl), "--out", str(text_path),
                   "--verbose", "--metadata"])
    stats, _ = _command(env, [env.pktmon, "etl2txt", str(etl), "--stats"])
    stats_path.write_text(stats, encoding="utf-8")
    _command(env, [env.tracerpt, str(etl), "-o", str(tracerpt_dump), "-of", "XML",
                   "-lr", "-summary", str(tracerpt_summary), "-report", str(tracerpt_report)])
    _command(env, [env.pktmon, "etl2pcap", str(etl), "--out", str(output / "capture.pcapng")])
    _command(env, [env.pktmon, "etl2pcap", str(etl), "--out", str(output / "capture-drops.pcapng"), "--drop-only"])
    tracerpt_data = "\n".join(path.read_text(encoding="utf-8", errors="replace")
                               for path in (tracerpt_summary, tracerpt_report, tracerpt_dump)
                               if path.exists())
    return (text_path.read_text(encoding="utf-8", errors="replace") + "\n" + tracerpt_data,
            stats_path.read_text(encoding="utf-8", errors="replace"))


def _collect_host_evidence(env, output, phase):
    """Persist privacy-sensitive host state into the private output directory."""
    destination = output / ("host-" + phase + ".txt")
    with destination.open("w", encoding="utf-8") as stream:
        for label, argv in (("clock", ["cmd", "/c", "echo", "%DATE% %TIME%"]),
                            ("os", ["cmd", "/c", "ver"]),
                            ("adapters", ["ipconfig", "/all"]),
                            ("drivers", ["driverquery", "/v"]),
                            ("processes", ["tasklist", "/fo", "list"]),
                            ("pktmon-components", [env.pktmon, "list"])):
            result = env.run(argv, timeout=30)
            if result.returncode:
                raise HarnessError("host-evidence-unavailable")
            stream.write("## " + label + "\n")
            stream.write(result.stdout or "")
            stream.write(result.stderr or "")
    return destination


def _export_system_window(env, output, capture_start_epoch=None):
    destination = output / "system-events.evtx"
    # timediff is relative to export time; include the complete trace plus a minute of setup.
    window_ms = max(HARNESS_SECONDS * 1000 + 60000,
                    int((env.now() - capture_start_epoch) * 1000) + 60000
                    if capture_start_epoch is not None else 0)
    query = "*[System[TimeCreated[timediff(@SystemTime) <= " + str(window_ms) + "]]]"
    _command(env, [env.wevtutil, "epl", "System", str(destination), "/q:" + query], timeout=90)
    return destination


def _terminate_child(process, env, graceful=True, deadline=None):
    def budget(limit):
        return limit if deadline is None else max(0, min(limit, deadline - env.monotonic()))
    if process.poll() is not None:
        return "already-exited"
    outcome = ""
    if graceful:
        try:
            env.send_graceful(process)
            process.wait(timeout=budget(10))
            return "graceful-stop"
        except BaseException:
            outcome = "graceful-timeout"
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=budget(5))
            return outcome + "+terminated"
        except BaseException:
            process.kill()
            process.wait(timeout=budget(2))
            return outcome + "+killed"
    return outcome or "already-exited"


def run_capture(capture, output, *, confirm_private_raw_capture=False,
                repo_root=None, env=None, rehearsal_duration=None):
    """Run the production command once or an entirely loopback rehearsal."""
    if not confirm_private_raw_capture:
        raise HarnessError("private-capture-confirmation-required")
    env = env or CaptureEnvironment()
    repo_root = Path(repo_root or Path(__file__).resolve().parents[1])
    output = Path(output)
    rehearsal = rehearsal_duration is not None
    if rehearsal and (capture is not None or not 1 <= rehearsal_duration <= REHEARSAL_MAX_SECONDS):
        raise HarnessError("invalid-rehearsal-request")
    if not rehearsal and capture is None:
        raise HarnessError("capture-required")
    output, capture = _safe_preflight(env, output, repo_root,
                                     Path(capture) if capture else None,
                                     rehearsal=rehearsal)
    output.mkdir()
    _write_command_record(output / "pktmon-start-help.txt",
                          getattr(env, "pktmon_start_help", ""),
                          getattr(env, "pktmon_start_help_stderr", ""))
    _write_command_record(output / "pktmon-preflight-status.txt",
                          getattr(env, "pktmon_preflight_status", ""),
                          getattr(env, "pktmon_preflight_status_stderr", ""))
    _write_command_record(output / "pktmon-filter-pre.txt",
                          getattr(env, "pktmon_preflight_filters", ""),
                          getattr(env, "pktmon_preflight_filters_stderr", ""))
    etl = output / "capture.etl"
    stdout_path, stderr_path = output / "application.stdout", output / "application.stderr"
    manifest_path = output / "manifest.json"
    started = utc_stamp()
    state = {"command": None, "application_start": None, "application_stop": None,
             "application_start_monotonic": None, "application_stop_monotonic": None,
             "child_shutdown_outcome": None,
             "application_exit_code": None, "application_outcome": "not-started",
             "capture_start": None, "capture_stop": None,
             "capture_start_monotonic": None, "capture_stop_monotonic": None,
             "capture_started": False, "capture_stopped": False,
             "filter_added": False, "filter_removed": False,
             "conversion_succeeded": False, "coverage": {"coverage_passed": False},
             "cleanup_errors": [], "harness_outcome": "failed"}
    process = None
    owned_filter_snapshot = None
    out_stream = err_stream = None
    app_start_epoch = app_stop_epoch = trace_start_epoch = trace_stop_epoch = None
    deadline = None
    try:
        _collect_host_evidence(env, output, "pre")
        state["filter_added"] = True
        _command(env, [env.pktmon, "filter", "add", FILTER_NAME, "-t", "TCP", "-p", "6801"])
        owned_filter, owned_filter_stderr = _command(
            env, [env.pktmon, "filter", "list"])
        _write_command_record(output / "pktmon-filter-owned.txt", owned_filter,
                              owned_filter_stderr)
        if not _owned_filter_is_confirmed(owned_filter):
            raise HarnessError("owned-filter-unconfirmed")
        owned_filter_snapshot = _normalize_filter_snapshot(owned_filter)
        trace_start_epoch = env.now()
        start_cmd = _pktmon_start_argv(env, etl)
        state["capture_command"] = start_cmd
        state["capture_started"] = True  # Stop conservatively if start partially succeeds.
        start_stdout, start_stderr = _command(env, start_cmd)
        _write_command_record(output / "pktmon-start.txt", start_stdout,
                              start_stderr)
        state["capture_start"] = utc_stamp()
        state["capture_start_monotonic"] = env.monotonic()
        running_status, running_stderr = _command(env, [env.pktmon, "status"])
        _write_command_record(output / "pktmon-running-status.txt", running_status,
                              running_stderr)
        if not _capture_active_confirmed(running_status):
            raise HarnessError("capture-start-unconfirmed")
        owned_filter, owned_filter_stderr = _command(
            env, [env.pktmon, "filter", "list"])
        _write_command_record(output / "pktmon-filter-active.txt", owned_filter,
                              owned_filter_stderr)
        if (not _owned_filter_is_confirmed(owned_filter) or
                _normalize_filter_snapshot(owned_filter) != owned_filter_snapshot):
            raise HarnessError("owned-filter-unconfirmed")
        if rehearsal:
            state["command"] = ["local-loopback-hsfz-rehearsal", str(rehearsal_duration)]
            app_start_epoch = env.now(); state["application_start"] = utc_stamp()
            state["application_start_monotonic"] = env.monotonic()
            deadline = state["application_start_monotonic"] + rehearsal_duration + 60
            state["application_outcome"] = _run_rehearsal(
                rehearsal_duration, deadline, env,
                health_check=lambda: _capture_health(env, output))
            state["application_exit_code"] = 0 if state["application_outcome"] == "completed" else 1
            app_stop_epoch = env.now(); state["application_stop"] = utc_stamp()
            state["application_stop_monotonic"] = env.monotonic()
        else:
            db = output / "decoded.sqlite"
            state["command"] = child_argv(capture, db)
            out_stream = stdout_path.open("wb")
            err_stream = stderr_path.open("wb")
            popen_kwargs = {"stdout": out_stream, "stderr": err_stream,
                            "shell": False, "cwd": str(repo_root)}
            group_flag = env.create_process_group()
            if group_flag:
                popen_kwargs["creationflags"] = group_flag
            app_start_epoch = env.now(); state["application_start"] = utc_stamp()
            state["application_start_monotonic"] = env.monotonic()
            deadline = state["application_start_monotonic"] + HARNESS_SECONDS
            monitoring_deadline = deadline - SHUTDOWN_RESERVE_SECONDS
            process = env.popen(state["command"], **popen_kwargs)
            state["application_outcome"] = "running"
            while True:
                remaining = monitoring_deadline - env.monotonic()
                if remaining <= HEALTH_POLL_SECONDS:
                    state["application_outcome"] = "hard-deadline"
                    state["child_shutdown_outcome"] = _terminate_child(
                        process, env, graceful=True, deadline=deadline)
                    state["application_exit_code"] = process.returncode
                    break
                probe_started = env.monotonic()
                health = _capture_health(env, output)
                if health:
                    state["application_outcome"] = health
                    state["child_shutdown_outcome"] = _terminate_child(
                        process, env, graceful=True, deadline=deadline)
                    state["application_exit_code"] = process.returncode
                    break
                try:
                    process.wait(timeout=min(max(0, HEALTH_POLL_SECONDS -
                                                 (env.monotonic() - probe_started)),
                                             monitoring_deadline - env.monotonic()))
                    state["application_exit_code"] = process.returncode
                    state["application_outcome"] = "completed" if process.returncode == 0 else "failed"
                    break
                except subprocess.TimeoutExpired:
                    continue
            app_stop_epoch = env.now(); state["application_stop"] = utc_stamp()
            state["application_stop_monotonic"] = env.monotonic()
        if state["application_outcome"] == "running":
            raise HarnessError("application-state-invalid")
    except KeyboardInterrupt:
        state["application_outcome"] = "operator-interrupt"
        if process is not None:
            state["application_exit_code"] = process.returncode
            state["child_shutdown_outcome"] = _terminate_child(
                process, env, graceful=True, deadline=deadline)
            state["application_exit_code"] = process.returncode
        app_stop_epoch = env.now(); state["application_stop"] = utc_stamp()
        state["application_stop_monotonic"] = env.monotonic()
    except HarnessError as exc:
        state["harness_outcome"] = str(exc)
    except Exception:
        state["harness_outcome"] = "unexpected-failure"
    finally:
        if process is not None and process.poll() is None:
            try:
                state["child_shutdown_outcome"] = _terminate_child(
                    process, env, graceful=True, deadline=deadline)
                state["application_exit_code"] = process.returncode
                app_stop_epoch = env.now(); state["application_stop"] = utc_stamp()
                state["application_stop_monotonic"] = env.monotonic()
            except Exception:
                state["cleanup_errors"].append("child-stop-failed")
        for stream in (out_stream, err_stream):
            if stream is not None:
                stream.close()
        if state["capture_started"]:
            try:
                stop_stdout, stop_stderr = _command(
                    env, [env.pktmon, "stop"], timeout=CAPTURE_STOP_SECONDS)
                _write_command_record(output / "pktmon-stop.txt", stop_stdout,
                                      stop_stderr)
            except Exception:
                state["cleanup_errors"].append("capture-stop-failed")
            else:
                try:
                    stopped, stopped_stderr = _command(
                        env, [env.pktmon, "status"],
                        timeout=CAPTURE_STATUS_SECONDS)
                    _write_command_record(output / "pktmon-stopped-status.txt",
                                          stopped, stopped_stderr)
                except Exception:
                    state["cleanup_errors"].append("capture-stop-unconfirmed")
                else:
                    if re.search(r"\b(stopped|not running|inactive)\b", stopped, re.I):
                        state["capture_stopped"] = True
                        state["capture_stop"] = utc_stamp()
                        trace_stop_epoch = env.now()
                        state["capture_stop_monotonic"] = env.monotonic()
                    else:
                        state["cleanup_errors"].append("capture-stop-unconfirmed")
        if state["filter_added"]:
            try:
                filters, filters_stderr = _command(
                    env, [env.pktmon, "filter", "list"])
                _write_command_record(output / "pktmon-filter-cleanup.txt", filters,
                                      filters_stderr)
                if (_normalize_filter_snapshot(filters) != owned_filter_snapshot
                        or not _owned_filter_is_confirmed(filters)):
                    state["cleanup_errors"].append("unexpected-filters-present-manual-recovery")
                else:
                    _command(env, [env.pktmon, "filter", "remove"])
                    remaining, remaining_stderr = _command(
                        env, [env.pktmon, "filter", "list"])
                    _write_command_record(output / "pktmon-filter-restored.txt",
                                          remaining, remaining_stderr)
                    if _no_filters_confirmed(remaining):
                        state["filter_removed"] = True
                    else:
                        state["cleanup_errors"].append("filter-removal-unconfirmed-manual-recovery")
            except Exception:
                state["cleanup_errors"].append("filter-removal-failed")
        try:
            _collect_host_evidence(env, output, "post")
            _export_system_window(env, output, trace_start_epoch)
        except Exception:
            state["cleanup_errors"].append("host-evidence-finalization-failed")
        if state["capture_stopped"] and etl.exists():
            try:
                metadata, stats = _metadata(env, etl, output)
                state["conversion_succeeded"] = True
                if None not in (app_start_epoch, app_stop_epoch, trace_start_epoch, trace_stop_epoch):
                    state["coverage"] = evaluate_coverage(
                        parse_native_coverage(metadata, stats),
                        app_start=app_start_epoch, app_stop=app_stop_epoch,
                        trace_start=trace_start_epoch, trace_stop=trace_stop_epoch)
            except Exception:
                state["cleanup_errors"].append("conversion-failed")
        artifacts_complete = _required_artifacts(output, rehearsal=rehearsal)
        state["required_artifacts_complete"] = artifacts_complete
        database_valid = rehearsal or _validate_decoded_database(output / "decoded.sqlite")
        state["decoded_database_valid"] = database_valid
        evidence_finalized = (state["capture_stopped"] and state["filter_removed"] and
                              state["conversion_succeeded"] and artifacts_complete and database_valid and
                              state["coverage"].get("coverage_passed") and
                              not state["cleanup_errors"])
        if state["harness_outcome"] == "failed":
            if evidence_finalized and state["application_outcome"] == "completed" and state["application_exit_code"] == 0:
                state["harness_outcome"] = "complete"
            elif evidence_finalized and state["application_outcome"] == "failed" and state["application_exit_code"] not in (None, 0):
                state["harness_outcome"] = "captured-application-failure"
            elif state["application_outcome"] in ("failed", "capture-health-lost", "capture-disk-low",
                                                    "hard-deadline", "operator-interrupt"):
                state["harness_outcome"] = ("application-failed" if state["application_outcome"] == "failed"
                                            else state["application_outcome"])
            elif not artifacts_complete or not database_valid:
                state["harness_outcome"] = "evidence-invalid"
            else:
                state["harness_outcome"] = ("coverage-unverified" if not state["coverage"].get("coverage_passed")
                                             else "evidence-invalid")
        state["evidence_bundle_finalized"] = bool(evidence_finalized)
        state["finished_at"] = utc_stamp()
        state["started_at"] = started
        state["runtime"] = sys.version.split()[0]
        state["host_os"] = platform.platform()
        state["tool_versions"] = {
            "pktmon": env.file_version(env.pktmon),
            "wevtutil": env.file_version(env.wevtutil),
            "tracerpt": env.file_version(env.tracerpt),
        }
        try:
            state["artifacts"] = artifact_inventory(output)
            manifest_path.write_text(json.dumps(state, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except Exception:
            # Do not print exception text or private paths.
            state["harness_outcome"] = "manifest-failed"
    return (0 if state["harness_outcome"] == "complete" else 1,
            state["harness_outcome"])


def _run_rehearsal(duration, deadline, env, *, port=6801, health_check=None):
    """Send a representative local HSFZ-shaped request/ack exchange only."""
    stop = threading.Event()
    failed = []
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind(("127.0.0.1", port))
        listener.listen(1)
        listener.settimeout(1)
        bound_port = listener.getsockname()[1]
    except OSError as exc:
        listener.close()
        raise HarnessError("rehearsal-loopback-bind-failed") from exc

    def peer():
        try:
            conn, address = listener.accept()
            if address[0] != "127.0.0.1":
                conn.close(); failed.append("non-loopback-peer"); return
            with conn:
                conn.settimeout(1)
                while not stop.is_set() and env.monotonic() < deadline:
                    data = conn.recv(6)
                    if not data:
                        return
                    while len(data) < 6:
                        part = conn.recv(6 - len(data))
                        if not part: return
                        data += part
                    body_length = int.from_bytes(data[:4], "big")
                    body = bytearray()
                    while len(body) < body_length:
                        part = conn.recv(body_length - len(body))
                        if not part: return
                        body.extend(part)
                    conn.sendall((2).to_bytes(4, "big") + b"\x00\x02" + bytes(body[:2]))
        except OSError:
            if not stop.is_set(): failed.append("peer-close")
        finally:
            listener.close()

    thread = threading.Thread(target=peer, daemon=True)
    thread.start()
    try:
        client = socket.create_connection(("127.0.0.1", bound_port), timeout=2)
        with client:
            client.settimeout(2)
            end = min(env.monotonic() + duration, deadline)
            sequence = 0
            while env.monotonic() < end:
                if health_check:
                    health = health_check()
                    if health:
                        return health
                payload = (sequence & 0xFFFFFFFF).to_bytes(4, "big")
                body = b"\xF4\x12" + payload
                client.sendall(len(body).to_bytes(4, "big") + b"\x00\x01" + body)
                # Read a complete local ACK. Partial/closed peers terminate the rehearsal.
                header = _socket_read_exact(client, 6)
                size = int.from_bytes(header[:4], "big")
                _socket_read_exact(client, size)
                sequence += 1
                env.wait(stop, .2)
        return "completed" if not failed else "peer-failed"
    except (OSError, EOFError):
        return "peer-failed"
    finally:
        stop.set()
        listener.close()
        thread.join(timeout=2)


def _socket_read_exact(sock, length):
    value = bytearray()
    while len(value) < length:
        block = sock.recv(length - len(value))
        if not block:
            raise EOFError("local rehearsal peer closed")
        value.extend(block)
    return bytes(value)
