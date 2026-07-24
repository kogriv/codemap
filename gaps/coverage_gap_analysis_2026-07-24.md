# codemap — гэп-анализ полноты покрытия кода и семантических связей

**Дата:** 2026-07-24  
**Тип:** гэп-документ (gap analysis)  
**Статус:** 🟠 открыто — задокументировано, не исправлено  
**Объект анализа:** инструмент `codemap/` (версия 0.0.1, вехи M0+M1 реализованы)  
**Целевой пакет:** `bquant/` (версия 0.0.3)  
**Метод:** статический прогон `codemap build ../bquant -o graph.json` + анализ артефакта, исходников экстрактора (`../codemap/extract/griffe_extractor.py`), query-слоя (`../codemap/query.py`), отчётов (`../codemap/serve/`) и дизайн-документа (`../DESIGN.md`)

**Связанные документы:**
- `../DESIGN.md` — заявленная модель графа и границы v1
- `../BACKLOG.md` — статус реализации M0/M1/M2/M3
- `../../devref/architecture/package_roadmap_2026-07.md` — место codemap в стадии P1
- `../../devref/gaps/gap_inventory_2026-07.md` — реестр гэпов репозитория (запись G13)

---

## 1. Резюме для принятия решений

**codemap не покрывает код пакета полностью в семантическом смысле.** Он **полностью индексирует структурные определения** (все Python-модули пакета, классы, функции, атрибуты верхнего уровня), но строит **ограниченный набор связей** между сущностями и **не моделирует потоки данных, вызовы функций, наследование как рёбра графа, динамическую регистрацию стратегий и поведенческую архитектуру**.

Текущий артефакт — это **«каталог определений + граф импортов модулей + карта ре-экспортов»**, а не полная архитектурная или data-flow модель кодовой базы.

Для потребителей из `DESIGN.md §1`:
- **Потребитель B (дока-как-продукт):** покрытие **хорошее** для API-surface, сигнатур, docstring, deprecated-маркеров, структуры модулей; **недостаточное** для class-диаграмм наследования, связей «поле модели → тип», поведенческих контрактов.
- **Потребитель A (CLI-AI / RAG / навигация):** покрытие **частичное** — «где определён символ» и «какие модули импортируют какие» работают; **не работают** «кто кого вызывает», «как DataFrame проходит по pipeline», «какая стратегия зарегистрирована под каким ключом».
- **Потребитель C (аудит / гигиена):** покрытие **эвристическое** — циклы импортов и orphan-модули; **нет** symbol-level dead code, unused private methods, полноты reachability от entry points.

**Вывод:** M0+M1 выполняют заявленный тонкий срез (§8 DESIGN), но **создают риск переоценки**, если читатель ожидает «полную карту внутренних взаимосвязей». Ниже — исчерпывающая детализация.

---

## 2. Методология и воспроизводимость

### 2.1. Команды прогона

```bash
cd codemap
# зависимости: griffe>=2.0, networkx>=3.0 (см. codemap/pyproject.toml)
codemap build ../bquant -o graph.json
codemap query analyze_zones --graph graph.json --format text
codemap report dependencies --graph graph.json
codemap report dead-code --graph graph.json
codemap report api-surface --graph graph.json
```

### 2.2. Версии и контекст

| Параметр | Значение |
|----------|----------|
| `codemap_schema` в артефакте | `0.1` |
| Реализованные вехи | M0 (API-surface pipeline) + M1 (import/export рёбра, query, audit reports) |
| Экстрактор | `griffe_extractor.py` (обёртка над `griffe`, статический разбор без импорта цели) |
| Query-бэкенд | `networkx` in-memory из JSON |
| Python-файлов в `bquant/` | 89 |
| Module-узлов в графе | 89 (соответствие 1:1) |

### 2.3. Сводная статистика артефакта `graph.json`

