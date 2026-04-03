#!/bin/bash
# Azure Deployment Script for NGO Databank
# Bash script to automate Azure resource creation and deployment
#
# USAGE: Run this script from the Backoffice/azure directory
#   cd Backoffice/azure
#   chmod +x azure-deploy.sh
#   ./azure-deploy.sh
#
# Or from the Backoffice directory:
#   chmod +x azure/azure-deploy.sh
#   ./azure/azure-deploy.sh

set -e  # Exit on error

# Default parameters (can be overridden)
RESOURCE_GROUP="${1:-rg-ifrc-databank-prod}"
LOCATION="${2:-eastus}"
ENVIRONMENT="${3:-production}"

# Color output functions
print_success() { echo -e "\033[0;32m$*\033[0m"; }
print_info() { echo -e "\033[0;36m$*\033[0m"; }
print_warning() { echo -e "\033[0;33m$*\033[0m"; }
print_error() { echo -e "\033[0;31m$*\033[0m"; }

print_info "=========================================="
print_info "NGO Databank - Azure Deployment"
print_info "=========================================="
echo ""

# Check if Azure CLI is installed
if ! command -v az &> /dev/null; then
    print_error "✗ Azure CLI is not installed."
    print_info "Install from: https://docs.microsoft.com/cli/azure/install-azure-cli"
    exit 1
fi
print_success "✓ Azure CLI is installed"

# Check if logged in to Azure
if ! az account show &> /dev/null; then
    print_warning "Not logged in to Azure. Initiating login..."
    az login
    if [ $? -ne 0 ]; then
        print_error "✗ Azure login failed"
        exit 1
    fi
fi
print_success "✓ Authenticated with Azure"

# Display current subscription
SUBSCRIPTION=$(az account show --query name -o tsv)
print_info "Current subscription: $SUBSCRIPTION"
read -p "Continue with this subscription? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_info "Available subscriptions:"
    az account list --output table
    read -p "Enter subscription ID to use: " SUB_ID
    az account set --subscription "$SUB_ID"
fi

echo ""
print_info "=========================================="
print_info "Configuration"
print_info "=========================================="
print_info "Resource Group: $RESOURCE_GROUP"
print_info "Location: $LOCATION"
print_info "Environment: $ENVIRONMENT"
echo ""

# Generate unique names
TIMESTAMP=$(date +%Y%m%d)
UNIQUE_ID=$(cat /dev/urandom | tr -dc 'a-z0-9' | fold -w 6 | head -n 1)

POSTGRES_SERVER="ifrc-databank-db-$ENVIRONMENT-$UNIQUE_ID"
STORAGE_ACCOUNT="ifrcstor${UNIQUE_ID}"
APP_SERVICE_PLAN="asp-ifrc-databank-$ENVIRONMENT"
WEBAPP_NAME="ifrc-databank-$ENVIRONMENT-$UNIQUE_ID"
APPINSIGHTS_NAME="ai-ifrc-databank-$ENVIRONMENT"

print_info "Generated resource names:"
print_info "  PostgreSQL: $POSTGRES_SERVER"
print_info "  Storage: $STORAGE_ACCOUNT"
print_info "  App Service: $WEBAPP_NAME"
echo ""

read -p "Proceed with deployment? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    print_warning "Deployment cancelled"
    exit 0
fi

# Step 1: Create Resource Group
echo ""
print_info "Step 1: Creating Resource Group..."
az group create --name "$RESOURCE_GROUP" --location "$LOCATION" --output none
if [ $? -eq 0 ]; then
    print_success "✓ Resource Group created: $RESOURCE_GROUP"
else
    print_error "✗ Failed to create Resource Group"
    exit 1
fi

# Step 2: Create PostgreSQL Server
echo ""
print_info "Step 2: Creating PostgreSQL Flexible Server..."
print_warning "This may take 5-10 minutes..."

# Generate strong password (16 chars with mixed case, numbers, symbols)
POSTGRES_PASSWORD=$(openssl rand -base64 16 | tr -d "=+/" | cut -c1-16)
POSTGRES_ADMIN="ifrcadmin"

az postgres flexible-server create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$POSTGRES_SERVER" \
    --location "$LOCATION" \
    --admin-user "$POSTGRES_ADMIN" \
    --admin-password "$POSTGRES_PASSWORD" \
    --sku-name Standard_B2ms \
    --tier Burstable \
    --version 15 \
    --storage-size 32 \
    --public-access 0.0.0.0 \
    --backup-retention 7 \
    --yes \
    --output none

