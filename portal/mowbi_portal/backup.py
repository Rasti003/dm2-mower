from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import uuid
import zipfile
import zlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Protocol

from .config import MemoryRegion, TargetProfile
from .probe import ProbeDetector


SCHEMA = "mowbi-backup/v1"
CONFIRMATION_PHRASE = "UTWÓRZ BACKUP TYLKO DO ODCZYTU"


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def file_digests(path: Path) -> dict[str, str | int]:
    sha256 = hashlib.sha256()
    blake2b = hashlib.blake2b(digest_size=32)
    crc32 = 0
    size = 0
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            sha256.update(chunk)
            blake2b.update(chunk)
            crc32 = zlib.crc32(chunk, crc32)
            size += len(chunk)
    return {
        "size": size,
        "sha256": sha256.hexdigest().upper(),
        "blake2b_256": blake2b.hexdigest().upper(),
        "crc32": f"{crc32 & 0xFFFFFFFF:08X}",
    }


def files_equal(first: Path, second: Path) -> bool:
    if first.stat().st_size != second.stat().st_size:
        return False
    with first.open("rb") as left, second.open("rb") as right:
        while True:
            left_chunk = left.read(1024 * 1024)
            right_chunk = right.read(1024 * 1024)
            if left_chunk != right_chunk:
                return False
            if not left_chunk:
                return True


class MemoryReader(Protocol):
    def read(self, region: MemoryRegion, destination: Path, attempt: int) -> dict[str, object]: ...


class PyOcdMemoryReader:
    """Generic CoreSight reader. It contains no target write or reset operation."""

    def __init__(self, pyocd_path: Path, profile: TargetProfile, probe: ProbeDetector) -> None:
        self.pyocd_path = pyocd_path
        self.profile = profile
        self.probe = probe

    def read(self, region: MemoryRegion, destination: Path, attempt: int) -> dict[str, object]:
        if region.transport != "swd":
            raise RuntimeError(f"Region {region.region_id} nie ma transportu SWD")
        if not region.enabled:
            raise RuntimeError(f"Region {region.region_id} jest wyłączony")
        if any(char.isspace() for char in str(destination)):
            raise RuntimeError("Ścieżka danych backupu nie może zawierać spacji")

        probe_ok, probe_output = self.probe.verify_with_pyocd()
        if not probe_ok:
            raise RuntimeError(f"pyOCD nie widzi sondy {self.profile.probe_uid}: {probe_output}")

        memory_command = (
            f"savemem 0x{region.base_address:08X} 0x{region.length:X} {destination}"
        )
        command = [
            str(self.pyocd_path),
            "commander",
            "--no-config",
            "--probe",
            self.profile.probe_uid,
            "--target",
            self.profile.pyocd_target,
            "--frequency",
            str(self.profile.swd_frequency_hz),
            "--connect",
            "attach",
            "--command",
            memory_command,
        ]
        started = utc_now()
        result = subprocess.run(command, capture_output=True, text=True, timeout=300, check=False)
        log = (result.stdout + "\n" + result.stderr).strip()
        if result.returncode != 0:
            raise RuntimeError(f"Odczyt SWD #{attempt} nie powiódł się: {log[-2000:]}")
        if not destination.exists() or destination.stat().st_size != region.length:
            actual = destination.stat().st_size if destination.exists() else 0
            raise RuntimeError(
                f"Odczyt SWD #{attempt} ma {actual} B, oczekiwano {region.length} B"
            )
        return {
            "tool": "pyocd",
            "target": self.profile.pyocd_target,
            "connect_mode": "attach",
            "frequency_hz": self.profile.swd_frequency_hz,
            "started_at": started,
            "finished_at": utc_now(),
            "return_code": result.returncode,
            "log_tail": log[-2000:],
            "write_operations": False,
            "reset_requested": False,
            "halt_requested": False,
        }


