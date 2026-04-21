# LibreTranslate Setup Script for Windows
# This script helps you set up and manage LibreTranslate using Docker

param(
    [string]$Action = "start"
)

Write-Host "LibreTranslate Docker Setup Script" -ForegroundColor Green
Write-Host "=================================" -ForegroundColor Green

switch ($Action.ToLower()) {
    "start" {
        Write-Host "Starting LibreTranslate..." -ForegroundColor Yellow

        # Check if Docker is running
        try {
            docker info | Out-Null
            Write-Host "✓ Docker is running" -ForegroundColor Green
        }
        catch {
            Write-Host "✗ Docker is not running. Please start Docker Desktop first." -ForegroundColor Red
            exit 1
        }

        # Start LibreTranslate
        Write-Host "Starting LibreTranslate container..." -ForegroundColor Yellow
        docker-compose up -d

        Write-Host "✓ LibreTranslate is starting..." -ForegroundColor Green
        Write-Host "The service will be available at: http://localhost:5000" -ForegroundColor Cyan
        Write-Host "First startup may take 10-30 minutes to download language models." -ForegroundColor Yellow
        Write-Host "You can check progress with: docker-compose logs -f" -ForegroundColor Cyan
    }

    "stop" {
        Write-Host "Stopping LibreTranslate..." -ForegroundColor Yellow
        docker-compose down
        Write-Host "✓ LibreTranslate stopped" -ForegroundColor Green
    }

    "restart" {
        Write-Host "Restarting LibreTranslate..." -ForegroundColor Yellow
        docker-compose restart
        Write-Host "✓ LibreTranslate restarted" -ForegroundColor Green
    }

    "logs" {
        Write-Host "Showing LibreTranslate logs..." -ForegroundColor Yellow
        docker-compose logs -f
    }

    "status" {
        Write-Host "Checking LibreTranslate status..." -ForegroundColor Yellow
        docker-compose ps
    }

    "test" {
        Write-Host "Testing LibreTranslate connection..." -ForegroundColor Yellow
        try {
            $response = Invoke-RestMethod -Uri "http://localhost:5000/translate" -Method POST -ContentType "application/json" -Body '{"q":"Hello world","source":"en","target":"fr"}' -TimeoutSec 10
            Write-Host "✓ LibreTranslate is working!" -ForegroundColor Green
            Write-Host "Translation: $($response.translatedText)" -ForegroundColor Cyan
        }
        catch {
            Write-Host "✗ LibreTranslate is not responding. It may still be starting up." -ForegroundColor Red
            Write-Host "Check logs with: .\setup_libretranslate.ps1 logs" -ForegroundColor Yellow
        }
    }

    default {
        Write-Host "Usage: .\setup_libretranslate.ps1 [action]" -ForegroundColor Yellow
        Write-Host "Actions:" -ForegroundColor Cyan
        Write-Host "  start   - Start LibreTranslate" -ForegroundColor White
        Write-Host "  stop    - Stop LibreTranslate" -ForegroundColor White
        Write-Host "  restart - Restart LibreTranslate" -ForegroundColor White
        Write-Host "  logs    - Show logs" -ForegroundColor White
        Write-Host "  status  - Show status" -ForegroundColor White
        Write-Host "  test    - Test connection" -ForegroundColor White
    }
}
