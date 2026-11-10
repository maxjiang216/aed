"""Plan metrics, enacted-plan comparison, and map rendering."""

from __future__ import annotations

import geopandas as gpd
import numpy as np
import pandas as pd
import shapely

from .graph import BlockGraph, EQUAL_AREA_CRS


def plan_metrics(g: BlockGraph, blocks: gpd.GeoDataFrame, assign: np.ndarray, k: int) -> dict:
    src = np.repeat(np.arange(g.n), np.diff(g.xadj))
    cut = assign[src] != assign[g.adjncy]
    cut_len = g.length[cut].sum() / 2
    # Perimeter per district = cut edges incident to it + state boundary.
    perim = np.bincount(assign[src[cut]], weights=g.length[cut], minlength=k)
    perim += np.bincount(assign, weights=g.exterior, minlength=k)
    area = np.bincount(assign, weights=(blocks["ALAND20"] + blocks["AWATER20"]).to_numpy(float), minlength=k)
    pop = np.bincount(assign, weights=g.pop, minlength=k).astype(np.int64)
    pp = 4 * np.pi * area / perim**2
    ideal = g.pop.sum() / k
    county = blocks["COUNTYFP20"].to_numpy()
    df = pd.DataFrame({"county": county, "d": assign})
    split_counties = int((df.groupby("county")["d"].nunique() > 1).sum())
    return {
        "districts": k,
        "total_pop": int(g.pop.sum()),
        "ideal_pop": ideal,
        "pop": pop.tolist(),
        "pop_spread": int(pop.max() - pop.min()),
        "max_dev_pct": float(np.abs(pop - ideal).max() / ideal * 100),
        "internal_border_km": float(cut_len / 1000),
        "polsby_popper": pp.round(4).tolist(),
        "polsby_popper_mean": float(pp.mean()),
        "split_counties": split_counties,
    }


def enacted_assignment(blocks: gpd.GeoDataFrame, cds: gpd.GeoDataFrame) -> np.ndarray:
    pts = gpd.GeoDataFrame(geometry=blocks.geometry.representative_point(), crs=blocks.crs)
    cds = cds.to_crs(blocks.crs)
    cd_field = [c for c in cds.columns if c.startswith("CD") and c.endswith("FP")][0]
    j = gpd.sjoin(pts, cds[[cd_field, "geometry"]], how="left", predicate="within")
    j = j[~j.index.duplicated()]
    codes = j[cd_field].ffill().to_numpy()
    _, assign = np.unique(codes, return_inverse=True)
    return assign.astype(np.int64)


def dissolve(blocks: gpd.GeoDataFrame, assign: np.ndarray, k: int) -> gpd.GeoDataFrame:
    geoms = blocks.geometry.values
    out = [shapely.coverage_union_all(geoms[assign == d]) for d in range(k)]
    return gpd.GeoDataFrame({"district": np.arange(k) + 1}, geometry=out, crs=blocks.crs)


def plot_plans(plans: dict[str, gpd.GeoDataFrame], metrics: dict[str, dict], title: str, path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    n = len(plans)
    fig, axes = plt.subplots(1, n, figsize=(6.5 * n, 5.5))
    axes = np.atleast_1d(axes)
    for ax, (name, gdf) in zip(axes, plans.items()):
        gdf.to_crs(EQUAL_AREA_CRS).plot(ax=ax, column="district", cmap="tab20", categorical=True,
                                        edgecolor="black", linewidth=0.6)
        m = metrics[name]
        ax.set_title(f"{name}\nborder {m['internal_border_km']:.0f} km · PP mean "
                     f"{m['polsby_popper_mean']:.3f} · spread {m['pop_spread']} · "
                     f"{m['split_counties']} split counties", fontsize=9)
        ax.set_axis_off()
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
