# Glove SDK for custom data collection

Use the `tactile_glove` Python package to acquire V01.12 glove samples and integrate them into your own collection, robotics, processing, or storage pipeline. Each port has an explicitly assigned hand, and each accepted frame contains tactile, bend, IMU, and host/device timing fields.

The SDK handles serial commands, framing, CRC validation, decoding, and optional per-pixel pressure/force calibration. Your application controls acquisition workers, reconnection, processing, and output storage. Cameras and the FusionX GUI are optional components of your own system.

- [Full Python API](api.md)
- [Sensor layout and indexing](sensors.md)
- [SDK installation and serial troubleshooting](troubleshooting.md)
- [Documentation home](../../README.md)

## Install and try the SDK

Download the compiled SDK **0.5.0** wheel from the [v3.0.0 release](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/tag/v3.0.0): [Windows x86_64](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/download/v3.0.0/tactile_glove_sdk-0.5.0-cp313-cp313-win_amd64.whl) or [Linux x86_64](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/download/v3.0.0/tactile_glove_sdk-0.5.0-cp313-cp313-linux_x86_64.whl). Both require **64-bit CPython 3.13**. A `cp313` wheel cannot be installed into Python 3.12 or 3.14. Install the wheel into your own Python environment; no compiler is required.

Linux, from the directory containing your downloaded wheel:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install ./tactile_glove_sdk-0.5.0-cp313-cp313-linux_x86_64.whl
git clone --single-branch --branch v3-thimfilm https://github.com/TouchTronix-Robotics/FusionX-DataCollection.git
cd FusionX-DataCollection
python examples/stream_glove.py --left /dev/ttyUSB0 --right /dev/ttyUSB1 --viewer
```

Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .\tactile_glove_sdk-0.5.0-cp313-cp313-win_amd64.whl
git clone --single-branch --branch v3-thimfilm https://github.com/TouchTronix-Robotics/FusionX-DataCollection.git
cd FusionX-DataCollection
python examples/stream_glove.py --left COM3 --right COM4 --viewer
```

Use the ports for your gloves. One glove also works:

```bash
python examples/stream_glove.py --right /dev/ttyUSB1 --viewer
python examples/stream_glove.py --left /dev/ttyUSB0 --seconds 30
python examples/read_one_frame.py /dev/ttyUSB1 --hand rh
python examples/test_glove.py /dev/ttyUSB1 --hand rh
```

The viewer has five 4×4 tactile patches and five raw bend bars per hand. Each selected port has its own acquisition worker; 25 FPS display refresh consumes only the latest readings and does not set the sensor rate. Close the window, press Ctrl+C, or use `--seconds` to stop and close ports. Reader/rendering errors are reported after cleanup. The SDK and its examples work with the selected gloves independently of cameras and the FusionX recording application.

## Read samples in your application

```python
from tactile_glove import GloveReader

# Hand comes from this explicit assignment, not the device or port order.
with GloveReader("/dev/ttyUSB1", hand="rh") as glove:
    frame = next(glove.stream())
    print(frame.hand)  # "rh"
    print(frame.tactile.finger_pressure["index"][9])  # row 2, column 1
    print(frame.tactile.finger_bend["little"])  # raw bend ADC
    print(frame.imu.euler_deg)  # pitch, roll, yaw in degrees
    print(frame.host_timestamp_ns, frame.device_timestamp_ms)
```

Use one reader per port and one consumer per reader. The default connection is 1,000,000 baud, 8N1. `read_frame()` returns a complete frame or `None` while waiting for one; `stream()` yields accepted frames. See the [API reference](api.md) for fields, types, lifecycle, and exceptions.

## Optional per-pixel calibration

Use the supplier file `calibrations/example_perpixel_pressure.json` with its companion `README_PerPixel_JSON.md`. It is specific to gloves LH_1/RH_1; assign their physical ports correctly. The JSON contains both hands, five fingers per hand, and 16 raw pixel keys (`r0c0`–`r3c3`) per finger, each holding 4096 pressure values in kPa. No metadata or pixel areas are added to this file.

```bash
python examples/stream_glove.py --left PORT_LEFT --right PORT_RIGHT --force calibrations/example_perpixel_pressure.json --seconds 30
python examples/read_one_frame.py PORT_RIGHT --hand rh --force calibrations/example_perpixel_pressure.json
```

Both examples capture a one-second resting tare after connecting. Keep each glove worn and contact-free during that phase. Streaming duration begins after tare. Terminal status reports the peak pixel pressure for each finger; the optional viewer displays raw ADC readings. Calibration is validated before any selected port opens.

