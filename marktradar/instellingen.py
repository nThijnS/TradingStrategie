"""Instellingen van MarktRadar. Staan los van config.json, zodat MarktRadar de bot niet kan beïnvloeden."""
import json
from pathlib import Path

PAD = Path(__file__).resolve().parent / "instellingen.json"
VELDEN = ("max_markten", "horizon", "scout_drempel", "drempel_volgen", "drempel_onderzoeken", "straf_per_ontbrekende_bot", "llm_model",
          "llm_max_tokens", "max_dagbudget_usd")


def laad(pad=PAD):
    i = json.loads(Path(pad).read_text())
    if sorted(i) != sorted(VELDEN):
        raise ValueError(f"instellingen moeten precies deze velden hebben: {VELDEN}")
    if not 0.5 < i["drempel_onderzoeken"] <= i["drempel_volgen"] <= 1:
        raise ValueError("drempels: 0,5 < onderzoeken <= volgen <= 1")
    if not 0 <= i["straf_per_ontbrekende_bot"] < 1 / 3:
        raise ValueError("straf_per_ontbrekende_bot moet tussen 0 en 1/3 liggen")
    if not 0.5 <= i["scout_drempel"] < 1:
        raise ValueError("scout_drempel moet tussen 0,5 en 1 liggen")
    if not isinstance(i["max_markten"], int) or i["max_markten"] < 1:
        raise ValueError("max_markten moet minstens 1 zijn")
    if not 0 <= i["max_dagbudget_usd"] <= 5:
        raise ValueError("max_dagbudget_usd moet tussen 0 en 5 dollar liggen")
    return i
