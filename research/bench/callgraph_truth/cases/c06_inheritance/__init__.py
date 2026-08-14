"""Decidable: a subclass method calls a method inherited from its base via
``self``. Resolving ``self.base_op()`` requires knowing ``self``'s class and
walking the MRO to the base definition.
"""


class Base:
    def base_op(self):
        return 1


class Derived(Base):
    def run(self):
        return self.base_op()
