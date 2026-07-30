# codemap — Бэклог

**Тип:** Живой бэклог реализации. **Рамка:** `DESIGN.md` (дизайн v1 закрыт, решения §10 приняты).
**Статус:** ✅ **M0 + M1 + M1.5 + M4 + M5 + M2 + M6 + M7 + M8–M16 сделаны** (M8–M12 — 2026-07-29,
findings глубокой обкатки F8/F4/F3/F7/F6; M13 — serve-эргономика F9–F13; M14 — 2026-07-30, soundness B1
F14/F15: `canonical`-ambiguity + column access-form, схема 0.9; M15 — diff/change-review A11 F16/F17:
локация→символ + change-set-ревью, `codemap review`; M16 — архитектура A9 F18–F21: слои/coupling/хотспоты,
`report architecture`) + **M3.1** тёплый serve-режим (граф в памяти, JSON-стдио). Осталось (отложено как
преждевременное) — **M3.2/M3.3** (freshness-watcher, SQLite), **двух-графовый diff** (added/deleted
символы) и тонкий MCP-адаптер — брать при живом потребителе/масштабе.

Вехи от «тонкого сквозного среза» к расширению. Внутри вехи задачи упорядочены по зависимости.
Отсылки `§N` — разделы `DESIGN.md`.

---

## M0 — Тонкий срез: API-surface (доказать конвейер) ✅

**Цель:** `codemap build <path>` → `graph.json` → markdown-отчёт API-поверхности, на `bquant`.
Самое маленькое сквозь весь конвейер Extract→Build→Store→Serve (§8).

- [x] **M0.1 Каркас пакета** — `codemap/codemap/` (§9), `pyproject.toml`, зависимость `griffe`,
      `codemap/tests/`, `.gitignore`, свой `.venv` (uv). Вне wheel `bquant` (whitelist).
- [x] **M0.2 Extract (griffe-адаптер)** — `extract/griffe_extractor.py`: статический разбор (без импорта),
      модули/классы/функции/атрибуты, сигнатуры, докстринги, публичность (`__all__`/`_`), депрекация
      по декоратору `@deprecated` (§3, §10.2). Алиасы/импорт-рёбра — M1.
- [x] **M0.3 Модель** — `model.py`: нейтральные `Node`/`Edge`/`Graph`, открытые kind, детерминированный
      `to_dict` (сортировка, без таймстампов; `codemap_schema`) (§2/§2.2).
- [x] **M0.4 Store** — `store.py`: канонический `graph.json` (JSON, диффабельный).
- [x] **M0.5 Report (вид D)** — `serve/api_surface.py`: markdown — публичные символы по модулям +
      сигнатуры + докстринги + маркер deprecated (§4.1-D).
- [x] **M0.6 CLI** — `cli.py`: `codemap build <path>`, `codemap report api-surface`; JSON по умолчанию,
      exit-коды (§6, §14.1).
- [x] **M0.7 Тесты на bquant** — 6 тестов зелены: 1709 узлов; `analyze_zones` верная сигнатура;
      `MACDZoneAnalyzer` deprecated; детерминизм; roundtrip; отчёт корректен.

**DoD:** ✅ на `bquant` end-to-end даёт корректный детерминированный API-surface отчёт.
Результат: 1709 узлов (89 mod / 126 cls / 863 fn / 631 attr), 6/6 тестов.

---

## M1 — Queryable граф + каталог запросов (§1) ✅

**Цель:** от одного отчёта — к графу, отвечающему на каталог §1.

- [x] **M1.1 Рёбра импортов** — griffe резолвит относительные (5-точечные) в абсолютные; экстрактор
      сводит к module→module `imports`-рёбрам (241 на bquant), внешние отсекаются (§3.1).
- [x] **M1.2 Идентичность + export-рёбра** — все внутренние ре-экспорты как `export`-рёбра с флагом
      `public` (кейс `analyze_zones` через `zones/__init__` — ре-экспортирован, но не в `__all__`) (§2.1).
- [x] **M1.3 Query-API + `codemap query`** — `query.py` (networkx): `find` / `where_defined`
      (резолв ре-экспортов) / `dependencies` / `dependents`; CLI `codemap query <name>` (§4).
