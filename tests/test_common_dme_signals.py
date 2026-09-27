import contextlib
import io
import json
import socket
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from supra_telemetry import __main__ as cli
from supra_telemetry.common_dme_support import (
    CHECK_NAME, CommonDmeSupportError, verify_common_dme_support,
)
from supra_telemetry.dme_check import DME_TARGET_ADDRESS
from supra_telemetry.hsfz import HsfzClient, encode_frame, recv_frame


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


def bitmap(supported):
    value = sum(1 << (32 - pid) for pid in supported)
    return value.to_bytes(4, "big")


class CommonDmeSignalTests(unittest.TestCase):
    def test_single_bounded_bitmap_request_and_all_candidate_bits(self):
        with tempfile.TemporaryDirectory() as directory:
            path = private_capture(directory)
            left, right = socket.socketpair()
            seen = []

            def ecu():
                frame = recv_frame(right)
                seen.append(frame)
                right.sendall(encode_frame(1, DME_TARGET_ADDRESS, 0xF4,
                                           b"\x41\x00" + bitmap((0x0C, 0x0D, 0x0F))))

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

            result = verify_common_dme_support(path, client_factory=factory,
                                               connector_factory=connector)
            worker.join(1)
            right.close()
            self.assertEqual(result, {
                "result": "verified", "check": CHECK_NAME,
                "engine_rpm_pid_0c_supported": True,
                "vehicle_speed_pid_0d_supported": True,
                "intake_air_temp_pid_0f_supported": True,
                "throttle_position_pid_11_supported": False,
                "requests_sent": 1,
            })
            self.assertEqual(len(created), 1)
            self.assertEqual(len(seen), 1)
            self.assertEqual(seen[0].payload, b"\x01\x00")
            self.assertEqual((seen[0].source, seen[0].target), (0xF4, DME_TARGET_ADDRESS))
            self.assertEqual(left.fileno(), -1)

    def test_malformed_and_negative_responses_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = private_capture(directory)
            # HSFZ framing rejects too-short payloads before the support parser sees them.
            for payload, reason in ((b"\x41\x00\x00", ("response-invalid", "connection-or-transport")),
                                    # HSFZ request correlation rejects a wrong-PID positive reply early.
                                    (b"\x41\x20" + b"\0" * 4, ("response-invalid", "connection-or-transport")),
                                    (b"\x7f\x01\x31", "uds-rejected")):
                left, right = socket.socketpair()

                def ecu(sock=right, response=payload):
                    recv_frame(sock)
                    sock.sendall(encode_frame(1, DME_TARGET_ADDRESS, 0xF4, response))

                worker = threading.Thread(target=ecu)
                worker.start()
                with self.assertRaises(CommonDmeSupportError) as raised:
                    verify_common_dme_support(path, connector_factory=lambda *_a, **_kw: left)
                worker.join(1)
                right.close()
                self.assertIn(raised.exception.reason, reason if isinstance(reason, tuple) else (reason,))
                self.assertEqual(raised.exception.requests_sent, 1)
                self.assertEqual(left.fileno(), -1)

    def test_cli_failure_does_not_echo_capture_or_transport_details(self):
        stdout = io.StringIO()
        with patch.object(cli, "verify_common_dme_support",
                          side_effect=CommonDmeSupportError("timeout", 1)), \
                contextlib.redirect_stdout(stdout):
            self.assertEqual(cli.main(["verify-common-dme-support", "--capture", "private.json"]), 1)
        output = json.loads(stdout.getvalue())
        self.assertEqual(output["result"], "failed")
        self.assertEqual(output["requests_sent"], 1)
        self.assertEqual(output["reason"], "timeout")
        self.assertNotIn("private.json", stdout.getvalue())
        self.assertNotIn("VIN", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
