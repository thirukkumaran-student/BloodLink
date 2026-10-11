<#
.SYNOPSIS
    BloodLink — PostgreSQL setup for Windows (PowerShell). Owner: D1.

.DESCRIPTION
    Creates the application and test databases if they are missing, installs the
    PostgreSQL driver if needed, runs the migrations, writes the connection into .env
    (generating a secret key), and prints exactly what to run next.

    Safe to re-run: existing databases, an already-migrated schema and existing .env
    keys are left alone.

.EXAMPLE
    .\scripts\setup_postgres.ps1
    # uses postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink

.EXAMPLE
    .\scripts\setup_postgres.ps1 -DatabaseUrl "postgresql+psycopg://postgres:secret@localhost:5432/bloodlink"

.EXAMPLE
    .\scripts\setup_postgres.ps1 -EnvFile "C:\temp\bloodlink.env"   # do not touch the repo .env

.NOTES
    Run this from the repository root. If PowerShell blocks the script, start a
    session with:  Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$DatabaseUrl,
    [string]$TestDatabaseUrl,
    [string]$EnvFile,
    [switch]$NoEnv
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version 2.0

$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot
if (-not $EnvFile) { $EnvFile = Join-Path $RepoRoot '.env' }

$DefaultUrl = 'postgresql+psycopg://bloodlink:bloodlink@localhost:5432/bloodlink'

function Say  { param([string]$Text) Write-Host "`n$Text" -ForegroundColor White }
function Ok   { param([string]$Text) Write-Host "  [ok] $Text"   -ForegroundColor Green }
function Warn { param([string]$Text) Write-Host "  [!!] $Text"   -ForegroundColor Yellow }
function Die  { param([string]$Text) Write-Host "  [xx] $Text" -ForegroundColor Red; exit 1 }

# ----------------------------------------------------------------- python lookup
$script:PythonExe = $null
$script:PythonArgs = @()

function Resolve-Python {
    if ($script:PythonExe) { return }
    $candidates = @(
        @{ Exe = 'py';      Args = @('-3') },   # the Windows launcher — most reliable
        @{ Exe = 'python';  Args = @() },
        @{ Exe = 'python3'; Args = @() }
    )
    foreach ($candidate in $candidates) {
        if (-not (Get-Command $candidate.Exe -ErrorAction SilentlyContinue)) { continue }
        try {
            $version = & $candidate.Exe @($candidate.Args + @('-c', 'import sys; print(sys.version_info[0])')) 2>$null
            if ($LASTEXITCODE -eq 0 -and ($version | Out-String).Trim() -eq '3') {
                $script:PythonExe = $candidate.Exe
                $script:PythonArgs = $candidate.Args
                return
            }
        } catch { }
    }
    Die "Python 3 not found. Install Python 3.12+ (winget install Python.Python.3.12) and reopen the terminal."
}

function Invoke-Python {
    Resolve-Python
    & $script:PythonExe @($script:PythonArgs + $args)
}

function Test-PythonImport {
    param([string]$Module)
    Resolve-Python
    & $script:PythonExe @($script:PythonArgs + @('-c', "import $Module")) 2>$null
    return $LASTEXITCODE -eq 0
}

# --------------------------------------------------------------- .env utilities
function Get-EnvValue {
    param([string]$Key)
    if (-not (Test-Path -LiteralPath $EnvFile)) { return $null }
    $line = Get-Content -LiteralPath $EnvFile |
        Where-Object { $_ -match "^$([regex]::Escape($Key))=" } |
        Select-Object -Last 1
    if (-not $line) { return $null }
    return ($line -split '=', 2)[1]
}

