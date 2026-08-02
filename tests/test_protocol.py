import json
from pathlib import Path

import pytest

from rk3_midi.protocol import (
    AnalogReport,
    DeviceInfo,
    DigitalReport,
    auto_message_command,
    parse_packet,
)


def test_linux_rk3_auto_message_handshake() -> None:
    assert auto_message_command() == bytes.fromhex("0b 01 0a 00")


def test_parse_device_info_wire_endianness() -> None:
    packet = bytes.fromhex("01 34 12 01 00 03 02 04 02 02 00 00 01 01 02")
    parsed = parse_packet(packet)
    assert isinstance(parsed, DeviceInfo)
    assert parsed.firmware_version == 0x1234
    assert parsed.num_analog_in == 3
    assert parsed.data_alignment == 2


def test_parse_digital_bits_lsb_first() -> None:
    parsed = parse_packet(bytes.fromhex("04 11 01"))
    assert isinstance(parsed, DigitalReport)
    assert [index for index, set_ in enumerate(parsed.bits) if set_] == [0, 4, 8]


def test_parse_three_big_endian_analog_axes() -> None:
    parsed = parse_packet(bytes.fromhex("03 00 01 01 00 03 ff"))
    assert parsed == AnalogReport(values=(1, 256, 1023))


def test_parse_real_rk3_padded_analog_report() -> None:
    packet = bytes.fromhex(
        "03 00 00 00 00 01 8c 04 00 00 00 00 00 00 00 00 00 "
        "00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00"
    )
    assert parse_packet(packet) == AnalogReport(values=(0, 0, 396))


def test_reject_short_analog_payload() -> None:
    with pytest.raises(ValueError, match="short READ_ANALOG"):
        parse_packet(bytes.fromhex("03 00 00"))


def test_real_phase1_control_capture() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "phase1_packets.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))

    for button in fixture["buttons"]:
        pressed = parse_packet(bytes.fromhex(button["pressed"]))
        released = parse_packet(bytes.fromhex(button["released"]))
        assert isinstance(pressed, DigitalReport)
        assert isinstance(released, DigitalReport)
        assert [index for index, value in enumerate(pressed.bits) if value] == [
            button["bit"]
        ]
        assert not any(released.bits)

    treadle = fixture["treadle"]
    minimum = parse_packet(bytes.fromhex(treadle["minimum"]))
    maximum = parse_packet(bytes.fromhex(treadle["maximum"]))
    overtravel = parse_packet(bytes.fromhex(treadle["toe_switch_overtravel"]))
    assert isinstance(minimum, AnalogReport)
    assert isinstance(maximum, AnalogReport)
    assert isinstance(overtravel, AnalogReport)
    assert minimum.values[treadle["axis"]] == treadle["observed_min"]
    assert maximum.values[treadle["axis"]] == treadle["observed_max"]
    assert overtravel.values[treadle["axis"]] == treadle["observed_overtravel"]
