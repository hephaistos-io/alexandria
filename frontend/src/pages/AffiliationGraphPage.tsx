import { useState } from "react";
import { useRelationTypes } from "../hooks/useRelationTypes";
import { RelationGraphTab } from "../components/graph/RelationGraphTab";
import { RelationTypesTab } from "../components/graph/RelationTypesTab";
import { TabBar } from "../components/shared/TabBar";

type GraphTab = "RELATION_GRAPH" | "RELATION_TYPES";

const TABS: { value: GraphTab; label: string }[] = [
  { value: "RELATION_GRAPH", label: "RELATION_GRAPH" },
  { value: "RELATION_TYPES", label: "RELATION_TYPES" },
];

export function AffiliationGraphPage() {
  const [activeTab, setActiveTab] = useState<GraphTab>("RELATION_GRAPH");

  const {
    relationTypes,
    loading: relationTypesLoading,
    error: relationTypesError,
    createRelationType,
    updateRelationType,
    deleteRelationType,
  } = useRelationTypes();

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Page header */}
      <div className="px-6 pt-6 pb-4 flex items-end justify-between border-b border-outline-variant/10">
        <div>
          <p className="font-mono text-[10px] text-outline uppercase tracking-widest mb-1">
            SYSTEM_CORE_LOG_14 // GRAPH_ENGINE_V1
          </p>
          <h1 className="font-headline text-4xl font-black uppercase tracking-tighter text-on-surface">
            Affiliation Graph
          </h1>
        </div>
        <div className="flex items-center gap-2 text-[10px] font-mono text-outline">
          <span className="w-1.5 h-1.5 bg-tertiary" />
          GRAPH_ENGINE
        </div>
      </div>

      <TabBar tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />

      {relationTypesError !== null && (
        <div className="mx-6 mt-4 px-4 py-2 bg-error/10 border border-error/30 font-mono text-[10px] text-error uppercase tracking-widest shrink-0">
          RELATION_TYPES_API_ERROR: {relationTypesError}
        </div>
      )}

      {activeTab === "RELATION_GRAPH" && (
        <div className="flex-1 flex flex-col overflow-hidden">
          <RelationGraphTab relationTypes={relationTypes} />
        </div>
      )}

      {activeTab === "RELATION_TYPES" && (
        <RelationTypesTab
          relationTypes={relationTypes}
          loading={relationTypesLoading}
          onCreateRelationType={createRelationType}
          onUpdateRelationType={updateRelationType}
          onDeleteRelationType={deleteRelationType}
        />
      )}
    </div>
  );
}
