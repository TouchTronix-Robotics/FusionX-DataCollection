#!/usr/bin/env python3
"""
Convert image-per-frame recordings into video files for visualization
and HuggingFace upload.

Encodes RGB frames to H.264 (.mp4) at constant frame rate.  The
``frames.parquet`` is read for metadata and tactile preview rendering
but is **never modified** — all parquet columns (raw + calibrated) are
written at recording time by ``multimodal_app.py``.

Output per recording:
    rgb.mp4              - H.264 at nominal FPS
    preview_glove.mp4    - H.264 pressure heatmap + bend bars (HOT colormap)
    preview_all.mp4      - composite (mono stereo + RGB + glove) for quick inspection
    video_meta.json      - absolute start/end timestamps, fps, stream info

Usage:

    # Record an episode (writes images + parquet directly to disk)
    python multimodal_app.py grasp_cup_01 --glove-port-lh /dev/ttyACM0

    # Convert to videos in-place (writes videos alongside images)
    python post_processing/convert_to_video.py dataset/recording_xxx --calibration calibrations/alice.json

    # Optional: specify fps and quality
    python post_processing/convert_to_video.py dataset/recording_xxx --fps 30 --crf 15 --calibration calibrations/alice.json

Dependencies:
    Python packages: numpy, opencv-python, pyarrow, tqdm
    System executables: ffmpeg and ffprobe on PATH (with libx264 support)
"""

import argparse
import json
import shutil
import subprocess
import sys
from contextlib import contextmanager
from pathlib import Path

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field

try:
    import cv2
    import numpy as np
    import pyarrow as pa
    import pyarrow.parquet as pq
    from tqdm import tqdm
except ModuleNotFoundError as exc:
    print(
        f"ERROR: Missing Python dependency: {exc.name}.\n"
        "Install with: pip install -r post_processing/requirements.txt",
        file=sys.stderr,
    )
    sys.exit(1)

# Standalone copy of the small tactile/calibration helpers needed by this
# converter.  This keeps the public utility independent of the private app
# modules (no depthai, pyserial, GUI, or license dependencies).

# Canonical finger order used by the recorded parquet columns.
FINGER_NAMES = ["thumb", "index", "middle", "ring", "little"]

# Sensor layout constants.
PALM_ROWS = 4
PALM_COLS = 15
FINGER_ROWS = 4
FINGER_COLS = 3

# Rendering constants.
RAW_BEND_MAX = 100.0
BEND_BAR_WIDTH = 20
BEND_BAR_GAP = 4
BEND_BAR_TOP_MARGIN = 20
FINGER_MARGIN = 1
TACTILE_HEIGHT = 240
SEPARATOR_WIDTH = 2
SEPARATOR_GRAY = 80

# Colors (BGR).
BAR_COLOR = (0, 200, 0)
LABEL_COLOR = (200, 200, 200)
LABEL_FONT_SCALE = 0.35
PANEL_LABEL_FONT_SCALE = 0.45


@dataclass
class HandCalibration:
    """Calibration data for one glove hand."""

    bend_min: dict[str, float] = field(default_factory=dict)
    bend_max: dict[str, float] = field(default_factory=dict)
    tactile_zero_finger: dict[str, list[float]] = field(default_factory=dict)
    tactile_zero_palm: list[float] = field(default_factory=list)

    def scale_bend(self, finger: str, raw_value: int) -> float:
        lo = self.bend_min.get(finger, 0)
        hi = self.bend_max.get(finger, 100)
        if hi <= lo:
            return 0.0
        return max(0.0, min(1.0, (raw_value - lo) / (hi - lo)))

    def zero_finger_pressure(self, finger: str, raw_values: list[int]) -> list[int]:
        baseline = self.tactile_zero_finger.get(finger, [0] * len(raw_values))
        return [max(0, int(v - b)) for v, b in zip(raw_values, baseline)]

    def zero_palm_pressure(self, raw_values: list[int]) -> list[int]:
        baseline = self.tactile_zero_palm or [0] * len(raw_values)
        if len(baseline) < len(raw_values):
            baseline = baseline + [0] * (len(raw_values) - len(baseline))
        return [max(0, int(v - b)) for v, b in zip(raw_values, baseline)]


