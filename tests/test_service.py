from dataclasses import replace

from rk3_midi.config import defaults
from rk3_midi.controls import ButtonEvent
from rk3_midi.protocol import Command
from rk3_midi.service import RK3MidiService, initialize_device


class FakeUSB:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.reads = [
            bytes.fromhex("0b"),
            bytes.fromhex(
                "0300000000018c0400000000000000000000000000000000000000000000000000"
            ),
            bytes.fromhex("010a00060003092902020000010102"),
            bytes.fromhex("0b"),
        ]

    def write(self, packet: bytes) -> None:
        self.writes.append(packet)

    def read(self, timeout_ms: int | None = None) -> bytes | None:
        return self.reads.pop(0) if self.reads else None


def test_initialize_enables_auto_messages_and_requests_initial_switch_state() -> None:
    usb = FakeUSB()
    info = initialize_device(usb)  # type: ignore[arg-type]
    assert info.firmware_version == 10
    assert usb.writes == [
        bytes.fromhex("0b000000"),
        bytes((Command.GET_DEVICE_INFO,)),
        bytes.fromhex("0b010a00"),
    ]


def test_pedal_led_toggles_without_changing_momentary_midi_mode() -> None:
    usb = FakeUSB()
    service = RK3MidiService(defaults())
    press = ButtonEvent("p9", True)
    release = ButtonEvent("p9", False)

    assert service.mapping.handle(press)[0].data == (0xB0, 28, 127)
    service._update_light(usb, press)  # type: ignore[arg-type]
    assert usb.writes[-1][6] == 0x01

    assert service.mapping.handle(release)[0].data == (0xB0, 28, 0)
    service._update_light(usb, release)  # type: ignore[arg-type]
    assert len(usb.writes) == 1

    service.mapping.handle(press)
    service._update_light(usb, press)  # type: ignore[arg-type]
    assert usb.writes[-1][6] == 0x00


def test_grouped_toggle_updates_all_wah_leds_from_either_button() -> None:
    service = RK3MidiService(defaults())
    usb = FakeUSB()

    service.mapping.handle(ButtonEvent("p8", True))
    service._update_light(usb, ButtonEvent("p8", True))  # type: ignore[arg-type]
    assert service.lights.enabled("p8")
    assert service.lights.enabled("pedal")

    service.mapping.handle(ButtonEvent("p9", True))
    service._update_light(usb, ButtonEvent("p9", True))  # type: ignore[arg-type]
    assert not service.lights.enabled("p8")
    assert not service.lights.enabled("pedal")


def test_exclusive_led_group_selects_only_last_pressed_button() -> None:
    config = defaults()
    buttons = dict(config.buttons)
    for name in ("p1", "p2"):
        buttons[name] = replace(
            buttons[name], led_mode="exclusive", led_group="presets"
        )
    service = RK3MidiService(replace(config, buttons=buttons))
    usb = FakeUSB()

    service.mapping.handle(ButtonEvent("p1", True))
    service._update_light(usb, ButtonEvent("p1", True))  # type: ignore[arg-type]
    assert service.lights.enabled("p1")
    assert not service.lights.enabled("p2")

    service.mapping.handle(ButtonEvent("p2", True))
    service._update_light(usb, ButtonEvent("p2", True))  # type: ignore[arg-type]
    assert not service.lights.enabled("p1")
    assert service.lights.enabled("p2")
    assert service.lights.enabled("pedal") is False


def test_preset_resets_effect_led_and_toggle_latch_without_effect_midi() -> None:
    config = defaults()
    buttons = dict(config.buttons)
    buttons["p1"] = replace(buttons["p1"], preset_state={"p4": False})
    buttons["p3"] = replace(buttons["p3"], preset_state={"p4": True})
    buttons["p4"] = replace(buttons["p4"], mode="toggle")
    service = RK3MidiService(replace(config, buttons=buttons))
    usb = FakeUSB()

    assert service.mapping.handle(ButtonEvent("p3", True))[0].data == (0xB0, 22, 127)
    service._update_light(usb, ButtonEvent("p3", True))  # type: ignore[arg-type]
    assert service.lights.enabled("p4")
    assert service.mapping.button_active("p4")
    assert service.mapping.handle(ButtonEvent("p4", True))[0].data == (0xB0, 23, 0)
    service._update_light(usb, ButtonEvent("p4", True))  # type: ignore[arg-type]

    service.mapping.handle(ButtonEvent("p3", False))
    assert service.mapping.handle(ButtonEvent("p1", True))[0].data == (0xB0, 20, 127)
    service._update_light(usb, ButtonEvent("p1", True))  # type: ignore[arg-type]
    assert not service.lights.enabled("p4")
    assert not service.mapping.button_active("p4")
    assert service.mapping.handle(ButtonEvent("p4", True))[0].data == (0xB0, 23, 127)
