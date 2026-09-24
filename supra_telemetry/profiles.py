"""Data-only JSON profile loading and complete fail-closed preflight."""
import json
import math
import re
from pathlib import Path
from .models import SignalDefinition
from .uds import MODE01_CODECS

_WIDTHS = {1, 2, 3, 4, 8}
_KINDS = {"measured", "derived", "unavailable"}
_SERVICES = {"01", "09", "22"}


def _exact_int(value, label, *, minimum=None, maximum=None):
    if type(value) is not int:
        raise ValueError(f"{label} must be an integer (booleans are not accepted)")
    if minimum is not None and value < minimum or maximum is not None and value > maximum:
        raise ValueError(f"{label} is outside the supported range")


def _finite_number(value, label, *, positive=False):
    try:
        finite = math.isfinite(value)
    except (OverflowError, TypeError):
        finite = False
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not finite:
        raise ValueError(f"{label} must be a finite number")
    if positive and value <= 0:
        raise ValueError(f"{label} must be positive")


def load_profile(path: str | Path, *, live: bool = False) -> tuple[dict, list[SignalDefinition]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("signals"), list):
        raise ValueError("profile must contain a signals list")
    signals = []
    seen = set()
    for index, item in enumerate(data["signals"]):
        if not isinstance(item, dict):
            raise ValueError(f"signal {index} must be a JSON object")
        try:
            sig = SignalDefinition(**item)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"invalid signal definition at index {index}: {exc}") from exc
        if not isinstance(sig.id, str) or not sig.id.strip() or sig.id != sig.id.strip() or sig.id in seen:
            raise ValueError(f"signal ids must be unique, non-empty strings: {sig.id!r}")
        seen.add(sig.id)
        for field in ("name", "unit", "provenance", "confidence", "verification"):
            value = getattr(sig, field)
            if not isinstance(value, str) or (field == "name" and not value.strip()):
                raise ValueError(f"{sig.id}.{field} must be a string" + (" and non-empty" if field == "name" else ""))
        if not isinstance(sig.kind, str) or sig.kind not in _KINDS:
            raise ValueError(f"unsupported signal kind for {sig.id}")
        if type(sig.enabled) is not bool or type(sig.signed) is not bool:
            raise ValueError(f"enabled and signed must be boolean values for {sig.id}")
        if sig.target_address is not None:
            _exact_int(sig.target_address, f"{sig.id}.target_address", minimum=0, maximum=255)
        if sig.response_offset is not None:
            _exact_int(sig.response_offset, f"{sig.id}.response_offset", minimum=0, maximum=8191)
        _exact_int(sig.width, f"{sig.id}.width", minimum=1, maximum=8)
        if sig.width not in _WIDTHS:
            raise ValueError(f"unsupported integer width for {sig.id}")
        if sig.response_offset is not None and sig.response_offset + sig.width > 8192:
            raise ValueError(f"decoder range exceeds maximum response size for {sig.id}")
        if sig.byteorder not in ("big", "little"):
            raise ValueError(f"unsupported byteorder for {sig.id}")
        _finite_number(sig.scale, f"{sig.id}.scale")
        _finite_number(sig.offset, f"{sig.id}.offset")
        if sig.expected_hz is not None: _finite_number(sig.expected_hz, f"{sig.id}.expected_hz", positive=True)
        if sig.observed_hz is not None: _finite_number(sig.observed_hz, f"{sig.id}.observed_hz", positive=True)
        if sig.service is not None or sig.request is not None:
            if not isinstance(sig.service, str) or sig.service not in _SERVICES or not isinstance(sig.request, str) or not re.fullmatch(r"(?:[0-9A-Fa-f]{2})+", sig.request):
                raise ValueError(f"invalid allowlisted service/request shape for {sig.id}")
            req = bytes.fromhex(sig.service + sig.request)
            if req[0] == 0x22 and (len(req) != 3 or req[1:3] == b"\0\0"):
                raise ValueError(f"ReadDataByIdentifier request must contain one non-zero DID for {sig.id}")
            if req[0] in (0x01, 0x09) and len(req) != 2:
                raise ValueError(f"SAE request must contain one parameter byte for {sig.id}")
            if req[0] == 0x01:
                canonical = MODE01_CODECS.get(req[1])
                if canonical is None:
                    raise ValueError(f"unsupported Mode 01 PID 0x{req[1]:02X} for {sig.id}")
                for field, expected in canonical.items():
                    if field in item:
                        actual = getattr(sig, field)
                        matches = (math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12)
                                   if isinstance(expected, float) else actual == expected)
                        if not matches:
                            raise ValueError(f"{sig.id}.{field} contradicts the canonical Mode 01 decoder")
                    setattr(sig, field, expected)
        if live and sig.enabled:
            if sig.kind != "measured" or sig.verification != "verified":
                raise ValueError(f"enabled live signal must be verified measured data: {sig.id}")
            if sig.service not in _SERVICES or sig.request is None or sig.target_address is None:
                raise ValueError(f"enabled live signal lacks explicit allowlisted request/address: {sig.id}")
            if sig.response_offset is None:
                raise ValueError(f"enabled live signal lacks response decoder offset: {sig.id}")
        signals.append(sig)

    if live:
        if data.get("validation_status") != "verified":
            raise ValueError("live mode requires validation_status=verified")
        if data.get("transport") != "HSFZ":
            raise ValueError("live mode requires explicit transport=HSFZ")
        _exact_int(data.get("tester_address"), "tester_address", minimum=0, maximum=255)
        if not any(sig.enabled for sig in signals):
            raise ValueError("live profile has no enabled signals")
    return data, signals
