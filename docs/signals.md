# Signal support matrix

| Signal | Current status | Source / formula | Rate |
|---|---|---|---|
| Engine RPM | Vehicle support bitmap and offline one-shot reader verified; value unverified | SAE Mode 01 PID 0x0C, raw/4 rpm | Demo 2 Hz; live unknown |
| Vehicle speed | Vehicle support bitmap and offline one-shot reader verified; value unverified | SAE Mode 01 PID 0x0D, raw km/h | Demo 2 Hz; live unknown |
| Coolant temperature | One-shot and one bounded 300-second monitor verified | SAE J1979 Mode 01 PID 0x05, raw−40 °C | Observed about 0.49–0.50 completed pairs/s in the bounded monitor; at least 2-second gap between cycles |
| Engine oil temperature | One-shot and one bounded 300-second monitor verified; absent from demo | SAE J1979 Mode 01 PID 0x5C, raw−40 °C | Observed about 0.49–0.50 completed pairs/s in the bounded monitor; at least 2-second gap between cycles |
| Intake-air temperature | Vehicle support bitmap and offline one-shot reader verified; value unverified | SAE Mode 01 PID 0x0F, raw−40 °C | Live unknown |
| Throttle position | Vehicle support bitmap and offline one-shot reader verified; value unverified | SAE Mode 01 PID 0x11, raw×100/255 % | Live unknown |
| Boost | Demo derived | Synthetic mock formula only; not vehicle data | Demo 2 Hz |
| Gear | Unavailable | No verified source configured | None |
| Accelerator, wheel speeds, steering, brakes, acceleration, transmission | Unverified / unsupported | Requires evidence-backed vehicle-specific support; no DIDs invented | Unknown |

The user confirmed both temperature values in one-shot reads and one 300-second normal-mode monitor run without PAD/Diagnostic Mode. The monitor completed cleanly with logging off and no observed acquisition or recording error. On 2026-09-27, one separate stationary, engine-off, PAD-off support check sent exactly one Mode 01 PID `00` request and verified that the DME advertises PIDs `0C`, `0D`, `0F`, and `11`. This does not establish plausible values or safe polling for those four signals. The temperature result does not verify longer duration, recording-enabled operation, or run-wide temperature extrema.

Signal definitions record measured/derived/unavailable category, provenance, confidence, verification, and expected/observed rates. The generic live profile loader checks unique IDs, supported types, exact address/offset/width types and bounds, safe request shapes, boolean flags, finite codecs, and positive finite expected rates before any socket client is constructed. The Supra template keeps all candidates disabled and omits vehicle addresses. Temperature values are limited to the dedicated one-shot reads and the single bounded monitor result; the four newly support-advertised signals do not yet have verified vehicle values. Live cycles include unavailable/disabled signals explicitly; after a live error, not-yet-polled signals are labeled halted without being requested.

The implemented Mode 01 subset is limited to PIDs `05`, `0C`, `0D`, `0F`, `11`, and `5C`. Their units and formulas are canonicalized during profile loading; a profile that supplies conflicting unit, width, offset, scale, signedness, or byte order is rejected before network I/O. PIDs `05` and `5C` and their one-byte raw−40 °C decoding have been verified with one-shot reads and one bounded 300-second monitor on this test vehicle. PIDs `0C`, `0D`, `0F`, and `11` have vehicle-verified support bits but no vehicle-verified value responses. Longer or recording-enabled monitoring remains unverified. Other Mode 01 PIDs remain unavailable until a decoder and tests are added.