| Метрика | Значение |
|---------|----------|
| Узлов всего | 1709 |
| Рёбер всего | 2428 |
| Узлы `module` | 89 |
| Узлы `class` | 126 |
| Узлы `function` | 863 |
| Узлы `attribute` | 631 |
| Рёбра `contains` | 1708 |
| Рёбра `export` | 479 |
| Рёбра `imports` | 241 |
| Рёбра `inherits` | **0** |
| Рёбра `decorated_by` | **0** |
| Рёбра `references` / `calls` | **0** |
| Import-циклы (модули) | 1 |
| Orphan-модули (эвристика) | 19 |
| Узлы с `is_deprecated: true` | 3 |
| Callable без docstring | 102 из 989 (function + class) |
| Function с return-type в signature | 685 из 863 |
| Символы с `DataFrame` в signature | 232 |

---

## 3. Что codemap покрывает полностью

### 3.1. Структурная индексация всех модулей пакета

Каждый файл `*.py` под `bquant/` порождает ровно один узел `kind: module` с:
- каноническим идентификатором (`bquant.analysis.zones.pipeline`);
- относительным путём к файлу;
- диапазоном строк (если доступно у griffe);
- флагом публичности (`visibility: public | private` по правилам griffe / `_` / `__all__`).

**Гэп отсутствует** на уровне «файл/модуль не попал в граф».

### 3.2. Иерархия вложенности (`contains`)

Рёбра `contains` связывают:
- модуль → класс, функция, атрибут модуля;
- класс → метод, вложенный атрибут, вложенный класс (если есть).

Пример для модели данных зон:

```
bquant.analysis.zones.models.ZoneAnalysisResult  (class)
  ├── .zones          (attribute)
  ├── .data           (attribute)
  ├── .statistics     (attribute)
  ├── .clustering     (attribute)
  └── ...             (ещё 5 полей dataclass)
```

**Покрытие:** структурное дерево «кто внутри кого объявлен» для top-level и class-member сущностей.

### 3.3. Публичная API-поверхность и ре-экспорты (`export`)

479 рёбер `export` фиксируют, что символ **доступен через импорт из модуля**, даже если определён в другом месте. Это критично для bquant:

- `analyze_zones` **определён** в `bquant.analysis.zones.pipeline.analyze_zones`;
- **доступен** как `from bquant.analysis.zones import analyze_zones` через `export`-ребро;
- при этом `analyze_zones` **не входит** в `__all__` пакета `bquant.analysis.zones` (только legacy-символы в `__all__`).

Query `where_defined('analyze_zones')` корректно возвращает оба пути — это **осознанная сильная сторона** M1.

### 3.4. Граф зависимостей на уровне модулей (`imports`)

241 ребро `imports` связывает **модуль → модуль** (внутренние зависимости; внешние `pandas`, `numpy` отсекаются).

Позволяет отвечать на:
- «от каких внутренних модулей зависит `pipeline`?»;
- «кто больше всего импортируется?» (`logging_config` — 58 входящих);
- «есть ли циклы?» — **да, один:** `cache → pipeline → cache`.

### 3.5. Метаданные узлов (атрибуты, не рёбра)

На каждом узле callable/class хранятся (если griffe извлёк):
- **signature** — строка с параметрами и return-аннотацией;
- **docstring** — полный текст;
- **decorators** — список имён/путей декораторов;
- **is_deprecated** — эвристика: декоратор с коротким именем `deprecated`;
- **visibility** — public/private;
- **file**, **lineno**, **endlineno**.

Подтверждённые находки на bquant:
- `MACDZoneAnalyzer`, `analyze_macd_zones`, `create_macd_analyzer` — `is_deprecated: true`;
- 35 классов с декоратором `dataclasses.dataclass` (в списке decorators, не в `extras.is_dataclass`);
- 12 символов с `@register` / `@register_swing_strategy` / `@register_divergence_strategy`.

### 3.6. Отчёты Serve (M0+M1)

