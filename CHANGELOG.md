# Changelog

All notable changes to this skill are documented here. Format loosely follows [Keep a Changelog](https://keepachangelog.com/) and the project uses [Semantic Versioning](https://semver.org/).

## [v1.0.0] — 2026-06-05

First stable release. No breaking changes from v0.2.0 — the version reflects the skill being declared stable, alongside the title-rendering fix below.


### Fixed

- **Pathogen names eaten from titles** — `scripts/daily_feed_filter.py:normalize_mcp_record` now decodes HTML entities *and* peels inline markup while keeping the wrapped text, via `html.unescape()` plus an `HTMLParser`-based text extractor (`_htmlish_to_text`). PubMed MCP titles that arrived with escaped inline tags (`&lt;i&gt;Cryptococcus neoformans&lt;/i&gt;`) or real inline tags (`<i>Salmonella</i>`) previously lost the genus/species name, leaving artefacts like `caused byG8 … ( )` and `Spermine suppresses-induced …`. These now render correctly. ([daily_feed_filter.py](./scripts/daily_feed_filter.py))

### Changed

- **Known limitations corrected** — v0.2.0 documented italic-tag content loss as unfixable from the skill side. Investigation showed the common cause was recoverable (escaped/real inline tags being stripped together with their text), and v1.0.0 fixes it. The README **Known limitations** section now scopes the residual, genuinely-unrecoverable case to titles where the MCP server drops the tag content *upstream* before the record reaches the skill.

### Notes

- No schema or interface changes; existing `output/`, `sjr_curated.json`, and `.seen_pmids.json` files continue to work unchanged.
- Skill triggers unchanged (`run daily digest`, `daily lit`, `跑每日文獻`, etc.).

[v1.0.0]: https://github.com/didiowen/pubmed-daily-digest/releases/tag/v1.0.0

## [v0.2.0] — 2026-05-31

### Fixed

- **PubMed MCP HTML entity decoding** — `scripts/daily_feed_filter.py:normalize_mcp_record` now wraps the incoming title with `html.unescape()`, so titles like `T&#xfc;rkiye` render as `Türkiye` instead of leaking the raw entity into the digest. ([daily_feed_filter.py](./scripts/daily_feed_filter.py))

### Documented

- **Known limitation: MCP `<i>…</i>` content loss** — the upstream PubMed MCP server sometimes strips italic-tag content along with the tags (e.g. `<i>Cryptococcus neoformans</i>` disappears entirely, leaving titles like `invasion of the orbital compartment …`). The cloud sandbox cannot refetch via E-utilities, so this can't be fully fixed from the skill side. README and the inline comment in `normalize_mcp_record` now point at the failure mode so users know when to skim and patch by hand. See the **Known limitations** section in [README.md](./README.md#known-limitations) / [README.zh-TW.md](./README.zh-TW.md#已知限制).

### Notes

- No schema or interface changes; existing `output/`, `sjr_curated.json`, and `.seen_pmids.json` files continue to work unchanged.
- Skill triggers unchanged (`run daily digest`, `daily lit`, `跑每日文獻`, etc.).

[v0.2.0]: https://github.com/didiowen/pubmed-daily-digest/releases/tag/v0.2.0
