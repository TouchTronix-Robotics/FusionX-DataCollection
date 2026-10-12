# Glove sensor layout and indexing

[SDK guide](README.md) · [Python API](api.md) · [Troubleshooting](troubleshooting.md)

The diagrams show the GUI's mirrored hand silhouette, current 4×4 patches, and corresponding wire indices. Cell labels use SDK `[row,column]`, with the first decoded row displayed at the bottom. Each `W` label is a zero-based pressure wire-channel index, provided for physical mapping. The palm area has no sensor channels.

### Left glove — caller assigns `hand="lh"`

![Left thin-film glove: five 4x4 patches, SDK row/column and wire indices, one bend channel per finger, blank palm](../glove-map-lh.png)

### Right glove — caller assigns `hand="rh"`

![Right thin-film glove: five 4x4 patches, SDK row/column and wire indices, one bend channel per finger, blank palm](../glove-map-rh.png)

For a decoded patch, use `frame.tactile.finger_pressure[finger][4 * row + column]`. The wire relationship is:

```text
wire_index = 16 * finger_index + 4 * column + (3 - row)
finger_index: thumb=0, index=1, middle=2, ring=3, little=4
```

Pressure wire blocks are thumb → little. The five raw bend values are in the opposite order, little → thumb; named `finger_bend` fields already map them to the correct fingers. All 80 pressure and five bend channels are preserved. There is no second bend sensor per finger, palm array, dorsal bend field, or transmitted quaternion in this API.
