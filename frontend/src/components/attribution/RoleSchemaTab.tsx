import { SchemaHealthPanel, RegistryTable, DefineForm } from "../shared/schema";
import type {
  EntityRoleType,
  CreateRoleTypePayload,
  UpdateRoleTypePayload,
} from "../../types/attribution";

interface RoleSchemaTabProps {
  roleTypes: EntityRoleType[];
  loading: boolean;
  onCreateRoleType: (payload: CreateRoleTypePayload) => Promise<boolean>;
  onUpdateRoleType: (id: number, patch: UpdateRoleTypePayload) => Promise<boolean>;
  onDeleteRoleType: (id: number) => Promise<boolean>;
}

export function RoleSchemaTab({
  roleTypes,
  loading,
  onCreateRoleType,
  onUpdateRoleType,
  onDeleteRoleType,
}: RoleSchemaTabProps) {
  function handleToggleEnabled(roleType: EntityRoleType) {
    onUpdateRoleType(roleType.id, { enabled: !roleType.enabled });
  }

  return (
    <div className="flex-1 p-8 grid grid-cols-12 gap-8 overflow-y-auto">
      {/* Left column: health stats + define form */}
      <div className="col-span-12 xl:col-span-4 flex flex-col gap-8">
        <SchemaHealthPanel
          items={roleTypes}
          panelId="ROLE_DASH_01"
          primaryStatLabel="Total Role Types"
          getEnabled={(rt) => rt.enabled}
        />
        <DefineForm
          title="Define_Role_Type"
          nameLabel="Role Identity"
          namePlaceholder="e.g. CONFLICT_ZONE"
          onSubmit={onCreateRoleType}
        />
      </div>

      {/* Right column: registry table */}
      <div className="col-span-12 xl:col-span-8">
        <RegistryTable
          items={roleTypes}
          loading={loading}
          title="Role_Registry"
          headerIcon="hub"
          emptyMessage="NO_ENTRIES — DEPLOY FIRST ROLE TYPE TO INITIALISE REGISTRY"
          getId={(rt) => rt.id}
          getName={(rt) => rt.name}
          getDescription={(rt) => rt.description}
          getColor={(rt) => rt.color}
          getEnabled={(rt) => rt.enabled}
          onToggleEnabled={handleToggleEnabled}
          onDelete={onDeleteRoleType}
        />
      </div>
    </div>
  );
}
