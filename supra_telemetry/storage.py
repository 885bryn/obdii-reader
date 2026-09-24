"""Thread-safe SQLite session, per-session signal metadata, samples, and raw audit storage."""
import csv
import sqlite3
import threading
from pathlib import Path
from .models import Sample, SignalDefinition


class TelemetryStore:
    def __init__(self, path: str | Path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.RLock()
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS sessions(id INTEGER PRIMARY KEY, started_utc TEXT NOT NULL, ended_utc TEXT, mode TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS signals(session_id INTEGER NOT NULL REFERENCES sessions(id), id TEXT NOT NULL, name TEXT, unit TEXT, kind TEXT, provenance TEXT, confidence TEXT, verification TEXT, expected_hz REAL, observed_hz REAL, service TEXT, request TEXT, target_address INTEGER, response_offset INTEGER, width INTEGER, byteorder TEXT, signed INTEGER, scale REAL, offset REAL, PRIMARY KEY(session_id, id));
        CREATE TABLE IF NOT EXISTS samples(id INTEGER PRIMARY KEY, session_id INTEGER NOT NULL, signal_id TEXT NOT NULL, timestamp_utc TEXT NOT NULL, monotonic_ns INTEGER NOT NULL, value TEXT, source TEXT, kind TEXT, quality TEXT, unit TEXT, error TEXT, observed_hz REAL, FOREIGN KEY(session_id, signal_id) REFERENCES signals(session_id, id));
        CREATE TABLE IF NOT EXISTS raw_exchanges(id INTEGER PRIMARY KEY, session_id INTEGER REFERENCES sessions(id), timestamp_utc TEXT NOT NULL, transport TEXT, request BLOB, response BLOB, outcome TEXT);
        """)
        self.db.commit()

    def start_session(self, started: str, mode: str = "demo") -> int:
        with self._lock:
            cur = self.db.execute("INSERT INTO sessions(started_utc, mode) VALUES (?, ?)", (started, mode)); self.db.commit(); return cur.lastrowid

    def register(self, session_id: int, sig: SignalDefinition) -> None:
        with self._lock:
            self.db.execute("INSERT INTO signals(session_id,id,name,unit,kind,provenance,confidence,verification,expected_hz,observed_hz,service,request,target_address,response_offset,width,byteorder,signed,scale,offset) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (session_id, sig.id, sig.name, sig.unit, sig.kind, sig.provenance, sig.confidence, sig.verification, sig.expected_hz, sig.observed_hz, sig.service, sig.request, sig.target_address, sig.response_offset, sig.width, sig.byteorder, sig.signed, sig.scale, sig.offset)); self.db.commit()

    def add_sample(self, session_id: int, sample: Sample) -> None:
        with self._lock:
            self.db.execute("INSERT INTO samples(session_id, signal_id, timestamp_utc, monotonic_ns, value, source, kind, quality, unit, error, observed_hz) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", (session_id, sample.signal_id, sample.timestamp_utc, sample.monotonic_ns, None if sample.value is None else str(sample.value), sample.source, sample.kind, sample.quality, sample.unit, sample.error, sample.observed_hz)); self.db.commit()

    def add_raw(self, session_id: int, exchange) -> None:
        with self._lock:
            self.db.execute("INSERT INTO raw_exchanges(session_id, timestamp_utc, transport, request, response, outcome) VALUES (?, ?, ?, ?, ?, ?)", (session_id, exchange.timestamp_utc, exchange.transport, exchange.request, exchange.response, exchange.outcome)); self.db.commit()

    def end_session(self, session_id: int, ended_utc: str) -> None:
        with self._lock:
            self.db.execute("UPDATE sessions SET ended_utc=? WHERE id=?", (ended_utc, session_id)); self.db.commit()

    def close(self):
        with self._lock: self.db.close()


def export_csv(db_path: str | Path, destination: str | Path) -> None:
    db = sqlite3.connect(db_path)
    try:
        with open(destination, "w", newline="", encoding="utf-8") as out:
            writer = csv.writer(out); writer.writerow(["session_id", "timestamp_utc", "signal_id", "source", "kind", "quality", "unit", "value", "observed_hz", "error"])
            writer.writerows(db.execute("SELECT session_id, timestamp_utc, signal_id, source, kind, quality, unit, value, observed_hz, error FROM samples ORDER BY session_id, timestamp_utc, id"))
    finally:
        db.close()
