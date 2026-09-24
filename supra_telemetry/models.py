"""Shared, JSON-safe telemetry models and declarative signal codecs."""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


@dataclass
class SignalDefinition:
    id: str
    name: str
    unit: str = ""
    kind: str = "measured"  # measured, derived, unavailable
    provenance: str = ""
    confidence: str = "unknown"
    verification: str = "unverified"
    enabled: bool = False
    service: str | None = None
    request: str | None = None
    target_address: int | None = None
    response_offset: int | None = None
    width: int = 1
    byteorder: str = "big"
    signed: bool = False
    scale: float = 1.0
    offset: float = 0.0
    expected_hz: float | None = None
    observed_hz: float | None = None


@dataclass
class Sample:
    signal_id: str
    value: float | str | None
    unit: str
    source: str
    kind: str
    quality: str
    timestamp_utc: str
    monotonic_ns: int
    error: str | None = None
    observed_hz: float | None = None


@dataclass
class RawExchange:
    timestamp_utc: str
    transport: str
    request: bytes
    response: bytes
    outcome: str


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sample_dict(sample: Sample) -> dict[str, Any]:
    return asdict(sample)


def decode_integer(data: bytes, definition: SignalDefinition) -> float:
    """Decode a bounded integer slice with a linear scale and offset."""
    start, width = definition.response_offset, definition.width
    if start is None or start < 0 or width not in (1, 2, 3, 4, 8) or start + width > len(data):
        raise ValueError("signal byte range is missing or outside the response")
    if definition.byteorder not in ("big", "little"):
        raise ValueError("byteorder must be big or little")
    raw = int.from_bytes(data[start:start + width], definition.byteorder, signed=definition.signed)
    return raw * definition.scale + definition.offset
