#!/usr/bin/env python3
"""Doorverwijzing: de instrumentcontrole bij Capital.com (alleen lezen) staat nu in execution/instruments.py (zelfde opties en uitvoer).
Deze bestandsnaam blijft bestaan voor de workflows, de Mac-starter en oude aanroepen."""
import sys

from execution import instruments as _impl

if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl
