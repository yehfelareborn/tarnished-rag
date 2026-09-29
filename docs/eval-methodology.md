# 評分方法論：LLM as judge

狀態：**現況記錄＋規劃**（2026-09-29）。這篇談「答案正確與否怎麼判」這件事本身，不是某一次跑的結果（那些在 `docs/local_run.md`、`docs/run_haiku.md`）。

## 現況（S1～S2）

計畫書原本規定答案正確與否由人工判定（`eval/run_eval.py` 的 docstring 仍這樣寫）。實際兩次基準線跑下來，判定都是 AI 做的：

- **Qwen 基準線**：`eval/draft_judgment.py` 用字詞重疊自動初判，我事後稽核並改正了 1 題誤判（q08）。
- **Haiku 基準線**：我逐題對照標準答案判定，`vector_baseline_anthropic_judgments.json` 明白標「非人工」。

兩份文件都已經寫明「非人工判定」，`local_run.md` 的「判定的可信度」一節記錄了目前發現的問題（q08 判錯、q101 偏鬆、拒答旗標偵測不到位）。這是**單一 AI 判官**、樣本數小（106 題）、目前只有我自己稽核過幾類題型，還沒有跟獨立的第二個判官或人工比對過。

## 規劃：雙模型交叉驗證＋人工仲裁

S6 對照實驗開始後，判定方式改成：

1. **兩個當代最強的模型各自獨立判定**（判定時互相看不到對方的結果，避免互相影響）。
2. **兩者判定一致**的題，採用該判定。
3. **兩者不一致**的題，交由人工判定，人工的結果為準。
4. 具體選哪兩個模型視屆時可用的資源決定，這裡先不寫死；判定的 prompt、輸入輸出格式要跟現有的 `correct`／`partial`／`wrong` 三檔一致，才能沿用 `run_eval.py score`。
5. 每次判定都要留下：兩個模型各自的判定與理由、是否一致、若交人工則人工的判定與理由——這樣才能回頭算「模型判官與人工的一致率」，而不是只有最終分數。

這解決的是「單一 AI 判官」的問題，但**兩個模型意見一致不等於判對**——下面 survey 的部分會講到這個限制，光靠雙模型不夠。

## Survey：現在業界／研究怎麼避免過度依賴 LLM as judge（2026-09）

### 已知的判官偏誤

