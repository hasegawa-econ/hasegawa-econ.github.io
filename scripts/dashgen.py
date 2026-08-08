#!/usr/bin/env python3
"""
dashgen.py — ダッシュボード用ローカルヘルパー (port 4322)

研究ダッシュボード.app から自動起動される。127.0.0.1のみで待ち受け、
公開サイトとは無関係。ダッシュボードのページから:

  GET  /health                 稼働確認
  POST /generate?ck=           extract.py でAI要約を生成（バックグラウンド）
  GET  /status?ck=             生成状態 {"state": "running"|"done"|"error: ..."}
  POST /shelf?ck=&status=      読書ステータス変更（未読/読中/読了）
  POST /star?ck=&on=1|0        ★の切り替え
  POST /hide?ck=               ダッシュボードから隠す（Zotero本体は触らない）
  GET  /pdf?ck=                ローカルPDFをブラウザに配信
  GET  /drafts                 ブログ下書きがある citekey 一覧
  POST /publish?ck=            下書きを記事化して本番ブログへデプロイ
  GET  /pubstatus?ck=          公開状態
"""
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE = Path(__file__).resolve().parent.parent          # ~/mysite
COCKPIT = BASE / "paper-ai-project"
DRAFTS = BASE / "notes" / "blog-drafts"
ECON = Path.home() / "Documents" / "Zotero Paper" / "Econ.json"
SHELF = COCKPIT / "shelf_state.json"
PORT = 4322
QUARTO = shutil.which("quarto") or "/usr/local/bin/quarto"
GIT = shutil.which("git") or "/usr/bin/git"

sys.path.insert(0, str(COCKPIT))
import zotero_lib  # noqa: E402

STATE = {}   # "gen:<ck>" / "pub:<ck>" -> "running" | "done" | "error: ..."
LOCK = threading.Lock()


def ensure_api_key():
    """必要な環境変数が無ければ ~/.zshrc から拾う。"""
    zshrc = Path.home() / ".zshrc"
    text = zshrc.read_text(encoding="utf-8", errors="ignore") if zshrc.exists() else ""
    for name in ("ANTHROPIC_API_KEY", "ZOTERO_API_KEY"):
        if not os.environ.get(name):
            m = re.search(r'export\s+' + name + r'=["\']?([^"\'\s]+)', text)
            if m:
                os.environ[name] = m.group(1)


def econ_source():
    """Econ.json（権限で読めない場合は同期コピー）のパスを返す。"""
    try:
        with open(ECON, "rb"):
            return ECON
    except OSError:
        return BASE / "dashboard" / "library.json"


def paper_of(ck):
    try:
        for p in zotero_lib.load_papers(econ_source()):
            if p["citekey"] == ck:
                return p
    except Exception:  # noqa: BLE001
        pass
    return None


# ---------- shelf（ステータス・★・非表示）----------

def load_shelf():
    try:
        return json.loads(SHELF.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save_shelf(shelf):
    SHELF.write_text(json.dumps(shelf, ensure_ascii=False, indent=1),
                     encoding="utf-8")
    for dst in [BASE / "dashboard" / "shelf.json",
                BASE / "docs" / "dashboard" / "shelf.json"]:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(shelf, ensure_ascii=False), encoding="utf-8")


def update_shelf(ck, **kw):
    with LOCK:
        shelf = load_shelf()
        entry = shelf.setdefault(ck, {"status": "未読", "star": False})
        entry.update(kw)
        save_shelf(shelf)
    return shelf[ck]


# ---------- Zotero本体からの削除（Web API・要 ZOTERO_API_KEY）----------

