# Architecture

The package is intentionally flat and importable. `models` contains signal metadata and bounded codecs; `safety` authorizes all future outbound diagnostic payloads; `uds` parses diagnostic responses independently from transport; `hsfz` owns HSFZ Ethernet framing; `doip` handles discovery only; `profiles` loads data-only JSON; `engine` serializes and schedules acquisition; `storage` records sessions, definitions, samples, and raw exchanges; `web` serves a loopback dashboard; `mock` drives the demo; `__main__` provides CLI commands.

The intended flow is profile → policy → transport → UDS correlation/decode → timestamped sample → optional SQLite and local dashboard. HSFZ framing and read requests are implemented, but live mode fails closed unless a profile is explicitly marked verified and provides the tester address, each ECU target address, allowlisted request, and bounded decoder. No Supra addresses or proprietary DIDs are guessed. HSFZ clients are persistent and serialized per ECU target; transfer acknowledgements are skipped, negative response pending uses a bounded overall deadline, alive-check frames are recorded and ignored without invented replies, and all traffic is auditable. The first live transport, protocol, negative-response, or decoding error halts acquisition and closes clients; later enabled signals receive explicit halted-quality samples and are not requested. A fresh run is required after inspecting the cause.

Dedicated discovery commands use the private capture's exact local source and peer plus the already verified DME route. They expose no raw-payload surface. The consolidated read-only suite sequences four independently bounded phases with a total ceiling of 20 requests and a two-second stop window between successful phases. It stops all later phases after the first failure and rebuilds any failure output from strict per-phase allowlists. The live DTC path uses explicit count-prefixed framing, validates the decoded count and trailing zero padding, and does not infer framing from payload parity. Direct negative responses must be exactly three bytes and correlated to the requested service; only fixed rejection categories can cross the public error boundary. Malformed pending replies fail as invalid, while raw replies, numeric response codes, transport details, and exception text remain private. The policy accepts only fixed-shape Mode 01, single-byte Mode 03/07/0A reads, Mode 09, UDS 0x22, and internal 0x3E; state-changing Mode 04, Mode 08, session control, routines, security access, and writes remain rejected.

The client dashboard has separate simulated and live sources behind one
loopback-only presentation. A Vite-built React frontend consumes only the
privacy-safe `/api/state` response and is packaged as local static assets; the
Python server restricts browser assets to its generated asset directory. The
presentation uses source-owned Farstar registry components, game-hud styles,
and Motion transitions while keeping coolant and oil temperature visually
dominant over RPM. Simulated mode has no transport/client surface. Live
startup first reserves the loopback listener, before any vehicle I/O, then runs
the existing three-read emissions-DTC snapshot once with at least one second
between request starts. It waits another full second before constructing
the sensor source only after either a complete snapshot or the exact previously
observed partial case in which stored and pending results are safe and permanent
Mode 0A is `service-not-supported`. Any other DTC failure prevents monitoring.
The live source uses a fixed 20-slot, two-second scheduler. Ten slots serialize
RPM four times, throttle twice, and speed, intake temperature, coolant
temperature, and oil temperature once each; the other slots are idle. The 100 ms
slot clock targets RPM every 0.5 seconds, throttle every second, and the other
four values every two seconds without concurrent requests. The source remains
limited by the selected 1–300 second wall duration, a rolling maximum of five
request starts in any one-second window, and at most 1,500 attempts for 300
seconds. Stationary gates apply to every value, and the first error closes the
source without retry. Slow responses may reduce the achieved cadence; overdue
scheduler slots are skipped rather than replayed. The preceding one-request-per-second schedule completed
one bounded vehicle run, and the faster schedule completed one separately
reviewed 30-second stationary run. Neither result establishes decoded recording,
moving-vehicle use, or a longer session.

The separate `drive-session` path reuses only that fixed six-PID scheduler and
the already verified, capture-bound route. It deliberately omits the DTC
snapshot, requires a new decoded-only SQLite database, and serves the same
packaged dashboard over loopback with an explicit recording indicator. Its
moving policy changes only the RPM and speed bounds to their standard decoded
domains; the stationary dashboard's zero-speed and idle-RPM gates remain
unchanged. The command is capped at 1,800 seconds and five starts per selected
second, skips overdue slots, never retries or reconnects, and shuts down on the
first acquisition, decoding, or recording error. Its privacy-safe final summary
contains request and sample counts plus achieved rates, never values, raw
exchanges, capture contents, or route identifiers. The implementation is
offline-capable because the Python runtime and dashboard assets are local, but
offline verification alone does not authorize a stationary or moving vehicle
run.

The installed Python runtime depends only on the standard library; React, Tailwind,
Farstar source components, game-hud, and Motion are build-time frontend inputs
whose compiled assets ship inside the Python package. Each vehicle request must be serialized. Use monotonic time for scheduling/freshness and UTC wall time for durable event records. Sample and cycle rates are measured from monotonic timestamps; the first observation has no rate. The dedicated common-DME monitor spaces every request start by at least one second, enforces a duration-derived ceiling of no more than 300 attempts, and stops on a stationary-gate or acquisition failure. SQLite signal definitions are scoped to sessions and retain the service/request, target address, decoder offset/width/byte order/signedness, scale, offset, provenance, and verification metadata. The dedicated monitors store decoded samples and non-identifying definitions without raw exchanges; CSV retains the session id and observed sample rate. Configuration is declarative JSON, fully checked before any socket client is constructed, and contains no executable expressions.
