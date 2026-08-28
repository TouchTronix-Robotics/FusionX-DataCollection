#!/usr/bin/env python3
"""Test a monocular Arducam wrist camera's 1080p UVC stream and IMU.

Run from the repository root:
    python tests/test_wrist_imu_stream.py

For a non-GUI check:
    python tests/test_wrist_imu_stream.py --headless --max-frames 30

Frames are host-timestamped when OpenCV ``VideoCapture.grab()`` returns. This
allows approximate host-time pairing with IMU samples, not hardware clock sync.
"""

from __future__ import annotations

import argparse
import sys
import time
from typing import Any

import cv2
from arducam_uvc_stereo_sdk import DeviceCapability, open_device

from test_stereo_imu_stream import (
    ImuHealthCheck,
    ImuSampler,
    SynchronizedImu,
    VideoPacket,
    format_stream_line,
    nonnegative_int,
    open_opencv_capture,
    positive_float,
    positive_int,
    select_sdk_device,
    validate_frame_rate,
)


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
        description="Test an Arducam wrist camera's 1080p UVC stream and IMU."
    )
    parser.add_argument("--device-index", type=nonnegative_int, default=0)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--serial", help="Select a camera by USB serial number")
    selection.add_argument("--device-path", help="Select a camera by its SDK device path")
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
    dev = select_sdk_device(args.device_index, args.serial, args.device_path)
    print(
        f"\nSelected: {dev.product} serial={dev.serial_number or '(none)'} "
        f"video={dev.video_node or dev.opencv}"
    )

    # Wrist cameras do not need flash transport in production.
    sdk_device = open_device(dev, DeviceCapability(0))

    imu = ImuSampler(sdk_device, interval_ms=args.imu_interval_ms)
    imu_health = ImuHealthCheck()
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
            imu_health.observe(synced.sample)
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
    imu_health.validate()
    print(f"Stopped after {captured_count} frame(s).")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
