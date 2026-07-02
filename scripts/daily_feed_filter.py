#!/usr/bin/env python3
"""Daily PubMed digest filter.

Reads `{OUTPUT_DIR}/{DATE}_raw.json` (produced by the `pubmed-daily-digest`
skill via the PubMed MCP server) and writes `{OUTPUT_DIR}/{DATE}_daily.json`
ready for annotation in the skill's Step 2 / Step 3. No network calls.

Usage:
    python scripts/daily_feed_filter.py YYYY-MM-DD

Input (raw.json) schema:
    {
      "meta": {"date": "YYYY-MM-DD", "reldate": 0 or 1},
      "raw_sections": {
        "transplant_id": [<mcp__PubMed__get_article_metadata records>, ...],
        "one_health":    [...]
      }
    }

Output (daily.json) schema — drop-in input for build_daily_md.py:
    {
      "meta": {"date": "YYYY-MM-DD", "reldate": 0 or 1},
      "sections": {
        "transplant_id": [<normalized + filtered + sorted articles>],
        "one_health":    [...]
      }
    }

Paths are resolved relative to the skill folder (the parent of this scripts/
directory), so the script works regardless of cwd as long as the layout is
intact: pubmed-daily-digest/{sjr_curated.json, output/, scripts/}.
"""

import html
import json
import re
import sys
from datetime import date, timedelta
from html.parser import HTMLParser
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# ── Self-locate skill data + outputs ──────────────────────────────────────────
SKILL_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = SKILL_ROOT / "output"
SJR_FILE   = SKILL_ROOT / "sjr_curated.json"
SEEN_FILE  = SKILL_ROOT / ".seen_pmids.json"

SEEN_TTL_DAYS = 7

# Per-section caps after IF sort. Edit if you change the section list.
CAPS = {"transplant_id": 30, "one_health": 10}

# ── Pubtype / language filter ─────────────────────────────────────────────────
# `language == "eng"` AND article_types intersects KEEP AND does not intersect DROP.
KEEP_TYPES = {
    "Journal Article", "Review", "Systematic Review",
    "Meta-Analysis", "Guideline", "Practice Guideline",
}
DROP_TYPES = {
    "Editorial", "Letter", "Comment", "News", "Case Reports",
    "Erratum", "Published Erratum",
    "Biography", "Historical Article", "Portrait",
    "Interview", "Personal Narrative",
}

# ── Basic-science title regex ────────────────────────────────────────────────
# Drops bench / chemistry papers that don't carry clinical takeaways. Edit
# freely; the patterns below are a starting point — add or remove to match
# your interests.
_BASIC_SCI_RE = re.compile("|".join([
    r"\bbiosynthe(sis|tic)\b",
    r"\b(polyketide|sesquiterpen|terpenoid|meroterpen|saponin|alkaloid)\w*\b",
    r"\bsynthase[s]?\b",
    r"\b(chemoenzymatic|biocatalytic)\b",
    r"\bmetabolic engineering\b",
    r"\bgenome[- ]guided\b",
    r"\bCRISPR\b",
    r"\bgene editing\b",
    r"\b(hairy root|rhizosphere|endophytic)\b",
    r"\b(secondary metabolite|natural product)\w*\b",
    r"\bin silico\b",
    r"\bmolecular docking\b",
    r"\bstructural stud(y|ies)\b",
    r"\bAlphaFold\b",
    r"\bmicrofluidic\b",
    r"\b(immobiliz(ed|ation)|hydrogel)\b",
    r"\bbioconversion\b",
    r"\bsolid[- ]state fermentation\b",
    r"\b(chemical composition|essential oils)\b",
    r"\bdrug delivery system\w*\b",
    r"\bformulation technolog\w*\b",
]), re.IGNORECASE)

_NOISE_RE = re.compile(
    r"^(erratum|corrigendum|correction|reply\b|in reply\b|response to\b)",
    re.IGNORECASE,
)

_PMID_COMMENT_RE = re.compile(r"<!-- pmids: ([\d,]+) -->")


def _load_prev_digest_pmids(date_str: str) -> set[str]:
    """Read PMIDs embedded in a previously built digest's HTML comment footer."""
    md_path = OUTPUT_DIR / f"{date_str}.md"
    if not md_path.exists():
        return set()
    m = _PMID_COMMENT_RE.search(md_path.read_text(encoding="utf-8"))
    if not m:
        return set()
    return set(m.group(1).split(","))


