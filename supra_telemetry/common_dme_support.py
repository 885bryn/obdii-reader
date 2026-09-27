"""One bounded read-only SAE Mode 01 support check for common DME signals."""
import socket

from .dme_check import DME_TARGET_ADDRESS
from .gateway_check import TESTER_ADDRESS, load_gateway_capture
from .hsfz import HsfzClient
from .temperature_support import pid_supported

CHECK_NAME = "HSFZ DME common signal PID support"
SIGNALS = {
    "engine_rpm_pid_0c_supported": 0x0C,
    "vehicle_speed_pid_0d_supported": 0x0D,
    "intake_air_temp_pid_0f_supported": 0x0F,
    "throttle_position_pid_11_supported": 0x11,
}
FAILURE_REASONS = frozenset({
    "capture-invalid", "timeout", "connection-or-transport",
    "uds-rejected", "response-invalid", "unexpected-error",
})


class CommonDmeSupportError(Exception):
    """Failure with a fixed safe reason and conservative request count."""

    def __init__(self, reason, requests_sent=0):
        self.reason = reason if reason in FAILURE_REASONS else "unexpected-error"
        self.requests_sent = requests_sent
        super().__init__(self.reason)


def verify_common_dme_support(path, timeout=2.0, *, client_factory=HsfzClient,
                              connector_factory=socket.create_connection):
    """Send exactly one PID 00 bitmap request using the captured DME route."""
    try:
        if not 0.1 <= float(timeout) <= 5.0:
            raise ValueError
        peer, interface, _gateway_target, _vin = load_gateway_capture(path)
    except Exception:
        raise CommonDmeSupportError("capture-invalid") from None

    def source_bound_connector(address, connect_timeout):
        return connector_factory(address, connect_timeout, source_address=(interface, 0))

    try:
        client = client_factory(peer, TESTER_ADDRESS, DME_TARGET_ADDRESS, port=6801,
                                timeout=timeout, fail_on_pending=True,
                                sock_factory=source_bound_connector)
    except TimeoutError:
        raise CommonDmeSupportError("timeout") from None
    except Exception:
        raise CommonDmeSupportError("connection-or-transport") from None

    requests_sent = 1  # Conservative: request may have been transmitted before an error.
    try:
        try:
            response = client.request(b"\x01\x00")
        except TimeoutError:
            raise CommonDmeSupportError("timeout", requests_sent) from None
        except Exception as exc:
            reason = "uds-rejected" if isinstance(exc, ConnectionError) and (
                "pending UDS response" in str(exc) or "HSFZ error control" in str(exc)
            ) else "connection-or-transport"
            raise CommonDmeSupportError(reason, requests_sent) from None
        if isinstance(response, bytes) and response[:1] == b"\x7f":
            raise CommonDmeSupportError("uds-rejected", requests_sent)
        if not isinstance(response, bytes) or len(response) != 6 or response[:2] != b"\x41\x00":
            raise CommonDmeSupportError("response-invalid", requests_sent)
        bitmap = response[2:]
        return {
            "result": "verified", "check": CHECK_NAME,
            **{key: pid_supported(bitmap, 0x00, pid) for key, pid in SIGNALS.items()},
            "requests_sent": requests_sent,
        }
    finally:
        client.close()