@dataclass
class GloveCalibration:
    """Calibration loaded from calib.json or calibrations/<user>.json."""

    user: str = ""
    timestamp: str = ""
    hands: dict[str, HandCalibration] = field(default_factory=dict)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "user": self.user,
            "timestamp": self.timestamp,
            "gloves": {h: asdict(hc) for h, hc in self.hands.items()},
        }
        path.write_text(json.dumps(data, indent=2))

    @staticmethod
    def load(path: Path) -> "GloveCalibration":
        data = json.loads(path.read_text())
        cal = GloveCalibration(
            user=data.get("user", ""),
            timestamp=data.get("timestamp", ""),
        )
        for hand_label, hd in data.get("gloves", {}).items():
            cal.hands[hand_label] = HandCalibration(
                bend_min=hd.get("bend_min", {}),
                bend_max=hd.get("bend_max", {}),
                tactile_zero_finger=hd.get("tactile_zero_finger", {}),
                tactile_zero_palm=hd.get("tactile_zero_palm", []),
            )
        return cal


def palm_to_grid(palm: list | np.ndarray) -> np.ndarray:
    """Convert 60 palm pressure values to a (4, 15) uint8 grid."""
    return np.array(palm, dtype=np.uint8).reshape(PALM_ROWS, PALM_COLS)


def finger_to_grid(values: list | np.ndarray) -> np.ndarray:
    """Convert 12 finger pressure values to a (4, 3) uint8 grid."""
    return np.array(values, dtype=np.uint8).reshape(FINGER_ROWS, FINGER_COLS)


def apply_calibration_zeroing(
    finger_pressure: dict[str, list[int]],
    palm_pressure: list[int],
    hand_cal: HandCalibration | None,
) -> tuple[dict[str, list[int]], list[int]]:
    """Apply tactile zeroing from calibration, if provided."""
    if hand_cal is None:
        return finger_pressure, palm_pressure
    fp = {
        f: hand_cal.zero_finger_pressure(f, list(finger_pressure[f]))
        for f in FINGER_NAMES
    }
    pp = hand_cal.zero_palm_pressure(list(palm_pressure))
    return fp, pp


def render_pressure_grid(
    finger_pressure: Mapping[str, list | np.ndarray],
    palm_pressure: list | np.ndarray,
    height: int,
    mirror: bool = False,
) -> np.ndarray:
    """Render finger + palm pressure as a HOT-colormap hand heatmap."""
    fingers = {f: finger_to_grid(finger_pressure[f]) for f in FINGER_NAMES}

    if palm_pressure is not None and len(palm_pressure) > 0:
        palm_img = palm_to_grid(palm_pressure)
    else:
        palm_img = np.zeros((PALM_ROWS, PALM_COLS), dtype=np.uint8)

    four_fingers = ["index", "middle", "ring", "little"]
    if mirror:
        four_fingers = list(reversed(four_fingers))
    top_parts: list[np.ndarray] = []
    for i, f in enumerate(four_fingers):
        if i > 0:
            top_parts.append(np.zeros((FINGER_ROWS, FINGER_MARGIN), dtype=np.uint8))
        top_parts.append(fingers[f])
    top_row = np.hstack(top_parts)

    thumb = fingers["thumb"]
    thumb_margin = np.zeros((palm_img.shape[0], FINGER_MARGIN), dtype=np.uint8)
    if mirror:
        bottom_row = np.hstack([palm_img, thumb_margin, thumb])
    else:
        bottom_row = np.hstack([thumb, thumb_margin, palm_img])

    top_w = top_row.shape[1]
    bot_w = bottom_row.shape[1]
    max_w = max(top_w, bot_w)

    margin_row = np.zeros((FINGER_MARGIN, max_w), dtype=np.uint8)
    pad_left = 0

    if top_w < max_w:
        if mirror:
            pad_right = thumb.shape[1] + FINGER_MARGIN
            pad_left = max_w - top_w - pad_right
            if pad_left < 0:
                pad_right = max(0, max_w - top_w)
                pad_left = 0
        else:
            pad_left = thumb.shape[1] + FINGER_MARGIN
            pad_right = max_w - top_w - pad_left
            if pad_right < 0:
                pad_left = max(0, max_w - top_w)
                pad_right = 0
        top_row = np.hstack(
            [
                np.zeros((top_row.shape[0], pad_left), dtype=np.uint8),
                top_row,
                np.zeros((top_row.shape[0], pad_right), dtype=np.uint8),
            ]
        )
    if bot_w < max_w:
        pad = np.zeros((bottom_row.shape[0], max_w - bot_w), dtype=np.uint8)
        bottom_row = np.hstack([bottom_row, pad])

    combined = np.vstack([top_row, margin_row, bottom_row])
    combined = np.pad(combined, pad_width=1, mode="constant", constant_values=0)
    border = 1

    colored = cv2.applyColorMap(combined, cv2.COLORMAP_HOT)
    scale = height / combined.shape[0]
    w = int(combined.shape[1] * scale)
    result = cv2.resize(colored, (w, height), interpolation=cv2.INTER_NEAREST)

    outline_color = (255, 255, 255)

    def _s(v: int) -> int:
        return int(v * scale)

    finger_x0 = pad_left + border
    gy0 = border
    for i in range(4):
        gx = finger_x0 + i * (FINGER_COLS + FINGER_MARGIN)
        cv2.rectangle(
            result,
            (_s(gx), _s(gy0)),
            (_s(gx + FINGER_COLS) - 1, _s(gy0 + FINGER_ROWS) - 1),
            outline_color,
            1,
        )

    bot_y = border + FINGER_ROWS + FINGER_MARGIN
    if mirror:
        palm_x = border
        thumb_x = border + PALM_COLS + FINGER_MARGIN
    else:
        thumb_x = border
        palm_x = border + FINGER_COLS + FINGER_MARGIN
    cv2.rectangle(
        result,
        (_s(thumb_x), _s(bot_y)),
        (_s(thumb_x + FINGER_COLS) - 1, _s(bot_y + FINGER_ROWS) - 1),
        outline_color,
        1,
    )
    cv2.rectangle(
        result,
        (_s(palm_x), _s(bot_y)),
        (_s(palm_x + PALM_COLS) - 1, _s(bot_y + PALM_ROWS) - 1),
        outline_color,
        1,
    )

    return result


