# 研究ワークスペースの使い方

このリポジトリは「研究のワークスペース」。ブログはその出力の一つ。

```
Safari/Chrome ──保存──▶ Zotero（本体: ~/Zotero）
                          │ Better BibTeX 自動エクスポート（設定済み）
                          ▼
        ~/Documents/Zotero Paper/Econ.json
                          │
   デスクトップ「研究ダッシュボード.app」をダブルクリック
                          │（Econ.json等を同期し、ヘルパーとプレビューを起動）
                          ▼
              サイトのダッシュボード localhost:4321/dashboard/
   一覧・検索・★・ステータス変更・AI要約の生成と閲覧・PDF・下書き・公開
                          │
          読む論文を pick ──▶ notes/ にメモ（Obsidian）
                          │
          公開したいものだけ ──▶ blog/posts/ に清書 ──▶ デプロイ
```

## 日々の動線

1. **論文を見つけたら**：ブラウザのZoteroコネクタで保存（Econ.jsonは自動更新）
2. **何を読むか決めるとき**：デスクトップの **研究ダッシュボード.app** をダブルクリック
3. **ダッシュボード上でできること**：ステータス変更（ピルをクリックで未読→読書中→読了）・★・
   「AI生成」「AI要約」（その場で生成・表示）・「PDF」（Chromeで開く）・「× 消す」（非表示化）・
   「🚀 公開」（下書きがある論文を機械整形して本番ブログへ）
4. **メモ**：Obsidianで `notes/papers/` に1論文1ファイル（テンプレ: `notes/templates/文献メモ.md`）。研究アイデアは `notes/ideas/`
5. **記事にする**：メモを `blog/posts/<スラッグ>/index.qmd` に清書

## 論文→ブログの動線（メインの使い方）

1. ダッシュボードでタグ（理論/構造推定/因果推論/Health）や検索で論文を選ぶ
2. その論文の「**✍ 下書き**」をクリック → Obsidianが開き、
   `notes/blog-drafts/<タグ>/<citekey>.md` に下書きが自動生成される
   （論文情報入りの雛形。見出し: 一言でいうと／面白かったポイント／自分の考え）
3. Obsidianで自由に書く
4. Claudeに「**書いた**」と言う → Claudeが下書きを読み、
   `blog/posts/<citekey>/index.qmd` に整形（タイトル・説明・カテゴリ付与）→
   プレビュー確認 → `quarto publish gh-pages` で公開

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
