# Incremental roadmap and risks

1. **Completed 2026-09-24:** validate the host and ENET adapter IPv4 link without sending diagnostics and capture a valid HSFZ identification response. No DoIP announcement was received in that bounded attempt.
2. **Gateway portion completed 2026-09-24:** after the connection-only check, the user reported that the separately reviewed, single-request gateway VIN identity check succeeded. This verifies gateway identity routing only. Candidate DME target routing remains unverified on the vehicle.
3. With vehicle stationary, confirm supported SAE reads, response correlation, and failure behavior. Add only verified signals to profiles.
4. Measure latency and sustainable update rates per signal/module, then schedule conservatively with one in-flight request and expose observed rate/freshness.
5. Add documented OEM-specific read identifiers only with provenance and verification evidence. Keep unavailable signals explicit.
6. Review logs and safe procedure, then expand UI and analysis/export features.

Risks include intermittent physical adapter/link behavior, gateway routing and version variability, bus load and ECU rate limits, ambiguous responses, and possible vehicle-state consequences from undocumented diagnostic interactions. Reconfirm a stable link before each session. The code currently prioritizes fail-closed behavior. Update rate is mocked at 2 Hz; no vehicle rates are measured.
