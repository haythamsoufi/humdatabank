param(
    [string]$Environment = 'PROD',
    [string]$RemotePath = '/tmp/email_failure_investigation.txt',
    [string]$LocalPath = 'c:\Humanitarian Databank\email_failure_investigation.txt'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'azure_webapp_config.ps1')
. (Join-Path $PSScriptRoot 'azure_webapp_ssh_lib.ps1')

$target = Resolve-AzureWebAppEnvironment -Name $Environment

# Called bare (not `$exitCode = ...`) so the downloaded file's contents print to the
# real console instead of being captured. See Use-AzureWebAppTunnel for why.
Use-AzureWebAppTunnel `
    -WebApp $target.WebApp `
    -ResourceGroup $target.ResourceGroup `
    -Port $target.Port `
    -Label $target.Label `
    -LogPrefix 'azure_webapp_download' `
    -Action {
        param($Ctx)
        if (Test-Path $LocalPath) { Remove-Item $LocalPath -Force }
        Receive-AzureWebAppRemoteFile -RemotePath $RemotePath -LocalPath $LocalPath -LocalPort $Ctx.Port
        Write-Host "Downloaded to $LocalPath"
        if (Test-Path $LocalPath) { Get-Content $LocalPath }
    }

exit $LASTEXITCODE
