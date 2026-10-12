# TouchTronix FusionX documentation

**V3 thin-film gloves · V01.12 firmware · `v3-thimfilm`**

Each glove has five 4×4 pressure patches and five bend channels.

## Download v3.0.0

[Release notes and all downloads](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/tag/v3.0.0)

| Package | Windows x86_64 | Linux x86_64 |
|---|---|---|
| FusionX GUI, with Python runtime | [Windows ZIP](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/download/v3.0.0/touchtronix-fusionX-v3.0.0-windows-x86_64.zip) | [Linux AppImage](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/download/v3.0.0/touchtronix-fusionX-v3.0.0-linux-x86_64.AppImage) |
| Glove SDK 0.5.0, for CPython 3.13 | [Windows wheel](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/download/v3.0.0/tactile_glove_sdk-0.5.0-cp313-cp313-win_amd64.whl) | [Linux wheel](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/releases/download/v3.0.0/tactile_glove_sdk-0.5.0-cp313-cp313-linux_x86_64.whl) |

GUI recording requires a TouchTronix license and supported Arducam head camera. Calibrated output requires the matching glove-pair file.

## Choose your workflow

| Guide | Collect |
|---|---|
| [FusionX GUI](docs/gui/README.md) | Gloves, head stereo/IMU, and optional wrist video to MCAP. |
| [Glove SDK](docs/sdk/README.md) | Glove samples and calibrated pressure/force in your own Python pipeline. |

## Daily use and maintenance

- Wipe with a soft, dry cloth; avoid sharp objects and solvents.
- Avoid cable strain or heavy pressure on the control board. Stop using damaged hardware.
- Contact TouchTronix for repairs; do not disassemble the glove.

## Earlier glove configurations

[V1](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/tree/v1-conductive-fabric) · [V2](https://github.com/TouchTronix-Robotics/FusionX-DataCollection/tree/v2-conductive-fabric). V3 needs its own SDK and calibration files.
