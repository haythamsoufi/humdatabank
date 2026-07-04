<#
.SYNOPSIS
    Upload and run a Backoffice Python script on an Azure App Service container via SSH tunnel.

.DESCRIPTION
    Resolves scripts under Backoffice/scripts/, optionally uploads local files, then runs:
      cd /app && PYTHONPATH=/app/scripts FLASK_CONFIG=<env> python <remote-script> <args>

.EXAMPLE
    # Dry-run UPR Yes/No cleanup on PROD
    .\azure-webapp\azure_webapp_run_script.ps1 -Environment PROD `
        -Script cleanup_upr_false_yes_no_defaults.py `
        -Upload "C:\data\UPR Master.xlsx=/tmp/upr_master.xlsx" `
        -RemoteArgs '--input /tmp/upr_master.xlsx --dry-run --since 2026-06-28'

.EXAMPLE
    # Run a script already deployed in the container image
    .\azure-webapp\azure_webapp_run_script.ps1 -Environment PROD `
        -Script backfill_stable_keys.py -UseDeployedScript `
        -RemoteArgs '--dry-run'

.EXAMPLE
    # Arbitrary remote shell command (no script upload)
    .\azure_webapp_tools.bat prod run "cd /app && python scripts/backfill_stable_keys.py --dry-run"
#>
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('PROD', 'STAGING')]
    [string]$Environment,

    [Parameter(Mandatory = $true, Position = 0)]
    [string]$Script,

    [string[]]$Upload = @(),

    [ValidateSet('production', 'development', 'testing')]
    [string]$FlaskConfig = 'production',

    [switch]$UseDeployedScript,

    [string]$RemoteArgs = ''
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'azure_webapp_config.ps1')
. (Join-Path $PSScriptRoot 'azure_webapp_ssh_lib.ps1')

$target = Resolve-AzureWebAppEnvironment -Name $Environment
$backoffice = Get-AzureWebAppBackofficeRoot

function Resolve-LocalScriptPath {
    param([string]$ScriptPath)
    if ([System.IO.Path]::IsPathRooted($ScriptPath)) {
        return $ScriptPath
    }
    $normalized = $ScriptPath -replace '\\', '/'
    if ($normalized -match '^scripts/(.+)$') {
        $normalized = $Matches[1]
    }
    $candidate = Join-Path (Join-Path $backoffice 'scripts') $normalized
    if (-not (Test-Path $candidate)) {
        throw "Script not found: $ScriptPath (looked for $candidate)"
    }
    return (Resolve-Path $candidate).Path
}

function Parse-UploadSpec {
    param([string]$Spec)
    if ($Spec -notmatch '^(.+)=(.+)$') {
        throw "Invalid -Upload value '$Spec'. Use localPath=remotePath"
    }
    return [PSCustomObject]@{
        Local  = $Matches[1].Trim()
        Remote = $Matches[2].Trim()
    }
}

$localScript = Resolve-LocalScriptPath -ScriptPath $Script
$scriptBaseName = [System.IO.Path]::GetFileName($localScript)
$remoteScript = if ($UseDeployedScript) { "/app/scripts/$scriptBaseName" } else { "/tmp/$scriptBaseName" }

$uploadPairs = @()
foreach ($spec in $Upload) {
    if ($spec) { $uploadPairs += Parse-UploadSpec -Spec $spec }
}

$remoteCmd = "cd /app && PYTHONPATH=/app/scripts FLASK_CONFIG=$FlaskConfig python $remoteScript"
if ($RemoteArgs.Trim()) { $remoteCmd += " $RemoteArgs" }

$useDeployed = [bool]$UseDeployedScript
$uploadList = @($uploadPairs)
$localScriptPath = $localScript
$remoteScriptPath = $remoteScript

Write-Host ""
Write-Host "=== $($target.Label) run script ==="
Write-Host "Local script : $localScript"
Write-Host "Remote script: $remoteScript"
if ($uploadPairs.Count -gt 0) {
    Write-Host "Uploads      : $($uploadPairs.Count) file(s)"
}
Write-Host "Command      : $remoteCmd"
Write-Host ""

$exitCode = Use-AzureWebAppTunnel `
    -WebApp $target.WebApp `
    -ResourceGroup $target.ResourceGroup `
    -Port $target.Port `
    -Label $target.Label `
    -LogPrefix 'azure_webapp_run_script' `
    -Action {
        param($Ctx)

        if (-not $useDeployed) {
            Write-Host "Uploading $scriptBaseName..."
            Send-AzureWebAppRemoteFile `
                -LocalPath $localScriptPath `
                -RemotePath $remoteScriptPath `
                -PlinkPath $Ctx.PlinkPath `
                -PscpPath $Ctx.PscpPath `
                -LocalPort $Ctx.Port `
                -HostKey $Ctx.HostKey
        }

        foreach ($pair in $uploadList) {
            Write-Host "Uploading $($pair.Local) -> $($pair.Remote)..."
            Send-AzureWebAppRemoteFile `
                -LocalPath $pair.Local `
                -RemotePath $pair.Remote `
                -PlinkPath $Ctx.PlinkPath `
                -PscpPath $Ctx.PscpPath `
                -LocalPort $Ctx.Port `
                -HostKey $Ctx.HostKey
        }

        Write-Host "Running on container..."
        return Invoke-AzureWebAppPlinkCommand `
            -PlinkPath $Ctx.PlinkPath `
            -LocalPort $Ctx.Port `
            -HostKey $Ctx.HostKey `
            -RemoteCommand $remoteCmd
    }

exit $exitCode
