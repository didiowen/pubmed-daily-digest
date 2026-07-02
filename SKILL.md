---
name: pubmed-daily-digest
description: |
  Daily medical-literature digest agent — searches the past 24 hours on PubMed
  across configurable thematic queries, fills in missing abstracts via CrossRef,
  writes a TL;DR and a one-line Hot Take for each article (English by default;
  language is configurable in Step 2/3), picks 3–5 notable highlights, and
  renders a Markdown digest to a local output directory.

  Trigger when the user says "run daily digest", "daily lit", "daily journal",
  "medical literature digest", or "跑每日文獻". For yearly maintenance the
  skill also handles "update SJR scores" / "refresh journal rankings" — see
  the Maintenance section near the bottom.
---

# PubMed Daily Digest

> A Claude Code skill that pulls fresh PubMed articles every day across a few
> thematic queries, refills missing abstracts via CrossRef, summarises each in
> English, picks 3–5 notable highlights, and writes a Markdown digest to a
> local output directory. Publishing the digest anywhere is up to you.

## Configuration

Edit these values in this file before running in a new setup:

| Key                | Default                                  | Notes                                                       |
|--------------------|------------------------------------------|-------------------------------------------------------------|
| `OUTPUT_DIR`       | `output/` (inside this skill folder)     | Where `{DATE}.md`, `{DATE}_raw.json`, `{DATE}_daily.json` go |
| `TIMEZONE`         | `UTC`                                    | IANA name passed to `ZoneInfo` in Step 0                    |
| `CROSSREF_MAILTO`  | `pubmed-daily-digest@noreply.example`    | CrossRef polite-pool identifier                             |
| `QUERIES`          | Four thematic queries, see Step 1 table  | Customise freely — see `README.md` for guidance             |

Scripts in `scripts/` resolve `sjr_curated.json` and the rolling `.seen_pmids.json`
cache relative to their own path, so they work from any cwd as long as the
folder layout is intact.

**Before the first run, build your own `sjr_curated.json`.** The repo ships
`sjr_curated.example.json` only as a schema reference — its contents reflect
the original author's specialty interests. Either copy and edit it for your
own journals, or ask Claude to bootstrap one for your specialty using the
Maintenance workflow below. If `sjr_curated.json` is absent, the filter
still runs but every article gets `if_score = 0` and the per-section IF
sort becomes order-of-arrival.

## Date handling

Runs use the **system clock + a configured timezone** to derive today's date.
Don't infer the date from filenames, git logs, or chat context — only the
Python clock is trustworthy.

```python
from datetime import datetime
from zoneinfo import ZoneInfo

TIMEZONE = "UTC"          # change to e.g. "Asia/Taipei", "America/New_York"
DATE = datetime.now(ZoneInfo(TIMEZONE)).strftime("%Y-%m-%d")
```

`DATE` is the canonical label used for output filenames and PubMed `edat`
queries. If PubMed returns 0 articles for `DATE` across all four queries
(common early in the morning), Step 1 falls back to `DATE − 1`.

---

## Step 0 — Confirm today's date

Get `DATE` via the snippet above, then sanity-check:

