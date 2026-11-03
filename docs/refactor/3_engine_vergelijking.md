# Engine-vergelijking ICT (HistData, oud tegenover nieuw)

Gemaakt met `python -m research.engine_vergelijking`. Protocol: NY AM, max 1 trade per dag, kosten zoals in `core/markets.py`, R netto, **2025 / 2026**. "oud" = de echte oude code (golden-opname vóór de refactor).

De ICT-detectie zelf is identiek (zelfde setups, zie `tests/test_golden.py`); alleen de afhandeling van de trade verschilt.

## Leren (5m-candles, Yahoo-formaat)

| markt | variant | doel | oud | oud-nagebootst | + vulcandle | + 5 uur | **nieuw** |
|---|---|---|---|---|---|---|---|
| NQ | basis | 1.0 | +0.2 / -4.5 | +0.2 / -4.9 | +0.2 / -6.9 | +0.2 / -6.6 | **+0.2 / -6.6** |
| NQ | basis | 1.5 | +0.5 / -7.4 | +0.5 / -7.8 | +0.5 / -7.8 | +0.9 / -6.8 | **+0.9 / -6.8** |
| NQ | basis | 2.0 | +0.0 / -9.9 | +0.0 / -10.3 | -3.0 / -10.3 | -2.6 / -9.4 | **-2.6 / -9.4** |
| NQ | basis | DOL | -5.1 / -7.3 | -5.1 / -7.7 | -5.1 / -7.7 | -4.3 / -7.1 | **-4.8 / -8.2** |
| NQ | strenger | 1.0 | +11.9 / +1.0 | +11.9 / +0.9 | +11.9 / -1.1 | +11.8 / -0.9 | **+11.8 / -0.9** |
| NQ | strenger | 1.5 | +10.6 / -2.0 | +10.7 / -2.0 | +10.7 / -2.0 | +11.0 / -1.1 | **+11.0 / -1.1** |
| NQ | strenger | 2.0 | +9.7 / -4.4 | +9.7 / -4.4 | +6.7 / -4.4 | +7.0 / -3.7 | **+7.0 / -3.7** |
| NQ | strenger | DOL | +5.9 / -1.8 | +5.9 / -1.8 | +5.9 / -1.8 | +6.7 / -1.4 | **+7.1 / -2.4** |
| EURUSD | basis | 1.0 | -12.2 / +3.5 | -12.2 / +3.5 | -14.0 / -2.5 | -14.1 / -2.3 | **-14.1 / -2.3** |
| EURUSD | basis | 1.5 | -12.7 / +0.9 | -12.7 / +0.9 | -12.7 / +0.9 | -12.8 / +0.9 | **-12.8 / +0.9** |
| EURUSD | basis | 2.0 | -15.8 / -0.2 | -15.8 / -0.2 | -15.8 / -0.2 | -15.1 / -0.2 | **-15.1 / -0.2** |
| EURUSD | basis | DOL | -10.2 / +1.2 | -10.2 / +1.2 | -10.2 / -1.0 | -10.3 / -0.4 | **-10.3 / -1.4** |
| EURUSD | strenger | 1.0 | -8.9 / +1.0 | -8.9 / +1.0 | -10.8 / -3.0 | -10.8 / -2.8 | **-10.8 / -2.8** |
| EURUSD | strenger | 1.5 | -10.1 / +0.0 | -10.1 / +0.1 | -10.1 / +0.1 | -10.2 / +0.1 | **-10.2 / +0.1** |
| EURUSD | strenger | 2.0 | -13.7 / -0.5 | -13.7 / -0.5 | -13.7 / -0.5 | -13.0 / -0.6 | **-13.0 / -0.6** |
| EURUSD | strenger | DOL | -7.3 / +0.8 | -7.3 / +0.8 | -7.3 / -1.4 | -7.4 / -0.9 | **-7.4 / -1.9** |
| GOUD | basis | 1.0 | +0.4 / -2.3 | +0.4 / -2.3 | +0.4 / -2.3 | +0.3 / -2.3 | **+0.3 / -2.3** |
| GOUD | basis | 1.5 | +4.6 / +1.7 | +4.6 / +1.6 | +4.6 / +1.6 | +4.9 / +1.5 | **+4.9 / +1.5** |
| GOUD | basis | 2.0 | +9.1 / +4.8 | +9.1 / +4.8 | +9.1 / +4.8 | +9.5 / +4.7 | **+9.5 / +4.7** |
| GOUD | basis | DOL | +7.2 / +2.3 | +7.2 / +2.3 | +7.2 / +2.3 | +7.3 / +2.1 | **+7.3 / +1.1** |
| GOUD | strenger | 1.0 | +0.4 / -3.2 | +0.4 / -3.2 | +0.4 / -3.2 | +0.5 / -3.2 | **+0.5 / -3.2** |
| GOUD | strenger | 1.5 | +2.6 / -0.2 | +2.6 / -0.2 | +2.6 / -0.2 | +3.2 / -0.4 | **+3.2 / -0.4** |
| GOUD | strenger | 2.0 | +6.6 / +2.8 | +6.6 / +2.8 | +6.6 / +2.8 | +7.2 / +2.6 | **+7.2 / +2.6** |
| GOUD | strenger | DOL | +3.2 / +1.0 | +3.2 / +1.0 | +3.2 / +1.0 | +3.5 / +0.7 | **+3.5 / -0.3** |

