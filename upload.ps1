$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$env:PLATFORMIO_CORE_DIR = Join-Path $projectRoot "tools\pio-core"
& (Join-Path $projectRoot "tools\pioenv\Scripts\platformio.exe") run --target upload --upload-port COM6
