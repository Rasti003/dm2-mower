$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$env:PLATFORMIO_CORE_DIR = Join-Path $projectRoot "tools\pio-core"
$platformio = Join-Path $projectRoot "tools\pioenv\Scripts\platformio.exe"

& $platformio run -e esp32dev
if ($LASTEXITCODE -ne 0) { throw "Kompilacja nie powiodla sie." }

$firmware = Join-Path $projectRoot ".pio\build\esp32dev\firmware.bin"
& curl.exe --fail --show-error --user "admin:uartlogger" --form "firmware=@$firmware" "http://uart-logger.local/api/update"
if ($LASTEXITCODE -ne 0) { throw "Aktualizacja OTA nie powiodla sie." }

Write-Host "`nAktualizacja wyslana. ESP32 uruchamia sie ponownie." -ForegroundColor Green
