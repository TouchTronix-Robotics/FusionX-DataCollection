# Glove SDK Python API

[SDK guide](README.md) · [Sensor indexing](sensors.md) · [Troubleshooting](troubleshooting.md)

SDK **0.6.0** exports four data/reader classes and the terminal calibration function:

```python
from tactile_glove import GloveReader, GloveFrame, TactileData, IMUData, calibrate
```

## GloveReader

Replace the port and hand with your physical assignment. Use one reader per port and one consumer per reader.

```python
PORT = "COM3"  # Linux example: "/dev/ttyUSB0"
# force, baseline_adc, and pixel_area_mm2 are keyword-only arguments.

with GloveReader(PORT, hand="lh") as glove:
    frame = next(glove.stream())  # Wait for a complete valid sample.
# The context manager stops streaming and closes the port, including on errors.
# Field examples below use this frame; every frame contains tactile and IMU data.
```

| Argument | Default | Meaning |
|---|---|---|
| `port` | Required | Serial port. Packets do not identify the hand. |
| `hand` | `"lh"` | `"lh"` or `"rh"`. |
| `baudrate` | `1_000_000` | Wired V01.12, 8N1. |
| `force` | `None` | Supplier per-pixel pressure JSON for this glove pair. |
| `baseline_adc` | `None` | Five finger names → 16 resting ADC values each, within 0–4096; requires `force`. Otherwise call `tare()`. |
| `pixel_area_mm2` | `22.5` | Positive uniform area or five named 16-area lists; `None` disables newtons. |

For polling instead of an iterator:

```python
with GloveReader(PORT, hand="lh") as glove:
    while True:
        frame = glove.read_frame()
        if frame is not None:  # None means no complete sample yet.
            print(frame.device_timestamp_ms)
            break
```

## GloveFrame

| Field | Type | Meaning |
|---|---|---|
| `hand` | `str` | Your LH/RH assignment. |
| `tactile` | `TactileData` | Pressure and bend readings. |
| `imu` | `IMUData` | Euler angles and raw motion readings. |
| `host_timestamp_ns` | `int` | Unix host decode time; includes buffering/processing delays. |
| `device_timestamp_ms` | `int` | Glove elapsed stream time; restarts at zero on stream start/reconnect. |

```python
sample: GloveFrame = frame
print(sample.hand)
print(sample.host_timestamp_ns / 1_000_000_000)  # Unix seconds.
print(sample.device_timestamp_ms)              # Elapsed milliseconds, not Unix time.
# Counter: uint32, 0–4,294,967,295 ms (~49.71 days); overflow behavior unverified.
# Observed healthy output: 8 ms spacing (~125 Hz). The SDK does not resample.
```

## TactileData

| Field | Shape | Values / order |
|---|---|---|
| `finger_pressure` | `dict[str, list[int]]` | Five 4×4 patches, 16 row-major ADC values each; `(0, 0)` is top-left. |
| `finger_bend` | `dict[str, int]` | One raw ADC value per finger. |
| `finger_pressure_kPa_pixels` | `dict[str, list[float]]` or `None` | One pressure reading in kPa for each of the 16 pixels; requires calibration and tare/baseline. |
| `finger_pressure_N_pixels` | `dict[str, list[float]]` or `None` | One force reading in N for each of the 16 pixels; `None` without calibration or with `pixel_area_mm2=None`. |
| `finger_pressure_saturated` | `dict[str, list[bool]]` or `None` | Raw ADC `>=4000`; requires calibration. |

```python
tactile: TactileData = frame.tactile
print(list(tactile.finger_pressure))  # thumb, index, middle, ring, little
pixels = tactile.finger_pressure["index"]  # 16 integers, 0–4096.
patch = [pixels[i:i + 4] for i in range(0, 16, 4)]
print(patch[0][0])                         # Top-left; no flip needed.
print(tactile.finger_pressure["index"][9]) # Row 2, column 1: 4 * row + column.
print(tactile.finger_bend["index"])        # Raw ADC, not a bend angle.
```

[Physical pixel maps](sensors.md) show all 80 pressure and five bend channels.

## IMUData

| Field | Tuple | Units |
|---|---|---|
| `euler_deg` | `(pitch, roll, yaw)` | Device degrees; no hand-dependent sign changes. |
| `gyro_raw` | `(x, y, z)` | Signed int16; physical scaling unverified. |
| `accel_raw` | `(x, y, z)` | Signed int16; physical scaling unverified. |

