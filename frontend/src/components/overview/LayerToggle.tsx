export interface LayerVisibility {
  articles: boolean;
  conflicts: boolean;
  heatmap: boolean;
}

interface LayerToggleProps {
  layers: LayerVisibility;
  onChange: (layers: LayerVisibility) => void;
}

interface ToggleButtonProps {
  label: string;
  active: boolean;
  color: string;
  onClick: () => void;
}

function ToggleButton({ label, active, color, onClick }: ToggleButtonProps) {
  return (
    <button
      onClick={onClick}
      className="flex items-center gap-1.5 cursor-pointer"
    >
      {/* Small colored indicator dot — filled when active, hollow when off */}
      <span
        className="block w-2 h-2 border transition-colors duration-150"
        style={{
          borderColor: color,
          backgroundColor: active ? color : "transparent",
        }}
      />
      <span
        className="uppercase tracking-wider transition-colors duration-150"
        style={{ color: active ? color : "var(--color-outline)" }}
      >
        {label}
      </span>
    </button>
  );
}

/**
 * Map layer toggle panel — positioned in the top-left of the map.
 *
 * Follows the existing tactical UI style: monospace 10px text, muted colours,
 * no backgrounds or borders. The toggle buttons use small square indicator
 * dots (matching each layer's colour) that fill when active.
 */
export function LayerToggle({ layers, onChange }: LayerToggleProps) {
  function toggle(key: keyof LayerVisibility) {
    onChange({ ...layers, [key]: !layers[key] });
  }

  return (
    <div className="absolute top-14 left-8 font-mono text-[10px] z-[400] flex flex-col gap-1.5">
      <p className="uppercase tracking-widest text-outline/60 mb-0.5">LAYERS</p>
      <ToggleButton
        label="ARTICLES"
        active={layers.articles}
        color="var(--color-primary)"
        onClick={() => toggle("articles")}
      />
      <ToggleButton
        label="CONFLICTS"
        active={layers.conflicts}
        color="#ff6b6b"
        onClick={() => toggle("conflicts")}
      />
      <ToggleButton
        label="HEATMAP"
        active={layers.heatmap}
        color="#ff9040"
        onClick={() => toggle("heatmap")}
      />
    </div>
  );
}
