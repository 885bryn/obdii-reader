"""Single-request, read-only verification of a captured DME identity route."""
import socket

from .gateway_check import TESTER_ADDRESS, VIN_REQUEST, load_gateway_capture
from .hsfz import HsfzClient

# Community-corroborated candidate only; Toyota has not published this routing
# address for the user's Supra. This check makes no signal/PID claims.
DME_TARGET_ADDRESS = 0x12

FAILURE_REASONS = frozenset({
    "capture-invalid", "timeout", "connection-or-transport", "hsfz-rejected",
    "pending-response", "negative-response", "identity-response-invalid",
    "unexpected-error",
})


class DmeVerificationError(Exception):
    """A DME check failure whose public reason is a fixed safe category."""

    def __init__(self, reason):
        if reason not in FAILURE_REASONS:
            reason = "unexpected-error"
        self.reason = reason
        super().__init__(reason)


def failure_reason(error):
    """Map known failures to allowlisted categories without exposing messages."""
    if isinstance(error, DmeVerificationError):
        return error.reason
    if isinstance(error, TimeoutError):
        return "timeout"
    if isinstance(error, ConnectionError):
        message = str(error)
        if message.startswith("HSFZ error control 0x") and len(message) == len("HSFZ error control 0x") + 4:
            return "hsfz-rejected"
        if message == "pending UDS response is not accepted":
            return "pending-response"
        return "connection-or-transport"
    if isinstance(error, (ValueError, OSError)):
        return "capture-invalid" if isinstance(error, ValueError) else "connection-or-transport"
    return "unexpected-error"


def verify_dme(path, timeout=2.0, *, client_factory=HsfzClient, connector_factory=socket.create_connection):
    """Send exactly one VIN read through the candidate DME route in the capture."""
    try:
        if not 0.1 <= float(timeout) <= 5.0:
            raise ValueError("timeout must be between 0.1 and 5 seconds")
        peer, interface, _gateway_target, discovered_vin = load_gateway_capture(path)
    except Exception as exc:
        raise DmeVerificationError("capture-invalid") from None

    def source_bound_connector(address, connect_timeout):
        return connector_factory(address, connect_timeout, source_address=(interface, 0))

    try:
        client = client_factory(peer, TESTER_ADDRESS, DME_TARGET_ADDRESS, port=6801,
                                timeout=timeout, fail_on_pending=True,
                                sock_factory=source_bound_connector)
    except Exception as exc:
        raise DmeVerificationError(failure_reason(exc)) from None
    try:
        try:
            response = client.request(VIN_REQUEST)
        except Exception as exc:
            reason = "identity-response-invalid" if isinstance(exc, ValueError) else failure_reason(exc)
            raise DmeVerificationError(reason) from None
        if response[:1] == b"\x7f" and len(response) >= 3 and response[1] == 0x22:
            if response[2] == 0x78:
                raise DmeVerificationError("pending-response")
            raise DmeVerificationError("negative-response")
        if len(response) != 20 or response[:3] != b"\x62\xf1\x90":
            raise DmeVerificationError("identity-response-invalid")
        returned_vin = response[3:]
        if any(byte < 0x20 or byte > 0x7e for byte in returned_vin) or returned_vin.decode("ascii") != discovered_vin:
            raise DmeVerificationError("identity-response-invalid")
        return {"result": "verified", "check": "HSFZ DME identity routing"}
    finally:
        client.close()
