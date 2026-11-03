"""Experimentregistratie: elk onderzoek legt vast wat er gedraaid is, met welke code, data en softwareversies.

Eén regel per run in rapport/experimenten.jsonl (alleen toevoegen, nooit herschrijven). Daarmee is later na te gaan
of een resultaat reproduceerbaar is: zelfde git-commit, zelfde dataperiode, zelfde pandas/numpy/yfinance.
"""
import hashlib
import json
import platform
import subprocess
from datetime import datetime, timezone

from storage import paths


def versions():
    out = dict(python=platform.python_version())
    for mod in ("pandas", "numpy", "yfinance"):
        try:
            out[mod] = __import__(mod).__version__
        except Exception:
            out[mod] = None
    return out


def git_commit():
    try:
        sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=paths.ROOT, capture_output=True, text=True, timeout=5).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain", "--", "*.py"], cwd=paths.ROOT, capture_output=True, text=True,
                               timeout=5).stdout.strip()
        return (sha or None), bool(dirty)
    except Exception:
        return None, None


def fingerprint(df):
    """Korte vingerafdruk van een OHLC-reeks: periode, aantal candles en een hash van de slotkoersen."""
    if df is None or not len(df):
        return None
    h = hashlib.sha256(df["Close"].round(8).to_numpy().tobytes()).hexdigest()[:16]
    return dict(van=df.index[0].isoformat(), tot=df.index[-1].isoformat(), candles=len(df), hash=h)


def record(name, params=None, results=None, data=None, path=None):
    sha, dirty = git_commit()
    row = dict(t=datetime.now(timezone.utc).isoformat(timespec="seconds"), experiment=name, commit=sha, code_gewijzigd=dirty,
               versies=versions(), parameters=params or {}, data=data or {}, resultaten=results or {})
    path = path or paths.EXPERIMENTS
    path.parent.mkdir(exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    return row
