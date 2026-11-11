"""Run every multi-district state, then summarise.

    python -m districting.national run   [--seeds 8] [--states IA,WI]   # per-state CLI runs
    python -m districting.national summary                              # table + national map
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from . import data

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "output" / "national"


REFERENCE_PLANS = ("enacted", "polished-enacted")


def run(states: list[str], seeds: int, workers: int, target_pct: float | None) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    tf = OUT / "timings.json"
    timings = json.loads(tf.read_text()) if tf.exists() else {}  # keep other states' timings
    for abbr in states:
        t = time.time()
        print(f"\n===== {abbr} =====", flush=True)
        rc = subprocess.call([sys.executable, "-W", "ignore", "-u", "-m", "districting.cli", abbr,
                              "--seeds", str(seeds), "--workers", str(workers),
                              "--out", str(OUT / abbr)]
                             + (["--target-pct", str(target_pct)] if target_pct else []), cwd=ROOT)
        timings[abbr] = {"seconds": round(time.time() - t, 1), "rc": rc}
        print(f"===== {abbr} rc={rc} {time.time()-t:.0f}s", flush=True)
        (OUT / "timings.json").write_text(json.dumps(timings, indent=1))


def summary() -> None:
    import geopandas as gpd
    import matplotlib
    import pandas as pd
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    timings = json.loads((OUT / "timings.json").read_text()) if (OUT / "timings.json").exists() else {}
    rows, shapes = [], []
    for fips, (abbr, k) in sorted(data.SEATS.items(), key=lambda x: x[1][0]):
        f = OUT / abbr / "metrics.json"
        if not f.exists():
            rows.append({"state": abbr, "seats": k, "status": "missing"})
            continue
        m = json.loads(f.read_text())
        algo = {n: v for n, v in m.items() if not n.startswith(REFERENCE_PLANS)}
        if not algo:
            rows.append({"state": abbr, "seats": k, "status": "no valid plan"})
            continue
        best = min(algo, key=lambda n: (algo[n]["pop_spread"] > algo[n].get("target", 1),
                                         algo[n]["internal_border_km"]))
        b, e, pe = algo[best], m.get("enacted (119th)", {}), m.get("polished-enacted", {})
        rows.append({
            "state": abbr, "seats": k, "method": best, "spread": b["pop_spread"],
            "border_km": round(b["internal_border_km"], 1),
            "enacted_border_km": round(e.get("internal_border_km", float("nan")), 1),
            "border_vs_enacted": round(b["internal_border_km"] / e["internal_border_km"], 3) if e else None,
            "polished_enacted_km": round(pe.get("internal_border_km", float("nan")), 1),
            "target": b.get("target"),
            "pp_mean": round(b["polsby_popper_mean"], 3),
            "enacted_pp_mean": round(e.get("polsby_popper_mean", float("nan")), 3),
            "split_counties": b["split_counties"], "enacted_split_counties": e.get("split_counties"),
            "seconds": timings.get(abbr, {}).get("seconds"),
        })
        gj = OUT / abbr / f"{best}_districts.geojson"
        if gj.exists():
            g = gpd.read_file(gj)
            g["state"] = abbr
            shapes.append(g)
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "summary.csv", index=False)
    with pd.option_context("display.max_rows", 100, "display.width", 200):
        print(df.to_string(index=False))
    ok = df[df.get("border_km").notna()] if "border_km" in df else df.iloc[:0]
    if len(ok):
        print(f"\nstates: {len(ok)}/{len(df)}; spread<=target: {(ok.spread <= ok.target.fillna(1)).sum()}; "
              f"total border {ok.border_km.sum():,.0f} km vs enacted {ok.enacted_border_km.sum():,.0f} km "
              f"({ok.border_km.sum()/ok.enacted_border_km.sum():.0%}); "
              f"total time {ok.seconds.sum()/60:.1f} min")
    if shapes:
        allg = pd.concat(shapes, ignore_index=True).to_crs("EPSG:5070")
        conus = allg[allg.state != "HI"]
        fig, ax = plt.subplots(figsize=(20, 12))
        conus.plot(ax=ax, column=conus.index % 20, cmap="tab20", edgecolor="black", linewidth=0.25)
        conus.dissolve("state").boundary.plot(ax=ax, color="black", linewidth=0.9)
        ax.set_axis_off()
        ax.set_title("Min-border, equal-population congressional districts (2020 census blocks), "
                     "contiguous US — single-district states not shown", fontsize=13)
        fig.savefig(OUT / "national_map.png", dpi=140, bbox_inches="tight")
        print(f"wrote {OUT / 'national_map.png'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "summary"])
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--target-pct", type=float, default=None)
    ap.add_argument("--states", default=None, help="comma list; default all multi-district states")
    a = ap.parse_args()
    if a.cmd == "run":
        states = a.states.split(",") if a.states else sorted(abbr for abbr, _ in data.SEATS.values())
        run(states, a.seeds, a.workers, a.target_pct)
        summary()
    else:
        summary()


if __name__ == "__main__":
    main()
