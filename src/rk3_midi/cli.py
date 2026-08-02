from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .calibrate import calibrate
from .config import ConfigError, load_config
from .dump import run_dump
from .midi_output import MidiPortError, list_output_ports
from .service import run_service
from .usb_device import RK3USBError, inspect_rk3


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="rk3-midi")
    subcommands = parser.add_subparsers(dest="command", required=True)

    subcommands.add_parser("inspect", help="print all RK3 USB descriptors")
    subcommands.add_parser("list-ports", help="list available MIDI output ports")

    run = subcommands.add_parser("run", help="run the RK3 USB-to-MIDI relay")
    run.add_argument("--config", type=Path, help="TOML configuration path")
    run.add_argument("--port", help="override the configured MIDI output port name")
    run.add_argument("--log-file", type=Path, help="override the rotating log path")
    run.add_argument("--verbose", action="store_true", help="print live MIDI output")

    dump = subcommands.add_parser(
        "dump", help="initialize RK3 and dump inbound EP1 packets"
    )
    dump.add_argument(
        "--output", type=Path, help="new JSONL capture file (must not exist)"
    )
    dump.add_argument("--duration", type=float, help="stop after this many seconds")

    calibration = subcommands.add_parser(
        "calibrate", help="capture pedal min/max to disk"
    )
    calibration.add_argument("pedal", choices=("treadle", "exp1", "exp2"))
    calibration.add_argument("--seconds", type=float, default=10.0)
    calibration.add_argument(
        "--config", type=Path, help="TOML path determining calibration location"
    )
    calibration.add_argument("--verbose", action="store_true", help="show raw samples")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "inspect":
            print("\n".join(inspect_rk3()))
        elif args.command == "list-ports":
            ports = list_output_ports()
            if ports:
                print("\n".join(f"{index}: {name}" for index, name in enumerate(ports)))
            else:
                print("No MIDI output ports found")
        elif args.command == "run":
            config = load_config(args.config)
            if args.port:
                from dataclasses import replace

                config = replace(config, midi_port=args.port)
            run_service(config, verbose=args.verbose, log_path=args.log_file)
        elif args.command == "dump":
            run_dump(output=args.output, duration=args.duration)
        elif args.command == "calibrate":
            minimum, maximum, path = calibrate(
                args.pedal,
                seconds=args.seconds,
                config_path=args.config,
                verbose=args.verbose,
            )
            print(f"saved {args.pedal} calibration {minimum}..{maximum} to {path}")
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)
        return 130
    except (
        ConfigError,
        MidiPortError,
        RK3USBError,
        RuntimeError,
        FileExistsError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
