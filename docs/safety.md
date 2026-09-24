# Safety and vehicle testing

## Hard prohibition

The application must remain read-only. Never code or flash ECUs, change configuration/calibration, clear faults, execute routines/actuators, perform security access, reset modules, or use download/upload services. No raw-payload CLI or client send surface is provided. `SafetyPolicy` allows only SAE Mode 01, Mode 09, UDS ReadDataByIdentifier (0x22), and its internal TesterPresent form. Session control is denied by default. HSFZ live reads require explicit verified profile status and explicit tester/target addresses; never copy an address from another vehicle or protocol example as a Supra value.

## Safe empirical procedure

1. Start with the vehicle parked outdoors, parking brake set, transmission in Park (or neutral for manual), wheels chocked, and engine off. Keep a second person available; do not test while driving.
2. Confirm the adapter and host OS network interface details before connecting; avoid changing vehicle state or network configuration based on guessed addresses.
3. Run only `discover` first. Its HSFZ UDP identification request and DoIP identification broadcast are bounded and contain no diagnostic requests. Record adapter, interface, vehicle state, timestamp, and captures.
4. Do not activate live `run` until routing and every request are reviewed against authoritative documentation and empirically shown to be read-only. Begin with one known standard read request, low rate, and stop on unexpected responses, errors, or vehicle warnings. Any transport, protocol, negative-response, or decoder error halts all later requests. Inspect the cause before starting a fresh run; in-process resume is not supported.
5. Check that data remains plausible while stationary. End the session, disconnect cleanly, and inspect logs before increasing scope or rate.

This is a conservative engineering checklist, not a substitute for Toyota/BMW service instructions. Do not probe unknown identifiers or try write-capable services.

Scapy's HSFZ parser documents short control `0x12` alive frames with source/target and a long identification-string variant. During a diagnostic request, this app audits and skips either frame without replying. Whether a particular gateway expects any keep-alive response remains unknown until vehicle testing.
