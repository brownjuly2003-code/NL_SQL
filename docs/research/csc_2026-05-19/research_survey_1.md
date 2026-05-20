<img src="https://r2cdn.perplexity.ai/pplx-full-logo-primary-dark%402x.png" style="height:64px;margin-right:32px"/>

# Сделай research-survey по text-to-SQL benchmarks и узнай, какие системы /

методы / папиры репортили **>90% execution accuracy** (особенно >95%),
на каком бенчмарке, какой ценой. Контекст: у меня pet-проект NL_SQL
(GitHub: brownjuly2003-code/NL_SQL) сейчас на 86.5% EA на BIRD Mini-Dev
n=200 BIRD-official gold (+4.55pp выше публичного \#1 paid AskData+GPT-4o
81.95%), free-tier \$0, codestral baseline 56% + multi-model voting через
helallao Pro bridge. Хочу понять реальную карту "что чем достигалось".

# Что хочу узнать (структурированно)

## 1. Benchmark-map

Перечисли актуальные text-to-SQL бенчмарки и текущие SOTA scores (2024-2026):

- BIRD (Mini-Dev + full dev + test set) — separate scores
- Spider 1.0 / Spider 2.0 / Spider-Realistic / DK / Syn
- KaggleDBQA
- Arcwise-Plat-SQL (corrected BIRD gold)
- Любые новые academic benchmarks 2025-2026 (CRT-SQL, BookSQL, ScienceBenchmark?)

Для каждого: human ceiling, current top paid, current top open-source / free-tier.

## 2. Top-системы пробившие >90% / >95%

Для каждой системы с >90% EA на любом из бенчмарков назови:

- Название (CHESS, CHASE-SQL, DAIL-SQL, MAC-SQL, XiYan-SQL, RSL-SQL, OmniSQL, что ещё)
- Бенчмарк + точный score
- Базовая LLM (GPT-4o / Claude 3.5 Sonnet / Gemini-Pro / fine-tuned open-source?)
- Cost class: paid API / fine-tuned own model / closed proprietary
- **Ключевые техники** (не "RAG" в общем, а конкретно: какой schema-linker, voter, repair pass, planning prompt, ensemble size, etc.)
- Воспроизводимость: есть ли публичный repo, доступна ли inference


## 3. Что приближает к ceiling за \$0 (most important)

Какие техники в публикациях / blog posts / repos показывали **наибольший +pp lift**
именно для free-tier setup'ов (codestral / llama-70b / qwen-32b / kimi / gemini-flash):

- Self-consistency voting (CSC-SQL, что ещё?)
- Schema-linking heuristics
- Few-shot retrieval (similar question → similar SQL)
- Iterative repair / critique passes
- M-Schema / DAIL serialization
- Plan-then-generate (CHASE-SQL divide-and-conquer)
- Fine-tuning small open-source модели на BIRD train

Где есть **измеренные ablation numbers** на BIRD — приведи цифры.

## 4. Что упирается в human ceiling

Если BIRD-human = 92.96% (per BIRD paper) — кто и как пробил >93%?
Делается ли это на:

- corrected gold (Arcwise) — тогда какие conditions
- ensemble of fine-tuned + GPT-4o
- specific narrow databases только
- какой-то trick которого я не знаю


## 5. Cost / accessibility breakdown

По каждому методу укажи:

- API tokens per question (estimate)
- \$/run на full BIRD dev (1534 questions)
- requires fine-tuning compute?
- Open-source code available?


## 6. Что НЕ работает (negative evidence)

Если в литературе есть отрицательные результаты — какие техники активно не помогают
свободному tier (gemini-flash повторяющий gold, llama-70b ансамбли без diversity, etc.)

# Формат ответа

- Таблица «System | Benchmark | Score | Base LLM | Cost class | Key technique | Repo»
на 10-15 строк (топ systems)
- Отдельная секция "Free-tier ceiling estimate 2026" — где реалистично потолок и почему
- Отдельная секция "Что попробовать в NL_SQL чтобы вылезти из 86.5% без paid escalation"
— конкретные идеи с ожидаемым +pp impact
- Источники с ссылками (arXiv ID или URL)


# Что МНЕ уже известно (не дублируй)

- BIRD human = 92.96%
- AskData+GPT-4o = 81.95% (paid top на BIRD при моём scoring)
- Free-tier ceiling эмпирически ~65-70% codestral solo, до 86.5% через multi-model Pro voting
- P3.F JOIN-path linker — design done, ceiling +0.5-1pp realistically (см. docs/p3f_design.md)
- CSC-SQL upgrade — упоминал docs/bird_sota_research.md, нужен fresh number
- DAC prompt switch + M-Schema serialization уже в коде проекта
- LIMIT-discipline prompt patch и row_count_repair node на baseline — оба ЗАКРЫТЫ negative
empirically (n=200 codestral, -0.5..-1pp)


# Глубина

Не делай поверхностный survey. Если для конкретной системы нет источника / public eval
methodology — пометь "claim только в маркетинге, нет independent verification".
Особенно важно про корпоративные системы (Snowflake Cortex, BigQuery NL, AskData) —
часто декларируют 90%+ без воспроизводимого setup'а.

Длина ответа: 1500-2500 слов структурированно. Без воды.

Можно скормить:

- Perplexity Pro (через helallao bridge) — model: claude-sonnet-thinking или gpt-5.2
- Research subagent (/research) — он есть в skills
- Kimi research (если auth жив)
- Прямо Claude.ai / ChatGPT

Сейчас никаких общепринятых систем, которые стабильно дают >90% execution accuracy на полном BIRD / Spider-2.0, не видно; >90% достигается в основном на Spider‑1.0 и на «подчищенных» или узких поднаборах (Template‑Constrained / matched‑set), а для BIRD полные тесты всё ещё в диапазоне ≈70–82% даже у топовых продакшн‑пайплайнов. Ваши 86.5% EA на BIRD Mini‑Dev при free‑tier + голосование — уже сильно ближе к практическому потолку «без платного GPT‑4/Claude», чем кажется по маркетингу.[^1][^2][^3][^4]

