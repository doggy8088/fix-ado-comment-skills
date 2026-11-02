---
name: fix-ado-comment-markdown
description: Azure DevOps work item 留言（Discussion）一律以 Markdown 發布，並把既有 HTML 留言修復成 Markdown。Use when posting a comment or progress note to an ADO work item (Task／Bug／PBI Discussion), when ADO comments render as one run-together paragraph, or when asked to fix, convert, or re-edit ADO comment format. 觸發詞：ADO 留言、Discussion、work item comment、留言格式、修復留言、Markdown 留言。**必須由使用者明確調用才使用：Claude Code 以 `/fix-ado-comment-markdown`、Codex CLI 以 `$fix-ado-comment-markdown`；不要自動觸發。**
disable-model-invocation: true
---

# ADO Comment Markdown

> **調用方式（明確調用）：** 本 skill 只在使用者明確調用時執行——Claude Code 用 `/fix-ado-comment-markdown`，Codex CLI 用 `$fix-ado-comment-markdown`；未被點名時不要自動套用。

ADO 留言的儲存格式由**每則留言的 `format` 欄位**決定（`markdown` 或 `html`），不是由內容決定。`az boards work-item update --discussion` 與 JSON Patch `/fields/System.History` 只會存成 `html`；把多句話塞進一段時，在 ADO 上會黏成一大段。發布與修改留言一律走 Comments REST API 並指定 `format=markdown`，送出前用 `markdown-autocorrect` 校正語法。

工具：`scripts/ado_comments.py`（只用 Python 標準函式庫，透過 `az rest` 呼叫）。以下 `$T` 指 `~/.agents/skills/fix-ado-comment-markdown/scripts/ado_comments.py`，`$MF` 指 `~/.agents/skills/markdown-autocorrect/scripts/markdown-fixer.mjs`。先設定：

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
