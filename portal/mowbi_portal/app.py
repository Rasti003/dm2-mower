from __future__ import annotations

import hmac
import shutil
from dataclasses import replace
from pathlib import Path
from threading import Lock

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .backup import BackupCoordinator, BackupStore, CONFIRMATION_PHRASE, PyOcdMemoryReader
from .config import PortalSettings, load_settings, public_profile, save_profile
from .probe import ProbeDetector
from .uart import ARM_CONFIRMATION, UartConsole


class LoginRequest(BaseModel):
    token: str


class BackupRequest(BaseModel):
    device_name: str = Field(min_length=1, max_length=80)
    note: str = Field(default="", max_length=500)
    confirmation: str


class ProfileConfirmation(BaseModel):
    chip_marking: str = Field(min_length=4, max_length=80)
    flash_length: int
    confirmation: str


class UartArmRequest(BaseModel):
    confirmation: str


class UartSendRequest(BaseModel):
    command: str = Field(default="", max_length=32)


class Runtime:
    def __init__(self, settings: PortalSettings) -> None:
        self.settings = settings
        self.store = BackupStore(settings.data_dir)
        self.lock = Lock()
        self.uart = UartConsole(settings.uart_port)
        self._build_hardware_services()

    def _build_hardware_services(self) -> None:
        profile = self.settings.profile
        self.probe = ProbeDetector(self.settings.pyocd_path, profile.probe_uid)
        self.reader = PyOcdMemoryReader(self.settings.pyocd_path, profile, self.probe)
        self.coordinator = BackupCoordinator(self.store, profile, self.reader)

    def confirm_profile(self, payload: ProfileConfirmation) -> None:
        internal_flash = next(
            region for region in self.settings.profile.regions if region.region_id == "internal_flash"
        )
        if payload.flash_length != internal_flash.length:
            raise ValueError(
                f"Potwierdzony rozmiar Flash musi wynosić {internal_flash.length} B dla tego profilu"
            )
        if payload.confirmation != "POTWIERDZAM OZNACZENIE MCU":
            raise ValueError("Nieprawidłowe potwierdzenie profilu MCU")
        profile = replace(
            self.settings.profile,
            chip_marking=" ".join(payload.chip_marking.strip().split()),
            profile_confirmed=True,
        )
        save_profile(self.settings.config_path, profile)
        with self.lock:
            self.settings = replace(self.settings, profile=profile)
            self._build_hardware_services()


settings = load_settings()
runtime = Runtime(settings)
static_dir = Path(__file__).parent / "static"

app = FastAPI(
    title="MOWBI Command Deck",
    version=__version__,
    docs_url=None,
    redoc_url=None,
)


def require_auth(request: Request) -> None:
    expected = runtime.settings.access_token
    if not expected:
        if request.client and request.client.host in {"127.0.0.1", "::1", "testclient"}:
            return
        raise HTTPException(status_code=503, detail="Portal nie ma jeszcze ustawionego klucza dostępu")
    supplied = request.headers.get("X-Mowbi-Token", "")
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nieprawidłowy klucz dostępu")


@app.get("/api/health")
def health() -> dict[str, object]:
    return {"ok": True, "service": "mowbi-command-deck", "version": __version__}


@app.post("/api/session")
def session(payload: LoginRequest, request: Request) -> dict[str, object]:
    expected = runtime.settings.access_token
    if not expected or not hmac.compare_digest(payload.token, expected):
        raise HTTPException(status_code=401, detail="Nieprawidłowy klucz dostępu")
    return {"ok": True, "version": __version__}


@app.get("/api/status", dependencies=[Depends(require_auth)])
def portal_status() -> dict[str, object]:
    disk = shutil.disk_usage(runtime.settings.data_dir)
    profile = runtime.settings.profile
    pending = [region.region_id for region in profile.regions if region.required and not region.enabled]
    return {
        "service": {"name": "MOWBI Command Deck", "version": __version__, "safe_mode": "read-only"},
        "probe": runtime.probe.quick_status().to_dict(),
        "profile": public_profile(profile),
        "storage": {"total": disk.total, "used": disk.used, "free": disk.free},
        "backup": {
            "confirmation_phrase": CONFIRMATION_PHRASE,
            "running_jobs": runtime.coordinator.jobs(),
            "count": len(runtime.store.list_manifests()),
            "required_regions_pending": pending,
        },
        "capabilities": {
            "read_memory": True,
            "write_memory": False,
            "erase": False,
            "restore": False,
            "missions": False,
            "uart_monitor": True,
            "uart_safe_commands": True,
        },
        "uart": runtime.uart.status(),
    }


@app.post("/api/profile/confirm", dependencies=[Depends(require_auth)])
def confirm_profile(payload: ProfileConfirmation) -> dict[str, object]:
    try:
        runtime.confirm_profile(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "profile": public_profile(runtime.settings.profile)}


@app.get("/api/backups", dependencies=[Depends(require_auth)])
def backups() -> dict[str, object]:
    return {"items": runtime.store.list_manifests(), "jobs": runtime.coordinator.jobs()}


@app.post("/api/backups", status_code=202, dependencies=[Depends(require_auth)])
def create_backup(payload: BackupRequest) -> dict[str, object]:
    try:
        job = runtime.coordinator.start(payload.device_name, payload.note, payload.confirmation)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return job.to_dict()


@app.get("/api/jobs/{job_id}", dependencies=[Depends(require_auth)])
def job(job_id: str) -> dict[str, object]:
    try:
        return runtime.coordinator.get_job(job_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Nie znaleziono zadania") from exc


@app.post("/api/backups/{backup_id}/verify", dependencies=[Depends(require_auth)])
def verify_backup(backup_id: str) -> dict[str, object]:
    try:
        return runtime.store.verify(backup_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail="Nie znaleziono backupu") from exc


@app.get("/api/backups/{backup_id}/download", dependencies=[Depends(require_auth)])
def download_backup(backup_id: str) -> FileResponse:
    try:
        path = runtime.store.archive_path(backup_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Nie znaleziono backupu") from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail="Archiwum nie jest dostępne")
    return FileResponse(path, filename=path.name, media_type="application/zip")


@app.get("/api/uart", dependencies=[Depends(require_auth)])
def uart(after: int = 0) -> dict[str, object]:
    if after < 0:
        raise HTTPException(status_code=400, detail="Numer sekwencji nie może być ujemny")
    return {"status": runtime.uart.status(), "records": runtime.uart.records_after(after)}


@app.post("/api/uart/arm", dependencies=[Depends(require_auth)])
def arm_uart(payload: UartArmRequest) -> dict[str, object]:
    try:
        return runtime.uart.arm(payload.confirmation)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/uart/disarm", dependencies=[Depends(require_auth)])
def disarm_uart() -> dict[str, object]:
    return runtime.uart.disarm()


@app.post("/api/uart/send", dependencies=[Depends(require_auth)])
def send_uart(payload: UartSendRequest) -> dict[str, object]:
    try:
        return runtime.uart.send(payload.command)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=423, detail=str(exc)) from exc


app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
