# rk3-midi

Windows userspace support for using a Native Instruments Rig Kontrol 3 as a MIDI
control surface. Audio is intentionally out of scope.

The finished signal path is:

```text
Rig Kontrol 3 -> WinUSB -> rk3-midi -> loopMIDI -> Neural DSP / DAW
```

The tool includes hardware discovery and packet capture, the configurable
USB-to-MIDI relay, pedal calibration/filtering, reconnect handling, standalone
Windows executables, and automatic startup at login. See
[PROTOCOL.md](docs/PROTOCOL.md) for the hardware-confirmed protocol.

## WinUSB setup

The original Native Instruments driver is version 3.1.0.761 (`rig3usb.inf`),
which Windows reports as blocked by application-control policy on this machine.
In Zadig:

1. Enable **Options > List All Devices**.
2. Select **RigKontrol3**, USB ID `17CC:1940`.
3. Choose **WinUSB** and select **Replace Driver**.
4. Unplug/replug the RK3.

Bind the whole RigKontrol3 device/interface 0. This unit has no separate `MI_00`
control child. Do not select another Native Instruments device, a USB hub, or an
endpoint. WinUSB handles the required bulk transfers; libusbK is unnecessary.

The tool installs no kernel driver and requires no change to Secure Boot, HVCI,
or driver-signature enforcement.

## loopMIDI setup

