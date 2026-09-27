import json
import struct
import tempfile
import unittest
from pathlib import Path

from supra_telemetry.dme_check import DME_TARGET_ADDRESS
from supra_telemetry.mode01_inventory import (
    BITMAP_BASES, CHECK_NAME, Mode01InventoryError, inventory_mode01,
)
from supra_telemetry.gateway_check import TESTER_ADDRESS


def capture(directory):
    vin, mac = "TESTVIN0000000001", "001122334455"
    body = b"DIAGADR10BMWMAC" + mac.encode() + b"BMWVIN" + vin.encode()
    packet = struct.pack(">IH", len(body), 0x11) + body
    record = {"peer": "169.254.10.20", "port": 6811,
              "identification": {"vin": vin, "mac": mac, "diagnostic_address": 0x10},
              "raw_hex": packet.hex()}
    path = Path(directory) / "capture.json"
    path.write_text(json.dumps({"interface": "169.254.10.30", "hsfz": [record]}), encoding="utf-8")
    return path


def bitmap(*ordinals):
    return sum(1 << (32 - ordinal) for ordinal in ordinals).to_bytes(4, "big")


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


class Mode01InventoryTests(unittest.TestCase):
    def run_inventory(self, responses):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = capture(directory.name)
        client = FakeClient(responses)
        factory_calls = []

        def factory(*args, **kwargs):
            factory_calls.append((args, kwargs))
            # Exercise the captured-source binding without opening a socket.
            bound = kwargs["sock_factory"]((args[0], kwargs["port"]), kwargs["timeout"])
            self.assertEqual(bound, "bound")
            return client

        def connector(address, timeout, *, source_address):
            self.assertEqual(address, ("169.254.10.20", 6801))
            self.assertEqual(source_address, ("169.254.10.30", 0))
            return "bound"

        return inventory_mode01(path, client_factory=factory,
                                connector_factory=connector), client, factory_calls

    def test_conditional_termination_returns_privacy_safe_sorted_inventory(self):
        # 00 advertises PID 20, 20 does not advertise PID 40.
        result, client, calls = self.run_inventory([
            b"\x41\x00" + bitmap(1, 12, 32),
            b"\x41\x20" + bitmap(1, 31),
        ])
        self.assertEqual(client.requests, [b"\x01\x00", b"\x01\x20"])
        self.assertTrue(client.closed)
        self.assertEqual(len(calls), 1)
        args, kwargs = calls[0]
        self.assertEqual(args, ("169.254.10.20", TESTER_ADDRESS, DME_TARGET_ADDRESS))
        self.assertEqual(kwargs["port"], 6801)
        self.assertTrue(kwargs["fail_on_pending"])
        self.assertEqual(result, {
            "result": "verified", "check": CHECK_NAME,
            "supported_pids": ["0x01", "0x0C", "0x21", "0x3F"],
            "highest_bitmap_base": "0x20", "requests_sent": 2,
        })
        serialized = json.dumps(result)
        for private_value in ("TESTVIN", "001122334455", "169.254.10.20", "169.254.10.30", "raw_hex"):
            self.assertNotIn(private_value, serialized)

    def test_full_eight_request_ceiling_ascending_order_and_continuation_binding(self):
        responses = []
        for base in BITMAP_BASES[:-1]:
            responses.append(bytes((0x41, base)) + bitmap(32))
        responses.append(b"\x41\xE0" + bitmap(31))
        result, client, _ = self.run_inventory(responses)
        self.assertEqual(client.requests, [bytes((0x01, base)) for base in BITMAP_BASES])
        self.assertTrue(client.closed)
        self.assertEqual(result["requests_sent"], 8)
        self.assertEqual(result["highest_bitmap_base"], "0xE0")
        # Continuation bitmap PIDs are routing metadata, never signal entries.
        self.assertEqual(result["supported_pids"], ["0xFF"])

    def test_bitmap_bit_orientation(self):
        # First and last bits in one range map to base+1 and base+32.
        result, _, _ = self.run_inventory([
            b"\x41\x00" + bitmap(1, 32),
            b"\x41\x20" + bitmap(),
        ])
        self.assertEqual(result["supported_pids"], ["0x01"])

    def test_failures_stop_without_retry_and_always_close(self):
        cases = [
            ([b"\x41\x00\x00"], "response-invalid", 1),
            ([b"\x41\x20" + b"\0" * 4], "response-invalid", 1),
            ([b"\x7f\x01\x31"], "uds-rejected", 1),
            ([TimeoutError("private timeout detail")], "timeout", 1),
            ([ConnectionError("private transport detail")], "connection-or-transport", 1),
        ]
        for responses, reason, count in cases:
            with self.subTest(reason=reason, responses=responses):
                directory = tempfile.TemporaryDirectory()
                self.addCleanup(directory.cleanup)
                client = FakeClient(responses)
                with self.assertRaises(Mode01InventoryError) as raised:
                    inventory_mode01(capture(directory.name), client_factory=lambda *_a, **_k: client)
                self.assertEqual(raised.exception.reason, reason)
                self.assertEqual(raised.exception.requests_sent, count)
                self.assertEqual(len(client.requests), count)
                self.assertTrue(client.closed)
                self.assertNotIn("private", str(raised.exception))

    def test_capture_and_connection_failures_have_fixed_reasons(self):
        with self.assertRaises(Mode01InventoryError) as raised:
            inventory_mode01("missing-private-capture.json")
        self.assertEqual(raised.exception.reason, "capture-invalid")
        self.assertEqual(raised.exception.requests_sent, 0)

        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(Mode01InventoryError) as raised:
                inventory_mode01(capture(directory), client_factory=lambda *_a, **_k: (_ for _ in ()).throw(OSError("private")))
        self.assertEqual(raised.exception.reason, "connection-or-transport")
        self.assertEqual(raised.exception.requests_sent, 0)


if __name__ == "__main__":
    unittest.main()