def zotero_uri_of(ck):
    """Econ.json から citekey → zotero.org の uri を引く。"""
    try:
        data = json.loads(econ_source().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    for it in data.get("items", []):
        if it.get("citationKey") == ck:
            return it.get("uri")
    return None


def zotero_delete(ck):
    """Zotero Web API でアイテムを完全削除（ライブラリは同期済み前提）。"""
    import urllib.request
    key = os.environ.get("ZOTERO_API_KEY")
    if not key:
        return False, "ZOTERO_API_KEY が未設定（非表示のみ行いました）"
    uri = zotero_uri_of(ck)
    m = uri and re.match(r"https?://zotero\.org/users/(\d+)/items/(\w+)", uri)
    if not m:
        return False, "Zotero上のアイテムIDが特定できませんでした（非表示のみ）"
    uid, item_key = m.group(1), m.group(2)
    api = f"https://api.zotero.org/users/{uid}/items/{item_key}"
    try:
        req = urllib.request.Request(api, headers={"Zotero-API-Key": key})
        with urllib.request.urlopen(req, timeout=30) as res:
            version = res.headers.get("Last-Modified-Version") or \
                json.loads(res.read()).get("version", "")
        req = urllib.request.Request(api, method="DELETE", headers={
            "Zotero-API-Key": key,
            "If-Unmodified-Since-Version": str(version),
        })
        with urllib.request.urlopen(req, timeout=30):
            pass
        return True, "Zoteroから削除しました（次回同期でローカルにも反映）"
    except Exception as e:  # noqa: BLE001
        return False, f"Zotero API エラー: {e}（非表示のみ行いました）"


# ---------- 裸PDFのメタデータをAIで推測 ----------

BARE_META = BASE / "dashboard" / "bare_meta.json"


def bare_pdf_path(key):
    """Econ.json（同期コピー可）から、指定キーの添付PDFのローカルパスを返す。"""
    try:
        data = json.loads(econ_source().read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    for it in data.get("items", []):
        if it.get("itemType") == "attachment" and (it.get("uri") or "").endswith(key):
            return it.get("path")
    return None


def load_bare_meta():
    try:
        return json.loads(BARE_META.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def save_bare_meta(meta):
    for dst in [BASE / "dashboard" / "bare_meta.json",
                BASE / "docs" / "dashboard" / "bare_meta.json"]:
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def enrich(key):
    """裸PDFの先頭を読み、タイトル・著者・年を Claude に推測させて保存。"""
    st = "gen:bare:" + key
    try:
        pdf = bare_pdf_path(key)
        if not pdf or not Path(pdf).exists():
            with LOCK:
                STATE[st] = "error: PDFが見つかりません"
            return
        from pypdf import PdfReader
        import anthropic
        reader = PdfReader(pdf)
        text = "\n".join((reader.pages[i].extract_text() or "")
                         for i in range(min(2, len(reader.pages))))[:6000]
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=400,
            tools=[{
                "name": "record_metadata",
                "description": "論文の書誌情報",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "authors": {"type": "string", "description": "著者名をカンマ区切りで"},
                        "year": {"type": "string"},
                    },
                    "required": ["title", "authors", "year"],
                },
            }],
            tool_choice={"type": "tool", "name": "record_metadata"},
            messages=[{"role": "user", "content":
                       "次の論文の1ページ目から、タイトル・著者・出版年を抽出して。\n\n" + text}],
        )
        data = next((b.input for b in msg.content if b.type == "tool_use"), None)
        if not data:
            with LOCK:
                STATE[st] = "error: 抽出に失敗しました"
            return
        with LOCK:
            meta = load_bare_meta()
            meta[key] = data
            save_bare_meta(meta)
            STATE[st] = "done"
    except Exception as e:  # noqa: BLE001
        with LOCK:
            STATE[st] = f"error: {e}"[:300]


# ---------- AI要約の生成 ----------

def sync_ai_outputs(ck):
    src = COCKPIT / "ai_summary" / f"{ck}.json"
    if not src.exists():
        raise FileNotFoundError(f"{src} がありません")
    for dst_dir in [BASE / "dashboard" / "ai", BASE / "docs" / "dashboard" / "ai"]:
        dst_dir.mkdir(parents=True, exist_ok=True)
        (dst_dir / src.name).write_bytes(src.read_bytes())
    keys = sorted(p.stem for p in (COCKPIT / "ai_summary").glob("*.json"))
    for lst in [BASE / "dashboard" / "ai_list.json",
                BASE / "docs" / "dashboard" / "ai_list.json"]:
        lst.write_text(json.dumps(keys, ensure_ascii=False), encoding="utf-8")


