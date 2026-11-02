#!/usr/bin/env python3
"""Azure DevOps work item 留言的 Markdown 發布與修復工具（只用標準函式庫，透過 `az rest` 呼叫 REST API）。

子命令：
  pull    列出指定 work item 的留言，把符合條件的 HTML 留言輸出成原文與 Markdown 草稿，並寫 manifest.json
  apply   依 manifest.json 把草稿以 format=markdown PATCH 回去（先核對 version、format 與 work item 狀態）
  post    以 format=markdown 發布一則新留言
  verify  讀回留言（$expand=renderedText），確認 format 與渲染結果

組織與專案可用 --org／--project 指定，或設定環境變數 ADO_ORG（例：https://dev.azure.com/contoso）與 ADO_PROJECT。
"""
import argparse
import html as htmllib
import json
import os
import re
import subprocess
import sys
import urllib.parse
from pathlib import Path

RESOURCE = "499b84ac-1321-427f-aa17-267ca6975798"  # Azure DevOps 的 Entra ID 資源 ID
API = "7.1-preview.4"
CLOSED_STATES = {"Done", "Removed", "Closed"}


def az_rest(method, uri, body=None):
    cmd = ["az", "rest", "--method", method, "--resource", RESOURCE, "--uri", uri]
    tmp = None
    if body is not None:
        tmp = Path(os.environ.get("TMPDIR", "/tmp")) / f"ado-comment-{os.getpid()}.json"
        tmp.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        cmd += ["--headers", "Content-Type=application/json", "--body", f"@{tmp}"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True)
    finally:
        if tmp and tmp.exists():
            tmp.unlink()
    if r.returncode:
        raise SystemExit(f"az rest {method} 失敗：{r.stderr.strip()[:500]}")
    return json.loads(r.stdout) if r.stdout.strip() else None


def base(args):
    org = (args.org or os.environ.get("ADO_ORG", "")).rstrip("/")
    project = args.project or os.environ.get("ADO_PROJECT", "")
    if not org or not project:
        raise SystemExit("需要 --org 與 --project（或環境變數 ADO_ORG、ADO_PROJECT）")
    return f"{org}/{urllib.parse.quote(project)}/_apis/wit/workItems"


def work_item_state(b, wi):
    d = az_rest("get", f"{b}/{wi}?fields=System.State&api-version=7.1")
    return d["fields"].get("System.State", "")


def list_comments(b, wi, expand=False):
    comments, token = [], None
    while True:
        q = {"api-version": API, "$top": "200"}
        if expand:
            q["$expand"] = "renderedText"
        if token:
            q["continuationToken"] = token
        d = az_rest("get", f"{b}/{wi}/comments?{urllib.parse.urlencode(q)}")
        comments += d.get("comments", [])
        token = d.get("continuationToken")
        if not token:
            return comments


def get_comment(b, wi, cid, expand=False):
    q = f"api-version={API}" + ("&$expand=renderedText" if expand else "")
    return az_rest("get", f"{b}/{wi}/comments/{cid}?{q}")


# ---------- HTML → Markdown 草稿（只是起點，送出前必須人工重整） ----------

def _split_top(body):
    """依句號與分號切句，但不切開括號或引號內的內容。"""
    out, buf, depth = [], "", 0
    for ch in body:
        if ch in "（(「":
            depth += 1
        elif ch in "）)」":
            depth = max(0, depth - 1)
        buf += ch
        if depth == 0 and ch in "。；":
            out.append(buf.rstrip("；").strip())
            buf = ""
    if buf.strip():
        out.append(buf.strip())
    return [x for x in out if x]


def _inline(fragment):
    fragment = re.sub(
        r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        lambda m: f'[{re.sub("<[^>]+>", "", m.group(2))}]({m.group(1)})',
        fragment,
        flags=re.S,
    )
    fragment = re.sub(r"</?(b|strong)>", "**", fragment)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return htmllib.unescape(fragment).strip()


