#!/usr/bin/env python3
"""Run the production camera hardware load using the per-device diagnostics.

This launches one stereo diagnostic and two wrist diagnostics concurrently with
the production stream profile:

- head stereo: native side-by-side MJPEG at 30 FPS, IMU polled every 3 ms
- two wrist cameras: 1920x1080 MJPEG at 30 FPS, IMUs polled every 10 ms

It checks simultaneous camera/IMU operation and sustained frame rate without
changing or duplicating the production application. It does not exercise the
packaged executable, FFmpeg/DirectShow stream-copy path, or MCAP writer.
"""

from __future__ import annotations

import argparse
import math
import subprocess
import sys
import threading
import time
from pathlib import Path

ARDUCAM_VID = 0x0C45
HEAD_PID = 0x0234
WRIST_PID = 0x2502
FPS = 30
HEAD_IMU_INTERVAL_MS = 3.0
WRIST_IMU_INTERVAL_MS = 10.0
WRIST_SIZE = (1920, 1080)


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test one stereo and two wrist cameras concurrently at the production load."
    )
    parser.add_argument(
        "--seconds",
        type=positive_float,
        default=10.0,
        help="Approximate full-load streaming duration after startup (default: 10)",
    )
    parser.add_argument(
        "--min-fps",
        type=positive_float,
        default=FPS * 0.95,
        help="Minimum measured FPS required from every camera (default: 28.5)",
    )
    parser.add_argument(
        "--startup-timeout",
        type=positive_float,
        default=120.0,
        help="Maximum startup time before the streaming duration (default: 120 seconds)",
    )
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def scan_camera_paths() -> tuple[str, list[str]]:
    try:
        from arducam_uvc_stereo_sdk import scan_devices
    except ImportError as exc:
        raise RuntimeError(
            "arducam-uvc-stereo-sdk is not installed; follow README.md camera setup"
        ) from exc

    devices = scan_devices()
    compatible: list[object] = []
    for index, device in enumerate(devices):
        if device.vid != ARDUCAM_VID or device.pid not in (HEAD_PID, WRIST_PID):
            continue
        if not device.device_path:
            raise RuntimeError(f"device[{index}] has no SDK device path")
        compatible.append(device)
        print(
            f"device[{index}]: vid=0x{device.vid:04x} pid=0x{device.pid:04x} "
            f"node={device.video_node} serial={device.serial_number or '(none)'} "
            f"product={device.product} path={device.device_path}"
        )

    heads = [str(device.device_path) for device in compatible if device.pid == HEAD_PID]
    wrists = [str(device.device_path) for device in compatible if device.pid == WRIST_PID]
    if len(heads) != 1 or len(wrists) != 2:
        raise RuntimeError(
            "expected exactly one head stereo camera and two wrist cameras; "
            f"found {len(heads)} head and {len(wrists)} wrist"
        )
    return heads[0], wrists


def build_commands(
    tests_dir: Path,
    head_path: str,
    wrist_paths: list[str],
    frame_count: int,
    minimum_fps: float,
) -> list[tuple[str, list[str]]]:
    common = [
        "--headless",
        "--fps",
        str(FPS),
        "--min-fps",
        str(minimum_fps),
        "--max-frames",
        str(frame_count),
        "--print-every",
        str(max(1, frame_count - 1)),
    ]
    commands = [
        (
            "stereo",
            [
                sys.executable,
                str(tests_dir / "test_stereo_imu_stream.py"),
                "--device-path",
                head_path,
                "--imu-interval-ms",
                str(HEAD_IMU_INTERVAL_MS),
                "--post-calibration-delay",
                "0",
                *common,
            ],
        )
    ]
    for number, device_path in enumerate(wrist_paths, 1):
        commands.append(
            (
                f"wrist-{number}",
                [
                    sys.executable,
                    str(tests_dir / "test_wrist_imu_stream.py"),
                    "--device-path",
                    device_path,
                    "--width",
                    str(WRIST_SIZE[0]),
                    "--height",
                    str(WRIST_SIZE[1]),
                    "--imu-interval-ms",
                    str(WRIST_IMU_INTERVAL_MS),
                    *common,
                ],
            )
        )
    return commands


