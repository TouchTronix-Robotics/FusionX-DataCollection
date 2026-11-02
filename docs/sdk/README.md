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

Base installation needs only pyserial and NumPy. Add `viewer` for PySide6/pyqtgraph or `audio` for the GUI's pinned miniaudio binding. For example, using a downloaded Linux x86_64 wheel:

```bash
python -m pip install "./tactile_glove_sdk-0.6.0-cp313-cp313-linux_x86_64.whl[viewer,audio]"
python examples/stream_glove.py --left /dev/ttyUSB0 --right /dev/ttyUSB1 --viewer
```

Use the matching Windows or ARM64 wheel filename on those platforms, and install only the extras you need. The viewer needs a desktop/display session and compatible Qt runtime libraries. It shows raw ADC at 25 FPS while each port acquires independently. Close the window or press Ctrl+C to stop and close ports.

All three SDK wheels include the original **13 English/Chinese calibration WAVs and beeps**, including when installed without extras. The `audio` extra supplies playback; no separate GUI installation, asset download, or speech service is needed. On Linux ARM64, the optional miniaudio binding may build from source and need a C compiler and Python development headers. Base acquisition and silent calibration do not need these audio build dependencies.

## Terminal wearer calibration

Close the GUI or other readers using these ports, then run from the repository root:

```bash
python examples/calibrate_gloves.py --left COM3 --right COM4 --user operator --output operator.json
# One glove also works:
python examples/calibrate_gloves.py /dev/ttyUSB0 --hand lh --user operator --output operator.json
```

Follow the printed **OPEN HAND** instruction with the worn glove relaxed and tactile pads contact-free, then make a **FIST** when instructed. Collection lasts three seconds per pose by default (`--hold-seconds` changes it). The routine uses the GUI's current calibration logic and saves a GUI-compatible wearer JSON with five 4×4 resting ADC patches, bend endpoints, pose samples, and quality results. Fist samples contain bend data only.

Audio plays automatically when miniaudio is available. `--language cn` selects Chinese voice cues; printed terminal instructions are English. Use `--no-audio` for silence. Missing audio or an output-device failure is reported while text instructions remain usable. Ctrl+C closes the ports and audio output. Failed/cancelled attempts preserve an existing output file; success replaces it.

The same workflow is available in Python:

```python
from tactile_glove import calibrate

wearer = calibrate(
    {"lh": "COM3", "rh": "COM4"},
    user="operator", output="operator.json",
    # language="cn",  # Chinese voice cues.
    # audio=False,    # Silent mode.
)
resting_adc = wearer["gloves"]["lh"]["tactile_zero_finger"]
```

Supply `resting_adc` as `GloveReader(..., force=PAIR_LUT, baseline_adc=resting_adc)` for the same wearer/session. The wearer calibration measures resting ADC and bend endpoints; pressure/newton output also needs the matching supplier per-pixel pressure LUT. Renew wearer calibration after putting the glove on again or changing wearers. See [the calibration API](api.md#wearer-calibration) for every argument, loading saved JSON, and cancellation.

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
