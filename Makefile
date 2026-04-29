# Build map data (writes data/elections.json and data/elections.embed.js). Run from repo root.
.PHONY: maps
maps:
	python3 scripts/build_maps.py