| Отчёт | Что даёт |
|-------|----------|
| `report api-surface` | Markdown: публичные символы по модулям, сигнатуры, первая строка docstring, маркер deprecated |
| `report dependencies` | Циклы импортов, топ модулей по in-degree |
| `report dead-code` | Модули без входящих import-рёбер (эвристика) |
| `query <name>` | Поиск по короткому имени, `where_defined`, dependencies/dependents для module-узлов |

---

## 4. Что codemap покрывает частично

### 4.1. Гэп CM-01 — Атрибуты: есть узлы, нет типов полей

**Симптом:** поля dataclass присутствуют как узлы `attribute`, но **без аннотации типа** в модели графа.

**Пример** (`ZoneAnalysisResult.zones`):

```json
{
  "id": "bquant.analysis.zones.models.ZoneAnalysisResult.zones",
  "kind": "attribute",
  "signature": null,
  "docstring": null,
  "extras": {}
}
```

**Ожидание по DESIGN §2:** Python-экстрактор должен класть специфику в `extras` (например `annotation: "List[ZoneInfo]"`).

**Факт:** griffe знает аннотации полей; экстрактор `_add_node()` их **не записывает**.

**Влияние:** нельзя построить схему модели данных, UML class diagram с типами полей, RAG-чанк «`zones` — список `ZoneInfo`» без повторного чтения исходников.

**Серьёзность:** средняя для доки-как-продукт; высокая для data-model-aware инструментов.

---

### 4.2. Гэп CM-02 — Dataclass: декоратор есть, семантический флаг отсутствует

**Симптом:** класс `ZoneAnalysisResult` имеет `decorators: ["dataclasses.dataclass"]`, но `extras` пуст и нет ребра/флага `is_dataclass: true` как в DESIGN §2.

**Влияние:** потребитель должен парсить строки декораторов сам; нет единого контракта для «модель данных vs обычный класс».

**Серьёзность:** низкая–средняя (обходимо, но хрупко).

---

### 4.3. Гэп CM-03 — Сигнатуры: богатые, но не структурированные

**Симптом:** 685 из 863 функций имеют return-type в **строке** signature; параметры не являются отдельными узлами; нет разбора `pd.DataFrame` → ссылка на внешний тип.

**Влияние:** 232 упоминания `DataFrame` в сигнатурах — это **текстовый поиск**, не семантическая связь «функция принимает/возвращает tabular data».

**Серьёзность:** средняя.

---

### 4.4. Гэп CM-04 — Docstrings: 102 callable без документации в графе

**Симптом:** 102 из 989 узлов `function`/`class` без `docstring` в артефакте (отсутствуют в исходнике или не извлечены griffe).

**Влияние:** API-surface и RAG-экспорт (M2, не реализован) будут неполными для ~10% callable.

**Серьёзность:** низкая–средняя (отражает реальное состояние кода).

---

### 4.5. Гэп CM-05 — Import-рёбра сведены к module→module

**Симптом:** из 241 import-рёбер **97** имеют target с глубиной больше одного сегмента после `bquant.`, но экстрактор `_resolve_edges()` **всегда** нормализует к containing module через `_containing_module()`.

**Пример:** импорт `from bquant.analysis.zones.models import ZoneInfo` в графе становится `imports: pipeline_module → models_module`, без ребра к узлу `ZoneInfo`.

**Влияние:** нельзя построить точный граф «какие типы/символы использует модуль»; только модульная coupling metrics.

**Серьёзность:** средняя; осознанное упрощение v1, но не задокументировано в BACKLOG как ограничение M1.

---

### 4.6. Гэп CM-06 — Декораторы как атрибут, не как рёбра `decorated_by`

**Дизайн (DESIGN §2):** ребро `decorated_by` от символа к декоратору — для навигации `@deprecated`, `@StrategyRegistry.register_*`.

**Реализация:** декораторы только в поле `decorators: list[str]` на узле; **рёбер `decorated_by` нет**.

