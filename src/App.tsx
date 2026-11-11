import { useEffect, useMemo, useState } from "react";
import { Controls } from "./components/Controls";
import { Legend } from "./components/Legend";
import { MapView, type Hover } from "./components/MapView";
import { NationalPanel, RacePanel, TooltipBody } from "./components/RacePanel";
import { loadCounties, loadHouse, loadIndex, loadStatewide } from "./data";
import {
  congressFor, loadDistrictMeta, loadDistrictShapes, loadShapes, type DistrictMeta, type Shapes,
} from "./geo";
import { fillFor, nationalEnv, partyHues, pickRace, previousRace, type Env } from "./model";
import { POSTAL_TO_FIPS, STATES } from "./states";
import type { DataIndex, Level, Office, Race, Selection, StatewideFile, View } from "./types";

const OFFICES: Office[] = ["president", "senate", "governor", "house"];
const LEVELS: Level[] = ["state", "county", "district"];
const VIEWS: View[] = ["result", "bias", "flip", "shift", "trend"];

function parseHash(): Partial<Selection> {
  const [office, level, year, view, seat] = window.location.hash.replace(/^#\/?/, "").split("/");
  return {
    office: OFFICES.includes(office as Office) ? (office as Office) : undefined,
    level: LEVELS.includes(level as Level) ? (level as Level) : undefined,
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

/** Races per region for one year, keyed by map region id, plus the previous year's. */
export interface LocalData {
  cur: Record<string, Race[]>;
  prev: Record<string, Race[]> | null;
  prevYear: number | null;
  /** States redrawn since prevYear (House): no like-for-like comparison there. */
  redrawn?: Set<string>;
}

async function loadLocal(sel: Selection, years: number[], meta: DistrictMeta | null): Promise<LocalData | null> {
  const prevYear = years.filter((y) => y < sel.year).pop() ?? null;
  if (sel.level === "county") {
    const wrap = (f: Record<string, Race>) => Object.fromEntries(Object.entries(f).map(([k, r]) => [k, [r]]));
    const [cur, prev] = await Promise.all([
      loadCounties(sel.office, sel.year),
      prevYear ? loadCounties(sel.office, prevYear) : null,
    ]);
    return { cur: wrap(cur), prev: prev && wrap(prev), prevYear };
  }
  if (sel.level === "district") {
    const [cur, prev] = await Promise.all([loadHouse(sel.year), prevYear ? loadHouse(prevYear) : null]);
    return { cur, prev, prevYear, redrawn: meta && prevYear ? redrawnBetween(meta, prevYear, sel.year) : undefined };
  }
  return null;
}

/** States whose districts changed in any Congress after prevYear's up to year's. */
export function redrawnBetween(meta: DistrictMeta, prevYear: number, year: number): Set<string> {
  const out = new Set<string>();
  for (let c = congressFor(prevYear) + 1; c <= congressFor(year); c++) {
    (meta.redistricted[c] ?? []).forEach((s) => out.add(s));
  }
  return out;
}

function loadMapShapes(sel: Selection, meta: DistrictMeta | null): Promise<Shapes | null> {
  if (sel.level !== "district") return loadShapes(sel.level);
  if (!meta || !sel.year) return Promise.resolve(null);
  const file = meta.congressFile[congressFor(sel.year)];
  return file ? loadDistrictShapes(file) : Promise.reject(new Error(`no district map for ${sel.year}`));
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
    const offices = Object.keys(index.value.offices) as Office[];
    if (!offices.includes(sel.office)) return setSel((s) => ({ ...s, office: "president" }));
    const levels = Object.keys(index.value.offices[sel.office]) as Level[];
    if (!levels.includes(sel.level)) return setSel((s) => ({ ...s, level: levels[0] }));
    if (years.length && !years.includes(sel.year)) {
      const nearest = years.reduce((a, b) => (Math.abs(b - sel.year) < Math.abs(a - sel.year) ? b : a));
      setSel((s) => ({ ...s, year: sel.year ? nearest : years[years.length - 1] }));
    }
  }, [index.value, sel.office, sel.level, sel.year, years]);

  const valid = !!index.value && years.includes(sel.year);

  useEffect(() => {
    const h = `#/${sel.office}/${sel.level}/${sel.year}/${sel.view}${sel.seat === "special" ? "/special" : ""}`;
    if (valid && window.location.hash !== h) window.history.replaceState(null, "", h);
  }, [sel, valid]);

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

  const isHouse = sel.office === "house";
  const meta = useAsync(() => (isHouse ? loadDistrictMeta() : Promise.resolve(null)), [isHouse]);
  const statewide = useAsync(
    () => (isHouse ? Promise.resolve(null) : loadStatewide(sel.office)),
    [sel.office, isHouse],
  );
  const shapes = useAsync(
    () => (valid ? loadMapShapes(sel, meta.value) : Promise.resolve(null)),
    [valid, sel.level, sel.level === "district" ? sel.year : 0, meta.value],
  );
  const local = useAsync(
    () => (valid ? loadLocal(sel, years, meta.value) : Promise.resolve(null)),
    [valid, sel.level, sel.office, sel.year, years, meta.value],
  );

  const stateYears = useMemo(() => yearsFor(index.value, sel.office, "state"), [index.value, sel.office]);
  const model = useMemo(
    () => (valid ? buildModel(sel, statewide.value, stateYears, local.value, shapes.value) : null),
    [valid, sel, statewide.value, stateYears, local.value, shapes.value],
  );

  const hasSpecial = useMemo(() => {
    const yr = statewide.value?.[sel.year];
    return sel.office === "senate" && !!yr && Object.values(yr).some((rs) => rs.some((r) => r.s));
  }, [statewide.value, sel.office, sel.year]);

  const error = index.error || statewide.error || shapes.error || local.error || meta.error;
  const focus = selected ?? hover?.id ?? null;

  return (
    <div className="app">
      <header className="top">
        <h1>American Elections Database</h1>
        <p className="lede">U.S. election results, 1828–present. Margin = (1st − 2nd) ÷ all votes cast.{" "}
          <a href="#/germany">What if the House used Germany's rules?</a>
        </p>
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
              note={model.noteFor(focus)}
              pinned={selected !== null}
              onClose={() => setSelected(null)}
            />
          ) : model ? (
            <NationalPanel sel={sel} races={model.allRaces} hues={model.hues} env={model.env} />
          ) : null}
        </aside>
      </main>
      <footer className="foot">
        Sources: MIT Election Data + Science Lab; Algara &amp; Amlani (Harvard Dataverse); Wikipedia results-by-state
        tables (CC BY-SA); district maps from Lewis et al. (UCLA) and the U.S. Census Bureau. Map: us-atlas.{" "}
        <a href="https://github.com/maxjiang216/aed">Code and data on GitHub</a>.
      </footer>
    </div>
  );
}

