# Pubmed Daily Digest

> [English version](./README.md)

一個 Claude Code skill，每天抓取 PubMed 過去 24 小時新增的文章，依照你預先設定的幾組主題查詢分類，為每篇文章寫一段 TL;DR 與一句話的 **Hot Take**（捧或酸都可以），再挑出 3–5 篇當天的重點，最後渲染成一份 Markdown 摘要寫到本機資料夾。輸出預設是英文，想換語言只要改一處 prompt 就好。

[![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-Skill%20Based-blueviolet?logo=anthropic)](https://claude.ai/claude-code)
[![Made in Taiwan](https://img.shields.io/badge/Made%20in-Taiwan%20%F0%9F%87%B9%F0%9F%87%BC-red)](https://github.com/htlin222/society-calendar)

## 資料夾結構

```
pubmed-daily-digest/
├── SKILL.md                       # skill 本體
├── README.md                      # 英文版
├── README.zh-TW.md                # 本檔案
├── LICENSE
├── sjr_curated.example.json       # schema 參考；請複製為 sjr_curated.json 再編輯
├── output/                        # 預設輸出位置（以 .gitkeep 保留）
└── scripts/
    ├── daily_feed_filter.py       # 過濾、去重、排序、限量，產出 {DATE}_daily.json
    └── build_daily_md.py          # 把標註後的 JSON 渲染成 {DATE}.md
```

`sjr_curated.json` 需要你自己建一份（從期刊縮寫或全名對應到 SJR 分數的小型查詢表），詳見下方的[建立 `sjr_curated.json`](#建立-sjr_curatedjson)。腳本會以自己的相對路徑找這個檔案以及 `.seen_pmids.json` 滾動快取，所以只要資料夾結構完整，從哪個工作目錄執行都可以。

## 相依套件

- **Claude Code**（含 Skill 系統）—— https://claude.com/claude-code
- 在 Claude Code MCP 設定中啟用的 **PubMed MCP server**
- 兩個內建腳本需要 **Python ≥ 3.9**（只用標準函式庫，不必 `pip install`）
- 預設流程不需要 `.env` 或 API 金鑰

## 安裝設定

1. 把整個資料夾放到任一專案的 skills 目錄底下：`<project>/.claude/skills/pubmed-daily-digest/`。
2. 確認 PubMed MCP server 已經設好。
3. 打開 `SKILL.md`，編輯檔案頂端的 **Configuration** 區塊：
   - `OUTPUT_DIR`：預設是內建的 `output/`，想寫到別處就改這裡。
   - `TIMEZONE`：預設 `UTC`，建議改成你的 IANA 時區，例如 `Asia/Taipei`、`America/New_York`、`Europe/Berlin`。
   - `CROSSREF_MAILTO`：任一個可用的電子郵件，給 CrossRef polite-pool 識別用。
4. （選用）改寫 Step 1 的四組 PubMed 查詢，貼近你自己的研究興趣，詳見下方的[自訂查詢](#自訂查詢)。
5. **準備自己的 `sjr_curated.json`**：filter 會用它在每個 section 內依期刊重要性排序文章。你可以複製 `sjr_curated.example.json` 後刪減，或請 Claude 依你的專長生成一份（詳見[建立 `sjr_curated.json`](#建立-sjr_curatedjson)）。沒有這個檔 filter 仍能跑，只是每篇文章的 `if_score` 都會是 0。
6. 從 Claude Code 觸發：直接跟它說「跑每日摘要」（run the daily digest），或以 skill 名稱呼叫。

## 自訂查詢

這通常是你最想動的部分。預設查詢反映原作者的興趣（器官移植感染症、One Health、糧食安全），你的興趣大概長得不一樣。

### 查詢放在哪裡

`SKILL.md` → **Step 1 — PubMed search + Python filter** 有一張表格，內含三個 section、共四組查詢：

- `transplant_id`（兩組平行子查詢，事後以 PMID 取聯集）
- `one_health`
- `food_security`

每一列會展開成一次平行的 `mcp__PubMed__search_articles` 呼叫。你可以改寫現有查詢、整段換掉某個 section，或再新增 section。

### PubMed 查詢語法速覽

PubMed 用 field qualifier 來限定詞彙範圍，預設查詢用到的有：

| Field       | 意義                                          |
|-------------|-----------------------------------------------|
| `[tiab]`    | 標題加摘要（最常用的主題查詢欄位）            |
| `[Title]`   | 僅標題（較嚴格）                              |
| `[Mesh]`    | MeSH 受控詞彙                                 |
| `[Journal]` | 期刊名稱（NLM 縮寫）                          |
| `[edat]`    | Entrez-added date（skill 在 Step 1 會自動填） |

可用 `AND`、`OR`、`NOT` 加括號自由組合。

### PubMed MCP 的兩個坑

都是踩過的：

- **不支援萬用字元**。`mycobacteri*` 會直接回 `INVALID_PARAMETERS`，請改用 `OR` 列舉：`mycobacterium OR tuberculosis OR NTM`。
- **單條查詢最多 20 個布林運算子**。一條查詢若用了超過 20 個 `AND`／`OR` 會失敗。遇到時拆成兩組平行子查詢即可，預設的 `transplant_id` 就是這樣處理的，Python filter 會把同一 section 的子查詢以 PMID 聯集起來。

### 範例：替換一個 section

假設你不在意糧食安全，但想追蹤 **antimicrobial resistance**。需要改三個地方，全部都在這個 repo 內：

1. **`SKILL.md`**：把 Step 1 表格裡 `food_security` 那列換成：
   ```
   antimicrobial_resistance | `"antimicrobial resistance"[tiab] OR "antibiotic resistance"[tiab] OR "drug resistance"[tiab] OR "multidrug resistant"[tiab] OR MDR[tiab] OR "carbapenem resistant"[tiab] OR CRE[tiab] OR ESBL[tiab] OR "vancomycin resistant"[tiab] OR VRE[tiab] OR MRSA[tiab]`
   ```
2. **`scripts/build_daily_md.py`**：更新 `SECTION_HEADERS` 與 `SECTION_ORDER`：
   ```python
   SECTION_HEADERS = {
       "transplant_id":           "## Transplant & Opportunistic Infections",
       "one_health":              "## One Health / Zoonoses",
       "antimicrobial_resistance":"## Antimicrobial Resistance",
   }
   SECTION_ORDER = ["transplant_id", "one_health", "antimicrobial_resistance"]
   ```
3. **`scripts/daily_feed_filter.py`**：更新 `CAPS` 字典與跨 section 去重迴圈，把舊的 section 名稱換掉就好（直接搜 `food_security` 全部替換即可）。

### 整段拿掉一個 section

作法一樣：從 Step 1 移除該列，從 `SECTION_HEADERS`、`SECTION_ORDER`、`CAPS` 移除對應 entry，再從 `scripts/daily_feed_filter.py` 的跨 section 去重優先順序清單中移除即可。

### 新增一個全新的 section

在 Step 1 表格新增一列，再到腳本裡的三個 dict／list 各加上對應 entry。Filter 與 renderer 可以容納任意數量的 section。

### 一定要納入特定病原（rescue pattern）

Filter 會限制每個 section 的文章數（`scripts/daily_feed_filter.py` 內的 `CAPS`）。如果你正在追某個特定病原，希望相關文章 **每天都進到摘要裡**，即使排不進每 section 上限也沒關係，可以加一段 rescue 區塊。

需要對 `scripts/daily_feed_filter.py` 改兩處：

1. 在其他 regex 常數附近（`_NOISE_RE` 旁邊）宣告要 rescue 什麼、要看哪些 section：
   ```python
   _MUST_INCLUDE_RE = re.compile(r"\b(your_pathogen|another_term)\b", re.IGNORECASE)
   _MUST_INCLUDE_SECTIONS = {"one_health", "food_security"}   # 要掃哪些 section
   _MUST_INCLUDE_RESCUE_CAP = 5                               # 每個 section 最多 rescue 幾篇
   ```
2. 在 `main()` 的每個 section 迴圈裡、`capped = filtered[:cap]` 那一行後面，把 rescue 的結果接回去：
   ```python
   capped_pmids = {a["pmid"] for a in capped}
   rescued = [a for a in filtered[cap:]
              if section in _MUST_INCLUDE_SECTIONS
              and _MUST_INCLUDE_RE.search(f"{a['title']} {a['abstract']}")
              and a["pmid"] not in capped_pmids]
   sections_out[section] = capped + rescued[:_MUST_INCLUDE_RESCUE_CAP]
   ```

Rescue 用 title 加 abstract 比對，在 IF 排序與上限套用之後才執行，並且有自己的上限，所以文章爆量的那週也不會把摘要撐爆。要追別的病原（`MRSA`、`Candida auris`，什麼都行）只要換 regex 就好。

### Commit 前先試查詢

寫進 `SKILL.md` 之前，建議先在 PubMed 網頁版跑一次，確認結果大致符合預期：

```
("BK virus"[tiab] OR BKV[tiab]) AND 2026/05/04:2026/05/10[edat]
```

網頁查得對，等價的 MCP 呼叫（把 `date_from` 與 `date_to` 以參數帶入，不要 inline 寫 `[edat]`）就會回傳同一組結果。

## 調整輸出風格

TL;DR 與 Hot Take 完全是 `SKILL.md` Step 2、Step 3 的 prompt 設定，想改就改：

- **語言**：把 Step 2 與 Step 3 中的 "English" 換成你想要的語言（例如繁體中文、Spanish、Japanese、French）。PubMed 與 CrossRef 回傳的摘要是原始語言（通常是英文），Claude 會在標註時即時翻譯，skill 其餘部分都不用動。
- **語氣標籤**：把 "Hot Take" 換成任何你喜歡的詞，例如 "key takeaway"、"clinical implication"、"bottom line"，或中文的「臨床意義」、「重點」。
- **長度與深度**：TL;DR 預設 1–2 句，想看得更深就放寬成一段、要更速覽就縮成一句，Hot Take 同理。

## 時區

Skill 會用系統時鐘加上你設定的 `TIMEZONE`（預設 `UTC`）來決定 `DATE`。請在 `SKILL.md` 的 Configuration 區塊改成你的 IANA 時區，例如：

- `Asia/Taipei`：UTC+8，台灣一早起來剛好可以跑
- `America/New_York`：含 DST 的美東
- `Europe/Berlin`：含 DST 的中歐
- `Australia/Sydney`：含 DST 的 AEST／AEDT

為什麼這件事很重要：PubMed 的 `edat`（Entrez-added date）走美東時間。如果你在 **自己這邊** 太早跑，PubMed 當天的索引可能還沒入庫，Step 1 會回零篇，這時 skill 會自動 fallback 到 `DATE − 1`。

## 建立 `sjr_curated.json`

`sjr_curated.json` 是一份從期刊縮寫或全名對應到 SJR（Scimago Journal Rank）分數的小型查詢表，filter 腳本會拿來在每個 section 內排序文章、決定哪幾篇能進到摘要。

Repo 內的 `sjr_curated.example.json` 純粹是 **schema 範例**，裡面的期刊清單反映原作者的專長，你直接拿來用大概不會剛好符合需求。

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

- `abbr`：NLM Title Abbreviation。可在 https://www.ncbi.nlm.nih.gov/nlmcatalog/journals 查到。
- `title`：期刊全名，作為 `abbr` 比不到時的 fallback。
- `if`：impact factor（或任何你想用來排序的數值）。Filter 以這個欄位作為排序與上限依據。
- `sjr`、`cluster`：你自己留著參考的中繼資料，腳本不會用到。

### 第一次建立（bootstrap）

最省事的做法是直接請 Claude 幫忙。Skill 認得的觸發詞包括 `"build sjr_curated"`、`"update SJR scores"`、`"refresh journal rankings"`。

第一次建立時，Claude 會：

1. 問你關心哪些醫學專科或主題（例如 Infectious Diseases、Hematology、Cardiology、Oncology、Public Health）。
2. 為每個專科整理約 10–30 本頂尖期刊，並以 https://www.scimagojr.com/ 的 SJR 排名作為客觀依據。
3. 依上述 schema 寫出 JSON。

也可以直接複製 `sjr_curated.example.json` 為 `sjr_curated.json`，手動精簡或替換條目。

### 每年更新一次

SCImago 每年（大約六月）會發布新的排名，分數會慢慢漂移。建議每年請 Claude `"update SJR scores"` 一次，它會讀你現有的期刊清單（不會自己加新期刊）、查最新的 SCImago 分數、原地更新檔案，並回報任何對不上的期刊。

跳過更新也不致命，filter 即使遇到過期或為零的分數仍會繼續運作。

## 已知限制

PubMed MCP server 偶爾會在屬名／種名周圍回傳帶有標記或 entity 問題的標題 — 跳脫的內聯標籤（`&lt;i&gt;Cryptococcus neoformans&lt;/i&gt;`）、真正的內聯標籤（`<i>Salmonella</i>`）、或未解碼的 HTML entity（`T&#xfc;rkiye` 應為 `Türkiye`）。若不處理，這些會在 digest 裡留下原始標籤，或在粗暴去除標籤後把病原名一起吃掉，留下顯眼的拼接痕跡（`Spermine suppresses-induced macrophage…`、`caused byG8 …（ ）`）。

v1.0.0 起，filter 會解碼 entity 並剝除內聯標記、保留被包住的文字（`normalize_mcp_record` 中的 `html.unescape()` ＋ `HTMLParser` 文字擷取器），因此上述情況都能正確呈現。唯一無法修補的殘留情況，是 MCP server 在記錄送達 skill 之前就「已經」把標籤內文丟掉了 — 文字根本不存在、無從還原，而雲端 sandbox 又擋住 PubMed E-utilities 重抓。這個殘留必須在 MCP server 本身修；受影響的標題仍會留下一眼可辨的痕跡（斜體不見、空括號），對準確度要求高時請翻一下當日輸出。詳見 [`scripts/daily_feed_filter.py:normalize_mcp_record`](./scripts/daily_feed_filter.py) 內聯註解。

## License

MIT，詳見 [`LICENSE`](./LICENSE)。
