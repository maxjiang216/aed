#!/usr/bin/env python3
"""Build data/statewide.json: every statewide race (president, Senate, governor) we have.

Run locally (needs pandas, pyreadr, lxml — see scripts/ingest/requirements.txt):
    python3 scripts/ingest/fetch_sources.py
    python3 scripts/ingest/build_statewide.py

Source per office and era (first match wins):
  president  1976–2024  MEDSL                     all candidates, official totals
             1828–1972  Wikipedia state tables    names third parties; checked vs Algara
  senate     1976–2024  MEDSL                     incl. specials and runoffs
             1908–1974  Algara & Amlani           D, R, combined Other
  governor   1959–2021  curated elections/*.txt   merged onto Algara for names + totals
             1865–2020  Algara & Amlani           D, R, combined Other

Also writes data/statewide_report.md with races that need a human look.
"""

from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import algara  # noqa: E402
import curated  # noqa: E402
import medsl  # noqa: E402
import overrides  # noqa: E402
import wiki_president  # noqa: E402
from common import REPO_ROOT, Candidate, Race  # noqa: E402


def _votes(r: Race, party: str) -> int:
    return sum(c.votes for c in r.candidates if c.party == party)


def merge_governor(alg: list[Race], cur: list[Race], report: list[str]) -> list[Race]:
    a_by = defaultdict(list)
    for r in alg:
        a_by[(r.year, r.state)].append(r)
    out: list[Race] = []
    used = set()
    for c in cur:
        k = (c.year, c.state)
        a = a_by.get(k, [None])[0] if len(a_by.get(k, [])) == 1 else None
        if a is None:
            out.append(c)
            continue
        used.add(k)
        names = {x.party: x.name for x in a.candidates if not x.lumped}
        cands = [Candidate(names.get(x.party, x.name), x.party, x.votes) for x in c.candidates]
        s = sum(x.votes for x in cands)
        curated_total_known = not any("total missing" in n for n in c.notes)
        total = c.total if curated_total_known else max(a.total, s)
        if total > s:
            cands.append(Candidate("Other (combined)", "Other", total - s, lumped=True))
        merged = Race("governor", c.year, c.state, cands, total, "curated+algara").sorted()
        for p in ("Democratic", "Republican"):
            cv, av = _votes(c, p), _votes(a, p)
            if abs(cv - av) > 0.01 * max(a.total, 1):
                merged.notes.append(f"curated {p} {cv:,} differs from Algara {av:,}")
        out.append(merged)
    for k, rs in a_by.items():
        if k not in used:
            out.extend(rs)
    return out


def pick(*layers: list[Race]) -> list[Race]:
    """Earlier layers win for the same (office, year, state, special, stage)."""
    seen: dict[tuple, Race] = {}
    for layer in layers:
        claimed = {(r.office, r.year) for r in layer}
        for r in layer:
            k = (r.office, r.year, r.state, r.special, r.stage)
            if k not in seen:
                seen[k] = r
        del claimed
    return list(seen.values())


def by_year(races: list[Race], lo: int | None = None, hi: int | None = None) -> list[Race]:
    return [r for r in races if (lo is None or r.year >= lo) and (hi is None or r.year <= hi)]


