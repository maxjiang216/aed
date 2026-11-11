"""How do national swings distribute across places? Empirical test of swing models.

Each model maps an area's previous two-party D share s to a prediction s' with ONE
national parameter c (fitted per cycle, vote-weighted least squares):

  uniform   s' = s + c                       fixed share of the whole electorate moves
  flip      c<0: s' = s(1+c)                 "% flipped": a fixed fraction of the losing
            c>0: s' = s + c(1-s)             side's voters switch (bigger swings where it's big)
  logit     logit s' = logit s + c           proportional odds == uniform *differential
                                             turnout* (D votes x(1+d), R votes x(1+r) everywhere)

Levels: states 1976-2024 (president), counties 2000-2024 (president), and House
districts between consecutive elections on unchanged lines (contested both years).

Also: swing-vs-lean slope diagnostic, battleground (prior closeness) effect on
residuals, and a switching-vs-turnout decomposition for 2020->2024 counties.

    python -m districting.swing_models
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize_scalar
from scipy.special import expit, logit

ROOT = Path(__file__).resolve().parent.parent
AED = Path.home() / "projects" / "aed"
OUT = ROOT / "output" / "swing_models"


# ------------------------------------------------------------------ data ---

def state_pres() -> pd.DataFrame:
    p = pd.read_csv(AED / "raw" / "medsl_president_1976_2024.csv", low_memory=False)
    p = p[p.party_simplified.isin(["DEMOCRAT", "REPUBLICAN"])]
    t = p.pivot_table(index=["year", "state_po"], columns="party_simplified", values="candidatevotes", aggfunc="sum")
    return t.rename(columns={"DEMOCRAT": "dem", "REPUBLICAN": "rep"}).reset_index().rename(columns={"state_po": "unit"})


def county_pres() -> pd.DataFrame:
    c = pd.read_csv(AED / "MIT" / "countypres_2000-2020.csv", low_memory=False)
    c = c[c.party.isin(["DEMOCRAT", "REPUBLICAN"]) & c.county_fips.notna() & (c.state_po != "AK")]
    has_total = c.groupby(["year", "county_fips"])["mode"].transform(lambda s: "TOTAL" in set(s))
    c = c[~has_total | (c["mode"] == "TOTAL")]  # avoid double counting mode breakdowns
    t = c.pivot_table(index=["year", "county_fips"], columns="party", values="candidatevotes", aggfunc="sum")
    t = t.rename(columns={"DEMOCRAT": "dem", "REPUBLICAN": "rep"}).reset_index()
    st = c.drop_duplicates("county_fips").set_index("county_fips").state_po
    t["state_po"] = t.county_fips.map(st)
    n = pd.read_csv(ROOT / "data" / "raw" / "pres_county" / "2024_county.csv")
    n = n[~n.state_name.isin(["Alaska", "Connecticut"])]  # AK by district; CT changed to planning regions
    n24 = pd.DataFrame({"year": 2024, "county_fips": n.county_fips.astype(float), "dem": n.votes_dem, "rep": n.votes_gop})
    n24["state_po"] = n24.county_fips.map(st)
    t = pd.concat([t, n24], ignore_index=True)
    return t.rename(columns={"county_fips": "unit"})


def house_pairs() -> pd.DataFrame:
    """Consecutive House elections on the same lines, D-vs-R contested both times."""
    h = pd.read_csv(AED / "raw" / "medsl_house_1976_2024.csv", low_memory=False)
    h = h[(h.stage == "GEN") & (~h.special) & (h.state_po != "DC")]
    party = h.party.fillna("").str.upper()
    h = h.assign(p=np.where(party.str.contains("DEMOCRAT"), "D", np.where(party.str.contains("REPUBLICAN"), "R", "O")))
    t = h[h.p != "O"].pivot_table(index=["year", "state_po", "district"], columns="p", values="candidatevotes",
                                  aggfunc="sum").reset_index()
    t = t.rename(columns={"D": "dem", "R": "rep"}).dropna()
    t = t[(t.dem > 0) & (t.rep > 0)]
    t["unit"] = t.state_po + "-" + t.district.astype(int).astype(str)
    # Same lines: skip pairs that cross a redistricting year (lines first used in years ending in 2).
    t["decade"] = (t.year - 2) // 10
    return t


def pairs(df: pd.DataFrame, y0: int, y1: int, extra=("state_po",)) -> pd.DataFrame:
    a = df[df.year == y0].set_index("unit")
    b = df[df.year == y1].set_index("unit")
    j = a.join(b, lsuffix="0", rsuffix="1", how="inner")
    j["s0"] = j.dem0 / (j.dem0 + j.rep0)
    j["s1"] = j.dem1 / (j.dem1 + j.rep1)
    j["w"] = j.dem1 + j.rep1
    for e in extra:
        if f"{e}0" in j:
            j[e] = j[f"{e}0"]
    return j[(j.s0 > 0) & (j.s0 < 1) & (j.s1 > 0) & (j.s1 < 1)].reset_index()


# ---------------------------------------------------------------- models ---

def m_uniform(s, c):
    return np.clip(s + c, 1e-6, 1 - 1e-6)


def m_flip(s, c):
    return np.where(c < 0, s * (1 + c), s + c * (1 - s))


def m_logit(s, c):
    return expit(logit(s) + c)


MODELS = {"uniform": (m_uniform, (-0.5, 0.5)), "flip": (m_flip, (-0.9, 0.9)), "logit": (m_logit, (-3, 3))}


def fit(model, s0, s1, w):
    f, bounds = MODELS[model]
    r = minimize_scalar(lambda c: np.sum(w * (f(s0, c) - s1) ** 2), bounds=bounds, method="bounded")
    pred = f(s0, r.x)
    rmse = np.sqrt(np.sum(w * (pred - s1) ** 2) / w.sum())
    return r.x, pred, rmse


def evaluate(j: pd.DataFrame) -> dict:
    s0, s1, w = j.s0.to_numpy(), j.s1.to_numpy(), j.w.to_numpy()
    nat = np.sum(w * (s1 - s0)) / w.sum()
    out = {"n": len(j), "national_swing": nat}
    for m in MODELS:
        c, pred, rmse = fit(m, s0, s1, w)
        out[f"{m}_rmse"] = rmse * 100
        out[f"{m}_param"] = c
        out[f"{m}_resid"] = s1 - pred
    # Diagnostic: weighted regression of swing on lean: swing = a + b (s0 - mean)
    x = s0 - np.sum(w * s0) / w.sum()
    X = np.c_[np.ones_like(x), x]
    beta = np.linalg.lstsq(X * np.sqrt(w)[:, None], (s1 - s0) * np.sqrt(w), rcond=None)[0]
    out["slope"] = beta[1]
    out["best"] = min(MODELS, key=lambda m: out[f"{m}_rmse"])
    return out


# -------------------------------------------------------------- analyses ---

def model_table(level: str, df: pd.DataFrame, cycles) -> tuple[pd.DataFrame, dict]:
    rows, keep = [], {}
    for y0, y1 in cycles:
        j = pairs(df, y0, y1)
        if len(j) < 5:
            continue
        e = evaluate(j)
        keep[(y0, y1)] = (j, e)
        rows.append({"level": level, "cycle": f"{y0}->{y1}", "n": e["n"],
                     "nat_swing_pts": round(e["national_swing"] * 100, 2),
                     **{f"{m}_rmse": round(e[f"{m}_rmse"], 2) for m in MODELS},
                     "best": e["best"], "slope_swing_on_lean": round(e["slope"], 3)})
    return pd.DataFrame(rows), keep


def battleground(keep: dict, best_by_cycle: dict, close: float = 0.05) -> pd.DataFrame:
    """Do places that were close last time move differently from the model?
    Residual measured *in the direction of the national swing* (+ = swung more)."""
    rows = []
    for (y0, y1), (j, e) in keep.items():
        m = best_by_cycle.get((y0, y1), "logit")
        r = e[f"{m}_resid"] * np.sign(e["national_swing"])
        bg = np.abs(j.s0.to_numpy() - 0.5) < close
        w = j.w.to_numpy()
        if bg.sum() < 3 or (~bg).sum() < 3:
            continue
        rows.append({"cycle": f"{y0}->{y1}", "model": m, "n_close": int(bg.sum()),
                     "resid_close_pts": round(100 * np.average(r[bg], weights=w[bg]), 2),
                     "resid_other_pts": round(100 * np.average(r[~bg], weights=w[~bg]), 2)})
    return pd.DataFrame(rows)


def switching_vs_turnout(df: pd.DataFrame, y0=2020, y1=2024) -> dict:
    j = pairs(df, y0, y1)
    tot0 = j.dem0 + j.rep0
    dd, dr = (j.dem1 - j.dem0) / tot0, (j.rep1 - j.rep0) / tot0
    w = tot0
    return {
        "counties": len(j),
        "share_D_down_R_up": round(float(np.average((dd < 0) & (dr > 0), weights=w)), 3),
        "share_both_up": round(float(np.average((dd > 0) & (dr > 0), weights=w)), 3),
        "share_both_down": round(float(np.average((dd < 0) & (dr < 0), weights=w)), 3),
        "mean_dD_pct_of_2020_total": round(float(np.average(dd, weights=w) * 100), 2),
        "mean_dR_pct_of_2020_total": round(float(np.average(dr, weights=w) * 100), 2),
        "corr_dD_dR": round(float(np.corrcoef(dd, dr)[0, 1]), 3),
    }


def plot(keep_c: dict, tables: pd.DataFrame, bg: pd.DataFrame, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig = plt.figure(figsize=(19.2, 10.8), dpi=100)
    gs = fig.add_gridspec(2, 3, left=0.05, right=0.98, top=0.9, bottom=0.07, hspace=0.35, wspace=0.25)
    # (1) RMSE by model per cycle and level
    ax = fig.add_subplot(gs[0, :2])
    t = tables.copy()
    t["label"] = t.level + " " + t.cycle
    x = np.arange(len(t))
    for i, m in enumerate(MODELS):
        ax.bar(x + (i - 1) * 0.27, t[f"{m}_rmse"], width=0.27, label=m)
    ax.set_xticks(x, t.label, rotation=60, ha="right", fontsize=8)
    ax.set_ylabel("vote-weighted RMSE (pts)")
    ax.set_title("Prediction error of each swing model (one national parameter per cycle; lower = better)")
    ax.legend()
    # (2) slope diagnostic
    ax = fig.add_subplot(gs[0, 2])
    for lvl, sub in t.groupby("level"):
        ax.scatter(sub.nat_swing_pts, sub.slope_swing_on_lean, label=lvl, s=30)
    xs = np.linspace(min(-8, t.nat_swing_pts.min()), max(8, t.nat_swing_pts.max()), 50)
    ax.plot(xs, -2 * np.abs(xs) / 100, color="tab:orange", lw=1.5, ls="--", label="flip model prediction (−2|swing|)")
    ax.axhline(0, color="grey", lw=0.8, label="uniform / logit ≈ 0")
    ax.axvline(0, color="grey", lw=0.8)
    ax.set_xlabel("national swing toward D (pts)")
    ax.set_ylabel("slope of local swing on prior D share")
    ax.set_title("Does local swing depend on prior lean?")
    ax.legend(fontsize=8)
    # (3)(4) county scatter 2016->20 and 2020->24 with model curves
    for k, cyc in enumerate([(2016, 2020), (2020, 2024)]):
        if cyc not in keep_c:
            continue
        j, e = keep_c[cyc]
        ax = fig.add_subplot(gs[1, k])
        idx = np.random.default_rng(0).choice(len(j), min(len(j), 3000), replace=False)
        ax.scatter(j.s0.iloc[idx], (j.s1 - j.s0).iloc[idx] * 100, s=np.sqrt(j.w.iloc[idx]) / 15,
                   alpha=0.25, color="#555555", linewidths=0)
        ss = np.linspace(0.05, 0.95, 100)
        for m, (f, _) in MODELS.items():
            ax.plot(ss, (f(ss, e[f"{m}_param"]) - ss) * 100, lw=2, label=f"{m} ({e[f'{m}_rmse']:.2f})")
        ax.axhline(0, color="grey", lw=0.6)
        ax.set_xlabel(f"{cyc[0]} D two-party share (county)")
        ax.set_ylabel("swing toward D (pts)")
        ax.set_title(f"Counties {cyc[0]}→{cyc[1]}: local swing vs prior lean (legend: RMSE)")
        ax.legend(fontsize=9)
    # (5) battleground residuals
    ax = fig.add_subplot(gs[1, 2])
    b = bg.copy()
    y = np.arange(len(b))
    ax.barh(y - 0.2, b.resid_close_pts, height=0.4, label="close last time (<5 pts)")
    ax.barh(y + 0.2, b.resid_other_pts, height=0.4, label="others")
    ax.set_yticks(y, b.level + " " + b.cycle, fontsize=8)
    ax.axvline(0, color="grey", lw=0.8)
    ax.set_xlabel("extra swing beyond best model, in direction of national swing (pts)")
    ax.set_title("Battleground effect")
    ax.legend(fontsize=8)
    fig.suptitle("How national swings spread: uniform vs '% flipped' vs logit (differential turnout)", fontsize=16)
    fig.savefig(path)
    plt.close(fig)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    sp = state_pres()
    cp = county_pres()
    hp = house_pairs()
    st_cycles = [(y, y + 4) for y in range(1976, 2021, 4)]
    co_cycles = [(y, y + 4) for y in range(2000, 2021, 4)]
    # House: consecutive elections within a decade of lines (skip y1 ending in 2).
    ho_cycles = [(y, y + 2) for y in range(1976, 2023, 2) if (y + 2) % 10 != 2]

    t_st, k_st = model_table("state", sp, st_cycles)
    t_co, k_co = model_table("county", cp, co_cycles)
    t_ho, k_ho = model_table("house", hp.assign(unit=hp.unit + "|" + hp.decade.astype(str)), ho_cycles)
    tables = pd.concat([t_st, t_co, t_ho], ignore_index=True)
    tables.to_csv(OUT / "model_fit.csv", index=False)

    summary = {}
    for lvl, t in (("state", t_st), ("county", t_co), ("house", t_ho)):
        summary[lvl] = {m: round(float(t[f"{m}_rmse"].mean()), 3) for m in MODELS}
        summary[lvl]["wins"] = t.best.value_counts().to_dict()

    bgs = []
    for lvl, k in (("state", k_st), ("county", k_co), ("house", k_ho)):
        b = battleground(k, {cyc: e["best"] for cyc, (_, e) in k.items()})
        b.insert(0, "level", lvl)
        bgs.append(b)
    bg = pd.concat(bgs, ignore_index=True)
    bg.to_csv(OUT / "battleground.csv", index=False)
    sw = switching_vs_turnout(cp)

    with pd.option_context("display.width", 220, "display.max_rows", 200):
        print(tables.to_string(index=False))
        print("\nmean RMSE (pts) and wins by level:", json.dumps(summary, indent=1))
        print("\nbattleground residuals:\n", bg.to_string(index=False))
        print("\n2020->2024 counties, switching vs turnout:", json.dumps(sw, indent=1))
    (OUT / "summary.json").write_text(json.dumps({"rmse": summary, "switching_vs_turnout": sw}, indent=1))
    plot(k_co, tables, bg, OUT / "swing_models.png")
    print(OUT / "swing_models.png")


if __name__ == "__main__":
    main()
