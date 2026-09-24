"""Standards-based DoIP discovery and vehicle announcement parsing only."""
import socket
import struct
import time
from dataclasses import dataclass

UDP_PORT = 13400
VERSION = 0x02
INVERSE_VERSION = VERSION ^ 0xFF
VEHICLE_IDENT_REQUEST = 0x0001
VEHICLE_ANNOUNCEMENT = 0x0004


@dataclass(frozen=True)
class DoipMessage:
    version: int
    payload_type: int
    payload: bytes


def encode_message(payload_type: int, payload: bytes = b"", *, version: int = VERSION) -> bytes:
    if version not in (0x02, 0x03):
        raise ValueError("unsupported DoIP protocol version")
    return struct.pack(">BBHI", version, version ^ 0xFF, payload_type, len(payload)) + payload


def parse_message(packet: bytes) -> DoipMessage:
    if len(packet) < 8:
        raise ValueError("truncated DoIP header")
    version, inverse, kind, length = struct.unpack(">BBHI", packet[:8])
    if version not in (0x02, 0x03) or inverse != (version ^ 0xFF) or length != len(packet) - 8:
        raise ValueError("invalid DoIP header or payload length")
    return DoipMessage(version, kind, packet[8:])


def parse_announcement(packet: bytes) -> dict:
    msg = parse_message(packet)
    if msg.payload_type != VEHICLE_ANNOUNCEMENT or len(msg.payload) < 32 or len(msg.payload) not in (32, 33):
        raise ValueError("not a valid DoIP vehicle announcement")
    payload = msg.payload
    return {"vin": payload[:17].decode("ascii", "strict"), "logical_address": payload[17:19].hex(),
            "eid": payload[19:25].hex(), "gid": payload[25:31].hex(),
            "further_action": payload[31], "sync_status": payload[32] if len(payload) == 33 else None}


def discover(interface: str, timeout: float = 0.6) -> list[dict]:
    """Send vehicle-identification request on selected interface IPv4 address."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    timeout = min(3.0, max(0.1, float(timeout)))
    found = []
    try:
        sock.bind((interface, 0))
        sock.sendto(encode_message(VEHICLE_IDENT_REQUEST), ("255.255.255.255", UDP_PORT))
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0: break
            sock.settimeout(remaining)
            try:
                packet, peer = sock.recvfrom(4096)
            except socket.timeout:
                break
            try:
                parsed = parse_message(packet)
                found.append({"peer": peer[0], "payload_type": parsed.payload_type, "announcement": parse_announcement(packet) if parsed.payload_type == VEHICLE_ANNOUNCEMENT else None, "raw_hex": packet.hex()})
            except ValueError:
                continue
    finally:
        sock.close()
    return found
