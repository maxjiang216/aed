import { useEffect, useMemo, useState } from "react";
import { Controls } from "./components/Controls";
import { Legend } from "./components/Legend";
import { MapView, type Hover } from "./components/MapView";
import { NationalPanel, RacePanel, TooltipBody } from "./components/RacePanel";
import { loadCounties, loadIndex, loadStatewide } from "./data";
import { loadShapes, type Shapes } from "./geo";
import { fillFor, nationalEnv, partyHues, pickRace, previousRace, type Env } from "./model";
import { STATES } from "./states";
import type { CountyFile, DataIndex, Level, Office, Race, Selection, StatewideFile, View } from "./types";

const OFFICES: Office[] = ["president", "senate", "governor"];
const VIEWS: View[] = ["result", "bias", "flip", "shift", "trend"];

function parseHash(): Partial<Selection> {
  const [office, level, year, view, seat] = window.location.hash.replace(/^#\/?/, "").split("/");
  return {
    office: OFFICES.includes(office as Office) ? (office as Office) : undefined,
    level: level === "county" || level === "state" ? level : undefined,
    year: year ? Number(year) : undefined,
    view: VIEWS.includes(view as View) ? (view as View) : undefined,
    seat: seat === "special" ? "special" : undefined,
  };
}

function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): { value: T | null; error: string | null } {
  const [state, setState] = useState<{ value: T | null; error: string | null }>({ value: null, error: null });
  useEffect(() => {
    let live = true;
    fn().then(
      (value) => live && setState({ value, error: null }),
      (e) => live && setState({ value: null, error: String(e) }),
    );
    return () => {
      live = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return state;
}

export default function App() {
  const index = useAsync(loadIndex, []);
  const [sel, setSel] = useState<Selection>(() => ({
    office: "president",
    level: "state",
    year: 0,
    view: "result",
    seat: "regular",
    ...Object.fromEntries(Object.entries(parseHash()).filter(([, v]) => v !== undefined)),
  }));
  const [hover, setHover] = useState<Hover | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  const years = useMemo(() => yearsFor(index.value, sel.office, sel.level), [index.value, sel.office, sel.level]);

  // Keep the selection valid for what the data offers.
  useEffect(() => {
    if (!index.value) return;
    const levels = Object.keys(index.value.offices[sel.office]) as Level[];
    if (!levels.includes(sel.level)) return setSel((s) => ({ ...s, level: "state" }));
    if (years.length && !years.includes(sel.year)) {
      const nearest = years.reduce((a, b) => (Math.abs(b - sel.year) < Math.abs(a - sel.year) ? b : a));
      setSel((s) => ({ ...s, year: sel.year ? nearest : years[years.length - 1] }));
    }
  }, [index.value, sel.office, sel.level, sel.year, years]);

  useEffect(() => {
    const h = `#/${sel.office}/${sel.level}/${sel.year}/${sel.view}${sel.seat === "special" ? "/special" : ""}`;
    if (sel.year && window.location.hash !== h) window.history.replaceState(null, "", h);
  }, [sel]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.target instanceof HTMLSelectElement || e.target instanceof HTMLInputElement) return;
      const i = years.indexOf(sel.year);
      if (e.key === "ArrowLeft" && i > 0) setSel((s) => ({ ...s, year: years[i - 1] }));
      if (e.key === "ArrowRight" && i >= 0 && i < years.length - 1) setSel((s) => ({ ...s, year: years[i + 1] }));
      if (e.key === "Escape") setSelected(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [years, sel.year]);

  const statewide = useAsync(() => loadStatewide(sel.office), [sel.office]);
  const shapes = useAsync(() => loadShapes(sel.level), [sel.level]);
  const prevCountyYear = years.filter((y) => y < sel.year).pop();
  const counties = useAsync<[CountyFile, CountyFile | null] | null>(
    () =>
      sel.level === "county" && sel.year
        ? Promise.all([
            loadCounties(sel.office, sel.year),
            prevCountyYear ? loadCounties(sel.office, prevCountyYear) : Promise.resolve(null),
          ])
        : Promise.resolve(null),
    [sel.level, sel.office, sel.year, prevCountyYear],
  );

  const stateYears = useMemo(() => yearsFor(index.value, sel.office, "state"), [index.value, sel.office]);
  const model = useMemo(
    () => buildModel(sel, statewide.value, stateYears, counties.value, shapes.value),
    [sel, statewide.value, stateYears, counties.value, shapes.value],
  );

  const hasSpecial = useMemo(() => {
    const yr = statewide.value?.[sel.year];
    return sel.office === "senate" && !!yr && Object.values(yr).some((rs) => rs.some((r) => r.s));
  }, [statewide.value, sel.office, sel.year]);

  const error = index.error || statewide.error || shapes.error || counties.error;
  const focus = selected ?? hover?.id ?? null;

  return (
    <div className="app">
      <header className="top">
        <h1>American Elections Database</h1>
        <p className="lede">U.S. statewide election results, 1828–present. Margin = (1st − 2nd) ÷ all votes cast.</p>
      </header>
      {index.value && (
        <Controls
          index={index.value}
          sel={sel}
          years={years}
          hasSpecial={hasSpecial}
          onChange={(patch) => {
            setSel((s) => ({ ...s, ...patch }));
            if (patch.office || patch.level) setSelected(null);
          }}
        />
      )}
      {error && <p className="error">Could not load data: {error}</p>}
      <main className="layout">
        <section className="map-wrap" aria-label="Map">
          {shapes.value && model ? (
            <MapView
              shapes={shapes.value}
              fills={model.fills}
              selected={selected}
              onHover={setHover}
              onSelect={(id) => setSelected((cur) => (cur === id ? null : id))}
            />
          ) : (
            <div className="map-loading">Loading…</div>
          )}
          {hover && model && (
            <div className="tooltip" style={{ left: hover.x, top: hover.y }} role="status">
              <TooltipBody name={regionName(hover.id, shapes.value)} race={model.shown(hover.id)} />
            </div>
          )}
          {model && <Legend view={sel.view} hues={model.hues} />}
        </section>
        <aside className="panel">
          {model && focus ? (
            <RacePanel
              title={regionName(focus, shapes.value)}
              races={model.racesFor(focus)}
              year={sel.year}
              office={sel.office}
              hues={model.hues}
              prev={model.prevFor(focus)}
              pinned={selected !== null}
              onClose={() => setSelected(null)}
            />
          ) : model ? (
            <NationalPanel sel={sel} races={model.stateRaces} hues={model.hues} env={model.env} />
          ) : null}
        </aside>
      </main>
      <footer className="foot">
        Sources: MIT Election Data + Science Lab; Algara &amp; Amlani (Harvard Dataverse); Wikipedia results-by-state
        tables (CC BY-SA). Map: us-atlas / U.S. Census Bureau.{" "}
        <a href="https://github.com/maxjiang216/aed">Code and data on GitHub</a>.
      </footer>
    </div>
  );
}

function yearsFor(index: DataIndex | null, office: Office, level: Level): number[] {
  return [...(index?.offices[office]?.[level] ?? [])].sort((a, b) => a - b);
}

function regionName(id: string, shapes: Shapes | null): string {
  if (id.length === 2) return STATES[id]?.[1] ?? id;
  const shape = shapes?.regions.find((r) => r.id === id);
  const st = STATES[id.slice(0, 2)]?.[0];
  return shape ? `${shape.properties.name}${st ? `, ${st}` : ""}` : id;
}

export interface MapModel {
  fills: Record<string, string>;
  hues: ReturnType<typeof partyHues>;
  env: Env;
  stateRaces: Race[];
  /** Race shown on the map for a region id (state FIPS or county FIPS). */
  shown: (id: string) => Race | null;
  /** All races in the region this year (Senate: regular, special, runoff). */
  racesFor: (id: string) => Race[];
  prevFor: (id: string) => { race: Race; year: number } | null;
}

export function buildModel(
  sel: Selection,
  statewide: StatewideFile | null,
  stateYears: number[],
  counties: [CountyFile, CountyFile | null] | null,
  shapes: Shapes | null,
): MapModel | null {
  if (!statewide || !shapes || !sel.year) return null;
  const year = statewide[sel.year] ?? {};
  const shownState: Record<string, Race> = {};
  for (const [st, races] of Object.entries(year)) {
    const r = pickRace(races, sel.seat);
    if (r) shownState[st] = r;
  }
  const stateRaces = Object.values(shownState);
  const env = nationalEnv(stateRaces);
  const hues = partyHues(stateRaces);

  const prevState = (st: string) => {
    const r = shownState[st];
    return r ? previousRace(sel.office, statewide, stateYears, sel.year, st, r) : null;
  };
  const envCache = new Map<number, Env>();
  const envOf = (y: number) => {
    if (!envCache.has(y)) {
      const races = Object.values(statewide[y] ?? {}).map((rs) => pickRace(rs)).filter((r): r is Race => !!r);
      envCache.set(y, nationalEnv(races));
    }
    return envCache.get(y)!;
  };

  const fills: Record<string, string> = {};
  if (sel.level === "county") {
    if (!counties) return null;
    const [cur, prev] = counties;
    const prevYear = stateYears.filter((y) => y < sel.year).pop();
    for (const shape of shapes.regions) {
      const race = cur[shape.id];
      if (!race) continue;
      fills[shape.id] = fillFor(race, {
        view: sel.view, hues, env,
        prev: prev?.[shape.id] ?? null,
        prevEnv: prevYear ? envOf(prevYear) : null,
      });
    }
    return {
      fills, hues, env, stateRaces,
      shown: (id) => cur[id] ?? null,
      racesFor: (id) => (cur[id] ? [cur[id]] : []),
      prevFor: (id) => (prev?.[id] && prevYear ? { race: prev[id], year: prevYear } : null),
    };
  }

  for (const shape of shapes.regions) {
    const st = STATES[shape.id]?.[0];
    const race = st ? shownState[st] : undefined;
    if (!race || !st) continue;
    const p = prevState(st);
    fills[shape.id] = fillFor(race, { view: sel.view, hues, env, prev: p?.race ?? null, prevEnv: p ? envOf(p.year) : null });
  }
  const postal = (id: string) => STATES[id]?.[0] ?? "";
  return {
    fills, hues, env, stateRaces,
    shown: (id) => shownState[postal(id)] ?? null,
    racesFor: (id) => {
      const rs = year[postal(id)] ?? [];
      return sel.seat === "special" ? rs.filter((r) => r.s) : rs;
    },
    prevFor: (id) => prevState(postal(id)),
  };
}
