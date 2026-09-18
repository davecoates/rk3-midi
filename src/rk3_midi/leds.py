"""Pure construction of Rig Kontrol 3 LED/output packets."""

from __future__ import annotations

from dataclasses import dataclass, field

from .protocol import Command, command_packet

LED_NAMES = tuple(f"p{index}" for index in range(1, 9)) + ("pedal",)
# The caiaq table numbers the two physical rows in the opposite order from the
# RK3's P1..P8 labels. Live observations confirmed P4 lit P8 and P8 lit P4.
_PROTOCOL_LED = {
    "p1": 5,
    "p2": 6,
    "p3": 7,
    "p4": 8,
    "p5": 1,
    "p6": 2,
    "p7": 3,
    "p8": 4,
    "pedal": 9,
}
LED_BITS = {name: 31 + index for name, index in _PROTOCOL_LED.items()}
OUTPUT_STATE_SIZE = 63


def default_output_state() -> bytearray:
    # Match the Linux driver's RK3 startup display: two centred dashes ("--").
    state = bytearray(OUTPUT_STATE_SIZE)
    state[:4] = bytes((0x00, 0x40, 0x40, 0x00))
    return state


@dataclass
class RK3Lights:
    state: bytearray = field(default_factory=default_output_state)

    def set(self, name: str, enabled: bool) -> bool:
        if name not in LED_BITS:
            raise ValueError(f"unknown RK3 LED {name!r}")
        bit = LED_BITS[name]
        index, mask = divmod(bit, 8)
        old = self.state[index]
        if enabled:
            self.state[index] |= 1 << mask
        else:
            self.state[index] &= ~(1 << mask)
        return self.state[index] != old

    def enabled(self, name: str) -> bool:
        if name not in LED_BITS:
            raise ValueError(f"unknown RK3 LED {name!r}")
        bit = LED_BITS[name]
        index, mask = divmod(bit, 8)
        return bool(self.state[index] & (1 << mask))

    def packet(self) -> bytes:
        return command_packet(Command.WRITE_IO, bytes(self.state))
