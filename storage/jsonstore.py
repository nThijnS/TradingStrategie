"""JSON laden en atomair opslaan. Eén implementatie voor alle modules."""
import json
import os
from pathlib import Path


def load(path, default=None):
    """Inhoud van een JSON-bestand, of `default` als het ontbreekt of kapot is."""
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def save(path, data, indent=1, compact=False, default=None):
    """Atomair wegschrijven: eerst een tijdelijk bestand, dan vervangen (nooit een half bestand).
    compact=True schrijft zonder spaties (grote bestanden zoals het leergeheugen en lab.json)."""
    path = Path(path)
    text = (json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=default) if compact
            else json.dumps(data, ensure_ascii=False, indent=indent, default=default))
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)
    return path
