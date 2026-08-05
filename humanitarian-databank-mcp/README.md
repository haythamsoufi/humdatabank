# IFRC Network Databank MCP

MCP server aligned with the [Custom GPT configuration](../Backoffice/docs/public/custom-gpt/README.md).
It proxies the **public** IFRC Humanitarian Databank API for Claude, Cursor, and other MCP clients.

**Scope:** FDRS + UPR **numeric data** and **public document** search (Unified Plans/Reports).

## Tools

| Tool | Custom GPT Action | Purpose |
|------|-------------------|---------|
| `databank_aggregate_global_trend` | `getGlobalTrend` | **Preferred** — deduped global totals by period |
| `databank_resolve_indicator` | `resolveIndicator` | Map natural-language metric names to indicator IDs |
| `databank_search_public_documents` | `searchPublicDocuments` | Public UPR/FDRS document chunks (cited Q&A) |
| `databank_search_indicators` | `getIndicatorBank` | Search indicator bank (ranked, slim, capped) |
| `databank_get_indicator` | `getIndicatorById` | One indicator's metadata |
| `databank_get_public_data` | `getPublicData` | One page of scoped public `/data` |
| `databank_get_public_data_all_pages` | — | Auto-paginate public `/data` (raw rows; not deduped) |
| `databank_api_info` | — | Configured base URL and endpoint summary |

Server instructions mirror [`instructions-core.md`](../Backoffice/docs/public/custom-gpt/instructions-core.md).

### Recommended flows

**FDRS trend:**
```text
databank_aggregate_global_trend(query="volunteers")
  → by_period totals (deduped, compact)
```

**UPR plan summary:**
```text
databank_search_public_documents(query="Syria unified plan 2026 focus areas")
  → chunks[] — cite document_title + page_number
```

**Cross-country UPR theme:**
```text
databank_search_public_documents(
  query="migration unified plan 2026",
  full_coverage=true
)
```

**Do not** sum raw `/data` rows for network-wide totals — use `databank_aggregate_global_trend`.
**Do not** set `include_dimensions=true` unless explicitly needed (matches Custom GPT).

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

Endpoint: `http://127.0.0.1:8000/mcp` — **not** port 5000 (Flask Backoffice).

Production: deploy `app` via `server:app` and gunicorn + uvicorn worker (see Dockerfile).

## Cursor

Wired in `.cursor/mcp.json` as `humanitarian-databank`. Restart Cursor after
`pip install -r requirements.txt`.

## Claude.ai (remote connector)

1. Deploy to a **public HTTPS URL** (e.g. `https://databank.ifrc.org/mcp` via Backoffice proxy).
2. Claude → **Settings → Connectors → Add custom connector**.
3. Paste the MCP URL → Connect → enable in chat.

Connector name: **IFRC Network Databank**. Icon:
`https://databank.ifrc.org/mcp/icon.svg` (default).

## Production deploy (Azure / Docker)

**Staging:** App Service `ifrc-databank-mcp-staging` in resource group `ifrctgo001rg`.  
**Image:** `ifrcimage.azurecr.io/databank_mcp:<tag>`  
**CI:** [`.github/workflows/deploy-mcp.yml`](../.github/workflows/deploy-mcp.yml)

### Backoffice proxy

```text
MCP_UPSTREAM_URL=https://ifrc-databank-mcp-staging.azurewebsites.net
```

**Env vars:**

| Variable | Default |
|----------|---------|
| `DATABANK_API_BASE` | `https://databank.ifrc.org/api/v1` |
| `MCP_PUBLIC_BASE_URL` | `https://databank.ifrc.org` (connector icon URL base) |
| `PORT` | `8000` |

## Tests

```bash
pip install -r requirements.txt
python -m pytest tests/ -q
```
