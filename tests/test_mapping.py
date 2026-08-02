from dataclasses import replace

from rk3_midi.config import defaults
from rk3_midi.controls import ButtonEvent, PedalEvent
from rk3_midi.mapping import MappingEngine


def test_default_momentary_and_pedal_messages() -> None:
    mapping = MappingEngine(defaults())
    assert mapping.handle(ButtonEvent("p1", True))[0].data == (0xB0, 20, 127)
    assert mapping.handle(ButtonEvent("p1", False))[0].data == (0xB0, 20, 0)
    assert mapping.handle(PedalEvent("treadle", 200, 63))[0].data == (0xB0, 11, 63)


def test_toggle_ignores_release_and_preserves_latch() -> None:
    config = defaults()
    buttons = dict(config.buttons)
    buttons["p2"] = replace(buttons["p2"], mode="toggle")
    mapping = MappingEngine(replace(config, buttons=buttons))
    assert mapping.handle(ButtonEvent("p2", True))[0].data == (0xB0, 21, 127)
    assert mapping.handle(ButtonEvent("p2", False)) == []
    assert mapping.handle(ButtonEvent("p2", True))[0].data == (0xB0, 21, 0)


def test_note_mode_and_disconnect_release() -> None:
    config = defaults()
    buttons = dict(config.buttons)
    buttons["p3"] = replace(buttons["p3"], mode="note", channel=2, number=60)
    mapping = MappingEngine(replace(config, buttons=buttons))
    assert mapping.handle(ButtonEvent("p3", True))[0].data == (0x91, 60, 127)
    assert mapping.release_active()[0].data == (0x81, 60, 0)
