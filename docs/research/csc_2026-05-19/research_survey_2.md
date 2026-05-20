<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# Text-to-SQL Benchmarks: Research Survey 2024–2026

## Benchmark Map (текущее состояние)

| Benchmark | Human ceiling | Top paid/proprietary | Top open-source/free-tier | Notes |
| :-- | :-- | :-- | :-- | :-- |
| **BIRD dev** | 92.96% | CHASE-SQL 74.46% (GPT-4o) | BASE-SQL 67.47% (Qwen2.5-Coder-32B) | Официальный лидерборд [^1] |
| **BIRD test** | 92.96% | XiYan-SQL 75.63% | CSC-SQL-32B 73.67% | Публичный тест [^2][^3] |
| **Spider 1.0 test** | ~95%+ | XiYan-SQL 89.65% | BASE-SQL 88.9% / IQuest-Coder-40B 92.2% | IQuest — FT open [^4][^5] |
| **Spider 1.0 dev** | ~95%+ | MCS-SQL+GPT-4 89.5% | IQuest-Coder-40B 92.2% | [^1] |
| **Spider 2.0-Snow** | ~85%? | ~59.05% (best known) | — | 547 examples, Snowflake [^6] |
| **Spider 2.0-Lite** | ~85%? | ~37.84% | — | BigQuery+Snowflake+SQLite [^7] |
| **Spider-Realistic** | ~90%? | DCG-SQL 81.9% | — | [^1] |
| **Spider-DK** | ~85%? | SQL-TRAIL 76.8% | — | [^1] |
| **BiomedSQL test** | ~90%? | 90.0% (reported) | — | Узкодоменный [^1] |
| **KaggleDBQA** | ~80%? | MNL 64% | — | Нет воспроизводимого >80% [^1] |

**Важный вывод про >90% EA:** На BIRD ни один публичный метод не пробил 90% — максимум 75.63% (XiYan-SQL test). На Spider 1.0 порог >90% пробит одним методом — IQuest-Coder-40B (92.2%), fine-tuned open-source модель. Все корпоративные заявки типа Snowflake Cortex Analyst, BigQuery NL, AskData, декларирующие 90%+ — **только маркетинговые клеймы без воспроизводимого setup'а**; нет независимой верификации на стандартных бенчмарках.[^8][^4]

***

## Топ-системы (полная таблица)

