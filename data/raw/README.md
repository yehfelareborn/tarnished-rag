# data/raw：原始資料與來源

This directory holds the unmodified source datasets. Both are released under **CC0 1.0 (public domain)** on Kaggle; their content was compiled by the uploaders from the Fextralife Elden Ring Wiki. Please credit the original uploaders.

本目錄放的是**未經修改**的原始資料。清理後的版本在 `data/processed/`，清理過程與每一項修正記錄在 `src/ingest/clean_raw.py` 與 `docs/data-sources.md`、`docs/note.md`。

## `dlc_scrape/`

| 項目 | 內容 |
|---|---|
| 資料集 | Ultimate Elden Ring with Shadow of The Erdtree DLC |
| 作者 | pedro altobelli（Kaggle: `pedroaltobelli`）|
| 連結 | https://www.kaggle.com/datasets/pedroaltobelli/ultimate-elden-ring-with-shadow-of-the-erdtree-dlc |
| 授權 | CC0: Public Domain |
| 原始出處 | 作者自述整理自 [Fextralife Elden Ring Wiki](https://eldenring.wiki.fextralife.com/) |
| 資料集最後更新 | 2024-07-16 |
| 取得日期 | 2026-09-28 |
| 內容 | armors、weapons、shields、talismans、sorceries、incantations、ashesOfWar、skills、spiritAshes、bosses、creatures、npcs、locations，`items/` 下 13 個子類，以及武器／盾牌強化數值表；每個檔案有 `dlc` 欄位（0／1）標記是否為 Shadow of the Erdtree 內容 |

## `boss_stats/`

| 項目 | 內容 |
|---|---|
| 資料集 | Elden Ring Ultimate Boss Dataset（v2）|
| 作者 | Vaibhav dhariwal 11（Kaggle: `vaibhavdhariwal11`）|
| 連結 | https://www.kaggle.com/datasets/vaibhavdhariwal11/elden-ring-ultimate-boss-dataset |
| 授權 | CC0: Public Domain |
| 原始出處 | 作者自述整理自 Fextralife Elden Ring Wiki |
| 資料集最後更新 | 2025-12-15 |
| 取得日期 | 2026-09-28 |
| 內容 | `elden_ring_boss_stats_clean.csv`（142 筆 boss 的分階段血量、傷害減免、異常狀態抗性、韌性等）；`SOURCE_README.md` 是作者原本的說明文件 |

## 已知的資料品質問題

原始資料有不少欄位問題（`dlc` 編碼不一致、CSV 欄位錯位、佔位字串、欄位互相污染等），逐項記錄在 `docs/data-sources.md`。所以**請不要直接把這裡的檔案當成乾淨資料使用**。

## 聲明

《艾爾登法環》（Elden Ring）與相關名稱、內容的著作權屬於 FromSoftware, Inc. 與 Bandai Namco Entertainment Inc.。本專案為教育／作品集用途，非商業使用，與上述公司沒有任何關聯。
