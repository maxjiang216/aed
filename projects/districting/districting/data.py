"""Download Census TIGER/Line 2020 block shapefiles (with PL 94-171 POP20) and
current congressional district shapes for comparison."""

from __future__ import annotations

import urllib.request
from pathlib import Path

import geopandas as gpd

DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "raw"

BLOCKS_URL = "https://www2.census.gov/geo/tiger/TIGER2020/TABBLOCK20/tl_2020_{fips}_tabblock20.zip"
CD_URL = "https://www2.census.gov/geo/tiger/TIGER2024/CD/tl_2024_{fips}_cd119.zip"

# 2020 apportionment (118th/119th Congress). Single-district states omitted.
SEATS = {
    "01": ("AL", 7), "04": ("AZ", 9), "05": ("AR", 4), "06": ("CA", 52), "08": ("CO", 8),
    "09": ("CT", 5), "12": ("FL", 28), "13": ("GA", 14), "15": ("HI", 2), "16": ("ID", 2),
    "17": ("IL", 17), "18": ("IN", 9), "19": ("IA", 4), "20": ("KS", 4), "21": ("KY", 6),
    "22": ("LA", 6), "23": ("ME", 2), "24": ("MD", 8), "25": ("MA", 9), "26": ("MI", 13),
    "27": ("MN", 8), "28": ("MS", 4), "29": ("MO", 8), "30": ("MT", 2), "31": ("NE", 3),
    "32": ("NV", 4), "33": ("NH", 2), "34": ("NJ", 12), "35": ("NM", 3), "36": ("NY", 26),
    "37": ("NC", 14), "39": ("OH", 15), "40": ("OK", 5), "41": ("OR", 6), "42": ("PA", 17),
    "44": ("RI", 2), "45": ("SC", 7), "47": ("TN", 9), "48": ("TX", 38), "49": ("UT", 4),
    "51": ("VA", 11), "53": ("WA", 10), "54": ("WV", 2), "55": ("WI", 8),
}
ABBR_TO_FIPS = {abbr: fips for fips, (abbr, _) in SEATS.items()}


def resolve_state(state: str) -> tuple[str, str, int]:
    """Accept 'IA' or '19'; return (fips, abbr, seats)."""
    fips = ABBR_TO_FIPS.get(state.upper(), state.zfill(2))
    if fips not in SEATS:
        raise SystemExit(f"unknown or single-district state: {state}")
    abbr, seats = SEATS[fips]
    return fips, abbr, seats


def _download(url: str, dest: Path) -> Path:
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"downloading {url}")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(dest)
    return dest


def load_blocks(fips: str) -> gpd.GeoDataFrame:
    cache = DATA_DIR.parent / "blocks" / f"{fips}.parquet"
    if cache.exists():
        return gpd.read_parquet(cache)
    path = _download(BLOCKS_URL.format(fips=fips), DATA_DIR / fips / f"tl_2020_{fips}_tabblock20.zip")
    gdf = gpd.read_file(path, columns=["GEOID20", "COUNTYFP20", "POP20", "ALAND20", "AWATER20"])
    gdf = gdf.sort_values("GEOID20").reset_index(drop=True)
    gdf["POP20"] = gdf["POP20"].astype("int64")
    cache.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(cache)
    return gdf


def load_enacted(fips: str) -> gpd.GeoDataFrame:
    path = _download(CD_URL.format(fips=fips), DATA_DIR / fips / f"tl_2024_{fips}_cd119.zip")
    return gpd.read_file(path)