function yearsFor(index: DataIndex | null, office: Office, level: Level): number[] {
  return [...(index?.offices[office]?.[level] ?? [])].sort((a, b) => a - b);
}

const ordinal = (n: number) => {
  const s = ["th", "st", "nd", "rd"];
  const v = n % 100;
  return n + (s[(v - 20) % 10] || s[v] || s[0]);
};

export function regionName(id: string, shapes: Shapes | null): string {
  if (/^[A-Z]{2}-/.test(id)) {
    const [st, d] = id.split("-");
    const name = STATES[POSTAL_TO_FIPS[st]]?.[1] ?? st;
    return d === "AL" ? `${name} at-large` : `${name}'s ${ordinal(Number(d))}`;
  }
  if (id.length === 2) return STATES[id]?.[1] ?? id;
  const shape = shapes?.regions.find((r) => r.id === id);
  const st = STATES[id.slice(0, 2)]?.[0];
  return shape ? `${shape.name}${st ? `, ${st}` : ""}` : id;
}

export interface MapModel {
  fills: Record<string, string>;
  hues: ReturnType<typeof partyHues>;
  env: Env;
  /** Every race the map shows (for national totals). */
  allRaces: Race[];
  shown: (id: string) => Race | null;
  /** All races in the region this year (regular, special, runoff). */
  racesFor: (id: string) => Race[];
  prevFor: (id: string) => { race: Race; year: number } | null;
  noteFor: (id: string) => string | null;
}