**Влияние:** нельзя запросить «все символы, декорированные `register_swing_strategy`» через обход рёбер; только фильтрация по атрибуту всех узлов.

**Серьёзность:** низкая–средняя.

---

### 4.7. Гэп CM-07 — Динамическая регистрация: видна форма, не семантика

**Контекст bquant (DESIGN §7):** поведение связывается через registry/factory:

```python
@StrategyRegistry.register_swing_strategy('zigzag')
class ZigZagSwingStrategy: ...

IndicatorFactory.create('pandas_ta', 'rsi', length=14)
```

**Что видит codemap:**
- узел класса `ZigZagSwingStrategy`;
- в `decorators` — путь к `register_swing_strategy`;
- **нет** ребра `'zigzag' → ZigZagSwingStrategy`;
- **нет** разбора строкового литерала аргумента декоратора;
- **нет** связи `IndicatorFactory.create` → конкретный класс индикатора.

**Ожидание DESIGN §7:** флаг `dynamic-registration` на узле + литерал ключа в атрибуте, если аргумент — строка.

**Факт:** даже флаг **не выставляется**; только сырой список decorators.

**Влияние:** для Universal Zone Pipeline **import-graph недостаточен** — архитектурно важные связи plugin/registry невидимы.

**Серьёзность:** **высокая** для понимания `bquant.analysis.zones`.

---

## 5. Что codemap не покрывает (критические пробелы)

### 5.1. Гэп CM-08 — Наследование (`inherits`): в дизайне есть, в графе нет

**Дизайн DESIGN §2:** ребро `inherits` — класс → базовый класс.

**Реализация:** `griffe_extractor.py` **не эмитит** `inherits`. Проверка griffe напрямую:

```
BaseIndicator bases: [ABC]
ZoneAnalysisPipeline bases: []
```

Данные у griffe **есть** (`obj.bases`), экстрактор их **игнорирует**.

**Влияние:**
- нет class hierarchy для `BaseIndicator`, detection strategies, swing strategies;
- M2 mermaid `classDiagram` (BACKLOG M2.3) **невозможен** без доработки экстрактора;
- потребитель B не получает «кто наследует кого».

**Серьёзность:** **высокая** (расхождение дизайн ↔ код).

**Рекомендация:** M1.5 или начало M2 — добавить pass в `_collect()` / `_resolve_edges()` для `inherits`, в т.ч. внешние базы (`ABC`) как `external` узлы или qualified string targets.

---

### 5.2. Гэп CM-09 — Call-graph / references: явно отложено, полностью отсутствует

**Дизайн DESIGN §2, §7:** `references`/`calls` — best-effort статически; точный call-graph отложен.

**Реализация:** **ноль** таких рёбер.

**Что невозможно ответить на bquant:**
- кто вызывает `analyze_zones()` внутри `MACDZoneAnalyzer`?
- цепочка `ZoneAnalysisPipeline.build()` → `_prepare_data()` → `_detect_zones()` → `_analyze_zones()`;
- какие стратегии вызывает `UniversalZoneAnalyzer`;
- передача `result.data` из pipeline в `ZoneVisualizer`.

**Влияние:** **нет поведенческой карты** — только структурная и модульная.

**Серьёзность:** **высокая** для CLI-AI навигации «как работает фича X»; осознанно отложено, но должно быть явно communicated потребителям.

---

### 5.3. Гэп CM-10 — Потоки данных (data flow): отсутствуют полностью

**Определение:** трассировка того, как значения (особенно `pd.DataFrame`, `ZoneAnalysisResult`, `List[ZoneInfo]`) создаются, трансформируются и передаются между функциями/методами.

**Статус:** не входит в v1 (DESIGN §7: «точная трассировка потоков через рантайм — слой глубины»).

