#!/usr/bin/env python3
"""Doorverwijzing: het schrijven van status.json en markt/*.json voor de website staat nu in dashboard/status.py (zelfde opties en uitvoer).
Deze bestandsnaam blijft bestaan voor de workflows, de Mac-starter en oude aanroepen."""
import sys

from dashboard import status as _impl

if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl
