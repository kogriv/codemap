# codemap — Бэклог

**Тип:** Живой бэклог реализации. **Рамка:** `DESIGN.md` (дизайн v1 закрыт, решения §10 приняты).
**Статус:** ✅ **M0 + M1 + M1.5 + M4 + M5 + M2 + M6 + M7 + M8–M18 сделаны** (M8–M12 — 2026-07-29,
findings глубокой обкатки F8/F4/F3/F7/F6; M13 — serve-эргономика F9–F13; M14 — 2026-07-30, soundness B1
F14/F15, схема 0.9; M15 — diff/change-review A11 F16/F17, `codemap review`; M16 — архитектура A9 F18–F21,
`report architecture`; **M17** — MCP-адаптер `serve --mcp`; **F22** — компактный MCP-payload; **M18** —
возраст графа в `stats` + `codemap refresh`) + **M3.1** тёплый serve-режим. **Режим: use-driven** —
codemap вынесен в отдельный репо и подключён к живому ИИ-агенту через MCP; оси добора (A10/A12/B2) —
watchlist «по нужде» (см. `gaps/dogfood_axes.md`). Отложено — **M3.2** полный watcher / **M3.3** SQLite /
**двух-графовый diff** (added/deleted) — брать при нужде/масштабе. 🟢 **R1** — исследовательский трэк
(ландшафт соседних тулов, `research/`) открыт 2026-08-02.

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
- [~] **M3.2 Свежесть** — 🟡 **три из четырёх кирпичей на месте**, остался только опциональный авто-watcher.
      Хронология: **M18** (2026-07-30) — возраст графа (`stats.freshness` из mtime) + сайдкар-рецепт ре-билда;
      **R1-C9** (2026-08-23) — быстрый инкремент (`build --incremental`, deep ~5s vs ~60s); **issue #3**
      (2026-08-23, коммит `cd93dc2`) — свежесть стала **честной** (`freshness()` описывает *обслуживаемый*
      снимок и помечает `stale: true` + `on_disk_built_at` + причину, когда файл на диске обогнал сервер —
      конец тихого «fresh» поверх старого графа) + новая операция **`reload`** (serve-op и MCP-tool: подхват
      пересобранного `graph.json` без рестарта). Итого ручная связка **`build --incremental` + `reload`** уже
      закрывает потребность честно. **Осталось (по нужде):** авто-петля «watch `*.py` → debounce →
      `build --incremental` → `reload`» — тривиальный glue поверх готовых операций, без своих решений (что
      считать изменением решает scope.py, дешёвый пересчёт — C9, подхват — `reload`); заводить дизайндок/
      отдельный пункт не нужно. Берём, когда появится живой сценарий «агент рядом, правлю код, хочу ноль
      ручных действий». **Hash-свежесть строится на M19.A** (сверка контент-хэшей с манифестом — точнее mtime).
- [x] **M18 — возраст графа + удобный ре-билд** ✅ (2026-07-30, без схемы) — MCP отдаёт статичный `graph.json`;
      теперь `stats` несёт `freshness` (`built_at`/`age_seconds` из mtime — агент видит, что карта могла
      устареть) + рецепт ре-билда. Канонический граф остаётся **без таймстампов** (детерминизм): метаданные
      живут в сайдкаре `<graph>.meta.json` (argv/cwd/target/built_at), пишется при `build -o`. Новая команда
      **`codemap refresh <graph.json>`** переигрывает записанный build. `serve` прокидывает `graph_path` в
      Session. `codemap/freshness.py`; сайдкар в .gitignore. +8 тестов.
- [ ] **M3.3 SQLite query-бэкенд** — индексы (§4). **Отложено:** networkx-бэкенд держит текущий масштаб
      (3k узлов); SQLite оправдан только при бóльшем графе/serve-нагрузке. Двери открыты за той же query-поверхностью.
- [x] **M17 — MCP-адаптер** ✅ (2026-07-30) — тонкая обёртка `Session.handle` в MCP-tools (18 tools,
      по одному на agent-facing op), нативный вызов из AI-агента. `serve/mcp_server.py`:
      `build_mcp_server(session)` (mcp 2.0 `MCPServer`, lazy-import), каждый tool зовёт `handle` и
      возвращает конверт (сигнал `resolved.ambiguous` F14 сохраняется). CLI `codemap serve --mcp`
      (stdio). `mcp` — **опциональная** зависимость (`pip install codemap[mcp]`; extra в pyproject),
      import ленивый — codemap работает без неё. Логики нет — только маппинг. +7 тестов (importorskip mcp).

---

## R1 — Исследовательский трэк: ландшафт соседних тулов 🟢 АКТИВЕН (2026-08-02)

**Рамка (от пользователя):** ядро доведено до естественной точки (вынесено в отдельный репо,
подключено к живому ИИ-агенту через MCP, findings F22/M18/F23 закрыты) → открываем
исследовательский трэк. Изучаем **соседние тулы анализа кодовой базы** и по каждому решаем,
как codemap должен к нему относиться: **прямая интеграция** / **тонкая обёртка-адаптер** /
**только референс** (учимся, не тащим). Формат — набор markdown-отчётов в `research/`
(один на тул или тему). Находки возвращаются сюда и в `gaps/dogfood_axes.md` как **конкретные
способности**, а не спекулятивные фичи.

**Оси сравнения (позиционирование codemap):** source-only (без сборки/рантайма) · детерминированный
канонический граф · CLI-AI-first (JSON по умолчанию) · Python-focus · граф-модель (узлы/рёбра
+ provenance) · warm-serve/MCP.

- [ ] **R1.0 Ландшафт** — `research/00_landscape.md`: категории тулов, где сидит codemap по осям,
      сводная матрица + вердикт integrate/wrap/learn по каждому.
- [ ] **R1.1 AI-context / repo-map** — aider repo-map, Cursor/Continue/Cody codebase-index — прямые
      «конкуренты» по AI-first-использованию (учимся + дифференцируемся).
- [ ] **R1.2 Code-graph / semantic-index инфра** — SCIP/LSIF, Kythe, Glean, Stack Graphs, Sourcegraph,
      ctags — интерчейндж-форматы и схемы графа (кандидаты в адаптер/экспорт).
- [ ] **R1.3 Query / dataflow движки** — CodeQL, Semgrep, ast-grep, tree-sitter, Comby — поверхность
      запросов и бэкенды экстракции.
- [ ] **R1.4 Python graph/arch пиры** — pydeps, pyan, code2flow, grimp/import-linter, snakefood, rope —
      прямые референс-пиры (что делают лучше/хуже, чему учимся).
- [x] **R1.5 Курируемые источники (field intake)** ✅ (2026-08-02) — `research/05_curated_sources.md`:
      обработан ТГ-дамп (каналы @ai_for_dev/DevHub/@data_analysis_ml) как bottom-up дополнение к R1.
      Сырьё вне git (`assets/` в .gitignore). Итог: поле **сошлось на тезисе codemap** («граф кода через
      MCP бьёт grep») — валидация + переполненность ниши. Добавляет живой ростер конкурентов (graphlens,
      CodeGraph, GitNexus, OntoIndex, Sentrux, cocoindex, rag_for_git, CodeWiki, …) и бенчмарк-доказательство
      (936 прогонов на superset: граф в 10–23× дешевле grep на impact-запросах).

Принцип трэка: **не строить фичи из отчётов сразу** — каждая находка проходит через backlog как
конкретная способность и берётся по нужде (use-driven), как остальные оси.

**Статус R1.0–R1.4: ✅ отчёты написаны** (2026-08-02) — `research/00_landscape.md` (карта + матрица +
консолидированные вердикты) + 4 тематических (`01_ai_context_repomap` / `02_codegraph_index_infra` /
`03_query_dataflow_engines` / `04_python_graph_arch_peers`). Метод: 4 grounded-агента (web-verified),
по каждому тулу вердикт integrate/wrap/learn.

**Ключевые структурные сигналы (для позиционирования):** (1) фронтир AI-context дрейфует К тезису codemap —
Cody уходит от эмбеддингов к search+graph, Anthropic: agentic grep бьёт RAG; (2) вся граф-инфра сходится на
примитивах codemap (Kythe VName / SCIP descriptor / LSIF moniker = каноничный устойчивый id — у codemap уже
есть); (3) два source-only-*графовых* прецедента размечают полосу: stack-graphs **заархивирован 2025** под
весом рукописных per-language DSL, ctags **живёт** простотой → *оставаться source-only+детерминированным, но
никогда не строить собственный name-resolution движок; делегировать jedi/griffe, фокус на Python*.

### R1 → кандидаты в способности (use-driven, по нужде; порядок = value÷cost)

Каждый пункт — готовая к взятию задача (**Scope / Зачем / Приёмка / Оценка**). Оценка в t-shirt: S≈полдня,
M≈1–2 дня, L≈неделя, XL≈крупная веха. Дефолт стойки сохраняется: **source-only, детерминизм, read-only,
Python-focus** — если задача его нарушает, это отмечено.

#### Tier 1 — высокая value÷cost, брать первыми

- [x] **R1-C1 SCIP-экспорт** ✅ (2026-08-02, без схемы) — `codemap export scip -o index.scip`.
      `codemap/serve/scip.py` (`build_scip`/`write_scip`) + вендоренные bindings `_scip_pb2.py`
      (сгенерены из офиц. `scip.proto`, guard ослаблен до 5.26), extra `codemap[scip]=protobuf` (lazy).
      **Честный scope:** граф symbol-level (нет координат call-site) → экспортируем **defs + SymbolInformation**
      (по одной Definition-occurrence на узел с локацией, kind, docstring, `inherits`/`implements` →
      SCIP `relationships` is_implementation); reference-occurrences (find-references) **намеренно не льём**
      (нет позиций токенов — фейк хуже пропуска). Symbol-string из каноничных id по грамматике дескрипторов
      SCIP (namespace `/`, type `#`, method `().`, term `.`). Детерминированные байты; проверено round-trip'ом
      protobuf и реальным `scip print`. **Частично закрывает R1-C7** (структурные descriptor-id доказаны).
      +8 тестов (importorskip protobuf; CLI-тест skip если `scip` не на PATH). На bquant: 206 documents,
      1826 symbols.
