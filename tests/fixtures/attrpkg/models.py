"""A dataclass with fields read/written via ``self.`` — plus a property (a function
node, which must NOT be modelled as an attribute)."""

from dataclasses import dataclass


@dataclass
class Config:
    width: int = 10
    height: int = 20
    depth: int = 0  # never accessed anywhere — the honesty (risk="unknown") case

    def area(self):
        return self.width * self.height   # self.field read (self)

    def reset(self):
        self.width = 0                    # self.field write (self)

    @property
    def diagonal(self):                   # a property -> function node, not attribute
        return self.width + self.height   # self.width/height reads (self)

    def perimeter(self):
        return self.diagonal * 2          # self.diagonal is a property (function) — no edge
