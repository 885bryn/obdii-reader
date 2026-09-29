# Safety and vehicle testing

## Hard prohibition

The application must remain read-only. Never code or flash ECUs, change configuration/calibration, clear faults, execute routines/actuators, perform security access, reset modules, or use download/upload services. No raw-payload CLI or client send surface is provided. `SafetyPolicy` allows only SAE Mode 01 current-data reads, the single-byte Mode 03/07/0A emissions-DTC reads, Mode 09 vehicle-information reads, UDS ReadDataByIdentifier (0x22), and its internal TesterPresent form. Mode 04 clear/reset and Mode 08 control remain prohibited. Session control is denied by default. HSFZ live reads require explicit verified profile status and explicit tester/target addresses; never copy an address from another vehicle or protocol example as a Supra value.

Diagnostic/PAD Mode is permitted only as a manually entered vehicle state for bounded read-only research when justified by the applicable vehicle procedure. It does not authorize broader traffic, retries, scans, writes, routines, or state-changing ECU services. Record whether each empirical result used Diagnostic/PAD Mode. A feature is not ready for the end product until a separate reviewed test verifies it in the intended normal vehicle mode with Diagnostic/PAD Mode off.

## Safe empirical procedure

1. Start with the vehicle parked outdoors, parking brake set, transmission in Park (or neutral for manual), wheels chocked, and engine off. Keep a second person available. Do not test while driving unless the current-authorization section contains an exact, independently reviewed moving procedure; any such exception applies only to that one bounded procedure and does not weaken the stationary default.
2. Confirm the adapter and host OS network interface details before connecting; avoid changing vehicle state or network configuration based on guessed addresses.
3. Run only `discover` first. Its HSFZ UDP identification request and DoIP identification broadcast are bounded and contain no diagnostic requests. Record adapter, interface, vehicle state, timestamp, and captures.
4. Optional gateway verification: `python -m supra_telemetry verify-gateway --capture captures/discovery.json`. This validates a single captured IPv4 link-local HSFZ record, then binds TCP to that capture's exact local interface IPv4 and makes exactly one HSFZ request: UDS ReadDataByIdentifier VIN (22 F190), tester address F4, to the captured diagnostic address. A missing/stale local address fails during connection setup before a diagnostic frame is sent. F4 is corroborated by community protocol evidence; Toyota has not published this routing detail. No scan, retry, diagnostic-session request, tester-present, raw capture, or identifier output is performed. A matching response verifies only gateway HSFZ identity routing; it does not identify the DME address or establish signal/PID support. Do not run this against any vehicle without a compatible, stable ENET connection and stationary vehicle setup.
5. Optional DME identity verification, after gateway verification: `python -m supra_telemetry verify-dme --capture captures/discovery.json`. This binds TCP to the capture's exact local interface and makes one HSFZ request: UDS VIN (22 F190), tester address F4, candidate DME target 0x12, captured peer, TCP 6801. F4 and 0x12 are community-corroborated, not Toyota-published for this vehicle. A stale local address fails before diagnostic bytes are sent. No scan, retry, session change, tester-present, raw capture, identifier output, or signal read is performed. Failures report only a fixed generic reason category. A matching response verifies DME identity routing only; it does not establish coolant/oil PID support.
6. Optional temperature-PID support check, only after DME identity verification: `python -m supra_telemetry verify-temperature-support --capture captures/discovery.json`. It binds to the capture's exact local IPv4 address and uses tester F4, candidate DME target 0x12, captured peer, and TCP 6801. It sends at most three SAE J1979 Mode 01 bitmap requests: always PID 00; PID 20 only if PID 00 advertises continuation; PID 40 only if PID 20 advertises continuation. It never requests PID 05 or 5C values, retries, scans, changes session, sends tester-present, saves exchanges, or polls. Output reports the two support bits and request count, or a generic allowlisted failure. SAE J1979 defines these standard bitmap/PID meanings; an advertised support bit does not prove a plausible temperature value or vehicle-specific decoder correctness.
7. Optional common-DME support check, only after DME identity verification and as a separately bounded action: `python -m supra_telemetry verify-common-dme-support --capture captures/discovery.json`. It binds to the capture's exact local interface and sends exactly one request, Mode 01 PID 00, through tester F4 to DME target 0x12 at the captured peer on TCP 6801. It reports only the advertised support bits for RPM PID 0C, vehicle speed PID 0D, intake-air-temperature PID 0F, and throttle-position PID 11 plus a conservative request count. It does not request values, retry, scan, poll, change session, send tester-present, write, actuate, or persist the exchange. The implementation passed offline verification and independent review. On 2026-09-27, its first bounded vehicle run completed stationary with the engine off and PAD/Diagnostic Mode off; one reported request advertised all four candidate PIDs. This establishes support bits only, not plausible values or safe polling. Do not repeat the check merely to reconfirm the result; any future rerun requires a separately justified, reviewed session and must stop after its result or on any warning or error.
8. The consolidated information-gathering check is `python -m supra_telemetry collect-read-only-suite --capture captures/discovery.json`. It uses only the captured source interface, captured peer, tester F4, fixed DME target 0x12, and TCP 6801. Its four fixed phases are: (1) conditional Mode 01 support bitmaps `00` through `E0`, at most eight requests; (2) one Mode 01 value request each for PIDs `0C`, `0D`, `0F`, and `11`, at most four; (3) one emissions-DTC read each for Mode 03, 07, and 0A, at most three; and (4) Mode 09 InfoType `00` followed only by advertised InfoTypes `02`, `04`, `06`, and `0A`, at most five. The total ceiling is 20 requests. It uses fresh support and stationary plausibility gates, a fresh source-bound connection for each phase, two-second warning windows, stop-on-first-failure behavior, and no retries, scans, session changes, tester-present, clears, controls, writes, polling, or raw persistence. On 2026-09-27, its first reviewed stationary, engine-idling, PAD-off run completed inventory and common values, then stopped during DTC reading with `response-invalid` after a conservative total of 11 requests. A second run verified strict count-prefixed decoding for stored and pending DTC reads, then stopped when the permanent read returned `uds-rejected` after a conservative total of 13 requests. It reported no stored DTCs and pending `P0420`. Neither run reached Mode 09 or the monitor. Future failure output preserves only allowlisted completed summaries, decoded codes, fixed structural or rejection categories, and counts; raw replies and numeric response codes remain private. Do not rerun this suite until a new procedure is separately reviewed.
9. The optional one-shot temperature-values check is available as `python -m supra_telemetry read-temperature-values --capture captures/discovery.json`. It uses the same exact capture interface, peer, tester F4, DME target 0x12, and TCP 6801. It attempts at most two application requests total on one connection: exactly Mode 01 PID 05 once, then PID 5C once. Any first-request failure stops the sequence. There are no support-bitmap repeats, retries, polling, scans, tester-present messages, session changes, fault clears, routines, actuator/security requests, writes, or raw persistence. A positive response must exactly match `41 05 xx` or `41 5C xx`; each reported value is the byte minus 40 °C. Output is privacy-safe and `requests_sent` conservatively counts attempts (an upper bound when transmission is uncertain). Both values and the route have been verified with one-shot reads on this vehicle in normal engine-running mode without PAD/Diagnostic Mode. Stop on unexpected response or vehicle warning.
10. The dedicated `monitor-temperatures --capture captures/discovery.json` path is limited to the two previously one-shot-verified standard temperature reads. It allows at most 300 seconds, with at least a 2-second idle gap after each completed two-read cycle. At the duration limit it starts no new request and closes the dashboard; an in-flight request may finish or time out before cleanup. Any request/response failure closes the dashboard and stops the command without retry. One controlled 300-second vehicle run completed on 2026-09-26 in normal engine-running mode without PAD/Diagnostic Mode, with logging off, a clean exit, and no observed acquisition or recording error. Its approximate completed-pair rate was 0.49–0.50 per second. Five chronological coolant/oil checkpoint pairs were 77/78, 79/84, 82/88, 81/90, and 83/90 °C; these are checkpoint samples, not run-wide extrema. This evidence establishes only that bounded run, not longer duration or recording. Keep any further test stationary, use the same conservative limits unless a separately reviewed procedure changes them, and stop immediately if anything unexpected occurs. The optional `--db` stores decoded samples only; logging is off by default and recording has not been vehicle-tested.
11. The client dashboard's simulated mode opens no vehicle connection. Live mode uses only the already verified DME route and six Mode 01 PIDs. It reserves its loopback listener before any vehicle request, then attempts the existing fixed Mode 03/07/0A emissions-DTC snapshot once with at least one second between request starts. Monitoring starts only after another one-second quiet interval and either a complete snapshot or the exact previously observed partial result in which stored and pending decode successfully and permanent Mode 0A is rejected as `service-not-supported`; every other DTC outcome prevents monitor construction. The current faster monitoring candidate uses a fixed 20-slot, two-second scheduler with ten request slots: RPM `0C` four times, throttle `11` twice, and speed `0D`, intake temperature `0F`, coolant `05`, and oil temperature `5C` once each. Its 100 ms slot clock targets 0.5-second RPM, one-second throttle, and two-second supporting values while keeping requests serialized. Monitoring is bounded by 300 seconds, a rolling maximum of five request starts in any one-second window, and five attempts per selected second for at most 1,500 monitoring attempts at 300 seconds. Slow responses may reduce the achieved cadence; overdue scheduler slots are skipped rather than replayed. Values remain subject to the stationary gates, and the first monitoring error closes the connection without retry. The dashboard persists neither samples nor raw exchanges. The prior one-request-per-second schedule completed one bounded vehicle run; the faster schedule later completed one separately reviewed 30-second stationary run. Neither result authorizes a retry, recording, moving use, or a longer session.
12. The separate `drive-session` command uses the same six fixed Mode 01 requests, verified capture-bound route, serialized scheduler, rolling five-starts-per-second limit, skipped overdue slots, and stop-on-first-error behavior. It sends no DTC request and exposes no retry, reconnect, discovery, address, raw-payload, session-change, clear, routine, control, or write option. It requires a new decoded-only SQLite database and serves the packaged dashboard over loopback, so internet and Codex are not runtime dependencies. Its source permits the standard decoded RPM and speed domains and is capped at 1,800 seconds and 9,000 monitoring attempts. It records no raw exchange or route/capture identifier and prints only privacy-safe counts and achieved rates. The stationary, 60-second moving, 300-second moving, and one-time 30-minute procedures are consumed. The 30-minute candidate stopped after 568.64 seconds on a vehicle-speed timeout. No moving command or raw-capture run is currently authorized.
13. Do not activate generic profile-driven live `run` until routing and every request are reviewed against authoritative documentation and empirically shown to be read-only. Any transport, protocol, negative-response, or decoder error halts all later requests. Inspect the cause before starting a fresh run; in-process resume is not supported.
14. Check that data remains plausible while stationary. For the consolidated engine-running check, vehicle speed must remain 0 km/h, RPM must be consistent with idle, intake-air temperature must be physically plausible, and throttle must remain within 0–100%; these are assessment expectations, not prior empirical verification. End the session, disconnect cleanly, and inspect results before increasing scope or rate.