Ниже — структурированный обзор по пунктам.

***

## 1. Карта text-to-SQL бенчмарков 2024–2026

### BIRD и производные

- **BIRD (оригинальный dev/test).** Масштабный кросс-доменный бенчмарк (12 751 пар, 95 БД). Человеческий потолок около 93% EA (вы это уже знаете). Текущие лучшие автоматические системы на полном тесте: XiYan‑SQL (75.63% EX), CHASE‑SQL / CHESS‑подобные мультиагентные фреймворки и усиленное RL‑обучение Arctic‑Text2SQL / Agentic SQL, дающие ≈70–82% на разных конфигурациях и метриках. Независимых >90% EA на полном BIRD dev/test не видно.[^5][^6][^2][^7][^8][^3][^1]
- **BIRD-Mini-Dev V2.** Обновлённый sub‑split (780 примеров, из них 500 «high‑quality» SELECT‑only) + bird23‑train‑filtered (≈70% train). Сейчас используется для лёгкой оценки и финтюнинга; серьёзные leaderboard‑метрики всё равно репортятся на полном dev/test.[^9]
- **BIRD‑Ent (enterprise‑вариант).** Перестроенный BIRD с огромными схемами (4000+ колонок) и корпоративными документами (≈1.5М токенов) под DRAG‑парадигму (Dual‑Retrieval‑Augmented‑Generation). Лучшие LLM‑ы дают всего 39.1% EX (BIRD‑Ent) — резкий провал относительно классического BIRD, подчёркивающий разрыв «академия → прод».[^10][^11]
- **BIRD‑INTERACT.** Многотуровый интерактивный бенчмарк, где модель может задавать уточнения, ходить в knowledge‑base и чинить ошибки. Это уже оценка агентных систем, а не one‑shot text‑to‑SQL.[^12]

**Top paid vs open на BIRD (классический):**

- **Top paid:** корпоративные пайплайны AskData+GPT‑4o, Agentar‑Scale‑SQL (Ant Group) и Arctic‑Text2SQL‑R1‑7B находятся в районе 70–82% EX на тесте; при этом большинство цифр идут из блогов/LinkedIn, а не из полностью воспроизводимых статей.[^13][^3][^4]
- **Top open / free‑inference:** XiYan‑SQL (fine‑tuned QwenCoder + multi‑generator ensemble, 75.63% EX), Arctic‑ExCoT (Llama‑3.1‑70B / Qwen‑2.5‑Coder‑32B с RL‑надстройкой, ≈68–69% EX dev/test), OmniSQL‑32B (fine‑tune на SynSQL‑2.5M + BIRD/Spider, outperform GPT‑4o/DeepSeek‑V3 на ряде бенчмарков).[^6][^14][^15][^4]


### Spider 1.0 и Spider 2.0

- **Spider 1.0.** Классический академический бенчмарк (EMNLP‑2018) остаётся «де‑факто» стандартом; человеческий уровень ≈91.2% по Spider‑2.0 paper.[^16]
    - Лучшие закрытые пайплайны: DAIL‑SQL (86.6% EX test c GPT‑4), MAC‑SQL+GPT‑4 (82.8% EX test, 86.75% EM dev), CHESS+GPT‑4 (87.2% EM на тесте).[^17][^18][^19][^1]
    - Лучший открытый single‑model: IQuest‑Coder‑V1‑40B‑Instruct с 92.2% exec acc (Spider overall), что формально пробивает human ceiling, но на относительно простом Spider‑1.0.[^20][^1]
- **Spider‑Realistic / Syn / DK / Lite 2.0.** Это более «грязные» вариации Spider; SOTA:
    - Spider‑Realistic: DCG‑SQL (81.9% EX), FineStep‑4B в районе 88.6% на некоторых измерениях,[^21][^1]
    - Spider‑Syn: FineStep‑4B / MTIR‑SQL‑4B ≈83.1–84.6% EX,[^22][^1]
    - Spider‑DK: SQL‑TRAIL ≈76.8% EX.[^1]
- **Spider 2.0.** Enterprise‑workflow бенчмарк (632 задач, сложные многотуровые пайплайны). Даже сильные code‑агенты на o1‑preview решают лишь 21.3% задач, при том что на Spider‑1.0 тот же стек даёт 91.2%, а на BIRD ≈73%. Это ключевой аргумент против «магических» 90% в продуктивных сценариях.[^23][^24][^16]


### KaggleDBQA, ScienceBenchmark и др.

- **KaggleDBQA.** Реалистичные web‑БД с документацией. SOTA около 64% EA (MNL по Wizwand), далеко от 90%.[^25][^26][^1]
- **ScienceBenchmark.** Три сложные научные БД; топ‑модели, которые берут до ≈85% на Spider, «очень плохо» переносятся сюда (значительно ниже 50%, точные цифры зависят от системы).[^27][^28]
- **BookSQL, SynSQL‑2.5M, SQALE.** Скорее крупные синтетические/полусинтетические корпуса для предобучения (BookSQL, SynSQL‑2.5M, SQALE) — сами по себе как train‑data, а не основные тестовые бенчмарки.[^14][^15]
- **NL2SQL‑BUGs.** Бенчмарк для детекции семантических ошибок в NL2SQL; показывает, что существующие LLM‑ы детектят лишь ≈75% ошибок и находят реальные баги в BIRD.[^29]

**Arcwise‑Plat‑SQL / CRT‑SQL.** Независимой академической публикации или leaderboard’а под такими названиями найти не удалось; похоже, это либо внутренние/маркетинговые наборы, либо переименованные варианты BIRD/Spider без общепринятой методологии.[^30][^11]

***

## 2. Системы с >90% / >95% EA

