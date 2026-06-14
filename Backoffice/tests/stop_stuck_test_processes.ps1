# Stop leftover pytest / xdist worker processes that hold PostgreSQL locks.
# Usage: .\tests\stop_stuck_test_processes.ps1

$current = $PID
$targets = Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'py.exe'" |
    Where-Object {
        $_.ProcessId -ne $current -and
        $_.CommandLine -match 'pytest|xdist|gw\d|run_full_coverage'
    }

if (-not $targets) {
    Write-Host "No stuck pytest/python test processes found." -ForegroundColor Green
    exit 0
}

Write-Host "Stopping $($targets.Count) stuck test process(es)..." -ForegroundColor Yellow
foreach ($proc in $targets) {
    Write-Host "  PID $($proc.ProcessId): $($proc.CommandLine)"
    Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
}

Write-Host "Done. Retry your test run." -ForegroundColor Green
