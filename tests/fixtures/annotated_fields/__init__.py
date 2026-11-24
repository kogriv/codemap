from __future__ import annotations


class Task:
    def __init__(self, worker: Worker):
        self._worker = worker

    def execute(self):
        return self._worker._work(1)


class Worker:
    def _work(self, task):
        return task

    def _unused(self):
        pass


class Other:
    def _work(self, task):
        return task
