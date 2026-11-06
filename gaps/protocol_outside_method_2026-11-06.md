# Гэп: метод, которого нет в Protocol, на объекте, типизированном Protocol, — ребра нет

**Дата:** 2026-11-06. **Источник:** bquearch, после перехода на 0.0.31 (их 3a8b1f9). **Статус:** ✅ закрыто 2026-11-06 (0.0.32);
дизайн — [`docs/design/protocol_outside_method.md`](../docs/design/protocol_outside_method.md), бэклог R1-C88.

## 1. Что показали

```python
# research/tests/test_zone_scale.py::test_scale_neighbours_are_the_band_neighbours
fc = ForecasterSpec(model_type="knn_path", ...).build().fit(df)
fc.member_values(q, 3, cols=[...])
```

На 0.0.31 тип `fc` выводится (R1-C81 D4): `build() -> PathForecaster`, `fit(...) -> "PathForecaster"`. Но у
`PathForecaster` нет `member_values`, он есть только у части реализаций (`KnnPathForecaster`,
`KnnStrataForecaster`). Ребра нет, и `tests KnnPathForecaster.member_values` этот тест не видит. Находит он
только `test_zcast`, который читает исходник.

## 2. Почему так

`_Typer.method(T, name)` ищет метод у класса `T` и его баз. Для Protocol это его собственные методы, и
`member_values` среди них нет. Код bquearch вызывает его после проверки `hasattr`, то есть знает, что метод
есть не у всех реализаций. Статический тип Protocol этого не выражает.

## 3. Чем это опасно

Это тот же класс ответа, что R1-C81 до исправления: профильный тест есть, вызов прямой, а `tests` его не
называет. Разница в том, что теперь тип выведен, и не хватает одного шага.
