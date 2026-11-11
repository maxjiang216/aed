import type { DataIndex, Level, Office, Selection, View } from "../types";

const OFFICE_LABEL: Record<Office, string> = {
  president: "President", senate: "Senate", governor: "Governor", house: "House",
};
const VIEW_LABEL: Record<View, [string, string]> = {
  result: ["Result", "Winner, shaded by margin over the runner-up"],
  bias: ["Lean", "Republican-minus-Democratic margin compared with the national result that year"],
  flip: ["Flip / hold", "Did the seat change party since the previous election for it?"],
  shift: ["Shift", "Change in the Democratic-minus-Republican margin since the previous election"],
  trend: ["Trend", "Change in lean relative to the nation since the previous election"],
};

interface Props {
  index: DataIndex;
  sel: Selection;
  years: number[];
  hasSpecial: boolean;
  onChange: (patch: Partial<Selection>) => void;
}

export function Segmented<T extends string>({
  label, value, options, onChange,
}: { label: string; value: T; options: [T, string, string?][]; onChange: (v: T) => void }) {
  return (
    <div className="segmented" role="radiogroup" aria-label={label}>
      {options.map(([v, text, title]) => (
        <button
          key={v}
          role="radio"
          aria-checked={v === value}
          className={v === value ? "on" : ""}
          title={title}
          onClick={() => onChange(v)}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

export function Controls({ index, sel, years, hasSpecial, onChange }: Props) {
  const levels = Object.keys(index.offices[sel.office]) as Level[];
  const i = years.indexOf(sel.year);
  return (
    <nav className="controls">
      <Segmented
        label="Office"
        value={sel.office}
        options={(Object.keys(OFFICE_LABEL) as Office[]).filter((o) => o in index.offices).map((o) => [o, OFFICE_LABEL[o]])}
        onChange={(office) => onChange({ office })}
      />
      {levels.length > 1 && (
        <Segmented
          label="Level"
          value={sel.level}
          options={levels.map((l) => [l, l === "state" ? "States" : l === "county" ? "Counties" : "Districts"])}
          onChange={(level) => onChange({ level })}
        />
      )}
      <div className="year" aria-label="Year">
        <button disabled={i <= 0} onClick={() => onChange({ year: years[i - 1] })} aria-label="Previous election">
          ◀
        </button>
        <select value={sel.year} onChange={(e) => onChange({ year: Number(e.target.value) })} aria-label="Year">
          {[...years].reverse().map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
        <button
          disabled={i < 0 || i >= years.length - 1}
          onClick={() => onChange({ year: years[i + 1] })}
          aria-label="Next election"
        >
          ▶
        </button>
      </div>
      {sel.office === "senate" && hasSpecial && (
        <Segmented
          label="Seat"
          value={sel.seat}
          options={[["regular", "Regular"], ["special", "Special"]]}
          onChange={(seat) => onChange({ seat })}
        />
      )}
      <Segmented
        label="View"
        value={sel.view}
        options={(Object.keys(VIEW_LABEL) as View[]).map((v) => [v, VIEW_LABEL[v][0], VIEW_LABEL[v][1]])}
        onChange={(view) => onChange({ view })}
      />
    </nav>
  );
}
