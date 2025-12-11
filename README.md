# RGB0 Capture Format

`RGB0` files are the binary captures used by the **GICO 5016A Artnet to DMX/LED controller** for offline playback from its SD card. Each file stores a fixed number of frames per port with contiguous RGB data. The existing `parser.py`/`exporter.py` read the format, while `writer.py` can build compatible captures for SD playback.

### File layout

1. **Header (0x17 bytes)**
   * `0x00-0x03`: ASCII `'RGB0'`.
   * `0x04-0x07`: ASCII version (currently `'1001'`).
   * `0x08-0x0B`: 32-bit sentinel (`0xFFFFFFFF`).
   * `0x0C-0x0D`: 16-bit header end offset.
   * `0x0E-0x0F`: 16-bit frame count (big-endian).
   * `0x10-0x13`: Frame size in bytes (sum of all port lengths, big-endian).
   * `0x14-0x15`: 16-bit port count.
   * `0x16`: Channel count (always `0x01` in observed captures).

2. **Port table (13 bytes per port)**
   * `0x00-0x01`: Port/segment index.
   * `0x02-0x03`: Bytes contributed to each frame (LED count ×3).
   * `0x04-0x07`: Reserved (zeros).
   * `0x08`: Mode (`0x06` for SPI/TTL).
   * `0x09-0x0A`: Flags (observed as `0x80FA`).
   * `0x0B`: Loop/control byte (observed `0x50` when the capture is valid).
   * `0x0C`: Reserved.

3. **Gamma LUT**
   * 256 big-endian 16-bit values (512 bytes). Most captures use the identity curve `0x0000, 0x0001, …`.

4. **Frame stream**
   * `frame_count` frames follow, each exactly `frame_size` bytes. Each frame concatenates the payloads for all ports in ascending index order, then the next frame begins immediately after (no separators or padding).

### Writer (`writer.py`)

`writer.py` exposes `write_sc_rgb0(...)`, which writes RGB0 files from an explicit list of frames composed of `RGB(r, g, b)` triplets.
* Each frame must be a 16‑entry sequence (one port per entry).
* Each port entry is a list of `RGB` instances; by default there are `1,000` LEDs per port (≈6 Art‑Net universes, i.e. 3,000 bytes).
* The writer writes the loop byte `0x50`, mode `0x06`, flags `0x80FA`, and identity gamma table to match the known working captures.
* Output is named `Sc-<run>-01.rgb` (run defaults to `01`), so `write_sc_rgb0(Path("out"), frames)` produces `out/Sc-01-01.rgb`.

Example usage:
```python
from pathlib import Path
from writer import RGB, write_sc_rgb0

dummy_frame = [[RGB(0, 0, 0) for _ in range(1000)] for _ in range(16)]
frames = [dummy_frame]

write_sc_rgb0(Path("exported"), frames)
```

The writer returns the path to the written file so you can copy it onto the controller’s SD card manually.

### Usage hints

* After writing a file, copy it onto the GICO 5016A’s SD card inside the `RGBFiles` folder to enable playback.
* **Important:** format the SD card immediately before copying the files. The GICO 5016 firmware exhibits a bug where stale filesystem metadata causes playback glitches; a fresh FAT32 format ensures the controller reads the newly written file cleanly.
### Compatibility note

While this documentation highlights the 5016, the RGB0 layout is general enough that other GICO units (and any software that understands RGB0/`RGB0`/`Sc-*` naming) can read the same files as long as their port counts and LED densities match. The writer assumes 1,000 LEDs/port, 16 ports (≈6 universes/port) to cover most deployments; adapt the code if a different topology is required.
