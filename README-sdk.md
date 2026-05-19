# Tactile Glove Python SDK

Use the Python SDK package when you want to read tactile glove data directly from Python.

The Python SDK wheel is provided separately on request. After you receive the wheel file, use the instructions below to install it into your Python environment.

## SDK package

- `tactile_glove_sdk-*.whl` — packaged Python wheel for the documented `tactile_glove` API

Choose the wheel that matches your operating system and Python version. For example, Python 3.12 wheels are named like:

```text
tactile_glove_sdk-0.1.0-cp312-cp312-linux_x86_64.whl
tactile_glove_sdk-0.1.0-cp312-cp312-win_amd64.whl
```

## Install the wheel

Ubuntu install example:

```bash
python3.12 -m venv ~/glove
source ~/glove/bin/activate
python3 -m pip install tactile_glove_sdk-0.1.0-cp312-cp312-linux_x86_64.whl
```

Windows PowerShell install example:

```powershell
py -3.12 -m venv glove
.\glove\Scripts\Activate.ps1
python -m pip install tactile_glove_sdk-0.1.0-cp312-cp312-win_amd64.whl
```

The wheel declares its runtime dependency on `pyserial`, so normal `pip install <wheel>` usage installs the Python dependency automatically when needed. You do not need Cython, build tools, pytest, or a source checkout to use the released wheel.

## Basic Python usage

```python
from tactile_glove import GloveReader

with GloveReader("/dev/ttyUSB0", hand="rh") as glove:
    frame = glove.read_frame()
    if frame is not None and frame.tactile is not None:
        print(frame.tactile.finger_pressure["thumb"])
        print(frame.imu.quaternion if frame.imu is not None else None)
```

Use `COM3`, `COM4`, etc. for Windows serial ports. Use `/dev/ttyUSB*` for the wireless dongle and `/dev/ttyACM*` for wired USB on Linux. The default baud rate is `921600`; supported hand labels are `"lh"` and `"rh"`.

## Example scripts

Example scripts are available under `examples/`:

```bash
python examples/sdk_read_one_frame.py /dev/ttyUSB0 --hand rh
python examples/sdk_stream_glove.py /dev/ttyUSB0 --hand rh --show-fps
# Diagnose serial connectivity and SDK parsing.
python examples/test_glove.py /dev/ttyUSB0 --hand rh
```

The diagnostic script prints raw byte counts, glove frame header counts, parsed SDK frame counts, and troubleshooting hints.

## Ubuntu serial-port access

Check serial-port access before using `sudo`. The user should be able to open the glove port from the same Python environment used to run the examples:

```bash
# Check which user and Python environment will run the SDK.
whoami
which python
python --version

# Confirm the glove serial device exists and note its group, usually dialout.
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null

# Confirm the current user is in the serial-port access group.
# On Ubuntu this is usually dialout; on some Linux distributions it may be uucp.
groups

# Replace /dev/ttyUSB0 with the actual glove port from the ls command above.
python - <<'PY'
import serial

port = "/dev/ttyUSB0"
with serial.Serial(port, baudrate=921600, timeout=1.0):
    print(f"Serial access OK: opened {port}")
PY
```

If opening the port fails with `Permission denied`, add the user to `dialout`, then log out and back in before retrying:

```bash
sudo usermod -aG dialout "$USER"
```

Avoid `sudo python ...` for normal SDK use because it can switch to root's Python environment instead of the activated virtual environment.

## Windows serial ports

On Windows, replace the serial port with a COM port, for example:

```powershell
python examples\sdk_read_one_frame.py COM3 --hand rh
python examples\sdk_stream_glove.py COM3 --hand rh --show-fps
```

## API reference

See [Tactile Glove SDK API](docs/tactile-glove-sdk-api.md) for the full public API and data shapes.
