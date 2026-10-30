"""Compatibility entry point: ``python main.py`` keeps working.

The implementation lives in :mod:`web_harvester.cli`; the console script
``web-harvester`` points there as well.
"""

import sys

from web_harvester.cli import main

if __name__ == "__main__":
    sys.exit(main())
