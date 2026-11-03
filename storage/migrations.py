#!/usr/bin/env python3
"""Controleerbare migraties van de opgeslagen data, altijd met backup en eerst een proefrun.

    python -m storage.migrations                       # overzicht: welke migraties, en of ze al gedraaid zijn
    python -m storage.migrations proef 001             # uitrekenen en de gevolgen tonen, niets schrijven
    python -m storage.migrations uitvoeren 001         # backup in backups/<tijd>/, dan schrijven en controleren
    python -m storage.migrations terugzetten <map>     # een backup terugzetten

Migratie 001 (leergeheugen, simulatie v2)
  Rekent de uitkomsten in leren_geheugen.json opnieuw uit met de centrale engine (backtesting/engine.py):
  doel in de vulcandle telt niet, precies 5 uur, DOL zonder liquiditeit = 1R zoals de app.
  - HistData-rijen: opnieuw uit de lokale HistData (data/raw); dezelfde setups (de detectie is ongewijzigd).
  - Yahoo-rijen: opnieuw uit de laatste 60 dagen Yahoo-data. Ouder dan 60 dagen kan niet; die rijen blijven
    zoals ze waren en houden sim=1 (ze tellen wel mee, zoals voorheen).
  Daarna kiest het leren mogelijk een andere variant. Draai deze migratie pas na de merge, lokaal (HistData nodig),
  en commit het resultaat zelf. Zolang ze niet gedraaid is, mengt het geheugen oude (sim=1) en nieuwe (sim=2) rijen.
"""
import hashlib
import json
import shutil
import sys
from datetime import datetime

from storage import jsonstore, paths

MIGRATIONS = {"001": "leergeheugen opnieuw uitrekenen met de centrale engine (simulatie v2)"}


# ------------- Backup -------------
def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def backup(files, tag):
    d = paths.BACKUPS / f"{datetime.now():%Y%m%d-%H%M%S}-{tag}"
    d.mkdir(parents=True)
    manifest = {}
    for f in files:
        if f.exists():
            shutil.copy2(f, d / f.name)
            manifest[f.name] = dict(pad=str(f.relative_to(paths.ROOT)), sha256=sha(f), bytes=f.stat().st_size)
    jsonstore.save(d / "MANIFEST.json", manifest)
    for name, m in manifest.items():           # backup controleren voordat er iets overschreven wordt
        assert sha(d / name) == m["sha256"], f"backup van {name} klopt niet"
    return d


def restore(d):
    manifest = jsonstore.load(d / "MANIFEST.json")
    for name, m in manifest.items():
        assert sha(d / name) == m["sha256"], f"backup van {name} is beschadigd"
        shutil.copy2(d / name, paths.ROOT / m["pad"])
    print(f"teruggezet uit {d}: {', '.join(manifest)}")


def log(entry):
    hist = jsonstore.load(paths.ROOT / "storage" / "migraties.json", [])
    hist.append(entry)
    jsonstore.save(paths.ROOT / "storage" / "migraties.json", hist)


# ------------- 001: leergeheugen simulatie v2 -------------
def m001_compute(mem):
    import pandas as pd
    from backtesting import engine
    from core import config, data
    from learning import ict as leren
    from strategies.ict_tjr import analyse
    new, stats = {}, dict(histdata=0, yahoo=0, ongewijzigd_oud=0, niet_gevonden=0)
    by_src = {}
    for k, r in mem.items():
        by_src.setdefault((r["markt"], r["bron"]), {})[k] = r
    for m in config.CFG["markets"]:
        for source in ("histdata", "yahoo"):
            rows = by_src.get((m["name"], source))
            if not rows:
                continue
            if source == "histdata":
                df, es = leren.histdata(m)
            else:
                df, es = data.fetch(m["symbol"], "60d"), data.fetch(m["smt"], "60d")
            B = engine.Bars(df)
            first = df.index[0].isoformat()
            setups = {}
            for dname, over in leren.DISP.items():
                cfg = {**config.CFG, **m["cfg"], **over, "max_per_day": 6, "need_bias_b": False,
                       "trade_sess": [("02:00", "05:00"), ("09:30", "11:30"), ("13:30", "15:30")]}
                for s in analyse(df, es, cfg)[0]:
                    setups[(dname, s["time"].isoformat(), s["side"])] = (s, cfg)
            for k, r in rows.items():
                found = setups.get((r["disp"], r["t"], k.split("|")[-1]))
                if found is None:
                    new[k] = r
                    stats["ongewijzigd_oud" if r["t"] < first else "niet_gevonden"] += 1
                    continue
                s, cfg = found
                R = leren.simulate5(B, s, r["target"], leren.COST.get(m["name"], 0), cfg["tp_r"])
                if R is None:
                    new[k] = r
                    stats["niet_gevonden"] += 1
                    continue
                new[k] = dict(r, R=round(float(R), 3), sim=leren.SIM_VERSION)
                stats[source] += 1
            print(f"{m['name']} {source}: {len(rows)} rijen", flush=True)
    return new, stats


def m001_impact(old, new):
    from learning import ict as leren
    prev = {k: dict(variant=leren._parse(v["variant"]), sinds=v.get("sinds"))
            for k, v in (jsonstore.load(paths.LEARNED, {}) or {}).get("markten", {}).items() if "variant" in v}
    a, _ = leren.choose(old, prev)
    b, _ = leren.choose(new, prev)
    out = {}
    for name in sorted(set(a) | set(b)):
        f = lambda c: None if not c else dict(variant=leren.vid(c["variant"]), actief=c["actief"], score=c["score"]["score"], n=c["score"]["n"])
        out[name] = dict(voor=f(a.get(name)), na=f(b.get(name)))
    return out


def run(cmd, mid):
    if mid != "001":
        sys.exit(f"onbekende migratie {mid}")
    old = jsonstore.load(paths.LEREN_MEMORY, {})
    new, stats = m001_compute(old)
    changed = sum(1 for k in old if old[k].get("R") != new[k].get("R"))
    impact = m001_impact(old, new)
    print(json.dumps(dict(rijen=len(old), opnieuw=stats, R_veranderd=changed, keuze=impact), ensure_ascii=False, indent=1))
    if cmd != "uitvoeren":
        print("proefrun: niets geschreven")
        return
    d = backup([paths.LEREN_MEMORY, paths.LEARNED], "001")
    jsonstore.save(paths.LEREN_MEMORY, new, compact=True)
    check = jsonstore.load(paths.LEREN_MEMORY)
    assert check == new and len(check) == len(old), "controle na schrijven mislukt"
    log(dict(migratie="001", t=datetime.now().isoformat(timespec="seconds"), backup=str(d.relative_to(paths.ROOT)),
             rijen=len(old), opnieuw=stats, R_veranderd=changed, keuze=impact))
    print(f"klaar; backup in {d}. Draai daarna `python leren.py --geen-data` om de keuze te vernieuwen.")


def main():
    a = sys.argv[1:]
    if not a:
        done = {x["migratie"] for x in jsonstore.load(paths.ROOT / "storage" / "migraties.json", [])}
        for k, v in MIGRATIONS.items():
            print(f"{k}  {'gedraaid' if k in done else 'open    '}  {v}")
        return
    if a[0] == "terugzetten":
        restore(paths.ROOT / a[1] if not a[1].startswith("/") else __import__("pathlib").Path(a[1]))
        return
    run(a[0], a[1])


if __name__ == "__main__":
    main()
