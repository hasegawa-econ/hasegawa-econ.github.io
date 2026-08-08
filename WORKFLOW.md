# 研究ワークスペースの使い方

このリポジトリは「研究のワークスペース」。ブログはその出力の一つ。

```
Safari/Chrome ──保存──▶ Zotero ──自動──▶ dashboard/library.json
                                              │
                デスクトップの「研究ダッシュボード.command」で閲覧
                                              │
                        読む論文を pick ──▶ notes/ にメモ（Obsidian）
                                              │
                        公開したいものだけ ──▶ blog/posts/ に清書 ──▶ デプロイ
```

## 日々の動線

1. **論文を見つけたら**：ブラウザのZoteroコネクタで保存し、タグ `to-read` を付ける
2. **何を読むか決めるとき**：デスクトップの **研究ダッシュボード.command** をダブルクリック
   （ブログのローカルプレビューが立ち上がり、ダッシュボードが開く）
3. **読み始めたら**：Zotero側でタグを `reading` に、読了したら `done` に変える
4. **メモ**：Obsidianで `notes/papers/` に1論文1ファイル（テンプレ: `notes/templates/文献メモ.md`）
   研究アイデアは `notes/ideas/` に
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
| `dashboard/library.json`（Zotero読書リスト） | ❌ gitignore済み・ビルドにも入らない |
| `notes/`（メモ・研究アイデア） | ❌ gitignore済み |

- 公開ビルド = `_quarto-public.yml`（デフォルト）、ローカル閲覧 = `_quarto-local.yml`
- ローカルプレビューを手動で起動する場合: `quarto preview --profile local`

## 記事の書き方メモ

- コードは ```` ```python ````（表示のみ）で書く。実行結果込みの記事
  （```` ```{python} ````）を書きたくなったら、先にPython環境へ
  `jupyter` 一式を入れること（今は未導入なのでビルドが失敗する）
