#!/bin/bash
# Dubbelklik om TradingStrategie te starten. Laat dit venster open; sluiten = stoppen.
cd "$(dirname "$0")"
if ! ./.venv/bin/python -c "import yfinance, pandas" 2>/dev/null; then
    echo "Eerste keer: benodigde onderdelen installeren..."
    rm -rf .venv
    python3 -m venv .venv && ./.venv/bin/pip install -q yfinance pandas
fi
# caffeinate: Mac valt niet in slaap zolang dit draait (behalve als je het deksel dichtdoet)
caffeinate -i ./.venv/bin/python -W ignore tradingstrategie.py "$@"

