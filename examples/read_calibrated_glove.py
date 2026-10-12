"""Print per-pixel pressure and force using a supplied glove calibration file."""

import argparse
import math
import time
from collections.abc import Sequence
from pathlib import Path

from tactile_glove import GloveReader


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("port", help="Serial port, e.g. /dev/ttyUSB0 or COM3")
    parser.add_argument("--hand", choices=("lh", "rh"), required=True)
    parser.add_argument("--force", type=Path, required=True, metavar="JSON")
    parser.add_argument("--seconds", type=float, default=10.0)
    parser.add_argument(
        "--interval", type=float, default=0.5, help="Seconds between terminal updates"
    )
    parser.add_argument(
        "--pixel-area-mm2", type=float, default=22.5, help="Active area per pixel"
    )
    args = parser.parse_args(argv)
    for name in ("seconds", "interval", "pixel_area_mm2"):
        value = getattr(args, name)
        if not math.isfinite(value) or value <= 0:
            parser.error(f"--{name.replace('_', '-')} must be finite and positive")
    return args


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    reader = GloveReader(
        args.port,
        hand=args.hand,
        force=args.force,
        pixel_area_mm2=args.pixel_area_mm2,
    )
    print(
        "Wear the glove and keep all tactile pads contact-free for the tare.",
        flush=True,
    )
    with reader as glove:
        glove.tare(duration_s=1.0)
        print(
            "Tare complete. Touch the pads to test the calibrated readings.\n"
            "Each list has one reading per pixel (16 pixels), row-major from top-left.\n"
            f"Pixel area: {args.pixel_area_mm2:g} mm². Ctrl+C stops the test.",
            flush=True,
        )
        deadline = time.monotonic() + args.seconds
        next_print = 0.0
        while time.monotonic() < deadline:
            frame = glove.read_frame()
            if frame is None:
                continue
            now = time.monotonic()
            if now < next_print:
                continue  # Keep acquiring between terminal updates.
            next_print = now + args.interval
            tactile = frame.tactile
            pressure = tactile.finger_pressure_kPa_pixels
            force = tactile.finger_pressure_N_pixels
            saturated = tactile.finger_pressure_saturated
            assert pressure is not None and force is not None and saturated is not None
            print(
                f"\n{frame.hand.upper()} host_timestamp_ns={frame.host_timestamp_ns} "
                f"device_timestamp_ms={frame.device_timestamp_ms}"
            )
            for finger, raw in tactile.finger_pressure.items():
                print(f"{finger}:")
                print(f"  ADC:       {raw}")
                print(f"  kPa:       {pressure[finger]}")
                print(f"  N:         {force[finger]}")
                print(f"  saturated: {saturated[finger]}")
            print(flush=True)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nStopped.")
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(f"Error: {error}") from error
