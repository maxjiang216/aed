"""Counterfactual: apportion the House (and so the Electoral College) by citizen
population instead of total population, 2020 census.

Citizen apportionment population per state =
    2020 resident population * citizen share (ACS 2016-2020 CVAP special tab, CIT_EST/TOT_EST)
    + overseas federal count (apportionment pop - resident pop; assumed all citizens).

Method of Equal Proportions, 435 seats, 1 minimum. Baseline (total population) must reproduce
the official 2020 apportionment. EC = seats + 2 (DC fixed at 3). Presidential results 2000-2024
are rerun under both apportionments (2020-census baseline for both, so the only change is the
population measure). ME/NE congressional-district splits use the actual split electors.

Usage: python -m districting.citizen_apportion
Outputs: output/citizen/{states.csv, elections.csv, summary.txt, citizen_apportion.png}
"""

from __future__ import annotations

import heapq
import math
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw" / "citizen"
AED = Path.home() / "projects" / "aed"
OUT = ROOT / "output" / "citizen"

ABBR = {
    "Alabama": "AL", "Alaska": "AK", "Arizona": "AZ", "Arkansas": "AR", "California": "CA",
    "Colorado": "CO", "Connecticut": "CT", "Delaware": "DE", "District of Columbia": "DC",
    "Florida": "FL", "Georgia": "GA", "Hawaii": "HI", "Idaho": "ID", "Illinois": "IL",
    "Indiana": "IN", "Iowa": "IA", "Kansas": "KS", "Kentucky": "KY", "Louisiana": "LA",
    "Maine": "ME", "Maryland": "MD", "Massachusetts": "MA", "Michigan": "MI", "Minnesota": "MN",
    "Mississippi": "MS", "Missouri": "MO", "Montana": "MT", "Nebraska": "NE", "Nevada": "NV",
    "New Hampshire": "NH", "New Jersey": "NJ", "New Mexico": "NM", "New York": "NY",
    "North Carolina": "NC", "North Dakota": "ND", "Ohio": "OH", "Oklahoma": "OK", "Oregon": "OR",
    "Pennsylvania": "PA", "Rhode Island": "RI", "South Carolina": "SC", "South Dakota": "SD",
    "Tennessee": "TN", "Texas": "TX", "Utah": "UT", "Vermont": "VT", "Virginia": "VA",
    "Washington": "WA", "West Virginia": "WV", "Wisconsin": "WI", "Wyoming": "WY",
}

# Actual split electors (D, R) in ME/NE where they split; otherwise winner-take-all.
SPLITS = {(2008, "NE"): (1, 4), (2016, "ME"): (3, 1), (2020, "ME"): (3, 1), (2020, "NE"): (1, 4),
          (2024, "ME"): (3, 1), (2024, "NE"): (1, 4)}


def load() -> pd.DataFrame:
    app = pd.read_excel(RAW / "app2020.xlsx", header=None, skiprows=4).iloc[:, :3]
    app.columns = ["state", "app_pop", "seats_official"]
    res = pd.read_excel(RAW / "apportionment-2020-table02.xlsx", header=None, skiprows=4).iloc[:, :2]
    res.columns = ["state", "res_pop"]
    cv = pd.read_csv(RAW / "cvap2020" / "State.csv", encoding="latin-1")
    cv = cv[cv.lnnumber == 1].rename(columns={"geoname": "state"})[["state", "tot_est", "cit_est"]]
    df = app.merge(res, on="state").merge(cv, on="state")
    df = df[df.state.isin(ABBR) & (df.state != "District of Columbia")].copy()
    assert len(df) == 50, len(df)
    df["st"] = df.state.map(ABBR)
    df["overseas"] = df.app_pop - df.res_pop
    df["cit_share"] = df.cit_est / df.tot_est
    df["cit_app_pop"] = (df.res_pop * df.cit_share + df.overseas).round().astype(int)
    return df.set_index("st").sort_index()


def huntington_hill(pop: pd.Series, n: int = 435) -> tuple[pd.Series, list]:
    cnt = pd.Series(1, index=pop.index)
    heap = [(-p / math.sqrt(2), s) for s, p in pop.items()]
    heapq.heapify(heap)
    order = []  # (seat number, state, priority value)
    for k in range(len(pop) + 1, n + 11):  # 10 extra to show the next-in-line
        if k == n + 1:
            seats = cnt.copy()
        pv, s = heapq.heappop(heap)
        order.append((k, s, -pv))
        cnt[s] += 1
        heapq.heappush(heap, (-pop[s] / math.sqrt(cnt[s] * (cnt[s] + 1)), s))
    return seats, order


