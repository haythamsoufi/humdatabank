# Azure Deployment Script for Humanitarian Databank
# PowerShell script to automate Azure resource creation and deployment
#
# USAGE: Run this script from the Backoffice/azure directory
#   cd Backoffice/azure
#   .\azure-deploy.ps1
#
# Or from the Backoffice directory:
#   .\azure\azure-deploy.ps1

param(
    [string]$ResourceGroup = "rg-ifrc-databank-prod",
    [string]$Location = "eastus",
    [string]$Environment = "production"
)

# Color output functions
function Write-Success { Write-Host $args -ForegroundColor Green }
function Write-Info { Write-Host $args -ForegroundColor Cyan }
function Write-Warning { Write-Host $args -ForegroundColor Yellow }
function Write-Error { Write-Host $args -ForegroundColor Red }

Write-Info "=========================================="
Write-Info "Humanitarian Databank - Azure Deployment"
Write-Info "=========================================="
Write-Info ""

# Check if Azure CLI is installed
try {
    $azVersion = az --version
    Write-Success "✓ Azure CLI is installed"
} catch {
    Write-Error "✗ Azure CLI is not installed. Please install from: https://aka.ms/installazurecliwindows"
    exit 1
}

# Check if logged in to Azure
Write-Info "Checking Azure authentication..."
$account = az account show 2>$null
if (-not $account) {
    Write-Warning "Not logged in to Azure. Initiating login..."
    az login
    if ($LASTEXITCODE -ne 0) {
        Write-Error "✗ Azure login failed"
        exit 1
    }
}
Write-Success "✓ Authenticated with Azure"

# Display current subscription
$subscription = az account show --query name -o tsv
Write-Info "Current subscription: $subscription"
$confirm = Read-Host "Continue with this subscription? (y/n)"
if ($confirm -ne 'y') {
    Write-Info "Available subscriptions:"
    az account list --output table
    $subId = Read-Host "Enter subscription ID to use"
    az account set --subscription $subId
}

Write-Info ""
Write-Info "=========================================="
Write-Info "Configuration"
Write-Info "=========================================="
Write-Info "Resource Group: $ResourceGroup"
Write-Info "Location: $Location"
Write-Info "Environment: $Environment"
Write-Info ""

# Generate unique names
$timestamp = Get-Date -Format "yyyyMMdd"
$uniqueId = -join ((48..57) + (97..122) | Get-Random -Count 6 | ForEach-Object {[char]$_})

$postgresServer = "ifrc-databank-db-$Environment-$uniqueId"
$storageAccount = "ifrcstor$uniqueId"
$appServicePlan = "asp-ifrc-databank-$Environment"
$webAppName = "ifrc-databank-$Environment-$uniqueId"
$appInsights = "ai-ifrc-databank-$Environment"

Write-Info "Generated resource names:"
Write-Info "  PostgreSQL: $postgresServer"
Write-Info "  Storage: $storageAccount"
Write-Info "  App Service: $webAppName"
Write-Info ""

$confirm = Read-Host "Proceed with deployment? (y/n)"
if ($confirm -ne 'y') {
    Write-Warning "Deployment cancelled"
    exit 0
}

# Step 1: Create Resource Group
Write-Info ""
Write-Info "Step 1: Creating Resource Group..."
az group create --name $ResourceGroup --location $Location --output none
if ($LASTEXITCODE -eq 0) {
    Write-Success "✓ Resource Group created: $ResourceGroup"
} else {
    Write-Error "✗ Failed to create Resource Group"
    exit 1
}

# Step 2: Create PostgreSQL Server
Write-Info ""
Write-Info "Step 2: Creating PostgreSQL Flexible Server..."
Write-Warning "This may take 5-10 minutes..."

# Generate strong password
$postgresPassword = -join ((33..126) | Get-Random -Count 16 | ForEach-Object {[char]$_})
$postgresAdmin = "ifrcadmin"

