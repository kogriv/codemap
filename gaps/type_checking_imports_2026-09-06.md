# Гэп: импорт под `if TYPE_CHECKING:` судится как eager — корректное дерево красное навсегда

**Дата:** 2026-09-06. **Источник:** [codemap#18](https://github.com/kogriv/codemap/issues/18) от
сессии bquant, вставшей на гейт `codemap check` с `no_cycles = true`. **Статус:** воспроизведено,
дизайн — [`docs/design/type_checking_imports.md`](../docs/design/type_checking_imports.md),
бэклог R1-C48.

## 1. Что видно

На дереве bquant `6b17e35` (0.0.14), `codmap` 0.0.12 и текущий `main` `dc2335d`, fast-тир:

```
## `no_cycles` — 1 import cycle(s)
- bquant.analysis.zones.cache → bquant.analysis.zones.pipeline → bquant.analysis.zones.cache

_Read 271 module-level and 26 function-local import(s)…_
### Dependency cycles closed only by a function-local import: 9
```

Ребро `cache → pipeline` лежит в графе с пустыми `extras` — как обычный импорт времени загрузки.
В `cache.py` единственный импорт `pipeline` стоит так:

```python
if TYPE_CHECKING:
    from .pipeline import ZoneAnalysisConfig
```

`TYPE_CHECKING` при исполнении всегда `False`: этот импорт не выполняется никогда, ни при
загрузке модуля, ни позже. Документация `no_cycles` обещает судить «the eager import graph only —
imports that run at import time». Обещание нарушено: гейт красный на дереве, где цикл разорван
стандартной идиомой, и его нельзя сделать зелёным, не переписав корректный код. Сессия bquant
выключила правило со ссылкой на issue.

## 2. Механизм

griffe кладёт в `module.imports` всё, что написано на уровне модуля, включая тела `if` — у него
нет понятия «условие, которое ложно при исполнении». codemap читает эту карту как module-level
(`scope` не проставлен → eager). Собственный AST-проход `_source_import_targets` (R1-C23, R1-C29)
ищет только то, чего у griffe нет: звёздочки, импорты в функциях и в телах классов; `if` на уровне
модуля он проходит насквозь как модульный уровень и ничего не добавляет. Ни один слой не смотрит
на условие.

На дереве bquant такой импорт один, на дереве codemap — тоже один (`serve/mcp_server.py`, под
`if TYPE_CHECKING:` для опциональной зависимости `mcp`); он никакого цикла не замыкает, поэтому
собственный контракт codemap (`no_lazy_cycles`) этого не поймал — гейт, которому ни разу не
показали то, что он обязан пропустить, не гейт (R1-C37).

## 3. Что следует для дизайна

Импорт под `if TYPE_CHECKING:` — третья область видимости, не вторая. Он не eager (не выполняется
при загрузке) и не function-local (не выполняется вообще). Складывать его в `function` — врать
о том, где он написан; оставлять в eager — врать о том, когда он выполняется. Нужна своя метка
`scope: "type_checking"`, свой счётчик в `import_map` (всегда, включая ноль — R1-C28), и все
потребители eager-графа обязаны его исключать. Циклы, замкнутые только через такой импорт, —
по-прежнему связность (модули ссылаются на типы друг друга), и они идут туда же, куда ленивые:
`lazy_cycles`, `no_lazy_cycles`. Формулировки «closed only by a function-local import» во всех
пяти потребителях становятся неверными и переписываются.

Что считается `TYPE_CHECKING`: `if TYPE_CHECKING:` и `if <что-угодно>.TYPE_CHECKING:` (имя
`typing.TYPE_CHECKING`, `t.TYPE_CHECKING`), их отрицание `if not …:` переворачивает ветви, ветка
`else:` — время исполнения. Составные условия (`if TYPE_CHECKING or X`) не распознаются и
остаются eager — узко нарочно: неузнанное условие судится строже, а не мягче.

## 4. Приёмка (R1-C48)

- На том же дереве bquant с `no_cycles = true`: гейт зелёный, строка охвата называет, сколько
  импортов под `TYPE_CHECKING` не судилось (здесь 1), `lazy_cycles` — 10 вместо 9 (цикл
  `cache ↔ pipeline` переехал из eager в ленивые).
- Побайтово: граф после правки отличается от графа до неё ровно одним ребром — `cache → pipeline`
  получает `extras.scope = "type_checking"`; узлы и остальные рёбра идентичны.
- На дереве codemap: один импорт под `TYPE_CHECKING` (`mcp_server`), собственный контракт
  по-прежнему зелёный, число ленивых циклов не меняется.
- Игрушка: `if TYPE_CHECKING`, `if typing.TYPE_CHECKING`, `if not TYPE_CHECKING … else`, тот же
  модуль импортирован и под `TYPE_CHECKING`, и на уровне модуля (eager побеждает), под
  `TYPE_CHECKING` внутри функции (остаётся `function`), составное условие (остаётся eager).
  Мутация «условие не распознаётся» красит тесты.

## 5. Чего не проверяли

- Другие «никогда не исполняемые» условия: `if False:`, `if sys.version_info < (3, 0):` — не
  распознаются, судятся как eager. Не измерено, насколько они встречаются.
- Импорт под `TYPE_CHECKING` как источник `references`/`calls` на deep-тире — jedi видит его как
  обычное имя; это про разрешение имён (D4 в `hard_python_robustness.md`), а не про eager-граф.
