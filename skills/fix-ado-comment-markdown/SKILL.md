---
name: fix-ado-comment-markdown
description: Azure DevOps work item 留言（Discussion）一律以 Markdown 發布，並把既有 HTML 留言修復成 Markdown；內附 Markdown 校正工具（markdown-fixer.mjs），可檢查、整理或自動校正 Markdown 常見語法錯誤（標題、清單、表格、全形標點、CJK 排版等）。Use when posting or repairing ADO work item comments (Task／Bug／PBI Discussion), when ADO comments render as one run-together paragraph, or when asked to fix, convert, or re-edit ADO comment format; also when asked to lint, clean, normalize, or fix Markdown. 觸發詞：ADO 留言、Discussion、work item comment、留言格式、修復留言、Markdown 留言、Markdown 校正、Markdown 整理、Markdown 檢查、修 Markdown、fix markdown、lint markdown、normalize markdown、math block。**必須由使用者明確調用才使用：Claude Code 以 `/fix-ado-comment-markdown`、Codex CLI 以 `$fix-ado-comment-markdown`；不要自動觸發。**
disable-model-invocation: true
---

# Fix ADO Comment Markdown

> **調用方式（明確調用）：** 本 skill 只在使用者明確調用時執行——Claude Code 用 `/fix-ado-comment-markdown`，Codex CLI 用 `$fix-ado-comment-markdown`；未被點名時不要自動套用。

本 skill 涵蓋兩件事：**ADO 留言的 Markdown 發布／修復**（A、B 流程），以及**通用 Markdown 校正工具**（C 節，內附）。

ADO 留言的儲存格式由**每則留言的 `format` 欄位**決定（`markdown` 或 `html`），不是由內容決定。`az boards work-item update --discussion` 與 JSON Patch `/fields/System.History` 只會存成 `html`；把多句話塞進一段時，在 ADO 上會黏成一大段。發布與修改留言一律走 Comments REST API 並指定 `format=markdown`，送出前用內附的 Markdown 校正工具校正語法。

工具都在本 skill 目錄下：`scripts/ado_comments.py`（只用 Python 標準函式庫，透過 `az rest` 呼叫）與 `scripts/markdown-fixer.mjs`（零依賴 Node）。以下 `<skill>` 指本 skill 目錄（例如 `~/.agents/skills/fix-ado-comment-markdown`），`$T` 指 `<skill>/scripts/ado_comments.py`，`$MF` 指 `<skill>/scripts/markdown-fixer.mjs`。先設定：

```bash
export ADO_ORG=https://dev.azure.com/<org> ADO_PROJECT=<project>
```

草稿與 manifest 放在暫存或 scratchpad 目錄，不放進專案工作樹。

## ADO Markdown 事實

- API：`POST .../_apis/wit/workItems/{id}/comments?format=markdown&api-version=7.1-preview.4` 新增；`PATCH .../comments/{commentId}?format=markdown&api-version=7.1-preview.4` 修改；body 都是 `{"text": "<markdown>"}`。`format` 是必填查詢參數。
- 既有 `html` 留言可直接 PATCH 成 `markdown`：`version` 加 1，畫面標示「已編輯」。
- 讀回時 `renderedText` 只在加 `$expand=renderedText` 時才回傳。
- `#12345` 會渲染成工作項目連結。**裸網址不會自動變成連結**：網址寫成 `[文字](URL)` 或 `<URL>`。
- 表格、`##`／`###` 標題、編號與項目清單、粗體、行內程式碼都會正常渲染；表格儲存格內不能有未轉義的 `|`。
- 同時要改狀態或指派時分兩步：先用 `az boards work-item update` 改欄位（不帶 `--discussion`），再發 Markdown 留言。
- 多行欄位（Description、Repro Steps 等）是另一個機制：JSON Patch 加 `/multilineFieldsFormat/<欄位>` = `Markdown`，存後不能改回 HTML。這個 skill 不處理欄位，除非使用者明確要求。

## A. 發布新留言

1. **寫草稿**：把內容寫成 `comment.md`。結構優先：一句話的標題、表格放對照資料（網址、版本、Task、Commit）、編號清單放步驟、項目清單放結果；SHA 與路徑加反引號；網址用 `[文字](URL)`。
   **完成條件：** 每個段落最多一個主題，沒有超過兩句的連續長段。
2. **校正**：`node $MF --check comment.md`，再 `node $MF --write --ignore-rule MDX018 comment.md`，重跑 `--check`。MDX070（裸網址）要改成連結；MDX018（第一個標題不是 H1）對留言可略過。
   **完成條件：** `--check` 只剩 MDX018，或 0 問題。
3. **發布**：`python3 -I $T post --id <workItemId> --file comment.md`。
   **完成條件：** 輸出的 `format` 為 `markdown`，`renderedLength` 大於 0。

## B. 修復既有 HTML 留言

1. **盤點**：`python3 -I $T pull --id <ID> [<ID> ...] --author <uniqueName> --out <dir>`。預設只取 `format=html`；`--format ''` 取全部。每則輸出 `<wi>-<cid>.orig.txt`（原文）、`<wi>-<cid>.md`（草稿）與 `manifest.json`（含 version 與 work item 狀態）。
   **完成條件：** 清單列出的留言數與使用者指定範圍一致；不在範圍內的留言已從 manifest 移除。
2. **重整草稿**：工具產生的 `.md` 只是起點（依句號／分號切句、開頭標籤加粗、SHA 加反引號）。逐則對照 `.orig.txt` 重新組織：可對照的資料改表格、步驟改編號清單。文字只重新排版，不改意思、不增刪事實。機械轉換的常見錯誤：粗體被切斷、括號內的「；」被拆成兩項、8 碼日期被當成 SHA、長標籤沒被辨識。
   **完成條件：** 每則草稿都讀過一遍並與原文比對，原文的每個事實都還在。
3. **校正**：`node $MF --check <dir>`，再對確定的檔案 `node $MF --write --ignore-rule MDX018 <files>`，重跑 `--check`；裸網址改成連結。
   **完成條件：** 只剩 MDX018，或 0 問題。
4. **預演**：`python3 -I $T apply --manifest <dir>/manifest.json --dry-run`。它會重讀每則留言，`version` 或 `format` 與盤點時不同就跳過；work item 為 Done／Removed／Closed 時跳過，只有使用者明確點名才加 `--include-closed`。
   **完成條件：** 每則都是 `dry-run` 或有說明理由的 `skip`。
5. **寫入**：去掉 `--dry-run` 再跑一次（可用 `--only <commentId ...>` 先試一則）。結果寫在 `<dir>/apply-results.json`。
   **完成條件：** 每則 `result` 為 `ok`、`newFormat` 為 `markdown`。
6. **抽查渲染**：`python3 -I $T verify --id <ID> --comment <commentId>`，確認 `renderedTags` 含預期的 `table`／`ol`／`ul`／`strong`；需要時加 `--show` 看 HTML。
   **完成條件：** 每種版型（表格型、清單型）至少抽查一則，渲染符合預期；向使用者回報處理數、跳過數與原因。

## 安全界線

- 只改使用者指定範圍內、指定作者的留言；他人的留言不動。
- 修改留言會在 ADO 顯示「已編輯」，對方已讀的交接留言改寫前先說明影響。
- Done／Removed／Closed 項目預設不改，使用者點名才加 `--include-closed`。
- 帳密與權杖只經 `az` 取得，不寫入草稿、manifest 或輸出。

## C. Markdown 校正工具（`markdown-fixer.mjs`）

零依賴的 Node 腳本（需 Node.js 20 以上，建議 22+），把 Markdown 的常見語法錯誤分成兩類：可自動修正的格式問題，以及必須人工判斷的結構或語意問題。流程是先檢查、再只寫入明確指定的檔案、看過 diff、最後重跑確認。

### 快速開始

```bash
# 檢查（預設模式；不帶路徑時掃描目前目錄）
node $MF --check README.md docs/

# 只寫入明確指定的檔案
node $MF --write README.md docs/guide.md

# 只看某幾條規則
node $MF --check --rule MDX010,MDX011 README.md

# 忽略某條規則
node $MF --check --ignore-rule MDX032 docs/

# CI 用的 JSON
node $MF --check --json docs/

# 列出規則
node $MF --list-rules
```

- `--check` 是預設模式，不會寫檔。
- `--write` 必須明確指定路徑；若給目錄，會處理該目錄下所有掃描到的 Markdown。先跑 `--check` 看清單；不帶路徑會直接拒絕，避免意外重寫整個工作樹。
- 結束碼：`0` 沒有需要處理的問題；`1` 仍有 warning/error（加 `--strict` 時 info 也算）；`2` 用法、I/O 或解析錯誤。
- `--rule MDX090` 會自動啟用 120 字元行長；也可用 `--max-line-length N` 指定。
- `--json` 的 `changed` 表示這次真的寫入，`wouldChange` 表示檔案需要變更；check 模式的 `changed` 一定是 `false`。

### 工作流程

1. **界定範圍。** 列出這次要處理的 Markdown 檔案；排除 `vendor/`、`node_modules/`、產生的檔案與 golden fixtures。
   **完成條件：** 有一份明確的檔案清單，知道哪些檔案不會被碰。

