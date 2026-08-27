from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MemoryRegion:
    region_id: str
    label: str
    base_address: int
    length: int
    enabled: bool
    required: bool
    transport: str
    note: str = ""


@dataclass(frozen=True)
class TargetProfile:
    profile_id: str = "dm2-main-mcu"
    device_label: str = "DM2 Main Controller"
    chip_marking: str = "NIEPOTWIERDZONE"
    profile_confirmed: bool = False
    pyocd_target: str = "cortex_m"
    probe_uid: str = "LU_2022_8888"
    swd_frequency_hz: int = 1_000_000
    repeat_reads: int = 3
    regions: tuple[MemoryRegion, ...] = field(
        default_factory=lambda: (
            MemoryRegion(
                region_id="internal_flash",
                label="Wewnętrzny Flash MCU",
                base_address=0x08000000,
                length=512 * 1024,
                enabled=True,
                required=True,
                transport="swd",
                note="Rozmiar wynika z analizowanego obrazu; wymaga potwierdzenia oznaczenia MCU.",
            ),
            MemoryRegion(
                region_id="external_nor",
                label="Zewnętrzny Winbond W25Q32",
                base_address=0,
                length=4 * 1024 * 1024,
                enabled=False,
                required=True,
                transport="external-spi",
                note="SWD nie gwarantuje dostępu. Wymaga osobnej, zweryfikowanej metody odczytu.",
            ),
            MemoryRegion(
                region_id="option_bytes",
                label="Option bytes / konfiguracja zabezpieczeń",
                base_address=0,
                length=0,
                enabled=False,
                required=True,
                transport="target-specific",
                note="Adresy i format zależą od pełnego modelu MCU; odczyt pozostaje zablokowany.",
            ),
        )
    )


@dataclass(frozen=True)
class PortalSettings:
    data_dir: Path
    pyocd_path: Path
    access_token: str
    profile: TargetProfile
    config_path: Path
    uart_port: Path


def _default_config_path() -> Path:
    return Path(os.environ.get("MOWBI_CONFIG_PATH", "~/.config/mowbi/portal.json")).expanduser()


def _default_data_dir() -> Path:
    return Path(os.environ.get("MOWBI_DATA_DIR", "~/.local/share/mowbi")).expanduser()


def _default_pyocd_path() -> Path:
    return Path(os.environ.get("MOWBI_PYOCD", "~/.venvs/mowbi-tools/bin/pyocd")).expanduser()


def _default_uart_port() -> Path:
    return Path(os.environ.get("MOWBI_UART_PORT", "/dev/serial0")).expanduser()


def _region_from_json(item: dict[str, Any]) -> MemoryRegion:
    values = dict(item)
    for key in ("base_address", "length"):
        value = values[key]
        if isinstance(value, str):
            values[key] = int(value, 0)
    return MemoryRegion(**values)


def _profile_from_json(payload: dict[str, Any]) -> TargetProfile:
    values = dict(payload)
    if "regions" in values:
        values["regions"] = tuple(_region_from_json(item) for item in values["regions"])
    return TargetProfile(**values)


def load_settings() -> PortalSettings:
    config_path = _default_config_path()
    profile = TargetProfile()
    if config_path.exists():
        profile = _profile_from_json(json.loads(config_path.read_text(encoding="utf-8")))

    access_token = os.environ.get("MOWBI_ACCESS_TOKEN", "").strip()
    return PortalSettings(
        data_dir=_default_data_dir(),
        pyocd_path=_default_pyocd_path(),
        access_token=access_token,
        profile=profile,
        config_path=config_path,
        uart_port=_default_uart_port(),
    )


def save_profile(path: Path, profile: TargetProfile) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(profile)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    path.chmod(0o600)


def public_profile(profile: TargetProfile) -> dict[str, Any]:
    payload = asdict(profile)
    for region in payload["regions"]:
        region["base_address_hex"] = f"0x{region['base_address']:08X}"
    return payload
