"""Run the GUI's OPEN/FIST wearer calibration from the terminal."""

import argparse
from collections.abc import Sequence
from pathlib import Path

from tactile_glove import calibrate


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "port", nargs="?", help="One serial port, e.g. COM3 or /dev/ttyUSB0"
    )
    parser.add_argument(
        "--hand", choices=("lh", "rh"), help="Single-port hand; default: lh"
    )
    parser.add_argument("--left", metavar="PORT", help="Assign the left glove port")
    parser.add_argument("--right", metavar="PORT", help="Assign the right glove port")
    parser.add_argument(
        "--user", required=True, help="Name saved in the wearer calibration"
    )
    parser.add_argument("--output", type=Path, required=True, metavar="JSON")
    parser.add_argument("--baudrate", type=int, default=1_000_000)
    parser.add_argument(
        "--hold-seconds", type=float, default=3.0, help="Collection duration per pose"
    )
    parser.add_argument(
        "--language", choices=("en", "cn"), default="en", help="Voice cue language"
    )
    parser.add_argument(
        "--no-audio", action="store_true", help="Print instructions without audio cues"
    )
    args = parser.parse_args(argv)
    named = {
        hand: port for hand, port in (("lh", args.left), ("rh", args.right)) if port
    }
    if args.port is not None:
        if named:
            parser.error("use one positional port with --hand, or --left/--right")
        args.ports = {args.hand or "lh": args.port}
    else:
        if not named:
            parser.error("provide a serial port or assign ports with --left/--right")
        if args.hand is not None:
            parser.error("--hand applies only to a single positional port")
        args.ports = named
    return args


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        calibrate(
            args.ports,
            args.user,
            args.output,
            audio=not args.no_audio,
            language=args.language,
            baudrate=args.baudrate,
            hold_seconds=args.hold_seconds,
        )
    except KeyboardInterrupt:
        print("\nCalibration cancelled.", flush=True)
        return 130
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Calibration error: {error}", flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
