"""Typed TOML configuration and independently persisted pedal calibration."""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any

BUTTON_NAMES = tuple(f"p{index}" for index in range(1, 10))
PEDAL_NAMES = ("exp1", "exp2", "treadle")
BUTTON_MODES = {"momentary", "toggle", "note"}
LED_NAMES = {"none", "pedal", *(f"p{index}" for index in range(1, 9))}
LED_MODES = {"follow", "toggle", "exclusive"}
CURVES = {"linear", "log", "exp"}


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class ButtonConfig:
    channel: int
    number: int
    mode: str
    debounce_ms: float = 20.0
    led: str | None = None
    led_mode: str = "follow"
    led_group: str | None = None
    preset_state: dict[str, bool] = field(default_factory=dict)


@dataclass(frozen=True)
class PedalConfig:
    channel: int
    cc: int
    minimum: int
    maximum: int
    curve: str = "linear"
    curve_amount: float = 3.0
    deadzone: float = 0.02
    smoothing_ms: float = 12.0
    jitter_raw: int = 2


@dataclass(frozen=True)
class AppConfig:
    midi_port: str
    buttons: dict[str, ButtonConfig]
    pedals: dict[str, PedalConfig]
    reconnect_initial_seconds: float = 1.0
    reconnect_max_seconds: float = 30.0
    log_max_bytes: int = 1_048_576
    log_backups: int = 3


def default_config_path() -> Path:
    base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return base / "rk3-midi" / "config.toml"


def default_calibration_path(config_path: Path | None = None) -> Path:
    return (config_path or default_config_path()).with_name("calibration.json")


def default_log_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "rk3-midi" / "rk3-midi.log"


def default_stop_request_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "rk3-midi" / "stop.request"


def defaults() -> AppConfig:
    preset_buttons = {"p1", "p2", "p3", "p5", "p6"}
    toggle_buttons = {"p4", "p7", "p8", "p9"}
    buttons = {
        name: ButtonConfig(
            channel=1,
            number=20 + index,
            mode="momentary",
            led="pedal" if name == "p9" else name,
            led_mode=(
                "toggle"
                if name in toggle_buttons
                else "exclusive"
                if name in preset_buttons
                else "follow"
            ),
            led_group=(
                "presets"
                if name in preset_buttons
                else "wah"
                if name in {"p8", "p9"}
                else None
            ),
        )
        for index, name in enumerate(BUTTON_NAMES)
    }
    pedals = {
        "exp1": PedalConfig(channel=1, cc=12, minimum=0, maximum=1023),
        "exp2": PedalConfig(channel=1, cc=13, minimum=0, maximum=1023),
        # Phase-1 ordinary sweep. P9 toe-switch overtravel reached 590 and is clamped.
        "treadle": PedalConfig(channel=1, cc=11, minimum=25, maximum=478),
    }
    return AppConfig(midi_port="loopMIDI", buttons=buttons, pedals=pedals)


def _table(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    if not isinstance(value, dict):
        raise ConfigError(f"[{key}] must be a TOML table")
    return value


def _integer(
    table: dict[str, Any], key: str, default: int, minimum: int, maximum: int
) -> int:
    value = table.get(key, default)
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not minimum <= value <= maximum
    ):
        raise ConfigError(f"{key} must be an integer in {minimum}..{maximum}")
    return value


def _number(
    table: dict[str, Any], key: str, default: float, minimum: float, maximum: float
) -> float:
    value = table.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"{key} must be numeric")
    result = float(value)
    if not minimum <= result <= maximum:
        raise ConfigError(f"{key} must be in {minimum}..{maximum}")
    return result


