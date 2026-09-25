"""BMW HSFZ Ethernet framing, UDP discovery, and read-only TCP client."""
import socket
import struct
import threading
import time
from dataclasses import dataclass
from .models import RawExchange, utc_now
from .safety import SafetyPolicy

TCP_PORT = 6801
UDP_PORT = 6811
DIAGNOSTIC = 0x0001
TRANSFER_ACK = 0x0002
VEHICLE_IDENT = 0x0011
ERROR_CONTROLS = set(range(0x0040, 0x0046)) | {0x00FF}
MAX_BODY = 8192


@dataclass(frozen=True)
class HsfzFrame:
    control: int
    source: int | None
    target: int | None
    payload: bytes = b""
    extra: bytes = b""


def encode_frame(control: int, source: int, target: int, payload: bytes = b"") -> bytes:
    """Encode diagnostic/ACK/alive-style HSFZ frame (length counts src+target+UDS)."""
    if not 0 <= control <= 0xFFFF or not 0 <= source <= 255 or not 0 <= target <= 255:
        raise ValueError("invalid HSFZ control/address")
    body = bytes((source, target)) + bytes(payload)
    if len(body) > MAX_BODY:
        raise ValueError("HSFZ body exceeds safety limit")
    return struct.pack(">IH", len(body), control) + body


def encode_control(control: int, payload: bytes = b"") -> bytes:
    """Encode a control message without source/target bytes, used by UDP discovery."""
    body = bytes(payload)
    if len(body) > MAX_BODY:
        raise ValueError("HSFZ body exceeds safety limit")
    return struct.pack(">IH", len(body), control) + body


def read_exact(sock: socket.socket, size: int, deadline: float | None = None) -> bytes:
    result = bytearray()
    while len(result) < size:
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0: raise TimeoutError("HSFZ receive deadline exceeded")
            sock.settimeout(remaining)
        chunk = sock.recv(size - len(result))
        if not chunk:
            raise ConnectionError("HSFZ peer closed the connection")
        result.extend(chunk)
    return bytes(result)


def parse_frame(header: bytes, body: bytes) -> HsfzFrame:
    if len(header) != 6:
        raise ValueError("HSFZ header must be six bytes")
    length, control = struct.unpack(">IH", header)
    if length != len(body) or length > MAX_BODY:
        raise ValueError("invalid or oversized HSFZ body length")
    if control == 0x0012 and len(body) == 2:
        return HsfzFrame(control, body[0], body[1], b"")
    if control == 0x0012:
        # Scapy documents longer 0x12 frames as carrying an identification string.
        return HsfzFrame(control, None, None, body, body)
    if control in (DIAGNOSTIC, TRANSFER_ACK):
        if len(body) < 2:
            raise ValueError("HSFZ message is missing source/target addresses")
        return HsfzFrame(control, body[0], body[1], body[2:])
    return HsfzFrame(control, None, None, body)


def recv_frame(sock: socket.socket, deadline: float | None = None) -> HsfzFrame:
    header = read_exact(sock, 6, deadline)
    length, _ = struct.unpack(">IH", header)
    if length > MAX_BODY:
        raise ValueError("HSFZ body exceeds safety limit")
    return parse_frame(header, read_exact(sock, length, deadline) if length else b"")


def parse_discovery_response(packet: bytes) -> dict:
    if len(packet) < 6:
        raise ValueError("truncated HSFZ discovery header")
    length, control = struct.unpack(">IH", packet[:6])
    if length != len(packet) - 6 or length > MAX_BODY or control != VEHICLE_IDENT:
        raise ValueError("invalid HSFZ vehicle identification response")
    body = packet[6:]
    marker = b"DIAGADR"
    idx = body.find(marker)
    if idx < 0 or body.find(marker, idx + len(marker)) >= 0 or idx + len(marker) + 2 > len(body):
        raise ValueError("unrecognized HSFZ identification response")
    address_text = body[idx + len(marker):idx + len(marker) + 2]
    if any(c not in b"0123456789abcdefABCDEF" for c in address_text):
        raise ValueError("malformed HSFZ diagnostic address")
    def marker_value(marker: bytes, size: int):
        idx = body.find(marker)
        if idx < 0 or idx + len(marker) + size > len(body):
            return None
        raw = body[idx + len(marker):idx + len(marker) + size]
        return raw.decode("ascii", "replace")
    return {"vin": marker_value(b"BMWVIN", 17), "mac": marker_value(b"BMWMAC", 12),
            "diagnostic_address": int(address_text, 16)}


