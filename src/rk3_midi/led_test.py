"""Interactive smoke test for the RK3 output LEDs."""

from __future__ import annotations

import time

from .leds import RK3Lights
from .usb_device import RK3USB


def test_led(name: str, seconds: float = 2.0) -> None:
    lights = RK3Lights()
    with RK3USB.open(timeout_ms=50) as device:
        lights.set(name, True)
        device.write(lights.packet())
        try:
            time.sleep(seconds)
        finally:
            lights.set(name, False)
            device.write(lights.packet())
