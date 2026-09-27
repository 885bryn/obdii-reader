"""Minimal UDS/OBD response parsing, independent of transport framing."""
from dataclasses import dataclass


# Canonical response metadata for the small SAE J1979 subset implemented by
# mode01_value. Offsets are relative to the full positive response
# (0x41, PID, data...). Profiles may omit these fields, but may not contradict
# them: persisted decoder metadata must describe the decoder actually used.
MODE01_CODECS = {
    0x0C: {"unit": "rpm", "response_offset": 2, "width": 2, "byteorder": "big", "signed": False, "scale": 0.25, "offset": 0.0},
    0x0D: {"unit": "km/h", "response_offset": 2, "width": 1, "byteorder": "big", "signed": False, "scale": 1.0, "offset": 0.0},
    0x05: {"unit": "°C", "response_offset": 2, "width": 1, "byteorder": "big", "signed": False, "scale": 1.0, "offset": -40.0},
    0x5C: {"unit": "°C", "response_offset": 2, "width": 1, "byteorder": "big", "signed": False, "scale": 1.0, "offset": -40.0},
    0x0F: {"unit": "°C", "response_offset": 2, "width": 1, "byteorder": "big", "signed": False, "scale": 1.0, "offset": -40.0},
    0x11: {"unit": "%", "response_offset": 2, "width": 1, "byteorder": "big", "signed": False, "scale": 100.0 / 255.0, "offset": 0.0},
}


@dataclass(frozen=True)
class ParsedResponse:
    positive: bool
    service: int
    data: bytes = b""
    nrc: int | None = None
    pending: bool = False


def parse_response(payload: bytes, request_service: int) -> ParsedResponse:
    if len(payload) >= 3 and payload[0] == 0x7F:
        if payload[1] != request_service:
            raise ValueError("negative response references a different service")
        return ParsedResponse(False, request_service, nrc=payload[2], pending=payload[2] == 0x78)
    expected = {0x01: 0x41, 0x03: 0x43, 0x07: 0x47, 0x09: 0x49,
                0x0A: 0x4A, 0x22: 0x62, 0x3E: 0x7E}.get(request_service)
    if expected is None or not payload or payload[0] != expected:
        raise ValueError("unexpected positive response service")
    return ParsedResponse(True, request_service, payload[1:])


def mode01_value(pid: int, data: bytes) -> tuple[float, str]:
    """Decode only common SAE-defined Mode 01 PIDs; input is PID data bytes."""
    if pid == 0x0C and len(data) == 2:  # RPM = ((A*256)+B)/4
        return (((data[0] << 8) | data[1]) / 4.0, "rpm")
    if pid == 0x0D and len(data) == 1:
        return (float(data[0]), "km/h")
    if pid == 0x05 and len(data) == 1:
        return (float(data[0]) - 40.0, "°C")
    if pid == 0x5C and len(data) == 1:
        return (float(data[0]) - 40.0, "°C")
    if pid == 0x0F and len(data) == 1:
        return (float(data[0]) - 40.0, "°C")
    if pid == 0x11 and len(data) == 1:
        return (data[0] * 100.0 / 255.0, "%")
    raise ValueError(f"unsupported or malformed SAE Mode 01 PID 0x{pid:02X}")
