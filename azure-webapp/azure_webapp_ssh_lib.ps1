# Shared SSH tunnel helpers for Azure App Service containers.
# Dot-source from azure_webapp_ssh.ps1, azure_webapp_run.ps1, azure_webapp_run_script.ps1

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

function Find-AzureWebAppPlink {
    @(
        (Get-Command plink -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        "${env:ProgramFiles}\PuTTY\plink.exe",
        "${env:ProgramFiles(x86)}\PuTTY\plink.exe",
        "${env:ProgramFiles}\Git\usr\bin\plink.exe"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

function Find-AzureWebAppPscp {
    @(
        (Get-Command pscp -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        "${env:ProgramFiles}\PuTTY\pscp.exe",
        "${env:ProgramFiles(x86)}\PuTTY\pscp.exe"
    ) | Where-Object { $_ -and (Test-Path $_) } | Select-Object -First 1
}

function Ensure-AzureWebAppPlink {
    $found = Find-AzureWebAppPlink
    if ($found) { return $found }
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) { return $null }
    Write-Host "PuTTY plink not found. Installing PuTTY (one-time)..."
    & winget install --id PuTTY.PuTTY -e --accept-package-agreements --accept-source-agreements --source winget
    return Find-AzureWebAppPlink
}

function Clear-AzureWebAppPlinkHostKeyCache {
    param([int]$LocalPort)
    $regPath = 'HKCU:\Software\SimonTatham\PuTTY\SshHostKeys'
    if (-not (Test-Path $regPath)) { return }
    $props = Get-ItemProperty -Path $regPath
    foreach ($name in $props.PSObject.Properties.Name) {
        if ($name -match '127\.0\.0\.1' -and $name -match "@${LocalPort}:") {
            Remove-ItemProperty -Path $regPath -Name $name -ErrorAction SilentlyContinue
        }
    }
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

function Get-AzureWebAppPlinkHostKeys {
    param(
        [string]$PlinkPath,
        [int]$LocalPort,
        [string]$Password = $script:AzureWebAppSshPassword
    )
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $output = & $PlinkPath -batch -ssh "root@127.0.0.1" -P $LocalPort -pw $Password 2>&1 | Out-String
    } finally {
        $ErrorActionPreference = $prev
    }
    $keys = @()
    if ($output -match 'ssh-ed25519 255 (SHA256:[A-Za-z0-9+/=]+)') {
        $keys += "ssh-ed25519 255 $($Matches[1])"
        $keys += $Matches[1]
    } elseif ($output -match '(SHA256:[A-Za-z0-9+/=]+)') {
        $keys += $Matches[1]
        $keys += "ssh-ed25519 255 $($Matches[1])"
    }
    return $keys | Select-Object -Unique
}

function Show-AzureWebAppTunnelDiagnostics {
    param([string]$LogPath, $Job)
    Write-Host ""
    Write-Host "Tunnel diagnostics:"
    if ($Job) { Write-Host "  Job state: $($Job.State)" }
    if (Test-Path $LogPath) {
        Write-Host ""
        Write-Host "Tunnel output:"
        Get-Content $LogPath -ErrorAction SilentlyContinue
    } else {
        Write-Host "  (no tunnel log at $LogPath)"
    }
}

function Invoke-AzureWebAppOpenSshSession {
    param([int]$LocalPort)
    $askPassCmd = Join-Path $env:TEMP 'azure_ssh_askpass.cmd'
    if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) { return 1 }
    @('@echo off', 'echo Docker!') | Set-Content -Path $askPassCmd -Encoding ASCII
    $env:SSH_ASKPASS = $askPassCmd
    $env:SSH_ASKPASS_REQUIRE = 'force'
    $env:DISPLAY = '1'
    & ssh -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile=NUL `
        -o PubkeyAuthentication=no -o PreferredAuthentications=password `
        -o MACs=hmac-sha1,hmac-sha1-96 `
        "root@127.0.0.1" -p $LocalPort
    $rc = $LASTEXITCODE
    Remove-Item Env:SSH_ASKPASS -ErrorAction SilentlyContinue
    Remove-Item Env:SSH_ASKPASS_REQUIRE -ErrorAction SilentlyContinue
    Remove-Item Env:DISPLAY -ErrorAction SilentlyContinue
    Remove-Item $askPassCmd -Force -ErrorAction SilentlyContinue
    return $rc
}

function Send-AzureWebAppRemoteFile {
    param(
        [string]$LocalPath,
        [string]$RemotePath,
        [string]$PlinkPath,
        [string]$PscpPath,
        [int]$LocalPort,
        [string]$HostKey,
        [string]$Password = $script:AzureWebAppSshPassword
    )
    if (-not (Test-Path $LocalPath)) {
        throw "Local file not found: $LocalPath"
    }
    if ($PscpPath) {
        & $PscpPath -batch -hostkey $HostKey -P $LocalPort -pw $Password $LocalPath "root@127.0.0.1:$RemotePath"
        if ($LASTEXITCODE -ne 0) { throw "pscp failed for $LocalPath" }
        return
    }
    Get-Content -Raw -Path $LocalPath | & $PlinkPath -batch -hostkey $HostKey -ssh "root@127.0.0.1" -P $LocalPort -pw $Password "cat > $RemotePath"
    if ($LASTEXITCODE -ne 0) { throw "Upload failed for $LocalPath" }
}

function Invoke-AzureWebAppPlinkCommand {
    param(
        [string]$PlinkPath,
        [int]$LocalPort,
        [string]$HostKey,
        [string]$RemoteCommand,
        [switch]$Interactive,
        [string]$Password = $script:AzureWebAppSshPassword
    )
    $args = @('-batch', '-hostkey', $HostKey, '-ssh', 'root@127.0.0.1', '-P', "$LocalPort", '-pw', $Password)
    if ($Interactive) { $args += '-t' }
    & $PlinkPath @args $RemoteCommand
    return $LASTEXITCODE
}

function Use-AzureWebAppTunnel {
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

    $plink = Ensure-AzureWebAppPlink
    if (-not $plink -and -not (Get-Command ssh -ErrorAction SilentlyContinue)) {
        throw 'Neither plink nor ssh found. Install PuTTY: winget install PuTTY.PuTTY'
    }

    $tunnelLog = Join-Path $env:TEMP "${LogPrefix}_${Port}.log"
    Stop-AzureWebAppTunnelPort -LocalPort $Port
    Clear-AzureWebAppPlinkHostKeyCache -LocalPort $Port

    Write-Host "Starting tunnel for ${Label} on 127.0.0.1:$Port..."
    $tunnelJob = Start-AzureWebAppTunnelJob -WebAppName $WebApp -ResourceGroupName $ResourceGroup -LocalPort $Port -LogPath $tunnelLog
    $tunnelReady = Wait-AzureWebAppTunnelReady -Job $tunnelJob -LogPath $tunnelLog -LocalPort $Port
    if (-not $tunnelReady) {
        Show-AzureWebAppTunnelDiagnostics -LogPath $tunnelLog -Job $tunnelJob
        Stop-AzureWebAppTunnelJob -Job $tunnelJob -LocalPort $Port
        throw 'Tunnel did not become ready in time.'
    }

    $exitCode = 1
    try {
        if (-not (Test-AzureWebAppTunnelAlive -Job $tunnelJob -LocalPort $Port)) {
            throw 'Tunnel closed before SSH could start.'
        }

        $hostKeys = @()
        if ($plink) {
            Write-Host 'Discovering SSH host key...'
            $hostKeys = Get-AzureWebAppPlinkHostKeys -PlinkPath $plink -LocalPort $Port
        }
        if ($hostKeys.Count -eq 0) {
            throw 'Could not discover SSH host key from tunnel.'
        }

        $ctx = [PSCustomObject]@{
            Label      = $Label
            WebApp     = $WebApp
            Port       = $Port
            PlinkPath  = $plink
            PscpPath   = Find-AzureWebAppPscp
            HostKeys   = $hostKeys
            HostKey    = $hostKeys[0]
            Password   = $script:AzureWebAppSshPassword
            TunnelJob  = $tunnelJob
            TunnelLog  = $tunnelLog
        }

        $result = & $Action $ctx
        if ($null -eq $result) {
            $exitCode = 0
        } elseif ($result -is [System.Array]) {
            $exitCode = [int]($result | Select-Object -Last 1)
        } else {
            $exitCode = [int]$result
        }
    } finally {
        Write-Host 'Closing tunnel...'
        Stop-AzureWebAppTunnelJob -Job $tunnelJob -LocalPort $Port
    }

    return [int]$exitCode
}
