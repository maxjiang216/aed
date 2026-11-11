# Shortest-border districts

Congressional districts at census-block level with equal population that minimise total internal
border length (ignores the VRA, county lines and communities of interest), plus projections of
how they would vote and a citizen-apportionment counterfactual. Results are on the site at
`#/districts`. Running log of experiments and findings: [`NOTES.md`](NOTES.md).

## Setup

```bash
cd projects/districting
uv venv .venv && uv pip install --python .venv/bin/python -r requirements.txt   # also needs METIS/KaHIP libs
make                     # builds the C++ refiner (pybind11)
```

## Pipeline

```bash
python -m districting.cli IA                      # one state -> output/IA/
python -m districting.national run --seeds 8 --workers 4 --target-pct 0.001   # all states -> output/national/
python -m districting.project output/national     # 2020 presidential votes -> projection.json per state
python -m districting.citizen_apportion           # output/citizen/
make web                                          # site data -> ../../public/districting/
```

Census TIGER/Line and VEST downloads land in `data/` (~17 GB, ignored). Some analyses read the
AED project's MEDSL files from `../aed/raw/` and `../aed/MIT/`.
