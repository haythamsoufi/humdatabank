<#
.SYNOPSIS
  Audit Azure App Service env vars for the Backoffice web app.

.DESCRIPTION
  Fetches Azure Web App "Application settings" and "Connection strings" (names only)
  and compares them against:
    - Backoffice/env.example
    - Backoffice/azure/azure.env.template
    - Critical runtime vars inferred from Backoffice/config/config.py (boot blockers)
    - (Optional) a lightweight code scan for os.environ.get / os.getenv usage

  It never prints secret values.

.REQUIREMENTS
  - Azure CLI installed (`az`)
  - Logged in (`az login`)
  - Permission to read Web App configuration

.EXAMPLE
  pwsh .\Backoffice\azure\audit-webapp-env.ps1 -ResourceGroup rg-prod -WebAppName ifrc-databank-backoffice -FlaskConfig production

.EXAMPLE
  pwsh .\Backoffice\azure\audit-webapp-env.ps1 -ResourceGroup rg-stg -WebAppName ifrc-databank-backoffice -Slot staging -FlaskConfig staging -IncludeCodeScan -OutJson .\env-audit.json
#>

[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$ResourceGroup,

  [Parameter(Mandatory = $true)]
  [string]$WebAppName,

  [string]$Slot,

  [ValidateSet('production', 'staging', 'development', 'testing', 'default')]
  [string]$FlaskConfig = 'production',

  # Defaults to Backoffice/ (script lives in Backoffice/azure/)
  [string]$BackofficePath = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path,

  # If set, scans Backoffice/**/*.py for os.environ.get/os.getenv usage (can be slower).
  [switch]$IncludeCodeScan,

  # If set, writes a JSON report to this path.
  [string]$OutJson
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Assert-AzCli {
  if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
    throw "Azure CLI ('az') is not installed or not on PATH."
  }
  try {
    $null = az account show --only-show-errors 2>$null
  } catch {
    throw "Not logged into Azure CLI. Run 'az login' (and 'az account set' if needed)."
  }
}

function Get-EnvKeysFromFile {
  param(
    [Parameter(Mandatory = $true)][string]$Path
  )
  if (-not (Test-Path -LiteralPath $Path)) {
    return @()
  }
  $keys = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)
  Get-Content -LiteralPath $Path | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq '' -or $line.StartsWith('#')) { return }
    # Matches: KEY=VALUE (KEY must be uppercase-like env var)
    $m = [regex]::Match($line, '^\s*([A-Z][A-Z0-9_]*)\s*=')
    if ($m.Success) { [void]$keys.Add($m.Groups[1].Value) }
  }
  # Convert HashSet to PowerShell array
  return [string[]]$keys
}

function Get-EnvKeysFromPythonFile {
  param(
    [Parameter(Mandatory = $true)][string]$Path
  )
  if (-not (Test-Path -LiteralPath $Path)) { return @() }
  $content = Get-Content -LiteralPath $Path -Raw
  $keys = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)

  # os.environ.get("VAR") / os.environ.get('VAR')
  foreach ($m in [regex]::Matches($content, "os\.environ\.get\(\s*['""]([A-Z][A-Z0-9_]*)['""]")) {
    [void]$keys.Add($m.Groups[1].Value)
  }
  # os.getenv("VAR") / os.getenv('VAR')
  foreach ($m in [regex]::Matches($content, "os\.getenv\(\s*['""]([A-Z][A-Z0-9_]*)['""]")) {
    [void]$keys.Add($m.Groups[1].Value)
  }

  # Convert HashSet to PowerShell array
  return [string[]]$keys
}

function Get-EnvKeysFromBackofficeCode {
  param(
    [Parameter(Mandatory = $true)][string]$Root
  )
  $keys = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)
  $pyFiles = Get-ChildItem -LiteralPath $Root -Recurse -File -Filter '*.py' -ErrorAction Stop
  foreach ($f in $pyFiles) {
    foreach ($k in (Get-EnvKeysFromPythonFile -Path $f.FullName)) {
      [void]$keys.Add($k)
    }
  }
  return [string[]]$keys
}

