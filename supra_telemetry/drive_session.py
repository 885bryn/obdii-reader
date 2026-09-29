"""Offline-capable, bounded moving-session dashboard runner."""
import json
import os
import threading
import time
from pathlib import Path

from .client_dashboard import (LIVE_FAILURES, SIGNALS, MovingDashboardLiveSource,
                               make_dashboard_handler, reserve_dashboard_server)
from .engine import AcquisitionEngine
from .models import SignalDefinition, utc_now
from .storage import TelemetryStore

FAILURES = LIVE_FAILURES | {"recording-error", "dashboard-error", "dashboard-bind-failed",
                            "source-unavailable"}


def run_drive_session(capture, db, *, duration=1800, timeout=2.0, host="127.0.0.1",
                      port=8765, source_factory=MovingDashboardLiveSource,
                      store_factory=TelemetryStore, server_factory=reserve_dashboard_server,
                      monotonic=time.monotonic):
    """Run one persisted Mode 01 session; injected factories make ordering testable."""
    server = store = source = engine = worker = None
    result, reason = "completed", None
    session_id = None
    database_path = Path(db)
    owns_database_path = False
    acquisition_started_at = None
    acquisition_started = False
    worker_alive = False
    try:
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("dashboard-error")
        if database_path.exists():
            raise FileExistsError("recording-error")
        server = server_factory(host, port)
        # Reserve the exact filename exclusively so setup cleanup can prove ownership.
        descriptor = os.open(database_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(descriptor)
        owns_database_path = True
        store = store_factory(database_path)
        session_id = store.start_session(utc_now(), mode="drive-session")
        # Register only fixed, privacy-safe signal metadata; no request or route fields.
        safe_signals = [SignalDefinition(s.id, s.name, s.unit, provenance="standard decoded signal",
                                         confidence=s.confidence, verification=s.verification,
                                         enabled=True) for s in SIGNALS]
        for signal in safe_signals:
            store.register(session_id, signal)
        source = source_factory(capture, timeout=timeout, duration=duration,
                                monotonic=monotonic)
        engine = AcquisitionEngine(source=source, store=store, session_id=session_id, interval=0.1)
        server.RequestHandlerClass = make_dashboard_handler(engine, source, "live", {"status": "unavailable", "stored": None, "pending": None, "permanent": None, "permanent_reason": None})
        stop = threading.Event()
        def acquire():
            engine.run(stop)
            if engine.halted:
                server.shutdown()
        worker = threading.Thread(target=acquire, daemon=True)
        acquisition_started_at = monotonic()
        worker.start()
        acquisition_started = True
        timer = threading.Timer(duration, server.shutdown)
        timer.daemon = True
        timer.start()
        try:
            print(f"Drive-session dashboard: http://{host}:{server.server_port}/", flush=True)
            server.serve_forever()
        finally:
            timer.cancel()
            stop.set()
            source.close()
            worker.join(timeout=timeout + 2)
            worker_alive = worker.is_alive()
            if worker_alive:
                result, reason = "failed", "dashboard-error"
        if engine.halted:
            result = "failed"
            reason = ("recording-error" if engine.recording_error else
                      getattr(source, "halt_reason", None) or "dashboard-error")
        elapsed = min(float(duration), max(0.0, monotonic() - acquisition_started_at))
        counts = {s.id: 0 for s in safe_signals}
        if not worker_alive:
            for signal_id, count in store.db.execute("SELECT signal_id, COUNT(*) FROM samples WHERE session_id=? GROUP BY signal_id", (session_id,)):
                if signal_id in counts:
                    counts[signal_id] = count
        else:
            counts = {signal_id: None for signal_id in counts}
        requests = min(getattr(source, "_started", 0), 5 * duration)
        summary = {"result": result, "duration_seconds": round(elapsed, 2),
                   "requests": requests,
                   "signals": {key: {"samples": count,
                                     "achieved_hz": (round(count / elapsed, 4) if elapsed else 0.0)
                                     if count is not None else None}
                               for key, count in counts.items()}}
        if reason:
            summary["reason"] = reason if reason in FAILURES else "dashboard-error"
        print(json.dumps(summary, sort_keys=True), flush=True)
        return 1 if result == "failed" else 0
    except Exception as exc:
        # Do not print exception text: it may contain a path, address, or capture data.
        result = "failed"
        reason = str(exc) if str(exc) in FAILURES else "source-unavailable"
        print(json.dumps({"result": result, "reason": reason, "duration_seconds": 0,
                          "requests": 0,
                          "signals": {s.id: {"samples": 0, "achieved_hz": 0.0}
                                      for s in SIGNALS}}, sort_keys=True), flush=True)
        return 1
    finally:
        if source is not None:
            try: source.close()
            except Exception: pass
        if server is not None:
            try: server.server_close()
            except Exception: pass
        if store is not None:
            if session_id is not None and acquisition_started and not worker_alive:
                try: store.end_session(session_id, utc_now())
                except Exception: pass
            if not worker_alive:
                try: store.close()
                except Exception: pass
        if owns_database_path and not acquisition_started:
            try: database_path.unlink()
            except OSError: pass
