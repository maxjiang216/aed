#!/usr/bin/env python3
"""Party composition of the House and Senate over time, from @unitedstates/congress-legislators
(public domain): every term of every member since 1789, with real exit dates for deaths and
resignations and dated party switches (`party_affiliations`).

Writes public/data/congress/seats.json:

  {"parties": [label, ...],
   "house"|"senate": {"t": [date, ...],          # change points, ISO dates
                      "seats": [n, ...],         # seats that exist at t
                      "n": [[party idx, count, ...], ...],   # filled seats by party
                      "dc": [n, ...], "rc": [n, ...],         # Dem / Rep incl. caucusing independents
                      "ev": [[[+1|-1, name, party idx, state], ...], ...]}}  # who came / went at t

Counts hold from t[i] until t[i+1]. Vacant = seats - sum(n).

Cleanup applied to the raw terms:
- Before 1935, terms list the date the member first sat (often December), not the date the
  Congress began (March 4). Terms that start no later than the most common start date of their
  Congress (+3 days) are moved back to the Congress's start; later starts are real mid-Congress
  arrivals (special elections, appointments, late seatings). Same for regular ends within 3 days
  of the next Congress's start, so swearing-in gaps (Jan 3 vs Jan 5) don't show as vacancies.
- House: territorial delegates and non-voting members (DC, PR, GU, ...) are dropped by keeping
  only terms of states that had been admitted.
- Seats: Senate = 2 x admitted states. House = 435 from 1913 (436/437 for Alaska and Hawaii until
  the 1963 reapportionment); before 1913 the apportionment changed often, so seats = the most
  members sitting at once during that Congress, and vacancies before 1913 are a lower bound.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

import congress_wiki as cw
from common import STATES as STATE_ABBR

WIKI_UNTIL = 101  # congress-legislators records exits itself from about here on
ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw" / "congress"
OUT = ROOT / "public" / "data" / "congress" / "seats.json"
BASE = "https://unitedstates.github.io/congress-legislators/"
FILES = ["legislators-historical.json", "legislators-current.json"]

ADMITTED = {
    "DE": "1787-12-07", "PA": "1787-12-12", "NJ": "1787-12-18", "GA": "1788-01-02",
    "CT": "1788-01-09", "MA": "1788-02-06", "MD": "1788-04-28", "SC": "1788-05-23",
    "NH": "1788-06-21", "VA": "1788-06-25", "NY": "1788-07-26", "NC": "1789-11-21",
    "RI": "1790-05-29", "VT": "1791-03-04", "KY": "1792-06-01", "TN": "1796-06-01",
    "OH": "1803-03-01", "LA": "1812-04-30", "IN": "1816-12-11", "MS": "1817-12-10",
    "IL": "1818-12-03", "AL": "1819-12-14", "ME": "1820-03-15", "MO": "1821-08-10",
    "AR": "1836-06-15", "MI": "1837-01-26", "FL": "1845-03-03", "TX": "1845-12-29",
    "IA": "1846-12-28", "WI": "1848-05-29", "CA": "1850-09-09", "MN": "1858-05-11",
    "OR": "1859-02-14", "KS": "1861-01-29", "WV": "1863-06-20", "NV": "1864-10-31",
    "NE": "1867-03-01", "CO": "1876-08-01", "ND": "1889-11-02", "SD": "1889-11-02",
    "MT": "1889-11-08", "WA": "1889-11-11", "ID": "1890-07-03", "WY": "1890-07-10",
    "UT": "1896-01-04", "OK": "1907-11-16", "NM": "1912-01-06", "AZ": "1912-02-14",
    "AK": "1959-01-03", "HI": "1959-08-21",
}
ADMITTED_D = {s: date.fromisoformat(d) for s, d in ADMITTED.items()}
FIRST_CONGRESS = date(1789, 3, 4)
HOUSE_FIXED_FROM = date(1913, 3, 4)
SLACK = timedelta(days=3)


def congress_starts(until: date) -> list[date]:
    out = [date(y, 3, 4) for y in range(1789, 1934, 2)]
    out += [date(y, 1, 3) for y in range(1935, until.year + 3, 2)]
    return out


def fetch() -> list[dict]:
    RAW.mkdir(parents=True, exist_ok=True)
    people = []
    for f in FILES:
        p = RAW / f
        if not p.exists() or "--refresh" in sys.argv:
            print("fetching", f, file=sys.stderr)
            urllib.request.urlretrieve(BASE + f, p)
        batch = json.loads(p.read_text())
        if f == "legislators-current.json":
            for person in batch:
                person["_current"] = True
        people += batch
    return people


def name_of(p: dict) -> str:
    n = p["name"]
    return n.get("official_full") or " ".join(x for x in (n.get("first"), n.get("last")) if x)


def norm_party(s: str | None) -> str:
    if not s:
        return "Unknown"
    return {"Democratic": "Democrat", "Republicans": "Republican"}.get(s, s)


def house_seats(d: date) -> int | None:
    if d < HOUSE_FIXED_FROM:
        return None
    n = 435
    if date(1959, 1, 3) <= d < date(1963, 1, 3):
        n += 1
    if date(1959, 8, 21) <= d < date(1963, 1, 3):
        n += 1
    return n


def senate_seats(d: date) -> int:
    return 2 * sum(1 for a in ADMITTED_D.values() if a <= d)


def pick(terms: list[list], names: list[str]) -> list[list]:
    """Terms whose member's last name is in names; when several match (a widow succeeding her
    husband), keep the ones whose first/middle/nickname also matches."""
    hit = [r for r in terms if cw.name_matches(r[6], names)]
    if len({id(r) for r in hit}) > 1 and len({r[4] for r in hit}) > 1:
        better = [r for r in hit if any(cw.name_matches(f, names) for f in r[7])]
        if better:
            return better
    return hit


def apply_wiki(raw: list[list], starts: list[date]) -> None:
    """Date mid-Congress departures/arrivals from Wikipedia's 'Changes in membership' tables.
    Only moves a term's start later or its end earlier, never outside the original term."""
    by_state = defaultdict(list)
    for r in raw:
        by_state[(r[0], r[5])].append(r)
    stats = Counter()
    for n in range(1, WIKI_UNTIL + 1):
        try:
            changes = cw.parse(n, cw.fetch(n, RAW / "wiki"))
        except Exception as e:  # noqa: BLE001 - one bad page shouldn't sink the build
            print(f"wiki {n}: {e}", file=sys.stderr)
            continue
        c0, c1 = starts[n - 1], starts[n]
        for ch in changes:
            st = STATE_ABBR.get(ch.state)
            if not st:
                stats["no state"] += 1
                continue
            terms = [r for r in by_state[(ch.chamber, st)] if r[1] < c1 and r[2] > c0]
            end = ch.left or ch.seated
            out_hit = pick(terms, ch.out_names) if ch.out_names else []
            if ch.out_names and end:
                hit = out_hit
                for r in hit:
                    if r[1] < end < r[2]:
                        r[2] = end
                        stats["end moved"] += 1
                stats["out matched" if hit else "out unmatched"] += 1
            if ch.in_names and ch.seated:
                hit = [r for r in pick(terms, ch.in_names) if r not in out_hit or not ch.out_names]
                for r in hit:
                    if r[1] < ch.seated < r[2]:
                        r[1] = ch.seated
                        stats["start moved"] += 1
                stats["in matched" if hit else "in unmatched"] += 1
    print("wiki:", dict(stats), file=sys.stderr)


