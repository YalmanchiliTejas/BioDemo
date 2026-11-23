# Can token-based LLMs natively represent and reason over numeric, time-series, tabular and process data? Evidence for and against (as of 19 Nov 2026)

Reading guide

- Thesis under test: "general LLMs + more data + complex harnesses are NOT enough for pharmaceutical manufacturing; vertical foundation models with native (non-text-token) representations will win on accuracy, representation and control."
- Each item is tagged **[SUPPORTS]**, **[UNDERMINES]** or **[MIXED]** relative to that thesis.
- **(2026)** marks the most recent work.
- Verification method: every paper below was opened in this session (arXiv abstract page, arXiv HTML full text, PMC full text, or a search result pointing at the primary source). Numbers come from the abstract unless marked "full text". Full-text numbers were pulled by an automated reader from arXiv HTML and should be spot-checked against the PDF tables before being quoted externally. Where a paper's own text and tables disagree, that is stated.
- Process limitation: the session's web-search budget ran out part-way through. After that, only direct fetches of known primary-source URLs were possible, so several sub-topics have thinner coverage than intended (see each Gaps list).

---

## 1. Number representation: how tokenization affects numeric reasoning and regression, and how much the fixes help

### Takeaway
Standard subword tokenization measurably damages numeric competence (accuracy collapses with digit length, errors are digit-wise rather than magnitude-wise), and purpose-built number encodings fix specific tasks cheaply. But the fixes are not uniformly "non-token": continuous encodings such as xVal win on some regression tasks and lose badly on exact-value tasks, while digit-level tokens with a better loss or positional scheme often do as well or better.

### Cited Findings