def discover(local_ipv4: str, timeout: float = 0.6, *, broadcast: str = "169.254.255.255", port: int = UDP_PORT) -> list[dict]:
    """Send exactly one HSFZ ident request and collect bounded candidate replies."""
    timeout = min(3.0, max(0.1, float(timeout)))
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.settimeout(timeout)
    found = []
    try:
        sock.bind((local_ipv4, 0))
        sock.sendto(bytes.fromhex("000000000011"), (broadcast, port))
        deadline = time.monotonic() + timeout
        while True:
            left = deadline - time.monotonic()
            if left <= 0:
                break
            sock.settimeout(left)
            try:
                packet, peer = sock.recvfrom(4096)
            except socket.timeout:
                break
            try:
                identification = parse_discovery_response(packet)
            except ValueError:
                identification = None
            found.append({"peer": peer[0], "port": peer[1], "identification": identification, "raw_hex": packet.hex()})
    finally:
        sock.close()
    return found


class HsfzClient:
    """One-connection, one-in-flight read client; caller supplies all addresses."""
    def __init__(self, host: str, source: int, target: int, port: int = TCP_PORT, timeout: float = 2.0,
                 policy: SafetyPolicy | None = None, audit=None, sock_factory=socket.create_connection,
                 fail_on_pending: bool = False):
        self.host, self.port, self.source, self.target = host, port, source, target
        self.timeout = min(10.0, max(0.1, float(timeout)))
        self.policy, self.audit, self.sock_factory = policy or SafetyPolicy(), audit, sock_factory
        self.fail_on_pending = fail_on_pending
        self._lock = threading.Lock()
        self._state_lock = threading.Lock()
        self._closed = False
        self._socket = None
        self.connected = False

    def close(self):
        # Deliberately does not wait for the request lock: shutdown must be
        # able to interrupt a blocked bounded receive in the acquisition thread.
        with self._state_lock:
            self._closed = True
            sock, self._socket = self._socket, None
            self.connected = False
        if sock is not None: sock.close()

    def _connect(self):
        if self._socket is None:
            sock = self.sock_factory((self.host, self.port), self.timeout)
            with self._state_lock:
                if self._closed:
                    sock.close()
                    raise ConnectionError("HSFZ client is closed")
                self._socket = sock
        self.connected = True
        self._socket.settimeout(self.timeout)

    def request(self, payload: bytes) -> bytes:
        authorized = self.policy.authorize(payload)
        if authorized.service not in (0x01, 0x09, 0x22):
            raise ValueError("only explicitly requested data reads are supported by HSFZ client")
        with self._lock:
            if self._closed: raise ConnectionError("HSFZ client is closed")
            request_frame = encode_frame(DIAGNOSTIC, self.source, self.target, authorized.payload)
            started = utc_now(); received = bytearray(); outcome = "error"
            try:
                self._connect()
                self._socket.sendall(request_frame)
                deadline = time.monotonic() + self.timeout
                while True:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0: raise TimeoutError("HSFZ response deadline exceeded")
                    self._socket.settimeout(remaining)
                    frame = recv_frame(self._socket, deadline)
                    received.extend(struct.pack(">IH", len(frame.payload) + (2 if frame.source is not None else 0), frame.control))
                    if frame.source is not None: received.extend((frame.source, frame.target))
                    received.extend(frame.payload)
                    if frame.control in ERROR_CONTROLS:
                        raise ConnectionError(f"HSFZ error control 0x{frame.control:04X}")
                    if frame.control == TRANSFER_ACK:
                        continue
                    if frame.control == 0x0012:
                        # Preserve raw bytes in audit; do not invent an alive reply.
                        continue
                    if frame.control != DIAGNOSTIC:
                        raise ConnectionError(f"unexpected HSFZ control 0x{frame.control:04X}")
                    if (frame.source, frame.target) != (self.target, self.source):
                        raise ConnectionError("HSFZ response source/target mismatch")
                    response = frame.payload
                    if not self.policy.correlate(payload, response):
                        raise ConnectionError("UDS response does not correlate with request")
                    if response[:1] == b"\x7f" and len(response) >= 3 and response[2] == 0x78:
                        if self.fail_on_pending:
                            raise ConnectionError("pending UDS response is not accepted")
                        continue
                    outcome = "ok"
                    return response
            except Exception:
                if self._socket is not None:
                    try: self._socket.close()
                    finally: self._socket = None
                self.connected = False
                raise
            finally:
                if self.audit:
                    self.audit(RawExchange(started, "HSFZ/TCP", request_frame, bytes(received), outcome))
