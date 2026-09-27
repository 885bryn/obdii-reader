import json
import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path

from supra_telemetry.dme_check import DME_TARGET_ADDRESS
from supra_telemetry.emissions_dtcs import (
    CHECK_NAME, EmissionsDtcError, decode_dtc, parse_dtc_payload, read_emissions_dtcs,
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
        self.assertEqual(parse_dtc_payload(bytes.fromhex("00000123 0000 C123")), ["P0123", "U0123"])
        with self.assertRaises(ValueError):
            parse_dtc_payload(b"\x01")

    def test_exact_single_ordered_requests_captured_route_and_redacted_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = private_capture(directory)
            left, right = socket.socketpair()
            seen = []
            responses = (b"\x43\x01\x23\x00\x00", b"\x47\x41\x23", b"\x4a\xc1\x23")

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
                self.assertEqual(client.calls, [b"\x03"])
                self.assertTrue(client.closed)
                self.assertNotIn("private", str(raised.exception))

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
