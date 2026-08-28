# FusionX-DataCollection

Multimodal data collection tools for synchronized OAK-D stereo video and tactile glove streams.

Download standalone app assets from the [Releases](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases) page. Each platform now has one unified FusionX GUI application rather than separate desktop and miniPC builds. The same application opens as a fullscreen touch interface by default; launch it with `--windowed` for desktop use. A separate headless CLI recorder is also available. Python SDK wheel packages are provided separately on request.

Standalone Foxglove Desktop viewer files are available directly from this repository:

- [`touchtronixrobotics.fusionx-tactile-panel-0.2.3.foxe`](touchtronixrobotics.fusionx-tactile-panel-0.2.3.foxe) — self-contained FusionX tactile panel extension.
- [`fusionx_foxglove_layout.json`](fusionx_foxglove_layout.json) — camera, tactile, OAK IMU, and LH/RH glove IMU workspace.

Install the extension before importing the layout. Neither file requires the application source tree, Node.js, or npm.

Choose the instructions for the package you are using:

- [Standalone app README](README-standalone-app.md) — unified fullscreen/windowed GUI, CLI recording, Foxglove playback, one-time Ubuntu miniPC setup, and offline post-processing.
- [Python SDK README](README-sdk.md) — install a provided `tactile_glove` wheel package and read tactile glove data directly from Python.

## Test Cameras

The camera/IMU tests use OpenCV and the Arducam SDK. From the repository root, install their dependencies into your Python environment:

```bash
python -m pip install arducam-uvc-stereo-sdk==0.3.0 "numpy>=2,<3" opencv-python==4.13.0.92
```

Test a stereo camera:

```bash
python tests/test_stereo_imu_stream.py
```

Test a monocular wrist camera at the default 1920x1080 resolution:

```bash
python tests/test_wrist_imu_stream.py
```

Press `q` or `Esc` to stop. Add `--serial SERIAL` when multiple Arducam cameras are connected.

For a repeatable headless test of calibration, IMU, and sustained frame rate, capture 301 frames while limiting console output:

```bash
python tests/test_stereo_imu_stream.py --headless --max-frames 301 --print-every 300
python tests/test_wrist_imu_stream.py --headless --max-frames 301 --print-every 300
```

Both tests report measured FPS and fail below 95 percent of the requested rate. Use `--min-fps` to set a different requirement.

The Arducam SDK currently provides Windows and Linux packages; macOS is not supported.
