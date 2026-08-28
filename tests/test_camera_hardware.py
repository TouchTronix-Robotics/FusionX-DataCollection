"""Opt-in pytest suite for all Arducam camera hardware diagnostics."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from test_full_camera_load import scan_camera_paths

FRAME_COUNT = 301
DIAGNOSTIC_TIMEOUT_SECONDS = 240
TESTS_DIR = Path(__file__).resolve().parent
BOLD_RED = "\033[1;31m"
RESET_COLOR = "\033[0m"


def _bold_reason(message: str) -> str:
    return f"{BOLD_RED}Reason: {message}{RESET_COLOR}"


def _run_diagnostic(script: str, *arguments: str) -> None:
    try:
        result = subprocess.run(
            [sys.executable, str(TESTS_DIR / script), *arguments],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=DIAGNOSTIC_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        pytest.fail(
            _bold_reason(
                f"{script} timed out after {DIAGNOSTIC_TIMEOUT_SECONDS} seconds"
            ),
            pytrace=False,
        )

    print(result.stdout, end="", flush=True)
    if result.returncode:
        output_tail = "\n".join(result.stdout.splitlines()[-20:])
        if "LIBUSB_ERROR_ACCESS" in result.stdout:
            message = (
                "Raw USB access required by the head calibration flash transport "
                "was denied."
            )
        else:
            error_line = next(
                (
                    line
                    for line in reversed(result.stdout.splitlines())
                    if "[ERROR]" in line
                ),
                "",
            )
            message = error_line.split("[ERROR]", 1)[-1].strip() or (
                f"{script} exited with code {result.returncode}"
            )
        pytest.fail(
            f"{_bold_reason(message)}\n{script} failed with exit code "
            f"{result.returncode}.\n{output_tail}",
            pytrace=False,
        )


CameraPaths = tuple[str, list[str]]


@pytest.fixture(scope="session")
def camera_paths() -> CameraPaths | Exception:
    try:
        return scan_camera_paths()
    except Exception as exc:
        return exc


def _require_camera_paths(camera_paths: CameraPaths | Exception) -> CameraPaths:
    if isinstance(camera_paths, Exception):
        pytest.skip(f"camera inventory failed: {camera_paths}")
    return camera_paths


def test_camera_inventory(camera_paths: CameraPaths | Exception) -> None:
    if isinstance(camera_paths, Exception):
        pytest.fail(_bold_reason(str(camera_paths)), pytrace=False)


def test_stereo_camera(camera_paths: CameraPaths | Exception) -> None:
    head_path, _ = _require_camera_paths(camera_paths)
    _run_diagnostic(
        "test_stereo_imu_stream.py",
        "--device-path",
        head_path,
        "--headless",
        "--max-frames",
        str(FRAME_COUNT),
        "--print-every",
        str(FRAME_COUNT - 1),
        "--post-calibration-delay",
        "0",
    )


@pytest.mark.parametrize("wrist_index", [0, 1], ids=["wrist-1", "wrist-2"])
def test_wrist_camera(
    camera_paths: CameraPaths | Exception,
    wrist_index: int,
) -> None:
    _, wrist_paths = _require_camera_paths(camera_paths)
    _run_diagnostic(
        "test_wrist_imu_stream.py",
        "--device-path",
        wrist_paths[wrist_index],
        "--headless",
        "--max-frames",
        str(FRAME_COUNT),
        "--print-every",
        str(FRAME_COUNT - 1),
    )


def test_full_camera_load(camera_paths: CameraPaths | Exception) -> None:
    _require_camera_paths(camera_paths)
    _run_diagnostic("test_full_camera_load.py")
