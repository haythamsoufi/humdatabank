# Load Backoffice/.env into the current PowerShell session (override=False).
# Usage: . .\tests\Import-BackofficeEnv.ps1

$loader = Join-Path $PSScriptRoot "load_backoffice_env.py"
if (-not (Test-Path $loader)) {
    return
}

$json = & python $loader --emit-json 2>$null
if (-not $json) {
    return
}

($json | ConvertFrom-Json).PSObject.Properties | ForEach-Object {
    Set-Item -Path "env:$($_.Name)" -Value $_.Value
}
