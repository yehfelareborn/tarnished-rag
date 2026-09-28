# tarnished-rag

Elden Ring GraphRAG 專案。回答《艾爾登法環》問題的 RAG 助手，主軸為向量檢索 + LLM 生成，差異集中在用知識圖譜處理關係、數值與多跳問題。
claude --resume 6f510b06-b91f-4e3b-a0c5-3910258aa67b
詳細計畫見 [`elden-ring-graphrag-plan (1).md`](./elden-ring-graphrag-plan%20%281%29.md)。

## 里程碑

S0 資料盤點 → S1 評估題庫 → S2 向量基準線 → S3 知識圖譜 → S4 圖檢索工具 → S5 整合 → S6 對照實驗 → S7 README／發表

## 結構

```
data/    原始與處理後資料
eval/    題庫、評分腳本、結果
src/     ingest / vector / graph / agent / app
docs/    資料來源、圖譜 schema、實驗紀錄
```
