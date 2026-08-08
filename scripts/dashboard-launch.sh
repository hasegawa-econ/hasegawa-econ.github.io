#!/bin/zsh
# 研究ダッシュボードの起動スクリプト（研究ダッシュボード.app から呼ばれる）
# 1) Zotero書誌・読書ステータス・AI要約をダッシュボードに同期
# 2) 生成ヘルパーとプレビューサーバーを起動（未起動なら）
# 3) ブラウザでダッシュボードを開く

export PATH="/usr/local/bin:$HOME/.local/bin:$PATH"

SITE_DIR="$HOME/mysite"
ECON_JSON="$HOME/Documents/Zotero Paper/Econ.json"
COCKPIT_DIR="$SITE_DIR/paper-ai-project"
PORT=4321
URL="http://localhost:$PORT/dashboard/"

cd "$SITE_DIR" || exit 1

# --- 1) データ同期（あるものだけ）---
[ -f "$ECON_JSON" ] && cp "$ECON_JSON" "$SITE_DIR/dashboard/library.json"
[ -f "$COCKPIT_DIR/shelf_state.json" ] && cp "$COCKPIT_DIR/shelf_state.json" "$SITE_DIR/dashboard/shelf.json"
if [ -d "$COCKPIT_DIR/ai_summary" ]; then
  ls "$COCKPIT_DIR/ai_summary" | grep '\.json$' | sed 's/\.json$//' | \
    /usr/bin/python3 -c 'import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))' \
    > "$SITE_DIR/dashboard/ai_list.json"
  mkdir -p "$SITE_DIR/dashboard/ai"
  rsync -a --delete --exclude thumbs "$COCKPIT_DIR/ai_summary/" "$SITE_DIR/dashboard/ai/"
fi
mkdir -p "$SITE_DIR/docs/dashboard"
for f in library.json shelf.json ai_list.json; do
  [ -f "$SITE_DIR/dashboard/$f" ] && cp "$SITE_DIR/dashboard/$f" "$SITE_DIR/docs/dashboard/$f"
done
[ -d "$SITE_DIR/dashboard/ai" ] && rsync -a --delete "$SITE_DIR/dashboard/ai/" "$SITE_DIR/docs/dashboard/ai/"

# --- 2) 生成・公開ヘルパー ---
if ! lsof -i :4322 >/dev/null 2>&1; then
  nohup zsh -ic "/usr/bin/python3 '$SITE_DIR/scripts/dashgen.py'" \
    > /tmp/dashgen.log 2>&1 &
fi

# --- 2') サイトのプレビューサーバー ---
if ! lsof -i :$PORT >/dev/null 2>&1; then
  nohup quarto preview --profile local --port $PORT --no-browser \
    > /tmp/quarto-preview.log 2>&1 &
  for i in {1..60}; do
    lsof -i :$PORT >/dev/null 2>&1 && break
    sleep 0.5
  done
fi

# --- 3) 開く ---
open "$URL"
exit 0
