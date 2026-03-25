import { MaterialIcon } from "../shared/MaterialIcon";

const HEADER_ICONS = ["sensors", "monitoring", "settings_input_antenna"] as const;

export function Header() {
  return (
    <header className="fixed top-0 left-0 right-0 z-40 h-16 bg-surface-container-low ghost-border border-b flex items-center justify-between px-6">
      <div className="flex items-center gap-4">
        <span className="font-headline text-2xl font-black text-primary-container tracking-tighter">
          ALEXANDRIA
        </span>

        <div className="w-px h-8 bg-outline-variant/20" />

        <span className="font-label uppercase tracking-widest text-xs text-primary-container">
          SYSTEM_STATUS: ACTIVE_INGESTION
        </span>
      </div>

      <div className="flex items-center gap-2">
        {HEADER_ICONS.map((icon) => (
          <button
            key={icon}
            className="p-2 text-on-surface-variant hover:text-primary-container hover:bg-surface-container transition-colors"
            aria-label={icon.replace(/_/g, " ")}
          >
            <MaterialIcon name={icon} />
          </button>
        ))}

        <div className="w-px h-8 bg-outline-variant/20 mx-2" />

        <div className="flex items-center gap-3">
          <span className="font-mono text-xs text-outline">OPERATOR_ID: $REDACTED</span>
          <div className="w-8 h-8 bg-surface-container-highest" aria-hidden="true" />
        </div>
      </div>
    </header>
  );
}
