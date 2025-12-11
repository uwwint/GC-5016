import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Dict, Iterator, List, Optional


@dataclass
class PortMeta:
    index: int           # port index
    length: int          # bytes per frame for this port
    mode: int            # 0x03 DMX512, 0x06 SPI&TTL, 0x1B TM1814
    flags: int           # 0x0080
    loop_flag: bool      # True if bit 7 set


@dataclass
class RgbHeader:
    magic: str              # "RGB0"
    version: str            # "1001"
    sentinel: int           # usually 0xFFFFFFFF
    header_end_offset: int  # offset of last header/gamma byte (frames start at +1)
    frame_count: int        # number of frames in the file
    frame_size: int         # bytes per frame (sum of all port lengths)
    port_count: int
    channels: int           # always 1 in observed code
    ports: List[PortMeta]
    gamma_lut: List[int]    # 256 entries, 0–65535


@dataclass
class RgbFile:
    header: RgbHeader
    frames: List[bytes]  # raw frame bytes, length = header.frame_size each

    def iter_frames(self) -> Iterator[bytes]:
        yield from self.frames

    def iter_port_frames(self, port_index: int) -> Iterator[bytes]:
        """Yield just the bytes for one port across all frames."""
        port = self.header.ports[port_index]
        # compute offsets based on port ordering
        offset = 0
        for s in self.header.ports:
            if s.index == port_index:
                break
            offset += s.length

        for frame in self.frames:
            yield frame[offset : offset + port.length]


def compute_port_offsets(header: RgbHeader) -> Dict[int, int]:
    offsets: Dict[int, int] = {}
    offset = 0
    for port in header.ports:
        offsets[port.index] = offset
        offset += port.length
    return offsets


def read_exact(f: BinaryIO, n: int) -> bytes:
    data = f.read(n)
    if len(data) != n:
        raise EOFError("Unexpected EOF while reading")
    return data


def parse_rgb_header(f: BinaryIO) -> RgbHeader:
    # Fixed header (0x17 bytes, ports start immediately after)
    hdr_raw = read_exact(f, 0x17)

    magic = hdr_raw[0:4].decode("ascii", errors="replace")
    version = hdr_raw[4:8].decode("ascii", errors="replace")
    # The reference binary writes these as big-endian words/integers
    sentinel = struct.unpack(">I", hdr_raw[8:12])[0]
    header_end_offset = struct.unpack(">H", hdr_raw[12:14])[0]
    frame_count = struct.unpack(">H", hdr_raw[14:16])[0]
    frame_size = struct.unpack(">I", hdr_raw[0x10:0x14])[0]
    port_count = struct.unpack(">H", hdr_raw[0x14:0x16])[0]
    channels = hdr_raw[0x16]

    if magic != "RGB0":
        raise ValueError(f"Not an RGB file (magic={magic!r})")
    # Optional sanity check:
    # if version != "1001": raise or warn

    ports: List[PortMeta] = []

    # Port entries: 0x0D bytes used per port
    seg_table_raw = read_exact(f, port_count * 0x0D)

    for i in range(port_count):
        off = i * 0x0D
        idx_hi = seg_table_raw[off + 0]
        idx_lo = seg_table_raw[off + 1]
        port_index = (idx_hi << 8) | idx_lo

        length_hi = seg_table_raw[off + 2]
        length_lo = seg_table_raw[off + 3]
        port_length = (length_hi << 8) | length_lo

        # 4 bytes reserved at off+4 .. off+7
        mode = seg_table_raw[off + 8]
        flags = struct.unpack(">H", seg_table_raw[off + 9 : off + 11])[0]  # 0x0080
        loop_byte = seg_table_raw[off + 11]
        loop_flag = bool(loop_byte & 0x80)
        # off+12 reserved

        ports.append(
            PortMeta(
                index=port_index,
                length=port_length,
                mode=mode,
                flags=flags,
                loop_flag=loop_flag,
            )
        )

    # Gamma LUT: 256 * 2 bytes, big-endian
    gamma_raw = read_exact(f, 256 * 2)
    gamma_lut = list(struct.unpack(">256H", gamma_raw))

    return RgbHeader(
        magic=magic,
        version=version,
        sentinel=sentinel,
        header_end_offset=header_end_offset,
        frame_count=frame_count,
        frame_size=frame_size,
        port_count=port_count,
        channels=channels,
        ports=ports,
        gamma_lut=gamma_lut,
    )


def parse_rgb_file(path: str, max_frames: Optional[int] = None) -> RgbFile:
    with open(path, "rb") as f:
        header = parse_rgb_header(f)

        frames: List[bytes] = []
        target_frames = max_frames
        if target_frames is None and header.frame_count:
            target_frames = header.frame_count

        while target_frames is None or len(frames) < target_frames:
            try:
                frame = read_exact(f, header.frame_size)
            except EOFError:
                break

            frames.append(frame)
            if target_frames is not None and len(frames) >= target_frames:
                break

    return RgbFile(header=header, frames=frames)


def summarize_rgb(path: Path) -> None:
    rgb = parse_rgb_file(str(path))
    frame_count = len(rgb.frames)
    print(f"{path.name}: frame_size={rgb.header.frame_size} bytes, frames={frame_count}", end="")
    if rgb.header.frame_count:
        print(f" (header claims {rgb.header.frame_count})")
    else:
        print()
    print(f"  gamma sample: {rgb.header.gamma_lut[:4]}")
    offsets = compute_port_offsets(rgb.header)
    for port in rgb.header.ports:
        offset = offsets.get(port.index, 0)
        print(
            f"    Port {port.index}: len={port.length}, mode=0x{port.mode:02x}, "
            f"flags=0x{port.flags:04x}, loop={port.loop_flag}, offset={offset}"
        )
    if rgb.frames:
        first_frame = rgb.frames[0]
        print(f"  first frame preview (16 bytes): {first_frame[:16].hex()}")


if __name__ == "__main__":
    args = sys.argv[1:] or ["temp.RGB"]
    for idx, path_str in enumerate(args):
        path = Path(path_str)
        if not path.is_file():
            print(f"{path} missing or not a file, skipping")
            continue
        summarize_rgb(path)
        if idx != len(args) - 1:
            print()
