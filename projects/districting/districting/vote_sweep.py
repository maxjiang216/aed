"""Sweep the vote-similarity exponent alpha and compare plans.

    python -m districting.vote_sweep --states IA,WI,NC --alphas 0,2,5,10,20

For each (alpha, state): draw with `cli --vote-alpha`, project seats, collect
border length, seats, competitive seats, average margin and within-district spread.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

from . import project

ROOT = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", default="IA,WI,NC")
    ap.add_argument("--alphas", default="0,2,5,10,20")
    ap.add_argument("--param", choices=["vote-alpha", "homog-rho"], default="vote-alpha",
                    help="which knob the --alphas values set")
    ap.add_argument("--seeds", type=int, default=8)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--target-pct", type=float, default=0.001)
    ap.add_argument("--out-root", default=str(ROOT / "output" / "vote_sweep"))
    a = ap.parse_args()
    root = Path(a.out_root)
    rows = []
    for alpha in [float(x) for x in a.alphas.split(",")]:
        for st in a.states.split(","):
            out = root / f"{a.param}{alpha:g}" / st
            if not (out / "metrics.json").exists():
                subprocess.run([sys.executable, "-W", "ignore", "-u", "-m", "districting.cli", st,
                                "--seeds", str(a.seeds), "--workers", str(a.workers),
                                "--target-pct", str(a.target_pct), f"--{a.param}", str(alpha),
                                "--no-enacted", "--out", str(out)], cwd=ROOT, check=True,
                               stdout=subprocess.DEVNULL)
            m = json.loads((out / "metrics.json").read_text())["metis"]
            p = project.project_state(out)["metis"]
            rows.append({"alpha": alpha, "state": st, "border_km": round(m["internal_border_km"], 1),
                         "pp_mean": round(m["polsby_popper_mean"], 3), "split_counties": m["split_counties"],
                         "dem_seats": p["dem_seats"], "rep_seats": p["rep_seats"],
                         "competitive": p["competitive_seats"], "mean_margin": p["mean_margin"],
                         "within_spread": p["within_district_spread"], "r2": p["r2_between"],
                         "eff_gap": p["efficiency_gap"]})
            print(rows[-1], flush=True)
    df = pd.DataFrame(rows)
    df.attrs["param"] = a.param
    df.to_csv(root / "sweep.csv", index=False)
    with pd.option_context("display.width", 200):
        print(df.to_string(index=False))
    plot(df, root)


def plot(df: pd.DataFrame, root: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    cols = [("border_km", "internal border (km)"), ("r2", "R² between districts (sorting)"),
            ("mean_margin", "average district margin"), ("dem_seats", "projected D seats")]
    fig, axes = plt.subplots(1, len(cols), figsize=(4.2 * len(cols), 3.6))
    for ax, (c, label) in zip(axes, cols):
        for st, sub in df.groupby("state"):
            ax.plot(sub.alpha, sub[c], marker="o", label=st)
        ax.set_xlabel(df.attrs.get("param", "alpha"))
        ax.set_title(label, fontsize=10)
    axes[0].legend()
    fig.tight_layout()
    fig.savefig(root / "sweep.png", dpi=130)
    plt.close(fig)


if __name__ == "__main__":
    main()
