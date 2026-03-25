import { useState, useRef, useEffect } from "react";
import { MaterialIcon } from "../shared/MaterialIcon";
import type { RelationType } from "../../types/graph";
import { entityTypeColor, halfLifeDays } from "./graphHelpers";
import type { FGNode } from "./graphHelpers";

export interface GraphControlsProps {
  lambdaDecay: number;
  setLambdaDecay: (v: number) => void;
  minStrength: number;
  setMinStrength: (v: number) => void;
  corroboration: number;
  setCorroboration: (v: number) => void;
  relationTypes: RelationType[];
  activeRelTypes: string[];
  setActiveRelTypes: (v: string[]) => void;
  nodeCount: number;
  edgeCount: number;
  nodes: FGNode[];
  onNavigateToNode: (node: FGNode) => void;
}

export function GraphControls({
  lambdaDecay,
  setLambdaDecay,
  minStrength,
  setMinStrength,
  corroboration,
  setCorroboration,
  relationTypes,
  activeRelTypes,
  setActiveRelTypes,
  nodeCount,
  edgeCount,
  nodes,
  onNavigateToNode,
}: GraphControlsProps) {
  const [query, setQuery] = useState("");
  const [showResults, setShowResults] = useState(false);
  const searchRef = useRef<HTMLDivElement>(null);

  // Filter nodes by name (case-insensitive substring match).
  // Limit to 8 results to keep the dropdown compact.
  const matches =
    query.length >= 2
      ? nodes.filter((n) => n.name.toLowerCase().includes(query.toLowerCase())).slice(0, 8)
      : [];

  // Close the dropdown when clicking outside the search area.
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(e.target as Node)) {
        setShowResults(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="px-6 py-3 bg-surface-container-low border-b border-outline-variant/10 flex flex-wrap items-center gap-6">
      {/* Node search */}
      <div ref={searchRef} className="relative">
        <div className="flex items-center gap-2">
          <MaterialIcon name="search" className="text-sm text-outline" />
          <input
            type="text"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setShowResults(true);
            }}
            onFocus={() => setShowResults(true)}
            placeholder="FIND_ENTITY..."
            className="bg-surface-container-highest/50 border border-outline-variant/20 px-2 py-1 font-mono text-[10px] text-on-surface placeholder:text-outline/50 uppercase w-40 focus:outline-none focus:border-primary/50"
          />
        </div>
        {showResults && matches.length > 0 && (
          <div className="absolute top-full left-0 mt-1 w-64 bg-surface-container-high border border-outline-variant/20 shadow-xl z-40 max-h-60 overflow-y-auto">
            {matches.map((node) => (
              <button
                key={node.id}
                onClick={() => {
                  onNavigateToNode(node);
                  setQuery("");
                  setShowResults(false);
                }}
                className="w-full text-left px-3 py-2 flex items-center gap-3 hover:bg-surface-container-highest transition-colors"
              >
                <span
                  className="w-2 h-2 rounded-full shrink-0"
                  style={{ backgroundColor: entityTypeColor(node.entity_type) }}
                />
                <span className="font-mono text-[10px] text-on-surface uppercase truncate">
                  {node.name}
                </span>
                <span className="font-mono text-[8px] text-outline ml-auto shrink-0">
                  {node.entity_type}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Lambda decay slider */}
      <div className="flex items-center gap-3">
        <span className="font-mono text-[10px] text-outline uppercase whitespace-nowrap">
          λ_DECAY:
        </span>
        <input
          type="range"
          min={0.001}
          max={0.1}
          step={0.001}
          value={lambdaDecay}
          onChange={(e) => setLambdaDecay(Number(e.target.value))}
          className="w-28 accent-primary cursor-pointer"
        />
        <span className="font-mono text-[10px] text-primary w-14">{lambdaDecay.toFixed(3)}</span>
        <span className="font-mono text-[9px] text-outline">t½={halfLifeDays(lambdaDecay)}</span>
      </div>

      {/* Min strength slider */}
      <div className="flex items-center gap-3">
        <span className="font-mono text-[10px] text-outline uppercase whitespace-nowrap">
          MIN_STR:
        </span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.05}
          value={minStrength}
          onChange={(e) => setMinStrength(Number(e.target.value))}
          className="w-28 accent-primary cursor-pointer"
        />
        <span className="font-mono text-[10px] text-primary w-8">{minStrength.toFixed(2)}</span>
      </div>

      {/* Corroboration slider — how much multi-article mentions boost edge strength */}
      <div className="flex items-center gap-3">
        <span className="font-mono text-[10px] text-outline uppercase whitespace-nowrap">
          CORROB_α:
        </span>
        <input
          type="range"
          min={0}
          max={1}
          step={0.1}
          value={corroboration}
          onChange={(e) => setCorroboration(Number(e.target.value))}
          className="w-28 accent-primary cursor-pointer"
        />
        <span className="font-mono text-[10px] text-primary w-8">{corroboration.toFixed(1)}</span>
      </div>

      {/* Relation type filter chips — empty selection means "show all" */}
      <div className="flex items-center gap-1.5 flex-wrap">
        {relationTypes
          .filter((rt) => rt.enabled)
          .map((rt) => {
            const isActive = activeRelTypes.length === 0 || activeRelTypes.includes(rt.name);
            const color = `#${rt.color.replace(/^#/, "")}`;
            return (
              <button
                key={rt.id}
                onClick={() => {
                  if (activeRelTypes.length === 0) {
                    // First click: select only this type
                    setActiveRelTypes([rt.name]);
                  } else if (activeRelTypes.includes(rt.name)) {
                    const next = activeRelTypes.filter((n) => n !== rt.name);
                    // If nothing left, go back to "show all"
                    setActiveRelTypes(next);
                  } else {
                    setActiveRelTypes([...activeRelTypes, rt.name]);
                  }
                }}
                className="px-2 py-0.5 font-mono text-[8px] uppercase tracking-wider border transition-all"
                style={{
                  color: isActive ? color : `${color}55`,
                  borderColor: isActive ? `${color}66` : `${color}22`,
                  backgroundColor: isActive ? `${color}1a` : "transparent",
                }}
              >
                {rt.name}
              </button>
            );
          })}
      </div>

      {/* Graph stats */}
      <div className="ml-auto flex items-center gap-4">
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 bg-primary" />
          <span className="font-mono text-[10px] text-outline">{nodeCount} NODES</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 bg-tertiary" />
          <span className="font-mono text-[10px] text-outline">{edgeCount} EDGES</span>
        </div>
      </div>
    </div>
  );
}
