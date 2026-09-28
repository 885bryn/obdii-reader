import contextlib
import io
import json
import unittest
from unittest.mock import patch

from supra_telemetry import __main__ as cli
from supra_telemetry.common_dme_values import CommonDmeValuesError
from supra_telemetry.emissions_dtcs import EmissionsDtcError
from supra_telemetry.mode01_inventory import Mode01InventoryError
from supra_telemetry.read_only_suite import SuiteError
from supra_telemetry.vehicle_info import VehicleInfoError


class ReadOnlyCliTests(unittest.TestCase):
    def invoke(self, command):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = cli.main([command, "--capture", "private.json"])
        return status, json.loads(output.getvalue())

    def test_new_commands_emit_their_safe_success_results(self):
        cases = (
            ("inventory-mode01-support", "inventory_mode01",
             {"result": "verified", "check": "inventory", "supported_pids": ["0x0C"],
              "highest_bitmap_base": "0x00", "requests_sent": 1}),
            ("read-common-dme-values", "read_common_dme_values",
             {"result": "verified", "check": "values", "values": {}, "requests_sent": 4}),
            ("read-emissions-dtcs", "read_emissions_dtcs",
             {"result": "verified", "check": "dtcs", "stored_dtcs": [],
              "pending_dtcs": [], "permanent_dtcs": [], "requests_sent": 3}),
            ("verify-vehicle-info", "verify_vehicle_info",
             {"result": "verified", "check": "info", "requests_sent": 1}),
            ("collect-read-only-suite", "run_read_only_suite",
             {"result": "verified", "check": "suite", "completed_phases": [],
              "phase_results": {}, "total_requests": 0}),
        )
        for command, function, expected in cases:
            with self.subTest(command=command), patch.object(cli, function, return_value=expected):
                status, result = self.invoke(command)
                self.assertEqual(status, 0)
                self.assertEqual(result, expected)

    def test_new_commands_redact_all_exception_details(self):
        secret = "TESTVIN0000000001 169.254.10.20 001122334455"
        cases = (
            ("inventory-mode01-support", "inventory_mode01",
             Mode01InventoryError("timeout", 1)),
            ("read-common-dme-values", "read_common_dme_values",
             CommonDmeValuesError("timeout", 2)),
            ("read-emissions-dtcs", "read_emissions_dtcs",
             EmissionsDtcError("timeout", 2)),
            ("verify-vehicle-info", "verify_vehicle_info",
             VehicleInfoError("timeout", 2)),
        )
        for command, function, error in cases:
            error.__cause__ = RuntimeError(secret)
            with self.subTest(command=command), patch.object(cli, function, side_effect=error):
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    status = cli.main([command, "--capture", secret])
                result = json.loads(output.getvalue())
                self.assertEqual(status, 1)
                self.assertEqual(result["reason"], "timeout")
                self.assertNotIn(secret, output.getvalue())
                self.assertNotIn("TESTVIN", output.getvalue())
                self.assertNotIn("169.254", output.getvalue())

    def test_unexpected_errors_have_fixed_public_shape(self):
        cases = (
            ("inventory-mode01-support", "inventory_mode01"),
            ("read-common-dme-values", "read_common_dme_values"),
            ("read-emissions-dtcs", "read_emissions_dtcs"),
            ("verify-vehicle-info", "verify_vehicle_info"),
            ("collect-read-only-suite", "run_read_only_suite"),
        )
        for command, function in cases:
            with self.subTest(command=command), patch.object(
                    cli, function, side_effect=RuntimeError("private raw response")):
                status, result = self.invoke(command)
                self.assertEqual(status, 1)
                self.assertEqual(result["reason"], "unexpected-error")
                self.assertNotIn("private raw response", json.dumps(result))

    def test_suite_failure_reports_only_safe_progress(self):
        error = SuiteError("read_emissions_dtcs", "uds-rejected", 9,
                           ("inventory_mode01", "read_common_dme_values"), {
                               "inventory_mode01": {"requests_sent": 2,
                                   "supported_pids": ["0x0C", "0x0D", "0x0F", "0x11"],
                                   "highest_bitmap_base": "0x00",
                                   "peer": "169.254.1.2", "raw": "VIN-SECRET"},
                               "read_common_dme_values": {"requests_sent": 4,
                                   "values": {
                                       "engine_rpm": {"value": 750.0, "unit": "rpm"},
                                       "vehicle_speed": {"value": 0.0, "unit": "km/h"},
                                       "intake_air_temperature": {"value": 25.0, "unit": "°C"},
                                       "throttle_position": {"value": 12.0, "unit": "%"}},
                                   "private_field": "VIN-SECRET"},
                           }, {"failed_read": "pending", "payload_issue": "odd-length",
                               "completed_reads": {"stored": ["P0123"]}})
        with patch.object(cli, "run_read_only_suite", side_effect=error):
            status, result = self.invoke("collect-read-only-suite")
        self.assertEqual(status, 1)
        self.assertEqual(result, {
            "result": "failed", "check": cli.READ_ONLY_SUITE_CHECK,
            "failed_phase": "read_emissions_dtcs", "reason": "uds-rejected",
            "completed_phases": ["inventory_mode01", "read_common_dme_values"],
            "completed_summaries": {"inventory_mode01": {
                "requests_sent": 2, "supported_pids": ["0x0C", "0x0D", "0x0F", "0x11"],
                "highest_bitmap_base": "0x00"},
                "read_common_dme_values": {"requests_sent": 4, "values": {
                    "engine_rpm": {"value": 750.0, "unit": "rpm"},
                    "vehicle_speed": {"value": 0.0, "unit": "km/h"},
                    "intake_air_temperature": {"value": 25.0, "unit": "°C"},
                    "throttle_position": {"value": 12.0, "unit": "%"}}}},
            "dtc_failure": {"read": "pending", "completed_reads": {
                                "stored": {"dtcs": ["P0123"], "count": 1}},
                            "payload_issue": "odd-length"},
            "total_requests": 9,
        })
        self.assertNotIn("VIN-SECRET", json.dumps(result))

    def test_direct_dtc_cli_failure_includes_only_fixed_structure(self):
        error = EmissionsDtcError("response-invalid", 2, failed_read="pending",
                                  payload_issue="odd-length",
                                  completed_reads={"stored": ["P0123"]})
        with patch.object(cli, "read_emissions_dtcs", side_effect=error):
            status, result = self.invoke("read-emissions-dtcs")
        self.assertEqual(status, 1)
        self.assertEqual(result["dtc_failure"], {
            "read": "pending", "completed_reads": {
                "stored": {"dtcs": ["P0123"], "count": 1}},
            "payload_issue": "odd-length"})
        self.assertEqual(result["requests_sent"], 2)
        self.assertNotIn("bytes", json.dumps(result))

    def test_common_dme_monitor_cli_wires_capture_timeout_duration_and_safe_runner_mode(self):
        source = object()
        with patch.object(cli, "CommonDmeMonitorSource", return_value=source) as source_factory, \
                patch.object(cli, "run_monitor", return_value=0) as runner:
            status = cli.main(["monitor-common-dme", "--capture", "private.json",
                               "--duration", "42", "--timeout", "1.5", "--port", "0"])
        self.assertEqual(status, 0)
        source_factory.assert_called_once_with("private.json", timeout=1.5, duration=42)
        self.assertEqual(runner.call_args.args[0], source)
        self.assertIsNone(runner.call_args.kwargs["store"])
        self.assertEqual(runner.call_args.kwargs["duration"], 42)
        self.assertEqual(runner.call_args.kwargs["interval"], 1.0)
        self.assertEqual(runner.call_args.kwargs["mode"], "common-dme-monitor")
        self.assertEqual(runner.call_args.kwargs["title"], "Common DME monitor")
        self.assertEqual(runner.call_args.kwargs["host"], "127.0.0.1")

    def test_common_dme_monitor_cli_enforces_duration_timeout_and_loopback(self):
        invalid = (("--duration", "0"), ("--duration", "301"),
                   ("--timeout", "0"), ("--timeout", "5.1"),
                   ("--ui-host", "0.0.0.0"))
        for option, value in invalid:
            with self.subTest(option=option, value=value), \
                    patch.object(cli, "CommonDmeMonitorSource") as source_factory:
                with self.assertRaises(SystemExit):
                    cli.main(["monitor-common-dme", "--capture", "private.json", option, value])
                source_factory.assert_not_called()

    def test_monitor_database_open_failures_are_redacted_and_prevent_source_creation(self):
        private_path = "C:/private/vehicle capture.sqlite"
        private_error = f"cannot open {private_path}: private driver detail"
        cases = (
            ("monitor-temperatures", "temperature monitor", "TemperatureMonitorSource"),
            ("monitor-common-dme", "common DME monitor", "CommonDmeMonitorSource"),
        )
        for command, check, source_name in cases:
            with self.subTest(command=command), \
                    patch.object(cli, "TelemetryStore", side_effect=OSError(private_error)), \
                    patch.object(cli, source_name) as source_factory:
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    status = cli.main([command, "--capture", "private-capture.json",
                                       "--db", private_path])
                self.assertEqual(status, 1)
                self.assertEqual(json.loads(output.getvalue()), {
                    "result": "failed", "check": check, "reason": "recording-unavailable"})
                self.assertNotIn(private_path, output.getvalue())
                self.assertNotIn("private driver detail", output.getvalue())
                source_factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