def render_bend_bars(
    finger_bend: dict[str, float] | np.ndarray | list,
    height: int,
    mirror: bool = False,
    hand_cal: HandCalibration | None = None,
) -> np.ndarray:
    """Render finger bend as vertical green bars for one hand."""
    if mirror:
        display_order = list(reversed(range(len(FINGER_NAMES))))
    else:
        display_order = list(range(len(FINGER_NAMES)))

    n = len(FINGER_NAMES)
    total_w = n * BEND_BAR_WIDTH + (n - 1) * BEND_BAR_GAP
    img = np.zeros((height, total_w, 3), dtype=np.uint8)

    if isinstance(finger_bend, dict):

        def get_val(idx: int) -> float:
            return finger_bend[FINGER_NAMES[idx]]
    else:

        def get_val(idx: int) -> float:
            return finger_bend[idx]

    usable_h = height - BEND_BAR_TOP_MARGIN
    for pos, idx in enumerate(display_order):
        f = FINGER_NAMES[idx]
        x = pos * (BEND_BAR_WIDTH + BEND_BAR_GAP)
        raw = get_val(idx)

        if hand_cal:
            normalized = hand_cal.scale_bend(f, int(raw))
        else:
            normalized = float(raw) / RAW_BEND_MAX

        bar_h = min(int(normalized * usable_h), usable_h)
        cv2.rectangle(
            img,
            (x, height - bar_h),
            (x + BEND_BAR_WIDTH - 1, height - 1),
            BAR_COLOR,
            -1,
        )
        cv2.putText(
            img,
            f[0].upper(),
            (x + 4, 12),
            cv2.FONT_HERSHEY_SIMPLEX,
            LABEL_FONT_SCALE,
            LABEL_COLOR,
            1,
        )
    return img


def label_panel(img: np.ndarray, text: str) -> None:
    """Draw a small label in the top-left corner of an image in-place."""
    cv2.putText(
        img,
        text,
        (4, 14),
        cv2.FONT_HERSHEY_SIMPLEX,
        PANEL_LABEL_FONT_SCALE,
        LABEL_COLOR,
        1,
    )


def make_separator(height: int) -> np.ndarray:
    """Create a vertical gray separator bar."""
    return np.full((height, SEPARATOR_WIDTH, 3), SEPARATOR_GRAY, dtype=np.uint8)


def assemble_hand_panels(
    panels: list[np.ndarray],
    labels: list[str] | None = None,
) -> np.ndarray:
    """Combine single-hand panels into a multi-hand display."""
    if labels and len(labels) == len(panels):
        for panel, lbl in zip(panels, labels):
            label_panel(panel, lbl)

    if len(panels) == 1:
        return panels[0]

    sep = make_separator(panels[0].shape[0])
    result = panels[0]
    for p in panels[1:]:
        result = np.hstack([result, sep, p])
    return result