@dataclass
class BackupJob:
    job_id: str
    backup_id: str
    status: str
    phase: str
    progress: int
    message: str
    created_at: str
    updated_at: str
    result: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class BackupStore:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.backups_dir = root / "backups"
        self.backups_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.root.chmod(0o700)
            self.backups_dir.chmod(0o700)
        except OSError:
            pass

    def create_dir(self, backup_id: str) -> Path:
        path = self.backups_dir / backup_id
        path.mkdir(mode=0o700, parents=False, exist_ok=False)
        return path

    def list_manifests(self) -> list[dict[str, object]]:
        items: list[dict[str, object]] = []
        for manifest_path in self.backups_dir.glob("*/manifest.json"):
            try:
                payload = json.loads(manifest_path.read_text(encoding="utf-8"))
                payload["download_available"] = self.archive_path(payload["backup_id"]).exists()
                items.append(payload)
            except (OSError, ValueError, KeyError):
                continue
        return sorted(items, key=lambda item: str(item.get("created_at", "")), reverse=True)

    def manifest(self, backup_id: str) -> dict[str, object]:
        return json.loads(self._safe_backup_dir(backup_id).joinpath("manifest.json").read_text(encoding="utf-8"))

    def archive_path(self, backup_id: str) -> Path:
        self._validate_id(backup_id)
        return self.backups_dir / f"{backup_id}.zip"

    def create_archive(self, backup_id: str) -> Path:
        backup_dir = self._safe_backup_dir(backup_id)
        destination = self.archive_path(backup_id)
        temporary = destination.with_suffix(".zip.tmp")
        with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for item in sorted(backup_dir.iterdir()):
                if item.is_file():
                    archive.write(item, arcname=f"{backup_id}/{item.name}")
        os.replace(temporary, destination)
        destination.chmod(0o600)
        return destination

    def verify(self, backup_id: str) -> dict[str, object]:
        backup_dir = self._safe_backup_dir(backup_id)
        manifest = self.manifest(backup_id)
        failures: list[str] = []
        checked = 0
        for region in manifest.get("regions", []):
            for read in region.get("reads", []):
                path = backup_dir / read["filename"]
                if not path.exists():
                    failures.append(f"Brak pliku {read['filename']}")
                    continue
                actual = file_digests(path)
                checked += 1
                for key in ("size", "sha256", "blake2b_256", "crc32"):
                    if actual[key] != read[key]:
                        failures.append(f"{read['filename']}: niezgodne {key}")
        return {
            "backup_id": backup_id,
            "verified_at": utc_now(),
            "ok": not failures and checked > 0,
            "files_checked": checked,
            "failures": failures,
        }

    def _safe_backup_dir(self, backup_id: str) -> Path:
        self._validate_id(backup_id)
        path = self.backups_dir / backup_id
        if not path.is_dir():
            raise FileNotFoundError(backup_id)
        return path

    @staticmethod
    def _validate_id(backup_id: str) -> None:
        if not backup_id or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for char in backup_id):
            raise ValueError("Nieprawidłowy identyfikator backupu")


