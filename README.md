# TouchTronix FusionX documentation

Documentation for **V3 thin-film gloves**, firmware **V01.12**, on branch **`v3-thimfilm`**. Each glove has five 4×4 tactile patches and five bend channels. Choose the guide for how you want to collect data.

## Choose your workflow

| Guide | For | What you collect / control |
|---|---|---|
| **[FusionX GUI data collection](docs/gui/README.md)** | Operators using the full FusionX desktop application | Glove data, required head stereo video/head IMU, and optional wrist video recorded to MCAP. The GUI handles calibration, sensor startup, recording, and recovery. |
| **[Glove SDK for custom pipelines](docs/sdk/README.md)** | Developers building their own acquisition, processing, or storage pipeline | Raw glove tactile/bend/IMU samples and timestamps through Python. Your code controls workers, processing, reconnection, and storage. |

### Full FusionX GUI

Obtain the matching GUI package, license key, and glove-pair calibration from TouchTronix. The Windows ZIP or Linux AppImage includes its Python runtime. Recording requires the supported Arducam head stereo camera; zero, one, or two wrist cameras can be assigned.

- [Installation and recording walkthrough](docs/gui/README.md)
- [Wearer and glove-pair calibration](docs/gui/calibration.md)
- [MCAP topics and recording contract](docs/gui/recording-format.md)
- [GUI troubleshooting and viewer setup](docs/gui/troubleshooting.md)

### Standalone glove SDK

Obtain a validated **`tactile-glove-sdk` 0.5.0** wheel for **CPython 3.13**, Windows x86_64 or Linux x86_64. The public package is `tactile_glove`; assign one reader to each glove port. The SDK can be used independently of the FusionX GUI and cameras.

- [Installation, examples, and a custom collection pipeline](docs/sdk/README.md)
- [Complete Python API](docs/sdk/api.md)
- [Physical sensor diagrams and pixel indexing](docs/sdk/sensors.md)
- [SDK installation, serial access, and timing troubleshooting](docs/sdk/troubleshooting.md)
- [Example scripts](examples/)

This repository supplies documentation, examples, and diagrams. SDK wheels are supplied privately; standalone Foxglove extension/layout assets are supplied with the matching GUI package or separately by TouchTronix.

## Daily use and maintenance

- Contact TouchTronix support for product issues or damaged sensors/cables. Do not disassemble the glove without authorization.
- Keep sharp objects away from the sensor patches and avoid pulling the cables forcefully.
- Inspect the glove and connections before a session; stop using damaged equipment.
- Clean the surface with a soft, dry cloth and avoid corrosive solvents.
- Avoid excessive pressure on the main control board.

## Earlier glove configurations

Earlier conductive-fabric guides remain on [v1-conductive-fabric](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/tree/v1-conductive-fabric) and [v2-conductive-fabric](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/tree/v2-conductive-fabric). Their SDKs, packet formats, and calibration files do not apply to these V3 gloves. Branch names identify glove configurations independently of SDK package versions.