def pres() -> pd.DataFrame:
    p = pd.read_csv(AED / "raw" / "medsl_president_1976_2024.csv", low_memory=False)
    p = p[p.party_simplified.isin(["DEMOCRAT", "REPUBLICAN"]) & (p.year >= 2000)]
    t = p.pivot_table(index=["year", "state_po"], columns="party_simplified", values="candidatevotes",
                      aggfunc="sum").rename(columns={"DEMOCRAT": "dem", "REPUBLICAN": "rep"})
    return t.reset_index()


def ec(results: pd.DataFrame, ev: pd.Series) -> tuple[int, int]:
    d = r = 0
    for row in results.itertuples():
        n = ev[row.state_po]
        if (row.year, row.state_po) in SPLITS:
            sd, sr = SPLITS[(row.year, row.state_po)]
            assert sd + sr == n, (row.year, row.state_po, n)  # ME/NE totals unchanged
            d, r = d + sd, r + sr
        elif row.dem > row.rep:
            d += n
        else:
            r += n
    return d, r


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    df = load()
    base, base_order = huntington_hill(df.app_pop)
    assert (base == df.seats_official).all(), "baseline does not reproduce official 2020 apportionment"
    cit, cit_order = huntington_hill(df.cit_app_pop)
    df["seats_total"] = base
    df["seats_citizen"] = cit
    df["delta"] = cit - base
    df.to_csv(OUT / "states.csv")

    ev_t = pd.concat([base + 2, pd.Series({"DC": 3})])
    ev_c = pd.concat([cit + 2, pd.Series({"DC": 3})])
    rows = []
    for y, g in pres().groupby("year"):
        dt, rt = ec(g, ev_t)
        dc, rc = ec(g, ev_c)
        rows.append(dict(year=y, D_total=dt, R_total=rt, D_citizen=dc, R_citizen=rc, R_gain=rc - rt))
    el = pd.DataFrame(rows)
    el.to_csv(OUT / "elections.csv", index=False)

    ch = df[df.delta != 0].sort_values("delta")
    lines = ["Citizen-population apportionment, 2020 census (ACS 2016-2020 citizen share)\n",
             f"US citizen share (50 states): {df.cit_est.sum() / df.tot_est.sum():.3f}",
             f"Seats moved: {int(ch.delta.clip(lower=0).sum())}\n",
             "Changed states (seats total-pop -> citizen-pop, citizen share):"]
    lines += [f"  {s}: {r.seats_total} -> {r.seats_citizen} ({r.delta:+d})  cit share {r.cit_share:.3f}"
              for s, r in ch.iterrows()]
    lines.append("\nLast seats / next in line, citizen apportionment (seat#, state, priority):")
    lines += [f"  {k}{'*' if k > 435 else ' '} {s} {pv:,.0f}" for k, s, pv in cit_order if k >= 428]
    lines.append("\nLast seats / next in line, actual (total-pop) apportionment:")
    lines += [f"  {k}{'*' if k > 435 else ' '} {s} {pv:,.0f}" for k, s, pv in base_order if k >= 428]
    lines.append("\nElectoral College (both on 2020-census apportionment):")
    lines.append(el.to_string(index=False))
    txt = "\n".join(lines)
    (OUT / "summary.txt").write_text(txt + "\n")
    print(txt)

    fig, axes = plt.subplots(1, 2, figsize=(19.2, 10.8), dpi=100)
    a = df.sort_values("cit_share")
    colors = ["tab:red" if d < 0 else "tab:green" if d > 0 else "0.7" for d in a.delta]
    axes[0].barh(a.index, a.cit_share, color=colors)
    axes[0].set_xlim(0.8, 1.0)
    axes[0].set_title("Citizen share of population (ACS 2016-20)\nred = loses seat(s), green = gains")
    for i, (s, r) in enumerate(a.iterrows()):
        if r.delta:
            axes[0].text(r.cit_share + 0.002, i, f"{r.delta:+d}", va="center", fontsize=9)
    axes[0].tick_params(axis="y", labelsize=7)
    ax = axes[1]
    x = range(len(el))
    ax.bar([i - 0.2 for i in x], el.R_total, 0.4, label="R EV, total-pop apportionment", color="#d88")
    ax.bar([i + 0.2 for i in x], el.R_citizen, 0.4, label="R EV, citizen-pop apportionment", color="#a22")
    ax.axhline(270, color="k", lw=1, ls="--")
    for i, r in el.iterrows():
        ax.text(i, max(r.R_total, r.R_citizen) + 3, f"{r.R_gain:+d}", ha="center")
    ax.set_xticks(list(x), el.year)
    ax.set_ylim(150, 330)
    ax.set_title("Republican electoral votes (2020-census apportionment both bars)")
    ax.legend(loc="lower right")
    fig.tight_layout()
    fig.savefig(OUT / "citizen_apportion.png")


if __name__ == "__main__":
    main()