```python
imu: IMUData = frame.imu
pitch, roll, yaw = imu.euler_deg
print(pitch, roll, yaw, imu.gyro_raw, imu.accel_raw)
# Inspected gyro/accel values were zero. No quaternion or magnetometer is transmitted.
```

## Wearer calibration

`calibrate()` reuses the GUI's OPEN/FIST wearer-calibration routine without importing Qt, cameras, or the recorder. It owns the selected ports while running; stop any other readers using them first.

```python
def calibrate(
    glove_ports,
    user,
    output=None,
    *,
    audio=True,
    language="en",
    baudrate=1_000_000,
    hold_seconds=3.0,
    log=print,
    stop_event=None,
): ...
```

| Argument | Meaning |
|---|---|
| `glove_ports` | Mapping of `"lh"` and/or `"rh"` to distinct serial-port strings. One glove works. |
| `user` | Nonempty wearer name saved in the result. |
| `output` | Optional string/`PathLike` JSON destination. Success replaces the file; failure/cancellation preserves an existing file. Omit for an in-memory result only. |
| `audio` | `True` by default: play miniaudio cues when available, with terminal-text fallback. `False` selects silence. |
| `language` | `"en"` or `"cn"` voice assets. Terminal instructions are English. |
| `baudrate` | Positive integer; default `1_000_000`. |
| `hold_seconds` | Finite positive collection duration per pose; default `3.0`. |
| `log` | Text callback; default `print`. |
| `stop_event` | Optional `threading.Event` for cancellation. |

```python
calibration = calibrate(
    {"lh": "COM3", "rh": "COM4"}, user="operator", output="operator.json",
    language="en",  # "cn" selects Chinese voice cues.
)
resting_adc = calibration["gloves"]["lh"]["tactile_zero_finger"]
```

The return value is a JSON-compatible dictionary with top-level `layout`, `user`, `timestamp`, and `gloves` keys. It uses the GUI's current V01.12 layout. Each selected hand contains:

- `tactile_zero_finger`: five named lists of 16 resting ADC medians from the last second of the OPEN collection, including fractional baselines.
- `bend_min` / `bend_max`: mean OPEN/FIST bend endpoints for all five fingers.
- `pose_samples`: OPEN tactile/bend samples and FIST bend samples, retaining host/device timing and raw bend channels. FIST pressure and glove IMU are not saved.
- `quality`: frame counts, bend deltas, and tactile-baseline quality information.

The minimum valid-frame check and tactile-baseline warning match the GUI. Zero, unchanged, small, or decreasing bend readings are preserved without bend acceptance criteria. Ports and audio output are cleaned up on success, read errors, Ctrl+C, or programmatic cancellation. Insufficient valid frames or cancellation raises `RuntimeError`; serial/time-out errors propagate after cleanup. Audio errors are reported independently and do not discard valid calibration data.

All SDK wheels include the GUI's original English/Chinese WAV cues and beeps. The optional `audio` extra installs miniaudio; headless calibration still works without that binding or any GUI libraries. See [audio installation](README.md#optional-viewer-and-audio).

### Zero tactile ADC readings from a saved JSON

