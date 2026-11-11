#!/usr/bin/env node
/**
 * Congressional district shapes for the House map -> public/data/house/shapes/.
 *
 *   95th–114th Congress (elected 1976–2014): Lewis, DeVine, Pritchett & Martis,
 *     "Digital Boundary Definitions of United States Congressional Districts, 1789-2012",
 *     https://cdmaps.polisci.ucla.edu/  (raw/districts/districtsNNN.zip)
 *   115th, 116th (=117th), 118th, 119th: U.S. Census Bureau cartographic boundary files
 *     (raw/districts/cb_YYYY_us_cdNNN_500k.zip)
 *
 * Output: one TopoJSON per distinct map (object "districts", property id "CA-12"/"WY-AL"),
 * kept in lon/lat and projected in the browser with the same Albers USA as us-atlas,
 * plus meta.json mapping each Congress to its file and listing states whose districts
 * changed since the previous Congress (the map greys out flip/shift there).
 *
 * Run: node scripts/ingest/build_district_shapes.mjs   (after fetch_sources.py)
 */
import { execFileSync } from "node:child_process";
import { createHash } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { geoArea, geoCentroid, geoDistance } from "d3-geo";
import mapshaper from "mapshaper";
import { feature, mergeArcs } from "topojson-client";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..", "..");
const RAW = join(ROOT, "raw", "districts");
const WORK = join(RAW, "x");
const OUT = join(ROOT, "..", "..", "public", "data", "house", "shapes"); // hub repo root
// Share of vertices kept (weighted Visvalingam). Percentage, not a fixed distance, so
// Manhattan-sized districts keep their shape while rural ones get coarse.
const KEEP = process.env.SIMPLIFY_PCT ?? "2%";

const STATES = {
  "01": ["AL", "Alabama"], "02": ["AK", "Alaska"], "04": ["AZ", "Arizona"], "05": ["AR", "Arkansas"],
  "06": ["CA", "California"], "08": ["CO", "Colorado"], "09": ["CT", "Connecticut"], "10": ["DE", "Delaware"],
  "12": ["FL", "Florida"], "13": ["GA", "Georgia"], "15": ["HI", "Hawaii"], "16": ["ID", "Idaho"],
  "17": ["IL", "Illinois"], "18": ["IN", "Indiana"], "19": ["IA", "Iowa"], "20": ["KS", "Kansas"],
  "21": ["KY", "Kentucky"], "22": ["LA", "Louisiana"], "23": ["ME", "Maine"], "24": ["MD", "Maryland"],
  "25": ["MA", "Massachusetts"], "26": ["MI", "Michigan"], "27": ["MN", "Minnesota"], "28": ["MS", "Mississippi"],
  "29": ["MO", "Missouri"], "30": ["MT", "Montana"], "31": ["NE", "Nebraska"], "32": ["NV", "Nevada"],
  "33": ["NH", "New Hampshire"], "34": ["NJ", "New Jersey"], "35": ["NM", "New Mexico"], "36": ["NY", "New York"],
  "37": ["NC", "North Carolina"], "38": ["ND", "North Dakota"], "39": ["OH", "Ohio"], "40": ["OK", "Oklahoma"],
  "41": ["OR", "Oregon"], "42": ["PA", "Pennsylvania"], "44": ["RI", "Rhode Island"], "45": ["SC", "South Carolina"],
  "46": ["SD", "South Dakota"], "47": ["TN", "Tennessee"], "48": ["TX", "Texas"], "49": ["UT", "Utah"],
  "50": ["VT", "Vermont"], "51": ["VA", "Virginia"], "53": ["WA", "Washington"], "54": ["WV", "West Virginia"],
  "55": ["WI", "Wisconsin"], "56": ["WY", "Wyoming"],
};
const BY_NAME = Object.fromEntries(Object.values(STATES).map(([p, n]) => [n.toLowerCase(), p]));
const BY_FIPS = Object.fromEntries(Object.entries(STATES).map(([f, [p]]) => [f, p]));

/** Congress -> source. The 117th Congress (elected 2020) used the 116th's districts. */
const SOURCES = {};
for (let c = 95; c <= 114; c++) SOURCES[c] = { zip: `districts${String(c).padStart(3, "0")}`, kind: "lewis" };
SOURCES[115] = { zip: "cb_2017_us_cd115_500k", kind: "census", field: "CD115FP" };
SOURCES[116] = { zip: "cb_2018_us_cd116_500k", kind: "census", field: "CD116FP" };
SOURCES[117] = SOURCES[116];
SOURCES[118] = { zip: "cb_2022_us_cd118_500k", kind: "census", field: "CD118FP" };
SOURCES[119] = { zip: "cb_2024_us_cd119_500k", kind: "census", field: "CD119FP" };

function districtId(postal, n, single) {
  return `${postal}-${n === 0 || single ? "AL" : String(n).padStart(2, "0")}`;
}

