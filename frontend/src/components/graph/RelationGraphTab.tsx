import { useState, useRef, useEffect, useCallback, useMemo } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { MaterialIcon } from "../shared/MaterialIcon";
import { EntityPopup } from "./EntityPopup";
import { GraphControls } from "./GraphControls";
import { NodeDetailSidebar } from "./NodeDetailSidebar";
import {
  entityTypeColor,
  buildRelationColorMap,
  resolveNodeId,
} from "./graphHelpers";
import type { FGNode, FGLink } from "./graphHelpers";
import { useRelationGraph } from "../../hooks/useRelationGraph";
import type { RelationType } from "../../types/graph";

interface RelationGraphTabProps {
  relationTypes: RelationType[];
}

export function RelationGraphTab({ relationTypes }: RelationGraphTabProps) {
  const [lambdaDecay, setLambdaDecay] = useState(0.01);
  const [minStrength, setMinStrength] = useState(0.1);
  const [corroboration, setCorroboration] = useState(0.5);
  // Active relation type filters — empty array means "show all".
  const [activeRelTypes, setActiveRelTypes] = useState<string[]>([]);
  const [selectedNode, setSelectedNode] = useState<FGNode | null>(null);
  const [hoveredNode, setHoveredNode] = useState<FGNode | null>(null);
  // Screen-space position of the selected node, used to anchor the EntityPopup.
  const [popupPos, setPopupPos] = useState<{ x: number; y: number } | null>(null);
  // Separate flag so the popup can be dismissed without closing the sidebar.
  const [popupOpen, setPopupOpen] = useState(false);

  const { data, loading, error } = useRelationGraph(
    lambdaDecay,
    minStrength,
    corroboration,
    activeRelTypes,
  );

  // We need the explicit pixel dimensions for ForceGraph2D —
  // it renders to a <canvas> and doesn't infer size from CSS.
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });

  useEffect(() => {
    const el = containerRef.current;
    if (el === null) return;

    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (entry) {
        setDimensions({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        });
      }
    });

    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  const colorMap = useMemo(() => buildRelationColorMap(relationTypes), [relationTypes]);

  // Transform our domain types into what ForceGraph2D expects.
  // The library mutates the objects it receives (adding x, y etc.),
  // so we create fresh objects only when the API data changes — not on
  // every render. Without useMemo, any state change (selecting a node,
  // opening a popup) would create new arrays and restart the simulation.
  const graphData = useMemo(() => {
    if (data === null) return { nodes: [] as FGNode[], links: [] as FGLink[] };

    const links: FGLink[] = data.edges.map((e) => ({
      source: e.source,
      target: e.target,
      relation_type: e.relation_type,
      display_strength: e.display_strength,
    }));

    // Assign curvature to parallel edges (multiple relations between the same
    // node pair). Without this, overlapping straight lines are indistinguishable.
    // We group edges by canonical pair key (smaller QID first) and spread them
    // symmetrically around 0 curvature with a 0.2 step between each.
    const pairGroups = new Map<string, FGLink[]>();
    for (const link of links) {
      const s = typeof link.source === "string" ? link.source : link.source.id;
      const t = typeof link.target === "string" ? link.target : link.target.id;
      const key = s < t ? `${s}|${t}` : `${t}|${s}`;
      const group = pairGroups.get(key);
      if (group) group.push(link);
      else pairGroups.set(key, [link]);
    }
    for (const group of pairGroups.values()) {
      if (group.length < 2) continue;
      const step = 0.2;
      const offset = -((group.length - 1) * step) / 2;
      for (let i = 0; i < group.length; i++) {
        group[i].curvature = offset + i * step;
      }
    }

    return {
      nodes: data.nodes.map((n): FGNode => ({
        id: n.qid,
        name: n.name,
        entity_type: n.entity_type,
      })),
      links,
    };
  }, [data]);

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const fgRef = useRef<any>(null);

  const handleNodeClick = useCallback((node: object) => {
    const fgNode = node as FGNode;
    setSelectedNode(fgNode);

    // Convert the node's graph-space coordinates to screen-space pixels
    // so we can position the popup card over the canvas.
    // graph2ScreenCoords is a method on the ForceGraph2D instance exposed via ref.
    if (fgRef.current && fgNode.x != null && fgNode.y != null) {
      const screenCoords = fgRef.current.graph2ScreenCoords(fgNode.x, fgNode.y);
      setPopupPos({ x: screenCoords.x, y: screenCoords.y });
      setPopupOpen(true);
    }
  }, []);

  const handleBackgroundClick = useCallback(() => {
    setSelectedNode(null);
    setPopupPos(null);
    setPopupOpen(false);
  }, []);

  // Build a degree lookup so we can size nodes by connection count
  // without recomputing inside every canvas draw call.
  const degreeMap = useMemo(() => {
    const m = new Map<string, number>();
    for (const link of graphData.links) {
      const sid = resolveNodeId(link.source as string | FGNode);
      const tid = resolveNodeId(link.target as string | FGNode);
      m.set(sid, (m.get(sid) ?? 0) + 1);
      m.set(tid, (m.get(tid) ?? 0) + 1);
    }
    return m;
  }, [graphData.links]);

  // When a node is hovered, compute the set of "highlighted" node IDs:
  // the hovered node itself plus all its direct neighbors. Everything
  // outside this set gets dimmed. Null means no hover — show everything.
  const highlightNodes = useMemo(() => {
    if (!hoveredNode) return null;
    const s = new Set<string>();
    s.add(hoveredNode.id);
    for (const link of graphData.links) {
      const sid = resolveNodeId(link.source as string | FGNode);
      const tid = resolveNodeId(link.target as string | FGNode);
      if (sid === hoveredNode.id) s.add(tid);
      if (tid === hoveredNode.id) s.add(sid);
    }
    return s;
  }, [hoveredNode, graphData.links]);

  // Configure d3 forces once the graph component mounts.
  // - Stronger charge repulsion pushes nodes apart (default is -30).
  // - Collision force prevents node circles from overlapping.
  // react-force-graph uses d3-force-3d under the hood, which exposes forceCollide.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.d3Force("charge")?.strength(-120);
    fg.d3Force("link")?.distance(80);
    // Import d3-force-3d (bundled by react-force-graph) for collision detection.
    // We track whether the effect was cleaned up so we don't mutate a stale ref.
    let cancelled = false;
    import("d3-force-3d")
      .then((d3) => {
        if (cancelled) return;
        fg.d3Force("collide", d3.forceCollide((node: FGNode) => {
          const degree = degreeMap.get(node.id) ?? 0;
          return Math.sqrt(Math.max(1, degree)) * 6 + 4;
        }));
      })
      .catch(() => {
        // d3-force-3d is a transitive dep of react-force-graph-2d.
        // If it fails to load, collide force simply won't be applied.
      });
    return () => { cancelled = true; };
  }, [degreeMap]);

  // Custom canvas renderer: semi-transparent filled circles with a subtle glow.
  // When a node is hovered, non-highlighted nodes are dimmed to near-invisible.
  const drawNode = useCallback(
    (node: object, ctx: CanvasRenderingContext2D, globalScale: number) => {
      const n = node as FGNode;
      if (n.x == null || n.y == null) return;
      const degree = degreeMap.get(n.id) ?? 0;
      const radius = Math.sqrt(Math.max(1, degree)) * 4 + 2;
      const color = entityTypeColor(n.entity_type);

      // Dim nodes that aren't part of the hovered neighborhood.
      const dimmed = highlightNodes !== null && !highlightNodes.has(n.id);
      const alpha = dimmed ? 0.08 : 1;

      ctx.globalAlpha = alpha;

      // Outer glow
      ctx.beginPath();
      ctx.arc(n.x, n.y, radius + 1.5, 0, 2 * Math.PI);
      ctx.fillStyle = color + "20";
      ctx.fill();

      // Main circle — semi-transparent
      ctx.beginPath();
      ctx.arc(n.x, n.y, radius, 0, 2 * Math.PI);
      ctx.fillStyle = color + "88";
      ctx.strokeStyle = color + "cc";
      ctx.lineWidth = 1;
      ctx.fill();
      ctx.stroke();

      // Label — only show when zoomed in enough
      if (globalScale > 1.2) {
        ctx.font = `${Math.min(12 / globalScale, 4)}px sans-serif`;
        ctx.textAlign = "center";
        ctx.textBaseline = "top";
        ctx.fillStyle = "#d0d4dc";
        ctx.fillText(n.name, n.x, n.y + radius + 2);
      }

      ctx.globalAlpha = 1;
    },
    [degreeMap, highlightNodes],
  );

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <GraphControls
        lambdaDecay={lambdaDecay}
        setLambdaDecay={setLambdaDecay}
        minStrength={minStrength}
        setMinStrength={setMinStrength}
        corroboration={corroboration}
        setCorroboration={setCorroboration}
        relationTypes={relationTypes}
        activeRelTypes={activeRelTypes}
        setActiveRelTypes={setActiveRelTypes}
        nodeCount={graphData.nodes.length}
        edgeCount={graphData.links.length}
        nodes={graphData.nodes as FGNode[]}
        onNavigateToNode={(node) => {
          const fg = fgRef.current;
          if (!fg || node.x == null || node.y == null) return;
          // Zoom in and center on the target node with a smooth 800ms animation.
          fg.centerAt(node.x, node.y, 800);
          fg.zoom(4, 800);
          // Select the node to open the sidebar + popup.
          setSelectedNode(node);
          const screenCoords = fg.graph2ScreenCoords(node.x, node.y);
          setPopupPos({ x: screenCoords.x, y: screenCoords.y });
          setPopupOpen(true);
        }}
      />

      {error !== null && (
        <div className="mx-6 mt-4 px-4 py-2 bg-error/10 border border-error/30 font-mono text-[10px] text-error uppercase tracking-widest shrink-0">
          GRAPH_API_ERROR: {error}
        </div>
      )}

      <div className="flex-1 flex overflow-hidden">
        {/* Canvas area */}
        <div
          ref={containerRef}
          className="flex-1 relative bg-surface-container-lowest overflow-hidden"
        >
          {/* Decorative grid overlay — matches the mockup aesthetic */}
          <div
            className="absolute inset-0 opacity-5 pointer-events-none"
            style={{
              backgroundImage:
                "linear-gradient(#8c919c 1px, transparent 1px), linear-gradient(90deg, #8c919c 1px, transparent 1px)",
              backgroundSize: "40px 40px",
            }}
          />

          {loading && (
            <div className="absolute inset-0 flex items-center justify-center z-10">
              <span className="font-mono text-[10px] text-outline uppercase tracking-widest">
                LOADING_GRAPH...
              </span>
            </div>
          )}

          {!loading && graphData.nodes.length === 0 && !error && (
            <div className="absolute inset-0 flex flex-col items-center justify-center z-10 gap-3">
              <MaterialIcon name="account_tree" className="text-4xl text-outline/30" />
              <span className="font-mono text-[10px] text-outline uppercase tracking-widest">
                NO_GRAPH_DATA — ingest articles and run relation extraction
              </span>
            </div>
          )}

          {/* Coordinate overlay — purely decorative, mirrors mockup */}
          <div className="absolute bottom-6 right-6 flex flex-col items-end pointer-events-none">
            <span className="text-primary font-mono text-[10px] tracking-widest">
              NODES: {graphData.nodes.length}
            </span>
            <span className="text-primary font-mono text-[10px] tracking-widest">
              EDGES: {graphData.links.length}
            </span>
            <span className="text-outline font-mono text-[9px] mt-1 opacity-50 uppercase">
              λ={lambdaDecay.toFixed(3)} // STR_MIN={minStrength.toFixed(2)}
            </span>
          </div>

          {/* Floating entity popup — anchored to the clicked node's screen position.
              Closing the popup leaves the sidebar open (independent state). */}
          {selectedNode !== null && popupPos !== null && popupOpen && (
            <EntityPopup
              qid={selectedNode.id}
              name={selectedNode.name}
              entityType={selectedNode.entity_type}
              screenX={popupPos.x}
              screenY={popupPos.y}
              entityTypeColor={entityTypeColor}
              onClose={() => setPopupOpen(false)}
            />
          )}

          <ForceGraph2D
            ref={fgRef}
            graphData={graphData}
            nodeId="id"
            nodeLabel="name"
            cooldownTicks={100}
            warmupTicks={50}
            nodeCanvasObject={drawNode}
            nodePointerAreaPaint={(node, color, ctx) => {
              // Invisible hit area matching the visual node size
              const n = node as FGNode;
              if (n.x == null || n.y == null) return;
              const degree = degreeMap.get(n.id) ?? 0;
              const radius = Math.sqrt(Math.max(1, degree)) * 4 + 2;
              ctx.beginPath();
              ctx.arc(n.x, n.y, radius, 0, 2 * Math.PI);
              ctx.fillStyle = color;
              ctx.fill();
            }}
            linkColor={(link) => {
              const fgLink = link as FGLink;
              const base = colorMap.get(fgLink.relation_type?.toUpperCase()) ?? "#424751";
              if (!highlightNodes) return base;
              const sid = resolveNodeId(fgLink.source as string | FGNode);
              const tid = resolveNodeId(fgLink.target as string | FGNode);
              const linked = highlightNodes.has(sid) && highlightNodes.has(tid);
              return linked ? base : base + "10";
            }}
            linkWidth={(link) => Math.max(0.3, (link as FGLink).display_strength * 0.8)}
            linkCurvature={(link) => (link as FGLink).curvature ?? 0}
            linkDirectionalParticles={2}
            linkDirectionalParticleWidth={(link) => {
              if (!highlightNodes) return Math.max(1.5, (link as FGLink).display_strength * 2.5);
              const fgLink = link as FGLink;
              const sid = resolveNodeId(fgLink.source as string | FGNode);
              const tid = resolveNodeId(fgLink.target as string | FGNode);
              const linked = highlightNodes.has(sid) && highlightNodes.has(tid);
              return linked ? Math.max(1.5, (link as FGLink).display_strength * 2.5) : 0;
            }}
            linkDirectionalParticleSpeed={0.005}
            linkDirectionalParticleColor={(link) => {
              const fgLink = link as FGLink;
              return colorMap.get(fgLink.relation_type?.toUpperCase()) ?? "#424751";
            }}
            linkLabel={(link) => (link as FGLink).relation_type ?? ""}
            backgroundColor="#0a0e16"
            onNodeHover={(node) => setHoveredNode(node ? (node as FGNode) : null)}
            onNodeClick={handleNodeClick}
            onBackgroundClick={handleBackgroundClick}
            width={dimensions.width}
            height={dimensions.height}
          />
        </div>

        {/* Entity detail sidebar — shown only when a node is selected */}
        {selectedNode !== null && (
          <NodeDetailSidebar
            node={selectedNode}
            links={graphData.links}
            onClose={() => setSelectedNode(null)}
          />
        )}
      </div>
    </div>
  );
}
