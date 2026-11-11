import { useEffect, useMemo, useState, type MouseEvent } from "react";
import { marginColor } from "../aed/colors";
import { STATES } from "../aed/states";
import {
  loadNational, loadState, loadSummary, NATIONAL_SIZE, PLAN_LABEL, PLANS,
  type MapPath, type NationalShapes, type Plan, type StateShapes, type Summary,
} from "./data";

const NAME_TO_POSTAL = Object.fromEntries(Object.values(STATES).map(([postal, name]) => [name, postal]));
const POSTAL_NAME = Object.fromEntries(Object.values(STATES).map(([postal, name]) => [postal, name]));
const ZERO = 20; // index of 0 in summary.swings

type Route = { tab: "map"; st: string | null } | { tab: "citizen" };

function parseRoute(): Route {
  const [, tab, st] = window.location.hash.replace(/^#\/?/, "").split("/");
  if (tab === "citizen") return { tab: "citizen" };
  return { tab: "map", st: st && /^[A-Z]{2}$/.test(st) ? st : null };
}

function useAsync<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [s, set] = useState<{ value: T | null; error: string | null }>({ value: null, error: null });
  useEffect(() => {
    let live = true;
    set({ value: null, error: null });
    fn().then((value) => live && set({ value, error: null }), (e) => live && set({ value: null, error: String(e) }));
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return s;
}

/** D two-party share after a uniform swing -> map colour (same scale as the election maps). */
function shareFill(share: number | null | undefined, swing: number): string {
  if (share == null) return "var(--no-data)";
  const s = share + swing;
  return marginColor(Math.abs(2 * s - 1), s > 0.5 ? "Blue" : "Red");
}

const pct = (x: number, d = 1) => `${(x * 100).toFixed(d)}%`;
const marginText = (share: number) => {
  const m = (2 * share - 1) * 100;
  return Math.abs(m) < 0.05 ? "Tie" : `${m > 0 ? "D" : "R"}+${Math.abs(m).toFixed(1)}`;
};
const swingText = (sw: number) => (Math.abs(sw) < 1e-9 ? "none (2020 result)" : `${sw > 0 ? "D" : "R"}+${Math.abs(sw * 100).toFixed(1)} pts`);

export function DistrictsPage() {
  const [route, setRoute] = useState(parseRoute);
  useEffect(() => {
    const on = () => setRoute(parseRoute());
    window.addEventListener("hashchange", on);
    return () => window.removeEventListener("hashchange", on);
  }, []);
  const summary = useAsync(loadSummary, []);

  return (
    <div className="app districts">
      <header className="top">
        <h1>{route.tab === "citizen" ? "Citizen apportionment" : "Shortest-border districts"}</h1>
        <p className="lede">
          {route.tab === "citizen"
            ? "House seats and electoral votes if each state's population counted only citizens."
            : "Equal-population House districts drawn from 2020 census blocks to minimise total border length, and how they would have voted."}
        </p>
      </header>
      <div className="controls">
        <div className="segmented" role="tablist">
          <a role="tab" className={route.tab === "map" ? "on" : ""} aria-selected={route.tab === "map"} href="#/districts">District maps</a>
          <a role="tab" className={route.tab === "citizen" ? "on" : ""} aria-selected={route.tab === "citizen"} href="#/districts/citizen">Citizen apportionment</a>
        </div>
      </div>
      {summary.error && <p className="error">Could not load data: {summary.error}</p>}
      {summary.value && (route.tab === "citizen" ? <CitizenTab s={summary.value} /> : <MapTab s={summary.value} st={route.st} />)}
      <footer className="foot">
        Method: census-block graph (TIGER/Line 2020, PL 94-171 population), METIS starting partitions refined in C++ for
        exact population balance and short borders. Ignores the Voting Rights Act, county lines and communities of
        interest. Votes: 2020 presidential results by precinct (VEST) allocated to blocks by population; two-party
        share. Enacted maps: TIGER 2024 (119th Congress). Code: <code>projects/districting</code>.
      </footer>
    </div>
  );
}

/* ---------- maps ---------- */

export function seatsAt(s: Summary, plan: Plan, i: number) {
  let dem = 0;
  let total = 0;
  for (const st of Object.values(s.states)) {
    const p = st.projection[plan] ?? st.projection.enacted;
    total += st.seats;
    if (p) dem += p.swing[i];
  }
  for (const share of Object.values(s.atLarge)) {
    total += 1;
    if (share + s.swings[i] > 0.5) dem += 1;
  }
  return { dem, rep: total - dem, total };
}

function MapTab({ s, st }: { s: Summary; st: string | null }) {
  const [i, setI] = useState(ZERO);
  const swing = s.swings[i];
  return (
    <>
      <div className="controls">
        <label className="opt swing">
          Uniform swing
          <input
            type="range" min={0} max={s.swings.length - 1} value={i}
            onChange={(e) => setI(Number(e.target.value))}
            aria-valuetext={swingText(swing)}
          />
          <b>{swingText(swing)}</b>
          {i !== ZERO && <button className="link" onClick={() => setI(ZERO)}>reset</button>}
        </label>
      </div>
      {st && s.states[st] ? <StateView s={s} st={st} i={i} /> : <NationalView s={s} i={i} />}
    </>
  );
}

function SeatBar({ label, dem, rep }: { label: string; dem: number; rep: number }) {
  return (
    <div className="seatbar">
      <div className="seatbar-label"><span>{label}</span><span><b className="d">{dem} D</b> · <b className="r">{rep} R</b></span></div>
      <div className="seatbar-track">
        <i style={{ flex: dem, background: "var(--s-dem)" }} />
        <i style={{ flex: rep, background: "var(--s-rep)" }} />
        <span className="seatbar-mid" style={{ left: `${(218 / (dem + rep)) * 100}%` }} />
      </div>
    </div>
  );
}

type Hover = { x: number; y: number; title: string; body: string } | null;

function NationalView({ s, i }: { s: Summary; i: number }) {
  const [plan, setPlan] = useState<Plan>("metis");
  const [hover, setHover] = useState<Hover>(null);
  const shapes = useAsync<NationalShapes>(loadNational, []);
  const swing = s.swings[i];

  const shareOf = useMemo(() => {
    const m = new Map<string, number | null>();
    for (const [st, v] of Object.entries(s.states)) {
      for (const p of PLANS) {
        const proj = v.projection[p] ?? v.projection.enacted;
        proj?.shares.forEach((x, k) => m.set(`${p}:${st}-${k + 1}`, x));
      }
    }
    return m;
  }, [s]);

  const totals = PLANS.map((p) => ({ p, ...seatsAt(s, p, i) }));
  const diffs = Object.entries(s.states)
    .map(([st, v]) => {
      const a = v.projection.metis?.swing[i];
      const b = v.projection.enacted?.swing[i];
      return { st, diff: a != null && b != null ? a - b : 0 };
    })
    .filter((d) => d.diff !== 0)
    .sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff) || a.st.localeCompare(b.st));

  const move = (e: MouseEvent, title: string, body: string) => {
    const box = (e.currentTarget.closest(".map-wrap") as HTMLElement).getBoundingClientRect();
    setHover({ x: e.clientX - box.left, y: e.clientY - box.top, title, body });
  };

  return (
    <main className="layout">
      <section className="map-wrap" aria-label="National district map">
        <div className="segmented plan-toggle">
          {PLANS.map((p) => (
            <button key={p} className={plan === p ? "on" : ""} onClick={() => setPlan(p)}>{PLAN_LABEL[p]}</button>
          ))}
        </div>
        {shapes.value ? (
          <svg className="map dmap" viewBox={`0 0 ${NATIONAL_SIZE[0]} ${NATIONAL_SIZE[1]}`} onMouseLeave={() => setHover(null)}>
            <g>
              {shapes.value.states.map((f) => {
                const st = NAME_TO_POSTAL[f.name];
                const at = s.atLarge[st] ?? (s.states[st] && !shapes.value!.plans[plan].some((d) => d.st === st)
                  ? s.states[st].projection.enacted?.statewideDem : undefined);
                return (
                  <path
                    key={f.name} d={f.path} fill={at != null ? shareFill(at, swing) : "var(--no-data)"}
                    onMouseMove={(e) => at != null && move(e, POSTAL_NAME[st] ?? f.name, `${s.atLarge[st] != null ? "At-large" : "Statewide"} · ${marginText(at + swing)}`)}
                    onClick={() => s.states[st] && (window.location.hash = `#/districts/map/${st}`)}
                  />
                );
              })}
            </g>
            <g className="districts">
              {shapes.value.plans[plan].map((d) => {
                const share = shareOf.get(`${plan}:${d.id}`) ?? shareOf.get(`enacted:${d.id}`);
                return (
                  <path
                    key={d.id} d={d.path} fill={shareFill(share, swing)}
                    onMouseMove={(e) => move(e, `${POSTAL_NAME[d.st]} · district ${d.d}`, share == null ? "no data" : marginText(share + swing))}
                    onClick={() => (window.location.hash = `#/districts/map/${d.st}`)}
                  />
                );
              })}
            </g>
            <path className="borders" d={shapes.value.borders} />
            <path className="outline" d={shapes.value.outline} />
          </svg>
        ) : (
          <div className="map-loading">{shapes.error ?? "Loading…"}</div>
        )}
        {hover && (
          <div className="tooltip" style={{ left: hover.x, top: hover.y }} role="status">
            <b>{hover.title}</b><br />{hover.body}
          </div>
        )}
        <p className="hint muted">Colour: 2020 presidential two-party margin in each district{swing ? `, shifted ${swingText(swing)}` : ""}. Click a state to compare its maps.</p>
      </section>
      <aside className="panel">
        <h2>House seats</h2>
        <p className="small muted">If every district voted like its 2020 presidential result{swing ? ` with a uniform ${swingText(swing)} swing` : ""}.</p>
        {totals.map((t) => <SeatBar key={t.p} label={PLAN_LABEL[t.p]} dem={t.dem} rep={t.rep} />)}
        <h3>Where the maps differ</h3>
        {diffs.length ? (
          <ul className="diffs">
            {diffs.map((d) => (
              <li key={d.st}>
                <a href={`#/districts/map/${d.st}`}>{POSTAL_NAME[d.st]}</a>
                <span className={d.diff > 0 ? "d" : "r"}>{d.diff > 0 ? `+${d.diff} D` : `+${-d.diff} R`}</span>
              </li>
            ))}
          </ul>
        ) : <p className="small muted">Same seat count in every state at this swing.</p>}
        <p className="note">No valid shortest-border plan for Hawaii or Louisiana yet; their enacted maps are used.
          Shortest-border maps drop the court-ordered majority-Black districts in Alabama and elsewhere.</p>
      </aside>
    </main>
  );
}

