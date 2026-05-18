# Tactile Glove SDK API

Python package: `tactile_glove`

The Tactile Glove SDK reads tactile glove data from a serial port and returns structured Python objects for tactile pressure, bend, and IMU orientation data.

Install the platform-specific wheel from the GitHub Releases page before using this API.

## Supported runtime

- Python 3.12 wheels are provided for Ubuntu x86_64 and Windows x86_64.
- Linux serial ports:
  - wireless dongle: `/dev/ttyUSB*`
  - wired USB: `/dev/ttyACM*`
- Windows serial ports: `COM3`, `COM4`, etc.
- Default baud rate: `921600`
- Supported hand labels: `"lh"` and `"rh"`

## Public imports

```python
from tactile_glove import FINGER_NAMES
from tactile_glove import GloveFrame
from tactile_glove import GloveReader
from tactile_glove import IMUData
from tactile_glove import TactileData
```

## `GloveReader`

```python
GloveReader(port: str, hand: str = "lh", baudrate: int = 921600)
```

High-level reader for one tactile glove serial stream.

### Parameters

- `port`: serial port name.
  - Ubuntu examples: `/dev/ttyUSB0`, `/dev/ttyUSB1`, `/dev/ttyACM0`
  - Windows examples: `COM3`, `COM4`
- `hand`: hand label used for sensor layout mapping.
  - `"lh"`: left hand
  - `"rh"`: right hand
- `baudrate`: serial baud rate. Default is `921600`.

### Methods

```python
connect() -> None
```

Open the serial connection.

```python
disconnect() -> None
```

Close the serial connection.

```python
read_frame() -> GloveFrame | None
```

Read and parse one complete glove frame if available. Returns `None` when a full frame is not yet available.

```python
stream() -> Iterator[GloveFrame]
```

Yield parsed frames continuously.

### Context manager usage

`GloveReader` can be used as a context manager. This opens the serial port on entry and closes it on exit.

```python
from tactile_glove import GloveReader

with GloveReader("/dev/ttyUSB0", hand="rh") as glove:
    frame = glove.read_frame()
    if frame is not None:
        print(frame)
```

### Streaming usage

```python
from tactile_glove import GloveReader

with GloveReader("/dev/ttyUSB0", hand="rh") as glove:
    for frame in glove.stream():
        if frame.tactile is None:
            continue
        print(frame.tactile.finger_bend)
```

Windows example:

```python
from tactile_glove import GloveReader

with GloveReader("COM3", hand="rh") as glove:
    frame = glove.read_frame()
    print(frame)
```

## `GloveFrame`

Parsed frame returned by `GloveReader.read_frame()` and `GloveReader.stream()`.

Fields:

```python
sensor_type: int
sensor_type_name: str
tactile: TactileData | None
imu: IMUData | None
timestamp: float
```

### Field descriptions

- `sensor_type`: raw sensor type byte from the glove packet.
- `sensor_type_name`: readable sensor type name when available.
- `tactile`: parsed tactile pressure and bend data. May be `None` if tactile data is unavailable.
- `imu`: parsed IMU orientation data. May be `None` if IMU data is unavailable.
- `timestamp`: host timestamp in Unix epoch seconds when the frame was parsed.

## `TactileData`

Tactile pressure and bend payload.

Fields:

```python
raw_bytes: bytes
finger_pressure: dict[str, list[int]]
finger_bend: dict[str, int]
palm_pressure: list[int]
timestamp: float
```

### `finger_pressure`

Dictionary keyed by finger name. Each finger contains 12 pressure values.

Finger names are:

```python
["thumb", "index", "middle", "ring", "little"]
```

Example:

```python
thumb_pressure = frame.tactile.finger_pressure["thumb"]
index_pressure = frame.tactile.finger_pressure["index"]
```

Shape:

```text
{
  "thumb":  [int, ... 12 values],
  "index":  [int, ... 12 values],
  "middle": [int, ... 12 values],
  "ring":   [int, ... 12 values],
  "little": [int, ... 12 values],
}
```

### `finger_bend`

Dictionary keyed by finger name. Each value is the raw bend sensor value for that finger.

Example:

```python
thumb_bend = frame.tactile.finger_bend["thumb"]
```

Shape:

```text
{
  "thumb": int,
  "index": int,
  "middle": int,
  "ring": int,
  "little": int,
}
```

### `palm_pressure`

List of palm pressure values in display order.

Example:

```python
palm = frame.tactile.palm_pressure
```

## `IMUData`

IMU payload parsed from the glove stream.

Fields:

```python
raw_bytes: bytes
quaternion: tuple[float, float, float, float]
gyro: tuple[float, float, float]
accel: tuple[float, float, float]
timestamp: float
```

### Field descriptions

- `quaternion`: fused orientation quaternion as `(w, x, y, z)`.
- `gyro`: raw gyro tuple `(x, y, z)` in rad/s when available. Current hardware may report zeros.
- `accel`: raw accelerometer tuple `(x, y, z)` in m/s² when available. Current hardware may report zeros.
- `raw_bytes`: raw IMU payload bytes.
- `timestamp`: host timestamp in Unix epoch seconds when the frame was parsed.

Example:

```python
if frame.imu is not None:
    w, x, y, z = frame.imu.quaternion
    print(w, x, y, z)
```

## `FINGER_NAMES`

Canonical finger order used by the SDK:

```python
FINGER_NAMES = ["thumb", "index", "middle", "ring", "little"]
```

Use this when iterating over finger pressure or bend dictionaries:

```python
from tactile_glove import FINGER_NAMES

for finger in FINGER_NAMES:
    pressure = frame.tactile.finger_pressure[finger]
    bend = frame.tactile.finger_bend[finger]
    print(finger, pressure, bend)
```

## Complete example

```python
from tactile_glove import FINGER_NAMES
from tactile_glove import GloveReader

port = "/dev/ttyUSB0"  # Use COM3/COM4 on Windows
hand = "rh"

with GloveReader(port, hand=hand) as glove:
    for frame in glove.stream():
        if frame.tactile is None:
            continue

        print(f"timestamp={frame.timestamp:.6f}")
        for finger in FINGER_NAMES:
            pressure = frame.tactile.finger_pressure[finger]
            bend = frame.tactile.finger_bend[finger]
            print(f"{finger}: pressure={pressure} bend={bend}")

        if frame.imu is not None:
            print(f"quaternion={frame.imu.quaternion}")
```

## Notes

- `read_frame()` is non-blocking at the frame level: it may return `None` until enough serial bytes have arrived for a complete parsed frame.
- For wireless glove dongles on Ubuntu, ensure the user has serial-port permission, usually via the `dialout` group.
- On Windows, install the appropriate USB-serial driver if the glove dongle does not appear as a COM port.