def center_pad_width(img: np.ndarray, target_w: int) -> np.ndarray:
    """Pad an image with black columns to center it at target_w."""
    if img.shape[1] >= target_w:
        return img
    total_pad = target_w - img.shape[1]
    left = total_pad // 2
    right = total_pad - left
    return np.hstack(
        [
            np.zeros((img.shape[0], left, 3), dtype=np.uint8),
            img,
            np.zeros((img.shape[0], right, 3), dtype=np.uint8),
        ]
    )

# On Windows, prevent subprocess calls from spawning visible console windows.
_SUBPROCESS_FLAGS: dict[str, int] = {}
if sys.platform == "win32":
    _SUBPROCESS_FLAGS["creationflags"] = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]


@contextmanager
def _pipe_to_ffmpeg(
    width: int,
    height: int,
    fps: int,
    crf: int,
    output_file: Path,
):
    """Context manager that pipes raw BGR24 frames to an ffmpeg H.264 encoder.

    Usage::

        with _pipe_to_ffmpeg(w, h, fps, crf, out) as write_frame:
            for frame in frames:
                write_frame(frame)
    """
    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "bgr24",
        "-s",
        f"{width}x{height}",
        "-r",
        str(fps),
        "-i",
        "pipe:0",
        "-c:v",
        "libx264",
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        str(output_file),
    ]
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
        **_SUBPROCESS_FLAGS,
    )

    def write_frame(frame: np.ndarray):
        proc.stdin.write(frame.tobytes())

    try:
        yield write_frame
    finally:
        proc.stdin.close()
        proc.wait()
        if proc.returncode != 0:
            raise subprocess.CalledProcessError(proc.returncode, cmd)


def read_parquet(parquet_path: Path) -> pa.Table:
    """Read the full frames.parquet table, handling duplicate columns."""
    pf = pq.ParquetFile(parquet_path)
    table = pf.read()
    # Deduplicate columns if needed (keep first occurrence)
    col_names = table.column_names
    if len(col_names) != len(set(col_names)):
        seen = {}
        unique_cols = []
        unique_names = []
        for i, name in enumerate(col_names):
            if name not in seen:
                seen[name] = i
                unique_cols.append(i)
                unique_names.append(name)
        cols = [table.column(i) for i in unique_cols]
        table = pa.table(cols, names=unique_names)
    return table


def _run_ffmpeg_with_progress(cmd: list[str], n_frames: int, desc: str) -> None:
    """Run an ffmpeg command while showing a tqdm progress bar.

    Appends ``-progress pipe:1`` to *cmd* and parses the ``frame=N``
    lines emitted by ffmpeg to update the bar.
    """
    cmd_prog = cmd + ["-progress", "pipe:1"]
    proc = subprocess.Popen(
        cmd_prog,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        **_SUBPROCESS_FLAGS,
    )
    bar = tqdm(total=n_frames, desc=desc, unit="frame")
    assert proc.stdout is not None
    for line in proc.stdout:
        text = line.decode("utf-8", errors="replace").strip()
        if text.startswith("frame="):
            try:
                frame_num = int(text.split("=", 1)[1])
                bar.update(frame_num - bar.n)
            except ValueError:
                pass
    proc.wait()
    bar.update(n_frames - bar.n)  # ensure bar reaches 100%
    bar.close()
    if proc.returncode != 0:
        raise subprocess.CalledProcessError(proc.returncode, cmd)


def encode_rgb(
    input_pattern: str,
    output_file: Path,
    fps: int,
    crf: int,
    start_number: int = 0,
    n_frames: int = 0,
) -> None:
    """Encode RGB images to H.264 mp4 at constant frame rate."""
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-start_number",
        str(start_number),
        "-i",
        input_pattern,
        "-c:v",
        "libx264",
        "-crf",
        str(crf),
        "-pix_fmt",
        "yuv420p",
        str(output_file),
    ]
    if n_frames > 0:
        _run_ffmpeg_with_progress(cmd, n_frames, "    RGB encode")
    else:
        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            **_SUBPROCESS_FLAGS,
        )


def _detect_hands(table: pa.Table) -> list[str]:
    """Detect which hand prefixes (lh, rh) are present in the parquet."""
    hands = []
    for hand in ("lh", "rh"):
        if f"{hand}_thumb_pressure" in table.column_names:
            hands.append(hand)
    return hands