**Конкретно для bquant невидимо:**
1. `get_sample_data()` → сырой OHLCV DataFrame;
2. `.with_indicator()` → augmented frame с колонками MACD/RSI;
3. `.detect_zones()` → список `ZoneInfo`;
4. `.analyze()` → `ZoneAnalysisResult` с `features`, `clustering`;
5. `result.data` как **обязательный** вход для `ZoneVisualizer` (контракт из AGENTS.md).

**Единственный слабый proxy:** совпадение имён типов в строках signature (`DataFrame` × 232).

**Серьёзность:** **критическая** для цели P1 «граф как ground truth для доки и CLI» **если** ожидать понимание pipeline semantics; **низкая** если P1 ограничен API-catalog + module deps.

---

### 5.4. Гэп CM-11 — Локальные переменные и внутрифункциональная структура

**Не извлекаются:**
- локальные переменные в телах функций;
- промежуточные присваивания;
- ветвления, циклы, exception paths;
- context managers (`with performance_context(...)`).

**Влияние:** внутренняя логика алгоритмов (swing detection, zone detection, clustering) **непредставлена** в графе.

**Серьёзность:** средняя (ожидаемо для AST-level static analysis v1).

---

### 5.5. Гэп CM-12 — Symbol-level dead code и reachability

**Текущий audit (`render_dead_code`):** только **модули** без входящих `imports`.

**Ложные срабатывания на bquant (19 модулей):**
- `bquant.cli` — entry point `pyproject.toml [project.scripts]`;
- `bquant.ml` — stub, импортируется из тестов/будущего кода;
- `bquant.analysis.zones` — публичный API-пакет, импортируется как `from bquant.analysis.zones import analyze_zones` (импорт пакета не всегда даёт incoming edge к submodule `zones` из-за нормализации);
- `bquant.visualization` — импортируется пользователями напрямую;
- embedded sample modules — загружаются через `samples` API динамически.

**Не детектируется:**
- функция, ни разу не вызванная и не экспортированная;
- private method без ссылок;
- deprecated wrapper после миграции на universal pipeline.

**Серьёзность:** средняя–высокая для потребителя C; отчёт должен сопровождаться дисклеймером (частично есть в `audit.py`).

---

### 5.6. Гэп CM-13 — Entry points, тесты, динамические импорты невидимы

**Статический анализ без исполнения не видит:**
- `bquant = "bquant.cli:main"` — CLI как точка входа;
- `pytest tests/` — какие модули реально используются;
- `importlib`, `__import__`, lazy imports в `LibraryManager.load_all_libraries()`;
- условные `try: import talib` (DESIGN §3.1 — должны быть `conditional` флаги; **не реализованы** в экстракторе).

**Влияние:** граф зависимостей **занижает** реальную связность и **завышает** orphan-count.

**Серьёзность:** средняя; фундаментальное ограничение static-only подхода.

---

### 5.7. Гэп CM-14 — Внешние зависимости отсекаются

Все импорты вне `bquant.*` **не попадают** в граф (`_resolve_edges` фильтрует external).

**Влияние:** нельзя ответить «какие модули bquant зависят от pandas-ta» на уровне графа; нет узлов `external:pandas`.

**Дизайн:** осознанно (DESIGN §3.1 — external leaf nodes). **Реализация external-узлов** — тоже отсутствует (импорты просто отбрасываются).

**Серьёзность:** низкая–средняя для внутренней архитектуры; средняя для supply-chain / dependency audit.

---

## 6. Матрица типов сущностей и связей

### 6.1. Сущности (узлы)

| Сущность | В графе | Примечание |
|----------|---------|------------|
| Package | как `module` корня `bquant` | отдельного kind `Package` нет |
| Module | ✅ | 89/89 файлов |
| Class | ✅ | 126 |
| Function (включая методы) | ✅ | 863; методы не отделены kind-ом |
| Method | ⚠️ | kind=`function`, эвристика по имени класса в id |
| Attribute (поле класса, константа модуля) | ✅ | 631 |
| Property | ⚠️ | как function/attribute в зависимости от griffe |
| Parameter | ❌ | только текст в signature |
| Local variable | ❌ | |
| Type alias (`TypeAlias`, `X = ...`) | ❌ | |
| Enum member | ⚠️ | зависит от griffe classification |
| Decorator definition | ❌ | только строка в decorators[] |
| Module `__all__` | ✅ | как attribute `bquant.__all__` |

