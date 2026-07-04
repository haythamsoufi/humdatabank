# Deploy IFRC Databank Backoffice container to Azure App Service (local CLI).
# Mirrors .github/workflows/deploy-to-webapp.yml: build/push ACR image, update Web App, upload static assets.
#
# Usage (from repo root via azure_webapp_tools.bat or directly):
#   .\azure-webapp\azure_webapp_deploy.ps1 -EnvironmentLabel STAGING -WebApp ifrc-databank-staging-2 `
#       -ResourceGroup ifrctgo001rg -Subscription f585c1c3-801b-4641-8d7f-145aa50ffb04
#
# Advanced: -ForceStaticUpload  -SkipBuild  -SkipStaticUpload  -Version v1.8
#
# Optional: azure_webapp.local.env with AZURE_STORAGE_CONNECTION_STRING for static asset upload only.

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('PROD', 'STAGING')]
    [string]$EnvironmentLabel,

    [Parameter(Mandatory = $true)]
    [string]$WebApp,

    [Parameter(Mandatory = $true)]
    [string]$ResourceGroup,

    [Parameter(Mandatory = $true)]
    [string]$Subscription,

    # Subscription that hosts ACR ifrcimage (used briefly to obtain a push token).
    [string]$AcrSubscription = '3e33b4c1-ada7-4922-9113-b9e41eaf1797',

    [string]$Version = '',
    [switch]$ForceStaticUpload,
    [switch]$SkipBuild,
    [switch]$SkipStaticUpload
)

$ErrorActionPreference = 'Stop'

# Docker/az write warnings to stderr; don't treat those as terminating errors (PowerShell 7+).
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

function Invoke-External {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [switch]$ShowOutput
    )
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    $exitCode = 1
    try {
        if ($ShowOutput) {
            & $Command 2>&1 | ForEach-Object { Write-Host $_ }
        } else {
            & $Command *> $null
        }
        $exitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $oldEap
    }
    # Unary comma: return exit code only, not mixed with command stdout on the pipeline.
    return ,$exitCode
}

function Test-DockerDaemon {
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & docker ps -q *> $null
        return ($LASTEXITCODE -eq 0)
    } finally {
        $ErrorActionPreference = $oldEap
    }
}

$AcrRegistry = 'ifrcimage.azurecr.io'
$AcrName = 'ifrcimage'
$ImageRepo = 'databank_backend'
$BuildCacheRef = "${AcrRegistry}/${ImageRepo}:buildcache"
$DefaultVersion = 'v1.7'
. (Join-Path $PSScriptRoot 'azure_webapp_config.ps1')
$RepoRoot = Get-AzureWebAppRepoRoot
$Dockerfile = Join-Path $RepoRoot 'Backoffice\Dockerfile'
$DockerContext = Join-Path $RepoRoot 'Backoffice'
$StaticUploadScript = Join-Path $RepoRoot 'Backoffice\azure\upload-static-assets.sh'
$LocalEnvFile = Join-Path $RepoRoot 'azure_webapp.local.env'

function Write-Step { param([string]$Message) Write-Host "`n=== $Message ===" -ForegroundColor Cyan }
function Write-Ok { param([string]$Message) Write-Host "OK: $Message" -ForegroundColor Green }
function Write-Warn { param([string]$Message) Write-Host "WARN: $Message" -ForegroundColor Yellow }
function Write-Err { param([string]$Message) Write-Host "ERROR: $Message" -ForegroundColor Red }

function Import-LocalEnvFile {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) {
        return $false
    }
    Write-Ok "Loaded secrets from $(Split-Path -Leaf $Path)"
    Get-Content -LiteralPath $Path | ForEach-Object {
        $line = $_.Trim()
        if ($line -match '^\s*#' -or $line -eq '') { return }
        if ($line -match '^([^=]+)=(.*)$') {
            $name = $matches[1].Trim()
            $value = $matches[2].Trim().Trim('"').Trim("'")
            Set-Item -Path "Env:$name" -Value $value
        }
    }
    return $true
}

function Get-AzCommandOutput {
    param([Parameter(Mandatory = $true)][string[]]$AzArgs)
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $out = az @AzArgs 2>&1
        if ($LASTEXITCODE -ne 0) { return $null }
        $text = ($out | Out-String).Trim()
        if ([string]::IsNullOrWhiteSpace($text)) { return $null }
        return $text
    } finally {
        $ErrorActionPreference = $oldEap
    }
}

