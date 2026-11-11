"""'Changes in membership' tables from Wikipedia's per-Congress articles ("63rd United States
Congress"), used to date mid-Congress departures and arrivals that congress-legislators lacks.

Before roughly the 100th Congress (1987), congress-legislators gives a House member who resigned
or died, and their successor, the same full-Congress start and end dates. These tables give the
vacancy date (from the "Reason" text, e.g. "Died May 5, 1913") and the successor's installation
date.

Wikitext is cached in raw/congress/wiki/<n>.json.
"""

from __future__ import annotations

import json
import re
import time
import unicodedata
import urllib.parse
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path

API = "https://en.wikipedia.org/w/api.php"
UA = "aed-ingest/1.0 (election data research script)"

MONTHS = {m: i for i, m in enumerate(
    ["january", "february", "march", "april", "may", "june", "july", "august",
     "september", "october", "november", "december"], 1)}
DATE_RE = re.compile(r"\b(January|February|March|April|May|June|July|August|September|October|"
                     r"November|December)\s+(\d{1,2}),?\s+(\d{4})")


@dataclass
class Change:
    congress: int
    chamber: str           # "house" | "senate"
    state: str             # full state name
    out_names: list[str]   # display/link names of the member who left ([] if seat was vacant)
    left: date | None      # date the seat became vacant
    in_names: list[str]
    seated: date | None    # successor installation date


def ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def fetch(n: int, cache: Path) -> str:
    cache.mkdir(parents=True, exist_ok=True)
    p = cache / f"{n}.json"
    if not p.exists():
        q = urllib.parse.urlencode({"action": "parse", "page": f"{ordinal(n)} United States Congress",
                                    "prop": "wikitext", "format": "json", "formatversion": 2,
                                    "redirects": 1})
        req = urllib.request.Request(f"{API}?{q}", headers={"User-Agent": UA})
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req) as r:
                    p.write_bytes(r.read())
                break
            except urllib.error.HTTPError as e:
                if e.code != 429 or attempt == 5:
                    raise
                time.sleep(int(e.headers.get("Retry-After") or 0) or 10 * 2 ** attempt)
        time.sleep(2)
    return json.loads(p.read_text())["parse"]["wikitext"]


def parse_date(s: str) -> date | None:
    m = DATE_RE.search(s)
    if not m:
        return None
    try:
        return date(int(m[3]), MONTHS[m[1].lower()], int(m[2]))
    except ValueError:
        return None


def clean(s: str) -> str:
    s = re.sub(r"<ref[^>]*/>", "", s)
    s = re.sub(r"<ref.*?</ref>", "", s, flags=re.S)
    s = re.sub(r"\{\{(efn|refn|sfn|citation needed|cn)[^{}]*\}\}", "", s, flags=re.I)
    return s


def names_in(cell: str) -> list[str]:
    """Wiki links in a cell, both target and label ('[[A B (politician)|A. B.]]')."""
    out = []
    for target, _, label in re.findall(r"\[\[([^\]|]+)(\|([^\]]+))?\]\]", cell):
        if re.search(r"\b(Party|Congress|Senate|House|Governor|Court|Secretary)\b|List of|district|:", target):
            continue
        out += [re.sub(r"\s*\(.*?\)", "", target), label]
    return [x for x in out if x]


def strip_attrs(cell: str) -> str:
    # "style=... | text" and "{{Party shading/X}} | text" -> text
    m = re.match(r"^((?:(?!\[\[).)*?)\|(?!\|)(.*)$", cell, flags=re.S)
    if m and re.search(r"\{\{|=|nowrap", m[1]):
        return m[2].strip()
    return cell


def rows(table: str) -> list[list[str]]:
    out = []
    for chunk in re.split(r"\n\|-[^\n]*", table)[1:]:
        cells = []
        for line in chunk.split("\n"):
            line = line.strip()
            if line.startswith("|}"):
                break
            if line.startswith("|") and not line.startswith("|+"):
                for c in re.split(r"\|\|", line[1:]):
                    cells.append(c.strip())
            elif cells and line and not line.startswith("!"):
                cells[-1] += " " + line
        if cells:
            out.append(cells)
    return out


STATE_RE = re.compile(r"\{\{ushr\|([^|}]+)|List of United States (?:senators|representatives) from "
                      r"([^|\]]+)|\[\[([A-Z][a-z]+(?: [A-Z][a-z]+)?)(?:'s|\]\]|\|)")


def state_of(cell: str) -> str | None:
    m = STATE_RE.search(cell)
    if not m:
        return None
    return (m[1] or m[2] or m[3]).strip()


def parse(n: int, text: str) -> list[Change]:
    text = clean(text)
    m = re.search(r"\n==\s*Changes in membership\s*==", text)
    if not m:
        return []
    sec = text[m.end():]
    out = []
    for chamber, head in (("senate", r"===\s*Senate\s*==="), ("house", r"===\s*House of Representatives\s*===")):
        m = re.search(head, sec)
        if not m:
            continue
        rest = sec[m.end():]
        end = re.search(r"\n==[^=]", rest)
        nxt = re.search(r"\n===", rest)
        stop = min(x.start() for x in (end, nxt) if x) if (end or nxt) else len(rest)
        body = rest[:stop]
        # Older pages open the table with a template ({{Ordinal US Congress change|Senate}}).
        for t in [body]:
            for cells in rows(t):
                if len(cells) < 5:
                    continue
                st = state_of(cells[0])
                if not st:
                    continue
                vac, reason, succ, when = (strip_attrs(c) for c in cells[1:5])
                out.append(Change(
                    congress=n, chamber=chamber, state=st,
                    out_names=names_in(vac), left=parse_date(reason),
                    in_names=names_in(succ), seated=parse_date(when),
                ))
    return out


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z ]", "", s)


def name_matches(last: str, names: list[str]) -> bool:
    lf = fold(last).strip()
    return bool(lf) and any(re.search(rf"\b{re.escape(lf)}\b", fold(x)) for x in names)