def load_config(path: Path | None = None) -> AppConfig:
    config = defaults()
    actual_path = path or default_config_path()
    if not actual_path.exists():
        return _apply_calibration(config, default_calibration_path(actual_path))

    try:
        with actual_path.open("rb") as source:
            data = tomllib.load(source)
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise ConfigError(f"could not read {actual_path}: {error}") from error

    midi = _table(data, "midi")
    midi_port = midi.get("port", config.midi_port)
    if not isinstance(midi_port, str) or not midi_port.strip():
        raise ConfigError("midi.port must be a non-empty string")

    button_tables = _table(data, "buttons")
    buttons: dict[str, ButtonConfig] = {}
    for name in BUTTON_NAMES:
        base = config.buttons[name]
        table = button_tables.get(name, {})
        if not isinstance(table, dict):
            raise ConfigError(f"[buttons.{name}] must be a TOML table")
        mode = table.get("mode", base.mode)
        aliases = {"latching_toggle": "toggle", "note_on_off": "note"}
        if not isinstance(mode, str):
            raise ConfigError(f"buttons.{name}.mode must be a string")
        mode = aliases.get(mode, mode)
        if mode not in BUTTON_MODES:
            raise ConfigError(f"buttons.{name}.mode must be momentary, toggle, or note")
        led = table.get("led", base.led)
        if not isinstance(led, str) or led not in LED_NAMES:
            raise ConfigError(
                f"buttons.{name}.led must be none, pedal, or p1 through p8"
            )
        led_mode = table.get("led_mode", base.led_mode)
        if not isinstance(led_mode, str) or led_mode not in LED_MODES:
            raise ConfigError(
                f"buttons.{name}.led_mode must be follow, toggle, or exclusive"
            )
        led_group = table.get("led_group", base.led_group)
        if led_group is not None and (
            not isinstance(led_group, str) or not led_group.strip()
        ):
            raise ConfigError(f"buttons.{name}.led_group must be a non-empty string")
        if led_mode == "exclusive" and led_group is None:
            raise ConfigError(
                f"buttons.{name}.led_group is required for exclusive LED mode"
            )
        preset_state = table.get("preset_state", {})
        if not isinstance(preset_state, dict) or any(
            name not in BUTTON_NAMES or not isinstance(enabled, bool)
            for name, enabled in preset_state.items()
        ):
            raise ConfigError(
                f"buttons.{name}.preset_state must map button names to booleans"
            )
        if preset_state and (led_mode != "exclusive" or led == "none"):
            raise ConfigError(
                f"buttons.{name}.preset_state requires an exclusive LED"
            )
        buttons[name] = ButtonConfig(
            channel=_integer(table, "channel", base.channel, 1, 16),
            number=_integer(table, "number", base.number, 0, 127),
            mode=mode,
            debounce_ms=_number(table, "debounce_ms", base.debounce_ms, 0, 250),
            led=None if led == "none" else led,
            led_mode=led_mode,
            led_group=led_group.strip() if isinstance(led_group, str) else None,
            preset_state=preset_state,
        )

    for name, button in buttons.items():
        group_states: dict[str, bool] = {}
        for target_name, enabled in button.preset_state.items():
            target = buttons[target_name]
            if target.led is None or target.led_mode != "toggle":
                raise ConfigError(
                    f"buttons.{name}.preset_state.{target_name} requires a toggle LED"
                )
            if target.led_group == button.led_group:
                raise ConfigError(
                    f"buttons.{name}.preset_state.{target_name} cannot target its preset group"
                )
            if target.led_group is not None:
                previous = group_states.setdefault(target.led_group, enabled)
                if previous != enabled:
                    raise ConfigError(
                        f"buttons.{name}.preset_state has conflicting values "
                        f"for LED group {target.led_group}"
                    )

    pedal_tables = _table(data, "pedals")
    pedals: dict[str, PedalConfig] = {}
    for name in PEDAL_NAMES:
        base = config.pedals[name]
        table = pedal_tables.get(name, {})
        if not isinstance(table, dict):
            raise ConfigError(f"[pedals.{name}] must be a TOML table")
        curve = table.get("curve", base.curve)
        if not isinstance(curve, str):
            raise ConfigError(f"pedals.{name}.curve must be a string")
        if curve not in CURVES:
            raise ConfigError(f"pedals.{name}.curve must be linear, log, or exp")
        minimum = _integer(table, "minimum", base.minimum, 0, 65535)
        maximum = _integer(table, "maximum", base.maximum, 0, 65535)
        if maximum <= minimum:
            raise ConfigError(f"pedals.{name}.maximum must be greater than minimum")
        pedals[name] = PedalConfig(
            channel=_integer(table, "channel", base.channel, 1, 16),
            cc=_integer(table, "cc", base.cc, 0, 127),
            minimum=minimum,
            maximum=maximum,
            curve=curve,
            curve_amount=_number(table, "curve_amount", base.curve_amount, 0.1, 10),
            deadzone=_number(table, "deadzone", base.deadzone, 0, 0.2),
            smoothing_ms=_number(table, "smoothing_ms", base.smoothing_ms, 0, 500),
            jitter_raw=_integer(table, "jitter_raw", base.jitter_raw, 0, 100),
        )

    usb_table = _table(data, "usb")
    logging_table = _table(data, "logging")
    config = AppConfig(
        midi_port=midi_port.strip(),
        buttons=buttons,
        pedals=pedals,
        reconnect_initial_seconds=_number(
            usb_table,
            "reconnect_initial_seconds",
            config.reconnect_initial_seconds,
            0.1,
            60,
        ),
        reconnect_max_seconds=_number(
            usb_table, "reconnect_max_seconds", config.reconnect_max_seconds, 1, 300
        ),
        log_max_bytes=_integer(
            logging_table, "max_bytes", config.log_max_bytes, 1024, 100_000_000
        ),
        log_backups=_integer(logging_table, "backups", config.log_backups, 1, 20),
    )
    if config.reconnect_max_seconds < config.reconnect_initial_seconds:
        raise ConfigError(
            "usb.reconnect_max_seconds must be >= reconnect_initial_seconds"
        )
    return _apply_calibration(config, default_calibration_path(actual_path))


def load_calibration(path: Path) -> dict[str, tuple[int, int]]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError(f"could not read calibration {path}: {error}") from error
    result: dict[str, tuple[int, int]] = {}
    for name, values in data.items():
        if name not in PEDAL_NAMES or not isinstance(values, dict):
            continue
        minimum, maximum = values.get("minimum"), values.get("maximum")
        if (
            isinstance(minimum, int)
            and not isinstance(minimum, bool)
            and isinstance(maximum, int)
            and not isinstance(maximum, bool)
            and 0 <= minimum < maximum <= 65535
        ):
            result[name] = (minimum, maximum)
    return result


def _apply_calibration(config: AppConfig, path: Path) -> AppConfig:
    calibration = load_calibration(path)
    pedals = dict(config.pedals)
    for name, (minimum, maximum) in calibration.items():
        pedals[name] = replace(pedals[name], minimum=minimum, maximum=maximum)
    return replace(config, pedals=pedals)


def save_calibration(path: Path, name: str, minimum: int, maximum: int) -> None:
    if name not in PEDAL_NAMES:
        raise ConfigError(f"unknown pedal {name}")
    if not 0 <= minimum < maximum <= 65535:
        raise ConfigError("calibration minimum must be below maximum")
    existing = load_calibration(path)
    existing[name] = (minimum, maximum)
    payload = {
        pedal: {"minimum": bounds[0], "maximum": bounds[1]}
        for pedal, bounds in sorted(existing.items())
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
