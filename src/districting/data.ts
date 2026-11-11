import { geoAlbersUsa, geoConicEqualArea, geoPath, geoCentroid } from "d3-geo";
import type { Feature, FeatureCollection, MultiPolygon, Polygon } from "geojson";
import { feature, mesh } from "topojson-client";
import type { GeometryCollection, Topology } from "topojson-specification";
import statesUrl from "us-atlas/states-albers-10m.json?url";

/** Data written by projects/districting/web/export.mjs. */

export type Plan = "metis" | "enacted";
export const PLANS: Plan[] = ["enacted", "metis"];
export const PLAN_LABEL: Record<Plan, string> = { metis: "Shortest border", enacted: "Enacted (2024)" };

export interface PlanMetrics {
  spread: number;
  maxDevPct: number;
  borderKm: number;
  ppMean: number;
  splitCounties: number;
}

export interface PlanProjection {
  dem: number;
  rep: number;
  statewideDem: number;
  efficiencyGap: number;
  competitive: number;
  /** Two-party D share of 2020 president, per district (district n at index n-1). */
  shares: number[];
  /** D seats at each uniform swing in Summary.swings. */
  swing: number[];
}

export interface StateSummary {
  seats: number;
  metrics: Partial<Record<Plan, PlanMetrics | null>>;
  projection: Partial<Record<Plan, PlanProjection | null>>;
}

export interface CitizenState {
  st: string;
  state: string;
  res_pop: number;
  cit_share: number;
  app_pop: number;
  cit_app_pop: number;
  seats_total: number;
  seats_citizen: number;
  delta: number;
}

export interface CitizenElection {
  year: number;
  D_total: number;
  R_total: number;
  D_citizen: number;
  R_citizen: number;
  R_gain: number;
}

export interface Summary {
  generated: string;
  swings: number[];
  states: Record<string, StateSummary>;
  /** Single-district states: 2020 president two-party D share. */
  atLarge: Record<string, number>;
  citizen: { states: CitizenState[]; elections: CitizenElection[] };
}

export interface DistrictProps {
  st: string;
  d: number;
  dem: number | null;
}
type DistrictFeature = Feature<Polygon | MultiPolygon, DistrictProps>;
type PlanTopo = Topology<{ metis: GeometryCollection<DistrictProps>; enacted: GeometryCollection<DistrictProps> }>;
type StatesTopo = Topology<{ states: GeometryCollection<{ name: string }>; nation: GeometryCollection }>;

const BASE = `${import.meta.env.BASE_URL}districting/`;
const cache = new Map<string, Promise<unknown>>();
function getJson<T>(url: string): Promise<T> {
  if (!cache.has(url)) {
    cache.set(url, fetch(url).then((r) => {
      if (!r.ok) throw new Error(`${r.status} loading ${url}`);
      return r.json();
    }));
  }
  return cache.get(url) as Promise<T>;
}

export const loadSummary = () => getJson<Summary>(`${BASE}summary.json`);

export interface MapPath {
  id: string; // "IA-3", or state postal code for whole states
  st: string;
  d: number | null;
  path: string;
}

export interface NationalShapes {
  plans: Record<Plan, MapPath[]>;
  /** Whole-state shapes (FIPS-keyed names in us-atlas -> postal codes by the caller). */
  states: { name: string; path: string }[];
  borders: string;
  outline: string;
}

/** Same Albers USA framing as the election maps (us-atlas, 975 x 610). */
const albers = geoAlbersUsa().scale(1300).translate([487.5, 305]);
export const NATIONAL_SIZE = [975, 610] as const;

const districtsOf = (topo: PlanTopo, plan: Plan) =>
  (feature(topo, topo.objects[plan]) as FeatureCollection<Polygon | MultiPolygon, DistrictProps>).features;

export async function loadNational(): Promise<NationalShapes> {
  const [topo, st] = await Promise.all([getJson<PlanTopo>(`${BASE}national.json`), getJson<StatesTopo>(statesUrl)]);
  const project = geoPath(albers);
  const planar = geoPath();
  const toPaths = (fs: DistrictFeature[]) =>
    fs.map((f) => ({ id: `${f.properties.st}-${f.properties.d}`, st: f.properties.st, d: f.properties.d, path: project(f) ?? "" }));
  const enacted = toPaths(districtsOf(topo, "enacted"));
  const metis = toPaths(districtsOf(topo, "metis"));
  // States with no shortest-border plan fall back to their enacted districts.
  const hasMetis = new Set(metis.map((p) => p.st));
  const states = (feature(st, st.objects.states) as FeatureCollection<Polygon | MultiPolygon, { name: string }>)
    .features.map((f) => ({ name: f.properties.name, path: planar(f) ?? "" }));
  return {
    plans: { enacted, metis: [...metis, ...enacted.filter((p) => !hasMetis.has(p.st))] },
    states,
    borders: planar(mesh(st, st.objects.states, (a, b) => a !== b)) ?? "",
    outline: planar(mesh(st, st.objects.nation)) ?? "",
  };
}

export interface StateShapes {
  plans: Partial<Record<Plan, MapPath[]>>;
  outline: string;
  size: [number, number];
}

/** One state's districts, both plans framed identically. */
export async function loadState(st: string, width = 480): Promise<StateShapes> {
  const topo = await getJson<PlanTopo>(`${BASE}states/${st}.json`);
  const layers = (["enacted", "metis"] as Plan[]).filter((p) => topo.objects[p]);
  const all = layers.flatMap((p) => districtsOf(topo, p));
  const fc: FeatureCollection = { type: "FeatureCollection", features: all };
  const [lon] = geoCentroid(fc);
  const proj = geoConicEqualArea().parallels([29.5, 45.5]).rotate([-lon, 0]);
  proj.fitWidth(width, fc);
  const path = geoPath(proj);
  const [[, y0], [, y1]] = path.bounds(fc);
  const plans: StateShapes["plans"] = {};
  for (const p of layers) {
    plans[p] = districtsOf(topo, p).map((f) => ({ id: `${st}-${f.properties.d}`, st, d: f.properties.d, path: path(f) ?? "" }));
  }
  const outline = path(mesh(topo, topo.objects[layers[0]], (a, b) => a === b)) ?? "";
  return { plans, outline, size: [width, Math.ceil(y1 - y0 + 2)] };
}
