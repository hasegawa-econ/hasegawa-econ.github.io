#!/usr/bin/env python3
"""
dashgen.py — ダッシュボードの「AI生成」ボタン用ローカルヘルパー (port 4322)

研究ダッシュボード.command から自動起動される。ダッシュボードのページから
  POST /generate?ck=<citekey>  … extract.py で要約生成（バックグラウンド）
  GET  /status?ck=<citekey>    … {"state": "running"|"done"|"error: ..."}
  GET  /health                 … 稼働確認
を受け、生成完了時に dashboard/ai/ と docs/dashboard/ai/ へ結果を同期する。
ローカル(127.0.0.1)のみで待ち受ける。公開サイトとは無関係。
"""
import json
import os
import re
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

BASE = Path(__file__).resolve().parent.parent          # ~/mysite
COCKPIT = BASE / "paper-ai-project"
ECON = Path.home() / "Documents" / "Zotero Paper" / "Econ.json"
PORT = 4322

sys.path.insert(0, str(COCKPIT))
import zotero_lib  # noqa: E402

STATE = {}   # citekey -> "running" | "done" | "error: ..."
LOCK = threading.Lock()


def ensure_api_key():
    """ANTHROPIC_API_KEY が環境になければ ~/.zshrc から拾う。"""
    if os.environ.get("ANTHROPIC_API_KEY"):
        return
    zshrc = Path.home() / ".zshrc"
    if zshrc.exists():
        m = re.search(r'export\s+ANTHROPIC_API_KEY=["\']?([^"\'\s]+)',
                      zshrc.read_text(encoding="utf-8", errors="ignore"))
        if m:
            os.environ["ANTHROPIC_API_KEY"] = m.group(1)


def pdf_for(ck):
    for p in zotero_lib.load_papers(ECON):
        if p["citekey"] == ck:
            return p.get("pdf") or ""
    return ""


def sync_outputs(ck):
    """生成された要約をダッシュボード（ソースと配信先の両方）へ反映。"""
    src = COCKPIT / "ai_summary" / f"{ck}.json"
    if not src.exists():
        raise FileNotFoundError(f"{src} がありません")
    for dst_dir in [BASE / "dashboard" / "ai", BASE / "docs" / "dashboard" / "ai"]:
        dst_dir.mkdir(parents=True, exist_ok=True)
        (dst_dir / src.name).write_bytes(src.read_bytes())
    keys = sorted(p.stem for p in (COCKPIT / "ai_summary").glob("*.json"))
    for lst in [BASE / "dashboard" / "ai_list.json",
                BASE / "docs" / "dashboard" / "ai_list.json"]:
        lst.parent.mkdir(parents=True, exist_ok=True)
        lst.write_text(json.dumps(keys, ensure_ascii=False), encoding="utf-8")


def generate(ck):
    try:
        pdf = pdf_for(ck)
        if not pdf or not Path(pdf).exists():
            with LOCK:
                STATE[ck] = "error: PDFが見つかりません（Zoteroに添付されていますか？）"
            return
        r = subprocess.run(
            [sys.executable, str(COCKPIT / "extract.py"), pdf, "--key", ck],
            cwd=str(COCKPIT), capture_output=True, text=True, timeout=1200)
        if r.returncode != 0:
            tail = (r.stderr or r.stdout or "").strip().splitlines()[-3:]
            with LOCK:
                STATE[ck] = "error: " + " / ".join(tail)[:300]
            return
        sync_outputs(ck)
        with LOCK:
            STATE[ck] = "done"
    except Exception as e:  # noqa: BLE001
        with LOCK:
            STATE[ck] = f"error: {e}"[:300]


class Handler(BaseHTTPRequestHandler):
    def _send(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # noqa: N802
        self._send({"ok": True})

    def do_GET(self):  # noqa: N802
        u = urlparse(self.path)
        q = parse_qs(u.query)
        ck = (q.get("ck") or [""])[0]
        if u.path == "/health":
            self._send({"ok": True})
        elif u.path == "/status":
            with LOCK:
                self._send({"state": STATE.get(ck, "unknown")})
        elif u.path == "/generate":
            self.do_POST()
        else:
            self._send({"error": "not found"}, 404)

    def do_POST(self):  # noqa: N802
        u = urlparse(self.path)
        q = parse_qs(u.query)
        ck = (q.get("ck") or [""])[0]
        if u.path != "/generate" or not ck:
            self._send({"error": "citekeyがありません"}, 400)
            return
        with LOCK:
            if STATE.get(ck) == "running":
                self._send({"state": "running"})
                return
            STATE[ck] = "running"
        threading.Thread(target=generate, args=(ck,), daemon=True).start()
        self._send({"state": "running"})

    def log_message(self, *a):  # 静かに
        pass


if __name__ == "__main__":
    ensure_api_key()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"dashgen: http://127.0.0.1:{PORT} (Ctrl+Cで終了)")
    server.serve_forever()
