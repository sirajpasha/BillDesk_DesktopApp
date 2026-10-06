# ==============================================================================
# BillDesk Native - Application Startup Script (PowerShell)
#
# Checks all required dependencies before starting the application:
# 1. Python environment and required packages (requirements.txt)
# 2. MongoDB service (127.0.0.1:27018) with auto-start if not running
# 3. Launches the native application: python main.py
# ==============================================================================

[CmdletBinding()]
param(
    [int]$Port = 27018,
    [switch]$SkipMongo,
    [switch]$ForceInstallDeps,
    [switch]$CheckOnly,
    [switch]$Help,
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$AppArgs
)

$ErrorActionPreference = "Stop"

function Write-Info($msg)    { Write-Host "[INFO] $msg" -ForegroundColor Cyan }
function Write-Success($msg) { Write-Host "[OK]   $msg" -ForegroundColor Green }
function Write-Warning($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Failure($msg) { Write-Host "[ERR]  $msg" -ForegroundColor Red }

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "============================================================" -ForegroundColor DarkCyan
Write-Host "         BillDesk Native Mandi POS & ERP Launcher           " -ForegroundColor White
Write-Host "============================================================" -ForegroundColor DarkCyan

# ------------------------------------------------------------------------------
# 1. Read .env configuration if present
# ------------------------------------------------------------------------------
$envFile = Join-Path $ScriptDir ".env"
$mongoHost = "127.0.0.1"
$mongoPort = $Port

if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#")) {
            $parts = $line.Split("=", 2)
            if ($parts.Length -eq 2) {
                $key = $parts[0].Trim()
                $val = $parts[1].Trim()
                if ($key -eq "MONGODB_URL") {
                    # e.g. mongodb://127.0.0.1:27018
                    if ($val -match "://([^:/]+)(?::(\d+))?") {
                        if ($matches[1]) { $mongoHost = $matches[1] }
                        if ($matches[2]) { $mongoPort = [int]$matches[2] }
                    }
                }
            }
        }
    }
}

# ------------------------------------------------------------------------------
# 2. Check Python Environment
# ------------------------------------------------------------------------------
Write-Info "Checking Python installation..."
$pythonCmd = Get-Command "python" -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command "python3" -ErrorAction SilentlyContinue
}

if (-not $pythonCmd) {
    Write-Failure "Python executable not found in PATH! Please install Python 3.10+ and add it to PATH."
    exit 1
}

$pyVersion = & python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
Write-Success "Found Python $pyVersion ($($pythonCmd.Source))"

# Check Python Packages
Write-Info "Checking Python dependency packages..."
$checkDepsPy = @"
import sys
required = ['pymongo', 'pydantic', 'dotenv', 'bcrypt', 'reportlab', 'pymupdf', 'certifi']
missing = []
for pkg in required:
    try:
        __import__(pkg)
    except ImportError:
        missing.append(pkg)
if missing:
    print('MISSING:' + ','.join(missing))
    sys.exit(1)
else:
    print('OK')
    sys.exit(0)
"@

$depsCheck = & python -c "$checkDepsPy" 2>$null
$needsInstall = ($LASTEXITCODE -ne 0) -or $ForceInstallDeps

if ($needsInstall) {
    Write-Warning "One or more Python dependencies are missing. Installing from requirements.txt..."
    & python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Failure "Failed to install Python dependencies. Please check your internet connection or pip configuration."
        exit 1
    }
    Write-Success "Python dependencies successfully installed."
} else {
    Write-Success "All Python package dependencies verified."
}

# ------------------------------------------------------------------------------
# 3. Check and Start MongoDB Dependency
# ------------------------------------------------------------------------------
function Test-PortOpen([string]$HostName, [int]$PortNum, [int]$TimeoutMs = 1000) {
    $client = $null
    try {
        $client = New-Object System.Net.Sockets.TcpClient
        $iar = $client.BeginConnect($HostName, $PortNum, $null, $null)
        $wh = $iar.AsyncWaitHandle
        if (-not $wh.WaitOne($TimeoutMs, $false)) {
            $client.Close()
            return $false
        }
        $client.EndConnect($iar)
        $client.Close()
        return $true
    } catch {
        if ($client) { $client.Close() }
        return $false
    }
}

