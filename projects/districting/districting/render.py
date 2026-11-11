"""Water-aware maps: districts drawn from land blocks only, water-only blocks in blue.

Census blocks cover each state's legal boundary, which runs through the Great Lakes
and out to sea; those areas are zero-population "water blocks" (ALAND20 == 0).
This re-renders from saved assignments, so it works on finished runs:

    python -m districting.render output/national/MI          # one state dir
    python -m districting.render output/national             # every state dir + national map
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd
import shapely

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from . import data, evaluate
from .graph import EQUAL_AREA_CRS

WATER = "#cfe3f3"
WATER_EDGE = "#9cc3e0"


MAJOR_WATER_KM2 = 50.0


def land_water(blocks: gpd.GeoDataFrame, min_km2: float = MAJOR_WATER_KM2):
    """Split blocks into land vs *major* water.

    Water-only blocks (ALAND20 == 0) are merged into connected water bodies; bodies of
    at least `min_km2` (Great Lakes, sea, big reservoirs) count as water. Smaller
    lakes and rivers are kept as land so they don't punch holes in the map."""
    wmask = blocks["ALAND20"].to_numpy() == 0
    if not wmask.any():
        return np.ones(len(blocks), bool), None
    wgeoms = blocks.geometry.values[wmask]
    parts = shapely.get_parts(shapely.coverage_union_all(wgeoms))
    areas = gpd.GeoSeries(parts, crs=blocks.crs).to_crs(EQUAL_AREA_CRS).area.to_numpy() / 1e6
    big = parts[areas >= min_km2]
    if len(big) == 0:
        return np.ones(len(blocks), bool), None
    tree = shapely.STRtree(big)
    pts = shapely.point_on_surface(wgeoms)
    hit = np.zeros(len(wgeoms), bool)
    hit[np.unique(tree.query(pts, predicate="within")[0])] = True
    major = np.zeros(len(blocks), bool)
    major[np.flatnonzero(wmask)[hit]] = True
    return ~major, shapely.union_all(big)


PALETTE = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f", "#edc948",
           "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac", "#86bcb6", "#d4a6c8"]


def neighbor_colors(gdf: gpd.GeoDataFrame) -> list[str]:
    """Greedy graph colouring so touching districts never share a colour."""
    geoms = gdf.geometry.values
    tree = shapely.STRtree(geoms)
    left, right = tree.query(geoms, predicate="intersects")
    nbrs = [set() for _ in geoms]
    for a, b in zip(left, right):
        if a != b:
            nbrs[a].add(b)
    order = sorted(range(len(geoms)), key=lambda i: -len(nbrs[i]))
    color = {}
    use = np.zeros(len(PALETTE), int)
    for i in order:
        taken = {color[j] for j in nbrs[i] if j in color}
        free = [c for c in range(len(PALETTE)) if c not in taken]
        c = min(free, key=lambda c: use[c]) if free else int(np.argmin(use))
        color[i] = c
        use[c] += 1
    return [PALETTE[color[i]] for i in range(len(geoms))]


def land_districts(blocks, assign, land, k) -> gpd.GeoDataFrame:
    geoms = blocks.geometry.values
    out = [shapely.coverage_union_all(geoms[(assign == d) & land]) for d in range(k)]
    return gpd.GeoDataFrame({"district": np.arange(k) + 1}, geometry=out, crs=blocks.crs)


