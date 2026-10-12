# Glove SDK Python API

[SDK guide](README.md) · [Sensor indexing](sensors.md) · [Troubleshooting](troubleshooting.md)

The `tactile-glove-sdk` **0.5.0** API exports the `tactile_glove` package. Runtime reader/parser modules are compiled. The examples in this repository use that installed wheel.

```python
from tactile_glove import (
    GloveReader, GloveFrame, TactileData, IMUData,
)
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
| `force` | `None`, keyword-only | Optional path to supplier per-pixel pressure LUT JSON for this physical glove pair, such as `calibrations/example_perpixel_pressure.json`. |
| `baseline_adc` | `None`, keyword-only | Optional mapping of five finger names to 16 finite resting ADC values each in 0–4096, in top-left row-major order. Requires `force`; otherwise call `tare()` before reading. |
| `pixel_area_mm2` | `22.5`, keyword-only | Active area in mm²: one positive finite uniform area or five finger names mapped to 16 areas in decoded patch order. The confirmed default enables per-pixel Newton output with calibration; `None` selects pressure-only output. |

| Operation | Behavior |
|---|---|
| `connect()` | Opens the port, stops a stale stream, queries firmware/battery, and starts combined samples. Connecting again restarts the connection and glove counter. |
| `disconnect()` | Stops streaming, closes the port, and clears pending input. Repeated calls are safe. |
| `read_frame()` | Returns `GloveFrame` or `None` while waiting for a complete valid packet; it can block briefly on a serial read. Two seconds without a valid sample raises `TimeoutError`. |
| `stream()` | Yields accepted complete frames, skipping temporary `None` results without resampling. |
| `tare(duration_s=1.0)` | With per-pixel calibration enabled and the reader connected, clears buffered input and measures fresh accepted samples for the interval after the first fresh sample, then prepares pressure-domain lookup tables from per-pixel resting ADC medians. Returns `dict[str, list[float]]`. Keep the worn glove contact-free. |
| `with GloveReader(...) as reader:` | Connects on entry and disconnects on exit, including when the body raises. |

Use one consumer per reader; do not read the same instance from multiple threads. The example's acquisition workers belong to the example, not to the synchronous `GloveReader` API. The SDK propagates serial errors and does not reconnect automatically. Reading before connecting raises `RuntimeError`; an unsupported hand raises `ValueError`. The valid-sample timeout starts at the stream-start command and resets only for accepted samples, not metadata or malformed packets. Recover by disconnecting/reconnecting and creating a new `stream()` iterator if the previous one raised. A prepared resting baseline survives reconnects of the same reader; renew it for a new wearer/session or after putting the glove on again. Invalid per-pixel calibration, areas, or resting ADC values raise `ValueError`. Reading with a force file but no resting baseline raises `RuntimeError` until `tare()` succeeds or `baseline_adc` is supplied.

## GloveFrame

Each accepted V01.12 frame contains both tactile/bend data and IMU fields. There are no pressure-only or IMU-only frame variants.

| Field | Type | Meaning |
|---|---|---|
| `hand` | `str` | Your explicit `lh`/`rh` assignment. |
| `tactile` | `TactileData` | All five finger patches and bend channels. |
| `imu` | `IMUData` | Euler angles and raw motion fields. |
| `host_timestamp_ns` | `int` | Unix host time in nanoseconds when a valid packet is decoded; serial buffering and processing can delay it. |
| `device_timestamp_ms` | `int` | Glove elapsed stream counter, separate from Unix time. |

Timing belongs to `GloveFrame`; sensor objects have no separate timestamps. There is no SDK `frame.timestamp` property. Convert host time to seconds with `frame.host_timestamp_ns / 1_000_000_000` if needed.

Sending the start command restarts the unsigned 32-bit millisecond counter at zero, including when already streaming. Its range is 0–4,294,967,295 ms (about 49.71 days); firmware overflow behavior has not been measured. Do not substitute this counter for the host timestamp. Healthy inspected output advanced by 8 ms per sample (125 Hz); the SDK returns accepted samples without resampling.

## TactileData

| Field | Shape | Values / order |
|---|---|---|
| `finger_pressure` | `dict[str, list[int]]` | Five named 4×4 patches, flattened row-major to 16 entries with `(0, 0)` at the top left. |
| `finger_bend` | `dict[str, int]` | One raw ADC value per named finger. |
| `finger_pressure_kPa_pixels` | `dict[str, list[float]]` or `None` | Five named lists of 16 calibrated contact pressures in kPa; `None` without calibration. |
| `finger_pressure_saturated` | `dict[str, list[bool]]` or `None` | Matching saturation flags from original raw ADC `>=4000`; `None` without calibration. |
| `finger_pressure_N_pixels` | `dict[str, list[float]]` or `None` | Matching 16 per-pixel forces in newtons per finger with calibration, using 22.5 mm² by default; `None` without calibration or with `pixel_area_mm2=None`. |

Finger dictionaries use `"thumb"`, `"index"`, `"middle"`, `"ring"`, and `"little"` in that order. ADC values remain **0–4096**, and the reader's default pixel area is **22.5 mm²**. All 80 pressure and five bend channels are present in the named finger dictionaries. Optional calibrated pixel arrays align with these unchanged raw ADC fields. Bend-angle calibration is not applied. The examples define their display conventions directly; the SDK exports the four classes shown above.

For named patch `[row, column]`:

```python
value = frame.tactile.finger_pressure["index"][4 * row + column]
# Corresponding pressure wire-channel index for the index finger:
wire_index = 16 + 4 * column + row
```

See the [left](../glove-map-lh.svg) and [right](../glove-map-rh.svg) diagrams. The parser returns decoded row zero at the top, so the viewer consumes each patch directly without flipping its data. Each pressure patch is a Python list; reshape its 16 row-major entries to 4×4 when needed. This glove has no palm channels or separate two-value bend/dorsal structure.

## IMUData

| Field | Tuple order | Meaning |
|---|---|---|
| `euler_deg` | `(pitch, roll, yaw)` | Raw device Euler angles in degrees; no hand-dependent sign changes. |
| `gyro_raw` | `(x, y, z)` | Signed 16-bit device values; physical scaling is unverified. |
| `accel_raw` | `(x, y, z)` | Signed 16-bit device values; physical scaling is unverified. |

Inspected V01.12 samples had populated Euler angles but zero raw gyro/accelerometer values. Preserve those fields without claiming verified rad/s or m/s² for the glove. The firmware does not transmit a quaternion or magnetometer reading.

## API changes in 0.5.0

Public frames omit `message_sequence`, `tactile.pressure_raw`, `tactile.bend_raw`, `tactile.raw_bytes`, and `imu.raw_bytes`. Use the named finger dictionaries for all 85 tactile/bend channels and the glove millisecond counter for sample spacing. The public data types are Python dataclasses in `tactile_glove.reader`; import them through `tactile_glove`. Tactile dictionaries/lists are mutable, while IMU values are tuples.

The SDK supports supplier per-pixel calibration through `force=FILE`, with `tare()` or provided `baseline_adc`. See [per-pixel calibration](README.md#optional-per-pixel-calibration) and [building a custom pipeline](README.md#build-your-own-data-collection-pipeline).

## Per-pixel calibration

```python
from tactile_glove import GloveReader

