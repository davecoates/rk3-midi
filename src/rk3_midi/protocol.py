"""Pure caiaq EP1 packet parsing; this module has no USB or MIDI dependencies."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum

VID_NATIVE_INSTRUMENTS = 0x17CC
PID_RIG_KONTROL_3 = 0x1940
EP_COMMAND_OUT = 0x01
EP_COMMAND_IN = 0x81
EP1_BUFFER_SIZE = 64
RK3_ANALOG_INPUTS = 3
RK3_DIGITAL_INPUTS = 9


class Command(IntEnum):
    GET_DEVICE_INFO = 0x01
    READ_ERP = 0x02
    READ_ANALOG = 0x03
    READ_IO = 0x04
    WRITE_IO = 0x05
    MIDI_READ = 0x06
    MIDI_WRITE = 0x07
    AUDIO_PARAMS = 0x09
    AUTO_MSG = 0x0B
    DIMM_LEDS = 0x0C


@dataclass(frozen=True)
class DeviceInfo:
    firmware_version: int
    hardware_subtype: int
    num_erp: int
    num_analog_in: int
    num_digital_in: int
    num_digital_out: int
    num_analog_audio_out: int
    num_analog_audio_in: int
    num_digital_audio_out: int
    num_digital_audio_in: int
    num_midi_out: int
    num_midi_in: int
    data_alignment: int


@dataclass(frozen=True)
class DigitalReport:
    """Digital payload and its least-significant-bit-first state bits."""

    payload: bytes
    bits: tuple[bool, ...]


@dataclass(frozen=True)
class AnalogReport:
    """Big-endian 16-bit analog values in firmware axis order."""

    values: tuple[int, ...]


@dataclass(frozen=True)
class UnknownReport:
    command: int
    payload: bytes


ParsedPacket = DeviceInfo | DigitalReport | AnalogReport | UnknownReport


def command_packet(command: Command | int, payload: bytes = b"") -> bytes:
    packet = bytes((int(command),)) + payload
    if len(packet) > EP1_BUFFER_SIZE:
        raise ValueError("EP1 command exceeds 64 bytes")
    return packet


def auto_message_command(digital: int = 1, analog: int = 10, erp: int = 0) -> bytes:
    """Enable RK3 automatic digital/analog reports as Linux input.c does."""

    for value in (digital, analog, erp):
        if not 0 <= value <= 0xFF:
            raise ValueError("AUTO_MSG values must be bytes")
    return command_packet(Command.AUTO_MSG, bytes((digital, analog, erp)))


def parse_packet(packet: bytes) -> ParsedPacket:
    """Parse one complete inbound EP1 packet without retaining any state."""

    if not packet:
        raise ValueError("empty EP1 packet")

    command = packet[0]
    payload = packet[1:]

    if command == Command.GET_DEVICE_INFO:
        if len(payload) < 14:
            raise ValueError(f"short GET_DEVICE_INFO payload: {len(payload)} < 14")
        return DeviceInfo(*struct.unpack_from("<H12B", payload))

    if command == Command.READ_IO:
        bits = tuple(
            bool(payload[index // 8] & (1 << (index % 8)))
            for index in range(min(RK3_DIGITAL_INPUTS, len(payload) * 8))
        )
        return DigitalReport(payload=payload, bits=bits)

    if command == Command.READ_ANALOG:
        meaningful_length = RK3_ANALOG_INPUTS * 2
        if len(payload) < meaningful_length:
            raise ValueError(
                f"short READ_ANALOG payload: {len(payload)} < {meaningful_length}"
            )
        values = tuple(
            int.from_bytes(payload[offset : offset + 2], "big")
            for offset in range(0, meaningful_length, 2)
        )
        return AnalogReport(values=values)

    return UnknownReport(command=command, payload=payload)


def describe_packet(packet: bytes) -> str:
    """Return a compact annotation while preserving raw bytes in dump output."""

    try:
        parsed = parse_packet(packet)
    except ValueError as error:
        return f"malformed: {error}"

    if isinstance(parsed, DeviceInfo):
        return (
            f"device-info fw={parsed.firmware_version} "
            f"digital-in={parsed.num_digital_in} analog-in={parsed.num_analog_in}"
        )
    if isinstance(parsed, DigitalReport):
        set_bits = [str(index) for index, value in enumerate(parsed.bits) if value]
        return "digital set-bits=" + (",".join(set_bits) if set_bits else "none")
    if isinstance(parsed, AnalogReport):
        return "analog " + " ".join(
            f"axis{index}={value}" for index, value in enumerate(parsed.values)
        )
    return f"command=0x{parsed.command:02x} payload={len(parsed.payload)}B"
