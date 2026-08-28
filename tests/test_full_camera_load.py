#!/usr/bin/env python3
"""Test the simultaneous camera load with a 40 Hz wrist-IMU target.

The test opens one dedicated SDK/IMU helper process per camera sequentially,
then starts all three MJPEG streams together:

- head stereo: 3840x1200 MJPEG at 30 FPS, IMU targeted at 100 Hz
- two wrist cameras: 1920x1080 MJPEG at 30 FPS, IMUs targeted at 40 Hz

The head must use a different USB bus from both wrists. The wrists may share a
bus. This does not exercise the packaged executable, FFmpeg/DirectShow capture,
or MCAP writing.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import math
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from arducam_uvc_stereo_sdk import sdk

from test_stereo_imu_stream import (
    DEFAULT_HEAD_IMU_INTERVAL_MS,
    DEFAULT_STEREO_SIZE,
    open_opencv_capture,
    validate_frame_rate,
)
from test_wrist_imu_stream import DEFAULT_WRIST_IMU_INTERVAL_MS, DEFAULT_WRIST_SIZE

ARDUCAM_VID = 0x0C45
HEAD_PID = 0x0234
WRIST_PID = 0x2502
FPS = 30
MIN_SANE_IMU_RATIO = 0.9
# A camera probed by a recent scan (this process or another) can stay missing
# from rescans for several seconds, so three attempts is not always enough.
SCAN_ATTEMPTS = 15
SCAN_RETRY_DELAY_SECONDS = 1.0


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Test one stereo and two wrist cameras under simultaneous load."
    )
    parser.add_argument(
        "--seconds",
        type=positive_float,
        default=10.0,
        help="Simultaneous streaming duration after startup (default: 10)",
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
        help="Maximum sequential IMU startup time (default: 120 seconds)",
    )
    parser.add_argument(
        "--skip-head-calibration",
        action="store_true",
        help="Skip stereo flash access for a prototype head camera",
    )
    parser.add_argument("--self-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--imu-worker", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--device-json", help=argparse.SUPPRESS)
    parser.add_argument("--poll-interval-ms", type=float, default=0.0, help=argparse.SUPPRESS)
    parser.add_argument("--read-calibration", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args()


def validate_usb_layout(head_bus: Any, wrist_buses: list[Any]) -> None:
    if head_bus in wrist_buses:
        raise RuntimeError(
            f"head camera must have its own USB bus; head is on bus {head_bus}, "
            f"wrists are on buses {wrist_buses[0]} and {wrist_buses[1]}"
        )


def _windows_usb_controller_id(device_path: str) -> str | None:
    """Resolve the PCI host controller instance ID behind an SDK device path.

    The SDK reports bus_number as 0 on Windows, so walk the PnP parent chain
    (device interface -> composite device -> hubs -> root hub -> controller)
    with cfgmgr32 instead.
    """
    parts = str(device_path).split("#")
    if len(parts) < 3:
        return None
    enumerator = parts[0].rsplit("\\", 1)[-1]
    instance_id = "\\".join((enumerator, parts[1], parts[2])).upper()
    try:
        cfgmgr = ctypes.WinDLL("cfgmgr32")
    except OSError:
        return None
    devinst = ctypes.c_uint32()
    if cfgmgr.CM_Locate_DevNodeW(
        ctypes.byref(devinst), ctypes.c_wchar_p(instance_id), 0
    ) != 0:
        return None
    buffer = ctypes.create_unicode_buffer(512)
    for _ in range(10):
        parent = ctypes.c_uint32()
        if cfgmgr.CM_Get_Parent(ctypes.byref(parent), devinst, 0) != 0:
            return None
        devinst = parent
        if cfgmgr.CM_Get_Device_IDW(devinst, buffer, len(buffer), 0) != 0:
            return None
        if buffer.value.upper().startswith("PCI\\"):
            return buffer.value
    return None


def _usb_bus_id(device: Any) -> Any:
    bus = int(device.bus_number)
    if bus:
        return bus
    if sys.platform == "win32":
        controller = _windows_usb_controller_id(str(device.device_path))
        if controller is not None:
            return controller
    return 0


def scan_camera_devices() -> tuple[Any, list[Any]]:
    devices: list[Any] = []
    heads: list[Any] = []
    wrists: list[Any] = []
    last_error: Exception | None = None
    for attempt in range(1, SCAN_ATTEMPTS + 1):
        try:
            devices = [
                device
                for device in sdk.scan_devices()
                if device.vid == ARDUCAM_VID
                and device.pid in (HEAD_PID, WRIST_PID)
            ]
            heads = [device for device in devices if device.pid == HEAD_PID]
            wrists = [device for device in devices if device.pid == WRIST_PID]
            last_error = None
        except Exception as exc:
            devices = []
            heads = []
            wrists = []
            last_error = exc

        if (
            len(heads) == 1
            and len(wrists) == 2
            and all(device.device_path for device in devices)
        ):
            break
        if attempt < SCAN_ATTEMPTS:
            print(
                f"[WARN] Camera scan {attempt}/{SCAN_ATTEMPTS} found "
                f"{len(heads)} head and {len(wrists)} wrist; retrying...",
                file=sys.stderr,
            )
            time.sleep(SCAN_RETRY_DELAY_SECONDS)

    if last_error is not None:
        raise RuntimeError(
            f"camera scan failed after {SCAN_ATTEMPTS} attempts: {last_error}"
        ) from last_error
    for index, device in enumerate(devices):
        if not device.device_path:
            raise RuntimeError(f"device[{index}] has no SDK device path")
        print(
            f"device[{index}]: vid=0x{device.vid:04x} pid=0x{device.pid:04x} "
            f"node={device.video_node} bus={device.bus_number} "
            f"serial={device.serial_number or '(none)'} product={device.product} "
            f"path={device.device_path}"
        )

    if len(heads) != 1 or len(wrists) != 2:
        raise RuntimeError(
            f"camera scan failed after {SCAN_ATTEMPTS} attempts: expected exactly "
            "one head stereo camera and two wrist cameras; "
            f"found {len(heads)} head and {len(wrists)} wrist"
        )

    head_bus = _usb_bus_id(heads[0])
    wrist_buses = [_usb_bus_id(device) for device in wrists]
    if not head_bus and not any(wrist_buses):
        print(
            "[WARN] USB bus information is unavailable; skipping USB layout validation",
            file=sys.stderr,
        )
    else:
        validate_usb_layout(head_bus, wrist_buses)
        print(
            f"USB layout: head bus {head_bus}; wrist buses "
            f"{wrist_buses[0]} and {wrist_buses[1]}"
        )
    wrists.sort(key=lambda device: str(device.device_path).casefold())
    return heads[0], wrists


def scan_camera_paths() -> tuple[str, list[str]]:
    """Return the validated topology for the pytest per-device fixture."""
    head, wrists = scan_camera_devices()
    return str(head.device_path), [str(device.device_path) for device in wrists]


def _device_fields(device: Any) -> dict[str, Any]:
    return {
        "vid": int(device.vid),
        "pid": int(device.pid),
        "bus_number": int(device.bus_number),
        "device_address": int(device.device_address),
        "serial_number": str(device.serial_number),
        "manufacturer": str(device.manufacturer),
        "product": str(device.product),
        "video_node": str(device.video_node),
        "device_path": str(device.device_path),
        "opencv": {
            int(backend): int(index)
            for backend, index in device.opencv_backend_indices.items()
        },
    }


def _emit(record: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(record, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def imu_worker(device_json: str, poll_interval_ms: float, read_calibration: bool) -> int:
    device = None
    try:
        fields = json.loads(device_json)
        info = sdk.DeviceInfo()
        for name in (
            "vid",
            "pid",
            "bus_number",
            "device_address",
            "serial_number",
            "manufacturer",
            "product",
            "video_node",
            "device_path",
        ):
            setattr(info, name, fields[name])
        info.opencv_backend_indices = {
            int(backend): int(index) for backend, index in fields["opencv"].items()
        }
        capabilities = (
            sdk.DeviceCapability.FLASH_TRANSPORT
            if read_calibration
            else sdk.DeviceCapability(0)
        )
        # Opening (which re-scans internally) and flash reads can fail for a
        # few seconds after another process probed this camera, so retry.
        open_deadline = time.monotonic() + 30.0
        while True:
            try:
                device = sdk.open_device(info, capabilities)
                if read_calibration:
                    version, text = device.read_json()
                    json.loads(text)
                    _emit({"type": "calibration", "version": int(version)})
                break
            except Exception:
                device = None
                if time.monotonic() >= open_deadline:
                    raise
                time.sleep(1.0)

        device.open_imu()
        _emit({"type": "ready"})
        if sys.stdin.readline().strip() != "start":
            return 0

        convert_imu = getattr(device, "convert_imu", sdk.convert_imu)
        interval_seconds = max(0.0, poll_interval_ms) / 1000.0
        while True:
            loop_start = time.monotonic()
            raw = device.read_imu()
            converted = convert_imu(raw)
            _emit(
                {
                    "type": "sample",
                    "host_ns": int(raw.host_timestamp_ns),
                    "ts_raw": int(raw.imu_timestamp_raw),
                    "temperature_c": float(converted.temperature_c),
                    "accel_g": [
                        float(converted.accel_x_g),
                        float(converted.accel_y_g),
                        float(converted.accel_z_g),
                    ],
                    "gyro_dps": [
                        float(converted.gyro_x_dps),
                        float(converted.gyro_y_dps),
                        float(converted.gyro_z_dps),
                    ],
                }
            )
            remaining = interval_seconds - (time.monotonic() - loop_start)
            if remaining > 0:
                time.sleep(remaining)
    except (BrokenPipeError, KeyboardInterrupt):
        return 0
    except Exception as exc:
        try:
            _emit({"type": "fatal", "message": str(exc)})
        except Exception:
            pass
        return 1
    finally:
        if device is not None:
            try:
                device.close_imu()
            except Exception:
                pass


class ImuWorker:
    """One dedicated SDK process, matching production's per-camera isolation."""

    def __init__(
        self,
        label: str,
        device: Any,
        poll_interval_ms: float,
        *,
        read_calibration: bool,
    ) -> None:
        self.label = label
        self.device = device
        self.poll_interval_ms = poll_interval_ms
        self.read_calibration = read_calibration
        self.process: subprocess.Popen[str] | None = None
        self.ready_event = threading.Event()
        self.error: str | None = None
        self.calibration_received = False
        self.total_samples = 0
        self.sane_samples = 0
        self.zero_timestamp_samples = 0
        self.nonfinite_samples = 0
        self.implausible_accel_samples = 0
        self.first_raw_timestamp: int | None = None
        self.last_raw_timestamp: int | None = None
        self.first_host_timestamp_ns: int | None = None
        self.last_host_timestamp_ns: int | None = None
        self._stopping = False

    def start(self) -> None:
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--imu-worker",
            "--device-json",
            json.dumps(_device_fields(self.device), separators=(",", ":")),
            "--poll-interval-ms",
            str(self.poll_interval_ms),
        ]
        if self.read_calibration:
            command.append("--read-calibration")
        self.process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        threading.Thread(target=self._read_stdout, daemon=True).start()
        threading.Thread(target=self._read_stderr, daemon=True).start()

    def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        for line in self.process.stdout:
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                print(f"[{self.label} IMU] {line}", end="")
                continue
            kind = record.get("type")
            if kind == "ready":
                self.ready_event.set()
            elif kind == "calibration":
                self.calibration_received = True
            elif kind == "sample":
                self._observe_sample(record)
            elif kind == "fatal":
                self.error = str(record.get("message", "unknown IMU worker error"))
                self.ready_event.set()
        if not self.ready_event.is_set() and not self._stopping:
            self.error = self.error or "IMU worker exited before readiness"
            self.ready_event.set()

    def _read_stderr(self) -> None:
        assert self.process is not None and self.process.stderr is not None
        for line in self.process.stderr:
            print(f"[{self.label} IMU] {line}", end="", file=sys.stderr)

    def _observe_sample(self, record: dict[str, Any]) -> None:
        self.total_samples += 1
        ts_raw = int(record["ts_raw"])
        values = [
            float(record["temperature_c"]),
            *(float(value) for value in record["accel_g"]),
            *(float(value) for value in record["gyro_dps"]),
        ]
        accel = [float(value) for value in record["accel_g"]]
        magnitude = math.sqrt(sum(value * value for value in accel))
        if ts_raw == 0:
            self.zero_timestamp_samples += 1
            return
        if not all(math.isfinite(value) for value in values):
            self.nonfinite_samples += 1
            return
        if not 0.3 <= magnitude <= 8.0:
            self.implausible_accel_samples += 1
            return
        self.sane_samples += 1
        host_ns = int(record["host_ns"])
        if self.first_raw_timestamp is None:
            self.first_raw_timestamp = ts_raw
            self.first_host_timestamp_ns = host_ns
        self.last_raw_timestamp = ts_raw
        self.last_host_timestamp_ns = host_ns

    def wait_ready(self, timeout: float) -> None:
        if not self.ready_event.wait(timeout):
            raise RuntimeError(f"{self.label} IMU worker startup timed out")
        if self.error is not None:
            raise RuntimeError(f"{self.label} IMU worker failed: {self.error}")
        if self.read_calibration and not self.calibration_received:
            raise RuntimeError(f"{self.label} calibration was not received")
        print(f"{self.label}: IMU ready")

    def start_polling(self) -> None:
        assert self.process is not None and self.process.stdin is not None
        self.process.stdin.write("start\n")
        self.process.stdin.flush()

    def validate(self) -> None:
        if self.error is not None:
            raise RuntimeError(f"{self.label} IMU worker failed: {self.error}")
        ratio = self.sane_samples / self.total_samples if self.total_samples else 0.0
        elapsed_seconds = (
            (self.last_host_timestamp_ns - self.first_host_timestamp_ns) / 1e9
            if self.first_host_timestamp_ns is not None
            and self.last_host_timestamp_ns is not None
            else 0.0
        )
        sample_rate = (
            (self.sane_samples - 1) / elapsed_seconds
            if self.sane_samples > 1 and elapsed_seconds > 0
            else 0.0
        )
        print(
            f"{self.label}: sane IMU samples {self.sane_samples}/{self.total_samples} "
            f"({ratio:.1%}, {sample_rate:.1f} Hz); "
            f"invalid timestamp={self.zero_timestamp_samples}, "
            f"nonfinite={self.nonfinite_samples}, "
            f"implausible accel={self.implausible_accel_samples}"
        )
        if self.sane_samples < 2:
            raise RuntimeError(f"{self.label} produced fewer than two sane IMU samples")
        if self.first_raw_timestamp == self.last_raw_timestamp:
            raise RuntimeError(f"{self.label} IMU timestamp did not advance")
        if ratio < MIN_SANE_IMU_RATIO:
            raise RuntimeError(
                f"{self.label} sane IMU ratio {ratio:.1%} is below "
                f"{MIN_SANE_IMU_RATIO:.0%}"
            )

    def stop(self) -> None:
        self._stopping = True
        process = self.process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


