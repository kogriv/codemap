"""Imports its sibling the flat way — resolved at runtime because the directory
itself is on sys.path, which is what makes this layout invisible to a loader that
only knows package-qualified names."""

from alpha import base_width          # flat: no package prefix


def doubled() -> int:
    return base_width() * 2
