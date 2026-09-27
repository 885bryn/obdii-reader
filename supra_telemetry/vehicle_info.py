"""Bounded, privacy-safe Mode 09 information availability check."""
import socket

from .dme_check import DME_TARGET_ADDRESS
from .gateway_check import TESTER_ADDRESS, load_gateway_capture
from .hsfz import HsfzClient

CHECK_NAME = "HSFZ DME Mode 09 information availability"
# InfoTypes to check, in fixed order. This deliberately excludes the wider
# Mode 09 catalogue and reads values only to compare/measure them in memory.
INFO_TYPES = ((0x02, "vin_match"), (0x04, "calibration_id"),
              (0x06, "calibration_verification_number"), (0x0A, "ecu_name"))
MAX_INFO_PAYLOAD = 256
FAILURE_REASONS = frozenset({
    "capture-invalid", "timeout", "connection-or-transport",
    "uds-rejected", "response-invalid", "unexpected-error",
})


class VehicleInfoError(Exception):
    """Failure exposing only a fixed safe reason and conservative request count."""

    def __init__(self, reason, requests_sent=0):
        self.reason = reason if reason in FAILURE_REASONS else "unexpected-error"
        self.requests_sent = requests_sent
        super().__init__(self.reason)


def info_type_supported(bitmap, info_type):
    """Return the SAE Mode 09 support bit for an InfoType in a four-byte map."""
    if not isinstance(bitmap, bytes) or len(bitmap) != 4:
        raise ValueError("bitmap must be four bytes")
    if not isinstance(info_type, int) or isinstance(info_type, bool) or not 1 <= info_type <= 0x20:
        raise ValueError("InfoType is outside bitmap range")
    return bool(int.from_bytes(bitmap, "big") & (1 << (32 - info_type)))


def _safe_request(client, payload, requests_sent):
    """Make one request and map all transport details to safe categories."""
    try:
        response = client.request(payload)
    except TimeoutError:
        raise VehicleInfoError("timeout", requests_sent + 1) from None
    except ConnectionError as exc:
        reason = "uds-rejected" if ("pending UDS response" in str(exc)
                                     or "HSFZ error control" in str(exc)) else "connection-or-transport"
        raise VehicleInfoError(reason, requests_sent + 1) from None
    except Exception:
        raise VehicleInfoError("connection-or-transport", requests_sent + 1) from None
    new_count = requests_sent + 1
    if isinstance(response, bytes) and response[:1] == b"\x7f":
        raise VehicleInfoError("uds-rejected", new_count)
    return response, new_count


def verify_vehicle_info(path, timeout=2.0, *, client_factory=HsfzClient,
                        connector_factory=socket.create_connection):
    """Check supported Mode 09 types on the capture-bound, verified DME route.

    The method requests 09 00 once, then each advertised candidate at most
    once. Raw values never leave this function.
    """
    try:
        if not 0.1 <= float(timeout) <= 5.0:
            raise ValueError
        peer, interface, _gateway_target, captured_vin = load_gateway_capture(path)
        vin_bytes = captured_vin.encode("ascii")
        if len(vin_bytes) != 17:
            raise ValueError
    except VehicleInfoError:
        raise
    except Exception:
        raise VehicleInfoError("capture-invalid") from None

    def source_bound_connector(address, connect_timeout):
        return connector_factory(address, connect_timeout, source_address=(interface, 0))

    try:
        client = client_factory(peer, TESTER_ADDRESS, DME_TARGET_ADDRESS, port=6801,
                                timeout=timeout, fail_on_pending=True,
                                sock_factory=source_bound_connector)
    except TimeoutError:
        raise VehicleInfoError("timeout") from None
    except Exception:
        raise VehicleInfoError("connection-or-transport") from None

    requests_sent = 0
    try:
        response, requests_sent = _safe_request(client, b"\x09\x00", requests_sent)
        if (not isinstance(response, bytes) or len(response) != 6
                or response[:2] != b"\x49\x00"):
            raise VehicleInfoError("response-invalid", requests_sent)
        bitmap = response[2:]
        result = {"result": "verified", "check": CHECK_NAME,
                  "requests_sent": requests_sent}
        for info_type, key in INFO_TYPES:
            if not info_type_supported(bitmap, info_type):
                result[f"{key}_supported"] = False
                continue
            response, requests_sent = _safe_request(
                client, bytes((0x09, info_type)), requests_sent)
            if (not isinstance(response, bytes) or len(response) < 3
                    or len(response) > 2 + MAX_INFO_PAYLOAD
                    or response[:2] != bytes((0x49, info_type))):
                raise VehicleInfoError("response-invalid", requests_sent)
            value = response[2:]
            if not value:
                raise VehicleInfoError("response-invalid", requests_sent)
            result[f"{key}_supported"] = True
            if info_type == 0x02:
                # SAE response includes an item count byte before the 17 VIN
                # characters. Compare only; never return or retain either VIN.
                if len(value) != 18 or value[0] != 1 or value[1:] != vin_bytes:
                    raise VehicleInfoError("response-invalid", requests_sent)
                result["vin_match"] = True
            else:
                result[f"{key}_response_received"] = True
                result[f"{key}_payload_length"] = len(value)
        result["requests_sent"] = requests_sent
        return result
    finally:
        client.close()
