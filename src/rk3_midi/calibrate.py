"""Interactive raw min/max calibration for one expression input."""

from __future__ import annotations

import time
from pathlib import Path

from .config import PEDAL_NAMES, default_calibration_path, save_calibration
from .protocol import AnalogReport, parse_packet
from .service import initialize_device
from .usb_device import RK3USB

AXIS_BY_NAME = {name: index for index, name in enumerate(PEDAL_NAMES)}


def calibrate(
    name: str,
    seconds: float,
    config_path: Path | None = None,
    verbose: bool = False,
) -> tuple[int, int, Path]:
    if name not in AXIS_BY_NAME:
        raise ValueError(f"unknown pedal {name}")
    if seconds <= 0:
        raise ValueError("calibration duration must be positive")
    axis = AXIS_BY_NAME[name]
    if name == "treadle":
        print(
            "Sweep the treadle through its ordinary heel/toe travel repeatedly. "
            "Do not press the P9 toe switch."
        )
    else:
        print(
            f"Sweep the pedal connected to {name.upper()} repeatedly through its full travel."
        )
    print(f"Capturing for {seconds:g} seconds...")

    minimum = 65535
    maximum = 0
    samples = 0
    with RK3USB.open(timeout_ms=50) as device:
        initialize_device(device)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            packet = device.read(timeout_ms=50)
            if packet is None:
                continue
            parsed = parse_packet(packet)
            if not isinstance(parsed, AnalogReport):
                continue
            raw = parsed.values[axis]
            minimum = min(minimum, raw)
            maximum = max(maximum, raw)
            samples += 1
            if verbose:
                print(
                    f"\r{name} raw={raw:4d} min={minimum:4d} max={maximum:4d}",
                    end="",
                    flush=True,
                )
    if verbose:
        print()
    if samples == 0 or maximum - minimum < 10:
        raise RuntimeError(
            f"insufficient {name} movement: samples={samples}, range={minimum}..{maximum}"
        )
    path = default_calibration_path(config_path)
    save_calibration(path, name, minimum, maximum)
    return minimum, maximum, path
