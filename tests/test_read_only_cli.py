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
                           ("inventory_mode01", "read_common_dme_values"))
        with patch.object(cli, "run_read_only_suite", side_effect=error):
            status, result = self.invoke("collect-read-only-suite")
        self.assertEqual(status, 1)
        self.assertEqual(result, {
            "result": "failed", "check": cli.READ_ONLY_SUITE_CHECK,
            "failed_phase": "read_emissions_dtcs", "reason": "uds-rejected",
            "completed_phases": ["inventory_mode01", "read_common_dme_values"],
            "total_requests": 9,
        })


if __name__ == "__main__":
    unittest.main()