- [x] **R1-C2 ctags-экспорт** ✅ (2026-08-16, без схемы) — `codemap export ctags [-o tags]`.
      `codemap/serve/ctags.py` (`build_ctags`) — из def-узлов (class/function/attribute) строки extended-
      формата universal-ctags: `name\tfile\t{address};"\t{kind}\t{ext-поля}`. **Адрес:** `/^<строка>$/`-паттерн
      когда исходник читаем (устойчив к сдвигу строк — весь смысл ctags-паттернов; экранируются `\`/`/`/`$`),
      иначе **бэкоф на голый номер строки** (всегда есть из графа). **Ext-поля** (всё из уже имеющихся данных,
      без догадок): `kind` (c/f/m/v), `line:`, `scope` (`class:Foo`, module-scope опущен как в u-ctags),
      `signature:(…)`+`typeref:typename:…` (функции, paren-balanced разбор), `access:` (public/private из
      visibility), `end:`. **Честный scope:** только дефы (не references — это SCIP); модули пропущены (=файлы,
      как u-ctags); ре-экспорт-алиасы (узел без своей локации) пропущены → каждый деф тегируется один раз в
      реальном месте. **Детерминизм:** pseudo-tags объявляют `!_TAG_FILE_SORTED\t1`, реальные теги сортированы
      по имени→файлу→адресу (binary-searchable). CLI: `export ctags` + `--project-root` как source-root.
      **Приёмка выполнена:** на bquant@graph 1585 тегов (все classes/functions/methods/attributes с локацией;
      core), байт-идентичен между прогонами, структурно валиден + сортирован (readtags binary-search находит
      `analyze_zones`). Доки `docs/export.md` (секция + таблица). +9 тестов (readtags-CLI-тест skip если не на
      PATH). Закрывает «пол» способностей из R1-ландшафта.
- [x] **R1-C3 Архитектурные контракты + `check`** ✅ (2026-08-14, без схемы). `codemap/arch.py`
      (декларативный контракт `[architecture]` в `codemap.toml`: **layers ordered / independent / forbidden
      / no_cycles / exhaustive**; парсер толерантен как gate — битый toml → пустой контракт) + `codemap check`
      (CLI-гейт: **exit 2** на нарушении со списком нарушающих import-рёбер, **exit 0** на чистом,
      `--require-contract` делает отсутствие контракта провалом) + serve-op `check` + MCP-tool `check`
      (паттерн «что я сломал» — агент спрашивает после правки). **Приёмка выполнена:** на bquant layers-контракт
      ловит реальное нарушение (`indicators.macd → analysis.zones.models` вверх + цикл `pipeline↔cache`, exit 2)
      и проходит на forbidden-контракте (exit 0); exhaustive падает на незадекларированном слое (тест).
      **Dogfood:** codemap описал **собственный** слой-контракт в `codemap.toml` и `codemap check --build
      ./codemap` зелёный (тест `test_r1c3_dogfood.py` стережёт). Доки `docs/architecture-contracts.md`.
      **Отложено из R1.5-словаря:** naming/file-size-правила, health-delta до/после (кандидаты в R1-C4/новый
      пункт). +18 тестов.
- [x] **R1-C4 Метрики сложности в hotspots** ✅ (2026-08-16, схема 0.10). Считаются в поведенческом
      ast-проходе (`extract/behavior._complexity`, тот же проход, что control-скелет — source-only,
      **stdlib-only, без radon**, детерминированно): `extras.complexity` на function-узлах несёт **cc**
      (McCabe цикломатическая: if/elif/тернар/for/while/except/bool-join/comprehension-clause+filters/
      match-case, по **собственному телу** — вложенные def не двоятся), **volume** (Halstead: операторы-
      символы AST + имена/константы), **sloc** (физический span), **mi** (Maintainability Index,
      radon-нормализованный 0–100, ln-входы прижаты к 1). **Вплетено в обе оси:** `Query.hotspots` →
      god-классы аннотированы `total_cc`/`max_cc` + новый список `complex_functions` (топ по CC, порог
      `min_cc`); `report architecture` и `report behavior` рендерят; **per-symbol cc/mi/volume/sloc в
      query-досье** (`build_query_result`). **Приёмка выполнена:** на bquant `_create_plotly_zones_on_price`
      CC 66/MI 12.5, `extract_zone_features` CC 59/MI 9.2; и разрешает коллизию «одинаковое число методов ≠
      одинаковая сложность» — `NotebookSimulator` (23 метода, ΣCC 50) vs `StatisticalPlots` (23, ΣCC 111).
      Числа детерминированы (проверено re-extract'ом). +15 тестов. **Отложено (по дизайну):** wily-стиль
      (метрики во времени) — поздняя надстройка над `review`; comment-терм MI опущен (скоринг per-symbol).

#### Tier 2 — среднее value÷cost, нужен небольшой дизайн

- [x] **R1-C5 Двух-графовый diff + API breaking-change** ✅ (2026-08-14, без схемы). `codemap/apidiff.py`
      (движок: added/removed/changed по **публичной** поверхности; сигнатуры парсятся через `ast` —
      `def <sig>: ...` — точный разбор параметров, не строковый diff; непарсящаяся → консервативный
      `signature-changed`, не ложный breaking). **Правила breaking:** удалённый публичный символ ·
      public→private · смена kind · удалён параметр · добавлен обязательный · optional→required · удалён
      `*args`/`**kwargs`. **warning:** смена типа параметра/возврата · newly-deprecated. **info:** добавлен
      optional-параметр · новый символ. `codemap diff old new [--exit-code]` (гейт релиза: exit 1 на breaking) +
      serve-op `diff` + MCP-tool `diff` + **влито в `review --base`** (добавляет removed/added/breaking,
      которых не видят хунки). **Приёмка выполнена:** на паре графов до/после diff помечает breaking
      (param made-required, removed symbol), added/deleted перечислены; тест на непарсящейся сигнатуре.
      Доки `docs/api-diff.md`. +21 тест.
- [x] **R1-C6 Relevance-ранжирование + token-budgeted pack** ✅ (2026-08-22, без схемы). codemap стал
      first-class context-provider. (a) **`Query.rank(seeds, root)`** — personalized PageRank по usage-рёбрам
      (`calls/imports/references/inherits/implements`, user→used); без seeds — глобальная важность (хабы
      наверх), с seeds (id/короткое имя/путь файла) — relevance к контексту (приём aider). **PageRank — чистый
      Python power-iteration** (без numpy/scipy — codemap лёгкий, как CC/MI без radon), детерминирован (sorted
      обход, округление). (b) **`codemap pack --budget N [--seed X]`** (`serve/pack.py`) — ранжированный срез
      под токен-бюджет: жадно добавляет по убыванию ранга, пока влезает; оценка токенов ≈ 4 симв/токен
      (детерминированно, без токенайзера). Поверхности: CLI `pack`, serve-op `pack`, **MCP-tool `pack`**.
      **Приёмка выполнена:** ранкинг детерминирован ✅; `pack` **никогда не превышает бюджет** ✅ (проверено на
      5/30/100/100k); на bquant топ-хабы (`logging_config`/`config`/`exceptions`) раньше листьев ✅;
      seed=`analyze_zones` → наверх zone-символы вместо глобальных хабов ✅. +12 тестов. Доки `docs/pack.md`.
      **Закрывает последний Tier-2-пункт.** Отложено: bit-точный токенайзер (эвристики хватает).
- [x] **R1-C7 Закрытый словарь edge-kind + структурные descriptor-id** ✅ (2026-08-22, без схемы).
      Структурные descriptor-id доказаны SCIP-экспортом (R1-C1). **Остаток закрыт:** `model.EDGE_TYPES` —
      закрытый frozenset из 10 типов (`contains/imports/export/inherits/decorated_by/calls/references/
      implements/reads/writes`) с doc по каждому; узлы остаются открытым множеством (по DESIGN §2, edges —
      typed). **Тест** `tests/test_r1c7_edge_vocab.py`: (1) пинует набор литералом; (2) падает, если живой
      граф эмитит незадекларированный тип; (3) падает, если задекларированный тип перестал появляться (нет
      мёртвого словаря). **Побочно поймал дрейф:** и `model.py`, и DESIGN §2 писали `exports`, а код эмитит
      `export` — синхронизировано (ровно тот дрейф, который тест теперь стережёт). Доки: `model.py` + DESIGN §2.
      +3 теста.
- [x] **R1-C8 Dead-code confidence + whitelist UX** ✅ (2026-08-22, без схемы). `Query.dead_code(whitelist,
      min_confidence)` — градуированные кандидаты (private-функция без входящего resolved-вызова) с
      провенанс-причиной: **high** (нет ни одного входящего ребра/хука), **medium** (декоратор/registry могут
      вызвать неявно — framework-hook/dispatch), **low** (на неё есть `references` — вероятно живая; причина
      называет, кто ссылается, по роутам). Low-тир = отсечка FP, которую call-only vulture не может. Whitelist
      (точный id / `fnmatch`-glob) из `[dead_code].whitelist` в codemap.toml + `--min-confidence` фильтр.
      `render_dead_code` группирует по уверенности с причинами; `dead_symbols()` остался тонкой обёрткой
      (обратная совместимость). Поверхности: CLI `report dead-code --min-confidence`, serve report-op (min_confidence
      + whitelist из source_root). **Приёмка выполнена:** confidence ✅, whitelist уважается ✅ (dogfood: 42→4
      после подавления argparse/dict-разводки `_cmd_*`/`_op_*` — ровно те framework-FP), провенанс-строка
      объясняет «почему не мёртвое» ✅. +10 тестов (фикстур-граф со всеми тирами + exclusions + whitelist/filter
      + loader). Доки `docs/dead-code.md`. Закрывает предпоследний Tier-2-пункт.

- [x] **R1-C20 Рёбра доступа к атрибутам (`impact`/refs для полей класса)** ✅ (2026-08-23, схема 0.11) — из
      dogfood на bquant при планировании rename поля dataclass (G16). **Гэп:** `impact` на атрибуте класса
      возвращал `refs:[]` и **`risk:"none"`** при реальных сайтах — атрибут-ноды извлекались, но **ни одно
      ребро в них не входило** (`reads`/`writes` все на `column:*`, M12). Аффирмативная ложь «ничего не
      зависит» там, где нужен `unknown`. **Сделано:** новый закрытый edge-type `accesses`
      (`extras.access ∈ {read,write}`, `extras.resolution`, R1-C7 + бамп схемы 0.10→0.11) + пасс
      `extract/attrflow.py` (по образцу `dataflow.py`): `self.field` (`self`), `ClassName.field` (`class`),
      construction-kwargs → write (`construct`) — fast-tier `ast`; `obj.field` на типизированном локале
      (`deep`) — deep-tier `jedi` через **инференс типа получателя** (не goto — goto садится на assignment
      внутри метода, а не на ноду поля); неразрешённое = счётчик (`extras.attr_access`), не ребро в неузел
      (R1-C13-f2). `accesses` вплетён в `_IMPACT_EDGES` (атрибут-скоуп — колонки остаются вне impact);
      `Query.readers`/`writers`, serve-op `accessors` + MCP-tool, блок `attributes` в досье, CLI-рендер.
      **P0 honesty:** `impact` на атрибуте без смоделированного accessor'а → `risk:"unknown"` + `risk_reason`,
      **никогда `none`** (для функции/класса пустой radius остаётся честным `none`). **Приёмка выполнена:** на
      bquant fast-tier 1619 `accesses`-рёбер (self 1027 / construct 587 / class 5), deep +158; `impact` на
      `SwingThresholds.zigzag_deviation` даёт 6 refs (было `[]`/`none`); 210 атрибутов без accessor'а честно
      `unknown` ✅. +15 тестов (фикстура `attrpkg`: все формы + property-нода griffe + soundness-гейты + deep).
      R1-C7 guard-тест обновлён (`accesses` в словаре + на dogfood-графе). **Открытие в ходе:** griffe моделит
      `@property` как **attribute**-ноду, не function → чтение `obj.prop` — легитимное `accesses`-ребро (D-corr,
      §7 дизайна). **Доки:** `docs/attribute-edges.md`, дизайн `docs/design/attribute_edges.md` (D1–D4 закрыты:
      B/да/да/да), гэп `gaps/attribute_impact_gap_2026-08-22.md`. **Смыкается с** M12, R1-C7, R1-C13.
      Issue [#1](https://github.com/kogriv/codemap/issues/1).
- [x] **R1-C21 Плоский layout: краш на namespace-каталоге + молчаливые 0 `imports`-рёбер** ✅ (2026-08-24,
      **без схемы**) — из попытки применить codemap на **втором реальном таргете** (приватная
      research-лаба рядом с bquant, движок в плоском каталоге `shared/`); оба дефекта пойманы **в первые
      20 минут на первой же сборке** — сигнал по оси **B2 (робастность)**, которого один dogfood-таргет дать
      не мог. **Гэп (две половины одного layout'а):** (a) **без `__init__.py`** griffe считает каталог
      namespace-пакетом, у которого `filepath` — это `list[Path]` → `TypeError: ... not 'list'`, причём
      сообщение не называет ни каталог, ни причину; (b) **с `__init__.py`** сборка **успешна и даёт 0
      `imports`-рёбер**: пакет грузится от родителя (`griffe_extractor.py:47-48`), id получаются
      `flatpkg.beta`, а griffe пишет таргет как в исходнике (`alpha.X`) → `_resolve_edges` (`:164-166`)
      отбрасывает его как внешний, неотличимо от `pandas.DataFrame`. **Почему (b) хуже краха:** отсутствие
      данных рендерится как **справка о здоровье** — «no layer violations», «граф импортов ацикличен», а
      `dead-code` объявляет **все** модули orphan (на реальном таргете — все 35 модулей работающего движка;
      `impact` на живом символе → «isolated», при grep 10+ файлов). Это тот же класс, что F14 и issue #3:
      уверенно выглядящее **ничто**. **Замерено на месте (не со слов):** игрушечный репро из 2 файлов даёт
      `Counter({'contains': 4})`, оба модуля orphan; правило «переписать неразрешённый импорт, чья голова
      называет sibling-модуль» даёт **0 ложных срабатываний** на codemap (45 модулей / 114 внешних импортов)
      и bquant (88 / 580); краш живёт **в 5 местах**-потребителях `filepath` (не в одном — после патча
      только `_rel` сборка падает дальше в `behavior.py:61`, guard `if not fp` непустой список проходит).
      **План (по убыванию ценности на строку):** (1) **честность** — 0 `imports` при ≥2 модулях объявляется
      на билде, в `stats` и в обоих отчётах *до* выводов (верно даже если резолв не чинить); (2) не падать —
      нормализация `filepath` в одной точке (`None` для namespace) + внятное сообщение, что за каталог и чем
      это грозит; (3) резолв sibling-импортов с **пометкой допущения** на ребре (`extras.resolution="flat"` —
      это инференс про `sys.path`, а приближения у нас метятся, не прячутся); (4) CI-guard на плоскую
      фикстуру. **Приёмка:** графы bquant и codemap до/после — **байт-в-байт идентичны** (замер §1 дизайна
      предсказывает ноль переписываний, тест это фиксирует); плоская фикстура в обеих формах собирается,
      ребро `beta→alpha` есть и помечено. **Доки:** гэп `gaps/flat_layout_gap_2026-08-24.md`, дизайн
      `docs/design/flat_layout.md` (**D1–D5 открыты**, рекомендации: A / A / да / нормализация+продолжать /
      derive). **Разблокирует класс таргетов:** переделка той лабы в настоящий пакет = переписать импорты в
      88 файлах, 52 из них — замороженные эксперименты, обязанные остаться байт-стабильными.
      **Сделано:** `extract/gsource.py` — точка нормализации: `module_file()` (`None` на namespace-списке,
      используется всеми 5 потребителями), `is_namespace_dir()`, **`module_imports()`** (квалифицирует
      плоские sibling-таргеты один раз — для всех пассов); `griffe_extractor` — двухпроходный резолв
      (сначала точный, потом `_flat_sibling`-ретрай) с пометкой `extras.resolution="flat"`;
      `codemap/diagnostics.py` — **дериваты, ничего не хранится**: `import_graph_diagnostic` (0 imports при
      ≥2 модулях) и `namespace_target_diagnostic` (выводится из `file is None` у корня), подключены в
      `cli build` (stderr), `stats.diagnostics` и **три** отчёта (architecture / dependencies / dead-code) —
      *перед* выводами, чтобы пустота не читалась как чистота. **Промах дизайна, найденный первым же тестом:**
      слеп был не только слой `imports` — **слой вызовов** тоже (`behavior._resolve` классифицирует таргет по
      префиксу пакета, а у плоского его нет); починка *на карте импортов*, а не внутри `_resolve`, держит
      инференс в одном месте и заодно вылечила `attrflow`. **Приёмка выполнена:** граф bquant до/после —
      **байт-в-байт идентичен** (fast), `attrpkg --deep` — тоже; инференс на здоровых пакетах срабатывает
      **ноль раз** (зафиксировано тестом на bquant); плоская фикстура собирается в обеих формах, ребро
      `beta→alpha` помечено, package-qualified остаётся без метки; честная половина работает автономно.
      +20 тестов (`tests/test_r1c21_flat_layout.py`, фикстура `flatpkg`), сьют 369→**389**. **Доки:**
      `docs/flat-layout.md`, дизайн `docs/design/flat_layout.md` (D1–D5 закрыты: A / A / да /
      нормализация+продолжать / derive), гэп `gaps/flat_layout_gap_2026-08-24.md`. **Смыкается с** R1-C13
      (метки приближений), M18/#3 (поверхность сообщает, когда может врать).
      Issues [#4](https://github.com/kogriv/codemap/issues/4), [#5](https://github.com/kogriv/codemap/issues/5).
- [x] **R1-C21-f1 (flat layout) consumer-корни: голый импорт в ядро не давал ребра** ✅ (2026-08-24, без
      схемы) — из повторного прогона R1-C21 автором на том же реальном репо. **Что уже работало:** внутри
      ядра `imports` 0→**75** (все `flat`), `calls` 316→**469**. **Гэп:** consumer-корень (`--consumer tests`),
      пишущий **тот же** голый импорт, не давал **ни одного** ребра — `roots.py::_consumer_imports`
      отсеивает statement, если модуль не квалифицирован ядром, ещё до попытки резолва; а
      `gsource.module_imports` сюда не достаёт (он правит карту импортов griffe-модулей ядра, а consumer-корни
      сканирует отдельный ast-пасс). **Почему это половина той же цены:** `--consumer` существует ради
      вопроса «кто пользуется X по всему репо», и на плоском layout ответ оставался уверенным нулём
      («No inbound references — isolated»), при 8 файлах с реальными call-site вне модуля. Диагностика R1-C21
      при этом **молчала** — импортов не 0, их 75, просто ни один не пересекает границу корня: проверка была
      написана на одно измерение уже, чем нужно. **Сделано (D6):** `_CoreIndex.qualify_flat()` +
      `core_is_flat` — кросс-рутовый инференс включается, **только если само ядро плоское** (namespace-корень
      либо в графе уже есть `flat`-рёбра). Гейт **структурный, а не статистический**: у нормального пакета
      каталог никогда не на `sys.path`, значит голый `import config` в скрипте **не может** вести в
      `pkg/config.py`, и ребро было бы выдумано (замер как вторичный аргумент: 0 ложных на 559 не-bquant
      импортов в его consumer-корнях). Гейт смотрит на **улику, а не на наличие `__init__.py`**: ядро с
      `__init__.py`, но с голыми импортами внутри — плоское по факту. **Сделано (D7):**
      `cross_root_diagnostic` — «≥1 не-core корень подан, но ни одна ссылка не доходит до ядра»; отдельная
      проверка на отдельное измерение, а не обобщение старой. **Приёмка:** repo-scoped граф bquant
      (core+tests+examples+docs, mode=full, 5.25 МБ) — **байт-в-байт идентичен**; на упакованном ядре голый
      импорт остаётся неразрешённым, квалифицированный работает без метки. +9 тестов, сьют 389→**398**.
      **Поправка автора к #5:** «grep находит в 10+ файлах» считало *упоминания*, не call-site; честно — 13
      упоминаний, **9 файлов с реальными вызовами** (8 вне своего модуля). Гэп верен в любом случае, но
      цифра была измерена небрежнее, чем звучала. Issue [#6](https://github.com/kogriv/codemap/issues/6).
- [x] **R1-C21-f2 (diagnostics) заметка выдавалась за предупреждение** ✅ (2026-08-24, без схемы) — из
      issue [#8](https://github.com/kogriv/codemap/issues/8). **Гэп:** рендереры отчётов дописывали **одну
      зашитую подпись** ко *всякой* диагностике — «findings below are derived from that empty import graph —
      unknown, not clean». Для проверки на пустой граф верно; для namespace-заметки — нет, и на репо с
      **404** import-рёбрами корректный раздел («Orphan modules: 0») подписывался как недостоверный. Это
      зеркало того самого дефекта, ради которого баннеры и заводились: отсутствие не должно читаться как
      здоровье, но и верный ответ не должен читаться как отсутствие. **Сделано:** severity и consequence
      принадлежат **проверке**, а не презентеру — `warning` обесценивает выводы ниже и сам приносит фразу об
      этом, `note` сообщает факт и не приносит ничего; единый рендер `diagnostics.render_lines` (⚠️/ℹ️),
      CLI печатает `[warning]`/`[note]`. Ни одна поверхность больше не может приписать смысл одной проверки
      условию другой. +3 теста, сьют 398→**401**.
- [x] **R1-C22 `high`-полоса dead-code врёт в 39% (ссылки, которые видны в исходнике, но не в графе)** 🆕
      ✅ (2026-08-24, **без схемы**) — из issue [#7](https://github.com/kogriv/codemap/issues/7), найдено
      при проверке flat-фиксов: *«рабочий граф и сделал это видимым»*. Не про плоский layout —
      **воспроизводится на самом codemap**. **Гэп:** `high` («no inbound calls, references, or decorators»)
      выставляется функции, на которую **есть ссылка в её же модуле**, просто в форме, которой граф не
      моделирует. `high` — это полоса, по которой действуют (и ровно её оставляет `--min-confidence high`).
      **Замерено — механизма три, а не один** (каждый пакет показывает только два, поэтому один dogfood-таргет
      этого дать не мог): ① **функция-как-значение** (значение dict, аргумент `default=`) — codemap 13,
      bquant 0; ② **вызов на уровне модуля** (`_register_all_indicators()` при импорте) — `behavior.py`
      обходит только именованные функции, модульные statements не посещаются вовсе: codemap 0, bquant 2;
      ③ **вызов внутри вложенного def** — весь вложенный def отбрасывается (`nested closure — not a
      definition node`), вместе с его вызовами: codemap 4, bquant 1. **Итого 20 из 51 (39%) ложных.**
      ② и ③ — это отсутствующие **`calls`**-рёбра, то есть страдает не только dead-code: `impact`,
      `callers`, `flows` и архитектурные виды читают граф без импорт-тайма и без тел замыканий. **План:**
      грейдер **не трогаем** (`_grade_dead` уже демотит в `low` по любому входящему ребру — фиксы проходят
      сами): ① `references`-ребро с `extras.resolution="name"` (~69 рёбер на codemap, ~149 на bquant; тип не
      новый — `references` в словаре и так «dispatch site → символ, который он называет»); ② `calls` от
      **узла модуля** (27/137 сайтов); ③ атрибуция вызова ближайшему объемлющему узлу графа — **дорогая**
      (619 / **5202** сайта), поэтому дельту меряем до мержа и при непропорциональности выносим отдельно.
      **Приёмка — НЕ байт-идентичность** (в отличие от R1-C21: здесь мы намеренно добавляем истинные рёбра):
      только добавления, каждое прослеживается до видимой в исходнике ссылки, замеренные ложные уходят в
      ноль, 31 действительно несослатый кандидат остаётся. **Доки:** гэп
      `gaps/dead_code_high_band_2026-08-24.md`, дизайн `docs/design/source_visible_references.md`
      (**D1–D5 закрыты**: да / да / да / грейдер не трогаем / additions-only), пользовательские —
      `docs/dead-code.md` §What counts as a reference. **Приёмка выполнена:** `high` **46→29** (codemap) и
      **5→2** (bquant) — ровно те 31, что аудит назвал настоящими; **только добавления** (bquant +364 пары,
      **0 удалений**; у codemap 1 удаление — ребро `add_behavior→_named_functions`, вызов которого эта же
      правка и заменила); все 278 name-ссылок на bquant проверены на присутствие имени цели в исходнике;
      дублей пар нет. +14 тестов (фикстура `refpkg`), сьют 401→**415**. **Три вещи, которых дизайн не
      предвидел:** ① большинство name-load'ов — **аннотации**, не диспетч (278 против прогноза 149); помечены
      отдельно `resolution="annotation"` (213) vs `"name"` (80), потому что это разные смыслы — «символ
      исполняется» и «символ в контракте»; ② **страх по D3 оказался фантомом**: из 5202 вложенных сайтов
      внутренне резолвятся 279, а новых пар всего **21** (codemap 4) — дорогим было число *сайтов*, а не
      *рёбер*; ③ **эталон бенчмарка точности устарел** — `c10_closure` держал `expected: []`, записав старое
      ограничение как правильный ответ, хотя docstring кейса **сам** называл `outer→helper` разрешимым
      ребром; исправлен на `decidable`, deep recall-overall 58%→**62.5%** при precision 100%. Плюс сплайс
      R1-C9 пришлось научить новым рёбрам — иначе инкремент их молча терял (поймал его собственный
      байт-идентичный тест). **Смыкается с** R1-C8 (градация), R1-C20 (тот же выбор: моделировать связь, а не
      чинить отчёт), R1-C13, R1-C9.
- [x] **R1-C22-f1 (dead-code) локальная переменная, затеняющая функцию модуля, считалась ссылкой** ✅
      (2026-08-24, без схемы) — issue [#9](https://github.com/kogriv/codemap/issues/9), зеркало #7: там была
      **недо**-атрибуция, здесь **пере**-атрибуция. Автор сперва подтвердил R1-C22 на своём репо —
      **10 из 10 верно** (было 9 из 10 неверно), плюс проверил два способа промахнуться (имя только в
      докстринге/строке и имя только в Store — ссылок не создают), 1248 кросс-рутовых рёбер, 0 ложных.
      **Гэп:** Load локально связанного имени, совпадающего с функцией модуля, атрибутировался этой функции —
      Python связывает **на область**, а не на инструкцию, поэтому `_x = 1` делает все чтения `_x` в функции
      локальными. Мёртвая функция пряталась в `low` вместо `high` (`--min-confidence high` её не видит; ничего
      живого не удаляется). **Шире, чем в issue:** ложные рёбра давали **шесть** форм — присваивание,
      **параметр**, `for`-таргет, `with ... as`, `except ... as` и вложенный `def` того же имени; параметры
      выглядели корректными у автора лишь потому, что имя не совпадало. **Сделано:** `_local_bindings` на
      область функции; `global`/`nonlocal` возвращают имя модулю; **модульная область не фильтруется** (там
      ре-биндинг — тот же символ). **Своя же ловушка, пойманная замером:** первый вариант считал теневыми и
      **функция-локальные импорты** — и уронил настоящее ребро на bquant
      (`register_builtin_indicators → IndicatorFactory`, импорт внутри тела); импорт связывает имя **с той
      самой целью**, которую ребро и фиксирует, поэтому подавлять его нельзя. **Приёмка:** шесть форм не дают
      рёбер и остаются `high`, `global` ребро сохраняет, диспетч-таблица уровня модуля не тронута;
      **0 подавленных рёбер** на codemap и bquant. +10 тестов, сьют 415→**425**. **Замечание по методике:**
      bquant в этот момент активно правился соседним агентом (файлы исчезали между чтениями), поэтому
      сравнения «до/после» на нём делались только вплотную по времени, а детерминизм проверялся на
      **замороженном снимке** — на нём граф байт-идентичен.
- [ ] **R1-C23 (ось B2) робастность на трудном Python — симлинк превращает 17 файлов в 615 модулей** 🆕
      ⬜ **замерено и спроектировано 2026-08-25, не построено.** Не репорт извне, а **упреждающий замер**
      последней открытой оси: именно B2 в прошлый раз отдала issues [#4](https://github.com/kogriv/codemap/issues/4)
      / [#5](https://github.com/kogriv/codemap/issues/5) в первые 20 минут первой чужой сборки. Проба —
      пакет на 17 файлов (2814 байт, 157 loc), по модулю на конструкцию: метакласс + `__init_subclass__`,
      `type()`-класс, модульный `__getattr__`, monkeypatch, условные импорты, PEP 695 (`def f[T]`,
      `class C[T]`, `type X = …`), `match`/walrus, async, `Protocol`, `@overload`, `functools.wraps`,
      `singledispatch`, star-импорт, взаимные импорты, `.pyi`, BOM, пустой файл, синтаксическая ошибка,
      latin-1, симлинк каталога на самого себя. **Сборка: exit 0, ни одного предупреждения.**
      **Сначала — что держится** (честность в обе стороны): метаклассы, `type()`-класс (записан как
      **attribute**, а не выдуман классом), PEP 562, monkeypatch, PEP 695-генерики, `match`, async,
      `singledispatch`, взаимные импорты, BOM, пустой файл, `.py` рядом с `.pyi` — всё корректно, и
      **`dead-code high` пуст** — ни одного ложного уверенного утверждения. Значит это не переписывание
      экстрактора, а **пять узких дыр**. **Замерено:** ① **симлинк-цикл** `loop → .` → **615 модулей вместо
      15** (600 фантомных, 98%), **2378 узлов / 3771 ребро вместо 58 / 91**, вложенность до глубины **40**,
      молча; при этом `codemap scope` на том же дереве отвечает **`files: 17`** — **две половины одного тула
      расходятся в 36 раз, и никто их не сравнивает**; ② **нечитаемый файл просто исчезает** — `broken.py`
      (синтаксис) и `latin1.py` (не-UTF-8) отсутствуют в графе без единого слова: тот же класс, что #5 —
      отчёт о дереве, которое не прочитали, отрендерен как справка о здоровье; ③ **`from X import *` не даёт
      `imports`-ребра** вообще → зависимость невидима для `architecture` (слои, циклы) и `check`;
      ④ **строковые / `TYPE_CHECKING` аннотации невидимы** (`-> "Base"` — ничего, `-> Reader` — ребро), а
      это ровно идиома для типов, которые иначе дали бы циклический импорт; ⑤ **stub-only модуль подаётся
      как настоящий код** (`api.pyi` без `api.py` → функция, которой в рантайме нет). Плюс две честные
      неполноты «на заметку»: PEP 695 `type Alias = …` не даёт узла; функция-локальный
      `from .x import a_fn` + `return a_fn` не даёт ссылки. **План (дизайн
      `docs/design/hard_python_robustness.md`, D1–D7):** D1 канонизация пути + visited-set (не запрет
      симлинков — легальный layout); D2 экстрактор **возвращает** список пропущенных входов, `build` их
      **называет**; D3 ребро `imports` для star-импорта (точное; раскрытие имён — отдельно, отложено как
      неизмеренное); D4 парсить строковые аннотации тем же путём, с тем же `resolution="annotation"`,
      **размер мерить до мержа** (урок D3 из R1-C22: 5202 сайта → 21 ребро); D5 `extras.stub=true` и
      исключение из dead-code вместо выдумывания; **D6 — главное: дериватив-сверка «модулей в графе vs
      файлов в scope-манифесте»**, ловит ① не зная про симлинки и ② не зная про синтаксис — закон сохранения,
      а не эвристика (и на #5 бы сработала). **Зависимость:** D2 и D6 нужен носитель, который путешествует
      вместе с графом → **сначала R1-C25**, иначе носитель придётся мигрировать. **Приёмка — НЕ
      байт-идентичность** (D3/D4 добавляют истинные рёбра, D1 убирает фиктивные): фикстура даёт 15/58/91 при
      живом симлинке; оба нечитаемых файла названы на stdout; D6 срабатывает на симлинке и на битом файле и
      **молчит** на codemap/bquant/всех фикстурах. **Гэп:** `gaps/hard_python_robustness_2026-08-25.md`.
- [ ] **R1-C24 (ось A10) test-mapping: «какие тесты покрывают X» — ответа нет, а наивный неверен в 82%** 🆕
      ⬜ **замерено и спроектировано 2026-08-25, не построено.** Ось в watchlist с 2026-07-30 («реальная
      задача упёрлась в отсутствие среза символ→тесты»). Замер на самом codemap
      (`build codemap --consumer tests --mode full`, оба тира): 1492 узла, 3585/4117 рёбер, **416 тест-функций,
      380 core-функций и классов**. **① Прямой ответ пуст для 82%:** входящее ребро от `tests.*` есть у
      **68/380 (18%)** — а это ровно то, что сегодня возвращают `callers`/`references_to`. Достижимость от
      тест-функций: **225/380 (59%) fast**, **304/380 (80%) deep**. Тест зовёт `extract()`, `extract()` зовёт
      двести вещей — почти ничто из проверяемого тестом не **названо** в тесте. **② Fast-тир здесь
      структурно нежизнеспособен, потому что тесты зовут методы на объекте:** входящие `calls` разрешены у
      **91% свободных функций, но лишь у 21% методов** (deep: 92% / **56%**). `Query.hotspots`,
      `Query.references_to`, `Query.consumers` покрыты реальными тестами и имеют **ноль** входящих вызовов на
      fast. **③ Достижимый ответ слишком велик, чтобы им пользоваться:** медиана **21** теста на символ,
      максимум **126** (из 416); только ближняя полоса — медиана **6.5**, p90 **66**. Распределение
      кратчайшей дистанции: 1 хоп — 63 символа, 2 — 95, 3 — 49, 4 — 64, 5 — 28, 6 — 5. **Ранжирование здесь
      не полировка, а сама фича.** **④ Шов pytest-фикстур не смоделирован:** **262 из 416 (63%)** тест-функций
      получают предмет параметром, 19 фикстур, **0 рёбер** тест→фикстура (17 существующих — `contains`
      модуль→фикстура). Структурно это шов F5/M7 (фабрика+реестр+вызов). **Но замеренная цена на этом репо —
      0 символов** (фикстуры достают подмножество того, что достают тела тестов), то есть шов стоит
      **атрибуции**, а не покрытия; и свидетель слабый — **у codemap нет `conftest.py`**, худшая форма шва тут
      не представлена вовсе. **⑤ 41% символов не достижимы ни одним тестом** (155/380 fast, 76 deep) — и этому
      числу пока верить нельзя: большая часть разницы — это ②, а не отсутствие тестов; любая поверхность
      обязана подавать это как **нижнюю границу покрытия**, а не как «не покрыто». **План (дизайн
      `docs/design/test_mapping.md`, D1–D6):** D1 «тест» **выводится**, не хранится (роль консьюмер-рута +
      имя по правилу pytest) — фикстура фреймворка не запекается в артефакт, и старые графы получают фичу без
      пересборки; D2 достижимость с **полосами по дистанции**, ближняя непустая полоса, жёсткий кап 25 и
      `log` того, что отрезано (правило «никаких молчаливых капов»), **две обязательные пометки** —
      over-set («достиг ≠ проверяет») и нижняя граница («динамика невидима»); эвристики похожести имён
      **отвергнуты** — дистанция это факт о графе, похожесть это догадка о намерении; D3 **тир — часть
      ответа**, на `fast` предупреждение (21% методов — не основание для «вот твои тесты»), но не отказ и не
      скрытая пересборка; D4 мост фикстур по имени вдоль цепочки conftest, ребро `references` с
      `resolution="fixture"` (не `calls` — зовёт pytest), **перед реализацией замерить на сьюте с conftest**,
      иначе кандидат на отсрочку; D5 поверхность `Query.tests_for` → op `tests` → `codemap tests <symbol>`,
      отдающая **pytest node id** (`tests/x.py::test_y`), иначе это упражнение по чтению, а не команда;
      обратный вопрос («что покрывает этот тест») — тем же индексом, бесплатно. **Приёмка — precision/recall
      против `coverage.py`, а не «выглядит разумно»** (дисциплина F14/F15): выборка 20 символов, оба тира,
      публикуем и плохие числа; главный показатель — **recall ближней полосы**; любой символ с «ноль тестов»
      сверяется с coverage — ложное «его ничто не покрывает» это тот же аффирматив над слепотой, под который
      уже выпущено четыре фикса. **Гэп:** `gaps/test_mapping_2026-08-25.md`.
- [ ] **R1-C25 провенанс графа: артефакт не говорит, кто его собрал, из чего и когда он перестал быть правдой** 🆕
      ⬜ **замерено и спроектировано 2026-08-25, не построено.** Источник — **прожитый эпизод** на R1-C22-f1:
      `test_determinism_with_semantics` покраснел, и причина была **не** в недетерминизме — таргет правился
      соседним процессом между двумя сборками. Ни граф, ни тест, ни тул не могли отличить «инструмент
      недетерминирован» от «вход сдвинулся»; развели вручную, пересборкой на замороженной копии. **Гэп:** у
      `graph.json` ровно четыре ключа верхнего уровня — `codemap_schema`, `target`, `nodes`, `edges`. Ни
      версии тула, ни ревизии исходника, ни тира, ни `scope_id`. А `codemap_schema` — единственное, что
      выглядит провенансом, — **пишется и никогда не читается**: `Graph.from_dict` и `store.load` его
      игнорируют. **Замер:** замороженная копия `tests/fixtures/refpkg`, собранная codemap'ом на `4858899` и
      на `16fe7de` (4 коммита) — **30 рёбер против 38**, `dead-code high` — **12 против 7**. Пять функций,
      которых один граф зовёт мёртвыми, а другой живыми; **оба объявляют `codemap_schema: "0.11"`**, и
      текущий тул грузит любой без единого слова. И заметь, что здесь **ничего не нарушено**: R1-C22 не
      добавила ни kind'а, ни типа ребра — только `extras`, которые DESIGN §2 намеренно оставляет открытыми,
      то есть **семантика изменилась правильно, и версия схемы правильно не двинулась**. В этом весь довод:
      **провенанс — не схема**; схема описывает форму файла, процесс не описывает ничто. `codemap diff` на
      этой паре отвечает «✅ No breaking changes» — верно (публичный API не менялся) и потому бесполезно как
      страховка. **Сайдкар не закрывает гэп:** `*.meta.json` действительно несёт `argv/built_at/cwd/target` +
      `scope{scope_id, git, files, profile}`, но (1) это **отдельный файл**, а граф путешествует один —
      в тикет, в соседний репо, агенту, в контейнер; (2) он **в `.gitignore`**, то есть ровно та половина,
      которой нельзя поделиться; (3) он **best-effort**: у лежащего сейчас в дереве bquant-сайдкара **нет
      ключа `scope` вообще**; (4) он пишет **`cwd`** — абсолютный личный путь, что по AGENTS.md делает его
      единственным файлом, который публиковать **нельзя**. **План (дизайн `docs/design/graph_provenance.md`,
      D1–D7):** D1 блок `provenance` **внутри** `graph.json`, схема **0.11 → 0.12** (первая правка с 0.11,
      которая бампа реально заслуживает — меняется форма), **без `built_at`**: детерминизм важнее, часы
      остаются в сайдкаре; D2 `version` всегда + `commit` когда резолвится, **никогда не выдумывать** —
      обе сборки из замера сделаны версией `0.0.2`, одной версии мало; хеш исходников экстрактора **отвергнут**
      (меняется от правки комментария, кричит волком); D3 **проверять `codemap_schema` при загрузке** —
      грузим, но громко (старее / новее / нечитаемо → предупреждение на трёх поверхностях: CLI, `stats`,
      конверт `serve`/MCP), отказ отвергнут (все существующие графы 0.11 и старше); D4 **`diff` сверяет
      провенанс первым** и предупреждает, когда пара несравнима (разный тул/тир/скоуп), но не отказывает;
      D5 **никаких абсолютных путей** в артефакте — тест на это (AGENTS.md); D6 явный раздел: **идентичность
      едет в графе, рецепт пересборки остаётся в сайдкаре** (`scope_id` дублируется намеренно: в графе —
      идентичность, в сайдкаре — ключ кэша для `--incremental`). **Приёмка:** байт-идентичность двух сборок
      замороженного дерева **включая** `provenance` (инвариант, которым эта правка рискует больше всего —
      тест первым); эксперимент из §2 гэпа **инвертируется** (старый граф грузится с видимым предупреждением,
      `diff` называет пару несравнимой); ноль абсолютных путей; `commit` **отсутствует**, а не выдуман, при
      установке из wheel; все 0.11-графы грузятся. **Разблокирует:** R1-C23 D2 и D6 (обоим нужен носитель) —
      поэтому **строить первым из трёх**; и пост блога **P4** (детерминизм), который намеренно ждал
      настоящего эпизода (у P5 «провенанс» — про другое: роли мульти-рута, это соседство R1-C24). **Гэп:** `gaps/graph_provenance_2026-08-25.md`.

#### Tier 3 — крупные / стратегические, строго по нужде

- [x] **R1-C9 Инкрементальные обновления графа** ✅ (2026-08-23, без схемы) — строится на M19.A
      (per-file sha256 манифест) + M18 (sidecar `.meta.json` со scope). **Ключевой замер:** полный deep-экстракт
      bquant ~97s, из них **~93s — jedi-тир** (`add_behavior(deep)` + `add_attrflow(deep)`); всё остальное
      (griffe + структура + dispatch + family + dataflow) ~4s. Значит инкремент имеет смысл только для deep, и
      единственная дорогая помодульная работа — два jedi-паса. **Сделано:** `codemap/incremental.py`
      `update_graph(old, pkg, old_scope, new_scope, deep)` — дешёвые пасы гоняются целиком и свежими каждый
      раз (всегда корректно), два jedi-паса — только на **affected**-модулях (`only=`-параметр в
      `add_behavior`/`add_attrflow`), остальное сплайсится из старого графа (calls/accesses-рёбра +
      extras calls/control/complexity/attr_access). **Affected** = changed/added/removed ∪ свежие импортёры
      изменённого ∪ старые зависимые (old-рёбра в изменённое). Fallback на полный ре-билд при >50% задетых.
      CLI `build --incremental` (переиспользует `--out`-граф + scope-sidecar). `to_dict` теперь сортирует
      рёбра и по `extras` → порядок insertion-независим (сплайс сериализуется как полный билд).
      **Приёмка:** правка одного файла → **incremental deep ~5s vs full ~60s (~12×)**, только 2 модуля
      пересчитаны; на fast-тире **байт-в-байт идентично полному** (bquant 7437 рёбер, 0 расхождений),
      +12 тестов (byte-identity на edit/add/remove/оба тира + no-op + fallback). **Открытие (важное, честное):**
      deep-тир **не детерминирован** — **два полных deep-билда bquant сами отличаются** на пару deep-рёбер
      (jedi bounded inference зависит от прогретости кэша: `resolved 11↔12`). Значит «идентично полному» —
      строго только на fast-тире; на deep инкремент идентичен полному **с точностью до собственной вариативности
      jedi** (её же имеют и полные билды), сам сплайс точен (доказано byte-identity на стабильной фикстуре).
      Задокументировано в `docs/incremental.md`. **Питает** отложенный M3.2 watcher (hot-path `mode=unchanged`).
- [ ] **R1-C10 lightweight навигатор графа** (L) — ниша ушедшего Sourcetrail без GUI-налога.
      **Scope:** статический self-contained HTML/mermaid-навигатор поверх `graph.json` (клик по символу →
      соседи/impact), генерится `codemap export --view web`. **Зачем:** Sourcetrail умер на поддержке
      кросс-платформенного GUI; наш детерминированный граф закрывает нишу дёшево. **Приёмка:** один HTML
      открывается без сервера, навигация по bquant-графу работает офлайн. **Оценка:** L.
- [ ] **R1-C11 tree-sitter multi-language backend** (XL) — выход за Python. **Scope:** tree-sitter (доказано
      ast-grep) как source-only/детерминированный/offline бэкенд *ширины*; **глубина (call-graph/impact/
      contracts) остаётся за jedi/griffe** — это ров codemap. **Зачем:** мультиязычность. **Приёмка:**
      структура (defs/imports) для ≥1 не-Python языка в том же графе. **Оценка:** XL. **Смыкается с**
      «Мультиязычность» ниже; брать только при явной нужде.
- [ ] **R1-C12 rope-безопасные правки** (L) — опциональный слой мутаций (rename по вычисленному
      blast-radius). **Нарушает read-only-дефолт** — держать за отдельным флагом/extra; read-only остаётся
      дефолтом. **Зачем:** от анализа к безопасным правкам. **Приёмка:** rename символа по impact-радиусу,
      dry-run по умолчанию. **Оценка:** L. Только если codemap пойдёт к правкам.

#### Позиционирование (доки, дёшево, не код)

- [x] **R1-C13 Бенчмарк call-graph + grep-vs-graph + честный потолок** ✅ (2026-08-14, без схемы). Приёмка
      закрыта: **`docs/accuracy.md`** (раздел) + два бенч-скрипта + CI-тесты (`tests/test_r1c13_*.py`).
      **(a) точность/потолок:** PyCG-как-оракул — **спайк-негатив** (`research/tools/pycg.md`): PyCG 0.0.8
      не запускается на Python 3.12 (import-hook хачит stdlib, падает даже на 3-строчном файле — три
      слоя поломки, третий структурный; та же «хюбрис-зона», что и graphlens). **Пивот:** свой
      **ручной ground-truth микро-сьют** (`research/bench/callgraph_truth/`, 10 кейсов: direct/self/
      cross-module/higher-order/decorator/inheritance/getattr/local-var/registry/closure) → deep-tier
      **precision 100% / recall(decidable) 100% / recall(all) 60%** (`callgraph_accuracy.py`). Литературный
      потолок PyCG (~99% precision / ~70% recall, ICSE 2021) процитирован, не запускался. Intrinsic-резолв
      на bquant@cb89a24: 6323 call-sites → 25.7% resolved / 46.1% external / 28.2% unresolved. **(b)
      grep-vs-graph:** `grep_vs_graph.py` (авто-таргеты, без черри-пика) на bquant: BREAKAGE — граф дешевле
      grep в **~11× (unique) → ~38× (polymorphic, до 55× на `calculate`)**; WHERE-DEFINED — **~1× (нет
      выигрыша, grep `def NAME` уже точен)** — честный нуль удержан. Дифференциатор: ценность графа на
      **связях, не локациях**. Дожфуд-CI на самом codemap (fast-tier, <1с).
- [x] **R1-C13-f1 (soundness) fast-tier наследование → фантомный таргет** ✅ (2026-08-14, без схемы) — из
      микро-сьюта (c06). `_class_scope`→`_class_members` теперь маппит каждый унаследованный член на
      **класс-владелец** (свой или базовый), и `self.<inherited>()` резолвится в реальный id базового
      метода, а не в фантом `ThisClass.<inherited>`. fast-precision 87.5% → **100%**.
- [x] **R1-C13-f2 (soundness) call в замыкание → ребро в неузел** ✅ (2026-08-14, без схемы) — из
      микро-сьюта (c10). Общий guard в `_process_function`: внутреннее call-ребро с таргетом-неузлом
      (локаль, которую jedi типизировал в её же scope-path; вложенная/closure-функция) **даунгрейдится в
      unresolved**, а не эмитится в никуда. Побочно убрало **40 латентных фантомов** на bquant-графе
      (callers/callees/impact больше не всплывают id, которых нет как узла). Материализация closure-узлов —
      будущая работа.
- [x] **R1-C14 Позиционные доки** ✅ (2026-08-06) — заведён **`research/positioning.md`** — публикационный
      слой (build-story hub): Story Zero (codemap + роадмэп M0→M19, дифференциаторы, честные дыры) + полная
      **Build-story #1 (graphlens)** с цифрами и «эмоцией» по горячим следам. Тезис: «codemap = точная
      структурная нога для index-free агентов через MCP» (не замена embeddings-RAG); дифференциаторы
      (каноничный diffable граф + provenance + agent/MCP-глаголы; **MIT** против non-commercial у GitNexus;
      SCIP-interop; honesty). **Закрыто:** корневой `README.md` получил секцию **How it compares** (тезис +
      позиционная строка + линки на positioning.md/comparison.md). Наполнять build-story по мере разборов
      (это continuous — живёт в positioning.md, не блокирует R1-C14). **R1.5 добавил остроты:** ниша
      переполнена → ров заявлять громко.
- [x] **R1-C15 Living docs из графа** ✅ (2026-08-07, без схемы). `codemap export docs` — нарративный документ,
      организованный **по подсистемам** (communities R1-C18), а не плоско по модулям. `serve/livingdocs.py`
      `render_docs`. **Honesty-контракт = дифференциатор** (vs CodeWiki/нейростатьи, которые галлюцинируют):
      всё трассируемо — структура (модули/классы/функции/imports/inheritance) = точный факт; докстринги
      цитируются **verbatim** (слова авторов, не генерятся); недокументированный символ **помечается**
      (`_(undocumented)_`), не выдумывается; call-flow-секции несут `epistemic: partial` (нижняя граница).
      Секции: overview+counts → subsystems (с публичными символами) → ungrouped-модули (полнота) → behavioural
      entry points (flows) → architecture-заметки (циклы/violations/god-objects) → honesty-footer. CLI
      `export docs [-o]` + serve export-view `docs`. **Core-only** (не документируем tests/docs-роуты).
      **Побочный фикс:** `Query.communities()` теперь кластеризует **только core**-модули (consumer-роуты
      утягивали ярлык в «(root)») — улучшило и R1-C18: на bquant ярлыки стали реальными (data/analysis/
      indicators вместо «(root) 45»). **Проверено на bquant:** 165 модулей, подсистемы, docstrings verbatim,
      god-objects, footer. +11 тестов. Полный прогон 220 passed/1 skip. Питается communities+flows+epistemic.
- [x] **R1-C16 Роутер/адаптер-слой над внешними тулами** ✅ (2026-08-16, без схемы графа). **Обе половины
      готовы и разведены.** Router-путь был (GitNexus passthrough, `codemap route`); достроена **adapter-
      половина**: базовый контракт `SemanticHit` + retrieval-поверхность `Integration.search()`
      (`integrations/base.py`); **cocoindex-адаптер** (`integrations/cocoindex.py`, Apache-2.0, capability
      `semantic-search` — зовёт `ccc search --json` в cwd репо, отдаёт сырые хиты); **энричер**
      `integrations/semantic.py` — резолвит ADAPTER (не router), мапит каждый fuzzy-хит `(file,line)` →
      **точный символ codemap** через `Query.symbol_at`, дедуп по символу (лучший score), сортировка.
      `registry.resolve(mode=ADAPTER)` — фильтр по режиму (semantic берёт именно адаптер, не роутер).
      Поверхности: **CLI `codemap semantic "<query>"`** (--build/--graph, --root, --limit, --format) + serve-op
      `semantic` + **MCP-tool `semantic_search`**. Лицензионная политика машинно-проверяется (adapter не-
      permissive → ValueError). Ядро работает без тула (нет adapter → `{resolver:None, hits:[]}`, не падение).
      **Приёмка выполнена:** detect (which ccc) ✅, opt-in (codemap.toml) ✅, оговорка (router-путь) ✅, **перевод
      в символы** (adapter) ✅, degrade ✅. +12 тестов (FakeAdapter — обобщённый путь; monkeypatch cocoindex
      argv/parse; live-skip если нет ccc). Доки `docs/integrations.md`. **Обобщено под будущие адаптеры**
      (любой permissive retrieval-тул регистрируется так же). Оригинальная карточка ниже 👇
- [ ] **R1-C16 (исходная формулировка)** (L) — 🆕 (2026-08-06, из разбора GitNexus). codemap
      не только самописный тул, но и **каркас-роутер** над сторонними: для способностей, которых у нас нет и
      строить свои нет смысла (семантический поиск, много языков, flow/community-нарратив), **вызывать чужой
      тул за адаптером** и переводить результат в наш нейтральный граф-контракт (реализует **DESIGN §13**).
      Два режима: **адаптер** (переводим ответ в нашу схему — только для лицензионно-совместимых, MIT/Apache)
      и **роутер** (перенаправляем вопрос, отдаём ответ как есть — для тяжёлых/чужих, opt-in subprocess).
      **Лицензионная политика интеграций (решено с пользователем 2026-08-06):** (1) **никогда не бандлить**
      внешний тул — только вызов установленного пользователем (codemap ничего не распространяет → ядро остаётся
      чистым MIT); (2) **opt-in, не по умолчанию**; (3) **оговорка по критерию «использование», не «перепродажа»**
      — для non-commercial-тулов (PolyForm-NC и т.п.) показывать разовую оговорку: *«тул X под лицензией
      PolyForm Noncommercial; этот маршрут — только для некоммерческого использования; при коммерческом не
      задействуйте его / возьмите enterprise-лицензию у автора»*; (4) при открытии codemap — **спросить автора**
      тула про явное разрешение на роутинг. Приватная фаза: ограничений нет. **Первый капабилити-кандидат
      ПОДТВЕРЖДЁН разбором (2026-08-16):** семантический поиск через **cocoindex-code (`ccc`)** —
      Apache-2.0, локальный (без БД/ключа), CLI+MCP, hands-on-измерен (`research/tools/cocoindex-code.md`);
      лицензионно-чистый → пригоден к **adapter** (перевод в наш контракт), не только `route`. GitNexus остаётся
      `learn` + NC-routable-plugin (не adapter). **Приёмка:** `codemap` умеет продетектить
      установленный внешний тул, сроутить в него opt-in запрос, показать лицензионную оговорку, перевести/
      прокинуть ответ; ядро работает и без него. **Оценка:** L. Связь: DESIGN §13, [research/tools/gitnexus.md],
      реестр кандидатов (§13.1).
- [x] **R1-C16-f1 (router) `npx`-фоллбэк детекта GitNexus** ✅ (2026-08-15, без схемы) — из живого вопроса
      «почему `which gitnexus` пусто, мы же ставили». Причина: GitNexus ставится как **локальный** npm-пакет
      (`npm install gitnexus`, 1.7 ГБ `node_modules` → бин в `./node_modules/.bin/`, запуск через `npx`),
      глобального `gitnexus` на PATH не было **никогда**; наш `is_available()` дергал только
      `which("gitnexus")` → всегда «unavailable». **Фикс:** `GitNexusRouter._launcher()` — глобальный бин,
      если на PATH; иначе `npx --no-install gitnexus` (работает с локальной инсталляцией, **без скрытой
      сетевой доустановки** — при отсутствии деградирует в None, не качает); иначе None. `is_available()`/
      `route()` идут через launcher, argv собирается launcher-независимо (`_verb_argv`). Снимает «setup
      friction — high» из карточки: роутер живёт без `npm install -g`. +5 тестов. Связь:
      [research/tools/gitnexus.md], DESIGN §13.1.

#### Из разбора graphlens + GitNexus (2026-08-07) — что встраивать в продукт

Прогон обоих проработанных тулов через рамку решения (DESIGN §13.1). Вывод: почти всё уникальное строится
**на своём графе** (networkx + канон уже есть) и лучше ложится на тезис детерминизм/provenance; настоящий
адаптер один.

- [~] **R1-C17 graphlens-адаптер: резолв внутрь зависимостей** — 🔬 **спайк сделан (2026-08-07) → ОТЛОЖЕНО (негатив)**.
      Гипотеза: codemap source-only-of-target (не резолвит в библиотеки), graphlens (MIT, `ty`-бэкенд) умеет — обернуть
      адаптером, `calls_external` → `external_symbol` в сайдкар. **Спайк-first проверил на синтетике** (`mypkg.core.dump`
      зовёт `json.dumps`; контроль — `caller`→`helper`): graphlens **действительно** пишет cross-boundary-рёбра
      (`calls: dump → external_symbol`, `resolves_to: import json → external_symbol {origin: stdlib}`, `has_type` на
      внешние типы) — этого у codemap нет. **НО два блокера убивают ценность сейчас:** (1) **внешний член не именуется** —
      цель вызова = span-плейсхолдер `call@6:17`, а не `json.dumps`; graphlens знает «вызов уходит в stdlib здесь», но не
      *какой* символ → заявленная ценность «какой pandas-API зовёт код» не отдаётся на symbol-гранулярности; (2) **реальный
      third-party кейс ломает резолвер** — на pandas `ty server` таймаутил (1s/30s повторно), 0 узлов за 10+ мин; собрался
      только stdlib-only проект, эмбеддинги упали (нет egress). **Вывод:** абсорбировать недетерминированные, низко-
      разрешённые, хрупкие данные в сайдкар ради маржинального выигрыша над уже имеющимися external-leaf-узлами codemap —
      не стоит. **Пересмотреть если:** graphlens начнёт именовать внешний член (не span) и/или ty стабилизируется на
      тяжёлых deps. Спайк-first гейт сработал — сэкономил постройку P3. Связь: DESIGN §13.1, [research/tools/graphlens.md].
- [x] **R1-C18 Communities + flows (на своём графе)** ✅ (2026-08-07, без схемы). Построено на своём графе +
      networkx (подсмотрено у GitNexus, но считаем сами — детерминированно). (a) `Query.communities()` — кластеры
      модулей через **greedy_modularity_communities** (детерминизм by construction, on-brand vs seed-Louvain) над
      undirected import-графом, ярлык = доминирующий слой; (b) `Query.entry_points()` — корни call-леса (зовут, но
      не зовомы) по роуту; (c) `Query.flow(entry, max_depth)` — форвардный call-flow по `calls` (зеркало impact),
      рёбра с distance, cycle-safe. Рендер `serve/subsystems.py` (`render_communities`/`render_flows`); CLI
      `report communities` + `report flows [--symbol X] [--depth N]`; serve-ops `communities`/`flows`; **MCP-tools**
      `communities`/`flows` (18→20). **Проверено на bquant:** 16 кластеров подсистем; 224 entry points,
      ранжированы по reach (swing `calculate` → 32). +11 тестов (конструированные 2-кластера + call-chain; CLI;
      serve). Полный прогон 204 passed/1 skip. **Питает R1-C15** (living docs). Строим сами (не wrap).
- [x] **R1-C19 Транзитивный impact + depth-гистограмма + risk** ✅ (2026-08-07, без схемы). Транзитивный BFS уже
      был (M6.6, `impact(depth=2)` метит `distance`); добавлено то, чего не было и что подсмотрено у GitNexus, но
      построено **на своём графе**: (1) `by_distance`-гистограмма + `max_distance` в `Query.impact`; (2) эвристичный
      **`risk`** (none/low/medium/high) из формы blast-radius — breadth × reach × **root-spread** (последнее —
      наш провенанс-дифференциатор: символ, задетый в core+tests+docs, дороже менять); (3) `--depth` на CLI
      `report impact` + проброс в serve report-op; (4) рендер показывает Risk + гистограмму. MCP-compact сохраняет
      новые поля (они на entry, не на refs). **Проверено на bquant:** `MACDZoneAnalyzer` → 28 refs (core 2/docs 7/
      tests 19), Risk MEDIUM (3 роута), d1×28. +10 тестов (конструированный граф — точный контроль; CLI; serve).
      Полный прогон 193 passed/1 skip. Строим сами (не wrap). Смыкается с M6 (impact) и R1-C5 (diff).
- [x] **R1-C13 (расширение) epistemic-метка** ✅ (2026-08-07, без схемы). Вариант 1 (одна метка на ответ, без
      per-edge confidence — рёбра уже несут `resolution`). Serve-конверт для call-graph-зависимых ops
      (`callers`/`callees`/`impact`/`flows`/`call_contract`) несёт `epistemic: "partial"` + причина —
      машиночитаемый двойник прозаических дисклеймеров; структурные ops (imports/contains/…) метку не несут
      (отсутствие = exact). Переживает MCP-компакцию. +5 тестов. Полный прогон 209 passed/1 skip. Остаток
      R1-C13 (бенчмарк PyCG + grep-vs-graph) — отдельно, см. основной R1-C13 выше.

---

## M19 — Модель скоупа: манифест входа (детерминизм на входе) 🟡 ДИЗАЙН (2026-08-02)

**Дизайн:** [docs/design/scope.md](docs/design/scope.md) (на ревью, до кода). **Мотив:** codemap
детерминирован на **выходе** (`graph.json`), но про **вход** фиксирует только команду сборки (M18-мета);
конкретный набор файлов лишь приблизительно восстановим, без контент-хэшей и профиля. Нужно для (1)
воспроизводимости/трекинга изменений codemap и (2) **валидных сравнений R2** (доказать, что тулы видели
байт-идентичный вход — пилот graphlens показал, как `venv_bquant` тихо меняет скоуп).

**Модель (общая):** spec (декларативный набор: roots+role, include/exclude с дефолтами против venv_*/кэшей)
→ резолв в отсортированный список файлов → **манифест** `{path, sha256, bytes}` + **профиль** (файлы/байты/
by_role/by_ext/py_loc) → **`scope_id`** (sha256 по отсортированным `path\tsha256`). Одинаковый `scope_id` ⇒
доказуемо одинаковый вход.

- [x] **M19.A codemap-фича: манифест входа** ✅ (2026-08-02) — `codemap/scope.py` (резолв+хэш+профиль+`scope_id`);
      **git-биндинг (O6 ✅):** перечисление через `git ls-files` в git-репо (gitignore-корректный набор —
      venv/build/кэши исключены сами) + fs-fallback; блок `git {commit,ref,dirty,dirty_files}` и бесплатные
      `git_blob` в манифесте; **идентичность = наш sha256** (mode-independent). CLI
      `codemap scope <path> [--consumer/--docs/--spec] [--no-git] [--json]` (резолв без сборки) и
      `codemap scope --diff <a.meta> <b.meta>` (делегирует `git diff`, когда обе стороны git-clean);
      `build` пишет блок `scope` в M18-сайдкар. `graph.json` остаётся чисто структурным (без схемы).
      Тесты: детерминизм, флип одного хэша, `--diff`, excludes, git-mode vs fs-mode, dirty. **Субстрат для
      отложенного:** контент-хэши = вход Merkle для **R1-C9** и hash-свежести для **M3.2**. Три пункта сходятся сюда.
- [x] **R2.0.1 харнесс бенч-скоупа** ✅ (2026-08-03) — см. ниже, в R2 (реализован поверх M19.A).

**Решения — все приняты (2026-08-02):** O1 `scope_id` только в сайдкаре (граф структурный) · **O2 — in-place
поверх реального дерева = дефолт** (живой/интерактивный/инкрементальный путь; git-режим держит набор чистым
без копий); **materialize — только бенч-костыль** для несговорчивых чужих тулов (§1.6) · O3 sha-256 full ·
O4 JSON-spec · O5 включать не-код `.md` · O6 git-биндинг (перечисление/провенанс/diff; идентичность = sha256).
Детали — в дизайн-доке. **Готово к реализации.**

---

## R2 — Глубокий разбор тулов (per-tool, hands-on) 🟢 АКТИВЕН (2026-08-02)

R1 закартировал поле сверху вниз; **R2** идёт по каждому тулу с **hands-on-замером на общей мишени**
(bquant) → карточка на тул в `research/tools/` + сводка `research/comparison.md` (матрица покрытия +
качество). Конвенция (codemap-native, на принципах tgsh) — в `research/README.md`.

**Решения (2026-08-02):** конвенция — **своя, codemap-native** (заточка под граф/замеры); **hands-on
всем** релевантным тулам (не только прямым конкурентам); **пилот — graphlens-mcp** (ближайший близнец +
у автора есть 936-прогонный бенч) для локировки формата.

**Принципы (из tgsh):** разбор ДО постройки соответствующей R1-C; «приходим с измерениями, а не с
приговором» (авторы — потенциальные соавторы); лицензии (читать/учиться — да, копировать код без
лицензии — нет); честная граница «что не проверяли» обязательна.

**Общий task-set** (ответ codemap = эталон): T1 где определён (`analyze_zones`) · T2 callers
(`MACDZoneAnalyzer`) · T3 impact (`MACDZoneAnalyzer`) · T4 что сломается при смене сигнатуры
(`analyze_zones`) · T5 архитектура/слои. Метрики: корректность · стоимость (токены/tool-calls) ·
латентность · детерминизм.

- [~] **R2.0 Конвенция + каркас** ✅ (2026-08-02) — `research/README.md` (конвенция), `research/tools/README.md`
      (шаблон карточки), `research/comparison.md` (сводная матрица, засеяна из R1/R1.5 на desk-уровне).
- [x] **R2.0.1 Харнесс бенч-скоупа** ✅ (2026-08-03) — единый источник правды для входа бенча.
      `research/tools/_scope/bquant.scope.json` (spec: 6 каталогов, venv исключён, с `expected`-блоком) +
      `materialize.py` (переиспользует `codemap.scope.resolve_scope` из M19.A → **копирует РОВНО файлы
      манифеста** → staging несёт тот же `scope_id`; self-verify round-trip). **codemap сам — in-place**;
      материализация только для venv-trap тулов. Канонический бенч-скоуп зафиксирован:
      **`scope_id sha256:300e0a01…5e47d2`**, `bquant@cb89a24`, **280 файлов** (207 .py / 73 .md;
      core 90 / tests 81 / docs 56 / research 30 / examples 12 / scripts 11). Поле **Scope** добавлено в
      шаблон карточки (`tools/README.md`) и `comparison.md` (якорь парити); graphlens-карточка ретро-проставлена
      (с честной пометкой: фактический прогон — на почти-идентичном ад-хок staging 285 файлов, +5 генерённых
      `docs/_build`). Проверено: `materialize` → 280 файлов, verify `== canonical ✓`.
- [x] **R2.1 Пилот: graphlens-mcp** ✅ (2026-08-02, **переизмерено 2026-08-03**) — полный hands-on разбор.
      Карточка `research/tools/graphlens.md`. Итоги: (1) **баг скоупа** — игнорит `.gitignore`, отсекает venv
      по хардкод-именам → `venv_bquant` утянул весь venv (>3ч45м/9ГБ); воркэраунд — чистое дерево/пакет.
      (2) **ИСПРАВЛЕНИЕ вывода первого прохода:** «T2/T3 пусто» было **нашим** окружением, не слабостью тула —
      graphlens бандлит `ty`, но ищет его через `shutil.which("ty")`, а `uv tool install` не кладёт
      бандл-`bin/` на PATH → тихий degrade в tree-sitter-only. Фикс: `ty` на PATH → `resolver_status: ok`.
      (3) Переизмерено на том же staging: type-resolved индексация **2м20с/424МБ/31МБ БД/32399 узлов/55691 ребро**
      (degraded было 12с/17.5МБ/16796). `relations` **работает** — `MACDZoneAnalyzer`: 9 callers+1 callee+2 refs
      (тесты авто-скрыты), ≈ codemap-овские 12 не-тестовых из 31. **T4/T5 инструментов реально нет.**
      Вердикт **learn (достойный peer, а не «пусто»)**; питает R1-C13 (бенч должен проверять `resolver_status==ok`)
      и R1-C14 (дифференциаторы: детерминизм, single-call provenance-impact, no-LSP-dependency, layout-robustness).
- [~] **R2.2… остальные** — 🟡 в работе.
      - [x] **GitNexus** ✅ (2026-08-06, **hands-on** через новый харнесс R2.0.1) — `research/tools/gitnexus.md`.
            v1.6.9, TS/Node, tree-sitter + LadybugDB + локальные ONNX-эмбеддинги, 14 языков, PolyForm-NC.
            Измерено на R2-скоупе (materialized staging, `scope_id` сверен): T1 ✅ (ambiguity как у нас),
            T2 ◐ (import fan-in, не call-sites), T3 ✅ (транзитивный import-closure + risk + epistemic),
            T4 ✖ (нет call-contract), T5 ◐ (cycles+кластеры+flows, без coupling/god-objects). Детерминизм ◐:
            **ответ** байт-идентичен (clean-room A/B), **артефакт** — 123 МБ бинарный LadybugDB (не diffable);
            re-analyze без clean не идемпотентен. Установка 1.7 ГБ node_modules. Вердикт **learn (сильный,
            смежный peer — комплементарен, не конкурент)**. Питает R1-C13 (epistemic/confidence-метки),
            R1-C14 (дифференциаторы: MIT vs NC, diffable JSON vs бинарь, provenance-impact, no-git), R1-C15
            (clusters+flows → living docs). **Новый gap:** семантический поиск + flow/community-нарратив.
            Build-story #2 в `research/positioning.md` («The one that does more, and why that's fine»).
      - [x] **cocoindex-code (`ccc`)** ✅ (2026-08-16, **hands-on** на R2-скоупе) — `research/tools/cocoindex-code.md`.
            0.2.41 на cocoindex 1.0.20, Apache-2.0, Python+Rust-движок, tree-sitter-чанкинг, локальные ST-эмбеддинги
            (`snowflake-arctic-embed-xs` — та же модель, что у GitNexus), встроенный **LMDB+SQLite (без БД-сервиса,
            без API-ключа)**. Развод: **CocoIndex** (ETL-фреймворк, часто Postgres+pgvector) vs **cocoindex-code**
            (сам CLI, embedded store) — карточка про второй. Измерено: 280 файлов → 6403 чанка; **T1 ◐** (semantic
            `search` даёт релевантный спред, деф не #1; точный деф — через bundled `ccc grep`, tree-sitter);
            **T2–T5 N/A** (векторный индекс, нет графа/вызовов/impact/арх); **concept-query блистает**
            (`swing pivot points` → точно `strategies/swing/pivot_points.py`, чего codemap не умеет); детерминизм ◐
            (ответ байт-идентичен, артефакт — бинарный LMDB/SQLite); **инкрементальная переиндексация ≈ 1с**
            (content-hash — тезис движка). GPU заблокирован **только на Pascal** (torch 2.13/cu130 не несёт
            cubin под sm_61 → CPU-only на 1080 Ti; onnxruntime GitNexus'а на sm_61 ехал — другой рантайм);
            на RTX 3070 (sm_86) замерено 2026-08-22: холодная сборка **48с против 216с CPU** на той же машине
            (~4.5×). Вердикт **wrap (opt-in
            семантик-адаптер) + learn (инкрементальный движок)**: **первый лицензионно-чистый (Apache-2.0)
            семантик-поиск, пригодный к обёртке за роутером R1-C16** (там, где GitNexus только `route`, но не
            `adapt` из-за NC). Питает **R1-C16** (первый adapter-кандидат семантики), **R1-C9** (content-hash
            инкрементальность — рабочее доказательство), **R1-C6** (relevance).
      - [ ] остальные — CodeGraph, OntoIndex, Sentrux, rag_for_git, Understand-Anything, CodeSlicer,
            ast-index, Graphify, grafema, CodeWiki, Foglamp (desk где SaaS/не воспроизводится — с честной
            пометкой). Порядок — по близости к codemap и по связи с R1-C.

---

## Находки из живого MCP-использования 2026-07-30 (реальный агент через `serve --mcp`)

Первый прогон codemap **как продукта в бою** — ИИ-агент (Claude Code) через MCP по графу bquant.
Инструменты отработали (architecture поймал `analysis↔indicators`; impact/call_contract дали карту для
смены сигнатуры; `resolved.ambiguous` прошёл через MCP). Находка эргономики канала:

- [x] **F22 (MCP/Workflow) — тяжёлый payload на хабах.** ✅ (2026-07-30, без схемы) На `MACDZoneAnalyzer`:
      `impact` возвращал **68 ссылок + дублирующий полный `markdown`**, `call_contract` — **61 запись**.
      Фикс: MCP-обёртки `impact`/`call_contract` компактны по умолчанию — `impact` без `markdown` + `limit=40`
      на плоский список refs (by_root-счётчики полны), `call_contract` `limit=30`; `full=true` возвращает
      всё. Underlying-ops/CLI не тронуты. Замер на хабе: impact **−65%** (32.7k→11.6k), call_contract
      **−49%** (17k→8.8k). `serve/mcp_server.py` `_compact_impact`/`_cap_list`. +4 теста (7→11 MCP).
- [x] **F23 (Query-surface) — `impact` не принимал полный/canonical id.** ✅ (2026-07-30, без схемы)
      На реальной задаче (bquant #110) `impact('bquant.analysis.zones.models.SwingPoint')` → **`[]`**.
      **Гипотеза «конструктор не ловится» ОПРОВЕРГНУТА при воспроизведении:** инстанциация класса
      **ловится** — у `SwingPoint` 9 inbound calls-рёбер, `references_to` = 9. Настоящая причина: op/рендер
      `impact` резолвили вход **только по короткому имени** (`find(sym)`), поэтому **полный id** (ровно то,
      что агент получает назад из `query`/`search`) не матчился ни во что → пустой blast-radius. Молчаливо
      неверно (как F13, но для impact). **Фикс:** `Query.impact_targets(name_or_id)` — node-id→сам,
      короткое имя→все матчи (фан-аут сохранён), иначе `canonical` (re-export), иначе `where_defined`;
      使用 в `_op_impact` и `render_impact`. Проверено: full id и re-export → 10 refs (было 0), короткое
      имя без изменений. +2 теста. **Урок:** воспроизводить до фикса — записанная гипотеза (extraction)
      оказалась неверной, реальный баг был в input-резолве serve-слоя.

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
