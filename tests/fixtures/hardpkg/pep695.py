type Alias = int | str

def identity[T](x: T) -> T:
    return x

class Box[T]:
    def __init__(self, v: T) -> None:
        self.v = v
    def get(self) -> T:
        return self.v
