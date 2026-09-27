"""Bounded, read-only inventory of standardized SAE Mode 01 PIDs."""
import socket

from .dme_check import DME_TARGET_ADDRESS
from .gateway_check import TESTER_ADDRESS, load_gateway_capture
from .hsfz import HsfzClient

CHECK_NAME = "HSFZ DME standardized Mode 01 PID inventory"
BITMAP_BASES = tuple(range(0x00, 0x100, 0x20))
FAILURE_REASONS = frozenset({
    "capture-invalid", "timeout", "connection-or-transport",
    "uds-rejected", "response-invalid", "unexpected-error",
})


class Mode01InventoryError(Exception):
    """Failure with an allowlisted reason and conservative request count."""

    def __init__(self, reason, requests_sent=0):
        self.reason = reason if reason in FAILURE_REASONS else "unexpected-error"
        self.requests_sent = requests_sent
        super().__init__(self.reason)


def _bitmap(response, base_pid):
    if isinstance(response, bytes) and response[:1] == b"\x7f":
        raise Mode01InventoryError("uds-rejected")
    if (not isinstance(response, bytes) or len(response) != 6
            or response[0] != 0x41 or response[1] != base_pid):
        raise Mode01InventoryError("response-invalid")
    return response[2:]


def _pid_supported(bitmap, ordinal):
    """Return whether one-based PID ordinal (1..32) is set in a bitmap."""
    return bool(int.from_bytes(bitmap, "big") & (1 << (32 - ordinal)))


def inventory_mode01(path, timeout=2.0, *, client_factory=HsfzClient,
                     connector_factory=socket.create_connection):
    """Read conditional support bitmaps, at most once for each base PID."""
    try:
        if not 0.1 <= float(timeout) <= 5.0:
            raise ValueError
        peer, interface, _gateway_target, _vin = load_gateway_capture(path)
    except Exception:
        raise Mode01InventoryError("capture-invalid") from None

    def source_bound_connector(address, connect_timeout):
        return connector_factory(address, connect_timeout, source_address=(interface, 0))

    try:
        client = client_factory(peer, TESTER_ADDRESS, DME_TARGET_ADDRESS, port=6801,
                                timeout=timeout, fail_on_pending=True,
                                sock_factory=source_bound_connector)
    except TimeoutError:
        raise Mode01InventoryError("timeout") from None
    except Exception:
        raise Mode01InventoryError("connection-or-transport") from None

    requests_sent = 0
    bitmaps = {}
    try:
        for base_pid in BITMAP_BASES:
            if base_pid and not _pid_supported(bitmaps[base_pid - 0x20], 32):
                break
            # Count before request: an exception cannot prove the frame was not sent.
            requests_sent += 1
            try:
                response = client.request(bytes((0x01, base_pid)))
            except TimeoutError:
                raise Mode01InventoryError("timeout", requests_sent) from None
            except Exception as exc:
                reason = "uds-rejected" if isinstance(exc, ConnectionError) and (
                    "pending UDS response" in str(exc) or "HSFZ error control" in str(exc)
                ) else "connection-or-transport"
                raise Mode01InventoryError(reason, requests_sent) from None
            try:
                bitmaps[base_pid] = _bitmap(response, base_pid)
            except Mode01InventoryError as exc:
                raise Mode01InventoryError(exc.reason, requests_sent) from None

        supported = []
        for base_pid, bitmap in bitmaps.items():
            for ordinal in range(1, 33):
                pid = base_pid + ordinal
                if pid < 0x100 and pid not in BITMAP_BASES and _pid_supported(bitmap, ordinal):
                    supported.append(f"0x{pid:02X}")

        return {
            "result": "verified", "check": CHECK_NAME,
            "supported_pids": sorted(supported),
            "highest_bitmap_base": f"0x{max(bitmaps):02X}",
            "requests_sent": requests_sent,
        }
    finally:
        client.close()
