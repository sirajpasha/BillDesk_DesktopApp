<#
.SYNOPSIS
  Downloads a pinned MongoDB Community release, verifies its SHA-256 against
  the checksum published by MongoDB, and extracts ONLY mongod (plus licence
  files) into resources/mongo/<platform>/ for running with the desktop app.
#>
param(
    [string]$Version = "8.0.4",
    [switch]$Force
)

$ErrorActionPreference = "Stop"
$root    = Split-Path -Parent $PSScriptRoot
$outDir  = Join-Path $root "resources\mongo\win32-x64"
$marker  = Join-Path $outDir "VERSION"
$zipName = "mongodb-windows-x86_64-$Version.zip"
$url     = "https://fastdl.mongodb.org/windows/$zipName"
$cache   = Join-Path $root ".cache\mongo"

if (-not $Force -and (Test-Path $marker) -and ((Get-Content $marker -Raw).Trim() -eq $Version) -and (Test-Path (Join-Path $outDir "mongod.exe"))) {
    Write-Host "mongod $Version already present at $outDir"
    exit 0
}

New-Item -ItemType Directory -Force -Path $cache, $outDir | Out-Null
$zipPath = Join-Path $cache $zipName

# Expected checksum comes from MongoDB itself
$expected = ((Invoke-RestMethod "$url.sha256") -split "\s+")[0].ToLower()
if ($expected.Length -ne 64) { throw "Could not read SHA-256 from $url.sha256" }

function Get-Hash256($p) { (Get-FileHash -Algorithm SHA256 -Path $p).Hash.ToLower() }

if (-not (Test-Path $zipPath) -or (Get-Hash256 $zipPath) -ne $expected) {
    Write-Host "Downloading $url ..."
    & curl.exe -L --fail -C - -o $zipPath $url
    if ($LASTEXITCODE -ne 0) { throw "Download failed (curl exit $LASTEXITCODE)" }
}

$actual = Get-Hash256 $zipPath
if ($actual -ne $expected) {
    Remove-Item $zipPath -Force
    throw "SHA-256 mismatch for $zipName. expected=$expected actual=$actual (corrupt file deleted; re-run)"
}
Write-Host "SHA-256 verified: $actual"

Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [System.IO.Compression.ZipFile]::OpenRead($zipPath)
try {
    $wanted = @{
        "bin/mongod.exe"      = "mongod.exe"
        "LICENSE-Community.txt" = "LICENSE-Community.txt"
        "THIRD-PARTY-NOTICES" = "THIRD-PARTY-NOTICES.txt"
    }
    $found = @{}
    foreach ($entry in $zip.Entries) {
        $rel = ($entry.FullName -split "/", 2)[1]
        if ($rel -and $wanted.ContainsKey($rel)) {
            $dest = Join-Path $outDir $wanted[$rel]
            [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $dest, $true)
            $found[$rel] = $true
        }
    }
    if (-not $found.ContainsKey("bin/mongod.exe")) { throw "mongod.exe not found inside $zipName" }
} finally {
    $zip.Dispose()
}

Set-Content -Path $marker -Value $Version -NoNewline
Write-Host "Extracted mongod $Version to $outDir"
& (Join-Path $outDir "mongod.exe") --version | Select-Object -First 2
