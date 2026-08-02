import json
from dataclasses import replace

import pytest

from rk3_midi.config import (
    ConfigError,
    default_calibration_path,
    defaults,
    load_config,
    save_calibration,
)


def test_defaults_mirror_reference_cc_map() -> None:
    config = defaults()
    assert [config.buttons[f"p{i}"].number for i in range(1, 10)] == list(range(20, 29))
    assert config.pedals["treadle"].cc == 11
    assert config.pedals["exp1"].cc == 12
    assert config.pedals["exp2"].cc == 13


def test_load_toml_and_calibration_override(tmp_path) -> None:
    path = tmp_path / "custom.toml"
    path.write_text(
        '[midi]\nport="RK3"\n[buttons.p1]\nchannel=3\nnumber=64\nmode="note_on_off"\n',
        encoding="utf-8",
    )
    default_calibration_path(path).write_text(
        json.dumps({"treadle": {"minimum": 30, "maximum": 470}}), encoding="utf-8"
    )
    config = load_config(path)
    assert config.midi_port == "RK3"
    assert config.buttons["p1"] == replace(
        defaults().buttons["p1"], channel=3, number=64, mode="note"
    )
    assert (config.pedals["treadle"].minimum, config.pedals["treadle"].maximum) == (
        30,
        470,
    )


def test_reject_invalid_mapping(tmp_path) -> None:
    path = tmp_path / "bad.toml"
    path.write_text("[buttons.p1]\nchannel=17\n", encoding="utf-8")
    with pytest.raises(ConfigError, match="channel"):
        load_config(path)


def test_save_calibration_merges_pedals_atomically(tmp_path) -> None:
    path = tmp_path / "calibration.json"
    save_calibration(path, "treadle", 25, 478)
    save_calibration(path, "exp1", 100, 900)
    assert json.loads(path.read_text(encoding="utf-8")) == {
        "exp1": {"minimum": 100, "maximum": 900},
        "treadle": {"minimum": 25, "maximum": 478},
    }
    assert not path.with_suffix(".json.tmp").exists()
