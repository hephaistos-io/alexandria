import { useState } from "react";
import { useLabelling } from "../hooks/useLabelling";
import { useClassificationLabels } from "../hooks/useClassificationLabels";
import { PageHeader } from "../components/labelling/PageHeader";
import { StatsGrid } from "../components/labelling/StatsGrid";
import { ArticleFilters } from "../components/labelling/ArticleFilters";
import { ArticleTable } from "../components/labelling/ArticleTable";
import { LabelSchemaTab } from "../components/labelling/LabelSchemaTab";
import { Pagination } from "../components/shared/Pagination";
import { TabBar } from "../components/shared/TabBar";

type ActiveTab = "LABEL_ASSIGNMENT" | "LABEL_SCHEMA";

const TABS: { value: ActiveTab; label: string }[] = [
  { value: "LABEL_ASSIGNMENT", label: "LABEL_ASSIGNMENT" },
  { value: "LABEL_SCHEMA", label: "LABEL_SCHEMA" },
];

export function LabellingPage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("LABEL_ASSIGNMENT");

  const {
    stats,
    articles,
    loading,
    error,
    page,
    setPage,
    filter,
    setFilter,
    sortBy,
    setSortBy,
    updateLabels,
    triggerExport,
  } = useLabelling();

  const {
    labels,
    loading: labelsLoading,
    createLabel,
    updateLabel,
    deleteLabel,
  } = useClassificationLabels();

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <PageHeader />

      <TabBar tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />

      {error !== null && (
        <div className="mx-6 mt-4 px-4 py-2 bg-error/10 border border-error/30 font-mono text-[10px] text-error uppercase tracking-widest">
          LABELLING_API_ERROR: {error}
        </div>
      )}

      {activeTab === "LABEL_ASSIGNMENT" && (
        <div className="flex-1 p-6 overflow-y-auto space-y-6">
          <StatsGrid stats={stats} onExport={triggerExport} />
          <ArticleFilters
            filter={filter}
            setFilter={setFilter}
            sortBy={sortBy}
            setSortBy={setSortBy}
          />
          <ArticleTable
            articles={articles}
            loading={loading}
            availableLabels={labels}
            onUpdateLabels={updateLabels}
          />
          <Pagination
            page={page}
            totalPages={Math.max(1, Math.ceil((articles?.total ?? 0) / 10))}
            onPageChange={setPage}
            totalEntries={articles?.total}
            pageSize={10}
          />
        </div>
      )}

      {activeTab === "LABEL_SCHEMA" && (
        <LabelSchemaTab
          labels={labels}
          loading={labelsLoading}
          onCreateLabel={createLabel}
          onUpdateLabel={updateLabel}
          onDeleteLabel={deleteLabel}
        />
      )}
    </div>
  );
}