def main() -> None:
    report: list[str] = []
    print("loading MEDSL ...")
    m_pres, m_sen = medsl.president(), medsl.senate()
    print("loading Wikipedia president tables ...")
    w_pres = wiki_president.president()
    print("loading Algara & Amlani ...")
    a_sen, a_gov, a_pres = algara.senate(), algara.governor(), algara.president()
    c_gov = curated.governor()

    races: list[Race] = []
    races += pick(m_pres, by_year(w_pres, hi=1972))
    races += pick(m_sen, by_year(a_sen, hi=1974))
    races += merge_governor(a_gov, c_gov, report)
    for msg in overrides.apply(races):
        print("WARNING:", msg)

    # --- checks -------------------------------------------------------------------------
    a_pres_by = {(r.year, r.state): r for r in a_pres}
    pres_diffs = []
    for r in races:
        if r.office != "president" or r.source != "wikipedia":
            continue
        a = a_pres_by.get((r.year, r.state))
        if not a:
            continue
        for p in ("Democratic", "Republican"):
            d = abs(_votes(r, p) - _votes(a, p)) / max(a.total, 1)
            if d > 0.01:
                pres_diffs.append(f"| {r.year} | {r.state} | {p} | {_votes(r, p):,} | {_votes(a, p):,} |")

    lumped_first, lumped_second = [], []
    for r in races:
        r.sorted()
        top2 = r.candidates[:2]
        if any(c.lumped for c in top2):
            (lumped_first if top2[0].lumped else lumped_second).append(f"| {r.office} | {r.year} | {r.state}{' (special)' if r.special else ''} "
                               f"| {r.source} | {'; '.join(r.notes)} |")

    flagged = [r for r in races if r.notes and r.source != "algara"]

    races.sort(key=lambda r: (r.office, r.year, r.state, r.special, r.stage != "gen"))
    out = {
        "schema": 1,
        "description": "U.S. statewide general-election results. Margin = (1st - 2nd) / total.",
        "sources": {
            "medsl": "MIT Election Data + Science Lab, Harvard Dataverse doi:10.7910/DVN/42MVDX "
                     "(president) and doi:10.7910/DVN/PEJ5QU (Senate)",
            "wikipedia": "Results-by-state tables of the English Wikipedia article for each "
                         "presidential election (CC BY-SA 4.0)",
            "algara": "Algara & Amlani, Harvard Dataverse doi:10.7910/DVN/DGUMFI; county returns "
                      "summed to state; only D and R are named",
            "curated": "Hand-entered AED tab files (elections/US_governor_state)",
        },
        "races": [r.to_json() for r in races],
    }
    data_dir = REPO_ROOT / "data"
    data_dir.mkdir(exist_ok=True)
    (data_dir / "statewide.json").write_text(
        json.dumps(out, separators=(",", ":"), ensure_ascii=False), encoding="utf-8")

    cov = defaultdict(Counter)
    for r in races:
        cov[r.office][r.source] += 1
    span = defaultdict(lambda: [9999, 0])
    for r in races:
        s = span[(r.office, r.source)]
        s[0], s[1] = min(s[0], r.year), max(s[1], r.year)
    lines = ["# Statewide data report", "", "Generated by `scripts/ingest/build_statewide.py`.", "",
             "## Coverage", "", "| office | source | races | years |", "|---|---|---|---|"]
    for (office, source), (lo, hi) in sorted(span.items()):
        lines.append(f"| {office} | {source} | {cov[office][source]} | {lo}–{hi} |")
    hdr = ["| office | year | state | source | notes |", "|---|---|---|---|---|"]
    lines += ["", f"## Winner unknown: combined 'Other' bloc finished first ({len(lumped_first)})", "",
              "The source lumps every non-D/R vote together, so the real winner is not named. "
              "Fix with a named source or an override.", "", *hdr, *lumped_first,
              "", f"## Runner-up is a combined 'Other' bloc ({len(lumped_second)})", "",
              "Margin is exact if the bloc is one candidate (common: lone minor-party or write-in "
              "opponent in an uncontested race), otherwise understated.", "", *hdr, *lumped_second,
              "", f"## President: Wikipedia vs Algara county sums, >1% of total ({len(pres_diffs)})", "",
              "Usually fusion tickets, alternate ballot lines or county-sum errors in Algara.", "",
              "| year | state | party | wikipedia | algara |", "|---|---|---|---|---|", *pres_diffs,
              "", f"## Other notes ({len(flagged)})", ""]
    lines += [f"- {r.office} {r.year} {r.state}{' special' if r.special else ''}"
              f"{' ' + r.stage if r.stage != 'gen' else ''}: {'; '.join(r.notes)}" for r in flagged]
    (data_dir / "statewide_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {len(races)} races; {len(lumped_first)} with unknown winner, "
          f"{len(lumped_second)} with a combined runner-up")
    for (office, source), (lo, hi) in sorted(span.items()):
        print(f"  {office:9} {source:15} {cov[office][source]:5}  {lo}-{hi}")


if __name__ == "__main__":
    main()
