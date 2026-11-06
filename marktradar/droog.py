"""Droge ronde: alle bots spelen opgenomen testuitvoer af, zonder netwerk, sleutels of LLM."""
import copy
import json
from pathlib import Path

from .chief import draai_ronde

TESTDATA = Path(__file__).resolve().parent / "testdata" / "droge_ronde.json"


def speler(uitvoer):
    return lambda context: copy.deepcopy(uitvoer)


def draai(pad=TESTDATA):
    data = json.loads(Path(pad).read_text(encoding="utf-8"))
    bots = {naam: speler(u) for naam, u in data["bots"].items()}
    return draai_ronde(bots, data["ronde_id"], data["peilmoment"], droog=True)
