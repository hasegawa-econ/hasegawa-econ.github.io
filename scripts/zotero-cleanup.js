// ============================================================
// Zotero 整理スクリプト — コレクション5個＋統制タグ体制へ
// 使い方: Zotero > ツール > 開発者 > Run JavaScript を開き、
//         「非同期関数として実行 (Run as async function)」に
//         チェックを入れて、全文貼り付けて Run。
//
// まず DRY_RUN = true のまま実行して計画を確認 → 問題なければ
// false に変えてもう一度実行（本実行）。
//
// やること:
//   1. サブコレクション所属 → 対応する統制タグに変換
//   2. アイテムを親の大分類（Empirical/Theory）に移す
//   3. 空になったサブコレクションを削除
//   4. タグのタイポ・重複を統制タグに正規化
//   5. コレクション名 "Emprical" → "Empirical" に修正
// ============================================================

const DRY_RUN = true;   // ← 確認が済んだら false にして本実行

// 統制タグは4本: 理論・構造推定・因果推論・Health
// 機械判定できないものは元のタグのまま残す（目視で仕分けする方針）

// サブコレクション名 → タグ（確実なものだけ変換。それ以外は元の名前をタグ化して保存）
const COLL_TO_TAG = {
  "因果推論": "因果推論",
  "ベイズ-A/B": "因果推論",
  "構造推定": "構造推定",
  // ↑以外のサブコレクションは、元の名前がそのままタグになる（情報は失わない）
};

// 旧タグ → 修正（タイポ吸収と確定分のみ。スコア・ナラティブ等はそのまま残す）
const TAG_MAP = {
  "Cousal": "因果推論", "Causal": "因果推論", "ABテスト": "因果推論",
  "Information": "情報設計", "Infromation": "情報設計",
  "Informaiton": "情報設計", "Inforamtion": "情報設計", "情報": "情報設計",
  "アリゴリズム": "アルゴリズム",
};

// Theoryツリー（直下＋サブ）の論文には「理論」タグを付ける
const THEORY_TAG = "理論";

const TOP_NAMES = new Set(["Emprical", "Empirical", "Theory", "おもしろ", "その他", "読み物"]);

const libID = Zotero.Libraries.userLibraryID;
const colls = Zotero.Collections.getByLibrary(libID, true);
const byID = {};
for (const c of colls) byID[c.id] = c;

const log = [];

// --- 1〜3: サブコレクションの解散 ---
// 対応表にあるものは統制タグへ、ないものは元の名前をタグとして保存（情報を失わない）
for (const c of colls) {
  if (!c.parentID) continue;                    // トップは対象外
  const parent = byID[c.parentID];
  if (!parent || !TOP_NAMES.has(parent.name)) continue;
  const tag = COLL_TO_TAG[c.name] || c.name;
  const items = c.getChildItems(false);
  log.push(`[サブ解散] ${parent.name}/${c.name} (${items.length}件) → タグ「${tag}」`);
  if (!DRY_RUN) {
    for (const item of items) {
      item.addTag(tag);
      item.addToCollection(parent.id);
      item.removeFromCollection(c.id);
      await item.saveTx();
    }
    await c.eraseTx();
  }
}

// --- Theoryツリー（直下＋サブ）に「理論」タグ ---
for (const c of colls) {
  const isTheoryTop = !c.parentID && c.name === "Theory";
  const isTheorySub = c.parentID && byID[c.parentID] && byID[c.parentID].name === "Theory";
  if (!isTheoryTop && !isTheorySub) continue;
  const items = c.getChildItems(false);
  log.push(`[理論タグ] ${c.name} (${items.length}件) に「${THEORY_TAG}」`);
  if (!DRY_RUN) {
    for (const item of items) {
      item.addTag(THEORY_TAG);
      await item.saveTx();
    }
  }
}

// --- 4: タグ正規化（全アイテム）---
const search = new Zotero.Search();
search.libraryID = libID;
search.addCondition("itemType", "isNot", "attachment");
const ids = await search.search();
let fixed = 0;
for (const id of ids) {
  const item = await Zotero.Items.getAsync(id);
  if (item.isNote() || item.isAttachment()) continue;
  let changed = false;
  for (const t of item.getTags().map((x) => x.tag)) {
    const to = TAG_MAP[t];
    if (to && to !== t) {
      log.push(`[タグ修正] ${item.getField("title").slice(0, 40)}…: ${t} → ${to}`);
      if (!DRY_RUN) {
        item.removeTag(t);
        item.addTag(to);
        changed = true;
      }
      fixed++;
    }
  }
  if (changed) await item.saveTx();
}

// --- 5: Emprical → Empirical ---
for (const c of colls) {
  if (c.name === "Emprical" && !c.parentID) {
    log.push("[改名] Emprical → Empirical");
    if (!DRY_RUN) {
      c.name = "Empirical";
      await c.saveTx();
    }
  }
}

return (DRY_RUN ? "★ DRY RUN（まだ何も変えていません）\n\n" : "★ 実行完了\n\n") +
  log.join("\n") + `\n\nタグ修正: ${fixed}件`;