### 6.2. Связи (рёбра)

| Связь | DESIGN | Реализация M0+M1 | Статус |
|-------|--------|------------------|--------|
| `contains` | ✅ | ✅ 1708 | **OK** |
| `exports` | ✅ | ✅ 479 | **OK** |
| `imports` (module→module) | ✅ | ✅ 241 | **OK, упрощённо** |
| `imports` (module→symbol) | опционально | ❌ | **Гэп CM-05** |
| `inherits` | ✅ | ❌ 0 | **Гэп CM-08** |
| `decorated_by` | ✅ | ❌ 0 | **Гэп CM-06** |
| `references` / `calls` | отложено | ❌ 0 | **Гэп CM-09** |
| `implements` / `protocol` | нет в v1 | ❌ | будущее |
| data flow | нет в v1 | ❌ | **Гэп CM-10** |
| registry key → implementation | §7 флаг | ❌ | **Гэп CM-07** |

---

## 7. Понимание моделей данных в bquant (case study)

### 7.1. Что codemap видит для `ZoneAnalysisResult`

| Аспект | Видимость |
|--------|-----------|
| Класс существует | ✅ узел `bquant.analysis.zones.models.ZoneAnalysisResult` |
| Это dataclass | ⚠️ только `decorators: ["dataclasses.dataclass"]` |
| Поля `zones`, `data`, `statistics`, ... | ✅ 9 attribute-узлов + contains-рёбра |
| Тип поля `zones: List[ZoneInfo]` | ❌ |
| Методы `_load_json`, `to_dict`, ... | ✅ как function-узлы |
| Связь `ZoneInfo` ↔ `ZoneAnalysisResult` | ❌ только если оба упомянуты в signature других функций текстом |
| Сериализация pickle/JSON/Parquet | ⚠️ имена методов видны, контракт полей при загрузке — нет |

### 7.2. Что codemap видит для Universal Zone Pipeline

| Аспект | Видимость |
|--------|-----------|
| `ZoneAnalysisBuilder`, `ZoneAnalysisPipeline` | ✅ классы и методы |
| Fluent API `.with_indicator().detect_zones()...` | ❌ call-chain |
| `ZoneDetectionRegistry` / `StrategyRegistry` | ✅ классы |
| Регистрация `zero_crossing` → `ZeroCrossingDetection` | ❌ **Гэп CM-07** |
| `CACHE_SCHEMA_VERSION` влияние на cache | ❌ data/control flow |
| Цикл `pipeline` ↔ `cache` | ✅ import-cycle на уровне модулей |
| `IndicatorConfig`, `ZoneAnalysisConfig` | ✅ dataclass-поля частично (без типов) |

### 7.3. Вывод по моделям данных

codemap даёт **скелет модели** (имена сущностей и вложенность полей), но **не даёт семантической схемы** (типы, инварианты, lifecycle объектов, обязательные поля на каждом этапе pipeline).

---

## 8. Понимание потоков данных и control flow (case study)

### 8.1. Типичный сценарий bquant (невидимый для codemap)

```
get_sample_data('tv_xauusd_1h')
    → DataFrame (OHLCV)
analyze_zones(data)
    → ZoneAnalysisBuilder
    .with_indicator(...)  → IndicatorFactory → augmented DataFrame
    .detect_zones(...)    → List[ZoneInfo]
    .with_strategies(...) → config strategies
    .analyze(...)         → UniversalZoneAnalyzer → features, clustering
    .build()              → ZoneAnalysisResult
ZoneVisualizer.plot(..., data=result.data)  → visualization
```