def _load_seen() -> dict:
    if not SEEN_FILE.exists():
        return {}
    try:
        return json.loads(SEEN_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _prune_seen(seen: dict) -> dict:
    cutoff = (date.today() - timedelta(days=SEEN_TTL_DAYS)).isoformat()
    return {pmid: d for pmid, d in seen.items() if d >= cutoff}


def _save_seen(seen: dict) -> None:
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(
        json.dumps(seen, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _build_if_lookup() -> dict:
    if not SJR_FILE.exists():
        print(f"  note: {SJR_FILE.name} not found — articles will sort with if_score=0; "
              f"copy sjr_curated.example.json to {SJR_FILE.name} and edit, or ask Claude "
              f"to build one ('update SJR scores')",
              file=sys.stderr)
        return {}
    sjr = json.loads(SJR_FILE.read_text(encoding="utf-8"))
    lookup = {}
    for j in sjr.get("journals", []):
        for k in (j.get("abbr"), j.get("title")):
            if k:
                lookup[k.lower()] = float(j.get("if") or 0)
    return lookup


def _if_for(rec: dict, lookup: dict) -> float:
    abbr = (rec.get("journal_abbr") or "").lower()
    full = (rec.get("journal_full") or "").lower()
    return lookup.get(abbr, lookup.get(full, 0.0))


class _TextExtractor(HTMLParser):
    """Collect the text nodes of an HTML fragment, discarding the tags."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _htmlish_to_text(value: str) -> str:
    """Decode entities and strip inline markup while keeping the wrapped text.

    PubMed titles sometimes arrive with escaped inline tags around genus/species
    names (e.g. "&lt;i&gt;Cryptococcus neoformans&lt;/i&gt;"). html.unescape()
    turns those back into real "<i>...</i>" tags; this then peels the tags off
    but keeps the text inside, so the pathogen name survives.
    """
    text = html.unescape(value or "")
    if "<" not in text or ">" not in text:
        return text

    parser = _TextExtractor()
    parser.feed(text)
    parser.close()
    return "".join(parser.parts)


def normalize_mcp_record(rec: dict) -> dict:
    """Translate `mcp__PubMed__get_article_metadata` shape to the schema used downstream."""
    ids = rec.get("identifiers", {}) or {}
    journal = rec.get("journal", {}) or {}
    pd = rec.get("publication_date", {}) or {}
    pubdate = " ".join(str(v) for v in (pd.get("year"), pd.get("month"), pd.get("day")) if v)

    authors = []
    for a in rec.get("authors", []) or []:
        last = a.get("last_name") or ""
        init = a.get("initials") or ""
        if last:
            authors.append(f"{last} {init}".strip())

    # PubMed MCP sometimes returns HTML entities undecoded (e.g. "T&#xfc;rkiye"
    # instead of "Türkiye") or escaped inline tags around genus/species names
    # (e.g. "&lt;i&gt;Cryptococcus neoformans&lt;/i&gt;"). _htmlish_to_text()
    # decodes the entities and peels off the markup while keeping the wrapped
    # text. If the MCP has already dropped the <i>...</i> content upstream, this
    # cannot recover it — that residual case must be fixed in the MCP server.
    title = _htmlish_to_text(rec.get("title") or "").rstrip(".").strip()

    return {
        "pmid": ids.get("pmid") or "",
        "title": title,
        "journal_full": journal.get("title") or "",
        "journal_abbr": journal.get("iso_abbreviation") or journal.get("title") or "",
        "authors": authors,
        "abstract": rec.get("abstract") or "",
        "abs_labeled": {},
        "pubdate": pubdate,
        "doi": ids.get("doi") or rec.get("doi") or "",
        "article_types": rec.get("article_types") or [],
        "language": (rec.get("language") or "").lower(),
        "if_score": 0.0,
        "section": "",
        "tldr": "",
        "comment": "",
    }


def passes_pubtype_filter(rec: dict) -> bool:
    if rec.get("language") not in {"eng", "english"}:
        return False
    types = set(rec.get("article_types") or [])
    if types & DROP_TYPES:
        return False
    if not (types & KEEP_TYPES):
        return False
    return True


def is_basic_science(rec: dict) -> bool:
    return bool(_BASIC_SCI_RE.search(rec.get("title") or ""))


def is_noise(rec: dict) -> bool:
    return bool(_NOISE_RE.match(rec.get("title") or ""))


def main(date_str: str) -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_path = OUTPUT_DIR / f"{date_str}_raw.json"
    out_path = OUTPUT_DIR / f"{date_str}_daily.json"
    if not raw_path.exists():
        raise SystemExit(f"raw file not found: {raw_path}")

    raw = json.loads(raw_path.read_text(encoding="utf-8"))
    reldate = raw.get("meta", {}).get("reldate", 0)

    if_lookup = _build_if_lookup()
    seen = _prune_seen(_load_seen())

    # Normalize MCP records per section.
    normalized: dict[str, list[dict]] = {}
    for section, recs in (raw.get("raw_sections") or {}).items():
        normalized[section] = [normalize_mcp_record(r) for r in recs or []]

    # If we fell back to the previous day's articles (reldate >= 1), explicitly
    # exclude PMIDs that were already published in that day's digest.
    if reldate >= 1:
        prev_date = (date.fromisoformat(date_str) - timedelta(days=reldate)).isoformat()
        prev_pmids = _load_prev_digest_pmids(prev_date)
        if prev_pmids:
            all_fetched_pmids = {
                a["pmid"] for arts in normalized.values() for a in arts if a["pmid"]
            }
            overlap = prev_pmids & all_fetched_pmids
            print(f"  Fallback mode (reldate={reldate}): {len(prev_pmids)} PMIDs in "
                  f"{prev_date} digest, {len(overlap)}/{len(all_fetched_pmids)} fetched "
                  f"overlap → excluded via seen cache")
            seen.update({p: prev_date for p in prev_pmids if p not in seen})
        else:
            print(f"  Fallback mode (reldate={reldate}): no machine-readable {prev_date} "
                  f"digest found, relying on seen cache only")

    # Cross-section dedup (priority follows insertion order of normalized).
    seen_pmids: set[str] = set()
    seen_dois: set[str] = set()
    seen_titles: set[str] = set()
    for sec in list(normalized.keys()):
        kept = []
        for a in normalized.get(sec, []):
            pmid = a["pmid"]
            doi = a["doi"]
            title = a["title"].lower()
            if (pmid and pmid in seen_pmids) \
               or (doi and doi in seen_dois) \
               or (title and title in seen_titles):
                continue
            kept.append(a)
            if pmid:  seen_pmids.add(pmid)
            if doi:   seen_dois.add(doi)
            if title: seen_titles.add(title)
        normalized[sec] = kept

    # Per-section: seen-cache drop, pubtype filter, basic-sci/noise drop, IF, sort, cap.
    sections_out: dict[str, list[dict]] = {k: [] for k in normalized.keys()}
    for section, arts in normalized.items():
        n_total = len(arts)
        arts = [a for a in arts if a["pmid"] and a["pmid"] not in seen]
        n_seen_dropped = n_total - len(arts)

        filtered = []
        for a in arts:
            if is_noise(a) or is_basic_science(a):
                continue
            if not passes_pubtype_filter(a):
                continue
            a["if_score"] = _if_for(a, if_lookup)
            a["section"] = section
            filtered.append(a)
        filtered.sort(key=lambda a: -a["if_score"])

        cap = CAPS.get(section, 20)
        capped = filtered[:cap]
        print(f"  {section}: {len(capped)} kept "
              f"({n_total} fetched, {n_seen_dropped} previously seen)")
        sections_out[section] = capped

    total = sum(len(v) for v in sections_out.values())

    payload = {
        "meta": {"date": date_str, "reldate": reldate},
        "sections": sections_out,
    }
    out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # Append today's kept PMIDs to the rolling seen cache.
    for sec_arts in sections_out.values():
        for a in sec_arts:
            if a["pmid"]:
                seen.setdefault(a["pmid"], date_str)
    _save_seen(seen)

    per_section = ", ".join(f"{k}: {len(v)}" for k, v in sections_out.items())
    print(f"Wrote {total} articles ({per_section}) → {out_path}")
    print(f"Seen cache now {len(seen)} PMIDs → {SEEN_FILE}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", sys.argv[1]):
        print(__doc__)
        sys.exit(2)
    main(sys.argv[1])
