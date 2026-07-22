# Staging resource-group separation & Application Gateway plan

**Date:** 2026-07-21  
**Author:** Databank engineering (inventory via `azure_webapp_tools.bat` / Azure CLI)  
**Audience:** Infrastructure, platform networking, Databank engineering  
**Status:** Proposal — ready for infra review  

---

## 1. Executive summary

**Goal:** Move all Databank staging resources out of **`ifrctgo001rg`** into a dedicated resource group. That RG is shared with other applications (VMs: `drefassist`, `sitroom`, `spark`, `SemiAutomatedDisasterBriefs`; shared VNet; GO frontend CDN; hundreds of deployment template-spec versions) and should not host Databank long term.

**Secondary goal:** Put staging behind **Application Gateway (AppGW)**, matching production. Staging is publicly reachable today with no IP restrictions and without mandatory HTTPS; prod accepts traffic only from the AppGW public IP.

**Recommended outcome:**

1. Create a dedicated Databank staging resource group (e.g. `ifrc-databank-staging-rg`) in subscription **IFRC Non-Prod** — same subscription, new RG only.
2. Move **Databank-owned** resources from `ifrctgo001rg` → new RG (see §4 and §10). Leave other apps' resources in place.
3. Work with the central networking team to place **`databank-stage.ifrc.org`** behind AppGW (VNet integration, IP restrictions).
4. Align staging security posture with prod where appropriate (HTTPS-only, private DB connectivity, monitoring).

**Note:** Production already has its own RG (`ifrcpunifiedplanning-rg001` in a separate subscription). This plan is **not** about splitting prod from staging — it is about giving staging the same isolation from unrelated non-prod workloads that prod already has from everything else.

---

## 2. Subscription & resource-group map

| Environment | Azure subscription | Subscription ID | Resource group | Primary hostname |
|-------------|-------------------|-----------------|----------------|------------------|
| **Production** | AppServices Prod | `3e33b4c1-ada7-4922-9113-b9e41eaf1797` | `ifrcpunifiedplanning-rg001` | `databank.ifrc.org` |
| **Staging** | IFRC Non-Prod | `f585c1c3-801b-4641-8d7f-145aa50ffb04` | `ifrctgo001rg` | `databank-stage.ifrc.org` |
| **Shared infra** (AppGW / hub VNet — inferred, not directly accessible) | Unknown name | `3d7b0c75-a042-4cb6-9d8d-a1b8803735a5` | `IFRC-NONPROD-APPS-RG`, `ifrcuunifiedplanning-rg001` | — |

**Container registry (shared):** `ifrcimage.azurecr.io` — referenced by both environments; hosted outside the Non-Prod subscription (ACR subscription `3e33b4c1-ada7-4922-9113-b9e41eaf1797` per repo tooling).

**Scope:** Staging must leave `ifrctgo001rg` because that RG belongs to multiple non-prod apps. Prod/staging are already in different subscriptions; the change is **staging RG separation + AppGW**.

---

## 3. Current inventory — `ifrctgo001rg` (IFRC Non-Prod)

**Location:** West Europe  
**Total resource count:** ~260 (including 210 `Microsoft.Resources/templateSpecs/versions` artifacts)

### 3.1 Resource counts by type

| Count | Resource type |
|------:|---------------|
| 210 | `Microsoft.Resources/templateSpecs/versions` |
| 4 | `Microsoft.Compute/virtualMachines` |
| 4 | `Microsoft.Compute/disks` |
| 4 | `Microsoft.Compute/sshPublicKeys` |
| 4 | `Microsoft.Network/networkInterfaces` |
| 4 | `Microsoft.Network/publicIPAddresses` |
| 5 | `Microsoft.Network/networkSecurityGroups` |
| 1 | `Microsoft.Network/virtualNetworks` |
| 3 | `Microsoft.Storage/storageAccounts` |
| 2 | `Microsoft.KeyVault/vaults` |
| 1 | `Microsoft.Web/sites` |
| 1 | `Microsoft.Web/serverFarms` |
| 1 | `Microsoft.Web/certificates` |
| 1 | `Microsoft.DBforPostgreSQL/flexibleServers` |
| 1 | `Microsoft.Cdn/profiles` + 1 endpoint |
| 1 | `Microsoft.LoadTestService/loadtests` |
| 1 | `microsoft.insights/components` + alerts/webtests/action groups |
| 2 | Smart detector alert rules |

