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
