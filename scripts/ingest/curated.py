"""Hand-curated tab files in elections/<type>/<year>.txt (original AED data).

Kept for governors 1959–2021, where they carry editorial calls from flavor/explanation.txt
(third-party winners, runoffs, who a candidate "counts as"). They have party columns only,
no candidate names, and the Total column is sometimes missing (then it is the sum of the
listed parties), so build_statewide.py merges them onto the Algara rows for names and totals.
"""

from __future__ import annotations

from common import REPO_ROOT, Candidate, Race, norm_party, state_abbr


def _parse(path) -> list[tuple[str, dict[str, int], int | None]]:
    parties: list[str] = []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = line.rstrip("\n").split("\t")
        if not cells or not cells[0]:
            continue
        if cells[0] == "_PARTIES":
            parties = [norm_party(p) if p != "Total" else "Total" for p in cells[1:]]
            continue
        if cells[0].startswith("_"):
            continue
        st = state_abbr(cells[0])
        if st is None:
            continue
        votes: dict[str, int] = {}
        total = None
        for p, v in zip(parties, cells[1:]):
            v = v.strip()
            if not v:
                continue
            if p == "Total":
                total = int(v)
            elif int(v) > 0:
                votes[p] = int(v)
        rows.append((st, votes, total))
    return rows


def governor() -> list[Race]:
    out: list[Race] = []
    for path in sorted((REPO_ROOT / "elections" / "US_governor_state").glob("*.txt")):
        year = int(path.stem)
        for st, votes, total in _parse(path):
            cands = [Candidate(f"{p} nominee", p, v) for p, v in votes.items()]
            s = sum(votes.values())
            r = Race("governor", year, st, cands, max(total or 0, s), "curated")
            if total is None:
                r.notes.append("curated total missing; sum of listed parties")
            out.append(r.sorted())
    return out
