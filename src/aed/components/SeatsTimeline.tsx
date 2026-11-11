import { useEffect, useMemo, useRef, useState } from "react";
import { loadSeats } from "../data";
import { rowAt, seatRows, type Chamber, type SeatRow, type SeatsFile } from "../seats";
import { Segmented } from "./Controls";

type Range = "all" | "1857" | "1945" | "1959" | "1995" | "10y";

const RANGES: [Range, string, string?][] = [
  ["all", "1789–", "Whole history"],
  ["1857", "1857–", "Democrats vs. Republicans"],
  ["1945", "1945–"],
  ["1959", "50 states", "Since Hawaii joined on Aug 21, 1959 (Alaska joined Jan 3, 1959)"],
  ["1995", "1995–"],
  ["10y", "10 yrs"],
];

const SERIES = [
  { key: "dem", label: "Democrats", cls: "s-dem" },
  { key: "other", label: "Other parties", cls: "s-other" },
  { key: "vacant", label: "Vacant", cls: "s-vacant" },
  { key: "rep", label: "Republicans", cls: "s-rep" },
] as const;

const H = 380;
const M = { top: 12, right: 12, bottom: 28, left: 40 };
const DAY = 86_400_000;

function rangeStart(r: Range, last: number): number {
  switch (r) {
    case "all": return Date.UTC(1789, 2, 4);
    case "1857": return Date.UTC(1857, 2, 4);
    case "1945": return Date.UTC(1945, 0, 3);
    case "1959": return Date.UTC(1959, 7, 21);
    case "1995": return Date.UTC(1995, 0, 3);
    case "10y": return last - 10 * 365.25 * DAY;
  }
}

function useWidth<T extends HTMLElement>(): [React.RefObject<T>, number] {
  const ref = useRef<T>(null);
  const [w, setW] = useState(900);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(320, Math.floor(e.contentRect.width))));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w];
}

const fmtDate = (iso: string) =>
  new Date(iso + "T00:00:00Z").toLocaleDateString("en-US", { timeZone: "UTC", year: "numeric", month: "short", day: "numeric" });

