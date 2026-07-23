param()

$ErrorActionPreference = "Continue"

$Subscription     = "f585c1c3-801b-4641-8d7f-145aa50ffb04"
$ResourceGroup    = "ifrctgo001rg"
$LoadTestResource = "DatabankTest1"

# ---------------------------------------------------------------------------
# Environment definitions  - add / edit entries here to support more targets.
# ---------------------------------------------------------------------------
$Environments = [ordered]@{
    staging = [pscustomobject]@{
        Name       = "Staging"
        Host       = "https://databank-stage.ifrc.org"
        AllowProd  = "false"
        ConfigFile = "loadtest.config.yaml"
        TestId     = "47c51031-8a61-41ec-b48d-2018263200f1"
        DefaultVus = 20
        DefaultSec = 120
    }
    prod    = [pscustomobject]@{
        Name       = "Production"
        Host       = "https://databank.ifrc.org"
        AllowProd  = "true"
        ConfigFile = "loadtest-prod.config.yaml"
        TestId     = "b8f71042-9e72-4c3a-a25e-3129374311f2"
        DefaultVus = 10
        DefaultSec = 60
    }
}

# Active environment  - defaults to staging; change via menu option E.
$script:ActiveEnv = $Environments["staging"]

Set-Location -LiteralPath $PSScriptRoot

function Pause-Menu {
    Write-Host ""
    Read-Host "Press Enter to continue" | Out-Null
}

function Ensure-AzureTools {
    if (-not (Get-Command az -ErrorAction SilentlyContinue)) {
        Write-Host "[error] Azure CLI (az) not found on PATH." -ForegroundColor Red
        Write-Host "        Install: https://aka.ms/installazurecliwindows"
        return $false
    }

    & az account show -o none 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Not logged in - launching 'az login' ..."
        & az login -o none
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[error] az login failed." -ForegroundColor Red
            return $false
        }
    }

    & az account set --subscription $Subscription
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[error] Could not set subscription $Subscription." -ForegroundColor Red
        return $false
    }

    & az extension show --name load -o none 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Installing 'load' CLI extension ..."
        & az extension add --name load -y
        if ($LASTEXITCODE -ne 0) {
            Write-Host "[error] Failed to install 'load' extension." -ForegroundColor Red
            return $false
        }
    }

    return $true
}

# ---------------------------------------------------------------------------
# Environment selection
# ---------------------------------------------------------------------------
function Select-Environment {
    Write-Host ""
    Write-Host "Select target environment:"
    Write-Host "  1. Staging     ($($Environments['staging'].Host))"
    Write-Host "  2. Production  ($($Environments['prod'].Host))"
    Write-Host "  Q. Cancel"
    Write-Host ""
    $envChoice = (Read-Host "Environment [1/2/Q]").ToUpper().Trim()

    switch ($envChoice) {
        "1" {
            $script:ActiveEnv = $Environments["staging"]
            Write-Host ""
            Write-Host "Environment set to: Staging" -ForegroundColor Green
            Pause-Menu
        }
        "2" {
            $script:ActiveEnv = $Environments["prod"]
            Write-Host ""
            Write-Host "Environment set to: PRODUCTION" -ForegroundColor Red
            Pause-Menu
        }
        default {
            Write-Host "No change  - environment remains: $($script:ActiveEnv.Name)"
            Pause-Menu
        }
    }
}

# ---------------------------------------------------------------------------
# Session cookie capture  - browser-assisted or manual paste
# ---------------------------------------------------------------------------

