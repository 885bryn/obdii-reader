import unittest

from supra_telemetry.read_only_suite import SuiteError, run_read_only_suite


def result(requests_sent, **extra):
    return {"result": "verified", "requests_sent": requests_sent, **extra}


class ReadOnlySuiteTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.waits = []

    def phase(self, name, count):
        def run(path, timeout):
            self.calls.append((name, path, timeout))
            extra = {"phase": name}
            if name == "inventory":
                extra["supported_pids"] = ["0x0C", "0x0D", "0x0F", "0x11"]
                extra["highest_bitmap_base"] = "0x00"
            if name == "values":
                extra["values"] = {
                    "engine_rpm": {"value": 750.0, "unit": "rpm"},
                    "vehicle_speed": {"value": 0.0, "unit": "km/h"},
                    "intake_air_temperature": {"value": 25.0, "unit": "°C"},
                    "throttle_position": {"value": 12.0, "unit": "%"},
                }
            return result(count, **extra)
        return run

    def dependencies(self, counts=(8, 4, 3, 5)):
        names = ("inventory", "values", "dtcs", "info")
        return [self.phase(name, count) for name, count in zip(names, counts)]

    def run_suite(self, phases):
        return run_read_only_suite(
            "capture.json", inventory_mode01=phases[0],
            read_common_dme_values=phases[1], read_emissions_dtcs=phases[2],
            verify_vehicle_info=phases[3],
            wait=lambda seconds: self.waits.append(seconds),
        )

    def test_success_order_waits_and_twenty_request_ceiling(self):
        output = self.run_suite(self.dependencies())
        expected = [
            "inventory_mode01", "read_common_dme_values",
            "read_emissions_dtcs", "verify_vehicle_info",
        ]
        self.assertEqual([name for name, _, _ in self.calls],
                         ["inventory", "values", "dtcs", "info"])
        self.assertTrue(all(timeout == 2.0 for _, _, timeout in self.calls))
        self.assertEqual(self.waits, [2.0, 2.0, 2.0])
        self.assertEqual(output["completed_phases"], expected)
        self.assertEqual(list(output["phase_results"]), expected)
        self.assertEqual(output["total_requests"], 20)

    def test_first_phase_failure_stops_and_exposes_only_safe_fields(self):
        secret = "VIN-SECRET-169.254.1.2"
        class Failure(Exception):
            reason = "timeout"
            requests_sent = 1
        def fail(_path, timeout):
            self.calls.append(("inventory", _path, timeout))
            raise Failure(secret)
        phases = [fail, *self.dependencies()[1:]]
        with self.assertRaises(SuiteError) as caught:
            self.run_suite(phases)
        error = caught.exception
        self.assertEqual((error.phase, error.reason, error.total_requests),
                         ("inventory_mode01", "timeout", 1))
        self.assertEqual(error.completed_phases, ())
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.waits, [])
        self.assertNotIn(secret, str(error))

    def test_middle_phase_failure_includes_prior_and_current_counts_then_stops(self):
        phases = self.dependencies((2, 4, 3, 5))
        class Failure(Exception):
            reason = "uds-rejected"
            requests_sent = 2
        def fail(_path, timeout):
            self.calls.append(("values", _path, timeout))
            raise Failure("private response")
        phases[1] = fail
        with self.assertRaises(SuiteError) as caught:
            self.run_suite(phases)
        error = caught.exception
        self.assertEqual(error.phase, "read_common_dme_values")
        self.assertEqual(error.reason, "uds-rejected")
        self.assertEqual(error.total_requests, 4)
        self.assertEqual(error.completed_phases, ("inventory_mode01",))
        self.assertEqual(error.completed_summaries, {
            "inventory_mode01": {"requests_sent": 2,
                                 "supported_pids": ["0x0C", "0x0D", "0x0F", "0x11"],
                                 "highest_bitmap_base": "0x00"},
        })
        self.assertEqual([name for name, _, _ in self.calls], ["inventory", "values"])
        self.assertEqual(self.waits, [2.0])
        self.assertNotIn("private response", str(error))

    def test_completed_summaries_are_rebuilt_from_allowlisted_fields(self):
        phases = self.dependencies((2, 4, 3, 5))
        phases[2] = lambda *_args: (_ for _ in ()).throw(type("Failure", (Exception,), {
            "reason": "response-invalid", "requests_sent": 1,
            "failed_read": "pending", "payload_issue": "odd-length",
            "rejection_subtype": "VIN-SECRET",
            "completed_reads": {"stored": ["P0123"]},
        })("VIN-SECRET"))
        original_inventory = phases[0]
        original_values = phases[1]
        def malicious_inventory(path, timeout):
            value = original_inventory(path, timeout)
            value.update(peer="169.254.1.2", raw="PRIVATE", supported_pids_extra="secret")
            return value
        def malicious_values(path, timeout):
            value = original_values(path, timeout)
            value["values"]["private"] = {"value": "VIN-SECRET", "unit": "secret"}
            return value
        phases[0], phases[1] = malicious_inventory, malicious_values
        with self.assertRaises(SuiteError) as caught:
            self.run_suite(phases)
        error = caught.exception
        self.assertEqual(error.failed_read, "pending")
        self.assertEqual(error.payload_issue, "odd-length")
        self.assertIsNone(error.rejection_subtype)
        self.assertEqual(error.dtc_completed_reads, {
            "stored": {"dtcs": ["P0123"], "count": 1}})
        self.assertEqual(error.completed_summaries, {
            "inventory_mode01": {"requests_sent": 2,
                                 "supported_pids": ["0x0C", "0x0D", "0x0F", "0x11"],
                                 "highest_bitmap_base": "0x00"},
        })
        self.assertNotIn("VIN-SECRET", repr(error.completed_summaries))
        self.assertEqual([name for name, _, _ in self.calls], ["inventory", "values"])

    def test_suite_error_rejects_malicious_completed_summary_fields(self):
        error = SuiteError("read_emissions_dtcs", "response-invalid", 9,
                           ("inventory_mode01",), {
                               "inventory_mode01": {"requests_sent": 2,
                                   "supported_pids": ["0x0C"],
                                   "highest_bitmap_base": "0x00",
                                   "peer": "169.254.1.2", "raw": "VIN-SECRET"},
                           }, {"failed_read": "pending", "payload_issue": "raw",
                               "completed_reads": {"stored": ["VIN-SECRET"]}})
        self.assertEqual(error.completed_summaries, {
            "inventory_mode01": {"requests_sent": 2, "supported_pids": ["0x0C"],
                                 "highest_bitmap_base": "0x00"},
        })
        self.assertEqual(error.failed_read, "pending")
        self.assertIsNone(error.payload_issue)

    def test_suite_error_preserves_count_mismatch_category(self):
        error = SuiteError("read_emissions_dtcs", "response-invalid", 9,
                           ("inventory_mode01", "read_common_dme_values"), {},
                           {"failed_read": "stored", "payload_issue": "count-mismatch",
                            "completed_reads": {}})
        self.assertEqual(error.failed_read, "stored")
        self.assertEqual(error.payload_issue, "count-mismatch")
        self.assertEqual(error.dtc_completed_reads, {})

    def test_suite_propagates_only_allowlisted_dtc_rejection_subtype(self):
        phases = self.dependencies((2, 4, 3, 5))
        class Failure(Exception):
            reason = "uds-rejected"
            requests_sent = 1
            failed_read = "stored"
            rejection_subtype = "conditions-not-correct"
        def fail_dtc(path, timeout):
            self.calls.append(("dtcs", path, timeout))
            raise Failure("private bytes")
        phases[2] = fail_dtc
        with self.assertRaises(SuiteError) as caught:
            self.run_suite(phases)
        self.assertEqual(caught.exception.reason, "uds-rejected")
        self.assertEqual(caught.exception.rejection_subtype, "conditions-not-correct")
        self.assertEqual([name for name, _, _ in self.calls], ["inventory", "values", "dtcs"])
        self.assertEqual(self.waits, [2.0, 2.0])

        error = SuiteError("read_emissions_dtcs", "uds-rejected", 9, (), {},
                           {"failed_read": "stored", "rejection_subtype": "VIN-SECRET"})
        self.assertIsNone(error.rejection_subtype)
        error = SuiteError("read_emissions_dtcs", "response-invalid", 9, (), {},
                           {"failed_read": "stored", "rejection_subtype": "other-nrc"})
        self.assertIsNone(error.rejection_subtype)
        self.assertEqual(error.dtc_completed_reads, {})

    def test_vehicle_info_summary_preserves_vin_support_and_match_states(self):
        for info, expected in (
                ({"vin_match_supported": False}, {"vin_match_supported": False}),
                ({"vin_match_supported": True, "vin_match": True},
                 {"vin_match_supported": True, "vin_match": True})):
            with self.subTest(info=info):
                error = SuiteError("verify_vehicle_info", "response-invalid", 5,
                                   ("verify_vehicle_info",), {
                                       "verify_vehicle_info": {"requests_sent": 5, **info,
                                           "raw": "VIN-SECRET"}})
                self.assertEqual(error.completed_summaries["verify_vehicle_info"],
                                 {"requests_sent": 5, **expected})

    def test_invalid_child_request_counts_fail_closed(self):
        for invalid in (True, -1, 9, 1.5, "1", None):
            with self.subTest(invalid=invalid):
                phases = self.dependencies()
                phases[0] = lambda _path, _timeout, value=invalid: result(value)
                self.calls.clear()
                self.waits.clear()
                with self.assertRaises(SuiteError) as caught:
                    self.run_suite(phases)
                self.assertEqual(caught.exception.reason, "response-invalid")
                self.assertEqual(caught.exception.total_requests, 0)
                self.assertEqual(caught.exception.completed_phases, ())
                self.assertEqual(self.calls, [])
                self.assertEqual(self.waits, [])

        phases = self.dependencies()
        phases[0] = lambda _path, _timeout: {"result": "failed", "requests_sent": 1}
        with self.assertRaises(SuiteError) as caught:
            self.run_suite(phases)
        self.assertEqual(caught.exception.reason, "response-invalid")
        self.assertEqual(caught.exception.total_requests, 0)

    def test_unexpected_error_does_not_leak_details_or_assume_requests(self):
        phases = self.dependencies()
        secret = "VIN-SECRET 169.254.1.2"
        phases[0] = lambda _path, _timeout: (_ for _ in ()).throw(RuntimeError(secret))
        with self.assertRaises(SuiteError) as caught:
            self.run_suite(phases)
        self.assertEqual(caught.exception.reason, "unexpected-error")
        self.assertEqual(caught.exception.total_requests, 0)
        self.assertNotIn(secret, str(caught.exception))

    def test_missing_support_stops_before_value_requests(self):
        phases = self.dependencies()
        phases[0] = lambda _path, _timeout: result(
            1, supported_pids=["0x0C", "0x0D", "0x0F"])
        with self.assertRaises(SuiteError) as caught:
            self.run_suite(phases)
        self.assertEqual(caught.exception.reason, "support-not-advertised")
        self.assertEqual(caught.exception.total_requests, 1)
        self.assertEqual(caught.exception.completed_phases, ("inventory_mode01",))
        self.assertEqual(self.calls, [])
        self.assertEqual(self.waits, [])

    def test_nonstationary_or_implausible_values_stop_before_dtc_reads(self):
        for signal, value in (("vehicle_speed", 1.0), ("engine_rpm", 0.0),
                              ("intake_air_temperature", 121.0),
                              ("throttle_position", float("nan"))):
            with self.subTest(signal=signal):
                phases = self.dependencies((1, 4, 3, 5))
                base_values = phases[1]
                def invalid_values(path, timeout, original=base_values,
                                   changed_signal=signal, changed_value=value):
                    output = original(path, timeout)
                    output["values"][changed_signal]["value"] = changed_value
                    return output
                phases[1] = invalid_values
                self.calls.clear()
                self.waits.clear()
                with self.assertRaises(SuiteError) as caught:
                    self.run_suite(phases)
                self.assertEqual(caught.exception.reason, "plausibility-failed")
                self.assertEqual(caught.exception.total_requests, 5)
                self.assertEqual(caught.exception.completed_phases,
                                 ("inventory_mode01", "read_common_dme_values"))
                self.assertEqual([name for name, _, _ in self.calls],
                                 ["inventory", "values"])
                self.assertEqual(self.waits, [2.0])

    def test_keyboard_interrupt_propagates_without_later_phase_calls(self):
        phases = self.dependencies()
        def interrupt(_seconds):
            raise KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            run_read_only_suite(
                "capture.json", inventory_mode01=phases[0],
                read_common_dme_values=phases[1], read_emissions_dtcs=phases[2],
                verify_vehicle_info=phases[3], wait=interrupt,
            )
        self.assertEqual([name for name, _, _ in self.calls], ["inventory"])


if __name__ == "__main__":
    unittest.main()
