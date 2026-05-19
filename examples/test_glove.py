import argparse
import time
from collections.abc import Sequence

import serial

from tactile_glove import GloveReader

FRAME_HEADER = bytes.fromhex("aa550399")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Diagnose tactile glove serial connectivity and SDK parsing."
    )
    parser.add_argument(
        "port",
        nargs="?",
        default="/dev/ttyUSB0",
        help="Serial device path, e.g. /dev/ttyUSB0, /dev/ttyACM0, or COM3",
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
        "--seconds",
        type=float,
        default=10.0,
        help="How long to listen during each diagnostic phase. Default: 10",
    )
    return parser.parse_args(argv)


def format_summary(
    *,
    port: str,
    hand: str,
    baudrate: int,
    elapsed: float,
    raw_bytes: int,
    header_count: int,
    parsed_frames: int,
) -> str:
    return "\n".join(
        [
            "Glove diagnostic summary",
            f"Port: {port}",
            f"Hand: {hand.upper()}",
            f"Baud rate: {baudrate}",
            f"Elapsed per phase: {elapsed:.1f}s",
            f"Raw bytes received: {raw_bytes}",
            f"Glove frame headers found: {header_count}",
            f"Parsed SDK frames: {parsed_frames}",
        ]
    )


def print_hints(raw_bytes: int, header_count: int, parsed_frames: int) -> None:
    if raw_bytes == 0:
        print(
            "No raw bytes were received. Check the port path, glove power/pairing, "
            "USB dongle/cable, and Linux serial permissions."
        )
    elif header_count == 0:
        print(
            "Raw bytes arrived, but no glove frame headers were found. Check baud rate, "
            "port selection, and whether the device is outputting the glove data stream."
        )
    elif parsed_frames == 0:
        print(
            "Glove-like headers arrived, but the SDK did not parse complete frames. "
            "This may indicate packet corruption, packet format mismatch, or an "
            "unexpected firmware/payload revision."
        )
    else:
        print("Glove stream looks healthy: raw bytes and parsed SDK frames were received.")


def collect_raw_bytes(port: str, baudrate: int, seconds: float) -> tuple[int, int]:
    print(f"[1/2] Listening for raw serial bytes on {port} at {baudrate} baud...")
    with serial.Serial(port, baudrate=baudrate, timeout=0.1) as ser:
        deadline = time.time() + seconds
        total = 0
        buffer = bytearray()
        while time.time() < deadline:
            waiting = ser.in_waiting
            if waiting:
                data = ser.read(waiting)
                total += len(data)
                buffer.extend(data)
                print(f"  received {len(data)} bytes, total={total}", flush=True)
            time.sleep(0.05)
    header_count = bytes(buffer).count(FRAME_HEADER)
    print(f"  first bytes: {bytes(buffer[:64]).hex(' ')}")
    return total, header_count


def collect_sdk_frames(port: str, hand: str, baudrate: int, seconds: float) -> int:
    print(f"[2/2] Reading parsed SDK frames for {hand.upper()} from {port}...")
    parsed_frames = 0
    deadline = time.time() + seconds
    with GloveReader(port, hand=hand, baudrate=baudrate) as glove:
        while time.time() < deadline:
            frame = glove.read_frame()
            if frame is not None:
                parsed_frames += 1
                print(f"  parsed frame {parsed_frames}: {frame.sensor_type_name}", flush=True)
            else:
                time.sleep(0.001)
    return parsed_frames


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    raw_bytes, header_count = collect_raw_bytes(args.port, args.baudrate, args.seconds)
    parsed_frames = collect_sdk_frames(args.port, args.hand, args.baudrate, args.seconds)
    print()
    print(
        format_summary(
            port=args.port,
            hand=args.hand,
            baudrate=args.baudrate,
            elapsed=args.seconds,
            raw_bytes=raw_bytes,
            header_count=header_count,
            parsed_frames=parsed_frames,
        )
    )
    print()
    print_hints(raw_bytes, header_count, parsed_frames)


if __name__ == "__main__":
    main()