LLM 判官有五種常見偏誤：位置偏誤、冗長偏誤（傾向給長答案較高分，即使短答案更準確）、自我偏好（判官偏好自己家族模型的輸出）、格式偏誤、校準漂移。其中**風格偏誤是最主要的**（各模型間 0.76–0.92），遠高於位置偏誤（≤ 0.04），但研究關注反而最少（[Judging the Judges](https://arxiv.org/pdf/2604.23178)）。

### 一致不等於準確——這點直接影響我們的雙模型設計

- 對 21 個判官、逾 50 萬筆判定的研究發現：**內部最一致的判官，反而常是準確率最低的那批**（[LLM-as-Judge 2026 指南](https://futureagi.com/blog/llm-as-judge-best-practices-2026/)）。
- **高判官間一致率常被當成「可以用 LLM 取代人工」的許可證，但在主觀評分上，判官彼此的一致率能到人類共識水準，實際卻只還原了 58–66% 的人類判斷**（[Are We on the Right Way to Assessing LLM-as-a-Judge?](https://arxiv.org/html/2512.16041v1)）。
- **多個判官的錯誤常是相關的**（同樣的訓練資料、同樣的盲點），九個判官實質上可能只有兩票的獨立資訊量（[Nine Judges, Two Effective Votes](https://arxiv.org/html/2605.29800)）。這對我們的規劃是個提醒：**兩個模型同時判對，不代表答案真的對，只代表它們沒有踩到同一個盲點**；「兩者一致就採用」這個規則本身有機率把同一種系統性錯誤放過去。

### 變動性（variance）：同一個判官跑多次，結果不會一樣——這是另一個問題，不是偏誤

上面談的是「判官系統性地偏向什麼」（偏誤）；變動性談的是「同一個判官、同一筆輸入，這次跑跟下次跑給的分數就不一樣」，兩者要分開處理：

- **低溫也不保證一致**：LLM 判官在各種生成任務與指標上都有低自我一致性的問題——同一個判官、相同輸入，預設溫度下不一定每次都給同一個判定（[Rating Roulette](https://arxiv.org/html/2510.27106v1)）。
- **硬把溫度設成 0 想換取一致性，反而可能讓判斷品質變差**：兩個受測模型在不加抽樣時的表現都會下降，「判官自身的可靠度」與「判斷品質」之間的取捨沒有那麼簡單（同上）。
- **緩解做法是重複抽樣＋多數決／平均，而不是硬求確定性**：同一題讓判官跑多次，取多數決或分數平均，比單跑一次的期望準確率更高；某些模型多數決後的平衡準確率甚至超過單次跑的最高準確率（同上）。
- **但多數決只能修變動性，修不了偏誤**：抽樣間的誤差如果夠不相關，投票能收斂到正確答案；但如果每次抽樣都共享同一個系統性偏誤（例如冗長偏誤），投票再多次也沒用。這跟前面「兩個模型錯誤相關」的提醒是同一類限制——**投票／多判官能處理的是隨機噪音，處理不了系統性的盲點**。

### 結構化評分與「有標準答案可對照」能從源頭降低變動性

- **結構化輸出比自由格式的整體評分變動性更小**：要求判官輸出帶數字分數與理由的 JSON，而不是一段自由文字的整體評語，本身就能降低變動性（[LLM-as-judge 完整指南](https://www.openlayer.com/blog/llm-as-judge-evaluation-guide)）。
- **把整體判斷拆成細項準則（rubric）**，比要求判官把所有維度揉進一個分數更穩定；G-Eval 的做法是先讓判官生成一串思考步驟（chain-of-thought），再依步驟逐項判斷才給分（[Rubric-Based LLM Evaluation Guide](https://qaskills.sh/blog/rubric-based-llm-evaluation-guide-2026)）。
- **有參考答案可對照（reference-guided）的評分，天生比開放式的整體品質評分變動性小**——這點對我們有利：我們的判定本來就是拿模型答案跟 `questions.jsonl` 的標準答案對照，屬於 reference-guided 而非開放式評「哪個回答比較好」，這類任務的判官一致性研究普遍認為比 pairwise 或整體品質評分更穩定。

### 業界作法：陪審團（panel/jury）與「不一致就是訊號」

- 多個中小型判官組成的陪審團（例如三個不同家族的模型），在六個資料集上打贏單一大型判官，且成本只要約七分之一（[Weak judges, strong panel](https://orq.ai/blog/llm-juries-in-practice)）。
- **陪審團不一致不是雜訊，是訊號**：判官意見分歧的案例，往往正是真正模稜兩可、值得人工看的案例（[LLM-as-a-jury](https://docs.evidentlyai.com/examples/LLM_jury)）。這與我們「不一致才交人工」的規劃方向一致，有研究支持。

### 校準與稽核的具體做法

- **先量人與人之間的一致率，再談模型與人的一致率**：如果人工判官彼此都常常意見不同，這就是任何自動判官能達到的上限，不該期待模型比人類彼此還一致（相關綜述見 [LLM-as-a-Judge vs. Human Evaluation](https://www.koji.so/docs/llm-as-a-judge-vs-human-evaluation)）。
- **定期用人工樣本校準**：建議每季（也有文章建議每月）抽一批樣本，由人工覆核判官的分數，追蹤判官與人類的一致率、分類不一致的原因；換判官模型要當成整套評分的遷移來處理，不是換個設定就好（[LLM-as-Judge Best Practices in 2026](https://futureagi.com/blog/llm-as-judge-best-practices-2026/)）。

## 這對我們專案的意思

**已經在做的**：
- 明確標註「非人工判定」，不假裝是人工結果。
- 抽稽核找到並改正誤判（q08）——這就是最小規模的人工校準。
- 每次判定都留下理由（`draft_note`、`judged_by`），可回頭追。

**規劃裡還缺的、要補上的（根據上面的 survey）**：
1. **「兩者一致就採用」不能是終點**：要另外抽一小批**兩個模型都判 correct**的題做人工抽查，因為相關錯誤可能讓兩個模型一起錯過同一種問題（我們在稽核 Qwen 結果時就是這樣抓到 q08 的：自動初判是 correct，人工複核才發現錯）。
2. **定期校準，不是只在 S6 做一次**：之後每輪新的基準線或新版本的圖／檢索，都該抽樣校準一次，而不是假設判官品質固定不變。
3. **判定要記理由，且理由本身也要抽查**：不只記 correct/partial/wrong，連「為什麼」也要能回頭稽核，現有的 `draft_note`／`judged_by` 欄位已經是這個方向，往兩個模型擴充時格式要保留這個習慣。
4. **注意冗長與風格偏誤**：這個題庫的標準答案多半簡短（一到兩句），要留意判官會不會因為某個模型的回答風格更像「教科書式」而給分偏高，這點目前沒有量過。
5. **目前每題只判一次，沒有處理變動性**：現有的判定（無論是 `draft_judgment.py` 的字詞重疊初判，還是 Claude 逐題判定）都是單次跑，同一題重跑一次判官會不會給出不同結果，完全沒測過。雙模型規劃解決的是「單一判官」這件事，不等於解決「同一個判官本身不穩定」這件事——嚴格說，雙模型交叉驗證要處理變動性，理想上每個模型也該對同一題判個兩三次取多數決，再跟另一個模型比對；目前的規劃只做到「兩個不同模型各判一次」，這是成本與嚴謹度之間的取捨，先寫進待決定
6. **我們的判定屬於 reference-guided，起點比開放式評分穩**：因為判官是拿答案跟標準答案對照，不是要判「哪個回答比較好」，這類任務理論上變動性天生較小；但沒有實測驗證這個假設在我們的題庫上成立

## 待決定

- 兩個判官模型具體選哪兩個（S6 開工前再定，取決於屆時可用的模型與預算）。
- 不一致送人工的流程：是每題都送，還是先看不一致的題型分布再決定人力怎麼分配。
- 要不要在「兩者一致」的題裡也抽一定比例做人工複查（上面第 1 點），以及抽多少比例。
- 是否需要對判官做位置輪替（這裡多數題型答案結構固定，不是成對比較，位置偏誤的影響可能比一般 pairwise 評測小，需要時再驗證）。
- 要不要對同一題重複抽樣判官（例如各判 3 次取多數決）以處理變動性，還是接受「兩模型各判一次」的簡化版；如果題庫規模擴大，重複抽樣的成本會跟著倍增，要考慮值不值得。
- 判定要不要改成結構化輸出（帶理由的 JSON，逐項準則而非整體判斷），現有的 `judgment` + `draft_note`／`judged_by` 已經有部分結構，但沒有拆成準則子項。

Sources: [LLM-as-Judge Best Practices in 2026](https://futureagi.com/blog/llm-as-judge-best-practices-2026/) · [Judging the Judges: bias mitigation](https://arxiv.org/pdf/2604.23178) · [Are We on the Right Way to Assessing LLM-as-a-Judge?](https://arxiv.org/html/2512.16041v1) · [Nine Judges, Two Effective Votes](https://arxiv.org/html/2605.29800) · [Weak judges, strong panel](https://orq.ai/blog/llm-juries-in-practice) · [LLM-as-a-jury](https://docs.evidentlyai.com/examples/LLM_jury) · [LLM-as-a-Judge vs. Human Evaluation](https://www.koji.so/docs/llm-as-a-judge-vs-human-evaluation) · [Rating Roulette: Self-Inconsistency in LLM-As-A-Judge](https://arxiv.org/html/2510.27106v1) · [LLM-as-judge evaluation guide](https://www.openlayer.com/blog/llm-as-judge-evaluation-guide) · [Rubric-Based LLM Evaluation Guide (G-Eval)](https://qaskills.sh/blog/rubric-based-llm-evaluation-guide-2026)
