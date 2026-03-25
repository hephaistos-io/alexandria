import { Pagination } from "../shared/Pagination";
import { AttributionStatsGrid } from "./AttributionStatsGrid";
import { AttributionFilters } from "./AttributionFilters";
import { AttributionArticleTable } from "./AttributionArticleTable";
import type {
  AttributionStats,
  AttributionFilter,
  AttributionSort,
  AttributionArticle,
  EntityRoleType,
} from "../../types/attribution";

interface AttributionTabProps {
  stats: AttributionStats | null;
  articles: { articles: AttributionArticle[]; total: number } | null;
  loading: boolean;
  page: number;
  setPage: (page: number) => void;
  filter: AttributionFilter;
  setFilter: (f: AttributionFilter) => void;
  sortBy: AttributionSort;
  setSortBy: (s: AttributionSort) => void;
  enabledRoleTypes: EntityRoleType[];
  onUpdateRoles: (articleId: number, roles: Record<string, string>) => Promise<boolean>;
}

const PAGE_SIZE = 10;

export function AttributionTab({
  stats,
  articles,
  loading,
  page,
  setPage,
  filter,
  setFilter,
  sortBy,
  setSortBy,
  enabledRoleTypes,
  onUpdateRoles,
}: AttributionTabProps) {
  const totalPages = Math.max(1, Math.ceil((articles?.total ?? 0) / PAGE_SIZE));

  return (
    <div className="flex-1 p-6 overflow-y-auto space-y-6">
      <AttributionStatsGrid stats={stats} />
      <AttributionFilters
        filter={filter}
        setFilter={setFilter}
        sortBy={sortBy}
        setSortBy={setSortBy}
      />
      <AttributionArticleTable
        articles={articles}
        loading={loading}
        enabledRoleTypes={enabledRoleTypes}
        onUpdateRoles={onUpdateRoles}
      />
      <Pagination
        page={page}
        totalPages={totalPages}
        onPageChange={setPage}
        totalEntries={articles?.total}
        pageSize={PAGE_SIZE}
      />
    </div>
  );
}
