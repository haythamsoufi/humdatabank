# IFRC Network Databank — Custom GPT configuration

Canonical files for the shareable ChatGPT Custom GPT:

| File | Use in ChatGPT |
|------|----------------|
| [`instructions.md`](instructions.md) | **Instructions** field (copy full content) |
| [`openapi.yaml`](openapi.yaml) | **Actions → Import from URL** or paste schema |
| This README | Maintainer notes only |

**Live GPT (production):** [IFRC Network Databank](https://chatgpt.com/g/g-6a7217c375ac81919b0913bdd4ef15b6-ifrc-network-databank)  
**Short link:** `https://databank.ifrc.org/gpt` (redirects to the GPT after Backoffice deploy)  
**Privacy policy URL (GPT settings):** `https://databank.ifrc.org/privacy`

## When to update

Update these files whenever you change public integration endpoints under `/api/v1/public/*`, slim `/data` behaviour, or product guidance for FDRS / UPR / documents. After merging to `main`, redeploy Backoffice if new routes are involved, then re-import or paste the schema in ChatGPT and refresh instructions.

## ChatGPT setup checklist

1. **Create / edit GPT** → Configure → Actions → import [`openapi.yaml`](openapi.yaml) (or paste manually; max ~30 operations).
2. **Schema limits:** ChatGPT rejects operation `description` fields longer than **300 characters** — keep [`openapi.yaml`](openapi.yaml) concise (details belong in [`instructions.md`](instructions.md)).
3. **Authentication:** None (public endpoints only).
3. **Instructions:** paste [`instructions.md`](instructions.md).
4. **Privacy policy:** `https://databank.ifrc.org/privacy`.
5. **Suggested conversation starters** (optional):
   - Global volunteer trend by reporting year
   - Compare staff numbers for Kenya and Bangladesh
   - Summarize focus areas in Syria Unified Plan 2026
   - Which countries reported volunteers in Annual 2023?

## Related repo docs

- Public API skill (Cursor): [`.cursor/skills/humanitarian-databank-api/SKILL.md`](../../../../.cursor/skills/humanitarian-databank-api/SKILL.md)
- FDRS reporting context: [`data-reporting/data-guidance-fdrs.md`](../../data-reporting/data-guidance-fdrs.md)
- UPR reporting context: [`data-reporting/data-guidance-upr.md`](../../data-reporting/data-guidance-upr.md)
- Public privacy notice: [`privacy-policy.md`](../privacy-policy.md)
