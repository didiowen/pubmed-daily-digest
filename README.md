# pubmed-daily-digest

A Claude Code skill that pulls the past 24 hours of new PubMed articles across a few configurable thematic queries, annotates each with a TL;DR and a one-line **Hot Take** (positive or snarky), selects 3–5 notable highlights, and renders a Markdown digest to a local output directory. Output is in English by default and the language is one prompt-edit away from anything else.

## Folder layout

```
pubmed-daily-digest/
├── SKILL.md                       # the skill
├── README.md                      # this file
├── LICENSE
├── sjr_curated.example.json       # schema reference — copy to sjr_curated.json and edit
├── output/                        # default destination for digests (kept by .gitkeep)
└── scripts/
    ├── daily_feed_filter.py       # filter, dedupe, rank, cap; produces {DATE}_daily.json
    └── build_daily_md.py          # render annotated JSON → {DATE}.md
```

You'll need to create your own `sjr_curated.json` (a small lookup from journal abbreviation / title to SJR score) — see [Building `sjr_curated.json`](#building-sjr_curatedjson) below. Scripts self-locate the file and the rolling `.seen_pmids.json` cache relative to their own path, so they work from any working directory as long as the folder layout is intact.

## Dependencies

- **Claude Code** (with the Skill system) — https://claude.com/claude-code
- **PubMed MCP server** configured in your Claude Code MCP settings
- **Python ≥ 3.9** for the two bundled scripts (stdlib only — no `pip install` step)
- No `.env` or API keys needed for the default workflow

## Setup

1. Drop this folder into the skills directory of any project: `<project>/.claude/skills/pubmed-daily-digest/`.
2. Confirm the PubMed MCP server is configured.
3. Open `SKILL.md` and edit the **Configuration** block at the top:
   - `OUTPUT_DIR` — default is the bundled `output/` folder; change if you'd rather write digests elsewhere.
   - `TIMEZONE` — default `UTC`; set to your IANA zone, e.g. `Asia/Taipei`, `America/New_York`, `Europe/Berlin`.
   - `CROSSREF_MAILTO` — any valid email (used as the CrossRef polite-pool identifier).
