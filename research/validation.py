"""Chronologische validatie: train/validatie/eindtest splitsen, walk-forward en de selectiepoort.

Regel: alles wat een keuze bepaalt, gebruikt alleen data van vóór de periode waarop die keuze getest wordt.
"""
import numpy as np
import pandas as pd

from backtesting.metrics import block_bootstrap

TRAIN_D, TEST_D = 240, 60     # walk-forward van het strategielab
MIN_TRAIN = 10                # minimaal aantal trades om een variant op trainingsdata te mogen kiezen
MIN_OOS = 30                  # minimaal aantal trades op nieuwe data voordat het lab een strategie mag kiezen


def walk_forward(by_variant, start, end):
    """Per periode van TEST_D dagen: de variant met de beste gemiddelde R op de TRAIN_D dagen ervoor."""
    oos, picks = [], []
    t = start + pd.Timedelta(days=TRAIN_D)
    while t < end:
        best, best_mean = None, None
        for vk, trades in by_variant.items():
            tr = [x["R"] for x in trades if t - pd.Timedelta(days=TRAIN_D) <= x["t"] < t]
            if len(tr) >= MIN_TRAIN and (best_mean is None or np.mean(tr) > best_mean):
                best, best_mean = vk, float(np.mean(tr))
        if best is not None:
            oos += [x for x in by_variant[best] if t <= x["t"] < t + pd.Timedelta(days=TEST_D)]
        picks.append(dict(van=t.date().isoformat(), variant=best))
        t += pd.Timedelta(days=TEST_D)
    return sorted(oos, key=lambda x: x["t"]), picks


def current_variant(by_variant, end):
    best, best_mean = None, None
    for vk, trades in by_variant.items():
        tr = [x["R"] for x in trades if end - pd.Timedelta(days=TRAIN_D) <= x["t"]]
        if len(tr) >= MIN_TRAIN and (best_mean is None or np.mean(tr) > best_mean):
            best, best_mean = vk, float(np.mean(tr))
    return best


def split(trades, val_start, hold):
    """Chronologisch: train < val_start <= validatie < hold <= eindtest."""
    tr = [x for x in trades if x["t"] < val_start]
    va = [x for x in trades if val_start <= x["t"] < hold]
    ho = [x for x in trades if x["t"] >= hold]
    return tr, va, ho


def split_by_date(rows, cut, key="t"):
    """Twee lijsten: vóór en vanaf `cut` (ISO-tekst of Timestamp), op volgorde van tijd."""
    rows = sorted(rows, key=lambda r: r[key])
    return [r for r in rows if r[key] < cut], [r for r in rows if r[key] >= cut]


def gate(tr, va, dsr):
    """De vooraf vastgelegde selectiepoort. Geeft (geslaagd, redenen-waarom-niet)."""
    why = []
    if len(va) < 30:
        why.append(f"P1: {len(va)} validatietrades (< 30)")
    ci = block_bootstrap(va, key="R15")
    m15 = np.mean([x["R15"] for x in va]) if va else -1
    if not (m15 > 0 and ci and ci[1] > 0):
        why.append(f"P2: validatie bij 1,5x kosten {m15:+.3f}R, ondergrens {ci[1] if ci else float('nan'):+.3f}R")
    if not tr or np.mean([x["R"] for x in tr]) <= 0:
        why.append(f"P3: train {np.mean([x['R'] for x in tr]) if tr else float('nan'):+.3f}R")
    if dsr < 0.95:
        why.append(f"P4: Deflated Sharpe {dsr:.2f} (< 0,95)")
    top = sorted((x["R"] for x in va), reverse=True)
    if len(top) <= 10 or np.mean(top[5:]) <= 0:
        why.append("P5: zonder de 5 beste validatietrades niet positief")
    return not why, why
