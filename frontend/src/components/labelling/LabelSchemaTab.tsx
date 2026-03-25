import { SchemaHealthPanel, DefineForm, RegistryTable } from "../shared/schema";
import type {
  ClassificationLabel,
  CreateLabelPayload,
  UpdateLabelPayload,
} from "../../types/classification";

interface LabelSchemaTabProps {
  labels: ClassificationLabel[];
  loading: boolean;
  onCreateLabel: (payload: CreateLabelPayload) => Promise<boolean>;
  onUpdateLabel: (id: number, patch: UpdateLabelPayload) => Promise<boolean>;
  onDeleteLabel: (id: number) => Promise<boolean>;
}

export function LabelSchemaTab({
  labels,
  loading,
  onCreateLabel,
  onUpdateLabel,
  onDeleteLabel,
}: LabelSchemaTabProps) {
  function handleToggleEnabled(label: ClassificationLabel) {
    void onUpdateLabel(label.id, { enabled: !label.enabled });
  }

  return (
    <div className="flex-1 p-8 grid grid-cols-12 gap-8 overflow-y-auto">
      <div className="col-span-12 xl:col-span-4 flex flex-col gap-8">
        <SchemaHealthPanel
          items={labels}
          panelId="SEC_DASH_01"
          primaryStatLabel="Total Labels"
          getEnabled={(l) => l.enabled}
        />
        <DefineForm
          title="Define_New_Entity"
          nameLabel="Label Identity"
          namePlaceholder="e.g. CYBER_PROTOCOL"
          onSubmit={onCreateLabel}
        />
      </div>

      <div className="col-span-12 xl:col-span-8">
        <RegistryTable
          items={labels}
          loading={loading}
          title="Registry_Interface"
          headerIcon="terminal"
          emptyMessage="NO_ENTRIES — DEPLOY FIRST ENTITY TO INITIALISE REGISTRY"
          getId={(l) => l.id}
          getName={(l) => l.name}
          getDescription={(l) => l.description}
          getColor={(l) => l.color}
          getEnabled={(l) => l.enabled}
          onToggleEnabled={handleToggleEnabled}
          onDelete={onDeleteLabel}
        />
      </div>
    </div>
  );
}
