"""One-shot, read-only SAE Mode 01 temperature value reads."""
import socket

from .dme_check import DME_TARGET_ADDRESS
from .gateway_check import TESTER_ADDRESS, load_gateway_capture
from .hsfz import HsfzClient

CHECK_NAME = "HSFZ DME temperature values"
FAILURE_REASONS = frozenset({
    "capture-invalid", "timeout", "connection-or-transport",
    "uds-rejected", "response-invalid", "unexpected-error",
})


class TemperatureValueError(Exception):
    """Failure with a fixed, safe public reason and request count."""

    def __init__(self, reason, requests_sent=0):
        self.reason = reason if reason in FAILURE_REASONS else "unexpected-error"
        self.requests_sent = requests_sent
        super().__init__(self.reason)


def decode_temperature(raw):
    """Decode SAE temperature byte as raw minus 40 degrees Celsius."""
    if not isinstance(raw, int) or isinstance(raw, bool) or not 0 <= raw <= 0xFF:
        raise ValueError("temperature value must be one byte")
    return raw - 40


def parse_temperature_response(response, pid):
    """Accept only the exact positive Mode 01 response for the requested PID."""
    if pid not in (0x05, 0x5C) or not isinstance(response, bytes) or len(response) != 3:
        raise ValueError("invalid temperature response")
    if response[:2] != bytes((0x41, pid)):
        raise ValueError("invalid temperature response")
    return decode_temperature(response[2])


def read_temperature_values(path, timeout=2.0, *, client_factory=HsfzClient,
                            connector_factory=socket.create_connection):
    """Read coolant then oil temperature once each over one captured HSFZ route."""
    try:
        if not 0.1 <= float(timeout) <= 5.0:
            raise ValueError
        peer, interface, _gateway_target, _vin = load_gateway_capture(path)
    except Exception:
        raise TemperatureValueError("capture-invalid") from None

    def source_bound_connector(address, connect_timeout):
        return connector_factory(address, connect_timeout, source_address=(interface, 0))

    try:
        client = client_factory(peer, TESTER_ADDRESS, DME_TARGET_ADDRESS, port=6801,
                                timeout=timeout, fail_on_pending=True,
                                sock_factory=source_bound_connector)
    except TimeoutError:
        raise TemperatureValueError("timeout") from None
    except Exception:
        raise TemperatureValueError("connection-or-transport") from None

    requests_sent = 0
    try:
        values = []
        for pid in (0x05, 0x5C):
            # Count before entering the client: failures can happen after sendall,
            # so this is a conservative upper bound on possible transmitted reads.
            requests_sent += 1
            try:
                response = client.request(bytes((0x01, pid)))
            except TimeoutError:
                raise TemperatureValueError("timeout", requests_sent) from None
            except Exception as exc:
                reason = "uds-rejected" if isinstance(exc, ConnectionError) and (
                    "pending UDS response" in str(exc) or "HSFZ error control" in str(exc)
                ) else "connection-or-transport"
                raise TemperatureValueError(reason, requests_sent) from None
            if isinstance(response, bytes) and response[:1] == b"\x7f":
                raise TemperatureValueError("uds-rejected", requests_sent)
            try:
                values.append(parse_temperature_response(response, pid))
            except Exception:
                raise TemperatureValueError("response-invalid", requests_sent) from None
        return {
            "result": "verified", "check": CHECK_NAME,
            "coolant_temp_c": values[0], "engine_oil_temp_c": values[1],
            "requests_sent": requests_sent,
        }
    finally:
        client.close()
