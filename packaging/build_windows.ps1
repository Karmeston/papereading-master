param(
    [string]$PythonExe = "",
    [switch]$SkipInstaller
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$packagingPython = Join-Path $root ".packaging-venv\Scripts\python.exe"
if (-not $PythonExe) {
    $PythonExe = if (Test-Path -LiteralPath $packagingPython) { $packagingPython } else { "python" }
}
$build = Join-Path $root "build"
$dist = Join-Path $root "dist"
$release = Join-Path $root "release"

foreach ($target in @($build, $dist, $release)) {
    $full = [IO.Path]::GetFullPath($target)
    if (-not $full.StartsWith($root + [IO.Path]::DirectorySeparatorChar)) {
        throw "Refusing to remove a path outside the repository: $full"
    }
    if (Test-Path -LiteralPath $full) {
        Remove-Item -LiteralPath $full -Recurse -Force
    }
}

& $PythonExe -c "import PyInstaller, webview, PIL" | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Desktop build dependencies are missing. Run: pip install -e .[desktop] pillow"
}

& $PythonExe (Join-Path $PSScriptRoot "create_icon.py")
if ($LASTEXITCODE -ne 0) { throw "Icon generation failed." }

Push-Location $root
try {
    & $PythonExe -m PyInstaller --noconfirm --clean (Join-Path $PSScriptRoot "PapereadingMaster.spec")
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller build failed." }
} finally {
    Pop-Location
}

if ($SkipInstaller) {
    Write-Host "Portable application built at: $dist\PapereadingMasterBeta"
    exit 0
}

$isccCandidates = @(
    ${env:INNO_SETUP_COMPILER},
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    "C:\Program Files (x86)\Inno Setup 6\ISCC.exe",
    "C:\Program Files\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

$iscc = $isccCandidates | Select-Object -First 1
if (-not $iscc) {
    throw "Inno Setup 6 was not found. Install it or set INNO_SETUP_COMPILER."
}

& $iscc (Join-Path $PSScriptRoot "PapereadingMaster.iss")
if ($LASTEXITCODE -ne 0) { throw "Installer build failed." }

$installer = Get-ChildItem -LiteralPath $release -Filter "*.exe" | Select-Object -First 1
if (-not $installer) { throw "Installer output was not found." }
$hash = Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256
"$($hash.Hash)  $($installer.Name)" | Set-Content -LiteralPath (Join-Path $release "SHA256SUMS.txt") -Encoding ascii
Write-Host "Installer built at: $($installer.FullName)"
Write-Host "SHA256: $($hash.Hash)"
