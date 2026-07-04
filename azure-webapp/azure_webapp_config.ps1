# Shared Azure App Service environment settings for IFRC Databank tooling.
# Edit here when web app names, resource groups, or subscriptions change.
# Lives in azure-webapp/; repo root is one level up.

$script:AzureWebAppToolsRoot = $PSScriptRoot
$script:AzureWebAppRepoRoot = Split-Path -Parent $PSScriptRoot
$script:AzureWebAppEnvironments = @{
    PROD = @{
        Label          = 'PROD'
        WebApp         = 'ifrc-databank-app'
        ResourceGroup  = 'ifrcpunifiedplanning-rg001'
        Subscription   = '3e33b4c1-ada7-4922-9113-b9e41eaf1797'
        Port           = 50222
    }
    STAGING = @{
        Label          = 'STAGING'
        WebApp         = 'ifrc-databank-staging-2'
        ResourceGroup  = 'ifrctgo001rg'
        Subscription   = 'f585c1c3-801b-4641-8d7f-145aa50ffb04'
        Port           = 50223
    }
}

# Shared container registry (not in Non-Prod subscription).
$script:AzureWebAppAcrSubscription = '3e33b4c1-ada7-4922-9113-b9e41eaf1797'

function Resolve-AzureWebAppEnvironment {
    param(
        [Parameter(Mandatory = $true)]
        [ValidateSet('PROD', 'STAGING')]
        [string]$Name
    )
    return $script:AzureWebAppEnvironments[$Name.ToUpper()]
}

function Get-AzureWebAppRepoRoot {
    return $script:AzureWebAppRepoRoot
}

function Get-AzureWebAppToolsRoot {
    return $script:AzureWebAppToolsRoot
}
function Get-AzureWebAppBackofficeRoot {
    return Join-Path (Get-AzureWebAppRepoRoot) 'Backoffice'
}
