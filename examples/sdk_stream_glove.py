import argparse
import time
from collections.abc import Callable
from collections.abc import Sequence

from tactile_glove import FINGER_NAMES
from tactile_glove import GloveReader
from tactile_glove import GloveFrame


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream tactile glove frames.")
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
    parser.add_argument(
        "--show-fps",
        action="store_true",
        help="Display the instantaneous frame rate in frames per second",
    )
    return parser.parse_args(argv)


class FrameRateMeter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._last_timestamp: float | None = None

    def tick(self) -> float | None:
        timestamp = self._clock()
        if self._last_timestamp is None:
            self._last_timestamp = timestamp
            return None
        elapsed = timestamp - self._last_timestamp
        self._last_timestamp = timestamp
        if elapsed <= 0:
            return None
        return 1.0 / elapsed


def format_frame(
    frame: GloveFrame,
    hand: str | None = None,
    fps: float | None = None,
) -> str:
    sensor_name = hand.upper() if hand is not None else getattr(frame, "sensor_type_name", "glove")
    header = f"[{sensor_name}]"
    if fps is not None:
        header = f"{header} fps={fps:.2f}"
    lines = [header]
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
    fps_meter = FrameRateMeter() if args.show_fps else None
    with GloveReader(args.port, hand=args.hand, baudrate=args.baudrate) as glove:
        for frame in glove.stream():
            fps = fps_meter.tick() if fps_meter is not None else None
            print(format_frame(frame, hand=args.hand, fps=fps))


if __name__ == "__main__":
    main()
