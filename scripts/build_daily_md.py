#!/usr/bin/env python3
"""Build the daily Markdown digest from the annotated JSON.

Reads `{OUTPUT_DIR}/{DATE}_daily.json` (with `tldr` / `comment` filled in by
the `pubmed-daily-digest` skill) and writes `{DATE}.md` next to the input.

Usage:
    python scripts/build_daily_md.py path/to/2026-05-07_daily.json

The output Markdown is written to the same directory as the input JSON.
Edit `SECTION_HEADERS` / `SECTION_ORDER` below if you change which sections
the skill produces (see README → Customising the queries).
"""
import json
import re
import sys
import urllib.parse
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

SECTION_HEADERS = {
    "transplant_id": "## Transplant & Opportunistic Infections",
    "one_health":    "## One Health / Zoonoses",
}
SECTION_ORDER = ["transplant_id", "one_health"]


def fmt_authors(authors):
    if not authors:
        return ""
    if len(authors) == 1:
        return authors[0]
    return f"{authors[0]} et al."


def fmt_doi_line(doi, pmid):
    if doi:
        return f"**DOI**: [{doi}](https://doi.org/{doi})"
    if pmid:
        return f"**PMID**: {pmid}"
    return None


def coins_span(a):
    """Hidden COinS span so the desktop Zotero Connector can one-click save the
    article straight from the digest page (no DOI copy-paste). Renders nothing."""
    title = a.get("title") or ""
    if not title:
        return None
    journal = a.get("journal_full") or a.get("journal_abbr") or ""
    year = ""
    m = re.search(r"\b(19|20)\d{2}\b", a.get("pubdate") or "")
    if m:
        year = m.group(0)
    pairs = [
        ("url_ver", "Z39.88-2004"),
        ("ctx_ver", "Z39.88-2004"),
        ("rfr_id", "info:sid/zotero.org:2"),
        ("rft_val_fmt", "info:ofi/fmt:kev:mtx:journal"),
        ("rft.genre", "article"),
        ("rft.atitle", title),
    ]
    if journal:
        pairs.append(("rft.jtitle", journal))
    if year:
        pairs.append(("rft.date", year))
    if a.get("doi"):
        pairs.append(("rft_id", f"info:doi/{a['doi']}"))
    if a.get("pmid"):
        pairs.append(("rft_id", f"info:pmid/{a['pmid']}"))
    for au in (a.get("authors") or []):
        # PubMed gives "Lastname Initials" (e.g. "Busca A"); emit "Lastname, Initials"
        # so Zotero's COinS parser reads surname/given correctly (comma = Last, First).
        last, sep, first = au.rpartition(" ")
        pairs.append(("rft.au", f"{last}, {first}" if sep else au))
    kev = "&".join(f"{k}={urllib.parse.quote(v, safe='')}" for k, v in pairs)
    # Escape & for the HTML attribute; the browser decodes it back before Zotero reads it.
    return f'<span class="Z3988" title="{kev.replace("&", "&amp;")}"></span>'


def fmt_article(a):
    lines = [f"### {a['title']}"]
    authors_str = fmt_authors(a.get("authors") or [])
    journal = a.get("journal_abbr", "")
    pubdate = a.get("pubdate", "")
    lines.append(f"**Authors**: {authors_str} | **Journal**: *{journal}* | **Date**: {pubdate}")
    doi_line = fmt_doi_line(a.get("doi", ""), a.get("pmid", ""))
    if doi_line:
        lines.append(doi_line)
    coins = coins_span(a)
    if coins:
        lines.append(coins)
    tldr = a.get("tldr", "")
    comment = a.get("comment", "")
    if tldr:
        lines.append(f"**TL;DR**: {tldr}")
    if comment:
        lines.append(f"**Hot Take**: {comment}")
    return "\n".join(lines)


def fmt_section(key, articles):
    out = [SECTION_HEADERS[key], ""]
    if not articles:
        out.append("> No matching articles today.")
    else:
        chunks = [fmt_article(a) for a in articles]
        out.append("\n\n---\n\n".join(chunks))
    return "\n".join(out)


def fmt_highlights(highlights: list) -> str:
    if not highlights:
        return ""
    lines = ["## Notable Highlights", ""]
    for h in highlights:
        pmid = h.get("pmid", "")
        title = h.get("title", "")
        reason = h.get("reason", "")
        if pmid:
            title_link = f"[{title}](https://pubmed.ncbi.nlm.nih.gov/{pmid}/)"
        else:
            title_link = title
        lines.append(f"- **{title_link}**  \n  {reason}")
    return "\n".join(lines)


