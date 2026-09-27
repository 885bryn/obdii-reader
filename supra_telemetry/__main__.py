"""CLI entry point."""
import argparse
import json
import socket
import threading
from pathlib import Path
from . import __version__
from .doip import discover as discover_doip
from .engine import AcquisitionEngine
from .hsfz import discover as discover_hsfz
from .gateway_check import verify_gateway
from .dme_check import FAILURE_REASONS, failure_reason as dme_failure_reason, verify_dme
from .temperature_support import (FAILURE_REASONS as TEMPERATURE_FAILURE_REASONS,
                                  TemperatureSupportError, verify_temperature_support)
from .common_dme_support import (CHECK_NAME as COMMON_DME_SUPPORT_CHECK,
                                 FAILURE_REASONS as COMMON_DME_SUPPORT_FAILURE_REASONS,
                                 CommonDmeSupportError, verify_common_dme_support)
from .temperature_values import (CHECK_NAME as TEMPERATURE_VALUES_CHECK,
                                 FAILURE_REASONS as TEMPERATURE_VALUES_FAILURE_REASONS,
                                 TemperatureValueError, read_temperature_values)
from .live import HsfzSignalSource
from .models import SignalDefinition, utc_now
from .profiles import load_profile
from .storage import TelemetryStore, export_csv
from .web import serve
from .temperature_monitor import TemperatureMonitorSource, run_monitor


def demo_signals():
    return [SignalDefinition("engine_rpm", "Engine RPM", "rpm", provenance="simulated demo", confidence="simulated", verification="demo", enabled=True),
            SignalDefinition("vehicle_speed", "Vehicle speed", "km/h", provenance="simulated demo", confidence="simulated", verification="demo", enabled=True),
            SignalDefinition("coolant_temp", "Coolant temperature", "°C", provenance="simulated demo", confidence="simulated", verification="demo", enabled=True),
            SignalDefinition("boost", "Boost (demo only)", "bar", kind="derived", provenance="mock formula", confidence="simulated", verification="demo", enabled=True),
            SignalDefinition("gear", "Gear", kind="unavailable", provenance="No vehicle source configured", confidence="none", verification="unavailable")]


