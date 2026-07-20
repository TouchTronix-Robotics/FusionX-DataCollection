#!/usr/bin/env python3
"""Export TouchTronix raw MCAP captures back to episode files.

This derives episode artifacts from current-format MCAP recordings:
``rgb/``, ``mono_left/``, ``mono_right/``, ``frames.parquet``,
``gloves.parquet``, ``oak_imu.parquet``, and calibration JSON files.

Standalone runtime dependencies: mcap, protobuf, numpy, and pyarrow.
"""

from __future__ import annotations

import argparse
import glob
import json
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from mcap.reader import make_reader

import foxglove_pb2

# Keep exporter standalone: duplicate protocol constants instead of importing
# glove_reader/oak_reader, which require hardware-facing dependencies.
FINGER_NAMES = ["thumb", "index", "middle", "ring", "little"]

_CAMERA_IMAGE_TOPICS = {
    "/oak/rgb/jpeg": "rgb_path",
    "/oak/mono_left/jpeg": "mono_left_path",
    "/oak/mono_right/jpeg": "mono_right_path",
}

_CALIBRATION_TOPICS = {
    "/calibration/glove/user/json": "user_calibration.json",
    "/calibration/glove/force/json": "force_calibration.json",
    "/calibration/camera/json": "camera_calibration.json",
}


@dataclass(frozen=True)
class OakImuSample:
    """Standalone OAK IMU sample DTO used for MCAP export only."""

    accel_timestamp: float
    accel: tuple[float, float, float]
    gyro_timestamp: float
    gyro: tuple[float, float, float]
    game_rotation_quaternion: tuple[float, float, float, float] | None = None
    game_rotation_timestamp: float | None = None
    game_rotation_accuracy: int | None = None


def _optional_f32(value: tuple | list | None) -> np.ndarray | None:
    return np.array(value, dtype=np.float32) if value is not None else None


def _optional_nested_f32(value: list[list[float]] | None) -> list[list[float]] | None:
    if value is None:
        return None
    return np.asarray(value, dtype=np.float32).tolist()


def _is_finite_number(value: float | None) -> bool:
    return value is not None and np.isfinite(value)


