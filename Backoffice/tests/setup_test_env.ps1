# Quick setup script for test environment
# Usage: . .\setup_test_env.ps1

Write-Host "Setting up test environment..." -ForegroundColor Cyan
Write-Host ""

# Set test database URL (adjust credentials as needed)
if (-not $env:TEST_DATABASE_URL) {
    $env:TEST_DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/test_db"
    Write-Host "Set TEST_DATABASE_URL" -ForegroundColor Green
} else {
    Write-Host "TEST_DATABASE_URL already set" -ForegroundColor Yellow
}

# Set Flask config
if (-not $env:FLASK_CONFIG) {
    $env:FLASK_CONFIG = "testing"
    Write-Host "Set FLASK_CONFIG=testing" -ForegroundColor Green
} else {
    Write-Host "FLASK_CONFIG already set: $env:FLASK_CONFIG" -ForegroundColor Yellow
}

# Set secret key for testing
if (-not $env:SECRET_KEY) {
    $env:SECRET_KEY = "test-secret-key"
    Write-Host "Set SECRET_KEY" -ForegroundColor Green
}

# Disable CSRF for testing
$env:WTF_CSRF_ENABLED = "false"

Write-Host ""
Write-Host "Test environment configured!" -ForegroundColor Green
Write-Host ""
Write-Host "Current settings:" -ForegroundColor Cyan
Write-Host "  TEST_DATABASE_URL: $env:TEST_DATABASE_URL" -ForegroundColor White
Write-Host "  FLASK_CONFIG: $env:FLASK_CONFIG" -ForegroundColor White
Write-Host "  SECRET_KEY: $env:SECRET_KEY" -ForegroundColor White
Write-Host ""
Write-Host "To create the test database, run:" -ForegroundColor Yellow
Write-Host "  psql -U postgres -c 'CREATE DATABASE test_db;'" -ForegroundColor White
Write-Host ""
Write-Host "Run tests with:" -ForegroundColor Yellow
Write-Host "  python -m pytest -v" -ForegroundColor White
Write-Host ""
