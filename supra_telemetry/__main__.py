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
from .live import HsfzSignalSource
from .models import SignalDefinition, utc_now
from .profiles import load_profile
from .storage import TelemetryStore, export_csv
from .web import serve


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


def main(argv=None):
    parser = argparse.ArgumentParser(prog="supra-telemetry", description="Read-only GR Supra ENET telemetry prototype")
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    demo = sub.add_parser("demo", help="run simulated dashboard and optional SQLite logger")
    add_server_args(demo)
    disc = sub.add_parser("discover", help="bounded HSFZ UDP and DoIP discovery; sends no diagnostics")
    disc.add_argument("--interface", required=True, help="local IPv4 address to bind")
    disc.add_argument("--timeout", type=float, default=.6); disc.add_argument("--broadcast", default="169.254.255.255"); disc.add_argument("--json")
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
        out = json.dumps(results, indent=2); print(out)
        if args.json: Path(args.json).write_text(out + "\n", encoding="utf-8")
        return 0
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
