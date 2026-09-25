# Signal support matrix

| Signal | Current status | Source / formula | Rate |
|---|---|---|---|
| Engine RPM | Demo only; live candidate, unverified | Mock waveform; candidate SAE Mode 01 PID 0x0C, SAE formula raw/4 | Demo 2 Hz; live unknown |
| Vehicle speed | Demo only; live candidate, unverified | Mock waveform; candidate SAE Mode 01 PID 0x0D, raw km/h | Demo 2 Hz; live unknown |
| Coolant temperature | Demo only; live candidate, unverified | Mock constant; candidate PID 0x05, raw−40 °C | Demo 2 Hz; live unknown |
| Engine oil temperature | Live candidate, unverified; absent from demo | Candidate SAE Mode 01 PID 0x5C, raw−40 °C; vehicle ECU support and ENET route unverified | Live unknown |
| Boost | Demo derived | Synthetic mock formula only; not vehicle data | Demo 2 Hz |
| Gear | Unavailable | No verified source configured | None |
| IAT, throttle, accelerator, wheel speeds, steering, brakes, acceleration, transmission | Unverified / unsupported | Requires evidence-backed vehicle-specific support; no DIDs invented | Unknown |

Signal definitions record measured/derived/unavailable category, provenance, confidence, verification, and expected/observed rates. Live profiles are preflighted for unique IDs, supported types, exact address/offset/width types and bounds, safe request shapes, boolean flags, finite codecs, and positive finite expected rates before any socket client is constructed. The Supra template keeps all candidates disabled and omits vehicle addresses. No signal is currently supported as real vehicle telemetry. Live cycles include unavailable/disabled signals explicitly; after a live error, not-yet-polled signals are labeled halted without being requested.

The implemented Mode 01 subset is limited to PIDs `05`, `0C`, `0D`, `0F`, `11`, and `5C`. Their units and formulas are canonicalized during profile loading; a profile that supplies conflicting unit, width, offset, scale, signedness, or byte order is rejected before network I/O. PID `5C` uses the standard one-byte raw−40 °C formula, but remains only a disabled/unverified vehicle candidate. Other Mode 01 PIDs remain unavailable until a decoder and tests are added.
