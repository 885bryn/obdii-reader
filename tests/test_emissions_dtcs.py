import json
import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path

from supra_telemetry.dme_check import DME_TARGET_ADDRESS
from supra_telemetry.emissions_dtcs import (
    CHECK_NAME, EmissionsDtcError, _parse_counted_dtc_payload, decode_dtc,
    parse_counted_dtc_payload, parse_dtc_payload, read_emissions_dtcs,
)
from supra_telemetry.hsfz import HsfzClient, encode_frame, recv_frame
from supra_telemetry.safety import SafetyPolicy, UnsafeRequest


def private_capture(directory):
    vin, mac = "TESTVIN0000000001", "001122334455"
    body = b"DIAGADR10BMWMAC" + mac.encode() + b"BMWVIN" + vin.encode()
    packet = struct.pack(">IH", len(body), 0x11) + body
    record = {"peer": "169.254.10.20", "port": 6811,
              "identification": {"vin": vin, "mac": mac, "diagnostic_address": 0x10},
              "raw_hex": packet.hex()}
    path = Path(directory) / "capture.json"
    path.write_text(json.dumps({"interface": "169.254.10.30", "hsfz": [record]}), encoding="utf-8")
    return path


class EmissionsDtcTests(unittest.TestCase):
    def test_decode_categories_empty_and_zero_padding(self):
        self.assertEqual([decode_dtc(n) for n in (0x0123, 0x4123, 0x8123, 0xC123)],
                         ["P0123", "C0123", "B0123", "U0123"])
        self.assertEqual(parse_dtc_payload(b""), [])
        self.assertEqual(parse_dtc_payload(bytes.fromhex("0123 C123 0000 0000")),
                         ["P0123", "U0123"])
        with self.assertRaises(ValueError) as malformed_pairs:
            parse_dtc_payload(bytes.fromhex("0123 0000 C123"))
        self.assertEqual(malformed_pairs.exception.issue, "invalid-shape")

    def test_count_prefixed_payloads_validate_count_and_preserve_zero_padding(self):
        self.assertEqual(parse_counted_dtc_payload(bytes.fromhex("01 0123")), ["P0123"])
        self.assertEqual(parse_counted_dtc_payload(bytes.fromhex("02 0123 C123 0000")),
                         ["P0123", "U0123"])
        self.assertEqual(parse_counted_dtc_payload(bytes.fromhex("00")), [])
        self.assertEqual(parse_counted_dtc_payload(bytes.fromhex("00 0000 0000")), [])
        with self.assertRaises(ValueError) as mismatch:
            parse_counted_dtc_payload(bytes.fromhex("02 0123"))
        self.assertEqual(mismatch.exception.issue, "count-mismatch")
        with self.assertRaises(ValueError) as zero_with_code:
            parse_counted_dtc_payload(bytes.fromhex("00 0123"))
        self.assertEqual(zero_with_code.exception.issue, "count-mismatch")
        with self.assertRaises(ValueError) as malformed_counted_pairs:
            parse_counted_dtc_payload(bytes.fromhex("02 0123 0000 C123"))
        self.assertEqual(malformed_counted_pairs.exception.issue, "invalid-shape")
        for truncated_or_extra in (bytes.fromhex("01 01"), bytes.fromhex("01 0123 00")):
            with self.subTest(payload=truncated_or_extra), self.assertRaises(ValueError) as malformed:
                parse_counted_dtc_payload(truncated_or_extra)
            self.assertEqual(malformed.exception.issue, "invalid-shape")
        # Pair-only bytes cannot be silently accepted as counted live framing.
        with self.assertRaises(ValueError) as wrong_framing:
            parse_counted_dtc_payload(bytes.fromhex("0123"))
        self.assertEqual(wrong_framing.exception.issue, "invalid-shape")
        with self.assertRaises(ValueError):
            parse_dtc_payload(bytearray(b"\x01"))
        for count in (True, -1, 256, "1"):
            with self.subTest(count=count), self.assertRaises(ValueError):
                _parse_counted_dtc_payload(count, b"")

    def test_exact_single_ordered_requests_captured_route_and_redacted_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = private_capture(directory)
            left, right = socket.socketpair()
            seen = []
            responses = (b"\x43\x01\x01\x23\x00\x00",
                         b"\x47\x01\x41\x23", b"\x4a\x01\xc1\x23")

            def ecu():
                for response in responses:
                    frame = recv_frame(right)
                    seen.append(frame)
                    right.sendall(encode_frame(1, DME_TARGET_ADDRESS, 0xF4, response))

            worker = threading.Thread(target=ecu)
            worker.start()
            created = []

            def factory(*args, **kwargs):
                created.append((args, kwargs))
                return HsfzClient(*args, **kwargs)

            def connector(address, timeout, *, source_address):
                self.assertEqual(address, ("169.254.10.20", 6801))
                self.assertEqual(source_address, ("169.254.10.30", 0))
                return left

            result = read_emissions_dtcs(path, client_factory=factory, connector_factory=connector)
            worker.join(1)
            right.close()
            self.assertEqual(result, {
                "result": "verified", "check": CHECK_NAME,
                "stored_dtcs": ["P0123"], "pending_dtcs": ["C0123"],
                "permanent_dtcs": ["U0123"], "stored_count": 1,
                "pending_count": 1, "permanent_count": 1, "requests_sent": 3,
            })
            self.assertEqual(len(created), 1)
            self.assertEqual([frame.payload for frame in seen], [b"\x03", b"\x07", b"\x0a"])
            self.assertTrue(all((frame.source, frame.target) == (0xF4, DME_TARGET_ADDRESS) for frame in seen))
            self.assertEqual(left.fileno(), -1)

    def test_invalid_negative_and_timeout_stop_without_retry_and_close(self):
        with tempfile.TemporaryDirectory() as directory:
            path = private_capture(directory)

            class Client:
                def __init__(self, outcome):
                    self.outcome, self.calls, self.closed = outcome, [], False

                def request(self, payload):
                    self.calls.append(payload)
                    if self.outcome == "timeout":
                        raise TimeoutError("private transport detail")
                    return self.outcome

                def close(self):
                    self.closed = True

            for outcome, reason in ((b"\x43\x01", "response-invalid"),
                                    (b"\x7f\x03\x31", "uds-rejected"),
                                    ("timeout", "timeout")):
                client = Client(outcome)
                with self.assertRaises(EmissionsDtcError) as raised:
                    read_emissions_dtcs(path, client_factory=lambda *_a, **_k: client)
                self.assertEqual(raised.exception.reason, reason)
                self.assertEqual(raised.exception.requests_sent, 1)
                if outcome == b"\x43\x01":
                    self.assertEqual(raised.exception.failed_read, "stored")
                    self.assertEqual(raised.exception.payload_issue, "count-mismatch")
                    self.assertEqual(str(raised.exception), "response-invalid")
                self.assertEqual(client.calls, [b"\x03"])
                self.assertTrue(client.closed)
                self.assertNotIn("private", str(raised.exception))

    def test_partial_failure_preserves_only_prior_decoded_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            path = private_capture(directory)

            class Client:
                def __init__(self):
                    self.calls = []
                    self.responses = [b"\x43\x01\x01\x23", b"\x47\x02\x01\x23"]

                def request(self, payload):
                    self.calls.append(payload)
                    return self.responses.pop(0)

                def close(self):
                    pass

            client = Client()
            with self.assertRaises(EmissionsDtcError) as caught:
                read_emissions_dtcs(path, client_factory=lambda *_a, **_k: client)
            self.assertEqual(client.calls, [b"\x03", b"\x07"])
            self.assertEqual(caught.exception.failed_read, "pending")
            self.assertEqual(caught.exception.payload_issue, "count-mismatch")
            self.assertEqual(caught.exception.completed_reads, {"stored": ["P0123"]})

    def test_live_path_rejects_pair_only_looking_truncated_counted_response(self):
        with tempfile.TemporaryDirectory() as directory:
            path = private_capture(directory)

            class Client:
                def __init__(self):
                    self.calls = []

                def request(self, payload):
                    self.calls.append(payload)
                    # Pair-only interpretation would decode this as P0101.
                    return b"\x43\x01\x01"

                def close(self):
                    pass

            client = Client()
            with self.assertRaises(EmissionsDtcError) as caught:
                read_emissions_dtcs(path, client_factory=lambda *_a, **_k: client)
            self.assertEqual(client.calls, [b"\x03"])
            self.assertEqual(caught.exception.reason, "response-invalid")
            self.assertEqual(caught.exception.payload_issue, "invalid-shape")

    def test_error_constructor_rejects_malicious_completed_reads(self):
        for invalid in (
                {"stored": ["VIN-SECRET"]},
                {"pending": ["P0123"]},
                {"stored": ["P0123"], "pending": ["P0123"]},
                {"stored": ["P0123", object()]},
                ["P0123"]):
            error = EmissionsDtcError("response-invalid", 2, failed_read="pending",
                                      completed_reads=invalid)
            self.assertEqual(error.completed_reads, {})

    def test_policy_allows_only_single_byte_dtc_reads_and_correlates_services(self):
        policy = SafetyPolicy()
        for service, positive in ((0x03, 0x43), (0x07, 0x47), (0x0A, 0x4A)):
            request = bytes((service,))
            self.assertEqual(policy.authorize(request).payload, request)
            self.assertTrue(policy.correlate(request, bytes((positive,))))
            self.assertTrue(policy.correlate(request, bytes((0x7F, service, 0x31))))
            with self.assertRaises(UnsafeRequest):
                policy.authorize(request + b"\x00")
        for prohibited in (b"\x04", b"\x08", b"\x04\x00", b"\x08\x01"):
            with self.assertRaises(UnsafeRequest):
                policy.authorize(prohibited)


if __name__ == "__main__":
    unittest.main()