async function build(c, src) {
  const shp = join(WORK, src.zip, `${src.zip}.shp`);
  if (!existsSync(shp)) {
    const zip = join(RAW, `${src.zip}.zip`);
    if (!existsSync(zip)) throw new Error(`missing ${zip}; run scripts/ingest/fetch_sources.py`);
    execFileSync("unzip", ["-o", "-q", zip, "-d", join(WORK, src.zip)]);
  }
  // Lewis districts are drawn per state and do not share exact edges: snap + clean so
  // neighbours share arcs (10x smaller files, no slivers).
  const repair = src.kind === "lewis" ? "snap-interval=0.0003 -clean gap-fill-area=5km2 overlap-rule=min-area" : "";
  const run = async (simplify, out) => {
    await mapshaper.runCommands(
      `-i "${shp}" ${repair} -filter-islands min-area=3km2 ${simplify} ` +
        `-o format=topojson quantization=${simplify ? 40000 : 1000000} force "${out}"`,
    );
    const t = JSON.parse(readFileSync(out, "utf8"));
    rmSync(out);
    return label(t, src);
  };
  const full = await run("", join(WORK, `c${c}-full.json`)); // for redistricting detection only
  const topo = await run(`-simplify ${KEEP} weighted keep-shapes`, join(WORK, `c${c}.json`));
  return { topo, print: fingerprint(full) };
}

function label(topo, src) {
  const layer = Object.keys(topo.objects)[0];
  const geoms = topo.objects[layer].geometries;
  // Resolve ids; drop DC, territories and Census "ZZ" (water / undefined).
  const rows = geoms.map((g) => {
    const p = g.properties ?? {};
    if (src.kind === "lewis") {
      return { g, postal: BY_NAME[String(p.STATENAME).toLowerCase()], n: Number(p.DISTRICT) };
    }
    const fp = String(p[src.field] ?? "");
    return { g, postal: BY_FIPS[p.STATEFP], n: /^\d+$/.test(fp) ? Number(fp) : NaN };
  });
  let keep = rows.filter((r) => r.postal && Number.isFinite(r.n) && r.n < 98);
  // Lewis files carry a statewide "district 0" outline for MT/SD even in Congresses where
  // they had two seats; drop it when numbered districts exist.
  const numbered = new Set(keep.filter((r) => r.n > 0).map((r) => r.postal));
  keep = keep.filter((r) => r.n > 0 || !numbered.has(r.postal));
  const perState = {};
  for (const r of keep) perState[r.postal] = (perState[r.postal] ?? 0) + 1;
  const byId = new Map();
  for (const r of keep) {
    const id = districtId(r.postal, r.n, perState[r.postal] === 1);
    byId.set(id, [...(byId.get(id) ?? []), r.g]);
  }
  // Some districts come as several records (e.g. islands, split parts): merge to one shape.
  const geometries = [...byId].map(([id, gs]) =>
    gs.length === 1 ? { ...gs[0], properties: { id } } : { ...mergeArcs(topo, gs), properties: { id } });
  topo.objects = { districts: { type: "GeometryCollection", geometries } };
  return topo;
}

/** Per district: area + centroid, for spotting redistricting between Congresses. */
function fingerprint(topo) {
  const fc = feature(topo, topo.objects.districts);
  const byId = {};
  for (const f of fc.features) {
    const id = f.properties.id;
    const cur = byId[id] ?? { area: 0, parts: [] };
    cur.area += geoArea(f);
    cur.parts.push(f);
    byId[id] = cur;
  }
  for (const v of Object.values(byId)) {
    v.centroid = geoCentroid({ type: "FeatureCollection", features: v.parts });
    delete v.parts;
  }
  return byId;
}

function changedStates(prev, cur, areaTol = 0.03, kmTol = 5) {
  const states = new Set();
  const ids = new Set([...Object.keys(prev), ...Object.keys(cur)]);
  for (const id of ids) {
    const a = prev[id];
    const b = cur[id];
    const st = id.slice(0, 2);
    if (!a || !b) { states.add(st); continue; }
    const relArea = Math.abs(a.area - b.area) / Math.max(a.area, b.area);
    const km = geoDistance(a.centroid, b.centroid) * 6371;
    if (relArea > areaTol || km > kmTol) states.add(st);
  }
  return [...states].sort();
}

mkdirSync(OUT, { recursive: true });
const meta = { congressFile: {}, redistricted: {}, sources: {
  lewis: "Lewis, DeVine, Pritchett & Martis, Digital Boundary Definitions of U.S. Congressional Districts, 1789-2012 (cdmaps.polisci.ucla.edu)",
  census: "U.S. Census Bureau, cartographic boundary files (500k)",
}, congressSource: {} };
let prevPrint = null;
let prevKind = null;
const built = new Map(); // zip -> { file, print }
for (const c of Object.keys(SOURCES).map(Number).sort((a, b) => a - b)) {
  const src = SOURCES[c];
  let entry = built.get(src.zip);
  if (!entry) {
    const { topo, print } = await build(c, src);
    const text = JSON.stringify(topo);
    const file = `${createHash("sha1").update(text).digest("hex").slice(0, 10)}.json`;
    writeFileSync(join(OUT, file), text);
    entry = { file, print };
    built.set(src.zip, entry);
    console.log(`congress ${c}: ${file} ${(text.length / 1024).toFixed(0)} KB, ${topo.objects.districts.geometries.length} districts`);
  }
  meta.congressFile[c] = entry.file;
  meta.congressSource[c] = src.kind;
  if (prevPrint) {
    // Lewis and Census draw coastlines differently, so compare loosely across the switch.
    meta.redistricted[c] = prevKind !== src.kind
      ? changedStates(prevPrint, entry.print, 0.12, 20)
      : changedStates(prevPrint, entry.print);
  }
  prevPrint = entry.print;
  prevKind = src.kind;
}
writeFileSync(join(OUT, "meta.json"), JSON.stringify(meta));
console.log("redistricted:", Object.entries(meta.redistricted).map(([c, s]) => `${c}:${s.length}`).join(" "));