## Current vehicle authorization and next gate

The second consolidated normal-mode run, the single conditional PAD comparison,
and the single normal-mode client-dashboard rehearsal have ended. The dashboard
run used the reviewed one-request-per-second build and exited cleanly after its
300-second bound. Application snapshots showed a connected, non-halted source,
zero speed, plausible stationary values, stored and pending `P0420`, and the
previously allowed permanent `service-not-supported` result. No raw exchange was
persisted. This establishes only that bounded run and does not approve a retry,
client demonstration, or higher request rate. The faster candidate passed all
117 offline tests, independent medium review, and fresh independent verification.
Independent review approved the exact 30-second procedure below, and its one
authorized stationary normal-mode run has now completed with exit code 0. The
operator reported no vehicle warning; the application reported no acquisition
error, and no retry or second command occurred. The dashboard did not persist an
end-of-run rate summary, so this result does not prove the achieved display rate.
The one-time stationary recording authorization has been consumed. On
2026-09-28 the reviewed command exited 0 after 60.0 seconds and 288 requests.
The privacy-safe counts/rates were RPM 119/1.9833 Hz, throttle 60/1.0 Hz,
speed 22/0.3667 Hz, intake 30/0.5 Hz, coolant 27/0.45 Hz, and oil 30/0.5 Hz.
Private local database review passed: an end timestamp was present, all speed
samples were zero, the six counts were coherent, there were no sample/session
errors, signal definitions were privacy-safe, and `raw_exchanges` was empty.
No sample values or identifiers belong in tracked records.