export function buildModel(
  sel: Selection,
  statewide: StatewideFile | null,
  stateYears: number[],
  local: LocalData | null,
  shapes: Shapes | null,
): MapModel | null {
  if (!shapes || !sel.year) return null;
  if (sel.level === "district") return local ? buildLocal(sel, local, shapes, null, null) : null;
  if (!statewide) return null;

  const year = statewide[sel.year] ?? {};
  const shownState: Record<string, Race> = {};
  for (const [st, races] of Object.entries(year)) {
    const r = pickRace(races, sel.seat);
    if (r) shownState[st] = r;
  }
  const stateRaces = Object.values(shownState);
  const env = nationalEnv(stateRaces);
  const envCache = new Map<number, Env>();
  const envOf = (y: number) => {
    if (!envCache.has(y)) {
      const races = Object.values(statewide[y] ?? {}).map((rs) => pickRace(rs)).filter((r): r is Race => !!r);
      envCache.set(y, nationalEnv(races));
    }
    return envCache.get(y)!;
  };

  if (sel.level === "county") {
    return local ? buildLocal(sel, local, shapes, env, envOf) : null;
  }

  const hues = partyHues(stateRaces);
  const postal = (id: string) => STATES[id]?.[0] ?? "";
  const prevState = (st: string) => {
    const r = shownState[st];
    return r ? previousRace(sel.office, statewide, stateYears, sel.year, st, r) : null;
  };
  const fills: Record<string, string> = {};
  for (const region of shapes.regions) {
    const st = postal(region.id);
    const race = shownState[st];
    if (!race) continue;
    const p = prevState(st);
    fills[region.id] = fillFor(race, { view: sel.view, hues, env, prev: p?.race ?? null, prevEnv: p ? envOf(p.year) : null });
  }
  return {
    fills, hues, env, allRaces: stateRaces,
    shown: (id) => shownState[postal(id)] ?? null,
    racesFor: (id) => {
      const rs = year[postal(id)] ?? [];
      return sel.seat === "special" ? rs.filter((r) => r.s) : rs;
    },
    prevFor: (id) => prevState(postal(id)),
    noteFor: () => null,
  };
}

/** Counties and districts: each region compares with the same id in the previous year.
 *  Without a statewide env (House), the national figure is the sum of the regions. */
function buildLocal(
  sel: Selection,
  local: LocalData,
  shapes: Shapes,
  stateEnv: Env | null,
  envOf: ((y: number) => Env) | null,
): MapModel {
  const shown: Record<string, Race> = {};
  for (const [id, rs] of Object.entries(local.cur)) {
    const r = pickRace(rs);
    if (r) shown[id] = r;
  }
  const prevShown: Record<string, Race> = {};
  for (const [id, rs] of Object.entries(local.prev ?? {})) {
    const r = pickRace(rs);
    if (r) prevShown[id] = r;
  }
  const all = Object.values(shown);
  const env = stateEnv ?? nationalEnv(all);
  const prevEnv = local.prevYear
    ? envOf ? envOf(local.prevYear) : nationalEnv(Object.values(prevShown))
    : null;
  const hues = partyHues(all);
  const redrawn = (id: string) => !!local.redrawn?.has(id.slice(0, 2));
  const prevFor = (id: string) =>
    prevShown[id] && local.prevYear && !redrawn(id) ? { race: prevShown[id], year: local.prevYear } : null;

  const fills: Record<string, string> = {};
  for (const region of shapes.regions) {
    const race = shown[region.id];
    if (!race) continue;
    fills[region.id] = fillFor(race, { view: sel.view, hues, env, prev: prevFor(region.id)?.race ?? null, prevEnv });
  }
  return {
    fills, hues, env, allRaces: all,
    shown: (id) => shown[id] ?? null,
    racesFor: (id) => local.cur[id] ?? [],
    prevFor,
    noteFor: (id) =>
      redrawn(id) && local.prevYear
        ? `District lines in ${id.slice(0, 2)} changed since ${local.prevYear}; flip/shift/trend not compared.`
        : null,
  };
}
