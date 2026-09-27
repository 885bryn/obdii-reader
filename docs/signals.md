# Signal support matrix

| Signal | Current status | Source / formula | Rate |
|---|---|---|---|
| Engine RPM | Demo only; live candidate, unverified | Mock waveform; candidate SAE Mode 01 PID 0x0C, SAE formula raw/4 | Demo 2 Hz; live unknown |
| Vehicle speed | Demo only; live candidate, unverified | Mock waveform; candidate SAE Mode 01 PID 0x0D, raw km/h | Demo 2 Hz; live unknown |
| Coolant temperature | One-shot verified; repeated monitor untested | SAE J1979 Mode 01 PID 0x05, raw−40 °C | At least 2-second gap between cycles |
| Engine oil temperature | One-shot verified; repeated monitor untested; absent from demo | SAE J1979 Mode 01 PID 0x5C, raw−40 °C | At least 2-second gap between cycles |
| Boost | Demo derived | Synthetic mock formula only; not vehicle data | Demo 2 Hz |
| Gear | Unavailable | No verified source configured | None |
| IAT, throttle, accelerator, wheel speeds, steering, brakes, acceleration, transmission | Unverified / unsupported | Requires evidence-backed vehicle-specific support; no DIDs invented | Unknown |

The user confirmed both temperature values were successfully read once with the engine running in normal mode without PAD/Diagnostic Mode. Repeated monitor behavior and sustained value plausibility remain unverified. SAE Mode 01 support bitmap advertisement alone does not establish plausible values.

Signal definitions record measured/derived/unavailable category, provenance, confidence, verification, and expected/observed rates. The generic live profile loader checks unique IDs, supported types, exact address/offset/width types and bounds, safe request shapes, boolean flags, finite codecs, and positive finite expected rates before any socket client is constructed. The Supra template keeps all candidates disabled and omits vehicle addresses. Temperature support is limited to the dedicated one-shot read and the not-yet-vehicle-tested monitor; no other real-vehicle signals are established. Live cycles include unavailable/disabled signals explicitly; after a live error, not-yet-polled signals are labeled halted without being requested.

The implemented Mode 01 subset is limited to PIDs `05`, `0C`, `0D`, `0F`, `11`, and `5C`. Their units and formulas are canonicalized during profile loading; a profile that supplies conflicting unit, width, offset, scale, signedness, or byte order is rejected before network I/O. PIDs `05` and `5C` and their one-byte raw−40 °C decoding have been verified with one-shot reads on this test vehicle. Repeated monitor behavior remains unverified. Other Mode 01 PIDs remain unavailable until a decoder and tests are added.
