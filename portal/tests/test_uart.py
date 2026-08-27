from pathlib import Path
from unittest.mock import call, patch

import pytest

from mowbi_portal.uart import ARM_CONFIRMATION, UartConsole


def connected_console() -> UartConsole:
    console = UartConsole(Path("/dev/test-uart"), autostart=False)
    console._connected = True
    console._fd = 99
    return console


def test_console_starts_disarmed_and_rejects_send() -> None:
    console = connected_console()
    assert console.status()["armed"] is False
    with pytest.raises(RuntimeError, match="rozbrojona"):
        console.send("version()")


def test_console_only_sends_allowlisted_command_with_cr() -> None:
    console = connected_console()
    console.arm(ARM_CONFIRMATION)
    with patch("mowbi_portal.uart.os.write") as write, patch("mowbi_portal.uart.time.sleep"):
        result = console.send("version()")
    assert result["sent"] is True
    assert write.call_args_list == [*(call(99, bytes((byte,))) for byte in b"version()"), call(99, b"\r")]


def test_console_rejects_unknown_command_even_when_armed() -> None:
    console = connected_console()
    console.arm(ARM_CONFIRMATION)
    with pytest.raises(ValueError, match="bezpiecznej liście"):
        console.send("reboot")


def test_records_keep_text_and_raw_hex() -> None:
    console = UartConsole(Path("/dev/test-uart"), autostart=False)
    console._append(b"finsh >\xff")
    records = console.records_after(0)
    assert records[0]["seq"] == 1
    assert records[0]["text"] == "finsh >�"
    assert records[0]["hex"] == "66 69 6E 73 68 20 3E FF"