## HistData-backtest (1m-candles)

| markt | variant | doel | oud | oud-nagebootst | + vulcandle | + 5 uur | **nieuw** |
|---|---|---|---|---|---|---|---|
| NQ | basis | 1.0 | +0.3 / -6.7 | +0.3 / -7.1 | +0.3 / -7.1 | +0.2 / -7.0 | **+0.2 / -7.0** |
| NQ | basis | 1.5 | +1.4 / -7.3 | +1.4 / -7.7 | +1.4 / -7.7 | +1.6 / -7.4 | **+1.6 / -7.4** |
| NQ | basis | 2.0 | -2.1 / -9.7 | -6.6 / -10.2 | -6.6 / -10.2 | -6.3 / -9.8 | **-6.3 / -9.8** |
| NQ | basis | DOL | -4.8 / -8.9 | -4.8 / -9.3 | -4.8 / -9.3 | -3.9 / -9.7 | **-3.9 / -9.7** |
| NQ | strenger | 1.0 | +12.0 / -1.2 | +12.0 / -1.2 | +12.0 / -1.2 | +11.9 / -1.2 | **+11.9 / -1.2** |
| NQ | strenger | 1.5 | +11.4 / -1.8 | +11.4 / -1.8 | +11.4 / -1.8 | +11.7 / -1.4 | **+11.7 / -1.4** |
| NQ | strenger | 2.0 | +7.5 / -4.3 | +3.0 / -4.3 | +3.0 / -4.3 | +3.2 / -3.8 | **+3.2 / -3.8** |
| NQ | strenger | DOL | +7.2 / -3.5 | +7.2 / -3.5 | +7.2 / -3.5 | +8.1 / -3.8 | **+8.1 / -3.8** |
| EURUSD | basis | 1.0 | -14.5 / -0.4 | -14.5 / -0.4 | -14.5 / -2.4 | -14.5 / -2.3 | **-14.5 / -2.3** |
| EURUSD | basis | 1.5 | -12.6 / +0.7 | -12.6 / +0.7 | -12.6 / +0.7 | -12.8 / +0.6 | **-12.8 / +0.6** |
| EURUSD | basis | 2.0 | -14.4 / -0.7 | -14.4 / -0.7 | -14.4 / -0.7 | -14.2 / -0.7 | **-14.2 / -0.7** |
| EURUSD | basis | DOL | -9.6 / -2.0 | -9.6 / -2.0 | -9.6 / -2.0 | -9.6 / -1.9 | **-9.6 / -1.9** |
| EURUSD | strenger | 1.0 | -11.3 / -2.9 | -11.3 / -2.9 | -11.3 / -2.9 | -11.3 / -2.8 | **-11.3 / -2.8** |
| EURUSD | strenger | 1.5 | -10.1 / +0.0 | -10.1 / +0.0 | -10.1 / +0.0 | -10.3 / -0.1 | **-10.3 / -0.1** |
| EURUSD | strenger | 2.0 | -12.4 / -0.9 | -12.4 / -0.9 | -12.4 / -0.9 | -12.2 / -1.0 | **-12.2 / -1.0** |
| EURUSD | strenger | DOL | -6.8 / -2.3 | -6.8 / -2.3 | -6.8 / -2.3 | -6.7 / -2.2 | **-6.7 / -2.2** |
| GOUD | basis | 1.0 | +0.6 / -0.2 | +0.6 / -0.2 | +0.6 / -2.2 | +0.4 / -2.2 | **+0.4 / -2.2** |
| GOUD | basis | 1.5 | +4.8 / +1.4 | +4.8 / +1.4 | +4.8 / +1.4 | +4.5 / +1.4 | **+4.5 / +1.4** |
| GOUD | basis | 2.0 | +9.4 / +4.6 | +9.4 / +4.6 | +9.4 / +4.6 | +9.1 / +4.6 | **+9.1 / +4.6** |
| GOUD | basis | DOL | +7.4 / +1.1 | +7.4 / +1.1 | +7.4 / +1.1 | +7.3 / +1.0 | **+7.3 / +1.0** |
| GOUD | strenger | 1.0 | +0.7 / -1.2 | +0.7 / -1.2 | +0.7 / -3.2 | +0.6 / -3.2 | **+0.6 / -3.2** |
| GOUD | strenger | 1.5 | +3.1 / -0.6 | +3.0 / -0.6 | +3.0 / -0.6 | +2.8 / -0.6 | **+2.8 / -0.6** |
| GOUD | strenger | 2.0 | +7.1 / +2.4 | +7.0 / +2.4 | +7.0 / +2.4 | +6.8 / +2.4 | **+6.8 / +2.4** |
| GOUD | strenger | DOL | +3.6 / -0.3 | +3.6 / -0.3 | +3.6 / -0.3 | +3.5 / -0.4 | **+3.5 / -0.4** |