def _render_tactile_frame(
    table: pa.Table,
    row: int,
    hands: list[str],
    height: int,
    calibration: GloveCalibration | None = None,
) -> np.ndarray:
    """Render one tactile preview frame for all active hands.

    Returns a BGR image with pressure heatmap + bend bars per hand,
    stacked side-by-side if dual-glove.

    When *calibration* is provided, tactile values are zeroed and bend
    bars are scaled to 0.0-1.0.
    """
    hand_panels = []
    labels = []
    for hand in hands:
        hand_cal = calibration.hands.get(hand) if calibration else None

        # Extract pressure data for this row
        raw_fp = {
            f: table.column(f"{hand}_{f}_pressure")[row].as_py() for f in FINGER_NAMES
        }
        raw_pp = table.column(f"{hand}_palm_pressure")[row].as_py()
        fp, pp = apply_calibration_zeroing(raw_fp, raw_pp, hand_cal)

        bend_col = table.column(f"{hand}_finger_bend")
        bend = np.array(bend_col[row].as_py(), dtype=np.int32)

        half_h = height // 2
        mirror = hand == "lh"
        pressure = render_pressure_grid(fp, pp, half_h, mirror=mirror)
        bars = render_bend_bars(bend, height - half_h, mirror=mirror, hand_cal=hand_cal)

        # Ensure same width, centering the narrower one
        max_w = max(pressure.shape[1], bars.shape[1])
        pressure = center_pad_width(pressure, max_w)
        bars = center_pad_width(bars, max_w)

        hand_panels.append(np.vstack([pressure, bars]))
        labels.append(hand.upper())

    return assemble_hand_panels(hand_panels, labels if len(hands) > 1 else None)


def encode_tactile_preview(
    table: pa.Table,
    hands: list[str],
    n_frames: int,
    output_file: Path,
    fps: int,
    crf: int,
    calibration: GloveCalibration | None = None,
) -> None:
    """Encode a tactile preview video from parquet data.

    Renders pressure heatmap (COLORMAP_HOT) + bend bars per hand,
    matching preview.py's layout.  When *calibration* is provided,
    tactile values are zeroed and bend bars scaled to 0.0-1.0.
    """
    # Render first frame to get dimensions
    first_frame = _render_tactile_frame(
        table, 0, hands, TACTILE_HEIGHT, calibration=calibration
    )
    h, w = first_frame.shape[:2]

    label = "    Glove calibrated"
    with _pipe_to_ffmpeg(w, h, fps, crf, output_file) as write_frame:
        write_frame(first_frame)
        for i in tqdm(
            range(1, n_frames), desc=label, unit="frame", initial=1, total=n_frames
        ):
            frame = _render_tactile_frame(
                table, i, hands, TACTILE_HEIGHT, calibration=calibration
            )
            write_frame(frame)


PREVIEW_DURATION_S: int | None = None  # None = full length, or set integer seconds
PREVIEW_ROW_HEIGHT = 360  # height of each row in the composite preview


