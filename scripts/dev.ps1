<#
.SYNOPSIS
    BloodLink task runner for Windows (PowerShell). Owner: D1.
    The Windows equivalent of the Makefile targets — `make` is not required.

.EXAMPLE
    .\scripts\dev.ps1 help
    .\scripts\dev.ps1 api                 # API on :8000, database from .env
    .\scripts\dev.ps1 api -Port 8010
    .\scripts\dev.ps1 web                 # web client on :5173
    .\scripts\dev.ps1 test
    .\scripts\dev.ps1 test-postgres -TestDatabaseUrl "postgresql+psycopg://user:pw@localhost:5432/bloodlink_test"
    .\scripts\dev.ps1 migrate
    .\scripts\dev.ps1 seed
    .\scripts\dev.ps1 reset-db
    .\scripts\dev.ps1 smoke

.NOTES
    If PowerShell blocks the script, run once per session:
        Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$Task = 'help',
    [string]$Port = '8000',
    [string]$WebPort = '5173',
    [string]$DatabaseUrl,
    [string]$TestDatabaseUrl,
    [string]$Message = 'schema change'
)

$ErrorActionPreference = 'Stop'
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $RepoRoot

# ';' on Windows, ':' elsewhere — the API imports its packages through this.
$env:PYTHONPATH = @(
    'apps/api', 'packages/config', 'packages/contracts', 'packages/validation'
) -join [System.IO.Path]::PathSeparator

$script:PythonExe = $null
$script:PythonArgs = @()