az postgres flexible-server create `
    --resource-group $ResourceGroup `
    --name $postgresServer `
    --location $Location `
    --admin-user $postgresAdmin `
    --admin-password $postgresPassword `
    --sku-name Standard_B2ms `
    --tier Burstable `
    --version 15 `
    --storage-size 32 `
    --public-access "0.0.0.0" `
    --backup-retention 7 `
    --yes `
    --output none

if ($LASTEXITCODE -eq 0) {
    Write-Success "✓ PostgreSQL Server created: $postgresServer"
    Write-Success "  Admin: $postgresAdmin"
    Write-Warning "  Password: $postgresPassword (SAVE THIS!)"
} else {
    Write-Error "✗ Failed to create PostgreSQL Server"
    exit 1
}

# Create database
Write-Info "Creating database..."
az postgres flexible-server db create `
    --resource-group $ResourceGroup `
    --server-name $postgresServer `
    --database-name ifrc_databank `
    --output none

if ($LASTEXITCODE -eq 0) {
    Write-Success "✓ Database created: ifrc_databank"
}

# Configure firewall
Write-Info "Configuring firewall rules..."
az postgres flexible-server firewall-rule create `
    --resource-group $ResourceGroup `
    --name $postgresServer `
    --rule-name AllowAzureServices `
    --start-ip-address 0.0.0.0 `
    --end-ip-address 0.0.0.0 `
    --output none

Write-Success "✓ Firewall configured"

# Step 3: Create Storage Account
Write-Info ""
Write-Info "Step 3: Creating Storage Account..."
az storage account create `
    --name $storageAccount `
    --resource-group $ResourceGroup `
    --location $Location `
    --sku Standard_LRS `
    --kind StorageV2 `
    --output none

if ($LASTEXITCODE -eq 0) {
    Write-Success "✓ Storage Account created: $storageAccount"
}

# Create container
$storageConnectionString = az storage account show-connection-string `
    --name $storageAccount `
    --resource-group $ResourceGroup `
    --output tsv

az storage container create `
    --name uploads `
    --connection-string $storageConnectionString `
    --public-access off `
    --output none

Write-Success "✓ Storage container created: uploads"

# Step 4: Create App Service Plan
Write-Info ""
Write-Info "Step 4: Creating App Service Plan..."
az appservice plan create `
    --name $appServicePlan `
    --resource-group $ResourceGroup `
    --location $Location `
    --is-linux `
    --sku P1v3 `
    --output none

if ($LASTEXITCODE -eq 0) {
    Write-Success "✓ App Service Plan created: $appServicePlan"
}

# Step 5: Create Web App
Write-Info ""
Write-Info "Step 5: Creating Web App..."
az webapp create `
    --resource-group $ResourceGroup `
    --plan $appServicePlan `
    --name $webAppName `
    --runtime "PYTHON:3.11" `
    --output none

if ($LASTEXITCODE -eq 0) {
    Write-Success "✓ Web App created: $webAppName"
}

# Step 6: Create Application Insights
Write-Info ""
Write-Info "Step 6: Creating Application Insights..."
az monitor app-insights component create `
    --app $appInsights `
    --location $Location `
    --resource-group $ResourceGroup `
    --application-type web `
    --output none

if ($LASTEXITCODE -eq 0) {
    Write-Success "✓ Application Insights created: $appInsights"
}

$appInsightsKey = az monitor app-insights component show `
    --app $appInsights `
    --resource-group $ResourceGroup `
    --query instrumentationKey `
    --output tsv

# Step 7: Configure Web App Settings
Write-Info ""
Write-Info "Step 7: Configuring Web App Settings..."

# Generate SECRET_KEY
$secretKey = -join ((33..126) | Get-Random -Count 32 | ForEach-Object {[char]$_})

# Generate API_KEY
$apiKey = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 32 | ForEach-Object {[char]$_})

# Build DATABASE_URL
$databaseUrl = "postgresql+psycopg2://${postgresAdmin}:${postgresPassword}@${postgresServer}.postgres.database.azure.com:5432/ifrc_databank?sslmode=require"

