# Rig Kontrol 3 control protocol

Status: Phase 1 hardware capture complete for all nine switches and the built-in
treadle on RK3 firmware 10. Rear EXP jack ordering is source-derived and the
disconnected zero values were observed, but those jacks were not swept with
external pedals during this capture.

Windows identifies the connected unit as one vendor-specific device
(`USB\\VID_17CC&PID_1940\\...`, class/subclass/protocol `ff/ff/00`) with no
`MI_00` child interface. Before WinUSB replacement, its Native Instruments
3.1.0.761 driver was blocked by application-control policy (PnP problem 39).
After replacement, the WinUSB device starts normally. This supports the
one-interface model in the Linux and macOS implementations.

## USB transport

- Device: Native Instruments `VID 0x17cc`, Rig Kontrol 3 `PID 0x1940`.
- Live descriptor: USB 2.00, one configuration, one vendor-specific interface.
- Interface 0 alternate 0: bulk `0x01 OUT`, bulk `0x81 IN`.
- Interface 0 alternate 1: the same bulk endpoints plus isochronous `0x82 IN`
  and `0x06 OUT`; every endpoint advertises max packet size 512 bytes.
- The dumper selects configuration 1, interface 0, alternate setting 1 to mirror
  the Linux driver.
- caiaq commands are bulk transfers: endpoint `0x01` OUT and endpoint `0x81` IN,
  with a maximum command buffer of 64 bytes.
- Interface 0 alternate setting 1 also exposes isochronous audio endpoints. Audio
  is not opened or configured by this project.

The endpoint topology is now confirmed directly by `rk3-midi inspect` on this
unit and agrees with Linux and `rk3-coreaudio`.

## Initialization

Each EP1 message starts with a one-byte command. The minimum input startup is:

1. Send `01` (`EP1_CMD_GET_DEVICE_INFO`) to endpoint `0x01`.
2. Read the `01 ...` device-info reply from endpoint `0x81`.
3. Send `0b 01 0a 00` (`EP1_CMD_AUTO_MSG`, digital 1, analog 10, ERP 0).
4. Continuously read endpoint `0x81`.

The `AUTO_MSG` values are the RK3-specific values in
`snd_usb_caiaq_input_init`. Omitting this command generally leaves the controls
silent.

Firmware 10 does not emit an initial digital snapshot after `AUTO_MSG`. Although
`READ_IO` exists in the caiaq command set, sending it directly to this RK3 stalled
EP1 and required a physical unplug/replug. The relay must not query it. Instead,
it seeds all switches as released on connection and accepts subsequent edges.

## Inbound packet layout

| Command | Meaning | Confirmed payload layout |
| --- | --- | --- |
| `0x01` | Device info | 14 bytes: little-endian firmware `u16`, then 12 one-byte capability fields |
| `0x03` | Analog inputs | Big-endian `u16` values, two bytes per axis |
| `0x04` | Digital inputs | Bit array, least-significant bit first in each payload byte |

Packet byte 0 is the command, so payload offset 0 below is absolute packet byte 1.
The device returns 33-byte analog reports. Device info advertises three analog
inputs, so only payload bytes 0..5 are meaningful; the remaining 26 bytes are
padding/stale buffer contents and must be ignored. Digital reports receive the
same treatment after the advertised first nine input bits.

The live `GET_DEVICE_INFO` reply is:

```text
01 0a 00 06 00 03 09 29 02 02 00 00 01 01 02
```

It reports firmware 10, three analog inputs, nine digital inputs, and data
alignment 2.

## Control map

The labelled Windows capture confirmed physical P1..P9 map to firmware bits
4, 5, 6, 7, 0, 1, 2, 3, 8 respectively. The built-in treadle was confirmed as
axis 2. Linux and the macOS port identify axes 0 and 1 as rear EXP1 and EXP2.

| Physical control | Packet field | Status / observed range |
| --- | --- | --- |
| P1 | packet byte 1 bit 4 | confirmed; press `04 10 ...`, release `04 00 ...` |
| P2 | packet byte 1 bit 5 | confirmed; press `04 20 ...`, release `04 00 ...` |
| P3 | packet byte 1 bit 6 | confirmed; press `04 40 ...`, release `04 00 ...` |
| P4 | packet byte 1 bit 7 | confirmed; press `04 80 ...`, release `04 00 ...` |
| P5 | packet byte 1 bit 0 | confirmed; press `04 01 ...`, release `04 00 ...` |
| P6 | packet byte 1 bit 1 | confirmed; press `04 02 ...`, release `04 00 ...` |
| P7 | packet byte 1 bit 2 | confirmed; press `04 04 ...`, release `04 00 ...` |
| P8 | packet byte 1 bit 3 | confirmed; press `04 08 ...`, release `04 00 ...` |
| P9 (treadle toe switch) | packet byte 2 bit 0 | confirmed; press `04 00 01 ...`, release `04 00 00 ...` |
| Rear EXP1 | packet bytes 1..2, big-endian `u16` (axis 0) | source mapping; disconnected value 0 |
| Rear EXP2 | packet bytes 3..4, big-endian `u16` (axis 1) | source mapping; disconnected value 0 |
| Built-in treadle | packet bytes 5..6, big-endian `u16` (axis 2) | confirmed; normal sweep 25..478 |

The Linux logical range is 0..1024 for all three axes. This unit's ordinary
heel-to-toe sweep was 25..478. Pressing the P9 toe switch mechanically pushed
the same axis into overtravel up to 590. Calibration should therefore use the
ordinary sweep and clamp the overtravel, otherwise the reachable CC range would
be compressed during normal wah use. `rk3-coreaudio` observed roughly 40..270
on another unit, so per-device calibration remains mandatory.

Digital reports observed during the capture were eight bytes long, while analog
reports were 33 bytes long. Both include unrelated/stale trailing bytes; parsing
is bounded by device-info's nine digital inputs and three analog inputs.

The complete raw capture is `captures/rk3-controls.jsonl`. A compact, labelled
subset is committed as `tests/fixtures/phase1_packets.json` and is exercised by
the pure parser tests.

## Capture procedure

After binding the RK3 to WinUSB and installing this project:

```powershell
rk3-midi inspect
rk3-midi dump --output captures/rk3-controls.jsonl
```

Start from all switches released. Press and release P1 through P9 one at a time,
with a short pause between each. Then sweep the built-in treadle slowly from heel
to toe and back. Stop with Ctrl-C. Do not connect or move the rear expression
pedals during this first capture; that keeps attribution unambiguous.

The JSONL capture preserves every raw packet, a monotonic timestamp, and a UTC
timestamp. The packet map and parser fixtures above were derived from this file.