if (-not $SkipMongo) {
    Write-Info "Checking MongoDB dependency on $mongoHost`:$mongoPort..."

    $isMongoRunning = Test-PortOpen $mongoHost $mongoPort 1000

    if ($isMongoRunning) {
        Write-Success "MongoDB is already running and accepting connections on $mongoHost`:$mongoPort."
    } else {
        Write-Warning "MongoDB is NOT running on $mongoHost`:$mongoPort. Attempting to start MongoDB service..."

        # Locate mongod.exe
        $candidates = @(
            (Join-Path $ScriptDir "resources\mongo\win32-x64\mongod.exe"),
            "C:\Program Files\MongoDB\Server\8.0\bin\mongod.exe",
            "C:\Program Files\MongoDB\Server\7.0\bin\mongod.exe",
            "C:\Program Files\MongoDB\Server\6.0\bin\mongod.exe"
        )

        $mongodExe = $null
        foreach ($c in $candidates) {
            if (Test-Path $c) {
                $mongodExe = $c
                break
            }
        }

        if (-not $mongodExe) {
            $fetchScript = Join-Path $ScriptDir "scripts\fetch-mongod.ps1"
            if (Test-Path $fetchScript) {
                Write-Info "mongod.exe not found locally. Downloading official MongoDB Community binary..."
                & powershell -NoProfile -ExecutionPolicy Bypass -File $fetchScript
                $localMongod = Join-Path $ScriptDir "resources\mongo\win32-x64\mongod.exe"
                if (Test-Path $localMongod) {
                    $mongodExe = $localMongod
                }
            }
        }

        if (-not $mongodExe -or -not (Test-Path $mongodExe)) {
            Write-Failure "Could not locate or download mongod.exe!"
            Write-Failure "Please install MongoDB Community Server or place mongod.exe into resources\mongo\win32-x64\."
            exit 1
        }

        Write-Info "Using MongoDB binary: $mongodExe"

        # Prepare data and logs directories
        $dataDir = Join-Path $env:APPDATA 'BillDesk\db'
        $logsDir = Join-Path $env:APPDATA 'BillDesk\logs'
        New-Item -ItemType Directory -Force -Path $dataDir, $logsDir | Out-Null

        $logPath = Join-Path $logsDir "mongod.log"

        Write-Info "Starting MongoDB daemon (Data: $dataDir, Port: $mongoPort)..."

        $mongoArgs = @(
            '--dbpath', $dataDir,
            '--bind_ip', $mongoHost,
            '--port', [string]$mongoPort,
            '--logpath', $logPath,
            '--logappend',
            '--wiredTigerCacheSizeGB', '0.5'
        )

        Start-Process -FilePath $mongodExe -ArgumentList $mongoArgs -WindowStyle Hidden

        # Wait for MongoDB to become ready (up to 25 seconds)
        Write-Info "Waiting for MongoDB to initialize..."
        $ready = $false
        for ($i = 1; $i -le 50; $i++) {
            Start-Sleep -Milliseconds 500
            if (Test-PortOpen $mongoHost $mongoPort 500) {
                $ready = $true
                break
            }
        }

        if (-not $ready) {
            Write-Failure "MongoDB failed to start within 25 seconds!"
            Write-Failure "Check MongoDB logs at: $logPath"
            exit 1
        }

        Write-Success "MongoDB started and verified on $mongoHost`:$mongoPort."
    }

    # Verify MongoDB connectivity via pymongo ping
    Write-Info "Testing database handshake..."
    $dbPingPy = @"
from pymongo import MongoClient
import sys
try:
    client = MongoClient('mongodb://$mongoHost`:$mongoPort', serverSelectionTimeoutMS=3000)
    client.admin.command('ping')
    print('PING_OK')
    sys.exit(0)
except Exception as e:
    print('PING_FAIL:', e)
    sys.exit(1)
"@
    $pingResult = & python -c "$dbPingPy" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Success "MongoDB database connection confirmed."
    } else {
        Write-Warning "MongoDB port is listening, but ping test returned: $pingResult"
    }
}

if ($CheckOnly) {
    Write-Success "All dependencies verified and ready! (CheckOnly mode)"
    exit 0
}

# ------------------------------------------------------------------------------
# 4. Start Application
# ------------------------------------------------------------------------------
Write-Host "------------------------------------------------------------" -ForegroundColor DarkCyan
Write-Info "Starting application: python main.py $AppArgs"
Write-Host "------------------------------------------------------------" -ForegroundColor DarkCyan

if ($AppArgs) {
    & python main.py $AppArgs
} else {
    & python main.py
}

$exitCode = $LASTEXITCODE
if ($exitCode -ne 0) {
    Write-Failure "Application exited with code $exitCode."
} else {
    Write-Success "Application closed normally."
}

exit $exitCode
