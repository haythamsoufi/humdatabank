param(
    [Parameter(Mandatory = $true)][string]$WebApp,
    [Parameter(Mandatory = $true)][string]$ResourceGroup,
    [Parameter(Mandatory = $true)][int]$Port,
    [Parameter(Mandatory = $true)][string]$Label
)

. (Join-Path $PSScriptRoot 'azure_webapp_ssh_lib.ps1')

Write-Host ""
Write-Host "$Label terminal SSH via local tunnel on port $Port."
Write-Host ""

# Called bare (not `$exitCode = ...`) so the interactive session's live I/O reaches the
# real console instead of being captured. See Use-AzureWebAppTunnel for why.
Use-AzureWebAppTunnel `
    -WebApp $WebApp `
    -ResourceGroup $ResourceGroup `
    -Port $Port `
    -Label $Label `
    -LogPrefix 'azure_webapp_ssh' `
    -Action {
        param($Ctx)
        Write-Host 'Opening SSH session (handshake can take a few seconds -- please wait for the login banner)...'
        Invoke-AzureWebAppSshInteractive -LocalPort $Ctx.Port
    }

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host 'SSH login failed.'
    Write-Host 'Browser WebSSH (no password): Azure Portal -> Development Tools -> SSH'
}

exit $LASTEXITCODE
