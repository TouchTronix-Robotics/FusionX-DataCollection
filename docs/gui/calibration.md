# FusionX GUI calibration

[GUI guide](README.md) · [Recording format](recording-format.md) · [Troubleshooting](troubleshooting.md)

| Selector | Purpose |
|---|---|
| **User Calibration** | Current wearer's resting ADC and bend endpoints. |
| **Glove Calibration** | Physical glove pair's pressure/force response. |

## Wearer calibration: exactly two poses

| Pose | Measurement |
|---|---|
| Open hand, pads contact-free | Per-pixel median over the final second; average open bend readings. |
| Closed fist, including thumb | Average closed bend readings; no tactile maximum. |

Renew after re-wearing gloves or changing wearer/session. A reused username replaces its file.

The app generates the complete JSON with a `gloves` wrapper and this required `layout`:

```json
{
  "protocol": "v01.12",
  "finger_names": ["thumb", "index", "middle", "ring", "little"],
  "pixels_per_finger": 16,
  "pixel_origin": "top_left",
  "adc_max": 4096,
  "pressure_channels": 80,
  "bend_channels": 5
}
```

## Supplier per-pixel pressure

`calibrations/example_perpixel_pressure.json` and its supplier guide apply only to **LH_1/RH_1**. Keep them intact; use the matching hand assignments.

| File requirement | Value |
|---|---|
| GUI filename | Contains `pressure`. |
| Hands / fingers | Exactly `lh`, `rh`; thumb, index, middle, ring, little per hand. |
| Pixels | `r0c0`–`r3c3`, each with 4,096 finite nonnegative kPa values; starts at zero and never decreases. |
| Layout mapping | Decoded `[row,col]` uses raw LUT key `r{col}c{row}`. |
| Supplier range | 0–207 kPa calibrated; 207–345 kPa extended. Saturated/table-top values are lower bounds. |

Conversion for one pixel, shared by GUI and SDK:

```python
def calibrated_pixel(raw_adc, resting_adc, lut_kpa):
    live = min(4095, max(0, int(raw_adc)))
    rest = min(4095, max(0, int(resting_adc)))
    pressure_kpa = max(lut_kpa[live] - lut_kpa[rest], 0)
    force_n = pressure_kpa * 22.5 * 0.001
    saturated = raw_adc >= 4000
    return pressure_kpa, force_n, saturated
# Raw ADC 4096 stays intact; only LUT indices are clamped.
```

The recorder outputs matching five-by-16 `finger_pressure_kPa_pixels`, `finger_pressure_N_pixels`, and `finger_pressure_saturated` arrays. Saturation uses raw ADC even when tared pressure is zero.

## Polynomial force

Separate format: filename contains `force`, with the current `meta.layout`. Produces five baseline-zeroed `finger_force_N_total` values. Pressure LUT files do not produce total-force values.

## What the recording preserves

MCAP retains raw ADC/timing and the selected wearer JSON at `/calibration/glove/user/json`. The glove-pair pressure/force JSON is **not embedded**; keep it with your session files.
