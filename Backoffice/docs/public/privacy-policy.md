# Privacy policy — public API and integrations

**Last updated:** August 2026

This page describes how the IFRC Network Databank (**Databank**) handles information when you use **public, read-only** services such as the public REST API, the Model Context Protocol (MCP) endpoint, and third-party assistants (for example ChatGPT Custom GPTs) configured to call those services.

It does **not** replace your organisation’s policies for logged-in use of the Databank portal, mobile app, or authenticated API access.

## Who operates this service

The Databank is operated by the International Federation of Red Cross and Red Crescent Societies (IFRC) and participating National Societies. The production site is [https://databank.ifrc.org](https://databank.ifrc.org).

## What these public integrations do

Public integrations allow software (including AI assistants) to **read** humanitarian indicator metadata and **public** submitted statistical values from the Databank API. Examples:

- Search the indicator bank (`/api/v1/indicator-bank`)
- Fetch scoped public form data (`/api/v1/data`) for indicators marked **public** in the Databank
- Compact analytics for AI assistants (`/api/v1/public/global-trend`, `/api/v1/public/indicators/resolve`)
- Search public document chunks (`/api/v1/public/documents/search`) from the AI Knowledge Base

Configuration for the official Custom GPT is maintained in [`docs/public/custom-gpt/`](../docs/public/custom-gpt/README.md).

No login is required for these scoped public reads. Integrations **cannot** use the public endpoints to access private or internal-only form items, authenticated exports, or user account data.

## Information the public API returns

Responses may include:

- Indicator names, definitions, units, sectors, and related catalogue metadata
- Aggregated or country-level **statistical values** that National Societies have submitted and marked as **public** visibility
- Reference tables needed to interpret values (for example country names and ISO codes)

The public API is designed **not** to expose personal identifiers from submissions. Operational guidance for focal points is to avoid personal data in public-facing indicators.

## Information we collect from you when using public integrations

When you (or an AI assistant on your behalf) call the public API or MCP endpoint:

- We process **HTTP request metadata** (for example IP address, timestamp, URL, user agent) in server and security logs, as with normal web traffic
- We do **not** require an API key, account, or profile for scoped public `/data` access
- Third-party assistants (OpenAI, Anthropic, Microsoft, etc.) process queries and API responses under **their own** privacy policies when you use their products

We do not sell personal data from public API use.

## MCP and AI assistant endpoints

- **MCP URL (production):** `https://databank.ifrc.org/mcp`
- **Purpose:** Lets supported clients call Databank tools that proxy the public API
- **Authentication:** None for public tools
- **Data flow:** Your assistant → Databank MCP/proxy → public API → aggregated public statistics returned to your assistant

Configure assistants to use only official IFRC Databank URLs. Do not enter portal passwords or API keys into public GPT instructions unless your organisation explicitly approves authenticated access.

## Data retention and security

- Public API responses may be cached briefly at the edge for performance
- Server logs are retained according to IFRC infrastructure and security policies
- Authenticated portal data is subject to separate access controls and retention rules not covered by this public-read notice

## Your responsibilities

If you build or publish a Custom GPT, MCP client, or other integration:

- Use only **public** endpoints unless you have contractual authorisation for authenticated access
- Do not republish raw exports in ways that violate National Society data-sharing rules
- Treat combined API outputs as **operational statistics**, not personal records

## Contact

For questions about this policy or the public API:

- Use your National Society or IFRC Databank administrator contact channel
- Portal: [https://databank.ifrc.org](https://databank.ifrc.org)

## Related internal guidance

Logged-in users: see **Help → Data reporting → Data handling and privacy** in the Databank portal for focal-point guidance on submissions and exports.
