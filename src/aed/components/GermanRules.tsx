import { useEffect, useMemo, useState } from "react";
import { DEFAULTS, simulate, sizeFor, type RuleSet, type SimOptions, type SimResult } from "../bundestag";
import { swatch, type Hue } from "../colors";
import { loadCanada, loadHouse, loadIndex } from "../data";
import { POSTAL_TO_FIPS, STATES } from "../states";
import type { HouseFile } from "../types";
import { Segmented } from "./Controls";

type CountryKey = "us" | "ca";

interface Country {
  title: string;
  chamber: string;
  district: string;
  region: string;
  years: () => Promise<number[]>;
  load: (year: number) => Promise<HouseFile>;
  /** Left-to-right seat order; unlisted parties go in the middle. */
  order: string[];
  hues: Record<string, Hue>;
  abbr: Record<string, string>;
  regionName: (code: string) => string;
  /** Offer the fill-in for districts one major party skipped. */
  impute: boolean;
}

const PROVINCES: Record<string, string> = {
  NL: "Newfoundland and Labrador", PE: "Prince Edward Island", NS: "Nova Scotia", NB: "New Brunswick",
  QC: "Quebec", ON: "Ontario", MB: "Manitoba", SK: "Saskatchewan", AB: "Alberta", BC: "British Columbia",
  YT: "Yukon", NT: "Northwest Territories", NU: "Nunavut",
};

const COUNTRIES: Record<CountryKey, Country> = {
  us: {
    title: "The U.S. House under Bundestag rules",
    chamber: "House",
    district: "district",
    region: "state",
    years: () => loadIndex().then((idx) => [...(idx.offices.house?.district ?? [])].sort((a, b) => a - b)),
    load: loadHouse,
    order: ["Democratic", "Republican"],
    hues: { Democratic: "Blue", Republican: "Red" },
    abbr: { Democratic: "D", Republican: "R", Independent: "I" },
    regionName: (s) => STATES[POSTAL_TO_FIPS[s]]?.[1] ?? s,
    impute: true,
  },
  ca: {
    title: "Canada's House of Commons under Bundestag rules",
    chamber: "House of Commons",
    district: "riding",
    region: "province",
    years: () => Promise.resolve([2015, 2019, 2021, 2025]),
    load: loadCanada,
    order: ["NDP", "Green", "Liberal", "Bloc Québécois", "Conservative", "People's Party"],
    hues: {
      Liberal: "Red", Conservative: "Blue", NDP: "Orange", "Bloc Québécois": "Teal", Green: "Green",
      "People's Party": "Purple",
    },
    abbr: {
      Liberal: "LPC", Conservative: "CPC", NDP: "NDP", "Bloc Québécois": "BQ", Green: "GPC",
      "People's Party": "PPC", Independent: "Ind",
    },
    regionName: (s) => PROVINCES[s] ?? s,
    impute: false,
  },
};

const pct = (x: number, d = 1) => `${(x * 100).toFixed(d)}%`;
const cap = (s: string) => s[0].toUpperCase() + s.slice(1);

const RULE_TEXT: Record<RuleSet, string> = {
  "2025":
    "Fixed size. Seats go to parties by national list vote (Sainte-Laguë), then to each party's lists by region. " +
    "A district winner sits only while the party's regional share covers them, best vote share first. A party under " +
    "the threshold (and the 3-district clause) gets nothing, district winners included; independents keep theirs.",
  "2013":
    "Every district winner sits. Where a party wins more districts than its regional share (overhang), the chamber " +
    "grows until every party's national share is proportional again (leveling seats).",
};

