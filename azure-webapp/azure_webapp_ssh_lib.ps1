# Shared SSH tunnel helpers for Azure App Service containers.
# Dot-source from azure_webapp_ssh.ps1, azure_webapp_run.ps1, azure_webapp_run_script.ps1,
# azure_webapp_download.ps1
#
# Connects over the tunnel opened by `az webapp create-remote-connection` using the OpenSSH
# client that ships with Windows 10/11 (ssh.exe / scp.exe under System32\OpenSSH) -- the same
# client Microsoft's own docs use for this feature:
# https://learn.microsoft.com/en-us/azure/app-service/configure-linux-open-ssh-session
#
# Host key checking is disabled (-o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=NUL)
# because every session gets a fresh local port; there is no prior host key to pin trust to,
# and the container's SSH password ("Docker!") is the same publicly-documented value for every
# Linux App Service container, so there's nothing meaningful to verify against.
#
# This previously shelled out to PuTTY's plink for password automation, but plink writes
# prompts and host-key confirmations directly to the Win32 console instead of through
# stdio/stderr. Under ConPTY-based terminals (Windows Terminal, VS Code/Cursor) and whenever
# its output is captured or piped, that write blocks for 30-90+ seconds (sometimes
# indefinitely) instead of returning -- which made every operation in this file painfully slow
# or made it look completely hung. OpenSSH doesn't have this problem, so it's the only
# supported client now.

$script:AzureWebAppSshPassword = 'Docker!'

function Stop-AzureWebAppTunnelPort {
    param([int]$LocalPort)
    try {
        Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue |
            ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
    } catch {
        netstat -ano | Select-String ":$LocalPort\s" | Select-String 'LISTENING' | ForEach-Object {
            $procId = ($_ -split '\s+')[-1]
            if ($procId -match '^\d+$') { Stop-Process -Id ([int]$procId) -Force -ErrorAction SilentlyContinue }
        }
    }
}

function Test-AzureWebAppPortListening {
    param([int]$LocalPort)
    try {
        return [bool](Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue)
    } catch {
        return [bool](netstat -ano | Select-String ":$LocalPort\s" | Select-String 'LISTENING')
    }
}

function Get-AzureWebAppExcludedPortRanges {
    # Windows (Hyper-V/WSL NAT) periodically reserves TCP port ranges that cannot be bound
    # by user-mode sockets, even though nothing shows as "listening" on them. Binding one of
    # these ports fails with WinError 10013 ("access forbidden by its access permissions").
    $ranges = @()
    try {
        $lines = netsh interface ipv4 show excludedportrange protocol=tcp 2>$null
        foreach ($line in $lines) {
            if ($line -match '^\s*(\d+)\s+(\d+)') {
                $ranges += [PSCustomObject]@{ Start = [int]$Matches[1]; End = [int]$Matches[2] }
            }
        }
    } catch {
        # netsh unavailable; fall through with no known exclusions.
    }
    return $ranges
}

function Test-AzureWebAppPortExcluded {
    param([int]$Port, [array]$ExcludedRanges)
    foreach ($range in $ExcludedRanges) {
        if ($Port -ge $range.Start -and $Port -le $range.End) { return $true }
    }
    return $false
}

function Get-AzureWebAppAvailableLocalPort {
    param(
        [Parameter(Mandatory = $true)][int]$PreferredPort,
        [int]$MaxAttempts = 500
    )
    $excluded = Get-AzureWebAppExcludedPortRanges
    for ($i = 0; $i -lt $MaxAttempts; $i++) {
        $candidate = $PreferredPort + $i
        if ($candidate -gt 65535) { break }
        if (Test-AzureWebAppPortExcluded -Port $candidate -ExcludedRanges $excluded) { continue }
        if (Test-AzureWebAppPortListening -LocalPort $candidate) { continue }
        return $candidate
    }
    throw "Could not find an available, non-Windows-reserved local port starting from $PreferredPort."
}

