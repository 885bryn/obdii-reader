import json
import struct
import tempfile
import unittest
from pathlib import Path

from supra_telemetry.dme_check import DME_TARGET_ADDRESS
from supra_telemetry.vehicle_info import (
    CHECK_NAME, INFO_TYPES, VehicleInfoError, info_type_supported,
    verify_vehicle_info,
)


VIN = "TESTVIN0000000001"
MAC = "001122334455"


def private_capture(directory, diagnostic_address=0x10):
    body = (b"DIAGADR" + f"{diagnostic_address:02X}".encode() + b"BMWMAC"
            + MAC.encode() + b"BMWVIN" + VIN.encode())
    packet = struct.pack(">IH", len(body), 0x11) + body
    record = {"peer": "169.254.10.20", "port": 6811,
              "identification": {"vin": VIN, "mac": MAC,
                                 "diagnostic_address": diagnostic_address},
              "raw_hex": packet.hex()}
    path = Path(directory) / "capture.json"
    path.write_text(json.dumps({"interface": "169.254.10.30", "hsfz": [record]}), encoding="utf-8")
    return path


def support_bitmap(types):
    return sum(1 << (32 - item) for item in types).to_bytes(4, "big")


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []
        self.closed = False

    def request(self, payload):
        self.requests.append(payload)
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return response

    def close(self):
        self.closed = True


class VehicleInfoTests(unittest.TestCase):
    def test_bitmap_interpretation(self):
        bitmap = support_bitmap((2, 4, 6, 10))
        self.assertEqual([info_type_supported(bitmap, item) for item, _ in INFO_TYPES],
                         [True, True, True, True])
        self.assertFalse(info_type_supported(support_bitmap((2,)), 4))
        with self.assertRaises(ValueError):
            info_type_supported(b"\0", 2)

    def test_reads_advertised_types_once_in_fixed_order_and_returns_only_safe_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            path = private_capture(directory)
            private_data = VIN.encode()
            responses = [b"\x49\x00" + support_bitmap((2, 4, 6, 10)),
                         b"\x49\x02\x01" + private_data,
                         b"\x49\x04CAL-ID", b"\x49\x06\x00\x01", b"\x49\x0aECU"]
            client = FakeClient(responses)
            created = []

            def factory(*args, **kwargs):
                created.append((args, kwargs))
                # Verify the exact captured peer, fixed DME route, and source bind.
                self.assertEqual(args[:3], ("169.254.10.20", 0xF4, DME_TARGET_ADDRESS))
                self.assertEqual(kwargs["sock_factory"](("169.254.10.20", 6801), 2), "socket")
                return client

            def connector(address, timeout, *, source_address):
                self.assertEqual(address, ("169.254.10.20", 6801))
                self.assertEqual(source_address, ("169.254.10.30", 0))
                return "socket"

            result = verify_vehicle_info(path, client_factory=factory,
                                         connector_factory=connector)
            self.assertEqual(client.requests, [b"\x09\x00", b"\x09\x02", b"\x09\x04",
                                               b"\x09\x06", b"\x09\x0a"])
            self.assertEqual(result, {
                "result": "verified", "check": CHECK_NAME,
                "requests_sent": 5,
                "vin_match_supported": True, "vin_match": True,
                "calibration_id_supported": True,
                "calibration_id_response_received": True, "calibration_id_payload_length": 6,
                "calibration_verification_number_supported": True,
                "calibration_verification_number_response_received": True,
                "calibration_verification_number_payload_length": 2,
                "ecu_name_supported": True, "ecu_name_response_received": True,
                "ecu_name_payload_length": 3,
            })
            self.assertNotIn(VIN, repr(result))
            self.assertNotIn(MAC, repr(result))
            self.assertTrue(client.closed)

    def test_only_advertised_candidates_are_requested(self):
        with tempfile.TemporaryDirectory() as directory:
            path = private_capture(directory)
            client = FakeClient([b"\x49\x00" + support_bitmap((4,)), b"\x49\x04X"])
            result = verify_vehicle_info(path, client_factory=lambda *_a, **_k: client)
            self.assertEqual(client.requests, [b"\x09\x00", b"\x09\x04"])
            self.assertEqual(result["requests_sent"], 2)
            self.assertFalse(result["vin_match_supported"])
            self.assertTrue(result["calibration_id_response_received"])

    def test_errors_stop_without_leaking_response_or_exception_secrets_and_close(self):
        with tempfile.TemporaryDirectory() as directory:
            path = private_capture(directory)
            bad_responses = [b"\x49\x00" + support_bitmap((2,)),
                             b"\x49\x02\x01" + VIN.encode()]
            for response, reason, count in (
                (b"\x7f\x09\x31", "uds-rejected", 1),
                (b"\x49\x00\0", "response-invalid", 1),
                (TimeoutError("private " + VIN), "timeout", 1),
                (ConnectionError("private " + VIN), "connection-or-transport", 1),
            ):
                client = FakeClient([response])
                with self.assertRaises(VehicleInfoError) as raised:
                    verify_vehicle_info(path, client_factory=lambda *_a, **_k: client)
                self.assertEqual(raised.exception.reason, reason)
                self.assertEqual(raised.exception.requests_sent, count)
                self.assertEqual(str(raised.exception), reason)
                self.assertNotIn(VIN, str(raised.exception))
                self.assertEqual(len(client.requests), count)
                self.assertTrue(client.closed)

            for response in (b"\x49\x04", b"\x49\x05SECRET", b"\x49\x04" + b"A" * 257):
                client = FakeClient([bad_responses[0], response])
                with self.assertRaises(VehicleInfoError) as raised:
                    verify_vehicle_info(path, client_factory=lambda *_a, **_k: client)
                self.assertEqual(raised.exception.reason, "response-invalid")
                self.assertEqual(raised.exception.requests_sent, 2)
                self.assertEqual(len(client.requests), 2)
                self.assertTrue(client.closed)
                self.assertNotIn("SECRET", str(raised.exception))

            # A failure on a conditional read also stops the rest of the list.
            client = FakeClient([bad_responses[0], TimeoutError("private " + VIN)])
            with self.assertRaises(VehicleInfoError) as raised:
                verify_vehicle_info(path, client_factory=lambda *_a, **_k: client)
            self.assertEqual(raised.exception.reason, "timeout")
            self.assertEqual(raised.exception.requests_sent, 2)
            self.assertEqual(client.requests, [b"\x09\x00", b"\x09\x02"])
            self.assertTrue(client.closed)
            self.assertNotIn(VIN, str(raised.exception))

            # A VIN mismatch fails closed without revealing either VIN.
            client = FakeClient([bad_responses[0], b"\x49\x02\x01" + b"X" * 17])
            with self.assertRaises(VehicleInfoError) as raised:
                verify_vehicle_info(path, client_factory=lambda *_a, **_k: client)
            self.assertEqual(raised.exception.reason, "response-invalid")
            self.assertNotIn("X" * 17, repr(raised.exception.__dict__))

    def test_capture_gateway_address_is_not_mistaken_for_fixed_dme_target(self):
        with tempfile.TemporaryDirectory() as directory:
            path = private_capture(directory, diagnostic_address=0x10)
            client = FakeClient([b"\x49\x00" + support_bitmap(())])
            result = verify_vehicle_info(path, client_factory=lambda *_a, **_k: client)
            self.assertEqual(result["requests_sent"], 1)
            self.assertEqual(client.requests, [b"\x09\x00"])


if __name__ == "__main__":
    unittest.main()