function Invoke-BrowserCookieCapture {
    <#
    .SYNOPSIS
        Run capture_session_cookie.py in a visible Chromium window.
        Returns the captured "session=<value>" string, or "" on failure.

    .NOTES
        stdout from the Python script (the cookie) is redirected to a temp file
        so PowerShell can read it cleanly.  stderr (status messages) flows directly
        to the console so the user sees progress while waiting for login.
    #>
    $captureScript = Join-Path $PSScriptRoot "capture_session_cookie.py"
    if (-not (Test-Path -LiteralPath $captureScript)) {
        Write-Host "  [warn] capture_session_cookie.py not found  - falling back to manual entry." -ForegroundColor Yellow
        return ""
    }

    $py = if (Get-Command python  -ErrorAction SilentlyContinue) { "python"  }
          elseif (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" }
          else { $null }

    if (-not $py) {
        Write-Host "  [warn] Python not found on PATH  - falling back to manual entry." -ForegroundColor Yellow
        return ""
    }

    # Check playwright; offer to install if missing.
    & $py -c "import playwright" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host ""
        Write-Host "  playwright is not installed (needed for browser-based capture)." -ForegroundColor Yellow
        Write-Host "  Install: pip install playwright && playwright install chromium" -ForegroundColor Yellow
        Write-Host ""
        $install = (Read-Host "  Install playwright now? (y/N)").Trim().ToLower()
        if ($install -match "^(y|yes)$") {
            Write-Host "  Installing playwright ..."
            & $py -m pip install playwright
            if ($LASTEXITCODE -eq 0) {
                Write-Host "  Installing Chromium browser ..."
                & $py -m playwright install chromium
            }
        }
        if ($LASTEXITCODE -ne 0) {
            Write-Host "  [warn] Install failed  - falling back to manual entry." -ForegroundColor Yellow
            return ""
        }
    }

    Write-Host ""
    Write-Host "  Opening browser  - log in to capture your session cookie automatically." -ForegroundColor Cyan
    Write-Host "  (Close the browser window to cancel and fall back to manual paste.)" -ForegroundColor Cyan
    Write-Host ""

    # Redirect stdout to a temp file; stderr stays attached to this console so the
    # user sees the [login] progress messages while waiting for the browser.
    $tempOut = [System.IO.Path]::GetTempFileName()
    try {
        $proc = Start-Process `
            -FilePath $py `
            -ArgumentList @($captureScript, "--host", $script:ActiveEnv.Host) `
            -RedirectStandardOutput $tempOut `
            -NoNewWindow `
            -PassThru `
            -Wait
        $cookie = (Get-Content $tempOut -Raw -ErrorAction SilentlyContinue | Out-String).Trim()
    } finally {
        Remove-Item $tempOut -ErrorAction SilentlyContinue
    }

    if ($proc.ExitCode -ne 0 -or [string]::IsNullOrWhiteSpace($cookie) -or $cookie -notmatch "=") {
        Write-Host "  [warn] Automatic capture failed or was cancelled." -ForegroundColor Yellow
        return ""
    }

    $masked = $cookie -replace "=.*", "=***"
    Write-Host "  Session cookie captured: $masked" -ForegroundColor Green
    return $cookie
}

function Get-SessionCookie {
    <#
    .SYNOPSIS
        Prompt the user for a session cookie via browser login, manual paste, or skip.
    .PARAMETER Required
        When set, "skip" is not offered and the function always returns a non-empty value
        (or the caller must handle the empty-string fallback separately).
    #>
    param([switch] $Required)

    # If already set in the environment, use it without prompting.
    $existing = ($env:LOADTEST_SESSION_COOKIE | Out-String).Trim()
    if (-not [string]::IsNullOrWhiteSpace($existing)) {
        return $existing
    }

    Write-Host ""
    if ($Required) {
        Write-Host "  A session cookie is required for this operation." -ForegroundColor Yellow
    } else {
        Write-Host "  A session cookie enables authenticated routes (navigation, entry-form, auto-setup)."
        Write-Host "  Omit it to run health + API-key-only tests."
    }
    Write-Host "  [B] Open browser to log in  - cookie captured automatically  (recommended)"
    Write-Host "  [P] Paste a session=<value> cookie manually"
    if (-not $Required) {
        Write-Host "  [S] Skip (proceed without a session cookie)"
    }
    Write-Host ""

    $skipHint = if ($Required) { "" } else { "/S" }
    $opt = (Read-Host "  Choice [B/P$skipHint, default=B]").ToUpper().Trim()

    # Default to browser on blank input.
    if ([string]::IsNullOrWhiteSpace($opt)) { $opt = "B" }

    switch ($opt) {
        "B" {
            $cookie = Invoke-BrowserCookieCapture
            if ([string]::IsNullOrWhiteSpace($cookie)) {
                $cookie = (Read-Host "  Paste session=<value> cookie (or press Enter to skip)").Trim()
            }
            return $cookie
        }
        "P" {
            return (Read-Host "  Paste session=<value> cookie").Trim()
        }
        "S" {
            if ($Required) {
                Write-Host "  Cookie is required  - opening browser ..." -ForegroundColor Yellow
                $cookie = Invoke-BrowserCookieCapture
                if ([string]::IsNullOrWhiteSpace($cookie)) {
                    $cookie = (Read-Host "  Paste session=<value> cookie").Trim()
                }
                return $cookie
            }
            return ""
        }
        default {
            if ($Required) {
                Write-Host "  Cookie is required  - opening browser ..." -ForegroundColor Yellow
                $cookie = Invoke-BrowserCookieCapture
                if ([string]::IsNullOrWhiteSpace($cookie)) {
                    $cookie = (Read-Host "  Paste session=<value> cookie").Trim()
                }
                return $cookie
            }
            return ""
        }
    }
}

