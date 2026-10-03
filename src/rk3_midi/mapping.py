"""Physical control events to raw three-byte MIDI messages."""

from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig
from .controls import ButtonEvent, ControlEvent, PedalEvent


@dataclass(frozen=True)
class MidiMessage:
    data: tuple[int, int, int]
    description: str


class MappingEngine:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._toggles = {name: False for name in config.buttons}
        self._active = {name: False for name in config.buttons}

    def button_active(self, name: str) -> bool:
        button = self.config.buttons[name]
        return self._toggles[name] if button.mode == "toggle" else self._active[name]

    def set_toggle_state(self, name: str, enabled: bool) -> None:
        if self.config.buttons[name].mode == "toggle":
            self._toggles[name] = enabled

    def handle(self, event: ControlEvent) -> list[MidiMessage]:
        if isinstance(event, PedalEvent):
            pedal = self.config.pedals[event.name]
            return [
                MidiMessage(
                    data=(0xB0 | (pedal.channel - 1), pedal.cc, event.value),
                    description=(
                        f"{event.name} raw={event.raw} -> ch{pedal.channel} "
                        f"CC{pedal.cc} {event.value}"
                    ),
                )
            ]

        button = self.config.buttons[event.name]
        if button.mode == "toggle":
            if not event.pressed:
                return []
            self._toggles[event.name] = not self._toggles[event.name]
            value = 127 if self._toggles[event.name] else 0
            return [
                MidiMessage(
                    data=(0xB0 | (button.channel - 1), button.number, value),
                    description=f"{event.name} toggle -> ch{button.channel} CC{button.number} {value}",
                )
            ]

        self._active[event.name] = event.pressed
        value = 127 if event.pressed else 0
        if button.mode == "note":
            status = (0x90 if event.pressed else 0x80) | (button.channel - 1)
            return [
                MidiMessage(
                    data=(status, button.number, value),
                    description=(
                        f"{event.name} -> ch{button.channel} note {button.number} "
                        f"{'on' if event.pressed else 'off'}"
                    ),
                )
            ]
        return [
            MidiMessage(
                data=(0xB0 | (button.channel - 1), button.number, value),
                description=(
                    f"{event.name} -> ch{button.channel} CC{button.number} {value}"
                ),
            )
        ]

    def release_active(self) -> list[MidiMessage]:
        messages: list[MidiMessage] = []
        for name, active in self._active.items():
            if active:
                messages.extend(self.handle(ButtonEvent(name=name, pressed=False)))
        return messages
