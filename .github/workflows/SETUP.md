# GitHub Actions Workflow Setup Guide

This guide explains how to configure the GitHub Actions workflow to automatically deploy to Azure.

---

## 🎯 Overview

The workflow in `azure-deploy.yml` is configured to deploy the Backoffice to Azure App Service.

> **Heads-up:** Automatic deployments on every `main` push are temporarily paused. For now the workflow only runs when triggered manually from the **Actions** tab. Re-enable the `push` trigger inside `azure-deploy.yml` when you're ready to resume automatic deploys.

**Current Status:** ❌ Not configured yet - needs Azure credentials

---

## 📋 Prerequisites

Before setting up the workflow, you need:

1. ✅ Azure resources created (Web App, Database, etc.)
2. ✅ Azure CLI installed
3. ✅ Access to your GitHub repository settings

---

## 🚀 Setup Steps

### Step 1: Create Azure Resources

**You must create the Azure infrastructure first!** The workflow deploys TO an existing Azure Web App.

**Option A: Automated (Fastest)**
```powershell
cd Backoffice/azure
.\azure-deploy.ps1
```

**Option B: Automated (Bash)**
```bash
cd Backoffice/azure
chmod +x azure-deploy.sh
./azure-deploy.sh
```

**Option C: Manual**
Follow `Backoffice/azure/DEPLOYMENT_GUIDE.md`

After completion, note down:
- ✅ Resource Group name (e.g., `rg-ngo-databank-prod`)
- ✅ Web App name (e.g., `ngo-databank-prod-abc123`)

---

### Step 2: Download Publish Profile

Get your Web App's deployment credentials:

```powershell
# Set your actual values
$RESOURCE_GROUP = "rg-ngo-databank-prod"
$WEBAPP_NAME = "ngo-databank-prod-abc123"

# Download publish profile
az webapp deployment list-publishing-profiles `
  --resource-group $RESOURCE_GROUP `
  --name $WEBAPP_NAME `
  --xml > publish-profile.xml
```

This creates `publish-profile.xml` in your current directory.

---

### Step 3: Add GitHub Secret

1. **Open the publish profile:**
   ```powershell
   notepad publish-profile.xml
   ```

2. **Copy ALL contents** (entire XML file)

3. **Go to GitHub repository settings:**
   - Navigate to: https://github.com/haythamsoufi/databank/settings/secrets/actions
   - Or: Repository → Settings → Secrets and variables → Actions

4. **Create new secret:**
   - Click **"New repository secret"**
   - **Name:** `AZURE_WEBAPP_PUBLISH_PROFILE`
   - **Value:** Paste the entire XML content (including `<?xml` header)
   - Click **"Add secret"**

5. **Delete the local file** (contains sensitive credentials):
   ```powershell
   Remove-Item publish-profile.xml
   ```

---

### Step 4: Update Workflow Configuration

Edit `.github/workflows/azure-deploy.yml`:

Find this section (line 21-24):
```yaml
env:
  AZURE_WEBAPP_NAME: YOUR-ACTUAL-WEBAPP-NAME  # TODO: Change this
  PYTHON_VERSION: '3.11'
  NODE_VERSION: '18'
```

Change to:
```yaml
env:
  AZURE_WEBAPP_NAME: ngo-databank-prod-abc123  # Your actual Web App name
  PYTHON_VERSION: '3.11'
  NODE_VERSION: '18'