# ---------------------------------------------------------------------------
# Core Azure Load Testing operations
# ---------------------------------------------------------------------------
function Show-RecentRuns {
    if (-not (Ensure-AzureTools)) { Pause-Menu; return }

    Write-Host ""
    Write-Host "Recent runs for test $($script:ActiveEnv.TestId) [$($script:ActiveEnv.Name)]:"
    & az load test-run list `
        --load-test-resource $LoadTestResource `
        --resource-group $ResourceGroup `
        --test-id $script:ActiveEnv.TestId `
        --query 'reverse(sort_by([].{run:testRunId, status:status, start:startDateTime, duration_s:duration}, &start))[:5]' `
        -o table

    Pause-Menu
}

function Sync-Test {
    param(
        [int]    $Vus,
        [int]    $RunTimeSeconds,
        [string] $ApiKey,
        [string] $SessionCookie,
        [string] $AssignmentAesIds,
        [string] $DocumentIds,
        [string] $DiSectionId,
        [string] $DiIndicatorBankId,
        [string] $AutoSetup,
        [string] $SetupTemplateId,
        [string] $SetupCountryIds,
        [string] $SetupCount
    )

    $configFile = $script:ActiveEnv.ConfigFile
    if (-not (Test-Path -LiteralPath $configFile)) {
        Write-Host "[error] $configFile not found in $(Get-Location)." -ForegroundColor Red
        return $false
    }

    Write-Host ""
    Write-Host "Syncing test definition + scripts to Azure Load Testing [$($script:ActiveEnv.Name)] ..."

    $azArgs = @(
        "load", "test", "update",
        "--load-test-resource", $LoadTestResource,
        "--resource-group", $ResourceGroup,
        "--test-id", $script:ActiveEnv.TestId,
        "--load-test-config-file", $configFile
    )

    # Always inject the target host and allow-prod flag so the YAML defaults
    # cannot accidentally run against the wrong environment.
    $envOverrides = @(
        "LOADTEST_HOST=$($script:ActiveEnv.Host)",
        "LOADTEST_ALLOW_PROD=$($script:ActiveEnv.AllowProd)"
    )

    if ($Vus -gt 0 -and $RunTimeSeconds -gt 0) {
        $envOverrides += @("LOCUST_USERS=$Vus", "LOCUST_RUN_TIME=$RunTimeSeconds")
    }
    if (-not [string]::IsNullOrWhiteSpace($ApiKey))            { $envOverrides += "LOADTEST_API_KEY=$ApiKey" }
    if (-not [string]::IsNullOrWhiteSpace($SessionCookie))     { $envOverrides += "LOADTEST_SESSION_COOKIE=$SessionCookie" }
    if (-not [string]::IsNullOrWhiteSpace($AssignmentAesIds))  { $envOverrides += "LOADTEST_ASSIGNMENT_AES_IDS=$AssignmentAesIds" }
    if (-not [string]::IsNullOrWhiteSpace($DocumentIds))       { $envOverrides += "LOADTEST_DOCUMENT_IDS=$DocumentIds" }
    if (-not [string]::IsNullOrWhiteSpace($DiSectionId))       { $envOverrides += "LOADTEST_DI_SECTION_ID=$DiSectionId" }
    if (-not [string]::IsNullOrWhiteSpace($DiIndicatorBankId)) { $envOverrides += "LOADTEST_DI_INDICATOR_BANK_ID=$DiIndicatorBankId" }
    if (-not [string]::IsNullOrWhiteSpace($AutoSetup))         { $envOverrides += "LOADTEST_AUTO_SETUP=$AutoSetup" }
    if (-not [string]::IsNullOrWhiteSpace($SetupTemplateId))   { $envOverrides += "LOADTEST_SETUP_TEMPLATE_ID=$SetupTemplateId" }
    if (-not [string]::IsNullOrWhiteSpace($SetupCountryIds))   { $envOverrides += "LOADTEST_SETUP_COUNTRY_IDS=$SetupCountryIds" }
    if (-not [string]::IsNullOrWhiteSpace($SetupCount))        { $envOverrides += "LOADTEST_SETUP_COUNT=$SetupCount" }

    $azArgs += @("--env") + $envOverrides

    & az @azArgs
    if ($LASTEXITCODE -eq 0) { return $true }

    # Optional bootstrap fallback for brand-new test IDs.
    Write-Host ""
    Write-Host "'az load test update' failed. Retrying with 'az load test create' ..." -ForegroundColor Yellow
    $azArgs[2] = "create"
    & az @azArgs
    return ($LASTEXITCODE -eq 0)
}

function Start-TestRun {
    param([Parameter(Mandatory = $true)] [string] $DisplayName)

    $runId = "run-{0}" -f (Get-Date -Format "yyyyMMdd-HHmmss")

    Write-Host ""
    Write-Host "Triggering run $runId ($DisplayName) [$($script:ActiveEnv.Name)] ..."
    & az load test-run create `
        --load-test-resource $LoadTestResource `
        --resource-group $ResourceGroup `
        --test-id $script:ActiveEnv.TestId `
        --test-run-id $runId `
        --display-name $DisplayName `
        --description "Triggered via Backoffice Azure load test runner" `
        --query '{runId:testRunId,status:status,portalUrl:portalUrl}' `
        -o json

    if ($LASTEXITCODE -ne 0) {
        Write-Host "[error] Run trigger failed." -ForegroundColor Red
        return
    }

    Write-Host ""
    Write-Host "Run started: $runId"
    Write-Host "Portal: https://portal.azure.com/#@/resource/subscriptions/$Subscription/resourceGroups/$ResourceGroup/providers/Microsoft.LoadTestService/loadtests/$LoadTestResource/testRunDetail/$runId"
    Write-Host ""

    $tail = Read-Host "Tail status until done? (y/N)"
    if ($tail -notmatch "^(y|yes)$") { return }

    do {
        $status = (& az load test-run show `
            --load-test-resource $LoadTestResource `
            --resource-group $ResourceGroup `
            --test-run-id $runId `
            --query status `
            -o tsv 2>$null)
        Write-Host "  status: $status"
        if ($status -in @("DONE", "FAILED", "CANCELLED")) { break }
        Start-Sleep -Seconds 15
    } while ($true)
}

