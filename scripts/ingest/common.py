"""Shared helpers for statewide ingest: state codes, party normalization, race records."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW = REPO_ROOT / "raw"

STATES = {
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
_STATE_KEY = {re.sub(r"[^a-z]", "", k.lower()): v for k, v in STATES.items()}
_STATE_KEY["washingtondc"] = "DC"
_STATE_KEY["dc"] = "DC"


def state_abbr(name: str) -> str | None:
    """'Alabama[a]' / 'ALABAMA' / 'D.C.' -> 'AL'/'DC'; None if not a state."""
    s = re.sub(r"\[.*?\]", "", str(name))
    s = re.sub(r"\(.*?\)", "", s)
    key = re.sub(r"[^a-z]", "", s.lower())
    if key in _STATE_KEY:
        return _STATE_KEY[key]
    if s.strip().upper() in STATES.values() and len(s.strip()) == 2:
        return s.strip().upper()
    return None


# Normalized party names. Order matters: first regex hit wins.
_PARTY_RULES: list[tuple[str, str]] = [
    (r"unpledged", "Unpledged Electors"),
    (r"dixiecrat|states'? ?rights", "States' Rights"),
    (r"southern democrat|texas regulars", "Southern Democratic"),
    (r"\(southern\) democratic|southern democratic", "Southern Democratic"),
    (r"\(northern\) democratic", "Democratic"),
    (r"straight-?out", "Straight-Out Democratic"),
    (r"national democrat", "National Democratic"),
    (r"democratic-republican", "Democratic-Republican"),
    (r"national republican", "National Republican"),
    (r"liberal republican|democratic/liberal", "Democratic"),
    (r"democratic/populist|democratic-farmer|dfl|democrat", "Democratic"),
    (r"national union", "Republican"),
    (r"republican", "Republican"),
    (r"whig", "Whig"),
    (r"american independent", "American Independent"),
    (r"bull moose|progressive", "Progressive"),
    (r"populist|people'?s", "Populist"),
    (r"farmer-?labor", "Farmer-Labor"),
    (r"socialist labor", "Socialist Labor"),
    (r"social democratic|socialist", "Socialist"),
    (r"prohibition", "Prohibition"),
    (r"greenback", "Greenback"),
    (r"free soil", "Free Soil"),
    (r"liberty", "Liberty"),
    (r"constitutional union", "Constitutional Union"),
    (r"know[- ]nothing|\bamerican$|american party", "American"),
    (r"union labor", "Union Labor"),
    (r"independence", "Independence"),
    (r"anti-?masonic", "Anti-Masonic"),
    (r"nullifier", "Nullifier"),
    (r"libertarian", "Libertarian"),
    (r"green", "Green"),
    (r"reform", "Reform"),
    (r"constitution", "Constitution"),
    (r"conservative", "Conservative"),
    (r"communist", "Communist"),
    (r"union", "Union"),
    (r"independent|no party|nonpartisan|unaffiliated", "Independent"),
]


def norm_party(raw: str | None) -> str:
    if raw is None:
        return "Other"
    s = str(raw).strip().lower()
    if not s or s in {"nan", "none", "other", "others"}:
        return "Other"
    for pat, name in _PARTY_RULES:
        if re.search(pat, s):
            return name
    return str(raw).strip().title()


@dataclass
class Candidate:
    name: str
    party: str
    votes: int
    lumped: bool = False  # True = several unidentified candidates combined ("Other")

    def to_json(self) -> dict:
        d = {"name": self.name, "party": self.party, "votes": int(self.votes)}
        if self.lumped:
            d["lumped"] = True
        return d


@dataclass
class Race:
    office: str  # president | senate | governor
    year: int
    state: str  # postal code
    candidates: list[Candidate]
    total: int  # all votes cast for the office (incl. minor + write-ins)
    source: str
    special: bool = False
    stage: str = "gen"  # gen | runoff
    seat: str | None = None  # senate class, when known
    notes: list[str] = field(default_factory=list)

    @property
    def key(self) -> tuple:
        return (self.office, self.year, self.state, self.special, self.stage, self.seat)

    def sorted(self) -> "Race":
        self.candidates.sort(key=lambda c: -c.votes)
        return self

    def to_json(self) -> dict:
        self.sorted()
        d = {
            "office": self.office,
            "year": self.year,
            "state": self.state,
            "total": int(self.total),
            "candidates": [c.to_json() for c in self.candidates],
            "source": self.source,
        }
        if self.special:
            d["special"] = True
        if self.stage != "gen":
            d["stage"] = self.stage
        if self.seat:
            d["seat"] = self.seat
        if self.notes:
            d["notes"] = self.notes
        return d
