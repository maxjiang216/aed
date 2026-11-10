import { useMemo } from "react";
import { swatch, type Hue } from "../colors";
import { hueFor, marginLabel, outcome, pct, type Env } from "../model";
import type { Office, Race, Row, Selection } from "../types";

const fmt = new Intl.NumberFormat("en-US");

const SOURCE_LABEL: Record<string, string> = {
  medsl: "MIT Election Data + Science Lab",
  wikipedia: "Wikipedia results-by-state table",
  algara: "Algara & Amlani county returns (only D and R named)",
  curated: "AED hand-entered data",
  "curated+algara": "AED hand-entered data + Algara & Amlani",
};

function raceTitle(race: Race, office: Office): string {
  const parts = [];
  if (race.s) parts.push("Special");
  if (race.r) parts.push("Runoff");
  if (office === "senate" && race.k) parts.push(`Class ${race.k}`);
  return parts.join(" · ");
}

function rowLabel(row: Row): string {
  return row[3] === 1 ? `${row[0]} — unnamed in source` : row[0];
}

export function CandidateTable({ race, hues }: { race: Race; hues: Record<string, Hue> }) {
  return (
    <table className="cands">
      <tbody>
        {race.c.map((row, i) => (
          <tr key={i} className={row[3] ? "minor" : ""}>
            <td>
              <i className="dot" style={{ background: row[3] === 2 ? "transparent" : swatch(hueFor(row, hues)) }} />
              <span className="name">{rowLabel(row)}</span>
              <span className="party">{row[1] !== "Other" ? row[1] : ""}</span>
            </td>
            <td className="num">{fmt.format(row[2])}</td>
            <td className="num">{pct(row[2] / race.t)}</td>
          </tr>
        ))}
        <tr className="total">
          <td>Total</td>
          <td className="num">{fmt.format(race.t)}</td>
          <td />
        </tr>
      </tbody>
    </table>
  );
}

interface PanelProps {
  title: string;
  races: Race[];
  year: number;
  office: Office;
  hues: Record<string, Hue>;
  prev: { race: Race; year: number } | null;
  pinned: boolean;
  onClose: () => void;
}

export function RacePanel({ title, races, year, office, hues, prev, pinned, onClose }: PanelProps) {
  return (
    <div className="race-panel">
      <div className="panel-head">
        <h2>
          {title} <span className="muted">{year}</span>
        </h2>
        {pinned && (
          <button className="close" onClick={onClose} aria-label="Close">
            ×
          </button>
        )}
      </div>
      {!races.length && <p className="muted">No {office} race in this data for {year}.</p>}
      {races.map((race, i) => {
        const o = outcome(race);
        return (
          <section key={i} className="race">
            {raceTitle(race, office) && <h3>{raceTitle(race, office)}</h3>}
            {o && (
              <p className="margin">
                <strong>{marginLabel(o)}</strong>
                {o.second && (
                  <span className="muted">
                    {" "}
                    {o.winner[0]} over {o.second[0]}
                  </span>
                )}
              </p>
            )}
            <CandidateTable race={race} hues={hues} />
            {race.n?.map((n, j) => (
              <p key={j} className="note">
                ⚠ {n}
              </p>
            ))}
            {race.src && <p className="source">Source: {SOURCE_LABEL[race.src] ?? race.src}</p>}
          </section>
        );
      })}
      {prev && races.length > 0 && <PrevLine prev={prev} />}
      {!pinned && <p className="hint muted">Click a region to pin it.</p>}
    </div>
  );
}

function PrevLine({ prev }: { prev: { race: Race; year: number } }) {
  const o = outcome(prev.race);
  if (!o) return null;
  return (
    <p className="muted prev">
      Previous ({prev.year}): {marginLabel(o)} — {o.winner[0]}
    </p>
  );
}

export function TooltipBody({ name, race }: { name: string; race: Race | null }) {
  const o = race && outcome(race);
  return (
    <>
      <strong>{name}</strong>
      {o ? (
        <>
          <div>{marginLabel(o)}</div>
          <div className="muted">
            {o.winner[0]} {pct(o.winner[2] / race!.t)}
            {o.second && ` · ${o.second[0]} ${pct(o.second[2] / race!.t)}`}
          </div>
        </>
      ) : (
        <div className="muted">No race / no data</div>
      )}
    </>
  );
}

/** Shown when no region is focused: national popular vote by candidate. */
export function NationalPanel({
  sel, races, hues, env,
}: { sel: Selection; races: Race[]; hues: Record<string, Hue>; env: Env }) {
  const summary = useMemo(() => {
    const byName = new Map<string, Row>();
    let wins: Record<string, number> = {};
    for (const race of races) {
      for (const row of race.c) {
        const key = row[3] ? `__other${row[3]}` : `${row[0]}|${row[1]}`;
        const cur = byName.get(key);
        if (cur) cur[2] += row[2];
        else byName.set(key, [row[3] ? (row[3] === 1 ? "Unnamed (combined)" : "Others") : row[0], row[1], row[2], row[3]]);
      }
      const o = outcome(race);
      if (o && !o.tie) {
        const w = o.winner[3] === 1 ? "Unnamed" : o.winner[1];
        wins = { ...wins, [w]: (wins[w] ?? 0) + 1 };
      }
    }
    const rows = [...byName.values()].sort((a, b) => b[2] - a[2]);
    return { rows, wins };
  }, [races]);

  const dm = env.t > 0 ? (env.d - env.r) / env.t : null;
  const isPres = sel.office === "president";
  const top = summary.rows.slice(0, isPres ? 6 : 4);
  return (
    <div className="race-panel">
      <h2>
        {sel.year} {isPres ? "presidential election" : sel.office === "senate" ? "Senate elections" : "governor elections"}
      </h2>
      <p className="muted">
        {races.length} {races.length === 1 ? "state" : "states"} with a race on the map.
        {dm !== null && ` Combined: ${dm >= 0 ? "D" : "R"}+${Math.abs(dm * 100).toFixed(1)}.`}
      </p>
      <h3>States won</h3>
      <ul className="wins">
        {Object.entries(summary.wins)
          .sort((a, b) => b[1] - a[1])
          .map(([p, n]) => (
            <li key={p}>
              <i className="dot" style={{ background: swatch(p === "Unnamed" ? "Gray" : hues[p] ?? "Purple") }} />
              {p} <strong>{n}</strong>
            </li>
          ))}
      </ul>
      {isPres && (
        <>
          <h3>Popular vote (states with data)</h3>
          <CandidateTable race={{ c: top, t: env.t }} hues={hues} />
        </>
      )}
      {dm === null && <p className="muted">No data.</p>}
      <p className="hint muted">Hover or click a state for details. ← → change year.</p>
    </div>
  );
}