2. **先檢查，不要先寫。** 對清單執行 `--check`，記錄 rule ID、行號與 severity。
   **完成條件：** 能分辨哪些是 fixable、哪些是 report-only、哪些是結構錯誤。

3. **判斷風險。** 如果出現 MDX081（未關閉 frontmatter）、MDX083（未關閉 HTML comment）、MDX053（非法 fence info）或 MDX085（未關閉 `$$` 數學區塊），先人工修好結構，不要期待 `--write` 處理。
   **完成條件：** 沒有會讓工具拒絕寫入的結構錯誤。

4. **只寫入明確檔案。** 用 `--write <files>`，一次一個範圍。不要用 `--write .`。
   **完成條件：** 指令結束，且沒有寫到清單以外的檔案。

5. **看 diff。** 執行 `git diff -- <files>`，逐段確認。特別注意標題、清單邊界、表格欄數與 CJK 行長。
   **完成條件：** 每一個 diff 都能說明為什麼要改；不想要的變更已用 `--ignore-rule` 或人工回退排除。

6. **人工處理 report-only 項目。** 依 `reference/rules.md` 的說明修正，或用 `--ignore-rule` 明確接受。
   **完成條件：** 每個剩下的 warning/error 都有處置理由。

7. **重跑驗證。** 再跑一次 `--check`；目標是 0 warning/0 error，或只剩已記錄理由的 info。
   **完成條件：** 指令結束碼為 `0`，或剩下的項目已明確說明。

8. **依專案規範收尾。** 若這是要提交的變更，照 `AGENTS.md` 更新版號、跑對應測試。
   **完成條件：** 專案要求的檢查與版號更新都完成。

### 安全契約

- 只改 Markdown 語法，不改意思、不改措辭、不重新排版段落。
- 不動 fenced code、inline code、frontmatter、數學式、URL、raw HTML、連結目的地。兩個行尾空格視為刻意換行，會保留。
- 不發明 image alt text、連結目標、標題層級或表格內容。
- 不確定的地方留給人判斷；report-only 規則不會被 `--write` 套用。
- `MDX081`、`MDX083`、`MDX053`、`MDX085`，以及「修正後會把 `---` 變成 frontmatter」的情況，會讓檔案保持原樣並回報原因；這是刻意的安全拒絕，不是 bug。blocking 規則即使被 `--ignore-rule` 點名，也不會放行寫入。
- 這個工具是行導向的啟發式檢查器，不是完整 CommonMark parser。跨行的 inline 結構、MDX/JSX、複雜 YAML 不會被完整解析。

### 可自動修正的規則

| Rule | 內容 |
| --- | --- |
| MDX001 | 移除檔案開頭的 UTF-8 BOM |
| MDX002 | 把 CRLF/CR 統一成 LF |
| MDX003 | 檔尾保留剛好一個換行 |
| MDX004 | 移除行尾空白；保留兩個空格的 hard break |
| MDX005 | 多個連續空行縮成一個 |
| MDX006 | 移除檔首空行 |
| MDX008 | 把 code/URL 以外的 NBSP 換成普通空格 |
| MDX010 | `#Title` → `# Title` |
| MDX011 | 標題標記後只留一個空格 |
| MDX012 | 移除 ATX 標題尾端的 `###` |
| MDX013 | 標題與相鄰段落之間補空行 |
| MDX020 | blockquote 的 `>` 後只留一個空格；保留縮排 code |
| MDX030 | `-item` → `- item`、`1.item` → `1. item` |
| MDX031 | 同一縮排層級的清單統一使用同一種 bullet |
| MDX040 | 移除 `**`、`__`、`*`、`_` 內側多餘空白（單一 `*`/`_` 只修非對稱情況） |
| MDX052 | 頂層 fenced code 與相鄰 block 之間補空行 |
| MDX060 | 表格分隔列每格至少三個 `-` |
| MDX062 | 頂層表格與相鄰 block 之間補空行 |
| MDX082 | frontmatter 後補一個空行 |

這些修正仍要看 diff。`MDX010` 無法分辨 `#hashtag` 與壞掉的標題；`MDX030` 無法分辨 `-item` 與以連字號開頭的英文字；`MDX031` 可能把空行隔開的兩個清單統一成同一種 marker。

### 只報告、不自動修正的規則

