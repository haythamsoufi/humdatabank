# Full-suite coverage run (fresh .coverage + HTML + XML).
# Usage: .\tests\run_full_coverage.ps1 [-Parallel] [-Workers <n>]

param(
    [switch]$Parallel,
    [int]$Workers = 0,
    [string[]]$ExtraArgs = @()
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "Import-BackofficeEnv.ps1")

$env:FLASK_CONFIG = "testing"

if (-not $env:TEST_DATABASE_URL -and -not $env:DATABASE_URL) {
    Write-Host "WARNING: TEST_DATABASE_URL or DATABASE_URL not set (check Backoffice\.env)." -ForegroundColor Yellow
}

$parallelArgs = @()
if ($Parallel) {
    if ($Workers -gt 0) {
        $parallelArgs = @("-n", "$Workers")
    } else {
        $parallelArgs = @("-n", "auto")
    }
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
python -m pytest @pytestArgs
$exitCode = $LASTEXITCODE

if ($exitCode -eq 0) {
    Write-Host "Coverage: htmlcov\index.html and coverage.xml" -ForegroundColor Green
} else {
    Write-Host "Tests finished with exit code $exitCode" -ForegroundColor Red
}

exit $exitCode
