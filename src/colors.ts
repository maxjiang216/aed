/** Margin color scales. Four stops per hue (tilt, lean, likely, solid) with linear
 *  interpolation between them; carried over from the original AED "rule 2" scale. */

export type RGB = [number, number, number];
export type Hue = "Blue" | "Red" | "Yellow" | "Green" | "Purple" | "Orange" | "Teal" | "Gray";

export const CUTOFFS = [0.05, 0.1, 0.2]; // margin where lean, likely, solid colors are reached

export const PALETTES: Record<Hue, RGB[]> = {
  Blue: [[148, 155, 179], [138, 175, 255], [87, 124, 204], [28, 64, 140]],
  Red: [[207, 137, 128], [255, 139, 152], [255, 88, 101], [191, 29, 41]],
  Yellow: [[184, 162, 82], [255, 231, 138], [232, 200, 77], [230, 183, 0]],
  Green: [[122, 153, 126], [138, 255, 151], [80, 200, 94], [28, 140, 40]],
  Purple: [[178, 146, 154], [187, 157, 204], [171, 106, 153], [110, 46, 91]],
  Orange: [[190, 150, 120], [255, 190, 130], [240, 140, 60], [190, 90, 20]],
  Teal: [[130, 160, 165], [140, 215, 225], [60, 170, 190], [0, 120, 140]],
  Gray: [[150, 150, 150], [175, 175, 175], [130, 130, 130], [85, 85, 85]],
};

export const TIE = "rgb(107, 110, 115)";

export const FLIP = {
  flipD: "rgb(28, 64, 140)",
  holdD: "rgb(138, 175, 255)",
  flipR: "rgb(191, 29, 41)",
  holdR: "rgb(255, 139, 152)",
};

const rgb = (c: RGB) => `rgb(${Math.round(c[0])}, ${Math.round(c[1])}, ${Math.round(c[2])})`;
const mix = (a: RGB, b: RGB, t: number): RGB => [
  a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t,
];

/** margin in [0, 1] -> color. 0 = tie (gray); between stops, linear interpolation. */
export function marginColor(margin: number, hue: Hue, cutoffs: number[] = CUTOFFS): string {
  if (!(margin > 0)) return TIE;
  const pal = PALETTES[hue];
  if (margin >= cutoffs[cutoffs.length - 1]) return rgb(pal[pal.length - 1]);
  if (margin < cutoffs[0]) return rgb(mix(pal[0], pal[1], margin / cutoffs[0]));
  for (let i = 0; i < cutoffs.length - 1; i++) {
    if (margin < cutoffs[i + 1]) {
      return rgb(mix(pal[i + 1], pal[i + 2], (margin - cutoffs[i]) / (cutoffs[i + 1] - cutoffs[i])));
    }
  }
  return rgb(pal[pal.length - 1]);
}

/** Signed change -> Blue/Red scale; |delta| capped at 0.4. */
export function deltaColor(delta: number | null, positiveIsBlue: boolean): string {
  if (delta === null || !Number.isFinite(delta) || Math.abs(delta) < 1e-12) return TIE;
  const blue = positiveIsBlue ? delta > 0 : delta < 0;
  return marginColor(Math.min(Math.abs(delta), 0.4), blue ? "Blue" : "Red");
}

export const FIXED_PARTY_HUES: Record<string, Hue> = {
  Democratic: "Blue",
  Republican: "Red",
  Other: "Gray",
};
export const THIRD_PARTY_HUES: Hue[] = ["Yellow", "Green", "Purple", "Orange"];

export function swatch(hue: Hue, level = 3): string {
  return rgb(PALETTES[hue][level]);
}
