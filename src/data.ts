import type { CountyFile, DataIndex, HouseFile, Office, StatewideFile } from "./types";
import type { SeatsFile } from "./seats";

const cache = new Map<string, Promise<unknown>>();

function getJson<T>(path: string): Promise<T> {
  const url = `${import.meta.env.BASE_URL}data/${path}`;
  if (!cache.has(url)) {
    cache.set(
      url,
      fetch(url).then((r) => {
        if (!r.ok) throw new Error(`${r.status} loading ${url}`);
        return r.json();
      }),
    );
  }
  return cache.get(url) as Promise<T>;
}

export const loadIndex = () => getJson<DataIndex>("index.json");
export const loadStatewide = (office: Office) => getJson<StatewideFile>(`statewide/${office}.json`);
export const loadCounties = (office: Office, year: number) =>
  getJson<CountyFile>(`county/${office}/${year}.json`);
export const loadHouse = (year: number) => getJson<HouseFile>(`house/${year}.json`);
export const loadCanada = (year: number) => getJson<HouseFile>(`canada/${year}.json`);
export const loadSeats = () => getJson<SeatsFile>("congress/seats.json");