function Invoke-RunProfile {
    param(
        [Parameter(Mandatory = $true)] [string] $DisplayName,
        [int]  $Vus,
        [int]  $RunTimeSeconds,
        [bool] $Run
    )

    if (-not (Ensure-AzureTools)) { Pause-Menu; return }

    # Extra confirmation gate for every production run.
    $apiKey = $env:LOADTEST_API_KEY
    if ([string]::IsNullOrWhiteSpace($apiKey) -and $Run) {
        $apiKey = Read-Host "API key (optional - leave blank for health-only run)"
    }

    $sessionCookie = $env:LOADTEST_SESSION_COOKIE
    if ([string]::IsNullOrWhiteSpace($sessionCookie) -and $Run) {
        $sessionCookie = Get-SessionCookie
    }
    $hasSessionCookie = -not [string]::IsNullOrWhiteSpace($sessionCookie)

    # Auto-setup: on by default when a session cookie is provided on staging.
    # On production it is off by default  - require LOADTEST_AUTO_SETUP=true explicitly.
    $autoSetupOverride = ($env:LOADTEST_AUTO_SETUP | Out-String).Trim()
    $autoSetupDisabled = ($autoSetupOverride -match "^(0|false|no|off)$")
    $autoSetupEnabled  = ($autoSetupOverride -match "^(1|true|yes|on)$")

    $useAutoSetup = $hasSessionCookie -and -not $autoSetupDisabled
    if ($useAutoSetup -and $script:ActiveEnv.AllowProd -eq "true" -and -not $autoSetupEnabled) {
        $useAutoSetup = $false
        Write-Host ""
        Write-Host "  Auto-setup disabled by default on production." -ForegroundColor Yellow
        Write-Host "  Set LOADTEST_AUTO_SETUP=true to enable (creates real data on prod DB)." -ForegroundColor Yellow
    }

    $setupTemplateId   = ($env:LOADTEST_SETUP_TEMPLATE_ID    | Out-String).Trim()
    $setupCountryIds   = ($env:LOADTEST_SETUP_COUNTRY_IDS    | Out-String).Trim()
    $setupCount        = ($env:LOADTEST_SETUP_COUNT           | Out-String).Trim()
    $assignmentAesIds  = ($env:LOADTEST_ASSIGNMENT_AES_IDS   | Out-String).Trim()
    $documentIds       = ($env:LOADTEST_DOCUMENT_IDS          | Out-String).Trim()
    $diSectionId       = ($env:LOADTEST_DI_SECTION_ID         | Out-String).Trim()
    $diIndicatorBankId = ($env:LOADTEST_DI_INDICATOR_BANK_ID  | Out-String).Trim()

    $autoSetup = if ($useAutoSetup) { "true" } else { "" }

    if ($Run) {
        Write-Host ""
        Write-Host "  Target:        $($script:ActiveEnv.Name) ($($script:ActiveEnv.Host))"
        Write-Host "  API key:       $(if (-not [string]::IsNullOrWhiteSpace($apiKey)) { 'provided' } else { 'not set (health-only)' })"
        Write-Host "  Session:       $(if ($hasSessionCookie) { 'provided' } else { 'not set (entry-form tasks disabled)' })"
        if ($useAutoSetup) {
            $tmplDisplay  = if ([string]::IsNullOrWhiteSpace($setupTemplateId)) { 'auto-discover' } else { $setupTemplateId }
            $cntryDisplay = if ([string]::IsNullOrWhiteSpace($setupCountryIds)) { '193 (Testland)' } else { $setupCountryIds }
            $countDisplay = if ([string]::IsNullOrWhiteSpace($setupCount))      { '3' }             else { $setupCount }
            Write-Host "  Auto-setup:    ON  (template=$tmplDisplay  countries=$cntryDisplay  count=$countDisplay)" -ForegroundColor Cyan
        } else {
            Write-Host "  Auto-setup:    OFF  (set LOADTEST_AUTO_SETUP=true to enable)"
        }
        Write-Host ""
    }

    if (-not (Sync-Test `
            -Vus $Vus `
            -RunTimeSeconds $RunTimeSeconds `
            -ApiKey $apiKey `
            -SessionCookie $sessionCookie `
            -AssignmentAesIds $assignmentAesIds `
            -DocumentIds $documentIds `
            -DiSectionId $diSectionId `
            -DiIndicatorBankId $diIndicatorBankId `
            -AutoSetup $autoSetup `
            -SetupTemplateId $setupTemplateId `
            -SetupCountryIds $setupCountryIds `
            -SetupCount $setupCount)) {
        Write-Host "[error] Test sync failed." -ForegroundColor Red
        Pause-Menu
        return
    }

    if ($Run) {
        Start-TestRun -DisplayName "$DisplayName [$($script:ActiveEnv.Name)]"
    }

    Pause-Menu
}

