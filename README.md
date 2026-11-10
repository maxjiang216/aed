# American Elections Database

Interactive maps of U.S. presidential, Senate and governor results by state since 1828
(president by county since 2000). Live at https://aed-ruby.vercel.app/.

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

Algara & Amlani name only the Democratic and Republican candidates; everything else is one
combined bloc. Races where that bloc places first or second are listed in
`data/statewide_report.md` and marked in the UI. Hand fixes go in `scripts/ingest/overrides.py`.

County 2024: the MEDSL 2000–2024 county file needs a guestbook form on Dataverse
(doi:10.7910/DVN/VOQCHQ). Download it manually to `raw/medsl_countypres_2000_2024.csv`
and run `make data`.

Pipeline: `fetch_sources.py` (raw files into `raw/`) → `build_statewide.py`
(`data/statewide.json` + report) → `export_web.py` (`public/data/`).
