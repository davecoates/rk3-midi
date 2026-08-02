"""Stateful conversion of parsed RK3 reports into debounced control values."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .config import AppConfig, PedalConfig
from .protocol import AnalogReport, DigitalReport, ParsedPacket

LABEL_TO_BIT = {
    f"p{label}": bit for label, bit in enumerate((4, 5, 6, 7, 0, 1, 2, 3, 8), 1)
}
AXIS_NAMES = ("exp1", "exp2", "treadle")


@dataclass(frozen=True)
class ButtonEvent:
    name: str
    pressed: bool


@dataclass(frozen=True)
class PedalEvent:
    name: str
    raw: int
    value: int


ControlEvent = ButtonEvent | PedalEvent


class DigitalDebouncer:
    def __init__(self, debounce_ms: dict[str, float]) -> None:
        self._debounce = {name: value / 1000.0 for name, value in debounce_ms.items()}
        self._stable: dict[str, bool] = {}
        self._pending: dict[str, tuple[bool, float]] = {}

    def seed(self, bits: tuple[bool, ...]) -> None:
        self._stable = {
            name: bits[bit] if bit < len(bits) else False
            for name, bit in LABEL_TO_BIT.items()
        }
        self._pending.clear()

    def feed(self, bits: tuple[bool, ...], timestamp: float) -> None:
        if not self._stable:
            self.seed(bits)
            return
        for name, bit in LABEL_TO_BIT.items():
            observed = bits[bit] if bit < len(bits) else False
            if observed == self._stable[name]:
                self._pending.pop(name, None)
            else:
                pending = self._pending.get(name)
                if pending is None or pending[0] != observed:
                    self._pending[name] = (observed, timestamp)

    def drain(self, timestamp: float) -> list[ButtonEvent]:
        events: list[ButtonEvent] = []
        for name, (state, since) in tuple(self._pending.items()):
            if timestamp - since < self._debounce[name]:
                continue
            self._stable[name] = state
            del self._pending[name]
            events.append(ButtonEvent(name=name, pressed=state))
        return events


class PedalFilter:
    def __init__(self, name: str, config: PedalConfig) -> None:
        self.name = name
        self.config = config
        self._accepted_raw: int | None = None
        self._filtered: float | None = None
        self._timestamp: float | None = None
        self._last_value: int | None = None

    def _normalize(self, raw: int) -> float:
        span = self.config.maximum - self.config.minimum
        value = min(1.0, max(0.0, (raw - self.config.minimum) / span))
        deadzone = self.config.deadzone
        if value <= deadzone:
            value = 0.0
        elif value >= 1.0 - deadzone:
            value = 1.0
        elif deadzone:
            value = (value - deadzone) / (1.0 - 2.0 * deadzone)

        amount = self.config.curve_amount
        if self.config.curve == "log":
            value = math.log1p(amount * value) / math.log1p(amount)
        elif self.config.curve == "exp":
            value = math.expm1(amount * value) / math.expm1(amount)
        return value

    def feed(self, raw: int, timestamp: float) -> PedalEvent | None:
        if self._accepted_raw is None:
            self._accepted_raw = raw
            self._filtered = self._normalize(raw)
            self._timestamp = timestamp
            self._last_value = round(self._filtered * 127)
            return None

        if abs(raw - self._accepted_raw) <= self.config.jitter_raw:
            self._timestamp = timestamp
            return None
        self._accepted_raw = raw
        target = self._normalize(raw)
        previous_timestamp = self._timestamp
        elapsed = (
            max(0.0, timestamp - previous_timestamp)
            if previous_timestamp is not None
            else 0.0
        )
        self._timestamp = timestamp
        if self.config.smoothing_ms <= 0:
            self._filtered = target
        else:
            tau = self.config.smoothing_ms / 1000.0
            alpha = 1.0 - math.exp(-elapsed / tau) if elapsed else 0.0
            self._filtered = (self._filtered or 0.0) + alpha * (
                target - (self._filtered or 0.0)
            )

        value = round((self._filtered or 0.0) * 127)
        if value == self._last_value:
            return None
        self._last_value = value
        return PedalEvent(name=self.name, raw=raw, value=value)


class ControlProcessor:
    def __init__(self, config: AppConfig) -> None:
        self._digital = DigitalDebouncer(
            {name: button.debounce_ms for name, button in config.buttons.items()}
        )
        # RK3 AUTO_MSG does not provide an initial digital snapshot and this
        # firmware stalls EP1 if READ_IO is queried directly. Released is the
        # safe seed: the first new press works, while a control held across a
        # reconnect cannot create a spurious press.
        self._digital.seed(tuple(False for _ in range(9)))
        self._pedals = {
            name: PedalFilter(name, config.pedals[name]) for name in AXIS_NAMES
        }

    def feed(self, packet: ParsedPacket, timestamp: float) -> list[ControlEvent]:
        events: list[ControlEvent] = []
        if isinstance(packet, DigitalReport):
            self._digital.feed(packet.bits, timestamp)
        elif isinstance(packet, AnalogReport):
            for name, raw in zip(AXIS_NAMES, packet.values, strict=True):
                event = self._pedals[name].feed(raw, timestamp)
                if event is not None:
                    events.append(event)
        events.extend(self._digital.drain(timestamp))
        return events

    def tick(self, timestamp: float) -> list[ButtonEvent]:
        return self._digital.drain(timestamp)
