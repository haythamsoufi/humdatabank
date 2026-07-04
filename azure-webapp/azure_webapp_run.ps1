param(
    [Parameter(Mandatory = $true)][string]$WebApp,
    [Parameter(Mandatory = $true)][string]$ResourceGroup,
    [Parameter(Mandatory = $true)][int]$Port,
    [Parameter(Mandatory = $true)][string]$Label,
    [Parameter(Mandatory = $true)][string]$Command
)

. (Join-Path $PSScriptRoot 'azure_webapp_ssh_lib.ps1')

Write-Host ""
Write-Host "$Label remote command via tunnel on port $Port"
Write-Host "Command: $Command"
Write-Host ""

$exitCode = Use-AzureWebAppTunnel `
    -WebApp $WebApp `
    -ResourceGroup $ResourceGroup `
    -Port $Port `
    -Label $Label `
    -LogPrefix 'azure_webapp_run' `
    -Action {
        param($Ctx)
        return Invoke-AzureWebAppPlinkCommand `
            -PlinkPath $Ctx.PlinkPath `
            -LocalPort $Ctx.Port `
            -HostKey $Ctx.HostKey `
            -RemoteCommand $Command
    }

exit $exitCode
