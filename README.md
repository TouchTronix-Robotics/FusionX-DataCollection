# TouchTronix FusionX documentation

Documentation for **V3 thin-film gloves**, firmware **V01.12**, on branch **`v3-thimfilm`**. Each glove has five 4×4 tactile patches and five bend channels. Choose the guide for how you want to collect data.

## Download v3.0.0

[Release notes and all downloads](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/tag/v3.0.0)

| Package | Windows x86_64 | Linux x86_64 |
|---|---|---|
| FusionX GUI, with Python runtime | [Windows ZIP](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/download/v3.0.0/touchtronix-fusionX-v3.0.0-windows-x86_64.zip) | [Linux AppImage](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/download/v3.0.0/touchtronix-fusionX-v3.0.0-linux-x86_64.AppImage) |
| Glove SDK 0.5.0, for CPython 3.13 | [Windows wheel](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/download/v3.0.0/tactile_glove_sdk-0.5.0-cp313-cp313-win_amd64.whl) | [Linux wheel](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/download/v3.0.0/tactile_glove_sdk-0.5.0-cp313-cp313-linux_x86_64.whl) |

The GUI requires a TouchTronix license and the supported Arducam head camera for recording. The SDK works independently with your own Python 3.13 environment. Obtain the matching glove-pair calibration from TouchTronix for calibrated pressure/force output.

## Choose your workflow

| Guide | For | What you collect / control |
|---|---|---|
| **[FusionX GUI data collection](docs/gui/README.md)** | Operators using the full FusionX desktop application | Glove data, required head stereo video/head IMU, and optional wrist video recorded to MCAP. The GUI handles calibration, sensor startup, recording, and recovery. |
| **[Glove SDK for custom pipelines](docs/sdk/README.md)** | Developers building their own acquisition, processing, or storage pipeline | Raw glove tactile/bend/IMU samples, timestamps, and optional calibrated per-pixel pressure/force through Python. Your code controls workers, processing, reconnection, and storage. |

## Daily use and maintenance

- Contact TouchTronix support for product issues or damaged sensors/cables. Do not disassemble the glove without authorization.
- Keep sharp objects away from the sensor patches and avoid pulling the cables forcefully.
- Inspect the glove and connections before a session; stop using damaged equipment.
- Clean the surface with a soft, dry cloth and avoid corrosive solvents.
- Avoid excessive pressure on the main control board.

## Earlier glove configurations

Earlier conductive-fabric guides remain on [v1-conductive-fabric](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/tree/v1-conductive-fabric) and [v2-conductive-fabric](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/tree/v2-conductive-fabric). Their SDKs, packet formats, and calibration files do not apply to these V3 gloves. Branch names identify glove configurations independently of SDK package versions.