---

## 4. Databank staging resources (candidates to move)

These resources directly support the Humanitarian Databank staging stack.

### 4.1 Compute & application

| Resource | Type | Details |
|----------|------|---------|
| `ifrc-databank-staging-2` | App Service (Linux container) | Image: `ifrcimage.azurecr.io/databank_backend:v1.7`; SKU plan Premium0V3; **Running** |
| `asp-ifrc-databank-staging` | App Service plan | **P0v3**, 1 worker, Linux, West Europe |
| `databank-stage` | App Service managed certificate | Wildcard `*.ifrc.org` / `ifrc.org`; expires **2026-09-01** |

**Custom domains**

| Hostname | SSL | Notes |
|----------|-----|-------|
| `databank-stage.ifrc.org` | SNI enabled | Primary staging URL (`BASE_URL`) |
| `ifrc-databank-staging-2.azurewebsites.net` | Default Azure | Direct access today (no AppGW filter) |

**Security posture (staging today — gaps vs prod)**

| Setting | Staging | Production |
|---------|---------|------------|
| `httpsOnly` | **false** | **true** |
| IP access restrictions | **Allow all** | Allow AppGW PIP `4.175.128.233/32` only; default **Deny** |
| VNet integration | **None** | Integrated to `IFRC-NONPROD-APPS-VNET` / subnet `ifrc-databank_app-service` |
| `vnetRouteAllEnabled` | **false** | **true** |
| Health check path | `/health` | `/health` |

**Azure Files mount (translations):**

- Storage account: `ifrcdatabankstorage2`
- Share: `translations-staging` → `/data/translations`

### 4.2 Database

| Resource | Type | Details |
|----------|------|---------|
| `ifrc-databank-db-staging-2` | PostgreSQL Flexible Server | PG **15**, SKU **Standard_B2ms** (Burstable), 32 GB Premium_LRS, AZ **1** |
| FQDN | | `ifrc-databank-db-staging-2.postgres.database.azure.com` |
| Network | | **Public access enabled**; no private endpoint |
| Backup | | 7-day retention, geo-redundant backup disabled |
| Firewall | | `AllowAzureServices` (0.0.0.0–0.0.0.0) + named developer IPs |

**Contrast with prod DB (`databank-db`):** PG 17, Standard_B1ms, public access enabled **but** has an approved **private endpoint** in shared infra RG `ifrcuunifiedplanning-rg001` (subscription `3d7b0c75-…`).

### 4.3 Storage

| Account | SKU | Role |
|---------|-----|------|
| `ifrcdatabankstorage2` | Standard_LRS | Backend uploads (`uploads-staging`), static assets (`static-staging`), translations file share |
| `gostoragestage` | Standard_RAGRS | Frontend SPA blob origin for CDN (`/go-frontend`) |

### 4.4 CDN / frontend (GO staging)

| Resource | Details |
|----------|---------|
| Profile `go-frontend-cdn-stage` | Azure CDN (classic) |
| Endpoint `go-frontend-stage` | Host: `go-frontend-stage.azureedge.net` |
| Custom domain | **`go-stage.ifrc.org`** |
| Origin | `gostoragestage.blob.core.windows.net` / path `/go-frontend` |
| Rules | HTTPS redirect, SPA rewrite to `/index.html`, long-cache static assets |

### 4.5 Secrets & monitoring

| Resource | Details |
|----------|---------|
| `databank-keyvault-stag` | RBAC-enabled Key Vault; public network access; URI `https://databank-keyvault-stag.vault.azure.net/` |
| `Databank-insight-staging` | Application Insights component |
| `databank-staging-databank-insigth` | Availability web test + metric alert |
| `Failure Anomalies - Databank-insight-staging` | Smart detector |
| Action groups | `databank_responsibles`, `DatabankStGr`, `DatabankStag` |
| `DatabankTest1` | Azure Load Testing resource (used by repo load-test scripts) |

### 4.6 App settings (names only — values are secrets)

Staging web app uses (among others): `BASE_URL`, `DATABASE_URL`, `AZURE_STORAGE_CONNECTION_STRING`, `AZURE_STORAGE_CONTAINER`, `STATIC_CDN_URL`, `DOCKER_REGISTRY_SERVER_URL`, `APPLICATIONINSIGHTS_CONNECTION_STRING`, `IFRC_TRANSLATE_URL`, `EMAIL_API_URL_*`.