function Get-AzureWebAppEnvKeys {
  param(
    [Parameter(Mandatory = $true)][string]$Rg,
    [Parameter(Mandatory = $true)][string]$Name,
    [string]$SlotName
  )
  $slotArgs = @()
  if ($SlotName -and $SlotName.Trim() -ne '') {
    $slotArgs = @('--slot', $SlotName)
  }

  # App settings (array of { name, value, slotSetting })
  $appSettingsJson = az webapp config appsettings list -g $Rg -n $Name @slotArgs --only-show-errors | Out-String
  $appSettings = @()
  if ($appSettingsJson.Trim() -ne '') {
    try {
      $parsed = $appSettingsJson | ConvertFrom-Json
      if ($parsed) {
        # Ensure it's always an array, even if JSON returns a single object
        $appSettings = @($parsed)
      }
    } catch {
      Write-Warning "Failed to parse app settings JSON: $_"
    }
  }
  $appSettingKeys = @()
  $appSettingsArray = @($appSettings)
  try {
    if ($appSettingsArray) {
      foreach ($setting in $appSettingsArray) {
        if ($setting -and $setting.name) {
          $appSettingKeys += $setting.name
        }
      }
    }
  } catch {
    Write-Warning "Error processing app settings: $_"
  }

  # Connection strings (object with properties)
  $connJson = az webapp config connection-string list -g $Rg -n $Name @slotArgs --only-show-errors | Out-String
  $connObj = $null
  if ($connJson.Trim() -ne '') {
    try {
      $connObj = $connJson | ConvertFrom-Json
    } catch {
      Write-Warning "Failed to parse connection strings JSON: $_"
    }
  }
  $connKeys = @()
  if ($connObj -and $connObj.PSObject -and $connObj.PSObject.Properties) {
    $connKeys = @($connObj.PSObject.Properties.Name | Where-Object { $_ })
  }

  $all = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)
  foreach ($k in ($appSettingKeys + $connKeys)) {
    if ($k -and $k.Trim() -ne '') { [void]$all.Add($k) }
  }

  # Convert HashSet to array
  $allKeysArray = [string[]]$all

  # Ensure we always return proper arrays
  $sortedAppSettings = @($appSettingKeys | Sort-Object -Unique)
  $sortedConnStrings = @($connKeys | Sort-Object -Unique)
  $sortedAllKeys = @($allKeysArray | Sort-Object)

  [pscustomobject]@{
    AppSettings      = $sortedAppSettings
    ConnectionStrings = $sortedConnStrings
    AllKeys          = $sortedAllKeys
  }
}

Assert-AzCli

$envExamplePath = Join-Path $BackofficePath 'env.example'
$azureTemplatePath = Join-Path $BackofficePath 'azure\azure.env.template'
$configPyPath = Join-Path $BackofficePath 'config\config.py'

$templateKeys = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)
foreach ($k in (Get-EnvKeysFromFile -Path $envExamplePath)) { [void]$templateKeys.Add($k) }
foreach ($k in (Get-EnvKeysFromFile -Path $azureTemplatePath)) { [void]$templateKeys.Add($k) }

# Critical boot-time vars based on Backoffice/config/config.py behavior:
# - DATABASE_URL is always required
# - SECRET_KEY is required in production (generated at runtime otherwise)
# - API_KEY is required in strict validation (production/staging by default)
$criticalKeys = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)
[void]$criticalKeys.Add('DATABASE_URL')
if ($FlaskConfig -eq 'production') { [void]$criticalKeys.Add('SECRET_KEY') }
if ($FlaskConfig -in @('production', 'staging')) { [void]$criticalKeys.Add('API_KEY') }

# Recommended (not always required), but usually expected on Azure:
$recommendedKeys = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)
[void]$recommendedKeys.Add('FLASK_CONFIG')

$codeKeys = @()
if ($IncludeCodeScan) {
  $codeKeys = Get-EnvKeysFromBackofficeCode -Root $BackofficePath
} else {
  # Lightweight: only scan config.py (captures most runtime env usage)
  $codeKeys = Get-EnvKeysFromPythonFile -Path $configPyPath
}
$codeKeySet = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)
foreach ($k in $codeKeys) { [void]$codeKeySet.Add($k) }

$azure = Get-AzureWebAppEnvKeys -Rg $ResourceGroup -Name $WebAppName -SlotName $Slot
$azureKeySet = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)
foreach ($k in $azure.AllKeys) { [void]$azureKeySet.Add($k) }

function Missing-From {
  param([string[]]$Keys)
  $missing = @()
  foreach ($k in ($Keys | Sort-Object -Unique)) {
    if (-not $azureKeySet.Contains($k)) { $missing += $k }
  }
  return $missing
}

$missingCritical = Missing-From -Keys ([string[]]$criticalKeys)
$missingRecommended = Missing-From -Keys ([string[]]$recommendedKeys)
$missingTemplate = Missing-From -Keys ([string[]]$templateKeys)
$missingCode = Missing-From -Keys ([string[]]$codeKeySet)

# Code-only missing (helps reduce noise): vars referenced in code but not documented in templates
$templateAndCritical = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)
foreach ($k in $templateKeys) { [void]$templateAndCritical.Add($k) }
foreach ($k in $criticalKeys) { [void]$templateAndCritical.Add($k) }
$missingCodeOnly = @()
foreach ($k in $missingCode) {
  if (-not $templateAndCritical.Contains($k)) { $missingCodeOnly += $k }
}