if [ $? -eq 0 ]; then
    print_success "✓ PostgreSQL Server created: $POSTGRES_SERVER"
    print_success "  Admin: $POSTGRES_ADMIN"
    print_warning "  Password: $POSTGRES_PASSWORD (SAVE THIS!)"
else
    print_error "✗ Failed to create PostgreSQL Server"
    exit 1
fi

# Create database
print_info "Creating database..."
az postgres flexible-server db create \
    --resource-group "$RESOURCE_GROUP" \
    --server-name "$POSTGRES_SERVER" \
    --database-name ifrc_databank \
    --output none

if [ $? -eq 0 ]; then
    print_success "✓ Database created: ifrc_databank"
fi

# Configure firewall
print_info "Configuring firewall rules..."
az postgres flexible-server firewall-rule create \
    --resource-group "$RESOURCE_GROUP" \
    --name "$POSTGRES_SERVER" \
    --rule-name AllowAzureServices \
    --start-ip-address 0.0.0.0 \
    --end-ip-address 0.0.0.0 \
    --output none

print_success "✓ Firewall configured"

# Step 3: Create Storage Account
echo ""
print_info "Step 3: Creating Storage Account..."
az storage account create \
    --name "$STORAGE_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --sku Standard_LRS \
    --kind StorageV2 \
    --output none

if [ $? -eq 0 ]; then
    print_success "✓ Storage Account created: $STORAGE_ACCOUNT"
fi

# Create container
STORAGE_CONNECTION_STRING=$(az storage account show-connection-string \
    --name "$STORAGE_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" \
    --output tsv)

az storage container create \
    --name uploads \
    --connection-string "$STORAGE_CONNECTION_STRING" \
    --public-access off \
    --output none

print_success "✓ Storage container created: uploads"

# Step 4: Create App Service Plan
echo ""
print_info "Step 4: Creating App Service Plan..."
az appservice plan create \
    --name "$APP_SERVICE_PLAN" \
    --resource-group "$RESOURCE_GROUP" \
    --location "$LOCATION" \
    --is-linux \
    --sku P1v3 \
    --output none

if [ $? -eq 0 ]; then
    print_success "✓ App Service Plan created: $APP_SERVICE_PLAN"
fi

# Step 5: Create Web App
echo ""
print_info "Step 5: Creating Web App..."
az webapp create \
    --resource-group "$RESOURCE_GROUP" \
    --plan "$APP_SERVICE_PLAN" \
    --name "$WEBAPP_NAME" \
    --runtime "PYTHON:3.11" \
    --output none

if [ $? -eq 0 ]; then
    print_success "✓ Web App created: $WEBAPP_NAME"
fi

# Step 6: Create Application Insights
echo ""
print_info "Step 6: Creating Application Insights..."
az monitor app-insights component create \
    --app "$APPINSIGHTS_NAME" \
    --location "$LOCATION" \
    --resource-group "$RESOURCE_GROUP" \
    --application-type web \
    --output none

if [ $? -eq 0 ]; then
    print_success "✓ Application Insights created: $APPINSIGHTS_NAME"
fi

APPINSIGHTS_KEY=$(az monitor app-insights component show \
    --app "$APPINSIGHTS_NAME" \
    --resource-group "$RESOURCE_GROUP" \
    --query instrumentationKey \
    --output tsv)

# Step 7: Configure Web App Settings
echo ""
print_info "Step 7: Configuring Web App Settings..."

# Generate SECRET_KEY
SECRET_KEY=$(openssl rand -base64 32)

# Generate API_KEY
API_KEY=$(cat /dev/urandom | tr -dc 'A-Za-z0-9' | fold -w 32 | head -n 1)

# Build DATABASE_URL
DATABASE_URL="postgresql+psycopg2://${POSTGRES_ADMIN}:${POSTGRES_PASSWORD}@${POSTGRES_SERVER}.postgres.database.azure.com:5432/ifrc_databank?sslmode=require"

