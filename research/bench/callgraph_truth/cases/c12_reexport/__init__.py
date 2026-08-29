"""Decidable: the callee is reached through a module that only re-exports it (R1-C30-f1).

A package that re-exposes its API (`from .impl import run`) is the most ordinary shape in
Python, and the name the caller writes — `api.helper` — is not a definition anywhere. The
fast tier resolved to that non-node and the soundness guard dropped the edge, silently;
the deep tier followed the alias, which made a missing lookup look like a type-inference
capability. `missing` is the guard: a name the re-exporting module does not carry must not
be routed to a plausible neighbour just because one exists.
"""

from c12_reexport.api import helper


def run():
    return helper()


def absent():
    from c12_reexport import api
    return api.missing()