function Assert-Command {
    param([string]$Name, [string]$InstallHint)
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        Write-Err "$Name not found in PATH. $InstallHint"
        exit 1
    }
}

function Get-GitOutput {
    param([string[]]$GitArgs)
    Push-Location $RepoRoot
    try {
        $out = & git @GitArgs 2>$null
        if ($LASTEXITCODE -ne 0) { return $null }
        return ($out | Out-String).Trim()
    } finally {
        Pop-Location
    }
}

function Test-FilesChangedSincePreviousCommit {
    param([string[]]$Paths)
    $gitArgs = @('diff', '--name-only', 'HEAD^..HEAD', '--') + @($Paths)
    $changed = Get-GitOutput -GitArgs $gitArgs
    if ($null -eq $changed) {
        # No parent commit - treat as changed (first deploy / shallow clone).
        return $true
    }
    return [bool]$changed
}

function Get-LatestReleaseTag {
    param([string]$FallbackTag)
    $remote = Get-GitOutput -GitArgs @('remote', 'get-url', 'origin')
    if ($remote -match 'github\.com[:/](?<owner>[^/]+)/(?<repo>[^/.]+)') {
        $owner = $Matches['owner']
        $repo = $Matches['repo'] -replace '\.git$', ''
        $apiUrl = "https://api.github.com/repos/$owner/$repo/releases/latest"
        try {
            if (Get-Command gh -ErrorAction SilentlyContinue) {
                $tag = gh release view --repo "$owner/$repo" --json tagName -q '.tagName' 2>$null
                if ($tag) {
                    Write-Ok "Latest GitHub release tag: $tag"
                    return $tag
                }
            }
            $response = Invoke-RestMethod -Uri $apiUrl -Headers @{ 'User-Agent' = 'ifrc-databank-deploy' } -ErrorAction Stop
            if ($response.tag_name) {
                Write-Ok "Latest GitHub release tag: $($response.tag_name)"
                return $response.tag_name
            }
        } catch {
            Write-Warn "Could not resolve latest GitHub release; using deploy tag $FallbackTag for APP_VERSION."
        }
    }
    return $FallbackTag
}

function Assert-DockerRunning {
    Write-Ok 'Checking Docker daemon...'
    if (-not (Test-DockerDaemon)) {
        Write-Err 'Docker is not running. Start Docker Desktop and try again.'
        exit 1
    }
    Write-Ok 'Docker daemon is running.'
}

function Invoke-AcrLogin {
    param(
        [Parameter(Mandatory = $true)]
        [string]$WebAppSubscription
    )

    Assert-DockerRunning

    $azShowExit = Invoke-External { az account show --output none }
    if ($azShowExit -ne 0) {
        Write-Err 'Not signed in to Azure CLI. Run: az login'
        exit 1
    }

    Write-Ok "Logging in to $AcrRegistry via az login (AcrPush required) ..."

    $acrLoginExit = 1
    $oldEap = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        if ($AcrSubscription -and $AcrSubscription -ne $WebAppSubscription) {
            Write-Ok "Using ACR subscription $AcrSubscription ..."
            az account set --subscription $AcrSubscription | Out-Null
        }

        # Prefer az acr login: configures Docker's ACR credential helper (avoids oversized Authorization headers).
        Write-Host '  az acr login (Docker credential helper) ...' -ForegroundColor DarkGray
        $acrLoginExit = Invoke-External -ShowOutput { az acr login --name $AcrName --subscription $AcrSubscription }

        if ($acrLoginExit -ne 0) {
            Write-Warn '  az acr login failed; trying registry-scoped --expose-token ...'
            $jsonText = Get-AzCommandOutput -AzArgs @(
                'acr', 'login',
                '--name', $AcrName,
                '--subscription', $AcrSubscription,
                '--expose-token',
                '-o', 'json'
            )
            if ($jsonText) {
                $acrInfo = $jsonText | ConvertFrom-Json
                $loginServer = if ($acrInfo.loginServer) { $acrInfo.loginServer } else { $AcrRegistry }
                $accessToken = $acrInfo.accessToken
                $acrLoginExit = Invoke-External -ShowOutput {
                    $accessToken | docker login $loginServer -u 00000000-0000-0000-0000-000000000000 --password-stdin
                }
            }
        }
    } finally {
        az account set --subscription $WebAppSubscription | Out-Null
        $ErrorActionPreference = $oldEap
    }

    if ($acrLoginExit -ne 0) {
        Write-Err @"
ACR login failed.

If you saw '400 Request Header Or Cookie Too Large', avoid piping a large AAD token into docker login.
Use the credential helper instead:

  az account set --subscription $AcrSubscription
  az acr login --name $AcrName

Requires AcrPush on '$AcrName'. Run: az login
"@
        exit 1
    }

    Write-Ok 'ACR login succeeded via az login.'
}