**codemap видит** только отдельные «острова» определений и то, что модули `pipeline`, `analyzer`, `detection`, `strategies`, `visualization.zones` **импортируют друг друга** (косвенно, через module graph).

**codemap не видит** последовательность, передачу `result.data`, выбор стратегии по строковому ключу, условное кэширование.

### 8.2. Implication для roadmap P2

Если P2-A (CLI-AI) и P2-B (дока-как-продукт) ожидают ответы на вопросы «как работает pipeline» — **одного codemap M0+M1 недостаточно**; нужен как минимум call-graph слой или ручная аннотация critical paths в графе.

---

## 9. Соответствие каталогу запросов DESIGN §1

### 9.1. Потребитель B — Дока-как-продукт

| Запрос | M0+M1 | Гэп |
|--------|-------|-----|
| Публичная API-поверхность | ✅ `api-surface` | слоёность `__all__` vs deep exports — **решено** export-рёбрами |
| Состав модуля X | ✅ contains | без типов полей |
| Deprecated символы | ✅ is_deprecated | только по имени декоратора `deprecated` |
| Docstring + signature для reference | ✅ | 102 callable без docstring |
| Class diagram наследования | ❌ | **CM-08** |
| Модель данных с типами полей | ❌ | **CM-01** |

### 9.2. Потребитель A — CLI-AI / RAG / навигация

| Запрос | M0+M1 | Гэп |
|--------|-------|-----|
| Где реализована фича X | ✅ query | |
| Зависимости модуля Y | ✅ dependencies | module-level only |
| Минимал для RAG (сигнатура+doc+соседи) | ⚠️ частично | M2 RAG export **не реализован**; соседи по calls — **нет** |
| Как данные текут через систему | ❌ | **CM-10** |
| Как вызывается цепочка API | ❌ | **CM-09** |

### 9.3. Потребитель C — Аудит / гигиена

| Запрос | M0+M1 | Гэп |
|--------|-------|-----|
| Orphan modules | ⚠️ эвристика | 19 FP на bquant — **CM-12, CM-13** |
| Import cycles | ✅ | найден 1 реальный |
| Symbol dead code | ❌ | |
| Public-but-undocumented | ⚠️ | можно вывести из visibility+docstring, отчёта нет |
| Дубли/затенение имён | ❌ | |
| Dynamic registration blind spots | ❌ | **CM-07** |

---

## 10. Расхождения DESIGN ↔ реализация (сводная таблица гэпов)

| ID | Название | Категория | Серьёзность | Веха-fix |
|----|----------|-----------|--------------|----------|
| **CM-01** | Типы полей атрибутов не извлекаются | модели данных | средняя | M2 |
| **CM-02** | Нет `extras.is_dataclass` | модели данных | низкая | M2 |
| **CM-03** | Сигнатуры не структурированы | модели данных | средняя | M2+ |
| **CM-04** | 102 callable без docstring в графе | полнота метаданных | низкая | — |
| **CM-05** | Import только module→module | связи | средняя | M2 |
| **CM-06** | Нет рёбер `decorated_by` | связи | средняя | M1.5 |
| **CM-07** | Registry/factory не резолвятся | поведение | **высокая** | M2+ |
| **CM-08** | Нет рёбер `inherits` (griffe данные есть) | связи | **высокая** | M1.5 |
| **CM-09** | Нет call-graph | поведение | **высокая** | отложено |
| **CM-10** | Нет data flow | поведение | **критическая*** | отложено |
| **CM-11** | Нет локальных переменных | полнота | средняя | отложено |
| **CM-12** | Dead-code только module-level | аудит | средняя | M2+ |
| **CM-13** | Entry points / tests невидимы | аудит | средняя | M3 |
| **CM-14** | External imports отбрасываются | зависимости | средняя | M2 |

