#!/usr/bin/env python3
"""Display Arducam stereo calibration and host-synchronize stereo frames with IMU.

The camera supplies one side-by-side MJPEG frame. This script captures it through
the OpenCV backend reported by the vendor SDK and host-timestamps each frame as
soon as ``VideoCapture.grab()`` returns. A background thread polls the camera's
UVC Extension Unit IMU and stores the SDK host-monotonic timestamp for each
sample. Each video frame is paired with an IMU sample interpolated between the
two closest host timestamps.

This is portable across the operating systems supported by the SDK, but it is
not hardware clock synchronization: OpenCV does not expose the camera's
start-of-exposure timestamp, and the SDK does not publish a camera/IMU clock map
or camera-to-IMU extrinsic calibration.

Run from this script's directory:
    ~/env_ego/bin/python test_stereo_imu_stream.py

Press q or Esc in the preview window to stop. For a non-GUI check:
    ~/env_ego/bin/python test_stereo_imu_stream.py --headless --max-frames 30
"""

from __future__ import annotations

import argparse
import bisect
import json
import math
import sys
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np
from arducam_uvc_stereo_sdk import OpenCvBackend, convert_imu, open_device, scan_devices


@dataclass(frozen=True)
class VideoPacket:
    sequence: int
    timestamp_ns: int
    timestamp_source: str = "HOST_RECEIVE"


@dataclass(frozen=True)
class ImuSample:
    host_timestamp_ns: int
    imu_timestamp_raw: int
    temperature_c: float
    accel_x_g: float
    accel_y_g: float
    accel_z_g: float
    gyro_x_dps: float
    gyro_y_dps: float
    gyro_z_dps: float


@dataclass(frozen=True)
class SynchronizedImu:
    sample: ImuSample
    method: str
    nearest_offset_ns: int
    bracket_span_ns: int


class ImuSampler:
    """Poll the SDK IMU in a background thread and retain timestamped samples."""

    def __init__(self, device: Any, interval_ms: float, max_samples: int = 4096) -> None:
        self.device = device
        self.convert_imu = getattr(device, "convert_imu", convert_imu)
        self.interval_sec = float(interval_ms) / 1000.0
        self.samples: deque[ImuSample] = deque(maxlen=max_samples)
        self.condition = threading.Condition()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.error: BaseException | None = None

    def start(self) -> None:
        self.device.open_imu()
        self.thread = threading.Thread(target=self._run, name="arducam-imu", daemon=True)
        self.thread.start()

    def _run(self) -> None:
        try:
            while not self.stop_event.is_set():
                loop_start = time.monotonic()
                raw = self.device.read_imu()
                converted = self.convert_imu(raw)
                sample = ImuSample(
                    host_timestamp_ns=int(raw.host_timestamp_ns),
                    imu_timestamp_raw=int(raw.imu_timestamp_raw),
                    temperature_c=float(converted.temperature_c),
                    accel_x_g=float(converted.accel_x_g),
                    accel_y_g=float(converted.accel_y_g),
                    accel_z_g=float(converted.accel_z_g),
                    gyro_x_dps=float(converted.gyro_x_dps),
                    gyro_y_dps=float(converted.gyro_y_dps),
                    gyro_z_dps=float(converted.gyro_z_dps),
                )
                with self.condition:
                    self.samples.append(sample)
                    self.condition.notify_all()

                remaining = self.interval_sec - (time.monotonic() - loop_start)
                if remaining > 0:
                    self.stop_event.wait(remaining)
        except BaseException as exc:
            with self.condition:
                self.error = exc
                self.condition.notify_all()

    def synchronized_sample(self, timestamp_ns: int, wait_ms: float) -> SynchronizedImu:
        deadline = time.monotonic() + float(wait_ms) / 1000.0
        with self.condition:
            while (
                not self.error
                and (not self.samples or self.samples[-1].host_timestamp_ns < timestamp_ns)
                and time.monotonic() < deadline
            ):
                self.condition.wait(deadline - time.monotonic())

            if self.error is not None:
                raise RuntimeError(f"IMU reader failed: {self.error}") from self.error
            snapshot = list(self.samples)

        if not snapshot:
            raise RuntimeError("no IMU samples are available")

        timestamps = [sample.host_timestamp_ns for sample in snapshot]
        upper_index = bisect.bisect_left(timestamps, timestamp_ns)

        if 0 < upper_index < len(snapshot):
            lower = snapshot[upper_index - 1]
            upper = snapshot[upper_index]
            span = upper.host_timestamp_ns - lower.host_timestamp_ns
            if span > 0:
                alpha = (timestamp_ns - lower.host_timestamp_ns) / span
                interpolated = self._interpolate(lower, upper, alpha, timestamp_ns)
                nearest = min(
                    (lower, upper),
                    key=lambda sample: abs(sample.host_timestamp_ns - timestamp_ns),
                )
                return SynchronizedImu(
                    sample=interpolated,
                    method="interpolated",
                    nearest_offset_ns=nearest.host_timestamp_ns - timestamp_ns,
                    bracket_span_ns=span,
                )

        nearest = min(
            snapshot,
            key=lambda sample: abs(sample.host_timestamp_ns - timestamp_ns),
        )
        return SynchronizedImu(
            sample=nearest,
            method="nearest",
            nearest_offset_ns=nearest.host_timestamp_ns - timestamp_ns,
            bracket_span_ns=0,
        )

    @staticmethod
    def _interpolate(
        lower: ImuSample,
        upper: ImuSample,
        alpha: float,
        timestamp_ns: int,
    ) -> ImuSample:
        def lerp(a: float, b: float) -> float:
            return a + (b - a) * alpha

        nearest_raw_timestamp = (
            lower.imu_timestamp_raw if alpha <= 0.5 else upper.imu_timestamp_raw
        )
        return ImuSample(
            host_timestamp_ns=timestamp_ns,
            imu_timestamp_raw=nearest_raw_timestamp,
            temperature_c=lerp(lower.temperature_c, upper.temperature_c),
            accel_x_g=lerp(lower.accel_x_g, upper.accel_x_g),
            accel_y_g=lerp(lower.accel_y_g, upper.accel_y_g),
            accel_z_g=lerp(lower.accel_z_g, upper.accel_z_g),
            gyro_x_dps=lerp(lower.gyro_x_dps, upper.gyro_x_dps),
            gyro_y_dps=lerp(lower.gyro_y_dps, upper.gyro_y_dps),
            gyro_z_dps=lerp(lower.gyro_z_dps, upper.gyro_z_dps),
        )

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=2.0)
            self.thread = None
        try:
            self.device.close_imu()
        except Exception as exc:
            print(f"[WARN] Failed to close IMU cleanly: {exc}", file=sys.stderr)


@dataclass(frozen=True)
class CalibrationSummary:
    left: dict[str, Any]
    right: dict[str, Any]
    combined_width: int
    height: int
    baseline_units: float


def parse_calibration(json_text: str) -> tuple[dict[str, Any], CalibrationSummary]:
    payload = json.loads(json_text)
    camera_data = payload.get("cameraData")
    if not isinstance(camera_data, list):
        raise RuntimeError("calibration JSON does not contain cameraData")

    cameras = {
        str(entry.get("name", "")).lower(): entry
        for entry in camera_data
        if isinstance(entry, dict)
    }
    if "left" not in cameras or "right" not in cameras:
        raise RuntimeError("calibration JSON must contain left and right cameras")

    left = cameras["left"]
    right = cameras["right"]
    width = int(left["width"])
    height = int(left["height"])
    if (int(right["width"]), int(right["height"])) != (width, height):
        raise RuntimeError("left and right calibration dimensions do not match")

    extrinsics = left.get("extrinsics")
    if not isinstance(extrinsics, dict):
        raise RuntimeError("left-to-right extrinsics are missing")
    translation = [float(value) for value in extrinsics["translation"]]
    baseline = math.sqrt(sum(value * value for value in translation))

    return payload, CalibrationSummary(
        left=left,
        right=right,
        combined_width=width * 2,
        height=height,
        baseline_units=baseline,
    )