def encode_composite_preview(
    rec_dir: Path,
    table: pa.Table,
    hands: list[str],
    n_frames: int,
    output_file: Path,
    fps: int,
    crf: int,
    start_number: int = 0,
    calibration: GloveCalibration | None = None,
) -> None:
    """Encode a composite preview: mono stereo on top, RGB below, glove at bottom.

    If PREVIEW_DURATION_S is set, limits to that many seconds.  When
    *calibration* is provided, the glove section shows zeroed tactile
    values and bend bars scaled to 0.0-1.0.  Layout:

        ┌─────────────┬─────────────┐
        │  Mono Left   │ Mono Right  │  (scaled to top_w, preserving aspect)
        ├─────────────┴─────────────┤
        │           RGB             │  (scaled to top_w, preserving aspect)
        ├───────────────────────────┤
        │       Glove Preview       │  (scaled to match top row width)
        └───────────────────────────┘
    """
    if PREVIEW_DURATION_S is not None:
        preview_frames = min(n_frames, fps * PREVIEW_DURATION_S)
    else:
        preview_frames = n_frames
    row_h = PREVIEW_ROW_HEIGHT

    # Read first RGB to get aspect ratio
    first_rgb = cv2.imread(str(rec_dir / "rgb" / f"{start_number:06d}.jpg"))
    orig_h, orig_w = first_rgb.shape[:2]

    has_glove = len(hands) > 0
    has_mono = (rec_dir / "mono_left").exists() and (rec_dir / "mono_right").exists()

    # Compute mono row dimensions
    mono_row_h = 0
    if has_mono:
        first_mono = cv2.imread(
            str(rec_dir / "mono_left" / f"{start_number:06d}.png"),
            cv2.IMREAD_GRAYSCALE,
        )
        if first_mono is not None:
            mono_orig_h, mono_orig_w = first_mono.shape[:2]
            # Each mono panel is half the top width
            mono_panel_w_target = int(orig_w * row_h / orig_h)
            top_w = mono_panel_w_target * 2
            mono_scale = mono_panel_w_target / mono_orig_w
            mono_row_h = int(mono_orig_h * mono_scale)
        else:
            has_mono = False

    if not has_mono:
        # Fall back: top_w based on RGB scaled to row_h
        rgb_scale = row_h / orig_h
        top_w = int(orig_w * rgb_scale)

    # RGB row: scale to full top_w
    rgb_scale = top_w / orig_w
    rgb_row_h = int(orig_h * rgb_scale)

    # Render first glove frame to get its native size
    if has_glove:
        glove_frame_0 = _render_tactile_frame(
            table, 0, hands, row_h, calibration=calibration
        )
        glove_native_h, glove_native_w = glove_frame_0.shape[:2]
        glove_scale = top_w / glove_native_w
        glove_h = int(glove_native_h * glove_scale)
    else:
        glove_h = 0

    total_h = mono_row_h + rgb_row_h + glove_h
    # Ensure even dimensions for H.264
    total_h = total_h + (total_h % 2)
    top_w = top_w + (top_w % 2)

    label = "    Calibrated composite"
    with _pipe_to_ffmpeg(top_w, total_h, fps, crf, output_file) as write_frame:
        for i in tqdm(range(preview_frames), desc=label, unit="frame"):
            file_idx = start_number + i

            rows: list[np.ndarray] = []

            # Mono stereo row (top)
            if has_mono:
                mono_panel_w = top_w // 2
                ml = cv2.imread(
                    str(rec_dir / "mono_left" / f"{file_idx:06d}.png"),
                    cv2.IMREAD_GRAYSCALE,
                )
                mr = cv2.imread(
                    str(rec_dir / "mono_right" / f"{file_idx:06d}.png"),
                    cv2.IMREAD_GRAYSCALE,
                )
                ml_resized = cv2.resize(ml, (mono_panel_w, mono_row_h))
                mr_resized = cv2.resize(mr, (mono_panel_w, mono_row_h))
                ml_bgr = cv2.cvtColor(ml_resized, cv2.COLOR_GRAY2BGR)
                mr_bgr = cv2.cvtColor(mr_resized, cv2.COLOR_GRAY2BGR)
                mono_row = np.hstack([ml_bgr, mr_bgr])
                if mono_row.shape[1] != top_w:
                    mono_row = cv2.resize(mono_row, (top_w, mono_row_h))
                rows.append(mono_row)

            # RGB row (full width)
            rgb = cv2.imread(str(rec_dir / "rgb" / f"{file_idx:06d}.jpg"))
            rgb_resized = cv2.resize(rgb, (top_w, rgb_row_h))
            rows.append(rgb_resized)

            # Glove row
            if has_glove:
                glove_frame = _render_tactile_frame(
                    table, i, hands, row_h, calibration=calibration
                )
                glove_resized = cv2.resize(glove_frame, (top_w, glove_h))
                rows.append(glove_resized)

            composite = np.vstack(rows)

            # Pad to exact total_h if needed
            if composite.shape[0] != total_h:
                pad = np.zeros((total_h - composite.shape[0], top_w, 3), dtype=np.uint8)
                composite = np.vstack([composite, pad])

            write_frame(composite)


def verify_frame_count(video_path: Path, expected: int) -> int:
    """Verify the encoded video has the expected number of frames."""
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-count_frames",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=nb_read_frames",
            "-of",
            "csv=p=0",
            str(video_path),
        ],
        capture_output=True,
        text=True,
        **_SUBPROCESS_FLAGS,
    )
    actual = int(result.stdout.strip())
    if actual != expected:
        print(
            f"  WARNING: {video_path.name} has {actual} frames, expected {expected}",
            file=sys.stderr,
        )
    return actual


