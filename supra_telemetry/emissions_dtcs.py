"""Bounded, read-only emissions DTC retrieval over the captured DME route."""
import re
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
_DTC_CODE = re.compile(r"[PCBU][0-3][0-9A-F]{3}\Z")
_MAX_CODES = 4094
PAYLOAD_ISSUES = frozenset({"count-mismatch", "invalid-shape", "odd-length"})


class DtcPayloadError(ValueError):
    """Malformed DTC response with a fixed structural category."""

    def __init__(self, issue):
        self.issue = issue if isinstance(issue, str) and issue in PAYLOAD_ISSUES else "invalid-shape"
        super().__init__(self.issue)


def _safe_completed_reads(completed_reads, failed_read):
    """Accept only a contiguous prefix of decoded reads preceding failed_read."""
    if not isinstance(completed_reads, dict) or not isinstance(failed_read, str):
        return {}
    labels = tuple(label for _, _, label in READS)
    try:
        failed_index = labels.index(failed_read)
    except ValueError:
        return {}
    keys = tuple(completed_reads)
    if keys != labels[:failed_index]:
        return {}
    safe = {}
    for label in keys:
        codes = completed_reads[label]
        if (not isinstance(codes, list) or len(codes) > _MAX_CODES
                or any(not isinstance(code, str) or not _DTC_CODE.fullmatch(code)
                       for code in codes)):
            return {}
        safe[label] = list(codes)
    return safe


class EmissionsDtcError(Exception):
    """Failure with an allowlisted public reason and conservative request count."""

    def __init__(self, reason, requests_sent=0, *, failed_read=None, payload_issue=None,
                 completed_reads=None):
        self.reason = reason if isinstance(reason, str) and reason in FAILURE_REASONS else "unexpected-error"
        self.requests_sent = requests_sent
        self.failed_read = (failed_read if isinstance(failed_read, str)
                            and failed_read in {label for _, _, label in READS} else None)
        self.payload_issue = (payload_issue if isinstance(payload_issue, str)
                              and payload_issue in PAYLOAD_ISSUES else None)
        self.completed_reads = _safe_completed_reads(completed_reads, self.failed_read)
        super().__init__(self.reason)


def decode_dtc(code):
    """Decode a two-byte SAE J2012 DTC integer to its five-character code."""
    if not isinstance(code, int) or isinstance(code, bool) or not 0 <= code <= 0xFFFF:
        raise ValueError("DTC must be a 16-bit integer")
    category = "PCBU"[(code >> 14) & 0x03]
    first_digit = (code >> 12) & 0x03
    return f"{category}{first_digit}{code & 0x0FFF:03X}"


def _parse_dtc_pairs(payload):
    codes = []
    padding_started = False
    for offset in range(0, len(payload), 2):
        code = (payload[offset] << 8) | payload[offset + 1]
        if code:
            if padding_started:
                raise DtcPayloadError("invalid-shape")
            codes.append(decode_dtc(code))
        else:
            padding_started = True
    return codes


def _parse_counted_dtc_payload(count, payload):
    """Decode ISO 15765-4's leading DTC item count and its following pairs."""
    if (type(count) is not int or not 0 <= count <= 0xFF
            or not isinstance(payload, bytes) or len(payload) % 2):
        raise DtcPayloadError("invalid-shape")
    codes = _parse_dtc_pairs(payload)
    if count != len(codes):
        raise DtcPayloadError("count-mismatch")
    return codes


def parse_dtc_payload(payload):
    """Parse an explicitly pair-only payload; zero padding must be trailing."""
    if not isinstance(payload, bytes):
        raise DtcPayloadError("invalid-shape")
    if len(payload) % 2:
        raise DtcPayloadError("invalid-shape")
    return _parse_dtc_pairs(payload)


def parse_counted_dtc_payload(payload):
    """Parse explicit ISO 15765-4 count-prefixed bytes after the service."""
    if not isinstance(payload, bytes) or not payload:
        raise DtcPayloadError("invalid-shape")
    count, pairs = payload[0], payload[1:]
    return _parse_counted_dtc_payload(count, pairs)


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

        def fail(reason, label, payload_issue=None):
            prior = {prior_label: result[f"{prior_label}_dtcs"]
                     for _, _, prior_label in READS[:next(
                         index for index, item in enumerate(READS) if item[2] == label)]}
            raise EmissionsDtcError(reason, requests_sent, failed_read=label,
                                    payload_issue=payload_issue,
                                    completed_reads=prior) from None

        for service, positive, label in READS:
            requests_sent += 1  # Count before request; send may precede a transport failure.
            try:
                response = client.request(bytes((service,)))
            except TimeoutError:
                fail("timeout", label)
            except Exception as exc:
                reason = "uds-rejected" if isinstance(exc, ConnectionError) and (
                    "pending UDS response" in str(exc) or "HSFZ error control" in str(exc)
                ) else "connection-or-transport"
                fail(reason, label)
            if isinstance(response, bytes) and response[:1] == b"\x7f":
                fail("uds-rejected", label)
            if not isinstance(response, bytes) or not response.startswith(bytes((positive,))):
                fail("response-invalid", label)
            try:
                result[f"{label}_dtcs"] = parse_counted_dtc_payload(response[1:])
            except DtcPayloadError as exc:
                fail("response-invalid", label, exc.issue)
            except Exception:
                fail("response-invalid", label, "invalid-shape")
        result.update({f"{label}_count": len(result[f"{label}_dtcs"]) for _, _, label in READS})
        result.update({"result": "verified", "check": CHECK_NAME, "requests_sent": requests_sent})
        return result
    finally:
        client.close()