- [x] **M1.4 Reports C** — `serve/audit.py`: `report dependencies` (циклы + топ-зависимые),
      `report dead-code` (сироты, с оговоркой про эвристику) (§1-C).

**DoD:** ✅ отвечает на каталог §1 для bquant; резолв импортов/ре-экспортов корректен. 13/13 тестов.
Находки codemap о bquant: цикл `pipeline↔cache`; `analyze_zones` вне `__all__` пакета zones.

**Гэп-док (полнота покрытия, семантика, data flow):** [gaps/coverage_gap_analysis_2026-07-24.md](gaps/coverage_gap_analysis_2026-07-24.md)
(CM-01…CM-14; реестр проекта G13).

---

## M1.5 — Семантические рёбра (закрытие «быстрых wins» гэп-дока §11.1) ✅

**Цель:** устранить расхождение дизайн↔код — эмитить рёбра, обещанные в §2 как v1, но
пропущенные в M0/M1; обогатить узлы данными, которые griffe уже даёт. Схема → `0.2`.

- [x] **M1.5.1 `inherits` (CM-08)** — класс → базовый класс; griffe резолвит базу в канон-путь;
      внешние базы (`abc.ABC`) помечаются `extras.external`. 52 ребра на bquant (41 внутр / 11 внешн).
- [x] **M1.5.2 `decorated_by` (CM-06)** — символ → путь декоратора; 165 рёбер; запрос
      `decorated_with('deprecated'/'register')` (§2).
- [x] **M1.5.3 Типы полей + dataclass (CM-01/02)** — `extras.annotation` для атрибутов
      (`List[ZoneInfo]`), `extras.is_dataclass` для классов.
- [x] **M1.5.4 Динамическая регистрация (CM-07)** — `@Registry.register('key')` → `extras.registry`
      `{decorator, key}`, wiring реестра стал queryable (§7).
- [x] **M1.5.5 Query + CLI** — `bases`/`subclasses`/`decorated_with`; `codemap query` для класса
      выводит иерархию. 10 тестов.

**DoD:** ✅ CM-01/02/06/07/08 закрыты; 23/23 теста; детерминизм держится; схема `0.2`.
Остаются отложенными (по дизайну §7): CM-09 call-graph, CM-10 data-flow, CM-11 локали.

---

## M2 — Виды B и A ✅

**Цель:** поверх одного графа (структура M0/M1/M1.5 + поведение M4/M5) — читаемые виды
для ИИ и человека. Только `serve/`, без нового извлечения. CLI-глагол `export`.

- [x] **M2.1 RAG-экспорт** — `serve/rag.py`: чанк на символ (id+сигнатура+докстринг+место+
      соседи `calls`/`called_by`/`bases`/`subclasses`/`returns`/`registered_as`) + поле `text`
      для эмбеддинга; JSONL. 989 чанков на bquant. `codemap export rag` (§1-A, §4).
- [x] **M2.2 Obsidian-vault (B)** — `serve/vault.py`: заметка на модуль/символ + `[[wikilinks]]`
      (внутренние цели), теги `#class`/`#function`/`#deprecated`, index. 1079 заметок.
      `codemap export vault -o <dir>` (§4.1-B).
- [x] **M2.3 Скоупленные подграфы + mermaid** — `serve/mermaid.py`: `class` (classDiagram из
      `inherits`), `deps` (из `imports`), `calls` (BFS от root по `calls`); `--scope`/`--root`/
      `--depth` (§4.2, §4.1-A). `codemap export mermaid --mkind ...`.

**DoD:** ✅ три вида (RAG/vault/mermaid) поверх одного графа; скоуп по префиксу/root+depth;
46/46 тестов. Питаются данными M4/M5 (соседи по вызовам, классовая иерархия).

---

## M4 — Поведенческий слой: call-graph + type-flow (bounded) ✅

**Цель:** закрыть до достаточной границы главную семантику — вызовы и потоки данных
(gap-док CM-09/10/11). Схема → `0.3`. Граница задана **спайком** (2026-07-26): чистое
разрешение вызовов по именам = ~18-19% call-site'ов; остальное — вызовы на локальных
переменных (нужен вывод типов локалей → **паркуется отдельным тиром**) + builtins/external
(помечаются, не гонимся). Принцип: **разрешил или честно пометил** — тул сообщает свой % сам.

