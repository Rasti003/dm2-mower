from __future__ import annotations

import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

try:
    import termios
except ImportError:  # pragma: no cover - module is deployed on Linux
    termios = None  # type: ignore[assignment]


ALLOWED_COMMANDS = (
    "",
    "version()",
    "list_device()",
    "list_thread()",
    "list_timer()",
    "list_msgqueue()",
    "list_mailbox()",
    "list_event()",
    "list_mutex()",
    "list_sem()",
    "list_mempool()",
    "list_mem()",
    "list_fd()",
    "free()",
    "time()",
)

ARM_CONFIRMATION = "ARM DM2 READ ONLY"
ARM_DURATION_SECONDS = 120
INTER_BYTE_DELAY_SECONDS = 0.003


class UartConsole:
    """Single-owner, read-mostly UART service for the split DM2 FinSH console."""

    def __init__(self, port: Path, baud: int = 115_200, autostart: bool = True) -> None:
        self.port = port
        self.baud = baud
        self._fd: int | None = None
        self._connected = False
        self._detail = "Oczekiwanie na port UART"
        self._records: deque[dict[str, object]] = deque(maxlen=1200)
        self._sequence = 0
        self._armed_until = 0.0
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        if autostart:
            self.start()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._read_loop, name="mowbi-uart", daemon=True)
        self._thread.start()

    def close(self) -> None:
        self._stop.set()
        with self._lock:
            self._close_port()

    def status(self) -> dict[str, object]:
        with self._lock:
            remaining = max(0, int((self._armed_until - time.monotonic()) * 1000))
            return {
                "connected": self._connected,
                "detail": self._detail,
                "port": str(self.port),
                "baud": self.baud,
                "format": "8N1",
                "armed": remaining > 0,
                "remaining_ms": remaining,
                "last_sequence": self._sequence,
                "allowed_commands": list(ALLOWED_COMMANDS),
            }

    def records_after(self, sequence: int) -> list[dict[str, object]]:
        with self._lock:
            return [dict(item) for item in self._records if int(item["seq"]) > sequence]

    def arm(self, confirmation: str) -> dict[str, object]:
        if confirmation != ARM_CONFIRMATION:
            raise ValueError("Nieprawidłowe potwierdzenie połączenia UART")
        with self._lock:
            if not self._connected or self._fd is None:
                raise RuntimeError("UART nie jest połączony")
            self._armed_until = time.monotonic() + ARM_DURATION_SECONDS
        return self.status()

    def disarm(self) -> dict[str, object]:
        with self._lock:
            self._armed_until = 0.0
        return self.status()

    def send(self, command: str) -> dict[str, object]:
        normalized = command.strip()
        if normalized not in ALLOWED_COMMANDS:
            raise ValueError("Komenda nie znajduje się na bezpiecznej liście diagnostycznej")
        with self._lock:
            if time.monotonic() >= self._armed_until:
                self._armed_until = 0.0
                raise RuntimeError("Konsola jest rozbrojona")
            if not self._connected or self._fd is None:
                raise RuntimeError("UART nie jest połączony")
            for byte in normalized.encode("ascii"):
                os.write(self._fd, bytes((byte,)))
                time.sleep(INTER_BYTE_DELAY_SECONDS)
            os.write(self._fd, b"\r")
            self._armed_until = time.monotonic() + ARM_DURATION_SECONDS
        return {"sent": True, "command": normalized or "Enter", "status": self.status()}

    def _open_port(self) -> None:
        if termios is None:
            raise RuntimeError("Obsługa UART jest dostępna tylko na systemie Linux")
        fd = os.open(self.port, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            attrs = termios.tcgetattr(fd)
            attrs[0] = 0
            attrs[1] = 0
            attrs[2] = termios.CLOCAL | termios.CREAD | termios.CS8
            attrs[3] = 0
            attrs[4] = termios.B115200
            attrs[5] = termios.B115200
            attrs[6][termios.VMIN] = 0
            attrs[6][termios.VTIME] = 1
            termios.tcsetattr(fd, termios.TCSANOW, attrs)
            termios.tcflush(fd, termios.TCIFLUSH)
        except Exception:
            os.close(fd)
            raise
        with self._lock:
            self._fd = fd
            self._connected = True
            self._detail = "Połączono z konsolą głównego MCU"

    def _close_port(self) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
        self._fd = None
        self._connected = False
        self._armed_until = 0.0

    def _append(self, payload: bytes) -> None:
        if not payload:
            return
        with self._lock:
            self._sequence += 1
            self._records.append(
                {
                    "seq": self._sequence,
                    "time": datetime.now(timezone.utc).isoformat(),
                    "text": payload.decode("utf-8", errors="replace"),
                    "hex": payload.hex(" ").upper(),
                }
            )

    def _read_loop(self) -> None:
        while not self._stop.is_set():
            try:
                if self._fd is None:
                    self._open_port()
                assert self._fd is not None
                payload = os.read(self._fd, 4096)
                if payload:
                    self._append(payload)
                else:
                    time.sleep(0.03)
            except BlockingIOError:
                time.sleep(0.03)
            except Exception as exc:
                with self._lock:
                    self._detail = f"UART niedostępny: {exc}"
                    self._close_port()
                self._stop.wait(2.0)
