"""Bounded SAE Mode 01 bitmap check for coolant and oil temperature PIDs."""
import socket

from .dme_check import DME_TARGET_ADDRESS
from .gateway_check import TESTER_ADDRESS, load_gateway_capture
from .hsfz import HsfzClient

CHECK_NAME = "HSFZ DME temperature PID support"
FAILURE_REASONS = frozenset({
    "capture-invalid", "timeout", "connection-or-transport",
    "uds-rejected", "response-invalid", "unexpected-error",
})


class TemperatureSupportError(Exception):
    """Failure with a fixed, safe public reason."""

    def __init__(self, reason):
        self.reason = reason if reason in FAILURE_REASONS else "unexpected-error"
        super().__init__(self.reason)


def pid_supported(bitmap, base_pid, pid):
    """Interpret a four-byte SAE bitmap; bit 31 represents base_pid + 1."""
    if not isinstance(bitmap, bytes) or len(bitmap) != 4:
        raise ValueError("bitmap must be four bytes")
    if not (base_pid in (0x00, 0x20, 0x40) and base_pid < pid <= base_pid + 0x20):
        raise ValueError("PID is outside bitmap range")
    ordinal = pid - base_pid
    return bool(int.from_bytes(bitmap, "big") & (1 << (32 - ordinal)))


def _bitmap_response(response, base_pid):
    if (not isinstance(response, bytes) or len(response) != 6
            or response[0] != 0x41 or response[1] != base_pid):
        raise TemperatureSupportError("response-invalid")
    return response[2:]


def verify_temperature_support(path, timeout=2.0, *, client_factory=HsfzClient,
                               connector_factory=socket.create_connection):
    """Send at most three conditional, read-only SAE support bitmap requests."""
    try:
        if not 0.1 <= float(timeout) <= 5.0:
            raise ValueError
        peer, interface, _gateway_target, _vin = load_gateway_capture(path)
    except Exception:
        raise TemperatureSupportError("capture-invalid") from None

    def source_bound_connector(address, connect_timeout):
        return connector_factory(address, connect_timeout, source_address=(interface, 0))

    try:
        client = client_factory(peer, TESTER_ADDRESS, DME_TARGET_ADDRESS, port=6801,
                                timeout=timeout, fail_on_pending=True,
                                sock_factory=source_bound_connector)
    except TimeoutError:
        raise TemperatureSupportError("timeout") from None
    except Exception:
        raise TemperatureSupportError("connection-or-transport") from None

    requests_sent = 0
    try:
        bitmaps = {}
        for base_pid in (0x00, 0x20, 0x40):
            if base_pid and not pid_supported(bitmaps[base_pid - 0x20], base_pid - 0x20, base_pid):
                break
            try:
                response = client.request(bytes((0x01, base_pid)))
                requests_sent += 1
            except TimeoutError:
                raise TemperatureSupportError("timeout") from None
            except Exception as exc:
                reason = "uds-rejected" if isinstance(exc, ConnectionError) and (
                    "pending UDS response" in str(exc) or "HSFZ error control" in str(exc)
                ) else "connection-or-transport"
                raise TemperatureSupportError(reason) from None
            bitmaps[base_pid] = _bitmap_response(response, base_pid)

        return {
            "result": "verified", "check": CHECK_NAME,
            "coolant_pid_05_supported": pid_supported(bitmaps[0x00], 0x00, 0x05),
            "engine_oil_temp_pid_5c_supported": pid_supported(bitmaps[0x40], 0x40, 0x5C)
                if 0x40 in bitmaps else False,
            "requests_sent": requests_sent,
        }
    finally:
        client.close()
