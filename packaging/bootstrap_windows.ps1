param(
    [string]$PythonExe = "python",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$venv = Join-Path $root ".packaging-venv"
$venvPython = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonExe -m venv $venv
    if ($LASTEXITCODE -ne 0) { throw "Failed to create the packaging environment." }
}

& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "Failed to upgrade pip." }
& $venvPython -m pip install -e "$root[desktop]"
if ($LASTEXITCODE -ne 0) { throw "Failed to install desktop build dependencies." }

& (Join-Path $PSScriptRoot "build_windows.ps1") -PythonExe $venvPython -SkipInstaller:$SkipInstaller
if ($LASTEXITCODE -ne 0) { throw "Windows package build failed." }
