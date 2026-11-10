# Rebuild data from raw sources (needs .venv: python3 -m venv .venv && .venv/bin/pip install -r scripts/ingest/requirements.txt).
.PHONY: data shapes
data:
	.venv/bin/python scripts/ingest/fetch_sources.py
	.venv/bin/python scripts/ingest/build_statewide.py
	.venv/bin/python scripts/ingest/export_web.py

# District maps (slow-ish, ~1 min; only needed when shapes or simplification change).
shapes:
	node scripts/ingest/build_district_shapes.mjs
