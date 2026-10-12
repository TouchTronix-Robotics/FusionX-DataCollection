# FusionX GUI troubleshooting

[GUI guide](README.md) · [Calibration](calibration.md) · [Recording format](recording-format.md) · [Documentation home](../../README.md)

## Packages and compatibility

Use the [v3.0.0 GUI package](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/tag/v3.0.0) for V01.12 gloves with five 4×4 patches and five bend channels. Windows packages are x86_64 ZIPs; Linux packages are x86_64 AppImages. The GUI includes its Python runtime and dependencies. Obtain a license key from TouchTronix.

The application records MCAP profile `touchtronix.raw.v4`. It requires the supported Arducam head stereo camera for recording; zero, one, or two assigned wrist cameras are supported. Standalone Foxglove viewer assets are supplied with the matching application package or separately by TouchTronix.

Earlier package validation at application source revision `5e0c572a70216329db423ff8a6b3010b5c4c6948` passed GitHub-hosted GUI builds and normal AppImage startup on Ubuntu 22.04 and 24.04. Simulated sensor tests and startup checks do not establish native-resolution hardware throughput.

## GUI starts but recording is not ready

- Connect the required Arducam head stereo camera before launch. Head IMU startup can take approximately 15–30 seconds.
- Close other camera/serial programs and allow the app's one-time discovery/preparation to finish.
- If a camera is added or moved to another port, restart the app. Assign optional wrists from live thumbnails after launch.
- Head IMU failure or absent factory calibration is fatal to setup. Do not bypass it or treat a partial sensor set as a complete recording.
- On Linux, the user needs head-camera USB control access to the reported `/dev/bus/usb/...` path in addition to video access. Ask an administrator for a scoped ACL or device rule, then restart. Do not run the GUI as root. Wrist cameras need video access only.

## Linux AppImage

The current AppImage uses FUSE 3. If it cannot mount/start, check executable permission and ask your administrator to install the distribution's FUSE 3 runtime. Launch it from a writable location if using the adjacent default `dataset/` or `calibrations/` directories, or select other locations in the GUI. Keep it outside a read-only mount when using those defaults.

The source tests Linux CPU encoding with FFmpeg; a system `ffmpeg` is preferred when available, otherwise the packaged executable is used. Recording setup validates that exact executable. If neither Intel QSV nor CPU `libx264` works at the selected native camera resolutions, use a compatible FFmpeg build and verify sustained throughput rather than reducing resolution silently.

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

## Glove ports or hand assignment

Select the actual LH/RH COM or Linux serial ports in the main window. Port numbering, repeated USB serial identities, and packets do not identify the hand. Touch one glove at a time to confirm its idle heatmap responds on the intended side. Close other programs using the same ports.

On Linux, grant the user access through the device's serial group, typically `dialout` on Ubuntu or `uucp` on other distributions. Log out and back in after a group change. Run the GUI as the normal user. On Windows, inspect Device Manager and install the vendor's serial driver if necessary.

The application uses 1,000,000 baud, 8N1. Its glove logger retries after read errors or two seconds without a valid combined sample. A metadata reply or malformed packet does not establish stream recovery; receiving a valid sample does.

## Stop, disconnects, and slow display

Wait for **Saved** after stopping and preserve files if an error is reported. Inspect MCAP counts/timestamps rather than assuming a session is complete. Video resumes at a keyframe after a same-port reconnect, so real gaps can remain.

Stop camera preview to reduce display work; this does not stop camera recording. If a glove preview reader is still closing, the GUI refuses calibration/record/refresh/exit until it releases the port. Wait and retry the requested action instead of opening that port in another program.
