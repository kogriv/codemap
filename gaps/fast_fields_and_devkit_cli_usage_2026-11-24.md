# Гэп — тип поля в fast и CLI в счётчике devkit

**Версия наблюдения:** codmap 0.0.47, схема 0.13, формат ответов 12.
**Статус:** исправлено в рабочем дереве 2026-11-24. **Бэклог:** R1-C147 и R1-C148.
**Дизайн:** [fast_fields_and_devkit_cli_usage.md](../docs/design/fast_fields_and_devkit_cli_usage.md).

## F1 — вызов через поле объекта пропадает из fast-графа

Репортёр увидел живой приватный метод среди кандидатов `dead-code` уровня `high`
и отсутствие входящего вызова в `query`. Это воспроизводилось на fast-графах
с обоими режимами потребительского корня. На deep-графе метод получал входящий
вызов и исчезал из `high`.

Синтетическая форма:

```python
from __future__ import annotations

class Task:
    def __init__(self, worker: Worker):
        self._worker = worker

    def execute(self):
        return self._worker._work()

class Worker:
    def _work(self):
        return 1
```

В 0.0.47 fast-резолвер знал прямой `self.method()` и цепи через импорт.
Для `self._worker` он терял связь между аннотацией параметра и полем конструктора.
[Классификатор dead code](../codemap/query.py#L654) присваивает `high`,
когда в графе отсутствуют входящие ссылки, вызовы и декораторы.

Контроль на коде тега `v0.0.47` и [синтетической фикстуре](../tests/fixtures/annotated_fields/__init__.py):
`callers(Worker._work)` вернул пустой список, а сам метод появился в
`dead_code(min_confidence="high")`. До правки тесты thin/full и отдельный
контроль строковой аннотации упали на отсутствии входящего вызова.

После правки `callers` показывает `Task.execute` на fast в thin и full.
Ребро имеет маршрут `annotated-field` и грейд `inferred`, а `Worker._work`
исчезает из `dead-code high`.

## F2 — CLI отсутствует в devkit usage

Репортёр видел использование CLI в журнале Claude Code, но
`devkit usage` показывал нулевую долю codemap при отсутствии MCP-вызовов.
Синтетический контроль: один Bash tool-use выполняет `codemap query Task`,
второй — `rg Task`. Старый отчёт считает один поиск и ноль использований
codemap. В 0.0.47 ветка Bash распознавала только grep.
До правки синтетический тест CLI без MCP и тест со смешанными командами
остановились на отсутствии отдельного счётчика CLI.

После правки [счётчик](../codemap/devkit/usage.py#L138) выводит MCP=0, CLI=1,
grep=1 и долю 50% в JSON и Markdown.

Отчёт охватывает локальные Claude Code transcripts, включая подагентов.
Codex и другие источники остаются вне области. В примерах используются
синтетические команды и идентификаторы.