Ниже — концентрат систем, которые *где‑то* пробивали >90% execution accuracy, плюс несколько чуть ниже, но структурно важных.

### 2.1 Явные >90% EA

1. **IQuest‑Coder‑V1‑40B‑Instruct**
    - **Бенчмарк:** Spider (overall), 92.2% Exec Acc.[^20][^1]
    - **База:** собственный 40B code‑LLM, открытый весами (IQuest‑Coder‑V1‑40B).[^20]
    - **Cost class:** fine‑tuned open‑weight; inference «бесплатно», но требует серьёзный GPU.
    - **Ключевые техники:** масштабное кодовое предобучение, дообучение на text‑to‑SQL (Spider, BIRD и др.), стандартное prompt‑ICL без тяжёлого агентного пайплайна.[^20]
    - **Репо:** модель на HuggingFace.[^20]
    - **Комментарий:** по сути «монолитный» LLM, который сам по себе выходит за human ceiling именно на Spider, но далеко от этого на более сложных бенчмарках (BIRD, Spider‑2.0).[^16]
2. **TeCoD‑SGC (Template Constrained Decoding)**
    - **Бенчмарк:**
        - Spider Non‑Synthesized Matched Set — 97.31% ExM,[^1]
        - BIRD Non‑Synthesized Matched Set — 93.15% ExM, BIRD Synthesized — 90.39% ExM.[^31][^1]
    - **База:** крупные LLM‑ы (в статье обобщённо, обычно GPT‑4‑класс или сильные open‑weights).[^32]
    - **Cost class:** обычно paid API или собственный крупный LLM + NLI‑модель для выбора шаблона.
    - **Ключевые техники:**
        - автоматическое извлечение шаблонов из исторических NL‑SQL пар;
        - NLI‑классификатор для выбора/отбрасывания шаблона;
        - грамматически‑ограниченный декодинг поверх шаблона (partitioned constrained decoding);
        - сильный uplift (до +36% EA на matched‑подмножествах vs чистый ICL).[^31][^32]
    - **Репо:** код обещан/частично доступен на OpenReview, но полноценного OSS‑пайплайна пока нет.[^31]
    - **Важная оговорка:** >95% достигается только на искусственно «matched» поднаборах, где запросы сильно похожи на train‑историю; это не равно full‑benchmark.
3. **BiomedSQL (domain‑specific)**
    - **Бенчмарк:** BiomedSQL test — 90% EX (по Wizwand).[^1]
    - **База:** специализированные мед‑модели (деталей мало).
    - **Cost class:** вероятно закрытый / корпоративный.
    - **Ключевые техники:** доменный финтюн на биомед SQL‑парах.
    - **Репо:** публичного кода и прозрачной методологии не видно; воспринимать как «узкодоменный special case».[^1]

### 2.2 Сильные, но <90% (структурно важные)

Ниже системы, которые не пробивают 90%, но SOTA на BIRD/Spider‑вариантах и задают планку по техникам.

#### Таблица топ‑систем (10+ штук)