4. (Optional) Edit the four PubMed queries in Step 1 to match your interests — see [Customising the queries](#customising-the-queries) below.
5. **Build your own `sjr_curated.json`** — the filter uses it to rank articles by journal impact within each section. Either copy and trim `sjr_curated.example.json`, or ask Claude to build one for your specialties (see [Building `sjr_curated.json`](#building-sjr_curatedjson)). The filter still runs without this file, but every article gets `if_score = 0`.
6. Trigger from Claude Code: ask it to "run the daily digest" or invoke the skill by name.

## Customising the queries

This is the main thing you'll want to change. The default queries cover the original author's interests (transplant infectious disease, One Health, food security). Yours will probably look different.

### Where the queries live

`SKILL.md` → **Step 1 — PubMed search + Python filter** has a table with four queries split across three sections:

- `transplant_id` (two parallel sub-queries, unioned by PMID)
- `one_health`
- `food_security`

Each row becomes one parallel `mcp__PubMed__search_articles` call. You can edit the existing queries, swap a section out entirely, or add more sections.

### PubMed query basics

PubMed's query language uses field qualifiers to scope a term. The ones the default queries use:

| Field      | Meaning                                            |
|------------|----------------------------------------------------|
| `[tiab]`   | Title + abstract (most common for topic queries)   |
| `[Title]`  | Title only (stricter)                              |
| `[Mesh]`   | MeSH controlled-vocabulary term                    |
| `[Journal]` | Journal name (NLM abbreviation)                   |
| `[edat]`   | Entrez-added date (the skill sets this in Step 1)  |

Combine with `AND`, `OR`, `NOT`, and parentheses for grouping.

### Two PubMed MCP pitfalls

Real, learned by trial:

- **No wildcards.** `mycobacteri*` fails with `INVALID_PARAMETERS`. Expand with `OR`: `mycobacterium OR tuberculosis OR NTM`.
- **20-operator cap per query.** A single query with more than 20 `AND`/`OR`s fails. Split into two parallel sub-queries if you hit this — `transplant_id` in the defaults already does this. The Python filter unions PMIDs from sub-queries belonging to the same section.

### Worked example: swap a section

Suppose you don't care about food security but want **antimicrobial resistance** instead. Three edits, all in this repo:

1. **`SKILL.md`** — replace the `food_security` row in Step 1's table with:
   ```
   antimicrobial_resistance | `"antimicrobial resistance"[tiab] OR "antibiotic resistance"[tiab] OR "drug resistance"[tiab] OR "multidrug resistant"[tiab] OR MDR[tiab] OR "carbapenem resistant"[tiab] OR CRE[tiab] OR ESBL[tiab] OR "vancomycin resistant"[tiab] OR VRE[tiab] OR MRSA[tiab]`
   ```
2. **`scripts/build_daily_md.py`** — update `SECTION_HEADERS` and `SECTION_ORDER`:
   ```python
   SECTION_HEADERS = {
       "transplant_id":           "## Transplant & Opportunistic Infections",
       "one_health":              "## One Health / Zoonoses",
       "antimicrobial_resistance":"## Antimicrobial Resistance",
   }
   SECTION_ORDER = ["transplant_id", "one_health", "antimicrobial_resistance"]
   ```
3. **`scripts/daily_feed_filter.py`** — update the `CAPS` dict and the cross-section dedup loop to use the new section name (search for `food_security` and replace).

### Dropping a section entirely

Same idea but remove the row from Step 1, remove the entry from `SECTION_HEADERS` / `SECTION_ORDER` / `CAPS`, and remove the section from the cross-section dedup priority list in `scripts/daily_feed_filter.py`.

### Adding a brand-new section

Add a new row to the Step 1 table, add a new entry to all three dicts/lists in the scripts. The filter and renderer scale to any number of sections.

### Always include certain pathogens (rescue pattern)

The filter caps each section at a fixed number of articles (`CAPS` in `scripts/daily_feed_filter.py`). If you're following a specific pathogen and want articles about it to **always** make it into the digest — even when they fall past the per-section cap — add a small rescue block.

Two patches to `scripts/daily_feed_filter.py`:

1. Near the other regex constants (around `_NOISE_RE`), declare what to rescue and where:
   ```python
   _MUST_INCLUDE_RE = re.compile(r"\b(your_pathogen|another_term)\b", re.IGNORECASE)
   _MUST_INCLUDE_SECTIONS = {"one_health", "food_security"}   # which sections to scan
   _MUST_INCLUDE_RESCUE_CAP = 5                               # max rescued per section
   ```
2. Inside the per-section loop in `main()`, right after the line `capped = filtered[:cap]`, splice rescued matches back in:
   ```python
   capped_pmids = {a["pmid"] for a in capped}
   rescued = [a for a in filtered[cap:]
              if section in _MUST_INCLUDE_SECTIONS
              and _MUST_INCLUDE_RE.search(f"{a['title']} {a['abstract']}")
              and a["pmid"] not in capped_pmids]
   sections_out[section] = capped + rescued[:_MUST_INCLUDE_RESCUE_CAP]
   ```

The rescue matches against title + abstract, runs after the IF sort + cap, and is bounded so a noisy week can't blow up your digest. To follow a different organism — `MRSA`, `Candida auris`, anything — swap the regex.

### Testing a query before committing it

Try the query on PubMed's web UI first to make sure it returns roughly what you expect:

```
("BK virus"[tiab] OR BKV[tiab]) AND 2026/05/04:2026/05/10[edat]
```

If the web search looks right, the MCP call (with `date_from` / `date_to` passed as parameters rather than inline `[edat]`) will return the same set.

## Adapting the output style

Both the TL;DR and the Hot Take are pure prompting choices in `SKILL.md` Step 2 and Step 3. To adapt:

- **Language**: replace "English" in Steps 2 and 3 with your preferred language (e.g. Traditional Chinese, Spanish, Japanese, French). PubMed and CrossRef return abstracts in their original language — usually English — and Claude translates on the fly. No other part of the skill needs changing.
- **Tone label**: rename "Hot Take" to whatever fits — "key takeaway", "clinical implication", "bottom line", etc.
- **Length / depth**: the default TL;DR is 1–2 sentences. Loosen it to a short paragraph for more depth, or tighten it to one sentence for skim-friendliness. Same for the Hot Take.

## Timezone

The skill anchors `DATE` to the system clock + your configured `TIMEZONE` (default `UTC`). Set this in `SKILL.md`'s Configuration block to your IANA zone, e.g.:

- `Asia/Taipei` — UTC+8, runs first thing in the morning in Taiwan
- `America/New_York` — DST-aware US east coast
- `Europe/Berlin` — DST-aware Central Europe
- `Australia/Sydney` — DST-aware AEST/AEDT

Why this matters: PubMed's `edat` (Entrez-added date) is in US Eastern time. If you run early in *your* morning and the PubMed indexing for that calendar day isn't done yet, Step 1 will return zero articles — and the skill falls back to `DATE − 1` automatically.

## Building `sjr_curated.json`

`sjr_curated.json` is a small lookup from journal abbreviation / title to SJR (Scimago Journal Rank) score. The filter script uses it to rank articles within each section and to cap how many make it into the digest.

The repo ships `sjr_curated.example.json` purely as a **schema reference** — its journal list reflects the original author's specialty interests and is unlikely to match yours.

### Schema

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

- `abbr` — NLM Title Abbreviation. Look up at https://www.ncbi.nlm.nih.gov/nlmcatalog/journals.
- `title` — full journal name. Used as a fallback lookup if `abbr` doesn't match.
- `if` — impact factor (or any numeric ranking value). The filter reads this as the score for sorting and capping.
- `sjr`, `cluster` — metadata for your own reference; not used by the script.

### Bootstrap (first time)

Easiest: just ask Claude. Trigger phrases the skill recognises: `"build sjr_curated"`, `"update SJR scores"`, `"refresh journal rankings"`.

For a new install, Claude will:

1. Ask which medical specialties / topics you care about (e.g. Infectious Diseases, Hematology, Cardiology, Oncology, Public Health).
2. Compile a list of ~10–30 top journals per specialty — using SJR rankings from https://www.scimagojr.com/ for objectivity.
3. Write the JSON in the schema above.

Alternatively, copy `sjr_curated.example.json` to `sjr_curated.json` and trim / replace entries by hand.

### Yearly refresh

SCImago publishes new rankings each year (around June), so scores drift. Once a year, ask Claude to `"update SJR scores"`. It reads your existing journal list (without adding journals), looks up the latest SCImago scores, updates the file in place, and reports any journals it couldn't match.

Skipping a refresh isn't fatal — the filter keeps working with stale or zero scores.

## License

MIT — see [`LICENSE`](./LICENSE).
