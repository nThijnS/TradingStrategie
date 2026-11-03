#!/usr/bin/env python3
"""Doorverwijzing: de orderuitvoering (Capital.com, demo standaard, live alleen na opt-in) staat nu in execution/runner.py (zelfde opties en uitvoer).
Deze bestandsnaam blijft bestaan voor de workflows, de Mac-starter en oude aanroepen."""
import sys

from execution import runner as _impl

if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl
