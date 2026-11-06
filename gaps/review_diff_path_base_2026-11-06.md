# Гэп: дифф с путями от корня репозитория при графе из подкаталога — `review` отвечает «0 changed symbol(s)»

**Дата:** 2026-11-06. **Источник:** найдено при воспроизведении R1-C82, затем подтверждено bquearch, которые
записали это себе в правила. **Статус:** открыто; дизайн —
[`docs/design/review_path_base.md`](../docs/design/review_path_base.md), бэклог R1-C87.

## 1. Что показали

bquearch `a948d6c`, граф собран из `research/` (`codemap build shared --mode full`), узлы `shared.*`, пути
файлов `shared/contracts.py`. Дифф снят обычным `git diff a948d6c^ a948d6c`, то есть с путями от корня
репозитория: `research/shared/contracts.py`. codmap 0.0.31:

```
# Change-set review
**0 changed symbol(s)**; blast by root: —.
_Unresolved hunks (module-level / unknown file): 1 — inspect manually._
```

С `git diff --relative=research` тот же дифф даёт `[medium] shared.contracts.SURFACE_NAMES`.

## 2. Почему так

`build_review` ищет файл хунка в графе по точному совпадению строки пути. База путей графа — общий корень его
корней сборки (R1-C31). База путей диффа — корень git. Если граф собран не из корня репозитория, эти базы
расходятся, ни один файл не совпадает, и все хунки уходят в `unresolved_hunks`. Там они лежат в одном списке
с честными хунками на уровне модуля, и подпись «module-level / unknown file» их не различает.

## 3. Чем это опасно

Ноль символов на непустом диффе читается как «ничего не задето». Строка про unresolved стоит ниже, мелким
курсивом, и говорит «module-level», хотя ни одна строка не была даже сопоставлена с графом. В JSON
(`summary.changed_symbols: 0`) различить нечем. Обход, который bquearch записали в правила (`--relative`),
держится на памяти, а не на инструменте.
