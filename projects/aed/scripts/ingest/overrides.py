"""Hand corrections applied after all sources are merged.

Each entry matches one race by (office, year, state[, special, stage]) and applies one action.
Every entry needs a `why` and, where numbers change, a `source`. Prefer fixing upstream data
over adding entries here.

Actions:
  name_lumped  give the combined "Other" bloc a name/party when it is known to be one ticket
"""

from __future__ import annotations

from common import Race

OVERRIDES: list[dict] = [
    *[
        {
            "match": {"office": "president", "year": 1860, "state": st},
            "action": "name_lumped",
            "name": "Fusion ticket (Douglas–Bell–Breckinridge)",
            "party": "Fusion",
            "why": "Anti-Lincoln parties ran a joint elector slate; the Wikipedia table lists it "
                   "outside the candidate columns. Bloc may include a few scattered votes.",
        }
        for st in ("NJ", "NY", "PA")
    ],
]


def _matches(r: Race, m: dict) -> bool:
    return all(getattr(r, k) == v for k, v in m.items())


def apply(races: list[Race]) -> list[str]:
    log: list[str] = []
    for o in OVERRIDES:
        hits = [r for r in races if _matches(r, o["match"])]
        if len(hits) != 1:
            log.append(f"override matched {len(hits)} races: {o['match']}")
            continue
        r = hits[0]
        if o["action"] == "name_lumped":
            for c in r.candidates:
                if c.lumped:
                    c.name, c.party, c.lumped = o["name"], o["party"], False
                    r.notes.append(f"override: {o['why']}")
                    break
        else:
            log.append(f"unknown action {o['action']}")
    return log
