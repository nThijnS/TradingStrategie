"""Alle bestandspaden van TradingStrategie op één plek.

De bestanden blijven waar ze altijd stonden (in de hoofdmap van de repo): de lopende keten op GitHub haalt
config.json, learned.json, lab.json en NOODSTOP elke minuut op bij pad, en de website leest raw/main/lab.json.
Verplaatsen kan later door alleen dit bestand aan te passen (en de workflows). Zie storage/MANIFEST.md.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# Instellingen (door de eigenaar beheerd)
CONFIG = ROOT / "config.json"                 # schakelaars, broker-modus, live-limieten
NTFY_TOPIC_FILE = ROOT / "ntfy_topic.txt"     # lokaal, git-ignored
NOODSTOP = ROOT / "NOODSTOP"

# Leren (ICT): geschreven door learning/ict.py, dagelijks gecommit door workflow Leren
LEARNED = ROOT / "learned.json"
LEREN_MEMORY = ROOT / "leren_geheugen.json"
LEREN_HISTORY = ROOT / "leren_geschiedenis.json"
JOURNAL = ROOT / "journaal"

# Strategielab: geschreven door learning/lab.py
LAB = ROOT / "lab.json"
LAB_VERSIONS = ROOT / "lab_versies.json"
LAB_HISTORY = ROOT / "lab_geschiedenis.json"
LAB_TEST = ROOT / "lab_test.json"
CANDIDATES = ROOT / "kandidaten.json"      # door het systeem gegenereerde strategievarianten (learning/generator.py)

# Keten (alleen in de GitHub Actions-cache, niet in de repo)
SENT = ROOT / "verstuurd.json"
LOGBOOK = ROOT / "logboek.json"
SETUPS_LOG = ROOT / "setups.log"
BROKER_STATE = {"demo": ROOT / "demo_staat.json", "live": ROOT / "live_staat.json"}

# Dashboard (naar de branch "live")
STATUS = ROOT / "status.json"
LIVE_CACHE = ROOT / ".cache_live"

# Onderzoek
REPORTS = ROOT / "rapport"
EXPERIMENTS = REPORTS / "experimenten.jsonl"
INSTRUMENTS = REPORTS / "instrumenten.json"

# Historische data (lokaal, git-ignored)
DATA = ROOT / "data"
HISTDATA_RAW = DATA / "raw"
BACKUPS = ROOT / "backups"