- [x] **M4.1 Type-flow (сильный дешёвый слой)** — структурные `params`/`returns` в extras
      функций (попутно CM-03); Query `producers`/`consumers` по имени типа. Отвечает «что
      порождает/ест `DataFrame`/`ZoneAnalysisResult`» без разрешения локалей (§7, CM-10 на уровне типов).
- [x] **M4.2 Call-graph best-effort** — `extract/behavior.py`: отдельный `ast`-проход (плагин),
      `calls`-рёбра caller→callee с меткой `resolution` (module/self/imported); внешние/builtin/
      локали — не рёбра, а счётчики. 933 ребра на bquant. Query `callers`/`callees` (CM-09).
- [x] **M4.3 Control-скелет** — `extras.control` на функции (ветвления/циклы/try/generator/async) (CM-11-lite).
- [x] **M4.4 Symbol-level dead-code** — `dead_symbols()`: приватные функции без входящих
      resolved-вызовов (сильный сигнал); отчёт `report behavior` + апгрейд `report dead-code` (CM-12).
- [x] **M4.5 Честность** — `report behavior` печатает % разрешения; каждое ребро — с `resolution`;
      dead-code с дисклеймером «кандидаты, не доказательство».

**DoD:** ✅ вызовы/потоки покрыты до заявленной границы; 33/33 теста; детерминизм; схема `0.3`.

---

## M5 — Deep-резолв вызовов (jedi, вывод типов локалей) ✅

**Цель:** снять хвост, запаркованный в M4 — вызовы на локальных переменных
(`x = Foo(); x.bar()`), где живёт кросс-объектный поток pipeline. Решение — **замерено
спайком, не заявлено** (см. `gaps/call_resolution_spike_2026-07-26.md`): jedi даёт
реальный подъём (self `.foo()` → 99%, хвост локалей → +27%), но упирается в ~28-30%
(остаток неразрешим статически — это Python, не лень).

- [x] **M5.1 jedi в зависимости** — `jedi>=0.19`; ленивый импорт (fast-путь её не тянет).
- [x] **M5.2 Deep-резолвер** — `behavior.py`: `jedi.Script.goto` на каждый call-site,
      резолв в определение bquant; метка `resolution="deep"`. griffe остаётся на структуру,
      jedi — только на вызовы (разделение труда, не замена).
- [x] **M5.3 Два тира** — `extract(deep=False|True)`, CLI `--deep`. fast (ast, <1с, дефолт,
      детерминизм/CI) и deep (jedi, ~50с, богатый граф). Оба детерминированы.
- [x] **M5.4 Тесты** — синтетический фикстур `tests/fixtures/deeppkg` (быстро, детерминированно):
      deep кракает `e.run()` на локали, fast — нет; self-вызовы; deep ⊃ fast; детерминизм.

**DoD:** ✅ на bquant fast 18.6% → deep **25.7%** (+359 рёбер), сборка 49.7с; 38/38 тестов;
детерминизм в обоих тирах. **Граница v1 (осознанно НЕ берём):** sound call-graph,
value-level data-flow, межфункциональный points-to (§7) — неразрешимо/непропорционально.

---

## M6 — Repo scope / impact-анализ (мульти-рут) ✅

**Цель:** снять доминирующий разрыв обкатки (F1, `gaps/observability_dogfood_2026-07-28.md`) —
codemap видел только пакет `bquant/`, а на вопрос «кто использует / можно ли удалить X» blast
radius живёт в тестах/доках/examples/scripts. Расширили область до **мульти-рута в пределах
одного репо** (§10.12), сохранив нейтральное ядро. **Ценность — не «ещё файлов», а транзитивный
типизированный impact-анализ, которого grep не даёт.** Схема → `0.4` (аддитивно). Оба режима
настоящие — прогнаны и сравнены эмпирически (обкатка-2 на том же `MACDZoneAnalyzer`).

