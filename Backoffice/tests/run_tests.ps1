# Fast default test run (no coverage, parallel when xdist is installed).
# Usage:
#   .\tests\run_tests.ps1
#   .\tests\run_tests.ps1 -Coverage -Append
#   .\tests\run_tests.ps1 -Marker unit -NoParallel
#   .\tests\run_tests.ps1 -Path tests\unit\test_middleware\test_api_tracker.py

param(
    [string]$Path = "tests",
    [string]$Marker = "",
    [switch]$Coverage,
    [switch]$Append,
    [switch]$EraseCoverage,
    [switch]$NoParallel,
    [switch]$FailFast,
    [switch]$Durations,
    [int]$Workers = 0
)

. (Join-Path $PSScriptRoot "Import-BackofficeEnv.ps1")

$env:FLASK_CONFIG = "testing"

if ($env:TEST_DATABASE_URL) {
    Write-Host "Database: TEST_DATABASE_URL loaded." -ForegroundColor DarkGray
} elseif ($env:DATABASE_URL) {
    Write-Host "Database: DATABASE_URL loaded." -ForegroundColor DarkGray
} elseif (Test-Path (Join-Path $PSScriptRoot "..\.env")) {
    Write-Host "WARNING: Backoffice\.env exists but TEST_DATABASE_URL / DATABASE_URL not found." -ForegroundColor Yellow
} else {
    Write-Host "WARNING: No Backoffice\.env and no database URL in environment." -ForegroundColor Yellow
}

$args = @($Path)

if ($Marker) {
    $args += @("-m", $Marker)
}

if ($Coverage) {
    if ($EraseCoverage) {
        Write-Host "Erasing previous coverage data..." -ForegroundColor Cyan
        python -m coverage erase
    }
    $args += @("--cov=app", "--cov-report=term-missing", "--cov-report=html:htmlcov")
    if ($Append) {
        $args += "--cov-append"
    } else {
        $args += "--cov-report=xml:coverage.xml"
    }
} else {
    $args += "--no-cov"
}

if (-not $NoParallel) {
    if ($Workers -gt 0) {
        $args += @("-n", "$Workers")
    } else {
        $args += @("-n", "auto")
    }
}

if ($FailFast) { $args += "-x" }
if ($Durations) { $args += "--durations=20" }

Write-Host "Running: python -m pytest $($args -join ' ')" -ForegroundColor Cyan
python -m pytest @args
exit $LASTEXITCODE
