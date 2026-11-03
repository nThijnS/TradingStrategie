#!/usr/bin/env python3
"""Doorverwijzing: de meldingen-app staat nu in app/alerts.py (zelfde opties en uitvoer).
Deze bestandsnaam blijft bestaan voor de workflows, de Mac-starter en oude aanroepen."""
import sys

from app import alerts as _impl

if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl
