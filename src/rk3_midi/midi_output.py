"""Small python-rtmidi output adapter with deterministic port matching."""

from __future__ import annotations

from dataclasses import dataclass

import rtmidi

from .mapping import MidiMessage


class MidiPortError(RuntimeError):
    pass


def list_output_ports() -> list[str]:
    output = rtmidi.MidiOut()
    try:
        return list(output.get_ports())
    finally:
        del output


def resolve_port(query: str, ports: list[str]) -> tuple[int, str]:
    exact = [(index, name) for index, name in enumerate(ports) if name == query]
    if exact:
        return exact[0]
    folded = [
        (index, name)
        for index, name in enumerate(ports)
        if name.casefold() == query.casefold()
    ]
    if len(folded) == 1:
        return folded[0]
    partial = [
        (index, name)
        for index, name in enumerate(ports)
        if query.casefold() in name.casefold()
    ]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise MidiPortError(f"MIDI output port matching {query!r} not found")
    names = ", ".join(name for _, name in partial)
    raise MidiPortError(f"MIDI output port {query!r} is ambiguous: {names}")


@dataclass
class MidiOutput:
    port_query: str
    verbose: bool = False

    def __post_init__(self) -> None:
        self._output = rtmidi.MidiOut()
        index, self.port_name = resolve_port(
            self.port_query, list(self._output.get_ports())
        )
        try:
            self._output.open_port(index)
        except Exception as error:
            raise MidiPortError(
                f"could not open MIDI port {self.port_name!r}: {error}"
            ) from error

    def send(self, message: MidiMessage) -> None:
        try:
            self._output.send_message(message.data)
        except Exception as error:
            raise MidiPortError(
                f"MIDI send failed on {self.port_name!r}: {error}"
            ) from error
        if self.verbose:
            print(message.description, flush=True)

    def close(self) -> None:
        try:
            self._output.close_port()
        except rtmidi.RtMidiError:
            pass
