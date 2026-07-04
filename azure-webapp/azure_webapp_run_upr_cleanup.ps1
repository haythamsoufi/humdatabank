<#
.SYNOPSIS
    Thin wrapper: UPR false Yes/No cleanup via azure_webapp_run_script.ps1
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('PROD', 'STAGING')]
    [string]$Environment,

    [Parameter(Mandatory = $true)]
    [string]$InputXlsx,

    [switch]$Force,
    [switch]$DryRun,
    [string]$Since = '2026-06-28',
    [string]$Period = ''
)

$ErrorActionPreference = 'Stop'
$runner = Join-Path $PSScriptRoot 'azure_webapp_run_script.ps1'
if (-not (Test-Path $InputXlsx)) {
    Write-Error "UPR Master not found: $InputXlsx"
}

$remoteXlsx = '/tmp/upr_master_cleanup.xlsx'
$runnerArgs = @(
    '-Environment', $Environment,
    '-Script', 'cleanup_upr_false_yes_no_defaults.py',
    '-Upload', "${InputXlsx}=${remoteXlsx}",
    '-RemoteArgs', "--input $remoteXlsx --since $Since $(if ($Force) { '--force' } else { '--dry-run' })$(if ($Period) { " --period `"$Period`"" } else { '' })"
)

& $runner @runnerArgs

exit $LASTEXITCODE
