# PowerShell script to run tests with proper environment setup
# Usage: .\tests\run_tests.ps1

Write-Host "Setting up test environment..." -ForegroundColor Cyan

# Check if TEST_DATABASE_URL is set
if (-not $env:TEST_DATABASE_URL -and -not $env:DATABASE_URL) {
    Write-Host "WARNING: TEST_DATABASE_URL or DATABASE_URL not set!" -ForegroundColor Yellow
    Write-Host "Tests may fail without a database connection." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Set it with:" -ForegroundColor Yellow
    Write-Host '  $env:TEST_DATABASE_URL="postgresql://user:pass@localhost/test_db"' -ForegroundColor Yellow
    Write-Host ""
}

# Set Flask config if not set
if (-not $env:FLASK_CONFIG) {
    $env:FLASK_CONFIG = "testing"
    Write-Host "Set FLASK_CONFIG=testing" -ForegroundColor Green
}

# Run tests with verbose output and show first error details
Write-Host "Running tests..." -ForegroundColor Cyan
Write-Host ""

python -m pytest -v --tb=short -x
