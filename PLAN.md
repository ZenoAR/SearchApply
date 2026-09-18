# SearchApply — Job Application Engine

## Overview

A CLI pipeline that pulls relevant job postings, analyzes them against your current skills, generates tailored resumes/cover letters, tracks application status, and surfaces the most common skill/question patterns across postings so study time is prioritized correctly.

Human review before submission is a hard constraint at every generation step — this tool drafts, it never auto-submits.

## Pipeline

```
source → ingest → analyze → draft → review → track → report
```

| Step | Purpose |
|---|---|
| **source** | Pull postings from ATS APIs (Greenhouse/Lever) for target companies + role-keyword searches; OR manual paste-in of a posting URL/text |
| **ingest** | Normalize raw posting (from either source) into a structured `postings/<id>.yaml` — title, company, description, requirements, raw text |
| **analyze** | Parse requirements → extract required/preferred skills, seniority signals, likely interview focus areas; diff against `skills.yaml` → gap list; compute `fit_score` (skill overlap %) |
| **draft** | Generate tailored resume variant (reordered/reweighted bullets, matched keywords) + cover letter, using `resume.yaml`, `stories.yaml`, `voice_samples.md` |
| **review** | You review/edit the draft before anything is marked ready — hard gate, never skipped |
| **track** | Log status in `tracker.csv`: saved → applied → interviewing → offer/rejected, with dates |
| **report** | Aggregate `analyze` output across all stored postings → frequency table of most-common required skills/quals → direct input into study priorities |

## Data files

```
/data
  resume.yaml         # existing — source of truth for experience/skills as stated
  stories.yaml         # existing — STAR-format stories for behavioral answers
  voice_samples.md     # existing — writing voice reference for draft step
  preferences.yaml     # existing — role/location/company preferences
  skills.yaml           # NEW — current actual skill level per skill, separate from resume.yaml
                        #   (resume.yaml = what's stated publicly; skills.yaml = honest self-assessment,
                        #    used for gap analysis so "practice this" targets reality, not the resume)
  companies.yaml        # NEW — target company list with ATS type + board slug, tiered (A/B)
  tracker.csv           # existing, extended schema below

/postings
  <posting_id>.yaml    # NEW — one file per posting: raw text + analyze output (skills required, fit_score, gap list)

/drafts
  <posting_id>_resume.md
  <posting_id>_cover_letter.md
```

### `tracker.csv` extended schema

```
posting_id, company, role, source, tier, date_saved, date_applied, status, fit_score, feedback_notes
```
`status` values: `saved`, `applied`, `interviewing`, `offer`, `rejected`, `withdrawn`

### `companies.yaml` shape

```yaml
- name: Fiserv
  tier: A
  ats: greenhouse
  board_slug: fiserv          # to be confirmed
- name: C2FO
  tier: A
  ats: unknown                # to be discovered
- name: "Sporting KC"
  tier: A
  ats: unknown
```

## ATS integration notes

- **Greenhouse public job board API**: `https://boards-api.greenhouse.io/v1/boards/{board_slug}/jobs` — returns JSON, no auth needed, no scraping/ToS issue.
- **Lever public API**: `https://api.lever.co/v0/postings/{company_slug}?mode=json` — same, public and structured.
- Not every company uses one of these — some run custom career pages (Workday, proprietary). For those, no clean API exists; fall back to manual paste-in (feature 6) rather than scraping.
- **First implementation task**: for each company in `companies.yaml`, determine which ATS (if any) they use — check their careers page URL pattern (a Greenhouse-hosted page usually shows `boards.greenhouse.io/{slug}` or embeds the API; Lever-hosted pages show `jobs.lever.co/{slug}`).

## `report` step — the highest-leverage feature

Aggregates `postings/*.yaml` analyze output into:
- Frequency table: skill/qualification → % of postings requiring it
- Sorted output feeds directly into interview-practice priorities (practice the top-frequency gaps first, not a random order)
- Also surfaces most commonly asked question *types* if postings include them (e.g., listed screening questions)

## Build order (phased, so each phase is independently useful)

**Phase 1 — Manual-input MVP**
- `skills.yaml` schema + fill in current honest skill levels
- `ingest` step for manually pasted postings (feature 6)
- `analyze` step: skill extraction + gap diff + fit_score
- Extend `tracker.csv` schema
- This alone gives you feature 2, 3, 4, 6 without touching any API

**Phase 2 — Resume/cover letter tailoring**
- `draft` step: generate tailored resume variant + cover letter from `resume.yaml`/`stories.yaml`/`voice_samples.md` + the analyze output
- `review` gate (simple: print draft, confirm before saving as "ready")

**Phase 3 — Automated sourcing**
- Discover ATS per company in `companies.yaml`
- `source` step: pull from Greenhouse/Lever APIs, filter by role keywords, feed into `ingest`

**Phase 4 — Reporting**
- `report` step: cross-posting frequency tally
- Simple CLI output first; a small dashboard later if useful

## Open questions to resolve while building

- Confirm board slugs for target companies (Phase 3 prerequisite)
- Decide `fit_score` formula (simple % overlap vs weighted by required-vs-preferred)
- Decide whether `skills.yaml` self-assessment uses a numeric scale or tiers (e.g., "learning" / "comfortable" / "confident")