The one-time 60-second low-speed moving authorization has been consumed. On
2026-09-28 the reviewed run exited 0 after 60.0 seconds and 287 requests.
Privacy-safe counts/rates were RPM 119/1.9833 Hz, throttle 60/1.0 Hz, vehicle
speed 23/0.3833 Hz, intake 30/0.5 Hz, coolant 25/0.4167 Hz, and oil 30/0.5 Hz.
Private database audit passed: the session was finalized, its summary matched
the counts and rates, there were no errors, speed included zero and nonzero
samples and stayed within 0–30 km/h, private plausibility and chronology checks
passed, definitions were privacy-safe, and `raw_exchanges` was empty. No sample
values or identifiers are recorded.

The one-time 300-second moving authorization has been consumed. The command
completed with exit code 0 after 300.0 seconds and 1,443 requests, and its six
privacy-safe signal counts/rates matched the private database. The database had
a finalized session, no recorded errors, both zero and nonzero speed samples,
plausible timestamp and non-speed-signal chronology, privacy-safe definitions,
and no raw exchanges. However, at least one recorded speed sample exceeded the
reviewed 30 km/h ceiling. The speed gate and overall procedure therefore failed.

The one-time 30-minute candidate later stopped fail-closed after 568.64 seconds
when a vehicle-speed request timed out. Its private database was finalized and
passed integrity, chronology, decoded-domain, privacy, and empty-raw-exchange
checks apart from the single allowlisted timeout row. The dashboard disappeared
because acquisition halt shuts down the loopback server.

**No vehicle command or raw-capture run is currently authorized. Do not repeat
the consumed 30-minute command.**

### Proposed capture-enhanced 30-minute repeat (draft; not authorized)

The user selected a second normal-driving candidate to investigate whether the
terminal timeout recurs and, if it does, what the host and transport observed.
"Capture all possible datapoints" means complete diagnostic evidence around the
same six-signal read-only session. It does **not** authorize discovery, scanning,
additional PIDs or ECUs, a different route or target, writes, controls, session
changes, retries, reconnects, or any other vehicle request.

The vehicle-facing behavior must remain identical to the consumed candidate:
the unchanged `drive-session` implementation from commit `fdb02f4`, the existing
verified capture-bound route, the same fixed six Mode 01 PIDs and scheduler, a
two-second response deadline, a maximum of five request starts per second, an
1,800-second ceiling, a 9,000-attempt ceiling, and stop on the first application
error. No application-level raw persistence will be added before this run,
because modifying the transport path would make the reproduction less direct.

The added evidence is passive and private:

1. The normal decoded-only SQLite database and privacy-safe command output.
2. A full-packet Windows Packet Monitor ETL filtered to TCP port 6801, captured
   at all Packet Monitor components with untruncated packets, all packet types,
   and packet/component/drop metadata. Preserve the original ETL as the
   authoritative artifact and derive separate normal and drop-only PCAPNG copies
   only for convenient packet inspection. PCAPNG conversion does not replace the
   ETL or its component/drop evidence.
