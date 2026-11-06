"""Charts: de technische stand per gekozen markt, met de bestaande code uit strategies/lab.py. Geen LLM.

Richting: alleen als de dagtrend (regime_now) en de uurtrend (indicators) het eens zijn. Anders "geen".

Zekerheid: geen gemeten kans. Bij gebrek aan bewijs loopt hij van 0,50 bij de trendgrens (efficiëntie 0,30) naar
hoogstens MAX_ZEKERHEID bij een efficiëntie van 0,70. Na genoeg afgerekende voorspellingen moet dit gemeten worden.

Strategiesignalen tonen we met richting "geen": geen enkele strategie is door de poort P1-P5 gekomen, dus een
signaal is hier informatie en geen stem.
"""
import pandas as pd

from strategies import lab

from .. import koersen as kz

MAX_ZEKERHEID = 0.60
TREND = {"Uptrend": "omhoog", "Downtrend": "omlaag"}


def _getal(x):
    return f"{x:.6g}"


def trend(df, X):
    regime = lab.regime_now(df)
    uur = str(X["trend"].iloc[-1])
    richting = "geen"
    if regime["trend"] == uur and uur in TREND:
        richting = TREND[uur]
    er = regime.get("efficientie", 0)
    zekerheid = round(0.5 + (MAX_ZEKERHEID - 0.5) * min(max((er - 0.3) / 0.4, 0), 1), 3) if richting != "geen" else 0.5
    return regime, richting, zekerheid, f"Trend: dag {regime['trend']} (efficiëntie {er:.2f}), uur {uur}."


def niveaus(df, X):
    dag = df.resample("1D").agg(dict(High="max", Low="min")).dropna()
    if len(dag) < 21:
        return None
    gisteren, maand = dag.iloc[-2], dag.iloc[-21:-1]
    return (f"Niveaus: slot {_getal(X['c'].iloc[-1])}, vorige dag {_getal(gisteren['Low'])}-{_getal(gisteren['High'])}, "
            f"20 dagen {_getal(maand['Low'].min())}-{_getal(maand['High'].max())}.")


def signalen(X):
    actief = []
    for sid, s in lab.STRATS.items():
        kanten = set()
        for v in s.get("varianten", ()):
            op, neer, _, _ = lab.signals(sid, X, v)
            if bool(op.fillna(False).iloc[-1]):
                kanten.add("long")
            if bool(neer.fillna(False).iloc[-1]):
                kanten.add("short")
        actief += [f"{s['titel']} {k}" for k in sorted(kanten)]
    return actief


def draai(context, koersen):
    bevindingen, ontbreekt, eindes = [], [], []
    for markt in context["markten"]:
        df = koersen.get(markt)
        if df is None or len(df) < 300:
            ontbreekt.append(f"{markt}: te weinig koersen")
            continue
        X = lab.indicators(df)
        bronnen = [kz.bron(markt, df)]
        eindes.append(kz.einde(df))

        def voeg_toe(tekst, richting="geen", zekerheid=0.5):
            bevindingen.append(dict(markt=markt, richting=richting, horizon=context["horizon"], zekerheid=zekerheid,
                                    bewering=tekst, bronnen=bronnen))

        regime, richting, zekerheid, tekst = trend(df, X)
        voeg_toe(tekst, richting, zekerheid)
        if "vol_percentiel" in regime:
            voeg_toe(f"Volatiliteit: {regime['vol']} (hoger dan {regime['vol_percentiel']:.0%} van de dagen dit jaar).")
        tekst = niveaus(df, X)
        if tekst:
            voeg_toe(tekst)
        actief = signalen(X)
        if actief:
            voeg_toe("Signaal op de laatste candle: " + ", ".join(actief) + ". Niet door de poort, dus geen bewijs.")
    tot = max(eindes, default=pd.Timestamp(context["peilmoment"]))
    return dict(bot="charts", ronde_id=context["ronde_id"], gemaakt_op=context["peilmoment"], data_tot=kz.isotijd(tot),
                bevindingen=bevindingen, ontbreekt=ontbreekt)
