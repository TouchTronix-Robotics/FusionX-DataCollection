# FusionX GUI MCAP recording format

[GUI guide](README.md) · [Calibration](calibration.md) · [Troubleshooting](troubleshooting.md)

The current profile is **`touchtronix.raw.v4`**. The application writes numbered `recording_###.mcap` files directly into the folder selected with **Save Folder**. Reusing that folder selects the next unused index. Wait for **Saved** before reading a file.

## Topics

| Topic | Encoding / schema | Content |
|---|---|---|
| `/camera/head/stereo/h264` | Protobuf, `foxglove.CompressedVideo` | Intact side-by-side stereo H.264, 3840×1200, `format="h264"`, `frame_id="head_left"`. |
| `/camera/wrist/{lh,rh}/h264` | Protobuf, `foxglove.CompressedVideo` | Assigned wrist video, 1920×1080; absent for unassigned hands. |
| `/camera/head/{left,right}/calibration` | Protobuf, `foxglove.CameraCalibration` | Per-eye 1920×1200 factory calibration, replayed in each segment. |
| `/calibration/camera/head/json` | JSON | Verbatim factory flash calibration plus head device identity. |
| `/camera/head/imu` | JSON, `touchtronix.UvcImuSample` | Head acceleration in m/s², gyro in rad/s, temperature, raw fields, and timing diagnostics. |
| `/glove/{lh,rh}/tactile` | JSON, `touchtronix.GloveTactileSample` | Raw five-patch pressure/bend fields and optional pressure/force results. |
| `/glove/{lh,rh}/imu` | JSON, `touchtronix.GloveImuSample` | Device Euler angles and raw signed motion fields. |
| `/calibration/glove/user/json` | JSON | Original wearer calibration, when selected. |
| `/tf_static` | Protobuf, `foxglove.FrameTransform` | Factory `head_left`→`head_right` stereo geometry, replayed each segment. |

The current wrists have no factory calibration and produce video only. Wrist IMU topics are absent. The format reserves wrist calibration topics for a supplied per-unit calibration; the ordinary V3 setup does not produce them. Dynamic `/tf` and glove-to-camera transforms are absent because a shared calibrated frame has not been established.

## Glove tactile fields

| Field | Meaning |
|---|---|
| `hand` | Operator's explicit `lh`/`rh` assignment. |
| `sample_idx` | Per-topic sample sequence. |
| `timestamp` | Host Unix time in seconds, derived from `host_timestamp_ns`. |
| `host_timestamp_ns` | Exact integer host timestamp, also used for MCAP log/publish time. |
| `device_timestamp_ms` | Separate unsigned 32-bit elapsed stream counter; start resets it to zero. |
| `message_sequence` | Wire NUM; repeated values are allowed. |
| `finger_pressure` | Five named flattened 4×4 patches, native 0–4096 ADC. |
| `finger_bend` | Five ADC values in thumb/index/middle/ring/little order. |
| `pressure_raw` | All 80 original pressure wire channels. |
| `bend_raw` | All five original bend wire channels, little → thumb. |
| `finger_force_N_total` | Optional five polynomial total-force values, in N. |
| `finger_pressure_kPa_pixels` | Optional five-by-16 calibrated contact pressures, in kPa. |
| `finger_pressure_saturated` | Matching five-by-16 booleans; present together with per-pixel pressure. |

Optional converted fields require matching calibrations. Raw fields remain unchanged. The recorder does not write derived tactile/bend images; Foxglove generates those views during playback.

Glove IMU JSON has the shared timing/hand/sequence fields plus `imu_euler_deg` (pitch, roll, yaw), `imu_gyro_raw`, and `imu_accel_raw`. Raw glove gyro/accelerometer scaling is unverified; inspected samples were zero. No glove quaternion or magnetometer field is transmitted.

## Camera video and timestamps

The capture backend is DirectShow on Windows and V4L2 on Linux. Recording tests Intel QSV MJPEG decode/H.264 encode, then CPU decoding plus `libx264`; no GPU is required. Resolution is not reduced to hide insufficient throughput.

Streams use one-second closed GOPs, no B-frames/lookahead, and repeated SPS/PPS/AUD headers. H.264 access units are stored without image decoding in the recorder. The head stereo image is not split into independent eyes; split it downstream if needed.

Video MCAP timestamps come from FFmpeg capture-side epoch PTS: DirectShow wall-clock PTS, or V4L2 device timestamps converted to epoch time. Host receipt time is diagnostic and is not substituted for capture time. There is no runtime frame matcher or resampling; downstream consumers can pair camera frames within approximately one frame interval.

Recording begins only after required head IMU/factory calibration and an independently decodable keyframe from every selected video stream are ready. Startup failure produces no episode/MCAP for that attempt. Segments rotate after 9,000 head units on the next head keyframe. A wrist withholds dependent frames after rotation until its next keyframe, so each segment's camera topics are independently playable.

## Head IMU and calibration

Every valid head IMU SDK reading is retained without host pacing or a fixed-frequency gate. Its SDK monotonic host timestamp is mapped to Unix epoch; this is host timing, not a verified sensor-acquisition clock. Preserve `imu_timestamp_raw`, including repeats. Diagnostic `read_duration_ns` and `delivery_delay_ns`, when present, help explain read/output delays.

Factory head flash calibration is required and preserved verbatim. Its native centimeter extrinsics are converted to meters for the static stereo transform (approximately 6 cm baseline). Foxglove camera messages use the first eight of the fourteen factory distortion coefficients as a rational-polynomial model. Both eye projection matrices use the right camera's intrinsics; the full original factory data remains in the JSON topic. Wrist calibration is not invented from the head's calibration.

## Recovery and completeness

Camera video processes and glove serial readers retry after transient failures until stopped; video resumes on a keyframe. The head IMU keeps its warm session, pauses while idle/calibrating, and retries transport recovery. Same-port reconnection is supported; new devices/ports require an application restart.

If the required head IMU helper/reader exits unexpectedly, the episode stops and captured MCAP data is preserved with a GUI error. A recording can contain real gaps during recovery. Inspect counts, time ranges, and errors before treating it as complete; average rates do not prove that no data was lost.

Stopping closes the shared capture gate before teardown. No synthetic recording-start/stop messages extend the sensor timeline. Source revision/build information and segment indexing use MCAP metadata, not timestamped sensor topics.

## Foxglove playback

Use the matching FusionX Tactile extension and V3 workspace layout supplied with the GUI package, or request them from TouchTronix. Install the extension before importing the layout; see [viewer setup guidance](troubleshooting.md#foxglove-panel-or-layout-is-missing). Open finished segments in Foxglove Desktop and use Data Source Info / Raw Messages to inspect the topics above. The tactile panel has raw ADC and optional per-pixel pressure modes, paired pressure/saturation data, and five bend bars per hand.
