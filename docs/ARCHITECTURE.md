# Phase 2 architecture

The implementation remains Python 3.12. The RK3 reports analog state at an effective
interval configured as 10 ms, so USB/MIDI scheduling dominates neither latency
nor pedal feel here. Rust would improve single-binary distribution and type-level
ownership, but not enough to justify slower protocol iteration before the Windows
behavior is stable. PyInstaller can package the proven Python implementation in
Phase 3; a Rust port remains possible because parsing is isolated.

## Data flow

```text
WinUSB interface 0 / EP 0x81
  -> USB reader and reconnect supervisor
  -> pure packet parser
  -> timestamped physical-control events
  -> debounce / calibration / curve / smoothing state
  -> mapping state (momentary, toggle, note)
  -> python-rtmidi output selected by configured name
```

## Module boundaries

- `protocol.py`: constants plus pure `bytes -> dataclass` parsing. It knows no
  USB, MIDI, configuration, clocks, or mutable state. Real capture fixtures test it.
- `usb_device.py`: descriptor validation, interface claim, initialization, reads,
  timeout handling, and transport errors. A supervisor above it will own reconnect.
- `controls.py`: delayed switch debounce plus calibration clamp, deadzones,
  response curves, time-based smoothing, and raw jitter rejection. It emits only
  changed 7-bit values.
- `mapping.py`: per-control MIDI channel/CC/note modes and toggle state.
- `midi_output.py`: loopMIDI discovery and output only; no protocol logic.
- `config.py`: typed TOML defaults, validation, and separate calibration storage.
- `service.py`: lifecycle, reconnect/backoff, suspend/resume behavior, and rotating
  logging.
- `cli.py`: thin command dispatch for `run`, `dump`, `calibrate`, and `list-ports`.

The RK3 does not provide an initial digital report after `AUTO_MSG`, and firmware
10 stalls EP1 when queried with a direct `READ_IO`. The processor therefore seeds
all switches as released on connection. This accepts the first new press,
suppresses a release from a control held across reconnect, resets smoothing and
physical edge state, and preserves configured toggle latches.

## Packaging direction

Prefer a per-user Scheduled Task triggered at logon, running a windowless packaged
executable with restart-on-failure. It has simpler permissions and MIDI-session
access than a Windows service and does not require a tray UI merely to remain
resident. A tray process is worthwhile only if live status/configuration controls
become a real requirement.