function parseHash(): { country: CountryKey; year: number | null; rules: RuleSet } {
  const parts = window.location.hash.replace(/^#\/?/, "").split("/").slice(1);
  const country: CountryKey = parts[0] === "ca" ? "ca" : "us";
  if (parts[0] === "us" || parts[0] === "ca") parts.shift();
  const [year, rules] = parts;
  return { country, year: year ? Number(year) : null, rules: rules === "2013" ? "2013" : "2025" };
}

export function GermanRules() {
  const init = parseHash();
  const [country, setCountry] = useState<CountryKey>(init.country);
  const [years, setYears] = useState<number[]>([]);
  const [year, setYear] = useState<number | null>(init.year);
  const [opts, setOpts] = useState<SimOptions>({
    rules: init.rules, ...DEFAULTS[init.rules], impute: COUNTRIES[init.country].impute,
  });
  const [files, setFiles] = useState<Record<number, HouseFile>>({});
  const [error, setError] = useState<string | null>(null);
  const C = COUNTRIES[country];

  useEffect(() => {
    let live = true;
    setFiles({});
    C.years().then((ys) => {
      if (!live) return;
      setYears(ys);
      setYear((y) => (y && ys.includes(y) ? y : ys[ys.length - 1]));
      Promise.all(ys.map((y) => C.load(y).then((f) => [y, f] as const))).then(
        (pairs) => live && setFiles(Object.fromEntries(pairs)),
        (e) => setError(String(e)),
      );
    }, (e) => setError(String(e)));
    return () => {
      live = false;
    };
  }, [C]);

  useEffect(() => {
    if (year) window.history.replaceState(null, "", `#/germany/${country}/${year}/${opts.rules}`);
  }, [country, year, opts.rules]);

  const results = useMemo(() => {
    const out: Record<number, SimResult> = {};
    for (const [y, f] of Object.entries(files)) out[Number(y)] = simulate(f, opts);
    return out;
  }, [files, opts]);

  const r = year ? results[year] : undefined;
  const file = year ? files[year] : undefined;
  const set = (patch: Partial<SimOptions>) => setOpts((o) => ({ ...o, ...patch }));
  const i = year ? years.indexOf(year) : -1;
  const nDistricts = file ? Object.keys(file).length : 0;
  const v = useMemo(() => view(C), [C]);

  return (
    <div className="app germany">
      <header className="top">
        <h1>{C.title}</h1>
        <p className="lede">
          What if each election had been counted the way Germany elects its Bundestag?{" "}
          <a href="#/president">← Back to the map</a>
        </p>
      </header>
      <nav className="controls">
        <Segmented
          label="Country"
          value={country}
          options={[["us", "United States"], ["ca", "Canada"]]}
          onChange={(c) => {
            setCountry(c);
            setYear(null);
            set({ impute: COUNTRIES[c].impute });
          }}
        />
        <div className="year" aria-label="Year">
          <button disabled={i <= 0} onClick={() => setYear(years[i - 1])} aria-label="Previous election">◀</button>
          <select value={year ?? ""} onChange={(e) => setYear(Number(e.target.value))} aria-label="Year">
            {[...years].reverse().map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <button disabled={i < 0 || i >= years.length - 1} onClick={() => setYear(years[i + 1])} aria-label="Next election">▶</button>
        </div>
        <Segmented
          label="Rules"
          value={opts.rules}
          options={[
            ["2025", "2025 rules", "Fixed size, uncovered district winners lose their seat"],
            ["2013", "2013–17 rules", "Overhang plus leveling seats; the chamber grows"],
          ]}
          onChange={(rules) => setOpts((o) => ({ ...o, rules, ...DEFAULTS[rules] }))}
        />
        <label className="opt" title="Germany: 630 seats for 299 constituencies (2025); base 598 = 2 × 299 (2013)">
          {opts.rules === "2025" ? "Seats" : "Base seats"}{" "}
          <input
            type="number" min={1} max={3000} step={1}
            value={nDistricts ? sizeFor(opts, nDistricts) : ""}
            onChange={(e) => {
              const n = Number(e.target.value);
              if (n > 0 && nDistricts) set({ seatsPerDistrict: n / nDistricts });
            }}
          />
        </label>
        <label className="opt">
          Threshold{" "}
          <input
            type="number" min={0} max={20} step={0.5} value={+(opts.threshold * 100).toFixed(2)}
            onChange={(e) => set({ threshold: Math.max(0, Number(e.target.value)) / 100 })}
          />
          %
        </label>
        <label className="opt" title={`Win this many ${C.district}s and the threshold does not apply (Germany: 3)`}>
          <input type="checkbox" checked={opts.directClause > 0} onChange={(e) => set({ directClause: e.target.checked ? 3 : 0 })} />
          3-{C.district} clause
        </label>
        {C.impute && (
          <label className="opt" title="Give the missing major party 25% in districts it did not contest">
            <input type="checkbox" checked={opts.impute} onChange={(e) => set({ impute: e.target.checked })} />
            Fill uncontested seats
          </label>
        )}
      </nav>
      {error && <p className="error">Could not load data: {error}</p>}
      {!r || !file ? (
        <div className="map-loading">Loading…</div>
      ) : (
        <main className="germany-grid">
          <section className="panel">
            <h2>{year}</h2>
            <p className="muted small">{RULE_TEXT[opts.rules]}</p>
            {bars(r, v, C).map((b) => <SeatBar key={b.label} bar={b} v={v} />)}
            <ul className="swatches small">
              <li>dark = {C.district} seat</li>
              <li>light = list seat</li>
              <li className="muted">line = half the chamber</li>
            </ul>
            <PartyTable r={r} v={v} C={C} />
            <Coalitions r={r} v={v} />
            <Unseated r={r} v={v} C={C} file={file} />
            <p className="hint muted">
              Voters cast no list vote, so each party's {C.district} votes stand in for it.
              {C.impute && opts.impute &&
                ` ${r.imputed.length} districts without both a Democrat and a Republican on the ballot get the missing one at 25%.`}
              {country === "ca" && " Results: Elections Canada, official voting results."}
            </p>
          </section>
          <section className="panel">
            <h3>Every election, these rules</h3>
            <YearsTable results={results} years={years} year={year!} onPick={setYear} v={v} />
          </section>
          <section className="panel wide">
            <h3>By {C.region} ({year}): actual → simulated</h3>
            <StateTable r={r} v={v} C={C} />
          </section>
        </main>
      )}
    </div>
  );
}

/** Party presentation for one country. */
interface ViewHelpers {
  hue: (p: string) => Hue;
  abbr: (p: string) => string;
  rank: (p: string) => number;
}

function view(C: Country): ViewHelpers {
  return {
    hue: (p) => C.hues[p] ?? "Gray",
    abbr: (p) => C.abbr[p] ?? p,
    rank: (p) => {
      const i = C.order.indexOf(p);
      return i >= 0 ? i : C.order.length / 2 - 0.25;
    },
  };
}

interface Bar { label: string; parts: { party: string; seats: number; kind: "direct" | "list" }[]; total: number }

function bars(r: SimResult, v: ViewHelpers, C: Country): Bar[] {
  const ps = [...r.parties].sort((a, b) => v.rank(a.party) - v.rank(b.party));
  return [
    {
      label: `Actual ${C.chamber}`,
      total: ps.reduce((s, p) => s + p.won, 0),
      parts: ps.map((p) => ({ party: p.party, seats: p.won, kind: "direct" as const })),
    },
    {
      label: `Bundestag rules (${r.options.rules})`,
      total: r.size,
      parts: ps.flatMap((p) => [
        { party: p.party, seats: p.direct, kind: "direct" as const },
        { party: p.party, seats: p.list, kind: "list" as const },
      ]),
    },
  ];
}

function SeatBar({ bar, v }: { bar: Bar; v: ViewHelpers }) {
  const majority = Math.floor(bar.total / 2) + 1;
  return (
    <div className="seatbar">
      <div className="seatbar-label">
        <span>{bar.label}</span>
        <span className="muted">{bar.total} seats · majority {majority}</span>
      </div>
      <div className="seatbar-track">
        {bar.parts.filter((p) => p.seats > 0).map((p, i) => (
          <i
            key={i}
            title={`${p.party}: ${p.seats} ${p.kind === "list" ? "list" : "district"} seats`}
            style={{ flexGrow: p.seats, background: swatch(v.hue(p.party), p.kind === "list" ? 1 : 3) }}
          />
        ))}
        <b className="seatbar-mid" style={{ left: "50%" }} aria-hidden />
      </div>
    </div>
  );
}

function PartyTable({ r, v, C }: { r: SimResult; v: ViewHelpers; C: Country }) {
  const rows = r.parties.filter((p) => p.seats > 0 || p.won > 0 || p.share >= 0.01);
  const other = r.parties.filter((p) => !rows.includes(p));
  const otherShare = other.reduce((s, p) => s + p.share, 0);
  return (
    <table className="cands">
      <thead>
        <tr className="muted small">
          <td>Party</td><td className="num">Votes</td><td className="num">Actual</td>
          <td className="num">{cap(C.district)}</td><td className="num">List</td><td className="num">Seats</td>
        </tr>
      </thead>
      <tbody>
        {rows.map((p) => (
          <tr key={p.party} className={p.seats ? "" : "minor"}>
            <td>
              <i className="dot" style={{ background: swatch(v.hue(p.party), 3) }} />
              {p.party}
              {!p.qualified && p.votes > 0 && <span className="party"> · below threshold</span>}
            </td>
            <td className="num">{p.votes > 0 ? pct(p.share) : "–"}</td>
            <td className="num">{p.won}</td>
            <td className="num">{p.direct}</td>
            <td className="num">{p.list}</td>
            <td className="num"><strong>{p.seats}</strong> <span className="party">{pct(p.seats / r.size)}</span></td>
          </tr>
        ))}
        {other.length > 0 && (
          <tr className="minor">
            <td>{other.length} other parties</td><td className="num">{pct(otherShare)}</td>
            <td className="num">0</td><td className="num">0</td><td className="num">0</td><td className="num">0</td>
          </tr>
        )}
      </tbody>
    </table>
  );
}

/** Minimal winning coalitions: over half the seats, and every member needed. */
export function coalitions(seats: Record<string, number>): string[][] {
  const parties = Object.keys(seats).filter((p) => seats[p] > 0).sort((a, b) => seats[b] - seats[a]).slice(0, 12);
  const total = Object.values(seats).reduce((a, b) => a + b, 0);
  const sum = (c: string[]) => c.reduce((s, p) => s + seats[p], 0);
  const out: string[][] = [];
  for (let mask = 1; mask < 1 << parties.length; mask++) {
    const members = parties.filter((_, i) => mask & (1 << i));
    const n = sum(members);
    if (n * 2 > total && members.every((p) => (n - seats[p]) * 2 <= total)) out.push(members);
  }
  return out.sort((a, b) => a.length - b.length || sum(b) - sum(a));
}

function Coalitions({ r, v }: { r: SimResult; v: ViewHelpers }) {
  const seats = Object.fromEntries(r.parties.map((p) => [p.party, p.seats]));
  const list = coalitions(seats).slice(0, 6);
  if (!list.length) return null;
  const sum = (c: string[]) => c.reduce((s, p) => s + seats[p], 0);
  return (
    <>
      <h3>{list[0].length === 1 ? "Majority" : "Possible majority coalitions"}</h3>
      <ul className="lost small">
        {list.map((c) => (
          <li key={c.join()}>
            {c.map((p) => (
              <span key={p} className="coal-member">
                <i className="dot" style={{ background: swatch(v.hue(p), 3) }} />{v.abbr(p)}
              </span>
            ))}
            <span className="muted"> {sum(c)} of {r.size}</span>
          </li>
        ))}
      </ul>
    </>
  );
}

function Unseated({ r, v, C, file }: { r: SimResult; v: ViewHelpers; C: Country; file: HouseFile }) {
  if (r.options.rules !== "2025") return null;
  const lost = r.winners.filter((w) => !w.seated);
  const name = (id: string) => {
    const nm = file[id]?.[0]?.nm;
    if (nm) return `${nm} (${id.slice(0, 2)})`;
    const [st, d] = id.split("-");
    return `${C.regionName(st)} ${d === "AL" ? "at-large" : Number(d)}`;
  };
  return (
    <>
      <h3>{cap(C.district)} winners left without a seat</h3>
      {lost.length === 0 ? (
        <p className="small muted">None: every party's regional list share covers all its {C.district} wins.</p>
      ) : (
        <ul className="lost small">
          {lost.map((w) => (
            <li key={w.id}>
              <i className="dot" style={{ background: swatch(v.hue(w.party), 3) }} />
              {w.name} ({v.abbr(w.party)}), {name(w.id)}: won with {pct(w.share)}
              {w.lost === "threshold" && <span className="muted"> · party below threshold</span>}
            </li>
          ))}
        </ul>
      )}
    </>
  );
}

function seatString(seats: Record<string, number>, v: ViewHelpers): string {
  return Object.entries(seats)
    .filter(([, n]) => n > 0)
    .sort((a, b) => v.rank(a[0]) - v.rank(b[0]))
    .map(([p, n]) => `${v.abbr(p)} ${n}`)
    .join(" · ");
}

function control(seats: Record<string, number>, v: ViewHelpers): string {
  const total = Object.values(seats).reduce((a, b) => a + b, 0);
  const top = Object.entries(seats).sort((a, b) => b[1] - a[1])[0];
  if (!top) return "–";
  return `${v.abbr(top[0])} ${top[1] * 2 > total ? "maj" : "min"}`;
}

function YearsTable({ results, years, year, onPick, v }: {
  results: Record<number, SimResult>; years: number[]; year: number; onPick: (y: number) => void; v: ViewHelpers;
}) {
  return (
    <table className="cands years">
      <thead>
        <tr className="muted small"><td>Year</td><td>Actual</td><td>Simulated</td><td className="num">Lost</td></tr>
      </thead>
      <tbody>
        {[...years].reverse().map((y) => {
          const r = results[y];
          if (!r) return null;
          const act = Object.fromEntries(r.parties.map((p) => [p.party, p.won]));
          const sim = Object.fromEntries(r.parties.map((p) => [p.party, p.seats]));
          const a = control(act, v);
          const s = control(sim, v);
          return (
            <tr key={y} className={y === year ? "picked" : ""} onClick={() => onPick(y)}>
              <td>{y}</td>
              <td className="small">{seatString(act, v)} <span className="tag">{a}</span></td>
              <td className="small">
                {seatString(sim, v)}{" "}
                <span className={`tag${a !== s ? " changed" : ""}`} title={a !== s ? "Different outcome than the actual result" : undefined}>{s}</span>
              </td>
              <td className="num">{r.options.rules === "2025" ? r.winners.filter((w) => !w.seated).length : "–"}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function StateTable({ r, v, C }: { r: SimResult; v: ViewHelpers; C: Country }) {
  const won: Record<string, Record<string, number>> = {};
  for (const w of r.winners) (won[w.state] ??= {})[w.party] = (won[w.state][w.party] ?? 0) + 1;
  const states = Object.keys(r.states).sort();
  return (
    <div className="state-grid">
      {states.map((s) => (
        <div key={s} className="state-cell" title={C.regionName(s)}>
          <strong>{s}</strong>
          <span className="muted">{seatString(won[s] ?? {}, v) || "–"}</span>
          <span>→ {seatString(r.states[s], v) || "no seats"}</span>
        </div>
      ))}
    </div>
  );
}
