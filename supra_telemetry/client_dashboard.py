"""Bounded loopback dashboard for a simulated demo or capture-bound live reads."""
import math
import socket
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json

from .common_dme_values import parse_value_response
from .dme_check import DME_TARGET_ADDRESS
from .emissions_dtcs import (FAILURE_REASONS as DTC_FAILURE_REASONS,
                             REJECTION_SUBTYPES, EmissionsDtcError,
                             read_emissions_dtcs)
from .gateway_check import TESTER_ADDRESS, load_gateway_capture
from .hsfz import HsfzClient
from .models import Sample, SignalDefinition, utc_now
from .temperature_values import parse_temperature_response

TICK_SECONDS = 0.1
# Two-second, 20-slot cycle split into identical one-second occupancy windows:
# five requests per second, with RPM every 0.5s, throttle every 1s, and each
# remaining signal every 2s. Empty slots keep requests serialized.
SCHEDULE = (0x0C, None, 0x11, 0x0D, None, 0x0C, None, 0x0F, None, None,
            0x0C, None, 0x11, 0x05, None, 0x0C, None, 0x5C, None, None)
SIGNALS = (
    SignalDefinition("engine_rpm", "Engine RPM", "rpm", provenance="SAE Mode 01 PID 0C", confidence="one-shot-verified", verification="one-shot-verified", enabled=True),
    SignalDefinition("vehicle_speed", "Vehicle speed", "km/h", provenance="SAE Mode 01 PID 0D", confidence="one-shot-verified", verification="one-shot-verified", enabled=True),
    SignalDefinition("intake_air_temperature", "Intake air temperature", "°C", provenance="SAE Mode 01 PID 0F", confidence="one-shot-verified", verification="one-shot-verified", enabled=True),
    SignalDefinition("throttle_position", "Throttle position", "%", provenance="SAE Mode 01 PID 11", confidence="one-shot-verified", verification="one-shot-verified", enabled=True),
    SignalDefinition("coolant_temp", "Coolant temperature", "°C", provenance="SAE Mode 01 PID 05", confidence="verified", verification="verified", enabled=True),
    SignalDefinition("engine_oil_temp", "Engine oil temperature", "°C", provenance="SAE Mode 01 PID 5C", confidence="verified", verification="verified", enabled=True),
)
BY_PID = {0x0C: SIGNALS[0], 0x0D: SIGNALS[1], 0x0F: SIGNALS[2], 0x11: SIGNALS[3], 0x05: SIGNALS[4], 0x5C: SIGNALS[5]}
BOUNDS = {0x0C: (300, 2500), 0x0D: (0, 0), 0x0F: (-40, 120), 0x11: (0, 100), 0x05: (-40, 120), 0x5C: (-40, 210)}
LIVE_FAILURES = frozenset({"timeout", "stationary-gate", "uds-rejected", "response-invalid", "connection-or-transport"})


