"""2020 presidential votes on census blocks, from VEST precinct results.

VEST (Voting and Election Science Team), "2020 Precinct-Level Election Results",
Harvard Dataverse doi:10.7910/DVN/K7760H. Precinct shapefiles with G20PREDBID /
G20PRERTRU (Biden / Trump) vote columns.

Disaggregation: each block's representative point is matched to the precinct that
contains it (nearest precinct if none); a precinct's votes are split over its blocks
in proportion to block population (evenly if the matched blocks have no people).
Precincts that no block point falls in give their votes to the nearest block.
Statewide totals are preserved exactly.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

from .data import DATA_DIR
from .graph import EQUAL_AREA_CRS

DATASET = "doi:10.7910/DVN/K7760H"
API = "https://dataverse.harvard.edu/api"
DEM, REP = "G20PREDBID", "G20PRERTRU"
CACHE = DATA_DIR.parent / "votes"


def _file_ids() -> dict[str, int]:
    f = CACHE / "vest_files.json"
    if not f.exists():
        CACHE.mkdir(parents=True, exist_ok=True)
        # curl, not urllib: Dataverse returns 403 to Python's urllib user agent.
        raw = subprocess.run(["curl", "-sfL", "--retry", "3",
                              f"{API}/datasets/:persistentId/?persistentId={DATASET}"],
                             check=True, capture_output=True).stdout
        files = json.loads(raw)["data"]["latestVersion"]["files"]
        f.write_text(json.dumps({x["dataFile"]["filename"]: x["dataFile"]["id"] for x in files}, indent=1))
    return json.loads(f.read_text())


def load_precincts(fips: str, abbr: str) -> gpd.GeoDataFrame:
    name = f"{abbr.lower()}_2020.zip"
    dest = DATA_DIR / fips / "vest" / name
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        print(f"downloading VEST {name}")
        # Dataverse returns 403 to Python's urllib user agent; curl is accepted.
        part = dest.with_suffix(".part")
        subprocess.run(["curl", "-sfL", "--retry", "3", "-o", str(part),
                        f"{API}/access/datafile/{_file_ids()[name]}"], check=True)
        part.rename(dest)
    g = gpd.read_file(dest)
    missing = {DEM, REP} - set(g.columns)
    if missing:
        raise RuntimeError(f"{name}: missing columns {missing}; have {list(g.columns)}")
    return g[[DEM, REP, "geometry"]]


def block_votes(fips: str, abbr: str, blocks: gpd.GeoDataFrame) -> pd.DataFrame:
    """DataFrame aligned to `blocks` with float columns dem, rep."""
    cache = CACHE / f"{fips}.parquet"
    if cache.exists():
        v = pd.read_parquet(cache)
        if len(v) == len(blocks) and (v["GEOID20"].to_numpy() == blocks["GEOID20"].to_numpy()).all():
            return v
    prec = load_precincts(fips, abbr).to_crs(EQUAL_AREA_CRS).reset_index(drop=True)
    prec["geometry"] = prec.geometry.make_valid()
    pts = gpd.GeoDataFrame(geometry=blocks.geometry.representative_point(), crs=blocks.crs).to_crs(EQUAL_AREA_CRS)

    j = gpd.sjoin(pts, prec[["geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated()]
    pid = j["index_right"].to_numpy(dtype=np.float64, copy=True)
    miss = np.isnan(pid)
    if miss.any():  # block points outside every precinct (coast, gaps): nearest precinct
        near = gpd.sjoin_nearest(pts[miss], prec[["geometry"]], how="left")
        near = near[~near.index.duplicated()]
        pid[miss] = near["index_right"].to_numpy()
    pid = pid.astype(np.int64)

    pop = blocks["POP20"].to_numpy(np.float64)
    nprec = len(prec)
    prec_pop = np.bincount(pid, weights=pop, minlength=nprec)
    prec_nblk = np.bincount(pid, minlength=nprec)
    share = np.where(prec_pop[pid] > 0, pop / np.maximum(prec_pop[pid], 1), 1.0 / np.maximum(prec_nblk[pid], 1))

    out = pd.DataFrame({"GEOID20": blocks["GEOID20"].to_numpy()})
    for col, name in ((DEM, "dem"), (REP, "rep")):
        votes = prec[col].to_numpy(np.float64)
        out[name] = votes[pid] * share

    orphan = np.flatnonzero(prec_nblk == 0)  # precincts that no block point fell in
    if len(orphan):
        cent = gpd.GeoDataFrame(geometry=prec.geometry.iloc[orphan].representative_point(), crs=EQUAL_AREA_CRS)
        near = gpd.sjoin_nearest(cent, pts, how="left")
        near = near[~near.index.duplicated()]
        tgt = near["index_right"].to_numpy(np.int64)
        for col, name in ((DEM, "dem"), (REP, "rep")):
            col_vals = out[name].to_numpy(copy=True)
            np.add.at(col_vals, tgt, prec[col].to_numpy(np.float64)[orphan])
            out[name] = col_vals

    for col, name in ((DEM, "dem"), (REP, "rep")):
        assert abs(out[name].sum() - prec[col].sum()) < 1e-3 * max(1, prec[col].sum()), name
    CACHE.mkdir(parents=True, exist_ok=True)
    out.to_parquet(cache)
    return out
