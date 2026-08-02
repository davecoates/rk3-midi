"""Timestamped raw EP1 capture."""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import TextIO

from .protocol import Command, auto_message_command, command_packet, describe_packet
from .usb_device import RK3USB


def _emit(packet: bytes, started: float, capture: TextIO | None) -> None:
    elapsed = time.perf_counter() - started
    wall_time = datetime.now(UTC).isoformat(timespec="milliseconds")
    hex_data = packet.hex(" ")
    annotation = describe_packet(packet)
    print(f"{elapsed:12.6f}  {hex_data:<64}  {annotation}", flush=True)
    if capture is not None:
        capture.write(
            json.dumps(
                {
                    "elapsed_seconds": round(elapsed, 6),
                    "utc": wall_time,
                    "data_hex": packet.hex(),
                    "annotation": annotation,
                }
            )
            + "\n"
        )
        capture.flush()


def run_dump(output: Path | None = None, duration: float | None = None) -> None:
    capture: TextIO | None = None
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        capture = output.open("x", encoding="utf-8")

    started = time.perf_counter()
    try:
        with RK3USB.open() as device:
            print("claimed interface 0, selected alternate setting 1")
            print("sending GET_DEVICE_INFO: 01")
            device.write(command_packet(Command.GET_DEVICE_INFO))

            info_seen = False
            deadline = time.perf_counter() + 2.0
            while time.perf_counter() < deadline:
                packet = device.read()
                if packet is None:
                    continue
                _emit(packet, started, capture)
                if packet[0] == Command.GET_DEVICE_INFO:
                    info_seen = True
                    break
            if not info_seen:
                raise RuntimeError(
                    "RK3 did not reply to GET_DEVICE_INFO within 2 seconds"
                )

            init = auto_message_command(1, 10, 0)
            print(f"sending AUTO_MSG (digital=1 analog=10 erp=0): {init.hex(' ')}")
            device.write(init)
            print("capturing endpoint 0x81; press Ctrl-C to stop")

            stop_at = None if duration is None else time.perf_counter() + duration
            while stop_at is None or time.perf_counter() < stop_at:
                packet = device.read()
                if packet is not None:
                    _emit(packet, started, capture)
    finally:
        if capture is not None:
            capture.close()