1. If `{OUTPUT_DIR}/{DATE}.md` **already exists**: today's digest was already
   built. Stop and tell the user (don't silently overwrite).
2. Confirm `DATE` is within 2 days of the most recent existing `.md` in
   `{OUTPUT_DIR}/`. A bigger gap usually means a system-clock anomaly — stop
   and ask the user.

---

## Step 1 — PubMed search + Python filter

Call `mcp__PubMed__search_articles` **in parallel** with `datetype=edat`,
`date_from=date_to=DATE`, `max_results=200`. Four default queries:

| Section | Query |
|---------|-------|
| `transplant_id` (part 1) | `aspergillosis[tiab] OR mucormycosis[tiab] OR "invasive fungal infection"[tiab] OR "invasive fungal disease"[tiab] OR candidemia[tiab] OR "invasive candidiasis"[tiab] OR cryptococcosis[tiab] OR "pneumocystis jirovecii"[tiab] OR "pneumocystis carinii"[tiab] OR PJP[tiab] OR "BK virus"[tiab] OR BKV[tiab] OR fusariosis[tiab] OR scedosporiosis[tiab] OR Scedosporium[tiab] OR PTLD[tiab] OR "post-transplant lymphoproliferative"[tiab]` |
| `transplant_id` (part 2) | `(cytomegalovirus[tiab] OR CMV[tiab] OR EBV[tiab] OR "Epstein-Barr virus"[tiab] OR toxoplasmosis[tiab] OR Strongyloides[tiab] OR histoplasmosis[tiab] OR nocardiosis[tiab] OR Nocardia[tiab] OR mycobacterium[tiab] OR tuberculosis[tiab] OR NTM[tiab]) AND (transplantation[tiab] OR SOT[tiab] OR HSCT[tiab] OR immunocompromised[tiab] OR immunosuppressed[tiab] OR HIV[tiab] OR AIDS[tiab] OR letermovir[tiab] OR maribavir[tiab])` |
| `one_health` | `zoonosis[tiab] OR zoonoses[tiab] OR zoonotic[tiab] OR "one health"[tiab] OR "zoonotic spillover"[tiab] OR "viral spillover"[tiab] OR "pathogen spillover"[tiab] OR "interspecies transmission"[tiab]` |

> **Customising the queries**: edit this table to fit your interests, then
> update `SECTION_HEADERS` / `SECTION_ORDER` in `scripts/build_daily_md.py` to
> match. See `README.md` → "Customising the queries" for worked examples.

**PubMed MCP caveats** (apply to every query):

- **No wildcards** — `mycobacteri*` fails with `INVALID_PARAMETERS`. Expand
  with `OR`: `mycobacterium OR tuberculosis`.
- **20-operator cap** — a single query with more than 20 `AND`/`OR`s fails.
  Split into two parallel sub-queries when needed (as `transplant_id` does
  above).
- **`max_results` ceiling is 200**.

Union the two `transplant_id` sub-queries' PMIDs, then for each of the three
sections call `mcp__PubMed__get_article_metadata` in batches of **≤ 20 PMIDs**
(larger batches are silently truncated).

Write the raw metadata to `{OUTPUT_DIR}/{DATE}_raw.json` in this shape
(`reldate`: `0` = same-day query; `1` = fallback to `DATE − 1`):

```json
{
  "meta": {"date": "YYYY-MM-DD", "reldate": 0},
  "raw_sections": {
    "transplant_id": [<get_article_metadata records>],
    "one_health":    [...]
  }
}
```

Then run the Python filter:

```sh
python scripts/daily_feed_filter.py {DATE}
```

It reads `{OUTPUT_DIR}/{DATE}_raw.json`, drops noise/basic-science/non-English
articles, sorts by the SJR score from `sjr_curated.json`, applies per-section
caps, and writes `{OUTPUT_DIR}/{DATE}_daily.json`. It also updates a rolling
`.seen_pmids.json` (7-day TTL) so the next run doesn't re-cover the same
article.

**Fallback to `DATE − 1`**: if all four PubMed queries return 0 articles, rerun
with `date_from=date_to=DATE−1` and set `meta.reldate = 1` in `_raw.json` —
the filter then excludes any PMIDs already present in the previous day's
digest (via the `<!-- pmids: ... -->` marker the digest emits).

---

## Step 2 — TL;DR annotation (English by default)

Read `{OUTPUT_DIR}/{DATE}_daily.json`. Each article record has fields
`pmid`, `title`, `journal_full`, `journal_abbr`, `authors`, `abstract`,
`pubdate`, `doi`, `article_types`, `language`, `if_score`, `section`,
`tldr`, `comment`.

### Refill missing abstracts via CrossRef (first)

For any article whose `abstract` is empty **or** starts with `[` (PubMed
sometimes returns `"[Abstract not available]"` as a string), if a `doi` is
present, query CrossRef:

- Endpoint: `https://api.crossref.org/works/{urlencoded_doi}?mailto={CROSSREF_MAILTO}`
- User-Agent: `pubmed-daily-digest/1.0`
- Timeout: 15 seconds; cache by DOI within one run.
- If `message.abstract` is present in the response: strip JATS/HTML tags and
  collapse whitespace, then write back to the article's `abstract` field.
- If CrossRef returns no abstract, non-200, timeout, or parse failure: do NOT
  abort. Keep the article in a "still missing abstract" list (its TL;DR and
  Hot Take stay blank; report the PMID at the end so the user can backfill).

### TL;DR rules

For each article that has an abstract:

- **English, 1–2 sentences**, focused on study design + key finding +
  clinical implication.
- Keep drug names and pathogen names (bacterial / viral / fungal) in their
  canonical form; do not translate the article title.
- No filler openings like "This study investigates…" — state the finding.

Write `tldr` back into the JSON in place
(`json.dump(..., ensure_ascii=False, indent=2)`).

> **Change the output language**: this step is pure prompting. Replace
> "English, 1–2 sentences" with "Traditional Chinese, max 50 字" / "Spanish,
> two sentences" / etc. Claude translates the source abstract on the fly;
> nothing else in the skill needs editing.

---

## Step 3 — Hot Take annotation

For every article that has a `tldr`, write a one-line **Hot Take** in
English. Pick the register that fits the content:

- *Positive* — for hopeful findings, breakthroughs, good outcomes
  (excited / cheerful tone).
- *Snarky* — for bad news, hard pathogens, depressing epidemiology, or old
  problems with no new answers (deadpan / self-aware, not cruel).

Length: one short sentence (target ≤ 20 words). If `tldr` is blank (no
abstract), leave `comment` blank too.

Write back in place.

> Same language-swap rule as Step 2 applies. Edit "in English" above to your
> preferred language.

---

## Step 3.5 — Notable Highlights

From articles that have a `tldr`, select **3–5** worth flagging. Criteria,
in priority order:

1. High clinical-practice impact (guideline updates, new therapies,
   management-changing findings).
2. High-IF journals (≥ 5) with novel or immediately actionable findings.
3. Public-health urgency (new pathogens, confirmed transmission chains, food /
   zoonotic alerts).
4. Locally relevant epidemiology (adjust this criterion to your region).

For each highlight, write a one-sentence reason (≤ 30 words) explaining *why
this is worth a second look* — don't just restate the TL;DR.

Store them on `meta.highlights`:

```json
{
  "meta": {
    "date": "YYYY-MM-DD",
    "reldate": 0,
    "highlights": [
      {"pmid": "12345678", "title": "...", "reason": "..."}
    ]
  },
  "sections": { ... }
}
```

Write back in place.

---

## Step 4 — Build the Markdown digest

```sh
python scripts/build_daily_md.py {OUTPUT_DIR}/{DATE}_daily.json
```

The script writes `{OUTPUT_DIR}/{DATE}.md` next to the input JSON. The
template (frontmatter, section headers, per-article block, empty-section
placeholder, PMID footer) is controlled by the script — edit
`SECTION_HEADERS` / `SECTION_ORDER` / `fmt_*` in
`scripts/build_daily_md.py` if you want a different layout.

---

## Step 5 — Save (optional commit)

The digest is now at `{OUTPUT_DIR}/{DATE}.md`. Stop here unless the user
explicitly asks to commit or publish.

If they want a vault commit:

```sh
git add {OUTPUT_DIR}/{DATE}.md
git commit -m "daily digest {DATE}"
```

Publishing somewhere else (a notes site, a blog, an SSG) is the user's call.

Clean up intermediate JSON after the digest is safely committed/published:

```sh
rm {OUTPUT_DIR}/{DATE}_raw.json {OUTPUT_DIR}/{DATE}_daily.json
```

Final report to the user: total articles, per-section counts, the highlights
list, and any PMIDs still missing abstracts (for manual backfill next run).

---

## Maintenance — build / refresh `sjr_curated.json`

`sjr_curated.json` is a small lookup table from journal abbreviation / title
to SJR (Scimago Journal Rank) score. The filter script uses it to rank and
cap articles within each section. Two scenarios use the same workflow:

- **First-time bootstrap** — the user just installed the skill and there's no
  `sjr_curated.json` yet.
- **Yearly refresh** — SCImago publishes new rankings around June each year;
  existing scores drift over time.

**Trigger phrases**: "build sjr_curated", "update SJR scores",
"refresh journal rankings".

**Schema** (preserve this exactly):

```json
{
  "journals": [
    {
      "title": "The New England Journal of Medicine",
      "abbr": "N Engl J Med",
      "sjr": 34.6,
      "if": 96.2,
      "cluster": "general"
    }
  ]
}
```

`abbr` (NLM Title Abbreviation) and `title` are both used for lookup; `if`
is the field the filter script reads as the score. `sjr` and `cluster` are
metadata for human reference. Look up NLM abbreviations at
https://www.ncbi.nlm.nih.gov/nlmcatalog/journals.

**Workflow** (prompt-driven — no extra script):

1. **First-time bootstrap**: ask the user which medical specialties /
   topics they care about (Infectious Diseases, Hematology, Cardiology,
   Oncology, etc.). For each specialty, pick the top ~10–30 journals by
   reputation / SJR rank. Aggregate into a single list; aim for 50–200
   entries total. If `sjr_curated.example.json` is present and the user
   wants to start from it, copy and trim instead of starting empty.
2. **Yearly refresh**: read the existing `sjr_curated.json` — that's the
   curated journal list. **Do not expand it** during a refresh; only
   update scores.
3. Visit `https://www.scimagojr.com/` and locate the current per-category
   ranking download (SCImago has changed their URL scheme historically, so
   check the live site rather than hardcoding a URL).
4. For each journal in the working list, match by NLM abbreviation / full
   title and pull the latest `sjr` and `if` (or the closest available
   proxy — SCImago publishes SJR; impact factors come from a separate
   source like Web of Science or Clarivate).
5. Report: how many journals updated, which couldn't be matched (so the
   user can fix manually), and median SJR shift (sanity check that the
   right year loaded).
6. Save to `sjr_curated.json` (preserving the schema).

Skipping a refresh isn't fatal — digests still rank/filter, just with stale
or zero scores.

---

## Error handling

| Situation                                       | Action                                                                                          |
|-------------------------------------------------|-------------------------------------------------------------------------------------------------|
| All four PubMed queries return 0 articles       | Retry with `DATE − 1` and set `reldate = 1` in `_raw.json`                                      |
| `daily_feed_filter.py` exits non-zero           | Report and stop — don't continue to Step 2                                                      |
| One query returns 0 articles                    | Continue; that section's Markdown shows a placeholder                                           |
| CrossRef fails for an article (any reason)      | Continue; leave `tldr` and `comment` blank; report PMID in the final summary                    |
| `{OUTPUT_DIR}/{DATE}.md` already exists         | Stop and report — don't silently overwrite a digest                                             |
| `sjr_curated.json` missing                      | Filter still runs (`if_score = 0` for all); see the Maintenance section to build / refresh it    |
