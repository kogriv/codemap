REGISTRY = {}

class Meta(type):
    def __call__(cls, *a, **k):
        return super().__call__(*a, **k)

class Base(metaclass=Meta):
    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        REGISTRY[cls.__name__] = cls

    def run(self):
        return self.step()

    def step(self):
        raise NotImplementedError

class Impl(Base):
    def step(self):
        return _helper_meta()

def _helper_meta():
    return 1
