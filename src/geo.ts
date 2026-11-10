import { feature, mesh } from "topojson-client";
import type { Feature, Geometry, MultiLineString } from "geojson";
import type { GeometryCollection, Topology } from "topojson-specification";
import countiesUrl from "us-atlas/counties-albers-10m.json?url";
import statesUrl from "us-atlas/states-albers-10m.json?url";

/** us-atlas shapes are pre-projected (Albers USA) into a 975 x 610 box. */
export const WIDTH = 975;
export const HEIGHT = 610;

export type Shape = Feature<Geometry, { name: string }> & { id: string };

export interface Shapes {
  regions: Shape[];
  borders: MultiLineString; // state borders drawn on top
  outline: MultiLineString;
}

type Atlas = Topology<{ states: GeometryCollection<{ name: string }>; counties?: GeometryCollection<{ name: string }>; nation: GeometryCollection }>;

const cache: Partial<Record<"state" | "county", Promise<Shapes>>> = {};

export function loadShapes(level: "state" | "county"): Promise<Shapes> {
  cache[level] ??= fetch(level === "state" ? statesUrl : countiesUrl)
    .then((r) => r.json() as Promise<Atlas>)
    .then((topo) => {
      const obj = level === "county" ? topo.objects.counties! : topo.objects.states;
      const fc = feature(topo, obj) as unknown as { features: Shape[] };
      return {
        regions: fc.features.map((f) => ({ ...f, id: String(f.id) })),
        borders: mesh(topo, topo.objects.states, (a, b) => a !== b),
        outline: mesh(topo, topo.objects.nation),
      };
    });
  return cache[level]!;
}
