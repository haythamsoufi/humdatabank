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

# Called bare (not `$exitCode = ...`) so the remote command's output reaches the real
# console instead of being captured. See Use-AzureWebAppTunnel for why.
Use-AzureWebAppTunnel `
    -WebApp $WebApp `
    -ResourceGroup $ResourceGroup `
    -Port $Port `
    -Label $Label `
    -LogPrefix 'azure_webapp_run' `
    -Action {
        param($Ctx)
        Invoke-AzureWebAppSshCommand -LocalPort $Ctx.Port -RemoteCommand $Command
    }

exit $LASTEXITCODE
