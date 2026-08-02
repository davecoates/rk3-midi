from rk3_midi.protocol import Command
from rk3_midi.service import initialize_device


class FakeUSB:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.reads = [
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
        bytes((Command.GET_DEVICE_INFO,)),
        bytes.fromhex("0b010a00"),
    ]
