import { MaterialIcon } from "../shared/MaterialIcon";
import { entityTypeColor, resolveNodeId } from "./graphHelpers";
import type { FGNode, FGLink } from "./graphHelpers";

interface NodeDetailSidebarProps {
  node: FGNode;
  links: FGLink[];
  onClose: () => void;
}

export function NodeDetailSidebar({ node, links, onClose }: NodeDetailSidebarProps) {
  // Find all edges that connect to this node (as source or target)
  const connected = links.filter(
    (l) => resolveNodeId(l.source) === node.id || resolveNodeId(l.target) === node.id,
  );

  return (
    <div className="w-80 bg-surface-container-low flex flex-col z-20 border-l border-outline-variant/10 shadow-[-10px_0_20px_rgba(0,0,0,0.4)]">
      {/* Header */}
      <div className="p-5 bg-surface-container-high border-b border-outline-variant/20">
        <div className="flex justify-between items-start mb-2">
          <span className="font-headline font-bold text-[10px] tracking-widest text-primary uppercase">
            ENTITY_DETAILS
          </span>
          <button onClick={onClose} className="text-outline hover:text-on-surface transition-colors">
            <MaterialIcon name="close" className="text-base" />
          </button>
        </div>
        <h2 className="font-headline font-black text-xl text-on-surface leading-tight uppercase">
          {node.name}
        </h2>
        <div className="flex items-center gap-3 mt-1">
          <span className="font-mono text-[10px] text-tertiary">{node.id}</span>
          <span
            className="font-mono text-[9px] px-2 py-0.5 border"
            style={{
              color: entityTypeColor(node.entity_type),
              borderColor: `${entityTypeColor(node.entity_type)}33`,
              backgroundColor: `${entityTypeColor(node.entity_type)}1a`,
            }}
          >
            {node.entity_type}
          </span>
        </div>
      </div>

      {/* Relations list */}
      <div className="flex-1 overflow-y-auto p-5">
        <h3 className="text-[10px] font-headline font-bold text-outline-variant uppercase tracking-tighter mb-3 flex items-center gap-2">
          <span className="w-1 h-1 bg-outline-variant" />
          Relations ({connected.length})
        </h3>

        {connected.length === 0 ? (
          <p className="font-mono text-[10px] text-outline uppercase">NO_CONNECTIONS</p>
        ) : (
          <div className="space-y-1">
            {connected.map((link, i) => {
              const sourceId = resolveNodeId(link.source);
              const targetId = resolveNodeId(link.target);
              const isOutgoing = sourceId === node.id;
              const otherId = isOutgoing ? targetId : sourceId;

              return (
                <div
                  key={i}
                  className="flex items-center justify-between p-2 bg-surface-container-highest/50 hover:bg-surface-container-highest transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <MaterialIcon
                      name={isOutgoing ? "east" : "west"}
                      className="text-sm text-primary"
                    />
                    <span className="text-[10px] font-mono uppercase text-on-surface truncate max-w-[100px]">
                      {otherId}
                    </span>
                  </div>
                  <span className="text-[9px] font-mono text-outline truncate max-w-[90px]">
                    {link.relation_type}
                  </span>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
