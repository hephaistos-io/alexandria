import { useState } from "react";
import type { ClassificationLabel } from "../../types/classification";

interface LabelChipPickerProps {
  availableLabels: ClassificationLabel[];
  currentLabels: string[];
  onSave: (labels: string[]) => void;
  onCancel: () => void;
}

const MAX_LABELS = 3;

export function LabelChipPicker({
  availableLabels,
  currentLabels,
  onSave,
  onCancel,
}: LabelChipPickerProps) {
  const [selectedLabels, setSelectedLabels] = useState<string[]>(currentLabels);

  function toggleLabel(name: string) {
    setSelectedLabels((prev) => {
      if (prev.includes(name)) {
        return prev.filter((l) => l !== name);
      }
      if (prev.length >= MAX_LABELS) return prev;
      return [...prev, name];
    });
  }

  const atLimit = selectedLabels.length >= MAX_LABELS;

  return (
    <div className="flex items-center gap-2 flex-wrap py-2">
      {availableLabels.map((label) => {
        const isSelected = selectedLabels.includes(label.name);
        const isDisabled = atLimit && !isSelected;
        const colorHex = `#${label.color.replace(/^#/, "")}`;

        const selectedStyle = {
          backgroundColor: `${colorHex}1a`,
          color: colorHex,
          borderColor: `${colorHex}33`,
        };

        return (
          <button
            key={label.id}
            onClick={() => toggleLabel(label.name)}
            disabled={isDisabled}
            style={isSelected ? selectedStyle : undefined}
            className={`px-2 py-0.5 text-[9px] font-mono border uppercase transition-all ${
              isSelected
                ? ""
                : "bg-surface-container text-outline border-outline-variant/20"
            } ${isDisabled ? "opacity-30 pointer-events-none" : "cursor-pointer hover:opacity-80"}`}
          >
            {label.name}
          </button>
        );
      })}

      <button
        onClick={() => onSave(selectedLabels)}
        className="px-3 py-0.5 bg-primary text-on-primary font-mono text-[9px] font-bold uppercase tracking-widest active:scale-95"
      >
        SAVE
      </button>
      <button
        onClick={onCancel}
        className="px-3 py-0.5 bg-surface-container text-outline font-mono text-[9px] font-bold uppercase tracking-widest hover:text-on-surface transition-colors"
      >
        CANCEL
      </button>
    </div>
  );
}