# Extras (configured on Azure but not in templates/code) - may be fine, but useful to review
$known = New-Object System.Collections.Generic.HashSet[string] ([System.StringComparer]::OrdinalIgnoreCase)
foreach ($k in $templateKeys) { [void]$known.Add($k) }
foreach ($k in $criticalKeys) { [void]$known.Add($k) }
foreach ($k in $recommendedKeys) { [void]$known.Add($k) }
foreach ($k in $codeKeySet) { [void]$known.Add($k) }
$extraAzureKeys = @()
foreach ($k in $azure.AllKeys) {
  if (-not $known.Contains($k)) { $extraAzureKeys += $k }
}

Write-Host ""
Write-Host "Azure Web App env audit (names only)" -ForegroundColor Cyan
Write-Host "  Resource group : $ResourceGroup"
Write-Host "  Web App        : $WebAppName"
if ($Slot -and $Slot.Trim() -ne '') { Write-Host "  Slot           : $Slot" }
Write-Host "  FLASK_CONFIG   : $FlaskConfig"
Write-Host "  Include scan   : $IncludeCodeScan"
Write-Host ""

$appSettingsCount = if ($azure.AppSettings) { @($azure.AppSettings).Count } else { 0 }
$connStringsCount = if ($azure.ConnectionStrings) { @($azure.ConnectionStrings).Count } else { 0 }
$allKeysCount = if ($azure.AllKeys) { @($azure.AllKeys).Count } else { 0 }
Write-Host ("Configured on Azure:"), ("{0} app settings, {1} connection strings, {2} total keys" -f $appSettingsCount, $connStringsCount, $allKeysCount)
Write-Host ""

function Print-List {
  param(
    [Parameter(Mandatory = $true)][string]$Title,
    [Parameter(Mandatory = $true)][string[]]$Items,
    [ConsoleColor]$Color = [ConsoleColor]::Yellow
  )
  Write-Host $Title -ForegroundColor $Color
  $itemsArray = @($Items)
  if (-not $itemsArray -or $itemsArray.Count -eq 0) {
    Write-Host "  (none)" -ForegroundColor DarkGray
    return
  }
  foreach ($i in ($itemsArray | Sort-Object -Unique)) {
    Write-Host "  - $i"
  }
}

Print-List -Title "Missing CRITICAL (can block boot / key auth in prod/stg):" -Items $missingCritical -Color Red
Print-List -Title "Missing RECOMMENDED:" -Items $missingRecommended -Color Yellow
Print-List -Title "Missing from templates (env.example + azure.env.template):" -Items $missingTemplate -Color Yellow
Print-List -Title "Missing from code scan (referenced in code):" -Items $missingCode -Color DarkYellow
Print-List -Title "Missing from code scan but NOT documented in templates:" -Items $missingCodeOnly -Color DarkYellow
Print-List -Title "Extra keys configured on Azure (not seen in templates/code):" -Items $extraAzureKeys -Color Gray

if ($OutJson -and $OutJson.Trim() -ne '') {
  $report = [pscustomobject]@{
    resourceGroup = $ResourceGroup
    webAppName = $WebAppName
    slot = $Slot
    flaskConfig = $FlaskConfig
    includeCodeScan = [bool]$IncludeCodeScan
    sources = [pscustomobject]@{
      envExample = $envExamplePath
      azureEnvTemplate = $azureTemplatePath
      configPy = $configPyPath
    }
    azureConfigured = [pscustomobject]@{
      appSettings = $azure.AppSettings
      connectionStrings = $azure.ConnectionStrings
      allKeys = $azure.AllKeys
    }
    required = [pscustomobject]@{
      critical = ([string[]]$criticalKeys) | Sort-Object
      recommended = ([string[]]$recommendedKeys) | Sort-Object
      template = ([string[]]$templateKeys) | Sort-Object
      codeScan = ([string[]]$codeKeySet) | Sort-Object
    }
    missing = [pscustomobject]@{
      critical = $missingCritical
      recommended = $missingRecommended
      template = $missingTemplate
      codeScan = $missingCode
      codeOnlyNotInTemplates = $missingCodeOnly
    }
    extraAzureKeys = $extraAzureKeys | Sort-Object
  }
  $json = $report | ConvertTo-Json -Depth 6
  $outPath = (Resolve-Path -LiteralPath (Split-Path -Parent $OutJson) -ErrorAction SilentlyContinue)
  if (-not $outPath) {
    # If the directory doesn't exist, try to create it
    $dir = Split-Path -Parent $OutJson
    if ($dir -and -not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir | Out-Null }
  }
  $json | Set-Content -LiteralPath $OutJson -Encoding UTF8
  Write-Host ""
  Write-Host "Wrote JSON report to: $OutJson" -ForegroundColor Cyan
}
