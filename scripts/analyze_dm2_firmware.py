#!/usr/bin/env python3
"""Read-only checks for the known DM2-SW-VBW 3.7.4 MCU image.

The script never writes to the firmware file.  Addresses and semantic labels in
this file are valid only for the image identified by KNOWN_SHA256.
"""

from __future__ import annotations

import argparse
import hashlib
import struct
import sys
from pathlib import Path


FLASH_BASE = 0x08000000
APP_BASE = 0x0800A000
KNOWN_SIZE = 512 * 1024
KNOWN_SHA256 = "45823d14ec9bf15776aa9a50d859ad937cc9e39732e432403d55018de4184c4a"

# Keil scatter-loading data reconstructed from the known image.
PACKED_DATA = 0x0805F450
PACKED_RAM_BASE = 0x20000000
PACKED_RAM_SIZE = 0x23A8

UART_STRUCTS = {
    "uart1": (0x200020A4, "USART1", 0x40013800, 37, "PA9", "PA10", "RT-Thread console TX/logs"),
    "uart2": (0x200020C0, "USART2", 0x40004400, 38, "PA2", "PA3", "motor-controller bus"),
    "uart3": (0x200020DC, "USART3", 0x40004800, 39, "PB10", "PB11", "role not confirmed"),
    "uart4": (0x200020F8, "UART4", 0x40004C00, 52, "PC10", "PC11", "role not confirmed"),
    "uart5": (0x20002114, "UART5", 0x40005000, 53, "PC12", "PD2", "FinSH shell RX/input"),
}


def u32(data: bytes, offset: int) -> int:
    return struct.unpack_from("<I", data, offset)[0]


def flash_offset(address: int) -> int:
    return address - FLASH_BASE


def keil_decompress(source: bytes, output_size: int) -> tuple[bytes, int]:
    """Decode the compact data format used by __scatterload_decompress."""
    output = bytearray()
    position = 0

    def take() -> int:
        nonlocal position
        if position >= len(source):
            raise ValueError("compressed stream ended unexpectedly")
        value = source[position]
        position += 1
        return value

    while len(output) < output_size:
        control = take()
        literal_count = control & 0x03
        if literal_count == 0:
            literal_count = take()

        match_count = control >> 4
        if match_count == 0:
            match_count = take()

        # The Thumb routine uses pre-decrement loops.
        for _ in range(max(0, literal_count - 1)):
            output.append(take())

        if match_count:
            low = take()
            mode = control & 0x0C
            if mode == 0x0C:
                distance = low | (take() << 8)
            else:
                distance = low | (mode << 6)
            if distance <= 0 or distance > len(output):
                raise ValueError(f"invalid back-reference distance {distance}")
            for _ in range(match_count + 2):
                output.append(output[-distance])

        if len(output) > output_size:
            raise ValueError("decompressed data exceeds expected size")

    return bytes(output), position


def motor_speed_frame(controller_id: int, speed: int, sequence: int) -> bytes:
    """Build a decoded example; this function performs no I/O."""
    if controller_id not in range(256):
        raise ValueError("controller ID must fit in one byte")
    speed = max(-4500, min(4500, speed))
    speed_u16 = speed & 0xFFFF
    sequence &= 0xFFFF
    frame = bytearray(
        [
            0xD5,
            0xE5,
            controller_id,
            sequence >> 8,
            0x02,
            sequence & 0xFF,
            0,
            speed_u16 >> 8,
            0,
            speed_u16 & 0xFF,
            0,
        ]
    )
    frame[6] = sum(frame[index] for index in (2, 3, 4, 5, 7, 8, 9, 10)) & 0x7F
    return bytes(frame)


def analyze(path: Path) -> int:
    image = path.read_bytes()
    digest = hashlib.sha256(image).hexdigest()
    print(f"file: {path}")
    print(f"size: {len(image)} bytes")
    print(f"sha256: {digest}")

    if len(image) != KNOWN_SIZE:
        print(f"ERROR: expected {KNOWN_SIZE} bytes", file=sys.stderr)
        return 2
    if digest != KNOWN_SHA256:
        print("ERROR: unknown image; fixed addresses must not be reused", file=sys.stderr)
        return 3

    boot_sp = u32(image, 0)
    boot_reset = u32(image, 4)
    app_offset = flash_offset(APP_BASE)
    app_sp = u32(image, app_offset)
    app_reset = u32(image, app_offset + 4)
    print(f"boot vector: SP=0x{boot_sp:08X}, reset=0x{boot_reset:08X}")
    print(f"app vector:  SP=0x{app_sp:08X}, reset=0x{app_reset:08X}")

    packed = image[flash_offset(PACKED_DATA) :]
    ram, consumed = keil_decompress(packed, PACKED_RAM_SIZE)
    print(f"initialized RAM: {len(ram)} bytes, compressed bytes consumed: {consumed}")
    print("UART devices (all 115200 8N1 in this image):")

    for name, (ram_address, peripheral_name, expected_base, expected_irq, tx, rx, role) in UART_STRUCTS.items():
        offset = ram_address - PACKED_RAM_BASE
        fields = struct.unpack_from("<7I", ram, offset)
        peripheral_base = fields[0]
        irq = fields[1]
        status = "OK" if (peripheral_base, irq) == (expected_base, expected_irq) else "MISMATCH"
        print(
            f"  {name}: {peripheral_name} base=0x{peripheral_base:08X} IRQ={irq}; "
            f"TX={tx}, RX={rx}; {role} [{status}]"
        )

    example = motor_speed_frame(controller_id=0, speed=1000, sequence=1)
    print("motor speed-frame example (ID 0, speed 1000, sequence 1):")
    print("  " + " ".join(f"{byte:02X}" for byte in example))
    print("NOTE: the example is analytical output only; the script does not access a serial port.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("firmware", type=Path, help="path to the 512 KiB MCU firmware image")
    return analyze(parser.parse_args().firmware)


if __name__ == "__main__":
    raise SystemExit(main())
