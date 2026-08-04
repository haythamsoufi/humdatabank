# Humanitarian Databank MCP

MCP server that proxies the **public** IFRC Humanitarian Databank API for Claude,
Cursor, and other MCP clients.

## Tools

| Tool | Purpose |
|------|---------|
| `databank_aggregate_global_trend` | **Preferred** — deduped global totals by period (e.g. volunteers by year) |
| `databank_resolve_indicator` | Map natural-language metric names to indicator IDs |
| `databank_search_indicators` | Search indicator bank (ranked, slim, capped) |
| `databank_get_indicator` | One indicator's metadata |
| `databank_get_public_data` | One page of scoped public `/data` (dimensions stripped by default) |
| `databank_get_public_data_all_pages` | Auto-paginate public `/data` (raw rows; not deduped) |
| `databank_api_info` | Configured base URL |

### Recommended flow

```text
databank_aggregate_global_trend(query="volunteers")
  → by_period totals (deduped, compact)

databank_resolve_indicator(query="total volunteers")
  → indicator id 724 (KPI_PeopleVol)

databank_get_public_data(indicator_bank_id=724, country_iso3="SYR")
  → raw rows for one country (include_dimensions only when joining)
```

**Do not** sum raw `/data` rows for network-wide totals — multiple submissions per
country+period exist. Use `databank_aggregate_global_trend` instead.

## Quick start (local)

```bash
cd humanitarian-databank-mcp
pip install -r requirements.txt
python server.py
```

Uses **stdio** transport (for Cursor / Claude Desktop local config).

### HTTP mode (Claude.ai remote connector)

**PowerShell (Windows):**

```powershell
cd humanitarian-databank-mcp
$env:MCP_TRANSPORT = "streamable-http"
$env:PORT = "8000"
python server.py
```

**cmd.exe:**

```bat
set MCP_TRANSPORT=streamable-http
set PORT=8000
python server.py
```

Endpoint: `http://127.0.0.1:8000/mcp` — **not** port 5000 (that is the Flask Backoffice).

`/mcp` is an MCP protocol endpoint (POST JSON-RPC), not a web page. A browser GET may
return 404/405; that is normal. Test via Cursor, Claude connector, or MCP Inspector.

Production: deploy `app` via `server:app` and gunicorn + uvicorn worker (see Dockerfile).

## Cursor

Already wired in `.cursor/mcp.json` as `humanitarian-databank`. Restart Cursor
after `pip install -r requirements.txt`.

## Claude.ai (remote connector)

1. Deploy this service to a **public HTTPS URL** (e.g. `https://mcp.databank.ifrc.org/mcp`).
2. Claude → **Settings → Connectors → Add custom connector**.
3. Paste the MCP URL → Connect → enable in chat.

Anthropic calls your server; your server calls `databank.ifrc.org`.

## Production deploy (Azure / Docker)

**Staging:** App Service `ifrc-databank-mcp-staging` in resource group `ifrctgo001rg`.  
**Image:** `ifrcimage.azurecr.io/databank_mcp:<tag>`  
**CI:** GitHub Actions workflow [`.github/workflows/deploy-mcp.yml`](../.github/workflows/deploy-mcp.yml) (manual or on push to `main` when `humanitarian-databank-mcp/**` changes).

### One-time GitHub secret

Download the staging publish profile and add it as **`AZURE_MCP_PUBLISH_PROFILE`** (repository → Settings → Secrets → Actions):

```powershell
az webapp deployment list-publishing-profiles `
  --resource-group ifrctgo001rg `
  --name ifrc-databank-mcp-staging `
  --xml
```

`ACR_USERNAME` and `ACR_PASSWORD` are shared with the Backoffice deploy workflow.

### Deploy via GitHub Actions

Actions → **Deploy MCP to Azure** → Run workflow → Staging → tag (e.g. `v1.1`).

### Backoffice proxy

Set on the Backoffice App Service that serves `/mcp`:

```text
MCP_UPSTREAM_URL=https://ifrc-databank-mcp-staging.azurewebsites.net
```

(no trailing slash). Staging Backoffice proxies `https://<staging-host>/mcp` to this upstream.

**Procfile / command:**

```bash
gunicorn server:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT
```

**Docker:**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn uvicorn
COPY databank_client.py server.py .
ENV MCP_TRANSPORT=streamable-http
CMD gunicorn server:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:${PORT:-8000}
```

**Env vars:**

| Variable | Default |
|----------|---------|
| `DATABANK_API_BASE` | `https://databank.ifrc.org/api/v1` |
| `PORT` | `8000` |

## Environment

Public API only — no API key required. Rate limits apply at the Databank API layer;
add reverse-proxy rate limiting in production if needed.

## Tests

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
```
