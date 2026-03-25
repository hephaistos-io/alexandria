import type { FilterStatus, SortField } from "../../types/labelling";

interface ArticleFiltersProps {
  filter: FilterStatus;
  setFilter: (f: FilterStatus) => void;
  sortBy: SortField;
  setSortBy: (s: SortField) => void;
}

const FILTER_OPTIONS: { value: FilterStatus; label: string }[] = [
  { value: "all", label: "ALL" },
  { value: "labelled", label: "LABELLED" },
  { value: "unlabelled", label: "NOT LABELLED" },
  { value: "auto_labelled", label: "AUTO LABELLED" },
];

export function ArticleFilters({ filter, setFilter, sortBy, setSortBy }: ArticleFiltersProps) {
  return (
    <section className="flex flex-col md:flex-row justify-between items-end gap-4">
      {/* Filter tabs */}
      <div className="flex gap-1 bg-surface-container p-1 ghost-border">
        {FILTER_OPTIONS.map(({ value, label }) => {
          const isActive = filter === value;
          return (
            <button
              key={value}
              onClick={() => setFilter(value)}
              className={
                isActive
                  ? "px-6 py-2 bg-surface-container-high text-primary font-mono text-[10px] font-bold uppercase tracking-widest border-b-2 border-primary"
                  : "px-6 py-2 text-outline font-mono text-[10px] font-bold uppercase tracking-widest hover:text-on-surface transition-colors"
              }
            >
              {label}
            </button>
          );
        })}
      </div>

      {/* Sort dropdown */}
      <div className="flex items-center gap-3 font-mono text-[10px] text-outline">
        <span>SORT_BY:</span>
        <select
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value as SortField)}
          className="bg-surface-container border-none text-[10px] py-1 pl-2 pr-8 focus:ring-0 text-on-surface uppercase font-mono"
        >
          <option value="date_ingested">DATE_INGESTED (DESC)</option>
          <option value="source_origin">SOURCE_ORIGIN</option>
        </select>
      </div>
    </section>
  );
}
