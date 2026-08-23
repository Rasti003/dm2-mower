#!/usr/bin/env python3
"""Build a display-only RPI MODE proof-of-concept firmware image."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path


FLASH_BASE = 0x08000000
KNOWN_SIZE = 512 * 1024
KNOWN_SHA256 = "45823d14ec9bf15776aa9a50d859ad937cc9e39732e432403d55018de4184c4a"
PAYLOAD_ADDRESS = 0x08060400
PAYLOAD_LIMIT = 0x200
RPI_STATE_ADDRESS = 0x2000FFE0

PATCH_EXPECTATIONS = {
    0x080330BE: bytes.fromhex("51 F8 25 00"),  # localized status-text load
    0x08046BD6: bytes.fromhex("06 F0 E1 FD"),  # BL 0x0804D79C
    0x08046C08: struct.pack("<I", 0x20010000),  # heap end
    0x0805F1B8: struct.pack("<I", 0x0804CCE9),  # ui_msg_test no-op
}


def offset(address: int) -> int:
    return address - FLASH_BASE


def locate_tool(name: str, repo_root: Path) -> str:
    suffix = ".exe" if sys.platform == "win32" else ""
    local = repo_root / "tools" / "pio-core" / "packages" / "toolchain-gccarmnoneeabi" / "bin" / f"{name}{suffix}"
    if local.is_file():
        return str(local)
    found = shutil.which(name) or shutil.which(f"{name}{suffix}")
    if found:
        return found
    raise FileNotFoundError(f"cannot find {name}; install the PlatformIO ARM toolchain")


def thumb2_branch(source: int, target: int, link: bool) -> bytes:
    displacement = target - (source + 4)
    if displacement & 1:
        raise ValueError("Thumb branch target must be halfword aligned")
    if not -(1 << 24) <= displacement < (1 << 24):
        raise ValueError("Thumb-2 branch target is out of range")
    encoded = displacement & 0x01FFFFFF
    s = (encoded >> 24) & 1
    i1 = (encoded >> 23) & 1
    i2 = (encoded >> 22) & 1
    imm10 = (encoded >> 12) & 0x3FF
    imm11 = (encoded >> 1) & 0x7FF
    j1 = (~(i1 ^ s)) & 1
    j2 = (~(i2 ^ s)) & 1
    first = 0xF000 | (s << 10) | imm10
    second_base = 0xD000 if link else 0x9000
    second = second_base | (j1 << 13) | (j2 << 11) | imm11
    return struct.pack("<HH", first, second)


def symbols_from_nm(nm: str, elf: Path) -> dict[str, int]:
    result = subprocess.run([nm, "-g", "--defined-only", str(elf)], check=True, text=True, capture_output=True)
    symbols: dict[str, int] = {}
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 3:
            symbols[parts[2]] = int(parts[0], 16)
    return symbols


def build_payload(script_dir: Path, repo_root: Path, build_dir: Path) -> tuple[bytes, dict[str, int]]:
    gcc = locate_tool("arm-none-eabi-gcc", repo_root)
    objcopy = locate_tool("arm-none-eabi-objcopy", repo_root)
    nm = locate_tool("arm-none-eabi-nm", repo_root)
    elf = build_dir / "rpi_mode.elf"
    binary = build_dir / "rpi_mode.bin"
    subprocess.run(
        [
            gcc,
            "-mcpu=cortex-m4",
            "-mthumb",
            "-nostdlib",
            "-Wl,--build-id=none",
            f"-Wl,-T,{script_dir / 'linker.ld'}",
            "-o",
            str(elf),
            str(script_dir / "rpi_mode.S"),
        ],
        check=True,
    )
    subprocess.run([objcopy, "-O", "binary", str(elf), str(binary)], check=True)
    payload = binary.read_bytes()
    if not payload or len(payload) > PAYLOAD_LIMIT:
        raise ValueError(f"payload length {len(payload)} is outside 1..{PAYLOAD_LIMIT}")
    return payload, symbols_from_nm(nm, elf)


def patch_image(source: Path, destination: Path, payload: bytes, symbols: dict[str, int]) -> None:
    image = bytearray(source.read_bytes())
    digest = hashlib.sha256(image).hexdigest()
    if len(image) != KNOWN_SIZE:
        raise ValueError(f"input size is {len(image)}, expected {KNOWN_SIZE}")
    if digest != KNOWN_SHA256:
        raise ValueError(f"unknown input SHA-256: {digest}")
    if source.resolve() == destination.resolve():
        raise ValueError("output path must differ from the golden input path")

    for address, expected in PATCH_EXPECTATIONS.items():
        actual = bytes(image[offset(address) : offset(address) + len(expected)])
        if actual != expected:
            raise ValueError(f"unexpected bytes at 0x{address:08X}: {actual.hex(' ')}")

    required = ("rpi_mode_command", "rpi_select_status_text", "rpi_init_wrapper")
    missing = [name for name in required if name not in symbols]
    if missing:
        raise ValueError(f"payload symbols missing: {', '.join(missing)}")

    payload_offset = offset(PAYLOAD_ADDRESS)
    existing = image[payload_offset : payload_offset + len(payload)]
    if any(value != 0xFF for value in existing):
        raise ValueError("payload destination is not erased")

    image[payload_offset : payload_offset + len(payload)] = payload
    image[offset(0x080330BE) : offset(0x080330BE) + 4] = thumb2_branch(
        0x080330BE, symbols["rpi_select_status_text"], link=True
    )
    image[offset(0x08046BD6) : offset(0x08046BD6) + 4] = thumb2_branch(
        0x08046BD6, symbols["rpi_init_wrapper"], link=True
    )
    image[offset(0x08046C08) : offset(0x08046C08) + 4] = struct.pack("<I", RPI_STATE_ADDRESS)
    image[offset(0x0805F1B8) : offset(0x0805F1B8) + 4] = struct.pack(
        "<I", symbols["rpi_mode_command"] | 1
    )

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(image)
    print(f"input sha256:  {digest}")
    print(f"output sha256: {hashlib.sha256(image).hexdigest()}")
    print(f"payload:        0x{PAYLOAD_ADDRESS:08X}, {len(payload)} bytes")
    print(f"reserved RAM:   0x{RPI_STATE_ADDRESS:08X}..0x2000FFFF")
    print(f"output:         {destination}")
    print("POC only: no motor-control code was added and nothing was flashed.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="golden MCU firmware image")
    parser.add_argument("output", type=Path, help="new patched image path")
    args = parser.parse_args()
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[1]
    try:
        with tempfile.TemporaryDirectory(prefix="dm2-rpi-mode-") as temporary:
            payload, symbols = build_payload(script_dir, repo_root, Path(temporary))
            patch_image(args.input, args.output, payload, symbols)
    except (FileNotFoundError, ValueError, subprocess.CalledProcessError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
