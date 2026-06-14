# Full-suite coverage run (fresh .coverage + HTML + XML).
# Usage: .\tests\run_full_coverage.ps1 [-Workers <n>] [-Parallel]
#
# Each worker gets its own database (ngo_databank_test_gw0 ... _gwN) so parallel
# workers no longer contend for DDL locks. The databases are created
# automatically by conftest.py if they do not already exist.

param(
    [switch]$Parallel,
    [int]$Workers = 4,
    [string[]]$ExtraArgs = @()
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "Import-BackofficeEnv.ps1")

$env:FLASK_CONFIG = "testing"

if (-not $env:TEST_DATABASE_URL -and -not $env:DATABASE_URL) {
    Write-Host "WARNING: TEST_DATABASE_URL or DATABASE_URL not set (check Backoffice\.env)." -ForegroundColor Yellow
}

$parallelArgs = @()
if ($Workers -gt 0) {
    $parallelArgs = @("-n", "$Workers", "--dist", "loadfile")
}
elseif ($Parallel) {
    $parallelArgs = @("-n", "auto", "--dist", "loadfile")
}

if ($Workers -gt 8) {
    Write-Host "NOTE: $Workers workers - each gets its own database (auto-created)." -ForegroundColor DarkGray
    Write-Host "      Very high counts may exhaust PostgreSQL connection limits." -ForegroundColor DarkGray
    Write-Host ""
}

Write-Host "Erasing previous coverage data..." -ForegroundColor Cyan
python -m coverage erase

$pytestArgs = @(
    "--cov=app",
    "--cov-report=term-missing",
    "--cov-report=html:htmlcov",
    "--cov-report=xml:coverage.xml"
) + $parallelArgs + $ExtraArgs

Write-Host "Running full coverage suite..." -ForegroundColor Cyan
Write-Host "Command: python -m pytest $($pytestArgs -join ' ')" -ForegroundColor DarkGray
if ($parallelArgs.Count -gt 0) {
    Write-Host "Tip: first tests are slow (Flask boot + full DB schema rebuild per test)." -ForegroundColor DarkGray
    Write-Host "     Live progress: Get-Content test_results.log -Wait -Tail 5" -ForegroundColor DarkGray
}
python -m pytest @pytestArgs
$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host "Coverage: htmlcov\index.html and coverage.xml" -ForegroundColor Green
}
else {
    Write-Host "Tests finished with exit code $exitCode" -ForegroundColor Red
}

exit $exitCode
