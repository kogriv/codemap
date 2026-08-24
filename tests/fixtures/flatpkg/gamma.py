"""Same layout, one level of indirection — and a package-qualified import beside the
flat one, so a test can tell an exact edge from an inferred one."""

import beta                            # flat, module form
from flatpkg.alpha import WIDTH        # package-qualified: must stay unlabelled


def report() -> int:
    return beta.doubled() + WIDTH
