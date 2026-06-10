# Start local dev server (Windows PowerShell).
# Usage: .\scripts\dev.ps1
#        .\scripts\dev.ps1 -NoReload   (used by dev.bat for clean Ctrl+C)

param(
    [switch]$NoReload
)

$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
Set-Location $Root

$env:PIP_DISABLE_PIP_VERSION_CHECK = "1"

$venvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    Write-Host "Creating virtual environment..."
    python -m venv .venv
}
& $venvPython -m pip install -r requirements.txt -q

$envFile = Join-Path $Root ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item (Join-Path $Root ".env.example") $envFile
    Write-Host "Created .env from .env.example - set API keys and passwords before verifying labels."
}

$labelsDir = Join-Path $Root "samples\labels"
if (-not (Test-Path (Join-Path $labelsDir "old_tom_pass.png"))) {
    Write-Host "Generating sample labels..."
    & $venvPython scripts/generate_samples.py
}

$port = if ($env:PORT) { $env:PORT } else { "8080" }
Write-Host ""
Write-Host "Local dev: http://127.0.0.1:$port/login"
Write-Host "Login: developer / DEVELOPER_PASSWORD from .env (unlimited tests if MAX_TESTS=0)"
Write-Host "Press Ctrl+C to stop."
if ($NoReload) {
    Write-Host "Hot reload: run .\scripts\dev.ps1 from PowerShell (without -NoReload)."
}
Write-Host ""

$uvicornArgs = @(
    "-m", "uvicorn", "app.main:app",
    "--host", "127.0.0.1",
    "--port", "$port"
)
if (-not $NoReload) {
    $uvicornArgs += "--reload"
}

try {
    & $venvPython @uvicornArgs
    exit $LASTEXITCODE
} catch [System.Management.Automation.PipelineStoppedException] {
    exit 0
}
