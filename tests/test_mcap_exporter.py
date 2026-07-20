import json
import sys
from pathlib import Path

import pyarrow.parquet as pq
from mcap.writer import Writer


POST_PROCESSING = Path(__file__).resolve().parents[1] / "post_processing"
sys.path.insert(0, str(POST_PROCESSING))

from mcap_exporter import export_mcap_to_episode  # noqa: E402


FINGERS = ["thumb", "index", "middle", "ring", "little"]


def _varint(value: int) -> bytes:
    encoded = bytearray()
    while value > 0x7F:
        encoded.append((value & 0x7F) | 0x80)
        value >>= 7
    encoded.append(value)
    return bytes(encoded)


def _compressed_image(data: bytes) -> bytes:
    image_format = b"jpeg"
    return (
        b"\x12"
        + _varint(len(data))
        + data
        + b"\x1a"
        + _varint(len(image_format))
        + image_format
    )


def _write_messages(path: Path, messages: list[tuple[str, str, bytes, int]]) -> None:
    writer = Writer(str(path))
    writer.start(profile="touchtronix.raw.v2", library="test")
    channels: dict[tuple[str, str], int] = {}
    for topic, encoding, data, sequence in messages:
        key = (topic, encoding)
        if key not in channels:
            channels[key] = writer.register_channel(
                topic=topic,
                message_encoding=encoding,
                schema_id=0,
            )
        writer.add_message(
            channel_id=channels[key],
            log_time=1_000_000_000,
            publish_time=1_000_000_000,
            sequence=sequence,
            data=data,
        )
    writer.finish()


def _camera_frame(frame_idx: int = 0) -> dict:
    return {
        "frame_idx": frame_idx,
        "timestamp": 1.1,
        "rgb_capture_timestamp": 1.0,
        "oak_rgb_timestamp": 10.0,
        "oak_mono_left_timestamp": 10.0,
        "oak_mono_right_timestamp": 10.0,
        "rgb_path": f"rgb/{frame_idx:06d}.jpg",
        "mono_left_path": f"mono_left/{frame_idx:06d}.jpg",
        "mono_right_path": f"mono_right/{frame_idx:06d}.jpg",
    }


def test_export_unwraps_foxglove_compressed_images(tmp_path):
    mcap_path = tmp_path / "recording_000.mcap"
    frame = _camera_frame()
    images = {
        "/oak/rgb/jpeg": b"rgb-jpeg",
        "/oak/mono_left/jpeg": b"left-jpeg",
        "/oak/mono_right/jpeg": b"right-jpeg",
    }
    messages = [("/oak/camera/frame", "json", json.dumps(frame).encode(), 0)]
    messages.extend(
        (topic, "protobuf", _compressed_image(data), 0)
        for topic, data in images.items()
    )
    _write_messages(mcap_path, messages)

    output_dir = tmp_path / "exported"
    export_mcap_to_episode(mcap_path, output_dir)

    assert (output_dir / frame["rgb_path"]).read_bytes() == images["/oak/rgb/jpeg"]
    assert (output_dir / frame["mono_left_path"]).read_bytes() == images["/oak/mono_left/jpeg"]
    assert (output_dir / frame["mono_right_path"]).read_bytes() == images["/oak/mono_right/jpeg"]


def test_export_writes_current_glove_calibration_topics(tmp_path):
    mcap_path = tmp_path / "recording_000.mcap"
    user_calibration = b'{"user":"test","gloves":{}}'
    force_calibration = b'{"type":"force"}'
    _write_messages(
        mcap_path,
        [
            ("/calibration/glove/user/json", "json", user_calibration, 0),
            ("/calibration/glove/force/json", "json", force_calibration, 0),
        ],
    )

    output_dir = tmp_path / "exported"
    export_mcap_to_episode(mcap_path, output_dir)

    assert (output_dir / "user_calibration.json").read_bytes() == user_calibration
    assert (output_dir / "force_calibration.json").read_bytes() == force_calibration


def test_export_preserves_calibrated_force_in_parquet_outputs(tmp_path):
    mcap_path = tmp_path / "recording_000.mcap"
    frame = _camera_frame()
    force_total = [1.0, 2.0, 3.0, 4.0, 5.0]
    force_pixels = [
        [float(finger + pixel) for pixel in range(12)] for finger in range(5)
    ]
    tactile = {
        "hand": "lh",
        "sample_idx": 0,
        "timestamp": 1.0,
        "finger_pressure": {
            finger: [index] * 12 for index, finger in enumerate(FINGERS)
        },
        "palm_pressure": list(range(60)),
        "finger_bend": [10, 20, 30, 40, 50],
        "finger_force_N_total": force_total,
        "finger_force_N_pixels": force_pixels,
    }
    imu = {
        "hand": "lh",
        "sample_idx": 0,
        "timestamp": 1.0,
        "imu_quaternion": [1.0, 0.0, 0.0, 0.0],
        "imu_gyro": [0.1, 0.2, 0.3],
        "imu_accel": [1.0, 2.0, 3.0],
    }
    messages = [("/oak/camera/frame", "json", json.dumps(frame).encode(), 0)]
    messages.extend(
        (topic, "protobuf", _compressed_image(data), 0)
        for topic, data in {
            "/oak/rgb/jpeg": b"rgb-jpeg",
            "/oak/mono_left/jpeg": b"left-jpeg",
            "/oak/mono_right/jpeg": b"right-jpeg",
        }.items()
    )
    messages.extend(
        [
            ("/glove/lh/tactile", "json", json.dumps(tactile).encode(), 0),
            ("/glove/lh/imu", "json", json.dumps(imu).encode(), 0),
        ]
    )
    _write_messages(mcap_path, messages)

    output_dir = tmp_path / "exported"
    export_mcap_to_episode(mcap_path, output_dir)

    gloves = pq.read_table(output_dir / "gloves.parquet").to_pydict()
    frames = pq.read_table(output_dir / "frames.parquet").to_pydict()
    assert gloves["finger_force_N_total"] == [force_total]
    assert gloves["finger_force_N_pixels"] == [force_pixels]
    assert frames["lh_finger_force_N_total"] == [force_total]
    assert frames["lh_finger_force_N_pixels"] == [force_pixels]
