# Glove SDK for custom data collection

Acquire glove samples in your own Python pipeline. The SDK handles serial decoding and optional calibration; your code handles storage and reconnection.

[Python API](api.md) · [Sensor maps](sensors.md) · [Troubleshooting](troubleshooting.md) · [Home](../../README.md)

## Install and try the SDK

Download the **SDK 0.5.0** wheel for your OS from [v3.0.0](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/tag/v3.0.0). Requires **64-bit CPython 3.13**. Use `--force-reinstall` when replacing an earlier 0.5.0 build.

Linux:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install ./tactile_glove_sdk-0.5.0-cp313-cp313-linux_x86_64.whl
```

Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .\tactile_glove_sdk-0.5.0-cp313-cp313-win_amd64.whl
```

Get the examples, then assign your actual glove ports:

```bash
git clone --single-branch --branch v3-thimfilm https://github.com/TouchTronix-Robotics/FusionX-DataCollection.git
cd FusionX-DataCollection
# Linux example; Windows ports are typically COM3/COM4.
python examples/stream_glove.py --left /dev/ttyUSB0 --right /dev/ttyUSB1 --viewer
# One glove also works:
python examples/read_one_frame.py /dev/ttyUSB0 --hand lh
```

The viewer shows raw ADC at 25 FPS while each port acquires independently. Close the window or press Ctrl+C to stop and close ports.

## Read samples in your application

```python
from tactile_glove import GloveReader

with GloveReader("/dev/ttyUSB0", hand="lh") as glove:
    frame = next(glove.stream())
    print(frame.tactile.finger_pressure["index"])  # One ADC reading per pixel (16 pixels).
    print(frame.tactile.finger_bend["index"])      # One bend ADC.
    print(frame.imu.euler_deg)                    # Pitch, roll, yaw in degrees.
    print(frame.host_timestamp_ns, frame.device_timestamp_ms)
```

See [the API examples](api.md) for every field, polling, and reconnection.

## Optional per-pixel calibration

The [example file](../../calibrations/example_perpixel_pressure.json) is for **LH_1/RH_1**. Use your own calibration for other gloves. Run from the repository root:

```bash
# Worn gloves must stay contact-free during the one-second startup tare.
python examples/read_calibrated_glove.py COM3 --hand lh --force calibrations/example_perpixel_pressure.json --seconds 10
```

The script prints raw ADC, pressure, force, and saturation for each pixel. `--interval` controls terminal refresh; acquisition continues between updates.

| Output | Readings per finger | Unit |
|---|---|---|
| Pressure | One reading for each of the 16 pixels. | kPa |
| Force | One reading for each of the 16 pixels. | N |
| Saturation | One flag for each of the 16 pixels. | Boolean (`raw ADC >=4000`) |

### Per-pixel newtons

`N = kPa × area_mm2 × 0.001`. Use `--pixel-area-mm2 AREA` or API `pixel_area_mm2` to override 22.5 mm². API `pixel_area_mm2=None` selects pressure only.

[Calibration API examples](api.md#per-pixel-calibration) · [LUT format and conversion](../gui/calibration.md#supplier-per-pixel-pressure)

## Build your own data collection pipeline

Save every accepted frame for 10 seconds, including both timestamps:

```python
from dataclasses import asdict
import json
import time
from tactile_glove import GloveReader

with open("lh_samples.jsonl", "x", encoding="utf-8") as output:
    with GloveReader("/dev/ttyUSB0", hand="lh") as glove:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            frame = glove.read_frame()
            if frame is not None:
                output.write(json.dumps(asdict(frame)) + "\n")
```

Use a new output filename each run. For two gloves, acquire each port in its own worker. Buffer slow storage with a defined capacity and report dropped samples; the viewer's latest-frame approach is for display.
