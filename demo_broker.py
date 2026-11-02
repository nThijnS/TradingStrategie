#!/usr/bin/env python3
"""Oude naam, blijft werken voor de workflow. De orderuitvoering staat nu in broker.py (demo standaard, live alleen
na opt-in); de risicoregels in risico.py en de Capital.com-koppeling in broker_capital.py.

De OANDA-koppeling is vervallen: die rekende met een aangenomen contractwaarde en kon het account niet
verifiëren. Capital.com is de enige ondersteunde broker.

    python demo_broker.py --status status.json --uit demo.json   (zelfde als python broker.py ...)
"""
from broker import main

if __name__ == "__main__":
    main()