- [x] **M6.1 Роуты + провенанс** — `extract_repo(core, consumers=, docs=, mode=, deep=)`
      (`extract/roots.py`); каждый узел помечен `extras.root` (`core`/`tests`/`examples`/`research`/
      `scripts`/`docs`). CLI-флаги `--consumer`/`--docs` (repeatable). Ядро остаётся на griffe;
      потребители (не-пакеты, россыпь `.py`) — ast-скан ссылок в ядро с резолвом ре-экспортов ядра.
- [x] **M6.2 Режим thin** — потребитель = один `module`-узел; его использования символов ядра →
      `calls`/`references`-рёбра от файла. Дёшево. bquant: 1872 узла / 5049 рёбер / 2.8с.
- [x] **M6.3 Режим full** — функции/классы потребителя материализуются (`contains`), ребро-
      использование исходит из объемлющей функции. Флаг `--mode` (дефолт thin). bquant: 3210 / 7139 / 3.2с.
- [x] **M6.4 Doc-слой** — скан `*.md` (регэкспы по имени ядра) на `from core… import X` +
      точечные `core.a.b.C` → `doc`-узлы + `references`-рёбра. Точный (from-import + exact node),
      прозаические упоминания голым именем не ловятся (осознанный lower bound: 7/11 doc-файлов на MACD).
- [x] **M6.5 Inbound-refs в query (F2)** — `query <symbol>` печатает `used by → root: N` (сводка
      входящих по роутам); `Query.references_to()` спанит все impact-рёбра.
- [x] **M6.6 Impact-вид** — `report impact --symbol X` (`serve/impact.py`): транзитивный blast radius
      (`Query.impact`, distance 1 + дальше по inbound), разбивка по роутам и типу ребра, дисклеймер «lower bound».
- [x] **M6.7 Тесты + обкатка-2** — фикстур `tests/fixtures/reporoot` (ядро+потребитель+doc, ре-экспорт);
      11 тестов; на bquant `MACDZoneAnalyzer` отдаёт полный blast radius (core 2 / docs 7 / examples 1 /
      scripts 2 / **tests 19** — точно совпало с grep-списком), thin/full сравнены.

**DoD:** ✅ на bquant impact-запрос по `MACDZoneAnalyzer` возвращает backward-compat тест-набор
(19 файлов / 55 функций в full) + doc-ссылки, сгруппированные по роуту и типу ребра, транзитивно;
thin/full сравнены; детерминизм держится; схема `0.4`; **57/57 тестов** (6 M0 + 7 M1 + 10 M1.5 +
8 M2 + 10 M4 + 5 M5 + 11 M6). Findings F3 (class-neighbors в RAG) и F4 (registry-map вид) —
кандидаты, не блокеры (открыты).

---

## M7 — Registry-aware call bridging (швы диспетчеризации) ✅

**Цель:** снять F5 (`gaps/dispatch_bridging_2026-07-28.md`) — навигационная обкатка показала,
что цепочка вызовов от `analyze_zones` рвётся на плагин-швах (детекция зон + стратегии фич):
`self.x = create_swing_strategy(name)` → `self.x.calculate(...)` уходит в unresolved. Данные для
моста есть (реестр M1.5: 12 привязок key→class + Protocol-базы) — не хватало ребра call-site→таблица.
Схема → `0.5`. **Ценность — навигация «что реально исполняется», не переизобретение grep.**

- [x] **M7.1 Таблица семейств** — `extract/dispatch.py`: группировка зарегистрированных классов по
      регистратору (`register_swing_strategy`→swing; `ZoneDetectionRegistry.register`→по классу).
      Конкретные стратегии Protocol не наследуют → группируем по реестру, не по inherits.
- [x] **M7.2 Атрибут-класса ↔ семейство** — скан `self.attr = create_X(...)`/`Registry.get_X(...)`
      в методах класса → привязка `attr` к семейству (паттерн bquant: bind в `__init__`, вызов в другом методе).
- [x] **M7.3 Мост метода** — `self.attr.method(...)` → `calls`-рёбра к `{impl}.method` всех
      реализаций семейства, `resolution="registry-candidate"` (честная over-approximation).
- [x] **M7.4 Прямой вызов + точный ключ** — фабрика/геттер → классы-реализации; строковый литерал
      ключа → единственное точное ребро `resolution="registry"`.
- [x] **M7.5 Честность** — рёбра типа `calls` (цепочка/impact/callers подхватывают сразу);
      `report behavior` считает мосты отдельно (exact/candidate); счётчик покрытия не трогаем.
- [x] **M7.6 Тесты** — фикстур `tests/fixtures/dispatchpkg` (реестр+фабрика+self-attr, без общей базы);
      6 тестов: self-attr→оба impl, литерал→точно, callers через мост, детерминизм, bquant-цепочка достаёт стратегии.

**DoD:** ✅ цепочка от `analyze_zones` 38 узлов/глубина 3 → **116/7**; `_detect_zones`→5 детекторов,
`extract_zone_features`→compute-методы стратегий; 44 моста (0 exact/44 candidate); 63/63 теста;
детерминизм; схема `0.5`. **Граница:** точную ветку (какой ключ из config) не берём — семейство-
кандидатов, не одиночку; мост опирается на data-driven соглашение реестра/фабрики.

---

## M3 — Serve и свежесть (операционка)

- [x] **M3.1 Тёплый serve-режим** ✅ (2026-07-29) — `serve/session.py` (`Session`: граф в памяти,
      `handle({op,args})→{ok,result}`, диспетч в существующие сервисы; ops: ping/stats/query/impact/
      column(s)/callers/callees/implementers/family/call_contract/report/export) + `serve/server.py`
      (построчный JSON-стдио-цикл, устойчив к битой строке/плохим args) + CLI `codemap serve`.
      Транспорт-нейтрально: MCP-адаптер — тонкая обёртка над тем же `handle` (когда понадобится `mcp`-dep).
      Досье-функция `build_query_result` вынесена и переиспользована в `codemap query`. +8 тестов (91/91).
- [ ] **M3.2 Свежесть** — git-хук / CI freshness-check / watcher (§15). **Отложено:** преждевременно —
      никто картой ежедневно не пользуется, инвалидировать нечего. Взять, когда появится живой потребитель.
- [ ] **M3.3 SQLite query-бэкенд** — индексы (§4). **Отложено:** networkx-бэкенд держит текущий масштаб
      (3k узлов); SQLite оправдан только при бóльшем графе/serve-нагрузке. Двери открыты за той же query-поверхностью.
- [ ] **M3.1+ MCP-адаптер** — тонкая обёртка `Session.handle` в MCP-tools (по одному tool на op), когда
      нужен нативный вызов из AI-агента; требует зависимости `mcp`. Логики нет — только маппинг.

---

## Кандидаты из обкатки архитектуры 2026-07-30 (ось A9, findings F18–F21) — ✅ ЗАКРЫТЫ (M16, 2026-07-30)

Обкатка A9 (`gaps/architecture_dogfood_2026-07-30.md`): роль архитектора — «форма системы целиком».
Было только `report dependencies` (циклы + top-imported). 4 гэпа, все Query-surface/Workflow, **без
схемы** (поверх import-графа/calls/contains/провенанса), +7 тестов (116→123); serve report-kinds 4→5,
ops 20→21. Реальная находка на bquant: слоевое нарушение `analysis ↔ indicators` (взаимозависимость).

- [x] **F18 (Query-surface/Workflow) — слои + направление + нарушения.** ✅ (M16, 2026-07-30, без схемы)
      `Query.layers()` → {слои (компонент под пакетом), межслойная матрица, **violations order-free** =
      слоевые пары с рёбрами в обе стороны — без хардкода порядка `core<analysis`}. На bquant: 8 слоёв,
      нарушение `analysis↔indicators`.
- [x] **F19 (Query-surface) — coupling / instability.** ✅ (M16, 2026-07-30, без схемы)
      `Query.coupling()` → per-module Ca (кто зависит от меня) / Ce (от кого завишу) / I=Ce/(Ca+Ce).
      `logging_config` Ca94 I0.01 (стабильный лист), `exceptions/config/nb` I0.00 (стабильное ядро).