def _forward_output(label: str, process: subprocess.Popen[str]) -> None:
    assert process.stdout is not None
    for line in process.stdout:
        print(f"[{label}] {line}", end="", flush=True)


def _stop_processes(processes: dict[str, subprocess.Popen[str]]) -> None:
    running = [process for process in processes.values() if process.poll() is None]
    for process in running:
        process.terminate()
    deadline = time.monotonic() + 5.0
    for process in running:
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def run_commands(commands: list[tuple[str, list[str]]], timeout: float) -> int:
    processes: dict[str, subprocess.Popen[str]] = {}
    output_threads: list[threading.Thread] = []
    deadline = time.monotonic() + timeout
    try:
        for label, command in commands:
            print(f"Starting {label}: {subprocess.list2cmdline(command)}")
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            processes[label] = process
            thread = threading.Thread(
                target=_forward_output,
                args=(label, process),
                daemon=True,
                name=f"output-{label}",
            )
            thread.start()
            output_threads.append(thread)

        failed = False
        remaining = set(processes)
        while remaining:
            if time.monotonic() > deadline:
                print(
                    f"[ERROR] full-load diagnostic timed out after {timeout:g} seconds",
                    file=sys.stderr,
                )
                failed = True
            for label in list(remaining):
                return_code = processes[label].poll()
                if return_code is None:
                    continue
                remaining.remove(label)
                if return_code != 0:
                    print(
                        f"[ERROR] {label} failed with exit code {return_code}",
                        file=sys.stderr,
                    )
                    failed = True
            if failed:
                _stop_processes(processes)
                break
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("\nInterrupted; stopping all camera diagnostics.", file=sys.stderr)
        _stop_processes(processes)
        return 130
    finally:
        _stop_processes(processes)
        for thread in output_threads:
            thread.join(timeout=2.0)

    return 1 if failed else 0


def self_test() -> None:
    commands = build_commands(
        Path("/tmp/tests"),
        r"\\?\usb#head",
        [r"\\?\usb#wrist1", r"\\?\usb#wrist2"],
        301,
        28.5,
    )
    assert [label for label, _ in commands] == ["stereo", "wrist-1", "wrist-2"]
    assert commands[0][1][commands[0][1].index("--device-path") + 1] == r"\\?\usb#head"
    assert [
        command[command.index("--device-path") + 1] for _, command in commands[1:]
    ] == [r"\\?\usb#wrist1", r"\\?\usb#wrist2"]
    assert commands[0][1][commands[0][1].index("--imu-interval-ms") + 1] == "3.0"
    assert all(
        command[command.index("--imu-interval-ms") + 1] == "10.0"
        for _, command in commands[1:]
    )
    assert "--post-calibration-delay" in commands[0][1]
    assert all("--post-calibration-delay" not in command for _, command in commands[1:])
    assert all(
        command[command.index("--max-frames") + 1] == "301"
        for _, command in commands
    )
    print("Self-test passed.")


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0

    head_path, wrist_paths = scan_camera_paths()
    frame_count = max(2, math.ceil(args.seconds * FPS) + 1)
    commands = build_commands(
        Path(__file__).resolve().parent,
        head_path,
        wrist_paths,
        frame_count,
        args.min_fps,
    )
    print(
        "\nRunning one stereo and two wrist diagnostics concurrently for "
        f"approximately {args.seconds:g} seconds ({frame_count} frames each).\n"
    )
    return_code = run_commands(commands, args.startup_timeout + args.seconds)
    if return_code == 0:
        print("\nPASS: all three camera/IMU diagnostics sustained the production hardware load.")
    else:
        print("\nFAIL: the simultaneous production camera load did not pass.", file=sys.stderr)
    return return_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
