"""Single-request, read-only verification of a captured DME identity route."""
import socket

from .gateway_check import TESTER_ADDRESS, VIN_REQUEST, load_gateway_capture
from .hsfz import HsfzClient

# Community-corroborated candidate only; Toyota has not published this routing
# address for the user's Supra. This check makes no signal/PID claims.
DME_TARGET_ADDRESS = 0x12


def verify_dme(path, timeout=2.0, *, client_factory=HsfzClient, connector_factory=socket.create_connection):
    """Send exactly one VIN read through the candidate DME route in the capture."""
    if not 0.1 <= float(timeout) <= 5.0:
        raise ValueError("timeout must be between 0.1 and 5 seconds")
    peer, interface, _gateway_target, discovered_vin = load_gateway_capture(path)

    def source_bound_connector(address, connect_timeout):
        return connector_factory(address, connect_timeout, source_address=(interface, 0))

    client = client_factory(peer, TESTER_ADDRESS, DME_TARGET_ADDRESS, port=6801,
                            timeout=timeout, fail_on_pending=True,
                            sock_factory=source_bound_connector)
    try:
        response = client.request(VIN_REQUEST)
        if len(response) != 20 or response[:3] != b"\x62\xf1\x90":
            raise ValueError("unexpected VIN response")
        returned_vin = response[3:]
        if any(byte < 0x20 or byte > 0x7e for byte in returned_vin) or returned_vin.decode("ascii") != discovered_vin:
            raise ValueError("VIN response mismatch")
        return {"result": "verified", "check": "HSFZ DME identity routing"}
    finally:
        client.close()