```python
from tactile_glove import GloveReader

with GloveReader(
    "/dev/ttyUSB1", hand="rh",
    force="calibrations/example_perpixel_pressure.json",
) as glove:
    resting_adc = glove.tare()  # One second with no tactile contact.
    frame = next(glove.stream())
    print(frame.tactile.finger_pressure_kPa_pixels["index"])  # 16 kPa values.
    print(frame.tactile.finger_pressure_saturated["index"])   # 16 flags.
    print(frame.tactile.finger_pressure_N_pixels["index"])    # 16 Newton values.
```

The parser returns each patch in row-major order starting at its top-left pixel: index `4 * row + col`, with no additional pixel flip needed for display. The SDK uses the GUI recorder's shared per-pixel conversion. Calibrated arrays align with the 16 decoded `finger_pressure` entries for each finger: patch `[row, col]` uses supplier table `r{col}c{row}`. Tare is `max(LUT[live_adc] - LUT[resting_adc], 0)` in pressure. Lookup indices are integer-clamped to 0–4095; original ADC readings of 4096 remain intact. Saturation flags use unmodified raw ADC `>=4000`, including pixels whose tared pressure is zero. Saturated/table-top readings are lower bounds; the supplier specifies 0–207 kPa calibrated and 207–345 kPa extended.

To use an existing resting measurement, pass `baseline_adc=resting_adc`. It must map all five finger names to 16 finite ADC values within 0–4096; half-count medians are accepted. Tare discards older buffered input and measures fresh samples without restarting the device counter. The baseline survives reconnects of the same reader; renew it for a new wearer/session or after putting the glove on again. Reading with a calibration but no baseline raises `RuntimeError` until `tare()` succeeds or a baseline is supplied.

### Per-pixel newtons

The supplier calibration contains kPa lookup values. Both the GUI recorder and SDK output `finger_pressure_kPa_pixels` and `finger_pressure_N_pixels`. For these thin-film gloves, the confirmed active area is **22.5 mm² per pixel**. The exported `tactile_glove.DEFAULT_PIXEL_AREA_MM2` supplies that shared default. The SDK computes `N = kPa × 22.5 × 0.001 = kPa × 0.0225`. With `--force JSON` or `force=path` and a resting tare, all 80 per-pixel Newton values are available automatically.

The API accepts `pixel_area_mm2=measured_pixel_area_mm2` to override the uniform default, or a dictionary mapping each of the five fingers to 16 positive finite areas in decoded patch order. With calibration and a resting baseline, `frame.tactile.finger_pressure_N_pixels["index"]` contains **16 per-pixel forces in newtons**. The pressure and saturation fields remain available. Pass `pixel_area_mm2=None` for pressure-only calibrated output. Raw-only readers have all three calibrated fields set to `None`.

The examples accept a uniform area override through `--pixel-area-mm2 AREA_MM2`; the default is 22.5 mm². `read_one_frame.py` prints all 16 Newton values per finger; streaming status reports each finger's peak pixel force. The calibration JSON itself stays unchanged.

## Build your own data collection pipeline

The example below writes every accepted sample from one right-hand glove to a JSON Lines file for 10 seconds. Use your actual port and a new output filename for each run. It includes all 80 pressure values, five bend values, decoded IMU readings, and both timestamps through the public dataclasses.

```python
from dataclasses import asdict
import json
import time

from tactile_glove import GloveReader

with open("rh_samples.jsonl", "x", encoding="utf-8") as output:
    with GloveReader("/dev/ttyUSB1", hand="rh") as glove:
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            frame = glove.read_frame()
            if frame is not None:
                output.write(json.dumps(asdict(frame)) + "\n")
```

A serial error or `TimeoutError` propagates after both resources close. Add explicit retry behavior if your pipeline should survive disconnects; reconnect the same physical port and create a new `stream()` iterator if the previous one raised. A fresh stream resets the glove millisecond counter.

For a larger pipeline:

- Acquire each glove in its own worker so one port does not stall the other. The [streaming example](../../examples/stream_glove.py) demonstrates this.
- Preserve integer `host_timestamp_ns` and `device_timestamp_ms` alongside every sample. The host timestamp is Unix decode time; the glove counter is elapsed stream time. Independently read gloves and other sensors are not automatically synchronized.
- Keep acquisition separate from slow storage, networking, or rendering. If you buffer data, define capacity and report any dropped samples. The viewer's latest-frame strategy is for display; recording pipelines should retain each accepted frame.
- Use `force=FILE` with a resting tare for per-pixel kPa pressure and saturation flags. Per-pixel Newton output uses the confirmed 22.5 mm² area by default; `pixel_area_mm2` overrides it. Keep the unchanged raw 0–4096 ADC values alongside calibrated data.

Healthy inspected glove output measured 125 Hz, with 8 ms between device counters. Measure the behavior of your complete pipeline under its actual load; this observation is not a guaranteed hardware sampling rate. Raw glove gyro/accelerometer units and usable output remain unverified. See [sensor values and timing](api.md) before converting units or aligning with other sensors.
