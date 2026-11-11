"""National map, side by side (1920x1080):
  left  - min-border districts, projected winner/margin from 2020 presidential votes
  right - enacted 119th districts, actual 2024 House winner/margin (MEDSL)

Colors: four stops per party (tilt, lean, likely, solid) reached at margins
5% / 10% / 20%, linearly interpolated -- same scale as the site (src/colors.ts).

    python -m districting.national_lean
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import geopandas as gpd
import matplotlib
import numpy as np
import pandas as pd

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from . import data, evaluate, render, votes
from .graph import EQUAL_AREA_CRS

ROOT = Path(__file__).resolve().parent.parent
NAT = ROOT / "output" / "national"
HOUSE_SRC = Path(__file__).resolve().parents[2] / "aed" / "raw" / "medsl_house_1976_2024.csv"
HOUSE = ROOT / "data" / "raw" / "house" / "medsl_house_1976_2024.csv"

# ---- aed margin colors (src/colors.ts) ----
CUTOFFS = [0.05, 0.1, 0.2]
PALETTES = {
    "Blue": [(148, 155, 179), (138, 175, 255), (87, 124, 204), (28, 64, 140)],
    "Red": [(207, 137, 128), (255, 139, 152), (255, 88, 101), (191, 29, 41)],
    "Gray": [(150, 150, 150), (175, 175, 175), (130, 130, 130), (85, 85, 85)],
}
TIE = (107, 110, 115)


def margin_color(margin: float, hue: str):
    """margin in [0, 1] -> RGB in [0, 1]; port of aed marginColor."""
    def mix(a, b, t):
        return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))
    if not margin > 0:
        c = TIE
    else:
        pal = PALETTES[hue]
        if margin >= CUTOFFS[-1]:
            c = pal[-1]
        elif margin < CUTOFFS[0]:
            c = mix(pal[0], pal[1], margin / CUTOFFS[0])
        else:
            c = pal[-1]
            for i in range(len(CUTOFFS) - 1):
                if margin < CUTOFFS[i + 1]:
                    c = mix(pal[i + 1], pal[i + 2], (margin - CUTOFFS[i]) / (CUTOFFS[i + 1] - CUTOFFS[i]))
                    break
    return tuple(x / 255 for x in c)


# ---- 2024 House results ----
def house_2024() -> pd.DataFrame:
    """One row per (state_po, district): winner party (D/R/O) and margin over runner-up
    as a share of all votes (uncontested = 1). Fusion lines summed per candidate."""
    if not HOUSE.exists():
        HOUSE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(HOUSE_SRC, HOUSE)
    d = pd.read_csv(HOUSE, low_memory=False)
    d = d[(d.year == 2024) & (d.stage == "GEN") & (~d.special) & d.candidate.notna()]
    d = d[(d.candidate.str.upper() != "WRITEIN") & (d.state_po != "DC")]  # DC delegate is non-voting
    party = d.party.fillna("").str.upper()
    d = d.assign(p=np.where(party.str.contains("DEMOCRAT"), "D", np.where(party.str.contains("REPUBLICAN"), "R", "O")))
    # Candidate party = major party if any of their lines is one (fusion tickets).
    cand = (d.groupby(["state_po", "district", "candidate"])
            .agg(votes=("candidatevotes", "sum"), p=("p", lambda s: "D" if "D" in set(s) else "R" if "R" in set(s) else "O"),
                 total=("totalvotes", "first"))
            .reset_index().sort_values("votes", ascending=False))
    rows = []
    for (st, dist), g in cand.groupby(["state_po", "district"]):
        top = g.iloc[0]
        second = g.iloc[1].votes if len(g) > 1 else 0
        total = max(top.total, g.votes.sum())
        rows.append({"state_po": st, "district": int(dist), "winner": top.p,
                     "margin": 1.0 if total <= 0 else (top.votes - second) / total})
    return pd.DataFrame(rows)


# ---- uniform swing: 2020 presidential -> 2024 House popular vote ----
PRES_SRC = Path(__file__).resolve().parents[2] / "aed" / "MIT" / "countypres_2000-2020.csv"
AT_LARGE_ALL = ["AK", "DE", "ND", "SD", "VT", "WY"]


def pres2020_by_state() -> pd.DataFrame:
    c = pd.read_csv(PRES_SRC, low_memory=False)
    c = c[(c.year == 2020) & c.party.isin(["DEMOCRAT", "REPUBLICAN"])]
    return c.pivot_table(index="state_po", columns="party", values="candidatevotes", aggfunc="sum")


def national_shift(house: pd.DataFrame | None = None) -> tuple[float, float, float]:
    """(shift, pres2020_D, house2024_D): two-party D shares; shift = house - pres."""
    t = pres2020_by_state().sum()
    pres = t["DEMOCRAT"] / (t["DEMOCRAT"] + t["REPUBLICAN"])
    h = pd.read_csv(HOUSE, low_memory=False)
    h = h[(h.year == 2024) & (h.stage == "GEN") & (~h.special) & (h.state_po != "DC")]
    party = h.party.fillna("").str.upper()
    hd = h[party.str.contains("DEMOCRAT")].candidatevotes.sum()
    hr = h[party.str.contains("REPUBLICAN")].candidatevotes.sum()
    hs = hd / (hd + hr)
    return float(hs - pres), float(pres), float(hs)


def shifted_seats(shift: float, plan: str) -> tuple[int, int]:
    """435-seat D/R totals for `plan` (falls back to enacted where missing) after uniform shift."""
    d = r = 0
    for fips, (abbr, k) in data.SEATS.items():
        proj = json.loads((NAT / abbr / "projection.json").read_text())
        sh = np.array((proj.get(plan) or proj["enacted"])["district_dem_share"]) + shift
        d += int((sh > 0.5).sum()); r += int((sh <= 0.5).sum())
    p = pres2020_by_state()
    for st in AT_LARGE_ALL:
        share = p.loc[st, "DEMOCRAT"] / (p.loc[st, "DEMOCRAT"] + p.loc[st, "REPUBLICAN"]) + shift
        d += int(share > 0.5); r += int(share <= 0.5)
    return d, r


# ---- shapes ----
def enacted_land(abbr: str) -> gpd.GeoDataFrame:
    """Land-only enacted districts with CD number, cached per state."""
    f = NAT / abbr / "enacted_districts_land.geojson"
    if f.exists():
        return gpd.read_file(f)
    fips, _, k = data.resolve_state(abbr)
    blocks = data.load_blocks(fips)
    cds = data.load_enacted(fips)
    field = [c for c in cds.columns if c.startswith("CD") and c.endswith("FP")][0]
    codes = np.sort(cds.loc[cds[field] != "ZZ", field].astype(int).unique())  # ZZ = water, no district
    asg = evaluate.enacted_assignment(blocks, cds)  # index into sorted codes
    land, _ = render.land_water(blocks)
    g = render.land_districts(blocks, asg, land, k)
    g["cd"] = codes[g["district"].to_numpy() - 1]
    g.to_file(f, driver="GeoJSON")
    return g


AT_LARGE = {"10": "DE", "38": "ND", "46": "SD", "50": "VT", "56": "WY"}  # contiguous at-large states


def at_large_shapes() -> gpd.GeoDataFrame:
    out = []
    for fips, abbr in AT_LARGE.items():
        g = data.load_enacted(fips)
        prec = votes.load_precincts(fips, abbr)
        dem, rep = prec[votes.DEM].sum(), prec[votes.REP].sum()
        out.append({"state": abbr, "geometry": g.union_all(), "proj_share": dem / (dem + rep)})
    return gpd.GeoDataFrame(out, crs=g.crs)


def main():
    house = house_2024()
    shift, pres, hs = national_shift()
    print(f"uniform shift {shift:+.4f} (2020 pres D {pres:.4f} -> 2024 House D {hs:.4f})")
    left, right, hatched = [], [], []
    for fips, (abbr, k) in sorted(data.SEATS.items(), key=lambda x: x[1][0]):
        if abbr == "HI":
            continue
        proj = json.loads((NAT / abbr / "projection.json").read_text())
        en = enacted_land(abbr).to_crs(EQUAL_AREA_CRS)
        # right: actual 2024 results on enacted districts
        h = house[house.state_po == abbr].set_index("district")
        missing = set(en.cd) - set(h.index)
        if missing:
            print(f"warning: {abbr} no 2024 result for CD {sorted(missing)}")
        en["winner"] = en.cd.map(h.winner).fillna("O")
        en["margin"] = en.cd.map(h.margin).fillna(0.0)
        en["state"] = abbr
        right.append(en)
        # left: min-border districts, projected from 2020 presidential
        f = NAT / abbr / "metis_districts_land.geojson"
        if f.exists() and "metis" in proj:
            g = gpd.read_file(f).to_crs(EQUAL_AREA_CRS)
            share = np.array(proj["metis"]["district_dem_share"])[g["district"].to_numpy() - 1] + shift
        else:  # no min-border plan (LA): show enacted districts, hatched
            g = en[["geometry"]].copy()
            share = np.array(proj["enacted"]["district_dem_share"]) + shift
            hatched.append(abbr)
        g["winner"] = np.where(share > 0.5, "D", "R")
        g["margin"] = np.abs(2 * share - 1)
        g["state"] = abbr
        left.append(g)

        print(abbr, flush=True)
    al = at_large_shapes().to_crs(EQUAL_AREA_CRS)
    for _, r in al.iterrows():
        ps = r.proj_share + shift
        left.append(gpd.GeoDataFrame([{"geometry": r.geometry, "winner": "D" if ps > 0.5 else "R",
                                       "margin": abs(2 * ps - 1), "state": r.state}], crs=al.crs))
        hr = house[house.state_po == r.state].iloc[0]
        right.append(gpd.GeoDataFrame([{"geometry": r.geometry, "winner": hr.winner, "margin": hr.margin,
                                        "state": r.state}], crs=al.crs))
    L = pd.concat(left, ignore_index=True)
    R = pd.concat(right, ignore_index=True)

    house_d = int((house.winner == "D").sum())
    house_r = int((house.winner == "R").sum())
    hue = {"D": "Blue", "R": "Red", "O": "Gray"}
    for df in (L, R):
        df["color"] = [margin_color(m, hue[w]) for w, m in zip(df.winner, df.margin)]

    # Seat totals (all 435 incl. AK, HI).
    d_l, r_l = shifted_seats(shift, "metis")
    d_e, r_e = shifted_seats(shift, "enacted")
    print(f"shifted seats: min-border {d_l}D-{r_l}R; enacted districts {d_e}D-{r_e}R; actual 2024 {house_d}D-{house_r}R")

    W, H, DPI = 1920, 1080, 100
    fig = plt.figure(figsize=(W / DPI, H / DPI))
    # Two ~1.6:1 US maps side by side fill ~55% of a 16:9 screen's height; keep the
    # title, maps and legend in one compact band instead of spreading them out.
    axl = fig.add_axes([0.0, 0.215, 0.5, 0.6])
    axr = fig.add_axes([0.5, 0.215, 0.5, 0.6])
    states_l = L.dissolve("state").boundary
    states_r = R.dissolve("state").boundary
    for ax, df, st in ((axl, L, states_l), (axr, R, states_r)):
        df.plot(ax=ax, color=df.color, edgecolor="white", linewidth=0.25)
        st.plot(ax=ax, color="#333333", linewidth=0.6)
        ax.set_axis_off()
        ax.set_aspect("equal")
    for abbr in hatched:
        L[L.state == abbr].plot(ax=axl, facecolor="none", edgecolor="#444444", hatch="////", linewidth=0)
    axl.set_title(f"Min-border districts — 2020 presidential vote shifted {shift * 100:+.1f} pts to 2024 House PV\n"
                  f"{d_l} D · {r_l} R   (enacted districts, same votes: {d_e} D · {r_e} R)", fontsize=14, pad=6)
    axr.set_title(f"Enacted districts (119th Congress) — actual 2024 House results\n{house_d} D · {house_r} R",
                  fontsize=15, pad=6)
    fig.suptitle("U.S. House: border-minimizing map vs reality", fontsize=20, y=0.93)

    # Legend: aed four-stop ramps.
    lax = fig.add_axes([0.25, 0.09, 0.5, 0.09])
    lax.set_xlim(0, 1); lax.set_ylim(0, 2); lax.set_axis_off()
    xs = np.linspace(0.001, 0.3, 120)
    for row, (party, hname) in enumerate((("Democratic", "Blue"), ("Republican", "Red"))):
        y = 1.1 - row * 0.9
        for i, m in enumerate(xs):
            lax.add_patch(Rectangle((0.18 + i * 0.8 / len(xs), y), 0.8 / len(xs) + 0.001, 0.6,
                                    color=margin_color(m, hname), linewidth=0))
        lax.text(0.17, y + 0.3, party, ha="right", va="center", fontsize=11)
    for m, lbl in ((0.0, "tilt"), (0.05, "lean 5%"), (0.10, "likely 10%"), (0.20, "solid 20%+")):
        lax.text(0.18 + m / 0.3 * 0.8, -0.05, lbl, ha="center", va="top", fontsize=10)
    notes = (f"Margin = winner minus runner-up. Left: 2020 two-party presidential share per district, uniformly shifted "
             f"{shift * 100:+.2f} pts so the national two-party vote matches the 2024 House ({hs:.1%} D); ignores candidates/incumbency. Right: MEDSL 2024 House returns; uncontested = solid. "
             f"AK, HI not shown (counted in totals). Hatched: {', '.join(hatched)} has no min-border plan — enacted districts shown.")
    fig.text(0.5, 0.02, notes, ha="center", va="bottom", fontsize=9.5, color="#444444", wrap=True)
    out = NAT / "national_lean_vs_2024.png"
    fig.savefig(out, dpi=DPI)
    print(out)


if __name__ == "__main__":
    main()
