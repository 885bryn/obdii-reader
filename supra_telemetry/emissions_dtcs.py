"""Bounded, read-only emissions DTC retrieval over the captured DME route."""
import socket

from .dme_check import DME_TARGET_ADDRESS
from .gateway_check import TESTER_ADDRESS, load_gateway_capture
from .hsfz import HsfzClient

CHECK_NAME = "HSFZ DME emissions DTCs"
READS = ((0x03, 0x43, "stored"), (0x07, 0x47, "pending"), (0x0A, 0x4A, "permanent"))
FAILURE_REASONS = frozenset({
    "capture-invalid", "timeout", "connection-or-transport",
    "uds-rejected", "response-invalid", "unexpected-error",
})


class EmissionsDtcError(Exception):
    """Failure with an allowlisted public reason and conservative request count."""

    def __init__(self, reason, requests_sent=0):
        self.reason = reason if reason in FAILURE_REASONS else "unexpected-error"
        self.requests_sent = requests_sent
        super().__init__(self.reason)


def decode_dtc(code):
    """Decode a two-byte SAE J2012 DTC integer to its five-character code."""
    if not isinstance(code, int) or isinstance(code, bool) or not 0 <= code <= 0xFFFF:
        raise ValueError("DTC must be a 16-bit integer")
    category = "PCBU"[(code >> 14) & 0x03]
    first_digit = (code >> 12) & 0x03
    return f"{category}{first_digit}{code & 0x0FFF:03X}"


def parse_dtc_payload(payload):
    """Parse bytes after the positive service; all-zero pairs are padding."""
    if not isinstance(payload, bytes) or len(payload) % 2:
        raise ValueError("malformed DTC payload")
    codes = []
    for offset in range(0, len(payload), 2):
        code = (payload[offset] << 8) | payload[offset + 1]
        if code:
            codes.append(decode_dtc(code))
    return codes


def read_emissions_dtcs(path, timeout=2.0, *, client_factory=HsfzClient,
                        connector_factory=socket.create_connection):
    """Read stored, pending, and permanent emissions DTCs once each in order."""
    try:
        if not 0.1 <= float(timeout) <= 5.0:
            raise ValueError
        peer, interface, _gateway_target, _vin = load_gateway_capture(path)
    except Exception:
        raise EmissionsDtcError("capture-invalid") from None

    def source_bound_connector(address, connect_timeout):
        return connector_factory(address, connect_timeout, source_address=(interface, 0))

    try:
        client = client_factory(peer, TESTER_ADDRESS, DME_TARGET_ADDRESS, port=6801,
                                timeout=timeout, fail_on_pending=True,
                                sock_factory=source_bound_connector)
    except TimeoutError:
        raise EmissionsDtcError("timeout") from None
    except Exception:
        raise EmissionsDtcError("connection-or-transport") from None

    requests_sent = 0
    try:
        result = {f"{label}_dtcs": [] for _, _, label in READS}
        for service, positive, label in READS:
            requests_sent += 1  # Count before request; send may precede a transport failure.
            try:
                response = client.request(bytes((service,)))
            except TimeoutError:
                raise EmissionsDtcError("timeout", requests_sent) from None
            except Exception as exc:
                reason = "uds-rejected" if isinstance(exc, ConnectionError) and (
                    "pending UDS response" in str(exc) or "HSFZ error control" in str(exc)
                ) else "connection-or-transport"
                raise EmissionsDtcError(reason, requests_sent) from None
            if isinstance(response, bytes) and response[:1] == b"\x7f":
                raise EmissionsDtcError("uds-rejected", requests_sent)
            if not isinstance(response, bytes) or not response.startswith(bytes((positive,))):
                raise EmissionsDtcError("response-invalid", requests_sent)
            try:
                result[f"{label}_dtcs"] = parse_dtc_payload(response[1:])
            except Exception:
                raise EmissionsDtcError("response-invalid", requests_sent) from None
        result.update({f"{label}_count": len(result[f"{label}_dtcs"]) for _, _, label in READS})
        result.update({"result": "verified", "check": CHECK_NAME, "requests_sent": requests_sent})
        return result
    finally:
        client.close()
