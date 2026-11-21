"""``python -m codemap`` — the same entry point as the ``codemap`` script.

The devkit pins this form when codemap runs without its console script (R1-C108 D2).
"""

from codemap.cli import main

raise SystemExit(main())