def print_calibration(
    version: int,
    payload: dict[str, Any],
    summary: CalibrationSummary,
    translation_unit_to_m: float,
) -> None:
    print("\n" + "=" * 80)
    print(f"ON-DEVICE CAMERA CALIBRATION (version {version})")
    print("=" * 80)
    print(json.dumps(payload, indent=2))
    print("-" * 80)
    print(
        f"Per-camera calibrated size: {summary.left['width']}x{summary.left['height']}"
    )
    print(f"Combined stereo stream:     {summary.combined_width}x{summary.height}")
    print(f"Stereo baseline:            {summary.baseline_units:.6f} calibration units")
    print(
        f"Stereo baseline in meters:  "
        f"{summary.baseline_units * translation_unit_to_m:.6f} m "
        f"(scale={translation_unit_to_m:g} m/unit)"
    )
    print("=" * 80 + "\n")


def select_sdk_device(device_index: int, serial: str | None) -> Any:
    devices = scan_devices()
    if not devices:
        raise RuntimeError("no Arducam UVC stereo devices found")

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


def open_opencv_capture(
    device: Any,
    width: int,
    height: int,
    fps: int,
) -> tuple[cv2.VideoCapture, OpenCvBackend, int]:
    sources = device.opencv_backend_indices
    if not sources:
        raise RuntimeError("the SDK did not report an OpenCV camera source")

    for backend_value, index in sources.items():
        backend = OpenCvBackend(int(backend_value))
        capture = cv2.VideoCapture(int(index), int(backend))
        if not capture.isOpened():
            capture.release()
            continue

        capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, width)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
        capture.set(cv2.CAP_PROP_FPS, fps)
        return capture, backend, int(index)

    raise RuntimeError("OpenCV could not open any camera source reported by the SDK")