```

**Save and commit:**
```bash
git add .github/workflows/azure-deploy.yml
git commit -m "Configure GitHub Actions workflow with Azure Web App name"
git push origin main
```

---

### Step 5: Verify Setup ✅

Check that everything is configured:

1. **Verify secret exists:**
   - Go to: https://github.com/haythamsoufi/databank/settings/secrets/actions
   - You should see: `AZURE_WEBAPP_PUBLISH_PROFILE` with green checkmark

2. **Verify workflow is updated:**
   - Check `.github/workflows/azure-deploy.yml` has your actual Web App name

3. **Test the workflow:**
   - Go to: https://github.com/haythamsoufi/databank/actions
   - Click "Deploy Backoffice to Azure App Service"
   - Click "Run workflow" → Select `main` branch → "Run workflow"
   - Watch it deploy! 🚀

---

## 🎯 How It Works

Once configured, you can deploy in two ways:

### 1. **Manual Deployment** (Current Mode)
- Go to: https://github.com/haythamsoufi/databank/actions
- Click "Deploy Backoffice to Azure App Service"
- Click "Run workflow"
- Select branch and click "Run workflow"

### 2. **Automatic Deployment** (Temporarily Disabled)
- Uncomment the `push` trigger in `.github/workflows/azure-deploy.yml`
- Push changes to the `main` branch affecting `Backoffice/**`
- Workflow automatically builds and deploys

---

## 📊 What the Workflow Does

When triggered, the workflow:

1. ✅ **Checks out code** from GitHub
2. ✅ **Sets up Python 3.11** and Node.js 18
3. ✅ **Installs dependencies** (pip, npm)
4. ✅ **Builds Tailwind CSS** (runs `npm run build:css`)
5. ✅ **Runs tests** (optional, currently skipped)
6. ✅ **Creates deployment package** (copies necessary files)
7. ✅ **Deploys to Azure** using publish profile
8. ✅ **Health check** (verifies app is responding)
9. ✅ **Creates summary** (shows deployment details)

**Time:** ~3-5 minutes per deployment

---

## 📁 Workflow Configuration

### Environment Variables

```yaml
env:
  AZURE_WEBAPP_NAME: your-webapp-name    # Your Azure Web App name
  PYTHON_VERSION: '3.11'                  # Python runtime version
  NODE_VERSION: '18'                      # Node.js version for build
```

### Triggers

```yaml
on:
  workflow_dispatch:                      # (Current) Manual trigger only
  # push:                                 # Uncomment to resume auto deploys
  #   branches: [main]
  #   paths: ['Backoffice/**']
```

### Secrets Required

| Secret Name | Description | How to Get |
|-------------|-------------|------------|
| `AZURE_WEBAPP_PUBLISH_PROFILE` | Azure deployment credentials | Download from Azure CLI or Portal |

---

## 🔍 Monitoring Deployments

### View Deployment Logs

1. **Go to GitHub Actions:**
   - https://github.com/haythamsoufi/databank/actions

2. **Click on a workflow run** to see:
   - ✅ Build logs
   - ✅ Deployment progress
   - ✅ Health check results
   - ✅ Deployment summary

3. **Check deployment on Azure:**
   ```powershell
   # View logs
   az webapp log tail --resource-group <rg> --name <app>
   
   # Open in browser
   az webapp browse --resource-group <rg> --name <app>
   ```

### Deployment Summary

After each deployment, check the summary for:
- ✅ Environment (production/staging)
- ✅ App name and URL
- ✅ Python and Node.js versions
- ✅ Who deployed (GitHub username)
- ✅ Commit SHA

---

## 🛠️ Troubleshooting

### ❌ Workflow Fails: "Secret not found"

**Problem:** `AZURE_WEBAPP_PUBLISH_PROFILE` secret is missing

**Solution:**
1. Verify secret exists: https://github.com/haythamsoufi/databank/settings/secrets/actions
2. If missing, follow Step 3 above to add it
3. Make sure you named it exactly: `AZURE_WEBAPP_PUBLISH_PROFILE` (no typos)

---

### ❌ Workflow Fails: "App not found"

**Problem:** Web App name in workflow doesn't match actual Azure Web App

**Solution:**
1. Get your actual Web App name from Azure:
   ```powershell
   az webapp list --output table
   ```
2. Update `.github/workflows/azure-deploy.yml` with correct name
3. Commit and push changes

---

### ❌ Deployment Succeeds but App Returns 500 Error

**Problem:** App deployed but not configured correctly

**Solution:**
1. Check Azure App Settings are configured:
   ```powershell
   az webapp config appsettings list --resource-group <rg> --name <app>
   ```
2. Verify DATABASE_URL, SECRET_KEY are set
3. Check logs:
   ```powershell
   az webapp log tail --resource-group <rg> --name <app>
   ```

---

### ❌ Build Fails: "Module not found"

**Problem:** Missing dependency in `requirements.txt`

**Solution:**
1. Verify all dependencies are in `Backoffice/requirements.txt`
2. Test locally:
   ```powershell
   cd Backoffice
   pip install -r requirements.txt
   python run.py
   ```
3. Add missing packages to `requirements.txt`
4. Commit and push

---

### ❌ CSS Not Loading After Deployment

**Problem:** Tailwind CSS build failed

**Solution:**
1. Check workflow logs for npm errors
2. Verify `package.json` has `build:css` script
3. Test locally:
   ```powershell
   cd Backoffice
   npm install
   npm run build:css
   ```
4. Ensure `tailwind.config.js` exists in Backoffice/assets/

---

## 🔐 Security Best Practices

### Protecting Secrets

✅ **DO:**
- Store all credentials as GitHub Secrets
- Delete local copies of publish profile
- Rotate publish profile periodically
- Use different secrets for staging/production

❌ **DON'T:**
- Commit publish profile to git
- Share secrets in pull requests
- Use same credentials for multiple environments
- Store secrets in workflow file

### Rotating Credentials

To update your publish profile:

```powershell
# Download new profile
az webapp deployment list-publishing-profiles `
  --resource-group $RESOURCE_GROUP `
  --name $WEBAPP_NAME `
  --xml > new-publish-profile.xml

# Update GitHub secret with new content
# Delete local file
Remove-Item new-publish-profile.xml
```

---

## 🎓 Advanced Configuration

### Multiple Environments

To deploy to staging and production:

1. **Create staging slot:**
   ```powershell
   az webapp deployment slot create `
     --resource-group $RESOURCE_GROUP `
     --name $WEBAPP_NAME `
     --slot staging
   ```

2. **Get staging publish profile:**
   ```powershell
   az webapp deployment list-publishing-profiles `
     --resource-group $RESOURCE_GROUP `
     --name $WEBAPP_NAME `
     --slot staging `
     --xml > staging-publish-profile.xml
   ```

3. **Add GitHub secret:** `AZURE_WEBAPP_PUBLISH_PROFILE_STAGING`

4. **Update workflow** to use different secrets based on environment

---

### Add Notifications

Extend the workflow to notify your team:

```yaml
- name: Notify Slack
  uses: slackapi/slack-github-action@v1
  with:
    payload: |
      {
        "text": "Deployment to Azure completed!"
      }
  env:
    SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

---

### Run Tests Before Deployment

Uncomment the test step in `azure-deploy.yml`:

```yaml
- name: 🧪 Run tests
  working-directory: ./Backoffice
  run: |
    python -m pytest tests/
```

Add tests to `Backoffice/tests/` folder.

---

## 📚 Additional Resources

- **GitHub Actions Docs:** https://docs.github.com/actions
- **Azure Web Apps Deployment:** https://docs.microsoft.com/azure/app-service/deploy-github-actions
- **Workflow Syntax:** https://docs.github.com/actions/reference/workflow-syntax-for-github-actions

---

## ✅ Quick Reference

### After Azure Resources Created:

```powershell
# 1. Get publish profile
az webapp deployment list-publishing-profiles `
  --resource-group <your-rg> `
  --name <your-webapp> `
  --xml > publish-profile.xml

# 2. Add to GitHub Secrets (via web UI)
# Name: AZURE_WEBAPP_PUBLISH_PROFILE
# Value: <contents of publish-profile.xml>

# 3. Update workflow
# Edit: .github/workflows/azure-deploy.yml
# Change: AZURE_WEBAPP_NAME to your actual name

# 4. Commit and push
git add .github/workflows/azure-deploy.yml
git commit -m "Configure workflow"
git push origin main

# 5. Watch it deploy!
# Go to: https://github.com/haythamsoufi/databank/actions
```

---

## 🎯 Summary

**Before the workflow works, you need to:**

1. ✅ Create Azure resources (`azure-deploy.ps1`)
2. ✅ Download publish profile from Azure
3. ✅ Add publish profile as GitHub secret
4. ✅ Update workflow with Web App name
5. ✅ Commit and push changes

**After setup, deployments are automatic!** Just push code to `main` branch and GitHub Actions handles the rest. 🚀

---

**Need help?** Check:
- Azure deployment: `Backoffice/azure/DEPLOYMENT_GUIDE.md`
- Workflow troubleshooting: See "Troubleshooting" section above
- GitHub Actions: https://github.com/haythamsoufi/databank/actions

**Last Updated:** October 2025

---

## 📱 Mobile App Build Secrets

The iOS and Android build workflows require API keys to be configured as GitHub Secrets.

### Required Secrets for Mobile App Builds

| Secret Name | Description | Required For |
|-------------|-------------|--------------|
| `API_KEY` | API key for public endpoints | All builds |
| `MOBILE_NOTIFICATION_API_KEY` | Shared secret for push notifications | All builds |
| `SENTRY_DSN` | Sentry error tracking DSN (optional) | Error tracking |

### Setting Up Mobile App Secrets

1. **Go to GitHub repository settings:**
   - Navigate to: https://github.com/haythamsoufi/databank/settings/secrets/actions
   - Or: Repository → Settings → Secrets and variables → Actions

2. **Add each secret:**
   - Click **"New repository secret"**
   - Add each secret with the exact name listed above
   - **Value:** Your actual API key value
   - Click **"Add secret"**

3. **Verify secrets are set:**
   - You should see all three secrets listed with green checkmarks

### How API Keys Are Used

The mobile app workflows pass these secrets via `--dart-define` flags during the build process:

```bash
flutter build ios --release \
  --dart-define=API_KEY="${{ secrets.API_KEY }}" \
  --dart-define=MOBILE_NOTIFICATION_API_KEY="${{ secrets.MOBILE_NOTIFICATION_API_KEY }}" \
  --dart-define=SENTRY_DSN="${{ secrets.SENTRY_DSN }}"
```

The app code reads these values using `String.fromEnvironment()` with fallback to `.env` file (for local development).

### Local Development

For local development, you can create a `.env` file in the `MobileApp` directory:

```
API_KEY=your_api_key_here
MOBILE_NOTIFICATION_API_KEY=your_mobile_notification_api_key_here
SENTRY_DSN=your_sentry_dsn_here
```

**Note:** The `.env` file is gitignored and not included in Flutter assets to avoid build errors in CI.

### Troubleshooting Mobile App Builds

**❌ Build fails: "API_KEY not found"**

- Verify the secret exists in GitHub: https://github.com/haythamsoufi/databank/settings/secrets/actions
- Check that the secret name is exactly `API_KEY` (case-sensitive)
- Ensure the workflow is using `${{ secrets.API_KEY }}` syntax

**❌ Build succeeds but app can't authenticate**

- Verify the API keys are correct
- Check that the keys match what the backend expects
- For local development, ensure `.env` file exists and is properly formatted

---
