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


def main() -> None:
    RAW.mkdir(exist_ok=True)
    for name, fid in FILES.items():
        dest = RAW / name
        if dest.exists() and dest.stat().st_size > 0:
            print(f"have {name}")
            continue
        print(f"get  {name}")
        req = urllib.request.Request(DATAVERSE.format(id=fid), headers={"User-Agent": "aed-data-build/0.1"})
        dest.write_bytes(urllib.request.urlopen(req, timeout=300).read())


if __name__ == "__main__":
    main()