function StateView({ s, st, i }: { s: Summary; st: string; i: number }) {
  const shapes = useAsync<StateShapes>(() => loadState(st), [st]);
  const [hover, setHover] = useState<Hover>(null);
  const v = s.states[st];
  const swing = s.swings[i];
  const shown = PLANS.filter((p) => v.metrics[p]);
  const options = Object.keys(s.states).sort();

  const row = (label: string, f: (p: Plan) => string | number | null | undefined, hint?: string) => (
    <tr>
      <th scope="row">{label}{hint && <span className="muted small"> {hint}</span>}</th>
      {shown.map((p) => <td key={p}>{f(p) ?? "—"}</td>)}
    </tr>
  );
  const proj = (p: Plan) => v.projection[p];
  const met = (p: Plan) => v.metrics[p];

  return (
    <main className="state-view">
      <p className="crumb">
        <a href="#/districts">← National map</a>{" "}
        <select value={st} onChange={(e) => (window.location.hash = `#/districts/map/${e.target.value}`)} aria-label="State">
          {options.map((o) => <option key={o} value={o}>{POSTAL_NAME[o]}</option>)}
        </select>
      </p>
      <div className="map-wrap pair" onMouseLeave={() => setHover(null)}>
        {shapes.value ? shown.map((p) => {
          const ds = shapes.value!.plans[p];
          const pr = proj(p);
          return (
            <figure key={p}>
              <figcaption>
                <b>{PLAN_LABEL[p]}</b>{" "}
                {pr && <span className="muted">{pr.swing[i]} D · {v.seats - pr.swing[i]} R</span>}
              </figcaption>
              {ds ? (
                <svg className="map dmap" viewBox={`0 0 ${shapes.value!.size[0]} ${shapes.value!.size[1]}`}>
                  {ds.map((d: MapPath) => {
                    const share = pr?.shares[(d.d ?? 1) - 1];
                    return (
                      <path
                        key={d.id} d={d.path} fill={shareFill(share, swing)}
                        onMouseMove={(e) => {
                          const box = (e.currentTarget.closest(".pair") as HTMLElement).getBoundingClientRect();
                          setHover({ x: e.clientX - box.left, y: e.clientY - box.top, title: `District ${d.d}`, body: share == null ? "no data" : `${marginText(share + swing)} (D ${pct(share + swing)})` });
                        }}
                      />
                    );
                  })}
                  <path className="outline" d={shapes.value!.outline} />
                </svg>
              ) : <div className="map-loading">No shapes</div>}
            </figure>
          );
        }) : <div className="map-loading">{shapes.error ?? "Loading…"}</div>}
        {hover && (
          <div className="tooltip" style={{ left: hover.x, top: hover.y }} role="status">
            <b>{hover.title}</b><br />{hover.body}
          </div>
        )}
      </div>
      {!v.metrics.metis && <p className="note">No shortest-border plan found for {POSTAL_NAME[st]} yet.</p>}
      <table className="metrics">
        <thead>
          <tr><th />{shown.map((p) => <th key={p} scope="col">{PLAN_LABEL[p]}</th>)}</tr>
        </thead>
        <tbody>
          {row("Seats (D–R)", (p) => proj(p) && `${proj(p)!.swing[i]}–${v.seats - proj(p)!.swing[i]}`, swing ? `at ${swingText(swing)}` : "2020 president")}
          {row("Competitive seats", (p) => proj(p)?.competitive, "within 5 pts, 2020")}
          {row("Efficiency gap", (p) => proj(p) && `${pct(Math.abs(proj(p)!.efficiencyGap))} ${proj(p)!.efficiencyGap > 0 ? "favours R" : "favours D"}`, "2020")}
          {row("Total internal border", (p) => met(p) && `${Math.round(met(p)!.borderKm).toLocaleString()} km`)}
          {row("Compactness", (p) => met(p)?.ppMean.toFixed(2), "mean Polsby-Popper")}
          {row("Counties split", (p) => met(p)?.splitCounties)}
          {row("Population spread", (p) => met(p) && `${met(p)!.spread.toLocaleString()} people`, "largest − smallest")}
        </tbody>
      </table>
      <p className="hint muted">Statewide 2020 two-party D share {pct(v.projection.enacted?.statewideDem ?? 0)}. Enacted-map population spreads use unadjusted census counts; some states reallocate prisoners.</p>
    </main>
  );
}