def write_video_meta(
    meta_path: Path,
    timestamps: np.ndarray,
    n_frames: int,
    fps: int,
    crf: int,
    has_rgb: bool,
    has_mono: bool,
    hands: list[str] | None = None,
    calibration: GloveCalibration | None = None,
) -> None:
    """Write video_meta.json with absolute start timestamp and stream info."""
    duration_s = float(timestamps[-1] - timestamps[0]) if n_frames > 1 else 0.0
    measured_fps = (n_frames - 1) / duration_s if duration_s > 0 else 0.0

    meta = {
        "video_start_timestamp": float(timestamps[0]),
        "video_end_timestamp": float(timestamps[-1]),
        "num_frames": n_frames,
        "duration_s": round(duration_s, 4),
        "measured_fps": round(measured_fps, 4),
        "video_fps": fps,
        "streams": {},
    }
    if has_rgb:
        meta["streams"]["rgb"] = {
            "file": "rgb.mp4",
            "codec": "libx264",
            "crf": crf,
            "pix_fmt": "yuv420p",
        }
    if hands:
        meta["streams"]["preview_glove"] = {
            "file": "preview_glove.mp4",
            "codec": "libx264",
            "crf": crf,
            "pix_fmt": "yuv420p",
            "hands": hands,
            "colormap": "HOT",
            "note": "Pressure heatmap + bend bars, for visualization only",
        }
    if has_rgb:
        if PREVIEW_DURATION_S is not None:
            preview_frames = min(n_frames, fps * PREVIEW_DURATION_S)
        else:
            preview_frames = n_frames
        meta["streams"]["preview_all"] = {
            "file": "preview_all.mp4",
            "codec": "libx264",
            "crf": crf,
            "pix_fmt": "yuv420p",
            "num_frames": preview_frames,
            "duration_s": round(preview_frames / fps, 2),
            "has_mono_stereo": has_mono,
            "note": "Composite mono stereo + RGB + glove",
        }
    if hands and calibration:
        meta["calibration"] = {
            "user": calibration.user,
            "timestamp": calibration.timestamp,
        }
    meta_path.write_text(json.dumps(meta, indent=2))


def _subsample_indices(timestamps: np.ndarray, target_fps: int) -> np.ndarray:
    """Compute indices to subsample a high-rate signal to target_fps.

    Uses nearest-neighbor selection on a uniform grid spanning the
    recording duration, so the output plays back at real-time speed
    when encoded at target_fps.
    """
    t0 = timestamps[0]
    duration = timestamps[-1] - t0
    n_out = max(1, int(round(duration * target_fps)))
    target_times = np.linspace(t0, timestamps[-1], n_out)
    indices = np.searchsorted(timestamps, target_times, side="right") - 1
    indices = np.clip(indices, 0, len(timestamps) - 1)
    return indices


