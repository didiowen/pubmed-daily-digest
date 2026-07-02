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


def build(json_path: Path) -> Path:
    data = json.loads(json_path.read_text(encoding="utf-8"))
    date_str = data["meta"]["date"]
    highlights = data["meta"].get("highlights") or []
    sections = data["sections"]
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
