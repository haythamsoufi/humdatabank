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

        # OpenSSH's ssh.exe is used first: unlike plink 0.82+, it correctly handles
        # interactive password auth under ConPTY-based terminals (Windows Terminal,
        # VS Code/Cursor's integrated terminal), where plink can hang right after
        # "Using username" because it tries to write auth prompts directly to the
        # console object instead of through stdio. See Invoke-AzureWebAppOpenSshSession.
        if (Get-Command ssh -ErrorAction SilentlyContinue) {
            Write-Host 'Opening SSH session via OpenSSH (handshake can take a few seconds -- please wait for the login banner)...'
            $rc = Invoke-AzureWebAppOpenSshSession -LocalPort $Ctx.Port
            if ($rc -eq 0) { return 0 }
            if (-not (Test-AzureWebAppTunnelAlive -Job $Ctx.TunnelJob -LocalPort $Ctx.Port)) {
                Write-Host 'ERROR: Tunnel closed during OpenSSH attempt.'
                return 1
            }
            Write-Host 'OpenSSH attempt failed; falling back to plink...'
        }

        foreach ($hostKey in $Ctx.HostKeys) {
            if (-not (Test-AzureWebAppTunnelAlive -Job $Ctx.TunnelJob -LocalPort $Ctx.Port)) {
                Write-Host 'ERROR: Tunnel closed during host key discovery.'
                return 1
            }
            Write-Host 'Opening SSH session via plink (handshake can take a few seconds -- please wait for the login banner)...'
            & $Ctx.PlinkPath -batch -legacy-stdio-prompts -hostkey $hostKey -t -ssh 'root@127.0.0.1' -P $Ctx.Port -pw $Ctx.Password
            if ($LASTEXITCODE -eq 0) { return 0 }
        }
        return 1
    }

if ($exitCode -ne 0) {
    Write-Host ""
    Write-Host 'SSH login failed.'
    Write-Host 'Browser WebSSH (no password): Azure Portal -> Development Tools -> SSH'
}

exit $exitCode