function Start-AzureWebAppTunnelJob {
    param(
        [string]$WebAppName,
        [string]$ResourceGroupName,
        [int]$LocalPort,
        [string]$LogPath
    )
    if (Test-Path $LogPath) { Remove-Item $LogPath -Force -ErrorAction SilentlyContinue }
    $azPath = (Get-Command az).Source
    return Start-Job -Name "AzureWebAppTunnel_$LocalPort" -ScriptBlock {
        param($AzPath, $WebAppName, $ResourceGroupName, $LocalPort, $LogPath)
        $ErrorActionPreference = 'Continue'
        & $AzPath webapp create-remote-connection `
            --name $WebAppName `
            --resource-group $ResourceGroupName `
            --port $LocalPort `
            --timeout 300 *>> $LogPath
    } -ArgumentList $azPath, $WebAppName, $ResourceGroupName, $LocalPort, $LogPath
}

function Wait-AzureWebAppTunnelReady {
    param(
        $Job,
        [string]$LogPath,
        [int]$LocalPort,
        [int]$TimeoutSec = 90
    )
    for ($elapsed = 0; $elapsed -lt $TimeoutSec; $elapsed += 2) {
        if ($Job.State -eq 'Failed' -or $Job.State -eq 'Completed') { return $false }
        $logText = if (Test-Path $LogPath) { Get-Content $LogPath -Raw -ErrorAction SilentlyContinue } else { '' }
        $logReady = $logText -match 'Opening tunnel on port|Tunnels are ready|SSH is available'
        if ($logReady -and (Test-AzureWebAppPortListening -LocalPort $LocalPort)) { return $true }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Stop-AzureWebAppTunnelJob {
    param($Job, [int]$LocalPort)
    if ($Job) {
        Stop-Job $Job -ErrorAction SilentlyContinue
        Remove-Job $Job -Force -ErrorAction SilentlyContinue
    }
    Stop-AzureWebAppTunnelPort -LocalPort $LocalPort
}

function Test-AzureWebAppTunnelAlive {
    param($Job, [int]$LocalPort)
    if (-not $Job -or $Job.State -eq 'Failed' -or $Job.State -eq 'Completed') { return $false }
    return (Test-AzureWebAppPortListening -LocalPort $LocalPort)
}

function Show-AzureWebAppTunnelDiagnostics {
    param([string]$LogPath, $Job)
    Write-Host ""
    Write-Host "Tunnel diagnostics:"
    if ($Job) { Write-Host "  Job state: $($Job.State)" }
    $logText = ''
    if (Test-Path $LogPath) {
        $logText = (Get-Content $LogPath -Raw -ErrorAction SilentlyContinue)
        Write-Host ""
        Write-Host "Tunnel output:"
        if ([string]::IsNullOrWhiteSpace($logText)) {
            Write-Host "  (log file is empty)"
        } else {
            Write-Host $logText
        }
    } else {
        Write-Host "  (no tunnel log at $LogPath)"
    }
    if ($logText -match 'WinError 10013') {
        Write-Host ""
        Write-Host "Hint: WinError 10013 means Windows refused the local socket bind for this port," -ForegroundColor Yellow
        Write-Host "usually because it falls in a Hyper-V/WSL port-exclusion range. Run:" -ForegroundColor Yellow
        Write-Host "  netsh interface ipv4 show excludedportrange protocol=tcp" -ForegroundColor Yellow
        Write-Host "and re-run; the tooling should now auto-pick a free port, but if this persists" -ForegroundColor Yellow
        Write-Host "try rebooting (Windows reshuffles these ranges on restart) or edit the Port in" -ForegroundColor Yellow
        Write-Host "azure_webapp_config.ps1." -ForegroundColor Yellow
    }
}

function Get-AzureWebAppSshOptions {
    # Shared -o options for both ssh and scp. Note: ssh's port flag is -p, scp's is -P;
    # callers add that themselves so this list stays usable by both.
    return @(
        '-o', 'StrictHostKeyChecking=accept-new',
        '-o', 'UserKnownHostsFile=NUL',
        '-o', 'PubkeyAuthentication=no',
        '-o', 'PreferredAuthentications=password',
        '-o', 'MACs=hmac-sha1,hmac-sha1-96',
        '-o', 'ConnectTimeout=20'
    )
}

function Invoke-AzureWebAppWithAskPass {
    # Wraps a scriptblock with SSH_ASKPASS so ssh/scp authenticate non-interactively
    # instead of prompting on a tty. SSH_ASKPASS_REQUIRE=force (OpenSSH 8.4+) makes this
    # work even when a real console is attached, which is always true here.
    #
    # IMPORTANT: this must be called *bare* (no `$x = ...`, no `| ...`) by every caller,
    # all the way up to the top-level script. Capturing a PowerShell function's output
    # anywhere in the call chain forces PowerShell to redirect every native command's
    # stdout underneath it (ssh/scp included) into that capture instead of the real
    # console -- silently discarding output instead of streaming it live. Exit codes are
    # read from $LASTEXITCODE by the caller instead, since that side-channel isn't
    # subject to this capturing.
    param(
        [Parameter(Mandatory = $true)][scriptblock]$ScriptBlock,
        [string]$Password = $script:AzureWebAppSshPassword
    )
    $askPassCmd = Join-Path $env:TEMP "azure_ssh_askpass_$PID.cmd"
    @('@echo off', "echo $Password") | Set-Content -Path $askPassCmd -Encoding ASCII
    $prevAskPass = $env:SSH_ASKPASS
    $prevAskPassRequire = $env:SSH_ASKPASS_REQUIRE
    $prevDisplay = $env:DISPLAY
    $env:SSH_ASKPASS = $askPassCmd
    $env:SSH_ASKPASS_REQUIRE = 'force'
    $env:DISPLAY = '1'
    try {
        & $ScriptBlock
    } finally {
        if ($null -ne $prevAskPass) { $env:SSH_ASKPASS = $prevAskPass } else { Remove-Item Env:SSH_ASKPASS -ErrorAction SilentlyContinue }
        if ($null -ne $prevAskPassRequire) { $env:SSH_ASKPASS_REQUIRE = $prevAskPassRequire } else { Remove-Item Env:SSH_ASKPASS_REQUIRE -ErrorAction SilentlyContinue }
        if ($null -ne $prevDisplay) { $env:DISPLAY = $prevDisplay } else { Remove-Item Env:DISPLAY -ErrorAction SilentlyContinue }
        Remove-Item $askPassCmd -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-AzureWebAppSshInteractive {
    # Call bare; check $LASTEXITCODE afterwards. See Invoke-AzureWebAppWithAskPass.
    param([Parameter(Mandatory = $true)][int]$LocalPort)
    Invoke-AzureWebAppWithAskPass -ScriptBlock {
        & ssh @(Get-AzureWebAppSshOptions) -p $LocalPort 'root@127.0.0.1'
    }
}

function Invoke-AzureWebAppSshCommand {
    # Call bare; check $LASTEXITCODE afterwards. See Invoke-AzureWebAppWithAskPass.
    param(
        [Parameter(Mandatory = $true)][int]$LocalPort,
        [Parameter(Mandatory = $true)][string]$RemoteCommand
    )
    Invoke-AzureWebAppWithAskPass -ScriptBlock {
        & ssh @(Get-AzureWebAppSshOptions) -p $LocalPort 'root@127.0.0.1' $RemoteCommand
    }
}

function Send-AzureWebAppRemoteFile {
    param(
        [Parameter(Mandatory = $true)][string]$LocalPath,
        [Parameter(Mandatory = $true)][string]$RemotePath,
        [Parameter(Mandatory = $true)][int]$LocalPort
    )
    if (-not (Test-Path $LocalPath)) {
        throw "Local file not found: $LocalPath"
    }
    Invoke-AzureWebAppWithAskPass -ScriptBlock {
        & scp @(Get-AzureWebAppSshOptions) -P $LocalPort $LocalPath "root@127.0.0.1:$RemotePath"
    }
    if ($LASTEXITCODE -ne 0) { throw "Upload failed for $LocalPath (scp exit $LASTEXITCODE)" }
}

function Receive-AzureWebAppRemoteFile {
    param(
        [Parameter(Mandatory = $true)][string]$RemotePath,
        [Parameter(Mandatory = $true)][string]$LocalPath,
        [Parameter(Mandatory = $true)][int]$LocalPort
    )
    Invoke-AzureWebAppWithAskPass -ScriptBlock {
        & scp @(Get-AzureWebAppSshOptions) -P $LocalPort "root@127.0.0.1:$RemotePath" $LocalPath
    }
    if ($LASTEXITCODE -ne 0) { throw "Download failed for $RemotePath (scp exit $LASTEXITCODE)" }
}

function Use-AzureWebAppTunnel {
    # IMPORTANT: call this *bare* (no `$exitCode = ...`, no `| ...`) from the top-level
    # script, then read $LASTEXITCODE for the result. See Invoke-AzureWebAppWithAskPass
    # for why -- the short version is that capturing this call's output would silently
    # swallow the ssh/scp session's live console output several frames down.
    param(
        [Parameter(Mandatory = $true)][string]$WebApp,
        [Parameter(Mandatory = $true)][string]$ResourceGroup,
        [Parameter(Mandatory = $true)][int]$Port,
        [string]$Label = '',
        [string]$LogPrefix = 'azure_webapp',
        [Parameter(Mandatory = $true)][scriptblock]$Action
    )

    if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        throw 'Azure CLI (az) not found in PATH.'
    }
    if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
        throw "OpenSSH client (ssh.exe) not found in PATH.`nEnable it via Settings > Apps > Optional features > Add a feature > OpenSSH Client,`nor from an admin PowerShell: Add-WindowsCapability -Online -Name OpenSSH.Client~~~~0.0.1.0"
    }

    $resolvedPort = Get-AzureWebAppAvailableLocalPort -PreferredPort $Port
    if ($resolvedPort -ne $Port) {
        Write-Host "Port $Port is reserved by Windows (Hyper-V/WSL port exclusions); using $resolvedPort instead."
    }
    $Port = $resolvedPort

    $tunnelLog = Join-Path $env:TEMP "${LogPrefix}_${Port}.log"
    Stop-AzureWebAppTunnelPort -LocalPort $Port

    Write-Host "Starting tunnel for ${Label} on 127.0.0.1:$Port..."
    $tunnelJob = Start-AzureWebAppTunnelJob -WebAppName $WebApp -ResourceGroupName $ResourceGroup -LocalPort $Port -LogPath $tunnelLog
    $tunnelReady = Wait-AzureWebAppTunnelReady -Job $tunnelJob -LogPath $tunnelLog -LocalPort $Port
    if (-not $tunnelReady) {
        Show-AzureWebAppTunnelDiagnostics -LogPath $tunnelLog -Job $tunnelJob
        Stop-AzureWebAppTunnelJob -Job $tunnelJob -LocalPort $Port
        throw 'Tunnel did not become ready in time.'
    }

    $global:LASTEXITCODE = 1
    try {
        if (-not (Test-AzureWebAppTunnelAlive -Job $tunnelJob -LocalPort $Port)) {
            throw 'Tunnel closed before SSH could start.'
        }

        $ctx = [PSCustomObject]@{
            Label     = $Label
            WebApp    = $WebApp
            Port      = $Port
            Password  = $script:AzureWebAppSshPassword
            TunnelJob = $tunnelJob
            TunnelLog = $tunnelLog
        }

        & $Action $ctx
        $exitCode = $LASTEXITCODE
    } catch {
        Write-Host ""
        Write-Host "ERROR: $($_.Exception.Message)" -ForegroundColor Red
        $exitCode = 1
    } finally {
        Write-Host 'Closing tunnel...'
        Stop-AzureWebAppTunnelJob -Job $tunnelJob -LocalPort $Port
    }

    $global:LASTEXITCODE = $exitCode
}
