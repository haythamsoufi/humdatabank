# IFRC Network Databank — Custom GPT configuration

Canonical files for the shareable ChatGPT Custom GPT:

| File | Use in ChatGPT |
|------|----------------|
| [`instructions-core.md`](instructions-core.md) | **Instructions** field (paste; must stay **≤8000** chars) |
| [`instructions.md`](instructions.md) | **Knowledge** upload (full workflows, FDRS/UPR detail) |
| [`openapi.yaml`](openapi.yaml) | **Actions → Import from URL** or paste schema |
| [`profile.md`](profile.md) | **Name**, **Description**, **Conversation starters** |
| This README | Maintainer notes only |
| [`../../../humanitarian-databank-mcp/README.md`](../../../humanitarian-databank-mcp/README.md) | **MCP connector** (Claude/Cursor; same tools as Actions) |

ChatGPT caps the **Instructions** field at **8000 characters**. The full [`instructions.md`](instructions.md) is ~20k chars — use the hybrid setup below, not a full paste.

**Live GPT (production):** [IFRC Network Databank](https://chatgpt.com/g/g-6a7217c375ac81919b0913bdd4ef15b6-ifrc-network-databank)  
**Short link:** `https://databank.ifrc.org/gpt` (redirects to the GPT after Backoffice deploy)  
**Privacy policy URL (GPT settings):** `https://databank.ifrc.org/privacy`

## When to update

Update these files whenever you change public integration endpoints under `/api/v1/public/*`, slim `/data` behaviour, or product guidance for FDRS / UPR / documents. After merging to `main`, redeploy Backoffice if new routes are involved, then re-import or paste the schema in ChatGPT and refresh instructions.

## ChatGPT setup checklist

1. **Create / edit GPT** → Configure → Actions → import [`openapi.yaml`](openapi.yaml) (or paste manually; max ~30 operations).
2. **Schema limits:** ChatGPT rejects operation `description` fields longer than **300 characters** — keep [`openapi.yaml`](openapi.yaml) concise (details belong in [`instructions.md`](instructions.md)).
3. **Action payload limit:** request and response bodies must stay under **~100,000 characters** each or ChatGPT returns `ResponseTooLargeError`. Use `full_coverage=true` with `page`/`per_page` for cross-country document queries; keep `top_k≤12` for non–full-coverage search.
4. **Authentication:** None (public endpoints only).
5. **Instructions:** paste [`instructions-core.md`](instructions-core.md) (~7.5k chars, stay under 8000).
6. **Knowledge:** upload [`instructions.md`](instructions.md) as a reference file (full workflows). The file includes rules **not** to cite it in user answers — refresh Instructions + Knowledge together after edits.
7. **Description & starters:** copy from [`profile.md`](profile.md).
8. **Privacy policy:** `https://databank.ifrc.org/privacy`.

### GPT cites `instructions.md` as a source

ChatGPT can treat uploaded **Knowledge** as citable material. If the live GPT lists `instructions.md` (or “knowledge file”) in a **Sources** block:

1. Re-paste [`instructions-core.md`](instructions-core.md) into **Instructions** (includes **Sources (strict)**).
2. Re-upload [`instructions.md`](instructions.md) to **Knowledge** (top banner + **Sources users may see**).
3. Optional: rename the upload in the GPT editor to something like `databank-operator-guide` (filename alone does not fix behavior; the content rules do).

## Related repo docs

- Public API skill (Cursor): [`.cursor/skills/humanitarian-databank-api/SKILL.md`](../../../../.cursor/skills/humanitarian-databank-api/SKILL.md)
- FDRS reporting context: [`data-reporting/data-guidance-fdrs.md`](../../data-reporting/data-guidance-fdrs.md)
- UPR reporting context: [`data-reporting/data-guidance-upr.md`](../../data-reporting/data-guidance-upr.md)
- Public privacy notice: [`privacy-policy.md`](../privacy-policy.md)
