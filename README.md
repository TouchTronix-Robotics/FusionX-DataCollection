# FusionX-DataCollection

Multimodal data collection tools for synchronized Arducam AR0234 stereo video and v1 conductive-fabric tactile gloves. The head stereo camera is required; wrist cameras and gloves are optional.

Download the [v1.3.1 release](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/tag/v1.3.1) for the Windows x86_64 GUI and the standalone SDK 0.1.0 wheels for CPython 3.12 on Windows/Linux x86_64.

The Windows GUI requires an enabled Intel integrated GPU with a current graphics driver for Quick Sync MJPEG decoding and H.264 encoding. Extract the entire GUI ZIP and keep `_internal/` beside `touchtronix-fusionX.exe`. The app opens fullscreen; use `--windowed` for a desktop window.

Camera preview starts automatically after camera discovery, head-IMU warm-up, and QSV validation. **Start Preview / Stop Preview** toggles visualization while idle or recording. Select **Language → English / 中文** for offline interface text and miniaudio voice cues. **Open Logs / 打开日志** opens the diagnostics directory.

For current recordings, use the Foxglove layout and packaged tactile extension from the GUI ZIP's `foxglove/` folder. Install the extension before importing the layout. Neither file requires the application source tree, Node.js, or npm. The older standalone [panel 0.2.3](touchtronixrobotics.fusionx-tactile-panel-0.2.3.foxe) and [layout](fusionx_foxglove_layout.json) remain in this branch for earlier recordings.

Choose the instructions for the package you are using:

- [Standalone app README](README-standalone-app.md) — Windows setup, automatic preview, calibration, recording, voice cues, and Foxglove playback. Earlier OAK/Linux tools are labeled as legacy.
- [Python SDK README](README-sdk.md) — install the `tactile_glove` wheel package and read tactile glove data directly from Python.

## Test Cameras

Close the GUI before running these independent hardware diagnostics. Their test-specific head/wrist IMU polling is separate from the current GUI, which records only head-camera IMU data.

The camera/IMU tests use OpenCV and the Arducam SDK. From the repository root, install their dependencies into your Python environment:

```bash
python -m pip install arducam-uvc-stereo-sdk==0.3.0 "numpy>=2,<3" opencv-python==4.13.0.92 "pytest>=7"
```

Test a stereo camera:

```bash
python tests/test_stereo_imu_stream.py
```

Test a monocular wrist camera at the default 1920x1080 resolution:

```bash
python tests/test_wrist_imu_stream.py
```

Press `q` or `Esc` to stop. Add `--serial SERIAL` when multiple Arducam cameras are connected. When serials are duplicated, use the printed Windows SDK USB instance path with `--device-path "PATH"`.

For a repeatable headless test of video, IMU, and sustained frame rate, capture 301 frames while limiting console output. The stereo test also validates its flash calibration:

```bash
python tests/test_stereo_imu_stream.py --headless --max-frames 301 --print-every 300
python tests/test_wrist_imu_stream.py --headless --max-frames 301 --print-every 300
```

Both tests report measured FPS and fail below 95 percent of the requested rate. Use `--min-fps` to set a different
requirement. The head test targets 100 Hz IMU polling, while the 1080p wrist test targets 40 Hz. They also require at
least 90 percent sane frame-paired IMU samples with a nonzero, advancing raw timestamp. A known non-MJPEG negotiated
mode fails; an unknown FOURCC produces a warning because some OpenCV backends do not report it.

After the stereo camera and each wrist camera pass individually, connect one stereo and two wrist cameras and run the
combined hardware-load diagnostic:

```bash
python tests/test_full_camera_load.py --seconds 30
```

This tests 3840x1200 stereo MJPEG at 30 FPS with test-specific 10 ms head-IMU polling (a 100 Hz target), plus two
1920x1080 wrist MJPEG streams at 30 FPS with test-specific 25 ms wrist-IMU polling (a 40 Hz target). It fails if the
required camera topology is missing, the stereo calibration fails, or any stream fails its frame-rate, video, or IMU
checks.
It does not test the packaged executable, its FFmpeg/DirectShow capture path, or MCAP writing.

To run the stereo test, both wrist tests, and the combined load test sequentially through pytest:

```bash
python -m pytest tests/test_camera_hardware.py -v -s
```

The suite requires exactly one stereo camera and two wrist cameras and normally takes a few minutes.

The Arducam SDK currently provides Windows and Linux packages; macOS is not supported.
