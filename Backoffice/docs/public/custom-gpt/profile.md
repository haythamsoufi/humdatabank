# Custom GPT profile (ChatGPT Configure fields)

Copy these into the GPT editor under **Configure** (not Instructions).

## Name

**IFRC Network Databank**

Alternative: **IFRC Humanitarian Databank — FDRS & UPR**

---

## Description (max 300 characters)

Use **one** of these in the Description field:

### Recommended — FDRS + UPR data & documents (251 chars)

```
Explore IFRC public FDRS annual statistics and UPR (Unified Planning & Reporting): indicator trends, country comparisons, funding & key NS figures, plus cited Unified Plan and report excerpts. Official public data and documents from databank.ifrc.org.
```

### Alternative — explicit split (289 chars)

```
Ask about IFRC Network Databank public FDRS data (volunteers, staff, branches, reach) and UPR planning data and documents (Unified Plans, reports, focus areas, funding). Trends, comparisons, and cited summaries from databank.ifrc.org.
```

### Shorter (199 chars)

```
IFRC FDRS statistics and UPR plans & reports in one place: global trends, country data, funding priorities, and cited Unified Plan excerpts from the public Network Databank.
```

---

## Conversation starters

ChatGPT allows up to **4** starters. The **recommended set** gives **two FDRS** and **two UPR document** starters (single-country plan + cross-country theme).

### Recommended set (FDRS + UPR data + UPR documents)

| # | Domain | Starter |
|---|--------|---------|
| 1 | **FDRS** | How many volunteers were reported globally each year? Show the trend. |
| 2 | **FDRS** | Compare paid staff in Kenya and Bangladesh for the latest annual period. |
| 3 | **UPR documents** | Summarize the strategic focus areas in Syria’s Unified Plan 2026. |
| 4 | **UPR documents** | Which countries mention migration activities in their 2026 Unified Plans? Summarize by country with citations. |

### Alternative — planning & reports emphasis

| # | Domain | Starter |
|---|--------|---------|
| 1 | **UPR documents** | What are the main priorities in Afghanistan’s public Unified Country Report? |
| 2 | **UPR data** | Compare branches and local units for two countries from UPR/FDRS public indicators. |
| 3 | **FDRS** | Top 10 countries by number of volunteers in Annual 2023 |
| 4 | **FDRS** | Which National Societies reported volunteer data in Annual 2023? |

### Alternative — focal point / country officer

| # | Domain | Starter |
|---|--------|---------|
| 1 | **UPR documents** | Summarize focus areas in [country] Unified Plan [year] with page citations |
| 2 | **UPR data** | Key NS figures (volunteers, staff, branches) for [country] — latest period |
| 3 | **FDRS** | FDRS trend for people reached — by reporting year |
| 4 | **Both** | How do FDRS and UPR definitions differ for volunteers and staff? |

Use literal country/year in the editor (e.g. Syria, 2026) if placeholders are not allowed.

---

## Capabilities blurb (website, share card, `/gpt` landing copy)

> The **IFRC Network Databank assistant** answers questions from **public** Federation data in two complementary programmes:
>
> - **FDRS** — annual National Society statistics (volunteers, staff, branches, people reached, income/expenditure, and related KPIs).
> - **UPR** — Unified Planning & Reporting: **numeric** plan/report indicators (key NS figures, funding, impact metrics) and **documents** (Unified Country Plans, Unified Country Reports, strategic priorities) when marked public in the Knowledge Base.
>
> Ask for global trends, country comparisons, indicator definitions, funding figures, or cited plan/report summaries. Source: [databank.ifrc.org](https://databank.ifrc.org). Private submissions and internal-only documents are excluded.

---

## What *not* to promise

- Non-public NS submissions or full PDF downloads
- Real-time emergency operations data
- Logged-in Backoffice / focal-point workflows
- Complete coverage for every country, plan year, or document (depends on public reporting and `is_public` documents)
