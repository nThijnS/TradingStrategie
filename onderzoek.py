#!/usr/bin/env python3
"""Doorverwijzing: het onderzoeksprotocol staat nu in research/protocol.py (zelfde opties en uitvoer).
Deze bestandsnaam blijft bestaan voor de workflows, de Mac-starter en oude aanroepen."""
import sys

from research import protocol as _impl

if __name__ == "__main__":
    _impl.main()
else:
    sys.modules[__name__] = _impl