def _code_spans(text):
    """把 SHA（含英文字母的 8 或 40 碼十六進位）與常見路徑加上反引號；已是連結或 URL 的片段不動。"""
    keep = []

    def hold(m, fmt=lambda s: s):
        keep.append(fmt(m.group(0)))
        return f"\x00{len(keep) - 1}\x00"

    text = re.sub(r"\[[^\]]*\]\([^)]*\)", hold, text)
    text = re.sub(r"https?://[^\s，。；、（）]+", hold, text)
    text = re.sub(r"(?<![\w/.-])(?:\.?[\w-]+/)+[\w.-]+\.(?:md|json|java|ts|xml|sql|jsp|py|sh|yml)\b",
                  lambda m: hold(m, lambda s: f"`{s}`"), text)
    text = re.sub(r"(?<![\w])(?=[0-9a-f]*[a-f])(?:[0-9a-f]{40}|[0-9a-f]{8})(?![\w])",
                  lambda m: hold(m, lambda s: f"`{s}`"), text)
    while "\x00" in text:
        text = re.sub(r"\x00(\d+)\x00", lambda m: keep[int(m.group(1))], text)
    return text


def _paragraph(p):
    if not p:
        return ""
    p = _code_spans(p)
    m = re.match(r"^([^：。；\n]{2,60}?)：(.+)$", p, re.S)
    label, body = (m.group(1), m.group(2)) if m else (None, p)
    items = _split_top(body)
    if len(items) <= 1:
        return (f"**{label}：** " if label else "") + (items[0] if items else "")
    head = f"**{label}**\n\n" if label else ""
    return head + "\n".join(f"- {x}" for x in items)


def html_to_markdown_draft(text):
    blocks = []
    for chunk in re.split(r"(<ul>.*?</ul>|<ol>.*?</ol>)", text.replace("\n", " "), flags=re.S):
        if re.match(r"<(ul|ol)>", chunk):
            mark = "1." if chunk.startswith("<ol>") else "-"
            blocks.append("\n".join(f"{mark} {_inline(li)}" for li in re.findall(r"<li>(.*?)</li>", chunk, re.S)))
            continue
        for p in re.split(r"<br\s*/?>|</p>|<p>|</div>|<div>", chunk):
            q = _paragraph(_inline(p))
            if q:
                blocks.append(q)
    return "\n\n".join(blocks).strip() + "\n"


# ---------- 子命令 ----------

def cmd_pull(args):
    b = base(args)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    manifest = []
    for wi in args.id:
        state = work_item_state(b, wi)
        for c in list_comments(b, wi):
            author = c.get("createdBy", {}).get("uniqueName", "")
            if args.author and author.lower() != args.author.lower():
                continue
            if args.format and c.get("format") != args.format:
                continue
            if c.get("isDeleted"):
                continue
            stem = f"{wi}-{c['id']}"
            (out / f"{stem}.orig.txt").write_text(c["text"], encoding="utf-8")
            draft = html_to_markdown_draft(c["text"]) if c.get("format") == "html" else c["text"]
            (out / f"{stem}.md").write_text(draft, encoding="utf-8")
            manifest.append({"workItem": wi, "commentId": c["id"], "version": c["version"],
                             "format": c.get("format"), "author": author, "state": state,
                             "createdDate": c.get("createdDate"), "draft": f"{stem}.md"})
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    for m in manifest:
        print(f"{m['workItem']}\t{m['commentId']}\tv{m['version']}\t{m['format']}\t{m['state']}\t{m['draft']}")
    print(f"共 {len(manifest)} 則，草稿與 manifest 在 {out}")


