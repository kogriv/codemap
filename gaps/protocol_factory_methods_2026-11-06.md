# Гэп: метод объекта, построенного фабрикой с возвратом Protocol, недостижим; `tests` отвечает unknown

**Дата:** 2026-11-06. **Источник:** bquearch (сводка [kogriv/codemap#25](https://github.com/kogriv/codemap/issues/25)).
**Статус:** открыто; дизайн — [`docs/design/protocol_dispatch.md`](../docs/design/protocol_dispatch.md), бэклог R1-C81.

## 1. Что показали

bquearch `703696d`, граф как в их MCP-скрипте: `shared`, `--deep --mode full`, консьюмеры `research/tests`,
`scripts`, `research/directions`, `apps`. codmap 0.0.30 (код e3a49ec).

```python
# research/tests/test_knn_recursive.py
def _spec(**params):
    from forecaster_menu import ForecasterSpec
    return ForecasterSpec(model_type="knn_recursive", ...)

def test_a_rows_scenarios_do_not_depend_on_who_else_was_asked():
    fc = _spec().build().fit(df)
    whole = fc.band(df, 3, GRID, ...)
```

```
tests KnnRecursiveForecaster.band   → confidence unknown, 0 tests      (fast и deep)
tests KnnRecursiveForecaster.fit    → unknown
tests KnnPathForecaster.member_values → unknown
implementers PathForecaster         → []
рёбра из теста: только calls → _frame, _spec (local)
```

## 2. Почему так — два разрыва

1. **От метода Protocol нет пути к реализациям.** `ForecasterSpec.build() -> PathForecaster`, класс выбирается
   через реестр `FORECASTER_REGISTRY.build(self.model_type, …)`. На deep jedi разрешает вызовы в ядре до
   `PathForecaster.band` (`evaluate_bar_path → PathForecaster.band`, `deep`), но дальше пути нет. Семейства
   реестров (M7/M9) понимают только `@Registry.register('key')` на классе. Здесь регистратор — алиас
   `register = FORECASTER_REGISTRY.register` экземпляра `Catalog`, декорирует он фабричные функции, а реализации
   Protocol не наследуют. Поэтому `implements` нет, и `implementers` пуст.
2. **В консьюмер-корне методы на объектах не разрешаются.** Скан корня работает по именам импортов. У
   `_spec().build().fit(df)` и `fc.band(…)` рёбер нет, хотя аннотации возврата (`build -> PathForecaster`,
   `fit -> "PathForecaster"`) называют тип каждого звена.

## 3. Чем это опасно

`tests` — ответ на вопрос «что прогнать перед правкой». На методах моделей меню bquearch он отвечает unknown,
а профильные тесты (`test_knn_recursive.py`) существуют и гоняют ровно эти методы. Unknown честен, но
бесполезен там, где правка чаще всего. На bquearch прототип насчитал 12 методов реализаций за двумя Protocol
(`PathForecaster`, `RuntimeForecaster`), из них 11 сейчас дают unknown.

## 4. Что не является причиной и что проверено заранее

- **Не тир.** На fast и deep одинаково unknown; deep лишь доводит вызовы в ядре до метода Protocol.
- **Структурное сопоставление по одним именам методов ложно.** Прототип на bquant записал четыре стратегии
  swing в реализации `ShapeCalculationStrategy` (два метода с общими именами) и `ZoneAnalysisBuilder` — в
  `ZoneDetectionStrategy`. Со сверкой имён и видов параметров это ушло: результат совпал с реестром bquant во
  всех шести протоколах. Лишний только `AdaptiveSwingStrategy`, обёртка, которая структурно действительно
  реализует `SwingCalculationStrategy`, просто не зарегистрирована.
