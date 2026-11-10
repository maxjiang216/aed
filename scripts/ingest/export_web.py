#!/usr/bin/env python3
"""Write the web app's data files into public/data/ from data/statewide.json + county returns.

  public/data/index.json                     offices, levels, years
  public/data/statewide/<office>.json        {"<year>": {"<ST>": [race, ...]}}
  public/data/county/president/<year>.json   {"<fips5>": race}

race = {"c": [[name, party, votes, flag], ...], "t": total, ...}
  flag 0 = named candidate
       1 = unnamed bloc that may be one real contender (source only names D and R)
       2 = several minor candidates / scattered write-ins folded together; never a contender
  optional: "s": 1 special, "r": 1 runoff, "k": "I"|"II"|"III" Senate class, "n": [notes], "src"
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RAW, REPO_ROOT  # noqa: E402

OUT = REPO_ROOT / "public" / "data"
KEEP = 6  # named candidates kept per race; the rest fold into one "Others" row
CLASS_BY_MOD6 = {0: "III", 2: "I", 4: "II"}  # regular Senate elections: year % 6


def compact(cands: list[dict], total: int, keep: int = KEEP, may_hide_contender: bool = False) -> dict:
    """may_hide_contender: the source's unnamed bloc could be one real candidate (Algara,
    Wikipedia leftovers) -> flag 1. Otherwise unnamed votes are scattered write-ins -> flag 2."""
    cands = sorted(cands, key=lambda c: -c["votes"])
    rows, rest = [], 0
    for i, c in enumerate(cands):
        if c.get("lumped"):
            rows.append([c["name"], c["party"], int(c["votes"]), 1 if may_hide_contender else 2])
        elif i < keep:
            rows.append([c["name"], c["party"], int(c["votes"]), 0])
        else:
            rest += int(c["votes"])
    if rest > 0:
        rows.append(["Others", "Other", rest, 2])
    rows.sort(key=lambda r: -r[2])
    return {"c": rows, "t": int(total)}


def statewide() -> dict[str, list[int]]:
    data = json.loads((REPO_ROOT / "data" / "statewide.json").read_text(encoding="utf-8"))
    by_office: dict[str, dict] = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    for r in data["races"]:
        if r["total"] <= 0:
            continue
        race = compact(r["candidates"], r["total"],
                       may_hide_contender=r["source"] in {"algara", "curated+algara", "wikipedia"})
        if r.get("special"):
            race["s"] = 1
        if r.get("stage") == "runoff":
            race["r"] = 1
        if r["office"] == "senate":
            seat = r.get("seat")
            if seat:
                race["k"] = seat.replace("Class ", "")
            elif not r.get("special") and r["year"] % 2 == 0:
                race["k"] = CLASS_BY_MOD6[r["year"] % 6]
        if r.get("notes"):
            race["n"] = r["notes"]
        race["src"] = r["source"]
        by_office[r["office"]][str(r["year"])][r["state"]].append(race)
    (OUT / "statewide").mkdir(parents=True, exist_ok=True)
    years = {}
    for office, ys in by_office.items():
        (OUT / "statewide" / f"{office}.json").write_text(
            json.dumps(ys, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")
        years[office] = sorted(int(y) for y in ys)
    return years


def _county_name(raw) -> str | None:
    if pd.isna(raw):
        return None
    s = str(raw).strip()
    if s.upper() in {"OTHER", "", "WRITEIN", "WRITE-IN"}:
        return None
    if "," in s:
        last, first = s.split(",", 1)
        s = f"{first.strip()} {last.strip()}"
    return s.title()


def county_president() -> list[int]:
    """MEDSL county presidential returns. Prefers raw/medsl_countypres_2000_2024.csv
    (needs a manual Dataverse download, doi:10.7910/DVN/VOQCHQ), else the 2000–2020 copy in MIT/."""
    src = RAW / "medsl_countypres_2000_2024.csv"
    if not src.exists():
        src = REPO_ROOT / "MIT" / "countypres_2000-2020.csv"
    df = pd.read_csv(src, dtype={"county_fips": str})
    df.loc[df["state_po"] == "DC", "county_fips"] = "11001"
    df = df[df["county_fips"].notna()].copy()
    df["county_fips"] = df["county_fips"].str.replace(r"\.0$", "", regex=True).str.zfill(5)
    df["cname"] = df["candidate"].map(_county_name)
    party_map = {"DEMOCRAT": "Democratic", "REPUBLICAN": "Republican", "GREEN": "Green",
                 "LIBERTARIAN": "Libertarian"}
    df["pname"] = df["party"].map(lambda p: party_map.get(str(p).upper(), "Other"))
    out_dir = OUT / "county" / "president"
    out_dir.mkdir(parents=True, exist_ok=True)
    years = []
    for year, g in df.groupby("year"):
        # Some states report by mode (election day, absentee, ...) as well as TOTAL; use TOTAL
        # where it exists so modes are not double counted.
        has_total = g[g["mode"].str.upper() == "TOTAL"]["county_fips"].unique()
        g = g[(g["mode"].str.upper() == "TOTAL") | ~g["county_fips"].isin(has_total)]
        res = {}
        for fips, cg in g.groupby("county_fips"):
            cands = []
            for name, nn in cg[cg["cname"].notna()].groupby("cname"):
                cands.append({"name": name, "party": nn["pname"].iloc[0], "votes": int(nn["candidatevotes"].sum())})
            other = int(cg.loc[cg["cname"].isna(), "candidatevotes"].sum())
            if other > 0:
                cands.append({"name": "Other / write-in", "party": "Other", "votes": other, "lumped": True})
            total = max(int(cg.groupby("mode")["totalvotes"].max().sum()), sum(c["votes"] for c in cands))
            if total > 0:
                res[fips] = compact(cands, total, keep=3)
        (out_dir / f"{int(year)}.json").write_text(json.dumps(res, separators=(",", ":")), encoding="utf-8")
        years.append(int(year))
    return sorted(years)


def main() -> None:
    sw = statewide()
    county = county_president()
    index = {
        "offices": {
            "president": {"state": sw.get("president", []), "county": county},
            "senate": {"state": sw.get("senate", [])},
            "governor": {"state": sw.get("governor", [])},
        },
        "sources": json.loads((REPO_ROOT / "data" / "statewide.json").read_text())["sources"],
    }
    index["sources"]["medsl_county"] = ("MIT Election Data + Science Lab, County Presidential Election "
                                        "Returns, Harvard Dataverse doi:10.7910/DVN/VOQCHQ")
    (OUT / "index.json").write_text(json.dumps(index, separators=(",", ":")), encoding="utf-8")
    for p in sorted(OUT.rglob("*.json")):
        print(f"{p.relative_to(REPO_ROOT)}  {p.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