- **標題與結構：** MDX014 縮排標題、MDX015 跳級、MDX016 空標題、MDX017 標題尾端標點、MDX018 第一個標題不是 H1、MDX019 多個 H1、MDX080 Setext 歧義、MDX081 未關閉 frontmatter、MDX083 未關閉 HTML comment、MDX084 全形 Markdown 語法、MDX085 未關閉的 `$$` 數學區塊。
- **清單與強調：** MDX032 清單與段落之間缺空行、MDX035 空清單項目、MDX041 可能未配對的強調符號。
- **Code fence：** MDX050 缺少語言、MDX051 未關閉 fence、MDX053 非法 fence info。
- **表格：** MDX061 欄數不一致、MDX063 表格 cell 內的 code/URL 含未轉義的 `|`。
- **連結與圖片：** MDX070 裸 URL、MDX071 空連結、MDX072 `] (` 的空格、MDX073 缺少 reference definition、MDX074 重複定義、MDX075 圖片缺 alt。
- **其他：** MDX007 tab、MDX009 零寬字元、MDX090 行長。

完整說明、before/after 範例、markdownlint 近似對應與 CJK 注意事項在 [`reference/rules.md`](reference/rules.md)。

### 常見操作

```bash
# 只修標題相關
node $MF --write --rule MDX010,MDX011,MDX012,MDX013 README.md

# 先看某個目錄有多少問題，不要寫入
node $MF --check docs/

# 把 info 也視為失敗，適合嚴格 CI
node $MF --check --strict docs/

# 只看前幾行問題
node $MF --check docs/ | head -40
```

### Paste-to-Markdown 專案注意事項

- 這個工具處理的是**專案裡的 Markdown 文件**，不是 app 的貼上轉換邏輯。執行期轉換在 `assets/clipboard2markdown.js` 與 `assets/to-markdown.js`；要改貼上行為，必須改 app 邏輯並補 `e2e/` 測試，不能只跑這支腳本。
- `tests/tcN-perfect.md` 是 golden fixtures，代表 app 的預期輸出。除非轉換行為刻意改變，否則不要對它們跑 `--write`；若真的改了轉換行為，連同 fixture 與對應的 E2E 期望一起更新。
- 不要在那個 repo 執行 `--write .`。它會掃到 `AGENTS.md`、`tasks/todo.md` 與 golden fixtures，產生不必要的 diff。
- 任何要提交的變更都要照 `AGENTS.md`：`index.html` 的 footer 與 JSON-LD `softwareVersion` 同步 bump patch 版號；只有改到 JS/CSS 時才需要更新 cache-busting query string。
- 這支腳本自己的測試：
  ```bash
  node --test <skill>/scripts/markdown-fixer.test.mjs
  ```

### 已知限制

- Frontmatter 必須從檔案第一個位元組開始（可有 BOM）。`---` 前面若有空行，語意上是 thematic break；若移除空行會讓第一行（忽略 BOM）變成 `---`，即使那行可能只是 thematic break，工具也會拒絕寫入，請人工確認。
- HTML block 採 CommonMark type 1–7 的近似判斷。type 6/7 會持續到下一個空行，所以 `</div>` 後面沒有空行時，後面的 Markdown 會被視為 raw HTML 而不處理。
- 縮排 4 個空白欄位（tab 以 4 欄計）以上的表格、blockquote 內的表格，可能不會被偵測；清單內縮排 1–3 個空格的表格會偵測，但 MDX062 不處理。
- 縮排段落延續（lazy continuation）與 indented code 的邊界用啟發式判斷；4 欄以上的行若緊接段落，會視為段落延續。
- 以 `---` 開頭且後面有第二條 `---` 的檔案一律視為 frontmatter；若其實是 Setext 標題或水平線，先人工確認。若移除檔首空行會讓後面的 `---` 變成 frontmatter，`--write` 會拒絕寫入。
- 目錄掃描預設跳過 `.git`、`node_modules`、`vendor`、`coverage`、`test-results`、`playwright-report`、`blob-report`、`.e2e-tmp`；其他隱藏目錄（例如 `.github`、`.agents`）仍會掃描。
- 行長以 Unicode code point 計算，CJK 算 1，不是終端顯示寬度；表格行不計入 MDX090。
- 跨行的 link/emphasis、巢狀 blockquote 內的標題與清單、複雜 YAML 不做完整解析。
- 多行數學區塊以行首、blockquote、清單或 task-list 內容開頭的 `$$` 開始，之後任一行含 `$$` 結束；若區塊內容本身含 `$$` 會提前結束。行首 `$$` 一律視為數學區塊開頭；若只是文字，請改寫或加反斜線。跨行單一 `$...$` 不支援；` ```math ` 仍由 fenced code 保護。更深的混合巢狀（例如清單內 blockquote 再清單）可能無法精確配對，會保守地回報 MDX085；`\[...\]`、`\begin{...}` 等其他數學語法也不特別保護。
- `MDX002` 停用時，若沒有其他修正，檔案維持原樣（含混合行尾）；若有其他修正，行尾會以 CRLF 優先、其次 CR 統整。
- URL 內的 NBSP 只報告、不自動改；請人工換成 `%20` 或修正 URL。
