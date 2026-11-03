"""Doorverwijzing: de Capital.com-client staat nu in execution/capital.py. Deze naam blijft bestaan voor oude imports."""
import sys

from execution import capital as _impl

sys.modules[__name__] = _impl
