"""Side-by-side maps: enacted vs plans from a parameter sweep.

    python -m districting.compare_maps NC --sweep output/homog_sweep --param homog-rho

Writes two 1920x1080 images (laptop screen) per state, same grid positions in both:
  compare_<ST>_precinct.png  - precincts shaded by 2020 two-party vote, district borders in black
  compare_<ST>_districts.png - districts filled by their own two-party share
Grid shape is chosen per state to make the maps as large as possible.
Titles: true border length, R² (share of voter-level partisan variance between
districts), projected seats. Water handled as in render.py.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import TwoSlopeNorm

from . import data, evaluate, project, render, votes
from .graph import EQUAL_AREA_CRS

ROOT = Path(__file__).resolve().parent.parent
CMAP = "RdBu"
NORM = TwoSlopeNorm(vmin=0.2, vcenter=0.5, vmax=0.8)


def internal_borders(dist: gpd.GeoDataFrame) -> gpd.GeoSeries:
    """Lines shared by two districts (excludes coastline and state boundary)."""
    import shapely
    geoms = dist.geometry.values
    bnds = shapely.boundary(geoms)
    tree = shapely.STRtree(geoms)
    left, right = tree.query(geoms, predicate="intersects")
    lines = [shapely.intersection(bnds[i], bnds[j]) for i, j in zip(left, right) if i < j]
    return gpd.GeoSeries([l for l in lines if not l.is_empty], crs=dist.crs)


def load_plan(path: Path, blocks) -> np.ndarray:
    a = pd.read_csv(path, dtype={"GEOID20": str}).set_index("GEOID20")["district"]
    return a.reindex(blocks.GEOID20).fillna(0).astype(int).to_numpy() - 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("state")
    ap.add_argument("--sweep", default=str(ROOT / "output" / "homog_sweep"))
    ap.add_argument("--param", default="homog-rho")
    ap.add_argument("--values", default=None, help="comma list; default: all found in sweep dir")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    fips, abbr, k = data.resolve_state(a.state)
    sweep = Path(a.sweep)
    blocks = data.load_blocks(fips)
    v = votes.block_votes(fips, abbr, blocks)
    land, water = render.land_water(blocks)

    plans = {"enacted (119th)": evaluate.enacted_assignment(blocks, data.load_enacted(fips))}
    found = sorted(((float(d.name[len(a.param):]), d) for d in sweep.glob(f"{a.param}*")
                    if (d / abbr / "metis_assignment.csv").exists()), key=lambda x: x[0])
    want = None if a.values is None else {float(x) for x in a.values.split(",")}
    for val, d in found:
        if want is None or val in want:
            plans[f"{a.param.split('-')[-1]} = {val:g}"] = load_plan(d / abbr / "metis_assignment.csv", blocks)

    # Border lengths from the block graph (same measure for every plan).
    from .cli import load_graph
    g = load_graph(fips, blocks)
    stats = {}
    for name, asg in plans.items():
        m = evaluate.plan_metrics(g, blocks, asg, k)
        p = project.plan_stats(*project.plan_votes(asg, v, k), asg, v)
        stats[name] = (m["internal_border_km"], p["r2_between"], p["dem_seats"], p["competitive_seats"])

    prec = votes.load_precincts(fips, abbr).to_crs(EQUAL_AREA_CRS)
    prec["share"] = prec[votes.DEM] / (prec[votes.DEM] + prec[votes.REP]).replace(0, np.nan)
    water_gs = gpd.GeoSeries([water], crs=blocks.crs).to_crs(EQUAL_AREA_CRS) if water is not None else None

    xmin, ymin, xmax, ymax = gpd.GeoSeries([blocks.union_all()], crs=blocks.crs).to_crs(EQUAL_AREA_CRS).total_bounds
    aspect = (xmax - xmin) / (ymax - ymin)
    outline = gpd.GeoSeries([blocks[land].union_all()], crs=blocks.crs).to_crs(EQUAL_AREA_CRS).boundary
    dists = {}
    for name, asg in plans.items():
        dist = render.land_districts(blocks, asg, land, k).to_crs(EQUAL_AREA_CRS)
        dv, rv = project.plan_votes(asg, v, k)
        dist["share"] = dv / (dv + rv)
        dists[name] = (dist, internal_borders(dist))

    base = Path(a.out) if a.out else sweep / f"compare_{abbr}"
    for view, label in (("precinct", "precinct vote + district lines"), ("districts", "district vote share")):
        fig, cells, spare = screen_grid(len(plans), aspect)
        for ax, (name, (dist, inner)) in zip(cells, dists.items()):
            if water_gs is not None:
                water_gs.plot(ax=ax, color=render.WATER, edgecolor=render.WATER_EDGE, linewidth=0.2)
            if view == "precinct":
                prec.plot(ax=ax, column="share", cmap=CMAP, norm=NORM, linewidth=0, missing_kwds={"color": "#dddddd"})
            else:
                dist.plot(ax=ax, column="share", cmap=CMAP, norm=NORM, linewidth=0)
            outline.plot(ax=ax, color="#777777", linewidth=0.4)
            if view == "precinct":  # white halo so lines read over dark precincts
                inner.plot(ax=ax, color="white", linewidth=3.0)
            inner.plot(ax=ax, color="black", linewidth=1.3 if view == "precinct" else 1.0)
            ax.set_xlim(xmin, xmax); ax.set_ylim(ymin, ymax)
            b_, r2, ds, comp = stats[name]
            ax.set_title(f"{name}\nborder {b_:.0f} km · R² {r2:.2f} · {ds}D-{k - ds}R · {comp} comp.", fontsize=11)
        colorbar(fig, spare)
        fig.suptitle(f"{abbr} — {label}   (J = (1-ρ)·border/B₀ + ρ·within-district vote variance/T)",
                     fontsize=13, y=0.995, va="top")
        out = base.with_name(f"{base.name}_{view}.png")
        fig.savefig(out, dpi=SCREEN_DPI)  # exactly SCREEN_W x SCREEN_H pixels
        plt.close(fig)
        print(out)


# Target display: 1920x1080 laptop screen (16:9).
SCREEN_W, SCREEN_H, SCREEN_DPI = 1920, 1080, 100
TITLE_IN, PANEL_TITLE_IN = 0.95, 0.45  # inches reserved for figure / panel titles


def screen_grid(n: int, aspect: float):
    """Figure exactly filling the screen, with the grid (rows x cols) that makes each map
    largest for this state's width/height aspect. Returns (fig, axes, spare_axes_or_None)."""
    W, H = SCREEN_W / SCREEN_DPI, SCREEN_H / SCREEN_DPI - TITLE_IN
    best = None
    for cols in range(1, n + 1):
        rows = -(-n // cols)
        cw, ch = W / cols, H / rows - PANEL_TITLE_IN
        scale = min(cw, ch * aspect)  # map width that fits the cell
        if best is None or scale > best[0]:
            best = (scale, rows, cols)
    _, rows, cols = best
    fig = plt.figure(figsize=(SCREEN_W / SCREEN_DPI, SCREEN_H / SCREEN_DPI))
    gs = fig.add_gridspec(rows, cols, left=0.005, right=0.995, bottom=0.01,
                          top=1 - TITLE_IN / (SCREEN_H / SCREEN_DPI), hspace=0.18, wspace=0.02)
    axes = [fig.add_subplot(gs[i // cols, i % cols]) for i in range(rows * cols)]
    for ax in axes:
        ax.set_axis_off()
        ax.set_aspect("equal")
    spare = axes[n] if len(axes) > n else None
    return fig, axes[:n], spare


def colorbar(fig, spare):
    sm = plt.cm.ScalarMappable(cmap=CMAP, norm=NORM)
    if spare is not None:  # put the scale in the empty grid cell
        cax = spare.inset_axes([0.1, 0.45, 0.8, 0.08])
        cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
    else:
        cax = fig.add_axes([0.35, 0.005, 0.3, 0.012])
        cb = fig.colorbar(sm, cax=cax, orientation="horizontal")
    cb.set_label("2020 two-party Biden share (blue = D)", fontsize=10)


if __name__ == "__main__":
    main()
