"""Doorverwijzing: de risicologica staat nu in risk/rules.py. Deze naam blijft bestaan voor oude imports."""
import sys

from risk import rules as _impl

sys.modules[__name__] = _impl