def _capture_video(
    label: str,
    device: Any,
    size: tuple[int, int],
    frame_count: int,
    minimum_fps: float,
    ready_barrier: threading.Barrier,
    start_event: threading.Event,
    open_timeout: float,
    results: dict[str, float],
    errors: list[tuple[str, Exception]],
) -> None:
    capture = None
    try:
        capture, backend, camera_index = open_opencv_capture(
            device,
            width=size[0],
            height=size[1],
            fps=FPS,
        )
        if not capture.grab():
            raise RuntimeError("warm-up grab failed")
        decoded, frame = capture.retrieve()
        if not decoded or frame is None:
            raise RuntimeError("warm-up decode failed")
        if (frame.shape[1], frame.shape[0]) != size:
            raise RuntimeError(
                f"warm-up frame is {frame.shape[1]}x{frame.shape[0]}, "
                f"expected {size[0]}x{size[1]}"
            )
        # The first frames after opening a UVC stream arrive slowly
        # (auto-exposure settling, pipeline warm-up) and would drag the
        # measured FPS down, so discard about a second of frames first.
        for _ in range(FPS):
            capture.grab()
        print(
            f"{label}: ready {size[0]}x{size[1]}@{FPS} through "
            f"OpenCV {backend.name} index {camera_index}"
        )
        ready_barrier.wait(timeout=open_timeout)
        if not start_event.wait(timeout=10.0):
            raise RuntimeError("timed out waiting for simultaneous video start")

        first_timestamp_ns = None
        last_timestamp_ns = None
        for index in range(frame_count):
            retry_deadline = time.monotonic() + (5.0 if index == 0 else 0.0)
            while not capture.grab():
                if time.monotonic() >= retry_deadline:
                    raise RuntimeError(f"grab failed at frame {index}")
                time.sleep(0.05)
            timestamp_ns = time.monotonic_ns()
            decoded, frame = capture.retrieve()
            if not decoded or frame is None:
                raise RuntimeError(f"decode failed at frame {index}")
            if (frame.shape[1], frame.shape[0]) != size:
                raise RuntimeError(
                    f"decoded frame is {frame.shape[1]}x{frame.shape[0]}, "
                    f"expected {size[0]}x{size[1]}"
                )
            if first_timestamp_ns is None:
                first_timestamp_ns = timestamp_ns
            last_timestamp_ns = timestamp_ns

        measured_fps = validate_frame_rate(
            first_timestamp_ns,
            last_timestamp_ns,
            frame_count,
            FPS,
            minimum_fps,
        )
        assert measured_fps is not None
        results[label] = measured_fps
    except Exception as exc:
        errors.append((label, exc))
        try:
            ready_barrier.abort()
        except Exception:
            pass
    finally:
        if capture is not None:
            capture.release()