Prod uses the same key names plus `UPLOAD_STORAGE_PROVIDER`.

---

## 5. Non-Databank resources remaining in `ifrctgo001rg`

These should **not** move to the new Databank staging RG unless explicitly owned by the same team.

| Resource group | Examples | Notes |
|----------------|----------|-------|
| **VMs (×4)** | `drefassist`, `sitroom`, `spark`, `SemiAutomatedDisasterBriefs` | Each with public IP, NSG, NIC, OS disk; attached to `unpl1-vnet` / `default` subnet |
| **Shared network** | `unpl1-vnet` (`172.16.0.0/16`), `unpl1-nsg` | Subnet `172.16.0.0/24` hosts all four VMs |
| **Other Key Vault** | `tgostagekeyvault` | Likely GO/frontend team |
| **Template specs** | `FrontendCDNTemplateSpec` + **210 version resources** | Deployment pipeline artifacts; cleanup candidate |
| **CDN template specs** | `FrontendCDNEnpointTemplateSpec` versions | Same |

---

## 6. Production reference architecture (target pattern for staging)

Production Databank is already locked down behind central networking:

```
Internet → DNS (databank.ifrc.org)
         → Application Gateway (PIP 4.175.128.233 — shared infra subscription)
         → App Service ifrc-databank-app (IP restriction: AppGW only)
              ↳ VNet-integrated (IFRC-NONPROD-APPS-VNET)
              ↳ Outbound routed via VNet
         → PostgreSQL databank-db (+ private endpoint in shared infra RG)
```

**Observed prod settings (from Azure CLI, 2026-07-21):**

| Component | Value |
|-----------|-------|
| Web App | `ifrc-databank-app` |
| Plan | `ifrc-databank-plan` — **P2v3**, 1 worker |
| AppGW allow rule | `allow-ifrc-prod-appgw-pip` → `4.175.128.233/32` |
| Default action | **Deny all** |
| VNet subnet | `/subscriptions/3d7b0c75-…/IFRC-NONPROD-APPS-RG/…/IFRC-NONPROD-APPS-VNET/subnets/ifrc-databank_app-service` |
| Deployment slot | `restore-b5c8` (running) |
| Custom domain | `databank.ifrc.org` (wildcard cert) |

**Note:** No Application Gateway resource exists in either **IFRC Non-Prod** or **AppServices Prod** subscriptions accessible to this account. AppGW lifecycle is owned by the **shared infra subscription** (`3d7b0c75-…`). Infra colleagues with access to that subscription must drive AppGW listener/backend-pool/WAF configuration.

---

## 7. Gap analysis — staging vs prod

| Area | Staging today | Prod today | Target staging |
|------|---------------|------------|----------------|
| Resource group | Shared `ifrctgo001rg` | Dedicated `ifrcpunifiedplanning-rg001` | Dedicated `ifrc-databank-staging-rg` (proposed) |
| Edge / WAF | Direct to App Service | AppGW front door | AppGW front door |
| IP restrictions | Open | AppGW PIP only | Staging AppGW PIP only |
| HTTPS enforcement | Optional | Required | Required |
| VNet integration | None | Yes (shared hub VNet) | Yes (staging subnet — infra to provision) |
| DB connectivity | Public + Azure services rule | Public + **private endpoint** | Private endpoint recommended |
| Monitoring | App Insights + alerts | App Insights + alerts + plan metrics | Keep; update resource IDs after move |
| Frontend CDN | `go-stage.ifrc.org` via CDN profile in same RG | (not inventoried here) | Move with backend or split per team ownership |

---

## 8. Proposed target architecture

```
Internet → DNS (databank-stage.ifrc.org)
         → Staging Application Gateway (new or shared WAF instance — infra decision)
         → App Service ifrc-databank-staging-2 (IP restriction: staging AppGW PIP only)
              ↳ VNet-integrated (new staging subnet in hub/spoke model)
              ↳ vnetRouteAllEnabled = true (match prod)
         → PostgreSQL ifrc-databank-db-staging-2 (private endpoint recommended)

Frontend (parallel path):
Internet → DNS (go-stage.ifrc.org) → CDN go-frontend-cdn-stage → gostoragestage
         (CDN may remain on Azure CDN or migrate with RG — see §9.3)
```