def generate(ck):
    key = "gen:" + ck
    try:
        p = paper_of(ck)
        pdf = (p or {}).get("pdf") or ""
        if not pdf or not Path(pdf).exists():
            with LOCK:
                STATE[key] = "error: PDFが見つかりません（Zoteroに添付されていますか？）"
            return
        r = subprocess.run(
            [sys.executable, str(COCKPIT / "extract.py"), pdf, "--key", ck],
            cwd=str(COCKPIT), capture_output=True, text=True, timeout=1200)
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "").strip().splitlines()[-3:]
            with LOCK:
                STATE[key] = "error: " + " / ".join(tail)[:300]
            return
        sync_ai_outputs(ck)
        with LOCK:
            STATE[key] = "done"
    except Exception as e:  # noqa: BLE001
        with LOCK:
            STATE[key] = f"error: {e}"[:300]


# ---------- ブログ公開 ----------

def find_draft(ck):
    if not DRAFTS.exists():
        return None
    for f in DRAFTS.glob(f"*/{ck}.md"):
        return f
    return None


def parse_front_matter(text):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", text, re.S)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"')
    return meta, m.group(2)


def build_post(ck):
    """下書き → blog/posts/<ck>/index.qmd（機械整形）。"""
    draft = find_draft(ck)
    if not draft:
        raise FileNotFoundError("下書きが見つかりません")
    meta, body = parse_front_matter(draft.read_text(encoding="utf-8"))
    body = re.sub(r"<!--.*?-->", "", body, flags=re.S).strip()

    paper = meta.get("paper", ck)
    tag = meta.get("tag", "")
    p = paper_of(ck) or {}
    # description: 「一言でいうと」の最初の中身
    m = re.search(r"##\s*一言でいうと\s*\n+([^\n#]+)", body)
    desc = (m.group(1).strip() if m else "読書メモ")[:80]

    from datetime import date
    biblio = "**論文**：{authors} ({year}). \"{title}.\" {venue}".format(
        authors=meta.get("authors", p.get("author", "")),
        year=meta.get("year", p.get("year", "")),
        title=paper, venue=("*" + p["venue"] + "*.") if p.get("venue") else "")
    link = p.get("doi") and f" [doi:{p['doi']}](https://doi.org/{p['doi']})" or \
           (p.get("url") and f" [リンク]({p['url']})" or "")

    qmd = "\n".join([
        "---",
        f'title: "「{paper}」を読んだ"',
        f'description: "{desc}"',
        f'date: "{date.today().isoformat()}"',
        "categories: [" + ", ".join([t for t in [tag, "読書メモ"] if t]) + "]",
        "---",
        "",
        body,
        "",
        "---",
        "",
        biblio + link,
        "",
    ])
    out = BASE / "blog" / "posts" / ck / "index.qmd"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(qmd, encoding="utf-8")
    return out


def publish(ck):
    key = "pub:" + ck
    try:
        out = build_post(ck)
        rel = str(out.relative_to(BASE))
        subprocess.run([GIT, "add", rel], cwd=str(BASE), check=True)
        subprocess.run([GIT, "commit", "-m", f"ブログ公開: {ck}（ダッシュボードから）"],
                       cwd=str(BASE), capture_output=True, text=True)
        subprocess.run([GIT, "push", "origin", "main"], cwd=str(BASE),
                       capture_output=True, text=True, timeout=120)
        r = subprocess.run([QUARTO, "publish", "gh-pages", "--no-browser", "--no-prompt"],
                           cwd=str(BASE), capture_output=True, text=True, timeout=900)
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "").strip().splitlines()[-3:]
            with LOCK:
                STATE[key] = "error: " + " / ".join(tail)[:300]
            return
        # 下書きの status を published に
        draft = find_draft(ck)
        if draft:
            t = draft.read_text(encoding="utf-8").replace(
                "status: draft", "status: published", 1)
            draft.write_text(t, encoding="utf-8")
        with LOCK:
            STATE[key] = "done"
    except Exception as e:  # noqa: BLE001
        with LOCK:
            STATE[key] = f"error: {e}"[:300]