def run_full_load(args: argparse.Namespace) -> None:
    head, wrists = scan_camera_devices()
    frame_count = max(2, math.ceil(args.seconds * FPS) + 1)
    devices = [
        ("head", head, DEFAULT_STEREO_SIZE),
        *(
            (f"wrist-{index}", device, DEFAULT_WRIST_SIZE)
            for index, device in enumerate(wrists, 1)
        ),
    ]
    workers = [
        ImuWorker(
            label,
            device,
            DEFAULT_HEAD_IMU_INTERVAL_MS
            if label == "head"
            else DEFAULT_WRIST_IMU_INTERVAL_MS,
            read_calibration=label == "head" and not args.skip_head_calibration,
        )
        for label, device, _size in devices
    ]

    print("Preparing IMU workers sequentially...")
    startup_deadline = time.monotonic() + args.startup_timeout
    try:
        for worker in workers:
            worker.start()
            worker.wait_ready(max(0.1, startup_deadline - time.monotonic()))

        ready_barrier = threading.Barrier(4)
        start_event = threading.Event()
        camera_open_timeout = max(30.0, startup_deadline - time.monotonic())
        results: dict[str, float] = {}
        errors: list[tuple[str, Exception]] = []
        threads = [
            threading.Thread(
                target=_capture_video,
                args=(
                    label,
                    device,
                    size,
                    frame_count,
                    args.min_fps,
                    ready_barrier,
                    start_event,
                    camera_open_timeout,
                    results,
                    errors,
                ),
                name=f"video-{label}",
            )
            for label, device, size in devices
        ]
        for thread in threads:
            thread.start()
        try:
            ready_barrier.wait(timeout=camera_open_timeout)
        except threading.BrokenBarrierError as exc:
            if errors:
                label, error = errors[0]
                raise RuntimeError(f"{label} video failed while opening: {error}") from error
            raise RuntimeError("not all camera streams opened") from exc

        for worker in workers:
            worker.start_polling()
            time.sleep(0.05)
        time.sleep(0.2)
        print(f"Streaming all cameras together for approximately {args.seconds:g} seconds...")
        start_event.set()

        join_timeout = args.seconds + 30.0
        for thread in threads:
            thread.join(timeout=join_timeout)
        alive = [thread.name for thread in threads if thread.is_alive()]
        if alive:
            raise RuntimeError("camera thread(s) did not stop: " + ", ".join(alive))
        if errors:
            label, error = errors[0]
            raise RuntimeError(f"{label} video failed: {error}") from error
        for worker in workers:
            worker.validate()
        for label, measured_fps in results.items():
            print(f"{label}: {measured_fps:.3f} FPS")
    finally:
        for worker in workers:
            worker.stop()


def self_test() -> None:
    validate_usb_layout(5, [1, 1])
    validate_usb_layout(5, [1, 3])
    try:
        validate_usb_layout(1, [1, 3])
    except RuntimeError as exc:
        assert "must have its own USB bus" in str(exc)
    else:
        raise AssertionError("shared head/wrist USB bus passed validation")
    print("Self-test passed.")


def main() -> int:
    args = parse_args()
    if args.imu_worker:
        if not args.device_json:
            raise RuntimeError("--imu-worker requires --device-json")
        return imu_worker(
            args.device_json,
            args.poll_interval_ms,
            args.read_calibration,
        )
    if args.self_test:
        self_test()
        return 0

    run_full_load(args)
    print("\nPASS: all three cameras and IMUs sustained the configured hardware load.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise SystemExit(1)
