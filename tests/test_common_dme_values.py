import json
import struct
import tempfile
import unittest
from pathlib import Path

from supra_telemetry.common_dme_values import (
    CHECK_NAME, CommonDmeValuesError, read_common_dme_values,
)
from supra_telemetry.dme_check import DME_TARGET_ADDRESS
from supra_telemetry.gateway_check import TESTER_ADDRESS
from supra_telemetry.hsfz import MalformedUdsResponse


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


class FakeClient:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []
        self.closed = False

    def request(self, payload):
        self.requests.append(payload)
        response = self.responses[len(self.requests) - 1]
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        self.closed = True


class CommonDmeValueTests(unittest.TestCase):
    def make_factory(self, client, collected):
        def factory(*args, **kwargs):
            collected["args"] = args
            collected["kwargs"] = kwargs
            return client
        return factory

    def test_exact_order_route_binding_decoding_and_close(self):
        responses = (b"\x41\x0c\x1f\x40", b"\x41\x0d\x3c",
                     b"\x41\x0f\x50", b"\x41\x11\x80")
        client, collected, connector_calls = FakeClient(responses), {}, []
        with tempfile.TemporaryDirectory() as directory:
            result = read_common_dme_values(private_capture(directory),
                client_factory=self.make_factory(client, collected),
                connector_factory=lambda *a, **kw: connector_calls.append((a, kw)) or "socket")

        self.assertEqual(client.requests, [b"\x01\x0c", b"\x01\x0d", b"\x01\x0f", b"\x01\x11"])
        self.assertEqual(collected["args"], ("169.254.10.20", TESTER_ADDRESS, DME_TARGET_ADDRESS))
        self.assertEqual(collected["kwargs"]["port"], 6801)
        self.assertEqual(collected["kwargs"]["fail_on_pending"], True)
        self.assertEqual(collected["kwargs"]["timeout"], 2.0)
        # Exercise and verify the source-bound connector closure.
        socket_value = collected["kwargs"]["sock_factory"](("169.254.10.20", 6801), 2.0)
        self.assertEqual(socket_value, "socket")
        self.assertEqual(connector_calls, [((("169.254.10.20", 6801), 2.0), {
            "source_address": ("169.254.10.30", 0),
        })])
        self.assertEqual(result, {
            "result": "verified", "check": CHECK_NAME, "requests_sent": 4,
            "values": {
                "engine_rpm": {"value": 2000.0, "unit": "rpm"},
                "vehicle_speed": {"value": 60.0, "unit": "km/h"},
                "intake_air_temperature": {"value": 40.0, "unit": "°C"},
                "throttle_position": {"value": 128 * 100 / 255, "unit": "%"},
            },
        })
        self.assertEqual(client.closed, True)

    def test_first_failure_stops_and_closes_without_leaking_details(self):
        cases = (
            (b"\x41\x0d\x01", "response-invalid"),
            (b"\x7f\x01\x31", "uds-rejected"),
            # HSFZ raises this for a malformed extra-byte NRC 0x78 frame;
            # its text must not trigger the legacy valid-pending classifier.
            (MalformedUdsResponse("malformed UDS negative response"),
             "connection-or-transport"),
            (TimeoutError("private address and VIN"), "timeout"),
        )
        for first_response, reason in cases:
            client, collected = FakeClient([first_response]), {}
            with tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(CommonDmeValuesError) as raised:
                    read_common_dme_values(private_capture(directory),
                        client_factory=self.make_factory(client, collected))
            self.assertEqual(raised.exception.reason, reason)
            self.assertEqual(raised.exception.requests_sent, 1)
            self.assertEqual(client.requests, [b"\x01\x0c"])
            self.assertTrue(client.closed)
            self.assertNotIn("private address", str(raised.exception))
            self.assertNotIn("VIN", repr(raised.exception.__dict__))
            if isinstance(first_response, MalformedUdsResponse):
                self.assertNotIn("pending UDS response", str(first_response))

    def test_invalid_capture_does_not_connect(self):
        connected = []
        with self.assertRaises(CommonDmeValuesError) as raised:
            read_common_dme_values("private capture name", connector_factory=lambda *a, **k: connected.append(1))
        self.assertEqual(raised.exception.reason, "capture-invalid")
        self.assertEqual(raised.exception.requests_sent, 0)
        self.assertEqual(connected, [])
        self.assertNotIn("private capture name", str(raised.exception))


if __name__ == "__main__":
    unittest.main()
