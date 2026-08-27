from __future__ import annotations

import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProbeStatus:
    connected: bool
    vendor_id: str
    product_id: str
    uid: str
    device_path: str | None
    detail: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class ProbeDetector:
    def __init__(
        self,
        pyocd_path: Path,
        uid: str,
        vendor_id: str = "c251",
        product_id: str = "f001",
        sys_usb_root: Path = Path("/sys/bus/usb/devices"),
    ) -> None:
        self.pyocd_path = pyocd_path
        self.uid = uid
        self.vendor_id = vendor_id.lower()
        self.product_id = product_id.lower()
        self.sys_usb_root = sys_usb_root

    def quick_status(self) -> ProbeStatus:
        if self.sys_usb_root.exists():
            for candidate in self.sys_usb_root.iterdir():
                vendor = self._read(candidate / "idVendor")
                product = self._read(candidate / "idProduct")
                if vendor == self.vendor_id and product == self.product_id:
                    serial = self._read(candidate / "serial") or self.uid
                    return ProbeStatus(
                        connected=True,
                        vendor_id=vendor,
                        product_id=product,
                        uid=serial,
                        device_path=str(candidate),
                        detail="CMSIS-DAP wykryty przez USB",
                    )
        return ProbeStatus(
            connected=False,
            vendor_id=self.vendor_id,
            product_id=self.product_id,
            uid=self.uid,
            device_path=None,
            detail="Sonda CMSIS-DAP nie jest podłączona",
        )

    def verify_with_pyocd(self, timeout: int = 20) -> tuple[bool, str]:
        command = [str(self.pyocd_path), "list", "--probes", "--no-header"]
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, str(exc)
        output = (result.stdout + "\n" + result.stderr).strip()
        return result.returncode == 0 and self.uid in output, output

    @staticmethod
    def _read(path: Path) -> str:
        try:
            return path.read_text(encoding="ascii").strip().lower()
        except OSError:
            return ""
