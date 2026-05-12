param()

$ErrorActionPreference = "Continue"

$Subscription = "f585c1c3-801b-4641-8d7f-145aa50ffb04"
$ResourceGroup = "ifrctgo001rg"
$LoadTestResource = "DatabankTest1"
$TestId = "47c51031-8a61-41ec-b48d-2018263200f1"
$ConfigFile = "loadtest.config.yaml"

Set-Location -LiteralPath $PSScriptRoot

function Pause-Menu {
    Write-Host ""
    Read-Host "Press Enter to continue" | Out-Null
}

function Invoke-Az {
    param(
        [Parameter(Mandatory = $true)]
        [string[]] $ArgsList
    )
    & az @ArgsList
    return $LASTEXITCODE
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

function Show-RecentRuns {
    if (-not (Ensure-AzureTools)) {
        Pause-Menu
        return
    }

    Write-Host ""
    Write-Host "Recent runs for test ${TestId}:"
    & az load test-run list `
        --load-test-resource $LoadTestResource `
        --resource-group $ResourceGroup `
        --test-id $TestId `
        --query "reverse(sort_by([].{run:testRunId, status:status, start:startDateTime, duration_s:duration}, &start))[:5]" `
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
        [string] $SubmitAesIds,
        [string] $DocumentIds,
        [string] $DiSectionId,
        [string] $DiIndicatorBankId,
        # Auto-setup params
        [string] $AutoSetup,
        [string] $SetupTemplateId,
        [string] $SetupCountryIds,
        [string] $SetupCount
    )

    if (-not (Test-Path -LiteralPath $ConfigFile)) {
        Write-Host "[error] $ConfigFile not found in $(Get-Location)." -ForegroundColor Red
        return $false
    }

    Write-Host ""
    Write-Host "Syncing test definition + scripts to Azure Load Testing ..."

    $args = @(
        "load", "test", "update",
        "--load-test-resource", $LoadTestResource,
        "--resource-group", $ResourceGroup,
        "--test-id", $TestId,
        "--load-test-config-file", $ConfigFile
    )

    $envOverrides = @()
    if ($Vus -gt 0 -and $RunTimeSeconds -gt 0) {
        $envOverrides += @("LOCUST_USERS=$Vus", "LOCUST_RUN_TIME=$RunTimeSeconds")
    }
    if (-not [string]::IsNullOrWhiteSpace($ApiKey)) {
        $envOverrides += "LOADTEST_API_KEY=$ApiKey"
    }
    if (-not [string]::IsNullOrWhiteSpace($SessionCookie)) {
        $envOverrides += "LOADTEST_SESSION_COOKIE=$SessionCookie"
    }
    if (-not [string]::IsNullOrWhiteSpace($AssignmentAesIds)) {
        $envOverrides += "LOADTEST_ASSIGNMENT_AES_IDS=$AssignmentAesIds"
    }
    if (-not [string]::IsNullOrWhiteSpace($SubmitAesIds)) {
        $envOverrides += "LOADTEST_SUBMIT_AES_IDS=$SubmitAesIds"
    }
    if (-not [string]::IsNullOrWhiteSpace($DocumentIds)) {
        $envOverrides += "LOADTEST_DOCUMENT_IDS=$DocumentIds"
    }
    if (-not [string]::IsNullOrWhiteSpace($DiSectionId)) {
        $envOverrides += "LOADTEST_DI_SECTION_ID=$DiSectionId"
    }
    if (-not [string]::IsNullOrWhiteSpace($DiIndicatorBankId)) {
        $envOverrides += "LOADTEST_DI_INDICATOR_BANK_ID=$DiIndicatorBankId"
    }
    if (-not [string]::IsNullOrWhiteSpace($AutoSetup)) {
        $envOverrides += "LOADTEST_AUTO_SETUP=$AutoSetup"
    }
    if (-not [string]::IsNullOrWhiteSpace($SetupTemplateId)) {
        $envOverrides += "LOADTEST_SETUP_TEMPLATE_ID=$SetupTemplateId"
    }
    if (-not [string]::IsNullOrWhiteSpace($SetupCountryIds)) {
        $envOverrides += "LOADTEST_SETUP_COUNTRY_IDS=$SetupCountryIds"
    }
    if (-not [string]::IsNullOrWhiteSpace($SetupCount)) {
        $envOverrides += "LOADTEST_SETUP_COUNT=$SetupCount"
    }
    if ($envOverrides.Count -gt 0) {
        $args += @("--env") + $envOverrides
    }

    & az @args
    if ($LASTEXITCODE -eq 0) {
        return $true
    }

    # Optional bootstrap fallback for brand-new test IDs.
    # In normal use this test already exists, so update is the right default.
    Write-Host ""
    Write-Host "'az load test update' failed. Retrying with 'az load test create' ..." -ForegroundColor Yellow
    $args[2] = "create"
    & az @args
    return ($LASTEXITCODE -eq 0)
}

function Start-TestRun {
    param(
        [Parameter(Mandatory = $true)] [string] $DisplayName
    )

    $runId = "run-{0}" -f (Get-Date -Format "yyyyMMdd-HHmmss")

    $runDisplayName = $DisplayName

    Write-Host ""
    Write-Host "Triggering run $runId ($runDisplayName) ..."
    & az load test-run create `
        --load-test-resource $LoadTestResource `
        --resource-group $ResourceGroup `
        --test-id $TestId `
        --test-run-id $runId `
        --display-name $runDisplayName `
        --description "Triggered via Backoffice Azure load test runner" `
        --query "{runId:testRunId,status:status,portalUrl:portalUrl}" `
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
    if ($tail -notmatch "^(y|yes)$") {
        return
    }

    do {
        $status = (& az load test-run show `
            --load-test-resource $LoadTestResource `
            --resource-group $ResourceGroup `
            --test-run-id $runId `
            --query status `
            -o tsv 2>$null)
        Write-Host "  status: $status"
        if ($status -in @("DONE", "FAILED", "CANCELLED")) {
            break
        }
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

    if (-not (Ensure-AzureTools)) {
        Pause-Menu
        return
    }

    # --- Two prompts only. Everything else comes from env vars or is auto-discovered. ---

    $apiKey = $env:LOADTEST_API_KEY
    if ([string]::IsNullOrWhiteSpace($apiKey) -and $Run) {
        $apiKey = Read-Host "API key (optional - leave blank for health-only run)"
    }

    $sessionCookie = $env:LOADTEST_SESSION_COOKIE
    if ([string]::IsNullOrWhiteSpace($sessionCookie) -and $Run) {
        $sessionCookie = Read-Host "Session cookie (optional - enables entry-form tasks and auto-setup)"
    }
    $hasSessionCookie = -not [string]::IsNullOrWhiteSpace($sessionCookie)

    # --- Auto-setup: on by default when a session cookie is provided. ---
    # Override by setting LOADTEST_AUTO_SETUP=false in env before running.
    $autoSetupOverride = ($env:LOADTEST_AUTO_SETUP | Out-String).Trim()
    $autoSetupDisabled = ($autoSetupOverride -match "^(0|false|no|off)$")
    $useAutoSetup = $hasSessionCookie -and -not $autoSetupDisabled

    # Advanced env-var-only options (no prompts -- set in env before running if needed):
    #   LOADTEST_SETUP_TEMPLATE_ID   auto-discovered when blank
    #   LOADTEST_SETUP_COUNTRY_IDS   auto-discovered when blank
    #   LOADTEST_SETUP_COUNT         default 3
    #   LOADTEST_SUBMIT_AES_IDS      submit/reopen cycle pool
    #   LOADTEST_DOCUMENT_IDS        document download pool
    #   LOADTEST_DI_SECTION_ID       dynamic indicator section
    #   LOADTEST_DI_INDICATOR_BANK_ID

    $setupTemplateId   = ($env:LOADTEST_SETUP_TEMPLATE_ID    | Out-String).Trim()
    $setupCountryIds   = ($env:LOADTEST_SETUP_COUNTRY_IDS    | Out-String).Trim()
    $setupCount        = ($env:LOADTEST_SETUP_COUNT           | Out-String).Trim()
    $assignmentAesIds  = ($env:LOADTEST_ASSIGNMENT_AES_IDS   | Out-String).Trim()
    $submitAesIds      = ($env:LOADTEST_SUBMIT_AES_IDS        | Out-String).Trim()
    $documentIds       = ($env:LOADTEST_DOCUMENT_IDS          | Out-String).Trim()
    $diSectionId       = ($env:LOADTEST_DI_SECTION_ID         | Out-String).Trim()
    $diIndicatorBankId = ($env:LOADTEST_DI_INDICATOR_BANK_ID  | Out-String).Trim()

    $autoSetup = if ($useAutoSetup) { "true" } else { "" }

    if ($Run) {
        Write-Host ""
        Write-Host "  API key:       $(if (-not [string]::IsNullOrWhiteSpace($apiKey)) { 'provided' } else { 'not set (health-only)' })"
        Write-Host "  Session:       $(if ($hasSessionCookie) { 'provided' } else { 'not set (entry-form tasks disabled)' })"
        if ($useAutoSetup) {
            $tmplDisplay = if ([string]::IsNullOrWhiteSpace($setupTemplateId)) { 'auto-discover' } else { $setupTemplateId }
            $cntryDisplay = if ([string]::IsNullOrWhiteSpace($setupCountryIds)) { 'auto-discover' } else { $setupCountryIds }
            $countDisplay = if ([string]::IsNullOrWhiteSpace($setupCount)) { '3' } else { $setupCount }
            Write-Host "  Auto-setup:    ON  (template=$tmplDisplay  countries=$cntryDisplay  count=$countDisplay)" -ForegroundColor Cyan
        } else {
            Write-Host "  Auto-setup:    OFF  (set LOADTEST_AUTO_SETUP=false to keep this behaviour)"
        }
        Write-Host ""
    }

    if (-not (Sync-Test `
            -Vus $Vus `
            -RunTimeSeconds $RunTimeSeconds `
            -ApiKey $apiKey `
            -SessionCookie $sessionCookie `
            -AssignmentAesIds $assignmentAesIds `
            -SubmitAesIds $submitAesIds `
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
        Start-TestRun -DisplayName $DisplayName
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

    # Resolve python executable
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
        $sessionCookie = Read-Host "LOADTEST_SESSION_COOKIE (required - captured post-B2C session cookie)"
    }
    if ([string]::IsNullOrWhiteSpace($sessionCookie)) {
        Write-Host "[error] Session cookie is required." -ForegroundColor Red
        Pause-Menu; return
    }
    $env:LOADTEST_SESSION_COOKIE = $sessionCookie

    if ($Mode -eq "setup") {
        $templateId = $env:LOADTEST_SETUP_TEMPLATE_ID
        if ([string]::IsNullOrWhiteSpace($templateId)) {
            $templateId = Read-Host "LOADTEST_SETUP_TEMPLATE_ID (leave blank to auto-discover)"
        }
        $countryIds = $env:LOADTEST_SETUP_COUNTRY_IDS
        if ([string]::IsNullOrWhiteSpace($countryIds)) {
            $countryIds = Read-Host "LOADTEST_SETUP_COUNTRY_IDS (leave blank to auto-discover, e.g. 5,12)"
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
        Write-Host "Running setup_loadtest_data.py setup ..."
        & $py $script setup
    } else {
        Write-Host ""
        Write-Host "Running setup_loadtest_data.py teardown ..."
        & $py $script teardown
    }

    Pause-Menu
}

function Get-RunLogs {
    if (-not (Ensure-AzureTools)) {
        Pause-Menu
        return
    }

    # Let user pick a run, defaulting to the most recent.
    Write-Host ""
    Write-Host "Recent runs:"
    & az load test-run list `
        --load-test-resource $LoadTestResource `
        --resource-group $ResourceGroup `
        --test-id $TestId `
        --query "reverse(sort_by([].{run:testRunId,status:status,start:startDateTime}, &start))[:10]" `
        -o table

    Write-Host ""
    $runId = (Read-Host "Run ID to fetch logs for (leave blank for latest)").Trim()

    if ([string]::IsNullOrWhiteSpace($runId)) {
        $runId = (& az load test-run list `
            --load-test-resource $LoadTestResource `
            --resource-group $ResourceGroup `
            --test-id $TestId `
            --query "reverse(sort_by([].testRunId, &@))[0]" `
            -o tsv 2>$null)
        if ([string]::IsNullOrWhiteSpace($runId)) {
            Write-Host "[error] Could not determine latest run ID." -ForegroundColor Red
            Pause-Menu
            return
        }
        Write-Host "  Using latest run: $runId"
    }

    # Show run summary first so we know what we're looking at.
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

    # Download all artifacts for this run into a local folder.
    $outDir = Join-Path $PSScriptRoot "logs\$runId"
    Write-Host ""
    Write-Host "Downloading artifacts for $runId -> $outDir ..."
    & az load test-run download-files `
        --load-test-resource $LoadTestResource `
        --resource-group $ResourceGroup `
        --test-run-id $runId `
        --path $outDir `
        --force
    # Non-zero exit here just means no files; don't abort - fall through to check dir.

    # Azure Load Testing delivers artifacts as ZIP files. Extract any found.
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

    # Collect log / text files (including those extracted from ZIPs above).
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
            # Colour-code key lines for quick scanning.
            if ($_ -match '\bERROR\b|\bFAILED\b|\bexception\b' -and $_ -notmatch 'INFO') {
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

    Write-Host ""
    Write-Host "Log folder: $outDir" -ForegroundColor Green
    Pause-Menu
}


while ($true) {
    Clear-Host
    Write-Host ""
    Write-Host "=============================================================="
    Write-Host " Humanitarian Databank - Azure Load Testing runner"
    Write-Host "=============================================================="
    Write-Host " Resource : $LoadTestResource   RG: $ResourceGroup"
    Write-Host " Test ID  : $TestId"
    Write-Host " Config   : $ConfigFile"
    Write-Host "=============================================================="
    Write-Host "  1. Smoke       (5 VUs,  60s)  - sync + run"
    Write-Host "  2. Default     (20 VUs, 120s) - sync + run  (matches YAML)"
    Write-Host "  3. Heavy       (50 VUs, 300s) - sync + run  (coordinate w/ ops)"
    Write-Host "  4. Custom      (enter VUs + duration) - sync + run"
    Write-Host "  5. Sync only   (upload YAML + locustfile, no run)"
    Write-Host "  6. Show last 5 runs"
    Write-Host "  7. Open test in portal"
    Write-Host "  8. Fetch & show logs for a run"
    Write-Host "  Q. Quit"
    Write-Host "=============================================================="
    Write-Host "  Auto-setup: set LOADTEST_AUTO_SETUP=true to create and"
    Write-Host "  clean up [LOADTEST] assignments automatically each run."
    Write-Host "=============================================================="
    Write-Host ""

    $choice = Read-Host "Select option [1-8 / Q]"
    switch ($choice.ToUpper()) {
        "1" { Invoke-RunProfile -DisplayName "Smoke" -Vus 5 -RunTimeSeconds 60 -Run $true }
        "2" { Invoke-RunProfile -DisplayName "Default staging" -Vus 20 -RunTimeSeconds 120 -Run $true }
        "3" { Invoke-RunProfile -DisplayName "Heavy staging" -Vus 50 -RunTimeSeconds 300 -Run $true }
        "4" {
            $vusInput = Read-Host "  Number of VUs [20]"
            $timeInput = Read-Host "  Run time in seconds [120]"
            $vus = if ([string]::IsNullOrWhiteSpace($vusInput)) { 20 } else { [int]$vusInput }
            $runTime = if ([string]::IsNullOrWhiteSpace($timeInput)) { 120 } else { [int]$timeInput }
            Invoke-RunProfile -DisplayName "Custom ($vus VUs / ${runTime}s)" -Vus $vus -RunTimeSeconds $runTime -Run $true
        }
        "5" { Invoke-RunProfile -DisplayName "Sync only" -Vus 0 -RunTimeSeconds 0 -Run $false }
        "6" { Show-RecentRuns }
        "7" { Open-Portal }
        "8" { Get-RunLogs }
        "Q" { exit 0 }
        default {
            Write-Host "Invalid choice."
            Start-Sleep -Seconds 1
        }
    }
}