function Set-EnvValues {
    param([hashtable]$Values)
    # Written through .NET so the file stays UTF-8 *without* a BOM (Windows
    # PowerShell's Set-Content would add one, which breaks the first key).
    $lines = @()
    if (Test-Path -LiteralPath $EnvFile) { $lines = @(Get-Content -LiteralPath $EnvFile) }
    foreach ($key in $Values.Keys) {
        $pattern = "^$([regex]::Escape($key))="
        $replaced = $false
        for ($i = 0; $i -lt $lines.Count; $i++) {
            if ($lines[$i] -match $pattern) {
                $lines[$i] = "$key=$($Values[$key])"
                $replaced = $true
                break
            }
        }
        if (-not $replaced) {
            if ($lines.Count -gt 0 -and $lines[-1] -ne '') { $lines += '' }
            $lines += "$key=$($Values[$key])"
        }
    }
    [System.IO.File]::WriteAllLines($EnvFile, $lines, (New-Object System.Text.UTF8Encoding($false)))
}

# ---------------------------------------------------------------------- URL prep
# `postgresql://` alone makes SQLAlchemy reach for psycopg2, which this project does
# not install — normalise to the driver we do install.
if ($DatabaseUrl -and $DatabaseUrl -match '^postgresql://') {
    $DatabaseUrl = 'postgresql+psycopg://' + ($DatabaseUrl -replace '^postgresql://', '')
}

# Precedence: parameter -> $env:BLOODLINK_DATABASE_URL -> .env -> built-in default.
$AppUrl = $DatabaseUrl
if (-not $AppUrl) { $AppUrl = $env:BLOODLINK_DATABASE_URL }
if (-not $AppUrl) { $AppUrl = Get-EnvValue 'BLOODLINK_DATABASE_URL' }
if (-not $AppUrl) { $AppUrl = $DefaultUrl }

if ($AppUrl -notmatch '^postgresql\+psycopg://') {
    Die "expected a postgresql+psycopg:// URL, got: $AppUrl"
}

$LibpqUrl = $AppUrl -replace 'postgresql\+psycopg', 'postgresql'
$DbName = ($LibpqUrl -split '/')[-1]
if ($DbName -match '\?') { $DbName = ($DbName -split '\?')[0] }
$BaseUrl = $LibpqUrl.Substring(0, $LibpqUrl.LastIndexOf('/'))
$MaintenanceUrl = "$BaseUrl/postgres"

if (-not $TestDatabaseUrl) { $TestDatabaseUrl = "$BaseUrl/${DbName}_test" }

Say 'BloodLink -> PostgreSQL setup'
Write-Host "  application database : $LibpqUrl"
Write-Host "  test database        : $TestDatabaseUrl"

