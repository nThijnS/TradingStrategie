#!/usr/bin/env python3
"""Doorverwijzing: het strategielab staat nu in learning/lab.py (zelfde opties en uitvoer).
Deze bestandsnaam blijft bestaan voor de workflows, de Mac-starter en oude aanroepen."""
import sys

from learning import lab as _impl

if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl
