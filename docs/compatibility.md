# V3 compatibility and troubleshooting

## Versions and distribution

| Component | Current configuration |
|---|---|
| Documentation branch | `v3-thimfilm` |
| Gloves | Thin-film V01.12, five 4×4 patches and five bend channels |
| Documented SDK API / import | `tactile-glove-sdk` 0.5.0 / `tactile_glove` |
| SDK wheel interpreter / platform | CPython 3.13, Windows x86_64 or Linux x86_64 |
| Application packages | Windows x86_64 ZIP; Linux x86_64 AppImage |
| Foxglove viewer assets | Supplied with the matching GUI package or separately by TouchTronix |
| MCAP profile | `touchtronix.raw.v4` |

The documentation reflects application source revision `5e0c572a70216329db423ff8a6b3010b5c4c6948`. GitHub-hosted builds passed for both GUI packages and both Python 3.13 SDK wheels; normal AppImage startup passed on Ubuntu 22.04 and 24.04. These CI checks use simulated hardware or unlicensed startup and do not establish native-resolution hardware throughput.

Those build results predate the SDK 0.5.0 API update. Request a validated wheel matching the [current API reference](sdk-api.md).

SDK wheels are privately supplied by TouchTronix and retained in the internal Actions workflow for 14 days. They are not committed on this branch or attached to public application releases. This branch contains customer documentation, SDK example scripts, and diagrams; the recording application's source and signing keys are not published here. Standalone Foxglove extension and layout files are supplied separately.

App/SDK packaging happens on GitHub-hosted runners. End users install supplied packages; Node.js, npm, a compiler, and the private application repository are not required. Building from source is outside this public guide.

## GUI starts but recording is not ready

- Connect the required Arducam head stereo camera before launch. Head IMU startup can take approximately 15–30 seconds.
- Close other camera/serial programs and allow the app's one-time discovery/preparation to finish.
- If a camera is added or moved to another port, restart the app. Assign optional wrists from live thumbnails after launch.
- Head IMU failure or absent factory calibration is fatal to setup. Do not bypass it or treat a partial sensor set as a complete recording.
- On Linux, the user needs head-camera USB control access to the reported `/dev/bus/usb/...` path in addition to video access. Ask an administrator for a scoped ACL or device rule, then restart. Do not run the GUI as root. Wrist cameras need video access only.

## Linux AppImage

The current AppImage uses FUSE 3. If it cannot mount/start, check executable permission and ask your administrator to install the distribution's FUSE 3 runtime. Launch it from a writable location if using the adjacent default `dataset/` or `calibrations/` directories, or select other locations in the GUI. Keep it outside a read-only mount when using those defaults.

The source tests Linux CPU encoding with FFmpeg; a system `ffmpeg` is preferred when available, otherwise the packaged executable is used. Recording setup validates that exact executable. If neither Intel QSV nor CPU `libx264` works at the selected native camera resolutions, use a compatible FFmpeg build and verify sustained throughput rather than reducing resolution silently.

## SDK wheel will not install

Check `python --version` and your selected environment. Supplied filenames contain `cp313` and target **64-bit CPython 3.13**. Python 3.12/3.14 and another architecture require different builds. Ask TouchTronix for a matching wheel; do not install the V1/V2 `touchtronix_glove` package for these gloves.

The wheel installs pyserial, PySide6, pyqtgraph, and their dependencies. The headless API does not import GUI libraries, but the optional viewer requires a desktop/GUI-capable environment. On Linux, Qt may additionally require the distribution's graphics runtime libraries, such as `libegl1`.

## Serial access, wrong hand, or no samples

1. Confirm the actual port in Windows Device Manager or `ls -l /dev/ttyUSB* /dev/ttyACM*` on Linux.
2. Verify the current user has that port's access group (`dialout` on Ubuntu, often `uucp` elsewhere). Log out/in after a group change.
3. Close all other readers. One port must have exactly one active consumer.
4. Use **1,000,000 baud, 8N1**. Older glove baud rates and packet formats do not apply.
5. Assign `--left`/`--right`, or the SDK's `hand`, from physical inspection. USB serial identity and packet data do not identify LH/RH.
6. Run `python examples/test_glove.py PORT --hand lh` (or `rh`) after the GUI releases the port. It reports raw byte and accepted-frame counts, and can capture a hex dump for support.

A two-second gap without a valid combined sample raises `TimeoutError`, even if malformed data or metadata continues arriving. Inspect the connection/cable/USB path and retry after correcting access/connectivity. The SDK examples propagate errors and close resources; they do not implement automatic reconnection. The recording app's glove logger does retry.

## Calibration or pressure is unavailable

- Create a fresh five-finger wearer calibration using only open hand and closed fist.
- Select the correct pressure/force file under **Glove Calibration** and confirm the physical glove pair/hand assignment.
- Use a filename containing `pressure` or `force`. Browse can load a file outside the app folder.
- V1/V2, shortened four-finger, or wrong-layout files are incompatible.
- Pressure conversion requires the wearer baseline and pair's LUTs. The optional fields are absent without that conversion; Foxglove reports Pixel pressure as unavailable.
- Saturated pixels are lower bounds. A tared zero does not clear the original raw saturation flag.

## Foxglove panel or layout is missing

Use the FusionX Tactile extension and V3 workspace layout from your matching GUI package, or request them from TouchTronix. Install the supplied extension, reload Foxglove, then import the supplied layout. Earlier glove configurations require different panels. Local file access, layout authoring, and local extension installation need the capabilities described in [Foxglove seat types](https://docs.foxglove.dev/docs/security/seat-types).

In the Windows GUI ZIP, the viewer assets are under `foxglove/` beside the executable. Inside the Linux AppImage they are at `usr/bin/foxglove`. Standalone viewer downloads are not hosted on this branch.

## Stop, disconnects, and slow display

Wait for **Saved** after stopping and preserve files if an error is reported. Inspect MCAP counts/timestamps rather than assuming a session is complete. Video resumes at a keyframe after a same-port reconnect, so real gaps can remain.

Stop camera preview to reduce display work; this does not stop camera recording. If a glove preview reader is still closing, the GUI refuses calibration/record/refresh/exit until it releases the port. Wait and retry the requested action instead of opening that port in another program.

The SDK viewer's window-close ordering is corrected in these examples: queued UI refreshes stop before touching a closed graphics scene, then acquisition workers stop and close their ports.
