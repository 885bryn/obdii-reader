"""Run the bounded read-only discovery phases in one offline-prepared suite."""

import math
import re
import time

from .common_dme_values import read_common_dme_values as _read_common_dme_values
from .emissions_dtcs import (REJECTION_SUBTYPES,
                             read_emissions_dtcs as _read_emissions_dtcs)
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
_DTC_CODE = re.compile(r"[PCBU][0-3][0-9A-F]{3}\Z")
_PID = re.compile(r"0x[0-9A-F]{2}\Z")
_BITMAP_BASES = frozenset(f"0x{base:02X}" for base in range(0, 0x100, 0x20))
_VEHICLE_INFO_FIELDS = (
    "vin_match_supported", "vin_match", "calibration_id_supported", "calibration_id_response_received",
    "calibration_id_payload_length", "calibration_verification_number_supported",
    "calibration_verification_number_response_received",
    "calibration_verification_number_payload_length", "ecu_name_supported",
    "ecu_name_response_received", "ecu_name_payload_length",
)


class SuiteError(Exception):
    """Safe suite failure containing only a fixed phase, reason and counts."""

    def __init__(self, phase, reason, total_requests, completed_phases,
                 completed_summaries=None, dtc_failure=None):
        allowed_phases = tuple(name for name, _, _ in PHASES)
        self.phase = phase if isinstance(phase, str) and phase in allowed_phases else "suite"
        self.reason = (reason if isinstance(reason, str) and reason in FAILURE_REASONS
                       else "unexpected-error")
        self.total_requests = (total_requests if type(total_requests) is int
                               and 0 <= total_requests <= 20 else 0)
        self.completed_phases = tuple(name for name in completed_phases
                                       if isinstance(name, str) and name in allowed_phases)
        raw_summaries = completed_summaries if isinstance(completed_summaries, dict) else {}
        self.completed_summaries = _summaries_for(
            self.completed_phases,
            {phase: {"result": "verified", **summary}
             for phase, summary in raw_summaries.items()
             if isinstance(phase, str) and isinstance(summary, dict)},
        )
        metadata = dtc_failure if isinstance(dtc_failure, dict) else {}
        failed_read = metadata.get("failed_read")
        payload_issue = metadata.get("payload_issue")
        rejection_subtype = metadata.get("rejection_subtype")
        self.failed_read = (failed_read if isinstance(failed_read, str)
                            and failed_read in {"stored", "pending", "permanent"} else None)
        self.payload_issue = (payload_issue if isinstance(payload_issue, str)
                              and payload_issue in {"count-mismatch", "odd-length",
                                                    "invalid-shape"} else None)
        self.rejection_subtype = (rejection_subtype if self.reason == "uds-rejected"
                                  and isinstance(rejection_subtype, str)
                                  and rejection_subtype in REJECTION_SUBTYPES else None)
        self.dtc_completed_reads = _safe_dtc_completed_reads(
            metadata.get("completed_reads"), self.failed_read)
        super().__init__(
            f"read-only suite failed during {self.phase}: {self.reason}"
        )


def _valid_count(value, ceiling):
    return type(value) is int and 0 <= value <= ceiling


def _safe_dtc_completed_reads(completed_reads, failed_read):
    """Rebuild only a contiguous prefix of safe DTC results before a fixed read."""
    labels = ("stored", "pending", "permanent")
    if not isinstance(completed_reads, dict) or not isinstance(failed_read, str):
        return {}
    try:
        failed_index = labels.index(failed_read)
    except ValueError:
        return {}
    if tuple(completed_reads) != labels[:failed_index]:
        return {}
    safe = {}
    for label in labels[:failed_index]:
        codes = completed_reads[label]
        if (not isinstance(codes, list) or len(codes) > 4094
                or any(not isinstance(code, str) or not _DTC_CODE.fullmatch(code)
                       for code in codes)):
            return {}
        safe[label] = {"dtcs": list(codes), "count": len(codes)}
    return safe