3. ETW events collected in the same bounded trace from exactly these locally
   verified providers: `Microsoft-Windows-NDIS`, `Microsoft-Windows-TCPIP`,
   `Microsoft-Windows-DriverFrameworks-UserMode`,
   `Microsoft-Windows-Kernel-PnP`, `Microsoft-Windows-USB-USBHUB3`,
   `Microsoft-Windows-USB-USBXHCI`, `Microsoft-Windows-Dhcp-Client`,
   `Microsoft-Windows-NetworkProfile`, and
   `Microsoft-Windows-Wired-AutoConfig`. The harness will use all keywords and
   verbose level 5 for each provider only if the offline rehearsal demonstrates
   bounded volume and acceptable overhead; otherwise the provider set or level
   must be reduced and independently re-reviewed before vehicle use. Collect
   providers directly into the private trace rather than permanently enabling
   dormant event-log channels.
4. Privacy-sensitive pre/post host metadata sufficient to correlate adapter,
   driver, link, process, wall-clock, and monotonic timing, plus the relevant
   existing Windows event-log window. The TCP-port packet filter minimizes raw
   packet scope, but provider events may still include unrelated private host or
   device activity; treat the entire bundle as private rather than claiming that
   unrelated activity is absent.
5. A private manifest containing file sizes, SHA-256 hashes, tool/runtime
   versions, capture start/stop times, application start/stop times, exit status,
   and whether each expected artifact finalized successfully.

All ETL, PCAPNG, database, event exports, console logs, metadata, and analysis
working files must live under a fresh Git-ignored private capture directory.
They may contain MAC, IP/interface, device, route, timing, raw frame, or other
private values. Never add them to Git, paste them into tracked documentation, or
include their raw contents in a public report. Tracked results are limited to
redacted classifications, counts, relative timing, and pass/fail outcomes.

Before any vehicle use, implement and offline-test a bounded capture harness
that performs these steps without altering the application command or vehicle
traffic:

- require administrative capture capability, a fresh private output directory,
  no existing Packet Monitor session, no existing Packet Monitor filters, and
  at least 10 GiB of free space;
- add one harness-owned TCP-port-6801 filter, then start full-packet and provider
  tracing before the application with `--comp all`, `--type all`,
  `--pkt-size 0`, packet flags `0x03F`, a 4,096 MiB file limit, and circular log
  mode. On this host, `pktmon start help` defines `0x03F` as the combination of
  internal errors, summaries, source/destination information, selected NDIS
  metadata, raw packets, and component-registration changes (`0x001` through
  `0x020`). Record the Packet Monitor version and help-derived flag map privately,
  and reject the preflight if this binary does not accept or report that exact
  configuration. Prove that both the owned filter and trace are active before
  starting the unchanged `drive-session` command once. The 4 GiB limit bounds
  disk use; the post-run coverage gate below detects and rejects overwrite of
  any part of the application interval;
- stop and finalize tracing in a `finally` path after application exit, operator
  interruption, or a hard harness deadline no later than 60 seconds after the
  1,800-second application ceiling;
- never restart Packet Monitor, the application, or the diagnostic connection
  within the procedure; a capture failure invalidates the evidence and requires
  stopping the diagnostic run at the next safe opportunity;
- remove the harness-owned filter during cleanup only after proving no prior
  filters existed. Failure to restore the initial stopped/session-free and
  filter-free state is a harness failure that must be reported for manual
  recovery, never hidden by another run;
- preserve command output and artifact hashes without printing private adapter,
  route, packet, database, or event contents.

The harness must pass offline fault-injection checks for clean completion,
application timeout, peer close, partial frame, capture-start failure,
capture-stop failure, pre-existing filters, circular overwrite, trace loss,
operator interruption, and hard-deadline cleanup. An offline HSFZ-shaped TCP
exchange on port 6801 must prove that the exact owned filter passes the intended
flow. A rehearsal lasting at least 35 minutes must prove that full packets,
component/drop capability, start-to-stop time coverage, and finalized artifacts
fit comfortably within the 4 GiB bound without lost events or unacceptable
timing/CPU overhead. Trace metadata and decoding must prove that every selected
provider was registered and enabled for the full interval; a provider may
legitimately emit zero events during a healthy rehearsal. Likewise, zero packet
drops is expected and does not fail the capability gate. Exercise controlled
offline network/provider events where safe, but never create a USB, driver, or
device fault merely to force an event. The capture stack itself may perturb host
timing, so any later comparison must state that limitation. The exact harness,
exact command, artifact handling, stop conditions, and post-run audit require
independent review. Passing offline checks does not authorize the vehicle run;
the Lead must record the reviewed one-time procedure and the user's final
go/no-go decision.

The eventual exact command must use a new database inside the fresh ignored
directory, for example `captures/private/t009-15-<private timestamp>/decoded.sqlite`;
the consumed `moving-recording-30min.sqlite` path must not be reused. The harness
must record the exact command privately and verify before start that both the
directory and database path are unused.