az webapp config appsettings set `
    --resource-group $ResourceGroup `
    --name $webAppName `
    --settings `
        FLASK_CONFIG="production" `
        FLASK_APP="run:app" `
        SECRET_KEY="$secretKey" `
        DATABASE_URL="$databaseUrl" `
        API_KEY="$apiKey" `
        SCM_DO_BUILD_DURING_DEPLOYMENT="true" `
        ENABLE_ORYX_BUILD="true" `
        POST_BUILD_COMMAND="npm install && npm run build:css" `
        WEBSITES_PORT="5000" `
        APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=$appInsightsKey" `
        UPLOAD_FOLDER="/home/site/wwwroot/uploads" `
        AZURE_STORAGE_CONNECTION_STRING="$storageConnectionString" `
        AZURE_STORAGE_CONTAINER="uploads" `
        BASE_URL="https://$webAppName.azurewebsites.net" `
        SECURITY_HEADERS_ENABLED="true" `
        SQLALCHEMY_POOL_SIZE="10" `
        SQLALCHEMY_MAX_OVERFLOW="20" `
        WEB_CONCURRENCY="4" `
    --output none

Write-Success "✓ App Settings configured"

# Configure general settings
Write-Info "Configuring general settings..."
az webapp config set `
    --resource-group $ResourceGroup `
    --name $webAppName `
    --always-on true `
    --http20-enabled true `
    --min-tls-version "1.2" `
    --ftps-state Disabled `
    --startup-file "startup.sh" `
    --output none

az webapp update `
    --resource-group $ResourceGroup `
    --name $webAppName `
    --client-affinity-enabled false `
    --output none

Write-Success "✓ General settings configured"

# Step 8: Summary
Write-Info ""
Write-Info "=========================================="
Write-Success "Deployment Complete!"
Write-Info "=========================================="
Write-Info ""
Write-Info "Resources created:"
Write-Info "  Resource Group: $ResourceGroup"
Write-Info "  PostgreSQL Server: $postgresServer"
Write-Info "  Database: ifrc_databank"
Write-Info "  Storage Account: $storageAccount"
Write-Info "  App Service Plan: $appServicePlan"
Write-Info "  Web App: $webAppName"
Write-Info "  Application Insights: $appInsights"
Write-Info ""
Write-Info "Web App URL: https://$webAppName.azurewebsites.net"
Write-Info ""
Write-Warning "=========================================="
Write-Warning "IMPORTANT: Save these credentials!"
Write-Warning "=========================================="
Write-Warning "PostgreSQL Admin: $postgresAdmin"
Write-Warning "PostgreSQL Password: $postgresPassword"
Write-Warning "SECRET_KEY: $secretKey"
Write-Warning "API_KEY: $apiKey"
Write-Warning ""
Write-Warning "Save these to a secure location NOW!"
Write-Warning "=========================================="
Write-Info ""
Write-Info "Next steps:"
Write-Info "1. Configure additional settings (email, AI keys, etc.) in Azure Portal"
Write-Info "2. Migrate your database using pg_restore"
Write-Info "3. Deploy your application from Backoffice directory:"
Write-Info "   cd .. (to Backoffice root)"
Write-Info "   git push azure main:master"
Write-Info "4. Create admin user: az webapp ssh and run 'flask create-admin'"
Write-Info ""
Write-Info "For detailed instructions, see azure/AZURE_DEPLOYMENT_GUIDE.md"
Write-Info ""

# Save credentials to file
$credsFile = "azure-credentials-$timestamp.txt"
@"
========================================
Azure Deployment Credentials
Generated: $(Get-Date)
========================================

Resource Group: $ResourceGroup
Location: $Location

PostgreSQL Server: $postgresServer
PostgreSQL Admin: $postgresAdmin
PostgreSQL Password: $postgresPassword
Database Name: ifrc_databank
Connection String: $databaseUrl

Web App: $webAppName
Web App URL: https://$webAppName.azurewebsites.net

SECRET_KEY: $secretKey
API_KEY: $apiKey

Application Insights Key: $appInsightsKey

Storage Account: $storageAccount

========================================
KEEP THIS FILE SECURE AND PRIVATE!
========================================
"@ | Out-File -FilePath $credsFile -Encoding UTF8

Write-Success "Credentials saved to: $credsFile"
Write-Warning "Delete this file after saving credentials to a secure location!"
