#!/usr/bin/env python3
"""
ARCHIEF (bevroren, november 2026): afgerond onderzoek; draait niet in de cloud. Bij de refactor zijn alleen de
imports aangepast. Backtests via backtest.simulate gebruiken nu de centrale engine (kleine verschillen met de
oorspronkelijke cijfers: zie docs/refactor/3_engine_vergelijking.md).

Maakt artifact/data.json voor het online dashboard (de Claude-artifact):
  - setups van de afgelopen 30 dagen (NQ en EURUSD) met grafiekdata en uitkomst
  - backtest-voorbeelden en de winstcurve (uit data/voorbeelden.json)
  - de laatste runs van de cloud-workflow op GitHub en de meldingen van de laatste 12 uur op ntfy
  - de huidige schakelaars uit config.json

Gebruik:
  python dashboard_export.py
"""
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))   # repo-root (archief)

import json
import urllib.request
from datetime import datetime

from dashboard_v1 import NL, build_live, jsonable, load_examples
from tradingstrategie import CFG, DEFAULT_SETTINGS, HERE, load_settings

REPO = "nThijnS/TradingStrategie"
OUT = HERE / "artifact" / "data.json"


def get_json(url, lines=False):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "TradingStrategie"}), timeout=15) as r:
            body = r.read().decode()
    except Exception as ex:
        print("Niet gelukt:", url, ex)
        return [] if lines else {}
    return [json.loads(l) for l in body.splitlines() if l.strip()] if lines else json.loads(body)


def runs():
    data = get_json(f"https://api.github.com/repos/{REPO}/actions/runs?per_page=30")
    return [dict(n=r["run_number"], event=r["event"], status=r["status"], conclusion=r["conclusion"],
                 start=r["run_started_at"] or r["created_at"], end=r["updated_at"], url=r["html_url"])
            for r in data.get("workflow_runs", [])]


def phone_messages():
    topic = CFG["ntfy_topic"]
    if not topic:
        return []
    msgs = get_json(f"https://ntfy.sh/{topic}/json?poll=1&since=12h", lines=True)
    return [dict(t=m["time"], title=m.get("title", ""), msg=m.get("message", ""), prio=m.get("priority", 3))
            for m in msgs if m.get("event") == "message"]


def main():
    live, errors = build_live()
    data = dict(
        made=datetime.now(NL).strftime("%Y-%m-%d %H:%M"),
        live=live, errors=errors, examples=load_examples(),
        runs=runs(), phone=phone_messages(),
        settings=load_settings(), defaults=DEFAULT_SETTINGS, repo=REPO,
        strategy=dict(sessions=dict(zip(["London", "NY AM", "NY PM"], CFG["trade_sess"])),
                      kans=CFG["kans_sess"], tp_r=CFG["tp_r"],
                      markets=[dict(name=m["name"], symbol=m["symbol"], tp=m["cfg"].get("tp_mode", CFG["tp_mode"]))
                               for m in CFG["markets"]]),
    )
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(data, default=jsonable, separators=(",", ":")))
    print(f"{OUT} geschreven: {len(live)} setups, {len(data['runs'])} runs, {len(data['phone'])} meldingen")


if __name__ == "__main__":
    main()
