import { memo, useMemo, useRef } from "react";
import { HEIGHT, WIDTH, type Shapes } from "../geo";

export interface Hover {
  id: string;
  x: number; // px within the map container
  y: number;
}

interface Props {
  shapes: Shapes;
  fills: Record<string, string>;
  selected: string | null;
  onHover: (h: Hover | null) => void;
  onSelect: (id: string) => void;
}

const Regions = memo(function Regions({ shapes, fills }: { shapes: Shapes; fills: Record<string, string> }) {
  return (
    <g className="regions">
      {shapes.regions.map((r) => (
        <path key={r.id} data-id={r.id} d={r.d} fill={fills[r.id] ?? "var(--no-data)"} />
      ))}
    </g>
  );
});

export function MapView({ shapes, fills, selected, onHover, onSelect }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const selectedD = useMemo(
    () => (selected ? shapes.regions.find((r) => r.id === selected)?.d ?? "" : ""),
    [selected, shapes],
  );
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
        <path className="borders" d={shapes.borders} />
        <path className="outline" d={shapes.outline} />
        {selectedD && <path className="selected" d={selectedD} />}
      </svg>
    </div>
  );
}
