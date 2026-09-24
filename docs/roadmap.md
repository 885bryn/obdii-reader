# Incremental roadmap and risks

1. Validate the host and ENET adapter link without sending diagnostics; observe vehicle network announcements and document interface setup.
2. Confirm the Supra gateway's actual HSFZ reachability and target routing/address behavior from trustworthy documentation or controlled captures; HSFZ framing tests exist, but this vehicle-specific layer remains unverified.
3. With vehicle stationary, confirm supported SAE reads, response correlation, and failure behavior. Add only verified signals to profiles.
4. Measure latency and sustainable update rates per signal/module, then schedule conservatively with one in-flight request and expose observed rate/freshness.
5. Add documented OEM-specific read identifiers only with provenance and verification evidence. Keep unavailable signals explicit.
6. Review logs and safe procedure, then expand UI and analysis/export features.

Risks include uncertain adapter/link configuration, gateway routing and version variability, bus load and ECU rate limits, ambiguous responses, and possible vehicle-state consequences from undocumented diagnostic interactions. The code currently prioritizes fail-closed behavior. Update rate is mocked at 2 Hz; no vehicle rates are measured.
