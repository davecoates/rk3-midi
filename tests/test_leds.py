from rk3_midi.leds import OUTPUT_STATE_SIZE, RK3Lights
from rk3_midi.protocol import Command


def test_led_packet_preserves_display_and_maps_switch_leds() -> None:
    lights = RK3Lights()
    assert lights.set("p1", True)
    assert lights.set("p8", True)
    assert lights.set("pedal", True)
    packet = lights.packet()

    assert len(packet) == OUTPUT_STATE_SIZE + 1
    assert packet[0] == Command.WRITE_IO
    assert packet[1:5] == bytes((0x00, 0x40, 0x40, 0x00))
    assert packet[5] == 0x18
    assert packet[6] == 0x01


def test_setting_led_is_idempotent() -> None:
    lights = RK3Lights()
    assert not lights.enabled("pedal")
    assert lights.set("pedal", True)
    assert lights.enabled("pedal")
    assert not lights.set("pedal", True)
    assert lights.set("pedal", False)
