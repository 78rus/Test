$ErrorActionPreference = "Stop"

$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $root

$pyLauncher = Get-Command py -ErrorAction SilentlyContinue
$pythonLauncher = Get-Command python -ErrorAction SilentlyContinue
if ($null -eq $pyLauncher -and $null -eq $pythonLauncher) {
    throw "Python 3.10+ was not found. Install Python from https://www.python.org/downloads/windows/"
}

$venv = Join-Path $root ".venv-windows"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
    if ($null -ne $pyLauncher) {
        & $pyLauncher.Source -3 -m venv $venv
    } else {
        & $pythonLauncher.Source -m venv $venv
    }
}

$venvPython = Join-Path $venv "Scripts\python.exe"
& $venvPython -m pip install --upgrade pip
& $venvPython -m pip install --upgrade ".[qt,ssh,secure,build]"

if (Test-Path (Join-Path $root "build")) {
    Remove-Item (Join-Path $root "build") -Recurse -Force
}
if (Test-Path (Join-Path $root "dist")) {
    Remove-Item (Join-Path $root "dist") -Recurse -Force
}

& $venvPython -m PyInstaller --noconfirm --clean "packaging\windows\CashdeskControl.spec"

Write-Host ""
Write-Host "Build complete: $root\dist\CashdeskControl\CashdeskControl.exe" -ForegroundColor Green
