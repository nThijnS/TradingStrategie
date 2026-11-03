#!/bin/bash
# Oude naam, blijft werken: start MarketPilot (zie "Start MarketPilot.command").
cd "$(dirname "$0")"
exec "./Start MarketPilot.command" "$@"