## Uitleg van de correcties

1. **Doel in de vulcandle telt niet meer.** Bij een limietorder op 5m-candles is niet te zien of het doel vóór of ná de vulling werd geraakt. De oude code telde dat als winst (optimistisch); de engine telt alleen de stop in die candle.
2. **Precies 5 uur.** De oude leren-simulatie nam de candle op +5:00 nog mee (5u05m); de oude 1m-backtest sloot pas op de close van de candle op of na 5 uur en 16:00 (een minuut te laat, zonder stopcontrole). Nu sluit een trade op de close van de laatste candle die vóór of op de deadline eindigt.
3. **DOL zonder liquiditeit = 1R (zoals de app).** Het leren rekende dan met 2R, terwijl de app met `tp_r` (1R) handelt. Het leren beoordeelde dus andere trades dan de app werkelijk neemt.
4. **Open voorbij de stop/het doel** sluit op de open (gat). Op 1m/5m binnen een sessie komt dat zelden voor. Het grootste geval: NQ basis/strenger 2R in 2025 (−4,5R in één trade). Op 10 oktober 2025 (tariefcrash) ontbreekt in de HistData de candle van 10:58; de koers viel in die minuut ruim door de stop. De oude code nam de stopprijs (optimistisch), de engine de open van 10:59 (voorzichtig). De echte vulling ligt daartussen.

Verder is er niets veranderd: zelfde setups, zelfde kosten, zelfde selectie. Het verschil tussen "oud" en "oud-nagebootst" laat zien hoe goed de engine de oude regels kan nabootsen (resterende verschillen: punt 4 en de zoekgrens van de 1m-vulling).
