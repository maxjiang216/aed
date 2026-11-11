import { geoAlbersUsa, geoPath } from "d3-geo";
import { feature, mesh } from "topojson-client";
import type { Feature, Geometry } from "geojson";
import type { GeometryCollection, Topology } from "topojson-specification";
import countiesUrl from "us-atlas/counties-albers-10m.json?url";
import statesUrl from "us-atlas/states-albers-10m.json?url";

/** us-atlas shapes are pre-projected (Albers USA) into a 975 x 610 box; district shapes are
 *  lon/lat and get the same projection here so state borders line up. */
export const WIDTH = 975;
export const HEIGHT = 610;
const albers = geoAlbersUsa().scale(1300).translate([487.5, 305]);
const planar = geoPath();
const projected = geoPath(albers);

export interface Region {
  id: string; // state FIPS "06", county FIPS "06037", district "CA-12"
  name: string;
  d: string; // SVG path
}

export interface Shapes {
  regions: Region[];
  borders: string; // state borders drawn on top
  outline: string;
}

type Props = { name?: string; id?: string };
type Atlas = Topology<{
  states: GeometryCollection<Props>;
  counties?: GeometryCollection<Props>;
  nation: GeometryCollection;
  districts?: GeometryCollection<Props>;
}>;

const cache = new Map<string, Promise<Shapes>>();
const getJson = <T,>(url: string) => fetch(url).then((r) => {
  if (!r.ok) throw new Error(`${r.status} loading ${url}`);
  return r.json() as Promise<T>;
});

const statesTopo = () => getJson<Atlas>(statesUrl);

function stateLines(topo: Atlas) {
  return {
    borders: planar(mesh(topo, topo.objects.states, (a, b) => a !== b)) ?? "",
    outline: planar(mesh(topo, topo.objects.nation)) ?? "",
  };
}

export function loadShapes(level: "state" | "county" | "district"): Promise<Shapes> {
  if (!cache.has(level)) {
    cache.set(level, getJson<Atlas>(level === "state" ? statesUrl : countiesUrl).then((topo) => {
      const obj = level === "county" ? topo.objects.counties! : topo.objects.states;
      const fc = feature(topo, obj) as unknown as { features: (Feature<Geometry, Props> & { id: string | number })[] };
      return {
        regions: fc.features.map((f) => ({ id: String(f.id), name: f.properties.name ?? "", d: planar(f) ?? "" })),
        ...stateLines(topo),
      };
    }));
  }
  return cache.get(level)!;
}

export interface DistrictMeta {
  congressFile: Record<string, string>;
  redistricted: Record<string, string[]>;
  congressSource: Record<string, string>;
}

export const loadDistrictMeta = () =>
  getJson<DistrictMeta>(`${import.meta.env.BASE_URL}data/house/shapes/meta.json`);

/** Congress seated after an election held in `year` (odd years: the sitting Congress). */
export function congressFor(year: number): number {
  return year % 2 === 0 ? (year - 1786) / 2 : (year - 1787) / 2;
}

export function loadDistrictShapes(file: string): Promise<Shapes> {
  const key = `district:${file}`;
  if (!cache.has(key)) {
    cache.set(key, Promise.all([
      getJson<Atlas>(`${import.meta.env.BASE_URL}data/house/shapes/${file}`),
      statesTopo(),
    ]).then(([topo, st]) => {
      const fc = feature(topo, topo.objects.districts!) as unknown as { features: Feature<Geometry, Props>[] };
      return {
        regions: fc.features.map((f) => ({ id: f.properties.id!, name: f.properties.id!, d: projected(f) ?? "" })),
        ...stateLines(st),
      };
    }));
  }
  return cache.get(key)!;
}
