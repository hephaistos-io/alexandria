import { useState } from "react";
import { MaterialIcon } from "../shared/MaterialIcon";
import { SchemaHealthPanel, RegistryTable, DefineForm } from "../shared/schema";
import type { RelationType, CreateRelationTypePayload, UpdateRelationTypePayload } from "../../types/graph";

interface RelationTypesTabProps {
  relationTypes: RelationType[];
  loading: boolean;
  onCreateRelationType: (payload: CreateRelationTypePayload) => Promise<boolean>;
  onUpdateRelationType: (id: number, patch: UpdateRelationTypePayload) => Promise<boolean>;
  onDeleteRelationType: (id: number) => Promise<boolean>;
}

// Directed toggle — rendered as an extraField inside DefineForm.
// The caller owns the `directed` state; this is just the UI for it.
interface DirectedToggleProps {
  directed: boolean;
  onChange: (v: boolean) => void;
}

function DirectedToggle({ directed, onChange }: DirectedToggleProps) {
  return (
    <div className="flex items-center justify-between">
      <div>
        <label className="block font-mono text-[10px] text-outline uppercase mb-1">
          Directed Edge
        </label>
        <p className="font-mono text-[9px] text-outline-variant">
          Draws an arrow from source to target
        </p>
      </div>
      <button
        type="button"
        onClick={() => onChange(!directed)}
        className={`flex items-center gap-2 px-3 py-2 border transition-colors ${
          directed
            ? "bg-primary/10 border-primary/30 text-primary"
            : "bg-surface-container border-outline-variant/30 text-outline"
        }`}
      >
        <MaterialIcon name={directed ? "arrow_forward" : "swap_horiz"} className="text-sm" />
        <span className="font-mono text-[10px] uppercase">
          {directed ? "DIRECTED" : "UNDIRECTED"}
        </span>
      </button>
    </div>
  );
}

export function RelationTypesTab({
  relationTypes,
  loading,
  onCreateRelationType,
  onUpdateRelationType,
  onDeleteRelationType,
}: RelationTypesTabProps) {
  // `directed` lives here so we can close over it in the DefineForm onSubmit callback.
  const [directed, setDirected] = useState(true);

  return (
    <div className="flex-1 p-8 grid grid-cols-12 gap-8 overflow-y-auto">
      {/* Left column: health stats + form */}
      <div className="col-span-12 xl:col-span-4 flex flex-col gap-8">
        <SchemaHealthPanel
          items={relationTypes}
          panelId="RELATION_SCHEMA"
          primaryStatLabel="Total Types"
          secondaryStat={{
            label: "Directed",
            value: (items) => items.filter((rt) => rt.directed).length,
          }}
          getEnabled={(rt) => rt.enabled}
        />

        <DefineForm
          title="Define_Relation_Type"
          namePlaceholder="e.g. ALLIED_WITH"
          nameLabel="Relation Identity"
          extraFields={<DirectedToggle directed={directed} onChange={setDirected} />}
          onSubmit={(base) =>
            onCreateRelationType({ ...base, directed })
          }
        />
      </div>

      {/* Right column: registry table */}
      <div className="col-span-12 xl:col-span-8">
        <RegistryTable
          items={relationTypes}
          loading={loading}
          title="Relation_Registry"
          headerIcon="account_tree"
          emptyMessage="NO_ENTRIES — DEPLOY FIRST RELATION TYPE TO INITIALISE REGISTRY"
          getId={(rt) => rt.id}
          getName={(rt) => rt.name}
          getDescription={(rt) => rt.description}
          getColor={(rt) => rt.color}
          getEnabled={(rt) => rt.enabled}
          extraColumns={[
            {
              header: "Directed",
              align: "center",
              renderCell: (rt) =>
                rt.directed ? (
                  <MaterialIcon
                    name="arrow_forward"
                    className="text-sm text-primary"
                    title="Directed"
                  />
                ) : (
                  <MaterialIcon
                    name="swap_horiz"
                    className="text-sm text-outline"
                    title="Undirected"
                  />
                ),
            },
          ]}
          onToggleEnabled={(rt) => onUpdateRelationType(rt.id, { enabled: !rt.enabled })}
          onDelete={onDeleteRelationType}
        />
      </div>
    </div>
  );
}
