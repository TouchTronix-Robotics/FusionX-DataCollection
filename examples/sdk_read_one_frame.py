import argparse
from collections.abc import Sequence

from tactile_glove import FINGER_NAMES
from tactile_glove import GloveReader
from tactile_glove import GloveFrame


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read one tactile glove frame.")
    parser.add_argument(
        "port",
        nargs="?",
        default="/dev/ttyUSB0",
        help="Serial device path, e.g. /dev/ttyUSB1 or /dev/ttyACM0",
    )
    parser.add_argument(
        "--hand",
        choices=("lh", "rh"),
        default="lh",
        help="Hand label: lh for left hand, rh for right hand",
    )
    parser.add_argument(
        "--baudrate",
        type=int,
        default=921600,
        help="Serial baud rate. Default: 921600",
    )
    return parser.parse_args(argv)


def format_waiting_message(port: str, hand: str, baudrate: int) -> str:
    return f"Opening {port} at {baudrate} baud for {hand.upper()}; waiting for glove frames..."


def format_frame(frame: GloveFrame, hand: str | None = None) -> str:
    sensor_name = hand.upper() if hand is not None else getattr(frame, "sensor_type_name", "glove")
    lines = [f"[{sensor_name}]"]
    if frame.tactile is not None:
        lines.append("finger:")
        for finger in FINGER_NAMES:
            pressure = frame.tactile.finger_pressure[finger]
            bend = frame.tactile.finger_bend[finger]
            lines.append(f"  {finger}: pressure={pressure} bend={bend}")
        lines.append(f"palm:\npressure={frame.tactile.palm_pressure}")
    if frame.imu is not None:
        lines.append(f"imu: quaternion={frame.imu.quaternion}")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    print(format_waiting_message(args.port, hand=args.hand, baudrate=args.baudrate), flush=True)
    with GloveReader(args.port, hand=args.hand, baudrate=args.baudrate) as glove:
        while True:
            frame = glove.read_frame()
            if frame is not None:
                print(format_frame(frame, hand=args.hand))
                return


if __name__ == "__main__":
    main()