| System | Benchmark | Score (metric) | Base LLM | Cost class | Key technique (очень коротко) | Repo |
| :-- | :-- | :-- | :-- | :-- | :-- | :-- |
| IQuest‑Coder‑V1‑40B | Spider | 92.2 Exec Acc[^1][^20] | 40B code LLM | Fine‑tuned open | Масштабный code‑pretrain + text‑to‑SQL SFT | HF model card[^20] |
| TeCoD‑SGC | Spider/BIRD matched sets | 97.31 / 93.15 / 90.39 ExM[^1][^31] | GPT‑4‑class | Paid API / big local | Template selection + grammar‑constrained decoding | OpenReview code (частично)[^31] |
| XiYan‑SQL | BIRD test; Spider test | 75.63% EX (BIRD); 89.65% EX (Spider)[^6][^33] | Fine‑tuned QwenCoder‑style | Own finetune | Multi‑generator ensemble, M‑Schema, selection model | GitHub XGenerationLab/XiYan‑SQL[^33] |
| MARS‑SQL | BIRD dev; Spider test | 77.84% EX (BIRD dev); 89.75% EX (Spider test)[^34][^35] | Strong LLM (неявно GPT‑4‑класс) | Paid / heavy RL | Multi‑agent RL: schema linker, generator, validator, ReAct‑loop | ICML’26 code repo (анонсирован)[^34] |
| CHASE‑SQL | BIRD test | 73.0% EX test (SOTA на момент submission)[^5] | GPT‑4 | Paid API | Divide‑and‑conquer planning, multi‑agent generation + selection LLM | OpenReview + GitHub (переход по paper)[^5] |
| CHESS | BIRD test | 71.10% EX test без доп. финтюна[^7][^36] | GPT‑4 / Llama‑3‑70B | Paid / own | 4 агента: IR, Schema Selector, Candidate Generator, Unit Tester; schema pruning ×5 сокращает токены | Stanford CHESS repo[^36] |
| MAC‑SQL + GPT‑4 | BIRD test; Spider | 59.59% EX (BIRD test), 82.8% EX (Spider test), 86.75% EM dev[^18][^1] | GPT‑4 | Paid API | Multi‑agent decomposition + агрессивный schema‑filtering | GitHub wbbeyourself/MAC‑SQL[^18] |
| DAIL‑SQL + GPT‑4 | Spider test | 86.6% EX test; ≈1600 токенов/вопрос на Spider‑dev[^17][^19] | GPT‑4 | Paid API | SQL‑encoded knowledge, skeleton‑based example selection, self‑consistency voting | Code на GitHub (ссылка в paper)[^19] |
| Agentic SQL / SQL‑ASTRA | BIRD | +5pp vs GRPO baseline; превосходит Arctic‑Text2SQL‑R1‑7B при той же модели[^37][^8] | Arctic‑Text2SQL‑R1‑7B | Fine‑tuned open | ATR + CSMR reward shaping, multi‑turn RL‑агент | arXiv:2603.16161 (код анонс)[^8] |
| Arctic‑Text2SQL‑R1 | BIRD test | до 71.83% EX test, \#1 на BIRD leaderboard в 2025[^3] | 7B Qwen‑/Llama‑based | Fine‑tuned open | GRPO‑обучение с execution‑reward’ом, curated data | HF: Snowflake Arctic‑ExCoT серии[^4] |
| Arctic‑ExCoT‑70B / Qwen‑32B | BIRD dev/test | ≈68.5% EX dev/test; +11pp к базовой модели[^4] | Llama‑3.1‑70B / Qwen‑2.5‑Coder‑32B | Fine‑tuned open | RL‑CoT (ExCoT), single‑model single‑inference SOTA | HF Snowflake/*‑Arctic‑ExCoT‑* [^4] |
| OmniSQL‑32B | BIRD, Spider, Spider‑Realistic | превосходит GPT‑4o и DeepSeek‑V3 на многих наборах (точные EA по таблице в paper)[^9][^15] | 7/14/32B open LMs | Fine‑tuned open | Предобучение на SynSQL‑2.5M (+CoT) + SFT на BIRD/Spider | GitHub RUCKBReasoning/OmniSQL[^38][^15] |
| CSC‑SQL (3B/7B) | BIRD dev | 65.28% EX (3B), 69.19% EX (7B) на dev[^39] | 3B/7B open LMs | Fine‑tuned open | Corrective self‑consistency: N‑sampling, merge‑revision, GRPO RL | GitHub CycloneBoy/csc_sql (анонс)[^39] |
| MTIR‑SQL‑4B | BIRD dev; Spider dev | 64.4% EX (BIRD dev), 84.6% EX (Spider dev)[^22] | 4B open LM | Fine‑tuned open | Multi‑turn Tool‑Integrated RL, execution‑aware reasoning | arXiv:2510.25510 (код заявлен)[^22] |

(В таблицу не влезли XiYan‑SQL‑CRITIC, Agentar‑Scale‑SQL и др., но по уровню EA они в тех же диапазонах 70–82% на BIRD.)[^33][^13]

***

## 3. Техники с наибольшим lift для free‑tier LLM’ов

Фокус: именно то, что даёт измеряемый прирост на BIRD/Spider при работе с открытыми или дешёвыми моделями.

### 3.1 Self-consistency / voting / CSC‑SQL

- Классический self‑consistency (DAIL‑SQL) даёт +0.4–1pp на Spider test поверх лучшего single‑shot prompting (с 86.2 до 86.6 EX через voting GPT‑4).[^19][^17]
- CSC‑SQL показывает более существенный gain для open‑моделей: 3B‑модель после RL‑обучения и двухшагового merge‑revision выходит на 65.28% EX на BIRD dev, 7B — на 69.19% EX, опережая базовые self‑consistency модели на несколько p.p. (авторы подчёркивают «значительное» улучшение).[^40][^39]
- Методика: N параллельных семплов, группировка по execution‑результату, выбор двух крупнейших групп, merge‑revision шаблон с обоими SQL + их результатами, генерация M новых кандидатов, вновь self‑consistency → RL (GRPO) обучает генератор и ревизор.[^39][^40]

**Практический вывод для free‑tier:**
Уже один extra pass «merge‑revision» поверх вашего текущего многомодельного голосования (вместо простого majority vote) может дать +2–4pp EA, если реализовать это даже на codestral/Qwen‑32B без RL‑обучения, за счёт более умного комбинирования уже сгенерированных вариантов.

### 3.2 Schema-linking и M‑Schema / структурная сериализация

- **MAC‑SQL.** За счёт агрессивного фильтра schema (таблицы/колонки) и decomposition на подзадачи MAC‑SQL+GPT‑4 поднимается с 46.35% EX (vanilla GPT‑4) до 59.59% EX на BIRD test — +13.2pp; на dev BIRD — 70.28% EA.[^18][^1]
- **XiYan‑SQL.** Вводит M‑Schema — полу‑структурное представление схемы (JSON‑подобное, с отношениями, алиасами, типами) — и ensemble из нескольких fine‑tuned генераторов с разными «предпочтениями»; итог — 75.63% EX на BIRD и 89.65% на Spider test.[^6][^33]
- **JOLT‑SQL.** Совмещает schema linking и SQL‑генерацию в одном loss (joint SFT), показывая, что разумная дискриминативная привязка схемы повышает robustness к noisy schema.[^41]

**Вывод:**
Для free‑tier моделек схематический uplift почти бесплатен: жёсткий lexical/value‑linker + M‑Schema‑подобная сериализация (с явным списком ключей, FK и синонимов) обычно даёт +2–5pp EA относительно «сырой DDL‑дамп» даже без смены модели.[^18][^6]

### 3.3 Few-shot retrieval / skeleton‑based ICL

- **DAIL‑SQL.** Показывает, что выбор примеров по skeleton‑similarity (структуре SQL) и фильтрация cross‑domain примеров дают значимый gain при фиксированном budget (≈1600 токенов/вопрос на Spider).[^17][^19]
- По их таблицам: лучшие комбинации question representation + example selection + organization дают ощутимый uplift относительно «рандомных» few‑shot примеров, особенно на сложных запросах.[^19]
- **OmniSQL / SynSQL‑2.5M.** Хотя OmniSQL в inference режиме работает без сложного ICL, paper подчёркивает, что разнообразие skeleton’ов в pretrain’е (2.19M уникальных skeleton’ов) критично для устойчивости к структуре запросов.[^15][^14]

**Вывод:**
Дешёвый, но эффективный шаг для NL_SQL — заменить «ручные» few‑shot‑примеры на retrieval по skeleton+NL‑similarity из bird23‑train‑filtered или из собственной истории ошибочных кейсов (k‑NN по embed’ам, ранжирование по совпадению SQL‑паттернов). Это способно дать +2–4pp при том же количестве токенов.[^17][^19]

### 3.4 План → генерация (divide-and-conquer)

- **CHASE‑SQL.** Делит задачу на под‑планы и использует нескольких агентов (planner, decomposer, generator, selection), что даёт 73.0% EX на BIRD test и SOTA на момент публикации.[^5]
- **Chain‑of‑Thought prompting для text‑to‑SQL.** Специальное CoT‑style prompting без лишнего «least‑to‑most» даёт +5.2pp на Spider dev и +6.5pp на Spider‑Realistic по сравнению с стандартным prompting, но более сложные CoT‑цепочки ухудшают результат из‑за error propagation.[^42][^5]

**Вывод:**
Лёгкий план на уровне «сначала текстовое описание join‑пути/агрегации, затем SQL» и/или decomposed prompts по подзадачам (schema linking, фильтры, group by) — дешёвый способ вытащить +2–3pp на сложных запросах, особенно если planner работает на более дешёвой модели, а генератор — на сильной.

### 3.5 RL и agentic SQL (для ориентира)

- **Agentic SQL / SQL‑ASTRA.** Вводит ATR (Aggregated Trajectory Reward) + CSMR (Column‑Set Matching Reward), что даёт +5pp EA на BIRD относительно бинарного GRPO, при этом outperform Arctic‑Text2SQL‑R1‑7B при той же базе.[^37][^8]
- **MARS‑SQL / MTIR‑SQL.** Мультиагентные RL‑фреймворки, использующие ReAct‑loop, промежуточное исполнение SQL и tool‑integration, выводят 4B–12B модели на ≈64–78% BIRD dev и ≈84–90% Spider dev/test.[^34][^35][^22]

Для вашего «no paid escalation» это больше ориентир, чем прямой рецепт: RL‑обучение потребует своего GPU‑кластера, но идеи (column‑set reward, multi‑turn refinement с execution feedback) можно частично реализовать как эвристики без RL.

***

## 4. Кто и как приближается / превышает human ceiling

### BIRD vs human

- Анализ шума в BIRD‑Bench показывает, что исходные gold‑SQL содержат значимое число ошибок и неоднозначностей; при исправленных gold‑записях и вопросах переранжирование моделей радикально меняется, и простые zero‑shot GPT‑3.5/4 становятся конкурентны сложным пайплайнам DIN‑SQL и MAC‑SQL.[^43][^1]
- Авторы прямо отмечают, что текущий gap «LLM (≈65%) vs человек (≈93%)» во многом искажается noise‑эффектами, и что benchmark как минимум частично «сломлен».[^44][^1]


### Есть ли >93% на BIRD?

- На полном BIRD dev/test независимо подтверждённых >93% EA нет; лучшие значения — в районе 75–82% для XiYan‑SQL, Agentar‑Scale‑SQL, Arctic‑Text2SQL‑R1, CHASE‑SQL/CHESS‑подобных систем.[^7][^3][^13][^6]
- >93% ExM есть только у TeCoD‑SGC на **BIRD Non‑Synthesized Matched Set** — аккуратно подобранном поднаборе, где каждый новый запрос хорошо «матчится» на исторический шаблон; это скорее оценка upper bound «template‑reuse» при повторяющихся workload’ах.[^31][^1]
- Корпоративные заявления «90%+ на BIRD / enterprise SQL» (Snowflake Cortex, BigQuery NL, AskData и др.) либо вообще не дают методологию, либо приводят только относительные улучшения против baseline‑а; ни одного публичного, воспроизводимого leaderboard‑результата >90% EX на полном BIRD/Spider‑2.0 не обнаружено.[^45][^46]


### Spider‑1.0 как «ложный ceiling»

- Spider‑1.0 действительно уже «закрыт»: IQuest‑Coder‑V1‑40B‑Instruct показывает 92.2% exec acc, XiYan‑SQL — 89.65%, MARS‑SQL — 89.75% и т.д.[^34][^6][^1]
- Spider‑2.0 при этом демонстрирует, что тот же стек на реальных enterprise‑workflow’ах падает до ≈21% task success даже у сильных код‑агентов; то есть «>90% на Spider‑1.0» никак не означает «решили text‑to‑SQL».[^24][^16]

***

## 5. Стоимость и доступность (очень грубо)

Оценка токенов и \$ очень приблизительная, где есть конкретика — ссылаюсь, где нет — описываю порядок, а не цифры.

- **Single‑shot / лёгкий CoT (IQuest‑Coder‑V1, OmniSQL).**
Один forward пасс ≈1–2k токенов (schema + вопрос + CoT). Для BIRD dev (1534 вопроса) это ≈1.5–3M токенов. При локальном запуске — только ваша электроэнергия; при API ценообразовании GPT‑4‑класса это несколько десятков долларов за полный прогон.[^15][^20]
- **DAIL‑SQL.** Репортирует ≈1600 токенов/вопрос на Spider‑dev при оптимизированном prompt’е (вопрос + примеры). На BIRD dev ожидайте 2–3k токенов/вопрос (схемы крупнее). При GPT‑4‑тарифах — десятки долларов за прогон, без учёта self‑consistency.[^17]
- **MAC‑SQL, CHESS, CHASE‑SQL, MARS‑SQL.**
    - Multi‑agent, multi‑candidate, execution‑aware; количество LLM‑звонков растёт ×5–×10 против single‑shot. CHESS сообщает сокращение токенов ×5 благодаря schema‑selector, но при использовании нескольких агентов итоговый budget всё равно выше single‑shot.[^36][^7]
    - BIRD dev в таком режиме легко уходит в десятки миллионов токенов → сотни долларов на GPT‑4/Claude‑классе.
- **TeCoD‑SGC.**
Требует отдельную NLI‑модель и грамматически‑ограниченный декодер; в matched‑режиме токены сопоставимы с ICL + небольшой overhead, но реальная стоимость — в необходимости иметь историю NL‑SQL и обученный NLI‑селектор.[^32]
- **RL‑подходы (Agentic SQL, MARS‑SQL, MTIR‑SQL, CSC‑SQL).**
Обучение: десятки/сотни GPU‑часов (3B–32B моделей) + множественные проходы по BIRD/Spider; inference после обучения — как у single‑ или multi‑turn агента (обычно ×3–×8 к single‑shot).[^8][^39][^22][^34]

**Open‑source доступность:**

- DAIL‑SQL, MAC‑SQL, CHESS, OmniSQL, XiYan‑SQL, MTIR‑SQL, SQL‑ASTRA/Agentic SQL, CSC‑SQL — либо уже имеют OSS‑репозитории, либо авторы прямо обещают выкладку кода.[^33][^39][^7][^8][^22][^18][^19][^15]
- TeCoD‑SGC, корпоративные системы (AskData, Snowflake Cortex, BigQuery) — маркетинговые заявления без полноценных OSS‑пайплайнов; нужно относиться как к «black‑box claims».[^46][^45][^32]

***

## 6. Что явно не работает (по литературе и данным)

### Глубокий CoT и сложные цепочки

- EMNLP‑работа по CoT‑prompting для text‑to‑SQL показывает, что least‑to‑most и чрезмерно подробные reasoning‑шаги дают **хуже** результат из‑за накопления ошибок; лучшие результаты даёт более компактный CoT‑стиль (+5.2pp / +6.5pp относительно стандартного prompting, но без многократной итерации).[^42]


### Переинжиниринг под noisy gold

- Анализ BIRD‑Bench показывает, что сложные пайплайны DIN‑SQL / MAC‑SQL выигрывают у zero‑shot на исходном noisy наборе, но **теряют преимущество** или проигрывают после исправления gold‑SQL и вопросов: zero‑shot GPT‑3.5/GPT‑4 выравниваются или переигрывают их, что говорит о частичном overfitting к шуму/артефактам, а не реальной «понимающей» генерации.[^43][^1]


### «Механическое» усиление ансамбля без diversity

- Те же работы и практические отчёты (включая NL2SQL‑BUGs) показывают, что просто наращивать число кандидатов однотипной модели (без разнообразия схем сериализации, prompt‑стилей и т.п.) даёт diminishing returns и даже ухудшения: модель повторяет одну и ту же семантическую ошибку во множестве вариантов SQL.[^29][^1]

***

## Free-tier ceiling estimate на 2026 год

Если под free‑tier понимать «без платных GPT‑4o/Claude API, но с возможностью гонять открытые 7–32B модели и делать ограниченный финтюн», то картина примерно такая:

- **Spider‑1.0:** IQuest‑Coder‑V1‑40B и OmniSQL‑32B уже показывают, что открытые модели могут выйти на 90%+ на этом конкретном бенчмарке. ceiling здесь ≈95% при комбинации fine‑tune + лёгкие агентные техники.[^15][^1][^20]
- **BIRD (classic dev/test):** лучшие полностью открытые стеки (XiYan‑SQL, OmniSQL‑32B, Arctic‑ExCoT) находятся в диапазоне 68–76% EX без платного API. При добавлении более агрессивного voting/repair/templating (CSC‑SQL, TeCoD‑подобные идеи) разумный ceiling для free‑tier выглядит как **≈80–85%** на полном dev/test, если вы готовы:[^4][^6][^15]
    - держать одну–две BIRD‑тюнинговые модели (7–32B) локально,
    - инвестировать в хорошие schema‑linkers, retrieval‑ICL и лёгкие agent loops.
- **Enterprise‑варианты (BIRD‑Ent, Spider‑2.0, ScienceBenchmark, KaggleDBQA):** здесь ни у кого нет даже 80%; лучшая открытая карта — 39.1% BIRD‑Ent, 60.5% Spider‑Ent, очень низкие числа на ScienceBenchmark и KaggleDBQA. Для free‑tier ceiling здесь честный диапазон **≈40–60%** в зависимости от задачи.[^11][^28][^10][^25][^27]

На фоне этого ваш результат 86.5% EA на BIRD Mini‑Dev (free‑tier мультимодельное голосование) выглядит как работа в направлении узкого matched‑сабсета (похожего на TeCoD‑matched‑set) с локальным ceiling в районе 90%, но по полной dev/test‑карте индустрия пока туда не добралась даже с GPT‑4‑классом.[^9][^31][^1]

***

## Что попробовать в NL_SQL, чтобы вылезти из 86.5% без paid escalation

Ниже — только то, что опирается на опубликованные uplift’ы и реалистично реализуемо с free‑tier моделями.

### 1. CSC‑style merge‑revision поверх вашего голосования (+2–4pp)

- Ваша текущая схема — multi‑model voting с majority‑vote. CSC‑SQL показывает, что даже для одиночной модели переход к схеме «N семплов → группировка по execution result → merge‑revision двух топ‑кандидатов → ещё один раунд self‑consistency» даёт заметный прирост.[^40][^39]
- Реализация:
    - оставить текущие N кандидатов от codestral/других free‑LLM;
    - сгруппировать по (нормализованному) SQL или по execution‑результату;
    - взять два наиболее крупные кластера и скормить их в отдельный revision‑prompt (на более дешёвой модели; можно той же codestral/Qwen‑7B), примерно в духе CSC‑SQL merge template;
    - снова проголосовать M ревизованных кандидатов.
- Поскольку ваш baseline уже использует многомодельность, этот шаг даёт прирост именно **качества агрегации** (исправление систематических ошибок), а не только «больше выборок» → по аналогии с CSC‑SQL можно ожидать **+2–4pp EA на Mini‑Dev**, пока не упрётесь в шум/gold.


### 2. TeCoD‑подобный template cache для повторяющихся паттернов (+1–3pp глобально, намного больше на частых шаблонах)

- В ваших логах наверняка уже видно, что значительная часть запросов на BIRD Mini‑Dev / dev опирается на несколько десятков типовых skeleton’ов (simple group‑by, top‑k, 2‑3‑join, conditional aggregation и т.п.).
- TeCoD показывает, что для matched‑subset’ов можно дойти до 93–97% ExM, если **узнать** нужный шаблон и жёстко его enforce‑нуть.[^32][^31][^1]
- Практическая схема:
    - собрать библиотеку (NL, SQL, skeleton, DB id) из всех train/dev кейсов;
    - обучить маленький NLI‑классификатор (или просто использовать cosine‑similarity + порог) для выбора кандидатов‑шаблонов;
    - если есть высокий confidence match, генерировать только заполнители (WHERE‑условия, literals) поверх skeleton, а не весь SQL;
    - дополнительно можно hard‑constraint’ить декодер (regexp/CFG) в «рамках шаблона».
- Это особенно эффективно на «частых» шаблонах; по TeCoD‑результатам uplift на matched‑части может быть двузначным, а глобально — **+1–3pp** при условии, что matched‑часть существенна.[^32][^31]


### 3. Retrieval‑based few‑shot по skeleton+NL (+2–4pp, почти бесплатно)

- Перейти от статичных примеров к DAIL‑SQL‑подобному retrieval:
    - взять bird23‑train‑filtered как основное хранилище,[^9]
    - хранить embedding’и NL‑вопросов + hash skeleton’ов,
    - для нового вопроса искать k ближайших примеров **из той же БД** с похожим skeleton и использовать их как few‑shot контекст (вместо либо в дополнение к DAC‑prompt).[^19][^17]
- DAIL‑SQL демонстрирует, что грамотный выбор примеров по skeleton‑similarity даёт ощутимый uplift при том же токен‑бюджете, особенно в сложных запросах.[^19]
- В вашем случае это почти бесплатно по compute (одно дополнительное ANN‑поиск + более информативный контекст) и реалистично даёт **+2–4pp** на dev/mini‑dev.


### 4. Усиленный schema linking + M‑Schema‑лайт (+1–2pp)

- Вы уже используете DAC и какую‑то сериализацию; можно добавить элементы XiYan‑style M‑Schema:
    - явный список PK/FK и их текстовые описания;
    - нормализованные и расширенные названия колонок (с учётом синонимов и словарей из документации);
    - компактные JSON‑блоки по таблицам вместо голого DDL.
- MAC‑SQL и XiYan‑SQL показывают, что улучшенный schema context даёт двузначные uplift’ы на слабых базовых LLM (GPT‑4 vs vanilla, QwenCoder vs base), причём часть эффекта достигается чисто инженерией.[^6][^18][^33]
- Если у вас уже есть P3.F JOIN‑path linker, добавить M‑Schema‑лайт и value‑based linking (по часто встречающимся литералам/категориям) может дать **ещё +1–2pp**.


### 5. Минимальный agent loop с execution‑feedback (+1–2pp)

Без RL, но с идеями Agentic SQL / MTIR‑SQL:

- Для запросов, где execution возвращает пустой/очевидно неправильный результат (0 строк при ожидаемых >0, агрегаты NaN/inf), запускать один «repair pass»:
    - prompt: NL вопрос + текущий SQL + результат исполнения (пример результата) + схема;
    - задача: объяснить, почему результат не соответствует вопросу, и предложить откорректированный SQL.
- Подобный single‑step self‑correction уже используется в DIN‑SQL/MAC‑SQL и даёт свой вклад; RL‑подходы просто усиливают это.[^8][^22][^18][^1]
- По аналогии с опубликованными абляциями, такой лёгкий loop (1 дополнительный вызов на «сомнительные» кейсы) может дать **+1–2pp** при относительном удорожании на 20–30% токенов.


### 6. Добавить один специализированный open‑source voter (OmniSQL‑7B / Arctic‑ExCoT‑7B) (+1–3pp)

- OmniSQL‑7B/14B/32B и Arctic‑ExCoT‑32B уже fine‑tuned под BIRD/Spider и свободно доступны; они дают глобально более высокую базовую EA, чем кодовые LLM вроде codestral, при сравнимом размере.[^4][^15]
- Подключение, скажем, OmniSQL‑7B как ещё одного участника в вашем существующем мультимодельном голосовании может добавить diversity в тех случаях, где codestral/прочие free‑LLM систематически ошибаются.
- Ожидаемый uplift, если удастся гонять хотя бы 7B‑вариант на GPU, — **+1–3pp** на Mini‑Dev за счёт лучшей базы на сложных схемах, без изменения логики пайплайна.

***

Если вам будет полезно, можно дальше углубиться в конкретный дизайн CSC‑style merge‑revision и TeCoD‑подобного шаблонного слоя именно поверх вашего текущего NL_SQL (учитывая существующий DAC, M‑Schema и P3.F‑linker), с расчётом прироста и токен‑бюджета по шагам.
<span style="display:none">[^47][^48][^49][^50][^51][^52][^53][^54][^55][^56][^57][^58][^59][^60][^61][^62][^63][^64][^65][^66][^67][^68][^69][^70][^71][^72][^73][^74]</span>

<div align="center">⁂</div>

[^1]: https://www.wizwand.com/task/text-to-sql

[^2]: https://neurips.cc/virtual/2023/poster/73529

[^3]: https://www.linkedin.com/posts/snowflake-developers_arctic-text2sql-r1-hit-1-on-the-bird-activity-7334279712006930432-MeDO

[^4]: https://huggingface.co/Snowflake/Qwen-2.5-coder-Arctic-ExCoT-32B

[^5]: https://openreview.net/pdf?id=CvGqMD5OtX

[^6]: https://arxiv.org/abs/2411.08599

[^7]: https://icml.cc/virtual/2025/49375

[^8]: https://arxiv.org/abs/2603.16161

[^9]: https://github.com/bird-bench/mini_dev

[^10]: https://openreview.net/pdf?id=gXkIkSN2Ha

[^11]: https://openreview.net/forum?id=gXkIkSN2Ha

[^12]: https://openreview.net/forum?id=nHrYBGujps

[^13]: https://www.linkedin.com/posts/sanjayjain22_agentar-scale-sql-advancing-text-to-sql-activity-7382619994108477440-6Q9F

[^14]: https://medium.com/@wolffcornelius/comparing-large-scale-text-to-sql-datasets-3e8d28c4c06d

[^15]: https://github.com/RUCKBReasoning/OmniSQL/blob/main/README.md

[^16]: https://chatpaper.com/chatpaper/paper/111294

[^17]: https://github.com/SZU-AdvTech-2023/308-Text-to-SQL-Empowered-by-Large-Language-Models-A-Benchmark-Evaluation

[^18]: https://www.wizwand.com/paper/68fa77761e209131cea7349e

[^19]: https://arxiv.org/abs/2308.15363

[^20]: https://hyper.ai/de/papers/IQuest

[^21]: https://www.themultiphysicsjournal.com/index.php/ijm/article/download/1570/954/3534

[^22]: https://arxiv.org/abs/2510.25510

[^23]: https://openreview.net/forum?id=XmProj9cPs

[^24]: https://www.semanticscholar.org/paper/Spider-2.0:-Evaluating-Language-Models-on-Workflows-Lei-Lei/ab649ecce8e85a7ac00e1cce9c1e4b605c1d8d0a

[^25]: https://aclanthology.org/2021.acl-long.176/

[^26]: https://arxiv.org/abs/2106.11455

[^27]: https://www.citedrive.com/en/discovery/sciencebenchmark-a-complex-real-world-benchmark-for-evaluating-natural-language-to-sql-systems/

[^28]: https://arxiv.org/abs/2306.04743

[^29]: https://nl2sql-bugs.github.io

[^30]: https://www.vldb.org/cidrdb/papers/2026/p5-jin.pdf

[^31]: https://arxiv.org/pdf/2604.28028.pdf

[^32]: https://arxiv.org/abs/2604.28028v1

[^33]: https://github.com/XGenerationLab/XiYan-SQL

[^34]: https://icml.cc/virtual/2026/poster/65053

[^35]: https://huggingface.co/papers/2511.01008

[^36]: https://scalingintelligence.stanford.edu/pubs/CHESSpaper/

[^37]: https://arxiv.org/pdf/2603.16161.pdf

[^38]: https://github.com/RUCKBReasoning/OmniSQL

[^39]: https://huggingface.co/papers/2505.13271

[^40]: https://www.themoonlight.io/en/review/csc-sql-corrective-self-consistency-in-text-to-sql-via-reinforcement-learning

[^41]: https://arxiv.org/html/2505.14305v1

[^42]: https://openreview.net/forum?id=gAzBhetShk\&noteId=5VDvwutS8o

[^43]: https://aclanthology.org/2024.acl-short.34/

[^44]: https://vldb.org/cidrdb/papers/2026/p5-jin.pdf

[^45]: https://contextual.ai/blog/open-sourcing-the-best-local-text-to-sql-system/

[^46]: https://www.snowflake.com/en/engineering-blog/arctic-text2sql-r1-sql-generation-benchmark/

[^47]: https://huggingface.co/papers/2402.12243

[^48]: https://bird-bench.github.io/?trk=public_post_main-feed-card-text

[^49]: https://bird-bench.github.io

[^50]: https://www.scribd.com/document/841443798/13657-Spider-2-0-Can-Language

[^51]: https://arxiv.org/pdf/2402.12243.pdf

[^52]: https://stream.eastsidefm.org/html/2405.16755v3

[^53]: https://aclanthology.org/2024.acl-short.34.pdf

[^54]: https://www.semanticscholar.org/paper/CHESS:-Contextual-Harnessing-for-Efficient-SQL-Talaei-Pourreza/421f82e616d887ec008d88be580459edba96c271

[^55]: https://www.databricks.com/blog/what-is-medallion-architecture

[^56]: https://github.com/DEEP-PolyU/Awesome-LLM-based-Text2SQL

[^57]: https://www.benthicsoftware.com/golden.html

[^58]: https://openproceedings.org/2025/conf/edbt/paper-41.pdf

[^59]: https://www.reddit.com/r/LangChain/comments/1ijw334/texttosql/

[^60]: https://arxiv.org/abs/2411.07763

[^61]: https://www.linkedin.com/posts/skphd_spider-20-text-to-sql-workflows-activity-7263055030721613824-eV9I

[^62]: https://www.semanticscholar.org/paper/KaggleDBQA:-Realistic-Evaluation-of-Text-to-SQL-Lee-Polozov/9cd3d6eef7c574830be410598c3024191ee974d4

[^63]: https://www.bers.nyc.gov/assets/finance/downloads/pdf/reports/issuers_allocation/2015/gct2015_part2.xlsx

[^64]: https://www.linkedin.com/posts/tomasztunguz_gpt-5-achieves-946-accuracy-on-aime-2025-activity-7361540127786979328-hF_s

[^65]: https://huggingface.co/datasets/micpst/bird/viewer/default/dev?p=3

[^66]: https://arxiv.org/html/2506.07423v1

[^67]: https://github.com/AlibabaResearch/DAMO-ConvAI/issues/39

[^68]: https://www.reddit.com/r/SideProject/comments/1peymfh/update_benchmarked_our_natural_language_table/

[^69]: https://github.com/cuplv/text-to-sql-wizardcoder

[^70]: https://www.reddit.com/r/LocalLLM/comments/1n5qebf/sql_benchmarks_how_ai_models_perform_on_texttosql/

[^71]: https://zenodo.org/records/5205322

[^72]: https://arxiv.org/html/2405.07467v1

[^73]: https://www.lights.co.uk/p/spider-pendant-light-in-black-7-bulb-10003663.html

[^74]: https://github.com/taoyds/spider

