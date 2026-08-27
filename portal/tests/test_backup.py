from __future__ import annotations

import json
import time
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from mowbi_portal.backup import (
    BackupCoordinator,
    BackupStore,
    CONFIRMATION_PHRASE,
    file_digests,
    files_equal,
)
from mowbi_portal.config import TargetProfile


class FakeReader:
    def __init__(self, mismatch_attempt: int | None = None) -> None:
        self.mismatch_attempt = mismatch_attempt

    def read(self, region, destination: Path, attempt: int) -> dict[str, object]:
        byte = 0xA5 if attempt != self.mismatch_attempt else 0x5A
        destination.write_bytes(bytes([byte]) * region.length)
        return {
            "tool": "fake",
            "attempt": attempt,
            "write_operations": False,
            "reset_requested": False,
            "halt_requested": False,
        }


def wait_for_job(coordinator: BackupCoordinator, job_id: str) -> dict[str, object]:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        job = coordinator.get_job(job_id)
        if job["status"] not in {"queued", "running"}:
            return job
        time.sleep(0.01)
    raise TimeoutError(job_id)


class DigestTests(unittest.TestCase):
    def test_digests_and_equality(self) -> None:
        with TemporaryDirectory() as folder:
            first = Path(folder) / "a.bin"
            second = Path(folder) / "b.bin"
            first.write_bytes(b"mowbi" * 100)
            second.write_bytes(first.read_bytes())
            digest = file_digests(first)
            self.assertEqual(digest["size"], 500)
            self.assertEqual(len(str(digest["sha256"])), 64)
            self.assertTrue(files_equal(first, second))
            second.write_bytes(b"changed")
            self.assertFalse(files_equal(first, second))


class CoordinatorTests(unittest.TestCase):
    def profile(self) -> TargetProfile:
        default = TargetProfile()
        tiny_region = replace(default.regions[0], length=4096)
        optional_nor = replace(default.regions[1], required=False)
        return replace(default, profile_confirmed=True, chip_marking="TEST-MCU", regions=(tiny_region, optional_nor))

    def test_three_identical_reads_create_verified_archive(self) -> None:
        with TemporaryDirectory() as folder:
            store = BackupStore(Path(folder))
            coordinator = BackupCoordinator(store, self.profile(), FakeReader())
            started = coordinator.start("DM2 test", "golden", CONFIRMATION_PHRASE)
            job = wait_for_job(coordinator, started.job_id)
            self.assertEqual(job["status"], "completed")
            manifest = store.manifest(started.backup_id)
            self.assertEqual(manifest["status"], "verified")
            self.assertTrue(manifest["complete_persistent_backup"])
            self.assertEqual(len(manifest["regions"][0]["reads"]), 3)
            self.assertTrue(store.archive_path(started.backup_id).exists())
            self.assertTrue(store.verify(started.backup_id)["ok"])

    def test_mismatch_is_rejected(self) -> None:
        with TemporaryDirectory() as folder:
            store = BackupStore(Path(folder))
            coordinator = BackupCoordinator(store, self.profile(), FakeReader(mismatch_attempt=2))
            started = coordinator.start("DM2 test", "mismatch", CONFIRMATION_PHRASE)
            job = wait_for_job(coordinator, started.job_id)
            self.assertEqual(job["status"], "failed")
            manifest = store.manifest(started.backup_id)
            self.assertEqual(manifest["status"], "mismatch")
            self.assertIsNone(manifest["regions"][0]["consensus_sha256"])

    def test_confirmation_and_profile_are_required(self) -> None:
        with TemporaryDirectory() as folder:
            store = BackupStore(Path(folder))
            unconfirmed = TargetProfile()
            coordinator = BackupCoordinator(store, unconfirmed, FakeReader())
            with self.assertRaisesRegex(ValueError, "Profil MCU"):
                coordinator.start("DM2", "", CONFIRMATION_PHRASE)
            confirmed = BackupCoordinator(store, self.profile(), FakeReader())
            with self.assertRaisesRegex(ValueError, "potwierdzenie"):
                confirmed.start("DM2", "", "wrong")


if __name__ == "__main__":
    unittest.main()