function Invoke-BashScript {
    param(
        [string]$ScriptPath,
        [hashtable]$EnvVars = @{}
    )
    $bash = $null
    foreach ($candidate in @(
        (Get-Command bash -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source),
        "${env:ProgramFiles}\Git\bin\bash.exe",
        "${env:ProgramFiles(x86)}\Git\bin\bash.exe"
    )) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) {
            $bash = $candidate
            break
        }
    }
    if (-not $bash) {
        Write-Err "bash not found (install Git for Windows). Required for upload-static-assets.sh"
        exit 1
    }

    foreach ($key in $EnvVars.Keys) {
        Set-Item -Path "Env:$key" -Value $EnvVars[$key]
    }

    $posixScript = $ScriptPath -replace '\\', '/'
    & $bash -lc "chmod +x '$posixScript'; '$posixScript'"
    if ($LASTEXITCODE -ne 0) {
        Write-Err "Static upload script failed (exit $LASTEXITCODE)."
        exit 1
    }
}

Import-LocalEnvFile -Path $LocalEnvFile | Out-Null

Write-Step 'Preflight'
Assert-Command -Name 'az' -InstallHint 'Install: https://aka.ms/installazurecliwindows'
if (-not $SkipBuild) {
    Assert-Command -Name 'docker' -InstallHint 'Install Docker Desktop.'
}
Assert-Command -Name 'git' -InstallHint 'Install Git.'

Write-Ok "Setting subscription $Subscription"
az account set --subscription $Subscription
if ($LASTEXITCODE -ne 0) {
    Write-Err "Failed to set subscription $Subscription. Run 'az login' and verify access."
    exit 1
}

if (-not (Test-Path -LiteralPath $Dockerfile)) {
    Write-Err "Dockerfile not found: $Dockerfile"
    exit 1
}

$gitSha = Get-GitOutput -GitArgs @('rev-parse', 'HEAD')
if (-not $gitSha) {
    Write-Err 'Could not resolve git HEAD. Run from a git checkout.'
    exit 1
}
Write-Ok "Git SHA: $gitSha"

if (-not $Version) {
    $Version = Read-Host "Container image tag [$DefaultVersion]"
    if ([string]::IsNullOrWhiteSpace($Version)) { $Version = $DefaultVersion }
}
$Version = $Version.Trim()
Write-Ok "Deploy image tag: $Version"

if ($EnvironmentLabel -eq 'PROD') {
    Write-Host ''
    Write-Warn "You selected PRODUCTION ($WebApp)."
    $confirm = Read-Host "Type 'yes' to deploy to PRODUCTION"
    if ($confirm -ne 'yes') {
        Write-Warn 'Production deploy cancelled.'
        exit 0
    }
}

$staticContainer = if ($EnvironmentLabel -eq 'PROD') { 'static' } else { 'static-staging' }
$imageTagVersion = "${AcrRegistry}/${ImageRepo}:$Version"
$imageTagSha = "${AcrRegistry}/${ImageRepo}:$gitSha"
$latestReleaseTag = Get-LatestReleaseTag -FallbackTag $Version

$depsChanged = Test-FilesChangedSincePreviousCommit -Paths @(
    'Backoffice/requirements.txt',
    'Backoffice/Dockerfile',
    'Backoffice/.dockerignore'
)
if ($depsChanged) {
    Write-Ok 'Dependency-related files changed - will refresh registry build cache.'
} else {
    Write-Ok 'No dependency file changes - fast build path (cache-from only).'
}