def cmd_apply(args):
    b = base(args)
    out = Path(args.manifest).parent
    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    only = set(args.only or [])
    results = []
    for m in manifest:
        if only and m["commentId"] not in only:
            continue
        tag = f"{m['workItem']}/{m['commentId']}"
        state = work_item_state(b, m["workItem"])
        if state in CLOSED_STATES and not args.include_closed:
            results.append({**m, "result": f"skip: work item 為 {state}（需 --include-closed）"})
            continue
        cur = get_comment(b, m["workItem"], m["commentId"])
        if cur["version"] != m["version"] or cur.get("format") != m["format"]:
            results.append({**m, "result": f"skip: 已被修改（v{cur['version']} {cur.get('format')}）"})
            continue
        text = (out / m["draft"]).read_text(encoding="utf-8")
        if args.dry_run:
            results.append({**m, "result": "dry-run"})
            continue
        az_rest("patch", f"{b}/{m['workItem']}/comments/{m['commentId']}?format=markdown&api-version={API}", {"text": text})
        chk = get_comment(b, m["workItem"], m["commentId"], expand=True)
        rendered = chk.get("renderedText") or ""
        results.append({**m, "result": "ok" if chk.get("format") == "markdown" else "format-mismatch",
                        "newVersion": chk["version"], "newFormat": chk.get("format"),
                        "renderedLength": len(rendered)})
    (out / "apply-results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in results:
        print(f"{r['workItem']}/{r['commentId']}\t{r['result']}\t{r.get('newFormat', '')}\tv{r.get('newVersion', r['version'])}")


def cmd_post(args):
    b = base(args)
    text = Path(args.file).read_text(encoding="utf-8")
    c = az_rest("post", f"{b}/{args.id}/comments?format=markdown&api-version={API}", {"text": text})
    chk = get_comment(b, args.id, c["id"], expand=True)
    print(json.dumps({"workItem": args.id, "commentId": c["id"], "format": chk.get("format"),
                      "version": chk["version"], "renderedLength": len(chk.get("renderedText") or "")},
                     ensure_ascii=False))


def cmd_verify(args):
    b = base(args)
    c = get_comment(b, args.id, args.comment, expand=True)
    rendered = c.get("renderedText") or ""
    tags = sorted(set(re.findall(r"<(h[1-6]|table|ul|ol|strong|code|a)\b", rendered)))
    print(json.dumps({"format": c.get("format"), "version": c["version"], "renderedTags": tags}, ensure_ascii=False))
    if args.show:
        print(rendered)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--org", help="例：https://dev.azure.com/contoso（預設讀 ADO_ORG）")
    ap.add_argument("--project", help="專案名稱（預設讀 ADO_PROJECT）")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pull", help="輸出留言原文、Markdown 草稿與 manifest.json")
    p.add_argument("--id", type=int, nargs="+", required=True, help="work item ID，可多個")
    p.add_argument("--author", help="只取此 uniqueName 的留言（例：will.huang@miniasp.com）")
    p.add_argument("--format", default="html", help="只取此格式（預設 html；給空字串表示全部）")
    p.add_argument("--out", required=True, help="草稿輸出目錄")
    p.set_defaults(func=cmd_pull)

    p = sub.add_parser("apply", help="把草稿以 format=markdown PATCH 回去")
    p.add_argument("--manifest", required=True)
    p.add_argument("--only", type=int, nargs="*", help="只處理這些 commentId")
    p.add_argument("--include-closed", action="store_true", help="允許修改 Done／Removed／Closed 項目的留言")
    p.add_argument("--dry-run", action="store_true", help="只核對，不寫入")
    p.set_defaults(func=cmd_apply)

    p = sub.add_parser("post", help="以 Markdown 發布新留言")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--file", required=True, help="Markdown 檔")
    p.set_defaults(func=cmd_post)

    p = sub.add_parser("verify", help="讀回並檢查渲染結果")
    p.add_argument("--id", type=int, required=True)
    p.add_argument("--comment", type=int, required=True)
    p.add_argument("--show", action="store_true", help="印出 renderedText")
    p.set_defaults(func=cmd_verify)

    args = ap.parse_args()
    if getattr(args, "format", None) == "":
        args.format = None
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