If eventually authorized, the operating conditions remain those of the prior
normal-driving candidate: two people; driver handles only the vehicle; passenger
handles only the secured laptop; normal engine operation with PAD/Diagnostic
Mode off; begin parked; no test-specific speed target or maneuver; obey all laws
and conditions; and stop at the next safe opportunity for any vehicle warning,
unsafe condition, stale display, application/capture/recording error, timeout,
transport or decoder error, implausible value, or equipment problem. There is no
retry regardless of whether the run completes or fails.

The private post-run audit must first validate database and artifact integrity,
then prove that the ETL began before the application, ended after it, did not
overwrite any part of the application interval, reported no lost/internal
capture events, contains registered subscriptions for the expected providers,
and has coherent packet/component coverage for the diagnostic flow. The
overwrite decision must use ETL buffer, sequence, loss, and coverage metadata;
file size and first/last timestamps alone are insufficient. If any
coverage gate fails, packet absence is uninterpretable and the result is limited
to application-level evidence; there is still no retry. With valid coverage, the
audit must correlate the final request with packet and host evidence and classify,
without publishing raw values, whether the Windows stack observed the request;
whether TCP acknowledged it; whether no, partial, control-only, complete, or
late HSFZ data arrived; and whether FIN, RST, retransmission, Packet Monitor
drop, link, driver, USB, PnP, power, or timing-anomaly evidence was present. The
ETL can locate evidence within the observed Windows stack but cannot prove what
happened beyond its observation points in the cable, adapter firmware, gateway,
or ECU. PCAPNG alone cannot support a packet-drop conclusion. Compare any failure
with the prior vehicle-speed timeout in signal, elapsed time, and transport shape.
A clean 30-minute run would show non-recurrence once, not prove the earlier event
fixed or establish indefinite reliability.

### Completed one-time 60-second low-speed moving gate (historical)

1. In daylight and dry weather, preselect a legal, quiet local route with a safe
   pull-off and a posted limit that permits remaining at or below 30 km/h. Do not
   use a highway, enter congestion, exceed 30 km/h, accelerate aggressively, or
   add another maneuver or test objective.
2. Use two people. The driver controls only the vehicle and must never view,
   touch, or operate the laptop. The front passenger is the sole operator and
   must be able to observe the dashboard without obstructing the driver.
3. Before starting, remain parked with the parking brake applied and transmission
   in Park. Run the engine normally with PAD/Diagnostic Mode off. Close ISTA,
   BimmerLink, coding tools, and every other diagnostic application. Confirm no
   vehicle warning, normal battery condition, the existing private capture and
   source-bound route, exactly one expected link-local adapter address, the
   reviewed build containing `fdb02f4`, all 134 offline tests passing, and that
   `moving-recording-60s.sqlite` does not exist. Do not rediscover, scan,
   substitute an address, or run another vehicle command in the same session.
4. Secure the laptop and adapter on the passenger side. Route and secure the
   cable completely away from pedals, steering, the driver's legs, seat travel,
   and other controls; verify it cannot be pinched by a door, window, or seat.
   If safe routing is uncertain, do not run. Toyota's stationary ISTA service
   instructions warn that pinching or disconnecting its Supra diagnostic cable
   can cause communication or ECU damage; those instructions do not approve
   moving use, so this physical gate is mandatory.
5. While still parked, the passenger runs exactly:

   ```powershell
   python -m supra_telemetry drive-session --capture captures/discovery.json --db moving-recording-60s.sqlite --duration 60 --confirm-hands-off
   ```

   The passenger opens the printed `127.0.0.1` URL and confirms `RECORDING`,
   fresh live values, zero speed, and plausible idle data before telling the
   driver to begin the preselected route. Internet and Codex are not required.
6. During the run, the driver follows the route and remains at or below 30 km/h.
   The passenger watches only for the recording indicator, fresh plausible data,
   and an application error. Any vehicle warning, unsafe traffic/weather/route
   condition, missing or stale display, browser/API failure, timeout, transport
   or decoder error, implausible value, recording error, adapter/cable problem,
   or speed above 30 km/h fails the gate. The driver pulls over safely; once safe,
   the passenger presses `Ctrl+C` if the process has not stopped. Do not retry,
   change PAD state, or run another vehicle command.
7. After automatic completion, park safely before the passenger handles or
   disconnects equipment. Keep the capture and SQLite file local. Share only
   the privacy-safe final JSON, request count, per-signal counts/rates, fixed
   error category, and post-run gate pass/fail results.
8. The private database review must confirm: one finalized session; exactly the
   six expected signals; positive counts for each signal; the six counts sum to
   the reported request count and the reported rates agree with counts/duration;
   no sample or session error; at least one speed sample above 0 km/h; every
   speed sample between 0 and 30 km/h; privately reviewed RPM, temperature, and
   throttle chronology is plausible for the bounded route; signal definitions
   contain no route/request/target identifiers; and `raw_exchanges` is empty.
   Any failed gate ends the candidate with no retry.

The 60-second moving gate is complete. It authorizes no retry or follow-up run.

### Completed 300-second moving stage (failed procedural gate; historical)

Independent medium review approved this exact stage for one run. It used the
same preselected legal quiet local route, roles, secured cable and
equipment, stationary start, <=30 km/h limit, existing capture-bound route,
PAD-off state, no-other-diagnostics preflight, and stop/no-retry boundaries as
the completed 60-second gate above. Use a fresh database path and confirm it does
not already exist. Begin the run while parked, with the passenger operating the
laptop and the driver fully hands-off from it. The proposed command is:

```powershell
python -m supra_telemetry drive-session --capture captures/discovery.json --db moving-recording-300s.sqlite --duration 300 --confirm-hands-off
```

This historical command is no longer authorized. After the run, the passenger had to wait until the
vehicle is safely parked before handling equipment. A private audit must apply
the same gates as the 60-second run: finalized session; matching summary,
counts, and rates; no errors; speed samples including both zero and nonzero and
all within 0–30 km/h; plausible private signal chronology; privacy-safe signal
definitions; and empty `raw_exchanges`. Any failed gate means stop and no retry.

The 300-second command completed at the application level, but its private audit
failed the reviewed 30 km/h ceiling. Under that procedure's no-retry rule, that
candidate ended. The application, database, and other audit gates passed. The
speed result is retained as evidence from ordinary road operation under the
then-current rule; it is not a software or database failure. Toyota PDS battery
guidance describes stationary PAD/ISTA service work; it does not establish a
safe battery or telemetry duration while driving.

### Completed one-time 30-minute normal-driving procedure (historical)

The user has selected ordinary lawful driving as the intended validation
condition. This procedure removes the test-specific 30 km/h ceiling: the driver
must obey posted limits, traffic laws, and conditions, and must not speed, race,
or make aggressive maneuvers for the test. The previous 60-second pass and
300-second run remain consumed; the latter's speed-ceiling failure does not
invalidate its application, recording, privacy, or other passing audit results.
The user explicitly accepts proceeding to 30 minutes without another staged
duration gate. The software still caps a session at 1,800 seconds and 9,000
monitoring attempts.

Independent medium review approved this exact procedure and the current
implementation for one run. That authorization has been consumed. Its historical
requirements were:

1. A competent two-person operation during an ordinary lawful trip. The driver
   operates only the car and never views, touches, or operates the laptop. A
   front passenger is the sole laptop operator and may stop the application
   without distracting the driver.
2. Normal engine operation with PAD/Diagnostic Mode off. Begin parked, with
   parking brake set and transmission in Park. Close ISTA, BimmerLink, coding
   tools, and every other diagnostic application. Check for vehicle warnings,
   suitable battery condition, the existing private capture and its verified
   source-bound route, and exactly one expected link-local adapter address.
   Do not rediscover, scan, substitute an address, or run another vehicle
   command in the session.
3. A fresh database path that does not already exist. Secure the laptop,
   adapter, and cable on the passenger side, away from pedals, steering, the
   driver's legs, seat travel, controls, doors, and windows.
4. While parked, run exactly once:

   ```powershell
   python -m supra_telemetry drive-session --capture captures/discovery.json --db moving-recording-30min.sqlite --duration 1800 --confirm-hands-off
   ```

   The passenger opens the printed loopback URL and confirms `RECORDING`, fresh
   plausible values, and zero speed before the trip proceeds. Internet and
   Codex are not required.
5. Drive normally, obeying posted limits, laws, and road/weather conditions.
   There is no test-specific speed target or maneuver. Stop the diagnostic run
   at the next safe opportunity if there is any vehicle warning, unsafe driving
   condition, missing/stale display, application or recording error, timeout,
   transport/decoder error, implausible value, or equipment/cable problem. Do
   not retry. Park safely before handling or disconnecting equipment.
6. Keep capture and database local. Private audit must confirm one finalized
   session; exactly the six expected signals with positive counts; counts sum
   to the privacy-safe reported request count and rates match counts/duration;
   no sample or session errors; decoded speed values remain in the standard
   decoder domain and are plausible in private chronology for the route; other
   signal chronology is plausible; definitions contain no route/request/target
   identifiers; and `raw_exchanges` is empty. Apply all summary, error,
   chronology, privacy, and raw-exchange gates. Any failed gate ends the
   candidate with no retry. Report only redacted pass/fail outcomes and
   privacy-safe counts/rates, never sample values or identifiers.

The run stopped after 568.64 seconds when one vehicle-speed request timed out.
The 1,800-second software ceiling and 9,000-attempt cap bounded the command but
did not establish sustained vehicle, battery, or bus behavior. The consumed
authorization covers no retry.

## Completed one-time decoded-recording gate (historical)

The exact implementation and procedure passed independent medium review, all
134 offline Python tests, the production frontend build, and installable-wheel
inspection, and were merged to local `main`. The one authorized stationary
validation is complete; this historical procedure no longer authorizes another
run, driving, or a longer duration.

The completed one-time procedure was:

1. Park outdoors, apply the parking brake, select Park, chock the wheels, and
   keep a second person available. Start the engine normally with PAD/Diagnostic
   Mode off. The vehicle must remain stationary for the entire command.
2. Close ISTA, BimmerLink, coding tools, and every other program that could use
   the diagnostic connection. Use only the existing private capture and its
   verified source-bound route. Do not rediscover, scan, substitute an address,
   or run another vehicle command in the same session.
3. Confirm the adapter has one expected IPv4 link-local address, checked-out
   `main` contains implementation commit `fdb02f4`, the full 134-test offline
   suite passed, independent review approved this procedure, and the chosen
   SQLite path does not already exist. Do not
   begin if the adapter, capture, vehicle state, battery condition, build, or
   procedure status is uncertain.