def build_preview(
    frame: np.ndarray,
    packet: VideoPacket,
    synced: SynchronizedImu,
    scale: float,
) -> np.ndarray:
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
    half = width // 2
    font = cv2.FONT_HERSHEY_SIMPLEX
    cv2.line(preview, (half, 0), (half, height), (0, 255, 255), 2)
    cv2.putText(preview, "LEFT", (20, 40), font, 1.0, (0, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(preview, "RIGHT", (half + 20, 40), font, 1.0, (0, 255, 255), 2, cv2.LINE_AA)

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


def format_stream_line(packet: VideoPacket, synced: SynchronizedImu) -> str:
    sample = synced.sample
    return (
        f"frame={packet.sequence:06d} "
        f"cam_{packet.timestamp_source.lower()}_ns={packet.timestamp_ns} "
        f"imu_host_ns={sample.host_timestamp_ns} "
        f"imu_raw_ts={sample.imu_timestamp_raw} "
        f"sync={synced.method} "
        f"nearest_offset_ms={synced.nearest_offset_ns / 1e6:+.3f} "
        f"accel_g=({sample.accel_x_g:+.6f},{sample.accel_y_g:+.6f},{sample.accel_z_g:+.6f}) "
        f"gyro_dps=({sample.gyro_x_dps:+.6f},{sample.gyro_y_dps:+.6f},{sample.gyro_z_dps:+.6f}) "
        f"temperature_c={sample.temperature_c:.3f}"
    )


def validate_frame_rate(
    first_timestamp_ns: int | None,
    last_timestamp_ns: int | None,
    frame_count: int,
    requested_fps: int,
    minimum_fps: float | None,
) -> float | None:
    if first_timestamp_ns is None or last_timestamp_ns is None or frame_count < 2:
        print("[WARN] At least two frames are needed to measure FPS.", file=sys.stderr)
        return None

    elapsed_ns = last_timestamp_ns - first_timestamp_ns
    if elapsed_ns <= 0:
        raise RuntimeError("camera frame timestamps did not advance")
    measured_fps = (frame_count - 1) * 1e9 / elapsed_ns
    required_fps = minimum_fps if minimum_fps is not None else requested_fps * 0.95
    print(
        f"Measured frame rate: {measured_fps:.3f} FPS "
        f"(requested {requested_fps}, minimum {required_fps:.3f})"
    )
    if measured_fps < required_fps:
        raise RuntimeError(
            f"measured frame rate {measured_fps:.3f} FPS is below "
            f"the required {required_fps:.3f} FPS"
        )
    return measured_fps


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def nonnegative_int(value: str) -> int:
    parsed = int(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must be zero or greater")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Display Arducam calibration and host-synchronized stereo/IMU data."
    )
    parser.add_argument("--device-index", type=nonnegative_int, default=0)
    parser.add_argument("--serial", help="Select a camera by USB serial number")
    parser.add_argument("--fps", type=positive_int, default=30)
    parser.add_argument(
        "--min-fps",
        type=positive_float,
        help="Minimum measured FPS (default: 95 percent of requested FPS)",
    )
    parser.add_argument(
        "--imu-interval-ms",
        type=positive_float,
        default=5.0,
        help="IMU polling interval in milliseconds (default: 5)",
    )
    parser.add_argument(
        "--sync-wait-ms",
        type=positive_float,
        default=20.0,
        help="Maximum wait for a bracketing IMU sample (default: 20)",
    )
    parser.add_argument(
        "--post-calibration-delay",
        type=float,
        default=3.0,
        help="Delay before streaming after flash access (default: 3 seconds)",
    )
    parser.add_argument(
        "--translation-unit-to-m",
        type=positive_float,
        default=0.01,
        help="Calibration translation scale in meters/unit (vendor default: 0.01)",
    )
    parser.add_argument(
        "--preview-scale",
        type=positive_float,
        default=0.5,
        help="GUI preview scale (default: 0.5)",
    )
    parser.add_argument(
        "--print-every",
        type=positive_int,
        default=1,
        help="Print one synchronized record every N frames (default: 1)",
    )
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

    # Default open options require flash transport, which catches missing raw USB permissions.
    sdk_device = open_device(dev)
    version, calibration_json = sdk_device.read_json()
    payload, calibration = parse_calibration(calibration_json)
    print_calibration(
        version,
        payload,
        calibration,
        translation_unit_to_m=args.translation_unit_to_m,
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
        # Build history before the first host-receive timestamp arrives.
        time.sleep(max(0.05, args.imu_interval_ms / 1000.0 * 4.0))
        capture, backend, camera_index = open_opencv_capture(
            dev,
            width=calibration.combined_width,
            height=calibration.height,
            fps=args.fps,
        )
        print(
            f"Streaming {calibration.combined_width}x{calibration.height}@{args.fps} "
            f"through OpenCV {backend.name} index {camera_index}, "
            f"with IMU polling every {args.imu_interval_ms:g} ms."
        )
        if not args.headless:
            print("Press q or Esc in the preview window to stop.")

        while True:
            if not capture.grab():
                raise RuntimeError("OpenCV failed to grab a camera frame")
            packet = VideoPacket(
                sequence=frame_count,
                timestamp_ns=time.monotonic_ns(),
            )
            decoded, frame = capture.retrieve()
            if not decoded or frame is None:
                raise RuntimeError(f"OpenCV failed to decode frame {packet.sequence}")
            if (
                frame.shape[1] != calibration.combined_width
                or frame.shape[0] != calibration.height
            ):
                raise RuntimeError(
                    f"decoded frame is {frame.shape[1]}x{frame.shape[0]}, "
                    f"expected {calibration.combined_width}x{calibration.height}"
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
                cv2.imshow("Arducam stereo + synchronized IMU", preview)
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
