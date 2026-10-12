# Glove SDK for custom data collection

Use the `tactile_glove` Python package to acquire V01.12 glove samples and integrate them into your own collection, robotics, processing, or storage pipeline. Each port has an explicitly assigned hand, and each accepted frame contains tactile, bend, IMU, and host/device timing fields.

The SDK handles serial commands, framing, CRC validation, and decoding. Your application controls acquisition workers, reconnection, processing, and output storage. Cameras and the FusionX GUI are optional components of your own system.

- [Full Python API](api.md)
- [Sensor layout and indexing](sensors.md)
- [SDK installation and serial troubleshooting](troubleshooting.md)
- [Documentation home](../../README.md)

## Install and try the SDK

TouchTronix supplies matching compiled wheels privately. This branch contains SDK examples and documentation, **not SDK wheels**. This API documentation targets SDK **0.5.0**; request a matching validated wheel for **CPython 3.13**, your OS, and x86_64 architecture. A `cp313` wheel cannot be installed into Python 3.12 or 3.14. Install the wheel into your own Python environment.

Linux, from the directory containing your supplied wheel:

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
- Apply any force/pressure calibration in your own processing layer while keeping the raw 0–4096 ADC values. SDK 0.5.0 accepts no calibration-file argument and produces no calibrated force or pressure.

Healthy inspected glove output measured 125 Hz, with 8 ms between device counters. Measure the behavior of your complete pipeline under its actual load; this observation is not a guaranteed hardware sampling rate. Raw glove gyro/accelerometer units and usable output remain unverified. See [sensor values and timing](api.md) before converting units or aligning with other sensors.
