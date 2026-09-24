"""Local-only original dashboard and JSON endpoint."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json, time

HTML = r'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Supra Telemetry</title><style>
*{box-sizing:border-box}body{margin:0;background:#0c1118;color:#eef3f8;font:16px system-ui}header{padding:20px 5vw;background:#121b25;display:flex;justify-content:space-between;align-items:center}h1{font-size:1.25rem;margin:0}.state{color:#a9c9d5}.wrap{max-width:1100px;margin:30px auto;padding:0 20px}.legend{color:#b8c3ce;margin-bottom:18px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}.card{background:#151f2a;border:1px solid #2c3948;border-radius:12px;padding:18px}.label{color:#a9b6c4}.value{font-size:2rem;font-weight:650;margin:16px 0}.meta{font-size:.82rem;color:#9aaaba}.pill{font-size:.75rem;color:#cce3ec}
</style></head><body><header><h1>GR Supra · Telemetry</h1><div class="state" id="state">Connecting…</div></header><main class="wrap"><div class="legend" id="legend">Signal types: <b>Measured</b> · <i>Derived</i> · unavailable signals are shown explicitly.</div><section class="grid" id="cards"></section></main><script>
async function update(){try{let d=await(await fetch('/api/state')).json();document.querySelector('#state').textContent=`${d.connection} · ${d.recording} · observed cycle ${d.cycle_observed_hz==null?'—':d.cycle_observed_hz.toFixed(2)+' Hz'}`;document.querySelector('#legend').dataset.mode=d.mode;document.querySelector('#legend').lastChild.textContent=d.halted?' HALTED. Inspect the cause and start a fresh run to resume.':d.mode==='demo'?' Demo values are simulated.':'';if(d.recording_error||d.acquisition_error)document.querySelector('#legend').lastChild.textContent+=` Error: ${d.recording_error||d.acquisition_error}`;let root=document.querySelector('#cards');root.replaceChildren();for(const s of d.samples){let card=document.createElement('article');card.className='card';let label=document.createElement('div');label.className='label';label.textContent=s.signal_id.replaceAll('_',' ');let value=document.createElement('div');value.className='value';value.textContent=`${s.value??'—'} ${s.unit}`;let meta=document.createElement('div');meta.className='meta';meta.textContent=`${s.kind} · ${s.quality} · ${s.age_ms} ms old · rate ${s.observed_hz==null?'—':s.observed_hz.toFixed(2)+' Hz'}`;card.append(label,value,meta);if(s.error){let error=document.createElement('div');error.className='meta';error.textContent=s.error;card.append(error)}root.append(card)}}catch(e){document.querySelector('#state').textContent='API unavailable'}}update();setInterval(update,500)
</script></body></html>'''


def make_handler(engine, recording=False, mode="demo"):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/":
                data, typ = HTML.encode(), "text/html; charset=utf-8"
            elif self.path == "/api/state":
                now = time.monotonic_ns()
                samples = [{**vars(s), "age_ms": max(0, (now - s.monotonic_ns) // 1_000_000)} for s in engine.latest.values()]
                source = getattr(engine, "source", None)
                connection = mode
                if mode == "live":
                    connection = "live / HALTED" if engine.halted or getattr(source, "halted", False) else "live / connected" if getattr(source, "connected", False) else "live / waiting"
                record_state = "error" if engine.recording_error else "halted" if engine.halted else "on" if recording else "off"
                data, typ = json.dumps({"connection": connection, "mode": mode, "recording": record_state,
                                        "halted": engine.halted or getattr(source, "halted", False),
                                        "acquisition_error": engine.last_error, "recording_error": engine.recording_error,
                                        "cycle_observed_hz": engine.observed_cycle_hz,
                                        "samples": samples}).encode(), "application/json"
            else:
                self.send_error(404); return
            self.send_response(200); self.send_header("Content-Type", typ); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
        def log_message(self, *args): pass
    return Handler


def serve(engine, host="127.0.0.1", port=8765, recording=False, mode="demo"):
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise ValueError("dashboard must bind to loopback")
    return ThreadingHTTPServer((host, port), make_handler(engine, recording, mode))
