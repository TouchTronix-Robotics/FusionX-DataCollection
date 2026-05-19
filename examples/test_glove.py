import argparse
import time
from collections.abc import Sequence
from pathlib import Path

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
    parser.add_argument(
        "--raw-output",
        default="glove_raw_bytes.txt",
        help="Text file for the raw serial byte hex dump. Default: glove_raw_bytes.txt",
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
    raw_output: str,
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
            f"Raw byte log: {raw_output}",
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


def write_raw_bytes_report(path: str | Path, data: bytes) -> None:
    lines = [
        "Raw glove serial bytes",
        f"Total bytes: {len(data)}",
        "Hex dump:",
    ]
    for offset in range(0, len(data), 16):
        chunk = data[offset : offset + 16]
        lines.append(f"{offset:08x}  {chunk.hex(' ')}")
    Path(path).write_text("\n".join(lines) + "\n")


def collect_raw_bytes(port: str, baudrate: int, seconds: float) -> tuple[bytes, int]:
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
    raw_data = bytes(buffer)
    header_count = raw_data.count(FRAME_HEADER)
    print(f"  first bytes: {raw_data[:64].hex(' ')}")
    return raw_data, header_count


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
    raw_data, header_count = collect_raw_bytes(args.port, args.baudrate, args.seconds)
    write_raw_bytes_report(args.raw_output, raw_data)
    print(f"  wrote raw byte log: {args.raw_output}")
    parsed_frames = collect_sdk_frames(args.port, args.hand, args.baudrate, args.seconds)
    print()
    print(
        format_summary(
            port=args.port,
            hand=args.hand,
            baudrate=args.baudrate,
            elapsed=args.seconds,
            raw_bytes=len(raw_data),
            header_count=header_count,
            parsed_frames=parsed_frames,
            raw_output=args.raw_output,
        )
    )
    print()
    print_hints(len(raw_data), header_count, parsed_frames)


if __name__ == "__main__":
    main()
