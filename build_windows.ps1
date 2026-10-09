<#
.SYNOPSIS
  Build BillDesk for Windows: tests -> PyInstaller -> self-test of the built exe -> installer.

.EXAMPLE
  .\build_windows.ps1                 # full pipeline
  .\build_windows.ps1 -SkipTests      # faster rebuild
  .\build_windows.ps1 -Version 1.1.0  # stamp the installer

Output:  dist\BillDesk\BillDesk.exe   (run this folder anywhere)
         dist\BillDesk-Setup.exe      (installer; needs Inno Setup 6)
The build FAILS if the packaged exe does not pass `BillDesk.exe --selftest`.
Needs resources\mongo\win32-x64\mongod.exe (run scripts\fetch-mongod.ps1 if it is missing).
#>
[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$SkipInstaller,
    [string]$Version = "1.0.0",
    [string]$Python = "python"
)
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Step($m) { Write-Host "`n=== $m" -ForegroundColor Cyan }
function Fail($m) { Write-Host "[ERR] $m" -ForegroundColor Red; exit 1 }

Step "Checking prerequisites"
if (-not (Test-Path "resources\mongo\win32-x64\mongod.exe")) { Fail "resources\mongo\win32-x64\mongod.exe is missing - run scripts\fetch-mongod.ps1" }
& $Python -m pip install --quiet -r requirements-dev.txt
if ($LASTEXITCODE) { Fail "pip install failed" }

if (-not $SkipTests) {
    Step "Running the test suite"
    $env:MONGODB_URL = "mongodb://127.0.0.1:1"      # the suite must not need (or touch) a real database
    & $Python -m pytest tests -q -p no:cacheprovider
    Remove-Item Env:MONGODB_URL
    if ($LASTEXITCODE) { Fail "tests failed - not building" }
}

Step "Cleaning previous build"
Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue

Step "Building with PyInstaller (BillDesk.spec)"
& $Python -m PyInstaller --noconfirm --clean BillDesk.spec
if ($LASTEXITCODE -or -not (Test-Path "dist\BillDesk\BillDesk.exe")) { Fail "PyInstaller failed" }

Step "Smoke test: dist\BillDesk\BillDesk.exe --selftest"
$out = Join-Path $env:TEMP "billdesk_selftest.txt"
$p = Start-Process -FilePath "dist\BillDesk\BillDesk.exe" -ArgumentList "--selftest" -RedirectStandardOutput $out -Wait -PassThru -WindowStyle Hidden
Get-Content $out
if ($p.ExitCode -ne 0) { Fail "the packaged application failed its self-test (exit $($p.ExitCode))" }

if (-not $SkipInstaller) {
    Step "Building the installer (Inno Setup)"
    $iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe", "$env:ProgramFiles\Inno Setup 6\ISCC.exe") |
        Where-Object { Test-Path $_ } | Select-Object -First 1
    if (-not $iscc) { Write-Host "[WARN] Inno Setup 6 not found - skipping the installer (winget install JRSoftware.InnoSetup)" -ForegroundColor Yellow }
    else {
        & $iscc "/DAppVersion=$Version" "installer\BillDesk.iss"
        if ($LASTEXITCODE) { Fail "Inno Setup failed" }
        Write-Host "[OK] dist\BillDesk-Setup.exe" -ForegroundColor Green
    }
}
Write-Host "`n[OK] Build complete: dist\BillDesk\BillDesk.exe" -ForegroundColor Green
