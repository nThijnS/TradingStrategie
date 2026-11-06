"""Rondes worden één keer weggeschreven en nooit overschreven: zo blijven voorspellingen vooraf vastgelegd."""
import json
from pathlib import Path


def rondepad(map_, ronde_id, droog=False):
    return Path(map_) / "rondes" / f"{ronde_id}{'-droog' if droog else ''}.json"


def bewaar(ronde, map_):
    pad = rondepad(map_, ronde["ronde_id"], ronde["droog"])
    pad.parent.mkdir(parents=True, exist_ok=True)
    tekst = json.dumps(ronde, indent=1, ensure_ascii=False, sort_keys=True, default=str)
    with open(pad, "x", encoding="utf-8") as f:     # "x" weigert een bestaand bestand
        f.write(tekst + "\n")
    return pad


def _rijen(pad):
    pad = Path(pad)
    return [json.loads(x) for x in pad.read_text(encoding="utf-8").splitlines() if x.strip()] if pad.exists() else []


def _voeg_toe(pad, rijen):
    pad = Path(pad)
    pad.parent.mkdir(parents=True, exist_ok=True)
    with open(pad, "a", encoding="utf-8") as f:
        for r in rijen:
            f.write(json.dumps(r, ensure_ascii=False, sort_keys=True) + "\n")


def lees_historie(map_):
    return _rijen(Path(map_) / "sentiment.jsonl")


def bewaar_metingen(map_, rijen):
    """Voegt metingen toe; per markt één meting per dag."""
    bestaand = {(r["t"][:10], r["markt"]) for r in lees_historie(map_)}
    _voeg_toe(Path(map_) / "sentiment.jsonl", [r for r in rijen if (r["t"][:10], r["markt"]) not in bestaand])


def besteed_op(map_, datum):
    return sum(r["usd"] for r in _rijen(Path(map_) / "kosten.jsonl") if r["datum"] == datum)


def boek_kosten(map_, datum, model, usd):
    _voeg_toe(Path(map_) / "kosten.jsonl", [dict(datum=datum, model=model, usd=round(usd, 6))])


def lees_uitkomsten(map_):
    return _rijen(Path(map_) / "uitkomsten.jsonl")


def bewaar_uitkomsten(map_, rijen):
    if rijen:
        _voeg_toe(Path(map_) / "uitkomsten.jsonl", rijen)


def kosten_per_maand(map_):
    uit = {}
    for r in _rijen(Path(map_) / "kosten.jsonl"):
        uit[r["datum"][:7]] = round(uit.get(r["datum"][:7], 0.0) + r["usd"], 6)
    return uit


def bewaar_dashboard(map_, data):
    pad = Path(map_) / "dashboard.json"
    pad.parent.mkdir(parents=True, exist_ok=True)
    pad.write_text(json.dumps(data, ensure_ascii=False, sort_keys=True), encoding="utf-8")