def _align_nearest(ref_ts: np.ndarray, src_ts: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Align *src* timestamps to *ref* timestamps by nearest neighbor."""
    ref = np.asarray(ref_ts, dtype=np.float64)
    src = np.asarray(src_ts, dtype=np.float64)
    right_idx = np.searchsorted(src, ref, side="left")
    right_idx = np.clip(right_idx, 0, len(src) - 1)
    left_idx = np.clip(right_idx - 1, 0, len(src) - 1)
    dt_left = np.abs(ref - src[left_idx])
    dt_right = np.abs(ref - src[right_idx])
    indices = np.where(dt_left <= dt_right, left_idx, right_idx)
    dt_ms = ((src[indices] - ref) * 1000.0).astype(np.float32)
    return indices, dt_ms


@dataclass
class ImuAccumulator:
    """Accumulate full-rate OAK IMU samples for oak_imu.parquet export."""

    _accel_timestamps: list[float] = field(default_factory=list)
    _accel_x: list[float] = field(default_factory=list)
    _accel_y: list[float] = field(default_factory=list)
    _accel_z: list[float] = field(default_factory=list)
    _gyro_timestamps: list[float] = field(default_factory=list)
    _gyro_x: list[float] = field(default_factory=list)
    _gyro_y: list[float] = field(default_factory=list)
    _gyro_z: list[float] = field(default_factory=list)
    _game_rotation_timestamp: list[float | None] = field(default_factory=list)
    _game_rotation_w: list[float | None] = field(default_factory=list)
    _game_rotation_x: list[float | None] = field(default_factory=list)
    _game_rotation_y: list[float | None] = field(default_factory=list)
    _game_rotation_z: list[float | None] = field(default_factory=list)
    _game_rotation_accuracy: list[int | None] = field(default_factory=list)

    def add_sample(self, sample: OakImuSample) -> None:
        if not (
            _is_finite_number(sample.accel_timestamp)
            and _is_finite_number(sample.gyro_timestamp)
        ):
            return
        self._accel_timestamps.append(float(sample.accel_timestamp))
        self._accel_x.append(sample.accel[0])
        self._accel_y.append(sample.accel[1])
        self._accel_z.append(sample.accel[2])
        self._gyro_timestamps.append(float(sample.gyro_timestamp))
        self._gyro_x.append(sample.gyro[0])
        self._gyro_y.append(sample.gyro[1])
        self._gyro_z.append(sample.gyro[2])
        if sample.game_rotation_quaternion is None:
            game_rotation_w = None
            game_rotation_x = None
            game_rotation_y = None
            game_rotation_z = None
        else:
            (
                game_rotation_w,
                game_rotation_x,
                game_rotation_y,
                game_rotation_z,
            ) = sample.game_rotation_quaternion
        self._game_rotation_timestamp.append(
            float(sample.game_rotation_timestamp)
            if _is_finite_number(sample.game_rotation_timestamp)
            else None
        )
        self._game_rotation_w.append(game_rotation_w)
        self._game_rotation_x.append(game_rotation_x)
        self._game_rotation_y.append(game_rotation_y)
        self._game_rotation_z.append(game_rotation_z)
        self._game_rotation_accuracy.append(sample.game_rotation_accuracy)

    @property
    def sample_count(self) -> int:
        return len(self._accel_timestamps)

    def to_table(self) -> pa.Table:
        return pa.table({
            "accel_timestamp": pa.array(self._accel_timestamps, type=pa.float64()),
            "accel_x": pa.array(self._accel_x, type=pa.float64()),
            "accel_y": pa.array(self._accel_y, type=pa.float64()),
            "accel_z": pa.array(self._accel_z, type=pa.float64()),
            "gyro_timestamp": pa.array(self._gyro_timestamps, type=pa.float64()),
            "gyro_x": pa.array(self._gyro_x, type=pa.float64()),
            "gyro_y": pa.array(self._gyro_y, type=pa.float64()),
            "gyro_z": pa.array(self._gyro_z, type=pa.float64()),
            "game_rotation_timestamp": pa.array(
                self._game_rotation_timestamp, type=pa.float64()
            ),
            "game_rotation_w": pa.array(self._game_rotation_w, type=pa.float64()),
            "game_rotation_x": pa.array(self._game_rotation_x, type=pa.float64()),
            "game_rotation_y": pa.array(self._game_rotation_y, type=pa.float64()),
            "game_rotation_z": pa.array(self._game_rotation_z, type=pa.float64()),
            "game_rotation_accuracy": pa.array(
                self._game_rotation_accuracy, type=pa.int16()
            ),
        })


@dataclass
class GloveAccumulator:
    """Accumulate one hand's glove samples for parquet export."""

    hand: str
    _timestamps: list[float] = field(default_factory=list)
    _finger_pressure: dict[str, list[np.ndarray]] = field(
        default_factory=lambda: {f: [] for f in FINGER_NAMES}
    )
    _palm_pressure: list[np.ndarray] = field(default_factory=list)
    _finger_bend: list[np.ndarray] = field(default_factory=list)
    _imu_quaternion: list[np.ndarray | None] = field(default_factory=list)
    _imu_gyro: list[np.ndarray | None] = field(default_factory=list)
    _imu_accel: list[np.ndarray | None] = field(default_factory=list)
    _finger_force_N_total: list[np.ndarray | None] = field(default_factory=list)
    _finger_force_N_pixels: list[list[list[float]] | None] = field(
        default_factory=list
    )

    def add_frame(
        self,
        timestamp: float,
        finger_pressure: dict[str, list[int]],
        palm_pressure: list[int],
        finger_bend: dict[str, int],
        imu_quaternion: tuple[float, ...] | None = None,
        imu_gyro: tuple[float, ...] | None = None,
        imu_accel: tuple[float, ...] | None = None,
        finger_force_N_total: list[float] | None = None,
        finger_force_N_pixels: list[list[float]] | None = None,
    ) -> None:
        self._timestamps.append(timestamp)
        for finger in FINGER_NAMES:
            self._finger_pressure[finger].append(
                np.array(finger_pressure[finger], dtype=np.uint8)
            )
        self._palm_pressure.append(np.array(palm_pressure, dtype=np.uint8))
        self._finger_bend.append(
            np.array([finger_bend[finger] for finger in FINGER_NAMES], dtype=np.int32)
        )
        self._imu_quaternion.append(_optional_f32(imu_quaternion))
        self._imu_gyro.append(_optional_f32(imu_gyro))
        self._imu_accel.append(_optional_f32(imu_accel))
        self._finger_force_N_total.append(_optional_f32(finger_force_N_total))
        self._finger_force_N_pixels.append(
            _optional_nested_f32(finger_force_N_pixels)
        )

    @property
    def frame_count(self) -> int:
        return len(self._timestamps)

    @property
    def timestamps(self) -> np.ndarray:
        return np.array(self._timestamps, dtype=np.float64)

    def aligned_columns(self, camera_timestamps: np.ndarray) -> dict[str, pa.Array]:
        n = len(camera_timestamps)
        if self.frame_count == 0:
            return self._null_columns(n)
        indices, dt_ms = _align_nearest(camera_timestamps, self.timestamps)
        hand = self.hand
        cols: dict[str, pa.Array] = {
            f"{hand}_glove_timestamp": pa.array(
                self.timestamps[indices], type=pa.float64()
            ),
            f"{hand}_glove_dt_ms": pa.array(dt_ms, type=pa.float32()),
        }
        for finger in FINGER_NAMES:
            cols[f"{hand}_{finger}_pressure"] = pa.array(
                [self._finger_pressure[finger][i] for i in indices],
                type=pa.list_(pa.uint8()),
            )
        cols[f"{hand}_palm_pressure"] = pa.array(
            [self._palm_pressure[i] for i in indices], type=pa.list_(pa.uint8())
        )
        cols[f"{hand}_finger_bend"] = pa.array(
            [self._finger_bend[i] for i in indices], type=pa.list_(pa.int32())
        )
        cols[f"{hand}_imu_quaternion"] = pa.array(
            [self._imu_quaternion[i] for i in indices], type=pa.list_(pa.float32())
        )
        cols[f"{hand}_imu_gyro"] = pa.array(
            [self._imu_gyro[i] for i in indices], type=pa.list_(pa.float32())
        )
        cols[f"{hand}_imu_accel"] = pa.array(
            [self._imu_accel[i] for i in indices], type=pa.list_(pa.float32())
        )
        cols[f"{hand}_finger_force_N_total"] = pa.array(
            [self._finger_force_N_total[i] for i in indices],
            type=pa.list_(pa.float32()),
        )
        cols[f"{hand}_finger_force_N_pixels"] = pa.array(
            [self._finger_force_N_pixels[i] for i in indices],
            type=pa.list_(pa.list_(pa.float32())),
        )
        return cols

    def _null_columns(self, n: int) -> dict[str, pa.Array]:
        hand = self.hand
        cols: dict[str, pa.Array] = {
            f"{hand}_glove_timestamp": pa.nulls(n, type=pa.float64()),
            f"{hand}_glove_dt_ms": pa.nulls(n, type=pa.float32()),
        }
        for finger in FINGER_NAMES:
            cols[f"{hand}_{finger}_pressure"] = pa.nulls(n, type=pa.list_(pa.uint8()))
        cols[f"{hand}_palm_pressure"] = pa.nulls(n, type=pa.list_(pa.uint8()))
        cols[f"{hand}_finger_bend"] = pa.nulls(n, type=pa.list_(pa.int32()))
        cols[f"{hand}_imu_quaternion"] = pa.nulls(n, type=pa.list_(pa.float32()))
        cols[f"{hand}_imu_gyro"] = pa.nulls(n, type=pa.list_(pa.float32()))
        cols[f"{hand}_imu_accel"] = pa.nulls(n, type=pa.list_(pa.float32()))
        cols[f"{hand}_finger_force_N_total"] = pa.nulls(
            n, type=pa.list_(pa.float32())
        )
        cols[f"{hand}_finger_force_N_pixels"] = pa.nulls(
            n, type=pa.list_(pa.list_(pa.float32()))
        )
        return cols

    def raw_rows(self) -> list[dict[str, Any]]:
        rows = []
        for idx, timestamp in enumerate(self._timestamps):
            row: dict[str, Any] = {
                "hand": self.hand,
                "timestamp": timestamp,
                "palm_pressure": self._palm_pressure[idx],
                "finger_bend": self._finger_bend[idx],
                "imu_quaternion": self._imu_quaternion[idx],
                "imu_gyro": self._imu_gyro[idx],
                "imu_accel": self._imu_accel[idx],
                "finger_force_N_total": self._finger_force_N_total[idx],
                "finger_force_N_pixels": self._finger_force_N_pixels[idx],
            }
            for finger in FINGER_NAMES:
                row[f"{finger}_pressure"] = self._finger_pressure[finger][idx]
            rows.append(row)
        return rows


def write_gloves_parquet(
    output_dir: Path, glove_accumulators: dict[str, GloveAccumulator] | None
) -> None:
    """Write gloves.parquet with raw-rate glove samples."""
    rows = []
    for hand in sorted(glove_accumulators or {}):
        acc = glove_accumulators[hand]
        if acc.frame_count:
            rows.extend(acc.raw_rows())
    if not rows:
        return
    rows.sort(key=lambda row: (row["timestamp"], row["hand"]))
    columns: dict[str, pa.Array] = {
        "hand": pa.array([row["hand"] for row in rows], type=pa.string()),
        "timestamp": pa.array([row["timestamp"] for row in rows], type=pa.float64()),
    }
    for finger in FINGER_NAMES:
        columns[f"{finger}_pressure"] = pa.array(
            [row[f"{finger}_pressure"] for row in rows], type=pa.list_(pa.uint8())
        )
    columns["palm_pressure"] = pa.array(
        [row["palm_pressure"] for row in rows], type=pa.list_(pa.uint8())
    )
    columns["finger_bend"] = pa.array(
        [row["finger_bend"] for row in rows], type=pa.list_(pa.int32())
    )
    columns["imu_quaternion"] = pa.array(
        [row["imu_quaternion"] for row in rows], type=pa.list_(pa.float32())
    )
    columns["imu_gyro"] = pa.array(
        [row["imu_gyro"] for row in rows], type=pa.list_(pa.float32())
    )
    columns["imu_accel"] = pa.array(
        [row["imu_accel"] for row in rows], type=pa.list_(pa.float32())
    )
    columns["finger_force_N_total"] = pa.array(
        [row["finger_force_N_total"] for row in rows],
        type=pa.list_(pa.float32()),
    )
    columns["finger_force_N_pixels"] = pa.array(
        [row["finger_force_N_pixels"] for row in rows],
        type=pa.list_(pa.list_(pa.float32())),
    )
    pq.write_table(pa.table(columns), output_dir / "gloves.parquet")


def write_oak_imu_parquet(output_dir: Path, imu_accumulator: ImuAccumulator) -> None:
    """Write oak_imu.parquet with full-rate OAK IMU data."""
    table = imu_accumulator.to_table()
    if table.num_rows:
        pq.write_table(table, output_dir / "oak_imu.parquet")


@dataclass(frozen=True)
class McapExportSummary:
    """Counts of artifacts reconstructed from MCAP segment file(s)."""

    camera_frames: int
    glove_samples: dict[str, int]
    oak_imu_samples: int


@dataclass
class _McapContents:
    frames: dict[int, dict[str, Any]] = field(default_factory=dict)
    images: dict[str, dict[int, bytes]] = field(
        default_factory=lambda: {topic: {} for topic in _CAMERA_IMAGE_TOPICS}
    )
    glove_accumulators: dict[str, GloveAccumulator] = field(default_factory=dict)
    glove_tactile: dict[str, dict[int, dict[str, Any]]] = field(default_factory=dict)
    glove_imu: dict[str, dict[int, dict[str, Any]]] = field(default_factory=dict)
    oak_imu: ImuAccumulator = field(default_factory=ImuAccumulator)
    oak_imu_samples: list[OakImuSample] = field(default_factory=list)
    calibration_json: dict[str, bytes] = field(default_factory=dict)


def export_mcap_to_episode(
    mcap_path: str | Path | Iterable[str | Path],
    output_dir: str | Path,
) -> McapExportSummary:
    """Reconstruct episode files from one or more ``recording_*.mcap`` files.

    The resulting folder contains image folders, camera-rate
    ``frames.parquet`` with nearest-neighbor glove alignment, raw-rate
    ``gloves.parquet``, and full-rate ``oak_imu.parquet``.
    """
    if isinstance(mcap_path, str | Path):
        mcap_paths = _expand_mcap_paths([mcap_path])
    else:
        mcap_paths = _expand_mcap_paths(mcap_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    contents = _read_mcap(mcap_paths)
    _write_camera_images(output_dir, contents)
    _write_calibration_json(output_dir, contents)
    if contents.frames:
        _write_frames_parquet(output_dir, contents)
    write_gloves_parquet(output_dir, contents.glove_accumulators)
    write_oak_imu_parquet(output_dir, contents.oak_imu)

    return McapExportSummary(
        camera_frames=len(contents.frames),
        glove_samples={
            hand: acc.frame_count for hand, acc in sorted(contents.glove_accumulators.items())
        },
        oak_imu_samples=contents.oak_imu.sample_count,
    )


def _expand_mcap_paths(paths: Iterable[str | Path]) -> list[Path]:
    """Expand shell-style MCAP path globs for cross-platform CLI use."""
    expanded: list[Path] = []
    for path in paths:
        text = str(path)
        matches = [Path(match) for match in glob.glob(text)] if glob.has_magic(text) else []
        expanded.extend(matches or [Path(path)])
    return sorted(expanded)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export TouchTronix recording_*.mcap files to episode artifacts."
    )
    parser.add_argument(
        "mcap_paths",
        nargs="+",
        help="Input MCAP segment file(s), e.g. dataset/episode/recording_*.mcap",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        required=True,
        help="Directory where images, parquet files, and calibration JSONs are written.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = _build_arg_parser().parse_args(argv)
    summary = export_mcap_to_episode(args.mcap_paths, args.output_dir)
    glove_counts = ", ".join(
        f"{hand}={count}" for hand, count in summary.glove_samples.items()
    ) or "none"
    print(
        "Exported MCAP: "
        f"camera_frames={summary.camera_frames}, "
        f"glove_samples={glove_counts}, "
        f"oak_imu_samples={summary.oak_imu_samples}, "
        f"output_dir={args.output_dir}"
    )


def _read_mcap(mcap_paths: Iterable[Path]) -> _McapContents:
    contents = _McapContents()
    for mcap_path in mcap_paths:
        with mcap_path.open("rb") as handle:
            reader = make_reader(handle)
            for _schema, channel, message in reader.iter_messages():
                topic = channel.topic
                if topic == "/oak/camera/frame":
                    payload = json.loads(message.data)
                    contents.frames[int(payload["frame_idx"])] = payload
                elif topic in _CAMERA_IMAGE_TOPICS:
                    image = foxglove_pb2.CompressedImage.FromString(message.data)
                    contents.images[topic][int(message.sequence)] = bytes(image.data)
                elif topic.startswith("/glove/") and topic.endswith("/tactile"):
                    _store_glove_tactile_payload(contents, json.loads(message.data))
                elif topic.startswith("/glove/") and topic.endswith("/imu"):
                    _store_glove_imu_payload(contents, json.loads(message.data))
                elif topic == "/oak/imu":
                    _append_oak_imu_payload(contents, json.loads(message.data))
                elif topic in _CALIBRATION_TOPICS:
                    contents.calibration_json[_CALIBRATION_TOPICS[topic]] = bytes(message.data)
                elif topic == "/metadata/event":
                    _apply_metadata_event(contents, json.loads(message.data))
    _materialize_glove_payloads(contents)
    return contents


def _apply_metadata_event(contents: _McapContents, payload: dict[str, Any]) -> None:
    """Initialize selected hands from recording metadata, if present."""
    if payload.get("name") != "recording_started":
        return
    for hand in payload.get("hands", []) or []:
        hand_key = str(hand).lower()
        if hand_key in ("lh", "rh"):
            contents.glove_accumulators.setdefault(hand_key, GloveAccumulator(hand=hand_key))


def _store_glove_tactile_payload(contents: _McapContents, payload: dict[str, Any]) -> None:
    hand = str(payload["hand"]).lower()
    sample_idx = int(payload["sample_idx"])
    contents.glove_tactile.setdefault(hand, {})[sample_idx] = payload
    contents.glove_accumulators.setdefault(hand, GloveAccumulator(hand=hand))


def _store_glove_imu_payload(contents: _McapContents, payload: dict[str, Any]) -> None:
    hand = str(payload["hand"]).lower()
    sample_idx = int(payload["sample_idx"])
    contents.glove_imu.setdefault(hand, {})[sample_idx] = payload
    contents.glove_accumulators.setdefault(hand, GloveAccumulator(hand=hand))


def _materialize_glove_payloads(contents: _McapContents) -> None:
    for hand in sorted(contents.glove_tactile):
        accumulator = contents.glove_accumulators.setdefault(hand, GloveAccumulator(hand=hand))
        imu_by_idx = contents.glove_imu.get(hand, {})
        for sample_idx in sorted(contents.glove_tactile[hand]):
            payload = contents.glove_tactile[hand][sample_idx]
            imu_payload = imu_by_idx.get(sample_idx, {})
            finger_bend = payload["finger_bend"]
            if not isinstance(finger_bend, dict):
                finger_bend = dict(zip(FINGER_NAMES, finger_bend, strict=True))
            accumulator.add_frame(
                timestamp=float(payload["timestamp"]),
                finger_pressure={
                    finger: payload["finger_pressure"][finger]
                    for finger in FINGER_NAMES
                },
                palm_pressure=payload["palm_pressure"],
                finger_bend=finger_bend,
                imu_quaternion=_tuple_or_none(imu_payload.get("imu_quaternion")),
                imu_gyro=_tuple_or_none(imu_payload.get("imu_gyro")),
                imu_accel=_tuple_or_none(imu_payload.get("imu_accel")),
                finger_force_N_total=payload.get("finger_force_N_total"),
                finger_force_N_pixels=payload.get("finger_force_N_pixels"),
            )


def _append_oak_imu_payload(contents: _McapContents, payload: dict[str, Any]) -> None:
    sample = OakImuSample(
        accel_timestamp=payload["accel_timestamp"],
        accel=tuple(payload["accel"]),
        gyro_timestamp=payload["gyro_timestamp"],
        gyro=tuple(payload["gyro"]),
        game_rotation_quaternion=_tuple_or_none(payload.get("game_rotation_quaternion")),
        game_rotation_timestamp=payload.get("game_rotation_timestamp"),
        game_rotation_accuracy=payload.get("game_rotation_accuracy"),
    )
    contents.oak_imu.add_sample(sample)
    contents.oak_imu_samples.append(sample)


def _tuple_or_none(value: Any) -> tuple[Any, ...] | None:
    if value is None:
        return None
    return tuple(value)


def _write_camera_images(output_dir: Path, contents: _McapContents) -> None:
    for frame_idx in sorted(contents.frames):
        frame = contents.frames[frame_idx]
        for topic, path_key in _CAMERA_IMAGE_TOPICS.items():
            try:
                data = contents.images[topic][frame_idx]
            except KeyError as exc:
                raise ValueError(
                    f"MCAP is missing {topic} data for frame {frame_idx}"
                ) from exc
            relative_path = Path(frame[path_key])
            target = output_dir / relative_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)


def _write_calibration_json(output_dir: Path, contents: _McapContents) -> None:
    for filename, data in contents.calibration_json.items():
        (output_dir / filename).write_bytes(data)


def _float_or_nan(value: Any) -> float:
    if value is None:
        return np.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def _aligned_oak_imu_columns(
    frames: list[dict[str, Any]],
    samples: list[OakImuSample],
) -> dict[str, pa.Array]:
    n = len(frames)
    if not samples:
        return {
            "oak_imu_quaternion": pa.nulls(n, type=pa.list_(pa.float32())),
            "oak_imu_gyro": pa.nulls(n, type=pa.list_(pa.float32())),
            "oak_imu_accel": pa.nulls(n, type=pa.list_(pa.float32())),
        }

    sorted_samples = sorted(samples, key=lambda sample: sample.accel_timestamp)
    src_ts = np.array([sample.accel_timestamp for sample in sorted_samples], dtype=np.float64)
    ref_ts = np.array([_float_or_nan(frame.get("oak_rgb_timestamp")) for frame in frames])
    valid = np.isfinite(ref_ts)

    quaternions: list[tuple[float, ...] | None] = [None] * n
    gyros: list[tuple[float, ...] | None] = [None] * n
    accels: list[tuple[float, ...] | None] = [None] * n
    if valid.any():
        indices, _dt_ms = _align_nearest(ref_ts[valid], src_ts)
        valid_rows = np.nonzero(valid)[0]
        for row_idx, sample_idx in zip(valid_rows, indices, strict=True):
            sample = sorted_samples[int(sample_idx)]
            quaternions[int(row_idx)] = sample.game_rotation_quaternion
            gyros[int(row_idx)] = sample.gyro
            accels[int(row_idx)] = sample.accel

    return {
        "oak_imu_quaternion": pa.array(quaternions, type=pa.list_(pa.float32())),
        "oak_imu_gyro": pa.array(gyros, type=pa.list_(pa.float32())),
        "oak_imu_accel": pa.array(accels, type=pa.list_(pa.float32())),
    }


def _write_frames_parquet(output_dir: Path, contents: _McapContents) -> None:
    frame_items = sorted(contents.frames.items())
    frames = [payload for _frame_idx, payload in frame_items]
    host_receive_timestamps = np.array(
        [frame["timestamp"] for frame in frames], dtype=np.float64
    )
    rgb_capture_timestamps = np.array(
        [frame.get("rgb_capture_timestamp", frame["timestamp"]) for frame in frames],
        dtype=np.float64,
    )
    columns: dict[str, pa.Array] = {
        "frame_idx": pa.array([frame_idx for frame_idx, _payload in frame_items], type=pa.int32()),
        "timestamp": pa.array(host_receive_timestamps, type=pa.float64()),
        "rgb_capture_timestamp": pa.array(rgb_capture_timestamps, type=pa.float64()),
        "oak_rgb_timestamp": pa.array(
            [frame.get("oak_rgb_timestamp") for frame in frames], type=pa.float64()
        ),
        "oak_mono_left_timestamp": pa.array(
            [frame.get("oak_mono_left_timestamp") for frame in frames], type=pa.float64()
        ),
        "oak_mono_right_timestamp": pa.array(
            [frame.get("oak_mono_right_timestamp") for frame in frames], type=pa.float64()
        ),
        "rgb_path": pa.array([frame.get("rgb_path") for frame in frames], type=pa.string()),
        "mono_left_path": pa.array(
            [frame.get("mono_left_path") for frame in frames], type=pa.string()
        ),
        "mono_right_path": pa.array(
            [frame.get("mono_right_path") for frame in frames], type=pa.string()
        ),
    }
    columns.update(_aligned_oak_imu_columns(frames, contents.oak_imu_samples))
    for hand in sorted(contents.glove_accumulators):
        columns.update(
            contents.glove_accumulators[hand].aligned_columns(rgb_capture_timestamps)
        )
    pq.write_table(pa.table(columns), output_dir / "frames.parquet")


if __name__ == "__main__":
    main()
