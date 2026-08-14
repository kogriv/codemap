"""Decidable: a method calls a sibling method via ``self``."""


class Widget:
    def render(self):
        return self.paint()

    def paint(self):
        return 1
