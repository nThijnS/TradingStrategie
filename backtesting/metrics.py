"""Statistiek over trades. Eén plek voor backtests, lab, leren en onderzoek.

basic_stats   R-reeks -> aantal, win%, gemiddelde, totaal, profit factor, max drawdown (HistData-backtests)
lab_stats     trades -> de statistiek van lab.json (het dashboard leest precies deze velden)
block_bootstrap, sharpe, deflated_sharpe, pbo_cscv   onderzoek (overfitting en onzekerheid)
"""
import itertools
import math

import numpy as np
import pandas as pd

Z = 1.0                                       # ondergrens = gemiddelde - Z standaardfouten
RNG = np.random.default_rng(20261102)         # vaste seed: bootstrap-uitkomsten zijn reproduceerbaar


def basic_stats(rs):
    rs = np.array(rs)
    if len(rs) == 0:
        return dict(n=0, win=0, avgR=0, totR=0, pf=0, maxDD=0)
    eq = np.cumsum(rs)
    dd = (np.maximum.accumulate(np.concatenate([[0], eq]))[1:] - eq).max()
    gains, losses = rs[rs > 0].sum(), -rs[rs < 0].sum()
    return dict(n=len(rs), win=(rs > 0).mean(), avgR=rs.mean(), totR=rs.sum(),
                pf=gains / losses if losses > 0 else 99, maxDD=dd)


def lab_stats(trades, full=True):
    R = np.array([t["R"] for t in trades], dtype=float)
    n = len(R)
    if n == 0:
        return dict(n=0)
    wins, losses = R[R > 0], R[R <= 0]
    eq = np.cumsum(R)
    dd = eq - np.maximum.accumulate(np.concatenate([[0.0], eq]))[1:]
    se = float(R.std(ddof=1) / math.sqrt(n)) if n > 1 else float("nan")
    gross = [t["bruto"] for t in trades if t["bruto"] is not None]
    s = dict(n=n, win=round(float((R > 0).mean()), 3), gem_winst=round(float(wins.mean()), 3) if len(wins) else 0.0,
             gem_verlies=round(float(losses.mean()), 3) if len(losses) else 0.0, expectancy=round(float(R.mean()), 3),
             pf=round(float(wins.sum() / -losses.sum()), 2) if losses.sum() < 0 else None,
             netto=round(float(R.sum()), 2), bruto=round(float(sum(gross)), 2) if len(gross) == n else None,
             max_dd=round(float(-dd.min()), 2), gem_rr=round(float(np.mean([t["rr"] for t in trades])), 2),
             se=round(se, 3) if np.isfinite(se) else None,
             ondergrens=round(float(R.mean() - Z * se), 3) if np.isfinite(se) else None,
             ci95=[round(float(R.mean() - 1.96 * se), 3), round(float(R.mean() + 1.96 * se), 3)] if np.isfinite(se) else None,
             t_stat=round(float(R.mean() / se), 2) if np.isfinite(se) and se > 0 else None,
             van=trades[0]["t"].isoformat(), tot=trades[-1]["t"].isoformat())
    if full:
        month, reg = {}, {}
        for t in trades:
            month.setdefault(t["t"].strftime("%Y-%m"), []).append(t["R"])
            for k in (t["trend"], t["vol"]):
                reg.setdefault(k, []).append(t["R"])
        s["per_maand"] = {k: [len(v), round(sum(v), 2)] for k, v in sorted(month.items())}
        s["per_conditie"] = {k: [len(v), round(sum(v), 2), round(float(np.mean(v)), 3)] for k, v in reg.items()}
        s["trades"] = [[int(t["t"].timestamp()), round(t["R"], 3)] for t in trades]
    return s


def block_bootstrap(trades, key="R", block_weeks=4, n=2000, rng=None):
    """Onzekerheid van de gemiddelde R per trade met weekblokken (trades die dicht bij elkaar liggen hangen samen)."""
    if len(trades) < 5:
        return None
    wk = pd.Series([x[key] for x in trades], index=pd.DatetimeIndex([x["t"] for x in trades])).groupby(pd.Grouper(freq="W"))
    sums, cnts = wk.sum().to_numpy(), wk.count().to_numpy()
    W = len(sums)
    if W < 2 * block_weeks:
        return None
    nb = math.ceil(W / block_weeks)
    starts = (rng or RNG).integers(0, W - block_weeks + 1, size=(n, nb))
    idx = (starts[:, :, None] + np.arange(block_weeks)).reshape(n, -1)[:, :W]
    s, c = sums[idx].sum(1), cnts[idx].sum(1)
    means = s[c > 0] / c[c > 0]
    return [float(np.quantile(means, 0.025)), float(np.quantile(means, 0.05)), float(np.quantile(means, 0.975))]


def sharpe(R):
    R = np.asarray(R, float)
    return float(R.mean() / R.std(ddof=1)) if len(R) > 2 and R.std(ddof=1) > 0 else 0.0


def deflated_sharpe(R, n_trials):
    """Deflated Sharpe Ratio (Bailey & López de Prado, 2014): kans dat de echte Sharpe > 0 is, na correctie voor
    het beste van N onafhankelijke proeven, scheefheid en dikke staarten. Sharpe per trade (niet geannualiseerd).
    Nulverdeling van de geschatte Sharpe: variantie 1/(T-1). (De spreiding over alle varianten zelf gebruiken
    werkt hier niet: varianten met weinig trades blazen die op.) N = aantal markt x strategiefamilie-combinaties,
    omdat varianten binnen één familie sterk samenhangen; dat is een benadering."""
    from statistics import NormalDist
    R = np.asarray(R, float)
    T, N = len(R), max(int(n_trials), 2)
    if T < 10:
        return 0.0
    sr = sharpe(R)
    nd = NormalDist()
    g = 0.5772156649
    sr0 = math.sqrt(1 / (T - 1)) * ((1 - g) * nd.inv_cdf(1 - 1 / N) + g * nd.inv_cdf(1 - 1 / (N * math.e)))
    z = (R - R.mean()) / (R.std(ddof=1) or 1)
    skew, kurt = float(np.mean(z ** 3)), float(np.mean(z ** 4))
    den = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr ** 2))
    return float(nd.cdf((sr - sr0) * math.sqrt(T - 1) / den))


def pbo_cscv(matrix, S=8):
    """Probability of Backtest Overfitting via CSCV: verdeel de tijd in S blokken; kies op elke helft de beste
    variant en kijk waar die op de andere helft eindigt. PBO = aandeel keren dat hij onder de mediaan valt."""
    M = np.asarray(matrix, float)               # rijen: tijdblokken, kolommen: varianten (som R per blok)
    T, N = M.shape
    if T < S or N < 2:
        return None
    blocks = np.array_split(np.arange(T), S)
    logits = []
    for combo in itertools.combinations(range(S), S // 2):
        is_idx = np.concatenate([blocks[i] for i in combo])
        os_idx = np.concatenate([blocks[i] for i in range(S) if i not in combo])
        best = int(np.argmax(M[is_idx].sum(0)))
        rank = (M[os_idx].sum(0) < M[os_idx].sum(0)[best]).sum() + 0.5
        w = rank / N
        logits.append(math.log(w / (1 - w)))
    return float(np.mean(np.array(logits) <= 0))