**xVal: A Continuous Numerical Tokenization for Scientific Language Models** — Golkar et al., 2023, NeurIPS 2023 ML for Physical Sciences workshop. [arXiv:2310.02989](https://arxiv.org/abs/2310.02989) **[MIXED]**
- Setup: transformers trained from scratch on arithmetic, ERA5 temperature forecasting and simulated planetary orbits; a single `[NUM]` token scaled by the value is compared with text encodings P10, P1000, B1999, FP15.
- Full text: ERA5 next-step MSE is 4.11e-3 to 4.29e-3 for xVal versus 4.54e-3 (FP15), 5.20e-2 (P1000) and 1.73e-1 (P10). Sequence length is about 1,800 tokens versus 5,000 to 8,000 for the P10 and P1000 text encodings. Training runtime is 9 h versus 19 h to 2 d 22 h at equal samples. — [full text](https://arxiv.org/html/2310.02989v2)
- Full text: out-of-distribution orbit prediction (semi-major axis) MSE is 1.6e-4 for xVal versus 4.07e-3 to 1.18e-2 for text encodings.
- Against the thesis, same paper: on 3-, 4- and 5-digit multiplication a text encoding (B1999) scores highest (R² 0.9998 / 0.9984 / 0.9997 versus xVal 0.9986 / 0.9975 / 0.9958). On exact number lookup xVal recovers 3 significant figures only 6% of the time versus 99.9% for FP15. xVal "performs uncharacteristically poorly" on planetary-mass prediction.

**Regress, Don't Guess — A Regression-like Loss on Number Tokens for Language Models** — Zausinger et al., 2024/2025, ICML 2025. [arXiv:2411.02083](https://arxiv.org/abs/2411.02083) **[MIXED, leans UNDERMINES]**
- Setup: adds a Number Token Loss (L_p or Wasserstein distance over digit tokens) to ordinary token models; T5 on the DeepMind mathematics dataset, rJokes regression, GSM8k.
- Full text: interpolation accuracy 0.64 (cross-entropy) rises to 0.75 (NTL-WAS); extrapolation 0.367 rises to 0.432. In this comparison xVal scores 0.10 (interpolation) and 0.058 (extrapolation). — [full text](https://arxiv.org/html/2411.02083v3)
- Full text: on rJokes regression NTL reaches RMSE 1.81 versus 1.82 for a dedicated regression head and 2.01 for cross-entropy. T5-3B on GSM8k improves from 13.5% to 17.7%.
- Implication: a loss change on ordinary digit tokens matches a native regression head, with no architecture change.

**FoNE: Precise Single-Token Number Embeddings via Fourier Features** — Zhou et al., 2025 (v2 revised April 2026), arXiv preprint. [arXiv:2502.09741](https://arxiv.org/abs/2502.09741) **[SUPPORTS]**
- Setup: each number becomes one token with two embedding dimensions per digit; tested on decimal addition, subtraction, multiplication.
- Result: on 6-digit decimal addition FoNE needs 64x less data to reach 99% accuracy than subword and digit-wise embeddings, using 3x and 6x fewer tokens per number. The abstract states it is the only method reaching 100% accuracy on over 100,000 test examples.

**Number Cookbook: Number Understanding of Language Models and How to Improve It** — Yang et al., 2024, ICLR 2025. [arXiv:2411.03766](https://arxiv.org/abs/2411.03766) **[SUPPORTS]**
- Setup: NUPA benchmark with 4 number representations, 17 tasks, 41 task combinations; tests GPT-4o, GPT-4o-mini, Llama, Qwen, Mixtral.
- Full text: GPT-4o integer addition is about 100% for short numbers, about 80% medium, about 40% long, about 15% extra-long. Float addition falls 90% → 60% → 15% → under 5%. Fractions and scientific notation average below 20% even for 1 to 4 digits. — [full text](https://arxiv.org/html/2411.03766v3)
- Full text: one-digit tokenizers beat three-digit tokenizers; a fine-tuned Llama-3.1-8B matches or beats GPT-4o on several tasks; rule-following chain-of-thought reaches 1.00 versus GPT-4o's 0.78 on 5-digit float addition but is about 17x slower.
- Full text: retrofitting new tokenizers or positional encodings onto an already-trained model caused substantial performance drops, which favours training from scratch over patching a general model.

**Exposing Numeracy Gaps: A Benchmark to Evaluate Fundamental Numerical Abilities in Large Language Models (NumericBench)** — Li et al., 2025, Findings of ACL 2025. [arXiv:2502.11075](https://arxiv.org/abs/2502.11075) **[MIXED]**
- Setup: number recognition, arithmetic, contextual retrieval, comparison, summary and logic over number lists, stock and weather series; 8-way choice, random baseline 12.5%.
- Full text: GPT-4o scores 41.7 / 37.5 / 48.8 on retrieval (number / stock / weather) and 11.6 on number-list summary, below random. Llama-3.1-405B scores 14.8 on stock comparison. Humans score 100 on all tasks except logic (52.6). — [full text](https://arxiv.org/html/2502.11075v2)
- Against the thesis, same table: reasoning models are far better. o3-mini scores 96.8 / 68.6 / 78.1 on retrieval and DeepSeek-R1 scores 93.6 on weather retrieval and 98.8 on weather comparison. The gap to non-reasoning models is 30 to 60 points, though both remain well short of human 100.

**Tokenization counts: the impact of tokenization on arithmetic in frontier LLMs** — Singh and Strouse, 2024, arXiv preprint. [arXiv:2402.14903](https://arxiv.org/abs/2402.14903) **[MIXED]**
- Setup: GPT-3.5 and GPT-4 arithmetic with left-to-right versus right-to-left 3-digit tokenization (enforced with commas).
- Result (qualitative in abstract): right-to-left tokenization gives "largely improved performance"; errors follow stereotyped patterns; the gap shrinks as models scale, "possibly indicating that larger models are better able to override this tokenization-dependent inductive bias."

**Transformers Can Do Arithmetic with the Right Embeddings (Abacus embeddings)** — McLeish et al., 2024, arXiv preprint. [arXiv:2405.17399](https://arxiv.org/abs/2405.17399) **[SUPPORTS]**
- Setup: adds a per-digit positional embedding; trains on up to 20-digit numbers on one GPU for one day.
- Result: up to 99% accuracy on 100-digit addition. Shows the failure is representational and fixable, but by changing the architecture, not by prompting.

**Faith and Fate: Limits of Transformers on Compositionality** — Dziri et al., 2023, arXiv preprint. [arXiv:2305.18654](https://arxiv.org/abs/2305.18654) **[SUPPORTS]**
- Setup: multi-digit multiplication, logic puzzles and dynamic programming framed as computation graphs.
- Full text: "off-the-shelf ChatGPT and GPT4 achieve only 55% and 59% accuracies" on 3-digit by 3-digit multiplication. Fine-tuning is near perfect in-distribution and declines sharply out-of-distribution (exact values are in figures only). — [full text](https://arxiv.org/html/2305.18654v3)

**Language Models Encode Numbers Using Digit Representations in Base 10** — Levy and Geva, 2024, NAACL 2025. [arXiv:2410.11781](https://arxiv.org/abs/2410.11781) **[SUPPORTS]**
- Probing and causal interventions show LLMs hold numbers as per-digit circular representations, not as a magnitude. Errors scatter across digits instead of landing near the true value. No headline number in the abstract.

**Arithmetic Without Algorithms: Language Models Solve Math With a Bag of Heuristics** — Nikankin et al., 2024, arXiv preprint (v2 May 2025). [arXiv:2410.21272](https://arxiv.org/abs/2410.21272) **[SUPPORTS]**
- Circuit analysis finds a sparse set of neurons implementing pattern-matching heuristics; their unordered combination explains most arithmetic accuracy. No headline number in the abstract.

**Pre-trained Large Language Models Use Fourier Features to Compute Addition** — Zhou et al., 2024, arXiv preprint. [arXiv:2406.03445](https://arxiv.org/abs/2406.03445) **[MIXED]**
- Pre-trained models represent numbers with sparse frequency-domain features; models trained from scratch use only low-frequency features and are less accurate. Adding pre-trained token embeddings to a randomly initialised model restores performance. This is evidence that language pre-training contributes useful numeric structure.

### Inferences
- The measured failure is specific: digit-wise internal representation plus length-dependent decay. For a regulated process setting this means a general LLM reading raw sensor values as text can be wrong in a high-order digit, which is a qualitatively worse error than a small regression residual.
- "Native, non-text-token" is too coarse a framing. The evidence splits three ways: continuous embeddings (xVal) help smooth regression and cut sequence length 3x to 4x; digit tokens with a better loss (NTL) match a regression head; single-token Fourier embeddings (FoNE) fix exact arithmetic. A vertical model would more defensibly claim "number-aware encoding and loss, trained on domain data" than "no tokens".
- Reasoning-mode models narrow the numeracy gap substantially (NumericBench), so tests run on GPT-4o-era models overstate the deficit for late-2025 and 2026 frontier models.

### Gaps
- I could not locate a paper with the exact title "Language Models (Mostly) Do Not Know Numbers". The closest verified works are Number Cookbook, NumericBench, Levy and Geva, and Nikankin et al.
- No verified 2026 numeracy benchmark covering the newest frontier models (GPT-5-class, Claude 4.x, Gemini 3) was found before the search budget ran out. NumericBench omitted Claude, Gemini and o1 for cost reasons.
- No study was found that tests number encodings on real manufacturing sensor or assay data; all evidence is arithmetic, weather, orbits, or generic regression.

---

## 2. Time series: LLMs as forecasters, anomaly detectors and reasoners

### Takeaway
The strongest controlled evidence says the language-model component adds nothing to forecasting accuracy (ablations win in 19 to 26 of 26 cases at a fraction of the cost), and LLM anomaly detection trails deep-learning baselines by about 30%. The counter-evidence is that zero-shot LLMs are surprisingly competitive on small univariate series, and that giving an LLM code access raises time-series reasoning accuracy, though the best agents still miss 22% to 34% of questions.

### Cited Findings

**Are Language Models Actually Useful for Time Series Forecasting?** — Tan et al., 2024, NeurIPS 2024 Spotlight. [arXiv:2406.16964](https://arxiv.org/abs/2406.16964) **[SUPPORTS]**
- Setup: ablates Time-LLM, OneFitsAll (GPT4TS) and CALF by removing the LLM or replacing it with one attention or transformer layer; 13 datasets, MAE and MSE.
- Full text: ablations beat the original in 26/26 cases for Time-LLM, 22/26 for CALF, 19/26 for OneFitsAll. — [full text](https://arxiv.org/html/2406.16964v2)
- Full text: Time-LLM has 6,651.82M parameters versus 0.55M for the ablation. Training on Weather takes 3,003 min versus 1.91 to 2.38 min. Inference is 28.2x slower on average.
- Full text: randomly initialised LLM weights plus fine-tuning won 8 of 16 cases versus 3 for pretrained plus fine-tuning. A patching plus one-layer-attention encoder ("PAttn") was best or second best 34 times versus 33 for LLM methods.
- Caveat: the paper's few-shot (10% data) text and tables disagree slightly (text says ablations win "12 out of 14" for CALF; the table shows the LLM winning 2 of 14).

**Large Language Models Are Zero-Shot Time Series Forecasters (LLMTime)** — Gruver et al., 2023, NeurIPS 2023. [arXiv:2310.07820](https://arxiv.org/abs/2310.07820) **[UNDERMINES, with caveats that SUPPORT]**
- Setup: encodes series as digit strings (spaces between digits for GPT-3); GPT-3 and LLaMA-2 zero-shot on Darts (8 datasets), Monash (19 evaluated), Informer (5).
- Result: zero-shot forecasts "comparable to or exceeding" purpose-built models trained on the target data; full text says LLMTime ranks best or second best in aggregate MAE on all benchmarks considered and handles missing values as text without imputation. — [full text](https://arxiv.org/html/2310.07820v3)
- Supporting the thesis, same paper: GPT-4 performs worse than GPT-3 "because of how it tokenizes numbers, and poor uncertainty calibration, which is likely the result of alignment interventions such as RLHF." Only about 300 Darts observations fit in context; multivariate series are handled one covariate at a time.

**Time-LLM: Time Series Forecasting by Reprogramming Large Language Models** — Jin et al., 2023, ICLR 2024. [arXiv:2310.01728](https://arxiv.org/abs/2310.01728) **[UNDERMINES as claimed; rebutted by Tan et al.]**
- Claims a frozen LLM with reprogrammed patch inputs outperforms specialised forecasters and excels in few-shot and zero-shot settings. No numbers in the abstract.

**One Fits All: Power General Time Series Analysis by Pretrained LM (GPT4TS / FPT)** — Zhou et al., 2023, NeurIPS 2023 Spotlight. [arXiv:2302.11939](https://arxiv.org/abs/2302.11939) **[UNDERMINES as claimed; rebutted by Tan et al.]**
- Claims a frozen pretrained GPT-2 backbone reaches comparable or state-of-the-art results on classification, anomaly detection, forecasting and few-shot tasks. No numbers in the abstract.

**Large language models can be zero-shot anomaly detectors for time series? (SigLLM)** — Alnegheimish et al., 2024, IEEE DSAA 2024. [arXiv:2405.14755](https://arxiv.org/abs/2405.14755) **[SUPPORTS]**
- Setup: prompt-based and forecast-based LLM detection across 11 datasets and 10 pipelines.
- Result: the forecasting method beat the prompting method on all 11 datasets; state-of-the-art deep learning models remain "30% better than large language models."

**Can LLMs Understand Time Series Anomalies?** — Zhou and Yu, 2024, arXiv (v3 March 2025). [arXiv:2410.05440](https://arxiv.org/abs/2410.05440) **[SUPPORTS]**
- Setup: GPT-4o-mini, Gemini-1.5-Flash, Qwen-VL-Chat, InternVL2 on synthetic point, range, frequency and trend anomalies; 21 prompt variants per model.
- Result: LLMs understand series better as images than as text; explicit reasoning prompts do not help (performance drops with chain-of-thought for most models); behaviour varies widely across models. Conclusion: LLMs can find "trivial" anomalies, with "no evidence that they can understand more subtle real-world anomalies."
- Full text: impairing Gemini's arithmetic (5-digit addition from 100% to 12%) left anomaly detection largely unchanged, so the weakness is not explained by arithmetic alone. — [full text](https://arxiv.org/html/2410.05440v3)

**Language Models Still Struggle to Zero-shot Reason about Time Series** — Merrill et al., 2024, arXiv preprint. [arXiv:2404.11757](https://arxiv.org/abs/2404.11757) **[SUPPORTS]**
- Setup: etiological reasoning, question answering and context-aided forecasting over series in ten domains.
- Result: models score marginally above random on etiological and QA tasks, "up to 30 percentage points worse than humans"; only modest success using text context to improve forecasts.

**TimeSeriesExam: A time series understanding exam** — Cai et al., 2024, NeurIPS 2024 workshop. [arXiv:2410.14752](https://arxiv.org/abs/2410.14752) **[SUPPORTS]**
- Over 700 procedurally generated questions from 104 templates; 7 LLMs. Closed models handle simple concepts; all struggle with complex ones, especially causality analysis.

**Time Series Forecasting with LLMs: Understanding and Enhancing Model Capabilities** — Tang et al., 2024, SIGKDD Explorations. [arXiv:2402.10835](https://arxiv.org/abs/2402.10835) **[MIXED]**
- LLMs forecast well on series with clear trend and seasonality and struggle on series lacking periodicity. External knowledge and natural-language paraphrasing improve results. No numbers in the abstract.

**Context is Key: A Benchmark for Forecasting with Essential Textual Information** — Williams et al., 2024, ICML 2025. [arXiv:2410.18959](https://arxiv.org/abs/2410.18959) **[UNDERMINES]**
- Setup: forecasting tasks that cannot be solved without accompanying text; compares statistical models, time-series foundation models and LLM forecasters.
- Result: a simple LLM prompting method performs best on the benchmark, while the paper also documents LLM forecaster failure modes. No numbers in the abstract. Relevance: batch context (recipe changes, deviations, raw-material lots) is text, and numeric-only foundation models cannot use it.

**ChatTS: Aligning Time Series with LLMs via Synthetic Data for Enhanced Understanding and Reasoning** — Xie et al., 2024, VLDB 2025. [arXiv:2412.03104](https://arxiv.org/abs/2412.03104) **[SUPPORTS]**
- A multimodal LLM with a native time-series encoder (series treated as a modality, trained on synthetic data) improves 46.0% on alignment tasks and 25.8% on reasoning tasks over GPT-4o-style vision and text/agent baselines. Self-reported.

**Chronos: Learning the Language of Time Series** — Ansari et al., 2024, arXiv (TMLR per authors; venue not shown on the arXiv page). [arXiv:2403.07815](https://arxiv.org/abs/2403.07815) **[MIXED]**
- Setup: T5 models (20M to 710M parameters) trained from scratch on time series that are scaled and quantised into a fixed token vocabulary with cross-entropy loss; 42 datasets.
- Result: significantly outperforms other methods on in-corpus datasets and has comparable, occasionally superior, zero-shot performance on new datasets. Note that this specialised winner is itself token-based; what changed is the vocabulary and the training data, not the autoregressive token paradigm.

**A decoder-only foundation model for time-series forecasting (TimesFM)** — Das et al., 2023, arXiv (v4 April 2024). [arXiv:2310.10688](https://arxiv.org/abs/2310.10688) **[SUPPORTS]**
- Patched-decoder model pretrained on a time-series corpus; zero-shot accuracy "comes close to" supervised state of the art per dataset. No numbers in the abstract.

**Zero-shot forecasting of chaotic systems** — Zhang and Gilpin, 2024, ICLR 2025. [arXiv:2409.15771](https://arxiv.org/abs/2409.15771) **[SUPPORTS native time-series models]**
- 135 chaotic systems, 10^8 timepoints. Time-series foundation models are competitive with custom-trained NBEATS and TiDE, most clearly when training data is limited, and preserve attractor geometry after point forecasts fail. Mechanism identified: "context parroting".

**LLMs learn governing principles of dynamical systems, revealing an in-context neural scaling law** — Liu et al., 2024, EMNLP 2024. [arXiv:2402.00795](https://arxiv.org/abs/2402.00795) **[UNDERMINES]**
- LLaMA-2, trained mainly on text, predicts dynamical-system series without fine-tuning; accuracy of the learned rule improves with context length. No numbers in the abstract.

**Can LLM Coding Agents Reason About Time Series?** — Rechtorík et al., **(2026)**, arXiv preprint June 2026. [arXiv:2606.16545](https://arxiv.org/abs/2606.16545) **[MIXED]**
- Setup: gpt-oss-120b and qwen3-next-80b on TimeSeriesExam (746 questions) and TSFU (2,000 questions), with raw data, a Python tool, or both.
- Full text: gpt-oss-120b scores 65.3% (raw), 70.4% (code), 78.0% (both) on TimeSeriesExam and 55.6% / 63.0% / 65.6% on TSFU. qwen3-next-80b gets worse with code only (63.5% → 56.4%). — [full text](https://arxiv.org/html/2606.16545)
- Full text: direct models chose a wrong core strategy in 33% of answers versus 9% for coding agents. Coding agents "over-trust returned numbers"; 25% of code-agent answers used a wrong method within the right strategy. Code was worse than raw data on outliers (64.8% versus 74.0%) and anomaly detection (48.8% versus 54.8%).
- Discrepancy: the abstract says "up to 10%" gain; the table shows 12.7 points. The best agent is wrong on about 22% to 34% of questions.

**TimeSage-MT: A Multi-Turn Benchmark for Evaluating Agentic Time Series Reasoning** — Kong et al., **(2026)**, arXiv preprint May 2026. [arXiv:2606.01498](https://arxiv.org/abs/2606.01498) **[SUPPORTS]**
- Setup: 240 tasks, 2,680 dialogue turns, 8 real-world domains, code-enabled frontier models.
- Full text: six frontier models land in a 35 to 40 overall band (Claude Sonnet 4.6 and GLM-5.1 at 40, GPT-5.3-Codex at 39). Scores drop 10 to 15 points from level 1 to level 2 tasks (GPT-5.3-Codex 48 → 34). Code correctness is high; the stated core weaknesses are numerical accuracy and analytical grounding. — [full text](https://arxiv.org/html/2606.01498)

**TFRBench: A Reasoning Benchmark for Evaluating Forecasting Systems** — Ahamed et al., **(2026)**, arXiv preprint April 2026. [arXiv:2604.05364](https://arxiv.org/abs/2604.05364) **[MIXED]**
- Ten datasets, five domains. Off-the-shelf LLMs do poorly on both reasoning and numeric forecasting; supplying generated reasoning traces lifts forecasting accuracy from about 40.2% to 56.6% (metric not defined in the abstract).

**MMTS-BENCH: A Comprehensive Benchmark for Time Series Understanding and Reasoning** — Yin et al., **(2026)**, arXiv preprint February 2026. [arXiv:2602.08588](https://arxiv.org/abs/2602.08588) **[UNDERMINES]**
- 2,424 time-series QA pairs. Time-series-adapted LLMs trail general-purpose LLMs in cross-domain generalisation; backbone capability matters more than the time-series encoder design; chain-of-thought and multimodal input substantially help. No scores in the abstract.

**GIFT-Eval: A Benchmark For General Time Series Forecasting Model Evaluation** — Aksu et al., 2024, arXiv preprint. [arXiv:2410.10393](https://arxiv.org/abs/2410.10393) **[context]**
- 23 datasets, over 144,000 series, 177 million points, 17 baselines. This is the leaderboard used in the agentic counter-example in section 5.

### Inferences
- For pure numeric forecasting, the "LLM backbone" contributes nothing measurable (Tan et al.) and specialised or from-scratch models are 100x to 10,000x cheaper. This is the cleanest piece of evidence for the thesis.
- For reasoning about series (why did this happen, what should we do), neither side has won. General LLMs with code reach 65% to 78% on multiple-choice exams and 35 to 40 out of 100 on multi-turn decision tasks. Native time-series encoders bolted onto LLMs (ChatTS) report large gains, but a 2026 benchmark (MMTS-BENCH) finds such adapted models generalise worse across domains than plain frontier LLMs.
- The 2026 failure pattern has shifted from "cannot compute" to "computes correctly but misreads or over-trusts the output and picks wrong parameters". That is an argument about harness and domain grounding, not about tokenization.
- Text context matters (Context is Key). A numeric-only vertical model that cannot ingest deviation notes, recipe changes or lot information leaves accuracy on the table.

### Gaps
- OpenReview reviewer criticisms of Tan et al., Time-LLM and LLMTime were not retrieved (search budget exhausted; forum IDs unknown).
- Exact F1 values for Zhou and Yu are in appendix figures not captured by the reader.
- No verified evaluation of LLM or foundation-model forecasting on real bioreactor, chromatography or batch-trajectory data was found. All benchmarks above are energy, traffic, weather, finance, health or synthetic.
- Current (late 2026) GIFT-Eval leaderboard standings for Chronos-2, TimesFM-2.x, Moirai and similar were not retrieved.

---

## 3. Tabular prediction and regression: LLMs versus gradient-boosted trees versus TabPFN, and where text-to-text regression works

### Takeaway
General LLMs are competitive only in the very-few-shot regime or when column semantics carry signal, and part of that reported advantage is contamination and evaluation artefact. The headline "LLM regression" successes (OmniPred, Google's RLM) are small encoder-decoders trained from scratch with custom numeric tokens on proprietary system data, which is closer to a vertical model than to a general LLM.

### Cited Findings

**Accurate predictions on small data with a tabular foundation model (TabPFN v2)** — Hollmann et al., 2025, Nature 637:319–326. [doi:10.1038/s41586-024-08328-6](https://doi.org/10.1038/s41586-024-08328-6), [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC11711098/) **[SUPPORTS]**
- Setup: transformer pre-trained on about 100 million synthetic datasets; cell values are z-normalised floats passed through linear encoders, not text tokens; in-context learning in one forward pass.
- Result: default TabPFN takes 2.8 s (classification) and 4.8 s (regression) and beats baselines tuned for 4 h, a 5,140x and 3,000x speed-up. Normalised ROC AUC 0.939 versus 0.752 for default CatBoost; normalised regression score 0.923 versus 0.872.
- Limits: evaluated only up to 10,000 samples and 500 features; single prediction 0.2 s on GPU versus 0.0002 s for CatBoost.

**Why do tree-based models still outperform deep learning on tabular data?** — Grinsztajn et al., 2022, arXiv (NeurIPS 2022 D&B per authors; venue not shown on the arXiv page). [arXiv:2207.08815](https://arxiv.org/abs/2207.08815) **[context / SUPPORTS]**
- 45 datasets, 20,000 compute-hours of tuning. Tree models remain state of the art at about 10K samples. Identifies robustness to uninformative features and irregular target functions as what neural models lack.

**TabArena: A Living Benchmark for Machine Learning on Tabular Data** — Erickson et al., 2025, NeurIPS 2025 Datasets and Benchmarks. [arXiv:2506.16791](https://arxiv.org/abs/2506.16791) **[SUPPORTS native tabular models]**
- 51 curated datasets, 16 models, about 25 million model runs. Tabular foundation models dominate on small data without tuning; gradient-boosted trees remain strong; ensembles across model types are best overall. (Verified through search-result summary of the arXiv HTML; not read in full.)

**Transformers Boost the Performance of Decision Trees on Tabular Data across Sample Sizes (LLM-Boost / PFN-Boost)** — Jayawardhana et al., 2025, arXiv preprint. [arXiv:2502.02672](https://arxiv.org/abs/2502.02672) **[MIXED]**
- States that LLMs and TabPFN do well on small tables but "are not competitive with gradient-boosted decision trees on medium or large datasets" because of context limits. Fusing either with a GBDT beats both components; PFN-Boost has the best average performance for all but very small datasets.

**TabLLM: Few-shot Classification of Tabular Data with Large Language Models** — Hegselmann et al., 2022, arXiv (AISTATS 2023 per authors; venue not shown on the arXiv page). [arXiv:2210.10723](https://arxiv.org/abs/2210.10723) **[UNDERMINES in few-shot only]**
- Serialises rows to text. Competitive with gradient-boosted trees "especially when very few labeled examples are available"; non-trivial zero-shot performance attributed to prior knowledge in the LLM. No numbers in the abstract.

**Large Scale Transfer Learning for Tabular Data via Language Modeling (TabuLa-8B)** — Gardner et al., 2024, NeurIPS 2024. [arXiv:2406.12031](https://arxiv.org/abs/2406.12031) **[UNDERMINES, but see next item]**
- Llama 3-8B fine-tuned on over 2.1B rows from 4M tables; 329 evaluation datasets. Zero-shot accuracy is more than 15 points above random; in the 1 to 32 shot setting it is 5 to 15 points more accurate than XGBoost and TabPFN trained on equal or up to 16x more data.

**The Illusion of Generalization in Tabular Language Models** — Gorla and Puduppully, **(2026)**, ICML 2026. [arXiv:2602.04031](https://arxiv.org/abs/2602.04031) **[SUPPORTS]**
- Re-evaluates TabuLa-8B on 165 UniPredict datasets. Binary and categorical classification show near-zero median lift over majority-class baselines. Instruction-tuning with no tabular exposure recovers 92.2% of standard classification performance. On quartile classification, format familiarity closes 71.3% of the gap, with the rest attributed to contaminated datasets.

**Elephants Never Forget: Memorization and Learning of Tabular Data in Large Language Models** — Bordt et al., 2024, COLM 2024. [arXiv:2404.06209](https://arxiv.org/abs/2404.06209) **[SUPPORTS]**
- LLMs have memorised many popular tabular datasets verbatim and score better on seen than on post-cutoff datasets. On novel data, few-shot sample efficiency "lags behind traditional statistical learning algorithms, especially as the dimension of the problem increases."

**From Words to Numbers: Your Large Language Model Is Secretly A Capable Regressor When Given In-Context Examples** — Vacareanu et al., 2024, COLM 2024. [arXiv:2404.07544](https://arxiv.org/abs/2404.07544) **[UNDERMINES]**
- Setup: 12 LLMs versus 10 supervised baselines on synthetic linear and non-linear regression with 50 in-context examples, 100 seeds, no gradient updates.
- Full text: on a linear task MAE is 0.12 (linear regression), 0.14 (Claude 3), 2.26 (GPT-4), 2.58 (gradient boosting), 5.32 (random forest). On Friedman #2, Claude 3 beats every method except polynomial linear regression. Claude 3 Opus beats gradient boosting and KNN on all 5 non-linear datasets. — [full text](https://arxiv.org/html/2404.07544v3)
- Limits stated: inputs rounded to two decimals; at most about 20 features; 20 to 500 examples; contamination mitigated, not excluded; LLMs struggle on targets generated by random neural networks.

**OmniPred: Language Models as Universal Regressors** — Song et al., 2024, TMLR. [arXiv:2402.14547](https://arxiv.org/abs/2402.14547) **[MIXED]**
- Setup: a roughly 200M-parameter T5 trained from scratch on Google Vizier (x, y) data as text; outputs use custom sign / digit / exponent tokens (72.5 → `<+><7><2><5><E-1>`).
- Full text: mean study error on 1,000 unseen real-world studies is 0.21 (pretrain plus fine-tune LM), 0.25 (MLP), 0.28 (single-task LM), 0.32 (tree), 0.32 (random forest), 0.42 (Gaussian process). — [full text](https://arxiv.org/html/2402.14547v6)
- Full text: removing parameter names (anonymising) raises BBOB error from 0.03 to 0.46, so the gain comes from semantic metadata. Sampling can "hallucinate" wildly wrong outliers through exponent or leading-digit errors, so predictions use the median of 64 samples.

**Performance Prediction for Large Systems via Text-to-Text Regression (Regression Language Model, RLM)** — Akhauri et al., 2025, arXiv preprint; code at google-deepmind/regress-lm. [arXiv:2506.21718](https://arxiv.org/abs/2506.21718) **[MIXED — the most relevant single item for an industrial-systems thesis]**
- Setup: a 60M-parameter encoder-decoder trained from random initialisation ("no language pretraining") to predict resource efficiency on Google's Borg cluster from serialised configuration and log text.
- Result: up to 0.99 (0.9 average) rank correlation across the fleet, 100x lower MSE than tabular approaches, adapts to new tasks with 500 examples.
- Full text: outputs use P10 sign / mantissa / exponent tokens; inputs average about 268,000 characters for the largest feature; predictive density captures multimodal outcomes and its spread correlates with error. All results come from one system; no comparison to a general pretrained LLM is reported. — [full text](https://arxiv.org/html/2506.21718)

**Decoding-based Regression** — Song and Bahri, 2025, TMLR. [arXiv:2501.19383](https://arxiv.org/abs/2501.19383) **[UNDERMINES the "non-token" part of the thesis]**
- Token-decoding numeric heads trained with cross-entropy are "as performant as standard pointwise heads" on standard regression benchmarks and can represent smooth densities. No numbers in the abstract.

**LLM Processes: Numerical Predictive Distributions Conditioned on Natural Language** — Requeima et al., 2024, NeurIPS 2024. [arXiv:2405.12856](https://arxiv.org/abs/2405.12856) **[UNDERMINES]**
- Elicits coherent joint numeric predictive distributions from LLMs; adding text describing prior knowledge improves predictive performance. No numbers in the abstract.

### Inferences
- The regime map is consistent across papers: under about 32 labelled rows with meaningful column names, a general LLM can win; from hundreds to 10,000 rows, native tabular foundation models win; above that, gradient-boosted trees or hybrids win. Most manufacturing datasets (tens to low hundreds of batches, each with long trajectories) sit awkwardly across the first two regimes.
- OmniPred and RLM are regularly cited as "LLMs can regress". Read closely, they support a refined thesis: train a small model from scratch on domain logs with purpose-built numeric tokens. They contradict the "non-token" wording, because both decode numbers as tokens.
- The reported value of text in regression comes from semantics (parameter names, configuration strings). When names are anonymised the advantage disappears (OmniPred 0.03 → 0.46). Manufacturing data with rich tags, units and recipe text is where a text-capable regressor has an edge over a pure tabular model.
- Contamination is a recurring confound for general-LLM tabular claims (Bordt et al.; Gorla and Puduppully). Any internal benchmark should use post-cutoff or proprietary data.

### Gaps
- "Leveraging large language models for predictive chemistry" (Jablonka et al., Nature Machine Intelligence, 2024; https://www.nature.com/articles/s42256-023-00788-1) is known to me as reporting that fine-tuned GPT-3 matches conventional ML in low-data chemistry tasks, but the page was paywall-redirected and I could not verify title or numbers in this session. Treat as unverified.
- No head-to-head of a frontier 2026 general LLM versus TabPFN-2.5 or TabICL on numeric-only regression was found.
- RLM reports no exact baseline MSE values in text (the 100x figure is against a variance bound for tabular-feature models, shown in figures).
- No tabular or regression LLM study on assay tables, CQA prediction or batch-record data was found.

---

## 4. Physical and process reasoning: physics, control, chemical engineering, fault diagnosis, P&IDs, pharma manufacturing

### Takeaway
Frontier LLMs now beat expert chemists on textbook-style chemistry knowledge but fail specific quantitative and graphical sub-skills (22% on NMR signal counting, 6.7% to 13.3% on Bode analysis), and as direct or supervisory controllers they are slower and less accurate than PID or MPC on disturbance rejection. They do well at structured recovery planning and root-cause explanation when wrapped in validators, digital twins and classical detectors. Evidence specific to pharmaceutical or bioprocess manufacturing is nearly absent.

### Cited Findings

**A framework for evaluating the chemical knowledge and reasoning abilities of large language models against the expertise of chemists (ChemBench)** — Mirza et al., 2025, Nature Chemistry 17:1027–1034 (preprint title "Are large language models superhuman chemists?"). [doi:10.1038/s41557-025-01815-x](https://doi.org/10.1038/s41557-025-01815-x), [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC12226332/), [arXiv:2404.01475](https://arxiv.org/abs/2404.01475) **[MIXED]**
- Setup: 2,788 question-answer pairs; 19 chemistry experts as the human baseline.
- Against the thesis: o1-preview outperformed the best human in the study "by almost a factor of two" overall.
- For the thesis: o1-preview answered only 22% of NMR signal-counting questions correctly; toxicity/safety and analytical chemistry are low-scoring topics; most models are poorly calibrated (details in section 6). The literature agent PaperQA2 did not fix knowledge-intensive failures because the needed facts live in databases, not papers.

**What can Large Language Models do in chemistry? A comprehensive benchmark on eight tasks** — Guo et al., 2023, NeurIPS 2023 Datasets and Benchmarks. [arXiv:2305.18365](https://arxiv.org/abs/2305.18365) **[MIXED]**
- GPT-4, GPT-3.5, Davinci-003, Llama, Galactica on eight chemistry tasks, zero- and few-shot. GPT-4 is best; the paper discusses limitations. No numbers in the abstract.

**Capabilities of Large Language Models in Control Engineering: A Benchmark Study on GPT-4, Claude 3 Opus, and Gemini 1.0 Ultra (ControlBench)** — Kevian et al., 2024, arXiv preprint. [arXiv:2404.03647](https://arxiv.org/abs/2404.03647) **[SUPPORTS]**
- Setup: 147 undergraduate control problems (26 with figures), graded by human experts.
- Full text: accuracy is 58.5% (Claude 3 Opus), 45.6% (GPT-4), 34.0% (Gemini 1.0 Ultra); after self-check 68.7% / 47.6% / 38.8%. — [full text](https://arxiv.org/html/2404.03647)
- Full text: Bode analysis 13.3% / 6.66% / 6.66%; Nyquist design 40% / 0% / 0%; control system design 33.3% / 29.2% / 25.0%.
- Full text failure modes: Claude 3 Opus's main weakness is calculation; one PI design placed poles at -0.60 and -0.33 instead of -0.1 and -0.2. A formatting-only change flipped Gemini's conclusion. A model repeated the same wrong step response after self-check while stating 95% confidence. Models are 2024 vintage.

**ControlAgent: Automating Control System Design via Novel Integration of LLM Agents and Domain Expertise** — Guo et al., 2024, arXiv preprint. [arXiv:2410.19811](https://arxiv.org/abs/2410.19811) **[UNDERMINES]**
- Multi-agent LLM plus a Python computation agent iteratively tunes controllers against stability, performance and robustness requirements on ControlEval (500 tasks). The abstract claims effectiveness versus LLM and toolbox baselines but gives no numbers.

**Pre-Trained Large Language Models for Industrial Control** — Song et al., 2023, arXiv preprint. [arXiv:2308.03028](https://arxiv.org/abs/2308.03028) **[UNDERMINES]**
- GPT-4 controls a simulated HVAC system from a text description, demonstrations and the current observation. Claims performance "comparable to RL methods" with few samples. No numbers in the abstract.

**Autonomous Control Leveraging LLMs: An Agentic Framework for Next-Generation Industrial Automation** — Vyas and Mercangöz, 2025, arXiv preprint (earlier version [arXiv:2411.05904](https://arxiv.org/abs/2411.05904)). [arXiv:2507.07115](https://arxiv.org/abs/2507.07115) **[MIXED]**
- Setup: (1) recovery planning over 180 random finite-state machines; (2) LLM controller on a physical TCLab dual-heater rig and its digital twin versus PID.
- Result: GPT-4o and GPT-4o-mini reach 100% valid-path success within five reprompts on the planning task.
- Full text: on the physical rig, time-weighted MAE is 1.03 K (GPT-3.5) versus 0.76 K (PID); on the digital twin 0.62 K versus 0.21 K. Inference cycle averages 34.18 s (range 10.58 to 72.69 s) on the physical system. The LLM's own temperature prediction error grows from 0.09 K at 3 s to 3.31 K at 30 s, and its reasoning included physically implausible steps (ignoring heat losses, a single finite-difference step). A local LLaMA-3.2 3B falls to 0.30 valid-path accuracy on 20- and 25-state machines. — [full text](https://arxiv.org/html/2507.07115v1)

**From Detection to Action: Using LLM Agents for Fault-Tolerant Control** — Vyas et al., **(2026)**, arXiv preprint June 2026. [arXiv:2606.28011](https://arxiv.org/abs/2606.28011) **[MIXED]**
- Setup: simulation only; a batch mixing module and a CSTR under PID; LLM agents propose recovery actions that a deterministic validator checks against interlocks and envelopes; 10 runs per fault.
- Full text: mixing module success is 60/60 for GPT-4.1-mini and 51/60 for GPT-4o-mini. CSTR success is 28/30 (93.3%) versus 23/30 (76.7%); on a stuck-closed cooling valve GPT-4o-mini succeeds 4/10 versus 10/10. Per-decision latency is 2.1 to 3.5 s. — [full text](https://arxiv.org/html/2606.28011)
- Stated limits: latencies rule out hard real-time; model mismatch, sensor noise and unmodelled dynamics were not evaluated; the twin only validates faults modelled in advance. (The paper's text and table disagree on one aggregate: 85% versus 80%.)

**Safety-Gated Agentic Supervisory Control on a Coupled Distillation Benchmark: Regime Map, Auditable Gate, and Co-Design Findings** — Rosenthal, **(2026)**, arXiv preprint July 2026, single independent author, not peer reviewed. [arXiv:2607.27849](https://arxiv.org/abs/2607.27849) **[MIXED — the most direct LLM-versus-MPC process-control comparison found]**
- Setup: an LLM agent writes composition setpoints every five minutes on Skogestad's Column A; compared with PID-only, linear MPC, an ungated agent and a gated agent on identical scenarios and seeds.
- Result against the thesis: in off-nominal target acquisition the ungated agent beats Pareto-tuned linear MPC (integral absolute error ratio 0.361 at the upper confidence bound).
- Result for the thesis: on disturbance rejection the ratio inverts by 10.18 (point estimate) and 16.03 (upper bound); the abstract concludes an ungated LLM supervisor "does not belong" there. The agent showed a "specification-abandonment" failure in 6/10 runs until a prompt fix. A rule-based twin gate cut 95th-percentile error from 11.5 to 0.77, but 534 of 590 gate interventions blocked a well-behaved operating point sitting on a safety limit.
- Caveat: results are for one column and specific small models (DeepSeek-V4-Flash, Nemotron-3-Super). Abstract only.

**FaultExplainer: Leveraging Large Language Models for Interpretable Fault Detection and Diagnosis** — Khan et al., 2024, arXiv preprint. [arXiv:2412.14492](https://arxiv.org/abs/2412.14492) **[MIXED]**
- Setup: Tennessee Eastman Process; PCA detects faults and ranks contributing variables; GPT-4o or o1-preview explains root cause.
- Full text: PCA detected 11 of 15 tested faults. With historical root causes supplied, top-3 diagnosis is correct for 7/11 (GPT-4o) and 9/11 (o1-preview). Without them, both give a correct or related cause for 8/11. Documented hallucinations include causal claims the authors call "nonsensical". The LLM never sees the raw trajectories; a classical detector does the numeric work. — [full text](https://arxiv.org/html/2412.14492v1)

**PHYBench: Holistic Evaluation of Physical Perception and Reasoning in Large Language Models** — Qiu et al., 2025, arXiv preprint. [arXiv:2504.16074](https://arxiv.org/abs/2504.16074) **[SUPPORTS]**
- 500 original physics problems (high school to Olympiad). Best model, Gemini 2.5 Pro, reaches 36.9% accuracy versus 61.9% for human experts.

**Talking like Piping and Instrumentation Diagrams (P&IDs)** — Alimin et al., 2025, Systems and Control Transactions. [arXiv:2502.18928](https://arxiv.org/abs/2502.18928) **[SUPPORTS on representation]**
- P&IDs are converted from the DEXPI data model to labelled property graphs and queried by an LLM through graph retrieval. The authors say this reduces hallucination. No quantitative evaluation in the abstract. The point: the diagram is given a native graph representation; the LLM is the interface.

**An Agentic Approach to Automatic Creation of P&ID Diagrams from Natural Language Descriptions** — Gowaikar et al., 2024, AAAI 2025 workshop (AI2ASE). [arXiv:2412.12898](https://arxiv.org/abs/2412.12898) **[UNDERMINES weakly]**
- A multi-step agentic workflow generates P&IDs from text and outperforms zero-shot and few-shot generation on soundness and completeness. No numbers in the abstract.

**Generative AI and Process Systems Engineering: The Next Frontier** — Decardi-Nelson et al., 2024, Computers & Chemical Engineering 187:108723. [arXiv:2402.10977](https://arxiv.org/abs/2402.10977) **[context]**
- Review. Names multiscale modelling, data requirements, missing evaluation benchmarks, and trust and safety as the open obstacles to using foundation models in process design, optimisation, monitoring and control.

**CeProAgents: A Hierarchical Agents System for Automated Chemical Process Development (with CeProBench)** — Yang et al., **(2026)**, arXiv preprint March 2026. [arXiv:2603.01654](https://arxiv.org/abs/2603.01654) **[UNDERMINES weakly]**
- Multi-agent system with knowledge, concept and parameter cohorts; new benchmark with six task types. Abstract claims superiority without numbers.

**PSE-Bench** — Sukpancharoen and Srinophakun, **(2026)**, [GitHub repository](https://github.com/sombsuk/PSE-Bench) **[context; low confidence]**
- 200 open-ended process-systems-engineering questions scored by five AI judges; five zero-shot models. Top element coverage 78.1% (DeepSeek-V3); process design ranked hardest. Publication venue is inconsistent on the page (Chemical Engineering Journal Advances versus Computers & Chemical Engineering "under review"), and human-judge agreement is reported as Spearman 0.416.

**Can Foundational Large Language Models Assist with Conducting Pharmaceuticals Manufacturing Investigations?** — Salami et al., 2024, arXiv preprint (authors include pharmaceutical-industry affiliations). [arXiv:2404.15578](https://arxiv.org/abs/2404.15578) **[UNDERMINES for text tasks]**
- GPT-3.5, GPT-4 and Claude-2 on a small set of real manufacturing deviations. GPT-4 and Claude-2 show "high accuracy" extracting root cause from unstructured records, and embedding search finds similar deviations accurately. No numbers in the abstract. The tasks are document tasks, not numeric process data.

**Benchmarking Local LLMs for Natural-Language-to-SQL Querying in Biopharmaceutical Manufacturing** — Bhetwal et al., **(2026)**, arXiv preprint June 2026. [arXiv:2606.01338](https://arxiv.org/abs/2606.01338) **[UNDERMINES the "vertical pretraining wins" assumption, narrowly]**
- Four local 7B to 8B models on 60 questions over a synthetic 63,000-record batch / MES / clean-in-place database. Code-tuned general models (Qwen 2.5 Coder, Llama 3.1) produced SQL for all tasks; the biomedical-domain model Meditron 7B failed on nearly all. The authors say human oversight and downstream validation are still required for regulated use. Small study on synthetic data.

### Inferences
- The split is by task type, not by domain. Knowledge recall, document extraction, recovery planning over discrete states and root-cause narration: general LLMs are at or above expert level or reach 100% with a validator loop. Reading plots and spectra, multi-step calculation, continuous closed-loop regulation and disturbance rejection: they lose to classical or specialised methods, sometimes by an order of magnitude.
- Every successful LLM-in-control result above depends on a non-LLM component doing the numeric or safety-critical work (PID or MPC regulatory layer, PCA detector, deterministic validator, digital twin, knowledge graph). This supports "LLM alone is not enough" and equally supports "LLM plus harness can be enough for supervisory tasks".
- Latency (2 to 34 s per decision) and run-to-run variability restrict LLMs to supervisory time scales. Many bioprocess decisions (feed adjustments, hold/release, deviation triage) are on those time scales, so this constraint is weaker for pharma batch operations than for continuous chemical plants.
- The one data point comparing a domain-pretrained LLM with a general code model on a pharma-manufacturing task (text-to-SQL) favoured the general model. Vertical pretraining on domain text does not by itself confer an advantage; the thesis must rest on native numeric and process representations specifically.

### Gaps
- No peer-reviewed benchmark was found that evaluates LLMs on real bioprocess trajectories, chromatograms, spectra (Raman, NIR) or batch records with quantitative ground truth. This is the largest evidence gap relative to the thesis, and applies to both sides.
- Spectra interpretation benchmarks (for example multimodal structure-elucidation benchmarks) could not be searched; the only verified spectra-related number is ChemBench's 22% on NMR signal counting.
- Journal-specific searches (AIChE Journal, Industrial & Engineering Chemistry Research, Digital Discovery, Nature Machine Intelligence) were not completed. A ChemRxiv preprint on monoclonal-antibody bioprocess engineering with conversational AI surfaced in search but returned HTTP 403 and is unverified.
- ChemCrow (Bran et al., [arXiv:2304.05376](https://arxiv.org/abs/2304.05376)) was verified as an 18-tool chemistry agent that planned and executed syntheses, but it reports no numeric benchmark relevant to process data.
- ControlBench has not, to my knowledge from this session, been re-run on 2026 frontier models.

---

## 5. Counter-evidence: general LLM plus tools, code execution or search matching or beating specialised models

### Takeaway
There are now several strong cases where a general LLM used as a hypothesis or code generator inside a search-and-evaluate loop beats specialised methods, including on time-series forecasting and mechanistic equation discovery. In every such case the LLM writes programs or model structures and numeric fitting is delegated to conventional optimisers, and broad agent benchmarks still show low end-to-end success rates (17% to 34%).

### Cited Findings

**An AI system to help scientists write expert-level empirical software (Empirical Research Assistance, ERA)** — Aygün et al., 2025 (v3 May 2026), arXiv preprint; a search result indicates a 2026 Nature version (DOI prefix 10.1038/s41586-026-10658-6), not independently confirmed. [arXiv:2509.06503](https://arxiv.org/abs/2509.06503) **[UNDERMINES — strongest single counter-example]**
- Setup: Gemini 2.5 Flash plus tree search over candidate programs, optimising a task metric.
- Result: 40 novel single-cell analysis methods outperform the top human-developed methods on a public leaderboard; 14 models outperform the CDC ensemble for COVID-19 hospitalisation forecasting.
- Full text: on GIFT-Eval, per-dataset solutions built from scikit-learn, XGBoost and statsmodels "outperformed the entire May 18, 2025 leaderboard" of time-series foundation models; a unified from-scratch library reached MASE 0.734. Search used 300 nodes per dataset. COVID average weighted interval score 26 versus 29 for the CovidHub ensemble. Best single-cell method is a 14% overall improvement over the best published method. — [full text](https://arxiv.org/html/2509.06503v3)
- Caveats: frozen leaderboard snapshot, not a live submission; the five largest datasets were excluded from per-dataset search and assigned the naive baseline.

**LLM-SR: Scientific Equation Discovery via Programming with Large Language Models** — Shojaee et al., 2024, ICLR 2025 Oral. [arXiv:2404.18400](https://arxiv.org/abs/2404.18400) **[UNDERMINES — directly relevant to mechanistic process models]**
- Setup: the LLM proposes equation skeletons as programs; parameters are fitted by numerical optimisers; evolutionary search; four problems including E. coli growth and material stress-strain, designed to prevent recitation.
- Full text: on E. coli growth, normalised MSE (in-domain / out-of-domain) is 0.0026 / 0.0037 for LLM-SR (Mixtral) versus 0.0376 / 1.0141 for PySR and 0.3322 / 5.4584 for uDSR. LLM-SR used about 2,500 iterations versus millions for search baselines. — [full text](https://arxiv.org/html/2404.18400v3)
- Full text ablation: when the LLM generates equations with numeric parameters end-to-end, error on one oscillator problem rises from 2.12e-7 to 3.78e-1. The LLM contributes structure; it cannot supply the numbers.

**LLM-SRBench: A New Benchmark for Scientific Equation Discovery with Large Language Models** — Shojaee et al., 2025, ICML 2025 Oral. [arXiv:2504.10415](https://arxiv.org/abs/2504.10415) **[SUPPORTS — tempers the item above]**
- 239 problems in four domains built to defeat memorisation. The best system "achieves only 31.5% symbolic accuracy."

**Automated Statistical Model Discovery with Language Models** — Li et al., 2024, ICML 2024. [arXiv:2402.17879](https://arxiv.org/abs/2402.17879) **[UNDERMINES]**
- The LLM proposes probabilistic programs and critiques them in a Box's-loop cycle; discovered models are "on par with human expert designed models". No numbers in the abstract.

**AlphaEvolve: A coding agent for scientific and algorithmic discovery** — Novikov et al., 2025, arXiv white paper. [arXiv:2506.13131](https://arxiv.org/abs/2506.13131) **[UNDERMINES]**
- LLM-driven evolutionary code search guided by evaluators. Produced a more efficient data-centre scheduling heuristic in production at Google and a 4x4 complex matrix multiplication in 48 scalar multiplications, the first improvement over Strassen in that setting in 56 years.

**Can Generalist Foundation Models Outcompete Special-Purpose Tuning? Case Study in Medicine (Medprompt)** — Nori et al., 2023, arXiv preprint. [arXiv:2311.16452](https://arxiv.org/abs/2311.16452) **[UNDERMINES]**
- GPT-4 with a prompting strategy surpasses 90% on MedQA for the first time, a 27% error-rate reduction versus the best specialist-model methods, state of the art on all nine MultiMedQA datasets, with an order of magnitude fewer model calls than Med-PaLM 2.
- Follow-up, **From Medprompt to o1** — Nori et al., 2024, [arXiv:2411.03590](https://arxiv.org/abs/2411.03590): o1-preview with no prompting technique largely outperforms GPT-4 with Medprompt, and few-shot prompting hurts it. Both are text question-answering results, not numeric data.

**Program of Thoughts Prompting: Disentangling Computation from Reasoning for Numerical Reasoning Tasks** — Chen et al., 2022, TMLR 2023. [arXiv:2211.12588](https://arxiv.org/abs/2211.12588) **[UNDERMINES]**
- The LLM writes a program and an interpreter executes it. Average gain of about 12% over chain-of-thought across five math word-problem and three financial QA datasets.

**MLE-bench: Evaluating Machine Learning Agents on Machine Learning Engineering** — Chan et al., 2024, ICLR 2025. [arXiv:2410.07095](https://arxiv.org/abs/2410.07095) **[MIXED]**
- 75 Kaggle competitions. Best setup (o1-preview with AIDE scaffolding) reaches at least bronze-medal level in 16.9% of competitions.

**DSBench: How Far Are Data Science Agents from Becoming Data Science Experts?** — Jing et al., 2024, arXiv (v3 April 2025). [arXiv:2409.07703](https://arxiv.org/abs/2409.07703) **[SUPPORTS]**
- 466 data-analysis and 74 data-modelling tasks. The best agent solves 34.12% of analysis tasks.

**The AI Scientist: Towards Fully Automated Open-Ended Scientific Discovery** — Lu et al., 2024, arXiv preprint. [arXiv:2408.06292](https://arxiv.org/abs/2408.06292) **[MIXED, weak]**
- End-to-end paper generation in three ML subfields at under $15 per paper; quality is judged by the authors' own automated reviewer.

See also in section 2: Rechtorík et al. (2026), code access adds 5 to 13 points on time-series reasoning; Context is Key (ICML 2025), an LLM prompting method tops a context-dependent forecasting benchmark; MMTS-BENCH (2026), general LLMs generalise better than time-series-adapted LLMs. In section 3: Vacareanu et al., in-context regression rivalling gradient boosting. In section 4: ChemBench, o1-preview above the best human chemist.

### Inferences
- The winning harness pattern is consistent: LLM proposes structure (code, equation skeleton, probabilistic program), a deterministic evaluator scores it on data, and search iterates. The final artefact that makes numeric predictions is conventional code or a fitted mechanistic model, not the LLM. This artefact is inspectable and deterministic, which is easier to validate in a regulated setting than either a general LLM or an opaque foundation model.
- This is the most serious challenge to the thesis. If a general LLM with tree search can write forecasting code that tops a leaderboard of native time-series foundation models, then "vertical foundation model" is not the only route to accuracy on numeric process data. The route requires a clear scoring metric and enough held-out data per problem, which small-batch pharma often lacks.
- The same evidence carries a point for the thesis: remove the numeric optimiser and LLM-SR degrades by six orders of magnitude; give agents open-ended end-to-end tasks and success is 17% to 34%. The LLM is not the numeric engine in any of the winning systems.
- A defensible synthesis: general LLMs are strong at model and code proposal and at text context; specialised numeric models or classical methods are needed for the actual estimation, forecasting and control. The competitive question is which layer captures the value.

### Gaps
- FunSearch (Romera-Paredes et al., Nature 2024; https://www.nature.com/articles/s41586-023-06924-6) is the precursor to AlphaEvolve but the page was paywall-redirected and not verified in this session.
- "Data-Driven Discovery of Dynamical Systems in Pharmacology using Large Language Models" (Holt et al., NeurIPS 2024) is known to me as an LLM-proposes-ODE-model result in pharmacokinetics, directly relevant to mechanistic bioprocess models, but I could not locate and verify it after the search budget ran out. Treat as unverified.
- The Nature publication status of the ERA paper rests on a search result showing a Springer Nature supplementary-file URL; the arXiv page lists no journal.
- No example was found of the propose-and-evaluate pattern applied to a GMP manufacturing dataset.

---

## 6. Hallucination, calibration and determinism for regulated, high-stakes use

### Takeaway
LLM self-reported confidence is poorly aligned with correctness on domain tasks, and identical inputs at nominally deterministic settings do not reliably yield identical outputs (accuracy swings up to 15% across runs; one 120B model reproduced its output 12.5% of the time at temperature 0). Smaller locally hosted models can be made fully reproducible, and from-scratch regression models expose usable predictive densities, so these are engineering constraints with known mitigations more than fundamental barriers.

### Cited Findings

**Non-Determinism of "Deterministic" LLM Settings** — Atil et al., 2024 (v5 April 2025), arXiv preprint. [arXiv:2408.04667](https://arxiv.org/abs/2408.04667) **[SUPPORTS]**
- Five LLMs, eight tasks, 10 runs each at settings meant to be deterministic. Accuracy varies up to 15% across naturally occurring runs; the gap between best possible and worst possible performance reaches 70%; "none of the LLMs consistently delivers repeatable accuracy across all tasks." (Earlier versions reported up to 10% with a different model set.)

**Understanding and Mitigating Numerical Sources of Nondeterminism in LLM Inference** — Yuan et al., 2025, arXiv preprint. [arXiv:2506.09501](https://arxiv.org/abs/2506.09501) **[MIXED]**
- With bfloat16 and greedy decoding, DeepSeek-R1-Distill-Qwen-7B shows up to 9% accuracy variation and up to 9,000 tokens difference in response length depending on GPU count, GPU type and batch size. Root cause: non-associative floating-point arithmetic; reasoning models are most affected. Mitigation proposed (LayerCast: 16-bit weights, 32-bit compute).

**LLM Output Drift: Cross-Provider Validation & Mitigation for Financial Workflows** — Khatchadourian and Franco, 2025, AI4F workshop at ACM ICAIF 2025. [arXiv:2511.07585](https://arxiv.org/abs/2511.07585) **[MIXED]**
- 480 runs across five models. At temperature 0.0, Granite-3-8B and Qwen2.5-7B reach 100% output consistency; GPT-OSS-120B reaches 12.5% (95% CI 3.5 to 36.0%). SQL tasks stay stable even at temperature 0.2; retrieval-augmented tasks drift 25% to 75%. Proposes a deterministic harness and invariant checks mapped to financial regulators' expectations.

**Can LLMs Express Their Uncertainty? An Empirical Evaluation of Confidence Elicitation in LLMs** — Xiong et al., 2023, ICLR 2024. [arXiv:2306.13063](https://arxiv.org/abs/2306.13063) **[SUPPORTS]**
- Five LLMs, five dataset types including arithmetic reasoning. Verbalised confidence is overconfident; failure-prediction AUROC is only 0.522 to 0.605 even for white-box methods; all methods struggle on tasks needing professional knowledge.

**Just Ask for Calibration: Strategies for Eliciting Calibrated Confidence Scores from Language Models Fine-Tuned with Human Feedback** — Tian et al., 2023, EMNLP 2023. [arXiv:2305.14975](https://arxiv.org/abs/2305.14975) **[MIXED]**
- For RLHF-tuned models (ChatGPT, GPT-4, Claude), verbalised confidence is better calibrated than token probabilities, often cutting expected calibration error by a relative 50% on TriviaQA, SciQ and TruthfulQA. General QA, not numeric outputs.

**ChemBench (Mirza et al., Nature Chemistry 2025)** — [PMC full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC12226332/) **[SUPPORTS]**
- On chemical safety-profile questions GPT-4 reported confidence 1.0 (scale 1 to 5) for the one question it got right and 4.0 for the six it got wrong. Claude-3.5 Sonnet averaged 2.0 for correct and 1.83 for incorrect answers on GHS pictogram questions. The authors report most models as poorly calibrated.

**ControlBench (Kevian et al., 2024)** — [full text](https://arxiv.org/html/2404.03647) **[SUPPORTS]**
- A model repeated the same wrong step-response answer after self-checking and stated 95% confidence. The paper notes the same question can produce very different answers across runs and that a formatting-only change reversed a conclusion.

**LLMTime (Gruver et al., NeurIPS 2023)** — [arXiv:2310.07820](https://arxiv.org/abs/2310.07820) **[SUPPORTS]**
- GPT-4's forecast uncertainty is worse calibrated than GPT-3's, attributed to alignment interventions such as RLHF. Base models outperform their chat-tuned counterparts across LLaMA-2 sizes (full text).

**OmniPred (Song et al., TMLR 2024)** — [full text](https://arxiv.org/html/2402.14547v6) **[SUPPORTS as a hazard specific to token-decoded numbers]**
- Token-decoded regression can emit wildly wrong outliers when an exponent or leading-digit token is mis-sampled. Mitigated by taking the median of 64 samples (error 0.15 with median versus 0.23 with mean on one dataset).

**Regression Language Model (Akhauri et al., 2025)** — [full text](https://arxiv.org/html/2506.21718) **[UNDERMINES]**
- A from-scratch text-to-text regressor yields a predictive density whose spread correlates with squared error and captures multimodal outcomes; point predictions aggregate 128 samples. Shows token-decoded numerics can carry usable uncertainty when trained for it.

**FaultExplainer (Khan et al., 2024)** — [full text](https://arxiv.org/html/2412.14492v1) **[SUPPORTS]**
- Documents hallucinated causal chains in process fault explanations, including one where the authors say the explanation "appears to be a hallucination rather than a reasoned deduction."

**Can LLM Coding Agents Reason About Time Series? (Rechtorík et al., 2026)** — [full text](https://arxiv.org/html/2606.16545) **[SUPPORTS]**
- When agents answered without running code, 80% to 92% of those answers lacked sufficient evidence; coding agents over-trust returned numbers.

**ChemCrow (Bran et al., 2023)** — [arXiv:2304.05376](https://arxiv.org/abs/2304.05376) **[SUPPORTS on evaluation risk]**
- GPT-4 used as an evaluator could not distinguish clearly wrong GPT-4 completions from the tool-augmented agent's output. LLM-as-judge is unreliable for technical correctness.

### Inferences
- For a validated GMP environment the practical requirements are bit-level or at least answer-level reproducibility, calibrated uncertainty on numeric outputs, and auditable reasoning. The evidence says hosted frontier LLMs fail the first by default, are weak on the second, and partially meet the third. Small self-hosted models and from-scratch numeric models meet the first two more readily.
- This favours an architecture where numeric predictions come from deterministic, versioned artefacts (a specialised model or LLM-authored code that has been reviewed and frozen), with the LLM confined to proposing, explaining and retrieving. That architecture is compatible with either side of the thesis.
- The hazard unique to token-decoded numbers (a single wrong exponent token giving an error of orders of magnitude) applies to vertical text-to-text regressors as well as general LLMs. It is an argument for continuous output heads or sample-aggregation safeguards in any numeric model used for control.
- Claims that domain-specific foundation models are better calibrated than general LLMs on process data are, on the evidence gathered, untested.

### Gaps
- No study was found measuring calibration of LLM numeric outputs (prediction intervals, not multiple-choice confidence) on process or manufacturing data.
- Hallucination-rate benchmarks for numeric extraction from tables or batch records were not retrieved.
- Regulatory sources (for example FDA's 2025 draft guidance on AI for regulatory decision-making in drug and biological products, EU GMP Annex 22 drafts) were not retrieved or verified in this session; they are outside the paper-evidence scope but bear directly on the determinism requirement.
- A 2026 preprint on miscalibrated LLM confidence affecting downstream regression (arXiv 2605.11954) and a 2026 paper on systems-level sources of nondeterminism (arXiv 2604.22411) surfaced in search summaries but were not opened; unverified.