**Suggested new resource group:** `ifrc-databank-staging-rg` in subscription **IFRC Non-Prod** (`f585c1c3-…`), region **West Europe**.

---

## 9. Migration plan (phased)

### Phase 0 — Discovery & approvals (infra + Databank)

| # | Task | Owner |
|---|------|-------|
| 0.1 | Confirm ownership of VMs and `unpl1-vnet` (not Databank) | Infra |
| 0.2 | Confirm AppGW model for staging: **new listener on existing prod AppGW** vs **dedicated staging AppGW** | Infra / Security |
| 0.3 | Confirm whether `go-stage.ifrc.org` CDN/storage moves with Databank or stays under GO team RG | Product / Infra |
| 0.4 | Obtain RBAC on shared infra subscription `3d7b0c75-…` for VNet/subnet + AppGW work | Infra |
| 0.5 | Decide staging AppGW public IP (new PIP) and WAF policy (clone prod rules?) | Infra / Security |
| 0.6 | Certificate strategy: reuse wildcard `*.ifrc.org` on AppGW vs App Service managed cert | Infra |

**Exit criteria:** Signed-off target RG name, AppGW design, maintenance window.

---

### Phase 1 — Prepare target resource group (no traffic cutover)

| # | Task | Notes |
|---|------|-------|
| 1.1 | Create `ifrc-databank-staging-rg` | Same subscription & region |
| 1.2 | Apply tags (`Environment=Staging`, `Application=Databank`, `CostCenter=…`) | Align with IFRC tagging standard |
| 1.3 | Define RBAC for Databank deployers vs infra | Least privilege |
| 1.4 | **Do not move** VMs, `unpl1-vnet`, or unrelated key vaults | |

---

### Phase 2 — Networking & AppGW (infra-led)

| # | Task | Notes |
|---|------|-------|
| 2.1 | Provision staging subnet (e.g. `ifrc-databank-staging_app-service`) in hub VNet | Mirror prod subnet naming |
| 2.2 | Configure AppGW listener for `databank-stage.ifrc.org` | Backend pool → staging App Service |
| 2.3 | Configure WAF rules / health probe on `/health` | Match prod probe path |
| 2.4 | Integrate App Service with staging subnet | Requires plan support (Premium — already satisfied) |
| 2.5 | Enable `WEBSITE_VNET_ROUTE_ALL=1` / route all outbound | Match prod |
| 2.6 | Create private endpoint for `ifrc-databank-db-staging-2` | Optional but strongly recommended |
| 2.7 | Update PostgreSQL firewall: remove broad rules after private endpoint validated | Reduce attack surface |

---

### Phase 3 — Resource move (same subscription)

Move resources **within IFRC Non-Prod** from `ifrctgo001rg` → `ifrc-databank-staging-rg`.

**Recommended move batches** (order matters for dependencies):

| Batch | Resources | Move constraints |
|-------|-----------|------------------|
| A | `asp-ifrc-databank-staging` + `ifrc-databank-staging-2` | App Service and plan must move together; brief restart |
| B | `ifrc-databank-db-staging-2` | PG Flexible Server move supported within region/subscription; plan downtime |
| C | `ifrcdatabankstorage2`, `gostoragestage` | Storage account move supported; update connection strings if endpoints referenced by URI with RG |
| D | `databank-keyvault-stag` | Key Vault move supported; verify RBAC assignments survive |
| E | `databank-stage` certificate | Bound to web app — move with app or rebind |
| F | `Databank-insight-staging`, alerts, action groups, web tests, smart detectors | Move after app; update alert scopes |
| G | `go-frontend-cdn-stage` (+ endpoint), `DatabankTest1` | CDN profile is global; confirm move policy with infra |

**Not moving (unless agreed):** `tgostagekeyvault`, all VMs/VNet/template-spec artifacts.

**Tooling:** `az resource move` / Azure Portal **Move resources** wizard; validate with [Azure resource move guidance](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/move-resource-group-and-subscription).

---

### Phase 4 — Lock down staging App Service

After AppGW serves traffic successfully:

| # | Task |
|---|------|
| 4.1 | Add IP restriction: allow **staging AppGW PIP** (analogous to prod `4.175.128.233/32`) |
| 4.2 | Set default action **Deny** |
| 4.3 | Enable **HTTPS Only** on App Service |
| 4.4 | Verify SCM/Kudu access policy (prod allows all on SCM — decide if staging should differ) |
| 4.5 | Smoke-test deploy pipeline (`azure_webapp_tools.bat staging deploy`) |

---

### Phase 5 — DNS cutover

| Record | Current (assumed) | Target |
|--------|-------------------|--------|
| `databank-stage.ifrc.org` | CNAME/ALIAS → App Service or Azure default | Point to **staging AppGW frontend** |
| `go-stage.ifrc.org` | CDN custom domain | Re-verify after CDN move (may be unchanged) |

**Cutover strategy:** Lower TTL 24–48 h before change; validate AppGW with `/etc/hosts` or `curl --resolve` before flipping DNS.

---

### Phase 6 — Update repo tooling & CI

Files referencing `ifrctgo001rg` today:

| File | Update |
|------|--------|
| `azure_webapp_tools.bat` | `STAGING_RESOURCE_GROUP` |
| `azure-webapp/azure_webapp_config.ps1` | `ResourceGroup` for STAGING |
| `azure-webapp/azure_webapp_deploy.ps1` | Comments / defaults |
| `Backoffice/azure/loadtest/loadtest.config.yaml` | Load test resource ID |
| `Backoffice/azure/loadtest/run-azure-loadtest.ps1` | Resource group |
| `.github/workflows/android-build.yml`, `ios-build*.yml` | No RG change (URLs only) |

---

### Phase 7 — Cleanup & hardening

| # | Task |
|---|------|
| 7.1 | Remove stale PostgreSQL firewall rules (developer IPs) if private connectivity works |
| 7.2 | Review whether 210 `FrontendCDNTemplateSpec` versions in `ifrctgo001rg` can be purged |
| 7.3 | Document staging AppGW PIP and runbook for deployers (SSH/deploy still via Azure CLI; not through AppGW) |
| 7.4 | Align staging load-test origin (`databank-stage.ifrc.org`) post-AppGW |

---

## 10. Resource move matrix (summary)

| Resource | Move to new RG? | AppGW impact | Downtime risk |
|----------|:---------------:|:------------:|:-------------:|
| `ifrc-databank-staging-2` | Yes | Backend target | Medium (restart) |
| `asp-ifrc-databank-staging` | Yes | — | Medium |
| `ifrc-databank-db-staging-2` | Yes | None (private EP optional) | **High** (plan window) |
| `ifrcdatabankstorage2` | Yes | None | Low |
| `gostoragestage` | Yes* | CDN origin | Low |
| `go-frontend-cdn-stage` | Yes* | Frontend edge | Medium |
| `databank-keyvault-stag` | Yes | None | Low |
| `databank-stage` (cert) | Yes | TLS termination depends on AppGW vs app | Low |
| App Insights + alerts | Yes | None | Low |
| `DatabankTest1` | Yes | None | Low |
| `unpl1-vnet`, VMs, `tgostagekeyvault` | **No** | None | — |
| Template spec versions (×210) | **No** (cleanup separately) | None | — |

\*Confirm ownership with GO/frontend team before moving CDN assets.

---

## 11. External dependencies (unchanged by RG move)

| Service | Staging endpoint | Notes |
|---------|------------------|-------|
| Container registry | `ifrcimage.azurecr.io` | Shared; cross-subscription pull |
| IFRC Translate API | `ifrc-translationapi-staging.azurewebsites.net` | External App Service |
| IFRC Email microservice | `microservices.ifrc.org/Email/api/Email` | Shared prod/stg URL in settings |

---

## 12. Risks & mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| AppGW config owned by separate subscription | Blocks staging lock-down | Early infra engagement; document required RBAC |
| DB move causes staging outage | Dev/test blocked | Maintenance window; pre-move backup; rehearse on clone if available |
| DNS cutover breaks mobile/CI builds | Pipeline failures | Staged TTL lowering; keep azurewebsites.net fallback temporarily |
| Storage/CDN move breaks static assets | 404 on uploads/frontend | Move storage before CDN; purge CDN after validation |
| Wildcard cert expiry **2026-09-01** | TLS failure | Renew/rebind cert during migration window |
| IP restriction lockout before AppGW ready | Total staging outage | Apply deny rules **only after** AppGW path verified |
| Shared VNet subnet exhaustion | Cannot integrate app | Infra to allocate dedicated staging subnet |
| Template-spec clutter obscures RG hygiene | Ops confusion | Separate cleanup project; do not bundle with Databank move |

