"""Long-running RK3 USB-to-MIDI service with reconnect and rotating logs."""

from __future__ import annotations

import logging
import signal
import threading
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import AppConfig, default_log_path
from .controls import ControlProcessor
from .mapping import MappingEngine, MidiMessage
from .midi_output import MidiOutput, MidiPortError
from .protocol import (
    Command,
    DeviceInfo,
    auto_message_command,
    command_packet,
    parse_packet,
)
from .usb_device import RK3USB, RK3USBError

LOGGER = logging.getLogger("rk3-midi")


def configure_logging(
    config: AppConfig, path: Path | None = None, verbose: bool = False
) -> Path:
    log_path = path or default_log_path()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    LOGGER.handlers.clear()
    LOGGER.setLevel(logging.DEBUG if verbose else logging.INFO)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    rotating = RotatingFileHandler(
        log_path,
        maxBytes=config.log_max_bytes,
        backupCount=config.log_backups,
        encoding="utf-8",
    )
    rotating.setFormatter(formatter)
    LOGGER.addHandler(rotating)
    if verbose:
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(formatter)
        LOGGER.addHandler(console)
    return log_path


def initialize_device(device: RK3USB) -> DeviceInfo:
    device.write(command_packet(Command.GET_DEVICE_INFO))
    deadline = time.monotonic() + 2.0
    info: DeviceInfo | None = None
    while time.monotonic() < deadline:
        packet = device.read(timeout_ms=100)
        if packet is None:
            continue
        parsed = parse_packet(packet)
        if isinstance(parsed, DeviceInfo):
            info = parsed
            break
    if info is None:
        raise RK3USBError("RK3 did not reply to GET_DEVICE_INFO within 2 seconds")
    if info.num_digital_in < 9 or info.num_analog_in < 3:
        raise RK3USBError(
            f"unexpected RK3 capabilities: {info.num_digital_in} digital, "
            f"{info.num_analog_in} analog"
        )
    device.write(auto_message_command())
    # Serialize EP1 commands: RK3 acknowledges AUTO_MSG with a one-byte 0x0b
    # packet and WinUSB may time out a second OUT transfer while it is pending.
    auto_deadline = time.monotonic() + 1.0
    while time.monotonic() < auto_deadline:
        packet = device.read(timeout_ms=100)
        if packet is not None and packet[0] == Command.AUTO_MSG:
            break
    else:
        raise RK3USBError("RK3 did not acknowledge AUTO_MSG within 1 second")
    return info


class RK3MidiService:
    def __init__(self, config: AppConfig, verbose: bool = False) -> None:
        self.config = config
        self.verbose = verbose
        self.stop_event = threading.Event()
        self.mapping = MappingEngine(config)
        self.midi: MidiOutput | None = None

    def request_stop(self, *_: object) -> None:
        self.stop_event.set()

    def _open_midi(self) -> MidiOutput:
        output = MidiOutput(self.config.midi_port, verbose=self.verbose)
        LOGGER.info("opened MIDI output %s", output.port_name)
        return output

    def _send(self, messages: list[MidiMessage]) -> None:
        if self.midi is None:
            raise MidiPortError("MIDI output is not open")
        for message in messages:
            self.midi.send(message)
            LOGGER.debug(message.description)

    def _close_midi(self) -> None:
        if self.midi is not None:
            self.midi.close()
            self.midi = None

    def run(self) -> None:
        for event_name in ("SIGINT", "SIGTERM"):
            event = getattr(signal, event_name, None)
            if event is not None:
                signal.signal(event, self.request_stop)

        delay = self.config.reconnect_initial_seconds
        LOGGER.info("service starting")
        try:
            while not self.stop_event.is_set():
                if self.midi is None:
                    try:
                        self.midi = self._open_midi()
                    except MidiPortError as error:
                        LOGGER.warning("%s; retrying in %.1fs", error, delay)
                        self.stop_event.wait(delay)
                        delay = min(delay * 2, self.config.reconnect_max_seconds)
                        continue

                try:
                    with RK3USB.open(timeout_ms=50) as device:
                        info = initialize_device(device)
                        LOGGER.info(
                            "RK3 connected: firmware=%d digital=%d analog=%d",
                            info.firmware_version,
                            info.num_digital_in,
                            info.num_analog_in,
                        )
                        delay = self.config.reconnect_initial_seconds
                        controls = ControlProcessor(self.config)
                        self._connected_loop(device, controls)
                except MidiPortError as error:
                    LOGGER.warning("%s; reopening MIDI output", error)
                    self._close_midi()
                except (RK3USBError, ValueError) as error:
                    LOGGER.warning("RK3 unavailable: %s", error)
                finally:
                    if self.midi is not None:
                        try:
                            self._send(self.mapping.release_active())
                        except MidiPortError:
                            self._close_midi()

                if not self.stop_event.is_set():
                    LOGGER.info("reconnecting in %.1fs", delay)
                    self.stop_event.wait(delay)
                    delay = min(delay * 2, self.config.reconnect_max_seconds)
        finally:
            if self.midi is not None:
                try:
                    self._send(self.mapping.release_active())
                except MidiPortError:
                    pass
            self._close_midi()
            LOGGER.info("service stopped")

    def _connected_loop(self, device: RK3USB, controls: ControlProcessor) -> None:
        while not self.stop_event.is_set():
            packet = device.read(timeout_ms=25)
            timestamp = time.monotonic()
            if packet is not None:
                try:
                    parsed = parse_packet(packet)
                except ValueError as error:
                    LOGGER.warning(
                        "discarding malformed packet %s: %s", packet.hex(), error
                    )
                else:
                    for event in controls.feed(parsed, timestamp):
                        self._send(self.mapping.handle(event))
            for event in controls.tick(timestamp):
                self._send(self.mapping.handle(event))


def run_service(
    config: AppConfig, verbose: bool = False, log_path: Path | None = None
) -> None:
    configured_path = configure_logging(config, path=log_path, verbose=verbose)
    LOGGER.info("logging to %s", configured_path)
    RK3MidiService(config, verbose=verbose).run()