\*критическая **относительно** ожидания «полная карта pipeline»; **низкая** относительно заявленных границ v1 §7.

---

## 11. Рекомендации по приоритизации

### 11.1. Быстрые wins (закрывают расхождение дизайн↔код)

1. **CM-08 `inherits`** — данные уже в griffe; добавить рёбра в экстрактор.
2. **CM-06 `decorated_by`** — тривиально из списка decorators.
3. **CM-01 типы полей** — записать `annotation` из griffe в `Node.extras` для attributes.
4. **CM-07 флаг `dynamic-registration`** — парсить строковый литерал первого аргумента `@register*`.

### 11.2. Средний горизонт (M2)

5. RAG-экспорт с соседями по `contains` + `imports` (не calls).
6. Scoped mermaid classDiagram с `inherits`.
7. Отчёт `public-but-undocumented`.
8. External import nodes (хотя бы как leaf `external:pandas`).

### 11.3. Долгий горизонт (явно за границей v1)

9. Best-effort static call-graph.
10. Data-flow / type propagation для `DataFrame`-like pipelines.
11. Entry-point awareness (`pyproject.scripts`, pytest collection).
12. Symbol reachability analysis.

---

## 12. Риски переоценки покрытия

| Риск | Описание | Митигация |
|------|----------|-----------|
| **R1** | AI-агент читает `graph.json` и считает import-graph = architecture | Явный `coverage_gap` metadata в schema v0.2; ссылка на этот документ в README |
| **R2** | `dead-code` отчёт используется для удаления модулей | Никогда не удалять по orphan-list без ручной проверки entry points |
| **R3** | Дока генерируется из графа без inherits/типов | Не обещать UML/схемы данных до CM-01/CM-08 |
| **R4** | Pipeline semantics выводятся из module deps | Для bquant.analysis.zones нужен отдельный «critical path» doc или call layer |

---

## 13. Критерии приёмки «полного покрытия» (definition of done для будущих вех)

Codemap можно считать **полно покрывающим структурно-семантический слой Python-пакета bquant**, когда:

1. ✅ Все модули, классы, функции, поля классов — **уже выполнено**.
2. ⬜ Все рёбра из DESIGN §2 (кроме отложённых calls) — **не выполнено** (`inherits`, `decorated_by`).
3. ⬜ Типы полей dataclass/Pydantic в `extras` — **не выполнено**.
4. ⬜ Registry keys резолвятся или помечены `dynamic-registration` — **не выполнено**.
5. ⬜ Call-graph best-effort для top-N публичных entry points (`analyze_zones`, `get_sample_data`) — **не выполнено**.
6. ⬜ Dead-code с учётом `pyproject.scripts` и pytest references — **не выполнено**.
7. ⬜ Документированный дисклеймер в CLI `--help` и в `graph.json` metadata — **не выполнено**.

Пункты 2–7 — кандидаты в BACKLOG после M2.

---

## 14. Заключение

**codemap M0+M1 полностью покрывает статическую структуру пакета bquant** (все 89 модулей, 1709 определений верхнего уровня) и **частично покрывает связи** — вложенность, ре-экспорты, импорты между модулями.

**codemap не покрывает:**
- наследование как рёбра графа (хотя данные доступны);
- вызовы функций и ссылки между символами;
- потоки данных и lifecycle объектов pipeline;
- динамическую wiring registry/factory, характерную для Universal Zone Analysis Pipeline;
- symbol-level аудит и reachability от реальных entry points.

Для целей **P1 roadmap** (факт-карта для доки и CLI) текущего покрытия **достаточно с оговорками**. Для целей **«исчерпывающее понимание внутренних взаимосвязей и моделей данных»** — **недостаточно**; этот документ фиксирует гэпы CM-01…CM-14 как основу для следующих вех BACKLOG.

---

*Документ подготовлен по результатам прогона 2026-07-24. Обновлять при bump `codemap_schema`, завершении M2/M3 или изменении экстрактора.*
