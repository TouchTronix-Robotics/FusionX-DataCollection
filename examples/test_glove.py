import argparse
import struct
import time
from collections.abc import Sequence
from pathlib import Path

import serial
from tactile_glove import GloveReader

FRAME_HEADER = bytes.fromhex("aabb")


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
        default=1_000_000,
        help="Serial baud rate. Default: 1_000_000",
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
            "No raw bytes were received. Check the port path, glove power, "
            "USB cable, and Linux serial permissions."
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
        print(
            "Glove stream looks healthy: raw bytes and parsed SDK frames were received."
        )


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


def _command(command: int, sequence: int) -> bytes:
    body = FRAME_HEADER + struct.pack("<BBBII", 1, command, 1, sequence, 0)
    crc = 0
    for value in body:
        crc ^= value
        for _ in range(8):
            crc = (crc >> 1) ^ (0x8C if crc & 1 else 0)
    return body + bytes((crc, 0xFF))


def collect_raw_bytes(port: str, baudrate: int, seconds: float) -> tuple[bytes, int]:
    print(f"[1/2] Reading raw serial bytes on {port} at {baudrate} baud...")
    buffer = bytearray()
    with serial.Serial(port, baudrate=baudrate, timeout=0.02, write_timeout=0.3) as ser:
        try:
            for sequence, command in enumerate((0x07, 0x09, 0x08), 1):
                ser.write(_command(command, sequence))
                deadline = time.monotonic() + 0.15
                while time.monotonic() < deadline:
                    buffer.extend(ser.read(ser.in_waiting or 1))
            ser.write(_command(0x06, 4))
            deadline = time.monotonic() + seconds
            while time.monotonic() < deadline:
                buffer.extend(ser.read(ser.in_waiting or 1))
        finally:
            ser.write(_command(0x07, 5))
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
                print(
                    f"  parsed frame {parsed_frames}: {frame.hand.upper()}", flush=True
                )
            else:
                time.sleep(0.001)
    return parsed_frames


def main(argv: Sequence[str] | None = None) -> None:
    args = parse_args(argv)
    raw_data, header_count = collect_raw_bytes(args.port, args.baudrate, args.seconds)
    write_raw_bytes_report(args.raw_output, raw_data)
    print(f"  wrote raw byte log: {args.raw_output}")
    parsed_frames = collect_sdk_frames(
        args.port, args.hand, args.baudrate, args.seconds
    )
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