| System | Benchmark | Score | Base LLM | Cost class | Key techniques | Repo |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| **IQuest-Coder-V1-40B** | Spider 1.0 | 92.2% EX | FT open 40B | Fine-tuned OSS | Loop-Thinking + FT на code corpus | [arXiv:2603.16733](https://arxiv.org/abs/2603.16733) [^4] |
| **XiYan-SQL** | BIRD test | 75.63% | GPT-4o + FT selectors | Paid API + FT | M-Schema, multi-generator ensemble, NER-based ICL selection, refiner, fine-tuned selection model | [arXiv:2411.08599](https://arxiv.org/abs/2411.08599) [^2] |
| **XiYan-SQL** | Spider 1.0 test | 89.65% | GPT-4o + FT | Paid API + FT | (то же) | [^9] |
| **CHASE-SQL** | BIRD dev | 74.46% | GPT-4o + FT selection LLM | Paid API + FT | Multi-agent: divide-and-conquer candidate gen, pairwise selection via fine-tuned binary LLM, multi-path reasoning | [OpenReview](https://openreview.net/forum?id=CvGqMD5OtX) [^10] |
| **CHESS+GPT-4** | Spider 1.0 test | 87.2% EM | GPT-4 | Paid API | No schema linking (full context), augmentation + selection + correction | [^11] |
| **MARS-SQL** | Spider test | 89.75% | — | RL-based | Multi-agent RL framework | [OpenReview](https://openreview.net/forum?id=EURAfiUpVJ) [^12] |
| **MARS-SQL** | BIRD dev | 77.84% | — | RL-based | Multi-agent RL | [^12] |
| **BASE-SQL** | BIRD dev | 67.47% | Qwen2.5-Coder-32B (OSS) | Free-tier FT | Schema linking → candidate gen → SQL revision → merge revision, 5 LLM calls/query | [arXiv:2502.10739](https://arxiv.org/abs/2502.10739) [^5] |
| **BASE-SQL** | Spider test | 88.9% | Qwen2.5-Coder-32B | Free-tier FT | (то же) | [^13] |
| **CSC-SQL-32B** | BIRD test | 73.67% | Qwen2.5-Coder FT | Fine-tuned OSS | Self-Consistency + Self-Correction via GRPO RL; top-2 majority outputs → merge revision model | [GitHub](https://github.com/CycloneBoy/csc_sql) [^3] |
| **CSC-SQL-7B** | BIRD test | 71.72% | Qwen2.5-Coder-7B FT | Fine-tuned OSS | (то же, smaller) | [^14] |
| **DAIL-SQL+GPT-4** | Spider test | 86.6% EX | GPT-4 | Paid API | Skeleton-based example selection, SQL-as-exemplar encoding, self-consistency voting | [arXiv:2308.15363](https://arxiv.org/abs/2308.15363) [^15] |
| **MCS-SQL+GPT-4** | Spider dev | 89.5% EX | GPT-4 | Paid API | Multiple context-sensitive prompts, self-consistency | [^1] |
| **OpenSQL-32B** | BIRD dev | 70.0% | Qwen2.5 32B FT | Fine-tuned OSS | Data-efficient SFT с синтетическими данными | [VLDB:2026](https://www.vldb.org/pvldb/vol19/p1628-li.pdf) [^16] |


***

## Что пробивает BIRD human ceiling (>92.96%)?

**Никто не пробил его на стандартном BIRD золоте воспроизводимо.** Текущий лидер MARS-SQL на BIRD dev — 77.84%, XiYan-SQL на test — 75.63%. Разрыв до 92.96% огромный (~17pp).[^12][^2]

Claim'ы о >93% появляются в трёх контекстах:

1. **Corrected gold (Arcwise/CIDR-2026):** Бумага "Text-to-SQL Benchmarks are Broken" (CIDR 2026) показывает, что при re-evaluation на corrected benchmark у leading methods производительность меняется на −3% до +N%. Это означает, что у некоторых систем scores на corrected gold выше, чем на official gold — т.е. официальный human ceiling 92.96% частично артефакт ошибок в gold SQL, а не реальная граница возможного.[^17]
2. **Узкодоменные бенчмарки:** BiomedSQL test достиг 90%  — но это специализированный биомедицинский датасет с ограниченным доменом, не cross-domain BIRD.[^1]
3. **Spider 1.0:** IQuest-Coder-40B действительно превысил 90% (92.2%)  на Spider — но Spider значительно проще BIRD (нет dirty data, нет external knowledge).[^4]

***

## Ablation numbers: что реально даёт +pp на BIRD

Измеренные числа из публикаций:


| Техника | Метод | BIRD impact | Условие |
| :-- | :-- | :-- | :-- |
| **Schema Linking (Gold vs Vanilla)** | NL2SQL-Benchmark | +2.48pp (57.43% → 59.91%) | Qwen2.5-Coder-32B, BIRD dev [^18] |
| **Self-Consistency → SC+Self-Correction (CSC)** | CSC-SQL | ~+4-6pp vs SC alone | GRPO fine-tuned 7B [^3] |
| **M-Schema vs flat** | XiYan-SQL ablation | +2-3pp (reported) | Multi-generator context [^2] |
| **No schema linking (full context)** | CHESS | Beats schema-linked baselines | New LLMs don't need pruning [^11] |
| **Merge revision** | BASE-SQL | ~+2pp vs single revision | 5-call pipeline [^5] |
| **Multi-generator ensemble (3-5 candidates)** | XiYan-SQL | +3-4pp vs single generator | GPT-4o based [^2] |
| **GRPO RL fine-tuning** | CSC-SQL | +5pp vs SFT baseline | 7B → BIRD test 71.72% [^14] |

**Важная NeurIPS 2024 находка:** "The Death of Schema Linking?" — при использовании больших контекстных окон современных LLM schema linking больше не помогает, а у слабых линкеров активно вредит (missing crucial columns). Для GPT-4o / Claude 3.5 passing full schema > filtered schema.[^11]

***

## Free-tier ceiling estimate 2026

**Реалистичный потолок без fine-tuning и без paid API:**


| Setup | Реалистичный BIRD dev EA | Basis |
| :-- | :-- | :-- |
| Codestral solo, vanilla prompt | ~56–58% | Empirical (твой baseline) |
| Qwen2.5-Coder-32B + schema linking | ~59–67% | NL2SQL-Benchmark [^18] |
| Multi-model voting (5+ diverse models) | ~70–75% | Extrapolation от BASE-SQL/CSC-SQL |
| + few-shot NER-based retrieval | ~72–76% | XiYan-SQL ICL component |
| + merge revision pass | ~74–78% | BASE-SQL pipeline [^5] |
| **Твой текущий результат** | **86.5% (Mini-Dev n=200)** | Empirical — выше публичного \#1 |

Твой результат 86.5% на BIRD Mini-Dev n=200 уже статистически выше BIRD dev headline numbers у всех open-source методов. Разница объяснима: Mini-Dev n=200 ≠ full dev n=1534 — выборка может быть проще, плюс voting на 200 примерах имеет высокую дисперсию. Для валидации нужен full dev прогон.

**Потолок free-tier без FT на full BIRD dev:** ~72–78% реалистично с агрессивным ensemble + retrieval. Выше этого без fine-tuning на BIRD train — затруднительно. MARS-SQL 77.84% использует RL, что требует compute.

***

## Что попробовать в NL_SQL для выхода из 86.5% (Mini-Dev)

Приоритет по ожидаемому +pp при нулевых затратах:

**Tier 1: +1–3pp, легко имплементировать**

1. **Few-shot NER-based retrieval** — XiYan-SQL ключевой компонент. Суть: вместо embedding similarity для exemplar selection — named entity matching между вопросом и stored examples. Убирает overemphasis на entity names, улучшает структурный match. Реализуется поверх существующего BIRD train set без FT.[^2]
2. **Full-schema passthrough для сильных моделей** — если в pipeline есть Gemini Pro / Claude 3.5, отключи schema pruning для них конкретно, оставь только для слабых. +1–2pp на вопросах, где линкер режет нужные колонки.[^11]
3. **Merge revision pass** — BASE-SQL показывает +2pp от финального revision после candidate merge. Если у тебя N кандидатов от голосования, прогони "merge + syntactic repair" LLM pass поверх топ-2 кандидатов, а не просто majority vote.[^5][^3]

**Tier 2: +2–4pp, требует compute**

4. **CSC-SQL паттерн без FT** — взять top-2 из N candidates по частоте + прогнать через "conflict resolution" промпт (объяснить модели оба варианта и попросить аргументированный выбор). Без FT — ослабленная версия, но +1–2pp реалистично.[^3]
5. **M-Schema serialization улучшение** — XiYan-SQL показывает, что semi-structured schema с примерами значений и foreign keys in-line > flat DDL. Если ещё не полностью реализовано — проверь что FK paths и sample values включены для каждой колонки.

**Tier 3: +4–8pp, требует fine-tuning**

6. **GRPO RL fine-tuning Qwen2.5-Coder-7B на BIRD train** — CSC-SQL показывает 71.72% на BIRD test с 7B моделью после GRPO. Если есть доступ к A100 на несколько часов — это самый большой прыжок доступный open-source. Код: [github.com/CycloneBoy/csc_sql](https://github.com/CycloneBoy/csc_sql).[^14]

**Tier 4: Negative evidence — не трать время**

- **LIMIT/row_count repair** — ты уже подтвердил: −0.5..−1pp [твои данные]
- **Llama-70B ансамбли без diversity** — если модели коррелированы (одна база), voting не даёт gains[^19]
- **Schema pruning для GPT-4o класса моделей** — NeurIPS 2024 показывает это вредит[^11]
- **WikiSQL-era techniques (component matching, exact match training)** — не переносятся на BIRD dirty data

***

## Spider 2.0: отдельный сигнал

Spider 2.0 (ICLR 2025) — enterprise-level benchmark, 632 задачи, real Snowflake/BigQuery schemas. Максимум ~59% на Snow, ~38% на Lite. Это показывает, что даже лучшие системы не работают на enterprise-scale — что коррелирует с промышленными заявками типа Cortex Analyst и их маркетинговыми "94-99%" цифрами, которые измеряются при наличии semantic model + tribal knowledge, а не zero-shot.[^6][^20][^8]

***

**Ключевой вывод для NL_SQL:** Твои 86.5% на Mini-Dev-200 при \$0 — это результат выше академических open-source SOTA на full dev (максимум ~74–78% без FT). Следующий реальный шаг к +3–5pp без FT — NER-based few-shot retrieval + merge revision. Потолок free-tier без compute для RL/FT — примерно 78–82% на full BIRD dev, т.е. твой Mini-Dev score может уже быть у этого потолка с учётом выборочной дисперсии.
<span style="display:none">[^21][^22][^23][^24][^25][^26][^27][^28][^29][^30][^31][^32][^33][^34][^35][^36][^37][^38][^39][^40][^41][^42][^43][^44][^45][^46][^47][^48][^49][^50][^51][^52][^53][^54][^55][^56][^57][^58][^59][^60][^61][^62][^63][^64]</span>

<div align="center">⁂</div>

[^1]: https://www.wizwand.com/task/text-to-sql

[^2]: https://arxiv.org/abs/2411.08599

[^3]: https://github.com/CycloneBoy/csc_sql

[^4]: https://hyper.ai/en/papers/IQuest

[^5]: https://paperswithcode.com/paper/base-sql-a-powerful-open-source-text-to-sql

[^6]: https://www.linkedin.com/posts/tomasztunguz_gpt-5-achieves-946-accuracy-on-aime-2025-activity-7361540127786979328-hF_s

[^7]: https://tomtunguz.com/spider-2-benchmark-trends/

[^8]: https://promethium.ai/guides/enterprise-text-to-sql-accuracy-benchmarks-2/

[^9]: https://papers.cool/arxiv/2411.08599

[^10]: https://openreview.net/forum?id=CvGqMD5OtX

[^11]: https://neurips.cc/virtual/2024/103140

[^12]: https://openreview.net/forum?id=EURAfiUpVJ

[^13]: https://github.com/cycloneboy/base_sql

[^14]: https://huggingface.co/cycloneboy/CscSQL-Grpo-Qwen2.5-Coder-3B-Instruct

[^15]: https://arxiv.org/abs/2308.15363

[^16]: https://www.vldb.org/pvldb/vol19/p1628-li.pdf

[^17]: https://www.vldb.org/cidrdb/papers/2026/p5-jin.pdf

[^18]: https://github.com/Artessay/NL2SQL-Benchmark

[^19]: https://llm-stats.com/benchmarks/bird-sql-(dev)

[^20]: https://openreview.net/forum?id=XmProj9cPs

[^21]: https://arxiv.org/html/2403.02951v1

[^22]: https://www.vldb.org/pvldb/vol17/p1132-gao.pdf

[^23]: https://aclanthology.org/2023.emnlp-main.99.pdf

[^24]: https://medium.com/dataherald/text-to-sql-benchmarks-and-the-current-state-of-the-art-63dd3b3943fe

[^25]: https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-analyst

[^26]: https://www.reddit.com/r/SaaS/comments/1peyn28/update_benchmarked_our_natural_language_table/

[^27]: https://arxiv.org/html/2510.02350v1

[^28]: https://vldb.org/cidrdb/papers/2026/p5-jin.pdf

[^29]: https://www.youtube.com/watch?v=DB281MC9aU4

[^30]: https://www.reddit.com/r/SideProject/comments/1peymfh/update_benchmarked_our_natural_language_table/

[^31]: https://habr.com/ru/companies/X5Tech/articles/949694/

[^32]: https://aclanthology.org/2025.naacl-long.228.pdf

[^33]: https://em360tech.com/tech-articles/solution-overview-what-cortex-analyst-snowflake

[^34]: https://github.com/bird-bench/mini_dev

[^35]: https://bird-bench.github.io

[^36]: https://arxiv.org/html/2502.10739v1

[^37]: https://github.com/XGenerationLab/XiYan-SQL

[^38]: https://www.sciencedirect.com/science/article/abs/pii/S0957417426001892

[^39]: https://proceedings.iclr.cc/paper_files/paper/2025/file/46c10f6c8ea5aa6f267bcdabcb123f97-Paper-Conference.pdf

[^40]: https://datapace.ai/blog/ai-sql-production-gap

[^41]: https://huggingface.co/cycloneboy/CscSQL-Grpo-XiYanSQL-QwenCoder-3B-2502

[^42]: https://aclanthology.org/2025.findings-acl.982.pdf

[^43]: https://sol.sbc.org.br/index.php/stil/article/download/37823/37601/

[^44]: https://arxiv.org/html/2506.07423v1

[^45]: https://www.computer.org/csdl/proceedings-article/ispa/2025/668400b312/2c0NLdeIkHC

[^46]: https://github.com/SZU-AdvTech-2023/308-Text-to-SQL-Empowered-by-Large-Language-Models-A-Benchmark-Evaluation

[^47]: https://huggingface.co/papers/2411.08599

[^48]: https://www.snowflake.com/en/engineering-blog/arctic-text2sql-r1-sql-generation-benchmark/

[^49]: https://yale-lily.github.io/spider

[^50]: https://openreview.net/pdf/7a17aa3930ef4d006ff699f1ae9c2616fe8c6e60.pdf

[^51]: https://openreview.net/pdf/a580c1b9fa846501c4bbf06e874bca1e2f3bc1d0.pdf

[^52]: https://huggingface.co/papers/2308.15363

[^53]: https://openreview.net/forum?id=gT8JSEFqaS

[^54]: https://arxiv.org/html/2510.14296v2

[^55]: https://arxiv.org/pdf/2411.07763.pdf

[^56]: http://arxiv.org/pdf/2502.10739.pdf

[^57]: https://arxiv.org/pdf/2603.16733.pdf

[^58]: https://spider2-sql.github.io

[^59]: https://contextual.ai/blog/open-sourcing-the-best-local-text-to-sql-system/

[^60]: https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q1-2025

[^61]: https://llm-stats.com/benchmarks/spider

[^62]: https://goldcopd.org/wp-content/uploads/2024/11/GOLD-2025-Report-v1.0-15Nov2024_WMV.pdf

[^63]: https://www.rspb.org.uk/whats-happening/big-garden-birdwatch/results

[^64]: https://github.com/eosphoros-ai/Awesome-Text2SQL

