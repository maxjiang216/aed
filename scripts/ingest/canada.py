#!/usr/bin/env python3
"""Canadian federal elections, results by riding, from Elections Canada's official voting
results (table 12, "Votes obtained by candidate"). Downloads into raw/canada/ and writes
public/data/canada/<year>.json in the House file format: riding id -> [race].

Riding ids are "<province postal code>-<5-digit district number>", e.g. "ON-35001".
Each race carries the riding name in "nm".

Elections Canada's candidate field packs name and party together ("Jane Doe ** Liberal/Libéral";
"**" marks the incumbent), so the party is matched from the French name after the last "/".
"""

from __future__ import annotations

import csv
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "raw" / "canada"
OUT = ROOT / "public" / "data" / "canada"

URLS = {
    2015: "https://www.elections.ca/res/rep/off/ovr2015app/41/data_donnees/table_tableau12.csv",
    2019: "https://www.elections.ca/res/rep/off/ovr2019app/51/data_donnees/table_tableau12.csv",
    2021: "https://www.elections.ca/res/rep/off/ovr2021app/53/data_donnees/table_tableau12.csv",
    2025: "https://www.elections.ca/res/rep/off/ovrGE45/62/data_donnees/table_tableau12.csv",
}

PROVINCES = {
    "10": "NL", "11": "PE", "12": "NS", "13": "NB", "24": "QC", "35": "ON",
    "46": "MB", "47": "SK", "48": "AB", "59": "BC", "60": "YT", "61": "NT", "62": "NU",
}

# French party label (after the last "/") -> (English label as it ends the left part, party name used here).
# The English suffix is stripped from the left part to recover the candidate name.
PARTIES = {
    "Libéral": ("Liberal", "Liberal"),
    "Conservateur": ("Conservative", "Conservative"),
    "NPD-Nouveau Parti démocratique": ("NDP-New Democratic Party", "NDP"),
    "Bloc Québécois": ("Bloc Québécois", "Bloc Québécois"),
    "Parti Vert": ("Green Party", "Green"),
    "Parti populaire - PPC": ("People's Party - PPC", "People's Party"),
    "Parti populaire": ("People's Party", "People's Party"),
    "Indépendant(e)": ("Independent", "Independent"),
    "Indépendant": ("Independent", "Independent"),
    "Aucune appartenance": ("No Affiliation", "No Affiliation"),
    "Marxiste-Léniniste": ("Marxist-Leninist", "Marxist-Leninist"),
    "ML": ("ML", "Marxist-Leninist"),
    "Parti de l'Héritage Chrétien": ("Christian Heritage Party", "Christian Heritage"),
    "Libertarien": ("Libertarian", "Libertarian"),
    "Communiste": ("Communist", "Communist"),
    "Parti Rhinocéros Party": ("Parti Rhinocéros Party", "Rhinoceros"),
    "Rhinocéros": ("Rhinoceros", "Rhinoceros"),
    "Parti Libre Canada": ("Free Party Canada", "Free Party"),
    "Parti Protection Animaux": ("Animal Protection Party", "Animal Protection"),
    "CAC": ("VCP", "Veterans Coalition"),
    "Maverick Party": ("Maverick Party", "Maverick"),
    "Pour l'Indépendance du Québec": ("Pour l'Indépendance du Québec", "Pour l'Indépendance du Québec"),
    "Centriste": ("Centrist", "Centrist"),
    "Parti Avenir Canadien": ("Canadian Future Party", "Canadian Future"),
    "Forces et Démocratie - Allier les forces de nos régions": (
        "Forces et Démocratie - Allier les forces de nos régions", "Forces et Démocratie"),
    "Parti Uni du Canada (UP)": ("United Party of Canada (UP)", "United Party"),
    "Parti Uni": ("United Party", "United Party"),
    "Radical Marijuana": ("Radical Marijuana", "Radical Marijuana"),
    "Parti PC": ("PC Party", "PC Party"),
    "Parti Marijuana": ("Marijuana Party", "Marijuana"),
    "QFC - Quatrième front du Canada": ("CFF - Canada's Fourth Front", "Canada's Fourth Front"),
    "Environment Voters": ("Animal Alliance/Environment Voters/Animal Alliance", "Animal Alliance"),
    "Alliance Nationale Citoyens": ("National Citizens Alliance", "National Citizens Alliance"),
    "Pirate": ("Pirate", "Pirate"),
    "Avancement de la Démocratie": ("Democratic Advancement", "Democratic Advancement"),
    "Nationaliste": ("Nationalist", "Nationalist"),
    "UPC": ("UPC", "United People's"),
    "PAC": ("CAP", "Canadian Action"),
    "Arrêtonslechangementclimatique": ("Stop Climate Change", "Stop Climate Change"),
    "Parti Patriote": ("Parti Patriote", "Parti Patriote"),
    "ADN": ("ATN", "Animal Alliance"),
    "PRCT": ("PACT", "PACT"),
    "Parti des aînés": ("Seniors Party", "Seniors Party"),
    "Le Lien": ("The Bridge", "The Bridge"),
    "Parti Canada": ("Canada Party", "Canada Party"),
}


def split_candidate(field: str) -> tuple[str, str]:
    # Longest French label that ends the field (some labels contain "/").
    for fr in sorted(PARTIES, key=len, reverse=True):
        if field.endswith("/" + fr):
            en, party = PARTIES[fr]
            left = field[: -len(fr) - 1]
            if left.endswith(en):
                left = left[: -len(en)]
            name = left.replace("**", "").strip().rstrip("*").strip()
            return name, party
    raise ValueError(f"unknown party in {field!r}")


def fetch(year: int) -> Path:
    path = RAW / f"{year}.csv"
    if not path.exists():
        RAW.mkdir(parents=True, exist_ok=True)
        req = urllib.request.Request(URLS[year], headers={"User-Agent": "aed-ingest"})
        with urllib.request.urlopen(req) as r:
            path.write_bytes(r.read())
    return path


def build(year: int) -> dict:
    races: dict[str, dict] = {}
    with fetch(year).open(encoding="utf-8-sig", newline="") as f:
        rows = csv.reader(f)
        next(rows)
        for row in rows:
            if len(row) < 7 or not row[2].strip().isdigit():
                continue
            num = row[2].strip()
            rid = f"{PROVINCES[num[:2]]}-{num}"
            name, party = split_candidate(row[3])
            race = races.setdefault(rid, {"c": [], "t": 0, "nm": row[1].strip(), "src": "elections-canada"})
            votes = int(row[6])
            race["c"].append([name, party, votes, 0])
            race["t"] += votes
    for race in races.values():
        race["c"].sort(key=lambda c: -c[2])
    return {rid: [race] for rid, race in sorted(races.items())}


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for year in URLS:
        data = build(year)
        (OUT / f"{year}.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")))
        print(year, len(data), "ridings", file=sys.stderr)


if __name__ == "__main__":
    main()
