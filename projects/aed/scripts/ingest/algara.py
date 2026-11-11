"""Algara & Amlani county-level returns aggregated to the state (D, R, everyone else).

Replication Data for: Partisanship & Nationalization in American Elections ... 1872-2020
doi:10.7910/DVN/DGUMFI  (CC0)
  raw/algara_senate_county.Rdata   Senate 1908-2020 (popular elections from 1914)
  raw/algara_gov_county.Rdata      Governor 1865-2020
  raw/algara_pres_county.Rdata     President 1868-2020 (validation only)

Only Democratic and Republican candidates are named. Every other vote is combined into
one "Other" bloc, which can hide a third-party winner. Those races are flagged.
"""

from __future__ import annotations

import pandas as pd
import pyreadr

from common import RAW, Candidate, Race


def _load(name: str) -> pd.DataFrame:
    return next(iter(pyreadr.read_r(RAW / name).values()))


def _name(raw) -> str | None:
    if raw is None or pd.isna(raw) or str(raw).strip() in {"", "None"}:
        return None
    s = str(raw).strip()
    if "," in s:  # "Bulger, Michael J." -> "Michael J. Bulger"
        last, first = s.split(",", 1)
        s = f"{first.strip()} {last.strip()}"
    return s


def _races(df: pd.DataFrame, office: str) -> list[Race]:
    out: list[Race] = []
    df = df.copy()
    df["democratic_raw_votes"] = df["democratic_raw_votes"].fillna(0)
    df["republican_raw_votes"] = df["republican_raw_votes"].fillna(0)
    df["raw_county_vote_totals"] = df["raw_county_vote_totals"].fillna(0)
    for eid, g in df.groupby("election_id"):
        year = int(g["election_year"].iloc[0])
        state = str(g["state"].iloc[0])
        d = int(g["democratic_raw_votes"].sum())
        r = int(g["republican_raw_votes"].sum())
        tot = int(g["raw_county_vote_totals"].sum())
        if tot <= 0:
            continue
        cands: list[Candidate] = []
        dn, rn = _name(g["dem_nominee"].iloc[0]), _name(g["rep_nominee"].iloc[0])
        if d > 0 or dn:
            cands.append(Candidate(dn or "Democratic nominee", "Democratic", d))
        if r > 0 or rn:
            cands.append(Candidate(rn or "Republican nominee", "Republican", r))
        other = tot - d - r
        if other > 0:
            cands.append(Candidate("Other (combined)", "Other", other, lumped=True))
        race = Race(
            office=office, year=year, state=state, candidates=cands, total=max(tot, d + r),
            source="algara", special=(str(g["election_type"].iloc[0]) == "S"),
            seat=(str(g["seat_class"].iloc[0]) if "seat_class" in g else None),
        ).sorted()
        status = str(g["seat_status"].iloc[0])
        if other > 0 and other >= min(d, r):
            race.notes.append("third-party votes combined into one bloc; may hide a third-party candidate in the top two")
        if "3rd Party" in status or "Third-Party" in status or "Independent" in status:
            race.notes.append(f"seat status: {status}")
        out.append(race)
    return out


def senate() -> list[Race]:
    return _races(_load("algara_senate_county.Rdata"), "senate")


def governor() -> list[Race]:
    return _races(_load("algara_gov_county.Rdata"), "governor")


def president() -> list[Race]:
    """Validation only: the Wikipedia tables are preferred because they name third parties."""
    df = _load("algara_pres_county.Rdata")
    df["election_id"] = df["election_year"].astype(int).astype(str) + " " + df["state"]
    df["seat_class"] = None
    return _races(df.drop(columns=["seat_class"]), "president")
