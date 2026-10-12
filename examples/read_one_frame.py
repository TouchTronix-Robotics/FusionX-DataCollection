import argparse
import math
from collections.abc import Sequence

from tactile_glove import GloveFrame, GloveReader

DEFAULT_PIXEL_AREA_MM2 = 22.5


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
        default=1_000_000,
        help="Serial baud rate. Default: 1_000_000",
    )
    parser.add_argument(
        "--force",
        metavar="JSON",
        help="Per-pixel pressure calibration; captures a contact-free startup tare",
    )
    parser.add_argument(
        "--pixel-area-mm2",
        type=float,
        default=DEFAULT_PIXEL_AREA_MM2,
        metavar="AREA",
        help=f"Active area of each pixel in mm² for --force (default: {DEFAULT_PIXEL_AREA_MM2})",
    )
    args = parser.parse_args(argv)
    if not math.isfinite(args.pixel_area_mm2) or args.pixel_area_mm2 <= 0:
        parser.error("--pixel-area-mm2 must be finite and positive")
    return args


def format_frame(frame: GloveFrame, hand: str | None = None) -> str:
    sensor_name = hand.upper() if hand is not None else frame.hand.upper()
    lines = [f"[{sensor_name}]", "finger:"]
    for finger, pressure in frame.tactile.finger_pressure.items():
        bend = frame.tactile.finger_bend[finger]
        lines.append(f"  {finger}: pressure={pressure} bend={bend}")
        calibrated = frame.tactile.finger_pressure_kPa_pixels
        if calibrated is not None:
            lines[-1] += f" pressure_kPa={calibrated[finger]}"
            lines[-1] += f" saturated={frame.tactile.finger_pressure_saturated[finger]}"
        forces = frame.tactile.finger_pressure_N_pixels
        if forces is not None:
            lines[-1] += f" force_N={forces[finger]}"
    lines.append(
        f"imu: euler_deg={frame.imu.euler_deg} gyro_raw={frame.imu.gyro_raw} accel_raw={frame.imu.accel_raw}"
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    print(
        f"Opening {args.port} at {args.baudrate} baud for {args.hand.upper()}; "
        "waiting for glove frames...",
        flush=True,
    )
    with GloveReader(
        args.port,
        hand=args.hand,
        baudrate=args.baudrate,
        force=args.force,
        pixel_area_mm2=args.pixel_area_mm2,
    ) as glove:
        if args.force is not None:
            print(
                "Keep the worn glove contact-free for the one-second tare.", flush=True
            )
            glove.tare()
        while True:
            frame = glove.read_frame()
            if frame is not None:
                print(format_frame(frame, hand=args.hand))
                return


if __name__ == "__main__":
    main()