function Resolve-Python {
    if ($script:PythonExe) { return }
    foreach ($candidate in @(
            @{ Exe = 'py'; Args = @('-3') },
            @{ Exe = 'python'; Args = @() },
            @{ Exe = 'python3'; Args = @() })) {
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
    Write-Host 'Python 3 not found on PATH. Install it (winget install Python.Python.3.12) and reopen the terminal.' -ForegroundColor Red
    exit 1
}

function Invoke-Python {
    Resolve-Python
    & $script:PythonExe @($script:PythonArgs + $args)
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}

function Get-EnvValue {
    param([string]$Key)
    $envFile = Join-Path $RepoRoot '.env'
    if (-not (Test-Path -LiteralPath $envFile)) { return $null }
    $line = Get-Content -LiteralPath $envFile |
        Where-Object { $_ -match "^$([regex]::Escape($Key))=" } |
        Select-Object -Last 1
    if (-not $line) { return $null }
    return ($line -split '=', 2)[1]
}

function Show-Help {
    Write-Host @'
BloodLink tasks (Windows)

  .\scripts\dev.ps1 setup-postgres [-DatabaseUrl URL]  databases + migrate + .env
  .\scripts\dev.ps1 api [-Port N] [-DatabaseUrl URL]   run the API (uvicorn, reload)
  .\scripts\dev.ps1 web [-WebPort N]                   run the web client (Vite)
  .\scripts\dev.ps1 build                              production bundle
  .\scripts\dev.ps1 test                               pytest (database from .env / SQLite)
  .\scripts\dev.ps1 test-postgres [-TestDatabaseUrl U] pytest against PostgreSQL
  .\scripts\dev.ps1 migrate                            alembic upgrade head
  .\scripts\dev.ps1 migrate-new -Message "add x"       autogenerate a revision (D1 only)
  .\scripts\dev.ps1 seed                               seed the demo dataset
  .\scripts\dev.ps1 smoke                              headless end-to-end walk (API running)
  .\scripts\dev.ps1 smoke-web                          browser-shaped smokes (API + web running)
  .\scripts\dev.ps1 export-contracts                   regenerate docs/*.md
  .\scripts\dev.ps1 reset-db                           wipe the demo data (Postgres) / delete the SQLite file
  .\scripts\dev.ps1 check                              tests + web build + docs

Notes
  - Ports default to 8000 / 5173; override with -Port / -WebPort.
  - Without -DatabaseUrl the database comes from .env (BLOODLINK_DATABASE_URL).
  - If scripts are blocked: Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
'@
}

# Run a database-backed command with an explicit URL, without disturbing .env.
function Invoke-WithDatabase {
    param([scriptblock]$Action)
    $previous = $env:BLOODLINK_DATABASE_URL
    if ($DatabaseUrl) {
        $env:BLOODLINK_DATABASE_URL = $DatabaseUrl
        Write-Host "  [db] $DatabaseUrl"
    } elseif ($previous) {
        Write-Host "  [db] $previous (environment)"
    } else {
        $fromEnv = Get-EnvValue 'BLOODLINK_DATABASE_URL'
        if ($fromEnv) { Write-Host "  [db] $fromEnv (from .env)" } else { Write-Host '  [db] <not set - the API default applies>' }
    }
    try { & $Action } finally { $env:BLOODLINK_DATABASE_URL = $previous }
}

switch ($Task.ToLowerInvariant()) {
    'help' { Show-Help }

    'setup-postgres' {
        $setup = Join-Path $RepoRoot 'scripts/setup_postgres.ps1'
        if ($DatabaseUrl) { & $setup -DatabaseUrl $DatabaseUrl } else { & $setup }
    }

    'api' {
        Invoke-WithDatabase { Invoke-Python -m uvicorn bloodlink_api.main:app --reload --host 0.0.0.0 --port $Port }
    }

    'web' {
        if ($WebPort -ne '5173') { $env:BLOODLINK_WEB_PORT = $WebPort }
        Write-Host "  [web] http://localhost:$WebPort (proxying /api -> http://127.0.0.1:8000)" -ForegroundColor Cyan
        & npm run dev
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

    'build' {
        & npm run build
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    }

    'test' {
        Invoke-WithDatabase { Invoke-Python -m pytest -q }
    }

    'test-postgres' {
        if (-not $TestDatabaseUrl) { $TestDatabaseUrl = Get-EnvValue 'BLOODLINK_TEST_DATABASE_URL' }
        if (-not $TestDatabaseUrl) {
            $appUrl = if ($DatabaseUrl) { $DatabaseUrl } else { Get-EnvValue 'BLOODLINK_DATABASE_URL' }
            if (-not $appUrl) {
                Write-Host '  Provide -TestDatabaseUrl, or set BLOODLINK_TEST_DATABASE_URL in .env.' -ForegroundColor Red
                exit 1
            }
            $TestDatabaseUrl = $appUrl -replace '^(.*/)([^/?]+)', '$1$2_test'
        }
        if ($TestDatabaseUrl -notmatch 'test') {
            Write-Host "  Refusing to run: $TestDatabaseUrl does not look like a test database (the suite drops every table)." -ForegroundColor Red
            exit 1
        }
        $previousTest = $env:BLOODLINK_TEST_DATABASE_URL
        $env:BLOODLINK_TEST_DATABASE_URL = $TestDatabaseUrl
        Write-Host "  [db] $TestDatabaseUrl (test)"
        try { Invoke-Python -m pytest -q } finally { $env:BLOODLINK_TEST_DATABASE_URL = $previousTest }
    }

    'migrate' {
        Invoke-WithDatabase { Invoke-Python -m alembic upgrade head }
    }

    'migrate-new' {
        Invoke-WithDatabase { Invoke-Python -m alembic revision --autogenerate -m $Message }
    }

    'seed' {
        Invoke-WithDatabase { Invoke-Python -m bloodlink_api.seed }
    }

    'smoke' {
        Invoke-Python scripts/smoke_flow.py
    }

    'smoke-web' {
        Invoke-Python scripts/smoke_web_flow.py
        if (Get-Command node -ErrorAction SilentlyContinue) { & node scripts/web_boot_smoke.mjs }
        else { Write-Host '  node not found - skipped the DOM boot smoke' -ForegroundColor Yellow }
    }

    'export-contracts' {
        Invoke-Python scripts/export_contracts.py
    }

    'check' {
        Invoke-Python -m pytest -q
        & npm run build
        if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
        Invoke-Python scripts/export_contracts.py
    }

    'reset-db' {
        $url = if ($DatabaseUrl) { $DatabaseUrl } else { Get-EnvValue 'BLOODLINK_DATABASE_URL' }
        if (-not $url -or $url -match 'sqlite') {
            $dbFile = Join-Path $RepoRoot 'bloodlink.db'
            if (Test-Path -LiteralPath $dbFile) {
                Write-Host '  Stop the API first if it is running (deleting the file under a live server breaks it).' -ForegroundColor Yellow
                Remove-Item -LiteralPath $dbFile -Force
                Write-Host '  Removed bloodlink.db - restart the API to create and seed a fresh one.' -ForegroundColor Green
            } else {
                Write-Host '  No bloodlink.db present - nothing to do.' -ForegroundColor Yellow
            }
        } else {
            if (-not (Get-Command psql -ErrorAction SilentlyContinue)) { Write-Host '  psql not on PATH.' -ForegroundColor Red; exit 1 }
            $libpq = $url -replace 'postgresql\+psycopg', 'postgresql'
            Write-Host '  Stop the API first if it is running.' -ForegroundColor Yellow
            $truncate = @'
TRUNCATE TABLE audit_logs, blood_request_events, blood_requests, conversations, donation_records, donor_outreach, donor_profiles, donor_responses, hospital_subscriptions, idempotency_records, messages, notification_deliveries, notifications, organization_memberships, organization_responses, organizations, patient_needs, push_subscriptions, refresh_tokens, users, verification_documents RESTART IDENTITY CASCADE;
'@
            & psql $libpq -c $truncate
            if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
            Write-Host '  Demo data cleared - restart the API (it re-seeds), or run: .\scripts\dev.ps1 seed' -ForegroundColor Green
        }
    }

    default {
        Write-Host "Unknown task '$Task'." -ForegroundColor Red
        Show-Help
        exit 1
    }
}
