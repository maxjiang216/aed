"""Presidential results by state, 1828–1972, from each Wikipedia election article's
"Results by state" table (CC BY-SA 4.0). Fetched pages are cached in raw/wiki/.

Used before 1976 because it names third-party candidates (Weaver, Roosevelt, La Follette,
Thurmond, Wallace, ...) that the Algara file lumps into one "Other" bloc. Every year is
checked against the Algara state D/R totals in build_statewide.py.
"""

from __future__ import annotations

import re
import time
import urllib.request
from io import StringIO

import pandas as pd

from common import RAW, Candidate, Race, norm_party, state_abbr

YEARS = list(range(1828, 1973, 4))
WIKI = RAW / "wiki"
UA = "aed-data-build/0.1 (election data project; contact via github.com/maxjiang216/aed)"

_SKIP_GROUP = re.compile(r"margin|swing|citation|electoral|^ev$|^state|^\[|unnamed|^#$|^%$", re.I)
_TOTAL_GROUP = re.compile(r"total", re.I)


def fetch(year: int) -> str:
    WIKI.mkdir(parents=True, exist_ok=True)
    path = WIKI / f"pres_{year}.html"
    if not path.exists() or path.stat().st_size == 0:
        url = (f"https://en.wikipedia.org/w/index.php?title={year}_United_States_presidential_election"
               "&action=render")
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        path.write_bytes(urllib.request.urlopen(req, timeout=60).read())
        time.sleep(1)
    return path.read_text(encoding="utf-8")


def _num(v) -> int | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = re.sub(r"\[.*?\]", "", str(v)).replace(",", "").replace("−", "-").strip()
    if not s or s in {"–", "—", "-", "N/A", "nan"} or s.lower().startswith("no"):
        return None
    m = re.fullmatch(r"-?\d+(\.0)?", s)
    return int(float(s)) if m else None


def _split_label(label: str) -> tuple[str, str]:
    """'George Wallace American Independent' -> ('George Wallace', 'American Independent')."""
    label = re.sub(r"\[.*?\]", "", label).strip()
    party = norm_party(label)
    m = re.search(r"\s(Democratic|Republican|Whig|National|American|Free|Liberty|Constitutional|"
                  r"Anti|Nullifier|Greenback|Prohibition|Union|Populist|People|Socialist|Social|"
                  r"Progressive|Farmer|Communist|Libertarian|Dixiecrat|States|Southern|Unpledged|"
                  r"Straight|Independence|Liberal|No Candidate)", label)
    name = label[: m.start()].strip() if m else label
    name = re.sub(r"\((Northern|Southern)\)$", "", name).strip()
    if label.lower().startswith("unpledged"):
        name = "Unpledged electors"
    if label.lower().startswith("no candidate"):
        name = "Unpledged electors" if "southern" in label.lower() or "texas" in label.lower() else name
    return name or label, party


def _votes_col(df: pd.DataFrame, group: str):
    subs = [c for c in df.columns if c[0] == group]
    for c in subs:
        if str(c[1]).strip().lower() in {"#", "votes", "vote", "no.", "votes cast", "popular vote"}:
            return c
    for c in subs:  # fall back to the first mostly-integer sub-column that is not EV/%
        if re.search(r"%|elect|ev", str(c[1]), re.I):
            continue
        vals = [_num(v) for v in df[c]]
        if sum(v is not None for v in vals) >= len(vals) * 0.5 and max((v or 0) for v in vals) > 1000:
            return c
    return None


def _pick_table(html: str) -> pd.DataFrame:
    tables = pd.read_html(StringIO(html))
    best, best_n = None, 0
    for t in tables:
        if not isinstance(t.columns, pd.MultiIndex) or t.shape[1] < 6:
            continue
        n = sum(state_abbr(v) is not None for v in t.iloc[:, 0])
        if n > best_n:
            best, best_n = t, n
    if best is None:
        raise ValueError("no results-by-state table")
    return best


def parse(year: int, html: str) -> list[Race]:
    t = _pick_table(html)
    t.columns = pd.MultiIndex.from_tuples([(str(a), str(b)) for a, b in t.columns])
    groups = list(dict.fromkeys(c[0] for c in t.columns))
    cand_cols, total_col = [], None
    for g in groups:
        if _TOTAL_GROUP.search(g):
            total_col = _votes_col(t, g) or next(c for c in t.columns if c[0] == g)
        elif g.strip().lower() in {"other", "others"}:
            col = _votes_col(t, g)
            if col:
                cand_cols.append((("Other", "Other"), col, True))
        elif not _SKIP_GROUP.search(g.strip()) and not g.lower().startswith("state"):
            col = _votes_col(t, g)
            if col:
                cand_cols.append((_split_label(g), col, False))
    races: list[Race] = []
    seen: set[str] = set()
    for _, row in t.iterrows():
        st = state_abbr(row.iloc[0])
        if st is None or st in seen:  # skip ME/NE district rows, totals, repeated header rows
            continue
        by_key: dict[tuple[str, str], Candidate] = {}
        for (name, party), col, lumped in cand_cols:
            v = _num(row[col])
            if not v:
                continue
            k = (party, name if party in {"Other", "Unpledged Electors"} else party)
            if k in by_key:  # e.g. 1836's four regional Whig candidates in one state
                by_key[k].votes += v
                if name not in by_key[k].name:
                    by_key[k].name += f" / {name}"
            else:
                by_key[k] = Candidate("Other (combined)" if lumped else name, party, v, lumped=lumped)
        cands = list(by_key.values())
        if not cands:
            continue  # legislature chose electors; no popular vote
        s = sum(c.votes for c in cands)
        total = _num(row[total_col]) if total_col is not None else None
        notes = []
        if total is None or total < s:
            total = s
        elif total > s * 1.0005:
            cands.append(Candidate("Other (combined)", "Other", total - s, lumped=True))
            notes.append("minor candidates not in source table combined")
        seen.add(st)
        races.append(Race("president", year, st, cands, total, "wikipedia", notes=notes).sorted())
    return races


def president() -> list[Race]:
    out: list[Race] = []
    for y in YEARS:
        out.extend(parse(y, fetch(y)))
    return out