class DashboardLiveSource:
    """Paced request cadence, source-bound route, finite budget, halt on error."""
    def __init__(self, capture, *, timeout=2.0, duration=300, client_factory=HsfzClient,
                 connector_factory=socket.create_connection, monotonic=time.monotonic, wait=None):
        if not 0.1 <= float(timeout) <= 5.0:
            raise ValueError("timeout must be between 0.1 and 5 seconds")
        if not isinstance(duration, int) or isinstance(duration, bool) or not 1 <= duration <= 300:
            raise ValueError("duration must be between 1 and 300 seconds")
        peer, interface, _target, _vin = load_gateway_capture(capture)
        def bound_connector(address, connect_timeout):
            return connector_factory(address, connect_timeout, source_address=(interface, 0))
        self.client = client_factory(peer, TESTER_ADDRESS, DME_TARGET_ADDRESS, port=6801,
                                     timeout=float(timeout), fail_on_pending=True,
                                     sock_factory=bound_connector)
        self.signals = list(SIGNALS)
        self.timeout, self.duration = float(timeout), duration
        self._max_attempts = 5 * duration
        self._monotonic, self._wait = monotonic, wait or time.sleep
        self._custom_wait = wait is not None
        self._stop = threading.Event()
        self._deadline = monotonic() + duration
        self._started = 0
        self._tick = 0
        self._next_slot_at = self._deadline - duration
        self._last_started = None
        self._request_starts = deque()
        self._gate = threading.Lock()
        self._closed = False
        self.halted = False
        self.halt_reason = None
        self.connected = False

    def close(self):
        self._stop.set()
        with self._gate:
            if not self._closed:
                self.client.close()
                self._closed = True
        self.connected = False

    def stop(self):
        self.close()

    def read(self):
        if self.halted:
            return []
        if self._started >= self._max_attempts or self._monotonic() >= self._deadline:
            return []
        while True:
            now = self._monotonic()
            if now >= self._deadline or self._stop.is_set():
                return []
            # Drop scheduler slots missed while the prior ECU request was in
            # flight; never replay overdue requests in a catch-up burst.
            while self._next_slot_at < now - 1e-9:
                self._tick += 1
                self._next_slot_at += TICK_SECONDS
            slot_at = max(self._next_slot_at,
                          self._last_started + TICK_SECONDS if self._last_started is not None
                          else self._next_slot_at)
            delay = slot_at - now
            if delay > 0:
                self._wait(delay)
                if self._stop.is_set():
                    return []
            pid = SCHEDULE[self._tick % len(SCHEDULE)]
            self._tick += 1
            self._next_slot_at += TICK_SECONDS
            if pid is not None:
                break
        try:
            with self._gate:
                while True:
                    if self._stop.is_set() or self._started >= self._max_attempts:
                        return []
                    now = self._monotonic()
                    if now >= self._deadline:
                        return []
                    while self._request_starts and now - self._request_starts[0] >= 1.0:
                        self._request_starts.popleft()
                    if len(self._request_starts) < 5:
                        break
                    wait_for = min(self._request_starts[0] + 1.0 - now,
                                   self._deadline - now)
                    if wait_for <= 0:
                        return []
                    if self._custom_wait:
                        self._wait(wait_for)
                    elif self._stop.wait(wait_for):
                        return []
                if self._stop.is_set() or self._started >= self._max_attempts:
                    return []
                self._last_started = self._monotonic()
                if self._last_started >= self._deadline:
                    return []
                self._request_starts.append(self._last_started)
                self._started += 1
                response = self.client.request(bytes((0x01, pid)))
            if isinstance(response, bytes) and response[:1] == b"\x7f":
                raise ConnectionError("negative response")
            value = (parse_temperature_response(response, pid) if pid in (0x05, 0x5C)
                     else parse_value_response(response, pid)[0])
            low, high = BOUNDS[pid]
            if not low <= value <= high:
                raise ValueError("stationary-gate")
            self.connected = bool(getattr(self.client, "connected", False))
            signal = BY_PID[pid]
            return [Sample(signal.id, value, signal.unit, "hsfz", "measured", "good",
                           utc_now(), time.monotonic_ns())]
        except Exception as exc:
            self.halted = True
            message = str(exc)
            self.halt_reason = ("stationary-gate" if message == "stationary-gate" else
                                "timeout" if isinstance(exc, TimeoutError) else
                                "uds-rejected" if isinstance(exc, ConnectionError) else
                                "response-invalid" if isinstance(exc, ValueError) else
                                "connection-or-transport")
            try:
                self.close()
            except Exception:
                pass
            self.connected = False
            signal = BY_PID[pid]
            return [Sample(signal.id, None, signal.unit, "hsfz", "measured", "error",
                           utc_now(), time.monotonic_ns(), self.halt_reason)]


class DashboardSimSource:
    """Predictable client-demo values with no connection or storage side effects."""
    def __init__(self, *, monotonic=time.monotonic):
        self._clock, self._start = monotonic, monotonic()
        self.signals = list(SIGNALS)
        self.halted = False
        self._tick = 0

    def read(self):
        t = self._clock() - self._start
        values = {
            "engine_rpm": 850 + int(140 * (1 + math.sin(t * 0.65))),
            "vehicle_speed": 0,
            "intake_air_temperature": round(27 + 2 * math.sin(t * 0.15), 1),
            "throttle_position": round(13 + 1.2 * math.sin(t * 0.4), 1),
            "coolant_temp": 91,
            "engine_oil_temp": 96,
        }
        now = time.monotonic_ns()
        selected = self.signals if self._tick == 0 else [self.signals[0]] if self._tick % 5 else self.signals[1:]
        self._tick += 1
        return [Sample(s.id, values[s.id], s.unit, "simulated", "measured", "simulated",
                       utc_now(), now) for s in selected]