- [x] **F20 (Query-surface) — god-объекты / хотспоты.** ✅ (M16, 2026-07-30, без схемы)
      `Query.hotspots()` → god-классы (методы≥порог: `ZoneVisualizer` 35, `NotebookSimulator` 23,
      `ZoneAnalysisPipeline` 20) + call-хабы (in+out) с флагом **pervasive** (логгер/util — ожидаемый шум,
      не риск; `ContextualLogger.info` 105 помечен, реальные хабы `analyze_zones` 48 выделяются).
- [x] **F21 (Workflow) — синтез: architecture overview.** ✅ (M16, 2026-07-30, без схемы)
      `serve/architecture.py`: `build_/render_architecture` (циклы+слои+coupling+хотспоты в один вид);
      report kind `architecture` (CLI `codemap report architecture` + serve report); serve op `architecture`
      (структурный). Проверено на живом графе — читаемый одностраничный обзор формы системы.

---

## Кандидаты из обкатки diff/change-review 2026-07-30 (ось A11, findings F16–F17) — ✅ ЗАКРЫТЫ (M15, 2026-07-30)

Обкатка A11 (`gaps/changereview_dogfood_2026-07-30.md`): вход ревьюера — **дифф** (файл+строки), не имя.
Два разрыва, оба в query/serve-слое (**без схемы**), +13 тестов (103→116); serve 18→20 ops.