def trim_overlaps(raw: list[list], starts: list[date]) -> None:
    """Where a seat's successor starts while the predecessor's term still runs (the source didn't
    record the exit), end the predecessor's term then. Senate seats are keyed by state + class;
    House seats by state + district within one Congress."""
    seats = defaultdict(list)
    for r in raw:
        t = r[3]
        if r[0] == "senate":
            seats[("s", r[5], t.get("class"))].append(r)
        elif t.get("district", 0) > 0:
            c = sum(1 for b in starts if b <= r[1])
            seats[("h", r[5], t["district"], c)].append(r)
    trimmed = same = 0
    for rs in seats.values():
        rs.sort(key=lambda r: (r[1], r[2]))
        for a, b in zip(rs, rs[1:]):
            if b[1] < a[2]:
                if b[1] > a[1]:
                    a[2] = b[1]
                    trimmed += 1
                else:
                    same += 1
    print(f"overlaps: {trimmed} trimmed, {same} unresolved (same start)", file=sys.stderr)


def build(people: list[dict]) -> dict:
    today = date.today()
    starts = congress_starts(today)

    def congress_of(d: date) -> int:
        i = max(0, sum(1 for s in starts if s <= d) - 1)
        return i

    # Raw intervals: (chamber, start, end, party, caucus, name, state)
    raw = []
    for p in people:
        nm = name_of(p)
        for k, t in enumerate(p["terms"]):
            if p.get("_current") and k == len(p["terms"]) - 1:
                # Still serving: an appointee's listed end (the special election date) can be past.
                t = {**t, "end": max(t["end"], (today + timedelta(days=1)).isoformat())}
            ch = "house" if t["type"] == "rep" else "senate"
            st = t["state"]
            if st not in ADMITTED_D:
                continue
            s, e = date.fromisoformat(t["start"]), date.fromisoformat(t["end"])
            if ch == "house" and s < ADMITTED_D[st] - timedelta(days=1):
                continue  # territorial delegate
            n = p["name"]
            firsts = [x for x in (n.get("first"), n.get("middle"), n.get("nickname")) if x]
            raw.append([ch, s, e, t, nm, st, n.get("last", ""), firsts])

    # Modal start per (chamber, Congress) for snapping.
    modal: dict[tuple[str, int], date] = {}
    by = defaultdict(Counter)
    for ch, s, *_ in raw:
        by[(ch, congress_of(s))][s] += 1
    for k, c in by.items():
        modal[k] = c.most_common(1)[0][0]

    def snap_start(ch: str, s: date) -> date:
        c = congress_of(s)
        if s <= modal[(ch, c)] + SLACK:
            return max(starts[c], FIRST_CONGRESS)
        return s

    def snap_end(e: date) -> date:
        for b in starts:
            if b - SLACK <= e <= b + SLACK:
                return b
        return e

    for r in raw:
        r[1], r[2] = snap_start(r[0], r[1]), snap_end(r[2])
        if r[0] == "house":
            r[1] = max(r[1], ADMITTED_D[r[5]])
    apply_wiki(raw, starts)
    trim_overlaps(raw, starts)

    intervals = []  # (chamber, start, end_exclusive, party, caucus, name, state)
    for ch, s2, e2, t, nm, st, *_ in raw:
        if e2 > today:
            e2 = date(9999, 1, 1)
        affs = t.get("party_affiliations") or [{"start": t["start"], "end": t["end"],
                                                  "party": t.get("party"), "caucus": t.get("caucus")}]
        for i, a in enumerate(affs):
            a_s = s2 if i == 0 else date.fromisoformat(a["start"])
            a_e = e2 if i == len(affs) - 1 else date.fromisoformat(a["end"])
            if a_e > a_s:
                party = norm_party(a.get("party"))
                caucus = norm_party(a.get("caucus") or a.get("party"))
                intervals.append((ch, a_s, a_e, party, caucus, nm, st))

    party_list = [p for p, _ in Counter(i[3] for i in intervals).most_common()]
    pidx = {p: i for i, p in enumerate(party_list)}

    out = {"parties": party_list, "source": BASE, "built": today.isoformat()}
    for ch in ("house", "senate"):
        ev = defaultdict(list)  # date -> [(+1/-1, name, party, caucus, state)]
        for c, s, e, party, caucus, nm, st in intervals:
            if c != ch:
                continue
            ev[s].append((1, nm, party, caucus, st))
            if e.year < 9999:
                ev[e].append((-1, nm, party, caucus, st))
        cnt: Counter = Counter()
        dc = rc = 0
        series = {"t": [], "seats": [], "n": [], "dc": [], "rc": [], "ev": []}
        for d in sorted(ev):
            changes = ev[d]
            for sign, nm, party, caucus, st in changes:
                cnt[party] += sign
                dc += sign * (caucus == "Democrat")
                rc += sign * (caucus == "Republican")
            # A party switch on the same day shows as -old +new; drop pairs that cancel exactly.
            net = Counter()
            for sign, nm, party, caucus, st in changes:
                net[(nm, party, st)] += sign
            evs = [[v, nm, pidx[party], st] for (nm, party, st), v in net.items() if v]
            if not evs:
                continue
            series["t"].append(d.isoformat())
            series["n"].append([x for p, k in sorted(cnt.items(), key=lambda kv: pidx[kv[0]])
                                if k for x in (pidx[p], k)])
            series["dc"].append(dc)
            series["rc"].append(rc)
            series["ev"].append(evs)
            series["seats"].append(senate_seats(d) if ch == "senate" else house_seats(d))
        if ch == "house":
            # Pre-1913: seats = most members sitting at once in that Congress.
            filled = [sum(n[1::2]) for n in series["n"]]
            peak: dict[int, int] = defaultdict(int)
            for d, f in zip(series["t"], filled):
                peak[congress_of(date.fromisoformat(d))] = max(peak[congress_of(date.fromisoformat(d))], f)
            series["seats"] = [s if s is not None else peak[congress_of(date.fromisoformat(d))]
                               for d, s in zip(series["t"], series["seats"])]
        out[ch] = series
    return out


def check(out: dict) -> None:
    for ch in ("house", "senate"):
        s = out[ch]
        over = [(t, sum(n[1::2]), seats) for t, n, seats in zip(s["t"], s["n"], s["seats"])
                if sum(n[1::2]) > seats]
        print(f"{ch}: {len(s['t'])} change points; {len(over)} with more members than seats",
              file=sys.stderr)
        for x in over[:10]:
            print("   over:", x, file=sys.stderr)


def main() -> None:
    out = build(fetch())
    check(out)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, separators=(",", ":"), ensure_ascii=False))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
