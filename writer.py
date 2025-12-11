import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

MAGIC = b"RGB0"
VERSION = b"1001"
SENTINEL = 0xFFFFFFFF
MODE_SPI_TTL = 0x06
FLAGS = 0x80FA
CHANNELS = 1
HEADER_PREFIX = 0x17
PORT_ENTRY_SIZE = 0x0D
GAMMA_SIZE = 256 * 2
LEDS_PER_PORT_DEFAULT = 1000
PORT_COUNT_DEFAULT = 16


@dataclass(frozen=True)
class RGB:
    r: int
    g: int
    b: int

    def to_bytes(self) -> bytes:
        return bytes((self.r & 0xFF, self.g & 0xFF, self.b & 0xFF))


def _build_header(frame_size: int, frame_count: int, port_count: int) -> bytes:
    header_end = HEADER_PREFIX + port_count * PORT_ENTRY_SIZE + GAMMA_SIZE - 1
    header = bytearray()
    header.extend(MAGIC)
    header.extend(VERSION)
    header.extend(struct.pack(">I", SENTINEL))
    header.extend(struct.pack(">H", header_end))
    header.extend(struct.pack(">H", frame_count))
    header.extend(struct.pack(">I", frame_size))
    header.extend(struct.pack(">H", port_count))
    header.append(CHANNELS)
    return bytes(header)


def _build_port_table(
    port_count: int,
    bytes_per_port: int,
    loop_byte: int,
    mode: int = MODE_SPI_TTL,
    flags: int = FLAGS,
) -> bytes:
    entries = bytearray()
    for idx in range(port_count):
        entries.extend(struct.pack(">H", idx))
        entries.extend(struct.pack(">H", bytes_per_port))
        entries.extend(struct.pack(">I", 0))
        entries.append(mode)
        entries.extend(struct.pack(">H", flags))
        entries.append(loop_byte)
        entries.append(0x00)
    return bytes(entries)


def _build_gamma_table(gamma_values: Optional[Sequence[int]] = None) -> bytes:
    entries = bytearray()
    lut = list(gamma_values) if gamma_values is not None else list(range(256))
    if len(lut) != 256:
        raise ValueError("gamma_values must contain exactly 256 entries")
    for value in lut:
        entries.extend(struct.pack(">H", value))
    return bytes(entries)


def _validate_frames(
    frames: Sequence[Sequence[Sequence[RGB]]], port_count: int, leds_per_port: int
) -> None:
    if not frames:
        raise ValueError("frames sequence must not be empty")
    for frame_idx, frame in enumerate(frames):
        if len(frame) != port_count:
            raise ValueError(
                f"frame {frame_idx} contains {len(frame)} ports; expected {port_count}"
            )
        for port_idx, port_data in enumerate(frame):
            if len(port_data) != leds_per_port:
                raise ValueError(
                    f"frame {frame_idx} port {port_idx} has {len(port_data)} LEDs; "
                    f"expected {leds_per_port}"
                )


def _port_bytes(port_pixels: Sequence[RGB]) -> bytes:
    buf = bytearray()
    for led in port_pixels:
        buf.extend(led.to_bytes())
    return bytes(buf)


def write_sc_rgb0(
    output_dir: Path,
    frames: Sequence[Sequence[Sequence[RGB]]],
    leds_per_port: int = LEDS_PER_PORT_DEFAULT,
    run_number: int = 1,
    gamma_values: Optional[Sequence[int]] = None,
    loop_byte: int = 0x50,
    mode: int = MODE_SPI_TTL,
    flags: int = FLAGS,
) -> Path:
    """
    Emit a capture file that is compatible with the GICO 5016A SD card runner.

    Args:
        output_dir: destination directory for the generated file.
        frames: list of frames; each frame must provide 16 ports and each port the expected number of bytes.
        leds_per_port: number of RGB pixels per port (default 1000, i.e., six Art-Net universes).
        run_number: value used to synthesize `Sc-<run_number:02d>-01.rgb`.
        gamma_values: optional 256-entry gamma LUT (defaults to identity).
        loop_byte: per-port control byte (0x50 preserves the working captures).
        mode: per-port SPI/TTL mode byte (0x06 by default).
        flags: per-port flags word (0x80FA matches existing captures).
    """
    port_count = PORT_COUNT_DEFAULT
    bytes_per_port = leds_per_port * 3
    frame_count = len(frames)
    _validate_frames(frames, port_count, bytes_per_port)

    frame_size = port_count * bytes_per_port
    header = _build_header(frame_size, frame_count, port_count)
    port_table = _build_port_table(port_count, bytes_per_port, loop_byte, mode, flags)
    gamma = _build_gamma_table(gamma_values)

    output_path = output_dir / f"Sc-{run_number:02d}-01.rgb"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as writer:
        writer.write(header)
        writer.write(port_table)
        writer.write(gamma)
        for frame in frames:
            for port_data in frame:
                writer.write(_port_bytes(port_data))
    return output_path
