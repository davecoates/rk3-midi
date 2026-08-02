"""PyUSB/libusb transport and descriptor discovery for the RK3."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from types import TracebackType
from typing import Any

import libusb_package
import usb.backend.libusb1
import usb.core
import usb.util

from .protocol import (
    EP1_BUFFER_SIZE,
    EP_COMMAND_IN,
    EP_COMMAND_OUT,
    PID_RIG_KONTROL_3,
    VID_NATIVE_INSTRUMENTS,
)

CONTROL_INTERFACE = 0
STREAMING_ALT_SETTING = 1
USB_TRANSFER_TYPE_BULK = 2


class RK3USBError(RuntimeError):
    pass


def _backend() -> Any:
    backend = usb.backend.libusb1.get_backend(find_library=libusb_package.find_library)
    if backend is None:
        raise RK3USBError("libusb-1.0 backend could not be loaded")
    return backend


def find_device() -> Any | None:
    return usb.core.find(
        idVendor=VID_NATIVE_INSTRUMENTS,
        idProduct=PID_RIG_KONTROL_3,
        backend=_backend(),
    )


def _endpoint_type(attributes: int) -> str:
    return {0: "control", 1: "isochronous", 2: "bulk", 3: "interrupt"}.get(
        attributes & 0x03, "unknown"
    )


def descriptor_lines(device: Any) -> list[str]:
    lines = [
        (
            f"device {device.idVendor:04x}:{device.idProduct:04x} "
            f"USB {device.bcdUSB >> 8:x}.{device.bcdUSB & 0xFF:02x} "
            f"class=0x{device.bDeviceClass:02x} configurations={device.bNumConfigurations}"
        )
    ]
    for configuration in device:
        lines.append(
            f"configuration {configuration.bConfigurationValue}: "
            f"interfaces={configuration.bNumInterfaces} max-power={configuration.bMaxPower * 2}mA"
        )
        for interface in configuration:
            lines.append(
                f"  interface {interface.bInterfaceNumber} alt {interface.bAlternateSetting}: "
                f"class=0x{interface.bInterfaceClass:02x} "
                f"subclass=0x{interface.bInterfaceSubClass:02x} "
                f"protocol=0x{interface.bInterfaceProtocol:02x} "
                f"endpoints={interface.bNumEndpoints}"
            )
            for endpoint in interface:
                direction = "IN" if endpoint.bEndpointAddress & 0x80 else "OUT"
                lines.append(
                    f"    endpoint 0x{endpoint.bEndpointAddress:02x} {direction} "
                    f"{_endpoint_type(endpoint.bmAttributes)} "
                    f"max-packet={endpoint.wMaxPacketSize} interval={endpoint.bInterval}"
                )
    return lines


def inspect_rk3() -> list[str]:
    device = find_device()
    if device is None:
        raise RK3USBError(
            "RK3 17cc:1940 was not visible to libusb. Plug it in and bind it to WinUSB."
        )
    try:
        return descriptor_lines(device)
    except usb.core.USBError as error:
        raise RK3USBError(f"could not read RK3 descriptors: {error}") from error
    finally:
        usb.util.dispose_resources(device)


@dataclass
class RK3USB(AbstractContextManager["RK3USB"]):
    device: Any
    timeout_ms: int = 250
    claimed: bool = False

    @classmethod
    def open(cls, timeout_ms: int = 250) -> RK3USB:
        device = find_device()
        if device is None:
            raise RK3USBError(
                "RK3 17cc:1940 was not visible to libusb. Bind the RK3 to WinUSB with Zadig."
            )
        transport = cls(device=device, timeout_ms=timeout_ms)
        try:
            transport._configure()
            return transport
        except Exception:
            transport.close()
            raise

    def _configure(self) -> None:
        try:
            self.device.set_configuration(1)
            usb.util.claim_interface(self.device, CONTROL_INTERFACE)
            self.claimed = True
            self.device.set_interface_altsetting(
                interface=CONTROL_INTERFACE,
                alternate_setting=STREAMING_ALT_SETTING,
            )
            interface = self.device.get_active_configuration()[
                (CONTROL_INTERFACE, STREAMING_ALT_SETTING)
            ]
            endpoints = {endpoint.bEndpointAddress: endpoint for endpoint in interface}
            for address in (EP_COMMAND_OUT, EP_COMMAND_IN):
                endpoint = endpoints.get(address)
                if (
                    endpoint is None
                    or endpoint.bmAttributes & 0x03 != USB_TRANSFER_TYPE_BULK
                ):
                    raise RK3USBError(
                        f"expected bulk endpoint 0x{address:02x} on interface 0 alt 1"
                    )
        except usb.core.USBError as error:
            raise RK3USBError(
                "could not claim interface 0 / alt setting 1 via WinUSB: " + str(error)
            ) from error

    def write(self, packet: bytes) -> None:
        try:
            # Linux allows 200 ms for EP1 commands. Keep read polling short for
            # shutdown responsiveness without applying it to command writes.
            written = self.device.write(
                EP_COMMAND_OUT, packet, timeout=max(self.timeout_ms, 200)
            )
        except usb.core.USBError as error:
            try:
                self.device.clear_halt(EP_COMMAND_OUT)
            except usb.core.USBError:
                pass
            raise RK3USBError(f"bulk write to 0x01 failed: {error}") from error
        if written != len(packet):
            raise RK3USBError(f"short bulk write: {written}/{len(packet)} bytes")

    def read(self, timeout_ms: int | None = None) -> bytes | None:
        try:
            data = self.device.read(
                EP_COMMAND_IN,
                EP1_BUFFER_SIZE,
                timeout=self.timeout_ms if timeout_ms is None else timeout_ms,
            )
            return bytes(data)
        except usb.core.USBTimeoutError:
            return None
        except usb.core.USBError as error:
            raise RK3USBError(f"bulk read from 0x81 failed: {error}") from error

    def close(self) -> None:
        if self.claimed:
            try:
                usb.util.release_interface(self.device, CONTROL_INTERFACE)
            except usb.core.USBError:
                pass
            self.claimed = False
        usb.util.dispose_resources(self.device)

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()