4. Run the exact reviewed command once. Open the printed `127.0.0.1` URL in a
   normal browser. Internet access and Codex are not required. Confirm the page
   shows `RECORDING`, fresh live values, zero speed, and plausible idle data while
   the vehicle remains parked.

The command used was:

```powershell
python -m supra_telemetry drive-session --capture captures/discovery.json --db stationary-recording-60s.sqlite --duration 60 --confirm-hands-off
```

Any missing recording indicator, browser/API failure, timeout, transport error,
unexpected response, implausible value, nonzero speed, recording error, adapter
problem, or vehicle warning ends the candidate run. While still parked, press
`Ctrl+C` if the process does not stop itself, then disconnect cleanly. Do not
retry, change PAD state, run another command, or begin driving. Share only the
final JSON result, request count, per-signal sample counts/rates, and fixed error
category. Keep the capture and SQLite file local; never share raw responses,
VIN, MAC, IP/interface details, or other identifiers.

After the command, the private database must be reviewed locally before the
candidate can be called clean. That offline review must confirm that the session
has an end timestamp, every recorded vehicle-speed sample is exactly 0 km/h,
all six expected signals have coherent counts and achieved rates, no sample or
session error was recorded, signal definitions contain no route/request/target
identifiers, and `raw_exchanges` is empty. Report only pass/fail for those gates
plus the command's privacy-safe counts/rates; do not copy sample values, database
rows, or identifiers into tracked documentation. Those gates later passed and
enabled the now-consumed 60-second moving gate. The subsequent 300-second
candidate failed its reviewed speed ceiling, so that historical command cannot
be repeated. The later one-time 30-minute command also stopped fail-closed and
cannot be repeated. No vehicle command is currently authorized.

## Completed faster-cadence validation

This procedure authorized one stationary 30-second candidate run of the reviewed
faster scheduler. That run is complete. The procedure is retained as historical
evidence only and is no longer authorization to run the command. Its clean result
verifies only this short bounded session; it does not authorize a retry, a
300-second run, or a client demonstration.

Before the candidate run:

1. Park outdoors, apply the parking brake, select Park, chock the wheels, and keep
   a second person available. Start the engine normally with PAD/Diagnostic Mode
   off. Do not test while driving.
2. Close ISTA, BimmerLink, coding tools, and every other application that could
   use the diagnostic connection. Use only the existing private capture and its
   verified source-bound route; do not rediscover, scan, substitute an address,
   or run another vehicle command in this session.
3. Confirm the adapter is up with one IPv4 link-local address, the synchronized
   build is at the reviewed commit, all 117 offline tests pass, and independent
   review approves this exact procedure. Do not begin if the adapter, capture,
   vehicle state, battery condition, or procedure status is uncertain.

The historical one-time command was:

```powershell
python -m supra_telemetry client-dashboard --mode live --capture captures/discovery.json --duration 30
```

The existing DTC snapshot remains limited to Mode 03, 07, and 0A once each with
at least one second between starts. Monitoring may proceed only after either a
complete safely decoded snapshot or the previously observed partial outcome of
safely decoded stored/pending results plus permanent `service-not-supported`.
Monitoring then uses the reviewed 20-slot
schedule, a rolling maximum of five starts in any one-second window, a 30-second
request-start deadline, and at most 150 monitoring attempts. Overdue slots are
skipped. The first error stops acquisition without retry or reconnect.

Any timeout, transport error, unexpected response, disallowed rejection,
implausible value, nonzero speed, vehicle warning, adapter issue, or browser/API
failure ends the run. On a browser/API failure, press `Ctrl+C` immediately because
the acquisition worker cannot detect a closed or failed browser; otherwise press
`Ctrl+C` only if the dashboard does not stop itself. Then disconnect cleanly. Do
not retry, switch PAD state, run another command, or
start a longer dashboard session. Report only exit status, decoded values/codes,
observed sample rates/ages, and fixed error categories. Never share the capture,
raw responses, VIN, MAC, IP/interface information, or other identifiers.

## Completed normal-mode client-dashboard rehearsal

The implementation, tests, independent review, synchronization, and one
authorized run are complete. The procedure below is retained as historical
evidence only and is no longer authorization to run the command. The completed
run verifies only the original one-request-per-second schedule in that bounded
stationary session; it does not authorize an additional demonstration or the
new faster schedule.

Before the candidate run:

1. Use the stationary setup in step 1 above: outdoors, parking brake set,
   transmission in Park, wheels chocked, engine idling normally with PAD/Diagnostic
   Mode off, and a second person available. Do not test while driving.
2. Close ISTA, BimmerLink, coding tools, and every other application that could use
   the diagnostic connection. Use only the existing private discovery capture and
   its already verified source-bound route; do not rediscover, scan, substitute an
   address, or run another vehicle command in this session.
3. Confirm the synchronized candidate build's complete offline test suite passes
   and its independent review approves this exact command and procedure. If the
   adapter, link, capture, vehicle state, or battery condition is uncertain, do not
   begin.

The historical one-time command was:

```powershell
python -m supra_telemetry client-dashboard --mode live --capture captures/discovery.json --duration 300
```