SIMULATED_DTCS = {"stored": ["P0420"], "pending": [], "permanent": ["P0420"]}


def safe_dtc_snapshot(result=None, error=None):
    """Normalize only decoder-vetted DTC values and allowlisted failure labels."""
    if error is not None:
        completed = getattr(error, "completed_reads", {}) or {}
        reason = getattr(error, "reason", "unexpected-error")
        if reason not in DTC_FAILURE_REASONS:
            reason = "unexpected-error"
        subtype = getattr(error, "rejection_subtype", None)
        if subtype not in REJECTION_SUBTYPES:
            subtype = None
        return {"stored": completed.get("stored"), "pending": completed.get("pending"),
                "permanent": completed.get("permanent"),
                "permanent_reason": (subtype or reason)
                if getattr(error, "failed_read", None) == "permanent" else None,
                "status": "partial" if completed else "unavailable"}
    return {"stored": result["stored_dtcs"], "pending": result["pending_dtcs"],
            "permanent": result["permanent_dtcs"], "permanent_reason": None, "status": "complete"}


HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GR Supra | Telemetry</title><style>
:root{color-scheme:dark;--bg:#08111c;--panel:#111e2b;--line:#26384a;--muted:#91a5b8;--cyan:#52d6e8;--amber:#ffc36a;--red:#ff7d7d}*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 50% -20%,#1b3850,var(--bg) 55%);color:#f1f6fa;font:16px Inter,system-ui,Segoe UI,sans-serif}header{display:flex;justify-content:space-between;align-items:center;padding:22px clamp(18px,5vw,70px);border-bottom:1px solid #ffffff12}.brand{font-size:18px;font-weight:750;letter-spacing:.04em}.sub{color:var(--muted);font-size:12px;margin-top:4px}.badges{display:flex;gap:10px;align-items:center}.badge{border:1px solid var(--line);border-radius:999px;padding:8px 12px;font-size:11px;font-weight:800;letter-spacing:.1em}.live{color:var(--cyan);border-color:#286778}.sim{color:var(--amber);border-color:#72582f}.wrap{max-width:1240px;margin:30px auto;padding:0 20px}.top{display:grid;grid-template-columns:minmax(280px,.95fr) 1.4fr;gap:18px}.panel,.metric{background:linear-gradient(145deg,#142434,#0f1b27);border:1px solid var(--line);border-radius:18px}.hero{padding:24px;display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:300px}.eyebrow{color:var(--muted);font-size:11px;font-weight:800;letter-spacing:.14em;text-transform:uppercase}.gauge{width:min(300px,90%);aspect-ratio:1.8;overflow:hidden;position:relative;margin:12px 0}.arc{position:absolute;width:100%;height:200%;border:16px solid #24394b;border-bottom-color:transparent;border-radius:50%;top:0}.arc:after{content:"";position:absolute;inset:-16px;border:16px solid transparent;border-top-color:var(--cyan);border-radius:50%;transform:rotate(var(--angle,-135deg));transition:transform .5s}.rpm{font-size:clamp(48px,7vw,78px);font-weight:800;letter-spacing:-.06em;line-height:1}.unit{font-size:12px;color:var(--muted);letter-spacing:.12em}.herofoot{display:flex;justify-content:space-between;width:90%;margin-top:20px;color:var(--muted);font-size:12px}.metrics{display:grid;grid-template-columns:repeat(2,minmax(145px,1fr));gap:14px}.metric{padding:19px;min-height:130px}.metric .value{font-size:32px;font-weight:750;margin:17px 0 5px;letter-spacing:-.04em}.metric .unit{letter-spacing:0}.fresh{color:var(--muted);font-size:11px}.section{margin-top:20px;padding:21px}.sectionhead{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}.section h2{font-size:14px;letter-spacing:.1em;text-transform:uppercase;margin:0}.codes{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.codebox{padding:15px;background:#0b1621;border:1px solid var(--line);border-radius:12px}.codebox h3{font-size:12px;color:var(--muted);margin:0 0 12px;text-transform:uppercase;letter-spacing:.1em}.code{font:700 17px ui-monospace,monospace;margin:5px 4px 0 0;display:inline-block}.empty{color:#72869a;font-size:13px}.foot{color:#71859a;text-align:center;font-size:11px;margin:24px}.error{color:var(--red)}@media(max-width:760px){.top{grid-template-columns:1fr}.metrics{grid-template-columns:repeat(2,1fr)}.codes{grid-template-columns:1fr}.hero{min-height:260px}header{align-items:flex-start;gap:12px;flex-direction:column}}
</style></head><body><header><div><div class="brand">GR SUPRA <span style="color:#607d94">/</span> TELEMETRY</div><div class="sub">Read only vehicle overview</div></div><div class="badges"><span class="badge" id="mode">CONNECTING</span><span class="badge" id="status">STARTING</span></div></header><main class="wrap"><div class="top"><section class="panel hero"><div class="eyebrow">Engine speed</div><div class="gauge"><div class="arc" id="arc"></div></div><div class="rpm" id="rpm">—</div><div class="unit">REVOLUTIONS PER MINUTE</div><div class="herofoot"><span id="rpmfresh">Waiting for RPM</span><span>0—7,000 RPM</span></div></section><section class="metrics" id="metrics"></section></div><section class="panel section"><div class="sectionhead"><h2>Emissions fault snapshot</h2><span class="sub" id="dtcstatus"></span></div><div class="codes" id="codes"></div></section><div class="foot" id="notice">Only verified Mode 01 values. No fault clearing or vehicle controls.</div></main><script>
const labels={vehicle_speed:['Vehicle speed','km/h'],coolant_temp:['Coolant temperature','°C'],engine_oil_temp:['Engine oil temperature','°C'],intake_air_temperature:['Intake air temperature','°C'],throttle_position:['Throttle position','%']};function age(s){return s?`${s.age_ms} ms old${s.observed_hz?` · ${s.observed_hz.toFixed(2)} Hz`:''}`:'Waiting for sample'}async function update(){try{const d=await(await fetch('/api/state')).json();const mode=document.querySelector('#mode');mode.textContent=d.mode==='simulated'?'SIMULATED':'LIVE';mode.className='badge '+(d.mode==='simulated'?'sim':'live');document.querySelector('#status').textContent=d.halted?'HALTED':d.connection.toUpperCase();document.querySelector('#status').className='badge '+(d.halted?'error':'');const by=Object.fromEntries(d.samples.map(s=>[s.signal_id,s]));const rpm=by.engine_rpm;document.querySelector('#rpm').textContent=rpm?.value??'—';document.querySelector('#arc').style.setProperty('--angle',`${-135+Math.max(0,Math.min(1,(rpm?.value||0)/7000))*270}deg`);document.querySelector('#rpmfresh').textContent=age(rpm);const root=document.querySelector('#metrics');root.replaceChildren();for(const [id,[name,unit]] of Object.entries(labels)){const s=by[id],card=document.createElement('article');card.className='metric';const eyebrow=document.createElement('div');eyebrow.className='eyebrow';eyebrow.textContent=name;const value=document.createElement('div');value.className='value';value.textContent=s?.value??'—';const units=document.createElement('div');units.className='unit';units.textContent=unit;const fresh=document.createElement('div');fresh.className='fresh';fresh.textContent=age(s);card.append(eyebrow,value,units,fresh);root.append(card)}const groups=document.querySelector('#codes');groups.replaceChildren();for(const [key,title] of [['stored','Stored'],['pending','Pending'],['permanent','Permanent']]){const box=document.createElement('div');box.className='codebox';const h=document.createElement('h3');h.textContent=title;box.append(h);const codes=d.dtcs[key];if(codes===null){const n=document.createElement('span');n.className='empty';n.textContent=key==='permanent'&&d.dtcs.permanent_reason?`Unavailable · ${d.dtcs.permanent_reason}`:'Unavailable';box.append(n)}else if(!codes.length){const n=document.createElement('span');n.className='empty';n.textContent='No codes reported';box.append(n)}else for(const c of codes){const n=document.createElement('span');n.className='code';n.textContent=c;box.append(n)}groups.append(box)}document.querySelector('#dtcstatus').textContent=d.dtcs.status.toUpperCase();document.querySelector('#notice').textContent=d.mode==='simulated'?'SIMULATED DATA · Values and sample fault codes are illustrative. No vehicle connection is opened.':'LIVE DATA · Target intervals: RPM 0.5s, throttle 1s, other sensors 2s. Slow ECU responses may reduce the actual update rate.';if(d.halted)document.querySelector('#notice').textContent+=` Acquisition stopped: ${d.acquisition_error||'unknown error'}`}catch(e){document.querySelector('#status').textContent='API UNAVAILABLE'}}update();setInterval(update,500)
</script></body></html>'''


def make_dashboard_handler(engine, source, mode, dtcs):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                data, content = HTML.encode(), "text/html; charset=utf-8"
            elif self.path == "/api/state":
                data = json.dumps(dashboard_state(engine, source, mode, dtcs)).encode()
                content = "application/json"
            else:
                self.send_error(404); return
            self.send_response(200); self.send_header("Content-Type", content); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        def log_message(self, *_): pass
    return Handler


def serve_client_dashboard(source, *, mode, dtcs, host="127.0.0.1", port=8765,
                           duration=300, worker_factory=threading.Thread, server=None):
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("dashboard must bind to loopback")
    if mode not in ("simulated", "live"):
        raise ValueError("mode must be simulated or live")
    if not 1 <= duration <= 300:
        raise ValueError("duration must be between 1 and 300 seconds")
    from .engine import AcquisitionEngine
    server = server
    timer = worker = None
    engine = None
    stop = threading.Event()
    try:
        engine = AcquisitionEngine(source=source, interval=0.1 if mode == "live" else 0.2)
        Handler = make_dashboard_handler(engine, source, mode, dtcs)
        if server is None:
            server = ThreadingHTTPServer((host, port), Handler)
        else:
            server.RequestHandlerClass = Handler
        worker = worker_factory(target=engine.run, args=(stop,), daemon=True)
        worker.start()
        print(f"{mode.title()} client dashboard: http://{host}:{server.server_port}/", flush=True)
        timer = threading.Timer(duration, server.shutdown); timer.daemon = True; timer.start()
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        if timer is not None: timer.cancel()
        stop.set()
        if hasattr(source, "close"):
            try: source.close()
            except Exception: pass
        if worker is not None and getattr(worker, "ident", None) is not None:
            worker.join(timeout=max(2.0, getattr(source, "timeout", 0) + 1))
        if server is not None: server.server_close()
    return 1 if engine is not None and engine.halted else 0


def reserve_dashboard_server(host="127.0.0.1", port=8765):
    """Bind loopback before any live vehicle I/O; expose only a fixed error."""
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("dashboard-bind-failed")
    try:
        class ReservedServer(ThreadingHTTPServer):
            allow_reuse_address = False
        return ReservedServer((host, port), BaseHTTPRequestHandler)
    except Exception:
        raise RuntimeError("dashboard-bind-failed") from None


def wait_after_dtc_snapshot(wait=time.sleep):
    """Keep a conservative quiet interval between the DTC and sensor sources."""
    wait(1.0)


def run_live_dtc_snapshot(capture, timeout=2.0, *, monotonic=time.monotonic, wait=time.sleep,
                          client_factory=None):
    """Exactly one existing three-service DTC snapshot, preserving safe partials."""
    try:
        kwargs = {"monotonic": monotonic, "wait": wait, "min_request_interval": 1.0}
        if client_factory is not None:
            kwargs["client_factory"] = client_factory
        return safe_dtc_snapshot(read_emissions_dtcs(capture, timeout, **kwargs))
    except EmissionsDtcError as exc:
        return safe_dtc_snapshot(error=exc)
    except Exception:
        return {"stored": None, "pending": None, "permanent": None,
                "permanent_reason": "unexpected-error", "status": "unavailable"}


def dashboard_state(engine, source, mode, dtcs):
    """Build the deliberately small, privacy-safe API response shape."""
    now = time.monotonic_ns()
    for _ in range(3):
        try:
            latest = tuple(engine.latest.values())
            break
        except RuntimeError:
            continue
    else:
        latest = ()
    samples = [{**vars(sample), "age_ms": max(0, (now - sample.monotonic_ns) // 1_000_000)}
               for sample in latest]
    reason = getattr(source, "halt_reason", None)
    if reason not in LIVE_FAILURES:
        reason = "unexpected-error" if engine.halted or source.halted else None
    return {"mode": mode,
            "connection": "running" if mode == "simulated" else "connected" if source.connected else "waiting",
            "halted": engine.halted or source.halted,
            "acquisition_error": reason,
            "samples": samples,
            "dtcs": dtcs}
