# FusionX GUI calibration

[GUI guide](README.md) · [Recording format](recording-format.md) · [Troubleshooting](troubleshooting.md)

Two different files are selected in the GUI: **User Calibration** describes the current wearer/session, and **Glove Calibration** describes the physical glove pair's pressure or force response.

## Wearer calibration: exactly two poses

1. **Open palm / open hand:** wear the gloves, straighten every finger, and keep the tactile pads free of contact. Follow the collection cue. The app records resting tactile values and open-hand bend readings.
2. **Closed fist:** close every finger, including the thumb, and hold through the collection cue. The app records the other bend endpoint only.

No extra thumb/pinch/finger poses are required. The fist does not calibrate a tactile maximum. Saved open-pose samples contain tactile and bend readings; fist samples contain bend readings only. Neither pose stores glove IMU readings in its pose samples. Host/device timing and raw bend channels are retained.

Bend endpoints are pose averages, not observed sample extrema. The resting tactile baseline is the per-pixel median of approximately the final second of the open pose. Renew it after putting the gloves on again or changing wearer/session.

Generated files have the `gloves` wrapper, five named fingers, 16 resting ADC values per finger, and this exact layout contract:

```json
{
  "protocol": "v01.12",
  "finger_names": ["thumb", "index", "middle", "ring", "little"],
  "pixels_per_finger": 16,
  "adc_max": 4096,
  "pressure_channels": 80,
  "bend_channels": 5
}
```

Use the app to generate the complete file. V1/V2 JQ files and earlier four-finger files are rejected. Selecting an existing username/file for recalibration replaces that file deliberately; choose a new name to preserve it.

## Supplier per-pixel pressure

The current reference pair uses `calibrations/example_perpixel_pressure.json` with `README_PerPixel_JSON.md`. Keep the pair's original file and guide intact. They apply only to physical gloves **LH_1/RH_1**; neither USB numbering nor packet contents can identify that pair or its hand assignment.

The pressure JSON contains exactly two top-level hand keys (`lh`, `rh`), five wire finger groups, and 16 pixel keys per finger (`r0c0` through `r3c3`). Each pixel has 4,096 finite, nonnegative, nondecreasing **kPa** values, starting at zero. There is no required metadata/pixel-area block. The calibration filename must contain `pressure` for the GUI's selection filter.

For each physical pixel:

```text
contact_kPa = max(LUT[raw_adc] - LUT[resting_adc], 0)
```

Raw ADC values remain in 0–4096; only pressure lookup indices are clamped to 0–4095 because each supplied LUT has 4,096 entries. Subtraction happens after both pressure lookups, not by looking up an ADC difference. The supplied raw LUT key `[r,c]` corresponds to wire index `16*finger + 4*r + c`; decoded patch `[row,col]` therefore uses key `r{col}c{3-row}`.

Recorded optional fields are:

- `finger_pressure_kPa_pixels`: five arrays of 16 contact-pressure values.
- `finger_pressure_saturated`: matching booleans, true when the **original raw ADC is at least 4,000**, even if pressure tare gives zero.

The supplier guide describes 0–207 kPa as calibrated and 207–345 kPa as extended with reduced resolution. Saturated or table-top values represent lower bounds. Pressure LUTs do not supply force in newtons; pixel-area measurements would be needed for that conversion. Do not reuse the older gloves' area constants.

## Polynomial force

A matching polynomial calibration is a separate format, selected with a filename containing `force`. It must include `meta.layout` matching the current glove. The recorder can emit five baseline-zeroed `finger_force_N_total` values. A pressure file does not produce these force values.

## What the recording preserves

The recording retains raw pressure/bend values without display normalization or resampling, plus the original wearer calibration under `/calibration/glove/user/json`. The selected pressure/force calibration JSON itself is not embedded in MCAP; retain it with the session's provenance when you need to reproduce conversion.

The GUI's familiar palm area is blank display space, not a missing sensor reading or calibration slot. All five current finger pads are 4×4 and their displayed pixel correction does not change which physical LUT is used.
