# Гэп: `review` на правке одной константы модуля поднимает весь модуль до high, а у самой константы «потребителей нет»

**Дата:** 2026-11-06. **Источник:** bquearch (codemap в их цикле с 703696d), сводка —
[kogriv/codemap#25](https://github.com/kogriv/codemap/issues/25). **Статус:** открыто; дизайн —
[`docs/design/review_changed_lines.md`](../docs/design/review_changed_lines.md), бэклог R1-C82.

## 1. Что показали

bquearch `a948d6c` меняет одну строку `research/shared/contracts.py:353`: в кортеж `SURFACE_NAMES` добавлено
`"zone-scale"`. Граф `shared` (`--mode full`, быстрый тир) собран на этом же коммите, codmap 0.0.29, дифф
`git diff --relative=research a948d6c^ a948d6c`:

```
**3 changed symbol(s)**; blast by root: {'core': 101}.
**Review first (high risk):** shared.contracts
## [high] shared.contracts (shared/contracts.py:None)
- Consumers by root: {'core': 101}
- Call-site contract: 123 site(s) — check on signature change
## [low] shared.contracts.DEFAULT_SURFACE (shared/contracts.py:355)
## [low] shared.contracts.SURFACE_NAMES (shared/contracts.py:353)
```

У bquearch на их графе было 647 мест. Число зависит от графа, форма та же.

## 2. Почему так — три причины, а не одна

1. **Контекст диффа считается правкой.** `parse_unified_diff` берёт из заголовка `@@ +350,7 @@` все семь
   строк, включая по три строки контекста с каждой стороны. Изменена одна строка, 353. Строки 350–352 —
   комментарии между определениями, поэтому они уходят в модуль (запасной вариант `symbols_in_range`).
   Строка 355 — соседняя константа `DEFAULT_SURFACE`, которую никто не трогал.
2. **Досье модуля суммирует всех его членов.** `call_contract` и `references_to` идут по `_member_ids`, то
   есть по каждой функции и классу модуля. Поэтому 123 места вызова, «check on signature change» там, где
   сигнатур в диффе нет, и high по сумме.
3. **У константы модуля нет входящих рёбер.** Фикстура:
   `gates.py: from pkg.contracts import NAMES; def gate(x): return x in NAMES` даёт только ребро `export`.
   Чтение `NAMES` по имени внутри функции ребра не даёт, ни в чужом модуле, ни в своём (`Spec.check`).
   Ребро `accesses` есть только у формы `contracts.LIMIT`. Поэтому `SURFACE_NAMES` выходит `[low]` без
   потребителей, хотя её читают `contracts.py:474` и `gates`.

## 3. Чем это опасно

Ревьюер получает тревогу не там (весь модуль, 123 места, «сигнатура») и тишину там, где правка
(«потребителей нет» у константы, которую сверяют при импорте). Это хуже, чем ничего: сигнал инвертирован. По 30
последним коммитам `research/shared` контекстные строки добавляют 52 символа к 207 настоящим (259 против 207).
Досье модуля — 30 против 22. Замер сделан на графе a948d6c, поэтому строки старых коммитов немного съехали.

## 4. Найдено рядом, но не здесь

Дифф с путём от корня репозитория (`research/shared/contracts.py`) при графе, собранном из `research/`, даёт
«0 changed symbol(s)» и «Unresolved hunks: 1 — inspect manually». Это не молчание, отказ назван. Но путь
сопоставить можно. Это отдельный пункт бэклога, R1-C87.
