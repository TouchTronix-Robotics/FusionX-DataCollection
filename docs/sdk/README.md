# Glove SDK for custom data collection

Acquire glove samples in your own Python pipeline. The SDK handles serial decoding and optional calibration; your code handles storage and reconnection.

[Python API](api.md) · [Sensor maps](sensors.md) · [Troubleshooting](troubleshooting.md) · [Home](../../README.md)

## Install and try the SDK

Download the **SDK 0.6.0** wheel for your OS and architecture from [v3.0.0](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/tag/v3.0.0). Requires **64-bit CPython 3.13**. Use `--force-reinstall` when replacing another build of the same SDK version.

Linux x86_64:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install ./tactile_glove_sdk-0.6.0-cp313-cp313-linux_x86_64.whl
```

Linux ARM64 (`aarch64`), with glibc 2.28+:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install ./tactile_glove_sdk-0.6.0-cp313-cp313-linux_aarch64.whl
```

The ARM64 wheel supports compatible 64-bit Raspberry Pi OS and other glibc-based systems; it does not require Ubuntu. The generic `linux_aarch64` tag does not encode the glibc requirement. It does not cover 32-bit ARM, musl-based systems, or other Python minor versions.

Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install .\tactile_glove_sdk-0.6.0-cp313-cp313-win_amd64.whl
```

Get the examples, then assign your actual glove ports:

```bash
git clone --single-branch --branch v3-thimfilm https://github.com/TouchTronix-Robotics/FusionX-DataCollection.git
cd FusionX-DataCollection
# Linux example; Windows ports are typically COM3/COM4.
python examples/stream_glove.py --left /dev/ttyUSB0 --right /dev/ttyUSB1 --seconds 10
# One glove also works:
python examples/read_one_frame.py /dev/ttyUSB0 --hand lh
```

### Optional viewer and audio

Install `audio` for spoken calibration instructions, `viewer` for the live glove display, or both. Run this in the folder containing your downloaded wheel (Linux x86_64 example):

```bash
python -m pip install "./tactile_glove_sdk-0.6.0-cp313-cp313-linux_x86_64.whl[viewer,audio]"
```

Use your platform's wheel filename. For just one option, replace `[viewer,audio]` with `[viewer]` or `[audio]`. All sound files are included in the wheel.

To open the viewer, run from the `FusionX-DataCollection` folder cloned above:

```bash
python examples/stream_glove.py --left /dev/ttyUSB0 --right /dev/ttyUSB1 --viewer
```

The viewer needs a desktop session. If installation or playback fails, see [troubleshooting](troubleshooting.md#quick-fixes), including Linux ARM64 audio build requirements.

## Glove calibration

Put on the gloves and close the GUI or any other program using their ports. From the `FusionX-DataCollection` folder, run:

```bash
python examples/calibrate_gloves.py --left /dev/ttyUSB0 --right /dev/ttyUSB1 --user operator --output operator.json
```

Replace the ports with your actual left/right glove ports (`COM3` and `COM4`, for example, on Windows), and replace `operator` with the wearer's name. For one glove, omit the unused `--left` or `--right` option.

Follow the prompts: hold your hands **OPEN** with the pads touching nothing, then make a **FIST** when asked. The script records each pose for three seconds. The result is saved to `operator.json`, which the GUI can also load.

English audio plays automatically when available after installing the `audio` option. Add `--language cn` for Chinese audio or `--no-audio` for silence. Text instructions always appear in English, even if sound is unavailable. Press Ctrl+C to cancel.

You can also call calibration from Python:

```python
from tactile_glove import calibrate

calibrate(
    {"lh": "/dev/ttyUSB0", "rh": "/dev/ttyUSB1"},
    user="operator", output="operator.json",
)
```

Repeat calibration after putting the gloves on again or changing wearers. This records resting sensor readings and finger bend endpoints; pressure/force output also needs the matching supplier calibration file. See [the calibration API](api.md#wearer-calibration) to reuse the saved readings in your SDK code.

### Use the saved JSON to zero tactile readings

Save this as `read_zeroed.py` in the same `FusionX-DataCollection` folder as `operator.json`, then run `python read_zeroed.py`:

```python
import json
from tactile_glove import GloveReader

HAND = "lh"  # Use "rh" and the right glove's port for the right hand.
PORT = "/dev/ttyUSB0"  # Windows example: "COM3".
with open("operator.json", encoding="utf-8") as source:
    wearer = json.load(source)
baseline = wearer["gloves"][HAND]["tactile_zero_finger"]

try:
    with GloveReader(PORT, hand=HAND) as glove:
        for frame in glove.stream():
            raw = frame.tactile.finger_pressure
            zeroed = {
                finger: [
                    max(0.0, value - resting)
                    for value, resting in zip(values, baseline[finger], strict=True)
                ]
                for finger, values in raw.items()
            }
            # Send zeroed to your processing/storage code; each finger has 16 pixels.
            print("index raw ADC:", raw["index"])
            print("index zeroed ADC:", zeroed["index"])
except KeyboardInterrupt:
    pass  # The context manager closes the glove port.
```

This subtracts each pixel's saved resting reading and clips negative results to zero, preserving fractional baselines. For example, raw `120` with baseline `100.5` becomes `19.5`; raw `98` becomes `0`. The `zeroed` dictionary contains all five fingers in the same pixel order as `raw`. The original frame, bend readings, and timestamps stay unchanged. Small positive readings can remain because of sensor noise.

Use the JSON for the same physical glove, hand, and wearing session. The selected hand must be present in the JSON; renew calibration after putting the glove on again or changing wearers. This example produces ADC counts and needs no supplier pressure file.

For kPa or newtons, pass the saved baseline as `baseline_adc` together with the matching supplier `force` file; see [saved-baseline pressure/force](api.md#use-the-saved-json-for-pressure-and-force). That option calibrates the pressure/force fields and leaves raw ADC unchanged.

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
