#!/usr/bin/env python3
"""Test a monocular Arducam wrist camera's calibration, 1080p UVC, and IMU.

Run from the repository root:
    python tests/test_wrist_imu_stream.py

For a non-GUI check:
    python tests/test_wrist_imu_stream.py --headless --max-frames 30

Frames are host-timestamped when OpenCV ``VideoCapture.grab()`` returns. This
allows approximate host-time pairing with IMU samples, not hardware clock sync.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from typing import Any

import cv2
from arducam_uvc_stereo_sdk import open_device, scan_devices

from test_stereo_imu_stream import (
    ImuSampler,
    SynchronizedImu,
    VideoPacket,
    format_stream_line,
    nonnegative_int,
    open_opencv_capture,
    positive_float,
    positive_int,
    validate_frame_rate,
)


@dataclass(frozen=True)
class WristCalibration:
    name: str
    width: int
    height: int
    intrinsic_matrix: list[list[float]]
    distortion_count: int


def parse_wrist_calibration(json_text: str) -> tuple[dict[str, Any], WristCalibration]:
    payload = json.loads(json_text)
    camera_data = payload.get("cameraData")
    if camera_data is None:
        camera = payload
    elif isinstance(camera_data, list) and len(camera_data) == 1:
        camera = camera_data[0]
    else:
        raise RuntimeError("expected calibration for exactly one wrist camera")

    if not isinstance(camera, dict):
        raise RuntimeError("wrist calibration is not a JSON object")
    try:
        width = int(camera["width"])
        height = int(camera["height"])
        matrix = [[float(value) for value in row] for row in camera["intrinsicMatrix"]]
    except (KeyError, TypeError, ValueError) as exc:
        raise RuntimeError("wrist calibration is missing valid dimensions or intrinsics") from exc
    if width <= 0 or height <= 0 or len(matrix) != 3 or any(len(row) != 3 for row in matrix):
        raise RuntimeError("wrist calibration dimensions or 3x3 intrinsic matrix are invalid")

    distortion = camera.get("dist_coeff", [])
    if not isinstance(distortion, list):
        raise RuntimeError("wrist distortion coefficients are not a list")
    return payload, WristCalibration(
        name=str(camera.get("name", "wrist")),
        width=width,
        height=height,
        intrinsic_matrix=matrix,
        distortion_count=len(distortion),
    )


def print_calibration(
    version: int,
    payload: dict[str, Any],
    calibration: WristCalibration,
) -> None:
    matrix = calibration.intrinsic_matrix
    print("\n" + "=" * 80)
    print(f"ON-DEVICE WRIST CAMERA CALIBRATION (version {version})")
    print("=" * 80)
    print(json.dumps(payload, indent=2))
    print("-" * 80)
    print(f"Camera name:             {calibration.name}")
    print(f"Calibrated image size:   {calibration.width}x{calibration.height}")
    print(f"Focal length:            fx={matrix[0][0]:.6f}, fy={matrix[1][1]:.6f}")
    print(f"Principal point:         cx={matrix[0][2]:.6f}, cy={matrix[1][2]:.6f}")
    print(f"Distortion coefficients: {calibration.distortion_count}")
    print("=" * 80 + "\n")


def select_sdk_device(device_index: int, serial: str | None) -> Any:
    devices = scan_devices()
    if not devices:
        raise RuntimeError("no compatible Arducam UVC devices found")

    for index, dev in enumerate(devices):
        print(
            f"device[{index}]: vid=0x{dev.vid:04x} pid=0x{dev.pid:04x} "
            f"node={dev.video_node} serial={dev.serial_number or '(none)'} "
            f"product={dev.product}"
        )

    if serial is not None:
        matches = [dev for dev in devices if dev.serial_number == serial]
        if not matches:
            raise RuntimeError(f"no Arducam camera has serial number {serial!r}")
        return matches[0]
    if device_index < 0 or device_index >= len(devices):
        raise RuntimeError(
            f"device index {device_index} is invalid; found {len(devices)} device(s)"
        )
    return devices[device_index]


def build_preview(
    frame: Any,
    packet: VideoPacket,
    synced: SynchronizedImu,
    scale: float,
) -> Any:
    if scale != 1.0:
        preview = cv2.resize(
            frame,
            None,
            fx=scale,
            fy=scale,
            interpolation=cv2.INTER_AREA,
        )
    else:
        preview = frame.copy()

    height, width = preview.shape[:2]
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.putText(preview, "WRIST", (20, 40), font, 1.0, (0, 255, 255), 2, cv2.LINE_AA)

    sample = synced.sample
    lines = [
        f"frame={packet.sequence} cam_ts={packet.timestamp_ns} ({packet.timestamp_source})",
        (
            f"sync={synced.method} nearest_offset={synced.nearest_offset_ns / 1e6:+.3f} ms "
            f"bracket={synced.bracket_span_ns / 1e6:.3f} ms"
        ),
        (
            f"accel [g]  x={sample.accel_x_g:+.4f} "
            f"y={sample.accel_y_g:+.4f} z={sample.accel_z_g:+.4f}"
        ),
        (
            f"gyro [dps] x={sample.gyro_x_dps:+.3f} "
            f"y={sample.gyro_y_dps:+.3f} z={sample.gyro_z_dps:+.3f}"
        ),
        f"temperature={sample.temperature_c:.2f} C  imu_ts_raw={sample.imu_timestamp_raw}",
    ]

    overlay = preview.copy()
    box_top = max(55, height - 175)
    cv2.rectangle(overlay, (0, box_top), (width, height), (0, 0, 0), -1)
    cv2.addWeighted(overlay, 0.58, preview, 0.42, 0.0, preview)
    for index, line in enumerate(lines):
        cv2.putText(
            preview,
            line,
            (15, box_top + 28 + index * 29),
            font,
            0.65,
            (230, 255, 230),
            1,
            cv2.LINE_AA,
        )
    return preview


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test Arducam wrist camera intrinsics, 1080p UVC, and IMU."
    )
    parser.add_argument("--device-index", type=nonnegative_int, default=0)
    parser.add_argument("--serial", help="Select a camera by USB serial number")
    parser.add_argument("--width", type=positive_int, default=1920)
    parser.add_argument("--height", type=positive_int, default=1080)
    parser.add_argument("--fps", type=positive_int, default=30)
    parser.add_argument(
        "--min-fps",
        type=positive_float,
        help="Minimum measured FPS (default: 95 percent of requested FPS)",
    )
    parser.add_argument("--imu-interval-ms", type=positive_float, default=5.0)
    parser.add_argument("--sync-wait-ms", type=positive_float, default=20.0)
    parser.add_argument("--post-calibration-delay", type=float, default=3.0)
    parser.add_argument("--preview-scale", type=positive_float, default=0.5)
    parser.add_argument("--print-every", type=positive_int, default=1)
    parser.add_argument("--headless", action="store_true", help="Do not open a GUI window")
    parser.add_argument(
        "--max-frames",
        type=nonnegative_int,
        default=0,
        help="Stop after N frames; zero streams until interrupted",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dev = select_sdk_device(args.device_index, args.serial)
    print(
        f"\nSelected: {dev.product} serial={dev.serial_number or '(none)'} "
        f"video={dev.video_node or dev.opencv}"
    )

    sdk_device = open_device(dev)
    version, calibration_json = sdk_device.read_json()
    payload, calibration = parse_wrist_calibration(calibration_json)
    print_calibration(version, payload, calibration)
    if (calibration.width, calibration.height) != (args.width, args.height):
        print(
            f"[WARN] Intrinsics are for {calibration.width}x{calibration.height}; "
            f"the requested UVC test mode is {args.width}x{args.height}.",
            file=sys.stderr,
        )

    if args.post_calibration_delay > 0:
        print(
            f"Waiting {args.post_calibration_delay:g} seconds after calibration flash access..."
        )
        time.sleep(args.post_calibration_delay)

    imu = ImuSampler(sdk_device, interval_ms=args.imu_interval_ms)
    capture: cv2.VideoCapture | None = None
    frame_count = 0
    captured_count = 0
    first_timestamp_ns: int | None = None
    last_timestamp_ns: int | None = None
    try:
        imu.start()
        time.sleep(max(0.05, args.imu_interval_ms / 1000.0 * 4.0))
        capture, backend, camera_index = open_opencv_capture(
            dev,
            width=args.width,
            height=args.height,
            fps=args.fps,
        )
        print(
            f"Streaming {args.width}x{args.height}@{args.fps} through OpenCV "
            f"{backend.name} index {camera_index}, with IMU polling every "
            f"{args.imu_interval_ms:g} ms."
        )
        if not args.headless:
            print("Press q or Esc in the preview window to stop.")

        while True:
            if not capture.grab():
                raise RuntimeError("OpenCV failed to grab a wrist camera frame")
            packet = VideoPacket(frame_count, time.monotonic_ns())
            decoded, frame = capture.retrieve()
            if not decoded or frame is None:
                raise RuntimeError(f"OpenCV failed to decode frame {packet.sequence}")
            if (frame.shape[1], frame.shape[0]) != (args.width, args.height):
                raise RuntimeError(
                    f"decoded frame is {frame.shape[1]}x{frame.shape[0]}, "
                    f"expected {args.width}x{args.height}"
                )
            if first_timestamp_ns is None:
                first_timestamp_ns = packet.timestamp_ns
            last_timestamp_ns = packet.timestamp_ns
            captured_count += 1

            synced = imu.synchronized_sample(packet.timestamp_ns, args.sync_wait_ms)
            if frame_count % args.print_every == 0:
                print(format_stream_line(packet, synced), flush=True)

            if not args.headless:
                preview = build_preview(frame, packet, synced, args.preview_scale)
                cv2.imshow("Arducam wrist camera + synchronized IMU", preview)
                key = cv2.waitKey(1) & 0xFF
                if key in (27, ord("q")):
                    break

            frame_count += 1
            if args.max_frames and frame_count >= args.max_frames:
                break
    except KeyboardInterrupt:
        print("\nInterrupted.")
    finally:
        if capture is not None:
            capture.release()
        imu.stop()
        cv2.destroyAllWindows()

    validate_frame_rate(
        first_timestamp_ns,
        last_timestamp_ns,
        captured_count,
        args.fps,
        args.min_fps,
    )
    print(f"Stopped after {captured_count} frame(s).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