- [x] **F16 (Query-surface) — резолвер локация→символ.** ✅ (M15, 2026-07-30, без схемы)
      Данные containment (`file`+`lineno`+`endlineno`) были, поверхности не было; `search` матчит только
      подстроку id. `Query.symbol_at(file,line)` (внутренний-первым, **fallback к модулю** для кода между
      def'ами) + `symbols_in_range(file,s,e)` (per-line дедуп); serve op `locate` ({file,line}|{file,lines}).
- [x] **F17 (Workflow) — агрегация ревью change-set.** ✅ (M15, 2026-07-30, без схемы)
      Было: 4 символа = ~20 ручных вызовов + склейка. `serve/review.py`: `build_review(hunks|symbols)` →
      сшитое досье (per-symbol callers/call_contract/columns/consumers_by_root) + union blast-by-root +
      **risk-ранг** (синтез из fan-out/cross-root/contract-sites/dataflow — R3 сложился бесплатно) +
      unresolved-хунки (ничего не теряется молча); `render_review` markdown; serve op `review`; CLI
      `codemap review <diff>` с парсером unified-хунков (`parse_unified_diff`, new-side диапазоны).
      Проверено на реальном `git diff` (7 хунков→10 символов, high-risk первыми, blast core 32/tests 27).

**Границы (не гэпы, в бэклог):** added/deleted символы → **двух-графовый diff** (rebuild@base vs @head),
отложено с M3.3 (резолвер деградирует к объемлющему узлу, added не выдумывает); consumer-руты
(tests/examples) `file` НЕ несут → дифф по тесту не локализуется (core-ревью — 80% случая).

---

## Кандидаты из обкатки soundness/trust 2026-07-30 (ось B1, findings F14–F15) — ✅ ЗАКРЫТЫ (M14, 2026-07-30)

Обкатка B1 (precision/recall трёх приближений + `canonical`, `gaps/soundness_dogfood_2026-07-30.md`):
сверка карты с исходником bquant. Итог: два «страшных» приближения — **фактически точны** (мост M7:
0 false-exact, веер честен; `implements`: 12/12 истинны, recall 100%); два реальных дефекта доверия —
**молчаливые** — закрыты вехой **M14**. +5 тестов (98→103).

- [x] **F14 (Soundness/Workflow) — молчаливая `canonical`-дизамбигуация.** ✅ (M14, 2026-07-30, без схемы)
      Голое короткое имя (`calculate` — 25 defs, `main` — 19) резолвилось в 1 узел по кратчайшему id, без
      сигнала — реляционный op уверенно отвечал про **не тот** символ (вплоть до тест-мока
      `MockSwingStrategy.calculate_global`). `Query.canonical_info` возвращает `{input,id,ambiguous,
      alternatives}` (`ambiguous` ⇔ ≥2 кандидата в ничью по path-сигналу); `canonical` делегирует ему;
      Session `_canon` пишет резолюцию, `handle` кладёт блок `resolved` в конверт, когда выбор был
      неоднозначным (F14) **или** переписал вход (re-export, F13); op `resolve` отдаёт полный инфо-дикт.
      На bquant: `callers('calculate')` → `resolved.ambiguous=True`, 24 альтернативы; `ZoneDetectionStrategy`
      (1 def) → `ambiguous=False` (ложной тревоги нет). Фикстура dispatchpkg (`run` в Alpha/Beta/Protocol)
      + 4 теста.
- [x] **F15 (Soundness/misleading-label) — column node-set = 71% payload-шум.** ✅ (M14, 2026-07-30, схема 0.9)
      Правило F6 «dict-literal ключ = writer» ловило **каждый** результат-словарь: из 1007 `column`-узлов
      71% — dict-literal-only ключи (`adf_statistic`, `n_simulations`, `text.color`), не колонки; агрегат
      `columns()` вводил в заблуждение. `extract/dataflow` пишет access-form: узел несёт
      `extras.subscripted` (был ли ключ хоть раз `x['k']`), ребро — `extras.access`
      (`subscript`|`dict-literal`). `Query.columns(subscripted_only=True)` по умолчанию отдаёт реальный
      column-set (~30%: 300/1007); точечный `column('macd_hist')` и продюсер-ребро F6 не тронуты; op
      `columns` принимает `all=true` для полного over-set. Фикстура flowpkg (`meta` = dict-only) + 2 теста.

---

## Кандидаты из обкатки агент-через-serve 2026-07-29 (findings F9–F13) — ✅ ЗАКРЫТЫ (M13, 2026-07-29)

Обкатка рабочего цикла агента через `serve` (`gaps/agent_workflow_dogfood_2026-07-29.md`): 5 гэпов
Workflow/Query-surface. Все закрыты одной вехой **M13** (serve/query-слой, **без схемы**), +7 тестов (98/98).

- [x] **F13 (Precision/Workflow) — реляционные ops резолвят re-export/короткое имя.** ✅ `Query.canonical`;
      Session-ops (`implementers`/`family`/`callers`/`callees`/`call_contract`/`columns_of`/`source`) резолвят
      вход через `_canon`; op `resolve`. `implementers('…detection.ZoneDetectionStrategy')` → 5 (было []).
- [x] **F12 (Workflow) — хендл к исходнику.** ✅ `file`/`lines` в `matches` (и в text-выводе); op `source`
      (сниппет по `--source-root`, best-effort; overlay-узлы → location-only с нотой).
- [x] **F9 (Query-surface) — discovery/поиск/обзор.** ✅ op `search`(подстрока+kind+limit), op `families`
      (Protocol → члены). `search ZoneDetection` → 5 классов (было пусто).
- [x] **F11 (Query-surface) — обратный dataflow.** ✅ `Query.columns_of(func)` + op `columns_of` + поле
      `columns` в query функции. `columns_of(extract_zone_features)` → reads [atr, close, …].
- [x] **F10 (Workflow) — extension-рецепт.** ✅ `registered_as`(decorator+key) в query класса + text
      «register with: @register('zero_crossing')»; op `families` отдаёт рецепт по каждому члену.

---

## Кандидаты из глубокой обкатки 2026-07-29 (findings F3/F4/F6/F7/F8)

Обкатка на 5 непокрытых осях (`gaps/deep_dogfood_2026-07-29.md`): 3 новых гэпа + 2 подтверждения.
Не блокеры; порядок — по «дёшево×ценно». Каждая находка с категорией по причине (диктует форму фикса).

- [x] **F8 (Representation) — провенанс-осознанный `report dead-code`.** ✅ (M8, 2026-07-29)
      `Query.orphan_modules(root=)` + `orphan_modules_by_root()`; отчёт показывает core-орфаны как
      сигнал (8), consumer-entrypoint'ы (116: tests 75/examples 11/research 24/scripts 6) свёрнуты с
      пояснением «orphan по природе, не dead code». Serve+query, без схемы. +2 теста (65/65).
- [x] **F4 (Query-surface) — вид семейства реестр+Protocol.** ✅ (M9, 2026-07-29, схема 0.6)
      `extract/dispatch.add_family_links` синтезирует `implements`-рёбра (impl→Protocol) по таблице
      семейств, data-driven матч (токен ⊂ имя Protocol; безтокенный — по имени реестра). 12 рёбер на
      bquant. Query: `implementers`/`implements`/`family_siblings` + вывод в `query`; mermaid class —
      realization `<|..` (семейство больше не пустое); RAG-чанк несёт Implements/Implemented by.
      Фикстура `dispatchpkg/base.py` (ThingProtocol) + test_m9_family.py (6 тестов). 71/71.
- [x] **F3 (Representation) — класс-чанк агрегирует call-соседей методов.** ✅ (M10, 2026-07-29)
      `serve/rag._methods_calls`: union внешних callees методов класса → `neighbors.calls_via_methods`
      (каждый target с меткой `via <метод>`) + текст «Methods call: …». Serve-only, без схемы.
      MACDZoneAnalyzer класс-чанк теперь показывает шов `analyze_zones (via analyze_complete_modular)`
      (+ detect_zones/with_indicator/build) — делегирование в pipeline видно без чтения методов. +1 тест (72/72).
- [x] **F7 (Representation+Precision) — арг-контракт на call-site.** ✅ (M11, 2026-07-29, схема 0.7)
      `behavior._arg_shape`/`_arg_contract`: `calls`-рёбра несут `callsites` (сколько выражений вызова
      схлопнуто) + `posargs`/`kwargs`/`splat` (наблюдённая форма аргументов); захват и в behavior-проходе,
      и в consumer-скане `roots.py`. `Query.call_contract` + секция «Call-site contract» в `report impact`.
      На bquant get_indicator_params: examples ×2 (схлопывание снова видно), все «1 positional». Фикстура
      argpkg + test_m11 (5 тестов). 77/77.
- [x] **F6 (Extraction) — dataflow по строковым ключам.** ✅ (M12, 2026-07-29, схема 0.8)
      `extract/dataflow.add_dataflow`: `column`-узел на строковый ключ + `writes` (subscript-store и
      dict-литерал-продюсер `{'k':…}`) / `reads` (subscript-load) рёбра function→column. Embedded-данные
      исключены. `Query.column(name)`/`columns()` + `query <col>` печатает producers/consumers. На bquant:
      1007 колонок / 2381 рёбер; `query macd_hist` → written by `MACD.calculate`, read by
      extract_zone_features + 4 визуализатора (было — пусто). Честно: over-set строковых ключей (dict-
      доступ тоже попадает). Фикстура flowpkg + test_m12 (6 тестов). 83/83.

---

## Отложено / будущее (двери открыты, не строим сейчас)

- **Мультиязычность** — экстракторы Go (`go/packages`, разбор `replan`), TS (`ts-morph`), C++ (libclang),
  Rust (rustdoc-json); tree-sitter как фолбэк (§12, §11).
- **Инкрементальность** — контент-хеш + инвалидация (заимствуя Salsa/build-систему) (§15.3).
- **Neo4j query-бэкенд** — на system-scale графе (§4, §16).
- **Система как граф** — инфра/микросервис-экстракторы (IaC/OpenAPI/OTel), твои серверы (§16).
- **Внешние тулы за адаптерами** + реестр кандидатов (§13).
- **Дистрибуция** — `uv`/`pipx` пакет; компилируемый бинарь (Nuitka) при нужде (§14).
- **Структурный разбор докстрингов** (Google/NumPy-секции) для потребителя B (§10.2).
- **Точный call-graph / sequence-виды** — слой глубины (§7).

---

## Порядок и принципы

1. **M0 первым** — тонкий срез доказывает конвейер, даёт пользу (вход для доки), проверяет форму.
2. Каждая веха — **сквозная и полезная** (не «слой без выхода»).
3. Расширять каталог §1 — только осознанно; «Отложено» не тащить в v1.
4. Ядро/схема/CLI стабильны; новое (языки, бэкенды, виды) — аддитивно за адаптерами.

*Живой документ. Отмечать `[x]`, дописывать задачи по мере реализации.*
