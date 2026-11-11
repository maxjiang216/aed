#!/usr/bin/env python3
"""Download raw source files into raw/ (gitignored). Safe to re-run; skips files present.

Wikipedia pages are fetched lazily by wiki_president.py into raw/wiki/.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RAW  # noqa: E402

DATAVERSE = "https://dataverse.harvard.edu/api/access/datafile/{id}?format=original"

# Harvard Dataverse file ids (dataset DOI in comments). Bump ids when a dataset is re-versioned.
FILES = {
    "medsl_president_1976_2024.csv": 13887042,  # doi:10.7910/DVN/42MVDX
    "medsl_senate_1976_2024.csv": 13887039,     # doi:10.7910/DVN/PEJ5QU
    "codebook_president.md": 7241480,
    "codebook_senate.md": 6708560,
    "algara_pres_county.Rdata": 5028532,        # doi:10.7910/DVN/DGUMFI
    "algara_senate_county.Rdata": 5028534,
    "algara_gov_county.Rdata": 5028535,
    "algara_manual.pdf": 5028533,
}


# Congressional district shapes: Lewis et al. (UCLA) for the 95th-114th Congress,
# Census cartographic boundaries after that. Used by build_district_shapes.mjs.
DISTRICT_URLS = {
    **{f"districts{c:03d}.zip": f"https://cdmaps.polisci.ucla.edu/shp/districts{c:03d}.zip" for c in range(95, 115)},
    **{f"cb_{y}_us_cd{c}_500k.zip": f"https://www2.census.gov/geo/tiger/GENZ{y}/shp/cb_{y}_us_cd{c}_500k.zip"
       for y, c in [(2017, 115), (2018, 116), (2022, 118), (2024, 119)]},
}

# Behind a Dataverse guestbook form: download by hand from the DOI page.
MANUAL = {
    "medsl_house_1976_2024.csv": "U.S. House 1976-2024, doi:10.7910/DVN/IG0UN2",
    "medsl_countypres_2000_2024.csv": "County Presidential Returns 2000-2024, doi:10.7910/DVN/VOQCHQ (optional)",
}


def _get(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "aed-data-build/0.1"})
    dest.write_bytes(urllib.request.urlopen(req, timeout=900).read())


def main() -> None:
    RAW.mkdir(exist_ok=True)
    (RAW / "districts").mkdir(exist_ok=True)
    for name, url in DISTRICT_URLS.items():
        dest = RAW / "districts" / name
        if not (dest.exists() and dest.stat().st_size > 0):
            print(f"get  districts/{name}")
            _get(url, dest)
    for name, fid in FILES.items():
        dest = RAW / name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"have {name}")
            continue
        print(f"get  {name}")
        _get(DATAVERSE.format(id=fid), dest)
    for name, what in MANUAL.items():
        if not (RAW / name).exists():
            print(f"MANUAL raw/{name}: {what}")


if __name__ == "__main__":
    main()
