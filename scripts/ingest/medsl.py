"""MIT Election Data + Science Lab statewide returns (president + Senate, 1976–2024).

Raw files (Harvard Dataverse):
  raw/medsl_president_1976_2024.csv   doi:10.7910/DVN/42MVDX
  raw/medsl_senate_1976_2024.csv      doi:10.7910/DVN/PEJ5QU
"""

from __future__ import annotations

import re

import pandas as pd

from common import RAW, Candidate, Race, norm_party

_MAJOR = {"DEMOCRAT": "Democratic", "REPUBLICAN": "Republican"}


def _pick_party(rows: pd.DataFrame) -> str:
    """Fusion candidates appear once per ballot line; prefer the major-party line."""
    simp = set(rows["party_simplified"].dropna())
    for k, v in _MAJOR.items():
        if k in simp:
            return v
    best = rows.sort_values("candidatevotes", ascending=False)["party_detailed"].dropna()
    return norm_party(best.iloc[0] if len(best) else None)


# Ballots that are not votes for anyone: excluded from candidates AND from the total.
_NOT_A_VOTE = re.compile(r"^(BLANK|OVER ?VOTES?|UNDER ?VOTES?|VOID)", re.I)
INVALID = "__invalid__"


def _clean_name(raw) -> str | None:
    """Normalized candidate name; None = unnamed/scattered votes; INVALID = blank/over/under."""
    if pd.isna(raw):
        return None
    s = str(raw).replace('""', '"').strip()
    if _NOT_A_VOTE.match(s) and "SCATTER" not in s.upper():
        return INVALID
    if s.upper() in {"", "OTHER", "SCATTER", "SCATTERING", "WRITEIN", "WRITE-IN",
                     "BLANK VOTE/SCATTERING", "BLANK VOTE/VOID VOTE/SCATTERING"}:
        return None
    if "," in s:  # "CARTER, JIMMY" -> "JIMMY CARTER"; keep "WYCHE FOWLER, JR." as is
        last, first = s.split(",", 1)
        if not re.fullmatch(r"\s*(JR|SR|II|III|IV)\.?\s*", first, re.I):
            s = f"{first.strip()} {last.strip()}"
    return s.title()


def _races(df: pd.DataFrame, office: str, group_cols: list[str]) -> list[Race]:
    out: list[Race] = []
    df = df.copy()
    df["cname"] = df["candidate"].map(_clean_name)
    invalid = df[df["cname"] == INVALID].groupby(group_cols)["candidatevotes"].sum().to_dict()
    df = df[df["cname"] != INVALID]
    for key, g in df.groupby(group_cols, dropna=False):
        meta = dict(zip(group_cols, key))
        key_t = key if isinstance(key, tuple) else (key,)
        total = int(g["totalvotes"].max()) - int(invalid.get(key_t, 0))
        cands: list[Candidate] = []
        named = g[g["cname"].notna()]
        for cname, cg in named.groupby("cname"):
            cands.append(Candidate(cname, _pick_party(cg), int(cg["candidatevotes"].sum())))
        unnamed = int(g.loc[g["cname"].isna(), "candidatevotes"].sum())
        if unnamed > 0:
            cands.append(Candidate("Other / write-in", "Other", unnamed, lumped=True))
        r = Race(
            office=office,
            year=int(meta["year"]),
            state=meta["state_po"],
            candidates=cands,
            total=max(total, sum(c.votes for c in cands)),
            source="medsl",
            special=bool(meta.get("special", False)),
            stage={"gen": "gen", "runoff": "runoff"}.get(str(meta.get("stage", "gen")).lower(), "gen"),
        )
        if total <= len(cands):  # MEDSL codes uncontested races as 1 vote
            r.notes.append("uncontested (no vote count reported)")
        out.append(r.sorted())
    return out


def president() -> list[Race]:
    df = pd.read_csv(RAW / "medsl_president_1976_2024.csv")
    return _races(df, "president", ["year", "state_po"])


def senate() -> list[Race]:
    df = pd.read_csv(RAW / "medsl_senate_1976_2024.csv", sep=None, engine="python")
    df["special"] = df["special"].astype(str).str.lower().eq("true")
    df["stage"] = df["stage"].str.lower().replace({"gen runoff": "runoff"})
    # GA 1992/2008: MEDSL codes the November general as "pre" and the runoff as "gen".
    ga = (df["state_po"] == "GA") & df["year"].isin([1992, 2008])
    df.loc[ga, "stage"] = df.loc[ga, "stage"].map({"pre": "gen", "gen": "runoff"})
    # Jan 2021 GA runoffs belong to the 2020 cycle.
    df.loc[(df["year"] == 2021) & (df["stage"] == "runoff"), "year"] = 2020
    df = df[df["stage"].isin(["gen", "runoff"])]
    return _races(df, "senate", ["year", "state_po", "special", "stage"])