---

## 13. Open questions for infra colleagues

1. **AppGW placement:** New staging AppGW instance, or additional listener/backend on the existing prod AppGW appliance in subscription `3d7b0c75-…`?
2. **Staging AppGW public IP:** New dedicated PIP, or shared front-end IP with host-based routing?
3. **WAF policy:** Reuse prod WAF ruleset or relaxed rules for staging?
4. **VNet/subnet:** Can we reuse `IFRC-NONPROD-APPS-VNET` with a new subnet, or is a separate staging spoke required?
5. **PostgreSQL private endpoint:** Hub DNS zone linkage for `privatelink.postgres.database.azure.com` — same as prod?
6. **CDN ownership:** Should `go-frontend-cdn-stage` / `gostoragestage` / `go-stage.ifrc.org` move with Databank or into a GO-team RG?
7. **Certificate termination:** TLS at AppGW (preferred for parity) or continue App Service managed cert?
8. **Developer access post-lockdown:** VPN/bastion/jump box for direct App Service access when IP restrictions enabled?
9. **Azure Load Testing:** Does `DatabankTest1` require public staging URL or can it use internal AppGW hostname?
10. **Cleanup:** Approval to delete orphaned `FrontendCDNTemplateSpec/*` versions from `ifrctgo001rg`?

---

## 14. Suggested timeline (indicative)

| Week | Activity |
|------|----------|
| W1 | Infra review of this document; answers to §13; approve target RG + AppGW design |
| W2 | Create RG; provision subnet + AppGW listener (no DNS change); VNet integrate app |
| W3 | Maintenance window: move DB + storage + app; private endpoint; internal testing |
| W4 | DNS cutover; enable IP restrictions + HTTPS-only; update repo tooling |
| W5 | Monitor; cleanup firewall rules; optional CDN/template-spec housekeeping |

---

## 15. Validation checklist (post-migration)

- [ ] `https://databank-stage.ifrc.org/health` returns 200 via AppGW
- [ ] Direct access to `*.azurewebsites.net` blocked from internet (if deny rules applied)
- [ ] Deploy via `azure_webapp_tools.bat staging deploy` succeeds
- [ ] SSH via `azure_webapp_tools.bat staging ssh` still works for operators
- [ ] Login + form submission + file upload against staging DB/storage
- [ ] Application Insights receiving telemetry
- [ ] Availability test alert firing on synthetic failure (test alert channel)
- [ ] Mobile CI builds against `https://databank-stage.ifrc.org` pass
- [ ] `go-stage.ifrc.org` frontend loads (if CDN moved)

---

## 16. Appendix — Azure CLI commands used

```powershell
# Subscriptions
az account list -o table

# Staging inventory
az account set --subscription "f585c1c3-801b-4641-8d7f-145aa50ffb04"
az group list -o table
az resource list -g ifrctgo001rg -o table
az webapp show -n ifrc-databank-staging-2 -g ifrctgo001rg
az appservice plan show -n asp-ifrc-databank-staging -g ifrctgo001rg
az postgres flexible-server show -n ifrc-databank-db-staging-2 -g ifrctgo001rg
az network vnet show -n unpl1-vnet -g ifrctgo001rg
az cdn endpoint show -n go-frontend-stage --profile-name go-frontend-cdn-stage -g ifrctgo001rg

# Production comparison
az account set --subscription "3e33b4c1-ada7-4922-9113-b9e41eaf1797"
az resource list -g ifrcpunifiedplanning-rg001 -o table
az webapp show -n ifrc-databank-app -g ifrcpunifiedplanning-rg001
az postgres flexible-server show -n databank-db -g ifrcpunifiedplanning-rg001
```

**Repo tooling entry point:** `azure_webapp_tools.bat staging …` (sets Non-Prod subscription automatically).

---

## 17. Document history

| Date | Change |
|------|--------|
| 2026-07-21 | Initial inventory and migration plan from live Azure CLI queries |
