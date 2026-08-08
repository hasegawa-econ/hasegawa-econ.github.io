# 研究ワークスペースの使い方

このリポジトリは「研究のワークスペース」。ブログはその出力の一つ。

```
Safari/Chrome ──保存──▶ Zotero（本体: ~/Zotero）
                          │ Better BibTeX 自動エクスポート（設定済み）
                          ▼
        ~/Documents/Zotero Paper/Econ.json
                          │
   デスクトップ「研究ダッシュボード.command」をダブルクリック
                          │（Econ.json・読書ステータス・AI要約リストを同期して起動）
        ┌─────────────────┴──────────────────┐
        ▼                                    ▼
  サイトのダッシュボード                AIコックピット(streamlit)
  localhost:4321/dashboard/            localhost:8501
  一覧・検索・★・ステータス            AI要約の生成・閲覧（paper-ai-project）
                          │
          読む論文を pick ──▶ notes/ にメモ（Obsidian）
                          │
          公開したいものだけ ──▶ blog/posts/ に清書 ──▶ デプロイ
```

## 日々の動線

1. **論文を見つけたら**：ブラウザのZoteroコネクタで保存（Econ.jsonは自動更新）
2. **何を読むか決めるとき**：デスクトップの **研究ダッシュボード.command** をダブルクリック
3. **AI要約を作る・読む**：ダッシュボード右上「AIコックピットを開く」→ 論文ごとのボタンで生成
4. **メモ**：Obsidianで `notes/papers/` に1論文1ファイル（テンプレ: `notes/templates/文献メモ.md`）。研究アイデアは `notes/ideas/`
5. **記事にする**：メモを `blog/posts/<スラッグ>/index.qmd` に清書

## 公開（デプロイ）

```sh
cd ~/mysite
quarto publish gh-pages --no-browser --no-prompt
```

数分で https://hasegawa-econ.github.io に反映される。

## 公開・非公開の境界（重要）

| 場所 | 公開される？ |
|---|---|
| `index.qmd` / `about.qmd` / `blog/` | ✅ 公開 |
| `dashboard/` のページ | ❌ ローカル専用（publicプロファイルから除外） |
| `dashboard/*.json`（書誌・ステータス・AIリスト） | ❌ gitignore済み・ビルドにも入らない |
| `notes/`（メモ・研究アイデア） | ❌ gitignore済み |
| `paper-ai-project/`（AIコックピット・要約データ） | ❌ gitignore済み |

- 公開ビルド = `_quarto-public.yml`（デフォルト）、ローカル閲覧 = `_quarto-local.yml`
- ローカルプレビューを手動で起動する場合: `quarto preview --profile local`

## 各コンポーネントの正本（どこが本物か）

| データ | 正本の場所 |
|---|---|
| 書誌・PDF | Zotero（`~/Zotero`）。ワークスペースには置かない |
| 読書ステータス・★ | `paper-ai-project/shelf_state.json` |
| AI要約 | `paper-ai-project/ai_summary/*.json` |
| 人間のメモ・アイデア | `notes/`（Obsidian） |
| 公開記事 | `blog/posts/` |

`dashboard/*.json` は全部コピー（表示用キャッシュ）。消えても .command 再実行で復活する。

## 記事の書き方メモ

- コードは ```` ```python ````（表示のみ）で書く。実行結果込みの記事
  （```` ```{python} ````）を書きたくなったら、先にPython環境へ
  `jupyter` 一式を入れること（今は未導入なのでビルドが失敗する）
