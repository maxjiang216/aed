"""U.S. House general elections by district, 1976–2024, from MEDSL.

Source: MIT Election Data + Science Lab, "U.S. House 1976–2024", Harvard Dataverse
doi:10.7910/DVN/IG0UN2. Dataverse requires a guestbook form for this file, so it is a
manual download: save it as raw/medsl_house_1976_2024.csv (or .tab).

Output rows use the same Race shape as the statewide data, keyed by district id "CA-12"
("WY-AL" for at-large seats).
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from common import RAW
from medsl import INVALID, _clean_name, _pick_party

NON_STATES = {"DC", "AS", "GU", "MP", "PR", "VI"}


def source_file() -> Path | None:
    for name in ("medsl_house_1976_2024.csv", "medsl_house_1976_2024.tab", "1976-2024-house.tab",
                 "1976-2024-house.csv"):
        p = RAW / name
        if p.exists() and p.stat().st_size > 100_000:  # not a saved error page
            return p
    return None


def district_id(state: str, district) -> str:
    n = int(float(district)) if str(district).strip() not in {"", "nan"} else 0
    return f"{state}-{'AL' if n == 0 else f'{n:02d}'}"


def load() -> pd.DataFrame:
    path = source_file()
    if path is None:
        raise FileNotFoundError(
            "MEDSL House file missing: download doi:10.7910/DVN/IG0UN2 (1976-2024-house) "
            "to raw/medsl_house_1976_2024.csv")
    df = pd.read_csv(path, sep=None, engine="python", dtype={"district": str})
    df.columns = [c.lower() for c in df.columns]
    df = df[~df["state_po"].isin(NON_STATES)].copy()
    stage = df.get("stage", pd.Series("gen", index=df.index)).astype(str).str.lower()
    df = df[stage.isin(["gen", "gen runoff", "runoff"])].copy()
    runoff = stage.loc[df.index].str.contains("runoff")
    if "runoff" in df.columns:
        runoff |= df["runoff"].astype(str).str.lower().eq("true")
    df["is_runoff"] = runoff
    df["is_special"] = df.get("special", False).astype(str).str.lower().eq("true")
    df["candidatevotes"] = pd.to_numeric(df["candidatevotes"], errors="coerce")
    df["totalvotes"] = pd.to_numeric(df["totalvotes"], errors="coerce")
    df["did"] = [district_id(s, d) for s, d in zip(df["state_po"], df["district"])]
    # Single-seat states are at-large whatever number the source gives them.
    n_seats = df.groupby(["year", "state_po"])["did"].transform("nunique")
    df.loc[n_seats == 1, "did"] = df.loc[n_seats == 1, "state_po"] + "-AL"
    if "party" in df.columns and "party_detailed" not in df.columns:
        df["party_detailed"] = df["party"]
    if "party_simplified" not in df.columns:
        df["party_simplified"] = df["party_detailed"].astype(str).str.upper().map(
            lambda p: "DEMOCRAT" if re.search(r"DEMOCRAT", p) else "REPUBLICAN" if "REPUBLICAN" in p else "OTHER")
    return df


def races() -> dict[int, dict[str, list[dict]]]:
    """year -> district id -> list of race dicts (statewide.json race format, plus "u" when
    the winner was unopposed and no vote count was reported)."""
    df = load()
    df["cname"] = df["candidate"].map(_clean_name)
    df = df[df["cname"] != INVALID]
    out: dict[int, dict[str, list[dict]]] = {}
    for (year, did, special, runoff), g in df.groupby(["year", "did", "is_special", "is_runoff"]):
        cands = []
        for cname, cg in g[g["cname"].notna()].groupby("cname"):
            votes = cg["candidatevotes"].sum(min_count=1)
            cands.append({"name": cname, "party": _pick_party(cg.fillna({"candidatevotes": 0})),
                          "votes": 0 if pd.isna(votes) else int(votes)})
        unnamed = g.loc[g["cname"].isna(), "candidatevotes"].sum()
        if unnamed and unnamed > 0:
            cands.append({"name": "Other / write-in", "party": "Other", "votes": int(unnamed), "lumped": True})
        if not cands:
            continue
        total = max(int(g["totalvotes"].max()) if g["totalvotes"].notna().any() else 0,
                    sum(c["votes"] for c in cands))
        race = {"candidates": sorted(cands, key=lambda c: -c["votes"]), "total": total}
        named = [c for c in cands if not c.get("lumped")]
        # Unopposed: one named candidate and no meaningful count (MEDSL uses NaN, 0 or 1).
        if len(named) == 1 and named[0]["votes"] <= 1:
            race["unopposed"] = True
            race["total"] = max(race["total"], 1)
            named[0]["votes"] = max(named[0]["votes"], 1)
        if special:
            race["special"] = True
        if runoff:
            race["stage"] = "runoff"
        out.setdefault(int(year), {}).setdefault(did, []).append(race)
    return out