In that reviewed build, the loopback listener was reserved before the DTC snapshot opened one source-bound
connection and attempts at most Mode 03, 07, and 0A once each in that order, with
at least one second between request starts. The known `service-not-supported` result for
permanent Mode 0A is the only partial result that may proceed, and only when stored
and pending results decoded safely. After another one-second quiet interval,
monitoring opened one source-bound
connection and used only the former fixed ten-request schedule, repeating within
the 300-attempt and 300-second ceiling. The complete command can therefore attempt
at most 303 application requests. It performs no retry, scan, reconnect after a
monitoring error, discovery, session change, tester-present exchange, clear,
routine, control, write, recording, or raw persistence.

Any timeout, transport error, unexpected response, rejection other than the exact
allowed permanent-service result, implausible value, nonzero speed, vehicle
warning, adapter problem, or browser/API error ends the run. Press `Ctrl+C` if the
dashboard does not stop itself, then disconnect cleanly. Do not retry, switch PAD
state, run another command, or present the live mode again in the same session.
Share only the command's fixed status and decoded values/codes; never share the
capture, raw responses, VIN, MAC, IP/interface information, or other identifiers.

Offline preparation and independent review were completed for a minimal read-only DTC comparison in manually entered PAD/Diagnostic Mode using only the already verified route and fixed Mode 03/07/0A reads. Implementation commit `ab599d2` is synchronized, and the single authorized run occurred on 2026-09-28. It must not be repeated. Toyota's published PAD instruction applies to its specific ISTA transport-mode deletion procedure and does not by itself establish that generic DTC reading requires PAD Mode.

## Completed manual PAD DTC comparison

The implementation, tests, documentation, independent review, synchronization, and one authorized run are complete. The command attempted all three fixed reads: stored and pending each decoded `P0420`, while the permanent Mode 0A read was rejected as `service-not-supported`. It reported three attempts and stopped with no retry, other vehicle command, or raw persistence. The historical normal-mode result was no stored DTC, pending `P0420`, and rejection of the permanent read. These single observations show that PAD did not make Mode 0A available in the comparison; they do not explain the stored-code difference, diagnose `P0420`, prove that PAD is required, or provide product-acceptance evidence.

The procedure below is retained as historical evidence only. It is no longer authorization to run the command.

Before the one candidate run:

1. Use the stationary setup in step 1 above: outdoors, parking brake set, transmission in Park (or neutral for a manual), wheels chocked, engine off, and a second person available. Do not test while driving.
2. Close ISTA, BimmerLink, coding tools, and any other application that could use the diagnostic connection. Use only the already verified private discovery capture and its source-bound route; do not rediscover, scan, or substitute addresses.
3. Connect an appropriate battery charger at the under-hood jump-start terminals. Toyota bulletin T-SB-0062-22 gives the conservative limits used here for its 2023 Supra PDS procedure: keep voltage at or above 12.3 V, do not exceed 14.8 V at room temperature for an AGM battery, and do not use rapid charging. If those conditions cannot be maintained, do not begin.
4. Manually enter PAD/Diagnostic Mode only after the charger and stationary setup are confirmed. The cited Toyota procedure uses three Start-Stop presses within 0.8 seconds. The application must never perform or simulate this action. Do not continue into the bulletin's ISTA transport-mode deletion steps; that workflow includes state-changing operations and fault-memory clearing that are prohibited here.
5. Confirm that the synchronized build's complete offline test suite passed and its independent review approved this exact command and procedure.

Run exactly once:

```powershell
python -m supra_telemetry compare-pad-emissions-dtcs --capture captures/discovery.json --confirm-manual-pad
```

The confirmation flag is mandatory and acknowledges only that PAD was entered manually under this reviewed procedure. The command opens one source-bound connection and attempts at most three application requests in order: Mode 03 stored DTCs once, Mode 07 pending DTCs once, and Mode 0A permanent DTCs once. The request counter advances before each attempt. It performs no retry, reconnect, discovery, scan, session change, tester-present exchange, fault clear, routine, control, write, or raw persistence.

Any timeout, connection or transport error, exact negative response, response-pending event, HSFZ error-control event, malformed or unexpected response, charger problem, acquisition error, or vehicle warning ends the run immediately. Later reads are not attempted. Do not switch vehicle state, retry, rerun the suite, or issue another diagnostic command in the same session. Save only the command's privacy-safe JSON result, which may contain decoded DTCs, counts, the failed read, fixed structural categories, and an allowlisted rejection category; never save or share raw replies, capture contents, numeric negative-response codes, or vehicle/network identifiers.

After the command exits, manually leave PAD mode and power the vehicle down according to the applicable vehicle instructions, then disconnect the diagnostic link and charger safely. Compare the one PAD result only with the recorded bounded normal-mode result. A PAD success or different rejection is research evidence only; normal PAD-off behavior remains the product requirement.

This is a conservative engineering checklist, not a substitute for Toyota/BMW service instructions. Do not probe unknown identifiers or try write-capable services.

Scapy's HSFZ parser documents short control `0x12` alive frames with source/target and a long identification-string variant. During a diagnostic request, this app audits and skips either frame without replying. Whether a particular gateway expects any keep-alive response remains unknown until vehicle testing.
