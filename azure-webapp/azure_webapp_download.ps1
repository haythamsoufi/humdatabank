param(
    [string]$Environment = 'PROD',
    [string]$RemotePath = '/tmp/email_failure_investigation.txt',
    [string]$LocalPath = 'c:\Humanitarian Databank\email_failure_investigation.txt'
)

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'azure_webapp_config.ps1')
. (Join-Path $PSScriptRoot 'azure_webapp_ssh_lib.ps1')

$target = Resolve-AzureWebAppEnvironment -Name $Environment

Use-AzureWebAppTunnel `
    -WebApp $target.WebApp `
    -ResourceGroup $target.ResourceGroup `
    -Port $target.Port `
    -Label $target.Label `
    -LogPrefix 'azure_webapp_download' `
    -Action {
        param($Ctx)
        $pscp = $Ctx.PscpPath
        if (-not $pscp) { throw 'pscp not found' }
        if (Test-Path $LocalPath) { Remove-Item $LocalPath -Force }
        & $pscp -batch -hostkey $Ctx.HostKey -P $Ctx.Port -pw $Ctx.Password "root@127.0.0.1:$RemotePath" $LocalPath
        if ($LASTEXITCODE -ne 0) { throw "pscp download failed ($LASTEXITCODE)" }
        Write-Host "Downloaded to $LocalPath"
        if (Test-Path $LocalPath) { Get-Content $LocalPath }
        return 0
    }
