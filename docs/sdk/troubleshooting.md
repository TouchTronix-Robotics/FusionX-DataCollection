# Glove SDK troubleshooting

[SDK guide](README.md) · [Python API](api.md) · [Sensor indexing](sensors.md) · [Documentation home](../../README.md)

## Supported configuration and distribution

| Component | Required configuration |
|---|---|
| Glove | Wired thin-film V01.12, five 4×4 tactile patches and five bend channels |
| Documented package / import | `tactile-glove-sdk` 0.5.0 / `tactile_glove` |
| Supplied wheel target | CPython 3.13, Windows x86_64 or Linux x86_64 |
| Serial connection | 1,000,000 baud, 8N1 |
| Hand assignment | One caller-assigned `lh` or `rh` per selected port |

Request a validated SDK 0.5.0 wheel from TouchTronix for your Python interpreter and platform. Wheels are supplied privately and are not committed on this branch. Earlier wheel build results predate the current 0.5.0 API update. Package installation and the examples do not require a compiler or the private application source repository.

## SDK wheel will not install

Check `python --version` and your selected environment. Supplied filenames contain `cp313` and target **64-bit CPython 3.13**. Python 3.12/3.14 and another architecture require different builds. Ask TouchTronix for a matching wheel; do not install the V1/V2 `touchtronix_glove` package for these gloves.

The wheel installs pyserial, PySide6, pyqtgraph, and their dependencies. The headless API does not import GUI libraries, but the optional viewer requires a desktop/GUI-capable environment. On Linux, Qt may additionally require the distribution's graphics runtime libraries, such as `libegl1`.

## Serial access, wrong hand, or no samples

1. Confirm the actual port in Windows Device Manager or `ls -l /dev/ttyUSB* /dev/ttyACM*` on Linux.
2. Verify the current user has that port's access group (`dialout` on Ubuntu, often `uucp` elsewhere). Log out/in after a group change.
3. Close all other readers. One port must have exactly one active consumer.
4. Use **1,000,000 baud, 8N1**. Older glove baud rates and packet formats do not apply.
5. Assign `--left`/`--right`, or the SDK's `hand`, from physical inspection. USB serial identity and packet data do not identify LH/RH.
6. Run `python examples/test_glove.py PORT --hand lh` (or `rh`) after other readers release the port. It reports raw byte and accepted-frame counts, and can capture a hex dump for support.

A two-second gap without a valid combined sample raises `TimeoutError`, even if malformed data or metadata continues arriving. Inspect the connection/cable/USB path and retry after correcting access/connectivity. The SDK examples propagate errors and close resources; they do not implement automatic reconnection.

On Linux, inspect your actual ports and access groups:

```bash
ls -l /dev/ttyUSB* /dev/ttyACM* 2>/dev/null
groups
```

For a device owned by `dialout` on Ubuntu, an administrator can grant group access:

```bash
sudo usermod -aG dialout "$USER"
```

Log out and back in before retrying. Other distributions may use `uucp`. Avoid `sudo python`, which can switch the Python environment. On Windows, inspect COM ports in Device Manager and install the vendor's serial driver if necessary.

## Time counters reset or samples arrive unevenly

`device_timestamp_ms` resets whenever streaming starts, including reconnects. Its unsigned 32-bit range is approximately 49.71 days; firmware overflow behavior has not been measured. `host_timestamp_ns` is the Unix host time when a valid packet is decoded, and serial buffering or processing can affect its spacing. Preserve both rather than substituting one for the other. See [frame timing](api.md#gloveframe).

## Force, pressure, or IMU physical units are missing

The SDK returns raw tactile/bend ADC values and accepts no calibration file. Implement calibrated force/pressure or bend-angle conversion in your own processing layer using calibration appropriate to the physical gloves and session. Preserve raw readings for reproducibility.

Euler angles are in degrees. Raw gyro/accelerometer values are signed integers with unverified physical scaling; inspected V01.12 samples were zero. The SDK does not transmit or produce a quaternion.

## Viewer, duration, and shutdown

Keep `examples/glove_viewer.py` beside `examples/stream_glove.py`. The optional viewer needs a GUI-capable desktop and may need system Qt graphics libraries. Run without `--viewer` for terminal-only acquisition.

The example refreshes display from the latest frame at 25 FPS while each selected port acquires independently. A slow or stale display does not establish whether acquisition lost samples; examine frame timestamps and your pipeline's storage behavior.

Duration expiry, Ctrl+C, window close, and reader/rendering errors stop and join workers and close all ports. Errors propagate after cleanup. For your own code, use the reader context manager or `disconnect()` in a `finally` block.
