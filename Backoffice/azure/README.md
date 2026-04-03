# Azure Deployment - NGO Databank

Complete guide for deploying the NGO Databank Backoffice to Microsoft Azure.

---

## 🚀 Quick Start

### Prerequisites
- Azure subscription with billing enabled
- Azure CLI installed: `winget install Microsoft.AzureCLI`
- Git, Python 3.11, Node.js 18+

### Option 1: Automated (15 minutes) ⚡
```powershell
cd Backoffice/azure
.\azure-deploy.ps1
```

### Option 2: Manual (60 minutes) 📖
Follow the [Deployment Guide](./DEPLOYMENT_GUIDE.md)

---

## 📚 Documentation

| File | Purpose |
|------|---------|
| **[DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)** | Complete deployment instructions, requirements & troubleshooting |
| **[CHECKLIST.md](./CHECKLIST.md)** | Verification checklist for deployment |
| **azure-deploy.ps1** | Automated deployment script (Windows) |
| **azure-deploy.sh** | Automated deployment script (Linux/macOS) |
| **azure.env.template** | Environment variables template |

---

## 💰 Cost Estimates

| Environment | Monthly Cost |
|-------------|--------------|
| Development | ~$26 (B1 App Service, B1ms PostgreSQL) |
| Production | ~$200 (P1v3 App Service, B2ms PostgreSQL) |
| High-Traffic | ~$975 (Scaled resources) |

---

## 📦 What Gets Deployed

- ✅ Azure App Service (Python 3.11, Linux)
- ✅ PostgreSQL Flexible Server (with backups)
- ✅ Application Insights (monitoring)
- ✅ Storage Account (optional, for uploads)
- ✅ Key Vault (optional, for secrets)

---

## 🎯 Deployment Flow

1. **Preparation** (15 min) - Install Azure CLI, generate credentials
2. **Infrastructure** (15 min) - Create Azure resources via script or manually
3. **Database** (10-30 min) - Create database or migrate existing data
4. **Deploy** (10 min) - Push code to Azure
5. **Verify** (15 min) - Test application, create admin user
6. **Production** (30 min) - Configure monitoring, backups, security

**Total Time:** 15 minutes (automated) or 90-120 minutes (manual)

---

## ⚡ Quick Commands

```powershell
# Login to Azure
az login

# Deploy (automated)
cd Backoffice/azure
.\azure-deploy.ps1

# View logs
az webapp log tail --resource-group <rg> --name <app>

# SSH into app
az webapp ssh --resource-group <rg> --name <app>

# Restart app
az webapp restart --resource-group <rg> --name <app>

# Deploy code manually
git push azure main:master
```

---

## 🆘 Common Issues

### App won't start
```powershell
# Check logs and verify DATABASE_URL
az webapp log tail --resource-group <rg> --name <app>
```

### Database connection failed
```powershell
# Verify firewall rules allow Azure services
# Check connection string includes ?sslmode=require
```

### CSS not loading
```powershell
# SSH and rebuild
az webapp ssh --resource-group <rg> --name <app>
npm install && npm run build:css
```

### High memory usage
```powershell
# Scale up
az appservice plan update --resource-group <rg> --name <plan> --sku P1v3
```

---

## ✅ Success Criteria

After deployment:
- ✅ Web app accessible via HTTPS
- ✅ Admin user can log in
- ✅ Database operations working
- ✅ File uploads working
- ✅ No 500 errors
- ✅ Monitoring configured
- ✅ Backups enabled

---

## 📞 Support

- **Azure Docs**: https://docs.microsoft.com/azure/app-service
- **Azure Support**: https://azure.microsoft.com/support
- **Pricing Calculator**: https://azure.microsoft.com/pricing/calculator

---

**Ready to deploy?**

- 🚀 **Fastest**: Run `.\azure-deploy.ps1`
- 📖 **Learning**: Follow [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)
- ✅ **Verifying**: Use [CHECKLIST.md](./CHECKLIST.md)

**Last Updated:** October 2025