# ------------------------------------------------------------------- 1. preflight
Say '1. Prerequisites'
if (-not (Get-Command psql -ErrorAction SilentlyContinue)) {
    Die @"
psql is not on PATH. Add the PostgreSQL bin folder, e.g.
    `$env:Path += ';C:\Program Files\PostgreSQL\17\bin'
or re-install with: winget install PostgreSQL.PostgreSQL.17
"@
}

if (-not (Test-PythonImport 'psycopg')) {
    Warn 'psycopg (PostgreSQL driver) is not installed - installing requirements-postgres.txt'
    Invoke-Python -m pip install -q -r requirements-postgres.txt
    if ($LASTEXITCODE -ne 0) { Die 'could not install the driver. Run: python -m pip install -r requirements-postgres.txt' }
}
$psycopgVersion = (Invoke-Python -c 'import psycopg; print(psycopg.__version__)') | Out-String
Ok "psycopg available ($($psycopgVersion.Trim()))"

$connected = $false
& psql $LibpqUrl -c 'select 1' *> $null
if ($LASTEXITCODE -eq 0) {
    $connected = $true
    Ok "connected to $DbName"
} else {
    Warn "cannot connect to $DbName - checking whether it exists"
    & psql $MaintenanceUrl -c 'select 1' *> $null
    if ($LASTEXITCODE -ne 0) {
        Die "cannot reach the server at $BaseUrl - is PostgreSQL running, and are the user/password right?"
    }
    Ok 'server reachable, database is missing'
}

if (-not $connected) {
    $created = 0
    foreach ($name in @($DbName, "$($DbName)_test")) {
        & psql $MaintenanceUrl -c "CREATE DATABASE `"$name`"" *> $null
        if ($LASTEXITCODE -eq 0) {
            Ok "created database $name"
            $created++
        } else {
            Warn "could not create $name (role lacks CREATEDB) - ask an administrator to run:"
            Write-Host "       CREATE DATABASE `"$name`";"
        }
    }
    if ($created -eq 0) { Die 'no database could be created; re-run this script afterwards' }
} else {
    & psql $MaintenanceUrl -c "CREATE DATABASE `"$($DbName)_test`"" *> $null
    if ($LASTEXITCODE -eq 0) { Ok "created test database $($DbName)_test" }
    else { Ok "test database $($DbName)_test already present (or not creatable by this role)" }
}

# -------------------------------------------------------------------- 2. migrate
Say '2. Migrations'
$previousUrl = $env:BLOODLINK_DATABASE_URL
$env:BLOODLINK_DATABASE_URL = $AppUrl
Invoke-Python -m alembic upgrade head
if ($LASTEXITCODE -ne 0) { $env:BLOODLINK_DATABASE_URL = $previousUrl; Die 'migration failed - see the output above' }
Invoke-Python -m alembic check
if ($LASTEXITCODE -ne 0) { Warn 'alembic check reported drift - run it yourself to see the detail' }

$tables = (& psql $LibpqUrl -tAc "select count(*) from information_schema.tables where table_schema='public'") | Out-String
Ok "schema ready ($($tables.Trim()) tables in $DbName)"

# ----------------------------------------------------------------------- 3. .env
if (-not $NoEnv) {
    Say "3. Configuration ($EnvFile)"
    $secret = Get-EnvValue 'BLOODLINK_SECRET_KEY'
    if (-not $secret) { $secret = (Invoke-Python -c 'import secrets; print(secrets.token_urlsafe(48))') | Out-String; $secret = $secret.Trim() }
    $seed = Get-EnvValue 'BLOODLINK_SEED_ON_STARTUP'
    if (-not $seed) { $seed = 'true' }
    Set-EnvValues @{
        BLOODLINK_DATABASE_URL        = $AppUrl
        BLOODLINK_SECRET_KEY          = $secret
        BLOODLINK_SEED_ON_STARTUP     = $seed
    }
    Ok "BLOODLINK_DATABASE_URL set"
    Ok "BLOODLINK_SECRET_KEY present"
    Ok "BLOODLINK_SEED_ON_STARTUP=$seed"
} else {
    Say '3. Configuration'
    Warn "skipped (-NoEnv). Add this line to your .env yourself:"
    Write-Host "       BLOODLINK_DATABASE_URL=$AppUrl"
}
$env:BLOODLINK_DATABASE_URL = $previousUrl

# ------------------------------------------------------------------ 4. next steps
Say 'Next: run it (two terminals)'
Write-Host @"
  Terminal 1 - API on :8000
      .\scripts\dev.ps1 api
      # equivalent long form:
      `$env:PYTHONPATH = 'apps/api;packages/config;packages/contracts;packages/validation'
      python -m uvicorn bloodlink_api.main:app --reload --port 8000

  Terminal 2 - web client on :5173
      .\scripts\dev.ps1 web

  Open http://localhost:5173 - demo accounts, password Bloodlink#2026:
      apollo.staff@bloodlink.dev    hospital     (review queue, request board)
      priya@bloodlink.dev           donor        (accept a matched request)
      redcross.staff@bloodlink.dev  blood centre (nearby requests, availability)
      admin@bloodlink.dev           admin        (verification, users, audit)
  First API start creates nothing extra (tables already migrated) and seeds the demo
  data when BLOODLINK_SEED_ON_STARTUP=true. Tour: docs/demo-walkthrough.md

  Tests against PostgreSQL:
      .\scripts\dev.ps1 test-postgres -TestDatabaseUrl "$TestDatabaseUrl"

  Reset the demo data (after a walkthrough consumes it):
      .\scripts\dev.ps1 reset-db
"@
