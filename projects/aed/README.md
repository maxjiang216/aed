# American Elections Database

Interactive maps of U.S. presidential, Senate and governor results by state since 1828
(president by county since 2000) and House results by congressional district since 1976. Live at https://aed-ruby.vercel.app/.

Margin is always **(1st − 2nd) ÷ all votes cast**, so third-party votes shrink it. Colors use
four stops per party (tilt, lean at 5%, likely at 10%, solid at 20%) with linear
interpolation between them.

## Run the site

```bash
npm install
npm run dev      # http://localhost:5173
npm test         # model + full-data render tests
npm run build    # static site in dist/ (what Vercel runs)
```

Stack: Vite + React + TypeScript; maps from `us-atlas` (Census shapes, pre-projected)
drawn with `d3-geo`. The URL hash holds the view, e.g. `#/president/state/1968/result`.

## Data

The site only reads the committed JSON in `public/data/`. To rebuild it from the sources:

```bash
python3 -m venv .venv && .venv/bin/pip install -r scripts/ingest/requirements.txt
make data
```

| office    | years      | source |
|-----------|------------|--------|
| president | 1976–2024  | MIT Election Data + Science Lab (doi:10.7910/DVN/42MVDX) |
| president | 1828–1972  | Wikipedia "results by state" tables, checked against Algara & Amlani |
| president, county | 2000–2020 | MEDSL county returns (`MIT/`) |
| senate    | 1976–2024  | MEDSL (doi:10.7910/DVN/PEJ5QU), incl. specials and runoffs |
| senate    | 1908–1974  | Algara & Amlani county returns summed to state (doi:10.7910/DVN/DGUMFI) |
| governor  | 1959–2021  | hand-entered `elections/US_governor_state/` merged with Algara & Amlani |
| governor  | 1865–1958  | Algara & Amlani |
| house     | 1976–2024  | MEDSL U.S. House (doi:10.7910/DVN/IG0UN2), manual download, see below |

House district maps: Lewis, DeVine, Pritchett & Martis (UCLA, cdmaps.polisci.ucla.edu) for the
95th–114th Congress, Census cartographic boundary files for the 115th–119th; built by
`make shapes` into `public/data/house/shapes/`. States whose districts changed between two
elections are listed in `meta.json`; the map does not compare flip/shift/trend there.

Algara & Amlani name only the Democratic and Republican candidates; everything else is one
combined bloc. Races where that bloc places first or second are listed in
`data/statewide_report.md` and marked in the UI. Hand fixes go in `scripts/ingest/overrides.py`.

Manual downloads (Dataverse asks for a guestbook form): save the House file
(doi:10.7910/DVN/IG0UN2, `1976-2024-house.tab`) as `raw/medsl_house_1976_2024.csv`, and
optionally the 2000–2024 county file (doi:10.7910/DVN/VOQCHQ) as
`raw/medsl_countypres_2000_2024.csv`, then run `make data`. The House tab appears once
`public/data/house/<year>.json` exists.

Pipeline: `fetch_sources.py` (raw files into `raw/`) → `build_statewide.py`
(`data/statewide.json` + report) → `export_web.py` (`public/data/`).
