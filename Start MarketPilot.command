#!/bin/bash
# Dubbelklik om MarketPilot te starten. Laat dit venster open; sluiten = stoppen.
cd "$(dirname "$0")"
if ! ./.venv/bin/python -c "import yfinance, pandas" 2>/dev/null; then
    echo "Eerste keer: benodigde onderdelen installeren..."
    rm -rf .venv
    python3 -m venv .venv && ./.venv/bin/pip install -q yfinance pandas
fi
# caffeinate: Mac valt niet in slaap zolang dit draait (behalve als je het deksel dichtdoet)
# tradingstrategie.py is de vaste (technische) naam van de meldingen-app; zie docs/MARKETPILOT.md
caffeinate -i ./.venv/bin/python -W ignore tradingstrategie.py "$@"