# ---------- HTTP ----------

class Handler(BaseHTTPRequestHandler):
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # noqa: N802
        self.send_response(200)
        self._cors()
        self.end_headers()

    def _start_thread(self, key, fn, ck):
        with LOCK:
            if STATE.get(key) == "running":
                self._send({"state": "running"})
                return
            STATE[key] = "running"
        threading.Thread(target=fn, args=(ck,), daemon=True).start()
        self._send({"state": "running"})

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        q = parse_qs(u.query)
        ck = (q.get("ck") or [""])[0]
        if u.path == "/health":
            self._send({"ok": True})
        elif u.path == "/status":
            with LOCK:
                self._send({"state": STATE.get("gen:" + ck, "unknown")})
        elif u.path == "/pubstatus":
            with LOCK:
                self._send({"state": STATE.get("pub:" + ck, "unknown")})
        elif u.path == "/enrichstatus":
            key = (q.get("key") or [""])[0]
            with LOCK:
                state = STATE.get("gen:bare:" + key, "unknown")
                meta = load_bare_meta().get(key) if state == "done" else None
            self._send({"state": state, "meta": meta})
        elif u.path == "/drafts":
            cks = sorted(f.stem for f in DRAFTS.glob("*/*.md")) if DRAFTS.exists() else []
            self._send({"drafts": cks})
        elif u.path == "/pdf":
            try:
                p = paper_of(ck)
                pdf = (p or {}).get("pdf") or ""
                if pdf and Path(pdf).exists():
                    data = Path(pdf).read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/pdf")
                    self.send_header("Content-Disposition",
                                     f'inline; filename="{ck}.pdf"')
                    self._cors()
                    self.end_headers()
                    self.wfile.write(data)
                else:
                    self._send({"error": "PDFが見つかりません"}, 404)
            except Exception as e:  # noqa: BLE001
                self._send({"error": f"PDFを開けませんでした: {e}"}, 500)
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):  # noqa: N802
        u = urlparse(self.path)
        q = parse_qs(u.query)
        # /enrich は key を使う（citekey 不要）ので先に処理
        if u.path == "/enrich":
            key = (q.get("key") or [""])[0]
            if not key:
                self._send({"error": "keyがありません"}, 400)
                return
            self._start_thread("gen:bare:" + key, enrich, key)
            return
        ck = (q.get("ck") or [""])[0]
        if not ck:
            self._send({"error": "citekeyがありません"}, 400)
            return
        if u.path == "/generate":
            self._start_thread("gen:" + ck, generate, ck)
        elif u.path == "/publish":
            self._start_thread("pub:" + ck, publish, ck)
        elif u.path == "/shelf":
            status = (q.get("status") or [""])[0]
            if status not in ("未読", "読中", "読了"):
                self._send({"error": "statusが不正です"}, 400)
                return
            self._send(update_shelf(ck, status=status))
        elif u.path == "/star":
            on = (q.get("on") or ["0"])[0] == "1"
            self._send(update_shelf(ck, star=on))
        elif u.path == "/hide":
            self._send(update_shelf(ck, hidden=True))
        elif u.path == "/delete":
            update_shelf(ck, hidden=True)      # まず即座に画面から消す
            deleted, note = zotero_delete(ck)
            self._send({"hidden": True, "deleted": deleted, "note": note})
        else:
            self._send({"error": "not found"}, 404)

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    ensure_api_key()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"dashgen: http://127.0.0.1:{PORT}")
    server.serve_forever()
