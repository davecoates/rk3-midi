from dataclasses import replace

from rk3_midi.config import defaults
from rk3_midi.controls import ButtonEvent, ControlProcessor, PedalEvent
from rk3_midi.protocol import parse_packet

RELEASED = parse_packet(bytes.fromhex("0400000000018b04"))
P1_DOWN = parse_packet(bytes.fromhex("0410000000018b04"))
HEEL = parse_packet(
    bytes.fromhex("030000000000190400000000000000000000000000000000000000000000000000")
)
TOE = parse_packet(
    bytes.fromhex("030000000001de0400000000000000000000000000000000000000000000000000")
)


def test_delayed_debounce_works_without_repeat_digital_packet() -> None:
    processor = ControlProcessor(defaults())
    assert processor.feed(P1_DOWN, 1.0) == []
    assert processor.tick(1.019) == []
    assert processor.tick(1.021) == [ButtonEvent(name="p1", pressed=True)]


def test_pedal_seeds_silently_then_emits_only_change() -> None:
    config = defaults()
    pedals = dict(config.pedals)
    pedals["treadle"] = replace(
        pedals["treadle"], smoothing_ms=0, jitter_raw=0, deadzone=0
    )
    processor = ControlProcessor(replace(config, pedals=pedals))
    assert processor.feed(HEEL, 0.0) == []
    assert processor.feed(TOE, 0.01) == [PedalEvent(name="treadle", raw=478, value=127)]
    assert processor.feed(TOE, 0.02) == []


def test_stationary_raw_jitter_is_suppressed() -> None:
    processor = ControlProcessor(defaults())
    assert processor.feed(HEEL, 0.0) == []
    for index, raw in enumerate((26, 24, 27, 25, 26), 1):
        packet = parse_packet(
            bytes.fromhex(
                f"0300000000{raw:04x}040000000000000000000000000000000000000000000000000000"
            )
        )
        assert processor.feed(packet, index * 0.01) == []