The [complete zeroing example](README.md#use-the-saved-json-to-zero-tactile-readings) loads `operator.json` and keeps its baseline keyed by finger name. For each finger, NumPy's `np.maximum(raw_pixels - baseline[finger], 0.0)` subtracts and clips all 16 pixels together. It requires no supplier LUT, retains fractional baselines, and produces a separate dictionary of NumPy arrays, such as `zeroed["index"]`. `frame.tactile.finger_pressure` always contains the original ADC readings.

### Use the saved JSON for pressure and force

Load a saved wearer JSON and pass its resting ADC with the matching supplier LUT. `baseline_adc` requires `force`; it prepares the calibrated kPa/N fields without changing raw ADC:

```python
import json

with open("operator.json", encoding="utf-8") as source:
    calibration = json.load(source)
with GloveReader(
    PORT, hand="lh", force="calibrations/example_perpixel_pressure.json",
    baseline_adc=calibration["gloves"]["lh"]["tactile_zero_finger"],
) as glove:
    frame = next(glove.stream())
    print(frame.tactile.finger_pressure_kPa_pixels["index"])
    print(frame.tactile.finger_pressure_N_pixels["index"])
```

The SDK converts the original raw ADC and resting ADC through the supplier LUT, then subtracts the resting pressure and clips at zero. Do not substitute zeroed ADC for the raw input to this conversion.

Wearer calibration does not generate the supplier pressure LUT. Keep the worn glove contact-free during OPEN collection, use the correct hand/pair file, and renew the baseline after a wearer/session change or putting the glove on again. Raw SDK samples and both clocks are preserved.

## Per-pixel calibration

Use the [example file](../../calibrations/example_perpixel_pressure.json) for **LH_1/RH_1**; use your own calibration for other gloves.

```python
CALIBRATION = "calibrations/example_perpixel_pressure.json"

with GloveReader(PORT, hand="lh", force=CALIBRATION) as glove:
    resting_adc = glove.tare(duration_s=1.0)  # Worn glove, no tactile contact.
    frame = next(glove.stream())
    print(frame.tactile.finger_pressure_kPa_pixels["thumb"])  # Pressure per pixel, in kPa.
    print(frame.tactile.finger_pressure_N_pixels["thumb"])    # Force per pixel, in N.
    print(frame.tactile.finger_pressure_saturated["thumb"])   # Saturation flag per pixel.
# N = kPa * area_mm2 * 0.001; default area is 22.5 mm².
# Saturated/table-top values are lower bounds, even when tared pressure is zero.
```

Reuse a recent resting measurement for the same glove and wearing session:

```python
reader = GloveReader(
    PORT, hand="lh", force=CALIBRATION, baseline_adc=resting_adc,
    pixel_area_mm2=22.5,  # Override with measured areas; None gives pressure only.
)
with reader as glove:
    frame = next(glove.stream())  # Baseline is already prepared.
# Retare after changing wearer/session or putting the glove on again.
# Tare clears buffered input without restarting the device counter.
# The same reader retains its prepared baseline across reconnects.
```

See [calibration format and conversion](../gui/calibration.md#supplier-per-pixel-pressure) for LUT validation, mapping, and pressure-domain tare.

## Reconnect after errors

```python
import time
from serial import SerialException

reader = GloveReader(PORT, hand="lh")
try:
    while True:
        try:
            reader.connect()
            for frame in reader.stream():  # New iterator after each reconnect.
                print(frame.device_timestamp_ms)
        except (TimeoutError, SerialException) as error:
            print(error)
        finally:
            reader.disconnect()
        time.sleep(1)  # Retry the same physical port.
except KeyboardInterrupt:
    pass  # The finally block has closed the port.
```

| Error | Check |
|---|---|
| `TimeoutError` | No valid sample for two seconds. Metadata/malformed packets do not reset the timeout. |
| `SerialException` | Connection, permissions, or another reader using the port. |
| `RuntimeError` | Connect before reading; with pressure calibration, provide a baseline or call `tare()`. `tare()` requires `force`. Wearer calibration also uses this error for insufficient valid frames or cancellation. |
| `ValueError` | Hand, calibration, baseline, area, tare duration, or wearer-calibration arguments. |

## Example behavior

```bash
# Run from the repository root; replace COM3/COM4 with your ports.
python examples/stream_glove.py --left COM3 --right COM4 --viewer --seconds 30
python examples/read_calibrated_glove.py COM3 --hand lh --force calibrations/example_perpixel_pressure.json --seconds 10
python examples/calibrate_gloves.py --left COM3 --right COM4 --user operator --output operator.json
python examples/test_glove.py COM3 --hand lh --raw-output glove_raw_bytes.txt
```

| Example | Behavior |
|---|---|
| `stream_glove.py` | One worker per port; prints counts/rate/frame age. `--force FILE` adds startup tare and peak kPa/N; timed streaming begins after tare. |
| `--viewer` | Raw ADC display at 25 FPS; latest frame only, stale data dims. Keep `glove_viewer.py` beside the script. |
| `--seconds` / Ctrl+C / window close | Stops workers and closes ports; reader/render errors propagate after cleanup. |
| `read_calibrated_glove.py` | Terminal test: requires `--hand` and `--force`; tares, then prints all pixel ADC/kPa/N/saturation values. |
| `calibrate_gloves.py` | GUI-compatible OPEN/FIST wearer calibration; requires port assignment, `--user`, and `--output`. Audio is automatic when available; `--language cn` selects Chinese cues and `--no-audio` disables sound. |
| `read_one_frame.py` | Prints one frame, including calibrated arrays with `--force FILE`. |
| `test_glove.py` | Counts bytes/frames and saves a hex dump; close other readers first. |

[Save frames in your pipeline](README.md#build-your-own-data-collection-pipeline).
