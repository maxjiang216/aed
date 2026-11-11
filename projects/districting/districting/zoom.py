"""Zoomed map: block outlines (faint) + district borders (bold) around a point.

    python -m districting.zoom IA output/IA/target_1/metis_assignment.csv --lon -93.62 --lat 41.59 --km 40
"""
import argparse

import geopandas as gpd
import matplotlib
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from shapely.geometry import Point

from . import data, evaluate
from .graph import EQUAL_AREA_CRS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("state"); ap.add_argument("assignment")
    ap.add_argument("--lon", type=float, required=True); ap.add_argument("--lat", type=float, required=True)
    ap.add_argument("--km", type=float, default=40, help="window width")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    fips, abbr, k = data.resolve_state(a.state)
    blocks = data.load_blocks(fips)
    assign = pd.read_csv(a.assignment, dtype={"GEOID20": str}).set_index("GEOID20").loc[blocks.GEOID20, "district"].to_numpy() - 1
    c = gpd.GeoSeries([Point(a.lon, a.lat)], crs=4326).to_crs(EQUAL_AREA_CRS).iloc[0]
    h = a.km * 500
    win = (c.x - h, c.y - h, c.x + h, c.y + h)
    bp = blocks.to_crs(EQUAL_AREA_CRS)
    sub = bp.cx[win[0]:win[2], win[1]:win[3]].copy()
    sub["district"] = assign[sub.index]
    dist = evaluate.dissolve(blocks, assign, k).to_crs(EQUAL_AREA_CRS)
    fig, ax = plt.subplots(figsize=(10, 10))
    sub.plot(ax=ax, column="district", cmap="tab20", categorical=True, alpha=0.45, edgecolor="grey", linewidth=0.15)
    dist.boundary.plot(ax=ax, color="black", linewidth=1.6)
    ax.set_xlim(win[0], win[2]); ax.set_ylim(win[1], win[3]); ax.set_axis_off()
    ax.set_title(f"{abbr} — {a.km:.0f} km window at ({a.lat}, {a.lon}); grey = census blocks, black = district border")
    out = a.out or a.assignment.replace("_assignment.csv", f"_zoom_{a.lat}_{a.lon}.png")
    fig.savefig(out, dpi=130, bbox_inches="tight"); print(out)


if __name__ == "__main__":
    main()
