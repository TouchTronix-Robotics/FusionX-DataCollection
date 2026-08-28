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

def _run_diagnostic(script: str, *arguments: str) -> None:
    subprocess.run(
        [sys.executable, str(TESTS_DIR / script), *arguments],
        check=True,
        timeout=DIAGNOSTIC_TIMEOUT_SECONDS,
    )


@pytest.fixture(scope="session")
def camera_paths() -> tuple[str, list[str]]:
    return scan_camera_paths()


def test_stereo_camera(camera_paths: tuple[str, list[str]]) -> None:
    head_path, _ = camera_paths
    _run_diagnostic(
        "test_stereo_imu_stream.py",
        "--device-path",
        head_path,
        "--headless",
        "--max-frames",
        str(FRAME_COUNT),
        "--print-every",
        str(FRAME_COUNT - 1),
        "--imu-interval-ms",
        "3",
        "--post-calibration-delay",
        "0",
    )


@pytest.mark.parametrize("wrist_index", [0, 1], ids=["wrist-1", "wrist-2"])
def test_wrist_camera(
    camera_paths: tuple[str, list[str]],
    wrist_index: int,
) -> None:
    _, wrist_paths = camera_paths
    _run_diagnostic(
        "test_wrist_imu_stream.py",
        "--device-path",
        wrist_paths[wrist_index],
        "--headless",
        "--max-frames",
        str(FRAME_COUNT),
        "--print-every",
        str(FRAME_COUNT - 1),
        "--imu-interval-ms",
        "10",
    )


def test_full_camera_load() -> None:
    _run_diagnostic("test_full_camera_load.py")