function parseHash(): { chamber: Chamber; range: Range } {
  const [, chamber, range] = window.location.hash.replace(/^#\/?/, "").split("/");
  return {
    chamber: chamber === "senate" ? "senate" : "house",
    range: (RANGES.map((r) => r[0]) as string[]).includes(range) ? (range as Range) : "1945",
  };
}

export function SeatsTimeline() {
  const [file, setFile] = useState<SeatsFile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const init = parseHash();
  const [chamber, setChamber] = useState<Chamber>(init.chamber);
  const [range, setRange] = useState<Range>(init.range);
  const [caucus, setCaucus] = useState(true);
  const [hover, setHover] = useState<number | null>(null);
  const [wrapRef, width] = useWidth<HTMLDivElement>();

  useEffect(() => {
    loadSeats().then(setFile, (e) => setError(String(e)));
  }, []);
  useEffect(() => {
    window.history.replaceState(null, "", `#/congress/${chamber}/${range}`);
  }, [chamber, range]);

  const rows = useMemo(() => (file ? seatRows(file, chamber, caucus) : []), [file, chamber, caucus]);
  const now = Date.now();
  const x0 = rows.length ? Math.max(rangeStart(range, now), rows[0].t) : 0;
  const x1 = now;

  // Rows visible in the window; the first is the state in force at x0.
  const vis = useMemo(() => {
    if (!rows.length) return [] as SeatRow[];
    const i0 = Math.max(0, rowAt(rows, x0));
    return rows.slice(i0).filter((r, i) => i === 0 || r.t <= x1);
  }, [rows, x0, x1]);

  const yMax = vis.reduce((a, r) => Math.max(a, r.seats, r.dem + r.rep + r.other), 0);
  const iw = width - M.left - M.right;
  const ih = H - M.top - M.bottom;
  const sx = (t: number) => M.left + ((Math.max(t, x0) - x0) / (x1 - x0)) * iw;
  const sy = (v: number) => M.top + ih - (v / (yMax || 1)) * ih;

  // Stacked step areas: each layer's band [lo, hi] per row, drawn as horizontal steps.
  const paths = useMemo(() => {
    const out: Record<string, string> = {};
    let base = vis.map(() => 0);
    for (const s of SERIES) {
      const top = vis.map((r, i) => base[i] + r[s.key]);
      let d = "";
      vis.forEach((_, i) => {
        const a = sx(vis[i].t);
        const b = i + 1 < vis.length ? sx(vis[i + 1].t) : sx(x1);
        d += `${i ? "L" : "M"}${a},${sy(top[i])}L${b},${sy(top[i])}`;
      });
      for (let i = vis.length - 1; i >= 0; i--) {
        const a = sx(vis[i].t);
        const b = i + 1 < vis.length ? sx(vis[i + 1].t) : sx(x1);
        d += `L${b},${sy(base[i])}L${a},${sy(base[i])}`;
      }
      out[s.key] = d + "Z";
      base = top;
    }
    // Majority line: more than half the seats that exist.
    out.majority = vis
      .map((r, i) => {
        const a = sx(r.t);
        const b = i + 1 < vis.length ? sx(vis[i + 1].t) : sx(x1);
        const y = sy(Math.floor(r.seats / 2) + 1);
        return `${i ? "L" : "M"}${a},${y}L${b},${y}`;
      })
      .join("");
    return out;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vis, width, yMax, x0, x1]);

  const years = useMemo(() => {
    const y0 = new Date(x0).getUTCFullYear();
    const y1 = new Date(x1).getUTCFullYear();
    const span = y1 - y0;
    const step = [1, 2, 4, 10, 20, 50].find((s) => span / s <= Math.max(4, iw / 80)) ?? 50;
    const out: number[] = [];
    for (let y = Math.ceil(y0 / step) * step; y <= y1; y += step) out.push(y);
    return out;
  }, [x0, x1, iw]);

  const yTicks = useMemo(() => {
    const step = yMax > 200 ? 100 : yMax > 60 ? 20 : 10;
    const out: number[] = [];
    for (let v = 0; v <= yMax; v += step) out.push(v);
    return out;
  }, [yMax]);

  const onMove = (e: React.PointerEvent<SVGRectElement>) => {
    const box = e.currentTarget.getBoundingClientRect();
    const t = x0 + ((e.clientX - box.left) / box.width) * (x1 - x0);
    const i = rowAt(vis, t);
    setHover(i >= 0 ? i : 0);
  };
  const onKey = (e: React.KeyboardEvent) => {
    if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
    e.preventDefault();
    const d = e.key === "ArrowLeft" ? -1 : 1;
    setHover((h) => Math.min(vis.length - 1, Math.max(0, (h ?? vis.length - 1) + d)));
  };

  const cur = hover !== null && vis[hover] ? vis[hover] : vis[vis.length - 1];
  const hx = cur ? sx(Math.max(cur.t, x0)) : 0;
  const name = chamber === "house" ? "House" : "Senate";

  return (
    <div className="app seats">
      <header className="top">
        <p className="crumb"><a href="#/president">← Election maps</a></p>
        <h1>Who holds the {name}</h1>
        <p className="lede">
          Seats held by each party, day by day — including vacancies from deaths, resignations and
          late seatings, and party switches.
        </p>
      </header>
      <div className="controls">
        <Segmented label="Chamber" value={chamber} options={[["house", "House"], ["senate", "Senate"]]}
          onChange={(c) => { setChamber(c); setHover(null); }} />
        <Segmented label="Range" value={range} options={RANGES} onChange={(r) => { setRange(r); setHover(null); }} />
        <label className="check" title="Count independents with the party they caucus with (e.g. Sanders, King as Democrats)">
          <input type="checkbox" checked={caucus} onChange={(e) => setCaucus(e.target.checked)} /> Count independents by caucus
        </label>
      </div>
      {error && <p className="error">{error}</p>}
      {!file && !error && <div className="map-loading">Loading…</div>}
      {file && cur && (
        <>
          <ul className="seat-legend" aria-label="Legend">
            {SERIES.map((s) => (
              <li key={s.key}>
                <svg width="12" height="12" aria-hidden="true"><rect width="12" height="12" rx="2" className={s.cls} /></svg>
                {s.label} <b>{cur[s.key]}</b>
              </li>
            ))}
            <li>
              <svg width="16" height="12" aria-hidden="true"><line x1="0" x2="16" y1="6" y2="6" className="majority" /></svg>
              Majority <b>{Math.floor(cur.seats / 2) + 1}</b>
            </li>
            <li className="muted">as of {fmtDate(cur.date)}</li>
          </ul>
          <div className="seats-chart" ref={wrapRef}>
            <svg width={width} height={H} role="img" aria-label={`${name} seats by party over time`}>
              <defs>
                <pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
                  <rect width="6" height="6" className="hatch-bg" />
                  <line x1="0" y1="0" x2="0" y2="6" className="hatch-line" />
                </pattern>
              </defs>
              {yTicks.map((v) => (
                <g key={v}>
                  <line x1={M.left} x2={M.left + iw} y1={sy(v)} y2={sy(v)} className="grid" />
                  <text x={M.left - 6} y={sy(v)} dy="0.32em" textAnchor="end" className="tick">{v}</text>
                </g>
              ))}
              {SERIES.map((s) => (
                <path key={s.key} d={paths[s.key]} className={s.cls} />
              ))}
              <path d={paths.majority} className="majority" fill="none" />
              {years.map((y) => (
                <text key={y} x={sx(Date.UTC(y, 0, 1))} y={H - 8} textAnchor="middle" className="tick">{y}</text>
              ))}
              {hover !== null && <line x1={hx} x2={hx} y1={M.top} y2={M.top + ih} className="crosshair" />}
              <rect
                x={M.left} y={M.top} width={iw} height={ih} fill="transparent" tabIndex={0}
                aria-label="Move through changes with the arrow keys"
                onPointerMove={onMove} onPointerLeave={() => setHover(null)} onKeyDown={onKey}
                onBlur={() => setHover(null)}
              />
            </svg>
            {hover !== null && (
              <div className="tooltip seats-tip" style={{ left: Math.min(hx + 12, width - 280), top: M.top + 8 }}>
                <b>{fmtDate(cur.date)}</b>
                <table>
                  <tbody>
                    {cur.byParty.map(([p, k]) => <tr key={p}><td>{p}</td><td>{k}</td></tr>)}
                    {cur.vacant > 0 && <tr><td>Vacant</td><td>{cur.vacant}</td></tr>}
                  </tbody>
                </table>
                {cur.changes.length > 0 && cur.changes.length <= 12 && (
                  <ul className="changes">
                    {cur.changes.map((c, i) => (
                      <li key={i}>{c.dir > 0 ? "+" : "−"} {c.name} ({c.party[0]}-{c.state})</li>
                    ))}
                  </ul>
                )}
                {cur.changes.length > 12 && <p className="muted">New Congress: {cur.changes.length} members in/out</p>}
              </div>
            )}
          </div>
          <ChangesTable rows={vis} />
          <p className="source">
            Source: <a href="https://github.com/unitedstates/congress-legislators">@unitedstates/congress-legislators</a>,
            with mid-Congress dates before 1989 from Wikipedia's per-Congress “Changes in membership” tables.
            House seats before 1913 are the most members sitting at once in each Congress, so early vacancies are a
            lower bound. Built {file.built}.
          </p>
        </>
      )}
    </div>
  );
}

/** Text view of mid-term changes (start-of-Congress turnover left out), newest first. */
function ChangesTable({ rows }: { rows: SeatRow[] }) {
  const items = useMemo(
    () => rows.filter((r, i) => i > 0 && r.changes.length <= 12).reverse(),
    [rows],
  );
  return (
    <details className="seat-table">
      <summary>Table: {items.length} mid-term changes in this range</summary>
      <table>
        <thead>
          <tr><th>Date</th><th>Change</th><th>D</th><th>R</th><th>Other</th><th>Vacant</th></tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.date}>
              <td>{fmtDate(r.date)}</td>
              <td>{r.changes.map((c) => `${c.dir > 0 ? "+" : "−"} ${c.name} (${c.party[0]}-${c.state})`).join("; ")}</td>
              <td>{r.dem}</td><td>{r.rep}</td><td>{r.other}</td><td>{r.vacant}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}
