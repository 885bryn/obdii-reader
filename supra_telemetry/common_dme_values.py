"""One-shot reads of the four capture-verified common DME Mode 01 values."""
import socket

from .dme_check import DME_TARGET_ADDRESS
from .gateway_check import TESTER_ADDRESS, load_gateway_capture
from .hsfz import HsfzClient
from .uds import mode01_value, parse_response

CHECK_NAME = "HSFZ DME common values"
SIGNALS = (
    (0x0C, "engine_rpm", 2),
    (0x0D, "vehicle_speed", 1),
    (0x0F, "intake_air_temperature", 1),
    (0x11, "throttle_position", 1),
)
FAILURE_REASONS = frozenset({
    "capture-invalid", "timeout", "connection-or-transport",
    "uds-rejected", "response-invalid", "unexpected-error",
})


class CommonDmeValuesError(Exception):
    """Failure with a fixed safe public reason and conservative request count."""

    def __init__(self, reason, requests_sent=0):
        self.reason = reason if reason in FAILURE_REASONS else "unexpected-error"
        self.requests_sent = requests_sent
        super().__init__(self.reason)


def parse_value_response(response, pid):
    """Validate an exact positive Mode 01 response and decode via canonical UDS codecs."""
    expected_width = dict((item[0], item[2]) for item in SIGNALS).get(pid)
    if expected_width is None or not isinstance(response, bytes):
        raise ValueError("invalid common value response")
    parsed = parse_response(response, 0x01)
    if not parsed.positive or len(response) != 2 + expected_width:
        raise ValueError("invalid common value response")
    if not parsed.data or parsed.data[0] != pid or len(parsed.data) != expected_width + 1:
        raise ValueError("invalid common value response")
    return mode01_value(pid, parsed.data[1:])


def read_common_dme_values(path, timeout=2.0, *, client_factory=HsfzClient,
                           connector_factory=socket.create_connection):
    """Read RPM, speed, intake temperature, then throttle once on the captured route."""
    try:
        if not 0.1 <= float(timeout) <= 5.0:
            raise ValueError
        peer, interface, _gateway_target, _vin = load_gateway_capture(path)
    except Exception:
        raise CommonDmeValuesError("capture-invalid") from None

    def source_bound_connector(address, connect_timeout):
        return connector_factory(address, connect_timeout, source_address=(interface, 0))

    try:
        client = client_factory(peer, TESTER_ADDRESS, DME_TARGET_ADDRESS, port=6801,
                                timeout=timeout, fail_on_pending=True,
                                sock_factory=source_bound_connector)
    except TimeoutError:
        raise CommonDmeValuesError("timeout") from None
    except Exception:
        raise CommonDmeValuesError("connection-or-transport") from None

    requests_sent = 0
    try:
        values = {}
        for pid, name, _width in SIGNALS:
            # Increment before entering transport: a send may have succeeded before failure.
            requests_sent += 1
            try:
                response = client.request(bytes((0x01, pid)))
            except TimeoutError:
                raise CommonDmeValuesError("timeout", requests_sent) from None
            except Exception as exc:
                reason = "uds-rejected" if isinstance(exc, ConnectionError) and (
                    "pending UDS response" in str(exc) or "HSFZ error control" in str(exc)
                ) else "connection-or-transport"
                raise CommonDmeValuesError(reason, requests_sent) from None
            if isinstance(response, bytes) and response[:1] == b"\x7f":
                raise CommonDmeValuesError("uds-rejected", requests_sent)
            try:
                value, unit = parse_value_response(response, pid)
            except Exception:
                raise CommonDmeValuesError("response-invalid", requests_sent) from None
            values[name] = {"value": value, "unit": unit}
        return {"result": "verified", "check": CHECK_NAME,
                "values": values, "requests_sent": requests_sent}
    finally:
        client.close()
