"""Run the bounded read-only discovery phases in one offline-prepared suite."""

import math
import time

from .common_dme_values import read_common_dme_values as _read_common_dme_values
from .emissions_dtcs import read_emissions_dtcs as _read_emissions_dtcs
from .mode01_inventory import inventory_mode01 as _inventory_mode01
from .vehicle_info import verify_vehicle_info as _verify_vehicle_info

PHASES = (
    ("inventory_mode01", _inventory_mode01, 8),
    ("read_common_dme_values", _read_common_dme_values, 4),
    ("read_emissions_dtcs", _read_emissions_dtcs, 3),
    ("verify_vehicle_info", _verify_vehicle_info, 5),
)
FAILURE_REASONS = frozenset({
    "capture-invalid", "timeout", "connection-or-transport",
    "uds-rejected", "response-invalid", "support-not-advertised",
    "plausibility-failed", "unexpected-error",
})
CHECK_NAME = "HSFZ DME bounded read-only discovery suite"
REQUIRED_COMMON_PIDS = frozenset(("0x0C", "0x0D", "0x0F", "0x11"))


class SuiteError(Exception):
    """Safe suite failure containing only a fixed phase, reason and counts."""

    def __init__(self, phase, reason, total_requests, completed_phases):
        self.phase = phase
        self.reason = (reason if isinstance(reason, str) and reason in FAILURE_REASONS
                       else "unexpected-error")
        self.total_requests = total_requests
        self.completed_phases = tuple(completed_phases)
        super().__init__(
            f"read-only suite failed during {self.phase}: {self.reason}"
        )


def _valid_count(value, ceiling):
    return type(value) is int and 0 <= value <= ceiling


def _common_values_plausible(result):
    """Apply the reviewed stationary, engine-idling gate before later phases."""
    try:
        values = result["values"]
        rpm = values["engine_rpm"]["value"]
        speed = values["vehicle_speed"]["value"]
        intake = values["intake_air_temperature"]["value"]
        throttle = values["throttle_position"]["value"]
        measured = (rpm, speed, intake, throttle)
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) for value in measured):
            return False
        return (300.0 <= rpm <= 2500.0 and speed == 0.0
                and -40.0 <= intake <= 120.0 and 0.0 <= throttle <= 100.0)
    except (KeyError, TypeError):
        return False


def run_read_only_suite(path, timeout=2.0, *, inventory_mode01=_inventory_mode01,
                        read_common_dme_values=_read_common_dme_values,
                        read_emissions_dtcs=_read_emissions_dtcs,
                        verify_vehicle_info=_verify_vehicle_info,
                        wait=time.sleep):
    """Run all four phases in order, stopping safely at the first failure.

    The injected phase callables each receive ``path``. The injected wait
    receives exactly 2.0 seconds after each successful phase except the last.
    """
    functions = (inventory_mode01, read_common_dme_values,
                 read_emissions_dtcs, verify_vehicle_info)
    completed = []
    results = {}
    total_requests = 0

    for index, ((phase, _default, ceiling), function) in enumerate(zip(PHASES, functions)):
        try:
            result = function(path, timeout)
        except Exception as exc:
            current = getattr(exc, "requests_sent", 0)
            reason = getattr(exc, "reason", "unexpected-error")
            if not isinstance(reason, str) or reason not in FAILURE_REASONS:
                reason, current = "unexpected-error", 0
            elif not _valid_count(current, ceiling):
                reason, current = "response-invalid", 0
            raise SuiteError(phase, reason, total_requests + current, completed) from None

        if (not isinstance(result, dict) or result.get("result") != "verified"
                or not _valid_count(result.get("requests_sent"), ceiling)):
            raise SuiteError(phase, "response-invalid", total_requests, completed)

        count = result["requests_sent"]
        total_requests += count
        results[phase] = result
        completed.append(phase)
        if phase == "inventory_mode01":
            supported = result.get("supported_pids")
            if (not isinstance(supported, list)
                    or not REQUIRED_COMMON_PIDS.issubset(supported)):
                raise SuiteError(phase, "support-not-advertised",
                                 total_requests, completed)
        if phase == "read_common_dme_values" and not _common_values_plausible(result):
            raise SuiteError(phase, "plausibility-failed", total_requests, completed)
        if index < len(PHASES) - 1:
            try:
                wait(2.0)
            except Exception:
                raise SuiteError(phase, "unexpected-error", total_requests, completed) from None

    return {
        "result": "verified", "check": CHECK_NAME,
        "completed_phases": completed,
        "phase_results": results,
        "total_requests": total_requests,
    }
