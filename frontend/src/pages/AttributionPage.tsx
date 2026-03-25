import { useState } from "react";
import { useAttribution } from "../hooks/useAttribution";
import { useEntityRoleTypes } from "../hooks/useEntityRoleTypes";
import { AttributionTab } from "../components/attribution/AttributionTab";
import { RoleSchemaTab } from "../components/attribution/RoleSchemaTab";
import { TabBar } from "../components/shared/TabBar";

type ActiveTab = "ROLE_ASSIGNMENT" | "ROLE_SCHEMA";

const TABS: { value: ActiveTab; label: string }[] = [
  { value: "ROLE_ASSIGNMENT", label: "ROLE_ASSIGNMENT" },
  { value: "ROLE_SCHEMA", label: "ROLE_SCHEMA" },
];

export function AttributionPage() {
  const [activeTab, setActiveTab] = useState<ActiveTab>("ROLE_ASSIGNMENT");

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
    updateRoles,
  } = useAttribution();

  const {
    roleTypes,
    loading: roleTypesLoading,
    error: roleTypesError,
    createRoleType,
    updateRoleType,
    deleteRoleType,
  } = useEntityRoleTypes();

  // Only enabled role types are offered in the assignment dropdown.
  const enabledRoleTypes = roleTypes.filter((rt) => rt.enabled);

  const combinedError = error ?? roleTypesError;

  return (
    <div className="flex flex-col h-full overflow-hidden">
      {/* Page header */}
      <div className="px-6 pt-6 pb-4 flex items-end justify-between border-b border-outline-variant/10">
        <div>
          <p className="font-mono text-[10px] text-outline uppercase tracking-widest mb-1">
            SYSTEM_CORE_LOG_11 // ATTRIBUTION_MANAGEMENT_V1
          </p>
          <h1 className="font-headline text-4xl font-black uppercase tracking-tighter text-on-surface">
            Attribution Core
          </h1>
        </div>
      </div>

      <TabBar tabs={TABS} activeTab={activeTab} onTabChange={setActiveTab} />

      {combinedError !== null && (
        <div className="mx-6 mt-4 px-4 py-2 bg-error/10 border border-error/30 font-mono text-[10px] text-error uppercase tracking-widest">
          ATTRIBUTION_API_ERROR: {combinedError}
        </div>
      )}

      {activeTab === "ROLE_ASSIGNMENT" && (
        <AttributionTab
          stats={stats}
          articles={articles}
          loading={loading}
          page={page}
          setPage={setPage}
          filter={filter}
          setFilter={setFilter}
          sortBy={sortBy}
          setSortBy={setSortBy}
          enabledRoleTypes={enabledRoleTypes}
          onUpdateRoles={updateRoles}
        />
      )}

      {activeTab === "ROLE_SCHEMA" && (
        <RoleSchemaTab
          roleTypes={roleTypes}
          loading={roleTypesLoading}
          onCreateRoleType={createRoleType}
          onUpdateRoleType={updateRoleType}
          onDeleteRoleType={deleteRoleType}
        />
      )}
    </div>
  );
}
