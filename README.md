# fix-ado-comment-skills

修復 Azure DevOps（ADO）work item 留言格式的一組 agent skills：發布真正的 Markdown 留言，並把既有黏成一大段的 HTML 留言改寫回可讀的 Markdown。

## 目錄結構

```
skills/
├── fix-ado-comment-markdown/   # ADO 留言發布與修復
│   ├── SKILL.md
│   ├── agents/openai.yaml      # Codex CLI 介面與調用政策
│   └── scripts/ado_comments.py
└── markdown-autocorrect/       # Markdown 語法校正
    ├── SKILL.md
    ├── agents/openai.yaml
    ├── scripts/markdown-fixer.mjs
    └── reference/rules.md
```

## skills 一覽

| Skill | 用途 | 觸發時機 |
|-------|------|----------|
| `fix-ado-comment-markdown` | 以 `format=markdown` 發布／修改 ADO 留言，並把既有 HTML 留言修復成 Markdown | ADO 留言、Discussion、work item comment、修復留言 |
| `markdown-autocorrect` | 檢查並校正常見 Markdown 語法錯誤（標題、清單、表格、全形標點、CJK 排版等） | Markdown 校正、lint、normalize、修 Markdown |

兩個 skill 都採**明確調用**制：只在使用者明確調用時啟用，不會依關鍵字自動觸發。Claude Code 與 Codex CLI 兩種格式都已支援：

| 環境 | 調用方式 | 實作機制 |
|------|----------|----------|
| Claude Code | `/fix-ado-comment-markdown`、`/markdown-autocorrect` | SKILL.md：`disable-model-invocation: true` |
| Codex CLI | `$fix-ado-comment-markdown`、`$markdown-autocorrect`（或 `/skills`） | `agents/openai.yaml`：`policy.allow_implicit_invocation: false` |

兩個 skill 是搭配使用的：`fix-ado-comment-markdown` 在發布或寫入前會呼叫 `markdown-autocorrect` 校正草稿。

### fix-ado-comment-markdown

ADO 留言的儲存格式由每則留言的 `format` 欄位決定。`az boards work-item update --discussion` 與 JSON Patch 只會存成 `html`，多句話會黏成一大段；本 skill 改走 Comments REST API 並指定 `format=markdown`。

工具是 `scripts/ado_comments.py`（純 Python 標準庫，透過 `az rest` 呼叫）：

```bash
export ADO_ORG=https://dev.azure.com/<org> ADO_PROJECT=<project>
T=~/.agents/skills/fix-ado-comment-markdown/scripts/ado_comments.py

python3 -I $T post   --id <workItemId> --file comment.md   # 發布新留言
python3 -I $T pull   --id <ID> --author <uniqueName> --out <dir>   # 盤點 HTML 留言
python3 -I $T apply  --manifest <dir>/manifest.json --dry-run      # 預演修復
python3 -I $T verify --id <ID> --comment <commentId>               # 抽查渲染結果
```

安全界線：只動使用者指定範圍與作者的留言；Done／Removed／Closed 項目預設不改。

### markdown-autocorrect

零依賴的 Node 腳本，把問題分成「可自動修正」與「只報告、需人工判斷」兩類：

```bash
MF=~/.agents/skills/markdown-autocorrect/scripts/markdown-fixer.mjs

node $MF --check <path>                                  # 只檢查
node $MF --write --ignore-rule MDX018 <files>            # 只寫入指定檔案
node $MF --list-rules                                    # 列出規則
```

規則清單見 `skills/markdown-autocorrect/reference/rules.md`。留言情境通常忽略 MDX018（第一個標題不是 H1）。

## 安裝

建議用 [skills](https://github.com/vercel-labs/skills) CLI（需 Node.js 22.20+），在專案目錄執行：

```bash
npx skills add doggy8088/fix-ado-comment-skills
```

會列出 skills 與可安裝的 coding agents 讓你挑選；也可以直接指定：

```bash
# 只裝一個 skill，指定 agent，裝到所有專案可用的位置
npx skills add doggy8088/fix-ado-comment-skills --skill fix-ado-comment-markdown -a claude-code -g
```

`-a` 指定目標 agent（`claude-code`、`codex` 等）；skills 會裝到該 agent 偵測的目錄。

其他常用指令：`npx skills list`（已安裝）、`npx skills check`／`update`（更新）、`npx skills remove`（移除）。

不想用 CLI 就手動複製到 agent 的 skills 目錄：

```bash
cp -R skills/* ~/.claude/skills/   # Claude Code（或專案的 .claude/skills/）
cp -R skills/* ~/.codex/skills/    # Codex CLI
```

## 需求

- Azure CLI（`az`），並已登入有 ADO 權限的帳號
- Python 3（執行 `ado_comments.py`）
- Node.js（執行 `markdown-fixer.mjs`）

## 授權

MIT License © 2026 Will 保哥