def process_recording(
    rec_dir: Path,
    target_dir: Path,
    fps: int,
    crf: int,
    calibration: GloveCalibration | None = None,
) -> None:
    """Convert one recording from image-per-frame to video.

    Encodes at constant ``fps``.  The original ``frames.parquet`` is read
    for metadata and tactile rendering but is **never modified** — all
    parquet columns (raw + calibrated) are written at recording time.

    For glove-only recordings (no camera images), the full-rate glove data
    is subsampled to ``fps`` for the video preview.
    """
    parquet_path = rec_dir / "frames.parquet"
    if not parquet_path.exists():
        print(f"  WARNING: No frames.parquet in {rec_dir}, skipping")
        return

    # Skip if already converted (video_meta.json exists)
    if (target_dir / "video_meta.json").exists():
        print("  Already converted, skipping (delete video_meta.json to reconvert)")
        return

    table = read_parquet(parquet_path)

    n_frames = table.num_rows
    if n_frames == 0:
        print(f"  WARNING: Empty parquet in {rec_dir}, skipping")
        return

    timestamps = table.column("timestamp").to_numpy()
    target_dir.mkdir(parents=True, exist_ok=True)

    has_rgb = (rec_dir / "rgb").exists() and any((rec_dir / "rgb").iterdir())
    has_mono = (rec_dir / "mono_left").exists() and (rec_dir / "mono_right").exists()
    is_glove_only = not has_rgb

    # For glove-only recordings, subsample to target fps for video encoding
    # but keep the full-rate table for the output parquet.
    sub_idx = None  # indices into full-rate table used for video frames
    video_table = table  # table used for video encoding (may be subsampled)
    n_video_frames = n_frames
    if is_glove_only and n_frames > 1:
        duration_s = timestamps[-1] - timestamps[0]
        data_fps = (n_frames - 1) / duration_s if duration_s > 0 else fps
        if data_fps > fps * 1.5:  # only subsample if significantly faster
            sub_idx = _subsample_indices(timestamps, fps)
            n_video_frames = len(sub_idx)
            video_table = table.take(sub_idx)
            print(
                f"  > Subsampling {n_frames} frames ({data_fps:.0f} Hz) "
                f"-> {n_video_frames} frames ({fps} Hz) for video"
            )

    # Detect start number from first file on disk (handles partial recordings)
    start_number = 0
    if has_rgb:
        first_rgb = min((rec_dir / "rgb").iterdir(), key=lambda p: p.name)
        start_number = int(first_rgb.stem)

    # Encode videos at constant frame rate
    if has_rgb:
        print(f"  > Encoding RGB video ({n_frames} frames @ {fps} fps)...")
        encode_rgb(
            str(rec_dir / "rgb" / "%06d.jpg"),
            target_dir / "rgb.mp4",
            fps,
            crf,
            start_number=start_number,
            n_frames=n_frames,
        )
        verify_frame_count(target_dir / "rgb.mp4", n_frames)

    # Encode tactile preview if glove data is present
    hands = _detect_hands(table)
    if hands:
        hand_str = "+".join(h.upper() for h in hands)
        print(f"  > Encoding preview_glove ({n_video_frames} frames, {hand_str})...")
        encode_tactile_preview(
            video_table,
            hands,
            n_video_frames,
            target_dir / "preview_glove.mp4",
            fps,
            crf,
            calibration=calibration,
        )
        verify_frame_count(target_dir / "preview_glove.mp4", n_video_frames)

    # Composite preview
    if has_rgb:
        if PREVIEW_DURATION_S is not None:
            preview_n = min(n_frames, fps * PREVIEW_DURATION_S)
        else:
            preview_n = n_frames
        print(f"  > Encoding preview_all ({preview_n} frames)...")
        encode_composite_preview(
            rec_dir,
            table,
            hands,
            n_frames,
            target_dir / "preview_all.mp4",
            fps,
            crf,
            start_number=start_number,
            calibration=calibration,
        )

    # Write video metadata with absolute start timestamp
    write_video_meta(
        target_dir / "video_meta.json",
        timestamps,
        n_video_frames,
        fps,
        crf,
        has_rgb,
        has_mono,
        hands=hands if hands else None,
        calibration=calibration,
    )

    duration_s = timestamps[-1] - timestamps[0]
    measured = (n_frames - 1) / duration_s if duration_s > 0 else 0
    print(
        f"  > video_meta.json: start_ts={timestamps[0]:.3f}, "
        f"measured_fps={measured:.2f}, video_fps={fps}"
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Convert a TouchTronix image-per-frame episode to MP4 preview videos."
    )
    parser.add_argument(
        "source",
        type=Path,
        help="Episode folder to convert (writes videos alongside images)",
    )
    parser.add_argument(
        "--fps",
        type=int,
        default=30,
        help="Video frame rate (default: 30)",
    )
    parser.add_argument(
        "--crf",
        type=int,
        default=15,
        help="H.264 CRF quality for RGB (default: 15, lower=better)",
    )
    parser.add_argument(
        "--calibration",
        type=str,
        default=None,
        metavar="FILE",
        help="Calibration JSON file (default: auto-detect calib.json in episode folder)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    # Verify ffmpeg/ffprobe are available before doing any work
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            print(
                f"ERROR: '{tool}' not found on PATH. "
                "Install ffmpeg (https://ffmpeg.org) and ensure it is on your PATH.",
                file=sys.stderr,
            )
            sys.exit(1)

    if not args.source.is_dir():
        print(f"ERROR: Source directory not found: {args.source}", file=sys.stderr)
        sys.exit(1)

    if not (args.source / "frames.parquet").exists():
        print(
            f"ERROR: No frames.parquet in {args.source}. "
            "Pass an episode folder, not a dataset folder.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Load calibration (auto-detect from episode folder or use override)
    calibration = None
    if args.calibration:
        cal_file = Path(args.calibration)
    else:
        cal_file = args.source / "calib.json"

    if cal_file.is_file():
        calibration = GloveCalibration.load(cal_file)
        print(f"Loaded calibration: {cal_file} (user: {calibration.user})\n")
    else:
        print("No calibration file found, encoding without calibration\n")

    print(f"--- {args.source.name} ---")
    process_recording(
        args.source, args.source, args.fps, args.crf, calibration=calibration
    )
    print(f"Done! Videos written to {args.source}")


if __name__ == "__main__":
    main()
