"""Single policy gateway for diagnostic requests."""
from dataclasses import dataclass


class UnsafeRequest(ValueError):
    pass


@dataclass(frozen=True)
class AllowedRequest:
    payload: bytes
    service: int


class SafetyPolicy:
    """Validate only known read services; callers cannot submit raw frames."""
    ALLOWED = frozenset((0x01, 0x03, 0x07, 0x09, 0x0A, 0x22, 0x3E))

    def authorize(self, payload: bytes, *, internal_tester_present: bool = False) -> AllowedRequest:
        if not isinstance(payload, bytes) or not payload:
            raise UnsafeRequest("diagnostic payload must be non-empty bytes")
        service = payload[0]
        if service not in self.ALLOWED:
            raise UnsafeRequest(f"service 0x{service:02X} is prohibited")
        if service == 0x01 and (len(payload) != 2 or not 0 <= payload[1] <= 0xFF):
            raise UnsafeRequest("Mode 01 requires exactly one PID")
        if service == 0x09 and (len(payload) != 2 or not 0 <= payload[1] <= 0xFF):
            raise UnsafeRequest("Mode 09 requires exactly one information type")
        if service in (0x03, 0x07, 0x0A) and len(payload) != 1:
            raise UnsafeRequest("emissions DTC reads do not accept request data")
        if service == 0x22 and (len(payload) != 3 or payload[1] == payload[2] == 0):
            raise UnsafeRequest("ReadDataByIdentifier requires exactly one non-zero 16-bit DID")
        if service == 0x3E and (not internal_tester_present or payload != b"\x3e\x00"):
            raise UnsafeRequest("TesterPresent is reserved for the internal keep-alive")
        return AllowedRequest(payload, service)

    def correlate(self, request: bytes, response: bytes) -> bool:
        """Check positive/negative response service correlation."""
        if not response:
            return False
        service = request[0]
        if response[0] == 0x7F:
            return len(response) >= 3 and response[1] == service
        expected = {0x01: 0x41, 0x03: 0x43, 0x07: 0x47, 0x09: 0x49,
                    0x0A: 0x4A, 0x22: 0x62, 0x3E: 0x7E}[service]
        if response[0] != expected:
            return False
        if service in (0x01, 0x09):
            return len(response) >= 2 and response[1] == request[1]
        if service == 0x22:
            return len(response) >= 3 and response[1:3] == request[1:3]
        return True
