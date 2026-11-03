"""Centrale configuratie van de ICT/TJR-app.

CFG          strategie- en meldingsinstellingen (standaard); per markt overschreven door markets[i]["cfg"]
SET          de schakelaars uit config.json (dashboard)
learned.json wat het leren per markt kiest; apply_learned() legt dat over de standaard heen

CFG en SET zijn gewone dicts die door apply_settings() IN PLAATS worden bijgewerkt, zodat elke module die ze
geïmporteerd heeft dezelfde waarden ziet. apply_settings() mag vaker worden aangeroepen: het begint telkens
vanaf de standaard.
"""
import copy
import os

from core.markets import ICT_MARKETS
from storage import jsonstore, paths

CFG = {
    "symbol": "NQ=F",          # Nasdaq futures (Yahoo); voor ES: "ES=F"
    "smt_symbol": "ES=F",      # gecorreleerd symbool voor SMT
    "markets": copy.deepcopy(ICT_MARKETS),
    "trade_sess": [("02:00", "05:00"), ("09:30", "11:30"), ("13:30", "15:30")],   # London, NY AM, NY PM
    "sb_sess": [("03:00", "04:00"), ("10:00", "11:00"), ("14:00", "15:00")],      # Silver Bullet per sessie
    "asia_sess": ("20:00", "23:59"),
    "lond_sess": ("02:00", "05:00"),
    "htf_a": "4h",             # context
    "htf_b": "1h",             # bias ("30min" kan ook)
    "htf_piv": 3,
    "need_bias_b": False,      # False: tegen de bias mag, maar telt als lagere kans
    "piv_len": 3,
    "disp_pct": 0.7,           # strenger dan 0.6/1.2: beter in de backtest
    "disp_atr": 1.5,
    "mss_window": 20,
    "fvg_window": 3,
    "smt_len": 20,
    "entry_mode": "50%",       # of "Rand"
    "entry_win": 12,
    "min_rr": 2.0,             # alleen voor het DOL-vinkje in de score
    "tp_r": 1.0,               # winst nemen op 1R (backtest: beter dan de DOL als doel)
    "tp_mode": "R",            # "R" = vaste tp_r, "DOL" = op de liquiditeit (valt terug op tp_r)
    "kans_sess": ["NY AM"],    # alleen setups in deze sessie(s) zijn "kans"
    "buf_ticks": 4,
    "tick": 0.25,
    "max_per_day": 6,          # alle setups samen, zodat je niet wordt overspoeld
    "min_score": 0,            # extra eis voor "kans" (backtest: de score hielp niet, dus uit)
    "no_close": False,         # TradingPool: na de sweep mag geen candle buiten het niveau sluiten
    "need_smt": False,         # TradingPool: divergentie (SMT) verplicht bij de sweep
    "day_end": "15:30",        # na dit tijdstip: melding als er vandaag niks was
    # Pushmelding op je telefoon via de gratis app "ntfy". Het onderwerp staat in ntfy_topic.txt
    # (niet in de code, zodat het geheim blijft) of in de omgevingsvariabele NTFY_TOPIC (cloud).
    "ntfy_topic": paths.NTFY_TOPIC_FILE.read_text().strip() if paths.NTFY_TOPIC_FILE.exists() else "",
}
BASE_CFG = copy.deepcopy(CFG)

# Aan/uit-schakelaars uit het dashboard. Staan in config.json; ontbreekt iets, dan geldt de standaard.
DEFAULT_SETTINGS = {
    "actief": True,                                        # hoofdschakelaar voor alle meldingen
    "markten": {"NQ": True, "EURUSD": True, "GOUD": True},
    "sessies": {"London": True, "NY AM": True, "NY PM": True},
    "alleen_kans": False,                                  # True: geen "LAGE KANS"-meldingen
    "entry_meldingen": True,                               # "prijs in entry-zone"
    "dagmelding": True,                                    # "vandaag geen setup" na day_end
    "telefoon": True,                                      # ntfy-pushmeldingen
    "max_per_day": 6,
}
SET = copy.deepcopy(DEFAULT_SETTINGS)
SESS_NAMES = ["London", "NY AM", "NY PM"]                  # zelfde volgorde als trade_sess en sb_sess


def load_settings(path=None):
    s = copy.deepcopy(DEFAULT_SETTINGS)
    own = jsonstore.load(path or paths.CONFIG)
    if not isinstance(own, dict):
        return s
    for k, v in own.items():
        if isinstance(s.get(k), dict) and isinstance(v, dict):
            s[k].update(v)
        elif k in s:
            s[k] = v
    return s


def apply_settings(settings_file=None, learned_file=None):
    """config.json toepassen op CFG (markten en sessies) en SET (meldingen), daarna learned.json."""
    if os.environ.get("NTFY_TOPIC"):   # in de cloud komt het onderwerp uit een geheim/variabele
        BASE_CFG["ntfy_topic"] = os.environ["NTFY_TOPIC"]
    new = load_settings(settings_file)
    SET.clear()
    SET.update(new)
    base = copy.deepcopy(BASE_CFG)
    CFG.clear()
    CFG.update(base)
    CFG["markets"] = [m for m in CFG["markets"] if SET["markten"].get(m["name"], True)]
    keep = [i for i, n in enumerate(SESS_NAMES) if SET["sessies"].get(n, True)]
    CFG["trade_sess"] = [CFG["trade_sess"][i] for i in keep]
    CFG["sb_sess"] = [CFG["sb_sess"][i] for i in keep]
    CFG["max_per_day"] = int(SET["max_per_day"])
    apply_learned(learned_file)


def apply_learned(learned_file=None):
    """Wat het leren per markt heeft gekozen over de standaard heen leggen; zonder learned.json verandert er niets."""
    learned = (jsonstore.load(learned_file or paths.LEARNED) or {}).get("markten", {})
    for m in CFG["markets"]:
        m.setdefault("base_cfg", dict(m["cfg"]))
        lm = learned.get(m["name"])
        if lm:
            m["cfg"] = dict(m["base_cfg"], **lm["cfg"], kans_sess=lm["kans_sess"], need_bias_b=lm["need_bias_b"])
            m["actief"], m["variant"] = bool(lm["actief"]), lm.get("variant")
        else:
            m["cfg"], m["actief"] = dict(m["base_cfg"]), not m.get("learn_only", False)
