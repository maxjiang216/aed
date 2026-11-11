"""Project House seats from 2020 presidential votes for enacted vs algorithmic plans.

    python -m districting.project output/national

For each state dir with assignments: district two-party Biden share -> winner;
seats, efficiency gap, mean-median, and a uniform-swing seats curve per plan.
Ignores incumbency and candidates: it measures how each map converts the same
votes into seats.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from . import data, evaluate, votes

# 2020 presidential winner in single-district states (same under every plan).
AT_LARGE = {"AK": "R", "DE": "D", "ND": "R", "SD": "R", "VT": "D", "WY": "R"}
SWINGS = np.round(np.arange(-0.10, 0.1001, 0.005), 3)


def plan_votes(assign: np.ndarray, v: pd.DataFrame, k: int) -> tuple[np.ndarray, np.ndarray]:
    ok = assign >= 0
    dem = np.bincount(assign[ok], weights=v["dem"].to_numpy()[ok], minlength=k)
    rep = np.bincount(assign[ok], weights=v["rep"].to_numpy()[ok], minlength=k)
    return dem, rep


def plan_stats(dem: np.ndarray, rep: np.ndarray) -> dict:
    share = dem / (dem + rep)
    tot = dem + rep
    need = np.floor(tot / 2) + 1
    # Wasted votes: all losing votes + winning votes above the threshold.
    wd = np.where(share > 0.5, dem - need, dem)
    wr = np.where(share > 0.5, rep, rep - need)
    eg = (wd.sum() - wr.sum()) / tot.sum()  # >0: map wastes more D votes (favours R)
    statewide = dem.sum() / tot.sum()
    return {
        "dem_seats": int((share > 0.5).sum()),
        "rep_seats": int((share <= 0.5).sum()),
        "statewide_dem": round(float(statewide), 4),
        "efficiency_gap": round(float(eg), 4),
        "mean_median": round(float(np.mean(share) - np.median(share)), 4),
        "district_dem_share": np.round(share, 4).tolist(),
        "swing_dem_seats": [int(((share + s) > 0.5).sum()) for s in SWINGS],
    }


def plan_assignments(state_dir: Path, blocks) -> dict[str, np.ndarray]:
    fips, abbr, k = data.resolve_state(state_dir.name)
    metrics = json.loads((state_dir / "metrics.json").read_text())
    plans = {}
    for name in metrics:
        if name.startswith("enacted"):
            plans["enacted"] = evaluate.enacted_assignment(blocks, data.load_enacted(fips))
            continue
        f = state_dir / f"{name}_assignment.csv"
        if f.exists():
            a = pd.read_csv(f, dtype={"GEOID20": str}).set_index("GEOID20")["district"]
            plans[name] = a.reindex(blocks.GEOID20).fillna(0).astype(int).to_numpy() - 1
    return plans


def project_state(state_dir: Path) -> dict:
    fips, abbr, k = data.resolve_state(state_dir.name)
    blocks = data.load_blocks(fips)
    v = votes.block_votes(fips, abbr, blocks)
    out = {}
    for name, a in plan_assignments(state_dir, blocks).items():
        out[name] = plan_stats(*plan_votes(a, v, k))
    (state_dir / "projection.json").write_text(json.dumps(out, indent=1))
    return out


def national(root: Path) -> pd.DataFrame:
    rows = []
    for d in sorted(root.iterdir()):
        if not (d.is_dir() and (d / "metrics.json").exists()):
            continue
        try:
            res = project_state(d)
        except Exception as e:  # keep going; report at the end
            print(f"{d.name}: FAILED {e!r}", flush=True)
            continue
        _, _, k = data.resolve_state(d.name)
        for plan, s in res.items():
            rows.append({"state": d.name, "seats": k, "plan": plan, **{x: s[x] for x in
                         ("dem_seats", "rep_seats", "statewide_dem", "efficiency_gap", "mean_median")}})
        e = res.get("enacted", {})
        print(f"{d.name}: " + "  ".join(f"{p} {s['dem_seats']}D-{s['rep_seats']}R" for p, s in res.items())
              + f"  (Biden {e.get('statewide_dem', float('nan')):.1%})", flush=True)
    df = pd.DataFrame(rows)
    df.to_csv(root / "projection_by_state.csv", index=False)
    return df


def summarize(root: Path, df: pd.DataFrame) -> None:
    at_d = sum(1 for p in AT_LARGE.values() if p == "D")
    at_r = len(AT_LARGE) - at_d
    states = set(df.state)
    lines = [f"at-large states (fixed): {at_d}D {at_r}R; states projected: {len(states)}"]
    totals = {}
    for plan in ["enacted", "metis", "polished-enacted"]:
        sub = df[df.plan == plan]
        if plan != "enacted":  # fall back to enacted where a plan is missing (e.g. skipped)
            sub = pd.concat([sub, df[(df.plan == "enacted") & ~df.state.isin(sub.state)]])
        d, r = int(sub.dem_seats.sum()) + at_d, int(sub.rep_seats.sum()) + at_r
        totals[plan] = (d, r)
        lines.append(f"{plan:17s} {d}D - {r}R   (of {d + r})")
    e = df[df.plan == "enacted"].set_index("state")
    m = df[df.plan == "metis"].set_index("state")
    diff = (m.dem_seats - e.dem_seats.reindex(m.index)).dropna()
    lines.append("states where min-border map changes the projected D seat count "
                 "(metis - enacted): " + ", ".join(f"{s} {int(x):+d}" for s, x in diff[diff != 0].items()))
    text = "\n".join(lines)
    print("\n" + text)
    (root / "projection_summary.txt").write_text(text + "\n")
    swing_plot(root, df)


def swing_plot(root: Path, df: pd.DataFrame) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    curves = {}
    for plan in ["enacted", "metis"]:
        tot = np.zeros(len(SWINGS))
        for st in sorted(set(df.state)):
            f = root / st / "projection.json"
            res = json.loads(f.read_text())
            s = res.get(plan) or res.get("enacted")
            if s:
                tot += np.array(s["swing_dem_seats"])
        tot += sum(1 for p in AT_LARGE.values() if p == "D")  # at-large fixed
        curves[plan] = tot
    fig, ax = plt.subplots(figsize=(8, 5))
    for plan, c in curves.items():
        ax.plot(SWINGS * 100, c, marker="o", ms=3, label=plan)
    ax.axhline(218, color="grey", lw=0.8, ls="--")
    ax.axvline(0, color="grey", lw=0.8)
    ax.set_xlabel("uniform swing toward Democrats (points), from 2020 presidential")
    ax.set_ylabel("projected Democratic House seats (of 435)")
    ax.set_title("Seats vs uniform swing: enacted maps vs min-border maps")
    ax.legend()
    fig.tight_layout()
    fig.savefig(root / "swing_curve.png", dpi=140)
    plt.close(fig)


def main():
    root = Path(sys.argv[1])
    if (root / "metrics.json").exists():
        print(json.dumps({p: {k: v for k, v in s.items() if k not in ("district_dem_share", "swing_dem_seats")}
                          for p, s in project_state(root).items()}, indent=1))
        return
    summarize(root, national(root))


if __name__ == "__main__":
    main()
