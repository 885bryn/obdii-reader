"""Single-request, read-only verification of a captured HSFZ gateway identity."""
import ipaddress
import json
import socket
from pathlib import Path

from .hsfz import HsfzClient, parse_discovery_response

TESTER_ADDRESS = 0xF4  # Community-corroborated convention; not Toyota-published.
VIN_REQUEST = b"\x22\xf1\x90"


def load_gateway_capture(path):
    """Validate one unambiguous HSFZ discovery record without leaking identifiers."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        interface = ipaddress.IPv4Address(data["interface"])
        if not interface.is_link_local:
            raise ValueError
        records = data["hsfz"]
        if not isinstance(records, list) or len(records) != 1:
            raise ValueError
        record = records[0]
        if not isinstance(record, dict) or record.get("port") != 6811:
            raise ValueError
        peer_address = ipaddress.IPv4Address(record["peer"])
        if not peer_address.is_link_local:
            raise ValueError
        peer = str(peer_address)
        if not isinstance(record.get("raw_hex"), str):
            raise ValueError
        raw_hex = record["raw_hex"]
        if len(raw_hex) % 2 or not raw_hex or any(c not in "0123456789abcdefABCDEF" for c in raw_hex):
            raise ValueError
        parsed = parse_discovery_response(bytes.fromhex(raw_hex))
        identification = record.get("identification")
        if not isinstance(identification, dict) or parsed["vin"] is None or parsed["mac"] is None:
            raise ValueError
        if identification.get("vin") != parsed["vin"] or identification.get("mac") != parsed["mac"]:
            raise ValueError
        if not isinstance(parsed["diagnostic_address"], int):
            raise ValueError
        if "diagnostic_address" in identification:
            captured_address = identification["diagnostic_address"]
            # Discovery serializes this parsed byte as a JSON integer. Reject
            # bools (which are ints in Python), strings, and out-of-range values.
            if (not isinstance(captured_address, int) or isinstance(captured_address, bool)
                    or not 0 <= captured_address <= 0xFF
                    or captured_address != parsed["diagnostic_address"]):
                raise ValueError
        return peer, str(interface), parsed["diagnostic_address"], parsed["vin"]
    except Exception as exc:
        raise ValueError("invalid or ambiguous HSFZ discovery capture") from exc


def verify_gateway(path, timeout=2.0, *, client_factory=HsfzClient, connector_factory=socket.create_connection):
    """Send one VIN read to the captured target and compare with discovery."""
    if not 0.1 <= float(timeout) <= 5.0:
        raise ValueError("timeout must be between 0.1 and 5 seconds")
    peer, interface, target, discovered_vin = load_gateway_capture(path)
    def source_bound_connector(address, connect_timeout):
        return connector_factory(address, connect_timeout, source_address=(interface, 0))
    client = client_factory(peer, TESTER_ADDRESS, target, port=6801, timeout=timeout,
                            fail_on_pending=True, sock_factory=source_bound_connector)
    try:
        response = client.request(VIN_REQUEST)
        if len(response) != 20 or response[:3] != b"\x62\xf1\x90":
            raise ValueError("unexpected VIN response")
        returned_vin = response[3:]
        if any(byte < 0x20 or byte > 0x7e for byte in returned_vin) or returned_vin.decode("ascii") != discovered_vin:
            raise ValueError("VIN response mismatch")
        return {"result": "verified", "check": "HSFZ gateway identity routing"}
    finally:
        client.close()
