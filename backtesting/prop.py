"""Prop-firm-simulatie (FTMO-achtige challenge) op een reeks trades in R."""
import numpy as np
import pandas as pd


def prop_sim(trades, risk_pct, size=10_000, target=0.10, max_loss=0.10, daily=0.05, max_days=None):
    """FTMO-achtige challenge: start op elke handelsdag, kijk of je eerst +target haalt of een limiet raakt.
    trades: lijst (tijd, R). Risico per trade = risk_pct van de startbalans."""
    if not trades:
        return dict(starts=0, passed=0, failed=0, open=0)
    df = pd.DataFrame(trades, columns=["t", "R"]).sort_values("t")
    days = sorted({t.date() for t in df["t"]})
    res = {"passed": 0, "failed": 0, "open": 0, "days_to_pass": []}
    for d0 in days:
        bal, day, day_start = size, None, size
        out = "open"
        for t, r in df[df["t"].dt.date >= d0].itertuples(index=False):
            if t.date() != day:
                day, day_start = t.date(), bal
            bal += r * risk_pct * size
            if bal <= size * (1 - max_loss) or bal <= day_start - daily * size:
                out = "failed"
                break
            if bal >= size * (1 + target):
                out = "passed"
                res["days_to_pass"].append((t.date() - d0).days)
                break
        res[out] += 1
    res["starts"] = len(days)
    res["median_days"] = float(np.median(res["days_to_pass"])) if res["days_to_pass"] else None
    del res["days_to_pass"]
    return res