def render_state(state_dir: Path) -> list[Path]:
    abbr = state_dir.name
    fips, _, k = data.resolve_state(abbr)
    mfile = state_dir / "metrics.json"
    if not mfile.exists():
        return []
    metrics = json.loads(mfile.read_text())
    blocks = data.load_blocks(fips)
    land, water = land_water(blocks)

    plans = {}
    for name in metrics:
        if name.startswith("enacted"):
            plans[name] = evaluate.enacted_assignment(blocks, data.load_enacted(fips))
        else:
            f = state_dir / f"{name}_assignment.csv"
            a = pd.read_csv(f, dtype={"GEOID20": str})
            # Blocks missing from the assignment (dropped water blocks) get -1 = undrawn.
            plans[name] = (a.set_index("GEOID20")["district"].reindex(blocks.GEOID20)
                           .fillna(0).astype(int).to_numpy() - 1)

    shapes = {name: land_districts(blocks, a, land, k) for name, a in plans.items()}
    written = []
    for name, gdf in shapes.items():
        if not name.startswith("enacted"):
            p = state_dir / f"{name}_districts_land.geojson"
            gdf.to_file(p, driver="GeoJSON")
            written.append(p)

    water_gs = gpd.GeoSeries([water], crs=blocks.crs).to_crs(EQUAL_AREA_CRS) if water is not None else None
    n = len(shapes)
    fig, axes = plt.subplots(1, n, figsize=(6.5 * n, 6))
    axes = np.atleast_1d(axes)
    for ax, (name, gdf) in zip(axes, shapes.items()):
        if water_gs is not None:
            water_gs.plot(ax=ax, color=WATER, edgecolor=WATER_EDGE, linewidth=0.3)
        gdf.to_crs(EQUAL_AREA_CRS).plot(ax=ax, color=neighbor_colors(gdf), edgecolor="black", linewidth=0.6)
        m = metrics[name]
        ax.set_title(f"{name}\nborder {m['internal_border_km']:.0f} km · PP mean "
                     f"{m['polsby_popper_mean']:.3f} · spread {m['pop_spread']} · "
                     f"{m['split_counties']} split counties", fontsize=9)
        ax.set_axis_off()
    fig.suptitle(f"{abbr}: {k} districts (land only; blue = water inside state boundary)")
    fig.tight_layout(rect=(0, 0, 1, 0.94))
    p = state_dir / "map_land.png"
    fig.savefig(p, dpi=150)
    plt.close(fig)
    written.append(p)
    return written


def render_national(root: Path) -> Path | None:
    shapes, waters = [], []
    for d in sorted(root.iterdir()):
        if not d.is_dir() or d.name == "HI":
            continue
        m = d / "metrics.json"
        if not m.exists():
            continue
        metrics = json.loads(m.read_text())
        algo = {n: v for n, v in metrics.items() if not n.startswith(("enacted", "polished-enacted"))}
        if not algo:
            continue
        best = min(algo, key=lambda n: (algo[n]["pop_spread"] > algo[n].get("target", 1),
                                        algo[n]["internal_border_km"]))
        f = d / f"{best}_districts_land.geojson"
        if not f.exists():
            continue
        g = gpd.read_file(f)
        g["state"] = d.name
        shapes.append(g)
        fips, _, _ = data.resolve_state(d.name)
        blocks = data.load_blocks(fips)
        _, water = land_water(blocks)
        if water is not None:
            waters.append(water)
    if not shapes:
        return None
    allg = pd.concat(shapes, ignore_index=True).to_crs(EQUAL_AREA_CRS)
    fig, ax = plt.subplots(figsize=(20, 12))
    if waters:
        gpd.GeoSeries(waters, crs=shapes[0].crs).to_crs(EQUAL_AREA_CRS).plot(
            ax=ax, color=WATER, edgecolor=WATER_EDGE, linewidth=0.2)
    allg.plot(ax=ax, color=neighbor_colors(allg), edgecolor="black", linewidth=0.25)
    allg.dissolve("state").boundary.plot(ax=ax, color="black", linewidth=0.9)
    ax.set_axis_off()
    ax.set_title("Min-border, equal-population congressional districts (2020 census blocks, land only), "
                 "contiguous US — single-district states not shown", fontsize=13)
    p = root / "national_map_land.png"
    fig.savefig(p, dpi=140, bbox_inches="tight")
    plt.close(fig)
    return p


def main():
    target = Path(sys.argv[1])
    if (target / "metrics.json").exists():
        for p in render_state(target):
            print(p)
        return
    for d in sorted(target.iterdir()):
        if d.is_dir() and (d / "metrics.json").exists():
            for p in render_state(d):
                print(p)
    print(render_national(target))


if __name__ == "__main__":
    main()