1. Install [Tobias Erichsen loopMIDI](https://www.tobias-erichsen.de/software/loopmidi.html).
2. Create a virtual port. On this machine, MIDI senders see the cable as
   `loopMIDI Port 2`, while MIDI receivers see it as `loopMIDI Port 1`.
3. In loopMIDI's tray menu, enable autostart.

loopMIDI ports are per-user and exist only while loopMIDI is running. rk3-midi
uses the unique query `loopMIDI` by default and safely retries if loopMIDI starts
after the relay.

## Install the packaged background app

Extract `rk3-midi-0.2.0-windows-x64.zip`, open PowerShell in the extracted
directory, and run:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\install.ps1
```

This per-user installation does not require administrator privileges. It:

- copies both executables to `%LOCALAPPDATA%\Programs\rk3-midi`;
- creates `%APPDATA%\rk3-midi\config.toml` without overwriting an existing file;
- registers a limited interactive-user Scheduled Task named `rk3-midi`;
- starts the windowless relay immediately and at every login;
- leaves WinUSB and loopMIDI unchanged.

A Scheduled Task is preferred over a Windows service because loopMIDI and the
plugin run in the signed-in user's MIDI session. The packaged application is
currently unsigned, so Windows may show a first-run reputation warning; it is a
userspace executable, not an unsigned driver.

Verify installation:

```powershell
Get-ScheduledTask -TaskName rk3-midi
& "$env:LOCALAPPDATA\Programs\rk3-midi\rk3-midi.exe" list-ports
Get-Content "$env:LOCALAPPDATA\rk3-midi\rk3-midi.log" -Tail 20
```

## Neural DSP setup

### Standalone application

1. Confirm the `rk3-midi` Scheduled Task and loopMIDI are running.
2. Open the Neural DSP standalone application's settings/audio settings.
3. Under **MIDI Input Devices**, enable `loopMIDI Port 1`, or your configured
   loopMIDI port.
4. Right-click the wah/whammy pedal and select **Enable MIDI Learn**.
5. Rock the RK3 treadle through its ordinary travel. It sends CC11 from 0 to 127.
6. Right-click the parameter again and select **Disable MIDI Learn**.
7. For a stomp, right-click its on/off control, enable MIDI Learn, and press the
   desired RK3 switch. P1..P9 default to CC20..CC28.

Neural DSP records mappings in its MIDI Mapping window, accessible from the MIDI
port icon in supported plugins. These steps follow Neural DSP's current
[official MIDI guide](https://neuraldsp.com/getting-started/controlling-plugins-with-midi).

### Plugin inside a DAW

Enable the receiver-side loopMIDI port (`loopMIDI Port 1` on this machine) as a
MIDI input in the DAW and route that MIDI to the
track/plugin instance according to the DAW's routing model. Then use the same
Neural DSP MIDI Learn steps. The rk3-midi side is identical for standalone and
plugin use.

## Configuration

The installer creates `%APPDATA%\rk3-midi\config.toml` from
[config.example.toml](config.example.toml). Defaults are channel 1:

- P1..P9 -> CC20..CC28
- built-in treadle -> CC11
- rear EXP1 -> CC12
- rear EXP2 -> CC13

Each button has its own MIDI channel, number, debounce time, and mode:

- `momentary`: CC 127 while pressed and CC 0 on release;
- `toggle`: alternate CC 127/0 on presses;
- `note`: note-on/velocity 127 and note-off/velocity 0.

For note mode, `number` is the note number; otherwise it is the CC number. Pedals
support `linear`, `log`, and `exp` curves, endpoint deadzones, time-based
smoothing, and raw ADC jitter rejection. Only changed 7-bit values are emitted.

After editing the installed config, restart the task:

```powershell
Stop-ScheduledTask -TaskName rk3-midi
Start-ScheduledTask -TaskName rk3-midi
```

## Calibration

Only one process can claim the RK3 interface. Stop the background task, calibrate,
then restart it:

```powershell
Stop-ScheduledTask -TaskName rk3-midi
& "$env:LOCALAPPDATA\Programs\rk3-midi\rk3-midi.exe" calibrate treadle --seconds 10 --verbose
Start-ScheduledTask -TaskName rk3-midi
```

Use `exp1` or `exp2` instead of `treadle` for the rear jacks. Sweep the selected
pedal repeatedly. For the built-in treadle, do not press the P9 toe switch: its
mechanical overtravel would compress the ordinary wah range. Measurements are
stored in `calibration.json` beside the config, leaving mappings untouched.

## CLI and development

The installed CLI supports:

```powershell
& "$env:LOCALAPPDATA\Programs\rk3-midi\rk3-midi.exe" run --verbose
& "$env:LOCALAPPDATA\Programs\rk3-midi\rk3-midi.exe" dump
& "$env:LOCALAPPDATA\Programs\rk3-midi\rk3-midi.exe" calibrate treadle
& "$env:LOCALAPPDATA\Programs\rk3-midi\rk3-midi.exe" list-ports
```

For source development:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
.\.venv\Scripts\python -m pytest -q
.\scripts\build-release.ps1
```

Logs are written to `%LOCALAPPDATA%\rk3-midi\rk3-midi.log`, rotated at 1 MiB
with three backups by default. USB and MIDI reconnect use bounded exponential
backoff across unplug/replug and sleep/resume.

## Uninstall

From the extracted release directory:

```powershell
.\uninstall.ps1
```

This preserves `%APPDATA%\rk3-midi`. Add `-RemoveUserData` only if you also want
to delete mappings and calibration. Uninstalling rk3-midi does not change WinUSB
or loopMIDI.

## Restore the Native Instruments driver

1. Stop or uninstall rk3-midi.
2. Open **Device Manager**, find **RigKontrol3**, and choose **Update driver**.
3. Select **Browse my computer for drivers** -> **Let me pick from a list**.
4. Choose the Native Instruments **Rig Kontrol 3** driver instead of WinUSB. On
   this machine it is staged as `oem70.inf`, original name `rig3usb.inf`, version
   3.1.0.761.
5. Unplug/replug the RK3.

The legacy driver may again be blocked by Windows application control/HVCI. This
project does not recommend disabling Secure Boot, HVCI, or signature enforcement
to recover RK3 audio.

## Troubleshooting

- **No loopMIDI port:** start loopMIDI, recreate/activate its port, and enable its
  autostart option. The relay reconnects automatically.
- **Neural DSP sees no MIDI:** enable the loopMIDI port under MIDI Input Devices.
  Do not look for `RigKontrol3`; WinUSB is not a MIDI-class device.
- **RK3 access denied:** another relay, dump, or calibration process owns
  interface 0. Stop the Scheduled Task before running diagnostics.
- **View logs:** inspect `%LOCALAPPDATA%\rk3-midi\rk3-midi.log` and its backups.