def _safe_phase_summary(phase, result):
    """Rebuild a small, allowlisted failure summary from a verified phase result."""
    if not isinstance(result, dict) or result.get("result") != "verified":
        return None
    count = result.get("requests_sent")
    ceiling = dict((name, max_requests) for name, _, max_requests in PHASES).get(phase)
    if ceiling is None or not _valid_count(count, ceiling):
        return None
    summary = {"requests_sent": count}
    if phase == "inventory_mode01":
        pids = result.get("supported_pids")
        highest = result.get("highest_bitmap_base")
        if (not isinstance(pids, list) or any(not isinstance(pid, str) or not _PID.fullmatch(pid)
                                              for pid in pids)
                or not isinstance(highest, str) or highest not in _BITMAP_BASES):
            return None
        summary.update(supported_pids=sorted(set(pids)), highest_bitmap_base=highest)
    elif phase == "read_common_dme_values":
        values = result.get("values")
        expected = {"engine_rpm": "rpm", "vehicle_speed": "km/h",
                    "intake_air_temperature": "°C", "throttle_position": "%"}
        if not isinstance(values, dict) or set(values) != set(expected):
            return None
        safe_values = {}
        for name, unit in expected.items():
            item = values.get(name)
            value = item.get("value") if isinstance(item, dict) else None
            if (not isinstance(item, dict) or item.get("unit") != unit
                    or isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value)):
                return None
            safe_values[name] = {"value": value, "unit": unit}
        summary["values"] = safe_values
    elif phase == "read_emissions_dtcs":
        for label in ("stored", "pending", "permanent"):
            codes = result.get(f"{label}_dtcs")
            count_value = result.get(f"{label}_count")
            if (not isinstance(codes, list) or any(not isinstance(code, str)
                                                    or not _DTC_CODE.fullmatch(code)
                                                    for code in codes)
                    or type(count_value) is not int or count_value != len(codes)):
                return None
            summary[f"{label}_dtcs"] = list(codes)
            summary[f"{label}_count"] = count_value
    elif phase == "verify_vehicle_info":
        for key in _VEHICLE_INFO_FIELDS:
            if key not in result:
                continue
            value = result[key]
            if key.endswith("_payload_length"):
                if type(value) is not int or not 1 <= value <= 256:
                    return None
            elif type(value) is not bool:
                return None
            summary[key] = value
    return summary


def _summaries_for(completed, results):
    summaries = {}
    for phase in completed:
        safe = _safe_phase_summary(phase, results.get(phase))
        if safe is not None:
            summaries[phase] = safe
    return summaries


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
            metadata = ({"failed_read": getattr(exc, "failed_read", None),
                        "payload_issue": getattr(exc, "payload_issue", None),
                        "rejection_subtype": getattr(exc, "rejection_subtype", None),
                        "completed_reads": getattr(exc, "completed_reads", None)}
                       if phase == "read_emissions_dtcs" else None)
            raise SuiteError(phase, reason, total_requests + current, completed,
                             _summaries_for(completed, results), metadata) from None

        if (not isinstance(result, dict) or result.get("result") != "verified"
                or not _valid_count(result.get("requests_sent"), ceiling)):
            raise SuiteError(phase, "response-invalid", total_requests, completed,
                             _summaries_for(completed, results))

        count = result["requests_sent"]
        total_requests += count
        results[phase] = result
        completed.append(phase)
        if phase == "inventory_mode01":
            supported = result.get("supported_pids")
            if (not isinstance(supported, list)
                    or not REQUIRED_COMMON_PIDS.issubset(supported)):
                raise SuiteError(phase, "support-not-advertised",
                                 total_requests, completed,
                                 _summaries_for(completed, results))
        if phase == "read_common_dme_values" and not _common_values_plausible(result):
            raise SuiteError(phase, "plausibility-failed", total_requests, completed,
                             _summaries_for(completed, results))
        if index < len(PHASES) - 1:
            try:
                wait(2.0)
            except Exception:
                raise SuiteError(phase, "unexpected-error", total_requests, completed,
                                 _summaries_for(completed, results)) from None

    return {
        "result": "verified", "check": CHECK_NAME,
        "completed_phases": completed,
        "phase_results": results,
        "total_requests": total_requests,
    }
