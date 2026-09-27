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
        self.assertEqual([name for name, _, _ in self.calls], ["inventory", "values"])
        self.assertEqual(self.waits, [2.0])
        self.assertNotIn("private response", str(error))

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
