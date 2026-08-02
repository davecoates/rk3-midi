import pytest

from rk3_midi.midi_output import MidiPortError, resolve_port


def test_resolve_unique_port_substring() -> None:
    assert resolve_port("loopMIDI", ["Synth", "loopMIDI Port 2"]) == (
        1,
        "loopMIDI Port 2",
    )


def test_reject_ambiguous_or_missing_port() -> None:
    with pytest.raises(MidiPortError, match="ambiguous"):
        resolve_port("loop", ["loop A", "loop B"])
    with pytest.raises(MidiPortError, match="not found"):
        resolve_port("missing", ["loop A"])