with GloveReader("COM3", hand="lh", force="calibrations/example_perpixel_pressure.json") as glove:
    resting_adc = glove.tare()  # One second, worn glove touching nothing.
    frame = next(glove.stream())
    print(frame.tactile.finger_pressure_kPa_pixels["thumb"])  # 16 values.
    print(frame.tactile.finger_pressure_saturated["thumb"])
    print(frame.tactile.finger_pressure_N_pixels["thumb"])  # 16 Newton values.
```

With a recent resting measurement, pass `baseline_adc=resting_adc` to enable calibrated output on the first accepted sample. Resting measurements use top-left row-major order. Tare discards buffered input, consumes fresh samples, and leaves the glove counter running. A failed tare invalidates the previous baseline.

`force` accepts the supplier JSON with exactly `lh` and `rh`, all five fingers in each hand, and exactly 16 raw pixel keys `r0c0`–`r3c3` per finger. Each table contains 4096 finite nonnegative kPa values, starts at zero, and never decreases. No metadata is required. This file belongs to physical gloves LH_1/RH_1; supply their matching hand assignments. Malformed tables and polynomial calibration files are rejected before a port opens.

The SDK reuses the GUI recorder's lookup preparation and conversion. Decoded patch `[row, col]` uses table `r{col}c{row}`. Contact pressure is `max(LUT[live_adc] - LUT[resting_adc], 0)`. Live and resting indices are clamped integers in 0–4095; raw ADC 4096 is preserved in `finger_pressure`. Saturation is based on raw ADC `>=4000`, even when tared pressure is zero. Output retains all 80 pixels without resampling. The guide defines 0–207 kPa calibrated and 207–345 kPa extended; saturated/table-top readings are lower bounds.

The supplied file contains kPa lookup values. Both the GUI recorder and SDK output per-pixel kPa and newtons. For these thin-film gloves the confirmed active area is **22.5 mm² per pixel**. The SDK therefore provides `finger_pressure_N_pixels` by default with `force` and a resting baseline: `N = kPa × 22.5 × 0.001 = kPa × 0.0225`. All five fingers retain their 16 individual pixel forces.

Override `pixel_area_mm2` with another measured uniform area or a five-finger dictionary of 16 areas per finger in decoded patch order. Pass `None` for pressure-only output. Raw ADC values, pressure, saturation flags, and both timestamps remain available.

## Example behavior

Run these commands from the cloned repository root.

```bash
python examples/stream_glove.py --left COM3 --right COM4 --viewer --seconds 30
python examples/stream_glove.py COM3 --hand lh --seconds 10
python examples/stream_glove.py --left COM3 --right COM4 --force calibrations/example_perpixel_pressure.json --seconds 30
```

The stream reports counts, mean received rate, and frame age once per second. With `--force`, it validates all selected hands before opening ports, takes a one-second contact-free tare per hand, and includes peak pixel pressures in kPa in terminal status. It also reports peak pixel forces in N using 22.5 mm² by default; `--pixel-area-mm2 AREA_MM2` overrides the area. Timed streaming begins after tare. Each selected port has its own worker. The optional viewer shows raw tactile/bend readings only and refreshes from the newest frame at 25 FPS. Unselected hands are labelled; stale readings dim.

Closing the viewer is checked before rendering another frame, so queued refreshes cannot access its closed graphics scene. Duration expiry, Ctrl+C, window close, and reader/rendering errors all stop and join acquisition and close ports. The script does not save recordings or reconnect automatically.

`examples/read_one_frame.py` reads one frame. `examples/test_glove.py` reports serial bytes/frame counts and writes a hex dump (default `glove_raw_bytes.txt`; `--raw-output` selects a different path). Run diagnostics only when the GUI and other readers have released that port.