APPRAISAL_LABELS = [
    ("設計", "design"), ("樣本", "sample"), ("關鍵數字", "findings"),
    ("Limitation", "limitations"), ("Bottom line", "bottom_line"),
]
# editorial / review carry arguments, not trial numbers — relabel findings so the
# template does not imply fabricated statistics (study_type comes from picks_codex).
APPRAISAL_LABELS_COMMENTARY = [
    ("設計", "design"), ("樣本", "sample"), ("關鍵論點", "findings"),
    ("Limitation", "limitations"), ("Bottom line", "bottom_line"),
]


def fmt_appraisals(appraisals: list, index: dict) -> str:
    """Render the deep-appraisal section (codex-picked highlights). `index` maps
    pmid -> article record so we can pull title / journal / IF / DOI."""
    if not appraisals:
        return ""
    chunks = []
    for ap in appraisals:
        a = index.get(str(ap.get("pmid", "")))
        if not a:
            continue
        title = a.get("title", "")
        title_md = a.get("title_md", "")
        heading = title_md if title_md and title_md.replace("*", "") == title else title
        block = [f"### {heading}"]
        meta_bits = []
        if a.get("journal_abbr"):
            meta_bits.append(f"*{a['journal_abbr']}*")
        if a.get("if_score"):
            meta_bits.append(f"IF {a['if_score']}")
        if a.get("doi"):
            meta_bits.append(f"[DOI](https://doi.org/{a['doi']})")
        if a.get("pmid"):
            meta_bits.append(f"PMID {a['pmid']}")
        if meta_bits:
            block.append(" | ".join(meta_bits))
            block.append("")  # blank line — without it, Python-Markdown (nl2br on
            # the public site) swallows the following list into this paragraph as
            # literal "- " text with only <br> tags instead of real <ul><li> items.
        d = ap.get("appraisal", {})
        labels = (APPRAISAL_LABELS_COMMENTARY
                  if ap.get("study_type") in ("editorial", "review")
                  else APPRAISAL_LABELS)
        for label, key in labels:
            if d.get(key):
                block.append(f"- **{label}**：{d[key]}")
        grade = ap.get("evidence_grade")
        if grade and grade.get("label"):
            block.append(f"- **GRADE 證據等級**：{grade['label']}")
        arg_check = ap.get("argument_check")
        if arg_check and not arg_check.get("clean") and arg_check.get("flags"):
            block.append(f"- **推論檢查**：{'；'.join(arg_check['flags'])}")
        chunks.append("\n".join(block))
    if not chunks:
        return ""
    return "\n".join(["## 🔬 深入評讀", "", "\n\n".join(chunks)])


def build(json_path: Path) -> Path:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    date_str = data["meta"]["date"]
    highlights = data["meta"].get("highlights") or []
    appraisals = data["meta"].get("appraisals") or []
    sections = data["sections"]
    article_index = {
        str(a["pmid"]): a
        for key in SECTION_ORDER
        for a in sections.get(key, [])
        if a.get("pmid")
    }
    counts = {k: len(sections.get(k, [])) for k in SECTION_ORDER}
    total = sum(counts.values())

    summary_parts = [f"{SECTION_HEADERS[k].lstrip('# ').strip()} × {counts[k]}" for k in SECTION_ORDER]
    summary = ", ".join(summary_parts)

    parts = [
        "---\n"
        "tags: [medical-literature, journal-digest]\n"
        f"date: {date_str}\n"
        "categories: [medicine, journal-digest]\n"
        "---",
        "",
        f"# Daily Journal Digest — {date_str}",
        "",
        f"> Past 24 hours: {summary}; {total} articles total.",
        "",
    ]
    if highlights:
        parts.append(fmt_highlights(highlights))
        parts.append("")
        parts.append("---")
        parts.append("")
    if appraisals:
        parts.append(fmt_appraisals(appraisals, article_index))
        parts.append("")
        parts.append("---")
        parts.append("")
    for key in SECTION_ORDER:
        parts.append(fmt_section(key, sections.get(key, [])))
        parts.append("")
        parts.append("---")
        parts.append("")
    parts.append(f"*Source: PubMed (articles retrieved {date_str})*")
    parts.append("")
    pmid_list = ",".join(
        a["pmid"]
        for key in SECTION_ORDER
        for a in sections.get(key, [])
        if a.get("pmid")
    )
    if pmid_list:
        parts.append(f"<!-- pmids: {pmid_list} -->")
        parts.append("")

    md_path = json_path.parent / f"{date_str}.md"
    md_path.write_text("\n".join(parts), encoding="utf-8")
    print(f"Wrote {total} articles → {md_path}")
    return md_path


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(2)
    build(Path(sys.argv[1]))


if __name__ == "__main__":
    main()