az webapp config appsettings set \
    --resource-group "$RESOURCE_GROUP" \
    --name "$WEBAPP_NAME" \
    --settings \
        FLASK_CONFIG="production" \
        FLASK_APP="run:app" \
        SECRET_KEY="$SECRET_KEY" \
        DATABASE_URL="$DATABASE_URL" \
        API_KEY="$API_KEY" \
        SCM_DO_BUILD_DURING_DEPLOYMENT="true" \
        ENABLE_ORYX_BUILD="true" \
        POST_BUILD_COMMAND="npm install && npm run build:css" \
        WEBSITES_PORT="5000" \
        APPLICATIONINSIGHTS_CONNECTION_STRING="InstrumentationKey=$APPINSIGHTS_KEY" \
        UPLOAD_FOLDER="/home/site/wwwroot/uploads" \
        AZURE_STORAGE_CONNECTION_STRING="$STORAGE_CONNECTION_STRING" \
        AZURE_STORAGE_CONTAINER="uploads" \
        BASE_URL="https://$WEBAPP_NAME.azurewebsites.net" \
        SECURITY_HEADERS_ENABLED="true" \
        SQLALCHEMY_POOL_SIZE="10" \
        SQLALCHEMY_MAX_OVERFLOW="20" \
        WEB_CONCURRENCY="4" \
    --output none

print_success "✓ App Settings configured"

# Configure general settings
print_info "Configuring general settings..."
az webapp config set \
    --resource-group "$RESOURCE_GROUP" \
    --name "$WEBAPP_NAME" \
    --always-on true \
    --http20-enabled true \
    --min-tls-version "1.2" \
    --ftps-state Disabled \
    --startup-file "startup.sh" \
    --output none

az webapp update \
    --resource-group "$RESOURCE_GROUP" \
    --name "$WEBAPP_NAME" \
    --client-affinity-enabled false \
    --output none

print_success "✓ General settings configured"

# Step 8: Summary
echo ""
print_info "=========================================="
print_success "Deployment Complete!"
print_info "=========================================="
echo ""
print_info "Resources created:"
print_info "  Resource Group: $RESOURCE_GROUP"
print_info "  PostgreSQL Server: $POSTGRES_SERVER"
print_info "  Database: ifrc_databank"
print_info "  Storage Account: $STORAGE_ACCOUNT"
print_info "  App Service Plan: $APP_SERVICE_PLAN"
print_info "  Web App: $WEBAPP_NAME"
print_info "  Application Insights: $APPINSIGHTS_NAME"
echo ""
print_info "Web App URL: https://$WEBAPP_NAME.azurewebsites.net"
echo ""
print_warning "=========================================="
print_warning "IMPORTANT: Save these credentials!"
print_warning "=========================================="
print_warning "PostgreSQL Admin: $POSTGRES_ADMIN"
print_warning "PostgreSQL Password: $POSTGRES_PASSWORD"
print_warning "SECRET_KEY: $SECRET_KEY"
print_warning "API_KEY: $API_KEY"
echo ""
print_warning "Save these to a secure location NOW!"
print_warning "=========================================="
echo ""
print_info "Next steps:"
print_info "1. Configure additional settings (email, AI keys, etc.) in Azure Portal"
print_info "2. Migrate your database using pg_restore"
print_info "3. Deploy your application from Backoffice directory:"
print_info "   cd .. (to Backoffice root)"
print_info "   git push azure main:master"
print_info "4. Create admin user: az webapp ssh and run 'flask create-admin'"
echo ""
print_info "For detailed instructions, see azure/AZURE_DEPLOYMENT_GUIDE.md"
echo ""

# Save credentials to file
CREDS_FILE="azure-credentials-$TIMESTAMP.txt"
cat > "$CREDS_FILE" << EOF
========================================
Azure Deployment Credentials
Generated: $(date)
========================================

Resource Group: $RESOURCE_GROUP
Location: $LOCATION

PostgreSQL Server: $POSTGRES_SERVER
PostgreSQL Admin: $POSTGRES_ADMIN
PostgreSQL Password: $POSTGRES_PASSWORD
Database Name: ifrc_databank
Connection String: $DATABASE_URL

Web App: $WEBAPP_NAME
Web App URL: https://$WEBAPP_NAME.azurewebsites.net

SECRET_KEY: $SECRET_KEY
API_KEY: $API_KEY

Application Insights Key: $APPINSIGHTS_KEY

Storage Account: $STORAGE_ACCOUNT

========================================
KEEP THIS FILE SECURE AND PRIVATE!
========================================
EOF

print_success "Credentials saved to: $CREDS_FILE"
print_warning "Delete this file after saving credentials to a secure location!"
