import { CUTOFFS, FLIP, TIE, deltaColor, marginColor, type Hue } from "../colors";
import type { View } from "../types";

const STEPS = [0.01, 0.03, 0.05, 0.075, 0.1, 0.15, 0.2];

function Ramp({ color, label }: { color: (m: number) => string; label: string }) {
  return (
    <div className="ramp">
      <span className="ramp-label">{label}</span>
      <span className="ramp-bar">
        {STEPS.map((m) => (
          <i key={m} style={{ background: color(m) }} />
        ))}
      </span>
    </div>
  );
}

const ticks = (
  <div className="ramp ticks" aria-hidden>
    <span className="ramp-label" />
    <span className="ramp-ticks">
      <span>0</span>
      {CUTOFFS.map((c) => (
        <span key={c}>{c * 100}%</span>
      ))}
    </span>
  </div>
);

export function Legend({ view, hues }: { view: View; hues: Record<string, Hue> }) {
  let body: React.ReactNode;
  if (view === "result") {
    const parties = Object.entries(hues).filter(([p]) => p !== "Other");
    body = (
      <>
        {parties.map(([p, h]) => (
          <Ramp key={p} label={p} color={(m) => marginColor(m, h)} />
        ))}
        <Ramp label="Unnamed (source lumps non-D/R)" color={(m) => marginColor(m, "Gray")} />
        {ticks}
      </>
    );
  } else if (view === "bias") {
    body = (
      <>
        <Ramp label="Bluer than nation" color={(m) => marginColor(m, "Blue")} />
        <Ramp label="Redder than nation" color={(m) => marginColor(m, "Red")} />
        {ticks}
      </>
    );
  } else if (view === "flip") {
    body = (
      <ul className="swatches">
        <li><i style={{ background: FLIP.flipD }} />Flipped to D</li>
        <li><i style={{ background: FLIP.holdD }} />Held D</li>
        <li><i style={{ background: FLIP.flipR }} />Flipped to R</li>
        <li><i style={{ background: FLIP.holdR }} />Held R</li>
        <li><i style={{ background: TIE }} />No prior race / unknown</li>
      </ul>
    );
  } else {
    const blue = view === "shift";
    body = (
      <>
        <Ramp label={blue ? "Toward D" : "Bluer vs nation"} color={(m) => deltaColor(blue ? m : -m, blue)} />
        <Ramp label={blue ? "Toward R" : "Redder vs nation"} color={(m) => deltaColor(blue ? -m : m, blue)} />
        {ticks}
      </>
    );
  }
  return (
    <div className="legend">
      {body}
      <div className="no-data-key">
        <i /> No race / no data
      </div>
    </div>
  );
}
