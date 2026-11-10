import { geoPath } from "d3-geo";
import { memo, useMemo, useRef } from "react";
import { HEIGHT, WIDTH, type Shapes } from "../geo";

export interface Hover {
  id: string;
  x: number; // px within the map container
  y: number;
}

const path = geoPath();

interface Props {
  shapes: Shapes;
  fills: Record<string, string>;
  selected: string | null;
  onHover: (h: Hover | null) => void;
  onSelect: (id: string) => void;
}

/** Path strings only depend on the shapes, so compute them once per level. */
const Regions = memo(function Regions({ shapes, fills }: { shapes: Shapes; fills: Record<string, string> }) {
  const ds = useMemo(() => shapes.regions.map((s) => [s.id, path(s) ?? ""] as const), [shapes]);
  return (
    <g className="regions">
      {ds.map(([id, d]) => (
        <path key={id} data-id={id} d={d} fill={fills[id] ?? "var(--no-data)"} />
      ))}
    </g>
  );
});

export function MapView({ shapes, fills, selected, onHover, onSelect }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const borders = useMemo(() => path(shapes.borders) ?? "", [shapes]);
  const outline = useMemo(() => path(shapes.outline) ?? "", [shapes]);
  const selectedD = useMemo(() => {
    const s = selected && shapes.regions.find((r) => r.id === selected);
    return s ? path(s) ?? "" : "";
  }, [selected, shapes]);

  const idAt = (e: React.MouseEvent) => (e.target as Element).getAttribute?.("data-id");

  return (
    <div
      ref={ref}
      className="map"
      onMouseMove={(e) => {
        const id = idAt(e);
        const box = ref.current?.getBoundingClientRect();
        if (!id || !box) return onHover(null);
        onHover({ id, x: e.clientX - box.left, y: e.clientY - box.top });
      }}
      onMouseLeave={() => onHover(null)}
      onClick={(e) => {
        const id = idAt(e);
        if (id) onSelect(id);
      }}
    >
      <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Map of results">
        <Regions shapes={shapes} fills={fills} />
        <path className="borders" d={borders} />
        <path className="outline" d={outline} />
        {selectedD && <path className="selected" d={selectedD} />}
      </svg>
    </div>
  );
}