if (-not $SkipBuild) {
    Write-Step 'ACR login'
    Invoke-AcrLogin -WebAppSubscription $Subscription

    Write-Step 'Build and push container image'
    $buildArgs = @(
        'buildx', 'build',
        '--platform', 'linux/amd64',
        '--file', $Dockerfile,
        '--tag', $imageTagVersion,
        '--tag', $imageTagSha,
        '--build-arg', "ASSET_VERSION=$gitSha",
        '--build-arg', "GIT_SHA=$gitSha",
        '--build-arg', "RELEASE_VERSION=$Version",
        '--build-arg', "LATEST_RELEASE_TAG=$latestReleaseTag",
        '--build-arg', 'BUILDKIT_INLINE_CACHE=1',
        '--cache-from', "type=registry,ref=$BuildCacheRef",
        '--provenance=false',
        '--push'
    )
    if ($depsChanged) {
        $buildArgs += @('--cache-to', "type=registry,ref=$BuildCacheRef,mode=max")
    }
    $buildArgs += $DockerContext

    Write-Host ("docker " + ($buildArgs -join ' '))
    Write-Host 'Build/push can take 10-20 minutes on first run - progress lines appear below.' -ForegroundColor DarkGray
    $buildExit = Invoke-External -ShowOutput { docker @buildArgs }
    if ($buildExit -ne 0) {
        Write-Err 'Docker build/push failed.'
        exit 1
    }
    Write-Ok "Pushed $imageTagVersion and $imageTagSha"
} else {
    Write-Warn 'SkipBuild set - assuming image already exists in ACR.'
}

Write-Step 'Deploy container to Azure Web App'
az webapp config container set `
    --name $WebApp `
    --resource-group $ResourceGroup `
    --container-image-name $imageTagVersion `
    --output none
if ($LASTEXITCODE -ne 0) {
    Write-Err 'Failed to set container image on Web App.'
    exit 1
}

az webapp restart --name $WebApp --resource-group $ResourceGroup --output none
if ($LASTEXITCODE -ne 0) {
    Write-Err 'Web App restart failed.'
    exit 1
}
Write-Ok "Web App '$WebApp' is pulling $imageTagVersion"

$shouldUploadStatic = $ForceStaticUpload.IsPresent
if (-not $shouldUploadStatic -and -not $SkipStaticUpload) {
    $shouldUploadStatic = Test-FilesChangedSincePreviousCommit -Paths @('Backoffice/app/static')
    if ($shouldUploadStatic) {
        Write-Ok 'Static files changed in latest commit - will upload.'
    } else {
        Write-Ok 'No static file changes in latest commit - skipping static upload.'
    }
}

if ($ForceStaticUpload) {
    Write-Ok 'ForceStaticUpload enabled - will upload static assets.'
}

if ($shouldUploadStatic -and -not $SkipStaticUpload) {
    $connString = [Environment]::GetEnvironmentVariable('AZURE_STORAGE_CONNECTION_STRING')
    if ([string]::IsNullOrWhiteSpace($connString)) {
        Write-Warn 'AZURE_STORAGE_CONNECTION_STRING is not set - skipping static upload.'
        Write-Warn "Set it in the environment or $LocalEnvFile then re-run with -ForceStaticUpload."
    } elseif (-not (Test-Path -LiteralPath $StaticUploadScript)) {
        Write-Warn "Static upload script not found: $StaticUploadScript"
    } else {
        Write-Step "Upload static assets to blob container '$staticContainer'"
        $envMap = @{
            AZURE_STORAGE_CONNECTION_STRING = $connString
            STATIC_BLOB_CONTAINER           = $staticContainer
        }
        if ($ForceStaticUpload) {
            $envMap['STATIC_FORCE_UPLOAD'] = '1'
        }
        Invoke-BashScript -ScriptPath $StaticUploadScript -EnvVars $envMap
        Write-Ok 'Static assets uploaded.'
    }
}

Write-Step 'Deploy complete'
Write-Host "Environment : $EnvironmentLabel"
Write-Host "Web App     : $WebApp"
Write-Host "Image       : $imageTagVersion"
Write-Host "Git SHA     : $gitSha"
Write-Host ''
Write-Host 'Tail logs:' -ForegroundColor Cyan
Write-Host "  az webapp log tail --name $WebApp --resource-group $ResourceGroup"