function Open-Portal {
    $url = "https://portal.azure.com/#@/resource/subscriptions/$Subscription/resourceGroups/$ResourceGroup/providers/Microsoft.LoadTestService/loadtests/$LoadTestResource/overview"
    Start-Process $url
}

function Invoke-SetupTeardown {
    param(
        [Parameter(Mandatory = $true)] [ValidateSet("setup","teardown")] [string] $Mode
    )

    $py = if (Get-Command python -ErrorAction SilentlyContinue) { "python" }
          elseif (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" }
          else {
              Write-Host "[error] python / python3 not found on PATH." -ForegroundColor Red
              Pause-Menu; return
          }

    $script = Join-Path $PSScriptRoot "setup_loadtest_data.py"
    if (-not (Test-Path -LiteralPath $script)) {
        Write-Host "[error] setup_loadtest_data.py not found at $script" -ForegroundColor Red
        Pause-Menu; return
    }

    $sessionCookie = $env:LOADTEST_SESSION_COOKIE
    if ([string]::IsNullOrWhiteSpace($sessionCookie)) {
        $sessionCookie = Get-SessionCookie -Required
    }
    if ([string]::IsNullOrWhiteSpace($sessionCookie)) {
        Write-Host "[error] Session cookie is required." -ForegroundColor Red
        Pause-Menu; return
    }
    $env:LOADTEST_SESSION_COOKIE = $sessionCookie
    $env:LOADTEST_HOST           = $script:ActiveEnv.Host
    $env:LOADTEST_ALLOW_PROD     = $script:ActiveEnv.AllowProd

    if ($Mode -eq "setup") {
        $templateId = $env:LOADTEST_SETUP_TEMPLATE_ID
        if ([string]::IsNullOrWhiteSpace($templateId)) {
            $templateId = Read-Host "LOADTEST_SETUP_TEMPLATE_ID (leave blank to auto-discover)"
        }
        $countryIds = $env:LOADTEST_SETUP_COUNTRY_IDS
        if ([string]::IsNullOrWhiteSpace($countryIds)) {
            $countryIds = Read-Host "LOADTEST_SETUP_COUNTRY_IDS (blank = Testland 193)"
        }
        $count = $env:LOADTEST_SETUP_COUNT
        if ([string]::IsNullOrWhiteSpace($count)) {
            $count = Read-Host "Number of assignments to create [3]"
            if ([string]::IsNullOrWhiteSpace($count)) { $count = "3" }
        }
        $env:LOADTEST_SETUP_TEMPLATE_ID = $templateId
        $env:LOADTEST_SETUP_COUNTRY_IDS = $countryIds
        $env:LOADTEST_SETUP_COUNT       = $count

        Write-Host ""
        Write-Host "Running setup_loadtest_data.py setup [$($script:ActiveEnv.Name)] ..."
        & $py $script setup
    } else {
        Write-Host ""
        Write-Host "Running setup_loadtest_data.py teardown [$($script:ActiveEnv.Name)] ..."
        & $py $script teardown
    }

    Pause-Menu
}

function Get-RunLogs {
    if (-not (Ensure-AzureTools)) { Pause-Menu; return }

    Write-Host ""
    Write-Host "Recent runs [$($script:ActiveEnv.Name)]:"
    & az load test-run list `
        --load-test-resource $LoadTestResource `
        --resource-group $ResourceGroup `
        --test-id $script:ActiveEnv.TestId `
        --query 'reverse(sort_by([].{run:testRunId,status:status,start:startDateTime}, &start))[:10]' `
        -o table

    Write-Host ""
    $runId = (Read-Host "Run ID to fetch logs for (leave blank for latest)").Trim()

    if ([string]::IsNullOrWhiteSpace($runId)) {
        $runId = (& az load test-run list `
            --load-test-resource $LoadTestResource `
            --resource-group $ResourceGroup `
            --test-id $script:ActiveEnv.TestId `
            --query 'reverse(sort_by([].testRunId, &@))[0]' `
            -o tsv 2>$null)
        if ([string]::IsNullOrWhiteSpace($runId)) {
            Write-Host "[error] Could not determine latest run ID." -ForegroundColor Red
            Pause-Menu
            return
        }
        Write-Host "  Using latest run: $runId"
    }

    Write-Host ""
    Write-Host "Run details:" -ForegroundColor Cyan
    $runJson = (& az load test-run show `
        --load-test-resource $LoadTestResource `
        --resource-group $ResourceGroup `
        --test-run-id $runId `
        -o json 2>$null) | ConvertFrom-Json

    Write-Host "  Status  : $($runJson.status)"
    Write-Host "  Result  : $($runJson.testResult)"
    Write-Host "  Duration: $([Math]::Round($runJson.duration / 1000))s"
    if ($runJson.errorDetails) {
        Write-Host "  Errors  : $($runJson.errorDetails | ConvertTo-Json -Compress)" -ForegroundColor Red
    }
    Write-Host "  Portal  : $($runJson.portalUrl)"

    if ($runJson.testResult -eq 'NOT_APPLICABLE' -and -not $runJson.errorDetails) {
        Write-Host ""
        Write-Host "  Result is NOT_APPLICABLE - the test engine likely exited before any" -ForegroundColor Yellow
        Write-Host "  virtual users spawned (setup failure). No artifacts were generated." -ForegroundColor Yellow
        Write-Host "  Run a fresh test with the latest locustfile to get real results." -ForegroundColor Yellow
        Pause-Menu
        return
    }

    $outDir = Join-Path $PSScriptRoot "logs\$runId"
    Write-Host ""
    Write-Host "Downloading artifacts for $runId -> $outDir ..."
    & az load test-run download-files `
        --load-test-resource $LoadTestResource `
        --resource-group $ResourceGroup `
        --test-run-id $runId `
        --path $outDir `
        --force

    $zips = @(Get-ChildItem -Recurse -File $outDir -Filter "*.zip" -ErrorAction SilentlyContinue)
    if ($zips.Count -gt 0) {
        Write-Host ""
        Write-Host "Extracting $($zips.Count) ZIP archive(s)..." -ForegroundColor Cyan
        foreach ($z in $zips) {
            $dest = Join-Path $z.DirectoryName $z.BaseName
            Write-Host "  $($z.Name) -> $dest"
            Expand-Archive -LiteralPath $z.FullName -DestinationPath $dest -Force
        }
    }

    Write-Host ""
    Write-Host "Downloaded files:" -ForegroundColor Cyan
    Get-ChildItem -Recurse -File $outDir | ForEach-Object {
        Write-Host "  $($_.FullName.Substring($outDir.Length + 1))  ($([Math]::Round($_.Length/1KB,1)) KB)"
    }

    $logFiles = @(Get-ChildItem -Recurse -File $outDir | Where-Object {
        $_.Extension -in '.log', '.txt' -or $_.Name -match '(?i)log'
    } | Where-Object { $_.Extension -ne '.zip' })

    if ($logFiles.Count -eq 0) {
        Write-Host ""
        Write-Host "No log/text files found after extraction." -ForegroundColor Yellow
        Write-Host "Try opening the portal (option 7) to view engine logs online," -ForegroundColor Yellow
        Write-Host "or check the files listed above manually." -ForegroundColor Yellow
        Pause-Menu
        return
    }

    foreach ($lf in $logFiles) {
        Write-Host ""
        Write-Host "--------------------------------------------------" -ForegroundColor Cyan
        Write-Host " $($lf.Name)" -ForegroundColor Cyan
        Write-Host "--------------------------------------------------" -ForegroundColor Cyan
        Get-Content $lf.FullName | ForEach-Object {
            if ($_ -match '\[loadtest-failures\]\s+SAMPLE|\[loadtest-failure\]') {
                Write-Host $_ -ForegroundColor Magenta
            } elseif ($_ -match '\[loadtest-failures\]\s+SUMMARY') {
                Write-Host $_ -ForegroundColor Red
            } elseif ($_ -match '\bERROR\b|\bFAILED\b|\bexception\b' -and $_ -notmatch 'INFO') {
                Write-Host $_ -ForegroundColor Red
            } elseif ($_ -match '\bWARN(ING)?\b') {
                Write-Host $_ -ForegroundColor Yellow
            } elseif ($_ -match '\[auto-setup\]|\[auto-teardown\]') {
                Write-Host $_ -ForegroundColor Cyan
            } else {
                Write-Host $_
            }
        }
    }

    $failureSummary = @(Get-ChildItem -Recurse -File $outDir -Filter "failure_summary.json" -ErrorAction SilentlyContinue)
    if ($failureSummary.Count -gt 0) {
        Write-Host ""
        Write-Host "--------------------------------------------------" -ForegroundColor Magenta
        Write-Host " failure_summary.json (rich failure samples)" -ForegroundColor Magenta
        Write-Host "--------------------------------------------------" -ForegroundColor Magenta
        foreach ($fs in $failureSummary) {
            Write-Host "  $($fs.FullName)" -ForegroundColor Green
            try {
                $json = Get-Content $fs.FullName -Raw | ConvertFrom-Json
                Write-Host "  total_failures: $($json.total_failures)" -ForegroundColor Red
                if ($json.by_endpoint) {
                    $json.by_endpoint.PSObject.Properties | Sort-Object Name | ForEach-Object {
                        Write-Host "    $($_.Name): $($_.Value)" -ForegroundColor Yellow
                    }
                }
            } catch {
                Write-Host "  (could not parse JSON: $_)" -ForegroundColor Yellow
            }
        }
    }

    Write-Host ""
    Write-Host "Log folder: $outDir" -ForegroundColor Green
    Pause-Menu
}

# ---------------------------------------------------------------------------
# Main menu loop
# ---------------------------------------------------------------------------
while ($true) {
    Clear-Host
    Write-Host ""
    Write-Host "=============================================================="
    Write-Host " Humanitarian Databank - Azure Load Testing runner"
    Write-Host "=============================================================="
    Write-Host " Resource : $LoadTestResource   RG: $ResourceGroup"
    Write-Host " Test ID  : $($script:ActiveEnv.TestId)"
    Write-Host " Config   : $($script:ActiveEnv.ConfigFile)"
    if ($script:ActiveEnv.AllowProd -eq "true") {
        Write-Host " Target   : *** PRODUCTION ***  $($script:ActiveEnv.Host)" -ForegroundColor Red
    } else {
        Write-Host " Target   : Staging  $($script:ActiveEnv.Host)" -ForegroundColor Green
    }
    Write-Host "=============================================================="
    Write-Host "  1. Smoke       (5 VUs,  60s)  - sync + run"
    Write-Host "  2. Default     ($($script:ActiveEnv.DefaultVus) VUs, $($script:ActiveEnv.DefaultSec)s) - sync + run"
    if ($script:ActiveEnv.AllowProd -eq "true") {
        Write-Host "  3. Heavy       (50 VUs, 300s) - sync + run  [REQUIRES OPS APPROVAL]" -ForegroundColor Red
    } else {
        Write-Host "  3. Heavy       (50 VUs, 300s) - sync + run  (coordinate w/ ops)"
    }
    Write-Host "  4. Custom      (enter VUs + duration) - sync + run"
    Write-Host "  5. Sync only   (upload YAML + locustfile, no run)"
    Write-Host "  6. Show last 5 runs"
    Write-Host "  7. Open test in portal"
    Write-Host "  8. Fetch & show logs for a run"
    Write-Host "  E. Switch environment  (currently: $($script:ActiveEnv.Name))"
    Write-Host "  Q. Quit"
    Write-Host "=============================================================="
    Write-Host "  Auto-setup: set LOADTEST_AUTO_SETUP=true to create and"
    Write-Host "  clean up [LOADTEST] assignments automatically each run."
    Write-Host "=============================================================="
    Write-Host ""

    $choice = Read-Host "Select option [1-8 / E / Q]"
    switch ($choice.ToUpper()) {
        "1" { Invoke-RunProfile -DisplayName "Smoke" -Vus 5 -RunTimeSeconds 60 -Run $true }
        "2" { Invoke-RunProfile -DisplayName "Default $($script:ActiveEnv.Name)" -Vus $script:ActiveEnv.DefaultVus -RunTimeSeconds $script:ActiveEnv.DefaultSec -Run $true }
        "3" { Invoke-RunProfile -DisplayName "Heavy $($script:ActiveEnv.Name)" -Vus 50 -RunTimeSeconds 300 -Run $true }
        "4" {
            $vusInput  = Read-Host "  Number of VUs [$($script:ActiveEnv.DefaultVus)]"
            $timeInput = Read-Host "  Run time in seconds [$($script:ActiveEnv.DefaultSec)]"
            $vus     = if ([string]::IsNullOrWhiteSpace($vusInput))  { $script:ActiveEnv.DefaultVus } else { [int]$vusInput }
            $runTime = if ([string]::IsNullOrWhiteSpace($timeInput)) { $script:ActiveEnv.DefaultSec } else { [int]$timeInput }
            Invoke-RunProfile -DisplayName "Custom $($script:ActiveEnv.Name) ($vus VUs / ${runTime}s)" -Vus $vus -RunTimeSeconds $runTime -Run $true
        }
        "5" { Invoke-RunProfile -DisplayName "Sync only" -Vus 0 -RunTimeSeconds 0 -Run $false }
        "6" { Show-RecentRuns }
        "7" { Open-Portal }
        "8" { Get-RunLogs }
        "E" { Select-Environment }
        "Q" { exit 0 }
        default {
            Write-Host "Invalid choice."
            Start-Sleep -Seconds 1
        }
    }
}