def run_dashboard(args, mode, store, source=None, session_id=None):
    session_id = session_id or (store.start_session(utc_now(), mode=mode) if store else None)
    definitions = source.signals if source is not None else demo_signals()
    if store:
        for definition in definitions: store.register(session_id, definition)
    engine = AcquisitionEngine(source=source, store=store, session_id=session_id, interval=args.interval)
    server = None
    stopper = threading.Event()
    worker = threading.Thread(target=engine.run, args=(stopper,), daemon=True)
    worker_started = False
    try:
        server = serve(engine, args.ui_host, args.port, bool(store), mode=mode)
        worker.start()
        worker_started = True
        print(f"{mode.title()} dashboard: http://{args.ui_host}:{server.server_port}/", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        stopper.set()
        # Closing the source interrupts an in-flight HSFZ socket read. Joining
        # before SQLite close ensures no worker can touch a closed connection.
        close_error = None
        if source is not None and hasattr(source, "close"):
            try: source.close()
            except Exception as exc: close_error = exc
        if worker_started:
            shutdown_timeout = min(15.0, max(1.0, float(getattr(args, "timeout", 2.0)) + 2.0))
            worker.join(timeout=shutdown_timeout)
            if worker.is_alive():
                if server is not None: server.server_close()
                raise RuntimeError(f"acquisition worker did not stop within {shutdown_timeout:.1f}s; SQLite left open")
        if server is not None: server.server_close()
        if store:
            if not worker_started: store.end_session(session_id, utc_now())
            store.close()
        if close_error is not None:
            raise RuntimeError(f"source shutdown failed: {close_error}") from close_error


def add_server_args(cmd, db_required=False):
    cmd.add_argument("--db", required=db_required); cmd.add_argument("--ui-host", default="127.0.0.1"); cmd.add_argument("--port", type=int, default=8765); cmd.add_argument("--interval", type=float, default=.5)


def redact_discovery(results):
    """Return a console-safe discovery summary without vehicle/network identifiers."""
    redacted = {"interface": "<redacted>", "hsfz": [], "doip": [], "doip_note": results["doip_note"],
                "hsfz_count": len(results["hsfz"]), "doip_count": len(results["doip"])}
    for item in results["hsfz"]:
        identification = item.get("identification")
        redacted["hsfz"].append({
            "peer": "<redacted>", "port": item.get("port"),
            "identification": ({key: "<redacted>" for key in identification} if identification is not None else None),
            "raw_hex": "<redacted>" if item.get("raw_hex") is not None else None,
        })
    for item in results["doip"]:
        announcement = item.get("announcement")
        redacted["doip"].append({
            "peer": "<redacted>", "payload_type": item.get("payload_type"),
            "announcement": ({key: (value if key in ("further_action", "sync_status") else "<redacted>")
                              for key, value in announcement.items()} if announcement is not None else None),
            "raw_hex": "<redacted>" if item.get("raw_hex") is not None else None,
        })
    return redacted


def main(argv=None):
    parser = argparse.ArgumentParser(prog="supra-telemetry", description="Read-only GR Supra ENET telemetry prototype")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run simulated dashboard and optional SQLite logger")
    add_server_args(demo)
    disc = sub.add_parser("discover", help="bounded HSFZ UDP and DoIP discovery; sends no diagnostics")
    disc.add_argument("--interface", required=True, help="local IPv4 address to bind")
    disc.add_argument("--timeout", type=float, default=.6); disc.add_argument("--broadcast", default="169.254.255.255"); disc.add_argument("--json"); disc.add_argument("--redact-console", action="store_true", help="redact vehicle and network identifiers from console JSON")
    gateway = sub.add_parser("verify-gateway", help="one bounded, read-only identity check using a private discovery capture")
    gateway.add_argument("--capture", required=True, help="private JSON file created by discover")
    gateway.add_argument("--timeout", type=float, default=2.0, help="bounded response timeout (0.1 to 5 seconds)")
    dme = sub.add_parser("verify-dme", help="one bounded, read-only DME identity check using a private discovery capture")
    dme.add_argument("--capture", required=True, help="private JSON file created by discover")
    dme.add_argument("--timeout", type=float, default=2.0, help="bounded response timeout (0.1 to 5 seconds)")
    temp_support = sub.add_parser("verify-temperature-support", help="bounded SAE Mode 01 PID support check")
    temp_support.add_argument("--capture", required=True, help="private JSON file created by discover")
    temp_support.add_argument("--timeout", type=float, default=2.0, help="bounded response timeout (0.1 to 5 seconds)")
    common_support = sub.add_parser("verify-common-dme-support", help="one bounded SAE Mode 01 common-signal support check")
    common_support.add_argument("--capture", required=True, help="private JSON file created by discover")
    common_support.add_argument("--timeout", type=float, default=2.0, help="bounded response timeout (0.1 to 5 seconds)")
    temp_values = sub.add_parser("read-temperature-values", help="one-shot coolant and oil temperature reads")
    temp_values.add_argument("--capture", required=True, help="private JSON file created by discover")
    temp_values.add_argument("--timeout", type=float, default=2.0, help="bounded response timeout (0.1 to 5 seconds)")
    monitor = sub.add_parser("monitor-temperatures", help="bounded local dashboard for repeated coolant and oil temperature reads")
    monitor.add_argument("--capture", required=True, help="private JSON file created by discover")
    monitor.add_argument("--db", help="optional SQLite sample log (off by default)")
    monitor.add_argument("--duration", type=int, default=300, help="automatic stop in seconds (1 to 300)")
    monitor.add_argument("--timeout", type=float, default=2.0, help="bounded response timeout (0.1 to 5 seconds)")
    monitor.add_argument("--ui-host", default="127.0.0.1"); monitor.add_argument("--port", type=int, default=8765)
    run = sub.add_parser("run", help="live HSFZ reads using a verified, address-explicit profile")
    run.add_argument("--profile", required=True); run.add_argument("--host", required=True, help="explicit discovered gateway IPv4 address"); run.add_argument("--db", required=True)
    run.add_argument("--ui-host", default="127.0.0.1"); run.add_argument("--port", type=int, default=8765); run.add_argument("--interval", type=float, default=1.0); run.add_argument("--timeout", type=float, default=2.0)
    exp = sub.add_parser("export", help="export recorded SQLite samples to CSV")
    exp.add_argument("database"); exp.add_argument("destination")
    args = parser.parse_args(argv)
    if args.command == "export":
        export_csv(args.database, args.destination); return 0
    if args.command == "discover":
        socket.inet_aton(args.interface)
        timeout = min(3.0, max(.1, args.timeout))
        results = {"interface": args.interface, "hsfz": discover_hsfz(args.interface, timeout, broadcast=args.broadcast),
                   "doip": discover_doip(args.interface, timeout),
                   "doip_note": "A vehicle announcement indicates DoIP detected; live DoIP routing activation is not implemented."}
        if args.json: Path(args.json).write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(redact_discovery(results) if args.redact_console else results, indent=2))
        return 0
    if args.command == "verify-gateway":
        try:
            result = verify_gateway(args.capture, args.timeout)
        except Exception:
            print(json.dumps({"result": "failed", "check": "HSFZ gateway identity routing"}))
            return 1
        print(json.dumps(result))
        return 0
    if args.command == "verify-dme":
        try:
            result = verify_dme(args.capture, args.timeout)
        except Exception as exc:
            reason = dme_failure_reason(exc)
            if reason not in FAILURE_REASONS:
                reason = "unexpected-error"
            print(json.dumps({"result": "failed", "check": "HSFZ DME identity routing", "reason": reason}))
            return 1
        print(json.dumps(result))
        return 0
    if args.command == "verify-temperature-support":
        try:
            result = verify_temperature_support(args.capture, args.timeout)
        except TemperatureSupportError as exc:
            reason = exc.reason if exc.reason in TEMPERATURE_FAILURE_REASONS else "unexpected-error"
            print(json.dumps({"result": "failed", "check": "HSFZ DME temperature PID support", "reason": reason}))
            return 1
        except Exception:
            print(json.dumps({"result": "failed", "check": "HSFZ DME temperature PID support", "reason": "unexpected-error"}))
            return 1
        print(json.dumps(result))
        return 0
    if args.command == "verify-common-dme-support":
        try:
            result = verify_common_dme_support(args.capture, args.timeout)
        except CommonDmeSupportError as exc:
            reason = exc.reason if exc.reason in COMMON_DME_SUPPORT_FAILURE_REASONS else "unexpected-error"
            print(json.dumps({"result": "failed", "check": COMMON_DME_SUPPORT_CHECK,
                              "engine_rpm_pid_0c_supported": None,
                              "vehicle_speed_pid_0d_supported": None,
                              "intake_air_temp_pid_0f_supported": None,
                              "throttle_position_pid_11_supported": None,
                              "requests_sent": exc.requests_sent, "reason": reason}))
            return 1
        except Exception:
            print(json.dumps({"result": "failed", "check": COMMON_DME_SUPPORT_CHECK,
                              "engine_rpm_pid_0c_supported": None,
                              "vehicle_speed_pid_0d_supported": None,
                              "intake_air_temp_pid_0f_supported": None,
                              "throttle_position_pid_11_supported": None,
                              "requests_sent": 0, "reason": "unexpected-error"}))
            return 1
        print(json.dumps(result))
        return 0
    if args.command == "read-temperature-values":
        try:
            result = read_temperature_values(args.capture, args.timeout)
        except TemperatureValueError as exc:
            reason = exc.reason if exc.reason in TEMPERATURE_VALUES_FAILURE_REASONS else "unexpected-error"
            result = {"result": "failed", "check": TEMPERATURE_VALUES_CHECK,
                      "coolant_temp_c": None, "engine_oil_temp_c": None,
                      "requests_sent": exc.requests_sent, "reason": reason}
            print(json.dumps(result))
            return 1
        except Exception:
            print(json.dumps({"result": "failed", "check": TEMPERATURE_VALUES_CHECK,
                              "coolant_temp_c": None, "engine_oil_temp_c": None,
                              "requests_sent": 0, "reason": "unexpected-error"}))
            return 1
        print(json.dumps(result))
        return 0
    if args.command == "monitor-temperatures":
        if not 1 <= args.duration <= 300:
            parser.error("duration must be between 1 and 300 seconds")
        if not 0.1 <= args.timeout <= 5.0:
            parser.error("timeout must be between 0.1 and 5 seconds")
        if args.ui_host not in ("127.0.0.1", "localhost", "::1"):
            parser.error("dashboard must bind to loopback")
        store = TelemetryStore(args.db) if args.db else None
        try:
            source = TemperatureMonitorSource(args.capture, timeout=args.timeout)
        except Exception:
            if store: store.close()
            print(json.dumps({"result": "failed", "check": "temperature monitor", "reason": "capture-or-connection-invalid"}))
            return 1
        try:
            status = run_monitor(source, store=store, duration=args.duration,
                                 host=args.ui_host, port=args.port)
        except Exception:
            print(json.dumps({"result": "failed", "check": "temperature monitor", "reason": "monitor-stopped"}))
            return 1
        return status
    if not 0.1 <= args.interval <= 10:
        parser.error("interval must be between 0.1 and 10 seconds")
    if args.command == "demo":
        store = TelemetryStore(args.db) if args.db else None
        run_dashboard(args, "demo", store)
        return 0
    profile, signals = load_profile(args.profile, live=True)
    socket.inet_aton(args.host)
    if not 0.1 <= args.timeout <= 10:
        parser.error("timeout must be between 0.1 and 10 seconds")
    store = TelemetryStore(args.db)
    session = store.start_session(utc_now(), mode="live")
    source = HsfzSignalSource(args.host, profile, signals, timeout=args.timeout,
                              audit=lambda record: store.add_raw(session, record))
    run_dashboard(args, "live", store, source, session)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