/* ---------- citizen apportionment ---------- */

function CitizenTab({ s }: { s: Summary }) {
  const [all, setAll] = useState(false);
  const rows = s.citizen.states
    .filter((r) => all || r.delta !== 0)
    .sort((a, b) => (all ? a.state.localeCompare(b.state) : a.delta - b.delta));
  return (
    <main className="germany-grid">
      <section>
        <h2>House seats</h2>
        <p className="small muted">Huntington–Hill on 2020 census resident population × ACS 2016–20 citizen share, plus the
          overseas count. The total-population baseline reproduces the official 2020 apportionment exactly.</p>
        <table className="metrics">
          <thead><tr><th scope="col">State</th><th scope="col">Citizen share</th><th scope="col">Seats now</th><th scope="col">Citizens only</th><th scope="col">Change</th></tr></thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.st}>
                <th scope="row">{r.state}</th>
                <td>{pct(r.cit_share)}</td>
                <td>{r.seats_total}</td>
                <td>{r.seats_citizen}</td>
                <td className={r.delta > 0 ? "d-strong" : r.delta < 0 ? "r-strong" : ""}>{r.delta > 0 ? `+${r.delta}` : r.delta || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <label className="check small"><input type="checkbox" checked={all} onChange={(e) => setAll(e.target.checked)} /> Show all states</label>
      </section>
      <section>
        <h2>Electoral College</h2>
        <p className="small muted">Each presidential result re-scored with both apportionments (2020-census base for both,
          so only the population measure changes).</p>
        <table className="metrics">
          <thead><tr><th scope="col">Year</th><th scope="col">Actual base (D–R)</th><th scope="col">Citizens only</th><th scope="col">R gain</th></tr></thead>
          <tbody>
            {s.citizen.elections.map((e) => (
              <tr key={e.year}>
                <th scope="row">{e.year}</th>
                <td>{e.D_total}–{e.R_total}</td>
                <td>{e.D_citizen}–{e.R_citizen}</td>
                <td>+{e.R_gain}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <p className="note">No winner changes. ACS undercounts non-citizens, so the real shift would likely be larger.</p>
      </section>
    </main>
  );
}
