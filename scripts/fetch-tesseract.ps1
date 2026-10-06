<#
.SYNOPSIS
  Fetches the open-source Tesseract OCR engine (Windows x64) + English/Tamil language data and extracts ONLY what
  the desktop app needs into resources/tesseract/win32-x64/ (tesseract.exe, its DLLs, tessdata).

.NOTES
  * Source: UB Mannheim Windows build of Tesseract (Apache-2.0). The installer is verified against the SHA-256
    published in the winget community manifest (independent of the download host).
  * Extraction uses 7-Zip (found on PATH / Program Files, otherwise the 7-Zip MSI is unpacked locally with an
    administrative extract: nothing is installed and no admin rights are needed); the MSI hash is pinned.
  * tam.traineddata comes from tessdata_best (noticeably better Tamil than tessdata_fast); its hash is pinned below.
  * Re-running is a no-op when the pinned version is already present (use -Force to redo).
#>
param([switch]$Force)

$ErrorActionPreference = "Stop"
$Version   = "5.4.0.20240606"
$InstUrl   = "https://github.com/UB-Mannheim/tesseract/releases/download/v$Version/tesseract-ocr-w64-setup-$Version.exe"
$InstSha   = "c885fff6998e0608ba4bb8ab51436e1c6775c2bafc2559a19b423e18678b60c9"
$TamUrl    = "https://github.com/tesseract-ocr/tessdata_best/raw/main/tam.traineddata"
$TamSha    = "4b9ce85987f629dd31eaf87443a1646452a43cdf91fcf05e017382ad595dcb9e"
$SevenMsi  = "https://www.7-zip.org/a/7z2409-x64.msi"
$SevenSha  = "ec6af1ea0367d16dde6639a89a080a524cebc4d4bedfe00ed0cac4b865a918d8"   # 7-Zip 24.09 x64 MSI (7-zip.org publishes no checksum; pinned on first download)

# Exactly the DLLs tesseract.exe needs (transitive imports, checked with pefile); the installer ships ~50.
$Dlls = "libarchive-13.dll libb2-1.dll libbz2-1.dll libcrypto-3-x64.dll libdeflate.dll libexpat-1.dll libgcc_s_seh-1.dll libgif-7.dll libiconv-2.dll libjbig-0.dll libjpeg-8.dll libleptonica-6.dll libLerc.dll liblz4.dll liblzma-5.dll libopenjp2-7.dll libpng16-16.dll libsharpyuv-0.dll libstdc++-6.dll libtesseract-5.dll libtiff-6.dll libwebp-7.dll libwebpmux-3.dll libwinpthread-1.dll libzstd.dll zlib1.dll".Split(" ")

$root   = Split-Path -Parent $PSScriptRoot
$out    = Join-Path $root "resources\tesseract\win32-x64"
$marker = Join-Path $out "VERSION"
$cache  = Join-Path $root ".cache\tesseract"

if (-not $Force -and (Test-Path $marker) -and ((Get-Content $marker -Raw).Trim() -eq $Version) -and (Test-Path (Join-Path $out "tesseract.exe")) -and (Test-Path (Join-Path $out "tessdata\tam.traineddata"))) {
    Write-Host "Tesseract $Version already present at $out"; exit 0
}

New-Item -ItemType Directory -Force -Path $cache | Out-Null
function Get-Verified($url, $sha, $dest) {
    if (-not (Test-Path $dest) -or (Get-FileHash $dest -Algorithm SHA256).Hash.ToLower() -ne $sha) {
        Write-Host "Downloading $url"
        & curl.exe -L --fail -C - -o $dest $url
        if ($LASTEXITCODE -ne 0) { throw "download failed: $url" }
    }
    $h = (Get-FileHash $dest -Algorithm SHA256).Hash.ToLower()
    if ($h -ne $sha) { Remove-Item $dest -Force; throw "SHA-256 mismatch for $url (got $h)" }
}

$inst = Join-Path $cache "tesseract-setup-$Version.exe"
$tam  = Join-Path $cache "tam.traineddata"
Get-Verified $InstUrl $InstSha $inst
Get-Verified $TamUrl  $TamSha  $tam

# --- 7-Zip
$seven = @("7z.exe") | ForEach-Object { (Get-Command $_ -ErrorAction SilentlyContinue).Source } | Where-Object { $_ } | Select-Object -First 1
if (-not $seven) { $seven = @("$env:ProgramFiles\7-Zip\7z.exe", "${env:ProgramFiles(x86)}\7-Zip\7z.exe", "$cache\7z\Files\7-Zip\7z.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1 }
if (-not $seven) {
    $msi = Join-Path $cache "7z.msi"
    Get-Verified $SevenMsi $SevenSha $msi
    Start-Process msiexec -ArgumentList "/a", "`"$msi`"", "/qn", "TARGETDIR=`"$cache\7z`"" -Wait
    $seven = "$cache\7z\Files\7-Zip\7z.exe"
}

# --- extract
$tmp = Join-Path $cache "extract"
if (Test-Path $tmp) { Remove-Item $tmp -Recurse -Force }
& $seven x -y "-o$tmp" $inst | Out-Null
if (-not (Test-Path (Join-Path $tmp "tesseract.exe"))) { throw "tesseract.exe not found in installer" }

if (Test-Path $out) { Remove-Item $out -Recurse -Force }
New-Item -ItemType Directory -Force -Path (Join-Path $out "tessdata") | Out-Null
Copy-Item (Join-Path $tmp "tesseract.exe") $out
foreach ($d in $Dlls) { Copy-Item (Join-Path $tmp $d) $out }
Copy-Item (Join-Path $tmp "tessdata\configs") (Join-Path $out "tessdata\configs") -Recurse
Copy-Item (Join-Path $tmp "tessdata\eng.traineddata"), (Join-Path $tmp "tessdata\osd.traineddata") (Join-Path $out "tessdata")
Copy-Item $tam (Join-Path $out "tessdata\tam.traineddata")
if (Test-Path (Join-Path $tmp "doc\LICENSE")) { Copy-Item (Join-Path $tmp "doc\LICENSE") (Join-Path $out "LICENSE-Tesseract.txt") }
Remove-Item $tmp -Recurse -Force
Set-Content -Path $marker -Value $Version -NoNewline

Write-Host "Tesseract $Version extracted to $out"
& (Join-Path $out "tesseract.exe") --list-langs
