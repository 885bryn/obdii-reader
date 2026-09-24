"""Live HSFZ source that halts the complete poll cycle on its first error."""
import threading
import time
from .hsfz import HsfzClient
from .models import Sample, decode_integer, utc_now
from .uds import mode01_value, parse_response


class HsfzSignalSource:
    def __init__(self, host: str, profile: dict, signals: list, *, timeout=2.0, client_factory=HsfzClient, audit=None):
        self.host, self.profile = host, profile
        self.signals = list(signals)
        self.poll_signals = [s for s in signals if s.enabled and s.kind == "measured"]
        self.timeout, self.client_factory = timeout, client_factory
        self._stop = threading.Event()
        self.clients = {address: client_factory(host, profile["tester_address"], address, timeout=timeout, audit=audit)
                        for address in dict.fromkeys(s.target_address for s in self.poll_signals)}
        self.connected = False
        self.last_error = None
        self.halted = False
        self.halt_reason = None

    def close(self):
        self._stop.set()
        for client in self.clients.values(): client.close()
        self.connected = False

    def _halt(self, reason):
        self.halted = True
        self.halt_reason = str(reason)
        self.last_error = self.halt_reason
        self.close()

    @staticmethod
    def _sample(sig, value, quality, error=None, unit=None):
        # Timestamp after blocking vehicle I/O and signal decoding.
        return Sample(sig.id, value, sig.unit if unit is None else unit, "hsfz", sig.kind,
                      quality, utc_now(), time.monotonic_ns(), error)

    def read(self):
        completed = {}
        if self.halted:
            for sig in self.signals:
                if sig.enabled:
                    completed[sig.id] = self._sample(sig, None, "halted", self.halt_reason)
                else:
                    completed[sig.id] = self._sample(sig, None, "unavailable", "Signal is disabled in profile")
            return [completed[s.id] for s in self.signals]

        for sig in self.poll_signals:
            if self._stop.is_set(): break
            try:
                req = bytes.fromhex(sig.service + sig.request)
                response = self.clients[sig.target_address].request(req)
                parsed = parse_response(response, req[0])
                if not parsed.positive:
                    raise ValueError(f"ECU negative response NRC 0x{parsed.nrc:02X}")
                if req[0] == 0x01:
                    value, unit = mode01_value(req[1], response[2:])
                else:
                    value, unit = decode_integer(response, sig), sig.unit
                completed[sig.id] = self._sample(sig, value, "good", unit=unit)
            except Exception as exc:
                completed[sig.id] = self._sample(sig, None, "error", str(exc))
                self._halt(exc)
                break

        self.connected = not self.halted and any(getattr(client, "connected", False) for client in self.clients.values())
        self.last_error = self.halt_reason
        for sig in self.signals:
            if sig.id in completed: continue
            if sig.kind == "unavailable" or not sig.enabled:
                completed[sig.id] = self._sample(sig, None, "unavailable", "Signal is unavailable or disabled")
            else:
                completed[sig.id] = self._sample(sig, None, "halted", self.halt_reason or "Not polled after shutdown")
        return [completed[s.id] for s in self.signals]
