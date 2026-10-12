# V3 thin-film SDK API

The supplied `tactile-glove-sdk` **0.4.0** wheel exports the `tactile_glove` package. Runtime reader/parser modules are compiled. The examples in this repository use that installed wheel.

```python
from tactile_glove import GloveReader, GloveFrame, TactileData, IMUData, FINGER_NAMES
```

## GloveReader

```python
reader = GloveReader("COM3", hand="lh", baudrate=1_000_000)
```

| Argument | Default | Meaning |
|---|---|---|
| `port` | Required string | One explicit serial port. Create separate readers for two gloves. |
| `hand` | `"lh"` | Caller-supplied `"lh"` or `"rh"`; device packets have no hand identifier. |
| `baudrate` | `1_000_000` | Wired V01.12 speed; 8 data bits, no parity, one stop bit. |

| Operation | Behavior |
|---|---|
| `connect()` | Opens the port, stops a stale stream, queries firmware/battery, and starts combined samples. |
| `disconnect()` | Stops streaming and closes the port; use it during cleanup and before reconnecting. |
| `read_frame()` | Returns `GloveFrame` or `None` during a short read wait. Two seconds without a valid sensor sample raises `TimeoutError`. |
| `stream()` | Yields accepted complete frames, skipping temporary `None` results without resampling. |
| `with GloveReader(...) as reader:` | Connects on entry and disconnects on exit, including when the body raises. |

Use one consumer per reader; do not read the same instance from multiple threads. The example's acquisition workers belong to the example, not to the synchronous `GloveReader` API. The application separately implements reconnection retries.

## GloveFrame

Each accepted V01.12 frame contains both tactile/bend data and IMU fields. There are no pressure-only or IMU-only frame variants.

| Field | Type | Meaning |
|---|---|---|
| `hand` | `str` | Your explicit `lh`/`rh` assignment. |
| `tactile` | `TactileData` | All five finger patches and bend channels. |
| `imu` | `IMUData` | Euler angles and raw motion fields. |
| `host_timestamp_ns` | `int` | Unix host timestamp in nanoseconds. |
| `device_timestamp_ms` | `int` | Glove elapsed stream counter, separate from Unix time. |
| `message_sequence` | `int` | Protocol NUM; it can repeat and must not be used to discard valid readings. |

Timing belongs to `GloveFrame`; sensor objects have no separate timestamps. There is no SDK `frame.timestamp` property. Convert host time to seconds with `frame.host_timestamp_ns / 1_000_000_000` if needed.

Sending the start command restarts the unsigned 32-bit millisecond counter at zero, including when already streaming. Its range is 0–4,294,967,295 ms (about 49.71 days); firmware overflow behavior has not been measured. Do not substitute this counter for the host timestamp or infer a reconnection solely from repeated protocol sequence numbers.

## TactileData

| Field | Shape | Values / order |
|---|---|---|
| `finger_pressure` | `dict[str, list[int]]` | Five named 4×4 patches, each flattened row-major to 16 entries. |
| `finger_bend` | `dict[str, int]` | One raw ADC value per named finger. |
| `pressure_raw` | 80 integers | Original wire order: 16 thumb, 16 index, 16 middle, 16 ring, 16 little. |
| `bend_raw` | Five integers | Original wire order: little, ring, middle, index, thumb. |
| `raw_bytes` | `bytes` | Original tactile/bend payload bytes. |

`FINGER_NAMES` is `["thumb", "index", "middle", "ring", "little"]`. ADC values remain **0–4095**. The SDK does not apply wearer tare, pressure LUTs, polynomial force conversion, or bend-angle calibration.

For named patch `[row, column]`:

```python
value = frame.tactile.finger_pressure["index"][4 * row + column]
# Equivalent original channel for finger index 1:
value_from_wire = frame.tactile.pressure_raw[16 + 4 * column + (3 - row)]
```

See the [left](glove-map-lh.png) and [right](glove-map-rh.png) diagrams. The GUI/SDK display correction places decoded row zero at the bottom; display changes never reorder recorded wire arrays. This glove has no palm channels or separate two-value bend/dorsal structure.

## IMUData

| Field | Tuple order | Meaning |
|---|---|---|
| `euler_deg` | `(pitch, roll, yaw)` | Raw device Euler angles in degrees; no hand-dependent sign changes. |
| `gyro_raw` | `(x, y, z)` | Signed 16-bit device values; physical scaling is unverified. |
| `accel_raw` | `(x, y, z)` | Signed 16-bit device values; physical scaling is unverified. |
| `raw_bytes` | `bytes` | Original IMU payload bytes. |

Inspected V01.12 samples had populated Euler angles but zero raw gyro/accelerometer values. Preserve those fields without claiming verified rad/s or m/s² for the glove. The firmware does not transmit a quaternion or magnetometer reading.

## Example behavior

```bash
python examples/stream_glove.py --left COM3 --right COM4 --viewer --seconds 30
python examples/stream_glove.py COM3 --hand lh --seconds 10
```

The stream reports counts, mean received rate, and frame age once per second. Each selected port has its own worker. The optional viewer shows raw tactile/bend readings only and refreshes from the newest frame at 25 FPS. Unselected hands are labelled; stale readings dim.

Closing the viewer is checked before rendering another frame, so queued refreshes cannot access its closed graphics scene. Duration expiry, Ctrl+C, window close, and reader/rendering errors all stop and join acquisition and close ports. The script does not save recordings or reconnect automatically.

`examples/read_one_frame.py` reads one frame. `examples/test_glove.py` reports serial bytes/frame counts and writes a hex dump (default `glove_raw_bytes.txt`; `--raw-output` selects a different path). Run diagnostics only when the GUI and other readers have released that port.
