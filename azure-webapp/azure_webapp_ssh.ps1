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

$exitCode = Use-AzureWebAppTunnel `
    -WebApp $WebApp `
    -ResourceGroup $ResourceGroup `
    -Port $Port `
    -Label $Label `
    -LogPrefix 'azure_webapp_ssh' `
    -Action {
        param($Ctx)

        foreach ($hostKey in $Ctx.HostKeys) {
            if (-not (Test-AzureWebAppTunnelAlive -Job $Ctx.TunnelJob -LocalPort $Ctx.Port)) {
                Write-Host 'ERROR: Tunnel closed during host key discovery.'
                return 1
            }
            Write-Host 'Opening SSH session...'
            & $Ctx.PlinkPath -batch -hostkey $hostKey -t -ssh 'root@127.0.0.1' -P $Ctx.Port -pw $Ctx.Password
            if ($LASTEXITCODE -eq 0) { return 0 }
        }

        if (Test-AzureWebAppTunnelAlive -Job $Ctx.TunnelJob -LocalPort $Ctx.Port) {
            Write-Host 'Retrying with OpenSSH client...'
            return Invoke-AzureWebAppOpenSshSession -LocalPort $Ctx.Port
        }
        return 1
    }

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host 'SSH login failed.'
    Write-Host 'Browser WebSSH (no password): Azure Portal -> Development Tools -> SSH'
}

exit $exitCode