class BackupCoordinator:
    def __init__(self, store: BackupStore, profile: TargetProfile, reader: MemoryReader) -> None:
        self.store = store
        self.profile = profile
        self.reader = reader
        self._jobs: dict[str, BackupJob] = {}
        self._lock = threading.Lock()
        self._active_job: str | None = None

    def jobs(self) -> list[dict[str, object]]:
        with self._lock:
            return [job.to_dict() for job in self._jobs.values()]

    def get_job(self, job_id: str) -> dict[str, object]:
        with self._lock:
            return self._jobs[job_id].to_dict()

    def start(self, device_name: str, note: str, confirmation: str) -> BackupJob:
        if confirmation != CONFIRMATION_PHRASE:
            raise ValueError("Nieprawidłowe potwierdzenie trybu tylko do odczytu")
        if not self.profile.profile_confirmed:
            raise ValueError("Profil MCU nie został jeszcze potwierdzony")
        clean_name = " ".join(device_name.strip().split())
        if not clean_name or len(clean_name) > 80:
            raise ValueError("Nazwa urządzenia musi mieć od 1 do 80 znaków")
        if len(note) > 500:
            raise ValueError("Notatka może mieć maksymalnie 500 znaków")

        now = datetime.now(UTC)
        backup_id = now.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:8]
        job_id = uuid.uuid4().hex
        job = BackupJob(job_id, backup_id, "queued", "preflight", 0, "Oczekuje", utc_now(), utc_now())
        with self._lock:
            if self._active_job is not None:
                raise RuntimeError("Inny backup jest już wykonywany")
            self._active_job = job_id
            self._jobs[job_id] = job
        thread = threading.Thread(target=self._run, args=(job_id, clean_name, note.strip()), daemon=True)
        thread.start()
        return job

    def _update(self, job_id: str, **changes: object) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in changes.items():
                setattr(job, key, value)
            job.updated_at = utc_now()

    def _run(self, job_id: str, device_name: str, note: str) -> None:
        job = self._jobs[job_id]
        backup_dir: Path | None = None
        try:
            backup_dir = self.store.create_dir(job.backup_id)
            regions_manifest: list[dict[str, object]] = []
            enabled_regions = [region for region in self.profile.regions if region.enabled]
            total_reads = max(1, len(enabled_regions) * self.profile.repeat_reads)
            completed_reads = 0

            for region in enabled_regions:
                region_reads: list[dict[str, object]] = []
                paths: list[Path] = []
                for attempt in range(1, self.profile.repeat_reads + 1):
                    self._update(
                        job_id,
                        status="running",
                        phase=f"read-{region.region_id}",
                        progress=int(completed_reads * 80 / total_reads),
                        message=f"Odczyt {attempt}/{self.profile.repeat_reads}: {region.label}",
                    )
                    destination = backup_dir / f"{region.region_id}-read-{attempt:02d}.bin"
                    tool = self.reader.read(region, destination, attempt)
                    digests = file_digests(destination)
                    region_reads.append({"attempt": attempt, "filename": destination.name, **digests, "tool": tool})
                    paths.append(destination)
                    completed_reads += 1

                identical = all(files_equal(paths[0], path) for path in paths[1:])
                canonical_name = None
                if identical:
                    canonical = backup_dir / f"{region.region_id}.bin"
                    shutil.copyfile(paths[0], canonical)
                    canonical.chmod(0o600)
                    canonical_name = canonical.name
                regions_manifest.append(
                    {
                        **asdict(region),
                        "base_address_hex": f"0x{region.base_address:08X}",
                        "reads": region_reads,
                        "identical": identical,
                        "consensus_sha256": region_reads[0]["sha256"] if identical else None,
                        "canonical_filename": canonical_name,
                    }
                )

            consensus = bool(regions_manifest) and all(item["identical"] for item in regions_manifest)
            required_pending = [
                region.region_id for region in self.profile.regions if region.required and not region.enabled
            ]
            manifest = {
                "schema": SCHEMA,
                "backup_id": job.backup_id,
                "created_at": job.created_at,
                "finished_at": utc_now(),
                "device_name": device_name,
                "note": note,
                "status": "verified" if consensus else "mismatch",
                "complete_persistent_backup": consensus and not required_pending,
                "required_regions_pending": required_pending,
                "profile": {
                    "profile_id": self.profile.profile_id,
                    "device_label": self.profile.device_label,
                    "chip_marking": self.profile.chip_marking,
                    "probe_uid": self.profile.probe_uid,
                    "pyocd_target": self.profile.pyocd_target,
                    "swd_frequency_hz": self.profile.swd_frequency_hz,
                    "repeat_reads": self.profile.repeat_reads,
                },
                "safety": {
                    "mode": "read-only",
                    "write_operations": False,
                    "erase_operations": False,
                    "reset_requested": False,
                    "halt_requested": False,
                },
                "regions": regions_manifest,
            }
            manifest_path = backup_dir / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            manifest_path.chmod(0o600)
            archive = self.store.create_archive(job.backup_id)
            result = {
                "backup_id": job.backup_id,
                "status": manifest["status"],
                "complete_persistent_backup": manifest["complete_persistent_backup"],
                "required_regions_pending": required_pending,
                "archive": archive.name,
            }
            self._update(
                job_id,
                status="completed" if consensus else "failed",
                phase="consensus",
                progress=100,
                message="Odczyty są identyczne" if consensus else "Odczyty różnią się — backup odrzucony",
                result=result,
            )
        except Exception as exc:  # Hardware errors must become visible job failures.
            self._update(job_id, status="failed", phase="error", message=str(exc), result=None)
            if backup_dir is not None:
                error_path = backup_dir / "error.json"
                error_path.write_text(
                    json.dumps({"schema": SCHEMA, "failed_at": utc_now(), "error": str(exc)}, indent=2) + "\n",
                    encoding="utf-8",
                )
        finally:
            with self._lock:
                self._active_job = None
