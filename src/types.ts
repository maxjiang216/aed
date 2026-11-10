/** [name, party, votes, flag]. flag 0 = named candidate; 1 = unnamed bloc that may be one real
 *  contender (source names only D and R); 2 = minor candidates / write-ins folded together. */
export type Row = [string, string, number, 0 | 1 | 2];

export interface Race {
  c: Row[];
  t: number; // all votes cast for the office
  s?: 1; // special election
  r?: 1; // runoff
  k?: string; // Senate class
  n?: string[]; // data notes
  src?: string;
}

export type Office = "president" | "senate" | "governor";
export type Level = "state" | "county";
export type View = "result" | "bias" | "flip" | "shift" | "trend";
export type SenateSeat = "regular" | "special";

/** year -> postal code -> every race that year (regular, special, runoff) */
export type StatewideFile = Record<string, Record<string, Race[]>>;
/** 5-digit FIPS -> race */
export type CountyFile = Record<string, Race>;

export interface DataIndex {
  offices: Record<Office, Partial<Record<Level, number[]>>>;
  sources: Record<string, string>;
}

export interface Selection {
  office: Office;
  level: Level;
  year: number;
  view: View;
  seat: SenateSeat;
}
